# What already exists, and what I used

One page. "Measured" means there is a run in `results/raw/` and an entry in
`EXPERIMENT_LOG.md`. "Not measured" means the decision rests on reading and reasoning only,
and says so.

## The task itself

**ABCD (Chen et al., NAACL 2021, "Action-Based Conversations Dataset").** The source of the
data and of `guidelines.json`. The paper defines Action State Tracking (predict the next
action from the dialogue so far) and Cascading Dialogue Success. This problem is close to AST
with the slot values removed. The paper's AST models are fine-tuned BERT/RoBERTa-sized
encoders with access to the full dialogue, so their numbers are not comparable to an 8-turn
window, but they tell me two things I used: the agent's own turns and the system's action
turns carry most of the next-step signal, and intent confusion is concentrated inside flows.
**Adopted** the framing (read speaker roles and system turns separately). **Did not adopt**
the models (next section).

**Published lexical baseline (`reference/baseline.py`).** Rerun unchanged as `baseline-001`;
it is the comparison point for every number in this repository.

## Classifiers

| Option | Decision | Evidence |
|---|---|---|
| TF-IDF + linear model (scikit-learn `LinearSVC`) | **Adopted.** Trains in minutes on CPU, serves in a few milliseconds, every feature group can be ablated | Measured: `ablate-001-*`, `train-001` |
| Logistic regression for the same features | Rejected for training cost: did not finish one fit in 10 minutes with 96 classes and 100k features on this laptop. Still used for the small confidence model | Measured once, stopped (planning probe, reconstructed note in the log) |
| Character n-grams for typo robustness (common advice) | Kept with doubts: it widened the noisy gap in the ablation | Measured: `ablate-001-wc` |
| Fine-tuned small encoder (MiniLM, DistilBERT) | Not built. Would add a ~100 MB artefact, a torch dependency and slower CPU serving for a gain I could not size in the time. Listed as the next experiment | Not measured |
| Sentence embeddings + nearest neighbours (hosted or local) | Not built. An embedding of the whole window blurs who said what and in which order, which the ablation shows is where much of the action signal is | Not measured; reasoning from `ablate-001-wcs` vs `-wc` |
| Hosted classifier APIs (zero-shot intent services) | Rejected: per-message cost and an upstream dependency for a 96-way label set they were not trained on | Not measured |
| Budget LLM as the classifier | Rejected; see below | Measured on a sample as a re-ranker [llm-001] |

## Policy and guardrails

| Option | Decision | Why |
|---|---|---|
| Policy as prompt text | Rejected | Cannot be tested as an invariant, and puts the rules where customer text can argue with them |
| Policy as a YAML table enforced in code after the model | **Adopted** | The permitted set depends only on the flow, so the whole written procedure fits in one readable file. Tested by editing it (`tests/test_policy_change.py`) |
| Guardrail frameworks (NeMo Guardrails, Guardrails AI, LLM-based injection classifiers such as Llama Guard or Prompt Guard) | Not used | They protect a model that follows instructions. This service has none in its decision path, so there is nothing for them to protect. A regex tripwire is kept only to route and count |
| JSON Schema validation library (`jsonschema`) | Not used | The response contract is five fields; a 20-line check that mirrors the official grader's own check is easier to audit and removes a dependency |

## Confidence

| Option | Decision | Evidence |
|---|---|---|
| Top-class probability or margin | Comparison point; it scores as well on the ratio, but is not a probability | Measured: 0.2735 on `ablate-001-wcsx` vs 0.2821 shipped |
| Temperature scaling (Guo et al., 2017) | **Adopted** to turn SVM scores into probabilities | Fitted on out-of-fold scores |
| A second model that predicts "is the final answer right" from scores and flags (a correctness predictor, as in selective classification) | **Adopted** | Measured in `train-001` out-of-fold and on dev |
| Conformal prediction sets | Not used. It gives sets with coverage guarantees; the contract wants one action and one number, and exchangeability fails on the noisy slice anyway | Not measured |
| The LLM's own stated confidence | Rejected | The problem statement warns against it; self-reported scores from small models cluster high |

## LLM (budget class)

Kept to one bounded experiment on the rows the local model is least sure about, with an
adoption rule fixed before the run (`DECISIONS.md`, decision 2). **Measured and rejected**
[llm-001]: `gpt-4.1-mini-2025-04-14` (pinned in MODELS.md, $0.40 / $1.60 per million tokens)
picking among the local model's top five intents on 150 low-confidence rows took intent
accuracy from 0.56 to 0.46, at p95 1.2 s and $0.014 in total. Not used by the service.

Not tried: `gpt-5-mini` (pinned; its reasoning tokens are billed as output, so even a one-number
answer costs more and takes longer), Claude Haiku and Gemini Flash, and open-weight models served
locally. With the slice's deciding information gone from the window, I expected none to
clear +5 points, and each try spends dev rows on selection.

## Serving

Starlette + uvicorn (small, async, no framework-level request validation that would turn a
bad envelope into a framework error page). FastAPI was the obvious alternative; rejected
because its automatic validation answers bad input with its own 422 shape, which is not the
contract's abstention shape, and turning that off removes most of what it adds.
