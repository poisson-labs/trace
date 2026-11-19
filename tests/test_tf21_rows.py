"""TF21-1 to TF21-11: the normalised shape, ``ingest/rows.py``.

Every field of ``Row``, ``SpanRecord`` and ``ToolCallRecord``, its type and unit, and what *not
recorded* looks like: ``None`` for a number or a word, never ``0``; ``0`` is a recorded zero.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import pytest
from tf21_support import (
    ERROR_MAX,
    ERROR_SPAN_KINDS,
    FAILURE_KINDS,
    FLOAT_FIELDS,
    INT_FIELDS,
    NEW_FIELDS,
    OLD_FIELDS,
    PROVE_KINDS,
    RESULTS,
    SIGNALS,
)

from poisson_trace.ingest import rows as rows_module
from poisson_trace.ingest.rows import Row, SpanRecord, ToolCallRecord


def _row(**kw: Any) -> Row:
    return Row("c1", "missed", None, **kw)


# ---------- TF21-1: Row keeps today's six positional fields, then the signals by keyword ----------


def test_tf21_1_row_keeps_its_six_positional_fields_in_order() -> None:
    names = [f.name for f in dataclasses.fields(Row)]
    assert tuple(names[:6]) == OLD_FIELDS
    row = Row("c1", "met", None, 0.9)
    assert (row.case, row.outcome, row.error, row.score, row.spans, dict(row.detail)) == (
        "c1", "met", None, 0.9, None, {},
    )


def test_tf21_1_every_signal_field_is_keyword_only_and_present() -> None:
    fields = {f.name: f for f in dataclasses.fields(Row)}
    assert set(NEW_FIELDS) <= set(fields)
    assert set(fields) == set(OLD_FIELDS) | set(NEW_FIELDS)
    for name in NEW_FIELDS:
        assert fields[name].kw_only, name
    assert dataclasses.is_dataclass(Row) and Row.__dataclass_params__.frozen  # type: ignore[attr-defined]


def test_tf21_1_a_row_built_as_today_records_no_signal() -> None:
    row = Row("c1", "met", None, 0.9)
    for name in (*INT_FIELDS, *FLOAT_FIELDS, "failure_kind", "error_type", "error_span_kind",
                 "result", "repeat", "tool_calls", "span_records"):
        assert getattr(row, name) is None, name
    assert dict(row.scores) == {} and dict(row.feedback) == {} and tuple(row.signals) == ()


# ---------- TF21-2: None is not recorded, 0 is a recorded zero ----------


@pytest.mark.parametrize("name", INT_FIELDS)
def test_tf21_2_an_int_signal_keeps_zero_apart_from_none(name: str) -> None:
    assert getattr(_row(**{name: 0}), name) == 0
    assert getattr(_row(**{name: 0}), name) is not None
    assert getattr(_row(**{name: 7}), name) == 7
    assert getattr(_row(), name) is None


@pytest.mark.parametrize("name", FLOAT_FIELDS)
def test_tf21_2_a_float_signal_keeps_zero_apart_from_none(name: str) -> None:
    assert getattr(_row(**{name: 0.0}), name) == 0.0
    assert getattr(_row(**{name: 0.0}), name) is not None
    assert getattr(_row(**{name: 1.25}), name) == 1.25
    assert getattr(_row(), name) is None


def test_tf21_2_tool_calls_none_is_not_recorded_and_empty_is_recorded_none_made() -> None:
    assert _row().tool_calls is None
    assert _row(tool_calls=()).tool_calls == ()


# ---------- TF21-3: types and ranges ----------


@pytest.mark.parametrize("name", INT_FIELDS)
@pytest.mark.parametrize("bad", [-1, 1.5, True, "3", math.nan])
def test_tf21_3_an_int_signal_refuses_what_is_not_a_count(name: str, bad: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        _row(**{name: bad})


@pytest.mark.parametrize("name", FLOAT_FIELDS)
@pytest.mark.parametrize("bad", [-0.5, math.nan, math.inf, True, "1.0"])
def test_tf21_3_a_float_signal_refuses_what_is_not_an_amount(name: str, bad: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        _row(**{name: bad})


@pytest.mark.parametrize("name", FLOAT_FIELDS)
def test_tf21_3_a_float_signal_takes_a_whole_number(name: str) -> None:
    assert getattr(_row(**{name: 3}), name) == 3.0


@pytest.mark.parametrize("bad", [-1, 1.0, True])
def test_tf21_3_repeat_is_a_count_from_zero(bad: Any) -> None:
    assert _row(repeat=0).repeat == 0 and _row(repeat=4).repeat == 4
    with pytest.raises((TypeError, ValueError)):
        _row(repeat=bad)


# ---------- TF21-4: result, failure kind and signals take only their words ----------


def test_tf21_4_results_are_the_three_words() -> None:
    assert tuple(rows_module.RESULTS) == RESULTS
    for word in RESULTS:
        assert _row(result=word).result == word
    for bad in ("met", "missed", "passed", "PASS", ""):
        with pytest.raises(ValueError):
            _row(result=bad)


def test_tf21_4_a_failure_kind_is_one_of_the_thirteen() -> None:
    for kind in FAILURE_KINDS:
        assert _row(result="fail", failure_kind=kind).failure_kind == kind
    for bad in ("Timeout", "error", "infra", ""):
        with pytest.raises(ValueError):
            _row(result="fail", failure_kind=bad)


@pytest.mark.parametrize("result", ["pass", None])
def test_tf21_4_only_a_failed_or_censored_row_has_a_kind(result: str | None) -> None:
    with pytest.raises(ValueError):
        _row(result=result, failure_kind="timeout")
    assert _row(result="censored", failure_kind="timeout").failure_kind == "timeout"


def test_tf21_4_signals_are_a_subset_of_the_three_in_their_order() -> None:
    row = _row(signals=("over_budget", "gave_up"))
    assert tuple(row.signals) == ("gave_up", "over_budget")
    assert tuple(_row(signals=SIGNALS).signals) == SIGNALS
    for bad in (("slow",), ("gave_up", "gave_up")):
        with pytest.raises(ValueError):
            _row(signals=bad)


def test_tf21_4_an_error_span_kind_is_a_kind_a_source_names() -> None:
    for kind in ERROR_SPAN_KINDS:
        assert _row(error_span_kind=kind).error_span_kind == kind
    with pytest.raises(ValueError):
        _row(error_span_kind="judge")


# ---------- TF21-5: token consistency ----------


def test_tf21_5_total_tokens_is_the_sum_when_the_source_left_it_out() -> None:
    assert _row(input_tokens=620, output_tokens=95).total_tokens == 715
    assert _row(input_tokens=0, output_tokens=0).total_tokens == 0


def test_tf21_5_total_tokens_stays_unrecorded_when_one_half_is() -> None:
    assert _row(input_tokens=620).total_tokens is None
    assert _row(output_tokens=95).total_tokens is None


def test_tf21_5_a_recorded_total_is_kept_as_the_source_wrote_it() -> None:
    assert _row(input_tokens=620, output_tokens=95, total_tokens=800).total_tokens == 800
    assert _row(total_tokens=12).total_tokens == 12


# ---------- TF21-6: no content (IC7) ----------


def test_tf21_6_an_error_is_cut_to_240_characters() -> None:
    long = "Traceback (most recent call last):\n" + "x" * 1000
    row = _row(error_type="RuntimeError")
    cut = Row("c1", None, long)
    assert len(cut.error or "") == ERROR_MAX and long.startswith(cut.error or "")
    assert Row("c1", None, "x" * ERROR_MAX).error == "x" * ERROR_MAX
    assert row.error is None


def test_tf21_6_lengths_are_plain_counts_and_no_text_field_exists() -> None:
    names = {f.name for f in dataclasses.fields(Row)}
    assert not names & {"input", "output", "prompt", "completion", "input_text", "output_text"}
    tool_names = {f.name for f in dataclasses.fields(ToolCallRecord)}
    assert tool_names == {"name", "status", "duration_s", "error_type", "attempt"}


# ---------- TF21-7: ToolCallRecord ----------


def test_tf21_7_a_tool_call_records_name_status_time_error_and_try() -> None:
    call = ToolCallRecord("run_sql", "error", 2.01, "ToolTimeoutError", 2)
    assert (call.name, call.status, call.duration_s, call.error_type, call.attempt) == (
        "run_sql", "error", 2.01, "ToolTimeoutError", 2,
    )
    plain = ToolCallRecord("search_docs", "ok")
    assert (plain.duration_s, plain.error_type, plain.attempt) == (None, None, 1)
    assert dataclasses.is_dataclass(ToolCallRecord)
    assert ToolCallRecord.__dataclass_params__.frozen  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "kw",
    [{"status": "failed"}, {"status": ""}, {"name": ""}, {"attempt": 0}, {"attempt": 1.0},
     {"duration_s": -1.0}, {"duration_s": math.nan}],
)
def test_tf21_7_a_tool_call_refuses_what_it_cannot_be(kw: dict[str, Any]) -> None:
    base: dict[str, Any] = {"name": "t", "status": "ok"}
    with pytest.raises((TypeError, ValueError)):
        ToolCallRecord(**{**base, **kw})


def test_tf21_7_a_row_holds_its_tool_calls_in_order() -> None:
    calls = (ToolCallRecord("a", "ok", 0.1), ToolCallRecord("b", "error", 0.2, "E", 2))
    assert _row(tool_calls=calls).tool_calls == calls
    with pytest.raises((TypeError, ValueError)):
        _row(tool_calls=({"name": "a", "status": "ok"},))


# ---------- TF21-8: SpanRecord follows Prove 0.1.2's span ----------


SPAN_FIELDS = (
    "span_id", "parent_id", "kind", "name", "start_ns", "end_ns", "tokens", "input_tokens",
    "output_tokens", "cost_usd", "error", "code", "operation", "step_name", "outcome",
    "outcome_by", "attempt", "gate", "truncated", "bytes_original",
)


def test_tf21_8_span_record_has_section_18_4_1s_fields_in_order() -> None:
    assert tuple(f.name for f in dataclasses.fields(SpanRecord)) == SPAN_FIELDS
    assert SpanRecord.__dataclass_params__.frozen  # type: ignore[attr-defined]


def test_tf21_8_a_span_record_leaves_every_optional_field_unrecorded() -> None:
    span = SpanRecord("s1", None, "llm", "gpt", 10, 20)
    for name in SPAN_FIELDS[6:]:
        assert getattr(span, name) is None, name


def test_tf21_8_span_kinds_are_prove_0_1_2s_kinds() -> None:
    for kind in PROVE_KINDS:
        assert SpanRecord("s", None, kind, "n", 0, 1).kind == kind
    for bad in ("step", "grader", "gate", "lifecycle"):
        with pytest.raises(ValueError):
            SpanRecord("s", None, bad, "n", 0, 1)


def test_tf21_8_an_open_span_has_no_end() -> None:
    assert SpanRecord("s", None, "tool", "n", 5, None).end_ns is None
    with pytest.raises(ValueError):
        SpanRecord("s", None, "tool", "n", 5, 4)


def test_tf21_8_a_row_holds_span_records_apart_from_the_spans_it_writes() -> None:
    spans = (SpanRecord("s1", None, "agent", "root", 0, 9), SpanRecord("s2", "s1", "tool", "t", 1, 2))
    row = _row(span_records=spans)
    assert row.span_records == spans and row.spans is None


# ---------- TF21-9: scores and feedback ----------


def test_tf21_9_scores_are_named_numbers_and_feedback_named_values() -> None:
    row = _row(scores={"exact_match": 0.0, "faithfulness": 0.85},
               feedback={"thumb": "down", "reviewer_score": 0.0, "flagged": True})
    assert dict(row.scores) == {"exact_match": 0.0, "faithfulness": 0.85}
    assert dict(row.feedback) == {"thumb": "down", "reviewer_score": 0.0, "flagged": True}


@pytest.mark.parametrize("bad", [{"m": math.nan}, {"m": "high"}, {"m": None}, {1: 0.5}])
def test_tf21_9_a_score_that_is_not_a_number_is_refused(bad: dict[Any, Any]) -> None:
    with pytest.raises((TypeError, ValueError)):
        _row(scores=bad)


# ---------- TF21-10: the record is frozen and hashable as today ----------


def test_tf21_10_rows_are_frozen() -> None:
    row = _row(wall_time_s=1.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.wall_time_s = 2.0  # type: ignore[misc]


def test_tf21_10_replace_keeps_the_rules() -> None:
    row = _row(input_tokens=1, output_tokens=2)
    assert dataclasses.replace(row, result="fail", failure_kind="wrong_answer").total_tokens == 3
    with pytest.raises(ValueError):
        dataclasses.replace(row, failure_kind="nope")


# ---------- TF21-11: the units, in the module's own words ----------


def test_tf21_11_the_module_names_each_signal_and_its_unit() -> None:
    from tf21_support import UNITS

    assert dict(rows_module.UNITS) == UNITS
