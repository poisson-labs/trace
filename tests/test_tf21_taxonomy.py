"""TF21-13 to TF21-22: the taxonomy engine, ``ingest/taxonomy.py``. The 13 terminal failure
kinds in precedence order, the 3 behavioural signals, the built-in rules and the order they apply
in. ``tf21_support``'s docstring lists the rules as these tests read them, and ``ref_kind`` is the
reference."""

from __future__ import annotations

import dataclasses
import hashlib
import itertools
import json
from typing import Any

import pytest
from tf21_support import FAILURE_KINDS, SIGNALS, ref_kind

from poisson_trace.ingest import taxonomy
from poisson_trace.ingest.rows import Row, ToolCallRecord
from poisson_trace.ingest.taxonomy import Budgets, Rule, classify, kind_of, signals_of


def failed(**kw: Any) -> Row:
    error = kw.pop("error", None)
    return Row("c1", "missed", error, **{"result": "fail", **kw})


# one row each rule matches alone, with no other rule's condition held
ALONE: dict[str, dict[str, Any]] = {
    "timeout": {"error_type": "TimeoutError"},
    "rate_limit": {"error_type": "RateLimitError"},
    "context_overflow": {"error_type": "ContextLengthExceeded"},
    "loop_detected": {"retries": 3, "steps": 10, "horizon": 10},
    "step_limit": {"steps": 10, "horizon": 10},
    "guardrail_blocked": {"error_span_kind": "gate"},
    "tool_error": {"tool_calls": (ToolCallRecord("run_sql", "error"),)},
    "retrieval_error": {"scores": {"context_recall": 0.0, "context_precision": 0.0}},
    "format_error": {"error_type": "JSONDecodeError"},
    "abstained": {"output_chars": 0},
    "crash": {"error_type": "RuntimeError"},
    "wrong_answer": {"score": 0.0},
    "unclassified_error": {},
}


# ---------- TF21-13: the kinds and the signals ----------


def test_tf21_13_the_thirteen_kinds_in_precedence_order() -> None:
    assert tuple(taxonomy.FAILURE_KINDS) == FAILURE_KINDS
    assert len(set(FAILURE_KINDS)) == 13


def test_tf21_13_the_three_signals() -> None:
    assert tuple(taxonomy.SIGNALS) == SIGNALS


# ---------- TF21-14: each rule alone ----------


@pytest.mark.parametrize("kind", FAILURE_KINDS)
def test_tf21_14_each_rule_alone_gives_its_kind(kind: str) -> None:
    row = classify(failed(**ALONE[kind]))
    assert row.failure_kind == kind
    assert kind_of(failed(**ALONE[kind])) == kind == ref_kind(failed(**ALONE[kind]))


@pytest.mark.parametrize("kind", FAILURE_KINDS)
def test_tf21_14_a_censored_row_gets_a_kind_too(kind: str) -> None:
    row = classify(Row("c1", None, None, result="censored", **ALONE[kind]))
    # a censored row has no grader's verdict: what would be wrong_answer is unclassified
    assert row.failure_kind == ("unclassified_error" if kind == "wrong_answer" else kind)


@pytest.mark.parametrize("result", ["pass", None])
def test_tf21_14_a_passed_or_unscored_row_has_no_kind(result: str | None) -> None:
    for kw in ALONE.values():
        row = classify(Row("c1", "met", None, result=result, **kw))
        assert row.failure_kind is None


# ---------- TF21-15: the patterns, as each source writes them ----------


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("TimeoutError", "timeout"), ("timeout", "timeout"), ("Request timed out", "timeout"),
        ("ETIMEDOUT", "timeout"), ("asyncio.exceptions.TimeoutError", "timeout"),
        ("HTTP 429", "rate_limit"), ("openai.RateLimitError", "rate_limit"),
        ("rate limit exceeded", "rate_limit"), ("rate_limit_exceeded", "rate_limit"),
        ("context_length_exceeded", "context_overflow"), ("ContextLengthError", "context_overflow"),
        ("max_tokens reached", "context_overflow"), ("model_length", "context_overflow"),
        ("token_limit", "context_overflow"), ("cost_limit", "context_overflow"),
        ("content_filter", "guardrail_blocked"), ("Guardrail tripped", "guardrail_blocked"),
        ("JSONDecodeError", "format_error"), ("pydantic.ValidationError", "format_error"),
        ("SchemaError", "format_error"),
        ("infra: worker lost", "crash"), ("ReplayMiss", "crash"), ("KeyError", "crash"),
        ("AssertionError", "wrong_answer"), ("builtins.AssertionError", "wrong_answer"),
    ],
)
def test_tf21_15_error_text_reads_the_same_from_error_type_or_error(text: str, kind: str) -> None:
    by_type = failed(error_type=text)
    assert kind_of(by_type) == kind == ref_kind(by_type)
    if not text.startswith("infra:") and kind not in ("crash", "wrong_answer"):
        by_error = Row("c1", None, text, result="censored")
        assert kind_of(by_error) == kind
    if text.startswith("infra:"):
        assert kind_of(Row("c1", None, text, result="censored")) == "crash"


def test_tf21_15_a_trace_reason_word_is_not_a_crash() -> None:
    # "no score" and "skipped" are Trace's own words for a row without an outcome
    for word in ("no score", "skipped", "no outcome"):
        assert kind_of(Row("c1", None, word, result="censored")) == "unclassified_error"


def test_tf21_15_span_kinds_name_their_kind() -> None:
    for span_kind, kind in [("gate", "guardrail_blocked"), ("tool", "tool_error"),
                            ("retrieval", "retrieval_error"), ("retriever", "retrieval_error"),
                            ("parser", "format_error"), ("lifecycle", "crash"),
                            ("grader", "wrong_answer"), ("llm", "unclassified_error")]:
        assert kind_of(failed(error_span_kind=span_kind)) == kind, span_kind


def test_tf21_15_step_limit_needs_both_numbers_and_a_horizon() -> None:
    assert kind_of(failed(steps=9, horizon=10)) == "unclassified_error"
    assert kind_of(failed(steps=11, horizon=10)) == "step_limit"
    assert kind_of(failed(steps=10)) == "unclassified_error"
    assert kind_of(failed(horizon=10)) == "unclassified_error"
    assert kind_of(failed(steps=0, horizon=0)) == "unclassified_error"


def test_tf21_15_retrieval_scores_need_recall_and_precision_both_zero() -> None:
    assert kind_of(failed(scores={"context_recall": 0.0, "context_precision": 0.1})) == "wrong_answer"
    assert kind_of(failed(scores={"id_based_context_recall": 0.0,
                                  "id_based_context_precision": 0.0})) == "retrieval_error"
    assert kind_of(failed(scores={"context_recall": 0.0})) == "wrong_answer"


def test_tf21_15_abstained_needs_a_recorded_empty_output_and_no_error() -> None:
    assert kind_of(failed(output_chars=0)) == "abstained"
    assert kind_of(failed(output_chars=1)) == "unclassified_error"
    assert kind_of(failed()) == "unclassified_error"
    assert kind_of(failed(output_chars=0, error_type="RuntimeError")) == "crash"


def test_tf21_15_wrong_answer_needs_a_graders_word() -> None:
    assert kind_of(failed(score=0.2)) == "wrong_answer"
    assert kind_of(failed(scores={"m": 0.2})) == "wrong_answer"
    assert kind_of(failed(error_type="AssertionError")) == "wrong_answer"
    assert kind_of(failed(error_span_kind="grader")) == "wrong_answer"
    assert kind_of(failed()) == "unclassified_error"


# ---------- TF21-16: precedence ----------


def _merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any] | None:
    out = dict(a)
    for key, value in b.items():
        if key not in out:
            out[key] = value
        elif key in ("scores",):
            out[key] = {**out[key], **value}
        elif key == "tool_calls":
            out[key] = (*out[key], *value)
        elif key == "error_type":
            return None  # one error type per row
        elif out[key] != value:
            return None
    return out


PAIRS = [
    (i, j) for i, j in itertools.combinations(FAILURE_KINDS, 2)
    if _merge(ALONE[i], ALONE[j]) is not None
]


@pytest.mark.parametrize(("first", "second"), PAIRS)
def test_tf21_16_two_rules_matching_give_the_earlier_kind(first: str, second: str) -> None:
    merged = _merge(ALONE[first], ALONE[second])
    assert merged is not None
    row = failed(**merged)
    got = classify(row).failure_kind
    assert got == ref_kind(classify(row)), (first, second)
    if first not in ("abstained",):
        assert got == first, (first, second, got)


@pytest.mark.parametrize(
    ("kw", "kind", "why"),
    [
        ({"error_type": "TimeoutError", "steps": 10, "horizon": 10}, "timeout",
         "a timed-out try at its step cap is a timeout"),
        ({"error": "HTTP 429 after 3 tries", "retries": 3}, "rate_limit",
         "a retried 429 is a rate limit, not a loop"),
        ({"retries": 4, "steps": 20, "horizon": 20, "error_span_kind": "tool"}, "loop_detected",
         "a retry storm at the cap is a loop, ahead of the tool that stormed"),
        ({"steps": 20, "horizon": 20, "error_span_kind": "gate"}, "step_limit",
         "section 18.5.1 puts step_limit (5) ahead of guardrail_blocked (6)"),
        ({"error_span_kind": "tool", "error_type": "RuntimeError"}, "tool_error",
         "a failing tool span with an exception is a tool error, not a crash"),
        ({"error": "infra: sandbox lost", "score": 0.0}, "crash",
         "a crash with a score is still a crash"),
        ({"error_type": "AssertionError", "score": 0.0}, "wrong_answer",
         "an assertion is the grader's word"),
    ],
)
def test_tf21_16_named_precedence_cases(kw: dict[str, Any], kind: str, why: str) -> None:
    assert classify(failed(**kw)).failure_kind == kind, why


# ---------- TF21-17: the behavioural signals ----------


def test_tf21_17_retry_storm_from_three_retries() -> None:
    assert "retry_storm" in signals_of(failed(retries=3))
    assert "retry_storm" not in signals_of(failed(retries=2))
    assert "retry_storm" in signals_of(Row("c1", "met", None, result="pass", retries=5))


def test_tf21_17_retry_storm_from_three_same_calls_two_failed() -> None:
    def calls(*statuses: str, names: str = "aaa") -> tuple[ToolCallRecord, ...]:
        return tuple(ToolCallRecord(n, s) for n, s in zip(names, statuses, strict=True))

    assert "retry_storm" in signals_of(failed(tool_calls=calls("error", "ok", "error")))
    assert "retry_storm" not in signals_of(failed(tool_calls=calls("error", "ok", "ok")))
    assert "retry_storm" not in signals_of(failed(tool_calls=calls("error", "error", "error",
                                                                   names="aba")))
    assert "retry_storm" in signals_of(failed(tool_calls=calls("ok", "error", "ok", "error",
                                                               names="baaa")))


def test_tf21_17_over_budget_from_a_declared_budget_strictly_exceeded() -> None:
    budgets = Budgets(max_wall_time_s=30.0, max_total_tokens=16000, max_cost_usd=0.10)
    assert "over_budget" in signals_of(failed(wall_time_s=30.5), budgets)
    assert "over_budget" not in signals_of(failed(wall_time_s=30.0), budgets)
    assert "over_budget" in signals_of(failed(input_tokens=9000, output_tokens=7001), budgets)
    assert "over_budget" in signals_of(failed(cost_usd=0.11), budgets)
    assert "over_budget" not in signals_of(failed(cost_usd=0.11))
    assert "over_budget" not in signals_of(failed(), budgets)
    assert "over_budget" in signals_of(Row("c1", "met", None, result="pass", cost_usd=1.0), budgets)


@pytest.mark.parametrize("kind", ["timeout", "context_overflow", "step_limit"])
def test_tf21_17_over_budget_from_a_cap_kind(kind: str) -> None:
    assert "over_budget" in classify(failed(**ALONE[kind])).signals


def test_tf21_17_gave_up_from_an_abstention_or_an_empty_stop_inside_the_budget() -> None:
    assert "gave_up" in classify(failed(output_chars=0)).signals
    assert "gave_up" in signals_of(Row("c1", "met", None, result="pass", output_chars=0,
                                       steps=2, horizon=10))
    assert "gave_up" not in signals_of(Row("c1", "met", None, result="pass", output_chars=0,
                                           steps=10, horizon=10))
    assert "gave_up" not in signals_of(Row("c1", "met", None, result="pass", output_chars=0))


def test_tf21_17_signals_keep_their_order_and_kind_rules_see_retry_storm() -> None:
    row = classify(failed(retries=3, steps=10, horizon=10))
    assert row.failure_kind == "loop_detected"
    assert tuple(row.signals) == ("retry_storm", "over_budget")


# ---------- TF21-18: classify fills kind and signals and nothing else ----------


def test_tf21_18_classify_changes_only_kind_and_signals() -> None:
    row = failed(error_type="TimeoutError", wall_time_s=4.82, input_tokens=1, output_tokens=2,
                 scores={"m": 0.5}, tool_calls=())
    got = classify(row)
    for f in dataclasses.fields(Row):
        if f.name not in ("failure_kind", "signals"):
            assert getattr(got, f.name) == getattr(row, f.name), f.name
    assert got.failure_kind == "timeout"


def test_tf21_18_classify_keeps_a_kind_the_source_gave() -> None:
    row = failed(failure_kind="abstained", error_type="TimeoutError")
    assert classify(row).failure_kind == "abstained"


def test_tf21_18_classify_is_deterministic() -> None:
    row = failed(retries=4, error="HTTP 429", tool_calls=(ToolCallRecord("a", "error"),))
    assert classify(row) == classify(row) == classify(classify(row))


# ---------- TF21-19: user rules first, in the order written ----------


def test_tf21_19_a_user_rule_wins_over_a_built_in() -> None:
    rules = (Rule("tool_error", when_error_matches="SqlDeadlockError|ConnectionResetByPeer",
                  when_span_kind="tool"),)
    row = failed(error_type="SqlDeadlockError timeout", error_span_kind="tool")
    assert kind_of(row) == "timeout"
    assert kind_of(row, rules) == "tool_error"


def test_tf21_19_every_condition_of_a_rule_must_hold() -> None:
    rule = Rule("tool_error", when_error_matches="SqlDeadlockError", when_span_kind="tool")
    assert kind_of(failed(error_type="SqlDeadlockError"), (rule,)) == "crash"
    assert kind_of(failed(error_span_kind="tool"), (rule,)) == "tool_error"
    assert kind_of(failed(error_type="SqlDeadlockError", error_span_kind="tool"), (rule,)) == "tool_error"


def test_tf21_19_rules_apply_in_the_order_written() -> None:
    a = Rule("guardrail_blocked", when_error_matches="PolicyViolation|PIIBlocked")
    b = Rule("crash", when_error_matches="PIIBlocked")
    row = failed(error_type="PIIBlocked")
    assert kind_of(row, (a, b)) == "guardrail_blocked"
    assert kind_of(row, (b, a)) == "crash"


def test_tf21_19_metric_below() -> None:
    rule = Rule("abstained", when_metric_below={"metric": "helpfulness", "cut": 0.2})
    assert kind_of(failed(scores={"helpfulness": 0.1}), (rule,)) == "abstained"
    assert kind_of(failed(scores={"helpfulness": 0.2}), (rule,)) == "wrong_answer"
    assert kind_of(failed(scores={"other": 0.0}), (rule,)) == "wrong_answer"


def test_tf21_19_a_user_rule_never_gives_a_passed_row_a_kind() -> None:
    rule = Rule("crash", when_error_matches=".*")
    assert kind_of(Row("c1", "met", None, result="pass", error_type="X"), (rule,)) is None


@pytest.mark.parametrize(
    "kw",
    [{"failure_kind": "oops", "when_error_matches": "x"}, {"failure_kind": "crash"},
     {"failure_kind": "crash", "when_error_matches": "("},
     {"failure_kind": "crash", "when_span_kind": "judge"},
     {"failure_kind": "crash", "when_metric_below": {"metric": "m"}},
     {"failure_kind": "crash", "when_metric_below": {"metric": "m", "cut": "high"}}],
)
def test_tf21_19_a_rule_that_cannot_be_is_refused(kw: dict[str, Any]) -> None:
    with pytest.raises((TypeError, ValueError)):
        Rule(**kw)


# ---------- TF21-20: the taxonomy's digest ----------


def _expected_sha(rules: list[dict[str, Any]], budgets: dict[str, Any]) -> str:
    doc = {"schema": "poisson.trace-taxonomy/1", "rules": rules, "budgets": budgets}
    text = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_tf21_20_the_digest_of_no_rules_and_no_budgets() -> None:
    assert taxonomy.taxonomy_sha256((), None) == _expected_sha([], {})
    assert taxonomy.taxonomy_sha256((), Budgets()) == _expected_sha([], {})


def test_tf21_20_the_digest_reads_rules_in_order_and_budgets_set() -> None:
    a = Rule("tool_error", when_error_matches="SqlDeadlockError", when_span_kind="tool")
    b = Rule("abstained", when_metric_below={"metric": "helpfulness", "cut": 0.2})
    budgets = Budgets(max_cost_usd=0.1)
    ra = {"failure_kind": "tool_error", "when_error_matches": "SqlDeadlockError",
          "when_span_kind": "tool"}
    rb = {"failure_kind": "abstained", "when_metric_below": {"metric": "helpfulness", "cut": 0.2}}
    assert taxonomy.taxonomy_sha256((a, b), budgets) == _expected_sha([ra, rb], {"max_cost_usd": 0.1})
    assert taxonomy.taxonomy_sha256((b, a), budgets) != taxonomy.taxonomy_sha256((a, b), budgets)
    assert len(taxonomy.taxonomy_sha256((a,), None)) == 64


# ---------- TF21-21: the alignment with Break and Monte ----------


@pytest.mark.parametrize(
    ("kw", "kind", "signal"),
    [
        ({"error": "timeout", "result": "censored"}, "timeout", "over_budget"),
        ({"retries": 3, "steps": 8, "horizon": 8}, "loop_detected", "retry_storm"),
        ({"error_type": "ContextLengthError"}, "context_overflow", "over_budget"),
        ({"output_chars": 0, "steps": 1, "horizon": 8}, "abstained", "gave_up"),
    ],
)
def test_tf21_21_break_outcomes_land_on_their_kind_and_signal(
    kw: dict[str, Any], kind: str, signal: str
) -> None:
    row = classify(failed(**dict(kw)))
    assert row.failure_kind == kind and signal in row.signals


# ---------- TF21-22: taxonomy.py imports nothing outside the standard library and rows ----------


def test_tf21_22_taxonomy_imports_only_the_standard_library_and_rows() -> None:
    import ast
    import sys
    from pathlib import Path

    tree = ast.parse(Path(taxonomy.__file__).read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module)
    allowed = set(sys.stdlib_module_names) | {"__future__", "poisson_trace.ingest.rows"}
    assert {r if r.startswith("poisson_trace") else r.split(".")[0] for r in roots} <= allowed
