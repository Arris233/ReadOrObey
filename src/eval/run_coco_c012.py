"""Run member 1's independent COCO Task/Read probes with resumable JSONL logs.

No API call is made without --execute. Configure the exact verified provider,
model ID, endpoint and key in the environment/CLI before paid experiments.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import time

from PIL import Image
from src.common.prompts import build_messages, coco_read_hint

ROOT = Path(__file__).resolve().parents[2]
def load_jobs(experiment: str, split: str, provisional: bool) -> list[dict]:
    suffix = ".provisional" if provisional else ""
    names = (["coco_c012_manifest"] if experiment == "main" else
             ["coco_c2_ablation_manifest"] if experiment == "ablation" else
             ["coco_c012_manifest", "coco_c2_ablation_manifest"])
    jobs = []
    for name in names:
        path = ROOT / "data/manifests" / f"{name}{suffix}.jsonl"
        if not path.is_file():
            raise FileNotFoundError(f"Missing {path}; run render_coco_c012.py first")
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["split"] != split:
                continue
            task_messages = build_messages("coco_task", {
                f"opt_{letter}": row["options"][letter] for letter in "ABCD"})
            jobs.append({**row, "probe": "task", "messages": task_messages,
                         "prompt": task_messages[-1]["content"]})
            if row["variant"].startswith("C2_"):
                read_messages = build_messages("coco_read", {
                    "overlay_hint": coco_read_hint(row["variant"])})
                jobs.append({**row, "probe": "read", "messages": read_messages,
                             "prompt": read_messages[-1]["content"]})
    return jobs


def request_key(job: dict, model: str, provider: str, base_url: str) -> str:
    payload = {key: job[key] for key in ("split", "image_id", "variant", "probe", "sha256", "messages")}
    payload.update(model=model, provider=provider, base_url=base_url)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def image_data(path: Path) -> str:
    with Image.open(path) as image:
        if image.size != (768, 768):
            raise ValueError(f"Unexpected image dimensions: {path}: {image.size}")
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def load_successes(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    keys = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("status") == "ok":
                keys.add(row["request_key"])
    return keys


def run(args: argparse.Namespace) -> None:
    jobs = load_jobs(args.experiment, args.split, args.provisional)
    if args.limit:
        jobs = jobs[:args.limit]
    output = Path(args.output) if args.output else ROOT / "runs" / f"coco_c012_{args.model.replace('/', '_')}.jsonl"
    successes = load_successes(output)
    pending = [(job, request_key(job, args.model, args.provider, args.base_url)) for job in jobs]
    pending = [(job, key) for job, key in pending if key not in successes]
    print(json.dumps({"total": len(jobs), "cached": len(jobs) - len(pending),
                      "pending": len(pending), "output": str(output)}, ensure_ascii=False))
    if not args.execute or not pending:
        return
    key = os.environ.get(args.api_key_env)
    if not key:
        raise ValueError(f"Missing API key environment variable {args.api_key_env}")
    from openai import OpenAI
    client = OpenAI(api_key=key, base_url=args.base_url, max_retries=0, timeout=args.timeout)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as stream:
        for job, cache_key in pending:
            path = ROOT / job["image_path"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != job["sha256"]:
                raise ValueError(f"Image hash mismatch: {path}")
            image_url = image_data(path)
            started = time.monotonic()
            error = None
            for attempt in range(args.retries + 1):
                try:
                    messages = [dict(message) for message in job["messages"]]
                    messages[-1]["content"] = [
                        {"type": "text", "text": job["prompt"]},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ]
                    response = client.chat.completions.create(
                        model=args.model, temperature=0, top_p=1,
                        max_tokens=64, stream=False, messages=messages,
                    )
                    message = response.choices[0].message
                    record = {"status": "ok", "raw_content": message.content,
                              "reasoning_content": getattr(message, "reasoning_content", None),
                              "response_id": response.id, "response_model": response.model,
                              "usage": response.usage.model_dump() if response.usage else None}
                    break
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    record = {"status": "error", "error": error}
                    if attempt < args.retries:
                        time.sleep(min(args.max_backoff, 2 ** attempt))
            record.update({key: job[key] for key in
                           ("split", "image_id", "variant", "probe", "sha256", "image_path",
                            "gold_option", "wrong_option", "text")})
            record.update(request_key=cache_key, provider=args.provider, base_url=args.base_url,
                          model=args.model, prompt=job["prompt"], elapsed_seconds=round(time.monotonic() - started, 3))
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
            if args.interval:
                time.sleep(args.interval)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", choices=("main", "ablation", "all"), default="main")
    parser.add_argument("--split", choices=("pilot", "formal"), default="pilot")
    parser.add_argument("--provisional", action="store_true", help="only for pilot QA; never formal claims")
    parser.add_argument("--model", required=True, help="verified provider model ID")
    parser.add_argument("--provider", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--output")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--execute", action="store_true", help="actually send requests; default prints request count")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--max-backoff", type=float, default=30)
    parser.add_argument("--interval", type=float, default=0)
    args = parser.parse_args()
    if args.split == "formal" and args.provisional:
        parser.error("Formal inference requires a frozen manifest")
    run(args)


if __name__ == "__main__":
    main()
