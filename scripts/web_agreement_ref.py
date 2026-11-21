#!/usr/bin/env python3
"""Write the inputs and the Python service's answers for the browser-engine agreement test.

    python scripts/web_agreement_ref.py --out <dir>
    node scripts/web_agreement.mjs --dir <dir>

Inputs: every published row (2,000 dev, 300 noisy, 9 hostile), reduced to what a client
sends, plus the 68 extended hostile envelopes from tests/cases.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "reference"))
sys.path.insert(0, str(ROOT / "tests"))

from cases import valid_cases  # noqa: E402
from evaluation_inputs import project  # noqa: E402
from triage.pipeline import Triage  # noqa: E402

DROP = ("latency_ms", "cost_usd")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for name in ("dev.jsonl", "dev_noisy.jsonl", "hostile.jsonl"):
        for line in (ROOT / "reference" / name).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(project("OP-06", json.loads(line)))
    rows += valid_cases()

    triage = Triage()
    with open(out / "inputs.jsonl", "w", encoding="utf-8", newline="\n") as fi, \
         open(out / "python.jsonl", "w", encoding="utf-8", newline="\n") as fo:
        for row in rows:
            fi.write(json.dumps(row) + "\n")
            resp = {k: v for k, v in triage.handle(row).items() if k not in DROP}
            fo.write(json.dumps(resp) + "\n")
    print(f"{len(rows)} inputs, model {triage.model.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
