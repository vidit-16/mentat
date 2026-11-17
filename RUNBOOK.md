# Runbook

For whoever operates the triage service. Commands assume the repository root.

## Start and stop

```bash
scripts/reproduce.sh setup      # once: .venv with pinned dependencies
scripts/reproduce.sh serve      # foreground, port $PORT (default 8000), $WORKERS processes
scripts/reproduce.sh start      # background; waits for /healthz; pid in .service.pid
scripts/reproduce.sh stop
```

Or with Docker: `docker build -t op06-triage . && docker run --rm -p 8000:8000 op06-triage`.

To restart, stop and wait for the process to exit before starting again (`stop` does this);
a new process cannot bind a port the old one still holds, and a health check would be
answered by the old one while it drains.

Ready means `GET /healthz` returns 200 with the model and policy versions. It only does so
after the model and policy loaded and a self-test request produced a real answer. If the
policy file is invalid the service refuses to start and the log says which line of the
policy is wrong; the previous process, if any, is unaffected.

The service keeps no state. Restarting it loses nothing, and any number of copies can run
behind a load balancer. The same request always gets the same answer for the same model and
policy versions, so a client may retry freely.

## Limits

| Limit | Value | What happens |
|---|---|---|
| Request body | 1 MB | HTTP 413 with an error object |
| Time to receive the body | 5 s (`TRIAGE_BODY_TIMEOUT_S`) | HTTP 408 |
| Turns | last 8 used | earlier turns are dropped, flag `too_many_turns` |
| Text per turn | 20,000 characters, then 80 words (first 50, last 30) | flag `truncated` |
| Open connections | 1,000 per process | further connections refused by the server |

Malformed JSON, a body that is not an object, or a missing or non-string `id` gets HTTP 400.
A valid envelope with unusable content (no readable text, wrong turn shape) gets HTTP 200 with
the abstention answer: `intent: "unknown"`, `action: "none"`, `confidence: 0`,
`needs_human: true`, and an `error` object saying why.

## Change a rule

The rules live in `policy/policy.yaml`, not in code.

1. Edit the file. Change `version` too, so every response and log line shows which rules
   produced it.
2. `scripts/reproduce.sh policy-check` — refuses the file if a name is unknown or an intent
   sits under two flows, and lists every dev conversation whose answer changes.
3. Restart the service.
4. Add a line to `policy/CHANGELOG.md`.

To roll back: restore the previous file from git, restart.

Examples:

- Stop the service from ever proposing refunds in returns conversations: remove
  `offer-refund` from `flows.product_defect.permitted`.
- Treat changing an order as risky: add `update-order` under `high_consequence.actions`.
  It will then only be proposed when the conversation already shows a system step.

## What to watch

`GET /metrics` gives counters per process since start. The log has one JSON line per request
(no message text) with the decision, confidence, reasons and versions.

| Signal | Normal on dev data | Investigate when |
|---|---|---|
| Share with `needs_human: true` | see MEMO.md | moves more than 5 points in a day |
| `reason:low_confidence` share | most of the human share | rises while traffic is unchanged: incoming messages no longer look like training data |
| `reason:policy_conflict` | about 2-3% | rises after a policy edit (expected) or without one (model drift) |
| `reason:injection_pattern` | near 0 | any sudden burst: someone is probing |
| `abstained` | near 0 | rises: a client is sending broken payloads |
| `error:internal_error` | 0 | any: a bug. The request still got a safe answer, but log it |
| p95 latency | see `results/latency_bench.json` | doubles: CPU starved, add a worker |

## Alerts and what they mean

- **Health check failing on start:** model or policy file missing or invalid. Read the first
  error in the log. Roll back the last change to `models/` or `policy/`.
- **`internal_error` count above zero:** a request hit a code path that raised. The client
  got the abstention answer. Take the request id from the log and reproduce with
  `tests/cases.py`.
- **Latency up, CPU at 100%:** add workers (`WORKERS`) or machines. Each request is a few
  milliseconds of single-core work.

## Retrain

```bash
scripts/reproduce.sh train          # about 15-25 minutes on a 4-core laptop
scripts/reproduce.sh eval           # compare with the previous results/ before switching
```

Training is deterministic for a given platform and library versions. Keep the previous
`models/` directory until the new one has been compared.
