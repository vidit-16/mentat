"""Estimate the chance that the returned action is right.

This is a separate small model, fitted on out-of-fold predictions of the whole pipeline
(classifiers and policy gate). Its inputs are scores and flags, never text.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

FEATURES = (
    "p_action", "p_margin", "score_margin", "p_flow", "p_intent", "entropy",
    "conflict", "blocked", "unseen_words", "n_turns", "has_system_turn",
    "truncated", "empty_last_customer", "odd_characters", "action_prior", "log_tokens",
)


def signals(decision, p_action: np.ndarray, action_scores: np.ndarray, unseen: float,
            n_turns: int, n_tokens: int, has_system_turn: bool, flags: dict,
            action_prior: dict) -> np.ndarray:
    top = np.sort(p_action)[::-1]
    raw = np.sort(action_scores)[::-1]
    entropy = float(-(p_action * np.log(p_action + 1e-12)).sum())
    return np.array([
        decision.p_action,
        float(top[0] - top[1]) if len(top) > 1 else 1.0,
        float(raw[0] - raw[1]) if len(raw) > 1 else 0.0,
        decision.p_flow,
        decision.p_intent,
        entropy,
        1.0 if decision.conflict else 0.0,
        1.0 if decision.blocked else 0.0,
        unseen,
        n_turns / 8.0,
        1.0 if has_system_turn else 0.0,
        1.0 if flags.get("truncated") else 0.0,
        1.0 if flags.get("empty_last_customer") else 0.0,
        1.0 if (flags.get("had_control") or flags.get("had_format")) else 0.0,
        action_prior.get(decision.action, 0.5),
        math.log1p(n_tokens) / 5.0,
    ], dtype=np.float64)


class Confidence:
    def __init__(self, path: str | Path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if tuple(data["features"]) != FEATURES:
            raise ValueError("confidence model was fitted on a different feature list")
        self.mean = np.array(data["mean"])
        self.scale = np.array(data["scale"])
        self.coef = np.array(data["coef"])
        self.intercept = float(data["intercept"])
        self.action_prior = data["action_prior"]
        self.threshold = float(data["threshold"])
        self.caps = data.get("caps", {})

    def estimate(self, x: np.ndarray) -> float:
        z = float(((x - self.mean) / self.scale) @ self.coef + self.intercept)
        z = max(-30.0, min(30.0, z))
        return 1.0 / (1.0 + math.exp(-z))
