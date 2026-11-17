"""Turn a cleaned context into sparse numeric features. The same code runs in training and
in the service, so there is no train/serve skew.

Four feature blocks, each one an ablation in EXPERIMENT_LOG.md:
  w  word 1-2 grams over all turns
  c  character 2-5 grams inside word boundaries (typos, code-mixed text)
  s  words tagged with who said them and how far from the end of the window
  x  procedure state read from `action` turns, plus the shape of the dialogue
"""
from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np

from .events import parse_event
from .sanitise import Turn

BLOCKS = ("w", "c", "s", "x")
_TOKEN = re.compile(r"<\w+>|\w+(?:'\w+)?")
_SPK = {"customer": "c", "agent": "a", "action": "x"}


def words(text: str) -> list[str]:
    return _TOKEN.findall(text)


def extract(turns: list[Turn], turn_index: int | None,
            blocks: tuple[str, ...] = BLOCKS) -> dict[str, Counter]:
    """Raw feature counts per block for one context."""
    out = {b: Counter() for b in blocks}
    n = len(turns)
    events: list[str] = []
    since_action = None
    for i, turn in enumerate(turns):
        toks = words(turn.text)
        dist = n - i                                   # 1 for the last turn
        spk = _SPK[turn.speaker]
        if "w" in out:
            out["w"].update(toks)
            out["w"].update(f"{a} {b}" for a, b in zip(toks, toks[1:]))
        if "c" in out and turn.speaker != "action":
            grams = out["c"]
            for tok in toks:
                padded = f" {tok} "
                for size in (2, 3, 4, 5):
                    for j in range(len(padded) - size + 1):
                        grams[padded[j:j + size]] += 1
        if "s" in out:
            pos = min(dist, 3)
            out["s"].update(f"{spk}{pos}:{t}" for t in toks)
            out["s"].update(f"{spk}:{t}" for t in toks)
        if turn.speaker == "action":
            name, values, _ = parse_event(turn.text)
            events.append(name)
            since_action = dist
            if "x" in out:
                out["x"][f"E:{name}"] += 1
                for v in values:
                    out["x"][f"V:{name}:{v}"] += 1
    if "x" in out:
        x = out["x"]
        for a, b in zip(events, events[1:]):
            x[f"E2:{a}>{b}"] += 1
        x[f"LAST:{events[-1] if events else 'none'}"] += 1
        x[f"NEV:{min(len(events), 4)}"] += 1
        x[f"N:{n}"] += 1
        speakers = [_SPK[t.speaker] for t in turns]
        x[f"LS:{''.join(speakers[-1:]) or '-'}"] += 1
        x[f"LS2:{''.join(speakers[-2:]) or '-'}"] += 1
        x[f"LS3:{''.join(speakers[-3:]) or '-'}"] += 1
        x[f"SINCE:{min(since_action, 6) if since_action else 'none'}"] += 1
        if turn_index is None:
            x["TI:na"] += 1
        else:
            x[f"TI:{min(turn_index // 3, 9)}"] += 1
            x[f"TIC:{'early' if turn_index <= 6 else 'mid' if turn_index <= 14 else 'late'}"] += 1
    return out


class Vectoriser:
    """TF-IDF per block, each block scaled to unit length, then joined."""

    def __init__(self, vocab: dict[str, dict[str, int]], idf: dict[str, np.ndarray],
                 weights: dict[str, float]):
        self.vocab = vocab
        self.idf = idf
        self.weights = weights
        self.blocks = tuple(b for b in BLOCKS if b in vocab)
        self.offsets, start = {}, 0
        for b in self.blocks:
            self.offsets[b] = start
            start += len(vocab[b])
        self.n_features = start

    @classmethod
    def fit(cls, rows: list[dict[str, Counter]], min_df: dict[str, int],
            max_features: dict[str, int], weights: dict[str, float]) -> "Vectoriser":
        vocab, idf = {}, {}
        n = len(rows)
        for b in BLOCKS:
            if b not in rows[0]:
                continue
            df = Counter()
            for row in rows:
                df.update(row[b].keys())
            keep = [(f, c) for f, c in df.items() if c >= min_df.get(b, 1)]
            keep.sort(key=lambda fc: (-fc[1], fc[0]))          # deterministic order
            keep = keep[:max_features.get(b, len(keep))]
            vocab[b] = {f: i for i, (f, _) in enumerate(keep)}
            idf[b] = np.array([math.log((1 + n) / (1 + c)) + 1.0 for _, c in keep],
                              dtype=np.float32)
        return cls(vocab, idf, weights)

    def transform(self, feats: dict[str, Counter]) -> tuple[np.ndarray, np.ndarray, float]:
        """Return (column indices, values, share of words not seen in training)."""
        idx_parts, val_parts = [], []
        seen = total = 0
        for b in self.blocks:
            vocab, idf = self.vocab[b], self.idf[b]
            idx, val = [], []
            for feat, count in feats[b].items():
                col = vocab.get(feat)
                if b == "w" and " " not in feat:
                    total += count
                    seen += count if col is not None else 0
                if col is not None:
                    idx.append(col)
                    val.append((1.0 + math.log(count)) * idf[col])
            if not idx:
                continue
            v = np.asarray(val, dtype=np.float32)
            norm = float(np.sqrt((v * v).sum()))
            if norm > 0:
                v *= self.weights.get(b, 1.0) / norm
            idx_parts.append(np.asarray(idx, dtype=np.int64) + self.offsets[b])
            val_parts.append(v)
        if not idx_parts:
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float32), 1.0
        unseen = 1.0 - (seen / total) if total else 1.0
        return np.concatenate(idx_parts), np.concatenate(val_parts), unseen
