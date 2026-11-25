"""Run the available-model Formal matrix in resumable sequential stages."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "reports/mind2web/formal_v2_manifest.provisional.jsonl"
REACT_RUN = "runs/mind2web_react_formal_v2"
PROBE_RUN = "runs/mind2web_probe_formal_v2"
MODELS = ("M1", "M2", "M3", "M4", "X9", "X27")
LOG = ROOT / "runs/mind2web_formal_pipeline.log"
STATE = ROOT / "runs/mind2web_formal_pipeline.json"


def run(name: str, command: list[str]) -> None:
    started = time.time()
    with LOG.open("a", encoding="utf-8") as log:
        log.write(f"\nSTART {name} {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.flush()
        process = subprocess.Popen([sys.executable, *command], cwd=ROOT,
                                   stdout=log, stderr=subprocess.STDOUT)
        exit_code = process.wait()
        log.write(f"END {name} exit={exit_code} elapsed_s={time.time()-started:.1f}\n")
    status = {"stage": name, "exit_code": exit_code, "completed_at": time.time(),
              "elapsed_s": round(time.time() - started, 1)}
    STATE.write_text(json.dumps(status, indent=2), encoding="utf-8")
    if exit_code:
        raise RuntimeError(f"{name} failed with exit code {exit_code}; see {LOG}")


def main() -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    common = ["--manifest", MANIFEST, "--split", "formal", "--models", *MODELS]
    run("validate", ["src/analysis/validate_mind2web_variant.py",
                     "--manifest", MANIFEST, "--split", "formal",
                     "--expected-cases", "60", "--require-balanced-subtypes"])
    run("three_case_react", ["src/eval/run_mind2web_react_pilot.py",
                             *common, "--cases", "3", "--stage", "base",
                             "--run-dir", REACT_RUN, "--retry-failed"])
    run("react_matrix_and_defenses", ["src/eval/run_mind2web_react_pilot.py",
                                      *common, "--cases", "60", "--stage", "all",
                                      "--run-dir", REACT_RUN, "--retry-failed"])
    run("paired_a2_wording", ["src/eval/run_mind2web_react_pilot.py",
                               *common, "--cases", "60", "--stage", "base",
                               "--variants", "A2G", "A2C", "--run-dir", REACT_RUN,
                               "--retry-failed"])
    run("independent_plan_read", ["src/eval/run_mind2web_pilot.py",
                                   *common, "--cases", "60", "--stage", "baseline",
                                   "--kinds", "plan", "read", "--run-dir", PROBE_RUN,
                                   "--retry-failed"])
    run("summary", ["src/analysis/summarize_mind2web_react_pilot.py",
                    "--manifest", MANIFEST, "--split", "formal", "--cases", "60",
                    "--models", *MODELS, "--run-dir", REACT_RUN,
                    "--direct-run-dir", PROBE_RUN,
                    "--output", "reports/mind2web/formal_v2_metrics.json"])


if __name__ == "__main__":
    main()
