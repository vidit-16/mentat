// The message you type breaks into the features the model actually fired; each spark flies
// to the head it pushed hardest (problem, flow, next step) and the towers rise by the real
// probabilities.
import { weight } from "../engine/model.js";
import { beep, nice, reduced } from "./main.js";

const HEADS = ["intent", "flow", "action"];
const MAX_SPARKS = 420;

export function hero(m) {
  const section = document.querySelector(".hero");
  const canvas = document.getElementById("hero-canvas");
  const ctx = canvas.getContext("2d");
  const say = document.getElementById("say");
  const towers = Object.fromEntries(HEADS.map((h) => [h, section.querySelector(`.tower[data-head="${h}"]`)]));
  let W = 0, H = 0, dpr = 1;
  const sparks = [];
  const motes = Array.from({ length: 70 }, () => ({ x: Math.random(), y: Math.random(), v: 0.00004 + Math.random() * 0.00012, r: Math.random() * 1.2 + 0.3 }));

  function size() {
    dpr = Math.min(2, devicePixelRatio || 1);
    W = section.clientWidth; H = section.clientHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  addEventListener("resize", size);
  size();

  const rel = (el) => { const a = el.getBoundingClientRect(), b = section.getBoundingClientRect(); return { x: a.left - b.left, y: a.top - b.top, w: a.width, h: a.height }; };

  function run(burst = true) {
    const text = say.textContent.trim() || " ";
    const t = m.trace({ id: "hero", context: [{ speaker: "customer", text }] });
    const r = t.response;
    if (!t.probs) return;
    const chosen = { intent: r.intent, flow: r.flow, action: r.action };
    for (const h of HEADS) {
      const k = m.model.classes[h].indexOf(chosen[h]);
      const p = k >= 0 ? t.probs[h][k] : 0;
      const tw = towers[h];
      tw.querySelector(".t-fill").style.height = `${Math.max(2, p * 100)}%`;
      tw.querySelector(".t-val").textContent = nice(chosen[h]);
      tw.querySelector(".t-p").textContent = `${Math.round(p * 100)}%`;
    }
    const v = document.getElementById("hero-verdict");
    const held = r.held_back ? `${nice(r.held_back.action)}: held back` : (r.flags || []).includes("injection_pattern") ? "Flagged as an attempt to instruct it" : "";
    v.innerHTML = "";
    const b = document.createElement("span"); b.className = "vb"; b.textContent = held; v.append(b);
    const s = document.createElement("span");
    s.textContent = `${r.needs_human ? "A person checks" : "Mentat handles it"} · ${r.confidence.toFixed(2)} sure`;
    v.append(s);
    if (burst && !reduced) launch(t, chosen);
  }

  function launch(t, chosen) {
    const src = rel(say);
    const cols = Object.fromEntries(HEADS.map((h) => [h, rel(towers[h].querySelector(".t-col"))]));
    const ks = Object.fromEntries(HEADS.map((h) => [h, m.model.classes[h].indexOf(chosen[h])]));
    const feats = t.vec.idx.map((col, n) => {
      let best = "intent", bc = 0;
      for (const h of HEADS) {
        if (ks[h] < 0) continue;
        const c = t.vec.val[n] * weight(m.model, col, h, ks[h]);
        if (Math.abs(c) > Math.abs(bc)) { bc = c; best = h; }
      }
      return { head: best, c: bc };
    }).sort((a, b) => Math.abs(b.c) - Math.abs(a.c)).slice(0, MAX_SPARKS);
    const now = performance.now();
    for (const f of feats) {
      const col = cols[f.head];
      const fill = towers[f.head].querySelector(".t-fill").offsetHeight;
      const x0 = src.x + Math.random() * src.w, y0 = src.y + Math.random() * src.h;
      const x1 = col.x + Math.random() * col.w, y1 = col.y + col.h - fill - 4 + Math.random() * 8;
      sparks.push({
        x0, y0, x1, y1, cx: (x0 + x1) / 2 + (Math.random() - 0.5) * 200, cy: Math.min(y0, y1) - 80 - Math.random() * 220,
        t0: now + Math.random() * 380, dur: 900 + Math.random() * 900,
        r: 0.8 + Math.min(3.2, Math.abs(f.c) * 6),
        col: f.c < 0 ? "255,75,31" : f.head === "action" ? "198,255,74" : "236,234,228",
      });
    }
    beep(220, 0.25, "sawtooth", 0.02);
    if (!raf) raf = requestAnimationFrame(frame);
  }

  let raf = 0;
  function frame(now) {
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = "rgba(6,7,8,0.28)";
    ctx.fillRect(0, 0, W, H);
    ctx.globalCompositeOperation = "lighter";
    for (const d of motes) {
      d.y -= d.v * 16; if (d.y < 0) { d.y = 1; d.x = Math.random(); }
      ctx.fillStyle = "rgba(236,234,228,0.10)";
      ctx.fillRect(d.x * W, d.y * H, d.r, d.r);
    }
    for (let i = sparks.length - 1; i >= 0; i--) {
      const s = sparks[i];
      const u = (now - s.t0) / s.dur;
      if (u < 0) continue;
      if (u >= 1) { sparks.splice(i, 1); continue; }
      const e = 1 - Math.pow(1 - u, 3);
      const x = (1 - e) * (1 - e) * s.x0 + 2 * (1 - e) * e * s.cx + e * e * s.x1;
      const y = (1 - e) * (1 - e) * s.y0 + 2 * (1 - e) * e * s.cy + e * e * s.y1;
      const a = u < 0.1 ? u * 10 : 1 - Math.max(0, u - 0.85) / 0.15;
      ctx.fillStyle = `rgba(${s.col},${0.9 * a})`;
      ctx.beginPath(); ctx.arc(x, y, s.r, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = `rgba(${s.col},${0.12 * a})`;
      ctx.beginPath(); ctx.arc(x, y, s.r * 4, 0, Math.PI * 2); ctx.fill();
    }
    const visible = section.getBoundingClientRect().bottom > 0;
    raf = visible || sparks.length ? requestAnimationFrame(frame) : 0;
  }
  new IntersectionObserver((es) => { if (es[0].isIntersecting && !raf) raf = requestAnimationFrame(frame); }).observe(section);

  let timer;
  say.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => run(true), 140); });
  say.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); run(true); } });
  run(false);
  setTimeout(() => run(true), 500);
}
