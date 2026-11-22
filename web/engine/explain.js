// Why the model chose what it chose, word by word. The model is linear, but words reach it
// through several features at once (the word, its pairs, its letters, who said it), so the
// honest measure is occlusion: remove one word, rerun the scoring, see how far the chosen
// answer's probability moves. Positive = the word pushed toward the answer.
import { cleanContext } from "./text.js?v=12";
import { extract, transform } from "./features.js?v=12";
import { scores, probabilities } from "./model.js?v=12";

const TOKEN = /<[\p{L}\p{N}_]+>|[\p{L}\p{N}_]+(?:'[\p{L}\p{N}_]+)?/gu;

function prob(m, turns, turnIndex, head, k) {
  const vec = transform(m, extract(turns, turnIndex, m.blocks));
  return probabilities(m, scores(m, vec.idx, vec.val))[head][k];
}

// Returns, for each turn, its cleaned text split into words and gaps, with a weight per word.
export function wordWeights(mentat, obj, head = "intent", label = null, maxWords = 160) {
  const m = mentat.model;
  const t = mentat.trace(obj);
  if (!t.cleaned || !t.decision) return null;
  label = label || (head === "intent" ? t.decision.intent : t.decision.action);
  const k = m.classes[head].indexOf(label);
  const turns = t.cleaned.turns;
  const ti = typeof obj.turn_index === "number" ? obj.turn_index : null;
  const base = prob(m, turns, ti, head, k);
  let budget = maxWords;
  const out = turns.map((turn, i) => {
    const pieces = [];
    let last = 0;
    for (const match of turn.text.matchAll(TOKEN)) {
      if (match.index > last) pieces.push({ text: turn.text.slice(last, match.index) });
      const word = { text: match[0], weight: 0 };
      if (budget-- > 0) {
        const cut = turn.text.slice(0, match.index) + turn.text.slice(match.index + match[0].length);
        const changed = turns.map((x, j) => (j === i ? { ...x, text: cut } : x));
        word.weight = base - prob(m, changed, ti, head, k);
      }
      pieces.push(word);
      last = match.index + match[0].length;
    }
    if (last < turn.text.length) pieces.push({ text: turn.text.slice(last) });
    return { speaker: turn.speaker, pieces };
  });
  return { label, head, probability: base, turns: out, trace: t };
}
