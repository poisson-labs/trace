"""TR1 to TR8: the clock and the placement (Trace — Spec First Slice, section 6).

Every store here is written through Prove's ``Store`` and read back through it; ``place`` is
called on exactly the frame ``Store.read(run, meta=False, trace="envelope")`` returns.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from proofload.store import Store

from conftest import (
    CELL_A, CELL_B, CS, CS_EVENTS, CS_RECORD, CS_REPLAY, SYNTH_CAP, SYNTH_COUNTS, SYNTH_EVENTS,
    TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, Row, deaths_rows, norm, roots, span, synth_rows, where,
)


def placement(root: Path, run: str, events, by: str = "kind"):  # type: ignore[no-untyped-def]
    from poisson_trace.clock import place

    store = Store(root)
    frame = store.read(run, meta=False, trace="envelope")
    return place(store.manifest(run), frame, store.tally(run), events=frozenset(events), by=by), frame, store


# ---------- TR1 ----------


def test_tr1_a_step_is_a_leaf_on_a_three_deep_chain(make_store) -> None:  # type: ignore[no-untyped-def]
    root, run = make_store([
        Row(CELL_A, "fail", [
            span("root", None, "agent", 1), span("child", "root", "llm", 2),
            span("grandchild", "child", "tool", 3),
        ])
    ])
    placed, _, _ = placement(root, run, ["fail"])
    assert len(placed.rows) == 1
    assert placed.rows[0].index == 1
    assert placed.rows[0].cause == "tool"
    assert placed.rows[0].died is True


def test_tr1_on_tau2_every_span_is_a_leaf_so_index_equals_span_count() -> None:
    placed, frame, _ = placement(TAU2, TAU2_A, TAU2_EVENTS)
    assert len(placed.rows) == 200
    for row, envelope in zip(placed.rows, frame["trace"], strict=True):
        assert row.index == len(envelope["spans"])


# ---------- TR2 ----------


def _tied_leaves(reverse: bool) -> list:  # type: ignore[type-arg]
    spans = [span("b", None, "tool", 5), span("a", None, "llm", 5), span("c", None, "llm", 1)]
    return spans[::-1] if reverse else spans


def test_tr2_equal_start_ns_orders_by_span_id(make_store) -> None:  # type: ignore[no-untyped-def]
    root, run = make_store([Row(CELL_A, "fail", _tied_leaves(reverse=False))])
    placed, _, _ = placement(root, run, ["fail"])
    assert placed.rows[0].index == 3
    # "a" < "b": the last leaf is "b", a tool span
    assert placed.rows[0].cause == "tool"


def test_tr2_reversed_span_list_gives_the_same_clock(make_store) -> None:  # type: ignore[no-untyped-def]
    forward = make_store([Row(CELL_A, "fail", _tied_leaves(reverse=False))])
    backward = make_store([Row(CELL_A, "fail", _tied_leaves(reverse=True))])
    a, _, _ = placement(*forward, ["fail"])
    b, _, _ = placement(*backward, ["fail"])
    assert a.rows == b.rows
    assert dict(a.excluded) == dict(b.excluded)


# ---------- TR3 ----------


def _nested() -> list:  # type: ignore[type-arg]
    return [
        span("root", None, "agent", 1, step_name="plan"),
        span("mid", "root", "agent", 2),
        span("leaf", "mid", "http", 3),
    ]


def test_tr3_cause_by_kind_is_the_kind_of_the_last_leaf(make_store) -> None:  # type: ignore[no-untyped-def]
    root, run = make_store([Row(CELL_A, "fail", _nested())])
    placed, _, _ = placement(root, run, ["fail"], by="kind")
    assert placed.rows[0].cause == "http"


def test_tr3_cause_by_step_walks_to_the_nearest_named_ancestor(make_store) -> None:  # type: ignore[no-untyped-def]
    root, run = make_store([Row(CELL_A, "fail", _nested())])
    placed, _, _ = placement(root, run, ["fail"], by="step")
    assert placed.rows[0].cause == "plan"


def test_tr3_cause_by_step_prefers_the_leaf_own_name(make_store) -> None:  # type: ignore[no-untyped-def]
    spans = _nested()
    spans[2] = span("leaf", "mid", "http", 3, step_name="fetch")
    root, run = make_store([Row(CELL_A, "fail", spans)])
    placed, _, _ = placement(root, run, ["fail"], by="step")
    assert placed.rows[0].cause == "fetch"


def test_tr3_cause_by_step_is_unnamed_when_no_ancestor_carries_a_name(make_store) -> None:  # type: ignore[no-untyped-def]
    root, run = make_store([Row(CELL_A, "fail", [span("root", None, "agent", 1), span("leaf", "root", "llm", 2)])])
    placed, _, _ = placement(root, run, ["fail"], by="step")
    assert placed.rows[0].cause == "unnamed"


def test_tr3_walk_stops_at_an_orphan(make_store) -> None:  # type: ignore[no-untyped-def]
    # "orphan" names a parent that is not in the trace; the walk reaches it and stops there.
    named = [span("orphan", "missing", "agent", 1, step_name="orphan_step"), span("leaf", "orphan", "llm", 2)]
    unnamed = [span("orphan", "missing", "agent", 1), span("leaf", "orphan", "llm", 2)]
    r1 = make_store([Row(CELL_A, "fail", named)])
    r2 = make_store([Row(CELL_A, "fail", unnamed)])
    assert placement(*r1, ["fail"], by="step")[0].rows[0].cause == "orphan_step"
    assert placement(*r2, ["fail"], by="step")[0].rows[0].cause == "unnamed"


# ---------- TR4 ----------


def test_tr4_event_outcome_dies_and_other_outcome_ends_at_the_last_step(make_store) -> None:  # type: ignore[no-untyped-def]
    root, run = make_store([
        Row(CELL_A, "fail", roots(["llm"] * 4), replicate_index=0),
        Row(CELL_A, "ok", roots(["llm"] * 6), replicate_index=1),
        Row(CELL_A, "other_fail", roots(["llm"] * 2), replicate_index=2),
    ])
    placed, _, _ = placement(root, run, ["fail"])
    by_index = {p.index: p for p in placed.rows}
    assert by_index[4].reason == "died" and by_index[4].died is True
    assert by_index[6].reason == "ended" and by_index[6].died is False
    assert by_index[2].reason == "ended" and by_index[2].died is False


def test_tr4_at_risk_counts_died_and_censored_alike(synth) -> None:  # type: ignore[no-untyped-def]
    root, run = synth
    result = where(root, run, SYNTH_EVENTS, "--json")
    assert result.code == 0, result.text
    curve = result.json()["curve"]
    placed, _, _ = placement(root, run, SYNTH_EVENTS)
    assert [c["step"] for c in curve] == [2]
    assert curve[0]["at_risk"] == sum(1 for p in placed.rows if p.index >= 2) == 4
    assert curve[0]["died"] == 1


def test_tr4_at_risk_on_tau2_matches_the_placement_at_every_death_step() -> None:
    result = where(TAU2, TAU2_A, TAU2_EVENTS, "--json")
    assert result.code == 0, result.text
    placed, _, _ = placement(TAU2, TAU2_A, TAU2_EVENTS)
    for row in result.json()["curve"]:
        assert row["at_risk"] == sum(1 for p in placed.rows if p.index >= row["step"])
        assert row["died"] == sum(1 for p in placed.rows if p.died and p.index == row["step"])


# ---------- TR5 ----------


def test_tr5_timeout_is_censored_never_a_death(synth) -> None:  # type: ignore[no-untyped-def]
    placed, frame, _ = placement(*synth, SYNTH_EVENTS)
    timed_out = [p for p in placed.rows if p.reason == "timed out"]
    assert len(timed_out) == 1
    assert timed_out[0].died is False
    assert timed_out[0].index == 2


def test_tr5_capped_row_is_censored_even_when_its_outcome_is_an_event(synth) -> None:  # type: ignore[no-untyped-def]
    # Sole catch for a build that checks died before capped.
    placed, _, _ = placement(*synth, SYNTH_EVENTS)
    capped = [p for p in placed.rows if p.reason == "capped"]
    assert len(capped) == 1
    assert capped[0].died is False
    assert capped[0].index == SYNTH_CAP
    assert sum(p.died for p in placed.rows) == 1


def test_tr5_the_cap_counts_spans_not_leaves(make_store) -> None:  # type: ignore[no-untyped-def]
    # four spans, two leaves, cap four: capped, censored at step 2
    nested = [
        span("root", None, "agent", 1), span("c1", "root", "llm", 2),
        span("c2", "root", "tool", 3), span("g1", "c1", "llm", 4),
    ]
    root, run = make_store([Row(CELL_A, "fail", nested)], cap=4)
    placed, _, _ = placement(root, run, ["fail"])
    assert placed.rows[0].reason == "capped"
    assert placed.rows[0].index == 2
    assert placed.rows[0].died is False


def test_tr5_timeout_beats_the_cap(make_store) -> None:  # type: ignore[no-untyped-def]
    root, run = make_store([Row(CELL_A, None, roots(["llm"] * 3), error="timeout")], cap=3)
    placed, _, _ = placement(root, run, ["fail"])
    assert placed.rows[0].reason == "timed out"
    assert placed.cap == 3


# ---------- TR6 ----------


def test_tr6_no_cap_means_no_capped_row(make_store) -> None:  # type: ignore[no-untyped-def]
    root, run = make_store(synth_rows(), cap=None)
    placed, _, _ = placement(root, run, SYNTH_EVENTS)
    assert placed.cap is None
    assert all(p.reason != "capped" for p in placed.rows)
    # the row at the cap now dies at its last step
    assert sum(p.died for p in placed.rows) == 2


def test_tr6_cap_absent_from_the_manifest_means_no_capped_row(tmp_path: Path) -> None:
    from proofload.store import RunManifest

    from conftest import build_store

    root = tmp_path / "nocap"
    build_store(root, "run", synth_rows(), cap=None)
    manifest = Store(root).manifest("run")
    bare = RunManifest(**{**manifest.to_dict(), "environment": {}, "declared": None})
    store = Store(root)
    from poisson_trace.clock import place

    placed = place(bare, store.read("run", meta=False, trace="envelope"), store.tally("run"),
                   events=frozenset(SYNTH_EVENTS), by="kind")
    assert placed.cap is None
    assert all(p.reason != "capped" for p in placed.rows)


# ---------- TR7 ----------


def test_tr7_the_four_exclusion_reasons_are_the_only_ones_and_all_print(synth) -> None:  # type: ignore[no-untyped-def]
    from poisson_trace.clock import EXCLUSIONS, REASONS

    placed, _, _ = placement(*synth, SYNTH_EVENTS)
    assert tuple(placed.excluded) == EXCLUSIONS == (
        "no trace", "unreadable trace", "no leaf span", "no outcome, not a timeout",
    )
    assert REASONS == ("died", "ended", "timed out", "capped")
    assert dict(placed.excluded) == SYNTH_COUNTS["excluded"]
    assert {p.reason for p in placed.rows} <= set(REASONS)


@pytest.mark.parametrize(
    "bad",
    [
        {"spans": [{"span_id": 1, "start_ns": 5}]},          # span_id not a string
        {"spans": [{"span_id": "x", "start_ns": "5"}]},      # start_ns not an integer
        {"spans": [{"span_id": "x", "start_ns": True}]},     # a bool is not an integer
        {"spans": ["not a mapping"]},                         # a span that is not a mapping
        {"spans": "nope"},                                    # spans not a list
        ["not", "a", "mapping"],                              # the envelope itself
    ],
)
def test_tr7_unreadable_trace_is_excluded_by_that_reason(synth, bad) -> None:  # type: ignore[no-untyped-def]
    # Prove's writer cannot store an unreadable envelope, so the frame it returns is doctored
    # in memory: one placed row's envelope is replaced and nothing under the store changes.
    from poisson_trace.clock import place

    root, run = synth
    store = Store(root)
    frame = store.read(run, meta=False, trace="envelope")
    tally = store.tally(run)
    before = place(store.manifest(run), frame, tally, events=frozenset(SYNTH_EVENTS), by="kind")
    target = next(i for i, (o, t) in enumerate(zip(frame["outcome"], frame["trace"])) if o == "ok" and t is not None)
    frame.at[target, "trace"] = bad
    after = place(store.manifest(run), frame, tally, events=frozenset(SYNTH_EVENTS), by="kind")
    assert after.excluded["unreadable trace"] == before.excluded["unreadable trace"] + 1 == 1
    assert len(after.rows) == len(before.rows) - 1
    assert sum(after.excluded.values()) == sum(before.excluded.values()) + 1


def test_tr7_excluded_rows_appear_in_no_curve(synth) -> None:  # type: ignore[no-untyped-def]
    root, run = synth
    result = where(root, run, SYNTH_EVENTS, "--json")
    assert result.code == 0, result.text
    data = result.json()
    assert data["run"]["placement"]["placed"] == 4
    assert all(row["at_risk"] <= 4 for row in data["curve"])


# ---------- TR8 ----------


def _reconcile(root: Path, run: str, events) -> None:  # type: ignore[no-untyped-def]
    placed, frame, store = placement(root, run, events)
    tally = store.tally(run)
    assert placed.tally == tally
    excluded = sum(placed.excluded.values())
    assert len(placed.rows) + excluded == tally.rows
    timed_out_placed = sum(1 for p in placed.rows if p.reason == "timed out")
    timed_out_no_trace = sum(
        1 for o, e, t in zip(frame["outcome"], frame["error"], frame["trace"])
        if o is None and e == "timeout" and t is None
    )
    assert timed_out_placed + timed_out_no_trace == tally.timed_out
    assert placed.excluded["no outcome, not a timeout"] == tally.infra + tally.other
    result = where(root, run, events, "--json")
    assert result.code == 0, result.text
    data = result.json()
    assert data["run"]["tally"] == tally.to_dict()
    text = norm(where(root, run, events).out)
    for label, value in (
        ("rows", tally.rows), ("with outcome", tally.with_outcome), ("timed out", tally.timed_out),
        ("infra", tally.infra), ("other", tally.other),
    ):
        assert f"{label} {value}" in text, (label, value)


def test_tr8_reconciliation_on_the_synthetic_store(synth) -> None:  # type: ignore[no-untyped-def]
    _reconcile(*synth, SYNTH_EVENTS)


def test_tr8_reconciliation_with_a_timed_out_row_that_has_no_trace(make_store) -> None:  # type: ignore[no-untyped-def]
    rows = synth_rows() + [Row(CELL_A, None, None, error="timeout", replicate_index=3)]
    root, run = make_store(rows, cap=SYNTH_CAP)
    placed, _, store = placement(root, run, SYNTH_EVENTS)
    assert store.tally(run).timed_out == 2
    assert sum(1 for p in placed.rows if p.reason == "timed out") == 1
    assert placed.excluded["no trace"] == 2
    _reconcile(root, run, SYNTH_EVENTS)


@pytest.mark.parametrize("root,run,events", [
    (TAU2, TAU2_A, TAU2_EVENTS), (TAU2, TAU2_B, TAU2_EVENTS),
    (CS, CS_RECORD, CS_EVENTS), (CS, CS_REPLAY, CS_EVENTS),
])
def test_tr8_reconciliation_on_the_committed_fixtures(root, run, events) -> None:  # type: ignore[no-untyped-def]
    _reconcile(root, run, events)


def test_tr8_a_placement_that_drops_a_row_silently_is_caught(make_store) -> None:  # type: ignore[no-untyped-def]
    # Sole catch: three rows in, three rows accounted for, whatever their reasons.
    root, run = make_store(deaths_rows([2, 3]) + [Row(CELL_B, "ok", roots(["tool"]), replicate_index=5)])
    placed, _, store = placement(root, run, ["fail"])
    assert len(placed.rows) + sum(placed.excluded.values()) == store.tally(run).rows == 3
