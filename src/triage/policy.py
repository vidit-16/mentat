"""The policy table and the gate that enforces it.

The table is a YAML file the support manager owns. The gate runs after the classifiers and
reads only scores and the table, never the message text. Whatever the classifiers say, the
action that leaves this module is in the permitted set of the chosen flow, or it is "none".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

from .respond import NONE_ACTION

MODES = ("route_to_human", "follow_label")


class PolicyError(ValueError):
    pass


@dataclass
class Decision:
    intent: str
    flow: str
    action: str
    p_action: float            # model probability of the returned action
    p_flow: float
    p_intent: float
    conflict: str | None = None       # the classifier's first choice, when it was not permitted
    blocked: str | None = None        # a high-consequence action held back for lack of evidence
    notes: list[str] = field(default_factory=list)


class Policy:
    def __init__(self, data: dict, known_intents: list[str], known_actions: list[str]):
        if not isinstance(data, dict):
            raise PolicyError("policy file must be a mapping")
        self.version = str(data.get("version", "unversioned"))
        self.mode = data.get("on_conflict", "route_to_human")
        if self.mode not in MODES:
            raise PolicyError(f"on_conflict must be one of {MODES}")
        self.aliases = dict(data.get("aliases") or {})
        hc = data.get("high_consequence") or {}
        self.high_consequence = frozenset(hc.get("actions") or [])
        self.require_system_turn = bool(hc.get("require_system_turn", True))
        flows = data.get("flows")
        if not isinstance(flows, dict) or not flows:
            raise PolicyError("policy file has no flows")

        self.known_actions = list(known_actions)
        self.flow_names = sorted(flows)
        self.flow_of: dict[str, str] = {}
        self.permitted: dict[str, frozenset] = {}
        self.unknown_names: dict[str, list[str]] = {}
        known = set(known_actions)
        for name in self.flow_names:
            spec = flows[name] or {}
            for intent in spec.get("intents") or []:
                if intent in self.flow_of:
                    raise PolicyError(f"intent {intent!r} is listed under two flows")
                self.flow_of[intent] = name
            written = set(spec.get("permitted") or [])
            # A label counts as permitted when the table lists it, or lists its written name.
            self.permitted[name] = frozenset(
                a for a in known if a in written or self.aliases.get(a) in written)
            alias_targets = set(self.aliases.values())
            self.unknown_names[name] = sorted(written - known - alias_targets)
        self.unmapped_intents = sorted(set(known_intents) - set(self.flow_of))
        for a in self.high_consequence:
            if a not in known:
                raise PolicyError(f"high_consequence action {a!r} is not a known action")

    @classmethod
    def load(cls, path: str | Path, known_intents: list[str], known_actions: list[str]) -> "Policy":
        try:
            data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise PolicyError(f"policy file is not valid YAML: {exc}")
        return cls(data, known_intents, known_actions)

    # ------------------------------------------------------------------ the gate

    def bind(self, intents: list[str], flows: list[str], actions: list[str]) -> None:
        """Precompute index tables for the classifier's class order."""
        self._intents, self._flows, self._actions = intents, flows, actions
        self._flow_idx = {f: i for i, f in enumerate(flows)}
        self._intent_flow = np.array(
            [self._flow_idx.get(self.flow_of.get(i, ""), -1) for i in intents])
        self._mask = {f: np.array([a in self.permitted.get(f, ()) for a in actions])
                      for f in flows}
        self._hc = np.array([a in self.high_consequence for a in actions])

    def decide(self, p_intent: np.ndarray, p_flow: np.ndarray, p_action: np.ndarray,
               has_system_turn: bool, top_flows: int = 3, mode: str | None = None) -> Decision:
        mode = mode or self.mode
        # Flow evidence from two models: the flow classifier, and the intent classifier summed
        # over each flow's intents.
        from_intent = np.zeros(len(self._flows))
        ok = self._intent_flow >= 0
        np.add.at(from_intent, self._intent_flow[ok], p_intent[ok])
        flow_score = np.sqrt(p_flow * from_intent + 1e-12)
        flow_score /= flow_score.sum()

        # Pick flow and action together, so a near-tie between flows is settled by which flow
        # actually permits the action the dialogue points to.
        best = None
        for fi in np.argsort(-flow_score)[:top_flows]:
            flow = self._flows[fi]
            if flow not in self.permitted:
                continue
            allowed = self._mask[flow]
            if has_system_turn or not self.require_system_turn:
                usable = allowed
            else:
                usable = allowed & ~self._hc
            if usable.any():
                ai = int(np.argmax(np.where(usable, p_action, -1.0)))
                joint = flow_score[fi] * p_action[ai]
            else:
                ai, joint = -1, flow_score[fi] * 1e-6
            if best is None or joint > best[0]:
                best = (joint, fi, ai, allowed)

        raw_ai = int(np.argmax(p_action))
        raw_action = self._actions[raw_ai]
        if best is None:
            ii = int(np.argmax(p_intent))
            return Decision(self._intents[ii], "unknown", NONE_ACTION, 0.0, 0.0,
                            float(p_intent[ii]), conflict=raw_action,
                            notes=["no flow in the policy table matches"])
        _, fi, ai, allowed = best
        flow = self._flows[fi]
        in_flow = self._intent_flow == fi
        if in_flow.any():
            ii = int(np.argmax(np.where(in_flow, p_intent, -1.0)))
        else:
            ii = int(np.argmax(p_intent))
        d = Decision(self._intents[ii], flow, NONE_ACTION, 0.0, float(flow_score[fi]),
                     float(p_intent[ii]))
        if ai >= 0:
            d.action, d.p_action = self._actions[ai], float(p_action[ai])
        else:
            d.notes.append("nothing is permitted for this flow")
        if not allowed[raw_ai]:
            d.conflict = raw_action
            if mode == "follow_label":
                d.action, d.p_action = raw_action, float(p_action[raw_ai])
        elif ai != raw_ai and self._hc[raw_ai]:
            d.blocked = raw_action
        return d


def describe(policy: Policy) -> dict:
    """A summary for the policy-check command."""
    return {
        "version": policy.version,
        "on_conflict": policy.mode,
        "flows": {f: sorted(policy.permitted[f]) for f in policy.flow_names},
        "written_names_that_are_not_labels": {f: v for f, v in policy.unknown_names.items() if v},
        "intents_without_a_flow": policy.unmapped_intents,
        "high_consequence": sorted(policy.high_consequence),
    }
