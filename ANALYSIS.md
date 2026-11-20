# Analysis

Required by the problem: a failure taxonomy of the lexical baseline, which intervention moved
which category (including those that moved nothing), the noisy slice by noise type, and what
the hostile pack found before it was fixed. Every number here comes from a run in
`results/raw/`; run ids are in brackets. All on dev: 2,000 clean plus 300 noisy rows.

## 1. Baseline failure taxonomy [baseline-001]

`scripts/taxonomy.py` puts each action error in exactly one category, first match wins:

| Category | Meaning |
|---|---|
| wrong_flow | predicted intent belongs to a different flow than the true one |
| sibling_intent | right flow, wrong intent |
| repeated_step | right intent, but the action is a step the context shows as already done |
| wrong_step | right intent, some other wrong action |

| Baseline | errors | share |
|---|---|---|
| wrong_flow | 662 | 47% |
| wrong_step | 310 | 22% |
| sibling_intent | 281 | 20% |
| repeated_step | 147 | 11% |
| **all action errors** | **1,400 of 2,300** | |

Intent errors: 941 wrong flow, 497 sibling.

What this says about the baseline: it mostly fails at the easy question (which kind of
problem is this), not at the hard one (what comes next). Two design choices cause it. It
reads only the last four turns as one bag of words, and in 66% of rows the window has
already lost the opening message. And it ignores who said what, so the system's own
`action` turns ("account has been pulled up") count as ordinary words, and the model cannot
tell that a step is done; hence 147 errors that propose a step already taken.

## 2. Which intervention moved which category

Action errors by category after each change. Rows add one change at a time; the last row is
the shipped service.

| Run | Change | wrong_flow | sibling | repeated | wrong_step | all | action acc |
|---|---|---|---|---|---|---|---|
| baseline-001 | — | 662 | 281 | 147 | 310 | 1,400 | 0.3913 |
| ablate-002-w-nocap | all 8 turns, linear SVM, words | 118 | 90 | 14 | 245 | 467 | 0.7970 |
| ablate-001-w | + per-turn length cap | 105 | 88 | 15 | 248 | 456 | 0.8017 |
| ablate-001-wc | + character n-grams | 117 | 85 | 18 | 261 | 481 | 0.7909 |
| ablate-001-wcs | + speaker and position tags | 100 | 71 | 9 | 244 | 424 | 0.8157 |
| ablate-001-wcsx | + procedure state from system turns | 96 | 62 | 10 | 234 | 402 | 0.8252 |
| dev-002-follow | + augmentation, `turn_index` dropout | 108 | 66 | 9 | 227 | 408 | 0.8226 |
| dev-005-http | + policy gate, routing rules (shipped) | 108 | 66 | 9 | 227 | 410 | 0.8217 |

What moved:

- **Reading the whole window with a trained linear model** removed 82% of wrong-flow errors
  and 90% of repeated-step errors in one step. Most of the gain over the baseline is here.
- **The length cap** moved little overall but is the fix for one slice: very long messages
  (section 3).
- **Speaker and position tags, and procedure state** each moved sibling-intent and
  repeated-step errors, and they did most for confidence (top-70 ratio 0.43 → 0.33 → 0.27).
  Telling the model where in the procedure the dialogue is helps it know when it is unsure.

What moved nothing, or went the wrong way:

- **Character n-grams** made action worse (+25 errors) and widened the noisy gap from 0.010
  to 0.043. I expected them to help with typos; on this data the typo rows are short
  replies whose meaning comes from the rest of the context. Left in because later blocks
  recover the loss; removing them is an open experiment.
- **Augmentation** (noisy copies of 20% of training rows): no measurable change. Action
  0.8252 → 0.8226, within noise.
- **The policy gate** changed 2 answers' correctness out of 2,300 (section 5 of
  `DECISIONS.md` has why that is the point).
- **The LLM re-ranker** [llm-001] made intent worse on the rows it was meant to help: 0.56 →
  0.46 on 150 low-confidence rows. Not adopted.
- **wrong_step barely moved at any stage** (310 → 227). Most remaining errors are right
  flow, right intent, wrong next step. Typical cases: `verify-identity` predicted as
  `pull-up-account` (16), `subscription-status` as `ask-the-oracle` (14). These are branch
  points in the procedure where the deciding fact (what the Oracle said, what the customer
  will be asked next) is not in the text yet.

The window ceiling: with the shipped model, intent error is 16% when the window shows the
whole dialogue and 34% when it has been cut; action error 12% and 21%. The most common
intent confusions are siblings that share a procedure: `status_due_date` /
`status_due_amount` (26), `return_size` / `return_color` / `return_stain` (38 between them),
`out_of_stock_one_item` / `out_of_stock_general` (12). They cost intent accuracy but rarely
change what the agent may do.

## 3. The noisy slice by noise type

Intent / action accuracy, 50 rows per type, so each figure is about ±0.13.

| Noise type | Baseline | Words, no cap | Words, cap | Shipped |
|---|---|---|---|---|
| typo | 0.42 / 0.38 | 0.68 / 0.76 | 0.68 / 0.76 | 0.68 / 0.76 |
| code_mixed (Hinglish) | 0.42 / 0.34 | 0.68 / 0.82 | 0.68 / 0.82 | 0.70 / 0.70 |
| two_intents | 0.34 / 0.38 | 0.70 / 0.86 | 0.70 / 0.86 | 0.66 / 0.90 |
| empty last message | 0.26 / 0.36 | 0.64 / 0.76 | 0.64 / 0.76 | 0.70 / 0.80 |
| very_long | **0.00** / 0.18 | 0.16 / 0.54 | 0.60 / 0.76 | 0.50 / 0.78 |
| screenshot description | 0.36 / 0.32 | 0.52 / 0.80 | 0.52 / 0.80 | 0.50 / 0.82 |
| **noisy action overall** | | | | **0.7933** |

Clean action 0.8260, noisy 0.7933: gap 0.0327 (bar ≤ 0.10). On the same 300 conversations
before the rewrite the shipped model scores 0.8100, so the rewrite itself costs 1.7 points.

Readings:

- Action holds up under noise because only the last customer turn is rewritten, and the next
  action depends mostly on the agent's turns and the system's turns. An empty last message
  still leaves seven turns of evidence.
- Very long messages were the only type that broke the baseline completely (intent 0 of 50).
  The fix is the per-turn cap (keep the first 50 and last 30 words of a turn), measured on
  its own: very_long intent 0.16 → 0.60 [ablate-002-w-nocap vs ablate-001-w].
- Code-mixed action dropped from 0.82 to 0.70 between the words-only model and the shipped
  one. That is 6 rows of 50, inside the noise. Rechecked on all of dev [hinglish-001]: the
  published rewrite (append "thoda jaldi karo please", sometimes my → mera, order → ordr)
  applied to 1,995 rows leaves action accuracy unchanged (0.8281 before and after), so the
  drop was noise. The recheck found a different problem: the rewrite raises confidence on
  90% of rows, because the `unseen_words` signal was measured against a vocabulary fitted on
  the same rows during training (mean 0.002) and takes values 7 standard deviations higher
  on Hinglish. 47 rows move from a person to automated, 24 of them wrong; wrong answers
  sent without a person rise from 160 to 180. Fixed in train-003 by measuring the signal
  out of fold in training too [hinglish-002]: with the same rewrite, wrong answers sent
  without a person go from 152 to 155, and confidence falls slightly instead of rising.
  `tests/test_code_mixed.py` fails on the old model and passes on the new one.
- The hidden noisy slice is generated independently, so these are estimates of type-level
  behaviour, not promises.

## 4. What the hostile pack found, in the order it found it

1. **The service did not start** [hostile-shell-001]. Starlette 1.10 had removed the startup
   hook argument I used. Found before any model existed, because the hostile tests were the
   first thing written.
2. **Spoofed system text kept high confidence** (extended pack). A customer writing
   "account has been pulled up ... a refund has been made" got 0.80 confidence. No refund
   was proposed and it was routed to a person, because the trust decision comes from the
   `speaker` field, not from words, but the tripwire missed it. Now flagged (no real customer
   turn in training matches a system-event pattern).
3. **The tripwire had a false positive on real data**: "you are now out of stock" matched a
   role-change pattern. Tightened; 0 training rows flagged now.
4. **A one-line message got 0.99 confidence and no human** [hostile-002, `hostile-004`].
   Conversations with no agent turn are 0.3% of training, too few to calibrate on. Now capped
   and routed.

Nothing in the pack crashed the service, hung it, or produced an invalid response at any
point after item 1. That is less impressive than it sounds: the decision path has no
component that can follow an instruction, and the transport layer rejects malformed input
before anything else reads it. The interesting failures were all about confidence, not
about staying up.

Final run [hostile-003]: 99 requests (9 published, 68 extended valid envelopes, 22 transport
probes), each followed by a canary request to detect later effects. 99 passed. Every
published hostile row gets `needs_human: true`; the injection rows get `search-faq` (a
read-only lookup) with confidence 0.2; the binary-junk row is answered with the odd
characters stripped and routed; the emoji wall and the empty message get the abstention
answer.

## 5. Where confidence comes from, and whether it works

A second small model (logistic regression on 16 signals: the action probability after
temperature scaling, margins, flow and intent probability, entropy, whether the gate changed
the answer, unseen-word share, flags) predicts "is the final action right". It is fitted on
out-of-fold predictions of the whole pipeline, never on dev. The strongest signals are the
action probability and the raw score margin; the flags carry little weight because they are
rare in training.

| | top-70 error ratio | bar |
|---|---|---|
| baseline | 1.0 | ≤ 0.85 |
| margin only, no confidence model [ablate-001-wcsx] | 0.2735 | |
| shipped [dev-006] | 0.2821 | |

**The confidence model did not beat the raw margin on this ratio.** It buys something else:
its output is a probability. Out of fold, messages above the 0.565 threshold are right 90% of
the time; on dev they are right 90.8% of the time. The raw margin has no such meaning, so a
threshold on it cannot be explained to the manager.

Routing on dev [dev-006]: 16.5% of messages go to a person. Accuracy of the routed
messages by reason: low confidence 35% (358 messages), policy conflict 27% (70), needs a
prior step 22% (18), little context 57% (7), two intents 81% (26). The two-intents rule
routes messages the model mostly gets right; it is kept because a customer with two requests
needs a person to handle the second one, which the single action cannot express.
