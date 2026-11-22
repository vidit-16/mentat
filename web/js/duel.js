// Duel the Mentat. Ten real development conversations; you and the model each pick the next
// step. The wrong options are steps the procedure allows for that conversation, chosen from
// the ones the model itself found likely, so they are plausible rather than silly.
import { nice, sfx } from "./main.js?v=12";

const SURE = [["Guessing", 0.4], ["Fairly sure", 0.7], ["Certain", 0.95]];
const shuffle = (a) => { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

export function duel(world) {
  const arena = document.getElementById("arena");
  const start = document.getElementById("duel-start");
  const note = document.getElementById("duel-note");
  const m = world.mentat;
  start.disabled = false;
  note.textContent = "Ten conversations, about three minutes.";
  const peek = document.getElementById("duel-peek");
  const sample = pickTen()[0];
  if (peek && sample) peek.innerHTML = sample.context.slice(-6).map((x) => `<div class="line ${x.speaker === "action" ? "sys" : ""}"><span class="who">${x.speaker === "action" ? "system" : x.speaker}</span><span class="txt">${esc(x.text)}</span></div>`).join("");
  start.addEventListener("click", play);

  function pickTen() {
    const pool = world.convos.filter((c) => !c.noise && c.context.length >= 4 && c.permitted && c.permitted.length >= 4
      && c.context.reduce((a, t) => a + t.text.length, 0) < 700);
    return shuffle([...pool]).slice(0, 10);
  }

  async function play() {
    sfx("tick");
    const rounds = pickTen();
    const log = [];
    for (let q = 0; q < rounds.length; q++) log.push(await ask(rounds[q], q, rounds.length));
    score(log);
  }

  function ask(c, q, n) {
    return new Promise((done) => {
      const obj = { id: c.id, context: c.context, turn_index: c.turn_index };
      const t0 = performance.now();
      const t = m.trace(obj);
      const mMs = performance.now() - t0;
      const r = t.response;
      const acts = m.model.classes.action, pa = t.probs ? t.probs.action : [];
      const likely = pa.map((p, i) => [acts[i], p]).sort((a, b) => b[1] - a[1]).map(([a]) => a)
        .filter((a) => a !== c.action && c.permitted.includes(a));
      const rest = shuffle(c.permitted.filter((a) => a !== c.action && !likely.includes(a)));
      const options = shuffle([c.action, ...[...likely, ...rest].slice(0, 3)]);

      arena.innerHTML = `
        <div class="duel-top"><span>Conversation <b>${q + 1}</b> of ${n}</span><span>${esc(c.id)}</span></div>
        <div class="duel-grid">
          <div class="log">${c.context.slice(-8).map((x) => `<div class="line ${x.speaker === "action" ? "sys" : ""}"><span class="who">${x.speaker === "action" ? "system" : x.speaker}</span><span class="txt">${esc(x.text)}</span></div>`).join("")}</div>
          <div>
            <p class="duel-q">What should the agent do next?</p>
            <div class="opts">${options.map((a) => `<button class="opt" data-a="${esc(a)}" aria-pressed="false">${esc(nice(a))}</button>`).join("")}</div>
            <div class="sure" hidden><span>How sure are you?</span>${SURE.map(([l, v]) => `<button data-v="${v}">${l}</button>`).join("")}</div>
            <p class="duel-reveal" aria-live="polite"></p>
          </div>
        </div>`;
      const started = performance.now();
      let choice = null, yourMs = 0;
      arena.querySelectorAll(".opt").forEach((b) => b.addEventListener("click", () => {
        if (arena.querySelector(".opt.right")) return;
        choice = b.dataset.a; yourMs = performance.now() - started;
        arena.querySelectorAll(".opt").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        arena.querySelector(".sure").hidden = false;
        sfx("tick");
      }));
      arena.querySelectorAll(".sure button").forEach((b) => b.addEventListener("click", () => {
        if (!choice || arena.querySelector(".opt.right")) return;
        const sure = +b.dataset.v;
        const youRight = choice === c.action, mRight = r.action === c.action;
        arena.querySelectorAll(".opt").forEach((x) => {
          const a = x.dataset.a;
          if (a === c.action) x.classList.add("right");
          else if (a === choice) x.classList.add("wrong");
          if (a === r.action) x.insertAdjacentHTML("beforeend", `<span class="tag">Mentat · ${r.confidence.toFixed(2)} sure</span>`);
        });
        if (!options.includes(r.action)) arena.querySelector(".opts").insertAdjacentHTML("beforeend", `<p class="arena-note">Mentat picked <b>${esc(nice(r.action))}</b>, which isn't one of the four.</p>`);
        sfx(youRight ? "pass" : "held");
        arena.querySelector(".sure").hidden = true;
        arena.querySelector(".duel-reveal").innerHTML =
          `You: <b>${youRight ? "right" : "wrong"}</b> in ${(yourMs / 1000).toFixed(1)} s. ` +
          `Mentat: <b>${mRight ? "right" : "wrong"}</b> in ${mMs.toFixed(1)} ms${r.needs_human ? ", and it would have asked a person" : ""}.` +
          `<br><button class="go" type="button" style="margin-top:14px">${q + 1 < n ? "Next" : "See the result"}</button>`;
        arena.querySelector(".duel-reveal .go").addEventListener("click", () => done({ youRight, mRight, sure, yourMs, mMs, mConf: r.confidence, mHuman: r.needs_human }));
      }));
    });
  }

  function score(log) {
    const n = log.length;
    const you = log.filter((x) => x.youRight).length, them = log.filter((x) => x.mRight).length;
    const certain = log.filter((x) => x.sure >= 0.9), certainRight = certain.filter((x) => x.youRight).length;
    const mSure = log.filter((x) => x.mConf >= 0.9), mSureRight = mSure.filter((x) => x.mRight).length;
    const avgYou = log.reduce((a, x) => a + x.yourMs, 0) / n / 1000, avgM = log.reduce((a, x) => a + x.mMs, 0) / n;
    const verdict = you > them ? "You beat the Mentat." : you === them ? "A draw." : "The Mentat wins.";
    arena.innerHTML = `
      <div class="score">
        <div class="you"><h3>You</h3><p class="big-n">${you}/${n}</p>
          <dl><div><dt>average time</dt><dd>${avgYou.toFixed(1)} s</dd></div>
          <div><dt>when you said certain</dt><dd>${certain.length ? `${certainRight} of ${certain.length} right` : "never said it"}</dd></div></dl></div>
        <div class="them"><h3>Mentat</h3><p class="big-n">${them}/${n}</p>
          <dl><div><dt>average time</dt><dd>${avgM.toFixed(1)} ms</dd></div>
          <div><dt>when it was over 0.9 sure</dt><dd>${mSure.length ? `${mSureRight} of ${mSure.length} right` : "never"}</dd></div></dl></div>
        <p class="score-line">${verdict} On all 2,300 development conversations it picks the right next step 82% of the time, and when it is not sure it asks a person.</p>
      </div>
      <button class="go" type="button" style="margin-top:22px">Play again</button>`;
    sfx(you > them ? "pass" : "person");
    arena.querySelector(".go").addEventListener("click", play);
  }
}
