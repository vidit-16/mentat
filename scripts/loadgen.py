#!/usr/bin/env python3
"""Measure latency of the running service from the outside, at a fixed concurrency.

    python scripts/loadgen.py --url http://127.0.0.1:8000 --concurrency 8 --requests 3000 \
        --out results/latency_bench.json

Each worker thread keeps one HTTP/1.1 connection and sends requests back to back. The payload
mix is every published dev, noisy and hostile row (projected to the reviewer's fields),
cycled in a fixed shuffled order, so long noisy rows and hostile rows are included.
Durations are measured here, by the client, never taken from the service's own latency_ms.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "reference"))
from evaluation_inputs import project  # noqa: E402


def payloads() -> list[bytes]:
    rows = []
    for name in ("dev.jsonl", "dev_noisy.jsonl", "hostile.jsonl"):
        for line in (ROOT / "reference" / name).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(project("OP-06", json.loads(line)))
    random.Random(7).shuffle(rows)
    return [json.dumps(r).encode("utf-8") for r in rows]


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round(p / 100 * len(ordered) + 0.5)) - 1))
    return ordered[k]


def cpu_name() -> str:
    try:
        if platform.system() == "Linux":
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
        if platform.system() == "Windows":
            return subprocess.run(["powershell", "-NoProfile", "-Command",
                                   "(Get-CimInstance Win32_Processor).Name"],
                                  capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:                                       # noqa: BLE001
        pass
    return platform.processor() or "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--requests", type=int, default=3000)
    ap.add_argument("--warmup", type=int, default=100)
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--out")
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    target = urlparse(args.url)
    bodies = payloads()
    lock = threading.Lock()
    counter = {"next": 0}
    records: list[dict] = []

    def take() -> int | None:
        with lock:
            i = counter["next"]
            if i >= args.requests + args.warmup:
                return None
            counter["next"] += 1
            return i

    def worker():
        conn = http.client.HTTPConnection(target.hostname, target.port or 80, timeout=args.timeout)
        while (i := take()) is not None:
            body = bodies[i % len(bodies)]
            rid = json.loads(body)["id"]
            started = time.perf_counter()
            status, error = None, None
            try:
                conn.request("POST", "/triage", body=body, headers={"content-type": "application/json"})
                resp = conn.getresponse()
                data = resp.read()
                status = resp.status
                json.loads(data)
            except Exception as exc:                        # noqa: BLE001
                error = type(exc).__name__
                conn.close()
                conn = http.client.HTTPConnection(target.hostname, target.port or 80,
                                                  timeout=args.timeout)
            took = (time.perf_counter() - started) * 1000
            if i >= args.warmup:
                with lock:
                    records.append({"seq": i - args.warmup, "id": rid, "ms": round(took, 3),
                                    "status": status, "error": error})
        conn.close()

    threads = [threading.Thread(target=worker) for _ in range(args.concurrency)]
    wall = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - wall

    ok = [r["ms"] for r in records if r["status"] == 200 and not r["error"]]
    result = {
        "label": args.label,
        "url_host": f"{target.hostname}:{target.port}",
        "concurrency": args.concurrency,
        "requests_measured": len(records),
        "warmup_requests": args.warmup,
        "ok": len(ok),
        "non_200": sum(1 for r in records if r["status"] not in (200, None)),
        "errors": sum(1 for r in records if r["error"]),
        "latency_ms": {"p50": round(pct(ok, 50), 2), "p95": round(pct(ok, 95), 2),
                       "p99": round(pct(ok, 99), 2), "max": round(max(ok), 2),
                       "mean": round(statistics.mean(ok), 2)} if ok else None,
        "throughput_rps": round((args.requests + args.warmup) / wall, 1),
        "wall_seconds": round(wall, 2),
        "client": {"python": platform.python_version(), "os": platform.platform(),
                   "cpu": cpu_name(), "logical_cpus": os.cpu_count()},
        "measured_by": "client-side wall clock per request (time.perf_counter)",
        "requests": sorted(records, key=lambda r: r["seq"]),
    }
    summary = {k: v for k, v in result.items() if k != "requests"}
    print(json.dumps(summary, indent=1))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return 0 if result["errors"] == 0 and result["non_200"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
