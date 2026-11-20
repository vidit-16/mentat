# OP-06 Triage the Inbox

A `POST /triage` service for the Deployment.inc Season 1 problem OP-06. It reads a support
conversation so far (up to eight turns) and returns the customer's problem type (ABCD
subflow), the next step the written procedure permits, a confidence, and whether a person
should look first.

No GPU, no API key, no outbound calls. Trained linear classifiers on CPU, a rule table the
support manager edits, and a separate confidence model.

## Results on the published development data

Measured by the unmodified official `grader.py` on 2,000 clean + 300 noisy + 9 hostile rows,
through the HTTP service, by `scripts/reproduce.sh all` on a clean GitHub Actions Ubuntu VM
[run `ci-44775973227`]. The laptop gives the same labels and metrics [run `dev-006`]; a few confidences differ in the sixth decimal between CPUs. These are development numbers; the hidden
test split is scored by the reviewers.

| | Shipped | Bar | Published baseline |
|---|---|---|---|
| Intent accuracy | 0.7204 | ≥ 0.55 | 0.3748 |
| Intent macro-F1 | 0.6895 | ≥ 0.50 | 0.4508 |
| Action accuracy | 0.8217 | ≥ 0.55 | 0.3913 |
| Clean-to-noisy action gap | 0.0327 | ≤ 0.10 | 0.0743 |
| Schema valid, incl. hostile | 100% | 100% | 100% |
| Top-70% error ratio | 0.2821 | ≤ 0.85 | 1.0 |
| Policy violation rate | 0.0778 | reported (gold: 0.0883) | 0.1404 |
| Sent to a person | 16.5% | — | — |
| Action accuracy when not sent to a person | 0.9084 | — | — |
| Hostile pack (99 requests: 9 published, 68 extended, 22 transport) | 99 passed | zero failures | — |
| p95 latency, concurrency 8 / 32 | 44 ms / 44 ms | reported | — |
| API cost per message | $0 | reported | $0 |

Latency is measured by the client, under load, on the clean CI machine (2 vCPU, 2 workers,
load generator on the same machine, 3,000 requests mixing every dev, noisy and hostile row):
p95 44 ms at concurrency 8 (189 requests/s) and 44 ms at concurrency 32 (750 requests/s), no
errors (`results/latency_bench.json`). On the 4-core development laptop the same test gave
p95 63 ms and 302 ms; laptop timings varied by about 40% between runs. Compute cost at the
list price of a 2-vCPU cloud VM ($0.089/hour) is about $0.0001 per thousand messages.

## How it works

```
request -> size/time limits -> JSON and shape checks -> Unicode cleaning, per-turn length cap
        -> features (words, characters, who said what and when, system steps already done)
        -> three linear classifiers: intent, flow, action
        -> policy gate (policy/policy.yaml): flow and action chosen together,
           only actions the flow permits, high-consequence actions need a system step in view
        -> confidence model (chance the returned action is right)
        -> routing rules -> response built from closed lists
```

- **Policy** is a YAML table: for each flow, its intents and permitted actions, built from the
  published procedure. When the model's first choice is not permitted, the service returns the
  best permitted action, sets `needs_human`, and names the held-back action in
  `policy_conflict`. Edit, run `scripts/reproduce.sh policy-check`, restart. See RUNBOOK.md.
- **Confidence** comes from a small model trained on out-of-fold predictions of the whole
  pipeline, not from any model's own word. Above the routing threshold (0.565) messages were
  right 90% of the time out of fold and 90.8% on dev.
- **Injection** has nothing to talk to. The decision path counts words; it cannot follow
  instructions. Trust comes from the `speaker` field, never from the text: a customer cannot
  write a system step. The action comes from the rule table, after the model. Injection-like
  text only ever raises `needs_human` and lowers confidence. Tests check these properties on
  every published row with injection text added (`tests/test_invariants.py`).

Extra response fields (allowed by the schema): `flow`, `human_reasons`, `flags`,
`policy_conflict`, `held_back`, `secondary_intent`, `versions` (model and policy), `latency_ms`,
`cost_usd`. Abstention, for a valid request with no usable text: `intent: "unknown"`,
`action: "none"`, `confidence: 0`, `needs_human: true`, plus `error`.

## Running it

On a Linux machine with Python 3.10+ and the `venv` module (Debian/Ubuntu:
`apt install python3-venv`):

```bash
scripts/reproduce.sh all
```

That is: create `.venv` with pinned dependencies, check the reference files against the
release hashes, run the 118 tests, evaluate through the HTTP service, run the hostile pack,
and load-test at concurrency 8 and 32. It uses the committed model; `scripts/reproduce.sh
train` retrains it (about 6 minutes on a 4-core laptop, 5 on the 2-vCPU CI runner). Each step is also its own subcommand; run the script
with no argument for the list. `serve` runs in the foreground; `start`/`stop` run it in the
background so the evaluation steps can reach it.

Docker: `docker build -t op06-triage . && docker run --rm -p 8000:8000 op06-triage`.

The same `reproduce.sh all` runs on a fresh Ubuntu VM in GitHub Actions on every push
(`.github/workflows/reproduce.yml`) and checks that the clean-machine accuracy matches the
committed numbers.

### Limits and timeouts

Request body 1 MB (413), body must arrive within 5 s (408), last 8 turns used, each turn cut to
20,000 characters and then 80 words (first 50, last 30), 1,000 open connections per worker.
Malformed JSON, a non-object body, duplicate keys, NaN or a missing/non-string `id` gets 400 with
`{"error": {...}}`. Every published hostile row returns 200 with a schema-valid body. Slowest
hostile request in the submitted run: 243 ms.

## Repository map

| Path | What |
|---|---|
| `src/triage/` | service: `app.py` (HTTP), `envelope.py`, `sanitise.py`, `events.py`, `features.py`, `model.py`, `policy.py`, `confidence.py`, `pipeline.py`, `respond.py`; `train.py` (training only) |
| `policy/` | the rule table and its change log |
| `models/` | trained weights (no pickle) and `MODEL_CARD.md` |
| `reference/` | unmodified challenge files and their release hashes |
| `scripts/` | `reproduce.sh`, evaluation, hostile run, load generator, taxonomy, manifest, ablations, LLM experiment |
| `tests/` | contract, hostile, invariants, policy change, fuzzing |
| `results/` | submitted predictions, hostile results, latency, `manifest.json`, `runs.yaml`, and every run in `raw/` |
| `PLAN.md` | the plan written before building |
| `ANALYSIS.md` | baseline failure taxonomy, what moved what, noisy slice by type, hostile findings |
| `DECISIONS.md` | two decisions, and every departure from the plan |
| `EXPERIMENT_LOG.md` | dated log, failures included |
| `LANDSCAPE.md` | what exists, what was used, what was rejected |
| `MEMO.md` | one page for the customer-support manager |
| `RUNBOOK.md` | operating the service and changing rules |

## Known failure modes

- Next step at procedure branch points (the deciding fact is not in the text yet): most of
  the remaining errors.
- Intent when the opening message has left the 8-turn window: error doubles (16% → 34%).
- Sibling intents with the same procedure (`return_size` / `return_color`).
- Code-mixed messages: action 0.70 on 50 rows, the one noise type that went down in the last
  change; small sample.
- Only trained on ABCD's synthetic retailer. New request types, products or procedure steps
  need retraining or rule edits.
- Development numbers are on public dev data; the reviewers' noisy slice is generated
  independently.

## Spend

API: $0.014076 for everything in `results/` (one LLM experiment, 150 calls, not used by the
service). Compute: the author's laptop. Details per run in `results/manifest.json`.

## Secrets

None in this repository. The service needs no key. `.env.example` lists the one optional
variable (`OPENAI_API_KEY`, only for rerunning `scripts/llm_experiment.py`); `.env` is ignored
by git.
