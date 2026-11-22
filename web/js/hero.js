// Your message, read live. Each word is coloured by how far removing it would move the
// answer (gold: it pushed toward the next step Mentat chose; orange: it pulled against).
// Press Enter and the words crumble into sand.
import { wordWeights } from "../engine/explain.js?v=12";
import { nice, reduced } from "./main.js?v=12";

export function hero(m) {
  const say = document.getElementById("say");
  const mirror = document.getElementById("say-mirror");
  const canvas = document.getElementById("hero-sand");
  const ctx = canvas.getContext("2d");
  const verdict = document.getElementById("hero-verdict");
  let lastVerdict = "";

  // One live line under the message: the answer in a few words.
  function read() {
    const text = say.textContent;
    const obj = { id: "hero", context: [{ speaker: "customer", text: text.trim() || " " }] };
    const t = m.trace(obj);
    const r = t.response;
    const flagged = (r.flags || []).includes("injection_pattern");
    let line, kind;
    if (r.held_back && r.held_back.action === "offer-refund") { line = "Refund held back. A person checks."; kind = "block"; }
    else if (r.held_back) { line = `${cap(nice(r.held_back.action))} held back. A person checks.`; kind = "block"; }
    else if (flagged) { line = "Flagged. A person checks."; kind = "block"; }
    else if (r.needs_human) { line = `Next step: ${nice(r.action)}. A person checks.`; kind = "person"; }
    else { line = `Next step: ${nice(r.action)}. Mentat handles it.`; kind = ""; }
    if (line !== lastVerdict) {
      verdict.textContent = line;
      verdict.className = `hero-verdict ${kind}`;
      void verdict.offsetWidth; verdict.classList.add("show");
      lastVerdict = line;
    }

    // Word colours, on the text exactly as typed (the mirror sits under the transparent editor).
    const ww = wordWeights(m, obj, "action");
    const weights = ww ? ww.turns[0].pieces.filter((p) => p.weight !== undefined).map((p) => p.weight) : [];
    const max = Math.max(1e-6, ...weights.map(Math.abs));
    // Three clear steps, not a blend: gold pushed the answer, off-white barely mattered,
    // orange pulled against it. Punctuation takes the colour of the word before it.
    const frag = document.createDocumentFragment();
    let k = 0, last = "#eee7da";
    for (const part of text.split(/([\p{L}\p{N}_']+)/u)) {
      if (!part) continue;
      if (/^[\p{L}\p{N}_']+$/u.test(part)) {
        const s = document.createElement("span"); s.className = "w"; s.textContent = part;
        const a = (weights[k++] || 0) / max;
        last = a > 0.5 ? "#e2c189" : a < -0.25 ? "#ff5a1f" : "#eee7da";
        s.style.color = last;
        frag.append(s);
      } else {
        const lead = part.match(/^[^\s]+/);
        if (lead) { const p = document.createElement("span"); p.textContent = lead[0]; p.style.color = last; frag.append(p, part.slice(lead[0].length)); }
        else frag.append(part);
      }
    }
    mirror.replaceChildren(frag);
  }

  // Sample the mirror's glyph pixels and let them blow away as sand, then the words return.
  const grains = [];
  let raf = 0;
  function crumble() {
    if (reduced) return;
    const dpr = Math.min(2, devicePixelRatio || 1);
    const W = canvas.clientWidth, H = canvas.clientHeight;
    canvas.width = W * dpr; canvas.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const cb = canvas.getBoundingClientRect();
    const off = document.createElement("canvas"); off.width = W; off.height = H;
    const o = off.getContext("2d");
    const cs = getComputedStyle(mirror);
    o.font = `${cs.fontWeight} ${cs.fontStretch} ${cs.fontSize} ${cs.fontFamily}`;
    o.textBaseline = "alphabetic";
    for (const span of mirror.querySelectorAll(".w")) {
      for (const rect of span.getClientRects()) {
        o.fillStyle = span.style.color || "#eee7da";
        o.fillText(span.textContent, rect.left - cb.left, rect.bottom - cb.top - rect.height * 0.22, rect.width + 4);
      }
    }
    const img = o.getImageData(0, 0, W, H).data;
    const step = 3;
    for (let y = 0; y < H; y += step) for (let x = 0; x < W; x += step) {
      const p = (y * W + x) * 4;
      if (img[p + 3] > 120) grains.push({ x, y, vx: 1 + Math.random() * 3, vy: -Math.random() * 1.5, d: Math.random() * 400 + x * 0.6, c: `rgb(${img[p]},${img[p + 1]},${img[p + 2]})`, s: 1.6 + Math.random() * 1.4, a: 1 });
    }
    mirror.classList.add("gone");
    const start = performance.now();
    cancelAnimationFrame(raf);
    const frame = (now) => {
      ctx.clearRect(0, 0, W, H);
      const t = now - start;
      for (const g of grains) {
        if (t > g.d) { g.vx += 0.12; g.vy += 0.09; g.x += g.vx; g.y += g.vy; g.a -= 0.012; }
        if (g.a <= 0) continue;
        ctx.globalAlpha = Math.max(0, g.a); ctx.fillStyle = g.c; ctx.fillRect(g.x, g.y, g.s, g.s);
      }
      ctx.globalAlpha = 1;
      if (t > 650) mirror.classList.remove("gone");
      if (t < 2600) raf = requestAnimationFrame(frame); else { grains.length = 0; ctx.clearRect(0, 0, W, H); }
    };
    raf = requestAnimationFrame(frame);
  }

  // Desktop: "Refund me. Right" / "now." (the punchline alone). Phones: "Refund me." / "Right now."
  const phone = matchMedia("(max-width: 640px)");
  const defaults = ["Refund me. Right\nnow.", "Refund me.\nRight now."];
  const setDefault = () => { if (defaults.includes(say.textContent) || say.textContent === "Refund me. Right now.") { say.textContent = defaults[phone.matches ? 1 : 0]; read(); } };
  phone.addEventListener("change", setDefault);
  say.textContent = defaults[phone.matches ? 1 : 0];

  let timer;
  say.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(read, 90); });
  say.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); read(); crumble(); } });
  read();
}

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
