// The 99 hostile requests from the test pack, as bricks. They light up one by one, like the
// test run that produced them; pick one to see what was sent and what came back.
import { beep, nice } from "./main.js";

export function wall(data) {
  const box = document.getElementById("wall");
  const card = document.getElementById("attack-card");
  const bricks = data.hostile.map((h, i) => {
    const b = document.createElement("button");
    b.className = "brick"; b.dataset.g = h.group; b.dataset.i = i;
    b.setAttribute("aria-label", `${h.group}: ${nice(h.label)}`);
    b.addEventListener("mouseenter", () => show(i, b));
    b.addEventListener("focus", () => show(i, b));
    b.addEventListener("click", () => show(i, b));
    box.append(b);
    return b;
  });
  const legend = document.createElement("p");
  legend.className = "legend";
  legend.innerHTML = '<span><i style="background:#eceae4"></i>published pack, 9</span><span><i style="background:#5d626c"></i>extended pack, 68</span><span><i style="background:#33373e"></i>broken HTTP, 22</span>';
  box.after(legend);

  function show(i, b) {
    bricks.forEach((x) => x.classList.toggle("sel", x === b));
    const h = data.hostile[i];
    const out = h.status !== 200
      ? `Refused with HTTP ${h.status} (${(h.error || "bad request").replace(/_/g, " ")}). The service stayed up.`
      : `${h.needs_human ? "Sent to a person" : "Answered"}. Next step: ${nice(h.action)}, ${(+h.confidence).toFixed(2)} sure.`;
    card.innerHTML = "";
    const add = (cls, text) => { const p = document.createElement("p"); p.className = cls; p.textContent = text; card.append(p); };
    add("ac-title", nice(h.label));
    add("ac-in", h.input || "(empty)");
    add("ac-out", out);
    add("ac-ms", `${h.ms} ms`);
  }

  let done = false;
  new IntersectionObserver((es) => {
    if (!es[0].isIntersecting || done) return;
    done = true;
    bricks.forEach((b, i) => setTimeout(() => { b.classList.add("done"); if (i % 3 === 0) beep(1200 + (i % 11) * 40, 0.015, "square", 0.01); }, i * 22));
  }, { threshold: 0.3 }).observe(box);
}
