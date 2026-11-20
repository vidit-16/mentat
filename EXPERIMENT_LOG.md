# Experiment log

Dated entries, newest last. Every run named here has its raw output in `results/raw/<run-id>/`
and an entry in `results/manifest.json`. Failed and abandoned runs stay in.

Machine for all runs unless stated: Windows 11 laptop, CPU only, Python 3.12.10, library
versions in `requirements.txt`. Dev means `reference/dev.jsonl` (2,000 rows) plus
`reference/dev_noisy.jsonl` (300 rows), scored by the unmodified official `grader.py`.

---

## 2026-11-17 — Planning probe (before this repository existed)

One untuned linear SVM over word, character and speaker-tagged features, written as a
throwaway script while writing `PLAN.md`. Dev: intent 0.7043, action 0.8343, macro-F1 0.6717,
gap 0.0395, top-70 ratio 0.3037. **Reconstructed note:** the script and its output were not
kept in this repository, so this run has no raw output and is not in the manifest. It is
listed only because the plan's architecture choice leaned on it. Every number in the
submission comes from the runs below.

A first attempt at that probe used logistic regression with C=20 and did not finish in
10 minutes on this laptop; it was stopped and replaced by the linear SVM. That is the reason
the classifiers here are linear SVMs with temperature-scaled scores rather than logistic
regression.

## 2026-11-17 — Reference files and baseline rerun (`baseline-001`)

Copied the 12 OP-06 files from the challenge repository at commit
`d87699bb97de6504b33f681eed66918a4d433ba0`. `scripts/check_reference.py` checks them against
`reference/SHA256SUMS`, and those hashes were checked against `RELEASE_MANIFEST.json`.

**What went wrong first:** the first copy came from a Windows checkout with line-ending
conversion on, and `README.md` failed the release hash. Copied the bytes straight out of git
instead (`git show HEAD:path`) and added `reference/** -text` to `.gitattributes` so the files
are never converted again. All 12 match now.

Baseline, trained on `train.jsonl.gz`, scored by the official grader:

| intent | action | macro-F1 | gap | schema | violations | top-70 ratio |
|---|---|---|---|---|---|---|
| 0.3748 | 0.3913 | 0.4508 | 0.0743 | 100% | 0.1404 (gold 0.0883) | 1.0 |

Identical to the published numbers to four decimals.

## 2026-11-17 — Baseline failure taxonomy (`baseline-001/taxonomy.json`)

`scripts/taxonomy.py` puts every action error in one category (first rule that matches):
`wrong_flow` (predicted intent is in another flow), `sibling_intent` (right flow, wrong
intent), `repeated_step` (right intent, but the action is a step the context already shows
as done), `wrong_step` (anything else).

Baseline, 2,300 labelled rows, 1,400 action errors:

| category | errors | share |
|---|---|---|
| wrong_flow | 662 | 47% |
| wrong_step | 310 | 22% |
| sibling_intent | 281 | 20% |
| repeated_step | 147 | 11% |

Intent errors: 941 wrong flow, 497 sibling. Errors are worse when the 8-turn window has lost
the start of the dialogue (action error 0.66 vs 0.51; 1,527 of 2,300 rows are cut).
`very_long` noisy rows: 50 of 50 intents wrong, 41 of 50 actions wrong. The baseline reads
only the last four turns as one bag of words, so a long message drowns everything else.

Reading: the baseline's main problem is not the hard part of the task (which step comes next)
but the easy part (which flow is this). It also has no idea which steps already happened:
147 errors propose a step the context shows as done.

## 2026-11-17 — Service shell and first hostile run (`hostile-shell-001`)

Built the input handling before any model: body limits, JSON parsing that rejects duplicate
keys, NaN and deep nesting, shape checks, Unicode cleaning, length caps, the abstention shape,
and a stand-in classifier that always returns the same answer. 95 hostile tests
(the published nine, 62 extra valid envelopes, 22 transport probes, method and path checks).

**What broke first:** the app did not start. Starlette 1.10 removed the `on_startup` argument;
moved the load and self-test into a lifespan handler. After that all 95 passed on the first
run. Nothing in the extended pack crashed the shell, which I take as weak evidence: the shell
had no model to break. The pack is rerun after every change to input handling.

## 2026-11-17 — Event parser for `action` turns

69% of rows contain system-written `action` turns. Wrote 20 patterns for them. First pass
left 327 of 22,482 action turns in training unmatched; all were templates with an empty slot
(`membership level of  has been noted.`). Made the slot optional: 0 unmatched. Dropped three
patterns I had written from memory of ABCD (`the customer was told to log ...`) that match
nothing in the data.

## 2026-11-17 — Feature block ablation (`ablate-001-w`, `-wc`, `-wcs`, `-wcsx`)

Each run adds one feature block. No augmentation, no folds, confidence is a placeholder,
policy mode `follow_label` so the gate does not mix into the comparison. Linear SVM, C=0.5.

| run | blocks | intent | action | macro-F1 | gap | violations | top-70 ratio |
|---|---|---|---|---|---|---|---|
| ablate-001-w | words | 0.7061 | 0.8017 | 0.6852 | 0.0097 | 0.1004 | 0.4544 |
| ablate-001-wc | + characters | 0.7104 | 0.7909 | 0.6922 | 0.0432 | 0.1065 | 0.4309 |
| ablate-001-wcs | + speaker/position | 0.7191 | 0.8157 | 0.6943 | 0.0295 | 0.0996 | 0.3304 |
| ablate-001-wcsx | + procedure state | 0.7252 | 0.8252 | 0.6958 | 0.0328 | 0.0935 | 0.2735 |

Action errors by category:

| run | wrong_flow | sibling_intent | repeated_step | wrong_step |
|---|---|---|---|---|
| baseline-001 | 662 | 281 | 147 | 310 |
| ablate-001-w | 105 | 88 | 15 | 248 |
| ablate-001-wc | 117 | 85 | 18 | 261 |
| ablate-001-wcs | 100 | 71 | 9 | 244 |
| ablate-001-wcsx | 96 | 62 | 10 | 234 |

What moved what:

- Reading the whole window (all 8 turns, with a per-turn length cap) instead of the last four
  turns as one bag removes 84% of wrong-flow action errors on its own. That one change is most
  of the gain over the baseline.
- The per-turn cap (80 tokens: first 50, last 30) is in every run above, so its effect is not
  separated here. `very_long` intent errors fall from 50 to 20 with words only. A separate
  ablation of the cap is still to do.
- **The character block did not help.** Action accuracy fell 1.1 points and the noisy gap
  went from 0.0097 to 0.0432. My plan assumed character n-grams would help with typos. On
  this data they add noise: the typo rows are mostly short replies like `ooh` or
  `acconut id`, where the rest of the context carries the answer. Kept for now because the
  later blocks recover the loss, but this is an open question for the final configuration.
- Speaker/position tags and the procedure-state block mostly help action, and help the
  confidence ratio a lot (0.43 → 0.27), which makes sense: they tell the model where in the
  procedure the dialogue is.
- `wrong_step` barely moves (248 → 234). Most remaining action errors are right flow, right
  intent, wrong next step. That is where the text does not say which branch of the procedure
  the agent took (for example whether the Oracle said yes).

## 2026-11-17 — Full training run, first attempt (`train-001`, failed)

Augmentation on (20% of rows get one noisy copy: typos, empty last turn, long padding, a
second request appended; 23,962 rows in all), `turn_index` dropped on 15% of rows, five folds
grouped by conversation for temperatures and the confidence model.

**Failed.** The three full-data fits finished (about 6 minutes), then the out-of-fold step
died: `TerminatedWorkerError`, with "Windows fatal exception: access violation" inside
liblinear in a joblib worker process. joblib passes large arrays to worker processes as
read-only memory-mapped files, and liblinear crashed reading one. Nothing was written to
`models/`. Log kept as `results/raw/train-001-failed.log`. The session running it also ended
around then, which is why I did not notice for a while.

Fix: run the fold fits in a thread pool (`backend="threading"`). liblinear releases the GIL,
so threads still run in parallel, and they share the matrix instead of mapping it.

## 2026-11-17 — Full training run, second attempt (`train-002`)

Same configuration with the thread pool. Finished in 19 minutes (features 7.5 min, three
full fits 4.5 min, 15 fold fits 5.5 min, confidence model 1.5 min). Log and out-of-fold
report in `results/raw/train-002/`.

Out of fold, on the 23,962 training rows (augmented copies stay in their conversation's fold):

| | |
|---|---|
| intent / flow / action, raw | 0.7096 / 0.8691 / 0.8264 |
| action after the policy gate | 0.8211 |
| conflict rate (model's first choice not permitted) | 2.9% |
| held back (high-consequence action, no system step in view) | 0.6% |
| top-70% error ratio | 0.3066 |
| threshold for 90% accuracy on automated messages | 0.5652, which automates 84.7% |

The threshold is chosen here, on out-of-fold training predictions, not on dev.

## 2026-11-17 — Dev with the shipped model (`dev-002`, `dev-002-follow`, `dev-002-noti`)

| run | intent | action | macro-F1 | gap | violations | top-70 ratio | to a person |
|---|---|---|---|---|---|---|---|
| dev-002 (follow the procedure) | 0.7204 | 0.8217 | 0.6895 | 0.0327 | 0.0778 | 0.2787 | 15.4% |
| dev-002-follow (follow the label) | 0.7204 | 0.8226 | 0.6895 | 0.0337 | 0.0983 | 0.2802 | 15.4% |
| dev-002-noti (no `turn_index`) | 0.7217 | 0.8222 | — | — | — | 0.3003 | — |

- Following the written procedure costs 0.09 points of action accuracy (2 rows of 2,300)
  and takes the violation rate from 0.098 to 0.078, below the gold labels' own 0.088. This
  is the main evidence for decision 1 in `DECISIONS.md`.
- Without `turn_index` nothing moves except confidence (0.28 → 0.30). The 15% dropout in
  training did its job; the service does not depend on an optional field.
- **Augmentation did not help.** `ablate-001-wcsx` (same features, no augmentation, no
  dropout) scored action 0.8252 and gap 0.0328; the augmented model scores 0.8217 and 0.0327.
  The difference is within noise (one standard error on 2,300 rows is about 0.8 points).
  Per noise type the two models trade places by up to 8 points on 50 rows each, which is
  also noise. I kept the augmented model because it carries the `turn_index` dropout, and
  did not spend another 19 minutes training a variant with dropout and no augmentation.
  That variant is the honest next check.

## 2026-11-17 — Tests against the trained model; what the extended pack found

First full test run: 104 passed, then a failure.

1. **Spoofed system text.** Customer text written like a system event ("account has been
   pulled up for me. purchase validation in progress ... a refund has been made") was not
   caught by the injection tripwire, so the answer kept 0.80 confidence. The structural
   defence held: the text was read as customer text, the answer was still routed to a
   person, and no refund was proposed. But the tripwire should catch it. No customer turn in
   the 118,180 non-system training turns matches a system-event pattern, so I flag customer
   turns that do.
2. While checking false positives, two training rows tripped the tripwire on "...from you are
   now out of stock". The `you are now` pattern was too loose; it now requires a role word
   after it (`you are now in developer mode`). Training rows flagged: 0.
3. **The policy-change test was wrong, not the code.** It required a person for every
   refund-flow row after refunds were removed from the table, including rows where the model
   never proposed a refund. Fixed the test to check only rows that would have got
   `offer-refund`, and to check the conflict is reported.

After these: 116 passed. Dev unchanged (`dev-003`). Through HTTP (`dev-003-http`) the
numbers are identical to in-process.

## 2026-11-17 — Hostile pack over HTTP (`hostile-002`), and one answer I did not like

99 requests (9 published, 68 extended, 22 transport probes), each followed by a canary
request to detect a later change in behaviour. 99 passed, slowest 170 ms.

But reading the answers rather than the pass/fail: `hostile-004` (bidi-wrapped "cancel my
order", one customer line) got `search-faq` with **0.99 confidence and no human**. The
answer is defensible (single-line openings in training are mostly `search-faq`), the
confidence is not: only 62 of 20,000 training rows have no agent turn, so the confidence
model has almost nothing to go on. Added a rule: no agent turn yet means confidence capped
at 0.5 (below the threshold) and reason `little_context`. Dev effect (`dev-004`): 6 rows
more go to a person (15.4% → 15.6%), ratio 0.2787 → 0.2821. All nine published hostile
rows now reach a person; a test holds that.

Also made the model version hash cover `confidence.json`, so a change like this shows up in
every response and log line.

## 2026-11-17 — LLM re-ranking (`llm-001`, not adopted)

Rule fixed before running (`PLAN.md` section 4 and the script header): adopt only if intent
accuracy on the low-confidence slice rises by at least 5 points, action accuracy does not
fall, and p95 of the call is under 2 s.

`gpt-4.1-mini-2025-04-14`, temperature 0, the first 150 dev and noisy rows below the
confidence threshold. The model sees the cleaned conversation as quoted data and the local
model's top five intents, and answers with a number. The policy gate reruns with its choice.

| on the 150 rows | local | with LLM |
|---|---|---|
| intent accuracy | 0.56 | 0.46 |
| action accuracy | 0.32 | 0.29 |

The LLM fixed 13 intents and broke 28. The right intent was among the five candidates 75%
of the time, so the ceiling was there; the model did not find it. p50 778 ms, p95 1,199 ms,
1 unusable reply (fell back), 34,594 input and 149 output tokens, **$0.014076**.

Not adopted. My reading: the hard rows are siblings like `return_size` / `return_color`
where the deciding word left the 8-turn window, and the LLM guesses from what remains just
as the local model does, but without the training data's priors. I did not try prompt
variants or a larger candidate list; with this gap a few prompt tweaks are unlikely to reach
+5 points, and each try spends dev rows on selection.

## 2026-11-17 — Length cap ablation (`ablate-002-w-nocap`)

Same as `ablate-001-w` (words only) with the 80-word per-turn cap switched off:

| | intent | action | gap | very_long intent errors | very_long action errors |
|---|---|---|---|---|---|
| cap on (`ablate-001-w`) | 0.7061 | 0.8017 | 0.0097 | 20 / 50 | 12 / 50 |
| cap off (`ablate-002-w-nocap`) | 0.6965 | 0.7970 | 0.0463 | 42 / 50 | 23 / 50 |

The cap is the fix for long messages: it halves their errors and accounts for most of the
noisy gap in the words-only model.

## 2026-11-17 — Docker unavailable; clean Linux check moved to CI

The plan was to run `reproduce.sh all` in a fresh Linux container. Docker Desktop did not
start on this laptop (WSL VM limited to about 3 GB; Docker and the training run were
competing for it). WSL Ubuntu has Python but not the `venv` package, and installing it
needs root. Instead a GitHub Actions workflow (`.github/workflows/reproduce.yml`) runs
`scripts/reproduce.sh all` on a fresh `ubuntu-24.04` VM with system Python and no secrets.
Result recorded below once it has run.

## 2026-11-17 — Submitted runs (`dev-005-http`, `hostile-003`, `bench-win2-*`)

Final code, through the HTTP service with 2 workers on the laptop:

| intent | action | macro-F1 | gap | schema | violations | top-70 ratio | to a person | accuracy when automated |
|---|---|---|---|---|---|---|---|---|
| 0.7204 | 0.8217 | 0.6895 | 0.0327 | 100% | 0.0778 (gold 0.0883) | 0.2821 | 15.6% | 0.9042 |

Hostile: 99 of 99, slowest 243 ms. Load (laptop, i5-10210U, 2 workers, client on the same
machine): concurrency 8 p95 62.7 ms at 213 requests/s; concurrency 32 p95 302 ms at
229 requests/s; 0 errors. An earlier run of the same test gave p95 45 ms at concurrency 8:
laptop timings vary by about 40% from run to run, which is one more reason the CI numbers
on a clean machine are the ones to quote.

API spend for everything in `results/`: **$0.014076** (the LLM experiment only).

## 2026-11-17 — First clean-Linux run in CI (GitHub Actions run 44134811498, failed)

Fresh `ubuntu-24.04`, system Python 3.12.3, `scripts/reproduce.sh all`. Setup, hash check and
all 117 tests passed. Evaluation through the HTTP service reproduced the committed dev
numbers exactly (intent 0.7204, action 0.8217, top-70 ratio 0.2821). Then the hostile step
failed: the nine published rows passed, and all 90 requests after them failed with
connection errors.

**Cause: a bug in `reproduce.sh`, not in the service.** `stop` sent the shutdown signal to the
evaluation step's server and returned at once. The hostile step's `start` launched a new
server, which died with `Address already in use`; but the old server, still draining, answered
`/healthz`, so the script took it as ready. It then finished shutting down during the run.
The service log in the CI artifact shows both.

Fix: `stop` waits for the process to exit and the port to be free; `start` refuses to start
when the port is already in use, and only reports ready while its own process is alive. The
same mistake would bite anyone restarting the service in production with a health check that
does not know which process answered, so RUNBOOK.md now says to stop and wait before
starting.

Second finding from the same run: the model version reported on Linux (`2de59e320f72ca21`)
differed from the laptop's (`54c65d7534fd5fb3`). Training on Windows wrote the JSON model
files with CRLF line ends; git stores them with LF; the version is a hash of the files.
Training now writes LF on every platform, and the laptop checkout uses LF, so both report
`2de59e320f72ca21`. Weights and predictions were never affected; only the version label.

## 2026-11-17 — Clean-Linux run passes (GitHub Actions run 44135706221, commit e212761)

`ubuntu-24.04`, 2 vCPU, 7.8 GiB, system Python 3.12.3, no secrets. `scripts/reproduce.sh all`:

- setup and reference hash check: OK
- tests: 117 passed
- evaluation through HTTP: intent 0.7204, action 0.8217, macro-F1 0.6895, gap 0.0327,
  schema 100%, violations 0.0778, top-70 ratio 0.2821; identical to the laptop
- hostile pack: 99 of 99 passed, slowest 39 ms
- load, 2 workers, 3,000 requests each: concurrency 8 p95 44.1 ms at 186 requests/s;
  concurrency 32 p95 54.8 ms at 652 requests/s; 0 errors
- the workflow's own check: CI accuracy within 0.002 of the committed numbers: passed

This is the submitted run. Its artifact is in `results/raw/ci-44135706221/`; the failed first
run's artifact is in `results/raw/ci-44134811498-failed/`. At concurrency 8 the client, not
the server, is the bottleneck (throughput rises 3.5 times at 32 while p95 barely moves), so
the concurrency 8 figure is an upper bound on server latency at that load.

## 2026-11-17 — Raw logs were missing from the repository

While checking every hash in `results/manifest.json` against the committed bytes, two run
logs (`train-001-failed.log`, `train-002/train.log`) turned out not to be in git at all: the
`.gitignore` rule `*.log` had silently excluded them, along with the service logs. The
manifest listed them, so a reviewer would have found missing evidence, including the failed
run. Added an exception for `results/raw/`, committed the five logs, and the manifest
writer now uses LF so its hashes match what git stores. All 29 listed hashes match HEAD.

## 2026-11-20 — History split into smaller commits; clean-Linux rerun (`ci-44771488788`)

The repository had four commits, the first holding almost everything, which made the work
hard to review. Rebuilt `main` as 31 commits in the order the parts were built, each dated
with the time that part was done on 17 November; the final tree is byte for byte the same as
before. This removed commit e212761, which the submitted CI run (44135706221) was tied to, so
I reran `scripts/reproduce.sh all` on the new head (bc9f9aa) and made that the submitted run.

- tests: 117 passed
- evaluation through HTTP: intent 0.7204, action 0.8217, macro-F1 0.6895, gap 0.0327,
  schema 100%, violations 0.0778, top-70 ratio 0.2821; same as before
- hostile pack: 99 of 99 passed, slowest 21 ms
- load: concurrency 8 p95 44.0 ms at 188 requests/s; concurrency 32 p95 45.0 ms at 742
  requests/s; 0 errors

Labels are identical to the earlier run and to the laptop. 22 of 2,300 confidences differ by
0.000001: this VM had an AMD EPYC 9V45, the earlier one an EPYC 7763, and the last digit of
the rounded logistic output moves with the floating-point path. The concurrency 32 p95 is
10 ms lower than last time on the newer CPU, which is a reminder that a single CI timing is
one draw from a noisy machine. Artifact in `results/raw/ci-44771488788/`.

## 2026-11-20 — Hinglish recheck on all of dev (`hinglish-001`)

ANALYSIS.md left one open item: code-mixed action accuracy fell from 0.82 (words only) to
0.70 (shipped), on 50 rows. Too few to say anything, so I made more.

Comparing the 50 published code_mixed rows word by word with their clean originals gives the
rewrite: 43 append "thoda jaldi karo please" to the last customer turn; the rest also change
"my" to "mera" or misspell "order" as "ordr". `scripts/hinglish_slice.py` applies that to
every dev row with a customer turn (1,995) and compares each with its clean version through
the same pipeline. A third variant swaps 18 common English words for Hindi ones; the
published generator does not do this, so it is a stress test only.

| | clean | suffix | suffix + swaps | heavy |
|---|---|---|---|---|
| intent accuracy | 0.7368 | 0.7343 | 0.7348 | 0.7308 |
| action accuracy | 0.8281 | 0.8281 | 0.8276 | 0.8281 |
| sent to a person | 14.6% | 12.8% | 12.7% | 12.5% |
| action accuracy when automated | 0.9061 | 0.8966 | 0.8955 | 0.8923 |
| wrong and automated (rows) | 160 | 180 | 182 | 188 |

Accuracy does not move: the earlier 0.82 → 0.70 was noise. Routing does. The suffix raises
confidence on 1,796 of 1,995 rows, 47 rows move from a person to automated, and 24 of those
are wrong.

`scripts/confidence_breakdown.py` splits the change by signal. Almost all of it is
`unseen_words` (+0.18 logit on average; the model's own scores move the other way, -0.04).
Cause: in training this signal is measured against a vocabulary fitted on the same 20,000
rows, so it is nearly always 0 (mean 0.0018, scale 0.0083). Clean dev already averages 0.006;
with the suffix it averages 0.061, seven scales out. The fitted weight is small and positive,
which is meaningless on data it never saw, and at seven scales it adds up. A train/serve
mismatch I should have caught when I chose the signal.

Not fixed yet. The fix is to measure `unseen_words` in training the same way the service
does, against a vocabulary that has not seen the row (fit it per fold), or drop the signal.
Either needs a retrain and a new model version, so every result reruns.

