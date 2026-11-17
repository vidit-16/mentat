#!/usr/bin/env python3
"""Write the first draft of policy/policy.yaml.

    python scripts/build_policy.py [--out policy/policy.yaml] [--check]

Source of the permitted lists: the `permitted_actions` field of the published training split.
The organisers built that field from guidelines.json and resolved the button names into the
action names the labels use. It is the same for every row of a flow, so it is a property of
the flow, not of a row. This script also reads guidelines.json and reports any button it lists
that the resolved list does not cover.

After this first draft the YAML file is edited by hand. Rerunning this script overwrites it,
so it refuses to do that unless --force is given.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "reference"

HIGH_CONSEQUENCE = ["offer-refund", "promo-code", "make-purchase", "update-order",
                    "update-account", "make-password"]

HEADER = """\
# Policy table for the triage service.
#
# This file decides what the service is allowed to answer. The classifier proposes; this
# table disposes. Edit it, run `scripts/reproduce.sh policy-check`, restart the service.
#
# version          shown in every response and every log line. Change it with every edit.
# on_conflict      route_to_human: never return an action the flow does not permit; return
#                    the best permitted one and send the message to a person.
#                  follow_label: return what agents usually did, even when the written
#                    procedure does not list it. Kept for measurement only.
# aliases          label name -> name used in the written procedure, where they differ.
# high_consequence actions that move money or change an account. With require_system_turn
#                  they are only returned when the conversation shows at least one system
#                  step (an `action` turn), which a customer cannot write.
# flows            for each flow: the intents that belong to it and the permitted actions.
"""


def slug(button: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", button.lower()).strip("-")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "policy" / "policy.yaml"))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--version", default="2026-11-17.1")
    args = ap.parse_args()

    out = Path(args.out)
    if out.exists() and not args.force:
        sys.exit(f"{out} exists; it is hand-maintained. Use --force to overwrite.")

    with gzip.open(REF / "train.jsonl.gz", "rt", encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    permitted, intents = {}, {}
    for r in rows:
        flow = r["flow"]
        current = sorted(r["permitted_actions"])
        if permitted.setdefault(flow, current) != current:
            sys.exit(f"flow {flow} has more than one permitted list in the data")
        intents.setdefault(flow, set()).add(r["intent"])

    guidelines = json.loads((REF / "guidelines.json").read_text(encoding="utf-8"))
    for flow_title, spec in guidelines.items():
        flow = slug(flow_title).replace("-", "_")
        buttons = {slug(a["button"]) for sub in spec["subflows"].values() for a in sub["actions"]}
        missing = sorted(b for b in buttons if b not in permitted.get(flow, []))
        print(f"guidelines.json {flow_title!r}: {len(buttons)} buttons, "
              f"not in resolved list: {missing or 'none'}")
    print("flows without a section in guidelines.json:",
          sorted(set(permitted) - {slug(t).replace('-', '_') for t in guidelines}) or "none")

    lines = [HEADER, f'version: "{args.version}"', "on_conflict: route_to_human", "",
             "aliases:", "  membership: membership-privileges", "",
             "high_consequence:", "  require_system_turn: true", "  actions:"]
    lines += [f"    - {a}" for a in HIGH_CONSEQUENCE]
    lines += ["", "flows:"]
    for flow in sorted(permitted):
        lines.append(f"  {flow}:")
        lines.append("    intents:")
        lines += [f"      - {i}" for i in sorted(intents[flow])]
        lines.append("    permitted:")
        lines += [f"      - {a}" for a in permitted[flow]]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
