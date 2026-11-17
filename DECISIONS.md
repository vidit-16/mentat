# Decisions

Two consequential decisions in the format JUDGMENT_REVIEW.md asks for, then every place where
the work departed from `PLAN.md` and why. Log entries are in `EXPERIMENT_LOG.md` under the
date and run id given.

## Decision 1. When the procedure and the agents disagree: follow the procedure, route the conflict

**Initial hypothesis.** About 9% of gold actions sit outside what the written procedure
permits. I expected that following the procedure strictly would cost close to that much
action accuracy, and that the right call would still be to follow it, because the manager's
question is what agents are *allowed* to do.

**Options.**

1. Follow the label: return whatever agents usually did next, permitted or not.
2. Follow the procedure silently: mask out forbidden actions and return the best permitted one.
3. Follow the procedure and flag the conflict: as 2, plus `needs_human: true` and a
   `policy_conflict` field naming the action that was held back.

**Constraint that mattered.** The service proposes actions an agent may take, including
refunds and account changes. An action outside the written procedure has no owner if it goes
wrong. Measured accuracy is what the bar checks; authorised action is what the manager
asked for.

**What changed my view.** Two measurements.

- Part of the 9% is naming, not behaviour. Of 1,697 out-of-procedure training labels, 724 are
  `membership` where the procedure says `membership-privileges`. I declared that one alias in
  the policy table. The remaining gap is agents pulling up accounts or verifying identity in
  flows whose procedure does not list those steps.
- The cost is far smaller than the gap, because the classifier rarely proposes a forbidden
  action in the first place: its first choice was forbidden in 70 of 2,300 dev rows (3.0%).
  Following the procedure changes the correctness of 2 answers:

| [dev-002] vs [dev-002-follow] | action accuracy | violation rate (gold: 0.0883) |
|---|---|---|
| follow the label (option 1) | 0.8226 | 0.0983 |
| follow the procedure, flag (option 3) | 0.8217 | 0.0778 |

Of the 70 conflicts, the held-back action was what the agent actually did in 21. Those are
exactly the cases a person should see: either the agent was right and the procedure needs a
new step, or the agent deviated.

**Chosen.** Option 3, the default in `policy/policy.yaml` (`on_conflict: route_to_human`).
Option 1 stays available as `follow_label`, for measurement only.

**What would reverse it.** If the manager says the labels, not the document, describe what
agents are authorised to do. Then the fix is still not option 1; it is adding the missing
step to the policy table, after which the conflict disappears on its own. I would also
revisit if the conflict rate on live traffic were much higher than 3%, because then routing
every conflict would swamp the human queue.

## Decision 2. Whether a budget LLM earns a place: no (a failed experiment)

**Initial hypothesis.** The local model's worst rows are ones where the 8-turn window has
lost the opening message and the remaining text is ambiguous between sibling intents. A
language model reading the text might pick the right sibling where bag-of-words features
cannot. `PLAN.md` kept this as one bounded experiment.

**Options.**

1. Local model only.
2. Cascade: local model for every message; for messages below the confidence threshold a
   budget LLM picks among the local model's top five intents; the policy gate reruns.
3. LLM for every message (rejected in the plan before measuring: per-message cost, an upstream
   dependency on the hot path, and a component that reads customer text and follows
   instructions).

**Constraint that mattered.** Adoption rule written before the run: on the low-confidence
slice, intent accuracy up at least 5 points, action accuracy not down, call p95 under 2 s.
Also: the experiment must not use dev rows for selection beyond this single comparison.

**What changed my view.** [llm-001], `gpt-4.1-mini-2025-04-14`, 150 rows, $0.014:

| low-confidence rows | local | with LLM |
|---|---|---|
| intent | 0.56 | 0.46 |
| action | 0.32 | 0.29 |

The LLM fixed 13 intents and broke 28. The right intent was among its five choices 75% of the
time, so the ceiling existed; it did not find it. p95 was 1.2 s. The hypothesis was wrong in
its premise: on these rows the deciding information is gone from the window, and a language
model cannot recover it from what remains any better than the training data's statistics.

**Chosen.** Option 1. No LLM in the service, no API key needed to run it.

**What would reverse it.** A context that keeps the conversation's opening turns (the
service only receives the last eight), or a measured gain of 5+ points from a different
budget model on a fresh sample. I did not try prompt variants: each would spend more dev rows
on selection, and the gap to the bar was 15 points.

## Where the work departed from PLAN.md

| Plan said | What happened | Why | Evidence |
|---|---|---|---|
| Logistic regression for the classifiers | Linear SVM with temperature-scaled scores | Logistic regression did not finish one fit in 10 minutes on this laptop | planning probe (reconstructed note) |
| Character n-grams for typo robustness | Kept, but they made action worse and the noisy gap wider | Measured; later blocks recover the loss; not removed because retraining is 19 min and the effect is small | ablate-001-wc |
| Noise augmentation helps the noisy slice | No measurable effect | Measured; kept only because it carries the `turn_index` dropout | dev-002-follow vs ablate-001-wcsx |
| Per-action prerequisite lists in the policy (`requires: offer-refund: [pull-up-account, ...]`) | One rule: high-consequence actions need at least one system turn in view | 83-97% of real high-consequence steps have a system turn in their window (make-purchase is lowest at 83%); per-action lists would have been written by me, not taken from the procedure, and a wrong list blocks correct refunds | data check, 2026-11-17 |
| Two flows' intents both high → route | Kept as planned | Those routed messages are 81% correct; kept because one action cannot serve two requests | dev-005-http |
| No rule for very short conversations | Added `little_context`: no agent turn yet → confidence capped, routed | The hostile pack showed a one-line message at 0.99 confidence; 62 of 20,000 training rows look like that | hostile-002, dev-004 |
| Clean Linux check in a Docker container | GitHub Actions Ubuntu runner | Docker Desktop would not start on this laptop (memory) | log, 2026-11-17 |
| Character-class tripwire only | Also flags customer text that imitates a system event | Found by the extended hostile pack | log, 2026-11-17 |

## Checks made on the outputs

Outputs verified directly rather than taken from a script's summary:

- The baseline rerun matches the published numbers to four decimals; the vendored reference
  files match the release manifest hashes (`scripts/check_reference.py`).
- The grader is the unmodified official file (its hash is in `reference/SHA256SUMS`); every
  accuracy number in this repository comes from its report or from `scripts/taxonomy.py`.
- HTTP and in-process evaluation give identical predictions [dev-003 vs dev-003-http].
- For the 70 policy conflicts in [dev-005-http], the held-back action was compared with the
  gold action (it matched in 21) and the gold action with the gold `permitted_actions`.
- Each of the nine published hostile answers was read, not only pass/fail counted; that is
  how the `hostile-004` confidence problem was found.
- The LLM experiment's 150 calls: token counts from the API's own usage field, priced at the
  MODELS.md rates; the fixed/broken counts recomputed from `calls.jsonl`.
