"""A manager edits policy/policy.yaml. The service must follow the edit without code changes.
This is the kind of change the technical review introduces, so it is tested directly."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import ROOT, project
from triage.pipeline import Triage
from triage.policy import Policy, PolicyError

POLICY = ROOT / "policy" / "policy.yaml"


def edited(tmp_path: Path, change) -> Path:
    data = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    change(data)
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def refund_rows(dev_rows):
    return [r for r in dev_rows if r["flow"] == "product_defect" and r["action"] == "offer-refund"]


def test_removing_an_action_from_a_flow(tmp_path, refund_rows, triage):
    assert refund_rows, "fixture needs product_defect rows whose next step is a refund"
    before = [triage.handle(project(r))["action"] for r in refund_rows]
    assert "offer-refund" in before

    def drop(data):
        data["version"] = "test-no-refund"
        data["flows"]["product_defect"]["permitted"].remove("offer-refund")

    t = Triage(policy_path=edited(tmp_path, drop))
    for row, was in zip(refund_rows, before):
        out = t.handle(project(row))
        assert out["versions"]["policy"] == "test-no-refund"
        if out["flow"] == "product_defect":
            assert out["action"] != "offer-refund"
            if was == "offer-refund":
                # The model still wants a refund; the table forbids it; a person decides.
                assert out["needs_human"] is True
                assert out["policy_conflict"]["suppressed_action"] == "offer-refund"


def test_emptying_a_flow_returns_none(tmp_path, dev_rows):
    def empty(data):
        data["flows"]["troubleshoot_site"]["permitted"] = []

    t = Triage(policy_path=edited(tmp_path, empty))
    rows = [r for r in dev_rows if r["flow"] == "troubleshoot_site"][:40]
    outs = [t.handle(project(r)) for r in rows]
    for out in outs:
        if out["flow"] == "troubleshoot_site":
            assert out["action"] == "none" and out["needs_human"] and out["confidence"] == 0
    assert any(o["flow"] == "troubleshoot_site" for o in outs)


def test_marking_an_action_high_consequence(tmp_path, dev_rows):
    def mark(data):
        data["high_consequence"]["actions"].append("pull-up-account")

    t = Triage(policy_path=edited(tmp_path, mark))
    no_system = [r for r in dev_rows if not any(x["speaker"] == "action" for x in r["context"])][:100]
    for row in no_system:
        assert t.handle(project(row))["action"] != "pull-up-account"


def test_bad_policy_files_are_refused(tmp_path, triage):
    intents, actions = triage.model.classes["intent"], triage.model.classes["action"]
    bad = [
        "flows: {}",
        "on_conflict: maybe\nflows: {a: {intents: [x], permitted: [pull-up-account]}}",
        "flows: {a: {intents: [status]}, b: {intents: [status]}}",
        "high_consequence: {actions: [launch-rocket]}\nflows: {a: {intents: [x]}}",
        "flows: [1, 2",
    ]
    for i, text in enumerate(bad):
        path = tmp_path / f"bad{i}.yaml"
        path.write_text(text, encoding="utf-8")
        with pytest.raises(PolicyError):
            Policy.load(path, intents, actions)
