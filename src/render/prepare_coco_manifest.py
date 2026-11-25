"""Build a *provisional* paired COCO split from the reviewed candidate pool."""
from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports/coco"
POOL = REPORT / "candidate_pool.json"
REVIEW = REPORT / "coco_review.csv"
OUTPUT = REPORT / "coco_base_120.provisional.json"
PILOT_GROUPS = ("animal", "vehicle", "food", "indoor")


def hashed_option(image_id: int, category_id: int) -> str:
    return hashlib.sha256(f"20261123|{image_id}|{category_id}".encode()).hexdigest()


def main() -> None:
    pool = json.loads(POOL.read_text(encoding="utf-8"))
    with REVIEW.open(encoding="utf-8-sig", newline="") as f:
        review = {int(r["image_id"]): r for r in csv.DictReader(f)}
    accepted = [r for r in pool
                if review.get(r["image_id"], {}).get("decision", "").strip().lower() == "accept"]
    pilot = []
    for group in PILOT_GROUPS:
        candidates = [r for r in accepted if r["supercategory"] == group]
        if len(candidates) < 3:
            raise ValueError(f"Insufficient pilot candidates in {group}")
        pilot.extend(candidates[:3])
    pilot_ids = {r["image_id"] for r in pilot}
    formal = [r for r in accepted if r["image_id"] not in pilot_ids][:120]
    reserve = [r for r in accepted if r["image_id"] not in pilot_ids][120:132]
    if len(formal) != 120 or len(reserve) != 12:
        raise ValueError("Need 144 accepted candidates: 12 pilot, 120 formal and 12 reserve")
    category_names = {r["category_id"]: r["category"] for r in pool}
    # The pool need not contain every COCO category; use the annotation catalog.
    annotations = json.loads((ROOT / "data/raw/coco/annotations/instances_val2017.json").read_text(encoding="utf-8"))
    category_names.update({c["id"]: c["name"] for c in annotations["categories"]})
    options = sorted(category_names)
    records = []
    for split, group in (("pilot", pilot), ("formal", formal), ("reserve", reserve)):
        for i, row in enumerate(group):
            forbidden = set(row["annotated_category_ids"])
            decoys = sorted((x for x in options if x not in forbidden),
                            key=lambda x: hashed_option(row["image_id"], x))[:3]
            true_slot = i % 4
            other_slots = [j for j in range(4) if j != true_slot]
            wrong_slot = other_slots[i % 3]
            slots = [None] * 4
            slots[true_slot] = row["category_id"]
            slots[wrong_slot] = decoys[0]
            remaining = [j for j in other_slots if j != wrong_slot]
            for j, cat in zip(remaining, decoys[1:]):
                slots[j] = cat
            records.append({
                "split": split, "image_id": row["image_id"],
                "image_path": f"data/raw/coco/val2017/{row['file_name']}",
                "category_id": row["category_id"], "category": row["category"],
                "supercategory": row["supercategory"], "main_bbox": row["main_bbox"],
                "main_bbox_ratio": row["main_bbox_ratio"],
                "second_other_bbox_ratio": row["second_other_bbox_ratio"],
                "wrong_class_id": decoys[0], "wrong_class": category_names[decoys[0]],
                "options": {chr(65 + j): category_names[cat] for j, cat in enumerate(slots)},
                "answer": chr(65 + true_slot), "wrong_answer": chr(65 + wrong_slot),
                "visual_review": review[row["image_id"]]["decision"],
                "mcq_visual_review": "pending",
            })
    output = {
        "status": "provisional; do not use for formal model evaluation",
        "seed": 20261123, "split_counts": dict(Counter(r["split"] for r in records)),
        "records": records,
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"path": str(OUTPUT), "split_counts": output["split_counts"],
                      "pending_visual_review": sum(r["visual_review"] == "pending" for r in records),
                      "formal_category_count": len({r["category_id"] for r in records if r["split"] == "formal"}),
                      "formal_supercategories": dict(Counter(r["supercategory"] for r in records if r["split"] == "formal")),
                      "formal_answer_balance": dict(Counter(r["answer"] for r in records if r["split"] == "formal"))},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
