// 2,300 real development conversations fall into piles by confidence. Right of the line,
// Mentat answers alone; left of it, a person checks. Red dots got the wrong answer.
import { beep, reduced } from "./main.js";

const BINS = 100;

export function storm(data) {
  const stage = document.querySelector(".storm-stage");
  const canvas = document.getElementById("storm-canvas");
  const ctx = canvas.getContext("2d");
  const cut = document.getElementById("cut");
  cut.value = String(Math.round(data.routing.threshold * 100) / 100);
  let who = "mentat";
  let W = 0, H = 0, dpr = 1, d = 3, pad = 0;
  const n = data.routing.mentat.length;
  // One dot per conversation; the same dot moves between Mentat's pile and the baseline's.
  const dots = Array.from({ length: n }, (_, i) => ({ i, x: 0, y: -10, vy: 0, tx: 0, ty: 0, live: false }));

  function layout() {
    dpr = Math.min(2, devicePixelRatio || 1);
    W = stage.clientWidth; H = stage.clientHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    pad = Math.max(18, Math.min(48, W * 0.032));
    const rows = data.routing[who];
    const bins = Array.from({ length: BINS }, () => []);
    rows.forEach(([c], i) => bins[Math.min(BINS - 1, Math.floor(c * BINS))].push(i));
    // Wrong answers sit on top of each pile, so they are visible.
    bins.forEach((b) => b.sort((a, z) => rows[z][1] - rows[a][1]));
    const binW = (W - pad * 2) / BINS;
    const most = Math.max(...bins.map((b) => b.length));
    d = 4;
    while (d > 1.2 && Math.ceil(most / Math.max(1, Math.floor(binW / d))) * d > H * 0.92) d -= 0.1;
    const cols = Math.max(1, Math.floor(binW / d));
    bins.forEach((b, k) => b.forEach((idx, j) => {
      const dot = dots[idx];
      dot.tx = pad + k * binW + (j % cols) * d + d / 2;
      dot.ty = H - Math.floor(j / cols) * d - d / 2;
    }));
  }

  function drop(kick) {
    dots.forEach((dot, k) => {
      if (!dot.live) { dot.x = dot.tx + (Math.random() - 0.5) * 60; dot.y = -Math.random() * H * 1.6 - 10; dot.vy = 0; dot.live = true; }
      else if (kick) { dot.vy = -2 - Math.random() * 6; dot.delay = k % 7; }
    });
    if (reduced) dots.forEach((dot) => { dot.x = dot.tx; dot.y = dot.ty; dot.vy = 0; });
    if (!raf) raf = requestAnimationFrame(frame);
  }

  function readout() {
    const th = +cut.value;
    const rows = data.routing[who];
    const above = rows.filter((r) => r[0] >= th);
    const right = above.filter((r) => r[1]).length;
    document.getElementById("s-auto").textContent = `${Math.round((above.length / rows.length) * 100)}%`;
    document.getElementById("s-right").textContent = above.length ? `${Math.round((right / above.length) * 100)}%` : "-";
    document.getElementById("s-wrong").textContent = String(above.length - right);
  }

  let raf = 0;
  function frame() {
    ctx.clearRect(0, 0, W, H);
    const th = +cut.value;
    const rows = data.routing[who];
    const xCut = pad + th * (W - pad * 2);
    ctx.fillStyle = "rgba(198,255,74,0.05)";
    ctx.fillRect(xCut, 0, W - pad - xCut, H);
    let moving = false;
    for (const dot of dots) {
      if (!dot.live) continue;
      dot.x += (dot.tx - dot.x) * 0.08;
      dot.vy += 0.45;
      dot.y += dot.vy;
      if (dot.y >= dot.ty) { dot.y = dot.ty; dot.vy = Math.abs(dot.vy) > 1.2 ? -dot.vy * 0.28 : 0; }
      if (dot.vy !== 0 || Math.abs(dot.tx - dot.x) > 0.3) moving = true;
      const [c, ok] = rows[dot.i];
      const auto = c >= th;
      ctx.fillStyle = !auto ? "#3a3f47" : ok ? "#eceae4" : "#ff4b1f";
      ctx.fillRect(dot.x - d / 2, dot.y - d / 2, d * 0.86, d * 0.86);
    }
    // the line
    ctx.fillStyle = "#c6ff4a";
    ctx.fillRect(xCut - 1, 0, 2, H);
    ctx.font = "12px 'JetBrains Mono', monospace";
    ctx.fillText(`${th.toFixed(2)} · drag me`, Math.min(xCut + 8, W - 130), 16);
    ctx.fillStyle = "#8a8f99";
    ctx.fillText("a person checks", Math.max(pad, xCut - 130), 34);
    ctx.fillText("Mentat alone", Math.min(xCut + 8, W - 110), 34);
    raf = moving ? requestAnimationFrame(frame) : 0;
  }

  cut.addEventListener("input", () => { readout(); if (!raf) raf = requestAnimationFrame(frame); beep(300 + +cut.value * 600, 0.02, "sine", 0.02); });
  document.querySelectorAll(".storm .seg button").forEach((b) => b.addEventListener("click", () => {
    who = b.dataset.who;
    document.querySelectorAll(".storm .seg button").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
    layout(); drop(true); readout();
  }));
  addEventListener("resize", () => { layout(); dots.forEach((dot) => { if (dot.live) { dot.x = dot.tx; dot.y = dot.ty; } }); if (!raf) raf = requestAnimationFrame(frame); });

  layout(); readout();
  let started = false;
  new IntersectionObserver((es) => {
    if (es[0].isIntersecting && !started) { started = true; drop(false); beep(140, 0.6, "sawtooth", 0.02); }
  }, { threshold: 0.3 }).observe(stage);
}
