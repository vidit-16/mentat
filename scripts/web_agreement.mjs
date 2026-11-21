// Run the browser engine (web/engine) on the inputs written by web_agreement_ref.py and
// compare every answer with the Python service's.
//
//   node scripts/web_agreement.mjs --dir <dir> [--report <file>]
//
// Every field must be identical, except confidence, which may differ by at most 1e-5: the
// Python service sums float32 values in BLAS order, the browser in float64. Exit code 1 on
// any disagreement.
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { Mentat } from "../web/engine/mentat.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const arg = (name, dflt) => { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : dflt; };
const dir = arg("--dir");
const reportPath = arg("--report", path.join(dir, "agreement.json"));
const TOL = 1e-5;

const lines = async (f) => (await readFile(f, "utf8")).split("\n").filter(Boolean).map(JSON.parse);
const model = path.join(ROOT, "web", "model");
const read = async (n) => { const b = await readFile(path.join(model, n)); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength); };

const t0 = performance.now();
const mentat = await Mentat.load(read);
const loadMs = performance.now() - t0;
const inputs = await lines(path.join(dir, "inputs.jsonl"));
const expected = await lines(path.join(dir, "python.jsonl"));

const canon = (v) => JSON.stringify(v, Object.keys(v).sort());
const mismatches = [];
let maxDiff = 0, sumMs = 0, maxMs = 0;
const out = [];
inputs.forEach((row, i) => {
  const s = performance.now();
  const got = mentat.handle(row);
  const ms = performance.now() - s;
  sumMs += ms; maxMs = Math.max(maxMs, ms);
  out.push(JSON.stringify(got));
  const want = expected[i];
  const diff = Math.abs(got.confidence - want.confidence);
  maxDiff = Math.max(maxDiff, diff);
  const fields = new Set([...Object.keys(got), ...Object.keys(want)]);
  const bad = [];
  for (const k of fields) {
    if (k === "confidence") { if (diff > TOL) bad.push(k); continue; }
    const a = got[k], b = want[k];
    const same = (a && typeof a === "object") ? (b && typeof b === "object" && JSON.stringify(a, Object.keys(a).sort()) === JSON.stringify(b, Object.keys(b).sort()))
      : a === b;
    if (!same) bad.push(k);
  }
  if (bad.length) mismatches.push({ id: String(row.id).slice(0, 80), fields: bad,
    js: Object.fromEntries(bad.map((k) => [k, got[k]])), python: Object.fromEntries(bad.map((k) => [k, want[k]])) });
});

const report = {
  model_version: mentat.model.version, rows: inputs.length,
  agree: inputs.length - mismatches.length, disagree: mismatches.length,
  max_confidence_diff: maxDiff, tolerance: TOL,
  load_ms: Math.round(loadMs), mean_ms: +(sumMs / inputs.length).toFixed(3), max_ms: +maxMs.toFixed(1),
  node: process.version, mismatches: mismatches.slice(0, 50),
};
await writeFile(reportPath, JSON.stringify(report, null, 1) + "\n");
await writeFile(path.join(dir, "js.jsonl"), out.join("\n") + "\n");
console.log(JSON.stringify({ ...report, mismatches: mismatches.slice(0, 5) }, null, 1));
process.exit(mismatches.length ? 1 : 0);
