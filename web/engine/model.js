// Loads the exported model (scripts/export_web_model.py) and scores a feature vector.
// Port of src/triage/model.py. Works in the browser and in Node.

export const HEADS = ["intent", "flow", "action"];

// float16 bits -> float32 value, for all 65,536 bit patterns.
const F16 = (() => {
  const t = new Float32Array(65536);
  for (let h = 0; h < 65536; h++) {
    const s = h & 0x8000 ? -1 : 1, e = (h >> 10) & 0x1f, f = h & 0x3ff;
    t[h] = e === 0 ? s * 2 ** -14 * (f / 1024)
      : e === 31 ? (f ? NaN : s * Infinity)
      : s * 2 ** (e - 15) * (1 + f / 1024);
  }
  return t;
})();

async function gunzip(buf) {
  const bytes = new Uint8Array(buf);
  if (!(bytes[0] === 0x1f && bytes[1] === 0x8b)) return buf;   // already decoded by the server
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
  return new Response(stream).arrayBuffer();
}

// `read(name)` returns an ArrayBuffer for a file in the exported model directory.
export async function loadModel(read) {
  const text = async (n) => new TextDecoder().decode(await read(n));
  const [meta, conf, policy, manifest, vocabBuf, weightBuf] = await Promise.all([
    text("model.json").then(JSON.parse), text("confidence.json").then(JSON.parse),
    text("policy.json").then(JSON.parse), text("manifest.json").then(JSON.parse),
    read("vocab.json.gz").then(gunzip), read("weights.f16.gz").then(gunzip),
  ]);
  const vocabRaw = JSON.parse(new TextDecoder().decode(vocabBuf));
  const vocab = {}, offsets = {};
  let start = 0;
  for (const b of meta.blocks) {
    vocab[b] = new Map(Object.entries(vocabRaw[b]));
    offsets[b] = start;
    start += vocab[b].size;
  }
  if (start !== meta.n_features) throw new Error("vocabulary does not match the weights");
  const weights = new Uint16Array(weightBuf);
  if (weights.length !== meta.n_features * meta.row_width) throw new Error("weight file has the wrong size");
  const cut = {};
  let at = 0;
  for (const h of HEADS) { cut[h] = [at, at + meta.classes[h].length]; at += meta.classes[h].length; }
  return {
    version: meta.version, classes: meta.classes, temperature: meta.temperature,
    blocks: meta.blocks, blockWeights: meta.block_weights, nFeatures: meta.n_features,
    rowWidth: meta.row_width, bias: meta.bias, idf: meta.idf, vocab, offsets, cut,
    weights, confidence: conf, policy, manifest,
  };
}

// The weight one feature column gives one class of one head.
export const weight = (m, col, head, k) => F16[m.weights[col * m.rowWidth + m.cut[head][0] + k]];

export function scores(m, idx, val) {
  const out = {};
  for (const h of HEADS) {
    const [a, b] = m.cut[h];
    const s = Float64Array.from(m.bias[h]);
    for (let n = 0; n < idx.length; n++) {
      const row = idx[n] * m.rowWidth, v = val[n];
      for (let k = a; k < b; k++) s[k - a] += v * F16[m.weights[row + k]];
    }
    out[h] = s;
  }
  return out;
}

export function softmax(s, t) {
  let max = -Infinity;
  for (const v of s) max = Math.max(max, v / t);
  const e = Array.from(s, (v) => Math.exp(v / t - max));
  const sum = e.reduce((a, b) => a + b, 0);
  return e.map((v) => v / sum);
}

export const probabilities = (m, sc) =>
  Object.fromEntries(HEADS.map((h) => [h, softmax(sc[h], m.temperature[h])]));
