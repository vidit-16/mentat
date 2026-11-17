"""Train the classifiers and the confidence estimator, and export plain arrays.

    python -m triage.train --out models [--blocks wcsx] [--no-augment] [--fast]

Deterministic for a given platform and library version: fixed seed, sorted vocabularies,
grouped folds built from sorted conversation ids. scikit-learn is used here only; the service
never imports it.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
import time
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix

from .confidence import FEATURES, signals
from .features import BLOCKS, Vectoriser, extract
from .model import HEADS, softmax
from .policy import Policy
from .sanitise import clean_context

ROOT = Path(__file__).resolve().parent.parent.parent
SEED = 20261117
C_SVM = 0.5
N_FOLDS = 5
AUGMENT_SHARE = 0.20
DROP_TURN_INDEX_SHARE = 0.15
MIN_DF = {"w": 2, "c": 5, "s": 2, "x": 1}
MAX_FEATURES = {"c": 40_000}
BLOCK_WEIGHTS = {"w": 1.0, "c": 1.0, "s": 1.0, "x": 1.0}
TARGET_AUTOMATED_ACCURACY = 0.90


def load_jsonl(path) -> list[dict]:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def stable_unit(key: str) -> float:
    """A repeatable number in [0, 1) for a string, independent of Python's hash seed."""
    return int(hashlib.sha256(key.encode()).hexdigest()[:12], 16) / 16 ** 12


# ----------------------------------------------------------------------------- augmentation

def _typo(text: str, rng: random.Random) -> str:
    out = []
    for tok in text.split(" "):
        if len(tok) > 2 and not tok.startswith("<") and rng.random() < 0.3:
            i = rng.randrange(len(tok) - 1)
            kind = rng.randrange(3)
            if kind == 0:
                tok = tok[:i] + tok[i + 1] + tok[i] + tok[i + 2:]
            elif kind == 1:
                tok = tok[:i] + tok[i + 1:]
            else:
                tok = tok[:i] + tok[i] + tok[i:]
        out.append(tok)
    return " ".join(out)


def augment(row: dict, rng: random.Random, pool_any: list[str], pool_first: list[str]) -> dict | None:
    """One noisy copy of a training row. Only the last customer turn is changed, the label
    is kept. Rules are generic; none was fitted to the published noisy rows."""
    context = [dict(t) for t in row["context"]]
    last = max((i for i, t in enumerate(context) if t["speaker"] == "customer"), default=None)
    if last is None:
        return None
    kind = rng.choice(["typo", "typo", "empty", "long", "long", "second_request"])
    text = context[last]["text"]
    if kind == "typo":
        text = _typo(text, rng)
    elif kind == "empty":
        text = ""
    elif kind == "long":
        filler = [rng.choice(pool_any) for _ in range(rng.randrange(15, 80))]
        filler.insert(rng.randrange(len(filler) + 1), text)
        text = " ".join(filler)
    else:
        text = f"{text} also {rng.choice(pool_first)}"
    context[last]["text"] = text
    return {**row, "id": row["id"] + "-aug", "context": context, "_aug": kind}


def with_augmentation(rows: list[dict]) -> list[dict]:
    rng = random.Random(SEED)
    pool_any = [t["text"] for r in rows for t in r["context"] if t["speaker"] == "customer" and t["text"]]
    pool_first = [next(t["text"] for t in r["context"] if t["speaker"] == "customer")
                  for r in rows if len(r["context"]) < 8
                  and any(t["speaker"] == "customer" for t in r["context"])]
    out = list(rows)
    for row in rows:
        if stable_unit("aug:" + row["id"]) < AUGMENT_SHARE:
            copy = augment(row, rng, pool_any, pool_first)
            if copy:
                out.append(copy)
    return out


# ----------------------------------------------------------------------------- features

def prepare(rows: list[dict], blocks: tuple[str, ...], drop_turn_index: bool):
    cleaned, feats = [], []
    for row in rows:
        c = clean_context(row["context"])
        ti = row.get("turn_index")
        if drop_turn_index and stable_unit("ti:" + row["id"]) < DROP_TURN_INDEX_SHARE:
            ti = None
        cleaned.append(c)
        feats.append(extract(c.turns, ti, blocks))
    return cleaned, feats


def to_matrix(vec: Vectoriser, feats: list[dict]):
    indptr, indices, data, unseen = [0], [], [], []
    for f in feats:
        idx, val, u = vec.transform(f)
        order = np.argsort(idx)
        indices.append(idx[order])
        data.append(val[order])
        indptr.append(indptr[-1] + len(idx))
        unseen.append(u)
    X = csr_matrix((np.concatenate(data), np.concatenate(indices), indptr),
                   shape=(len(feats), vec.n_features), dtype=np.float32)
    return X, np.array(unseen)


def fit_head(X, y, classes):
    from sklearn.svm import LinearSVC
    clf = LinearSVC(C=C_SVM, random_state=SEED)
    clf.fit(X, y)
    order = [list(clf.classes_).index(c) for c in classes]
    return clf.coef_[order].T.astype(np.float32), clf.intercept_[order].astype(np.float32)


def _fold_job(X, y, classes, train_idx, test_idx):
    W, b = fit_head(X[train_idx], [y[i] for i in train_idx], classes)
    return test_idx, np.asarray(X[test_idx] @ W) + b


def fit_temperature(scores: np.ndarray, y_idx: np.ndarray) -> float:
    best, best_t = None, 1.0
    for t in np.geomspace(0.02, 2.0, 60):
        z = scores / t
        z = z - z.max(axis=1, keepdims=True)
        logp = z - np.log(np.exp(z).sum(axis=1, keepdims=True))
        nll = -logp[np.arange(len(y_idx)), y_idx].mean()
        if best is None or nll < best:
            best, best_t = nll, float(t)
    return round(best_t, 5)


# ----------------------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", default=str(ROOT / "reference" / "train.jsonl.gz"))
    ap.add_argument("--policy", default=str(ROOT / "policy" / "policy.yaml"))
    ap.add_argument("--out", default=str(ROOT / "models"))
    ap.add_argument("--blocks", default="wcsx")
    ap.add_argument("--no-augment", action="store_true")
    ap.add_argument("--fast", action="store_true",
                    help="skip the folds; confidence falls back to the action probability")
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args(argv)
    t0 = time.time()
    blocks = tuple(b for b in BLOCKS if b in args.blocks)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    base = load_jsonl(args.train)
    rows = base if args.no_augment else with_augmentation(base)
    cleaned, feats = prepare(rows, blocks, drop_turn_index=not args.no_augment)
    vec = Vectoriser.fit(feats, MIN_DF, MAX_FEATURES, BLOCK_WEIGHTS)
    X, unseen = to_matrix(vec, feats)
    print(f"rows {len(rows)} (base {len(base)}) features {vec.n_features} [{time.time() - t0:.0f}s]")

    labels = {"intent": [r["intent"] for r in rows], "flow": [r["flow"] for r in rows],
              "action": [r["action"] for r in rows]}
    classes = {h: sorted(set(labels[h])) for h in HEADS}

    weights, bias = {}, {}
    for h in HEADS:
        weights[h], bias[h] = fit_head(X, labels[h], classes[h])
        print(f"fitted {h} ({len(classes[h])} classes) [{time.time() - t0:.0f}s]")

    temperature = {h: 0.2 for h in HEADS}
    conf = {"features": list(FEATURES), "mean": [0.0] * len(FEATURES), "scale": [1.0] * len(FEATURES),
            "coef": [4.0] + [0.0] * (len(FEATURES) - 1), "intercept": -2.0, "action_prior": {},
            "threshold": 0.5, "caps": {"conflict": 0.35, "injection": 0.2, "odd_characters": 0.5,
                     "little_context": 0.5},
            "fitted": False}
    oof_report = {}

    if not args.fast:
        from joblib import Parallel, delayed
        from sklearn.linear_model import LogisticRegression

        # Folds are grouped by conversation: rows of one dialogue never sit on both sides.
        conv = [r["id"].split("-")[0] for r in rows]
        fold_of = {c: i % N_FOLDS for i, c in enumerate(sorted(set(conv)))}
        fold = np.array([fold_of[c] for c in conv])
        jobs = []
        for h in HEADS:
            for k in range(N_FOLDS):
                jobs.append((h, np.where(fold != k)[0], np.where(fold == k)[0]))
        # Threads, not processes: liblinear crashed (access violation) on Windows when loky
        # handed workers a memory-mapped copy of the matrix. Threads share the matrix.
        results = Parallel(n_jobs=args.jobs, backend="threading")(
            delayed(_fold_job)(X, labels[h], classes[h], tr, te) for h, tr, te in jobs)
        oof = {h: np.zeros((len(rows), len(classes[h])), dtype=np.float32) for h in HEADS}
        for (h, _, _), (te, scores) in zip(jobs, results):
            oof[h][te] = scores
        print(f"out-of-fold scores done [{time.time() - t0:.0f}s]")

        for h in HEADS:
            y_idx = np.array([classes[h].index(v) for v in labels[h]])
            temperature[h] = fit_temperature(oof[h].astype(np.float64), y_idx)
            oof_report[f"{h}_accuracy_raw"] = round(float((oof[h].argmax(1) == y_idx).mean()), 4)

        policy = Policy.load(args.policy, classes["intent"], classes["action"])
        policy.bind(classes["intent"], classes["flow"], classes["action"])
        decisions, correct, sig_inputs = [], [], []
        for i, row in enumerate(rows):
            p = {h: softmax(oof[h][i].astype(np.float64), temperature[h]) for h in HEADS}
            turns = cleaned[i].turns
            has_sys = any(t.speaker == "action" and t.text for t in turns)
            d = policy.decide(p["intent"], p["flow"], p["action"], has_sys)
            decisions.append(d)
            correct.append(d.action == row["action"])
            sig_inputs.append((d, p["action"], oof["action"][i], unseen[i],
                               len(turns), sum(len(t.tokens) for t in turns), has_sys,
                               cleaned[i].flags))
        correct = np.array(correct)

        # How often each returned action is right, shrunk towards the overall rate.
        overall = float(correct.mean())
        prior = {}
        for a in classes["action"]:
            hit = np.array([d.action == a for d in decisions])
            prior[a] = round(float((correct[hit].sum() + 20 * overall) / (hit.sum() + 20)), 4)
        S = np.array([signals(*s, prior) for s in sig_inputs])
        mean, scale = S.mean(axis=0), S.std(axis=0)
        scale[scale < 1e-6] = 1.0
        lr = LogisticRegression(C=1.0, max_iter=2000)
        # The confidence model is itself checked out of fold, so the numbers below are honest.
        est = np.zeros(len(rows))
        for k in range(N_FOLDS):
            lr.fit((S[fold != k] - mean) / scale, correct[fold != k])
            est[fold == k] = lr.predict_proba((S[fold == k] - mean) / scale)[:, 1]
        lr.fit((S - mean) / scale, correct)

        order = np.argsort(-est)
        hits = np.cumsum(correct[order]) / np.arange(1, len(order) + 1)
        ok = np.where(hits >= TARGET_AUTOMATED_ACCURACY)[0]
        cut = int(ok.max()) if len(ok) else 0
        threshold = float(est[order][cut])
        top70 = order[: int(round(0.7 * len(order)))]
        oof_report.update({
            "rows": len(rows),
            "intent_accuracy_gated": round(float(np.mean([d.intent == r["intent"] for d, r in zip(decisions, rows)])), 4),
            "action_accuracy_gated": round(overall, 4),
            "conflict_rate": round(float(np.mean([bool(d.conflict) for d in decisions])), 4),
            "held_back_rate": round(float(np.mean([bool(d.blocked) for d in decisions])), 4),
            "top70_error_ratio": round(float((1 - correct[top70].mean()) / (1 - overall)), 4),
            "threshold": round(threshold, 4),
            "automated_share_at_threshold": round(float((cut + 1) / len(order)), 4),
            "automated_accuracy_at_threshold": round(float(hits[cut]), 4),
        })
        conf.update({"mean": mean.round(6).tolist(), "scale": scale.round(6).tolist(),
                     "coef": lr.coef_[0].round(6).tolist(), "intercept": round(float(lr.intercept_[0]), 6),
                     "action_prior": prior, "threshold": round(threshold, 4), "fitted": True})

    arrays = {}
    for h in HEADS:
        arrays[f"W_{h}"] = weights[h].astype(np.float16)
        arrays[f"b_{h}"] = bias[h].astype(np.float32)
    for b in vec.blocks:
        arrays[f"idf_{b}"] = vec.idf[b]
    np.savez_compressed(out / "model.npz", **arrays)
    (out / "vocab.json").write_text(json.dumps(vec.vocab, ensure_ascii=True, sort_keys=True),
                                    encoding="utf-8")
    import sklearn
    meta = {"classes": classes, "temperature": temperature, "block_weights": BLOCK_WEIGHTS,
            "blocks": list(vec.blocks), "seed": SEED, "c_svm": C_SVM,
            "augmented": not args.no_augment, "train_rows": len(rows),
            "n_features": vec.n_features,
            "libraries": {"numpy": np.__version__, "scikit-learn": sklearn.__version__},
            "train_sha256": hashlib.sha256(Path(args.train).read_bytes()).hexdigest()}
    (out / "meta.json").write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (out / "confidence.json").write_text(json.dumps(conf, indent=1) + "\n", encoding="utf-8")
    (out / "oof_report.json").write_text(json.dumps(oof_report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(oof_report, indent=1))
    print(f"wrote {out} [{time.time() - t0:.0f}s]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
