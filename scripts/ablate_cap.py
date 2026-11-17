#!/usr/bin/env python3
"""Ablation: train and score words-only, no augmentation, with the per-turn length cap
switched off. Compare with ablate-001-w, which is the same configuration with the cap on.

    python scripts/ablate_cap.py --model-dir <scratch dir> --out results/raw/ablate-002-w-nocap
"""
import argparse
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import triage.sanitise as sanitise  # noqa: E402

sanitise.MAX_TURN_TOKENS = 10 ** 9      # no word cap; the 20,000-character cap stays

ap = argparse.ArgumentParser()
ap.add_argument("--model-dir", required=True)
ap.add_argument("--out", required=True)
args = ap.parse_args()

from triage import train  # noqa: E402
train.main(["--fast", "--no-augment", "--blocks", "w", "--out", args.model_dir])
sys.argv = ["evaluate.py", "--model-dir", args.model_dir, "--mode", "follow_label", "--out", args.out]
runpy.run_path(str(ROOT / "scripts" / "evaluate.py"), run_name="__main__")
