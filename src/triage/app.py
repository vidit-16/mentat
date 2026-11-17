"""HTTP layer: size limits, timeouts, JSON in and out. All decisions happen in pipeline.py."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
from collections import Counter

from starlette.applications import Starlette
from starlette.requests import ClientDisconnect, Request
from starlette.responses import Response
from starlette.routing import Route

from .envelope import MAX_BODY_BYTES, BadRequest, parse_body
from .pipeline import Triage

log = logging.getLogger("triage")
BODY_TIMEOUT_S = float(os.environ.get("TRIAGE_BODY_TIMEOUT_S", "5"))


def _json(payload: dict, status: int = 200) -> Response:
    # ensure_ascii keeps odd characters in an echoed id from breaking a client's decoder.
    body = json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    return Response(body, status_code=status, media_type="application/json")


def _error(status: int, code: str, message: str) -> Response:
    return _json({"error": {"code": code, "message": message}}, status)


async def _read_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise BadRequest("request body too large", 413)
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise BadRequest("request body too large", 413)
        chunks.append(chunk)
    return b"".join(chunks)


def create_app(triage: Triage | None = None) -> Starlette:
    state = {"triage": triage, "ready": False, "counters": Counter(), "started": time.time()}

    def load() -> None:
        if state["triage"] is None:
            state["triage"] = Triage()
        # Self-test: one known request must produce a real answer before we report ready.
        probe = state["triage"].handle({"id": "selftest", "context": [
            {"speaker": "customer", "text": "i want to return an item"}]})
        if "error" in probe:
            raise RuntimeError("self-test failed: " + probe["error"]["code"])
        state["ready"] = True
        log.info("ready %s", json.dumps(state["triage"].versions))

    @contextlib.asynccontextmanager
    async def lifespan(app):
        load()
        yield

    async def healthz(request: Request) -> Response:
        if not state["ready"]:
            return _error(503, "not_ready", "model is still loading")
        return _json({"status": "ok", **state["triage"].versions})

    async def metrics(request: Request) -> Response:
        return _json({"uptime_s": round(time.time() - state["started"], 1),
                      "pid": os.getpid(), "counters": dict(state["counters"])})

    async def triage_route(request: Request) -> Response:
        c = state["counters"]
        c["requests"] += 1
        if not state["ready"]:
            return _error(503, "not_ready", "model is still loading")
        try:
            raw = await asyncio.wait_for(_read_body(request), BODY_TIMEOUT_S)
            obj = parse_body(raw)
        except BadRequest as exc:
            c["bad_request"] += 1
            code = "payload_too_large" if exc.status == 413 else "bad_request"
            return _error(exc.status, code, exc.message)
        except asyncio.TimeoutError:
            c["body_timeout"] += 1
            return _error(408, "timeout", "request body was not received in time")
        except ClientDisconnect:
            c["client_disconnect"] += 1
            return _error(400, "bad_request", "client disconnected")
        out = state["triage"].handle(obj)
        if "error" in out:
            c["abstained"] += 1
            c["error:" + out["error"]["code"]] += 1
        if out["needs_human"]:
            c["needs_human"] += 1
        for reason in out.get("human_reasons", ()):
            c["reason:" + reason] += 1
        log.info(json.dumps({
            "id": out["id"][:64], "intent": out["intent"], "action": out["action"],
            "confidence": out["confidence"], "needs_human": out["needs_human"],
            "reasons": out.get("human_reasons", []), "flags": out.get("flags", []),
            "ms": out["latency_ms"], **out["versions"]}))
        return _json(out)

    async def server_error(request: Request, exc: Exception) -> Response:
        log.exception("unhandled error in HTTP layer")
        return _error(500, "internal_error", "internal error")

    app = Starlette(routes=[Route("/healthz", healthz, methods=["GET"]),
                            Route("/metrics", metrics, methods=["GET"]),
                            Route("/triage", triage_route, methods=["POST"])],
                    lifespan=lifespan, exception_handlers={Exception: server_error})
    app.state.triage_state = state
    return app


def factory() -> Starlette:
    """Entry point for `uvicorn --factory triage.app:factory`."""
    logging.basicConfig(level=os.environ.get("TRIAGE_LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    return create_app()
