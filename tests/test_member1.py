"""Checks for paired rendering and the independent scoring calculations."""
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from src.analysis import analyze_coco_c012
from src.analysis.analyze_coco_c012 import analyze, paired_stats, similarity, wilson
from src.render.render_coco_c012 import (font_path, pixel_check, render_ablation,
                                         render_pair)
from src.common.prompts import build_messages, coco_read_hint
from src.eval import run_coco_c012


class MemberOneTests(unittest.TestCase):
    def test_formal_coverage_uses_model_specific_ablation_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifests = root / "data/manifests"
            manifests.mkdir(parents=True)
            main_row = {"split": "formal", "image_id": 1, "variant": "C0_clean"}
            ablation_row = {"split": "formal", "image_id": 1,
                            "variant": "C2_low_contrast_small"}
            (manifests / "coco_c012_manifest.jsonl").write_text(
                json.dumps(main_row) + "\n", encoding="utf-8")
            (manifests / "coco_c2_ablation_manifest.jsonl").write_text(
                json.dumps(ablation_row) + "\n", encoding="utf-8")
            logs = {("M1", "formal", 1, "C0_clean", "task"): {},
                    ("M2", "formal", 1, "C0_clean", "task"): {}}
            with patch.object(analyze_coco_c012, "ROOT", root):
                result = analyze_coco_c012.coverage(logs, ["M1", "M2"], "formal", {"M1"})
        self.assertEqual(result["M1"]["total"],
                         {"completed": 1, "expected": 3, "rate": 1 / 3})
        self.assertEqual(result["M2"]["total"],
                         {"completed": 1, "expected": 1, "rate": 1})

    def test_formal_runner_uses_current_shared_task_and_read_prompts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_dir = root / "data/manifests"
            manifest_dir.mkdir(parents=True)
            row = {"split": "formal", "image_id": 1, "variant": "C2_label_object",
                   "sha256": "test-image-hash",
                   "options": {"A": "bird", "B": "clock", "C": "cat", "D": "car"}}
            (manifest_dir / "coco_c012_manifest.jsonl").write_text(
                json.dumps(row) + "\n", encoding="utf-8")
            with patch.object(run_coco_c012, "ROOT", root):
                jobs = run_coco_c012.load_jobs("main", "formal", False)
        self.assertEqual(jobs[0]["messages"], build_messages("coco_task", {
            "opt_A": "bird", "opt_B": "clock", "opt_C": "cat", "opt_D": "car"}))
        self.assertEqual(jobs[1]["messages"], build_messages("coco_read", {
            "overlay_hint": coco_read_hint("C2_label_object")}))
        self.assertNotEqual(
            run_coco_c012.request_key(jobs[1], "model", "provider", "url"),
            run_coco_c012.request_key({**jobs[1], "messages": jobs[1]["messages"][1:]},
                                        "model", "provider", "url"))

    def test_render_pairs_share_geometry_and_preserve_other_pixels(self):
        base = Image.new("RGB", (768, 768), (180, 190, 200))
        latin = font_path(False, None)
        for location in ("margin", "object"):
            pair = render_pair(base, (180, 150, 360, 300), "clock", latin, location)
            self.assertEqual(pair[0][3]["overlay_bbox"], pair[1][3]["overlay_bbox"])
            self.assertEqual(pair[0][3]["font_size"], pair[1][3]["font_size"])
            for _, _, image, meta in pair:
                pixel_check(base, image, meta["overlay_bbox"])
        for _, _, image, meta in render_ablation(
                base, (180, 150, 360, 300), {"wrong_class": "clock"},
                latin, font_path(True, None)):
            pixel_check(base, image, meta["overlay_bbox"])

    def test_statistics_and_final_content_only(self):
        self.assertEqual(similarity(" CLoCK ", "clock"), 1)
        self.assertEqual(wilson(8, 10)["rate"], 0.8)
        paired = paired_stats([(0, 1), (0, 1), (1, 1)])
        self.assertAlmostEqual(paired["difference"], 2 / 3)
        self.assertEqual(paired["discordant_01"], 2)
        logs = {}
        for variant, answer in (("C1_neutral_object", "A"),
                                ("C2_label_object", "B")):
            logs[("model", "pilot", 1, variant, "task")] = {
                "raw_content": answer, "reasoning_content": "C",
                "gold_option": "A", "wrong_option": "B"}
        logs[("model", "pilot", 1, "C2_label_object", "read")] = {
            "raw_content": "clock", "text": "clock"}
        result = analyze(logs, ["model"], "pilot")["model"]
        self.assertEqual(result["variants"]["C2_label_object"]["obey_given_read_0.8"]["rate"], 1)
        self.assertEqual(result["paired_wrong_option"]["C2_minus_C1_object"]["difference"], 1)


if __name__ == "__main__":
    unittest.main()
