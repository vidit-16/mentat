#!/usr/bin/env python3
"""Paired comparison of two evaluation runs on the same dev + noisy rows.

    python scripts/compare_runs.py results/raw/dev-006 results/raw/dev-007

Prints action accuracy, top-70% error ratio and accuracy of the 85% most confident rows for
each run, then 95% intervals for the differences (second minus first) from 1,000 paired
bootstrap resamples of the rows, seed 1.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def scores(pred: dict, gold: dict, ids: list[str]) -> tuple[float, float, float]:
    right = {i: pred[i]["action"] == gold[i] for i in set(ids)}
    acc = sum(right[i] for i in ids) / len(ids)
    order = sorted(ids, key=lambda i: -pred[i]["confidence"])
    top70 = order[: round(0.7 * len(order))]
    err70 = 1 - sum(right[i] for i in top70) / len(top70)
    top85 = order[: round(0.85 * len(order))]
    return acc, err70 / (1 - acc), sum(right[i] for i in top85) / len(top85)


def main() -> int:
    first, second = (Path(a) for a in sys.argv[1:3])
    gold = {}
    for name in ("dev.jsonl", "dev_noisy.jsonl"):
        for row in load(ROOT / "reference" / name):
            gold[row["id"]] = row["action"]
    a = {p["id"]: p for p in load(first / "predictions.jsonl") if p["id"] in gold}
    b = {p["id"]: p for p in load(second / "predictions.jsonl") if p["id"] in gold}
    ids = sorted(set(a) & set(b))
    names = ("action accuracy", "top-70% error ratio", "accuracy of 85% most confident")
    sa, sb = scores(a, gold, ids), scores(b, gold, ids)
    print(f"{len(ids)} rows")
    print(f"{'':32s} {first.name:>14s} {second.name:>14s}")
    for n, x, y in zip(names, sa, sb):
        print(f"{n:32s} {x:14.4f} {y:14.4f}")
    rng = random.Random(1)
    diffs = []
    for _ in range(1000):
        s = [rng.choice(ids) for _ in ids]
        diffs.append([y - x for x, y in zip(scores(a, gold, s), scores(b, gold, s))])
    print("95% interval of the difference (second - first):")
    for k, n in enumerate(names):
        v = sorted(d[k] for d in diffs)
        print(f"  {n:30s} {v[25]:+.4f} to {v[974]:+.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
