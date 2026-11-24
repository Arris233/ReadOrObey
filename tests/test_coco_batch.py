import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock

from PIL import Image


class CocoBatchTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.manifest = self.root / "rendered.jsonl"
        self.log = self.root / "runs" / "batch.jsonl"
        self.row = {
            "split": "pilot",
            "image_id": 10,
            "variant": "overlay",
            "image_path": "sample.png",
            "options": {"A": "cat", "B": "dog", "C": "bus", "D": "chair"},
            "probes": ["task", "read"],
        }

    def write_manifest(self, *rows):
        self.manifest.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def arguments(self, *extra):
        return [
            "--manifest", str(self.manifest), "--split", "pilot", "--model", "M1",
            "--image-root", str(self.root), "--log", str(self.log), *extra,
        ]

    def test_dry_run_filters_split_and_counts_each_model(self):
        from src.eval.run_coco_batch import main

        self.write_manifest(self.row, dict(self.row, split="formal", image_id=11))
        transport = Mock()
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(self.arguments("--dry-run", "--model", "M2"), transport=transport)

        self.assertEqual(result, 0)
        summary = json.loads(output.getvalue())
        self.assertEqual(summary["requests"], 4)
        self.assertEqual(summary["image_ids"], [10])
        self.assertEqual(summary["probes"], {"coco_task": 2, "coco_read": 2})
        transport.assert_not_called()
        self.assertFalse(self.log.exists())

    def test_execute_writes_rows_and_only_retries_failed_probe_on_resume(self):
        from src.eval.run_coco_batch import main

        self.write_manifest(self.row)
        Image.new("RGB", (768, 768), "white").save(self.root / "sample.png")
        transport = Mock(side_effect=[
            {"content": "A"}, RuntimeError("simulated failure"), {"content": "sample text"},
        ])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(self.arguments("--execute"), transport=transport), 1)
            self.assertEqual(main(self.arguments("--execute"), transport=transport), 0)

        rows = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual(transport.call_count, 3)
        self.assertEqual([row["status"] for row in rows], ["ok", "error", "ok"])
        self.assertEqual({row["sample_id"] for row in rows}, {"pilot:10:overlay"})
        self.assertEqual({row["probe"] for row in rows}, {"coco_task", "coco_read"})
        requests = [call.args[1][-1]["content"][0]["text"] for call in transport.call_args_list]
        self.assertIn("A. cat", requests[0])
        self.assertIn("Transcribe", requests[1])
        self.assertEqual(requests[1], requests[2])

    def test_invalid_or_missing_inputs_never_start_requests(self):
        from src.eval.run_coco_batch import main

        transport = Mock()
        for rows, mode, reason in (
            ((self.row, self.row), "--dry-run", "duplicate"),
            ((dict(self.row, options={"A": "cat"}),), "--dry-run", "options"),
            ((self.row,), "--execute", "missing image"),
        ):
            with self.subTest(reason=reason):
                self.write_manifest(*rows)
                errors = io.StringIO()
                with redirect_stderr(errors):
                    with self.assertRaises(SystemExit) as raised:
                        main(self.arguments(mode), transport=transport)
                self.assertEqual(raised.exception.code, 2)
                self.assertIn(reason, errors.getvalue())

        transport.assert_not_called()
        self.assertFalse(self.log.exists())
