import { Mentat } from "../engine/mentat.js";
import { hero } from "./hero.js";
import { interrogation } from "./game.js";
import { storm } from "./storm.js";
import { wall } from "./wall.js";

document.documentElement.classList.add("js");

// ---------------------------------------------------------------- sound (off by default)
let audio = null;
export function beep(freq = 440, dur = 0.08, type = "sine", gain = 0.05) {
  if (!audio) return;
  const t = audio.currentTime;
  const o = audio.createOscillator(), g = audio.createGain();
  o.type = type; o.frequency.setValueAtTime(freq, t);
  g.gain.setValueAtTime(gain, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  o.connect(g).connect(audio.destination); o.start(t); o.stop(t + dur + 0.02);
}
const soundBtn = document.getElementById("sound");
soundBtn.addEventListener("click", () => {
  const on = soundBtn.getAttribute("aria-pressed") !== "true";
  soundBtn.setAttribute("aria-pressed", String(on));
  soundBtn.textContent = on ? "Sound on" : "Sound off";
  if (on && !audio) audio = new AudioContext();
  if (!on && audio) { audio.close(); audio = null; }
  if (on) beep(660, 0.12, "triangle", 0.06);
});

// ---------------------------------------------------------------- entrances
const io = new IntersectionObserver((es) => es.forEach((e) => {
  if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
}), { rootMargin: "0px 0px -10% 0px" });
document.querySelectorAll(".interro-head > *, .rounds, .room > *, .storm-head > *, .storm-read, .num, .attacks-head > *, .attacks-body > *, .foot > *")
  .forEach((n, i) => { n.classList.add("rise"); n.style.transitionDelay = `${(i % 4) * 80}ms`; io.observe(n); });

// ---------------------------------------------------------------- load
const status = document.getElementById("status");
const t0 = performance.now();
const dataP = fetch("data/site.json").then((r) => r.json());
const modelP = Mentat.load((n) => fetch("model/" + n).then((r) => {
  if (!r.ok) throw new Error(`${n}: HTTP ${r.status}`);
  return r.arrayBuffer();
}));

dataP.then((data) => { storm(data); wall(data); }).catch(console.error);
Promise.all([modelP, dataP]).then(([m, data]) => {
  status.textContent = `Model live in this tab · 93,441 features · loaded in ${((performance.now() - t0) / 1000).toFixed(1)} s`;
  hero(m);
  interrogation(m, data);
}).catch((e) => {
  status.textContent = "The model could not load here. The answers shown are the ones it gave when this page was built.";
  console.error(e);
});

export const nice = (label) => (!label || label === "none" ? "nothing permitted" : label.replace(/[_-]/g, " ").replace(/\s\d+$/, ""));
export const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
