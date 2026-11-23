"""Audit COCO val2017 and build a deterministic, reviewable candidate pool.

This script never marks images as human-approved or freezes an experiment split.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[2]
COCO = ROOT / "data/raw/coco"
OUT = ROOT / "reports/coco"
ANNOTATIONS = COCO / "annotations/instances_val2017.json"
SEED = "20261123"


def digest(image_id: int) -> str:
    return hashlib.sha256(f"{SEED}|coco|{image_id}".encode()).hexdigest()


def find_image(name: str) -> Path | None:
    for folder in (COCO / "val2017", COCO / "val2017_sample"):
        path = folder / name
        if path.is_file():
            return path
    return None


def make_contact_sheets(rows: list[dict], categories: dict[int, dict]) -> None:
    available = [r for r in rows if find_image(r["file_name"])]
    for batch_start in range(0, len(available), 40):
        sheet = Image.new("RGB", (1200, 8 * 175), "white")
        draw = ImageDraw.Draw(sheet)
        for j, row in enumerate(available[batch_start:batch_start + 40]):
            source = find_image(row["file_name"])
            with Image.open(source) as im:
                thumb = ImageOps.contain(im.convert("RGB"), (232, 145))
            x, y = (j % 5) * 240, (j // 5) * 175
            sheet.paste(thumb, (x + (240 - thumb.width) // 2, y))
            draw.text((x + 3, y + 147), f"{batch_start + j + 1:03d} {row['image_id']}", fill="black")
            draw.text((x + 3, y + 160), categories[row["category_id"]]["name"][:23], fill="black")
        sheet.save(OUT / f"contact_{batch_start // 40 + 1:02d}.jpg", quality=88)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = json.loads(ANNOTATIONS.read_text(encoding="utf-8"))
    images = {im["id"]: im for im in data["images"]}
    categories = {cat["id"]: cat for cat in data["categories"]}
    by_image = defaultdict(list)
    for ann in data["annotations"]:
        if ann["iscrowd"] == 0:
            by_image[ann["image_id"]].append(ann)

    funnel = Counter()
    grouped = defaultdict(list)
    all_rows = []
    for image_id, image in images.items():
        funnel["all_images"] += 1
        anns = by_image[image_id]
        if not anns:
            continue
        funnel["has_noncrowd_instance"] += 1
        pixel_area = image["width"] * image["height"]
        ranked = sorted(anns, key=lambda a: a["bbox"][2] * a["bbox"][3], reverse=True)
        top = ranked[0]
        top_ratio = top["bbox"][2] * top["bbox"][3] / pixel_area
        second_other = max((a["bbox"][2] * a["bbox"][3] / pixel_area
                            for a in ranked if a["category_id"] != top["category_id"]), default=0.0)
        short = min(image["width"], image["height"])
        aspect = max(image["width"], image["height"]) / short
        if not (0.25 <= top_ratio <= 0.85):
            continue
        funnel["primary_bbox_25_to_85pct"] += 1
        if not second_other < 0.12:
            continue
        funnel["second_other_category_lt_12pct"] += 1
        if not (short >= 320 and aspect <= 2):
            continue
        funnel["resolution_and_aspect"] += 1
        row = {
            "image_id": image_id, "file_name": image["file_name"],
            "width": image["width"], "height": image["height"],
            "category_id": top["category_id"], "category": categories[top["category_id"]]["name"],
            "supercategory": categories[top["category_id"]]["supercategory"],
            "main_bbox": top["bbox"], "main_bbox_ratio": round(top_ratio, 5),
            "second_other_bbox_ratio": round(second_other, 5),
            "annotated_category_ids": sorted({a["category_id"] for a in anns}),
            "image_available": bool(find_image(image["file_name"])),
            "selection_hash": digest(image_id),
        }
        all_rows.append(row)
        grouped[row["category_id"]].append(row)

    for rows in grouped.values():
        rows.sort(key=lambda r: r["selection_hash"])
    pool = []
    for rank in range(6):
        for category_id in sorted(grouped):
            if len(grouped[category_id]) > rank:
                pool.append(grouped[category_id][rank])
                if len(pool) == 200:
                    break
        if len(pool) == 200:
            break
    funnel["candidate_pool"] = len(pool)
    stats = {
        "source": "COCO 2017 val instances annotations",
        "images": len(images), "annotations": len(data["annotations"]),
        "categories": len(categories), "funnel": dict(funnel),
        "eligible_categories": len(grouped),
        "eligible_supercategories": dict(Counter(r["supercategory"] for r in all_rows)),
        "pool_supercategories": dict(Counter(r["supercategory"] for r in pool)),
        "pool_categories": len({r["category_id"] for r in pool}),
        "pool_images_available": sum(r["image_available"] for r in pool),
        "full_archive_present": (COCO / "val2017.zip").is_file(),
    }
    (OUT / "audit_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "candidate_pool.json").write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")
    review = OUT / "coco_review.csv"
    if not review.exists():
        with review.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["rank", "image_id", "category", "supercategory", "main_bbox_ratio",
                             "second_other_bbox_ratio", "available", "decision", "reason", "notes"])
            for i, row in enumerate(pool, 1):
                writer.writerow([i, row["image_id"], row["category"], row["supercategory"],
                                 row["main_bbox_ratio"], row["second_other_bbox_ratio"],
                                 row["image_available"], "pending", "", ""])
    make_contact_sheets(pool, categories)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
