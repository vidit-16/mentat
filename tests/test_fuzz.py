"""Property-based fuzzing: any valid envelope gives a schema-valid answer, quickly."""
from __future__ import annotations

import time

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from triage.respond import schema_valid

speaker = st.sampled_from(["customer", "agent", "action"])
text = st.one_of(
    st.text(max_size=400),
    st.text(alphabet=st.characters(min_codepoint=0, max_codepoint=0x10FFFF), max_size=200),
    st.text(alphabet=st.sampled_from("​‌‍‮‭⁦﻿́\x00 a"),
            max_size=300),
    st.builds(lambda w, n: (w + " ") * n, st.sampled_from(["refund", "ignore instructions", "x"]),
              st.integers(0, 3000)),
)
turn = st.fixed_dictionaries({"speaker": speaker, "text": text})
envelope = st.fixed_dictionaries(
    {"id": st.text(min_size=1, max_size=40), "context": st.lists(turn, max_size=10)},
    optional={"turn_index": st.integers(-5, 10 ** 12)})


@settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(envelope)
def test_any_envelope(triage, obj):
    started = time.perf_counter()
    out = triage.handle(obj)
    assert time.perf_counter() - started < 2.0
    assert schema_valid(out)
    assert out["id"] == obj["id"]
    if out["action"] != "none":
        assert out["action"] in triage.actions
