# Member 1 COCO C0/C1/C2 delivery

This PR delivers the frozen COCO split, review records, C0/C1/C2 rendering and evaluation code, M1–M4 formal statistics, and the C2 ablation figure. It contains no Mind2Web files. The accepted Pilot protocol v3 narrowed this run to the four Qwen3-VL models; it was revised after Pilot, not preregistered.

## Files to hand off

| Purpose | Files |
| --- | --- |
| Shared split and review trail | `data/manifests/coco_base_120.json`; `reports/coco/coco_review.csv`, `coco_mcq_review.csv`, `coco_base_120.provisional.json`; `candidate_pool.json`, `audit_stats.json` |
| Render recipe and frozen indexes | `src/render/prepare_coco_manifest.py`, `select_coco.py`, `render_coco_c012.py`; `data/manifests/coco_c012_manifest.jsonl`, `coco_c2_ablation_manifest.jsonl` |
| Prompt, runner, analysis | `configs/prompts.yaml`, `src/common/prompts.py`, `src/eval/run_coco_c012.py`, `src/analysis/analyze_coco_c012.py`, `plot_coco_c2.py` |
| Gate and visual evidence | `pilot_protocol_v3_proposal.md`, `coco_protocol_v3_pilot_all_qwen.json`, `member1_formal_freeze_check.md`, `member1_formal_render_check.md`, `formal_c012_render_contact.jpg` |
| Formal results | `coco_c012_formal_summary.json`, `coco_c012_formal_report.md`, `coco_c012_formal_usage.json`, `reports/figures/coco_c2_ablation.png` and `.pdf` |

The frozen split has 12 Pilot, 120 Formal and 12 Reserve images. Its SHA-256 is `258132c4e96669dde32b72a4e4f6f6b41d371998f72477d01d1f2777ef32815e`. The two frozen render indexes specify 660 C0/C1/C2 images and 132 C2 ablation images, including 12 Pilot ablations. The figure compares M1 and M3 on the same first 40 Formal images.

## Reproduction and limits

COCO original photographs, generated full-size PNGs, API keys and per-request `runs/*.jsonl` remain local and are excluded from Git. Download the official COCO val2017 images and annotations with `python scripts/download_coco.py`; then render from the frozen split with `python -m src.render.render_coco_c012`. A recipient should check the regenerated PNG hashes against the frozen JSONL indexes before using them with C3. Font or Pillow differences across machines can change PNG bytes even when the visual layout is equivalent; the indexes record the exact files used in the formal run.

Formal M1–M4 coverage is 3,840/3,840 planned successful requests. `coco_c012_formal_usage.json` records token usage and local raw-log SHA-256 values so results can be checked against the original logs. Those logs are required to recompute the statistics from individual responses; the committed summary alone cannot reproduce the paired Bootstrap or McNemar calculation. Actual SiliconFlow charges still require the account bill.

To regenerate the C2 ablation figure from the committed summary (no API call):

```powershell
python -m src.analysis.plot_coco_c2 reports/coco/coco_c012_formal_summary.json --only-ablation
```

`read_exact` in the left panel is exact normalized transcription from an independent Read call. The right panel is the fraction of Task calls that output the wrong option. The panels should not be read as a within-call causal chain.
