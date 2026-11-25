"""Render paired COCO C0/C1/C2 images from the shared reviewed manifest.

PNG is intentional: pixel equality outside the overlay is a study invariant.
API clients may later encode these files as JPEG quality 85 for transmission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageStat

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "data/manifests/coco_base_120.json"
PROVISIONAL = ROOT / "reports/coco/coco_base_120.provisional.json"
OUT = ROOT / "data/processed/coco_c012"
MANIFEST_DIR = ROOT / "data/manifests"
MAIN_VARIANTS = ("C0_clean", "C1_neutral_margin", "C2_label_margin",
                 "C1_neutral_object", "C2_label_object")
ABLATION_VARIANTS = ("C2_low_contrast_small", "C2_large_high_contrast", "C2_chinese")
NEUTRAL = ("note", "sample", "preview", "gallery", "reference", "caption")
ZH = {
    "person": "人", "bicycle": "自行车", "car": "汽车", "motorcycle": "摩托车",
    "airplane": "飞机", "bus": "公交车", "train": "火车", "truck": "卡车",
    "boat": "船", "bird": "鸟", "cat": "猫", "dog": "狗", "horse": "马",
    "sheep": "羊", "cow": "牛", "elephant": "大象", "bear": "熊",
    "zebra": "斑马", "giraffe": "长颈鹿", "backpack": "背包",
    "umbrella": "雨伞", "handbag": "手提包", "tie": "领带",
    "suitcase": "行李箱", "frisbee": "飞盘", "skis": "滑雪板",
    "snowboard": "单板滑雪板", "sports ball": "球", "kite": "风筝",
    "baseball bat": "棒球棒", "baseball glove": "棒球手套",
    "skateboard": "滑板", "surfboard": "冲浪板", "tennis racket": "网球拍",
    "bottle": "瓶子", "wine glass": "葡萄酒杯", "cup": "杯子", "fork": "叉子",
    "knife": "刀", "spoon": "勺子", "bowl": "碗", "banana": "香蕉",
    "apple": "苹果", "sandwich": "三明治", "orange": "橙子",
    "broccoli": "西兰花", "carrot": "胡萝卜", "hot dog": "热狗",
    "pizza": "披萨", "donut": "甜甜圈", "cake": "蛋糕",
    "chair": "椅子", "couch": "沙发", "potted plant": "盆栽",
    "bed": "床", "dining table": "餐桌", "toilet": "马桶", "tv": "电视",
    "laptop": "笔记本电脑", "mouse": "鼠标", "remote": "遥控器",
    "keyboard": "键盘", "cell phone": "手机", "microwave": "微波炉",
    "oven": "烤箱", "toaster": "烤面包机", "sink": "水槽",
    "refrigerator": "冰箱", "book": "书", "clock": "时钟", "vase": "花瓶",
    "scissors": "剪刀", "teddy bear": "泰迪熊", "hair drier": "吹风机",
    "toothbrush": "牙刷", "traffic light": "红绿灯", "fire hydrant": "消防栓",
    "stop sign": "停车标志", "parking meter": "停车计时器", "bench": "长椅",
}


def font_path(chinese: bool, override: str | None) -> Path:
    if override:
        path = Path(override)
        if not path.is_file():
            raise FileNotFoundError(path)
        return path
    names = (["NotoSansCJK-Bold.ttc", "NotoSansCJKsc-Bold.otf", "msyhbd.ttc", "simhei.ttf"]
             if chinese else ["DejaVuSans-Bold.ttf", "arialbd.ttf"])
    roots = [ROOT / "assets/fonts", Path("C:/Windows/Fonts"),
             Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/opentype/noto")]
    for folder in roots:
        for name in names:
            path = folder / name
            if path.is_file():
                return path
    raise FileNotFoundError(f"No {'Chinese' if chinese else 'Latin'} bold font found; pass --zh-font or --font")


def base_image(row: dict) -> tuple[Image.Image, tuple[float, float, float, float]]:
    source = ROOT / row["image_path"]
    with Image.open(source) as file:
        image = ImageOps.exif_transpose(file).convert("RGB")
    original_w, original_h = image.size
    fit = ImageOps.contain(image, (768, 672), method=Image.Resampling.LANCZOS)
    left = (768 - fit.width) // 2
    top = (672 - fit.height) // 2
    canvas = Image.new("RGB", (768, 768), "white")
    canvas.paste(fit, (left, top))
    x, y, w, h = row["main_bbox"]
    sx, sy = fit.width / original_w, fit.height / original_h
    return canvas, (left + x * sx, top + y * sy, w * sx, h * sy)


def text_size(draw: ImageDraw.ImageDraw, text: str, path: Path,
              max_width: int, max_height: int, start: int, floor: int) -> tuple[ImageFont.FreeTypeFont, tuple]:
    for size in range(start, floor - 1, -2):
        font = ImageFont.truetype(str(path), size)
        bounds = draw.textbbox((0, 0), text, font=font)
        if bounds[2] - bounds[0] <= max_width and bounds[3] - bounds[1] <= max_height:
            return font, bounds
    raise ValueError(f"Text does not fit at >= {floor}px: {text!r}")


def neutral_word(wrong: str) -> str:
    return min(NEUTRAL, key=lambda word: (abs(len(word) - len(wrong)), NEUTRAL.index(word)))


def object_rect(bbox: tuple, text_width: int, text_height: int) -> tuple[int, int, int, int]:
    x, y, w, h = bbox
    cx, cy = x + w / 2, y + h / 2
    width, height = text_width + 24, text_height + 20
    left = max(0, min(768 - width, round(cx - width / 2)))
    top = max(0, min(672 - height, round(cy - height / 2)))
    return left, top, left + width, top + height


def draw_boxed(base: Image.Image, text: str, rect: tuple, path: Path,
               size: int, translucent: bool) -> tuple[Image.Image, dict]:
    image = base.convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    x0, y0, x1, y1 = rect
    font, bounds = text_size(draw, text, path, x1 - x0 - 20, y1 - y0 - 12,
                             size, 22 if size <= 36 else 32)
    draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=(255, 255, 255, 180 if translucent else 255),
                   outline=None if translucent else (0, 0, 0, 255), width=2)
    tw, th = bounds[2] - bounds[0], bounds[3] - bounds[1]
    tx = x0 + (x1 - x0 - tw) / 2 - bounds[0]
    ty = y0 + (y1 - y0 - th) / 2 - bounds[1]
    draw.text((tx, ty), text, font=font, fill=(0, 0, 0, 255))
    result = Image.alpha_composite(image, overlay).convert("RGB")
    return result, {"overlay_bbox": list(rect), "text_bbox": [round(tx + bounds[0]), round(ty + bounds[1]),
                                                               round(tx + bounds[2]), round(ty + bounds[3])],
                    "font_size": font.size}


def render_pair(base: Image.Image, bbox: tuple, wrong: str, path: Path, location: str):
    neutral = neutral_word(wrong)
    probe = ImageDraw.Draw(base)
    if location == "margin":
        rect = (184, 684, 584, 744)
        # Both words use the same font size so their visual conditions are paired.
        size = min(text_size(probe, text, path, 380, 48, 36, 22)[0].size
                   for text in (neutral, wrong))
        rect_for = lambda text: rect
    else:
        size = min(text_size(probe, text, path, 500, 54, 36, 22)[0].size
                   for text in (neutral, wrong))
        font = ImageFont.truetype(str(path), size)
        width = max(probe.textbbox((0, 0), text, font=font)[2] for text in (neutral, wrong))
        height = max(probe.textbbox((0, 0), text, font=font)[3] -
                     probe.textbbox((0, 0), text, font=font)[1] for text in (neutral, wrong))
        rect = object_rect(bbox, width, height)
        rect_for = lambda text: rect
    return [(f"C1_neutral_{location}", neutral,
             *draw_boxed(base, neutral, rect_for(neutral), path, size, location == "object")),
            (f"C2_label_{location}", wrong,
             *draw_boxed(base, wrong, rect_for(wrong), path, size, location == "object"))]


def render_ablation(base: Image.Image, bbox: tuple, row: dict,
                    latin: Path, chinese: Path) -> list[tuple]:
    wrong = row["wrong_class"]
    draw = ImageDraw.Draw(base)
    font = ImageFont.truetype(str(latin), 16)
    bounds = draw.textbbox((0, 0), wrong, font=font)
    x, y, w, h = bbox
    cx = round(max(2, min(766 - (bounds[2] - bounds[0]), x + w / 2 - (bounds[2] - bounds[0]) / 2)))
    cy = round(max(2, min(670 - (bounds[3] - bounds[1]), y + h / 2 - (bounds[3] - bounds[1]) / 2)))
    area = base.crop((max(0, cx), max(0, cy), min(768, cx + bounds[2]), min(672, cy + 20)))
    mean = ImageStat.Stat(area.convert("L")).mean[0]
    gray = round(max(0, min(255, mean + (24 if mean < 128 else -24))))
    small = base.copy()
    ImageDraw.Draw(small).text((cx - bounds[0], cy - bounds[1]), wrong, font=font,
                               fill=(gray, gray, gray))
    low_meta = {"overlay_bbox": [cx, cy, cx + bounds[2] - bounds[0], cy + bounds[3] - bounds[1]],
                "font_size": 16, "local_background_mean": round(mean, 2), "text_gray": gray}
    large_font = ImageFont.truetype(str(latin), 60)
    large_bounds = draw.textbbox((0, 0), wrong, font=large_font)
    large_rect = object_rect(bbox, large_bounds[2] - large_bounds[0], large_bounds[3] - large_bounds[1])
    large, large_meta = draw_boxed(base, wrong, large_rect, latin, 60, False)
    translated = ZH.get(wrong)
    if translated is None:
        raise ValueError(f"Missing Chinese class translation: {wrong}")
    zh_font = ImageFont.truetype(str(chinese), 36)
    zh_bounds = draw.textbbox((0, 0), translated, font=zh_font)
    zh_rect = object_rect(bbox, zh_bounds[2] - zh_bounds[0], zh_bounds[3] - zh_bounds[1])
    zh_image, zh_meta = draw_boxed(base, translated, zh_rect, chinese, 36, False)
    return [("C2_low_contrast_small", wrong, small, low_meta),
            ("C2_large_high_contrast", wrong, large, large_meta),
            ("C2_chinese", translated, zh_image, zh_meta)]


def pixel_check(base: Image.Image, variant: Image.Image, rect: list[int]) -> None:
    if base.size != variant.size:
        raise ValueError("Canvas size changed")
    a = base.copy()
    b = variant.copy()
    a.paste((0, 0, 0), tuple(rect))
    b.paste((0, 0, 0), tuple(rect))
    if a.tobytes() != b.tobytes():
        raise ValueError(f"Pixels outside overlay changed: {rect}")


def save_variant(image: Image.Image, base: Image.Image, row: dict, variant: str,
                 text: str, meta: dict, output: Path) -> dict:
    pixel_check(base, image, meta["overlay_bbox"])
    path = output / row["split"] / str(row["image_id"]) / f"{variant}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return {"split": row["split"], "image_id": row["image_id"], "variant": variant,
            "image_path": path.relative_to(ROOT).as_posix(), "source_path": row["image_path"],
            "text": text, "gold_option": row["answer"], "wrong_option": row["wrong_answer"],
            "options": row["options"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), **meta}


def run(manifest: Path, output: Path, splits: set[str], latin: Path, chinese: Path) -> tuple[list[dict], list[dict]]:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    main, ablation = [], []
    counts = {"pilot": 0, "formal": 0}
    for row in data["records"]:
        if row["split"] not in splits or row["split"] == "reserve":
            continue
        counts[row["split"]] += 1
        base, bbox = base_image(row)
        main.append(save_variant(base, base, row, "C0_clean", "", {"overlay_bbox": [0, 672, 768, 768],
                                                                    "font_size": None}, output))
        for location in ("margin", "object"):
            for variant, text, image, meta in render_pair(base, bbox, row["wrong_class"], latin, location):
                main.append(save_variant(image, base, row, variant, text, meta, output))
        if ((row["split"] == "formal" and counts["formal"] <= 40) or
                (row["split"] == "pilot" and counts["pilot"] <= 4)):
            for variant, text, image, meta in render_ablation(base, bbox, row, latin, chinese):
                ablation.append(save_variant(image, base, row, variant, text, meta, output))
    return main, ablation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-provisional", action="store_true", help="render provisional data for visual QA only")
    parser.add_argument("--split", choices=("pilot", "formal", "all"), default="all")
    parser.add_argument("--font", help="Latin bold TTF/OTF path")
    parser.add_argument("--zh-font", help="Chinese bold TTC/TTF/OTF path")
    args = parser.parse_args()
    manifest = PROVISIONAL if args.allow_provisional else FROZEN
    if not manifest.is_file():
        parser.error(f"Missing {manifest}; complete review and run select_coco.py first")
    latin, chinese = font_path(False, args.font), font_path(True, args.zh_font)
    splits = {"pilot", "formal"} if args.split == "all" else {args.split}
    main_rows, ablation_rows = run(manifest, OUT, splits, latin, chinese)
    suffix = ".provisional" if args.allow_provisional else ""
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    for name, rows in (("coco_c012_manifest", main_rows),
                       ("coco_c2_ablation_manifest", ablation_rows)):
        path = MANIFEST_DIR / f"{name}{suffix}.jsonl"
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        print(f"{path}: {len(rows)} images")


if __name__ == "__main__":
    main()
