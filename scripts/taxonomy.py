#!/usr/bin/env python3
"""Sort a run's errors into named categories, so runs can be compared category by category.

    python scripts/taxonomy.py --pred results/raw/<run>/predictions.jsonl --out <file.json>

Action errors, each counted once, first matching rule wins:
  wrong_flow      predicted intent belongs to a different flow than the gold intent
  sibling_intent  right flow, wrong intent
  repeated_step   right intent, but the predicted action is a step the context shows as done
  wrong_step      right intent, some other wrong action
Intent errors: wrong_flow or sibling_intent.
Every count is also split by whether the 8-turn window shows the start of the dialogue
(`full_window`) and, for noisy rows, by noise kind.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from triage.events import done_actions  # noqa: E402
from triage.sanitise import clean_context  # noqa: E402

REF = ROOT / "reference"


def load(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()

    train = load(REF / "train.jsonl.gz")
    flow_of = {r["intent"]: r["flow"] for r in train}
    preds = {p["id"]: p for p in load(args.pred)}
    rows = [("clean", r) for r in load(REF / "dev.jsonl")] + \
           [(r["noise_kind"], r) for r in load(REF / "dev_noisy.jsonl")]

    n = Counter()
    action_err = defaultdict(Counter)
    intent_err = defaultdict(Counter)
    for kind, row in rows:
        pred = preds.get(row["id"], {})
        window = "full_window" if len(row["context"]) < 8 else "cut_window"
        slices = ["all", window, "noisy" if kind != "clean" else "clean"]
        if kind != "clean":
            slices.append("noise:" + kind)
        for s in slices:
            n[s] += 1
        p_intent, p_action = pred.get("intent"), pred.get("action")
        same_flow = flow_of.get(p_intent) == row["flow"]
        if p_intent != row["intent"]:
            cat = "sibling_intent" if same_flow else "wrong_flow"
            for s in slices:
                intent_err[s][cat] += 1
        if p_action != row["action"]:
            if not same_flow:
                cat = "wrong_flow"
            elif p_intent != row["intent"]:
                cat = "sibling_intent"
            elif p_action in done_actions(clean_context(row["context"]).turns):
                cat = "repeated_step"
            else:
                cat = "wrong_step"
            for s in slices:
                action_err[s][cat] += 1

    report = {"rows": dict(n), "action_errors": {}, "intent_errors": {}}
    for name, table in (("action_errors", action_err), ("intent_errors", intent_err)):
        for s in n:
            total = sum(table[s].values())
            report[name][s] = {"n": n[s], "errors": total, "error_rate": round(total / n[s], 4),
                               **{k: v for k, v in sorted(table[s].items())}}
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name in ("action_errors", "intent_errors"):
        print(name)
        for s in ("all", "clean", "noisy", "full_window", "cut_window"):
            print(f"  {s:<12}", report[name][s])
        for s in sorted(k for k in n if k.startswith("noise:")):
            print(f"  {s:<18}", report[name][s])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
