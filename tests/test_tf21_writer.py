"""TF21-25 to TF21-33: the writer, ``ingest/writer.py``.

A Row becomes one of Prove 0.1.2's episode records with no change to Prove: ``wall_time``,
``t``, ``horizon`` and ``confidence`` from the signals where recorded, the
``poisson.trace-signals/1`` record in ``meta["trace_signals"]`` with ``None`` kept as null,
``meta["cost_usd"]`` where a cost was recorded, ``meta["import"]`` as today, and an
``events.jsonl`` in Prove's own event shape. Every column a Trace verb reads stays as today:
``test_tf21_unchanged.py`` pins those bytes for every committed import."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import pytest
from poisson_prove.store import Store
from tf21_support import (
    ERROR_MAX,
    RECORD_KEYS,
    RECORD_SCHEMA,
    STARTED,
    TOOL_CALL_KEYS,
    frame,
    records,
)

from poisson_trace.ingest.rows import Row, Run, ToolCallRecord
from poisson_trace.ingest.writer import trace_signals, write


def make_run(rows: list[Row], name: str = "run", tool: str = "deepeval") -> Run:
    return Run(
        name=name, tool=tool, rows=tuple(rows), started=STARTED, started_from="given",
        declared={"metric": "Score", "cut": 0.5, "side": "below", "case": "name"},
        files=({"name": "results.json", "sha256": "ab" * 32},),
    )


FULL = Row(
    "case_042", "missed", None, 0.0,
    result="fail", failure_kind="tool_error", error_type="ToolTimeoutError",
    error_span_kind="tool", wall_time_s=4.82, working_time_s=4.10, ttft_s=0.61,
    input_chars=1840, output_chars=312, input_tokens=620, output_tokens=95, cached_tokens=512,
    reasoning_tokens=0, cost_usd=0.0024, steps=3, horizon=8, llm_calls=2,
    tool_calls=(ToolCallRecord("search_docs", "ok", 0.42, None, 1),
                ToolCallRecord("run_sql", "error", 2.01, "ToolTimeoutError", 2)),
    retries=1, scores={"exact_match": 0.0, "faithfulness": 0.85}, feedback={"thumb": "down"},
    signals=("retry_storm",),
)
BARE = Row("case_007", "met", None)


def _stored(tmp_path: Path, rows: list[Row]) -> tuple[Path, Any]:
    root = tmp_path / "store"
    write(make_run(rows), root)
    df = frame(root, "run")
    return root, df


# ---------- TF21-25: the record ----------


def test_tf21_25_the_signals_record_keys_and_values() -> None:
    record = trace_signals(FULL, 0)
    assert tuple(record) == RECORD_KEYS
    assert record == {
        "schema": RECORD_SCHEMA, "case": "case_042", "repeat": 0, "outcome": "fail",
        "failure_kind": "tool_error", "error_type": "ToolTimeoutError", "error_span_kind": "tool",
        "wall_time_s": 4.82, "working_time_s": 4.10, "ttft_s": 0.61, "input_chars": 1840,
        "output_chars": 312, "input_tokens": 620, "output_tokens": 95, "cached_tokens": 512,
        "reasoning_tokens": 0, "total_tokens": 715, "cost_usd": 0.0024, "steps": 3, "horizon": 8,
        "llm_calls": 2, "tool_call_count": 2, "tool_error_count": 1,
        "tool_calls": [
            {"name": "search_docs", "status": "ok", "duration_s": 0.42, "error_type": None,
             "attempt": 1},
            {"name": "run_sql", "status": "error", "duration_s": 2.01,
             "error_type": "ToolTimeoutError", "attempt": 2},
        ],
        "retries": 1, "score": 0.0, "scores": {"exact_match": 0.0, "faithfulness": 0.85},
        "feedback": {"thumb": "down"}, "signals": ["retry_storm"],
    }
    assert all(tuple(c) == TOOL_CALL_KEYS for c in record["tool_calls"])


def test_tf21_25_a_row_that_records_nothing_is_all_null() -> None:
    record = trace_signals(BARE, 3)
    assert tuple(record) == RECORD_KEYS
    assert record["schema"] == RECORD_SCHEMA and record["case"] == "case_007"
    assert record["repeat"] == 3
    for key in RECORD_KEYS[3:]:
        if key in ("scores", "feedback"):
            assert record[key] == {}, key
        elif key == "signals":
            assert record[key] == [], key
        else:
            assert record[key] is None, key


def test_tf21_25_tool_counts_follow_tool_calls_none_and_empty_apart() -> None:
    none = trace_signals(Row("c", "met", None), 0)
    empty = trace_signals(Row("c", "met", None, tool_calls=()), 0)
    assert (none["tool_call_count"], none["tool_error_count"], none["tool_calls"]) == (None, None, None)
    assert (empty["tool_call_count"], empty["tool_error_count"], empty["tool_calls"]) == (0, 0, [])


# ---------- TF21-26: the record is stored in meta, nulls kept ----------


def test_tf21_26_meta_holds_the_record_and_the_import(tmp_path: Path) -> None:
    _, df = _stored(tmp_path, [FULL, BARE])
    metas = {m["trace_signals"]["case"]: m for m in df["meta"]}
    assert metas["case_042"]["trace_signals"] == json.loads(json.dumps(trace_signals(FULL, 0)))
    assert metas["case_007"]["trace_signals"] == json.loads(json.dumps(trace_signals(BARE, 0)))
    assert metas["case_042"]["import"] == {"score": 0.0}
    assert metas["case_007"]["import"] == {"score": None}
    assert metas["case_007"]["trace_signals"]["wall_time_s"] is None


def test_tf21_26_cost_usd_sits_at_metas_top_only_where_recorded(tmp_path: Path) -> None:
    _, df = _stored(tmp_path, [FULL, BARE])
    metas = {m["trace_signals"]["case"]: m for m in df["meta"]}
    assert metas["case_042"]["cost_usd"] == 0.0024
    assert "cost_usd" not in metas["case_007"]
    assert set(metas["case_007"]) == {"import", "trace_signals"}


def test_tf21_26_repeat_in_the_record_is_the_replicate_written(tmp_path: Path) -> None:
    rows = [Row("a", "met", None), Row("b", "met", None), Row("a", "missed", None),
            Row("a", "met", None)]
    root = tmp_path / "store"
    write(make_run(rows), root)
    df = frame(root, "run")
    for meta, replicate, config in zip(df["meta"], df["replicate_index"], df["config"],
                                       strict=True):
        assert meta["trace_signals"]["repeat"] == int(replicate)
        assert meta["trace_signals"]["case"] == config["case"]
    assert sorted((r["case"], r["repeat"]) for r in records(root, "run")) == [
        ("a", 0), ("a", 1), ("a", 2), ("b", 0)]


# ---------- TF21-27: wall_time, t, horizon, confidence ----------


def test_tf21_27_wall_time_is_the_recorded_time_else_zero(tmp_path: Path) -> None:
    _, df = _stored(tmp_path, [FULL, BARE, Row("z", "met", None, wall_time_s=0.0)])
    by = {m["trace_signals"]["case"]: w for m, w in zip(df["meta"], df["wall_time"], strict=True)}
    assert by["case_042"] == 4.82 and by["case_007"] == 0.0 and by["z"] == 0.0
    recs = {r["case"]: r for r in records(tmp_path / "store", "run")}
    # the column cannot hold "not recorded"; the record keeps it apart
    assert recs["case_007"]["wall_time_s"] is None and recs["z"]["wall_time_s"] == 0.0


def test_tf21_27_t_and_horizon_are_the_recorded_steps_where_given(tmp_path: Path) -> None:
    _, df = _stored(tmp_path, [FULL, BARE, Row("s", "met", None, steps=4)])
    by = {m["trace_signals"]["case"]: (t, h) for m, t, h in
          zip(df["meta"], df["t"], df["horizon"], strict=True)}
    assert by["case_042"] == (3.0, 8.0)
    # no steps and no spans: one step, so Prove 0.1.3's pages build over the store; the
    # rows whose source recorded no horizon share one, the most steps any of them took, since
    # Prove's pages refuse a run of mixed horizons (a LangSmith run's rows, for one, record
    # different numbers of steps)
    assert by["case_007"] == (1.0, 4.0)
    assert by["s"] == (4.0, 4.0)


def test_tf21_27_confidence_is_the_score_on_a_row_with_an_outcome(tmp_path: Path) -> None:
    _, df = _stored(tmp_path, [FULL, BARE, Row("q", "met", None, 0.75)])
    by = {m["trace_signals"]["case"]: c for m, c in zip(df["meta"], df["confidence"], strict=True)}
    assert by["case_042"] == 0.0 and by["q"] == 0.75
    assert by["case_007"] is None or math.isnan(by["case_007"])


def test_tf21_27_a_row_without_an_outcome_stays_an_errored_record(tmp_path: Path) -> None:
    row = Row("e", None, "timeout", 0.4, result="censored", failure_kind="timeout",
              wall_time_s=30.0, steps=5, horizon=8)
    _, df = _stored(tmp_path, [row])
    r = df.iloc[0]
    assert r["outcome"] is None and r["error"] == "timeout"
    assert all(v is None or (isinstance(v, float) and math.isnan(v))
               for v in (r["t"], r["horizon"], r["confidence"]))
    assert r["wall_time"] == 30.0
    rec = r["meta"]["trace_signals"]
    assert (rec["outcome"], rec["failure_kind"], rec["steps"], rec["horizon"]) == (
        "censored", "timeout", 5, 8)


def test_tf21_27_outcome_and_error_are_never_both_written(tmp_path: Path) -> None:
    from poisson_trace.ingest.rows import Refusal

    with pytest.raises(Refusal):
        write(make_run([Row("x", "missed", "infra: lost")]), tmp_path / "store")
    assert not (tmp_path / "store" / "run").exists()


# ---------- TF21-28: the stored error is cut, the record holds no text ----------


def test_tf21_28_a_long_error_is_stored_cut_to_240(tmp_path: Path) -> None:
    long = "Traceback (most recent call last):\n" + "y" * 900
    _, df = _stored(tmp_path, [Row("e", None, long, result="censored")])
    assert len(df.iloc[0]["error"]) == ERROR_MAX


def test_tf21_28_the_record_carries_no_error_text() -> None:
    record = trace_signals(Row("e", None, "infra: secret prompt text", result="censored",
                               error_type="RuntimeError"), 0)
    assert "error" not in record
    assert "secret" not in json.dumps(record)


# ---------- TF21-29: Prove 0.1.2 reads the run as it reads any ----------


def test_tf21_29_prove_reads_tallies_and_lists_the_run(tmp_path: Path) -> None:
    root, _ = _stored(tmp_path, [FULL, BARE, Row("e", None, "timeout", result="censored")])
    store = Store(root)
    assert store.runs() == ["run"]
    assert store.manifest("run").status == "complete"
    assert store.tally("run").to_dict() == {"rows": 3, "with_outcome": 2, "no_outcome": 1,
                                            "timed_out": 1, "infra": 0, "other": 0}
    assert len(store.read("run", meta=False, trace="none")) == 3


def test_tf21_29_the_case_id_column_stays_empty(tmp_path: Path) -> None:
    # meta["case_id"] is Prove's own rollout key; the import names cases in config, as today
    _, df = _stored(tmp_path, [FULL, BARE])
    assert all(c is None for c in df["case_id"])


# ---------- TF21-30: events.jsonl in Prove's own event shape, the full log ----------


AT = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z")


def test_tf21_30_the_import_writes_the_full_event_log(tmp_path: Path) -> None:
    # the import writes Prove's full log: planned, started, progress and finished;
    # a row with no outcome counts as errored, as Prove counts its own
    root, _ = _stored(tmp_path, [FULL, BARE, Row("e", None, "timeout", result="censored")])
    lines = (root / "run" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines]
    kinds = [e["kind"] for e in events]
    assert kinds[:2] == ["planned", "started"] and kinds[-1] == "finished"
    assert set(kinds[2:-1]) == {"progress"}
    for e in events:
        assert tuple(e) == ("schema", "at", "kind", "detail")
        assert e["schema"] == "poisson.run-event/1" and AT.fullmatch(e["at"])
    assert events[0]["detail"] == {"run_id": "run", "reader": "deepeval",
                                   "files": ["results.json"], "rows": 3}
    assert events[1]["detail"] == {"run_id": "run"}
    assert events[-2]["detail"] == {"done": 3, "kept": 2, "errored": 1, "total": 3}
    assert events[-1]["detail"] == {"status": "complete", "kept": 2}
    assert [e["at"] for e in events] == sorted(e["at"] for e in events)


def test_tf21_30_no_event_carries_a_signal_key(tmp_path: Path) -> None:
    root, _ = _stored(tmp_path, [FULL])
    text = (root / "run" / "events.jsonl").read_text(encoding="utf-8")
    for key in ("failure_kind", "input_tokens", "cost_usd", "signals", "scores", "trace_signals"):
        assert key not in text


def test_tf21_30_a_refused_import_leaves_no_events_file(tmp_path: Path) -> None:
    from poisson_trace.ingest.rows import Refusal

    root = tmp_path / "store"
    with pytest.raises(Refusal):
        write(make_run([Row("x", None, None)]), root)
    assert not (root / "run").exists()


# ---------- TF21-31: the taxonomy's digest is in the manifest, beside declared ----------


def test_tf21_31_the_manifest_records_which_rules_classified(tmp_path: Path) -> None:
    from poisson_trace.ingest import taxonomy

    root, _ = _stored(tmp_path, [FULL])
    recorded = Store(root).manifest("run").environment["import"]
    assert recorded["taxonomy_sha256"] == taxonomy.taxonomy_sha256((), None)
    assert "taxonomy_sha256" not in recorded["declared"]
    assert recorded["declared"] == {"metric": "Score", "cut": 0.5, "side": "below", "case": "name"}


def test_tf21_31_write_takes_the_rules_and_budgets_it_classified_with(tmp_path: Path) -> None:
    from poisson_trace.ingest import taxonomy
    from poisson_trace.ingest.taxonomy import Budgets, Rule

    rules = (Rule("guardrail_blocked", when_error_matches="PIIBlocked"),)
    budgets = Budgets(max_cost_usd=0.001)
    root = tmp_path / "store"
    write(make_run([FULL]), root, rules=rules, budgets=budgets)
    recorded = Store(root).manifest("run").environment["import"]
    assert recorded["taxonomy_sha256"] == taxonomy.taxonomy_sha256(rules, budgets)


# ---------- TF21-32: write classifies what the reader left unclassified ----------


def test_tf21_32_write_fills_kind_and_signals_with_the_taxonomy(tmp_path: Path) -> None:
    from poisson_trace.ingest.taxonomy import Budgets, classify

    rows = [Row("a", "missed", None, 0.1, result="fail", cost_usd=0.5),
            Row("b", None, "timeout", result="censored"),
            Row("c", "met", None, 0.9, result="pass", retries=4)]
    budgets = Budgets(max_cost_usd=0.1)
    root = tmp_path / "store"
    write(make_run(rows), root, budgets=budgets)
    got = {r["case"]: r for r in records(root, "run")}
    for row in rows:
        want = classify(row, (), budgets)
        assert got[row.case]["failure_kind"] == want.failure_kind
        assert got[row.case]["signals"] == list(want.signals)
    assert got["a"]["failure_kind"] == "wrong_answer" and got["a"]["signals"] == ["over_budget"]
    assert got["b"]["failure_kind"] == "timeout"
    assert got["c"]["failure_kind"] is None and got["c"]["signals"] == ["retry_storm"]


# ---------- TF21-33: Written, the import's own count, is unchanged ----------


def test_tf21_33_the_written_counts(tmp_path: Path) -> None:
    rows = [FULL, BARE, Row("e", None, "timeout", result="censored")]
    written = write(make_run(rows), tmp_path / "store")
    assert (written.rows, written.cases, written.repeats_min, written.repeats_max) == (3, 3, 1, 1)
    assert dict(written.outcomes) == {"met": 1, "missed": 1}
    assert dict(written.no_outcome) == {"timeout": 1}
