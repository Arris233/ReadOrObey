"""Create full A0/A1/A2 review sheets and an editable decision CSV."""

from __future__ import annotations

import argparse
import csv
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = Path("C:/Windows/Fonts/arial.ttf")
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--split", default=None)
    parser.add_argument("--per-page", type=int, default=4)
    args = parser.parse_args()
    manifest = ROOT / args.manifest
    output_dir = ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    records = [json.loads(x) for x in manifest.read_text(encoding="utf-8").splitlines() if x]
    if args.split:
        records = [x for x in records if x.get("split") == args.split]
    if not records:
        raise ValueError("No records selected")

    fields = ["sample_id", "split", "website", "confirmed_task", "a1_subtype", "a2_subtype",
              "task_self_contained", "gold_target_unambiguous", "all_boxes_correct",
              "a1_semantically_benign", "a2_clearly_illegitimate", "button_no_occlusion",
              "text_fully_visible", "decision", "notes"]
    with (output_dir / "review_decisions.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({k: record.get(k, "") for k in fields})

    label = font(16)
    task_font = font(14)
    thumb_w, thumb_h, header_h = 512, 340, 74
    for page_start in range(0, len(records), args.per_page):
        subset = records[page_start:page_start + args.per_page]
        sheet = Image.new("RGB", (thumb_w * 3, (thumb_h + header_h) * len(subset)), "white")
        draw = ImageDraw.Draw(sheet)
        for row_index, record in enumerate(subset):
            y = row_index * (thumb_h + header_h)
            title = (f"{record['sample_id']} | {record.get('website','')} | "
                     f"A1={record.get('a1_subtype','')} A2={record.get('a2_subtype','')}")
            draw.text((6, y + 3), title, fill="black", font=label)
            task_lines = textwrap.wrap(record["confirmed_task"], width=110)[:2]
            draw.text((6, y + 25), "\n".join(task_lines), fill="#334155", font=task_font, spacing=1)
            draw.text((6, y + 58), "A0", fill="#1D4ED8", font=label)
            draw.text((thumb_w + 6, y + 58), f"A1: {record['injection_text_A1']}", fill="#1D4ED8", font=label)
            draw.text((2 * thumb_w + 6, y + 58), f"A2: {record['injection_text_A2']}", fill="#1D4ED8", font=label)
            for column, variant in enumerate(("A0", "A1", "A2")):
                with Image.open(ROOT / record["image_paths"][variant]) as image:
                    sheet.paste(image.convert("RGB").resize((thumb_w, thumb_h)),
                                (column * thumb_w, y + header_h))
        page = page_start // args.per_page + 1
        sheet.save(output_dir / f"review_{page:02d}.jpg", quality=90)
    print(json.dumps({"records": len(records), "pages": (len(records) + args.per_page - 1) // args.per_page,
                      "csv": str((output_dir / 'review_decisions.csv').relative_to(ROOT))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
