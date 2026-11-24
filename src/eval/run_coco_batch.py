"""Plan and run COCO Task/Read probes against a rendered JSONL manifest."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from src.common.api_client import Endpoint, EvalRequest, Transport, run_request
from src.common.prompts import build_messages

ROOT = Path(__file__).resolve().parents[2]
MODEL_SUFFIXES = {
    "M1": "8B-Instruct",
    "M2": "8B-Thinking",
    "M3": "32B-Instruct",
    "M4": "32B-Thinking",
}
PROBES = {"task": "coco_task", "read": "coco_read"}
KEY_ENV = "SILICONFLOW_API_KEY"


def load_requests(manifest: Path, split: str, image_root: Path) -> list[EvalRequest]:
    requests = []
    sample_ids = set()
    with manifest.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict) or row.get("split") not in ("pilot", "formal", "reserve"):
                    raise ValueError("expected an object with split pilot, formal, or reserve")
                if row["split"] != split:
                    continue
                image_id, variant = row.get("image_id"), row.get("variant")
                if type(image_id) is not int or image_id <= 0:
                    raise ValueError("image_id must be a positive integer")
                if not isinstance(variant, str) or not variant.strip() or ":" in variant:
                    raise ValueError("variant must be non-empty text without colons")
                sample_id = f"{split}:{image_id}:{variant}"
                if sample_id in sample_ids:
                    raise ValueError(f"duplicate sample: {sample_id}")
                sample_ids.add(sample_id)

                image_path = row.get("image_path")
                if not isinstance(image_path, str) or not image_path.strip():
                    raise ValueError("image_path must be non-empty text")
                probes = row.get("probes")
                if (
                    not isinstance(probes, list)
                    or not probes
                    or any(probe not in ("task", "read") for probe in probes)
                    or len(set(probes)) != len(probes)
                ):
                    raise ValueError("probes must list task and/or read, without duplicates")
                options = row.get("options")
                if "task" in probes and (
                    not isinstance(options, dict)
                    or options.keys() != set("ABCD")
                    or any(not isinstance(value, str) or not value.strip() for value in options.values())
                ):
                    raise ValueError("task requires non-empty options A–D")
                for kind in probes:
                    probe = PROBES[kind]
                    variables = {f"opt_{letter}": options[letter] for letter in "ABCD"} if kind == "task" else {}
                    messages = build_messages(probe, variables)
                    requests.append(EvalRequest(sample_id, probe, messages, image=image_root / image_path))
            except ValueError as error:
                raise ValueError(f"{manifest}:{line_number}: {error}") from error

    if not requests:
        raise ValueError(f"No samples found for split {split}")
    return requests


def main(argv: list[str] | None = None, *, transport: Transport | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path, help="Rendered COCO JSONL manifest")
    parser.add_argument("--split", required=True, choices=("pilot", "formal"))
    parser.add_argument("--model", required=True, action="append", choices=MODEL_SUFFIXES, help="Repeat to select models")
    parser.add_argument("--image-root", type=Path, default=ROOT, help="Base directory for relative image paths")
    parser.add_argument("--log", type=Path, help="JSONL results path (required with --execute)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Print the plan without creating a log or calling an API")
    mode.add_argument("--execute", action="store_true", help="Run requests using the SiliconFlow API")
    args = parser.parse_args(argv)

    try:
        requests = load_requests(args.manifest, args.split, args.image_root)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    models = list(dict.fromkeys(args.model))
    counts = Counter(request.probe for request in requests)
    sample_ids = {request.sample_id for request in requests}
    summary = {
        "split": args.split,
        "models": models,
        "image_ids": sorted({int(sample_id.split(":")[1]) for sample_id in sample_ids}),
        "samples": len(sample_ids),
        "probes": {probe: count * len(models) for probe, count in counts.items()},
        "requests": len(requests) * len(models),
    }
    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    if args.log is None:
        parser.error("--execute requires --log")
    if args.log.resolve() == args.manifest.resolve():
        parser.error("--log must differ from --manifest")
    for image_path in dict.fromkeys(request.image for request in requests):
        if not Path(image_path).is_file():
            parser.error(f"missing image: {image_path}")
        if args.log.resolve() == Path(image_path).resolve():
            parser.error("--log must differ from input images")
    if transport is None and not os.environ.get(KEY_ENV, "").strip():
        parser.error(f"{KEY_ENV} is missing from the environment")

    kwargs = {"transport": transport} if transport is not None else {}
    failed = 0
    for model in models:
        suffix = MODEL_SUFFIXES[model]
        endpoint = Endpoint(
            "siliconflow", f"Qwen/Qwen3-VL-{suffix}", "https://api.siliconflow.cn/v1",
            "cn", KEY_ENV, thinking=suffix.endswith("Thinking"),
        )
        for request in requests:
            result = run_request(request, endpoint, args.log, **kwargs)
            failed += result["status"] != "ok"

    print(json.dumps({**summary, "ok": summary["requests"] - failed, "failed": failed}, ensure_ascii=False))
    return int(failed > 0)


if __name__ == "__main__":
    raise SystemExit(main())
