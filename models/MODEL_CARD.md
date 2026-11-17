# Model card

| | |
|---|---|
| What | Three linear classifiers (intent: 96 classes, flow: 10, action: 30) and a confidence model |
| Trained on | `reference/train.jsonl.gz`, sha256 `9243c4129368a7696526688990edde9ad0243f842f987ec5f1196bfdb89011be`, plus 3962 noisy copies made by `src/triage/train.py` |
| Never trained on | `dev.jsonl`, `dev_noisy.jsonl`, `hostile.jsonl`, or any held-out data |
| Training command | `scripts/reproduce.sh train` (run id train-002, about 19 minutes on a 4-core laptop) |
| Seed | 20261117 |
| Libraries | numpy 2.5.5, scikit-learn 1.9.1 (training only) |
| Features | 93,441 sparse features in blocks w, c, s, x (see `src/triage/features.py`) |
| Temperatures | action 0.33218, flow 0.35914, intent 0.22484 |
| Files | `model.npz` (weights as float16, no pickle), `vocab.json`, `meta.json`, `confidence.json` |
| Version | first 16 hex of sha256 over the four files; shown by `/healthz` and in every response |

Out-of-fold results on the training data (5 folds grouped by conversation):
intent 0.7097, action after the policy gate 0.8211,
top-70% error ratio 0.3066, routing threshold 0.5652 which automates
84.7% of messages at 90% accuracy.

`confidence.json` also holds the confidence caps applied after the model (policy conflict,
injection pattern, odd characters, little context). The `little_context` cap was added after
training (EXPERIMENT_LOG.md, 2026-11-17, hostile-002); retraining writes it by default.

Known limits: sees only the last 8 turns; trained on one synthetic retailer's procedures;
weak on the next step at procedure branch points. See ANALYSIS.md.
