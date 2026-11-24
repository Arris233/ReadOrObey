"""Validate the provisional Mind2Web manifest and rendered image alignment."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "reports" / "mind2web" / "mind2web_manifest.provisional.jsonl"


def intersects(a: list[int], b: list[int]) -> bool:
    return not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0]
                or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])


def main() -> None:
    rows = [json.loads(line) for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line]
    assert Counter(r["split"] for r in rows) == {"pilot": 10, "formal": 60, "reserve": 10}
    assert len({r["annotation_id"] for r in rows}) == 80
    assert len({r["website"] for r in rows if r["split"] == "pilot"}) == 10
    assert Counter(r["injected_id"] for r in rows if r["split"] == "formal") == {i: 12 for i in range(1, 6)}
    assert {r["source_split"] for r in rows} == {"test_task", "test_website"}
    for r in rows:
        assert r["status"] == "provisional_needs_visual_review"
        assert r["target_action_index"] == "0", r["sample_id"]
        assert len(r["real_elements_A0"]) == len(r["real_elements_A1_A2"]) == 4
        assert {e["id"] for e in r["real_elements_A0"]} == {1, 2, 3, 4}
        assert {e["id"] for e in r["real_elements_A1_A2"]} == set(range(1, 6)) - {r["injected_id"]}
        assert r["gold_id_A0"] in range(1, 5)
        assert r["gold_id_A1_A2"] in set(range(1, 6)) - {r["injected_id"]}
        injection = r["injection_box_1024"]
        assert all(not intersects(injection, e["bbox_1024"]) for e in r["real_elements_A1_A2"])
        target = next(e["bbox_1024"] for e in r["real_elements_A1_A2"] if e["id"] == r["gold_id_A1_A2"])
        distance = math.hypot(injection[0] + 90 - target[0] - target[2] / 2,
                              injection[1] + 22 - target[1] - target[3] / 2)
        assert distance <= 200 if r["injection_distance"] == "near" else distance >= 300
        images = {key: Image.open(ROOT / path).convert("RGB") for key, path in r["image_paths"].items()}
        assert all(image.size == (1024, 680) for image in images.values())
        # The JPEG-encoded A1/A2 pair may differ in blocks adjacent to the text;
        # outside the injected button (plus one MCU margin) they must match exactly.
        difference = ImageChops.difference(images["A1"], images["A2"])
        box = difference.getbbox()
        assert box is not None
        assert box[0] >= injection[0] - 32 and box[1] >= injection[1] - 32
        assert box[2] <= injection[0] + injection[2] + 32 and box[3] <= injection[1] + injection[3] + 32
        for image in images.values():
            image.close()
    print(f"PASS {len(rows)} steps, {len(rows)*3} images; 210 active images + 30 reserve images")


if __name__ == "__main__":
    main()
