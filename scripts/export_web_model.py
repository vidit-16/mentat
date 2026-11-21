#!/usr/bin/env python3
"""Export the shipped model and policy in a form the browser engine (web/engine/) can load.

    python scripts/export_web_model.py [--out web/model]

Nothing is retrained or rounded further. The weights are the same float16 values stored in
models/model.npz, rearranged so the 136 class weights of one feature sit next to each other
(intent 96, flow 10, action 30), then gzipped. The browser decompresses them with the
built-in DecompressionStream.

Files:
  weights.f16.gz   uint16 (IEEE float16 bits), shape [n_features, 136], little endian, gzip
  vocab.json.gz    {block: {feature: column within block}}, gzip
  model.json       classes, temperatures, block order and weights, biases, idf per block
  confidence.json  the confidence model, unchanged
  policy.json      the policy table resolved to label lists (no YAML parser in the browser)
  manifest.json    model version, policy version, sha256 of every file above
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from triage.model import HEADS, Model  # noqa: E402
from triage.policy import Policy  # noqa: E402


def write_gz(path: Path, data: bytes) -> None:
    """gzip with a fixed timestamp, so the same input gives the same bytes."""
    path.write_bytes(gzip.compress(data, compresslevel=9, mtime=0))


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n",
                    encoding="utf-8", newline="\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "web" / "model"))
    ap.add_argument("--model-dir", default=str(ROOT / "models"))
    ap.add_argument("--policy", default=str(ROOT / "policy" / "policy.yaml"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    src = Path(args.model_dir)

    model = Model(src)
    raw = np.load(src / "model.npz", allow_pickle=False)
    # Same float16 values as the npz, one row per feature: [intent | flow | action].
    rows = np.concatenate([raw[f"W_{h}"] for h in HEADS], axis=1).astype("<f2")
    assert rows.dtype == np.float16
    write_gz(out / "weights.f16.gz", rows.view("<u2").tobytes())

    vocab = json.loads((src / "vocab.json").read_text(encoding="utf-8"))
    write_gz(out / "vocab.json.gz",
             json.dumps(vocab, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    meta = model.meta
    write_json(out / "model.json", {
        "version": model.version,
        "heads": list(HEADS),
        "classes": model.classes,
        "temperature": model.temperature,
        "blocks": list(model.vectoriser.blocks),
        "block_weights": meta["block_weights"],
        "n_features": model.vectoriser.n_features,
        "row_width": int(rows.shape[1]),
        "bias": {h: [float(v) for v in raw[f"b_{h}"].astype(np.float32)] for h in HEADS},
        "idf": {b: [float(v) for v in raw[f"idf_{b}"].astype(np.float32)]
                for b in model.vectoriser.blocks},
    })
    shutil.copyfile(src / "confidence.json", out / "confidence.json")

    policy = Policy.load(args.policy, model.classes["intent"], model.classes["action"])
    write_json(out / "policy.json", {
        "version": policy.version,
        "on_conflict": policy.mode,
        "require_system_turn": policy.require_system_turn,
        "high_consequence": sorted(policy.high_consequence),
        "flow_of": policy.flow_of,
        "permitted": {f: sorted(policy.permitted[f]) for f in policy.flow_names},
    })

    files = ["weights.f16.gz", "vocab.json.gz", "model.json", "confidence.json", "policy.json"]
    write_json(out / "manifest.json", {
        "model_version": model.version,
        "policy_version": policy.version,
        "sha256": {f: hashlib.sha256((out / f).read_bytes()).hexdigest() for f in files},
        "bytes": {f: (out / f).stat().st_size for f in files},
    })
    print(json.dumps({"model_version": model.version, "rows": list(rows.shape),
                      "bytes": {f: (out / f).stat().st_size for f in files}}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
