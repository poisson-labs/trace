"""HY12 to HY14: properties of the signals record and the failure taxonomy (spec sections 18.4
and 18.5.1), added by the Hypothesis follow-up to the test standard pass (yes/no 9, ruled yes
2026-10-29). TF21's tests hold each of these on worked examples; these hold them on random rows.

- HY12: classification is deterministic: the same row gives the same kind and signals, a
  classified row classifies to itself, the kind follows the precedence of section 18.5.1 (the
  support file's reference), and a row has exactly one kind when it failed or was censored.
- HY13: classification is order-independent where section 18.5.1 makes it so: the order of a
  row's scores, the order rows are classified in, and the order of tool calls wherever the
  retry storm (three calls in a row, by definition ordered) reads the same.
- HY14: a value the source did not record never becomes a zero: through the signals record,
  the store and back, and into the continuous measures' inputs.

Each property is one body run as a fast test (fixed seed, bounded examples) and a slow wide twin.
User rules apply in the order written (section 18.5.3), so their order is not permuted here.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tf21_support import STARTED, ref_kind
from poisson_trace.ingest.prove import read_rows
from poisson_trace.ingest.rows import (
    AMOUNT_SIGNALS, COUNT_SIGNALS, ERROR_SPAN_KINDS, FAILURE_KINDS, SIGNALS, Row, Run, ToolCallRecord,
)
from poisson_trace.ingest.taxonomy import Budgets, classify, retry_storm
from poisson_trace.ingest.tries import try_of, version_of
from poisson_trace.ingest.writer import trace_signals, write
from poisson_trace.stats.continuous import MEASURES, compare

_COMMON: dict[str, Any] = dict(deadline=None, derandomize=True, database=None,
                               suppress_health_check=[HealthCheck.too_slow])


def twin(fast_n: int, wide_n: int, *strategies: Any) -> Callable[[Callable[..., None]], tuple[Any, Any]]:
    """The property as two tests: the fast one for every pull request, the wide one slow."""
    def make(body: Callable[..., None]) -> tuple[Any, Any]:
        fast = settings(max_examples=fast_n, **_COMMON)(given(*strategies)(body))
        wide = pytest.mark.slow(settings(max_examples=wide_n, **_COMMON)(given(*strategies)(body)))
        return fast, wide
    return make


# ---------- rows ----------

ERROR_TYPES = [None, None, "TimeoutError", "RateLimitError", "AssertionError", "ValueError",
               "JSONDecodeError", "ToolTimeoutError", "pytest.AssertionError"]
ERRORS = [None, None, "timed out after 30s", "HTTP 429", "context_length exceeded", "infra: sandbox",
          "content_filter", "boom", "ETIMEDOUT", "max_tokens reached", "ValidationError: bad"]
SCORE_NAMES = ["context_recall", "context_precision", "faithfulness", "ragas.context_recall"]
TOOLS = ["search", "run_sql"]

counts_ = st.one_of(st.none(), st.just(0), st.integers(1, 5_000))
amounts_ = st.one_of(st.none(), st.just(0.0), st.floats(1e-6, 1e4))
calls_ = st.one_of(st.none(), st.lists(
    st.builds(ToolCallRecord, st.sampled_from(TOOLS), st.sampled_from(["ok", "error"]),
              st.one_of(st.none(), st.floats(0, 10)), st.sampled_from([None, "ToolError"]),
              st.integers(1, 3)),
    max_size=6).map(tuple))


@st.composite
def rows(draw, case: str | None = None, storable: bool = False):  # type: ignore[no-untyped-def]
    """A normalised row. ``storable`` keeps to the rows a reader makes for the store: exactly one
    of an outcome word and an error reason (Prove's record refuses both or neither)."""
    outcome = draw(st.sampled_from([None, "met", "missed"]))
    error = draw(st.sampled_from(ERRORS))
    if storable:
        error = None if outcome is not None else (error or "boom")
    result = draw(st.sampled_from([None, "pass", "fail", "fail", "censored"]))
    kind = None
    if result in ("fail", "censored") and draw(st.integers(0, 9)) == 0:
        kind = draw(st.sampled_from(FAILURE_KINDS))
    fields: dict[str, Any] = {name: draw(counts_) for name in COUNT_SIGNALS}
    fields.update({name: draw(amounts_) for name in AMOUNT_SIGNALS})
    for name in ("steps", "horizon", "retries"):
        fields[name] = draw(st.one_of(st.none(), st.integers(0, 6)))
    scores = draw(st.dictionaries(st.sampled_from(SCORE_NAMES),
                                  st.sampled_from([0.0, 0.0, 0.4, 1.0]), max_size=4))
    held = draw(st.lists(st.sampled_from(SIGNALS), unique=True, max_size=3))
    return Row(
        case if case is not None else draw(st.sampled_from(["a", "b", "c", "d"])),
        outcome,
        error,
        draw(st.one_of(st.none(), st.sampled_from([0.0, 0.3, 1.0]))),
        result=result, failure_kind=kind,
        error_type=draw(st.sampled_from(ERROR_TYPES)),
        error_span_kind=draw(st.one_of(st.none(), st.sampled_from(ERROR_SPAN_KINDS))),
        tool_calls=draw(calls_), scores=scores,
        signals=tuple(s for s in SIGNALS if s in held), **fields,
    )


budgets_ = st.one_of(st.none(), st.builds(
    Budgets, st.one_of(st.none(), st.floats(0, 100)), st.one_of(st.none(), st.integers(0, 3_000)),
    st.one_of(st.none(), st.floats(0, 10))))


# ---------- HY12: deterministic, by the precedence of section 18.5.1 ----------


def _hy12(row, budgets) -> None:  # type: ignore[no-untyped-def]
    once = classify(row, budgets=budgets)
    assert classify(row, budgets=budgets) == once
    assert classify(once, budgets=budgets) == once
    if row.result in ("fail", "censored"):
        assert once.failure_kind in FAILURE_KINDS
        assert once.failure_kind == (row.failure_kind if row.failure_kind is not None else ref_kind(row))
    else:
        assert once.failure_kind is None
    assert set(row.signals) <= set(once.signals)
    assert once.signals == tuple(s for s in SIGNALS if s in once.signals)
    assert replace(once, failure_kind=row.failure_kind, signals=row.signals) == row


test_hy12_classification_is_deterministic, test_hy12_wide = twin(80, 1_500, rows(), budgets_)(_hy12)


# ---------- HY13: order-independent where section 18.5.1 makes it so ----------


def _hy13(batch, budgets, rnd) -> None:  # type: ignore[no-untyped-def]
    for row in batch:
        once = classify(row, budgets=budgets)
        names = list(row.scores)
        rnd.shuffle(names)
        reordered = replace(row, scores={k: row.scores[k] for k in names})
        assert classify(reordered, budgets=budgets) == replace(once, scores=reordered.scores)
        if row.tool_calls:
            calls = list(row.tool_calls)
            rnd.shuffle(calls)
            moved = replace(row, tool_calls=tuple(calls))
            if retry_storm(moved) == retry_storm(row):
                other = classify(moved, budgets=budgets)
                assert (other.failure_kind, other.signals) == (once.failure_kind, once.signals)
    order = list(range(len(batch)))
    rnd.shuffle(order)
    alone = [classify(r, budgets=budgets) for r in batch]
    shuffled = {i: classify(batch[i], budgets=budgets) for i in order}
    assert [shuffled[i] for i in range(len(batch))] == alone


test_hy13_classification_is_order_independent, test_hy13_wide = twin(
    40, 600, st.lists(rows(), min_size=1, max_size=6), budgets_, st.randoms(use_true_random=False))(_hy13)


# ---------- HY14: a value not recorded never becomes a zero ----------

SIGNAL_FIELDS = (*AMOUNT_SIGNALS, *COUNT_SIGNALS)


def _same(stored: Any, source: Any) -> bool:
    """None stays None, and a number stays that number (a zero stays a zero)."""
    return stored is None if source is None else (stored is not None and stored == source)


def _store(batch: list[Row]) -> tuple[Row, ...]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "store"
        write(Run(name="run", tool="deepeval", rows=tuple(batch), started=STARTED,
                  started_from="given",
                  declared={"metric": "Score", "cut": 0.5, "side": "below", "case": "name"},
                  files=({"name": "results.json", "sha256": "ab" * 32},)), root)
        return read_rows(root, "run", ("missed",))


def _hy14(batch) -> None:  # type: ignore[no-untyped-def]
    classified = [classify(r) for r in batch]
    for row in classified:
        record = trace_signals(row, 0)
        for name in SIGNAL_FIELDS:
            assert _same(record[name], getattr(row, name)), name
        values = try_of(row).values
        for m in MEASURES:
            assert _same(values[m], getattr(row, m)), m
    back = _store(batch)
    assert len(back) == len(classified)
    by_case: dict[str, list[Row]] = {}
    for row in back:
        by_case.setdefault(row.case, []).append(row)
    for row in classified:
        got = by_case[row.case].pop(0)
        for name in SIGNAL_FIELDS:
            assert _same(getattr(got, name), getattr(row, name)), name
        assert (got.tool_calls is None) == (row.tool_calls is None)
    # a measure no try of one version recorded is not recorded, never a zero mean
    old = version_of(classified, "run-old", "old")
    new = version_of([replace(r, wall_time_s=None) for r in classified], "run-new", "new")
    m = compare(old, new).measures["wall_time_s"]
    assert m.status == "not_recorded"
    assert (m.mean_a, m.mean_b, m.change, m.p_value) == (None, None, None, None)


def _batch(n: int) -> Any:
    return st.lists(st.sampled_from(["a", "b", "c"]).flatmap(lambda c: rows(case=c, storable=True)),
                    min_size=1, max_size=n)


test_hy14_a_value_not_recorded_never_becomes_zero, test_hy14_wide = twin(8, 120, _batch(6))(_hy14)
