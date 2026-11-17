#!/usr/bin/env python3
"""Predict every published row and score it with the official grader.

    python scripts/evaluate.py --out results/raw/<run-id> [--url http://127.0.0.1:8000]
                               [--model-dir models] [--policy policy/policy.yaml]

With --url the rows go through the running HTTP service, which is how the reviewer scores.
Without it the pipeline is called in-process (faster, used for ablations).

Rows are first reduced to the fields a reviewer sends (id, context, turn_index) with the
same allowlist as reference/evaluation_inputs.py. Labels never reach the pipeline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "reference"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(REF))
from evaluation_inputs import project  # noqa: E402


def load(path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--url")
    ap.add_argument("--model-dir")
    ap.add_argument("--policy")
    ap.add_argument("--mode", choices=["route_to_human", "follow_label"],
                    help="override the policy file's on_conflict (in-process only)")
    ap.add_argument("--no-turn-index", action="store_true",
                    help="drop turn_index from every request, to measure reliance on it")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    sets = {"dev": load(REF / "dev.jsonl"), "noisy": load(REF / "dev_noisy.jsonl"),
            "hostile": load(REF / "hostile.jsonl")}
    inputs = {name: [project("OP-06", r) for r in rows] for name, rows in sets.items()}
    if args.no_turn_index:
        for rows in inputs.values():
            for r in rows:
                r.pop("turn_index", None)

    if args.url:
        def predict(payload):
            req = urllib.request.Request(args.url.rstrip("/") + "/triage",
                                         data=json.dumps(payload).encode("utf-8"),
                                         headers={"content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        versions = json.loads(urllib.request.urlopen(args.url.rstrip("/") + "/healthz", timeout=10).read())
    else:
        from triage.pipeline import Triage
        triage = Triage(args.model_dir, args.policy)
        if args.mode:
            triage.policy.mode = args.mode
        predict = triage.handle
        versions = triage.versions

    started = time.time()
    preds = {}
    for name, rows in inputs.items():
        preds[name] = [predict(r) for r in rows]
        (out / f"{name}_predictions.jsonl").write_text(
            "".join(json.dumps(p) + "\n" for p in preds[name]), encoding="utf-8")
    took = time.time() - started
    everything = preds["dev"] + preds["noisy"] + preds["hostile"]
    (out / "predictions.jsonl").write_text("".join(json.dumps(p) + "\n" for p in everything),
                                           encoding="utf-8")

    subprocess.run([sys.executable, str(REF / "grader.py"), "--pred", str(out / "predictions.jsonl"),
                    "--gold", str(REF / "dev.jsonl"), "--noisy", str(REF / "dev_noisy.jsonl"),
                    "--hostile", str(REF / "hostile.jsonl"), "--schema", str(REF / "schema.json"),
                    "--report", str(out / "report.json")], check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "taxonomy.py"), "--pred",
                    str(out / "predictions.jsonl"), "--out", str(out / "taxonomy.json")],
                   check=True, stdout=subprocess.DEVNULL)

    labelled = preds["dev"] + preds["noisy"]
    gold = {r["id"]: r for r in sets["dev"] + sets["noisy"]}
    auto = [p for p in labelled if not p["needs_human"]]
    summary = {
        "via": "http" if args.url else "in-process",
        "versions": versions,
        "seconds": round(took, 1),
        "rows": len(everything),
        "input_sha256": hashlib.sha256("".join(
            json.dumps(r, sort_keys=True) for rows in inputs.values() for r in rows).encode()).hexdigest(),
        "needs_human_share": round(1 - len(auto) / len(labelled), 4),
        "automated_action_accuracy": round(
            sum(p["action"] == gold[p["id"]]["action"] for p in auto) / max(1, len(auto)), 4),
        "abstentions": sum("error" in p for p in labelled),
        "policy_conflicts": sum("policy_conflict" in p for p in labelled),
        "no_turn_index": args.no_turn_index,
        "mode_override": args.mode,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
