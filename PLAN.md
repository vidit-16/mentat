# Mentat: plan and architecture

Status: plan only. No solution code exists yet.
Written 17 November 2026.
Source read: the benchmark's problem statement, reference files, rubric, evaluation
protocol, calibration notes, version pins and model list.

## 1. Summary

Build a stateless `POST /triage` service whose serving path is a small trained classifier on
CPU, followed by a policy gate that reads the written procedure from a data file, followed by
a separate confidence estimator. No generative model sits in the default serving path.

The reason is a measurement, not a preference. A quick probe on the published splits (linear
model over word, character and speaker-tagged features, untuned, one run) already clears every
numeric bar by a wide margin at zero API cost. That changes what the work is. The numbers are
the easy part. The submission will be judged on the policy layer, the confidence signal, the
hostile-input behaviour and the honesty of the write-up.

A budget-class LLM is kept as one bounded experiment (re-ranking intent on the low-confidence
slice). It is adopted only if it moves a named failure category enough to pay for its cost,
latency and attack surface. Either result gets reported.

## 2. What the problem asks

Input: `{id, context, turn_index?}`. `context` is up to 8 turns, each
`{speaker: customer|agent|action, text}`. `turn_index` is optional. Labels and
`permitted_actions` never reach the service.

Output: `{id, intent, action, confidence, needs_human}`. `intent` is the ABCD subflow (96
classes). `action` is the next action (30 classes) or `none`. Extra keys are tolerated.

Abstention envelope for a valid request whose text cannot be handled:
`intent: "unknown"`, `action: "none"`, `confidence: 0`, `needs_human: true`, optional
`error: {code: "invalid_input", message}`. Malformed HTTP or JSON may return 400.

### Qualification bars (hidden test split, their scorer)

| # | Bar | Target | Published baseline |
|---|---|---|---|
| 1 | Intent accuracy, clean + noisy | >= 0.55 | 0.3748 |
| 1 | Intent macro-F1 | >= 0.50 | 0.4508 |
| 2 | Action accuracy, clean + noisy | >= 0.55 | 0.3913 |
| 3 | Clean-to-noisy action gap | <= 0.10 | 0.0743 |
| 4 | Hostile pack | zero crashes, hangs, unhandled exceptions, injection-driven changes; 100% schema valid | 100% schema valid |
| 5 | Top-70% error ratio | <= 0.85 | 1.0 |
| 6 | p95 latency at stated concurrency, cost per message | measured under load and reported | laptop, free |

Details of the scorer that shape the design:

- The confidence ratio is computed on **action** correctness, not intent. Confidence must
  estimate "is the action right".
- Ties at the 70% cut are kept, so confidence needs many distinct values.
- A missing or schema-invalid prediction counts as wrong with confidence 0.
- Policy violations are reported next to the gold labels' own rate (0.0883 on dev). There is
  no bar on it, but the write-up is expected to explain the choice.
- The assessment table also mentions "permitted-nothing accuracy". The published data has no
  row with an empty permitted set, so the hidden set may. The design must be able to answer
  `none`.
- Hostile behaviour, latency and cost are measured by the reviewer on their machine through a
  metered gateway. Nothing self-reported counts.

### Seven rubric dimensions (rated 0 to 3 each)

1 Did it work. 2 Do you know why. 3 Would it survive production. 4 Right trade-offs.
5 Can a business owner act on it. 6 Honest reporting. 7 Knew what already exists.
The Starter problem puts extra weight on 3, 6 and 7. A rating of 3 needs tested alternatives
and a statement of when the decision stops being valid.

## 3. What the data says

Measured on `train.jsonl.gz` (20,000 rows), `dev.jsonl` (2,000) and `dev_noisy.jsonl` (300).

- 96 intents, 30 actions, 10 flows. Smallest intent has 3 training rows; the single-item
  query flow alone holds 32 near-duplicate intents (`shirt_how_4`, `jeans_other_3`, ...).
- 66% of rows have a full 8-turn window, and `turn_index` runs up to 41. So the opening
  customer message, which carries most of the intent signal, is often outside the window.
  In the probe, intent accuracy is 0.86 when the whole dialogue is visible and 0.66 when it
  is truncated. This is the main ceiling on intent.
- 69% of rows contain at least one `action` turn ("account has been pulled up for ...",
  "identity verification in progress ..."). These are a direct record of where the procedure
  has got to. The published baseline ignores speaker roles entirely, which is a large part of
  why it is weak on action.
- The permitted set depends only on the flow: one set per flow, 6 to 22 actions each. So
  "what is permitted" reduces to "which flow is this", then a table lookup.
- Rows come from 7,763 conversations, up to 19 rows each. Any validation split must group by
  conversation (the id prefix before the dash) or the scores leak.
- Median context is 281 characters. The longest noisy context is 6,280 characters.

### The 9% policy gap is partly a naming artefact

8.5% of training labels fall outside the permitted set. Of those 1,697 rows, 724 are the
label `membership`, and in 658 of them the flow's permitted set contains
`membership-privileges` instead. The permitted lists also carry names that never occur as a
label (`enter-detail`, `notify-internal-team`, `select-answer`, `end-conversation`, `n-a`).
So roughly 40% of the "deviation" is the same action under two names, and the remaining
~5% is real: agents pulling up an account or verifying identity in flows whose written
procedure does not list that step.

This matters for the write-up. The gap should be reported split into "alias" and "real
deviation", not as one number.

### Exploratory probe (not a submission result)

Linear SVM, word 1-2 grams + character 2-5 grams + speaker- and position-tagged tokens +
action-turn tokens. No tuning, no selection on dev, one run, laptop CPU, about 80 seconds
to fit.

| Metric | Probe | Bar |
|---|---|---|
| Intent accuracy (clean + noisy) | 0.7043 | 0.55 |
| Intent macro-F1 | 0.6717 | 0.50 |
| Action accuracy (clean + noisy) | 0.8343 | 0.55 |
| Clean-to-noisy action gap | 0.0395 | 0.10 |
| Top-70% error ratio (margin as confidence) | 0.3037 | 0.85 |
| Flow accuracy, clean / noisy | 0.8835 / 0.7867 | none |
| Policy violation rate of predictions | 0.0955 | gold 0.089 |

Noisy slice by type (50 rows each, so each figure is +/- about 0.13):

| Noise type | Intent | Action |
|---|---|---|
| typo | 0.66 | 0.78 |
| code_mixed | 0.72 | 0.84 |
| two_intents | 0.64 | 0.88 |
| empty | 0.64 | 0.80 |
| screenshot | 0.56 | 0.82 |
| very_long | 0.18 | 0.68 |

Readings:

- Action survives noise because only the last customer turn is rewritten, and action depends
  mostly on the agent and action turns.
- `very_long` breaks intent badly. A long message swamps the feature vector. This needs a
  specific fix (per-turn length cap and per-turn weighting), and it is the weakest slice.
- The largest intent confusions are siblings inside one flow: `return_size` / `return_color`
  / `return_stain`, `status_due_date` / `status_due_amount`, `promo_code_invalid` /
  `promo_code_out_of_date`. These share a flow, a procedure and a permitted set, so they cost
  intent accuracy but almost never change what the agent may do.

The probe must be rerun inside the solution repository and logged in `EXPERIMENT_LOG.md`
before any of these numbers are quoted in the submission. The hidden noisy slice is
"independently generated", so the dev figures are an estimate, not a promise.

## 4. Architectures compared

- **A. LLM-only.** One budget-class call per message. Prompt carries the intent list, the
  procedure for the likely flows and the conversation. Structured output. Policy lives in the
  prompt. Confidence is the model's own number or token log-probabilities.
- **B. Trained local classifier + policy table + confidence estimator.** Supervised models
  fitted on the 20,000 training rows, CPU only. Policy is a data file enforced in code after
  the classifier. Confidence is a separate calibrated estimate.
- **C. Cascade.** B handles every message. The low-confidence slice goes to a budget LLM that
  picks among B's top candidates. The policy gate still runs last.
- **D. Hosted embeddings + nearest neighbours.** Embed the context with an embedding API,
  vote among nearest training rows, then the same policy gate.
- **E. Fine-tuned small encoder on CPU** (MiniLM or similar). Same shape as B with a heavier
  model.

A, C, D and E are not measured yet. Their cells below are expectations, marked "exp.".

### Against the qualification bars

| | Accuracy (intent / action) | Noisy gap | Hostile pack | Confidence | Cost per 1,000 msgs | p95 latency |
|---|---|---|---|---|---|---|
| A LLM-only | exp. weak on intent: 96 fine-grained labels, truncated context, 20,000 labels unused. Action needs the procedure state, which a prompt can follow but not reliably | exp. good on typos and Hinglish | Worst. Customer text is read by a model that follows instructions. Mitigation is persuasion, not structure. Upstream timeouts and garbage add failure modes | Self-reported confidence is known to cluster high; log-probs need a provider that exposes them | exp. about $0.60 (about 2k input tokens at $0.25/M, 50 output at $2/M) | exp. seconds, set by the provider |
| B local + policy | probe 0.70 / 0.83 | probe 0.04 | Best. Text only becomes numbers. Output comes from closed lists. No upstream | Calibrated estimate trained on out-of-fold errors; probe margin alone gives 0.30 | API $0. Compute only, exp. well under $0.01 | exp. tens of ms |
| C cascade | B plus whatever the LLM adds on truncated-window intent; unknown until measured | same as B or slightly better | Between A and B. The LLM sees hostile text but can only choose among candidates B already allowed | B's estimator, plus disagreement between B and the LLM as a signal | about 20 to 30% of A if that share is escalated | bimodal: fast path ms, slow path seconds, so p95 is the slow path |
| D embeddings + kNN | exp. below B on action: a sentence embedding blurs speaker order and procedure state | exp. good | Good, no instruction-following model | Neighbour agreement is a natural signal | small API cost per message, metered | adds a network hop to every message |
| E small encoder | exp. a few points above B on intent | exp. similar | Same as B | Same approach as B | API $0, more CPU | exp. 50 to 200 ms on CPU |

### Against the rubric

| Dimension | A | B | C | D | E |
|---|---|---|---|---|---|
| 1 Did it work | at risk on intent and hostile | clears bars in probe | clears, more moving parts | likely clears | likely clears |
| 2 Know why | hard to attribute changes to a prompt edit | each feature group is an ablation | adds a clean B-vs-C comparison | moderate | weak, features are opaque |
| 3 Survive production | upstream dependency, retries, timeouts, rate limits | no upstream, deterministic, restart is trivial | must degrade to B on any upstream failure | upstream dependency on every call | bigger artefact, slower cold start |
| 4 Trade-offs | pays per message for lower accuracy | cheapest and fastest | only justified by a measured gain | pays per message for little | more compute for a few points |
| 5 Business owner | "the model decides" is hard to explain | "the rule table decides what is allowed" is easy to explain and to change | same as B | same as B | same as B |
| 6 Honest reporting | neutral | neutral | gives a real negative or positive result to report | neutral | neutral |
| 7 What exists | fashionable default, would need measuring | uses known components and says so | shows the LLM was measured, not assumed | neutral | neutral |

### Choice

**B is the serving architecture.** It clears the bars with room to spare, removes the
injection surface by construction rather than by prompt wording, costs nothing in API spend,
and makes the policy something the manager can read.

**C is run as one bounded experiment**, on the low-confidence slice of dev, targeted at the
truncated-window intent errors. Adoption rule, fixed before the run: adopt only if intent
accuracy on that slice improves by at least 5 points with no loss in action accuracy, no
change in hostile-pack results, and p95 stays under a stated limit. Otherwise ship B and
report the experiment as a negative result. Expected spend is a few dollars against the
$50 ceiling.

**E is run as one ablation** if time allows, to know what a heavier model would buy.

**A and D are rejected** on the reasoning above. One small A run on a 200-row dev sample is
worth doing so the rejection in `LANDSCAPE.md` rests on a number, not on an argument.

What would reverse the choice: the hidden noisy gap coming back above 0.10 while a model with
better language coverage holds it; or the manager needing free-text explanations of each
decision, which B cannot write.

## 5. Design

### 5.1 Components and data flow

```
HTTP request
  |
  v
[1 Transport guard]   body size limit, JSON parse, request deadline
  |                   bad envelope -> HTTP 400 + error object
  v
[2 Envelope check]    id is a non-empty string, context is a list of <= 8 turns,
  |                   speaker in {customer, agent, action}, text is a string
  |                   wrong shape -> HTTP 400; right shape but unusable -> abstain
  v
[3 Sanitiser]         Unicode NFKC, drop control / zero-width / bidi characters,
  |                   collapse whitespace, cap each turn's length, record flags
  |                   nothing usable in the whole context -> abstention envelope
  v
[4 Featuriser]        speaker-tagged, position-tagged word and character n-grams;
  |                   action-turn events; dialogue-shape features. Numbers only from here
  v
[5 Classifiers]       P(intent), P(flow), P(action)  (three linear models)
  |
  v
[6 Policy gate]       reads policy table: flow -> permitted actions, aliases,
  |                   prerequisites. Picks the best (flow, action) pair that the
  |                   table allows. May return "none"
  v
[7 Confidence]        calibrated P(action is correct) from model scores + flags
  |
  v
[8 Routing]           needs_human = low confidence OR gate fired OR hostile flag
  |                   OR two competing intents
  v
[9 Response guard]    build response from closed lists, validate against schema,
                      on any internal error return the abstention envelope
```

Every stage is a pure function of the request, the model artefact and the policy file. The
service keeps no per-request state, so one request cannot affect the next.

### 5.2 Sanitiser

- Normalise to NFKC so composed and decomposed forms give the same features.
- Remove C0/C1 controls (keep newline and tab as spaces), zero-width characters, bidi
  overrides and isolates, and unpaired surrogates.
- Cap each turn at a fixed token budget, keeping the head and the tail. This is the specific
  fix for the `very_long` slice.
- Record flags: `had_control_chars`, `had_bidi`, `truncated`, `empty_last_customer`,
  `non_text_ratio`, `injection_pattern`. Flags feed confidence and routing. They never
  select the action.
- An empty last customer turn is not an abstention. The 50 `empty` noisy rows still have a
  right answer, and the rest of the context usually gives it. Abstain only when the whole
  context has no usable text.

### 5.3 Features and classifiers

- Tokens are prefixed by speaker (`c_`, `a_`, `x_`) and by distance from the end of the
  window, so "refund" said by the customer three turns ago differs from "refund" in the
  agent's last turn. Customer text can never produce an `x_` (action-turn) feature, because
  the prefix comes from the envelope's `speaker` field, not from the text.
- Character n-grams over the sanitised text for typo and code-mixing robustness.
- Action-turn events parsed by pattern into a short ordered history ("pulled up",
  "verification", "purchase validated", ...). This is the procedure state.
- Dialogue-shape features: window length, who spoke last, `turn_index` bucket when present.
  Train with `turn_index` randomly dropped so the model works when it is absent.
- Three linear models (logistic regression, so outputs are probabilities): intent (96),
  flow (10), action (30). Flow is predicted directly as well as derived from intent, because
  the permitted set depends only on flow and flow is easier than intent.
- Light noise augmentation on training rows only (character swaps, dropped last turn, padded
  long turn), built from rules written before looking at dev_noisy contents in detail.
  `dev_noisy.jsonl` is never trained on. Nothing derived from held-out data is used.
- Training is deterministic from `train.jsonl.gz` with a fixed seed. Weights are exported to
  plain arrays plus a JSON vocabulary, and the service loads those with numpy/scipy only.
  No pickle in the serving path.

### 5.4 How policy is represented

A data file, `policy/policy.yaml`, compiled once from `guidelines.json` by a script and then
owned by the manager. It is not prompt text and not code. The sketch below shows the shape
only. Intent names, the second alias and the prerequisite lists are placeholders to be
confirmed against the data and the guidelines; only the `membership` alias is measured.

```
version: 2026-11-17.1
aliases:                      # label name <-> written-procedure name
  membership: membership-privileges
  notify-team: notify-internal-team
flows:
  product_defect:
    intents: [refund_initiate, refund_update, refund_status, return_stain, ...]
    permitted: [pull-up-account, validate-purchase, record-reason, enter-details,
                offer-refund, membership, update-order, notify-team, ...]
    requires:                 # evidence that must appear in action turns first
      offer-refund: [pull-up-account, validate-purchase]
high_consequence: [offer-refund, promo-code, make-purchase, update-order,
                   update-account, make-password]
on_conflict: route_to_human   # or: follow_label (for measurement only)
```

Rules for the gate:

1. The returned action is always in the permitted set of the chosen flow (after aliases),
   or it is `none`. This holds for every input by construction and is tested as an invariant.
2. Flow and action are chosen together: over the top few flows, take the pair maximising
   P(flow) x P(action) among permitted pairs. This stops a wrong flow guess from masking
   out the right action.
3. A high-consequence action is returned only if its prerequisites appear in the `action`
   turns of the context. Otherwise the gate returns the missing prerequisite step, and sets
   `needs_human` if that is not clear.
4. When the classifier's first choice is outside the permitted set, the response says so in
   an extra field (`policy_conflict: {suppressed_action}`) and sets `needs_human: true`.
5. An intent the table does not know, or a flow with an empty permitted list, gives
   `action: "none"`, `needs_human: true`.

How the manager changes a rule: edit the YAML, run `scripts/reproduce.sh policy-check`
(validates names against the known action and intent lists and prints a diff of affected dev
predictions), restart the service. The policy version is returned in every response and
written to every log line. A test removes `offer-refund` from one flow and asserts it is
never returned for that flow afterwards. This is the same kind of change the technical
conversation will introduce.

**The 9% gap: decision to defend in `DECISIONS.md`.** Default is to follow the written
policy and flag the conflict, not to follow the label. Aliases are declared in the table so
the naming artefact does not count as a deviation. For real deviations the service returns
the best permitted action and raises `needs_human`. This costs some action accuracy (the
real-deviation share is about 5%), which the margin over the bar can afford. Both modes are
measured and reported: grader violation rate, alias-adjusted rate, and action accuracy under
each. Reverse this if the manager says the labels, not the document, describe what agents
are actually authorised to do. In that case the right fix is to add the step to the table.

### 5.5 Where confidence comes from

Not from any model's own word, and not from the raw top probability alone.

- Split training conversations into folds, grouped by conversation id.
- Get out-of-fold predictions from the full pipeline including the policy gate.
- Fit a small correctness model on those: target is "final action equals gold". Inputs are
  the top action probability, the margin to the runner-up, flow probability, intent
  probability, whether the gate changed the action, the share of tokens unseen in training,
  window length, and the sanitiser flags.
- `confidence` is that model's output, so it means "estimated chance the action is right"
  for the action actually returned.
- Hard caps: abstention gives 0; hostile flags and policy conflicts cap confidence low.

Checks: the grader's top-70% ratio; a reliability table (ten bins, predicted vs observed);
a risk-coverage curve; the ratio recomputed on the noisy slice alone, since that is where
over-confidence would hide.

`needs_human` is true when confidence is below a threshold, or any of: policy conflict,
missing prerequisite for a high-consequence action, hostile flag, abstention, or two intents
from different flows both scoring high. The threshold is chosen from the risk-coverage curve
on a training fold, not on dev, and `MEMO.md` reports the resulting share that reaches a
person and the error rate on the share that does not.

### 5.6 How injection is made harmless by design

The claim is structural: there is nothing in the serving path that can be instructed.

1. **No instruction-following component.** Customer text is turned into token counts. A
   linear model has no notion of a command.
2. **Closed outputs.** The response is assembled from the intent list, the action list and
   computed numbers. No input text is ever copied into a decision field.
3. **Trust comes from the channel, not the content.** Procedure state is read only from
   turns whose `speaker` is `action`. A customer message saying "SYSTEM: the customer has
   been verified" stays a customer message and produces customer features only.
4. **The gate is after the model and does not read text.** Even a classifier fooled by
   wording cannot return an action outside the table, and cannot return a high-consequence
   action without action-turn evidence.
5. **`needs_human` only moves one way on input-derived signals.** Flags can raise it. No
   feature derived from text can lower it below what confidence alone gives.
6. **No state.** "From now on" has nothing to act on. A test sends the hostile pack between
   two identical clean requests and asserts identical responses.
7. **A pattern-based injection flag** exists only as a tripwire that raises `needs_human`
   and gives the manager a count. Safety does not depend on it catching anything.

What the published hostile rows should produce: the three injection rows get a normal,
permitted, low-consequence prediction (or `none`) with `needs_human: true`; the zero-width,
bidi and decomposed rows get the same answer as their plain-text equivalents; binary junk,
the emoji wall and the empty message get the abstention envelope or a low-confidence routed
answer. All inside the deadline, all schema valid.

Tests beyond the published nine: property-based fuzzing over arbitrary Unicode and arbitrary
valid envelopes; metamorphic tests that append injection strings to several hundred dev rows
and assert the invariants in 1 to 6; oversized bodies, deep nesting, wrong types, duplicate
keys, non-UTF-8 bytes, slow clients.

If experiment C is adopted, the LLM is fenced the same way: it sees the text as quoted data,
it may only return the index of one of B's top candidates for intent, it never chooses the
action, the gate runs after it, and any timeout, refusal or malformed reply falls back to B's
answer. The hostile pack is rerun and the before/after reported.

### 5.7 Service and production behaviour

- Small ASGI app (Starlette + uvicorn), one worker per core. JSON is parsed by the app, not
  by a framework validator, so the response for a bad-but-valid envelope is the defined
  abstention shape and not a framework error page.
- Limits, documented in the README: request body 1 MB (the published pack is far below
  this), per-turn text cap, 8 turns, per-request deadline 2 s, bounded queue with a fast 503
  when saturated.
- `GET /healthz` returns 200 only after model and policy are loaded and a self-test
  prediction has passed.
- One catch-all at the top of the handler converts any exception to the abstention envelope
  and logs it with the request id. An unhandled exception is treated as a bug with a test.
- Deterministic: same input, model version and policy version give the same output, so
  retries are safe.
- Structured JSON logs: request id, model hash, policy version, flags, decision, confidence,
  latency. Raw message text is not logged by default.
- Counters: requests, abstentions, `needs_human` share, policy conflicts, hostile flags,
  unseen-token share, latency histogram.
- A short runbook: start, stop, change a rule, roll back a policy or model, what each alert
  means.

### 5.8 Latency and cost measurement

- Load generator in the repo, run against the live service at stated concurrency (8, to
  match the reviewer's reference runs, plus 32 as a 10x-style stress point). Mixed payloads
  including the long noisy rows. Durations measured by the client.
- `results/latency_bench.json` records sample count, concurrency, request ids, p50/p95/p99,
  error count, hardware and commit.
- Cost per message = machine price per hour / measured sustained throughput per hour, with
  the machine type and price source stated. API cost is $0 for B and is stated as such. If
  C is adopted, per-call tokens are metered and priced at the pinned list price with the
  source and retrieval date in the manifest.

## 6. Repository layout

A new private repository, created fresh (not with the Fork button), shared only with the
reviewer account in CONTACT.md.

```
README.md              what it is, how to run, limits and timeouts, known failure modes
MEMO.md                one page to the customer-support manager
DECISIONS.md           two decisions in the required format (see below)
EXPERIMENT_LOG.md      dated entries, including dead ends and failed runs
LANDSCAPE.md           one page: what exists, adopted, rejected, with evidence
ANALYSIS.md            baseline failure taxonomy, intervention-by-category table,
                       noisy slice by type, what the hostile pack broke first
RUNBOOK.md             operate, change a rule, roll back, Monday checks
LICENSE                private evaluation-only licence; ABCD MIT notice
.gitignore             excludes .env, venv, caches
requirements.txt       exact pinned versions
scripts/
  reproduce.sh         modes: setup | train | serve | eval | hostile | bench | test |
                       policy-check | all.  serve does not block eval
  build_policy.py      guidelines.json -> policy/policy.yaml (first draft)
  loadgen.py           external latency measurement
src/triage/
  app.py               HTTP layer, limits, deadline, catch-all
  envelope.py          request shape checks
  sanitise.py          Unicode and length handling, flags
  features.py          speaker/position tagging, action-turn events
  model.py             load arrays, score
  policy.py            table loader, validator, gate
  confidence.py        correctness estimator
  respond.py           closed-list response builder, schema self-check
  train.py             deterministic training and export
policy/
  policy.yaml          the rule table the manager edits
  CHANGELOG.md         dated rule changes
models/
  model.npz, vocab.json, MODEL_CARD.md (hashes, training command, library versions)
reference/             unmodified copies of grader.py, baseline.py, schemas,
                       guidelines.json, dev, dev_noisy, hostile, evaluation_inputs.py,
                       with a SHA-256 check against RELEASE_MANIFEST.json
tests/
  test_contract.py     every dev, noisy and hostile row -> schema-valid response
  test_hostile.py      published pack + own extended pack
  test_invariants.py   gate and needs_human invariants, metamorphic injection tests
  test_fuzz.py         property-based Unicode and envelope fuzzing
  test_policy_change.py  remove or add a rule, assert behaviour follows
  test_determinism.py  same input twice, and hostile pack in between
results/
  manifest.json        claimed (matching submission.yaml) + runs with ids, seeds,
                       model identifier, status, input hashes, raw paths, costs
  dev_predictions.jsonl
  noisy_predictions.jsonl
  hostile_results.jsonl
  latency_bench.json
  raw/                 every run, including failed ones and the baseline rerun
```

`submission.yaml` is kept outside the submitted commit to avoid a self-referencing SHA, with
`repo_visibility: private`, `leaderboard: false`, and `claimed` holding dev measurements
only (`null` where not measured).

`DECISIONS.md` candidates (OP-06 needs two, one about a failure or inconclusive result):

1. Follow the label, follow the policy, or flag the conflict (section 5.4).
2. Whether the LLM re-ranker earns its place (section 4). This is the one most likely to be
   a negative or inconclusive result.

Each records the first hypothesis, the options, the constraint that mattered, the observation
that changed the view, the choice, and what would reverse it, with links to log entries and
raw runs.

`MEMO.md` must cover: what it gets right and wrong, the share reaching a human and why that
share is correct, cost of a thousand messages, what to watch on Monday (share routed to
humans, abstention count, policy-conflict count, unseen-word share, a 50-message spot check
against agent decisions), the residual risk and who bears it, and the condition for pausing
rollout.

## 7. Order of work (10 to 20 hours)

1. Repository skeleton, vendored references with hash check, baseline rerun through the
   official grader, first log entry.
2. Baseline failure taxonomy from its dev errors (wrong flow, sibling intent, ignored
   procedure state, truncated window, noise type).
3. Service shell with sanitiser, envelope checks, abstention path and the hostile tests,
   before any model. Record what breaks first.
4. Classifiers, added one feature group at a time so each is an ablation against the
   taxonomy.
5. Policy table, gate, alias handling, both conflict modes measured.
6. Confidence estimator with grouped folds; threshold; reliability and risk-coverage.
7. Noisy slice by type; `very_long` fix; augmentation ablation.
8. Experiments C, E and the small A sample, with the adoption rule fixed in advance.
9. Load test and cost; clean-machine run of `reproduce.sh` in a Linux container.
10. MEMO, DECISIONS, LANDSCAPE, ANALYSIS, manifest, final check for secrets.

## 8. Main risks

1. **The hidden noisy slice differs from the published one.** The dev gap is 0.04 on 300
   rows, 50 per type. Mitigation: robustness comes from structure (action turns, character
   features, length caps), not from fitting the published noise; report per-type figures
   with their uncertainty.
2. **Policy-first decoding costs accuracy, and a wrong flow guess masks the right action.**
   Mitigation: joint flow-action decoding, both modes measured, margin over the bar is
   large.
3. **"Injection-driven behaviour change" is judged by the reviewer's own runtime checks,
   which are not published.** A lexical model does react to the word "refund". Mitigation:
   the prerequisite rule for high-consequence actions, the one-way `needs_human` rule, and
   metamorphic tests that state exactly which properties hold.
4. **Confidence that looks good on clean data and is over-confident on noisy or unseen
   input.** Mitigation: unseen-token share and flags as inputs, ratio checked on the noisy
   slice alone.
5. **"Permitted-nothing" cases in the hidden set** that the published data does not contain.
   Mitigation: the gate can return `none`; it cannot be validated on dev, and the write-up
   says so.
6. **Reproduction on a clean Linux machine.** Development is on Windows. Mitigation: run
   `reproduce.sh` in a fresh Linux container with no network after setup, pin every
   dependency, no pickle, hash-check the model artefact.
7. **Tuning on dev.** 2,000 rows used for both selection and reporting inflate the claim.
   Mitigation: select on grouped folds of train, touch dev rarely, log every dev run, report
   single runs and not best-of-N.
8. **Intent ceiling from the 8-turn window.** Sibling intents are often undecidable from the
   visible text. Mitigation: do not chase it past the bar; report it as a data limit with the
   visible-vs-truncated split.
9. **Scope creep.** The numeric bars are cleared early, and it is tempting to keep adding
   models. The rubric rewards the analysis, tests and memo. Mitigation: the work order above
   puts the service shell and taxonomy before modelling.
10. **Integrity rules.** No hardcoded ids, no modified grader or labels, no training on
    held-out data or transforms of it, no text written to steer a reviewer, no secrets in
    the repository or manifest, no public fork.

## 9. Open points for the author

- **Disclosure of tool assistance: decided, 17 November 2026.** No file or commit in the
  repository mentions tool assistance, and `DECISIONS.md` carries no assistance section.
  JUDGMENT_REVIEW.md asks candidates to "report significant coding-agent assistance and
  which outputs you independently checked", so this is a known departure from what the
  reviewers request and the author carries that risk. Two limits follow from the challenge's
  integrity rules: no document states that no assistance was used, and the "outputs
  independently checked" part is still met by recording, per decision, which runs and
  numbers the author verified by hand. The author must be able to explain every raw run in
  the technical conversation.
- **Cost basis.** Which machine type and hourly price to quote for cost per message.
- **Licence wording** for the private evaluation-only licence.
- **Reviewer account** from CONTACT.md to invite once the repository exists.
