// Port of the gate in src/triage/policy.py. Reads only probabilities and the table.
export const NONE_ACTION = "none";

const argmax = (a) => { let b = 0; for (let i = 1; i < a.length; i++) if (a[i] > a[b]) b = i; return b; };

// Build the index tables for the model's class order. `table` is web/model/policy.json, or
// an edited copy of it.
export function bindPolicy(table, classes) {
  const { intent: intents, flow: flows, action: actions } = classes;
  const flowIdx = new Map(flows.map((f, i) => [f, i]));
  const permitted = new Map(Object.entries(table.permitted).map(([f, a]) => [f, new Set(a)]));
  const hcSet = new Set(table.high_consequence);
  return {
    table, intents, flows, actions, permitted,
    flowOf: table.flow_of,
    mode: table.on_conflict,
    requireSystemTurn: table.require_system_turn,
    intentFlow: intents.map((i) => (table.flow_of[i] !== undefined && flowIdx.has(table.flow_of[i]) ? flowIdx.get(table.flow_of[i]) : -1)),
    mask: new Map(flows.map((f) => [f, actions.map((a) => (permitted.get(f) || new Set()).has(a))])),
    hc: actions.map((a) => hcSet.has(a)),
  };
}

export function decide(P, pIntent, pFlow, pAction, hasSystemTurn, topFlows = 3, mode = null) {
  mode = mode || P.mode;
  const fromIntent = new Array(P.flows.length).fill(0);
  P.intentFlow.forEach((fi, i) => { if (fi >= 0) fromIntent[fi] += pIntent[i]; });
  let flowScore = pFlow.map((p, i) => Math.sqrt(p * fromIntent[i] + 1e-12));
  const sum = flowScore.reduce((a, b) => a + b, 0);
  flowScore = flowScore.map((v) => v / sum);

  const order = flowScore.map((v, i) => i).sort((a, b) => flowScore[b] - flowScore[a]).slice(0, topFlows);
  let best = null;
  const considered = [];
  for (const fi of order) {
    const flow = P.flows[fi];
    if (!P.permitted.has(flow)) continue;
    const allowed = P.mask.get(flow);
    const usable = (hasSystemTurn || !P.requireSystemTurn) ? allowed : allowed.map((a, k) => a && !P.hc[k]);
    let ai = -1, joint;
    if (usable.some(Boolean)) {
      ai = argmax(pAction.map((p, k) => (usable[k] ? p : -1)));
      joint = flowScore[fi] * pAction[ai];
    } else {
      joint = flowScore[fi] * 1e-6;
    }
    considered.push({ flow, score: flowScore[fi], action: ai >= 0 ? P.actions[ai] : NONE_ACTION, joint, usable });
    if (best === null || joint > best.joint) best = { joint, fi, ai, allowed };
  }
  const rawAi = argmax(pAction);
  const rawAction = P.actions[rawAi];
  if (best === null) {
    const ii = argmax(pIntent);
    return { intent: P.intents[ii], flow: "unknown", action: NONE_ACTION, p_action: 0, p_flow: 0,
             p_intent: pIntent[ii], conflict: rawAction, blocked: null, flowScore, considered };
  }
  const { fi, ai, allowed } = best;
  const inFlow = P.intentFlow.map((f) => f === fi);
  const ii = inFlow.some(Boolean) ? argmax(pIntent.map((p, k) => (inFlow[k] ? p : -1))) : argmax(pIntent);
  const d = { intent: P.intents[ii], flow: P.flows[fi], action: NONE_ACTION, p_action: 0,
              p_flow: flowScore[fi], p_intent: pIntent[ii], conflict: null, blocked: null,
              flowScore, considered };
  if (ai >= 0) { d.action = P.actions[ai]; d.p_action = pAction[ai]; }
  if (!allowed[rawAi]) {
    d.conflict = rawAction;
    if (mode === "follow_label") { d.action = rawAction; d.p_action = pAction[rawAi]; }
  } else if (ai !== rawAi && P.hc[rawAi]) {
    d.blocked = rawAction;
  }
  return d;
}
