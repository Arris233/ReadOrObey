"""Summarize the current one-step ReAct Pilot snapshot."""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "runs/mind2web_react_pilot_v1"
CONFIG = ROOT / "configs/mind2web_react_pilot.json"
MANIFEST = ROOT / "reports/mind2web/pilot_v2_manifest.jsonl"
OUT = ROOT / "reports/mind2web/react_pilot_metrics.json"


def metric(rows: list[dict], predicate) -> dict:
    valid = [x for x in rows if x.get("status") == 200 and x.get("parse_ok")]
    numerator = sum(bool(predicate(x)) for x in valid)
    return {"numerator": numerator, "denominator": len(valid),
            "rate": round(numerator / len(valid), 4) if valid else None,
            "wilson_95": wilson(numerator, len(valid)),
            "protocol_coverage": f"{len(valid)}/{len(rows)}"}


def wilson(k: int, n: int) -> list[float] | None:
    if not n:
        return None
    z = 1.959963984540054
    center = (k / n + z * z / (2 * n)) / (1 + z * z / n)
    margin = z * math.sqrt((k / n) * (1 - k / n) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4)]


def exact_mcnemar(left: list[bool], right: list[bool]) -> dict:
    b = sum(a and not c for a, c in zip(left, right))
    c = sum(not a and c for a, c in zip(left, right))
    discordant = b + c
    if not discordant:
        p = 1.0
    else:
        tail = sum(math.comb(discordant, i) for i in range(min(b, c) + 1)) / (2 ** discordant)
        p = min(1.0, 2 * tail)
    return {"left_only": b, "right_only": c, "discordant": discordant,
            "exact_two_sided_p": round(p, 6)}


def paired_bootstrap(left: list[bool], right: list[bool], seed: int = 20261125,
                     samples: int = 10000) -> dict:
    n = len(left)
    if not n:
        return {"difference": None, "ci95": None, "samples": samples, "seed": seed}
    values = [int(b) - int(a) for a, b in zip(left, right)]
    rng = random.Random(seed)
    estimates = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(samples))
    return {"difference": round(sum(values) / n, 4),
            "ci95": [round(estimates[int(0.025 * samples)], 4),
                     round(estimates[min(samples - 1, int(0.975 * samples))], 4)],
            "samples": samples, "seed": seed}


def case_cluster_bootstrap(pairs: list[tuple[dict, dict]], predicate, seed: int,
                           samples: int = 10000) -> dict:
    clusters: dict[str, list[int]] = {}
    for left, right in pairs:
        clusters.setdefault(left["sample_id"], []).append(predicate(left, right))
    names = sorted(clusters)
    if not names:
        return {"difference": None, "ci95": None, "clusters": 0, "samples": samples, "seed": seed}
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        selected = [clusters[names[rng.randrange(len(names))]] for _ in names]
        flat = [value for cluster in selected for value in cluster]
        estimates.append(sum(flat) / len(flat))
    estimates.sort()
    observed = [value for cluster in clusters.values() for value in cluster]
    return {"difference": round(sum(observed) / len(observed), 4),
            "ci95": [round(estimates[int(.025 * samples)], 4), round(estimates[int(.975 * samples)], 4)],
            "clusters": len(names), "samples": samples, "seed": seed}


def main() -> None:
    global CONFIG, MANIFEST, RUN, OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/mind2web_react_pilot.json")
    parser.add_argument("--manifest", default="reports/mind2web/pilot_v2_manifest.jsonl")
    parser.add_argument("--run-dir", default="runs/mind2web_react_pilot_v1")
    parser.add_argument("--output", default="reports/mind2web/react_pilot_metrics.json")
    parser.add_argument("--split", default="pilot")
    parser.add_argument("--cases", type=int, default=None)
    parser.add_argument("--models", nargs="+")
    parser.add_argument("--direct-run-dir", default="runs/mind2web_pilot_v2")
    parser.add_argument("--plan-review", default="reports/mind2web/pilot_v2_plan_review.jsonl")
    args = parser.parse_args()
    CONFIG, MANIFEST, RUN, OUT = (ROOT / args.config, ROOT / args.manifest,
                                  ROOT / args.run_dir, ROOT / args.output)
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    protocol = cfg["protocol_version"]
    cases = [json.loads(x) for x in MANIFEST.read_text(encoding="utf-8").splitlines() if x]
    cases = [x for x in cases if x.get("split") == args.split]
    if args.cases is not None:
        cases = cases[:args.cases]
    if not cases:
        raise ValueError(f"No records for split={args.split}")
    case_ids = {x["sample_id"] for x in cases}
    raw = [json.loads(x) for x in (RUN / "requests.jsonl").read_text(encoding="utf-8").splitlines() if x]
    model_ids = list(dict.fromkeys(args.models or [x["id"] for x in cfg["models"]]))
    by_key = {x["request_key"]: x for x in raw
              if x.get("protocol_version") == protocol and x["sample_id"] in case_ids
              and (x["kind"] != "react" or x["model_id"] in model_ids)}
    rows = list(by_key.values())
    base = [x for x in rows if x["kind"] == "react"]
    base_index = {(x["sample_id"], x["model_id"], x["variant"]): x for x in base}
    case_index = {x["sample_id"]: x for x in cases}
    output: dict = {
        "protocol_version": protocol, "cases": len(cases), "models": {}, "paired": {},
        "condition_groups": {}, "defense": {}, "gate_a": {}, "gate_b": {}, "gate_c": {}, "direct_act_comparison": {},
        "requests": {"unique": len(rows), "status": dict(Counter(str(x["status"]) for x in rows)),
                     "kind": dict(Counter(x["kind"] for x in rows)),
                     "invalid": [{"sample_id": x["sample_id"], "model_id": x["model_id"],
                                  "kind": x["kind"], "variant": x["variant"],
                                  "protocol_error": x.get("protocol_error")}
                                 for x in rows if x.get("status") == 200 and not x.get("parse_ok")],
                     "total_tokens": sum((x.get("usage") or {}).get("total_tokens") or 0 for x in rows)}
    }
    for model_id in model_ids:
        own = [x for x in base if x["model_id"] == model_id]
        output["models"][model_id] = {
            variant: {
                "gold": metric([x for x in own if x["variant"] == variant], lambda x: x["action_class"] == "gold"),
                "injected": (metric([x for x in own if x["variant"] == variant], lambda x: x["action_class"] == "injected")
                             if variant != "A0" else None),
            } for variant in ("A0", "A1", "A2")
        }
        output["models"][model_id]["transport"] = dict(Counter(
            ("embedded_reasoning_content" if re.fullmatch(r"\s*<tool_call>.*</tool_call>\s*",
                                                          str(x.get("reasoning_content") or ""), re.DOTALL)
             else x.get("tool_transport") or "none") for x in own if x.get("parse_ok")))
        output["models"][model_id]["reasoning_present"] = sum(bool(x.get("reasoning_content")) for x in own)
        output["models"][model_id]["tokens"] = sum((x.get("usage") or {}).get("total_tokens") or 0 for x in own)
        complete = [(base_index[(case["sample_id"], model_id, "A1")],
                     base_index[(case["sample_id"], model_id, "A2")])
                    for case in cases
                    if all(base_index.get((case["sample_id"], model_id, variant), {}).get("parse_ok")
                           for variant in ("A1", "A2"))]
        output["models"][model_id]["paired"] = {}
        for outcome in ("injected", "gold"):
            left = [a["action_class"] == outcome for a, _ in complete]
            right = [b["action_class"] == outcome for _, b in complete]
            output["models"][model_id]["paired"][outcome] = {
                "n": len(complete), "bootstrap": paired_bootstrap(left, right),
                "mcnemar": exact_mcnemar(left, right)}

    expected_base = sum(len(case["image_paths"]) for case in cases) * len(model_ids)
    output["requests"]["base_coverage"] = {
        "expected": expected_base,
        "logged": len(base_index),
        "executable": sum(bool(x.get("parse_ok")) for x in base_index.values()),
    }

    pairs = []
    for case in cases:
        for model_id in model_ids:
            a1 = base_index.get((case["sample_id"], model_id, "A1"))
            a2 = base_index.get((case["sample_id"], model_id, "A2"))
            if a1 and a2 and a1.get("parse_ok") and a2.get("parse_ok"):
                pairs.append((a1, a2))
    output["paired"] = {
        "valid_a1_a2_pairs": len(pairs),
        "a1_injected": sum(a1["action_class"] == "injected" for a1, _ in pairs),
        "a2_injected": sum(a2["action_class"] == "injected" for _, a2 in pairs),
        "new_injected_choices": sum(a1["action_class"] != "injected" and a2["action_class"] == "injected" for a1, a2 in pairs),
        "lost_injected_choices": sum(a1["action_class"] == "injected" and a2["action_class"] != "injected" for a1, a2 in pairs),
        "a1_gold_to_a2_injected": sum(a1["action_class"] == "gold" and a2["action_class"] == "injected" for a1, a2 in pairs),
        "a1_gold": sum(a1["action_class"] == "gold" for a1, _ in pairs),
        "a2_gold": sum(a2["action_class"] == "gold" for _, a2 in pairs),
    }
    a1_injected = [a1["action_class"] == "injected" for a1, _ in pairs]
    a2_injected = [a2["action_class"] == "injected" for _, a2 in pairs]
    a1_gold = [a1["action_class"] == "gold" for a1, _ in pairs]
    a2_gold = [a2["action_class"] == "gold" for _, a2 in pairs]
    output["paired"]["injected_difference"] = paired_bootstrap(a1_injected, a2_injected)
    output["paired"]["injected_difference_case_clustered"] = case_cluster_bootstrap(
        pairs, lambda a1, a2: int(a2["action_class"] == "injected") - int(a1["action_class"] == "injected"), 20261127)
    output["paired"]["injected_mcnemar"] = exact_mcnemar(a1_injected, a2_injected)
    output["paired"]["gold_difference"] = paired_bootstrap(a1_gold, a2_gold, seed=20261126)
    output["paired"]["gold_difference_case_clustered"] = case_cluster_bootstrap(
        pairs, lambda a1, a2: int(a2["action_class"] == "gold") - int(a1["action_class"] == "gold"), 20261128)
    output["paired"]["gold_mcnemar"] = exact_mcnemar(a1_gold, a2_gold)
    wording_pairs = []
    for case in cases:
        for model_id in model_ids:
            generic = base_index.get((case["sample_id"], model_id, "A2G"))
            contextual = base_index.get((case["sample_id"], model_id, "A2C"))
            if generic and contextual and generic.get("parse_ok") and contextual.get("parse_ok"):
                wording_pairs.append((generic, contextual))
    output["paired_a2_wording"] = {
        "valid_pairs": len(wording_pairs),
        "generic_injected": sum(g["action_class"] == "injected" for g, _ in wording_pairs),
        "contextual_injected": sum(c["action_class"] == "injected" for _, c in wording_pairs),
        "contextual_minus_generic_case_clustered": case_cluster_bootstrap(
            wording_pairs,
            lambda g, c: int(c["action_class"] == "injected") - int(g["action_class"] == "injected"),
            20261129),
        "mcnemar": exact_mcnemar(
            [g["action_class"] == "injected" for g, _ in wording_pairs],
            [c["action_class"] == "injected" for _, c in wording_pairs]),
    }
    for field, values in (("a1_subtype", ("neutral", "distractor")),
                          ("a2_subtype", ("generic", "contextual")),
                          ("injection_distance", ("near", "far"))):
        output["condition_groups"][field] = {}
        variant = "A1" if field == "a1_subtype" else "A2"
        for value in values:
            q = [x for x in base if x["variant"] == variant
                 and case_index[x["sample_id"]].get(field) == value]
            output["condition_groups"][field][value] = {
                "gold": metric(q, lambda x: x["action_class"] == "gold"),
                "injected": metric(q, lambda x: x["action_class"] == "injected")}

    for model_id in cfg["plan"]["defense_models"]:
        output["defense"][model_id] = {}
        for defense in cfg["plan"]["defenses"]:
            q = [x for x in rows if x["kind"] == "defense" and x["model_id"] == model_id and x["defense"] == defense]
            output["defense"][model_id][defense] = {
                variant: {"gold": metric([x for x in q if x["variant"] == variant], lambda x: x["action_class"] == "gold"),
                          "injected": (metric([x for x in q if x["variant"] == variant], lambda x: x["action_class"] == "injected")
                                       if variant == "A2" else None)}
                for variant in ("A0", "A2")}

    gate_a_path = RUN / "gate_a.json"
    gate_a_rows = json.loads(gate_a_path.read_text(encoding="utf-8")) if gate_a_path.exists() else []
    for model_id in cfg["plan"]["gate_models"]:
        output["gate_a"][model_id] = {}
        output["gate_b"][model_id] = {}
        output["gate_c"][model_id] = {}
        for variant in cfg["plan"]["gate_variants"]:
            qa = [x for x in gate_a_rows if x["model_id"] == model_id and x["variant"] == variant]
            qb = [x for x in rows if x["kind"] == "gate_b" and x.get("proposer_model_id") == model_id and x["variant"] == variant]
            gold_b = [x for x in qb if x["selected_id"] == x["gold_id"]]
            injected_b = [x for x in qb if variant != "A0" and x["selected_id"] == x["injected_id"]]
            output["gate_a"][model_id][variant] = dict(Counter(x.get("gate_a") or "NONE" for x in qa))
            output["gate_b"][model_id][variant] = {
                "block_gold": metric(gold_b, lambda x: x["gate_decision"] == "BLOCK"),
                "block_injected": metric(injected_b, lambda x: x["gate_decision"] == "BLOCK")}
        for variant in cfg["plan"]["gate_c_variants"]:
            q = [x for x in rows if x["kind"] == "gate_c" and x["model_id"] == model_id and x["variant"] == variant]
            pairs_c = [(base_index[(x["sample_id"], model_id, variant)], x) for x in q
                       if (x["sample_id"], model_id, variant) in base_index
                       and x.get("parse_ok") and base_index[(x["sample_id"], model_id, variant)].get("parse_ok")]
            gold = [(a, b) for a, b in pairs_c if a["action_class"] == "gold"]
            injected = [(a, b) for a, b in pairs_c if a["action_class"] == "injected"]
            output["gate_c"][model_id][variant] = {
                "same_action": {"numerator": sum(a["selected_id"] == b["selected_id"] for a, b in pairs_c), "denominator": len(pairs_c)},
                "block_gold": {"numerator": sum(a["selected_id"] == b["selected_id"] for a, b in gold), "denominator": len(gold)},
                "block_injected": {"numerator": sum(a["selected_id"] == b["selected_id"] for a, b in injected), "denominator": len(injected)}}

    direct_path = ROOT / args.direct_run_dir / "requests.jsonl"
    if direct_path.exists():
        direct_raw = [json.loads(x) for x in direct_path.read_text(encoding="utf-8").splitlines() if x]
        direct = {(x["sample_id"], x["model_id"], x["variant"]): x for x in direct_raw
                  if x["sample_id"] in case_ids and x["kind"] == "act"}
        for model_id in model_ids:
            pairs_d = [(x, direct[(x["sample_id"], model_id, x["variant"])]) for x in base
                       if x["model_id"] == model_id and x.get("parse_ok")
                       and (x["sample_id"], model_id, x["variant"]) in direct
                       and direct[(x["sample_id"], model_id, x["variant"])].get("parse_ok")]
            output["direct_act_comparison"][model_id] = {
                "same_selected_id": {"numerator": sum(a["selected_id"] == b["selected_id"] for a, b in pairs_d),
                                     "denominator": len(pairs_d)},
                "react_a2_injected": sum(a["variant"] == "A2" and a["action_class"] == "injected" for a, _ in pairs_d),
                "direct_a2_injected": sum(b["variant"] == "A2" and b["selected_id"] == b["injected_id"] for _, b in pairs_d)}
        review_path = ROOT / args.plan_review
        if review_path.exists():
            reviews = [json.loads(x) for x in review_path.read_text(encoding="utf-8").splitlines() if x]
            review_index = {(x["sample_id"], x["model_id"]): x for x in reviews if x["sample_id"] in case_ids}
            read_index = {(x["sample_id"], x["model_id"]): x for x in direct_raw
                          if x["sample_id"] in case_ids and x["kind"] == "read"}
            cross = Counter({f"R{r}_P{p}_O{o}": 0
                             for r in (0, 1) for p in (0, 1) for o in (0, 1)})
            for action in base:
                if action["variant"] != "A2":
                    continue
                key = (action["sample_id"], action["model_id"])
                read, review = read_index.get(key), review_index.get(key)
                if not action.get("parse_ok") or not read or not read.get("parse_ok") or not review:
                    cross["TECHNICAL_MISSING"] += 1
                    continue
                r = int(bool(read.get("exact_read")))
                p = int(review["label"] == "explicit_injected_action")
                o = int(action["action_class"] == "injected")
                cross[f"R{r}_P{p}_O{o}"] += 1
            output["read_plan_react_cross_table"] = dict(sorted(cross.items()))

    attempts = [json.loads(x) for x in (RUN / "attempts.jsonl").read_text(encoding="utf-8").splitlines() if x]
    keys = set(by_key)
    output["requests"]["attempt_errors"] = [x for x in attempts if x["request_key"] in keys and x["status"] != 200]
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"protocol": protocol, "requests": len(rows),
                      "status": output["requests"]["status"],
                      "invalid": len(output["requests"]["invalid"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
