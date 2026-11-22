// The manager's rulebook. Each switch rewrites the rule table the gate reads; the model
// itself never changes. Every answer on the page (hero, game, storm) follows at once.
import { runAll, sfx } from "./main.js?v=12";

export function rulebook(world) {
  const m = world.mentat;
  const shipped = JSON.parse(JSON.stringify(m.policyTable));
  const state = { refunds: false, promo: false, system: true, human: true };
  const out = {
    changed: document.getElementById("re-changed"), person: document.getElementById("re-person"),
    viol: document.getElementById("re-viol"), refunds: document.getElementById("re-refunds"),
    note: document.getElementById("re-note"),
  };
  let first = null;     // results under the shipped rules, the reference for "changed"

  function table() {
    const t = JSON.parse(JSON.stringify(shipped));
    for (const f of Object.keys(t.permitted)) {
      t.permitted[f] = t.permitted[f].filter((a) =>
        !(state.refunds && a === "offer-refund") && !(state.promo && a === "promo-code"));
    }
    t.require_system_turn = state.system;
    t.on_conflict = state.human ? "route_to_human" : "follow_label";
    const edits = Object.entries(state).filter(([k, v]) => v !== { refunds: false, promo: false, system: true, human: true }[k]).map(([k]) => k);
    t.version = edits.length ? `${shipped.version}+${edits.join("+")}` : shipped.version;
    return t;
  }

  function report() {
    if (!world.results) return;
    const R = world.results, C = world.convos;
    if (!first) first = R.map((r) => r.action + "|" + r.needs_human);
    let changed = 0, person = 0, viol = 0, refunds = 0;
    R.forEach((r, i) => {
      if (r.action + "|" + r.needs_human !== first[i]) changed++;
      if (r.needs_human) person++;
      if (r.action === "offer-refund") refunds++;
      // a step outside the written procedure for this conversation's true problem, as the
      // benchmark's scoring script counts it (the row's own permitted list)
      if (r.action !== "none" && C[i].permitted && !C[i].permitted.includes(r.action)) viol++;
    });
    out.changed.textContent = String(changed);
    out.person.textContent = `${person} (${Math.round((person / R.length) * 100)}%)`;
    out.viol.textContent = `${viol} (${((viol / R.length) * 100).toFixed(1)}%)`;
    out.refunds.textContent = String(refunds);
    out.note.textContent = changed ? `Rule table version ${m.policyTable.version}. The model weights are the same; only the table changed.`
      : "These are the shipped rules. Flip one.";
  }

  document.querySelectorAll("#rules .rule").forEach((b) => b.addEventListener("click", async () => {
    const k = b.dataset.rule;
    state[k] = !state[k];
    b.setAttribute("aria-pressed", String(state[k]));
    sfx("switch");
    m.setPolicy(table());
    if (!world.convos) { out.note.textContent = "Still loading the conversations…"; return; }
    out.note.textContent = "Re-running 2,300 conversations…";
    await runAll("rules");
  }));
  world.on(report);
}
