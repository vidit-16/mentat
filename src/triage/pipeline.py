"""One request in, one response out. Pure function of the request, the model files and the
policy file. Nothing is remembered between requests."""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from . import respond
from .confidence import Confidence, signals
from .envelope import check_context, turn_index
from .features import extract
from .model import Model
from .policy import Policy
from .sanitise import clean_context

log = logging.getLogger("triage")
ROOT = Path(__file__).resolve().parent.parent.parent

# When two intents from different flows both score this high, a person should look.
SECOND_INTENT_MIN = 0.20
SECOND_INTENT_RATIO = 0.50


class Triage:
    def __init__(self, model_dir: str | Path | None = None, policy_path: str | Path | None = None):
        model_dir = Path(model_dir or os.environ.get("TRIAGE_MODEL_DIR") or ROOT / "models")
        policy_path = Path(policy_path or os.environ.get("TRIAGE_POLICY")
                           or ROOT / "policy" / "policy.yaml")
        self.model = Model(model_dir)
        self.conf = Confidence(model_dir / "confidence.json")
        self.intents = frozenset(self.model.classes["intent"])
        self.actions = frozenset(self.model.classes["action"])
        self.policy = Policy.load(policy_path, self.model.classes["intent"],
                                  self.model.classes["action"])
        self.policy.bind(self.model.classes["intent"], self.model.classes["flow"],
                         self.model.classes["action"])
        self.versions = {"model": self.model.version, "policy": self.policy.version}

    def handle(self, obj: dict) -> dict:
        """Never raises. Any internal failure becomes the abstention shape."""
        started = time.perf_counter()
        rid = obj["id"]
        try:
            out = self._handle(rid, obj)
        except Exception:                                   # noqa: BLE001
            log.exception("internal error on request %r", rid[:64])
            out = respond.abstain(rid, "internal error", code="internal_error")
        if not respond.schema_valid(out):
            log.error("built an invalid response for request %r", rid[:64])
            out = respond.abstain(rid, "internal error", code="internal_error")
        out["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        out["cost_usd"] = 0.0
        out["versions"] = self.versions
        return out

    def _handle(self, rid: str, obj: dict) -> dict:
        context, problem, was_cut = check_context(obj)
        if problem:
            return respond.abstain(rid, problem)
        cleaned = clean_context(context)
        flags = dict(cleaned.flags)
        if was_cut:
            flags["too_many_turns"] = True
        active = sorted(k for k, v in flags.items() if v)
        if not cleaned.usable:
            return respond.abstain(rid, "no readable text in the conversation", flags=active)

        turns = cleaned.turns
        has_system_turn = any(t.speaker == "action" and t.text for t in turns)
        feats = extract(turns, turn_index(obj), self.model.vectoriser.blocks)
        idx, val, unseen = self.model.vectoriser.transform(feats)
        scores = self.model.scores(idx, val)
        probs = self.model.probabilities(scores)
        d = self.policy.decide(probs["intent"], probs["flow"], probs["action"], has_system_turn)

        n_tokens = sum(len(t.tokens) for t in turns)
        x = signals(d, probs["action"], scores["action"], unseen, len(turns), n_tokens,
                    has_system_turn, flags, self.conf.action_prior)
        confidence = self.conf.estimate(x)

        reasons = []
        if d.action == respond.NONE_ACTION:
            confidence = 0.0
            reasons.append("nothing_permitted")
        if d.conflict:
            confidence = min(confidence, self.conf.caps.get("conflict", 1.0))
            reasons.append("policy_conflict")
        if d.blocked:
            reasons.append("needs_prior_step")
        if flags.get("injection_pattern"):
            confidence = min(confidence, self.conf.caps.get("injection", 0.2))
            reasons.append("injection_pattern")
        if not any(t.speaker == "agent" and t.text for t in turns):
            # 62 of 20,000 training rows have no agent turn. Too few to trust a confidence
            # computed for them, so a person looks. Found by the hostile pack (hostile-004).
            confidence = min(confidence, self.conf.caps.get("little_context", 0.5))
            reasons.append("little_context")
        if flags.get("had_control"):
            confidence = min(confidence, self.conf.caps.get("odd_characters", 0.5))
            reasons.append("odd_characters")
        second = self._second_intent(probs["intent"], d)
        if second:
            reasons.append("two_intents")
        if confidence < self.conf.threshold:
            reasons.append("low_confidence")

        extra = {"flow": d.flow, "flags": active, "human_reasons": reasons}
        if d.conflict:
            extra["policy_conflict"] = {"suppressed_action": d.conflict}
        if d.blocked:
            extra["held_back"] = {"action": d.blocked, "reason": "no system step in view"}
        if second:
            extra["secondary_intent"] = second
        return respond.build(rid, d.intent, d.action, float(confidence), bool(reasons),
                             self.intents, self.actions, **extra)

    def _second_intent(self, p_intent, d) -> str | None:
        """Best intent from a different flow, when it is strong enough to matter."""
        order = p_intent.argsort()[::-1]
        top = float(p_intent[order[0]])
        names = self.model.classes["intent"]
        for i in order[1:4]:
            other = names[i]
            if self.policy.flow_of.get(other) != d.flow:
                p = float(p_intent[i])
                if p >= SECOND_INTENT_MIN and p >= SECOND_INTENT_RATIO * top:
                    return other
                return None
        return None
