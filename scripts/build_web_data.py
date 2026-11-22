#!/usr/bin/env python3
"""Write web/data/site.json: the real numbers and rows the project site draws from.

    python scripts/build_web_data.py

Everything comes from committed results (the submitted CI run, the baseline run, the hostile
pack) and the reference data. Nothing is typed in by hand except the choice of example rows.
"""
from __future__ import annotations

import gzip
import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

from cases import transport_cases, valid_cases  # noqa: E402

SHOWCASE_ID = "7522-8"
REFUND_ID = "7958-19"   # a real conversation where the agent's next step was a refund


def jl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def preview(text: str, n: int = 64) -> str:
    """Short, printable view of an input, with invisible characters spelled out."""
    out = []
    for ch in text[:n]:
        cp = ord(ch)
        if ch == " " or (ch.isprintable() and not 0xD800 <= cp <= 0xDFFF
                         and unicodedata.category(ch) not in ("So", "Sk", "Co", "Cn")):
            out.append(ch)
        else:
            out.append(f"\\u{cp:04x}" if cp <= 0xFFFF else f"\\U{cp:08x}")
    s = "".join(out)
    if len(s) > n:                      # escapes are long; keep the preview short either way
        s = s[:n].rstrip("\\")
    if len(text) > n or len(s) >= n:
        s += f" … ({len(text):,} characters)"
    return s


def main() -> int:
    gold = {r["id"]: r for name in ("dev.jsonl", "dev_noisy.jsonl")
            for r in jl(ROOT / "reference" / name)}
    mentat = jl(ROOT / "results" / "dev_predictions.jsonl") + jl(ROOT / "results" / "noisy_predictions.jsonl")
    base = {p["id"]: p for p in jl(ROOT / "results" / "raw" / "baseline-001" / "predictions.jsonl")}
    rows = [p for p in mentat if p["id"] in gold]
    routing = {
        "mentat": [[round(p["confidence"], 4), int(p["action"] == gold[p["id"]]["action"])] for p in rows],
        "baseline": [[round(base[p["id"]]["confidence"], 4), int(base[p["id"]]["action"] == gold[p["id"]]["action"])]
                     for p in rows if p["id"] in base],
        "threshold": json.loads((ROOT / "models" / "confidence.json").read_text())["threshold"],
        "needs_human": sum(p["needs_human"] for p in rows),
    }

    # The extended pack: what each input was, and what came back.
    sent = {c["id"]: c for c in valid_cases()}
    raw = dict(transport_cases())
    hostile = []
    pub = {r["id"]: r for r in jl(ROOT / "reference" / "hostile.jsonl")}
    for r in jl(ROOT / "results" / "hostile_results.jsonl"):
        if r.get("summary"):
            continue
        g, rid = r["group"], r["id"]
        if g == "published":
            text = " | ".join(t["text"] for t in pub[rid]["context"])
            label = pub[rid].get("hostile_kind", "")
        elif g == "extended":
            ctx = sent.get(rid, {}).get("context", [])
            text = " | ".join(str(t.get("text", "")) if isinstance(t, dict) else str(t) for t in ctx[:3]) if isinstance(ctx, list) else str(ctx)
            label = rid[2:] if rid.startswith("x-") else rid
        else:
            text = raw[rid][:200].decode("utf-8", "replace")
            label = rid
        resp = r.get("response") or {}
        hostile.append({"group": g, "id": preview(rid, 40), "label": preview(label, 40), "ms": r["ms"], "status": r["status"],
                        "input": preview(text),
                        "action": resp.get("action"), "confidence": resp.get("confidence"),
                        "needs_human": resp.get("needs_human"),
                        "error": (resp.get("error") or {}).get("code")})

    manifest = json.loads((ROOT / "results" / "manifest.json").read_text(encoding="utf-8"))
    ex = gold[SHOWCASE_ID]
    site = {
        "results": manifest["claimed"],
        "run": manifest["submitted_run"],
        "routing": routing,
        "hostile": hostile,
        "showcase": {"id": ex["id"], "context": ex["context"], "turn_index": ex.get("turn_index"),
                     "gold": {"intent": ex["intent"], "action": ex["action"]}},
        "refund": {"id": REFUND_ID, "context": gold[REFUND_ID]["context"],
                   "turn_index": gold[REFUND_ID].get("turn_index"),
                   "gold": {"intent": gold[REFUND_ID]["intent"], "action": gold[REFUND_ID]["action"]}},
    }
    out = ROOT / "web" / "data"
    out.mkdir(parents=True, exist_ok=True)

    # Every dev and noisy conversation, as a client sends it, plus the gold labels, so the
    # page can re-run the model on all of them (rulebook, Hinglish time machine, click a grain).
    convos = []
    for name in ("dev.jsonl", "dev_noisy.jsonl"):
        for r in jl(ROOT / "reference" / name):
            row = {"id": r["id"], "context": [{"speaker": t["speaker"], "text": t["text"]} for t in r["context"]],
                   "intent": r["intent"], "action": r["action"], "noise": r.get("noise_kind"),
                   "permitted": r.get("permitted_actions", [])}
            if "turn_index" in r:
                row["turn_index"] = r["turn_index"]
            convos.append(row)
    (out / "convos.json.gz").write_bytes(gzip.compress(json.dumps(convos, separators=(",", ":")).encode("utf-8"),
                                                       compresslevel=9, mtime=0))
    order = [c["id"] for c in convos]
    assert order == [p["id"] for p in rows], "routing rows and conversations must share one order"
    (out / "site.json").write_text(json.dumps(site, separators=(",", ":")) + "\n",
                                   encoding="utf-8", newline="\n")
    print(len(routing["mentat"]), "routing rows,", len(routing["baseline"]), "baseline,",
          len(hostile), "hostile,", (out / "site.json").stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
