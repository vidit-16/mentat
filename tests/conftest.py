"""Shared fixtures. Tests run against the real model in models/. Set TRIAGE_STUB=1 to test
only the input handling with a fixed-answer stand-in (used before a model existed)."""
from __future__ import annotations

import gzip
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
REF = ROOT / "reference"


def load_jsonl(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def project(row: dict) -> dict:
    """What the reviewer sends: the same allowlist as reference/evaluation_inputs.py."""
    out = {k: row[k] for k in ("id", "turn_index") if k in row}
    out["context"] = [{k: t[k] for k in ("speaker", "text") if k in t} for t in row["context"]]
    return out


class StubTriage:
    """Runs the real input handling and feature extraction, then returns a fixed answer."""
    versions = {"model": "stub", "policy": "stub"}

    def handle(self, obj: dict) -> dict:
        from triage import respond
        from triage.envelope import check_context, turn_index
        from triage.features import extract
        from triage.sanitise import clean_context
        rid = obj["id"]
        try:
            context, problem, _ = check_context(obj)
            if problem:
                out = respond.abstain(rid, problem)
            else:
                cleaned = clean_context(context)
                if not cleaned.usable:
                    out = respond.abstain(rid, "no readable text in the conversation")
                else:
                    extract(cleaned.turns, turn_index(obj))
                    out = respond.build(rid, "status", "pull-up-account", 0.5, True,
                                        frozenset(["status"]), frozenset(["pull-up-account"]))
        except Exception:                                   # noqa: BLE001
            out = respond.abstain(rid, "internal error", code="internal_error")
        out.update(latency_ms=0.0, cost_usd=0.0, versions=self.versions)
        return out


@pytest.fixture(scope="session")
def triage():
    if os.environ.get("TRIAGE_STUB") == "1":
        return StubTriage()
    if not (ROOT / "models" / "model.npz").exists():
        pytest.skip("no trained model in models/; run scripts/reproduce.sh train")
    from triage.pipeline import Triage
    return Triage()


@pytest.fixture(scope="session")
def is_stub():
    return os.environ.get("TRIAGE_STUB") == "1"


@pytest.fixture(scope="session")
def client(triage):
    from starlette.testclient import TestClient
    from triage.app import create_app
    with TestClient(create_app(triage), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="session")
def dev_rows():
    return load_jsonl(REF / "dev.jsonl")


@pytest.fixture(scope="session")
def noisy_rows():
    return load_jsonl(REF / "dev_noisy.jsonl")


@pytest.fixture(scope="session")
def hostile_rows():
    return load_jsonl(REF / "hostile.jsonl")
