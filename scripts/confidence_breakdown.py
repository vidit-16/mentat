#!/usr/bin/env python3
"""Which confidence signals move when the Hinglish suffix is added, averaged over dev.

    python scripts/confidence_breakdown.py [--variant suffix] > results/raw/<run>/confidence_breakdown.txt

For each row, records the 16 confidence signals for the clean and rewritten row and prints
the mean change in the confidence logit that each signal causes (coef * change / scale).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from hinglish_slice import last_customer, rewrite  # noqa: E402
from triage.confidence import FEATURES  # noqa: E402
from triage.pipeline import Triage  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="suffix", choices=["suffix", "swaps", "heavy"])
    ap.add_argument("--model-dir", default=str(ROOT / "models"))
    args = ap.parse_args()

    triage = Triage(model_dir=Path(args.model_dir))
    seen: list[np.ndarray] = []
    estimate = triage.conf.estimate

    def recording(x):
        seen.append(np.asarray(x, dtype=float))
        return estimate(x)

    triage.conf.estimate = recording
    dev = [json.loads(line) for line in
           (ROOT / "reference" / "dev.jsonl").read_text(encoding="utf-8").splitlines()]
    dev = [r for r in dev if last_customer(r["context"]) is not None]
    before, after = [], []
    for row in dev:
        payload = {"id": row["id"], "context": [dict(t) for t in row["context"]]}
        if "turn_index" in row:
            payload["turn_index"] = row["turn_index"]
        seen.clear()
        triage.handle(payload)
        before.append(seen[-1])
        i = last_customer(payload["context"])
        payload["context"][i]["text"] = rewrite(payload["context"][i]["text"], args.variant)
        seen.clear()
        triage.handle(payload)
        after.append(seen[-1])
    before, after = np.array(before), np.array(after)
    shift = ((after - before) / triage.conf.scale * triage.conf.coef).mean(axis=0)
    print(f"variant {args.variant}, {len(dev)} rows, model {triage.model.version}")
    print(f"{'signal':22s} {'mean clean':>11s} {'mean rewritten':>15s} {'logit change':>13s} {'coef':>7s}")
    for k in np.argsort(-np.abs(shift)):
        print(f"{FEATURES[k]:22s} {before[:, k].mean():11.4f} {after[:, k].mean():15.4f} "
              f"{shift[k]:+13.4f} {triage.conf.coef[k]:+7.3f}")
    i = FEATURES.index("unseen_words")
    print(f"training mean / scale of unseen_words: {triage.conf.mean[i]:.6f} / {triage.conf.scale[i]:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
