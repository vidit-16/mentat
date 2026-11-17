#!/usr/bin/env python3
"""Write results/manifest.json in the SUBMISSION_SCHEMA.md (revision 4) shape.

    python scripts/build_manifest.py

Run list comes from results/runs.yaml, which is edited by hand as runs happen (one entry per
run, failed ones included). This script fills in hashes and measured numbers from the raw
files, so a number in the manifest is always one that a raw file supports.

`claimed` holds development measurements of the run named in runs.yaml as `submitted: true`
and must match submission.yaml exactly. Unmeasured values are null.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe(rel: str) -> Path:
    path = (ROOT / rel).resolve()
    if ROOT.resolve() not in path.parents or path.is_symlink():
        sys.exit(f"unsafe artifact path: {rel}")
    if not path.exists():
        sys.exit(f"missing artifact: {rel}")
    return path


def main() -> int:
    spec = yaml.safe_load((RESULTS / "runs.yaml").read_text(encoding="utf-8"))
    inputs = {name: sha256(ROOT / "reference" / name)
              for name in ("dev.jsonl", "dev_noisy.jsonl", "hostile.jsonl", "train.jsonl.gz")}
    runs, seen, submitted = [], set(), None
    for entry in spec["runs"]:
        rid = entry["run_id"]
        if rid in seen:
            sys.exit(f"duplicate run_id {rid}")
        seen.add(rid)
        raw = safe(entry["raw_path"])
        run = {"run_id": rid, "date": entry["date"], "seed": entry.get("seed"),
               "model": entry["model"], "status": entry["status"],
               "input_sha256": inputs[entry.get("input", "dev.jsonl")],
               "raw_path": entry["raw_path"],
               "raw_sha256": sha256(raw) if raw.is_file() else None,
               "description": entry["description"],
               "config": entry.get("config", {}),
               "api_calls": entry.get("api_calls", 0),
               "input_tokens": entry.get("input_tokens", 0),
               "output_tokens": entry.get("output_tokens", 0),
               "cost_usd": entry.get("cost_usd", 0.0)}
        report = raw.parent / "report.json" if raw.is_file() else raw / "report.json"
        if report.exists():
            r = json.loads(report.read_text(encoding="utf-8"))
            run["metrics"] = {
                "intent_accuracy": r["intent"]["accuracy_all"],
                "macro_f1": r["intent"]["macro_f1_all"],
                "action_accuracy": r["action"]["accuracy_all"],
                "noisy_accuracy": r["action"]["accuracy_noisy"],
                "noisy_gap": r["action"]["noisy_gap"],
                "schema_valid_pct": round(r["schema"]["valid_rate_all_inputs"] * 100, 4),
                "top70_error_ratio": r["confidence"]["top70_error_ratio"],
                "policy_violation_rate": r["policy"]["violation_rate"],
                "gold_policy_violation_rate": r["policy"]["gold_violation_rate"],
                "grader_version": r["grader_version"],
            }
        if entry.get("submitted"):
            if submitted:
                sys.exit("more than one run marked submitted")
            submitted = run
        runs.append(run)
    if not submitted or "metrics" not in submitted:
        sys.exit("no submitted run with a grader report")

    bench_path = RESULTS / "latency_bench.json"
    latency_p95_s = None
    cost_per_message = None
    if bench_path.exists():
        bench = json.loads(bench_path.read_text(encoding="utf-8"))
        c8 = next((r for r in bench["runs"] if r["concurrency"] == 8), None)
        if c8 and c8["latency_ms"]:
            latency_p95_s = round(c8["latency_ms"]["p95"] / 1000, 4)
            per_1000 = c8["compute_usd_per_1000_messages_at_this_throughput"]
            cost_per_message = round(per_1000 / 1000, 9) if per_1000 is not None else None

    m = submitted["metrics"]
    claimed = {"intent_accuracy": m["intent_accuracy"], "macro_f1": m["macro_f1"],
               "action_accuracy": m["action_accuracy"], "noisy_accuracy": m["noisy_accuracy"],
               "schema_valid_pct": m["schema_valid_pct"],
               "top70_error_ratio": m["top70_error_ratio"],
               "cost_per_message_usd": cost_per_message, "latency_p95_s": latency_p95_s}
    spend = round(sum(r["cost_usd"] for r in runs), 6)
    manifest = {
        "problem": "OP-06",
        "claimed": claimed,
        "submitted_run": submitted["run_id"],
        "spend": {"results_usd": spend, "compute_usd": 0,
                  "note": "API spend at pinned list prices for every run below, failed runs "
                          "included. Compute ran on the author's own laptop."},
        "models": spec["models"],
        "reference": spec["reference"],
        "artifacts": {name: {"path": f"results/{name}", "sha256": sha256(RESULTS / name)}
                      for name in ("dev_predictions.jsonl", "noisy_predictions.jsonl",
                                   "hostile_results.jsonl", "latency_bench.json")
                      if (RESULTS / name).exists()},
        "runs": runs,
    }
    (RESULTS / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"claimed": claimed, "runs": len(runs), "spend_usd": spend}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
