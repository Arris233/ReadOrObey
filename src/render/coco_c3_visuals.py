"""Shared visual helpers for C3 size and contrast ablations."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageStat


def wrapped(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}" if current else word
        if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
            current = trial
        else:
            if not current:
                raise ValueError(f"Word too wide: {word}")
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_gradient(base: Image.Image, text: str, bbox: tuple[float, float, float, float],
                  latin: Path, large: bool) -> tuple[Image.Image, dict]:
    """Draw the 16px low-contrast or 60px high-contrast object overlay."""
    size = 60 if large else 16
    font = ImageFont.truetype(str(latin), size)
    lines = wrapped(text, font, 680)
    if len(lines) > (4 if large else 2):
        raise ValueError(f"Instruction too tall at {size}px: {text}")
    line_step = size + (10 if large else 4)
    probe = ImageDraw.Draw(base)
    widths = [probe.textbbox((0, 0), line, font=font)[2] for line in lines]
    height = len(lines) * line_step
    center_x = bbox[0] + bbox[2] / 2
    center_y = bbox[1] + bbox[3] / 2
    top = max(12, min(672 - height - 12, round(center_y - height / 2)))
    left = max(12, min(768 - max(widths) - 12, round(center_x - max(widths) / 2)))
    pad = 12 if large else 0
    rect = (max(0, left - pad), max(0, top - pad),
            min(768, left + max(widths) + pad), min(672, top + height + pad))
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    if large:
        draw.rectangle((rect[0], rect[1], rect[2] - 1, rect[3] - 1),
                       fill=(255, 255, 255, 235))
        gray = 0
        mean = None
    else:
        mean = ImageStat.Stat(base.crop(rect).convert("L")).mean[0]
        gray = round(max(0, min(255, mean + (24 if mean < 128 else -24))))
    for index, line in enumerate(lines):
        draw.text((left, top + index * line_step), line, font=font, fill=(gray, gray, gray, 255))
    image = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    return image, {"overlay_bbox": list(rect), "font_size": size,
                   "text_lines": lines, "local_background_mean": round(mean, 2) if mean is not None else None,
                   "text_gray": gray}
