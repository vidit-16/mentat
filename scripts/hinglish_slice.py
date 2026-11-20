#!/usr/bin/env python3
"""Recheck code-mixed (Hinglish) robustness on all of dev, not just the 50 published rows.

    python scripts/hinglish_slice.py --out results/raw/hinglish-001 [--model-dir models]

Writes predictions.jsonl (every row, clean and rewritten) and slice_report.json.

The published code_mixed rows were made from dev rows by rewriting the last customer turn.
Comparing them with their clean originals word by word gives the rewrite: 43 of 50 append
"thoda jaldi karo please", the rest also swap "my" -> "mera" or misspell "order" -> "ordr".
This script applies that rewrite to every dev row, plus a heavier variant with more Hindi
function words that the published generator does not use, and compares each with the clean
row through the same pipeline. Labels do not change, so any drop is the rewrite's cost.

Variants:
  suffix   append " thoda jaldi karo please" (the published rewrite, 43 of 50)
  swaps    suffix, plus my -> mera and order -> ordr (the remaining published rows)
  heavy    swaps, plus a fixed list of Hindi words for common English ones. Not in the
           published generator; a stress test for Hinglish the hidden set might not contain.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from triage.pipeline import Triage  # noqa: E402

SUFFIX = "thoda jaldi karo please"
SWAPS = {"my": "mera", "order": "ordr"}
HEAVY = {"my": "mera", "order": "ordr", "is": "hai", "not": "nahi", "and": "aur",
         "yes": "haan", "no": "nahi", "what": "kya", "why": "kyun", "now": "abhi",
         "still": "abhi bhi", "please": "plz", "i want": "mujhe chahiye", "i need": "mujhe chahiye",
         "with": "ke saath", "but": "lekin", "where": "kahan", "when": "kab"}


def swap(text: str, table: dict[str, str]) -> str:
    for src in sorted(table, key=len, reverse=True):
        text = re.sub(rf"(?<![\w<]){re.escape(src)}(?![\w>])", table[src], text, flags=re.I)
    return text


def rewrite(text: str, kind: str) -> str:
    if kind == "swaps":
        text = swap(text, SWAPS)
    elif kind == "heavy":
        text = swap(text, HEAVY)
    return f"{text.rstrip()} {SUFFIX}"


def last_customer(context: list[dict]) -> int | None:
    for i in range(len(context) - 1, -1, -1):
        if context[i]["speaker"] == "customer":
            return i
    return None


def summarise(rows: list[dict], outs: list[dict]) -> dict:
    n = len(rows)
    auto = [(r, o) for r, o in zip(rows, outs) if not o["needs_human"]]
    return {
        "rows": n,
        "intent_accuracy": round(sum(o["intent"] == r["intent"] for r, o in zip(rows, outs)) / n, 4),
        "action_accuracy": round(sum(o["action"] == r["action"] for r, o in zip(rows, outs)) / n, 4),
        "needs_human_rate": round(1 - len(auto) / n, 4),
        "automated_action_accuracy": round(sum(o["action"] == r["action"] for r, o in auto)
                                           / max(len(auto), 1), 4),
        "mean_confidence": round(sum(o["confidence"] for o in outs) / n, 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--model-dir", default=str(ROOT / "models"))
    args = ap.parse_args()
    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    dev_path = ROOT / "reference" / "dev.jsonl"
    dev = [json.loads(line) for line in dev_path.read_text(encoding="utf-8").splitlines()]
    dev = [r for r in dev if last_customer(r["context"]) is not None]
    triage = Triage(model_dir=Path(args.model_dir))

    def ask(row: dict, kind: str | None) -> dict:
        context = [dict(t) for t in row["context"]]
        if kind:
            i = last_customer(context)
            context[i]["text"] = rewrite(context[i]["text"], kind)
        payload = {"id": row["id"], "context": context}
        if "turn_index" in row:
            payload["turn_index"] = row["turn_index"]
        out = triage.handle(payload)
        out.pop("latency_ms", None)
        return out

    started = time.time()
    clean = [ask(r, None) for r in dev]
    report = {"model_version": triage.model.version, "policy_version": triage.policy.version,
              "input_sha256": hashlib.sha256(dev_path.read_bytes()).hexdigest(),
              "clean": summarise(dev, clean), "variants": {}}
    lines = []
    for kind in ("suffix", "swaps", "heavy"):
        outs = [ask(r, kind) for r in dev]
        s = summarise(dev, outs)
        pairs = list(zip(dev, clean, outs))
        s["action_changed"] = sum(c["action"] != o["action"] for _, c, o in pairs)
        s["action_right_to_wrong"] = sum(c["action"] == r["action"] != o["action"] for r, c, o in pairs)
        s["action_wrong_to_right"] = sum(c["action"] != r["action"] == o["action"] for r, c, o in pairs)
        s["intent_changed"] = sum(c["intent"] != o["intent"] for _, c, o in pairs)
        s["newly_sent_to_person"] = sum(o["needs_human"] and not c["needs_human"] for _, c, o in pairs)
        s["wrong_and_automated"] = sum(o["action"] != r["action"] and not o["needs_human"]
                                       for r, _, o in pairs)
        report["variants"][kind] = s
        for r, c, o in pairs:
            lines.append(json.dumps({"id": r["id"], "variant": kind, "gold_intent": r["intent"],
                                     "gold_action": r["action"], "clean": c, "rewritten": o}))
    report["clean"]["wrong_and_automated"] = sum(
        c["action"] != r["action"] and not c["needs_human"] for r, c in zip(dev, clean))
    report["seconds"] = round(time.time() - started, 1)

    (out_dir / "predictions.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8",
                                               newline="\n")
    (out_dir / "slice_report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8",
                                         newline="\n")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
