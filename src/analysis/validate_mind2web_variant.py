"""Validate any versioned Mind2Web manifest before API execution."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[2]


def intersects(a: list[int], b: list[int]) -> bool:
    return not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0]
                or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--expected-cases", type=int, required=True)
    parser.add_argument("--require-balanced-subtypes", action="store_true")
    args = parser.parse_args()
    path = ROOT / args.manifest
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
    rows = [x for x in rows if x.get("split") == args.split]
    assert len(rows) == args.expected_cases, (len(rows), args.expected_cases)
    assert len({x["sample_id"] for x in rows}) == len(rows)
    assert len({x["annotation_id"] for x in rows}) == len(rows)
    assert all(str(x["target_action_index"]) == "0" for x in rows)
    if args.require_balanced_subtypes:
        assert Counter(x["a1_subtype"] for x in rows) == {"neutral": len(rows) // 2, "distractor": len(rows) // 2}
        assert Counter(x["a2_subtype"] for x in rows) == {"generic": len(rows) // 2, "contextual": len(rows) // 2}
    for row in rows:
        assert row["injection_text_A1"] != row["injection_text_A2"]
        assert len(row["real_elements_A0"]) == len(row["real_elements_A1_A2"]) == 4
        assert {x["id"] for x in row["real_elements_A0"]} == {1, 2, 3, 4}
        assert {x["id"] for x in row["real_elements_A1_A2"]} == set(range(1, 6)) - {row["injected_id"]}
        assert row["gold_id_A0"] in range(1, 5)
        assert row["gold_id_A1_A2"] != row["injected_id"]
        box = row["injection_box_1024"]
        assert all(not intersects(box, x["bbox_1024"]) for x in row["real_elements_A1_A2"]), row["sample_id"]
        opened = {}
        for variant, relative in row["image_paths"].items():
            image_path = ROOT / relative
            assert image_path.exists(), image_path
            if row.get("image_sha256"):
                assert hashlib.sha256(image_path.read_bytes()).hexdigest() == row["image_sha256"][variant]
            opened[variant] = Image.open(image_path).convert("RGB")
            assert opened[variant].size == (1024, 680)
        difference = ImageChops.difference(opened["A1"], opened["A2"]).getbbox()
        assert difference is not None
        assert difference[0] >= box[0] - 32 and difference[1] >= box[1] - 32
        assert difference[2] <= box[0] + box[2] + 32 and difference[3] <= box[1] + box[3] + 32
        if {"A2G", "A2C"} <= opened.keys():
            assert row["injection_text_A2G"] != row["injection_text_A2C"]
            assert row["image_sha256"]["A2"] == row["image_sha256"][
                "A2G" if row["a2_subtype"] == "generic" else "A2C"]
            pair_difference = ImageChops.difference(opened["A2G"], opened["A2C"]).getbbox()
            assert pair_difference is not None
            assert pair_difference[0] >= box[0] - 32 and pair_difference[1] >= box[1] - 32
            assert pair_difference[2] <= box[0] + box[2] + 32
            assert pair_difference[3] <= box[1] + box[3] + 32
        for image in opened.values():
            image.close()
    print(json.dumps({"status": "PASS", "cases": len(rows),
                      "images": sum(len(row["image_paths"]) for row in rows),
                      "a1": Counter(x.get("a1_subtype") for x in rows),
                      "a2": Counter(x.get("a2_subtype") for x in rows)}, ensure_ascii=False, default=dict))


if __name__ == "__main__":
    main()
