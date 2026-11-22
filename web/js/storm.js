// 2,300 real conversations as sand. Above the ground: answered by Mentat alone, piled by
// confidence. Below: the queue a person works through. Drag the blue handle and grains hop
// between the two. Orange grains are wrong answers that went out unchecked. Click a grain to
// read the conversation it stands for.
import { nice, sfx, reduced, runAll, evaluate, dragWind } from "./main.js?v=12";

const BINS = 90;
const SAND = ["#e2c189", "#d7b47a", "#ecd2a3"];

export function storm(world) {
  const data = world.data;
  const stage = document.getElementById("storm-stage");
  const canvas = document.getElementById("storm-canvas");
  const cut = document.getElementById("cut");
  const reader = document.getElementById("reader");
  const ctx = canvas.getContext("2d");
  cut.value = String(data.routing.threshold);
  let who = "mentat";
  let W = 0, H = 0, ground = 0, pad = 0, d = 3, binW = 0;
  const n = data.routing.mentat.length;
  const grains = Array.from({ length: n }, (_, i) => ({ i, x: 0, y: 0, tx: 0, ty: 0, vx: 0, vy: 0, live: false, born: 0, side: 0 }));
  let pick = -1, lastMoved = 0;

  // [confidence, right?, sent to a person for a reason other than confidence?] for the current
  // view: Mentat (live, with the current rules) or the baseline. A held-back refund, a flagged
  // injection, a forbidden step or two requests send a conversation to a person whatever the
  // line says, so those grains always sit in the queue. With the line at the shipped value the
  // queue is exactly Mentat's own needs_human, the number the rulebook and time machine show.
  function rows() {
    if (who === "baseline") return data.routing.baseline.map(([c, ok]) => [c, ok, 0]);
    if (world.results && world.convos) return world.results.map((r, i) => [
      r.confidence, r.action === world.convos[i].action ? 1 : 0,
      (r.human_reasons || []).some((x) => x !== "low_confidence") ? 1 : 0]);
    return data.routing.mentat.map(([c, ok]) => [c, ok, 0]);
  }
  const queued = (row, th) => row[0] < th || row[2] === 1;

  function size() {
    const dpr = Math.min(2, devicePixelRatio || 1);
    W = stage.clientWidth; H = stage.clientHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    pad = Math.max(16, Math.min(52, W * 0.034));
    ground = H * 0.62;
  }

  function layout(kick) {
    const th = +cut.value, R = rows();
    const bins = Array.from({ length: BINS }, () => []);
    const queue = [];
    let moved = 0;
    R.forEach((row, i) => {
      const q = queued(row, th);
      if (grains[i].live && (q ? 1 : -1) !== -grains[i].side) moved++;
      (q ? queue : bins[Math.min(BINS - 1, Math.floor(row[0] * BINS))]).push(i);
    });
    lastMoved = moved;
    binW = (W - pad * 2) / BINS;
    const xLine = pad + th * (W - pad * 2);
    const most = Math.max(1, ...bins.map((b) => b.length));
    d = 3.4;
    while (d > 1.3 && Math.ceil(most / Math.max(1, Math.floor(binW / d))) * d > (ground - H * 0.18) * 0.95) d -= 0.1;
    const cols = Math.max(1, Math.floor(binW / d));
    bins.forEach((b, k) => {
      b.sort((a, z) => R[z][1] - R[a][1]);       // wrong ones on top, where they can be seen
      b.forEach((idx, j) => {
        const g = grains[idx];
        const side = 1;
        if (kick && g.live && g.side !== side) { g.vy = -6 - Math.random() * 4; }
        g.side = side;
        // never left of the line: the band the line falls in moves just right of it, so a
        // grain Mentat answers alone always sits on its side
        const start = pad + k * binW, shift = Math.max(0, xLine + 3 - start);
        g.tx = start + shift + (j % cols) * d;
        g.ty = ground - d - Math.floor(j / cols) * d;
      });
    });
    // The queue: rows under the ground, filling from the left, ordered by confidence.
    queue.sort((a, z) => R[z][0] - R[a][0]);
    const qd = Math.max(2.2, d);
    const qcols = Math.max(1, Math.floor((W - pad * 2) / qd));
    queue.forEach((idx, j) => {
      const g = grains[idx];
      if (kick && g.live && g.side !== -1) { g.vy = 2 + Math.random() * 2; }
      g.side = -1;
      g.tx = pad + (j % qcols) * qd;
      g.ty = ground + 34 + Math.floor(j / qcols) * qd;
    });
    const above = R.filter((r) => !queued(r, th)), right = above.filter((r) => r[1]).length;
    document.getElementById("s-auto").textContent = `${Math.round((above.length / R.length) * 100)}%`;
    document.getElementById("s-right").textContent = above.length ? `${Math.round((right / above.length) * 100)}%` : "-";
    document.getElementById("s-wrong").textContent = String(above.length - right);
    document.getElementById("s-queue").textContent = String(queue.length);
    wake();
  }

  function blowIn() {
    const now = performance.now();
    for (const g of grains) {
      g.live = true;
      g.x = -Math.random() * W * 0.5 - 10; g.y = Math.random() * ground * 0.9;
      g.vx = 6 + Math.random() * 6; g.vy = 0; g.born = now + Math.random() * 1400;
      if (reduced) { g.x = g.tx; g.y = g.ty; g.born = 0; }
    }
    sfx("sandstorm");
    wake();
  }

  let raf = 0;
  const wake = () => { if (!raf) raf = requestAnimationFrame(frame); };
  function frame(now) {
    raf = 0;
    ctx.clearRect(0, 0, W, H);
    const th = +cut.value, R = rows();
    const xc = pad + th * (W - pad * 2);
    // ground and queue labels
    ctx.fillStyle = "#1b1e26"; ctx.fillRect(pad, ground, W - pad * 2, 2);
    ctx.font = "14px Archivo, sans-serif"; ctx.fillStyle = "#a9dcff";
    ctx.fillText("Below the line: a person checks", pad, ground + 22);
    // the line and its handle: the handle is always fully on screen, with the number centred
    // in it and "drag" under the number; side labels appear only where there is room
    const hw = 56, hh = Math.max(46, H * 0.11), top = H * 0.03;
    const hx = Math.min(Math.max(xc - hw / 2, 2), W - hw - 2);
    ctx.fillStyle = "#a9dcff";
    ctx.fillRect(xc - 1, top + hh, 2, ground - top - hh);
    ctx.beginPath(); ctx.roundRect ? ctx.roundRect(hx, top, hw, hh, 8) : ctx.rect(hx, top, hw, hh); ctx.fill();
    ctx.fillStyle = "#0b0c10"; ctx.textAlign = "center";
    ctx.font = "700 14px Archivo, sans-serif"; ctx.fillText(th.toFixed(2), hx + hw / 2, top + hh / 2 - 2);
    ctx.font = "12px Archivo, sans-serif"; ctx.fillText("drag", hx + hw / 2, top + hh / 2 + 14);
    ctx.font = "14px Archivo, sans-serif"; ctx.fillStyle = "#8f877b";
    const midY = top + hh / 2 + 5;
    ctx.textAlign = "right";
    if (hx - 12 - ctx.measureText("a person checks").width > pad) ctx.fillText("a person checks", hx - 12, midY);
    ctx.textAlign = "left";
    if (hx + hw + 12 + ctx.measureText("Mentat alone").width < W - pad) ctx.fillText("Mentat alone", hx + hw + 12, midY);
    let moving = false;
    for (const g of grains) {
      if (!g.live || now < g.born) continue;
      const dx = g.tx - g.x, dy = g.ty - g.y;
      if (Math.abs(dx) > 0.4 || Math.abs(dy) > 0.4 || Math.abs(g.vy) > 0.3) {
        moving = true;
        g.vx = (g.vx + dx * 0.03) * 0.8; g.vy = (g.vy + dy * 0.03 + 0.04) * 0.82;
        g.x += g.vx; g.y += g.vy;
        if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5 && Math.abs(g.vx) + Math.abs(g.vy) < 0.25) { g.x = g.tx; g.y = g.ty; g.vx = g.vy = 0; }
      }
      const row = R[g.i], ok = row[1];
      ctx.fillStyle = queued(row, th) ? "#7fa9c6" : ok ? SAND[g.i % 3] : "#ff5a1f";
      const s = g.side === -1 ? Math.max(1.6, d * 0.8) : d * 0.92;
      ctx.fillRect(g.x, g.y, s, s);
      if (g.i === pick) { ctx.strokeStyle = "#a9dcff"; ctx.lineWidth = 2; ctx.strokeRect(g.x - 4, g.y - 4, s + 8, s + 8); }
    }
    if (moving) wake();
  }

  // Click a grain: open that conversation.
  canvas.addEventListener("click", (e) => {
    const b = canvas.getBoundingClientRect(), x = e.clientX - b.left, y = e.clientY - b.top;
    let best = -1, bd = 1e9;
    for (const g of grains) { const dd = (g.x - x) ** 2 + (g.y - y) ** 2; if (dd < bd) { bd = dd; best = g.i; } }
    if (best < 0 || bd > 400) return;
    pick = best; sfx("pop"); open(best); wake();
  });

  function open(i) {
    const c = world.convos && world.convos[i];
    const r = world.results && world.results[i];
    reader.hidden = false;
    if (!c || !r) { reader.textContent = "The conversations are still loading."; return; }
    const lines = c.context.slice(-8).map((t) => `<div class="line ${t.speaker === "action" ? "sys" : ""}"><span class="who">${t.speaker === "action" ? "system" : t.speaker}</span><span class="txt">${esc(t.text)}</span></div>`).join("");
    const right = r.action === c.action;
    reader.innerHTML = `
      <div><h4>Conversation ${esc(c.id)}${c.noise ? ` · rewritten: ${esc(c.noise.replace("_", " "))}` : ""}</h4><div class="log">${lines}</div></div>
      <div><h4>What happened</h4><dl>
        <div><dt>Mentat's next step</dt><dd class="${right ? "ok" : "bad"}">${esc(nice(r.action))}</dd></div>
        <div><dt>What the agent really did</dt><dd>${esc(nice(c.action))}</dd></div>
        <div><dt>Problem</dt><dd>${esc(nice(r.intent))}</dd></div>
        <div><dt>Sure</dt><dd>${r.confidence.toFixed(2)}</dd></div>
        <div><dt>Who handles it</dt><dd>${r.needs_human ? "a person checks" : "Mentat alone"}</dd></div>
        ${r.human_reasons && r.human_reasons.length ? `<div><dt>Why a person</dt><dd>${esc(r.human_reasons.map((x) => x.replace(/_/g, " ")).join(", "))}</dd></div>` : ""}
      </dl><button class="reader-close" type="button">Close</button></div>`;
    reader.querySelector(".reader-close").addEventListener("click", () => { reader.hidden = true; pick = -1; wake(); });
    reader.scrollIntoView({ block: "nearest", behavior: reduced ? "auto" : "smooth" });
  }

  cut.addEventListener("input", () => { layout(true); dragWind(0.08 + Math.min(0.42, lastMoved / 90)); });
  document.querySelectorAll("[data-who]").forEach((b) => b.addEventListener("click", () => {
    who = b.dataset.who;
    document.querySelectorAll("[data-who]").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
    for (const g of grains) g.vy = -4 - Math.random() * 8;
    sfx("sandstorm"); layout(false);
  }));
  addEventListener("resize", () => { size(); layout(false); grains.forEach((g) => { g.x = g.tx; g.y = g.ty; }); wake(); });

  // The Hinglish time machine and the rulebook re-run the model; the storm follows.
  world.on(() => { if (who === "mentat") { for (const g of grains) if (g.live) g.vy -= Math.random() * 3; layout(true); } });
  const machineBtn = document.getElementById("m-hinglish");
  const mOut = document.getElementById("m-out");
  let base = null;
  async function machine(rerun = true) {
    if (!world.convos) { mOut.textContent = "Still loading the conversations…"; return; }
    if (rerun) { mOut.textContent = "Re-running 2,300 conversations…"; await runAll("machine"); }
    const auto = world.results.filter((r) => !r.needs_human).length;
    const wrong = world.results.filter((r, i) => !r.needs_human && r.action !== world.convos[i].action).length;
    if (!world.hinglish && world.model === "fixed") base = { auto, wrong };
    const ref = base || { auto, wrong };
    const dAuto = auto - ref.auto, dWrong = wrong - ref.wrong;
    mOut.innerHTML = world.hinglish
      ? `With the phrase on every message, the <b class="${world.model === "old" ? "" : "calm"}">${world.model === "old" ? "old" : "fixed"} model</b> answers ${auto} alone (${dAuto >= 0 ? "+" : ""}${dAuto}) and lets <b class="${dWrong > 0 ? "" : "calm"}">${wrong} wrong answers</b> through unchecked (${dWrong >= 0 ? "+" : ""}${dWrong}).`
      : `No phrase added. The ${world.model} model answers ${auto} alone and lets ${wrong} wrong answers through unchecked.`;
  }
  machineBtn.addEventListener("click", () => {
    world.hinglish = !world.hinglish;
    machineBtn.setAttribute("aria-pressed", String(world.hinglish)); sfx("switch"); machine();
  });
  document.querySelectorAll("[data-model]").forEach((b) => b.addEventListener("click", () => {
    world.model = b.dataset.model;
    document.querySelectorAll("[data-model]").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
    sfx("switch"); machine();
  }));
  world.on((why) => { if (why === "loaded" || why === "rules") { base = null; machine(false); counts(); } });

  // Wrong answers sent out without a person, for each model with and without the phrase,
  // under the current rules. Counted in the background, one setting at a time.
  let countRun = 0;
  async function counts() {
    const id = ++countRun;
    const bars = [...document.querySelectorAll(".mr-bar")];
    bars.forEach((b) => { b.querySelector("b").textContent = "…"; });
    const got = {};
    for (const b of bars) {
      const [model, h] = b.dataset.k.split("|");
      const R = await evaluate(model, h === "1");
      if (id !== countRun) return;
      got[b.dataset.k] = R.filter((r, i) => !r.needs_human && r.action !== world.convos[i].action).length;
      const max = Math.max(...Object.values(got));
      for (const x of bars) {
        const v = got[x.dataset.k];
        if (v === undefined) continue;
        x.style.setProperty("--w", `${(v / max) * 100}%`);
        x.querySelector("b").textContent = String(v);
      }
    }
    // the phrase row turns calm when it lets nothing more through
    for (const model of ["fixed", "old"]) {
      const hb = bars.find((x) => x.dataset.k === `${model}|1`);
      hb.classList.toggle("calm", got[`${model}|1`] <= got[`${model}|0`]);
    }
  }
  const markOn = () => document.querySelectorAll(".mr-bar").forEach((x) => x.classList.toggle("on", x.dataset.k === `${world.model}|${world.hinglish ? 1 : 0}`));
  world.on(markOn);

  size(); layout(false);
  let started = false;
  new IntersectionObserver((es) => { if (es[0].isIntersecting && !started) { started = true; blowIn(); } }, { threshold: 0.2 }).observe(stage);
}

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
