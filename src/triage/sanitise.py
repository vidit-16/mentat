"""Turn raw turn text into something safe and bounded to compute features from.

Nothing here decides an intent or an action. It only cleans text and records what it saw.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .events import parse_event

# Hard caps. A turn longer than this is cut before any other work so that no input can make
# the service spend unbounded time.
MAX_TURN_CHARS = 20_000
MAX_TURN_TOKENS = 80
HEAD_TOKENS = 50
TAIL_TOKENS = MAX_TURN_TOKENS - HEAD_TOKENS
MAX_TOKEN_CHARS = 40
MAX_TURNS = 8

SPEAKERS = ("customer", "agent", "action")

_WS = re.compile(r"\s+")

# Wording that tries to address the system instead of describing a problem. This is a tripwire
# for routing and counting only. Safety does not depend on it matching.
_INJECTION = re.compile(
    r"ignore (all |any |your |the |previous |prior |above )+(instruction|rule|polic|prompt)"
    r"|disregard (all |any |your |the |previous |prior )+(instruction|rule|polic)"
    r"|\bnew instruction"
    r"|\bsystem\s*:"
    r"|\bsystem prompt\b"
    r"|</?\s*(context|system|instruction|prompt)\b"
    r"|\bneeds_human\b"
    r"|\bfrom now on\b"
    r"|\byou are now (a|an|in|the|my|acting)\b"
    r"|\boverride (the |your )?(polic|rule|instruction)"
    r"|\bdeveloper mode\b"
    r"|\bjailbreak\b"
)


def _looks_like_system_event(text: str) -> bool:
    """Customer text written like a system event ("account has been pulled up ...").
    No customer turn in the 20,000 training rows does this, so it is a spoofing attempt."""
    return any(not parse_event(part.strip())[0].startswith("other")
               for part in re.split(r"[.!?]\s+|\.\.\.", text) if part.strip())


@dataclass
class Turn:
    speaker: str
    text: str            # cleaned, lower-cased, length-capped
    tokens: list[str]


@dataclass
class Cleaned:
    turns: list[Turn]
    flags: dict[str, bool] = field(default_factory=dict)
    usable: bool = True  # False when no turn has any letter or digit left


def clean_text(raw: str) -> tuple[str, dict[str, bool]]:
    """Normalise one string. Returns the cleaned text and what was removed."""
    flags = {"had_control": False, "had_format": False, "truncated": False}
    if len(raw) > MAX_TURN_CHARS:
        # Keep both ends: a long message usually states the request at the start or the end.
        half = MAX_TURN_CHARS // 2
        raw = raw[:half] + " " + raw[-half:]
        flags["truncated"] = True
    text = unicodedata.normalize("NFKC", raw)
    out = []
    for ch in text:
        if ch in "\n\r\t\v\f":
            out.append(" ")
            continue
        cat = unicodedata.category(ch)
        if cat == "Cc":                       # control characters, including NUL
            flags["had_control"] = True
            continue
        if cat == "Cf":                       # zero-width and bidi formatting characters
            flags["had_format"] = True
            continue
        if cat in ("Cs", "Co", "Cn"):         # lone surrogates, private use, unassigned
            flags["had_control"] = True
            continue
        if cat == "Mn" and ch in "︎️":
            continue                          # emoji variation selectors
        out.append(ch)
    text = _WS.sub(" ", "".join(out)).strip().lower()
    return text, flags


def _cap_tokens(tokens: list[str]) -> tuple[list[str], bool]:
    tokens = [t[:MAX_TOKEN_CHARS] for t in tokens]
    if len(tokens) <= MAX_TURN_TOKENS:
        return tokens, False
    return tokens[:HEAD_TOKENS] + tokens[-TAIL_TOKENS:], True


def clean_context(context: list[dict]) -> Cleaned:
    """Clean every turn of an already shape-checked context."""
    flags = {"had_control": False, "had_format": False, "truncated": False,
             "injection_pattern": False, "empty_last_customer": False}
    turns: list[Turn] = []
    for item in context[-MAX_TURNS:]:
        text, f = clean_text(item["text"])
        for key, value in f.items():
            flags[key] = flags[key] or value
        tokens, cut = _cap_tokens(text.split(" ") if text else [])
        flags["truncated"] = flags["truncated"] or cut
        if cut:
            text = " ".join(tokens)
        if item["speaker"] == "customer" and (
                _INJECTION.search(text) or _looks_like_system_event(text)):
            flags["injection_pattern"] = True
        turns.append(Turn(item["speaker"], text, tokens))

    customer = [t for t in turns if t.speaker == "customer"]
    if customer and not customer[-1].text:
        flags["empty_last_customer"] = True
    usable = any(any(ch.isalnum() for ch in t.text) for t in turns)
    return Cleaned(turns=turns, flags=flags, usable=usable)
