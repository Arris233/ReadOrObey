"""Review and freeze the shared COCO MCQ split once human checks are complete.

The existing audit_coco.py and prepare_coco_manifest.py generate the candidate
pool and a provisional split. This command is deliberately strict: pending
reviews cannot silently become formal experiment data.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports/coco"
PROVISIONAL = REPORT / "coco_base_120.provisional.json"
REVIEW = REPORT / "coco_review.csv"
MCQ_REVIEW = REPORT / "coco_mcq_review.csv"
OUTPUT = ROOT / "data/manifests/coco_base_120.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_mcq_review(records: list[dict], sync: bool = False) -> None:
    if MCQ_REVIEW.exists() and not sync:
        raise FileExistsError(f"Review file already exists; refusing to overwrite {MCQ_REVIEW}")
    columns = ("split", "image_id", "category", "wrong_class", "A", "B", "C", "D",
               "answer", "wrong_answer", "decision", "reason", "notes")
    previous = {}
    if MCQ_REVIEW.exists():
        with MCQ_REVIEW.open(encoding="utf-8-sig", newline="") as stream:
            previous = {int(row["image_id"]): row for row in csv.DictReader(stream)}
    target = MCQ_REVIEW.with_suffix(".csv.tmp")
    preserved = 0
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in records:
            record = {**{key: row.get(key, "") for key in columns}, **row["options"]}
            old = previous.get(row["image_id"])
            stable = (old is not None and
                      all(old.get(key) == record.get(key) for key in
                          ("category", "wrong_class", "A", "B", "C", "D", "answer", "wrong_answer")))
            if stable:
                record.update({key: old.get(key, "") for key in ("decision", "reason", "notes")})
                preserved += 1
            else:
                record.update(decision="pending", reason="", notes="")
            writer.writerow(record)
    target.replace(MCQ_REVIEW)
    print(f"{MCQ_REVIEW}: {len(records)} rows, {preserved} unchanged reviews preserved")


def validate(records: list[dict], review: dict[int, dict], mcq_review: dict[int, dict], root: Path) -> dict:
    errors = []
    counts = Counter(row["split"] for row in records)
    if counts != {"pilot": 12, "formal": 120, "reserve": 12}:
        errors.append(f"split counts: {dict(counts)}")
    ids = [row["image_id"] for row in records]
    if len(ids) != len(set(ids)):
        errors.append("duplicate image IDs")
    formal = [row for row in records if row["split"] == "formal"]
    category_counts = Counter(row["category_id"] for row in formal)
    if len(category_counts) < 30 or max(category_counts.values(), default=0) > 6:
        errors.append("formal category coverage or per-category cap failed")
    if Counter(row["answer"] for row in formal) != dict.fromkeys("ABCD", 30):
        errors.append("formal answer letters must be balanced 30 each")
    for row in records:
        image_id = row["image_id"]
        review_row = review.get(image_id, {})
        if review_row.get("decision", "").strip().lower() != "accept":
            errors.append(f"{image_id}: image review is not accept")
        mcq = mcq_review.get(image_id, {})
        if mcq.get("decision", "").strip().lower() != "accept":
            errors.append(f"{image_id}: MCQ review is not accept")
        if mcq and (any(mcq.get(letter) != row.get("options", {}).get(letter) for letter in "ABCD") or
                    mcq.get("wrong_class") != row.get("wrong_class") or
                    mcq.get("answer") != row.get("answer")):
            errors.append(f"{image_id}: MCQ review row differs from provisional options")
        path = root / row["image_path"]
        if not path.is_file():
            errors.append(f"{image_id}: missing source image {path}")
        opts = row.get("options", {})
        if set(opts) != set("ABCD") or len(set(opts.values())) != 4:
            errors.append(f"{image_id}: invalid options")
            continue
        if opts.get(row["answer"]) != row["category"]:
            errors.append(f"{image_id}: answer does not match category")
        if opts.get(row["wrong_answer"]) != row["wrong_class"]:
            errors.append(f"{image_id}: wrong answer does not match wrong class")
        if row["answer"] == row["wrong_answer"]:
            errors.append(f"{image_id}: answer equals wrong answer")
    return {"counts": dict(counts), "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate without writing the frozen manifest")
    parser.add_argument("--export-mcq-review", action="store_true", help="create the MCQ review CSV once")
    parser.add_argument("--sync-mcq-review", action="store_true",
                        help="rebuild MCQ review CSV after the split changes, preserving unchanged entries")
    parser.add_argument("--pilot-approved", action="store_true",
                        help="assert that the human-reviewed Pilot gates passed")
    args = parser.parse_args()
    data = json.loads(PROVISIONAL.read_text(encoding="utf-8"))
    if args.export_mcq_review or args.sync_mcq_review:
        export_mcq_review(data["records"], sync=args.sync_mcq_review)
        return
    with REVIEW.open(encoding="utf-8-sig", newline="") as stream:
        review = {int(row["image_id"]): row for row in csv.DictReader(stream)}
    if not MCQ_REVIEW.is_file():
        parser.error(f"Missing {MCQ_REVIEW}; run --export-mcq-review and complete the review")
    with MCQ_REVIEW.open(encoding="utf-8-sig", newline="") as stream:
        mcq_review = {int(row["image_id"]): row for row in csv.DictReader(stream)}
    result = validate(data["records"], review, mcq_review, ROOT)
    if result["errors"]:
        print(json.dumps({"valid": False, "error_count": len(result["errors"]),
                          "first_errors": result["errors"][:20]}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    if args.check:
        print(json.dumps({"valid": True, "counts": result["counts"]}))
        return
    if not args.pilot_approved:
        parser.error("Pass --pilot-approved only after reviewing Pilot results and gates")
    if OUTPUT.exists():
        parser.error(f"Frozen manifest already exists: {OUTPUT}; preserve its version")
    frozen = {
        "status": "frozen after human image and MCQ review",
        "seed": data["seed"],
        "split_counts": {"pilot": 12, "formal": 120},
        "source_sha256": {"provisional": sha256(PROVISIONAL), "review_csv": sha256(REVIEW),
                          "mcq_review_csv": sha256(MCQ_REVIEW)},
        "records": [{**row, "visual_review": "accept", "mcq_visual_review": "accept"}
                    for row in data["records"]
                    if row["split"] in ("pilot", "formal")],
        "reserve_records": [{**row, "visual_review": "accept", "mcq_visual_review": "accept"}
                            for row in data["records"]
                            if row["split"] == "reserve"],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Frozen {len(frozen['records'])} records at {OUTPUT}")


if __name__ == "__main__":
    main()
