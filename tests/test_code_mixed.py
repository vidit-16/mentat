"""Hinglish in the last customer turn must not make the service more sure of itself.

hinglish-001 found that appending the published code-mixed phrase raised confidence on 90% of
dev rows and moved wrong answers away from a person, through the unseen_words signal. The
model's own scores went down; confidence must not go the other way.
"""
from __future__ import annotations

import sys

from conftest import ROOT, project

sys.path.insert(0, str(ROOT / "scripts"))
from hinglish_slice import last_customer, rewrite  # noqa: E402


def test_code_mixed_suffix_does_not_raise_confidence(triage, dev_rows):
    rows = [r for r in dev_rows if last_customer(r["context"]) is not None][:400]
    clean_conf, mixed_conf, clean_human, mixed_human = 0.0, 0.0, 0, 0
    for row in rows:
        payload = project(row)
        clean = triage.handle(payload)
        i = last_customer(payload["context"])
        payload["context"][i]["text"] = rewrite(payload["context"][i]["text"], "swaps")
        mixed = triage.handle(payload)
        clean_conf += clean["confidence"]
        mixed_conf += mixed["confidence"]
        clean_human += clean["needs_human"]
        mixed_human += mixed["needs_human"]
    assert mixed_conf <= clean_conf + 0.002 * len(rows), (clean_conf / len(rows), mixed_conf / len(rows))
    assert mixed_human >= clean_human - len(rows) // 100, (clean_human, mixed_human)
