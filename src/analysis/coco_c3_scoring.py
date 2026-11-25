"""Prompt identity and exact target recognition for C3 analysis."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata

from src.common.prompts import build_messages, coco_read_hint


def prompt_sha256(sample: dict, probe: str) -> str:
    if probe == "coco_task":
        variables = {f"opt_{letter}": sample["options"][letter] for letter in "ABCD"}
    elif probe == "coco_read":
        variables = {"overlay_hint": coco_read_hint(sample["variant"])}
    else:
        raise ValueError(f"Unsupported COCO probe: {probe}")
    messages = build_messages(probe, variables)
    raw = json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def target_seen(content: str | None, target: str) -> bool:
    text = " ".join(unicodedata.normalize("NFKC", content or "").casefold().split())
    target = " ".join(unicodedata.normalize("NFKC", target).casefold().split())
    return bool(re.search(rf"(?<![\w-]){re.escape(target)}(?![\w-])", text))
