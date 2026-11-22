// Port of src/triage/features.py.
import { parseEvent } from "./text.js?v=12";

const TOKEN = /<[\p{L}\p{N}_]+>|[\p{L}\p{N}_]+(?:'[\p{L}\p{N}_]+)?/gu;
const SPK = { customer: "c", agent: "a", action: "x" };

export const words = (text) => text.match(TOKEN) || [];

const add = (m, k, n = 1) => m.set(k, (m.get(k) || 0) + n);

// Raw feature counts per block, in Python's insertion order.
export function extract(turns, turnIndex, blocks) {
  const out = {};
  for (const b of blocks) out[b] = new Map();
  const n = turns.length;
  const events = [];
  let sinceAction = null;
  turns.forEach((turn, i) => {
    const toks = words(turn.text);
    const dist = n - i;
    const spk = SPK[turn.speaker];
    if (out.w) {
      for (const t of toks) add(out.w, t);
      for (let j = 0; j + 1 < toks.length; j++) add(out.w, `${toks[j]} ${toks[j + 1]}`);
    }
    if (out.c && turn.speaker !== "action") {
      for (const tok of toks) {
        const padded = Array.from(` ${tok} `);
        for (const size of [2, 3, 4, 5]) {
          for (let j = 0; j + size <= padded.length; j++) add(out.c, padded.slice(j, j + size).join(""));
        }
      }
    }
    if (out.s) {
      const pos = Math.min(dist, 3);
      for (const t of toks) add(out.s, `${spk}${pos}:${t}`);
      for (const t of toks) add(out.s, `${spk}:${t}`);
    }
    if (turn.speaker === "action") {
      const [name, values] = parseEvent(turn.text);
      events.push(name);
      sinceAction = dist;
      if (out.x) {
        add(out.x, `E:${name}`);
        for (const v of values) add(out.x, `V:${name}:${v}`);
      }
    }
  });
  if (out.x) {
    const x = out.x;
    for (let j = 0; j + 1 < events.length; j++) add(x, `E2:${events[j]}>${events[j + 1]}`);
    add(x, `LAST:${events.length ? events[events.length - 1] : "none"}`);
    add(x, `NEV:${Math.min(events.length, 4)}`);
    add(x, `N:${n}`);
    const speakers = turns.map((t) => SPK[t.speaker]);
    add(x, `LS:${speakers.slice(-1).join("") || "-"}`);
    add(x, `LS2:${speakers.slice(-2).join("") || "-"}`);
    add(x, `LS3:${speakers.slice(-3).join("") || "-"}`);
    add(x, `SINCE:${sinceAction ? Math.min(sinceAction, 6) : "none"}`);
    if (turnIndex === null) add(x, "TI:na");
    else {
      add(x, `TI:${Math.min(Math.floor(turnIndex / 3), 9)}`);
      add(x, `TIC:${turnIndex <= 6 ? "early" : turnIndex <= 14 ? "mid" : "late"}`);
    }
  }
  return out;
}

// TF-IDF per block, each block scaled to unit length, then joined. Returns the column
// indices, values, which block and feature each came from, and the unseen-word share.
export function transform(model, feats) {
  const idx = [], val = [], names = [];
  let seen = 0, total = 0;
  for (const b of model.blocks) {
    const vocab = model.vocab[b], idf = model.idf[b];
    const bi = [], bv = [], bn = [];
    for (const [feat, count] of feats[b]) {
      const col = vocab.get(feat);
      if (b === "w" && !feat.includes(" ")) {
        total += count;
        if (col !== undefined) seen += count;
      }
      if (col !== undefined) {
        bi.push(col);
        bv.push((1 + Math.log(count)) * idf[col]);
        bn.push([b, feat]);
      }
    }
    if (!bi.length) continue;
    let sq = 0;
    for (const v of bv) sq += v * v;
    const norm = Math.sqrt(sq);
    const scale = norm > 0 ? (model.blockWeights[b] ?? 1) / norm : 1;
    for (let k = 0; k < bi.length; k++) {
      idx.push(bi[k] + model.offsets[b]);
      val.push(norm > 0 ? bv[k] * scale : bv[k]);
      names.push(bn[k]);
    }
  }
  if (!idx.length) return { idx, val, names, unseen: 1.0 };
  return { idx, val, names, unseen: total ? 1 - seen / total : 1.0 };
}
