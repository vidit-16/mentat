#!/usr/bin/env python3
"""Combine load-test runs into results/latency_bench.json, with cost per message.

    python scripts/bench_summary.py results/raw/bench-c8.json results/raw/bench-c32.json \
        --workers 2 --out results/latency_bench.json

Cost per message is compute only (the service makes no API calls):
    hourly price of the machine / messages served per hour at the measured throughput.
The price used is a public on-demand list price for a general-purpose cloud VM of similar
size, stated with its source below. It is an estimate of what the manager would pay, not a
measurement of this laptop.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# AWS EC2 on-demand, Linux, us-east-1, c7i.large (2 vCPU, 4 GiB). The AWS pricing page loads
# its table with scripts, so the figure was read from a third-party price aggregator on
# 2026-11-17. It is an estimate for the memo, not a quote.
VM = {"name": "AWS EC2 c7i.large (2 vCPU, 4 GiB), on-demand, Linux, us-east-1",
      "usd_per_hour": 0.08925,
      "source": "https://instances.vantage.sh/aws/ec2/c7i.large (aggregator of AWS list prices)",
      "read": "2026-11-17"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--workers", type=int, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    runs = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.runs]
    out = {"service_workers": args.workers, "api_cost_usd_per_message": 0.0,
           "compute_price_basis": VM, "runs": []}
    for run, path in zip(runs, args.runs):
        rps = run["throughput_rps"]
        summary = {k: v for k, v in run.items() if k != "requests"}
        summary["raw_path"] = str(Path(path).as_posix())
        summary["request_ids"] = [r["id"] for r in run["requests"]][:50] + ["..."]
        summary["compute_usd_per_1000_messages_at_this_throughput"] = round(
            VM["usd_per_hour"] / (rps * 3600) * 1000, 6) if rps else None
        out["runs"].append(summary)
    Path(args.out).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    for r in out["runs"]:
        print(r["label"], "c", r["concurrency"], "p95", r["latency_ms"]["p95"], "ms",
              "rps", r["throughput_rps"], "errors", r["errors"],
              "$/1000", r["compute_usd_per_1000_messages_at_this_throughput"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
