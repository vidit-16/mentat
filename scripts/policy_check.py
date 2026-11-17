#!/usr/bin/env python3
"""Validate a policy file and show what it changes on the published dev rows.

    python scripts/policy_check.py [policy/policy.yaml] [--against <older policy file>]

Prints problems that would stop the service from starting (unknown action names, an intent
under two flows), warnings (names that are not labels, intents without a flow), and for dev:
how many answers change compared with --against (default: the committed copy in git, or
nothing if git is unavailable).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "reference"))
from evaluation_inputs import project  # noqa: E402
from triage.pipeline import Triage  # noqa: E402
from triage.policy import PolicyError, describe  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("policy", nargs="?", default=str(ROOT / "policy" / "policy.yaml"))
    ap.add_argument("--against")
    args = ap.parse_args()

    try:
        new = Triage(policy_path=args.policy)
    except PolicyError as exc:
        print(f"POLICY REFUSED: {exc}")
        return 1
    info = describe(new.policy)
    print(f"policy {info['version']}  on_conflict={info['on_conflict']}")
    for flow, names in info["written_names_that_are_not_labels"].items():
        print(f"  note: {flow} lists names no label uses: {', '.join(names)}")
    if info["intents_without_a_flow"]:
        print("  WARNING: intents with no flow (always answered 'none'):",
              ", ".join(info["intents_without_a_flow"]))

    old_path = args.against
    if not old_path:
        try:
            text = subprocess.run(["git", "show", "HEAD:policy/policy.yaml"], cwd=ROOT,
                                  capture_output=True, text=True, check=True).stdout
            tmp = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
            tmp.write(text)
            tmp.close()
            old_path = tmp.name
        except (OSError, subprocess.CalledProcessError):
            old_path = None
    rows = [json.loads(line) for line in
            (ROOT / "reference" / "dev.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if old_path:
        old = Triage(policy_path=old_path)
        changed = []
        for row in rows:
            a, b = old.handle(project("OP-06", row)), new.handle(project("OP-06", row))
            if (a["action"], a["needs_human"]) != (b["action"], b["needs_human"]):
                changed.append((row["id"], a["action"], b["action"], a["needs_human"], b["needs_human"]))
        print(f"dev rows whose answer changes vs {old_path}: {len(changed)} of {len(rows)}")
        for c in changed[:15]:
            print(f"  {c[0]}: {c[1]} -> {c[2]}  needs_human {c[3]} -> {c[4]}")
    outs = [new.handle(project("OP-06", r)) for r in rows]
    print(f"dev with this policy: action accuracy "
          f"{sum(o['action'] == r['action'] for o, r in zip(outs, rows)) / len(rows):.4f}, "
          f"sent to a person {sum(o['needs_human'] for o in outs) / len(rows):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
