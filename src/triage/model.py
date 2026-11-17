"""Load the trained weights and score a feature vector. Plain arrays only: the service does
not import scikit-learn and does not unpickle anything."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from .features import Vectoriser

HEADS = ("intent", "flow", "action")


def softmax(scores: np.ndarray, temperature: float) -> np.ndarray:
    z = scores / temperature
    z = z - z.max()
    e = np.exp(z)
    return e / e.sum()


class Model:
    def __init__(self, directory: str | Path):
        directory = Path(directory)
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
        vocab = json.loads((directory / "vocab.json").read_text(encoding="utf-8"))
        arrays = np.load(directory / "model.npz", allow_pickle=False)
        self.meta = meta
        self.classes = {h: meta["classes"][h] for h in HEADS}
        self.temperature = {h: float(meta["temperature"][h]) for h in HEADS}
        self.weights = {h: arrays[f"W_{h}"].astype(np.float32) for h in HEADS}
        self.bias = {h: arrays[f"b_{h}"].astype(np.float32) for h in HEADS}
        idf = {b: arrays[f"idf_{b}"].astype(np.float32) for b in vocab}
        self.vectoriser = Vectoriser(vocab, idf, meta["block_weights"])
        digest = hashlib.sha256()
        for name in ("model.npz", "vocab.json", "meta.json", "confidence.json"):
            digest.update((directory / name).read_bytes())
        self.version = digest.hexdigest()[:16]
        for h in HEADS:
            if self.weights[h].shape != (self.vectoriser.n_features, len(self.classes[h])):
                raise ValueError(f"weight shape for {h} does not match vocabulary")

    def scores(self, idx: np.ndarray, val: np.ndarray) -> dict[str, np.ndarray]:
        out = {}
        for h in HEADS:
            if len(idx):
                out[h] = val @ self.weights[h][idx] + self.bias[h]
            else:
                out[h] = self.bias[h].copy()
        return out

    def probabilities(self, scores: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        return {h: softmax(scores[h].astype(np.float64), self.temperature[h]) for h in HEADS}
