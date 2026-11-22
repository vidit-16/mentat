import { Mentat } from "../engine/mentat.js?v=12";
import { hero } from "./hero.js?v=12";
import { interrogation } from "./game.js?v=12";
import { rulebook } from "./rules.js?v=12";
import { storm } from "./storm.js?v=12";
import { wall, horizon } from "./wall.js?v=12";
import { duel } from "./duel.js?v=12";

document.documentElement.classList.add("js");
export const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
export const nice = (l) => (!l || l === "none" ? "nothing permitted" : l.replace(/[_-]/g, " ").replace(/\s\d+$/, ""));

// ---------------------------------------------------------------- sound
// Browsers only allow audio after the visitor interacts, so it starts on the first click or key.
let ac = null, master = null, muted = false;
const soundBtn = document.getElementById("sound");
function arm() {
  if (ac || muted) return;
  ac = new AudioContext();
  master = ac.createGain(); master.gain.value = 0.9; master.connect(ac.destination);
  makeNoise();
}
addEventListener("pointerdown", arm, { once: false });
addEventListener("keydown", arm, { once: false });
soundBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  muted = !muted;
  soundBtn.setAttribute("aria-pressed", String(!muted));
  soundBtn.classList.toggle("muted", muted);
  soundBtn.setAttribute("aria-label", muted ? "Sound off. Click to turn it on." : "Sound on. Click to mute.");
  if (master) master.gain.value = muted ? 0 : 0.9;
  if (!muted) { arm(); sfx("tick"); }
});
function tone(freq, dur, type, gain, slideTo) {
  const t = ac.currentTime, o = ac.createOscillator(), g = ac.createGain();
  o.type = type; o.frequency.setValueAtTime(freq, t);
  if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, t + dur);
  g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(gain, t + 0.01); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  o.connect(g).connect(master); o.start(t); o.stop(t + dur + 0.05);
}

// Noise is made once, when sound first starts, and reused: building it on every sound was
// what made the wind lag behind a drag.
let airBuf = null, hissBuf = null;
function makeNoise() {
  const sr = ac.sampleRate, len = sr * 4;
  airBuf = ac.createBuffer(1, len, sr); hissBuf = ac.createBuffer(1, len, sr);
  const a = airBuf.getChannelData(0), h = hissBuf.getChannelData(0);
  let last = 0;
  for (let i = 0; i < len; i++) { last = (last + 0.02 * (Math.random() * 2 - 1)) / 1.02; a[i] = last * 3.2; h[i] = Math.random() * 2 - 1; }
}
function source(buf, loop = false) {
  const s = ac.createBufferSource(); s.buffer = buf; s.loop = loop;
  s.loopStart = 0; s.loopEnd = buf.duration;
  return s;
}
function burst(dur, gain, freq = 800, q = 0.8) {
  const t = ac.currentTime, s = source(hissBuf), f = ac.createBiquadFilter(), g = ac.createGain();
  f.type = "bandpass"; f.frequency.value = freq; f.Q.value = q;
  g.gain.setValueAtTime(gain, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  s.connect(f).connect(g).connect(master); s.start(t, Math.random() * 2); s.stop(t + dur + 0.05);
}

// Desert wind carrying fine sand: a soft rush of air whose pitch drifts like gusts, with a very
// faint fine hiss on top. No separate clicks, so it never sounds like gravel.
function wind(dur, amount = 1) {
  const t = ac.currentTime;
  const s1 = source(airBuf, true);
  const band = ac.createBiquadFilter(); band.type = "bandpass"; band.Q.value = 0.9;
  band.frequency.setValueAtTime(320, t);
  const gusts = Math.max(1, Math.round(dur / 0.9));
  for (let k = 1; k <= gusts; k++) band.frequency.linearRampToValueAtTime(k % 2 ? 900 + Math.random() * 500 : 300 + Math.random() * 150, t + (dur * k) / gusts);
  const g1 = ac.createGain();
  g1.gain.setValueAtTime(0.0001, t);
  g1.gain.exponentialRampToValueAtTime(0.9 * amount, t + dur * 0.35);
  g1.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  s1.connect(band).connect(g1).connect(master); s1.start(t, Math.random() * 2); s1.stop(t + dur + 0.05);

  const s2 = source(hissBuf, true);
  const hp = ac.createBiquadFilter(); hp.type = "highpass"; hp.frequency.value = 5200;
  const g2 = ac.createGain();
  g2.gain.setValueAtTime(0.0001, t);
  g2.gain.exponentialRampToValueAtTime(0.035 * amount, t + dur * 0.4);
  g2.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  s2.connect(hp).connect(g2).connect(master); s2.start(t, Math.random() * 2); s2.stop(t + dur + 0.05);
}

// While the storm line is dragged: one continuous wind whose strength follows the drag and
// fades out a moment after it stops. Nothing new is created per drag event.
let drag = null, dragIdle = 0;
export function dragWind(amount) {
  if (!ac || muted || !airBuf) return;
  if (ac.state === "suspended") ac.resume();
  const t = ac.currentTime;
  if (!drag) {
    const s = source(airBuf, true), band = ac.createBiquadFilter(), g = ac.createGain();
    band.type = "bandpass"; band.Q.value = 0.8; band.frequency.value = 520;
    g.gain.value = 0.0001;
    s.connect(band).connect(g).connect(master); s.start(t, Math.random() * 3);
    drag = { s, band, g };
  }
  const level = Math.max(0.06, Math.min(0.5, amount));
  drag.g.gain.setTargetAtTime(level, t, 0.06);
  drag.band.frequency.setTargetAtTime(420 + level * 900, t, 0.1);
  clearTimeout(dragIdle);
  dragIdle = setTimeout(() => {
    if (!drag) return;
    const d = drag; drag = null;
    d.g.gain.setTargetAtTime(0.0001, ac.currentTime, 0.18);
    d.s.stop(ac.currentTime + 1.2);
  }, 160);
}

export function sfx(name) {
  if (!ac || muted || !airBuf) return;
  if (ac.state === "suspended") ac.resume();
  switch (name) {
    case "tick": tone(1400 + Math.random() * 300, 0.035, "square", 0.05); break;
    case "held": tone(110, 0.32, "sine", 0.28, 70); burst(0.14, 0.08, 400, 1.2); break;
    case "sandstorm": wind(2.8, 1); break;
    case "flag": tone(220, 0.22, "sawtooth", 0.18, 180); tone(233, 0.22, "sawtooth", 0.14, 190); break;
    case "pass": tone(440, 0.18, "triangle", 0.25); setTimeout(() => tone(660, 0.18, "triangle", 0.22), 110); setTimeout(() => tone(880, 0.4, "triangle", 0.2), 220); break;
    case "person": tone(520, 0.3, "sine", 0.2, 390); break;
    case "pop": tone(300, 0.06, "sine", 0.12, 700); break;
    case "switch": tone(760, 0.05, "square", 0.06); break;
  }
}

// ---------------------------------------------------------------- top bar: hide going down, show going up
const bar = document.getElementById("top-bar");
let lastY = scrollY;
addEventListener("scroll", () => {
  const y = scrollY;
  bar.classList.toggle("hide", y > lastY && y > 200);
  lastY = y;
}, { passive: true });

// ---------------------------------------------------------------- entrances
const io = new IntersectionObserver((es) => es.forEach((e) => {
  if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
}), { rootMargin: "0px 0px -8% 0px" });
document.querySelectorAll(".sec-head > *, .rounds, .room > *, .rules-body > *, .storm-bar, .machine, .arena, .h2h-rows, .attacks-body > *, .end-in")
  .forEach((n, i) => { n.classList.add("rise"); n.style.transitionDelay = `${(i % 3) * 90}ms`; io.observe(n); });

// ---------------------------------------------------------------- the shared model and all 2,300 conversations
const status = document.getElementById("status");
const t0 = performance.now();
const read = (n) => fetch("model/" + n).then((r) => { if (!r.ok) throw new Error(`${n}: HTTP ${r.status}`); return r.arrayBuffer(); });
const dataP = fetch("data/site.json").then((r) => r.json());
const mentatP = Mentat.load(read);

// One place re-runs everything when a rule or the model changes; listeners redraw.
export const world = {
  mentat: null, data: null, convos: null, results: null,
  hinglish: false, model: "fixed", oldConf: null,
  listeners: [],
  on(fn) { this.listeners.push(fn); },
  emit(why) { this.listeners.forEach((fn) => fn(why)); },
};

const SUFFIX = " thoda jaldi karo please";
function lastCustomer(ctx) { for (let i = ctx.length - 1; i >= 0; i--) if (ctx[i].speaker === "customer") return i; return -1; }

// Runs a model (fixed or old) with or without the Hinglish phrase over all 2,300 under the
// current rules, in small slices so the page never freezes. Returns the answers; changes nothing.
export async function evaluate(model, hinglish) {
  const m = world.mentat, conf = model === "old" ? world.oldConf : m.model.confidence, saved = m.conf;
  const out = new Array(world.convos.length);
  for (let i = 0; i < world.convos.length; i += 120) {
    m.conf = conf;
    for (let j = i; j < Math.min(i + 120, world.convos.length); j++) {
      const c = world.convos[j];
      let ctx = c.context;
      if (hinglish) { const k = lastCustomer(ctx); if (k >= 0) ctx = ctx.map((t, n) => (n === k ? { ...t, text: t.text + SUFFIX } : t)); }
      out[j] = m.handle({ id: c.id, context: ctx, turn_index: c.turn_index });
    }
    m.conf = saved;
    await new Promise((res) => setTimeout(res, 0));
  }
  return out;
}

// Runs the current model and rules over all 2,300, in small slices so the page never freezes.
let runId = 0;
export async function runAll(why) {
  if (!world.convos) return;
  const id = ++runId;
  const m = world.mentat;
  const conf = world.model === "old" ? world.oldConf : m.model.confidence;
  const saved = m.conf;
  const out = new Array(world.convos.length);
  for (let i = 0; i < world.convos.length; i += 120) {
    if (id !== runId) return;
    // Swap the confidence model only inside this synchronous slice, so the hero and the game,
    // which run between slices, always use the shipped model.
    m.conf = conf;
    for (let j = i; j < Math.min(i + 120, world.convos.length); j++) {
      const c = world.convos[j];
      let ctx = c.context;
      if (world.hinglish) {
        const k = lastCustomer(ctx);
        if (k >= 0) ctx = ctx.map((t, n) => (n === k ? { ...t, text: t.text + SUFFIX } : t));
      }
      const r = m.handle({ id: c.id, context: ctx, turn_index: c.turn_index });
      out[j] = r;
    }
    m.conf = saved;
    await new Promise((res) => setTimeout(res, 0));
  }
  world.results = out;
  world.emit(why);
}

Promise.all([mentatP, dataP]).then(async ([m, data]) => {
  world.mentat = m; world.data = data;
  status.textContent = `Model live in this tab · 93,441 features · loaded in ${((performance.now() - t0) / 1000).toFixed(1)} s`;
  hero(m);
  interrogation(m, data);
  wall(data);
  storm(world);
  rulebook(world);
  // The conversations and the old confidence model load after the page is usable.
  const [buf, old] = await Promise.all([
    fetch("data/convos.json.gz").then((r) => r.arrayBuffer()),
    fetch("model/confidence-train-002.json").then((r) => r.json()),
  ]);
  const bytes = new Uint8Array(buf);
  const plain = bytes[0] === 0x1f && bytes[1] === 0x8b
    ? await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"))).arrayBuffer() : buf;
  world.convos = JSON.parse(new TextDecoder().decode(plain));
  world.oldConf = old;
  await runAll("loaded");
  duel(world);
}).catch((e) => {
  status.textContent = "The model could not load here. The answers shown are the ones it gave when this page was built.";
  console.error(e);
});

horizon();

// Head to head: bars grow when the section comes into view; a row opens to explain itself.
const h2h = document.querySelector(".h2h");
new IntersectionObserver((es, o) => { if (es[0].isIntersecting) { h2h.classList.add("in"); o.disconnect(); } }, { threshold: 0.3 }).observe(h2h);
document.querySelectorAll(".h2h-row").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".h2h-row").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
  document.getElementById("hx-title").textContent = b.querySelector(".h2h-name").textContent;
  document.getElementById("hx-text").textContent = b.dataset.explain;
  sfx("tick");
}));
