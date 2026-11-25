"""Plot the member 1 C2 half of the scaling figure and visual ablation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def rate(data: dict, variant: str, metric: str) -> float:
    value = data["variants"].get(variant, {}).get(metric, {}).get("rate")
    return float("nan") if value is None else 100 * value


def plot_ablation(data: dict, models: list[str], output_dir: Path) -> list[Path]:
    """Plot matched 40-image C2 variants with the same denominator throughout."""
    import matplotlib.pyplot as plt
    import numpy as np

    variants = ("C2_label_object_ablation_cohort", "C2_low_contrast_small",
                "C2_large_high_contrast", "C2_chinese")
    labels = ("36px\nstandard", "16px\nlow contrast", "60px\nlarge", "Chinese\ninstruction")
    ablation_models = [model for model in models
                       if all(variant in data[model]["variants"] for variant in variants)]
    if not ablation_models:
        raise ValueError("No selected model has the complete C2 ablation cohort")

    for model in ablation_models:
        sizes = {data[model]["variants"][variant]["task_coverage"] for variant in variants}
        if sizes != {40}:
            raise ValueError(f"Expected the same 40 images for every variant of {model}: {sizes}")

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.2), sharey=True)
    colors = ("#2563a6", "#d47727", "#31845a", "#8051a2")
    x = np.arange(len(variants))
    width = 0.35
    for axis, metric, title in zip(
        axes,
        ("read_exact", "wrong_option"),
        ("Exact text transcription", "Wrong-option answer"),
    ):
        for index, model in enumerate(ablation_models):
            model_name = "M1 · 8B-Instruct" if "8B-Instruct" in model else "M3 · 32B-Instruct"
            values = [data[model]["variants"][variant][metric] for variant in variants]
            heights = [100 * value["rate"] for value in values]
            lower = [100 * (value["rate"] - value["ci95"][0]) for value in values]
            upper = [100 * (value["ci95"][1] - value["rate"]) for value in values]
            positions = x + (index - (len(ablation_models) - 1) / 2) * width
            bars = axis.bar(positions, heights, width=width, color=colors[index],
                            label=model_name, yerr=[lower, upper], capsize=3,
                            error_kw={"elinewidth": 1, "capthick": 1})
            for bar, value in zip(bars, values):
                axis.annotate(f'{value["successes"]}/40',
                              (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                              xytext=(0, 12), textcoords="offset points",
                              ha="center", va="bottom", fontsize=8)
        axis.set_title(title, fontweight="bold")
        axis.set_xticks(x, labels)
        axis.set_ylim(0, 116)
        axis.set_yticks(np.arange(0, 101, 20))
        axis.grid(axis="y", alpha=0.2)
        axis.set_axisbelow(True)
    axes[0].set_ylabel("Percent of images (%)")
    axes[0].legend(loc="lower left", fontsize=9)
    fig.suptitle("C2 visual ablation · first 40 formal images", fontweight="bold")
    fig.text(0.5, 0.025,
             "Bars: rate across the same 40 images; whiskers: 95% Wilson CI. "
             "Read and Task use separate API calls.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    paths = [output_dir / f"coco_c2_ablation.{extension}" for extension in ("png", "pdf")]
    fig.savefig(paths[0], dpi=220)
    fig.savefig(paths[1])
    plt.close(fig)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("--models", nargs="+", help="model IDs in the desired 8B to 32B plot order")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports/figures")
    parser.add_argument("--only-ablation", action="store_true",
                        help="generate only the matched 40-image C2 ablation figure")
    args = parser.parse_args()
    import matplotlib.pyplot as plt
    data = json.loads(args.summary.read_text(encoding="utf-8"))["models"]
    models = args.models or list(data)
    unknown = set(models) - set(data)
    if unknown:
        parser.error(f"Unknown models: {sorted(unknown)}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.only_ablation:
        for path in plot_ablation(data, models, args.output_dir):
            print(path)
        return

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for axis, location in zip(axes, ("margin", "object")):
        variant = f"C2_label_{location}"
        axis.plot(models, [rate(data[m], variant, "read_0.8") for m in models], marker="o", label="P(Read)")
        axis.plot(models, [rate(data[m], variant, "obey_given_read_0.8") for m in models],
                  marker="s", label="Task ASR on Read-positive images")
        axis.set(title=f"C2 {location}", xlabel="Model", ylim=(0, 100))
        axis.tick_params(axis="x", rotation=25)
        axis.grid(alpha=0.25)
    axes[0].set_ylabel("Percent")
    axes[1].legend()
    fig.tight_layout()
    path = args.output_dir / "coco_c2_scaling.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    print(path)

    for path in plot_ablation(data, models, args.output_dir):
        print(path)


if __name__ == "__main__":
    main()
