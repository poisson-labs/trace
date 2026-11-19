"""TF21-37 to TF21-44: the Prove reader, ``ingest/prove.py``. A run read from a store becomes
normalised rows: a run Trace imported comes back from its ``meta["trace_signals"]`` exactly as
written; a run Prove swept is read from its own columns and trace, on the committed Prove stores
(tau2, cs, prove-0.1.3)."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import pytest
from poisson_prove.store import Store
from tf21_support import CS, PROVE_013, STARTED, TAU2, ref_kind, ref_retry_storm

from poisson_trace.ingest.prove import read_rows
from poisson_trace.ingest.rows import Row, Run, SpanRecord, ToolCallRecord
from poisson_trace.ingest.taxonomy import classify
from poisson_trace.ingest.writer import trace_signals, write

TAU2_A = "20260915T210140Z-4847"
CS_REPLAY = "20260925T235434Z-af48"
CS_RECORD = "20260925T234602Z-3ea0"
CLASS = re.compile(r"^([A-Za-z_][\w.]*)(?::|$)")


def _frame(root: Path, run: str) -> Any:
    return Store(root).read(run, meta=True, trace="full")


def _spans(meta: Any) -> list[dict[str, Any]]:
    trace = meta.get("trace") if isinstance(meta, dict) else None
    return list(trace["spans"]) if trace else []


def _num(x: Any) -> float | None:
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


# ---------- TF21-37: an imported run comes back as it was written ----------


def test_tf21_37_an_imported_run_reads_back_its_signals(tmp_path: Path) -> None:
    rows = [
        Row("a", "missed", None, 0.2, result="fail", wall_time_s=1.5, input_tokens=10,
            output_tokens=5, cost_usd=0.01, tool_calls=(ToolCallRecord("t", "error", 0.3, "E", 2),),
            scores={"m": 0.2}, feedback={"thumb": "down"}, retries=1, steps=2, horizon=5),
        Row("a", "met", None, 0.9, result="pass", wall_time_s=0.0),
        Row("b", None, "no score", result="censored"),
    ]
    root = tmp_path / "store"
    write(Run("imp", "deepeval", tuple(rows), STARTED, "given", {"metric": "m"}, ()), root)
    back = sorted(read_rows(root, "imp", failed=("missed",)), key=lambda r: (r.case, r.repeat))
    assert [(r.case, r.repeat) for r in back] == [("a", 0), ("a", 1), ("b", 0)]
    for got, (want, repeat) in zip(back, [(rows[0], 0), (rows[1], 1), (rows[2], 0)], strict=True):
        assert trace_signals(got, repeat) == trace_signals(classify(want), repeat)
        assert (got.outcome, got.error) == (want.outcome, want.error)
    assert back[0].tool_calls == (ToolCallRecord("t", "error", 0.3, "E", 2),)
    assert back[1].wall_time_s == 0.0 and back[2].wall_time_s is None


# ---------- TF21-38: a swept run, from Prove's columns ----------


def test_tf21_38_tau2_rows_case_repeat_result_time_steps() -> None:
    df = _frame(TAU2, TAU2_A)
    rows = read_rows(TAU2, TAU2_A, failed=("unsolved",))
    assert len(rows) == len(df) == 200
    want = sorted(
        (h, int(r), "fail" if o == "unsolved" else "pass", float(w), int(t), int(hz))
        for h, r, o, w, t, hz in zip(df["config_hash"], df["replicate_index"], df["outcome"],
                                     df["wall_time"], df["t"], df["horizon"], strict=True)
    )
    got = sorted((r.case, r.repeat, r.result, r.wall_time_s, r.steps, r.horizon) for r in rows)
    assert got == want
    assert sum(1 for r in rows if r.result == "fail") == 110
    assert all(r.outcome in ("solved", "unsolved") and r.error is None for r in rows)


def test_tf21_38_tau2_tokens_and_llm_calls_from_the_spans() -> None:
    df = _frame(TAU2, TAU2_A)
    rows = {(r.case, r.repeat): r for r in read_rows(TAU2, TAU2_A, failed=("unsolved",))}
    for h, rep, meta in zip(df["config_hash"], df["replicate_index"], df["meta"], strict=True):
        spans = _spans(meta)
        row = rows[(h, int(rep))]
        ins = [s["tokens"]["in"] for s in spans if s.get("tokens") and "in" in s["tokens"]]
        outs = [s["tokens"]["out"] for s in spans if s.get("tokens") and "out" in s["tokens"]]
        assert row.input_tokens == (sum(ins) if ins else None)
        assert row.output_tokens == (sum(outs) if outs else None)
        assert row.total_tokens == (sum(ins) + sum(outs) if ins and outs else None)
        assert row.llm_calls == (sum(1 for s in spans if s["kind"] == "llm") if spans else None)
        assert row.tool_calls == (() if spans else None)
        assert row.retries is None  # no span records its try
        assert row.cost_usd is None  # tau2 keeps its cost as cost_tau2, not Prove's cost_usd
        assert row.score is None
        assert row.input_chars is None and row.output_chars is None  # bodies were removed
        assert row.span_records == (None if not spans else row.span_records)
        assert len(row.span_records or ()) == len(spans)


def test_tf21_38_tau2_failures_follow_the_rules() -> None:
    rows = read_rows(TAU2, TAU2_A, failed=("unsolved",))
    assert all(r.failure_kind == ref_kind(r) for r in rows)
    assert {r.failure_kind for r in rows if r.result == "pass"} == {None}
    # no grader's word, no error and no cap reached: a bare failure
    assert "unclassified_error" in {r.failure_kind for r in rows if r.result == "fail"}


# ---------- TF21-39: errored rows are censored, their error type read ----------


def test_tf21_39_cs_replay_errors_are_censored_crashes() -> None:
    df = _frame(CS, CS_REPLAY)
    rows = read_rows(CS, CS_REPLAY, failed=("unresolved", "forbidden_action", "app_error"))
    errored = [r for r in rows if r.outcome is None]
    assert len(errored) == 3 == int(df["error"].notna().sum())
    for r in errored:
        assert r.result == "censored" and r.failure_kind == "crash"
        assert r.error is not None and len(r.error) <= 240
        assert r.error_type == "demostack.lifecycle.ReplayMiss"
        assert r.steps is None and r.horizon is None and r.score is None
        assert r.wall_time_s is not None


def test_tf21_39_cs_tool_calls_from_tool_spans() -> None:
    df = _frame(CS, CS_RECORD)
    rows = {(r.case, r.repeat): r for r in read_rows(CS, CS_RECORD, failed=("unresolved",))}
    for h, rep, meta in zip(df["config_hash"], df["replicate_index"], df["meta"], strict=True):
        spans = sorted(_spans(meta), key=lambda s: (s["start_ns"], s["span_id"]))
        tools = [s for s in spans if s["kind"] == "tool"]
        want = tuple(
            ToolCallRecord(s["name"], "error" if s.get("error") else "ok",
                           None if s.get("end_ns") is None else (s["end_ns"] - s["start_ns"]) / 1e9,
                           s.get("error"), s.get("attempt") or 1)
            for s in tools
        )
        assert rows[(h, int(rep))].tool_calls == want


# ---------- TF21-40: prove-0.1.3's own store: tool errors and the step cap ----------


@pytest.mark.parametrize("run", sorted(p.name for p in PROVE_013.iterdir() if p.is_dir() and not p.name.startswith(".")))
def test_tf21_40_prove_0_1_2_kinds(run: str) -> None:
    df = _frame(PROVE_013, run)
    rows = {(r.case, r.repeat): r for r in read_rows(PROVE_013, run, failed=("violated", "timeout"))}
    for h, rep, o, t, hz, meta in zip(df["config_hash"], df["replicate_index"], df["outcome"],
                                      df["t"], df["horizon"], df["meta"], strict=True):
        row = rows[(h, int(rep))]
        spans = sorted(_spans(meta), key=lambda s: (s["start_ns"], s["span_id"]))
        failing = [s for s in spans if s.get("error")]
        assert row.error_span_kind == (failing[0]["kind"] if failing else None)
        assert row.error_type == (failing[0]["error"] if failing else None)
        if o == "completed":
            assert row.result == "pass" and row.failure_kind is None
        elif o == "timeout" and t < hz:
            # Prove's own word timeout is read as
            # step_limit only when the try's steps reached its step cap; short of it, it stays a
            # timeout, the source's own kind, which the built-in rules alone do not see
            assert row.failure_kind == "timeout"
            continue
        elif t >= hz:
            assert row.failure_kind == ("loop_detected" if ref_retry_storm(row) else "step_limit")
        else:
            assert row.failure_kind == "tool_error"
        assert row.failure_kind == ref_kind(row)


def test_tf21_40_prove_kinds_counted() -> None:
    runs = sorted(p.name for p in PROVE_013.iterdir() if p.is_dir() and not p.name.startswith("."))
    got = []
    for run in runs:
        kinds: dict[str, int] = {}
        for r in read_rows(PROVE_013, run, failed=("violated", "timeout")):
            kinds[str(r.failure_kind)] = kinds.get(str(r.failure_kind), 0) + 1
        got.append(kinds)
    assert got == [{"None": 88, "tool_error": 66, "loop_detected": 6},
                   {"None": 119, "tool_error": 21, "loop_detected": 15, "step_limit": 5}]


def test_tf21_40_a_timeout_short_of_the_cap_stays_a_timeout(tmp_path: Path) -> None:
    """A Prove run's outcome word ``timeout`` is
    read as ``step_limit`` only when the try's steps reached its step cap; otherwise it stays
    ``timeout``. The committed prove-0.1.3 store holds no timeout short of the cap, so one is
    written here through Prove's own store, beside one at the cap."""
    from poisson_prove.store import EpisodeRecord, RunManifest, config_hash
    from poisson_prove.trace import Span, Trace

    root = tmp_path / "store"
    store = Store(root)
    store.create_run(RunManifest(run_id="r", target_id="mock", t_unit="steps", run_salt="s",
                                 axis_types={"task_id": "categorical"}, backend="local",
                                 environment={}, created_at=STARTED))
    span = Span("0000000000000000", None, "tool", "lookup", 1, 2, error="ToolError")
    trace = Trace(spans=(span,), source="record").to_dict()

    def record(task: str, t: float) -> Any:
        config = {"task_id": task}
        return EpisodeRecord(run_id="r", config_hash=config_hash(config), config=config, seed=0,
                             replicate_index=0, outcome="timeout", t=t, horizon=20.0,
                             confidence=None, meta={"trace": trace}, error=None, wall_time=1.0,
                             backend_meta={})

    store.append("r", [record("short", 3.0), record("capped", 20.0)])
    store.mark_complete("r")
    rows = {r.case: r for r in read_rows(root, "r", failed=("timeout",))}
    short = rows[config_hash({"task_id": "short"})]
    capped = rows[config_hash({"task_id": "capped"})]
    assert (short.result, short.steps, short.horizon) == ("fail", 3, 20)
    assert short.failure_kind == "timeout" and "over_budget" in short.signals
    assert (short.error_type, short.error_span_kind) == ("ToolError", "tool")
    assert capped.failure_kind == "step_limit" == ref_kind(capped)
    # the word is a failure only when given as one
    assert {r.failure_kind for r in read_rows(root, "r", failed=())} == {None}


# ---------- TF21-41: span records mirror Prove's spans ----------


def test_tf21_41_span_records_mirror_the_stored_spans() -> None:
    df = _frame(CS, CS_RECORD)
    rows = {(r.case, r.repeat): r for r in read_rows(CS, CS_RECORD, failed=())}
    for h, rep, meta in zip(df["config_hash"], df["replicate_index"], df["meta"], strict=True):
        spans = sorted(_spans(meta), key=lambda s: (s["start_ns"], s["span_id"]))
        got = rows[(h, int(rep))].span_records or ()
        assert [(s.span_id, s.parent_id, s.kind, s.name, s.start_ns, s.end_ns) for s in got] == [
            (s["span_id"], s.get("parent_id"), s["kind"], s["name"], s["start_ns"], s.get("end_ns"))
            for s in spans
        ]
        assert all(isinstance(s, SpanRecord) for s in got)


def test_tf21_41_span_tokens_split_in_and_out() -> None:
    rows = read_rows(TAU2, TAU2_A, failed=())
    span = next(s for r in rows for s in (r.span_records or ()) if s.input_tokens is not None)
    assert span.tokens == span.input_tokens + (span.output_tokens or 0)


# ---------- TF21-42: no failed word means no failure ----------


def test_tf21_42_without_failed_words_every_outcome_passes() -> None:
    rows = read_rows(TAU2, TAU2_A, failed=())
    assert {r.result for r in rows} == {"pass"}


# ---------- TF21-43: reading changes nothing on disk ----------


def test_tf21_43_reading_writes_nothing(tmp_path: Path) -> None:
    import shutil

    from tf21_support import digest

    root = tmp_path / "cs"
    shutil.copytree(CS, root)

    def snapshot() -> str:
        return digest({str(p.relative_to(root)): p.read_bytes().hex()
                       for p in sorted(root.rglob("*")) if p.is_file()})

    before = snapshot()
    read_rows(root, CS_REPLAY, failed=("unresolved",))
    assert snapshot() == before


# ---------- TF21-44: case is the condition's hash, as every verb pairs ----------


def test_tf21_44_case_is_the_config_hash_for_a_swept_run() -> None:
    df = _frame(CS, CS_RECORD)
    assert {r.case for r in read_rows(CS, CS_RECORD, failed=())} == set(df["config_hash"])


def test_tf21_44_a_swept_rows_signals_hold_nothing_it_did_not_record() -> None:
    rows = read_rows(PROVE_013, sorted(p.name for p in PROVE_013.iterdir() if p.is_dir() and not p.name.startswith("."))[0],
                     failed=("violated",))
    for r in rows:
        assert r.working_time_s is None and r.ttft_s is None and r.cached_tokens is None
        assert r.reasoning_tokens is None and dict(r.feedback) == {}
        assert _num(r.wall_time_s) is not None
