"""Create a visual review sheet and an editable decision CSV for Mind2Web."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "mind2web"
MANIFEST = REPORT / "mind2web_manifest.provisional.jsonl"


def main() -> None:
    records = [json.loads(line) for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line]
    with (REPORT / "visual_review.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=["sample_id", "split", "source_split", "annotation_id",
                                                    "task_self_contained", "target_clear", "four_boxes_correct",
                                                    "button_no_occlusion", "dom_text_matches", "decision", "notes"])
        writer.writeheader()
        for r in records:
            writer.writerow({"sample_id": r["sample_id"], "split": r["split"],
                             "source_split": r["source_split"], "annotation_id": r["annotation_id"]})
    # Review all Pilot steps and a deterministic spread of ten Formal steps.
    chosen = [r for r in records if r["split"] == "pilot"]
    formal = [r for r in records if r["split"] == "formal"]
    chosen.extend(formal[i] for i in range(0, 60, 6) if i < len(formal))
    label_font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
    for page in range(0, len(chosen), 10):
        subset = chosen[page:page + 10]
        sheet = Image.new("RGB", (2048, 1840), "white")
        draw = ImageDraw.Draw(sheet)
        for i, item in enumerate(subset):
            x = (i % 4) * 512
            y = (i // 4) * 368
            image = Image.open(ROOT / item["image_paths"]["A2"])
            sheet.paste(image.resize((512, 340)), (x, y + 24))
            draw.text((x + 4, y + 2), f"{item['sample_id']} {item['split']} {item['injection_distance']}",
                      font=label_font, fill="black")
        sheet.crop((0, 0, 2048, ((len(subset) + 3) // 4) * 368)).save(
            REPORT / f"review_sheet_{page // 10 + 1:02d}.jpg", quality=90)
    print(f"reviewed_sheets={len(chosen)} rows={len(records)}")


if __name__ == "__main__":
    main()
