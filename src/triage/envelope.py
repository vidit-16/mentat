"""Check the shape of a request before anything else looks at it.

Two outcomes for a bad request:
  - the body is not a JSON object with a usable `id`  -> BadRequest (HTTP 400)
  - the `id` is usable but the rest is not              -> a problem string, and the caller
                                                          answers 200 with the abstention shape
"""
from __future__ import annotations

import json

from .sanitise import MAX_TURNS, SPEAKERS

MAX_BODY_BYTES = 1_000_000
MAX_ID_CHARS = 512


class BadRequest(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _no_constants(name):
    raise ValueError(f"{name} is not valid JSON")


def _no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate key {key!r}")
        out[key] = value
    return out


def parse_body(raw: bytes) -> dict:
    """Decode and parse a request body. Raises BadRequest when there is nothing to answer."""
    if len(raw) > MAX_BODY_BYTES:
        raise BadRequest("request body too large", 413)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise BadRequest("body is not valid UTF-8")
    try:
        obj = json.loads(text, parse_constant=_no_constants, object_pairs_hook=_no_duplicates)
    except RecursionError:
        raise BadRequest("JSON is nested too deeply")
    except ValueError as exc:
        raise BadRequest(f"body is not valid JSON: {str(exc)[:120]}")
    if not isinstance(obj, dict):
        raise BadRequest("body must be a JSON object")
    rid = obj.get("id")
    if not isinstance(rid, str) or not rid:
        raise BadRequest("id must be a non-empty string")
    if len(rid) > MAX_ID_CHARS:
        raise BadRequest("id is too long")
    return obj


def check_context(obj: dict) -> tuple[list[dict] | None, str | None, bool]:
    """Return (context, problem, was_cut). Fields other than id, context and turn_index are
    never read, so a labelled row sent by mistake cannot leak its label into a prediction."""
    context = obj.get("context")
    if not isinstance(context, list):
        return None, "context must be a list of turns", False
    turns = []
    for item in context:
        if not isinstance(item, dict):
            return None, "each turn must be an object", False
        speaker, text = item.get("speaker"), item.get("text")
        if speaker not in SPEAKERS:
            return None, "speaker must be customer, agent or action", False
        if not isinstance(text, str):
            return None, "text must be a string", False
        turns.append({"speaker": speaker, "text": text})
    was_cut = len(turns) > MAX_TURNS
    return turns[-MAX_TURNS:], None, was_cut


def turn_index(obj: dict) -> int | None:
    value = obj.get("turn_index")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return min(value, 10_000)
