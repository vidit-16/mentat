// The 99 hostile requests from the test pack, and the dune horizon that ends the page.
import { nice, sfx } from "./main.js?v=12";

export function wall(data) {
  const box = document.getElementById("wall");
  const card = document.getElementById("attack-card");
  const bricks = data.hostile.map((h, i) => {
    const b = document.createElement("button");
    b.className = "brick"; b.dataset.g = h.group;
    b.setAttribute("aria-label", `${h.group}: ${nice(h.label)}`);
    const go = () => show(i, b);
    b.addEventListener("mouseenter", go); b.addEventListener("focus", go); b.addEventListener("click", () => { sfx("tick"); go(); });
    box.append(b);
    return b;
  });
  const legend = document.createElement("p");
  legend.className = "legend";
  legend.innerHTML = '<span><i style="background:#e2c189"></i>published pack, 9</span><span><i style="background:#8a7552"></i>extended pack, 68</span><span><i style="background:#4a4031"></i>broken HTTP, 22</span>';
  box.after(legend);

  function show(i, b) {
    bricks.forEach((x) => x.classList.toggle("sel", x === b));
    const h = data.hostile[i];
    const out = h.status !== 200
      ? `Refused with HTTP ${h.status} (${(h.error || "bad request").replace(/_/g, " ")}). The service stayed up.`
      : `${h.needs_human ? "Sent to a person" : "Answered"}. Next step: ${nice(h.action)}, ${(+h.confidence).toFixed(2)} sure.`;
    card.replaceChildren(...[["ac-title", nice(h.label)], ["ac-in", h.input || "(empty)"], ["ac-out", out], ["ac-ms", `${h.ms} ms`]].map(([c, t]) => {
      const p = document.createElement("p"); p.className = c; p.textContent = t; return p;
    }));
  }

  show(0, bricks[0]);   // start on the first attack, so the card is never empty

  let done = false;
  new IntersectionObserver((es) => {
    if (!es[0].isIntersecting || done) return;
    done = true;
    bricks.forEach((b, i) => setTimeout(() => { b.classList.add("done"); if (i % 4 === 0) sfx("tick"); }, i * 22));
  }, { threshold: 0.3 }).observe(box);
}

export function horizon() {
  const c = document.getElementById("horizon"), x = c.getContext("2d");
  function draw() {
    const dpr = Math.min(2, devicePixelRatio || 1), W = c.clientWidth, H = c.clientHeight;
    c.width = W * dpr; c.height = H * dpr; x.setTransform(dpr, 0, 0, dpr, 0, 0);
    x.clearRect(0, 0, W, H);
    [["#15141a", 0.5, 34, 0.0032, 0.4], ["#231d18", 0.64, 48, 0.0021, 1.9], ["#3a2e20", 0.8, 40, 0.0046, 3.1]].forEach(([col, b, amp, f, ph]) => {
      x.fillStyle = col; x.beginPath(); x.moveTo(0, H);
      for (let px = 0; px <= W; px += 5) x.lineTo(px, H * b - amp * (Math.sin(px * f + ph) * 0.7 + Math.sin(px * f * 2.3 + ph) * 0.3) ** 2);
      x.lineTo(W, H); x.fill();
    });
  }
  draw(); addEventListener("resize", draw);
}
