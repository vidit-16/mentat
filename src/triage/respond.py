"""Build responses. Every decision field comes from a closed list or a computed number.
No part of the request text is ever copied into intent, action, confidence or needs_human."""
from __future__ import annotations

import math

NONE_ACTION = "none"
UNKNOWN_INTENT = "unknown"


def abstain(rid: str, message: str, code: str = "invalid_input", **extra) -> dict:
    """The defined abstention shape from the service contract."""
    out = {"id": rid, "intent": UNKNOWN_INTENT, "action": NONE_ACTION, "confidence": 0.0,
           "needs_human": True, "error": {"code": code, "message": message}}
    out.update(extra)
    return out


def build(rid: str, intent: str, action: str, confidence: float, needs_human: bool,
          intents: frozenset, actions: frozenset, **extra) -> dict:
    if intent not in intents or (action != NONE_ACTION and action not in actions):
        raise ValueError("decision outside the closed lists")
    if not isinstance(confidence, float) or not math.isfinite(confidence):
        raise ValueError("confidence is not a finite number")
    out = {"id": rid, "intent": intent, "action": action,
           "confidence": round(min(1.0, max(0.0, confidence)), 6),
           "needs_human": bool(needs_human)}
    out.update(extra)
    return out


def schema_valid(resp) -> bool:
    """Same structural checks as the official grader, used as a last self-check."""
    if not isinstance(resp, dict):
        return False
    if not all(k in resp for k in ("id", "intent", "action", "confidence", "needs_human")):
        return False
    if not all(isinstance(resp[k], str) for k in ("id", "intent", "action")):
        return False
    conf = resp["confidence"]
    if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not math.isfinite(conf):
        return False
    if not 0.0 <= conf <= 1.0:
        return False
    return isinstance(resp["needs_human"], bool)
