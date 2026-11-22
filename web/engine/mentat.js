// The whole pipeline: port of src/triage/pipeline.py, confidence.py, envelope.py and
// respond.py. `handle` returns the same response the Python service returns; `trace` also
// returns every intermediate step, for the site to show.
import { cleanContext, SPEAKERS, MAX_TURNS } from "./text.js?v=12";
import { extract, transform } from "./features.js?v=12";
import { loadModel, scores, probabilities } from "./model.js?v=12";
import { bindPolicy, decide, NONE_ACTION } from "./policy.js?v=12";

const SECOND_INTENT_MIN = 0.20;
const SECOND_INTENT_RATIO = 0.50;

export const FEATURES = [
  "p_action", "p_margin", "score_margin", "p_flow", "p_intent", "entropy",
  "conflict", "blocked", "unseen_words", "n_turns", "has_system_turn",
  "truncated", "empty_last_customer", "odd_characters", "action_prior", "log_tokens",
];

function signals(d, pAction, actionScores, unseen, nTurns, nTokens, hasSys, flags, prior) {
  const top = [...pAction].sort((a, b) => b - a);
  const raw = [...actionScores].sort((a, b) => b - a);
  let entropy = 0;
  for (const p of pAction) entropy -= p * Math.log(p + 1e-12);
  return [
    d.p_action,
    top.length > 1 ? top[0] - top[1] : 1.0,
    raw.length > 1 ? raw[0] - raw[1] : 0.0,
    d.p_flow, d.p_intent, entropy,
    d.conflict ? 1 : 0, d.blocked ? 1 : 0,
    unseen, nTurns / 8, hasSys ? 1 : 0,
    flags.truncated ? 1 : 0, flags.empty_last_customer ? 1 : 0,
    (flags.had_control || flags.had_format) ? 1 : 0,
    prior[d.action] ?? 0.5,
    Math.log1p(nTokens) / 5,
  ];
}

function estimate(c, x) {
  let z = c.intercept;
  const parts = x.map((v, i) => ((v - c.mean[i]) / c.scale[i]) * c.coef[i]);
  for (const p of parts) z += p;
  z = Math.max(-30, Math.min(30, z));
  return { p: 1 / (1 + Math.exp(-z)), parts };
}

const round6 = (v) => Math.round(Math.min(1, Math.max(0, v)) * 1e6) / 1e6;

function abstain(id, message, extra = {}) {
  return { id, intent: "unknown", action: NONE_ACTION, confidence: 0.0, needs_human: true,
           error: { code: "invalid_input", message }, ...extra };
}

function checkContext(obj) {
  const context = obj.context;
  if (!Array.isArray(context)) return [null, "context must be a list of turns", false];
  const turns = [];
  for (const item of context) {
    if (item === null || typeof item !== "object" || Array.isArray(item)) return [null, "each turn must be an object", false];
    if (!SPEAKERS.includes(item.speaker)) return [null, "speaker must be customer, agent or action", false];
    if (typeof item.text !== "string") return [null, "text must be a string", false];
    turns.push({ speaker: item.speaker, text: item.text });
  }
  return [turns.slice(-MAX_TURNS), null, turns.length > MAX_TURNS];
}

function turnIndex(obj) {
  const v = obj.turn_index;
  if (typeof v !== "number" || !Number.isInteger(v) || v < 0) return null;
  return Math.min(v, 10000);
}

export class Mentat {
  constructor(model, policyTable = null) {
    this.model = model;
    this.conf = model.confidence;
    this.setPolicy(policyTable || model.policy);
  }

  static async load(read) { return new Mentat(await loadModel(read)); }

  // Swap the rule table, e.g. after the manager edits it on the page.
  setPolicy(table) {
    this.policyTable = table;
    this.policy = bindPolicy(table, this.model.classes);
  }

  handle(obj) { return this.trace(obj).response; }

  trace(obj) {
    const t = this.traceInner(obj);
    t.response.versions = { model: this.model.version, policy: this.policyTable.version };
    return t;
  }

  traceInner(obj) {
    const id = obj.id;
    const [context, problem, wasCut] = checkContext(obj);
    if (problem) return { response: abstain(id, problem) };
    const cleaned = cleanContext(context);
    const flags = { ...cleaned.flags };
    if (wasCut) flags.too_many_turns = true;
    const active = Object.keys(flags).filter((k) => flags[k]).sort();
    if (!cleaned.usable) return { cleaned, response: abstain(id, "no readable text in the conversation", { flags: active }) };

    const m = this.model;
    const turns = cleaned.turns;
    const hasSys = turns.some((t) => t.speaker === "action" && t.text);
    const feats = extract(turns, turnIndex(obj), m.blocks);
    const vec = transform(m, feats);
    const sc = scores(m, vec.idx, vec.val);
    const probs = probabilities(m, sc);
    const d = decide(this.policy, probs.intent, probs.flow, probs.action, hasSys);

    const nTokens = turns.reduce((a, t) => a + t.tokens.length, 0);
    const x = signals(d, probs.action, sc.action, vec.unseen, turns.length, nTokens, hasSys, flags, this.conf.action_prior);
    const est = estimate(this.conf, x);
    let confidence = est.p;
    const caps = this.conf.caps || {};
    const reasons = [];
    if (d.action === NONE_ACTION) { confidence = 0; reasons.push("nothing_permitted"); }
    if (d.conflict) { confidence = Math.min(confidence, caps.conflict ?? 1); reasons.push("policy_conflict"); }
    if (d.blocked) reasons.push("needs_prior_step");
    if (flags.injection_pattern) { confidence = Math.min(confidence, caps.injection ?? 0.2); reasons.push("injection_pattern"); }
    if (!turns.some((t) => t.speaker === "agent" && t.text)) {
      confidence = Math.min(confidence, caps.little_context ?? 0.5); reasons.push("little_context");
    }
    if (flags.had_control) { confidence = Math.min(confidence, caps.odd_characters ?? 0.5); reasons.push("odd_characters"); }
    const second = this.secondIntent(probs.intent, d);
    if (second) reasons.push("two_intents");
    if (confidence < this.conf.threshold) reasons.push("low_confidence");

    const response = { id, intent: d.intent, action: d.action, confidence: round6(confidence),
                       needs_human: reasons.length > 0, flow: d.flow, flags: active, human_reasons: reasons };
    if (d.conflict) response.policy_conflict = { suppressed_action: d.conflict };
    if (d.blocked) response.held_back = { action: d.blocked, reason: "no system step in view" };
    if (second) response.secondary_intent = second;
    return { cleaned, feats, vec, scores: sc, probs, decision: d, signals: x,
             confidenceParts: est.parts, rawConfidence: est.p, threshold: this.conf.threshold, response };
  }

  secondIntent(pIntent, d) {
    const order = pIntent.map((p, i) => i).sort((a, b) => pIntent[b] - pIntent[a]);
    const top = pIntent[order[0]];
    for (const i of order.slice(1, 4)) {
      const other = this.model.classes.intent[i];
      if (this.policy.flowOf[other] !== d.flow) {
        const p = pIntent[i];
        return p >= SECOND_INTENT_MIN && p >= SECOND_INTENT_RATIO * top ? other : null;
      }
    }
    return null;
  }
}
