#!/usr/bin/env bash
# Reproduce Mentat on a plain Linux machine. No GPU, no API key.
#
#   scripts/reproduce.sh setup         create .venv and install pinned dependencies
#   scripts/reproduce.sh check         verify reference files against the release hashes
#   scripts/reproduce.sh baseline      rerun the published baseline through the official grader
#   scripts/reproduce.sh train         retrain models/ from reference/train.jsonl.gz (~6 min)
#   scripts/reproduce.sh serve         run the service in the foreground on $PORT (blocks)
#   scripts/reproduce.sh start | stop  run the service in the background (pid in .service.pid)
#   scripts/reproduce.sh test          unit, invariant, policy-change, fuzz and hostile tests
#   scripts/reproduce.sh eval          score dev + noisy + hostile through the HTTP service
#   scripts/reproduce.sh hostile       send the hostile pack to the HTTP service
#   scripts/reproduce.sh bench         load test at concurrency 8 and 32
#   scripts/reproduce.sh policy-check  validate policy/policy.yaml and show its effect on dev
#   scripts/reproduce.sh web-check     browser engine (web/engine) against the Python service
#                                      on 2,377 inputs; needs Node 20+
#   scripts/reproduce.sh all           setup check test eval hostile bench (uses committed models)
#
# Environment: PORT (default 8000), WORKERS (default 2), PYTHON (default python3),
# OUT (results directory for eval/hostile/bench, default results).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-2}"
PYTHON="${PYTHON:-python3}"
OUT="${OUT:-results}"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"
URL="http://127.0.0.1:$PORT"
PIDFILE="$ROOT/.service.pid"
export PYTHONPATH="$ROOT/src"
export PYTHONHASHSEED=0

need_venv() {
  [ -x "$PY" ] || { echo "no .venv; run: scripts/reproduce.sh setup" >&2; exit 1; }
}

setup() {
  "$PYTHON" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ needed"'
  if [ ! -x "$PY" ]; then
    "$PYTHON" -m venv "$VENV" || {
      rm -rf "$VENV"
      echo "could not create a virtual environment. On Debian/Ubuntu: apt install python3-venv" >&2
      exit 1
    }
  fi
  "$PY" -m pip install --quiet --upgrade pip
  "$PY" -m pip install --quiet -r requirements.txt
  echo "setup done: $("$PY" --version)"
}

check() { need_venv; "$PY" scripts/check_reference.py; }

baseline() {
  need_venv
  mkdir -p "$OUT/raw/baseline-repro"
  (cd reference && "$PY" baseline.py --train train.jsonl.gz --eval dev.jsonl \
     --eval-noisy dev_noisy.jsonl --eval-hostile hostile.jsonl \
     --pred-out "$ROOT/$OUT/raw/baseline-repro/predictions.jsonl" && \
   "$PY" grader.py --pred "$ROOT/$OUT/raw/baseline-repro/predictions.jsonl" --gold dev.jsonl \
     --noisy dev_noisy.jsonl --hostile hostile.jsonl --schema schema.json \
     --report "$ROOT/$OUT/raw/baseline-repro/report.json")
}

train() { need_venv; "$PY" -m triage.train --out models; }

serve() {
  need_venv
  exec env PORT="$PORT" WORKERS="$WORKERS" "$PY" -m triage.serve
}

healthy() {
  "$PY" - "$URL" <<'EOF' 2>/dev/null
import sys, urllib.request
urllib.request.urlopen(sys.argv[1] + "/healthz", timeout=2).read()
EOF
}

port_busy() {
  "$PY" - "$PORT" <<'EOF' 2>/dev/null
import socket, sys
s = socket.socket()
try:
    s.connect(("127.0.0.1", int(sys.argv[1])))
except OSError:
    sys.exit(1)
EOF
}

start() {
  need_venv
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "service already running (pid $(cat "$PIDFILE"))"; return 0
  fi
  # Something else on the port would answer /healthz and be mistaken for this service.
  if port_busy; then
    echo "port $PORT is already in use by another process; stop it or set PORT" >&2
    return 1
  fi
  mkdir -p "$OUT/raw"
  PORT="$PORT" WORKERS="$WORKERS" nohup "$PY" -m triage.serve >> "$OUT/raw/service.log" 2>&1 &
  local pid=$!
  echo "$pid" > "$PIDFILE"
  for _ in $(seq 1 120); do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "service exited during start; see $OUT/raw/service.log" >&2
      rm -f "$PIDFILE"; return 1
    fi
    if healthy; then
      echo "service ready on $URL (pid $pid, log $OUT/raw/service.log)"; return 0
    fi
    sleep 1
  done
  echo "service did not become ready on $URL" >&2
  return 1
}

stop() {
  [ -f "$PIDFILE" ] || return 0
  local pid
  pid="$(cat "$PIDFILE")"
  kill "$pid" 2>/dev/null || true
  # Wait for the process to exit and the port to be released, so a following start cannot
  # be answered by a server that is still shutting down.
  for _ in $(seq 1 60); do
    if ! kill -0 "$pid" 2>/dev/null && ! port_busy; then break; fi
    sleep 0.5
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$PIDFILE"
  echo "service stopped"
}

with_service() {
  local started=0
  if ! { [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }; then
    start; started=1
  fi
  local rc=0
  "$@" || rc=$?
  [ "$started" = 1 ] && stop
  return $rc
}

test_() { need_venv; "$PY" -m pytest -q -p no:cacheprovider tests; }

eval_inner() {
  local run="$OUT/raw/eval-$(date -u +%Y%m%dT%H%M%SZ)"
  "$PY" scripts/evaluate.py --url "$URL" --out "$run"
  cp "$run/dev_predictions.jsonl" "$OUT/dev_predictions.jsonl"
  cp "$run/noisy_predictions.jsonl" "$OUT/noisy_predictions.jsonl"
  echo "raw run in $run"
}
eval_() { need_venv; with_service eval_inner; }

hostile_inner() {
  "$PY" scripts/hostile_run.py --url "$URL" --out "$OUT/hostile_results.jsonl"
}
hostile() { need_venv; with_service hostile_inner; }

bench_inner() {
  "$PY" scripts/loadgen.py --url "$URL" --concurrency 8 --requests 3000 \
    --label "c8" --out "$OUT/raw/bench-c8.json"
  "$PY" scripts/loadgen.py --url "$URL" --concurrency 32 --requests 3000 \
    --label "c32" --out "$OUT/raw/bench-c32.json"
  "$PY" scripts/bench_summary.py "$OUT/raw/bench-c8.json" "$OUT/raw/bench-c32.json" \
    --workers "$WORKERS" --out "$OUT/latency_bench.json"
}
bench() { need_venv; with_service bench_inner; }

policy_check() { need_venv; "$PY" scripts/policy_check.py "${@}"; }

web_check() {
  need_venv
  command -v node >/dev/null || { echo "node not found; web-check needs Node 20+" >&2; exit 1; }
  local dir="$OUT/raw/web-agreement"
  mkdir -p "$dir"
  # The exported files in web/model must come from the committed model and policy.
  "$PY" - <<'PY'
import json, sys
sys.path.insert(0, "src")
from triage.pipeline import Triage
t = Triage()
m = json.load(open("web/model/manifest.json"))
assert m["model_version"] == t.model.version, (m["model_version"], t.model.version)
assert m["policy_version"] == t.policy.version, (m["policy_version"], t.policy.version)
print("web/model matches models/ and policy/:", m["model_version"], m["policy_version"])
PY
  "$PY" scripts/web_agreement_ref.py --out "$dir"
  node scripts/web_agreement.mjs --dir "$dir"
}

all() { setup; check; test_; eval_; hostile; bench; }

trap 'stop >/dev/null 2>&1 || true' INT TERM

cmd="${1:-help}"; shift || true
case "$cmd" in
  setup) setup ;;
  check) check ;;
  baseline) baseline ;;
  train) train ;;
  serve) serve ;;
  start) start ;;
  stop) stop ;;
  test) test_ ;;
  eval) eval_ ;;
  hostile) hostile ;;
  bench) bench ;;
  policy-check) policy_check "$@" ;;
  web-check) web_check ;;
  all) all ;;
  *) sed -n '2,20p' "$0"; exit 2 ;;
esac
