"""Read the system-written `action` turns as a record of which procedure steps already ran.

An `action` turn looks like "account has been pulled up for sanya afzal." It is written by the
agent desktop, not by the customer. Whether a turn is an action turn is decided by the
envelope's `speaker` field and never by the words in it.
"""
from __future__ import annotations

import re

# (pattern, event name, action label the event corresponds to)
_RULES: list[tuple[re.Pattern, str, str | None]] = [
    (re.compile(r"^account has been pulled up"), "pull_up", "pull-up-account"),
    (re.compile(r"^identity verification in prog"), "verify", "verify-identity"),
    (re.compile(r"^purchase validation in prog"), "validate", "validate-purchase"),
    (re.compile(r"^searching the faq pages"), "search_faq", "search-faq"),
    (re.compile(r"^querying the system for (?P<v>.*)"), "query", None),
    (re.compile(r"^querying the system"), "query", None),
    (re.compile(r"^agent is looking"), "looking", None),
    (re.compile(r"^system action: search (?P<v>\w+)"), "search_topic", None),
    (re.compile(r"^system action: (?P<v>.*)"), "sys", None),
    (re.compile(r"^membership level of ?(?P<v>.*?) ?has been noted"), "membership", "membership"),
    (re.compile(r"^shipping status of ?(?P<v>.*?) ?has been noted"), "shipping", "shipping-status"),
    (re.compile(r"^details of ?(?P<v>.*?) ?have been entered"), "details", "enter-details"),
    (re.compile(r"^a reason of ?(?P<v>.*?) ?has been recorded"), "reason", "record-reason"),
    (re.compile(r"^order has been updated with (?P<v>.*)"), "order_updated", "update-order"),
    (re.compile(r"^account has been updated with (?P<v>.*)"), "account_updated", "update-account"),
    (re.compile(r"^faq answer related to (?P<v>\w+)"), "faq_selected", "select-faq"),
    (re.compile(r"^a refund has been made"), "refund", "offer-refund"),
    (re.compile(r"^a promo code has been created"), "promo", "promo-code"),
    (re.compile(r"^a purchase of ?.*was made"), "purchase", "make-purchase"),
    (re.compile(r"^a password has been generated"), "password", "make-password"),
    (re.compile(r"^a link will be sent"), "link", "send-link"),
    (re.compile(r"team has been notified|department has been notified|has been notified"),
     "notified", "notify-team"),
]

_DIGITS = re.compile(r"\d+")
_WORD = re.compile(r"[a-z<>_']+")


def parse_event(text: str) -> tuple[str, list[str], str | None]:
    """Return (event name, up to two value tokens, matching action label or None)."""
    for pattern, name, action in _RULES:
        m = pattern.search(text)
        if m:
            value = (m.groupdict().get("v") or "").strip()
            value = _DIGITS.sub("#", value)
            return name, _WORD.findall(value)[:2] or (["#"] if "#" in value else []), action
    words = _WORD.findall(_DIGITS.sub("", text))[:4]
    return ("other_" + "_".join(words)) if words else "other", [], None


def done_actions(turns) -> set[str]:
    """Action labels for which the visible context shows a completed step."""
    done = set()
    for turn in turns:
        if turn.speaker == "action":
            action = parse_event(turn.text)[2]
            if action:
                done.add(action)
    return done
