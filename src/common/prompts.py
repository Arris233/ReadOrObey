from collections.abc import Mapping
from pathlib import Path

import yaml

PROMPTS_PATH = Path(__file__).resolve().parents[2] / "configs" / "prompts.yaml"
DEFENDED_PROBES = {"coco_task", "mind2web_act"}


def build_messages(
    probe: str, variables: Mapping[str, object], defense: str = "D0"
) -> list[dict[str, str]]:
    """Render one independent probe using the project's templates."""
    if defense not in {"D0", "D1", "D3"}:
        raise ValueError(f"Unknown defense: {defense}")
    templates = yaml.safe_load(PROMPTS_PATH.read_text(encoding="utf-8"))
    if probe not in templates["probes"]:
        raise ValueError(f"Unknown probe: {probe}")
    try:
        user_text = templates["probes"][probe].format_map(variables)
    except KeyError as error:
        raise ValueError(f"Missing variable for {probe}: {error.args[0]}") from error

    messages = []
    if defense == "D1" and probe in DEFENDED_PROBES:
        messages.append({"role": "system", "content": templates["defenses"]["D1"]})
    if defense == "D3" and probe in DEFENDED_PROBES:
        user_text += "\n" + templates["defenses"]["D3"]
    messages.append({"role": "user", "content": user_text})
    return messages
