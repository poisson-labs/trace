"""TF25-16 to TF25-27: the signals, the failure kinds, scores and feedback, and what is kept (spec
sections 18.1 and 18.1.1 row 10, 18.4.1 and 18.4.2 as TF21's SA1 reads them, 18.5.2's Braintrust
row; SG2; IC7; the LangSmith pair's LS-7 to LS-14 in Braintrust's words).

- TF25-16: time. The wall time is the root's end less its start, from every export, and never
  the summary's ``duration``, which is the task span's; the time to first token is Braintrust's
  own figure for the model call, the same from every export, and not recorded where the trace
  made no model call.
- TF25-17: lengths. The characters of every value in the root's input and output, keys and
  punctuation not counted; an errored root's null output is not recorded.
- TF25-18: tokens and cost. From the spans, summed over the trace's ``llm`` spans; from the
  summary and the page's rows, the row's rolled-up metrics; the same figures either way, cached
  and reasoning tokens among them (recorded zeros), and where each came from kept beside the
  row. Where a trace made no model call the spans record nothing and the rolled-up row says 0
  tokens: each export's own fact, kept as it is; no export records a cost there.
- TF25-19: structure. From the spans: steps are the spans with no child, the grading spans
  left out; LLM calls the ``llm`` spans (a recorded zero where there is none); tool calls the
  ``tool`` spans in start order with their names, how each ended, its time and the class of its
  error; a call that follows a failed call of the same name is attempt 2 and one retry. The
  summary and the page's rows give the count of model calls alone.
- TF25-20: the kinds on the captures, through the one rule set. A failed case takes the kind
  its classification names (the baseline's two stale answers wrong answers, its ``unknown`` an
  abstention). The baseline's failed tool call is a timeout wherever the traceback is whole
  (the spans, the page's rows) and a tool error from the summary, which cuts the traceback and
  counts a tool error; the candidate's cut reply is a crash from the spans and the page's rows
  (a function span raised a ``ValueError``) and unclassified from the summary. A passed row has
  no kind. Where no classification names the kind, it is the one TF21's reference gives.
- TF25-21: the kinds section 18.5.2 names that the captures lack, on a capture edited in one
  place: a last line saying a rate limit, a context overflow or a timeout; the kind of the span
  that failed; a classification or a tag naming a kind, on a failed row alone; three calls in a
  row to one tool under a root that succeeded and failed its score (a loop).
- TF25-22: scores and feedback. The scores are the row's scores, the same from every export;
  a classification is feedback, its word the ids of its items, read alike from the API's list
  and the page's string of JSON; tags and comments are not kept.
- TF25-23: the store's trace, from the spans: one span an event of the agent's work (the
  grading spans, ``score`` and ``classifier``, are read for what they hold and left out, so a
  failure is placed on the agent's last step and never on its grader), its parent the first of
  ``span_parents``, ids the spans' own, kinds by span type (``llm``, ``tool``, else ``other``),
  the model's name beside an ``llm`` span; ``where`` reads the run. The summary and the page's
  rows write no trace.
- TF25-24: the columns Prove reads: ``t`` the steps (1 where none is recorded), ``wall_time``
  the wall time, ``confidence`` the score read; ``meta["cost_usd"]`` only where a cost was
  recorded.
- TF25-25: no content. No prompt, input, output, error, traceback or path text of the captures
  is in any file of the store or in anything printed.
- TF25-26: every stored record has exactly the writer's keys; ``horizon``, ``working_time_s``
  and the signals no Braintrust export records are not recorded.
- TF25-27: the record is checked against a second reading of the files, written here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tf21_support import RECORD_KEYS, run_import
from tf25_support import (
    ANSWER, CASES, CLASSIFIED, CONTENT, ERRORED, EXACT, EXPORTS, GAVE_ANSWER, ITEM, LOOKUP, QUESTIONS, ROW_EXPORTS, RUN,
    SPAN_EXPORTS, TTFT, USAGE, VERSIONS, WALL, approx, bt_argv, by_error, children, columns, edited, export, imported, metas,
    recs, roots, rows_of, span_type, stored_bytes, trace_rows, traceback_of, tries, work_spans, world,
)

BOTH = [(v, k) for v in VERSIONS for k in EXPORTS]
BOTH_SPANS = [(v, k) for v in VERSIONS for k in SPAN_EXPORTS]
BOTH_ROWS = [(v, k) for v in VERSIONS for k in ROW_EXPORTS]
PAGE = ("ui-json", "ui-csv")
#: The kind each export reaches for the case that errored, by version: from the spans, from the
#: summary, and from the page's rows.
ERRORED_KIND = {
    "baseline": {"span": "timeout", "summary": "tool_error", "ui": "timeout"},
    "candidate": {"span": "crash", "summary": "unclassified_error", "ui": "crash"},
}


def _family(kind: str) -> str:
    return "span" if kind in SPAN_EXPORTS else "summary" if kind == "summary" else "ui"


# ---------- TF25-16 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf25_16_the_wall_time_is_the_root_s_end_less_its_start(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "error")
    stored = recs(root, RUN)
    for case in CASES:
        assert approx(stored[case]["wall_time_s"], WALL[version][case], 1e-6), (case, stored[case]["wall_time_s"])
        assert stored[case]["working_time_s"] is None


@pytest.mark.parametrize("version", VERSIONS)
def test_tf25_16_the_summary_s_duration_is_not_the_wall_time(tmp_path_factory: Any, version: str) -> None:
    root, _ = world(tmp_path_factory, version, "summary", "error")
    stored = recs(root, RUN)
    rolled = {case: r["metrics"]["duration"] for case, r in roots(rows_of(export(version, "summary")[0])).items()}
    for case in CASES:
        assert rolled[case] < WALL[version][case] and not approx(stored[case]["wall_time_s"], rolled[case], 1e-5), case


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf25_16_the_time_to_first_token_is_braintrust_s_own(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "error")
    stored = recs(root, RUN)
    assert sum(1 for v in TTFT[version].values() if v is None) == (1 if version == "baseline" else 0)
    for case in CASES:
        got, want = stored[case]["ttft_s"], TTFT[version][case]
        if want is None:
            assert got is None, (case, got)
        else:
            assert approx(got, want, 1e-9) and 0 < got <= stored[case]["wall_time_s"], (case, got, want)


@pytest.mark.parametrize("name", LOOKUP)
@pytest.mark.parametrize("kind", EXPORTS)
def test_tf25_16_no_model_call_no_time_to_first_token(tmp_path_factory: Any, name: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, name, kind, "exact")
    assert all(rec["ttft_s"] is None for rec in tries(root, RUN).values())


# ---------- TF25-17 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf25_17_the_lengths_are_the_characters_of_the_values(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "error")
    stored = recs(root, RUN)
    for case in CASES:
        assert stored[case]["input_chars"] == len(case) + len(ITEM[case]), case
        answer = ANSWER[version][case]
        assert stored[case]["output_chars"] == (None if answer is None else len(answer)), case


@pytest.mark.parametrize("kind", ["fetch", "ui-json"])
def test_tf25_17_a_plain_text_input_counts_as_written(tmp_path_factory: Any, kind: str) -> None:
    root, _ = world(tmp_path_factory, "old", kind, "exact")
    got = tries(root, RUN)
    assert {key: rec["input_chars"] for key, rec in got.items()} == {(q, n): 2 for q in QUESTIONS for n in (0, 1)}
    assert got[("q1", 0)]["output_chars"] == len("banana") and got[("q2", 0)]["output_chars"] == len("nope")


@pytest.mark.parametrize("kind", ["fetch", "summary", "ui-csv"])
def test_tf25_17_numbers_count_as_json_writes_them_and_a_missing_value_is_not_recorded(tmp_path: Path, kind: str) -> None:
    def edit(rows: list[dict[str, Any]]) -> None:
        held = roots(rows)
        held["c01"]["output"] = {"n": 12, "ok": True, "nested": {"words": ["ab", "cde"], "none": None}, "x": 1.5}  # type: ignore[index]
        held["c02"]["output"] = 7  # type: ignore[index]
        held["c03"]["output"] = None  # type: ignore[index]
        held["c04"]["output"] = ""  # type: ignore[index]

    path = edited(tmp_path, "baseline", kind, edit)
    imported(by_error(path, tmp_path / "st", "r"))
    stored = recs(tmp_path / "st", "r")
    assert stored["c01"]["output_chars"] == 2 + 4 + 2 + 3 + 3  # 12, true, ab, cde, 1.5
    assert stored["c02"]["output_chars"] == 1
    assert stored["c03"]["output_chars"] is None
    assert stored["c04"]["output_chars"] == 0
    assert stored["c05"]["output_chars"] == len("reorder")


# ---------- TF25-18 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf25_18_tokens_and_cost_are_the_model_calls(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "error")
    stored, held = recs(root, RUN), metas(root, RUN)
    where = "llm spans" if kind in SPAN_EXPORTS else "row metrics"
    for case in CASES:
        usage, rec = USAGE[version][case], stored[case]
        if usage is None:
            continue
        assert (rec["input_tokens"], rec["output_tokens"], rec["total_tokens"]) == usage[:3], case
        assert rec["cost_usd"] == usage[3] and held[case]["cost_usd"] == usage[3], case
        assert rec["cached_tokens"] == 0 and rec["reasoning_tokens"] == 0, case
        assert held[case]["import"]["tokens_from"] == where and held[case]["import"]["cost_from"] == where, held[case]["import"]


@pytest.mark.parametrize("kind", EXPORTS)
def test_tf25_18_a_trace_with_no_model_call_records_what_its_export_says_and_no_more(tmp_path_factory: Any, kind: str) -> None:
    """The baseline's c08 stopped at its tool, before any model call. Its spans hold no token
    count; the summary and the page's rows roll the trace up and write 0 tokens. No export
    writes a cost. Not recorded is kept apart from zero either way."""
    root, _ = world(tmp_path_factory, "baseline", kind, "error")
    rec, meta = recs(root, RUN)["c08"], metas(root, RUN)["c08"]
    assert rec["cost_usd"] is None and "cost_usd" not in meta and "cost_from" not in meta["import"]
    tokens = (rec["input_tokens"], rec["output_tokens"], rec["total_tokens"], rec["cached_tokens"], rec["reasoning_tokens"])
    if kind in SPAN_EXPORTS:
        assert tokens == (None, None, None, None, None) and "tokens_from" not in meta["import"]
    else:
        assert tokens == (0, 0, 0, 0, 0) and meta["import"]["tokens_from"] == "row metrics"
    assert rec["llm_calls"] == 0


@pytest.mark.parametrize("name", LOOKUP)
@pytest.mark.parametrize("kind", EXPORTS)
def test_tf25_18_an_experiment_that_called_no_model_has_no_cost(tmp_path_factory: Any, name: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, name, kind, "exact")
    for rec in tries(root, RUN).values():
        assert rec["cost_usd"] is None and rec["llm_calls"] == 0
        assert rec["total_tokens"] == (None if kind in SPAN_EXPORTS else 0)


@pytest.mark.parametrize("kind", ["fetch", "summary", "ui-json", "ui-csv"])
def test_tf25_18_the_total_is_the_one_recorded_and_is_not_worked_out(tmp_path: Path, kind: str) -> None:
    """A total that is more than the input and output tokens together (a provider that counts
    its reasoning apart): the total the export wrote is the total kept. A span writes it as
    ``tokens`` and a rolled-up row as ``total_tokens``."""
    def edit(rows: list[dict[str, Any]]) -> None:
        if kind == "fetch":
            llm = next(r for r in work_spans(rows, "c02") if span_type(r) == "llm")
            llm["metrics"]["tokens"] = 500
        else:
            row = roots(rows)["c02"]
            row["metrics"] = {**row["metrics"], "total_tokens": 500}  # type: ignore[index]

    path = edited(tmp_path, "candidate", kind, edit)
    imported(by_error(path, tmp_path / "st", "r"))
    stored = recs(tmp_path / "st", "r")
    assert (stored["c02"]["input_tokens"], stored["c02"]["output_tokens"], stored["c02"]["total_tokens"]) == (86, 7, 500)
    assert stored["c03"]["total_tokens"] == 93


def test_tf25_18_two_model_calls_in_one_trace_are_summed(tmp_path: Path) -> None:
    def edit(rows: list[dict[str, Any]]) -> None:
        llm = next(r for r in work_spans(rows, "c02") if span_type(r) == "llm")
        twin = json.loads(json.dumps(llm))
        twin["id"], twin["span_id"] = twin["id"][:-4] + "ffff", twin["span_id"][:-4] + "ffff"
        twin["metrics"]["start"] += 0.0001
        twin["metrics"]["time_to_first_token"] = 0.123
        rows.append(twin)

    path = edited(tmp_path, "candidate", "fetch", edit)
    imported(by_error(path, tmp_path / "st", "r"))
    rec = recs(tmp_path / "st", "r")["c02"]
    usage = USAGE["candidate"]["c02"]
    assert usage is not None
    assert (rec["input_tokens"], rec["output_tokens"], rec["total_tokens"]) == tuple(2 * n for n in usage[:3])
    assert approx(rec["cost_usd"], 2 * usage[3], 1e-12) and rec["llm_calls"] == 2 and rec["steps"] == 5
    # the first model call's time to first token is the row's
    assert approx(rec["ttft_s"], TTFT["candidate"]["c02"], 1e-9)


# ---------- TF25-19 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH_SPANS)
def test_tf25_19_steps_calls_and_retries_from_the_spans(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "error")
    stored = recs(root, RUN)
    for case in CASES:
        under, rec = children(version, case), stored[case]
        tools = [bad for span, bad in under if span == "tool"]
        assert rec["steps"] == len(under), case
        assert rec["llm_calls"] == sum(1 for span, _ in under if span == "llm"), case
        assert rec["horizon"] is None
        assert rec["tool_call_count"] == len(tools) and rec["tool_error_count"] == sum(tools), case
        assert [c["name"] for c in rec["tool_calls"]] == ["check_stock"] * len(tools), case
        assert [c["status"] for c in rec["tool_calls"]] == ["error" if bad else "ok" for bad in tools], case
        assert rec["retries"] == (1 if (version, case) == ("candidate", "c04") else 0), case
        for call in rec["tool_calls"]:
            assert call["duration_s"] is not None and 0 <= call["duration_s"] < 1, call
        assert rec["signals"] == (["over_budget"] if rec["failure_kind"] == "timeout" else []), (case, rec["signals"])


@pytest.mark.parametrize("kind", SPAN_EXPORTS)
def test_tf25_19_a_call_after_a_failed_call_of_the_same_name_is_the_next_attempt(tmp_path_factory: Any, kind: str) -> None:
    root, _ = world(tmp_path_factory, "candidate", kind, "error")
    stored = recs(root, RUN)
    calls = stored["c04"]["tool_calls"]
    assert [(c["status"], c["attempt"], c["error_type"]) for c in calls] == [("error", 1, "RuntimeError"), ("ok", 2, None)]
    assert all(c["attempt"] == 1 for case in CASES if case != "c04" for c in stored[case]["tool_calls"])
    failed = recs(world(tmp_path_factory, "baseline", kind, "error")[0], RUN)["c08"]["tool_calls"]
    assert [(c["status"], c["attempt"], c["error_type"]) for c in failed] == [("error", 1, "TimeoutError")]


@pytest.mark.parametrize("name", LOOKUP)
def test_tf25_19_the_grading_spans_are_not_steps(tmp_path_factory: Any, name: str) -> None:
    """The lookup fixture's trace is a root, a task and a score span: one step."""
    root, _ = world(tmp_path_factory, name, "fetch", "exact")
    for rec in tries(root, RUN).values():
        assert rec["steps"] == 1 and rec["tool_calls"] == [] and rec["retries"] == 0


@pytest.mark.parametrize(("version", "kind"), BOTH_ROWS)
def test_tf25_19_the_summary_and_the_page_s_rows_give_the_count_of_model_calls_alone(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "error")
    for case, rec in recs(root, RUN).items():
        for key in ("steps", "tool_calls", "tool_call_count", "tool_error_count", "retries", "horizon"):
            assert rec[key] is None, (case, key)
        assert rec["llm_calls"] == sum(1 for span, _ in children(version, case) if span == "llm"), case


# ---------- TF25-20 ----------


def _kinds(root: Path) -> dict[str, Any]:
    return {case: r["failure_kind"] for case, r in recs(root, RUN).items()}


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf25_20_the_kinds_by_the_score(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "exact")
    want: dict[str, Any] = dict.fromkeys(CASES)
    want.update(CLASSIFIED[version])
    want[ERRORED[version][0]] = ERRORED_KIND[version][_family(kind)]
    assert _kinds(root) == want
    assert want["c06"] == "wrong_answer"
    if version == "baseline":
        assert want["c10"] == "abstained" and want["c03"] == "wrong_answer"


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf25_20_the_kinds_by_the_error(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "error")
    bad, error_type, _, span_kind, _ = ERRORED[version]
    want: dict[str, Any] = dict.fromkeys(CASES)
    want[bad] = ERRORED_KIND[version][_family(kind)]
    assert _kinds(root) == want
    rec = recs(root, RUN)[bad]
    family = _family(kind)
    # the summary cuts the traceback short, so the class its last line names is not in that shape
    assert rec["error_type"] == (None if family == "summary" else error_type)
    # the kind of the span that failed: the span itself, or the rolled-up count of tool errors
    assert rec["error_span_kind"] == (span_kind if family == "span" else "tool" if version == "baseline" else None)
    for case, other in recs(root, RUN).items():
        if case != bad:
            assert other["error_type"] is None and other["error_span_kind"] is None, case


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf25_20_where_no_classification_names_it_the_kind_is_tf21_s_reference_s(tmp_path_factory: Any, version: str, kind: str) -> None:
    from tf10_support import ref_kind_of

    for mode in ("error", "exact"):
        root, _ = world(tmp_path_factory, version, kind, mode)
        for case, rec in recs(root, RUN).items():
            if mode == "exact" and case in CLASSIFIED[version]:
                assert rec["failure_kind"] == CLASSIFIED[version][case], (mode, case)
            else:
                assert rec["failure_kind"] == ref_kind_of(rec), (mode, case)


# ---------- TF25-21 ----------

LINES = {
    "rate_limit": "RateLimited: 429 too many requests",
    "rate_limit by words": "RuntimeError: the provider said: rate limit exceeded",
    "context_overflow": "BadRequestError: context_length_exceeded: this model's limit is 8192",
    "timeout by words": "RuntimeError: the call timed out",
}


@pytest.mark.parametrize("kind", ["fetch", "ui-json", "ui-csv"])
@pytest.mark.parametrize("label", list(LINES))
def test_tf25_21_an_error_s_last_line_gives_its_kind(tmp_path: Path, kind: str, label: str) -> None:
    def edit(rows: list[dict[str, Any]]) -> None:
        for row in (trace_rows(rows, "c09") if kind == "fetch" else [roots(rows)["c09"]]):
            if row.get("error"):
                row["error"] = traceback_of(LINES[label])  # type: ignore[index]

    path = edited(tmp_path, "candidate", kind, edit)
    imported(by_error(path, tmp_path / "st", "r"))
    rec = recs(tmp_path / "st", "r")["c09"]
    assert rec["failure_kind"] == label.split()[0], rec
    assert rec["outcome"] == "fail" and rec["error_type"] == LINES[label].split(":")[0]


def test_tf25_21_a_line_inside_the_traceback_is_not_the_error_s(tmp_path: Path) -> None:
    """Only the last line names the error: a file path or a quoted line above it that says
    ``timeout`` does not make the case a timeout."""
    def edit(rows: list[dict[str, Any]]) -> None:
        for row in trace_rows(rows, "c09"):
            if row.get("error"):
                row["error"] = 'Traceback (most recent call last):\n  File "/x/timeout_utils.py", line 3, in wait\n    raise RateLimit("429")\nValueError: bad reply\n'

    path = edited(tmp_path, "candidate", "fetch", edit)
    imported(by_error(path, tmp_path / "st", "r"))
    rec = recs(tmp_path / "st", "r")["c09"]
    assert rec["failure_kind"] == "crash" and rec["error_type"] == "ValueError"


def test_tf25_21_a_summary_s_error_that_is_whole_is_read(tmp_path: Path) -> None:
    def edit(rows: list[dict[str, Any]]) -> None:
        roots(rows)["c09"]["error"] = "RateLimitError: 429 too many requests"  # type: ignore[index]

    path = edited(tmp_path, "candidate", "summary", edit)
    imported(by_error(path, tmp_path / "st", "r"))
    rec = recs(tmp_path / "st", "r")["c09"]
    assert rec["failure_kind"] == "rate_limit" and rec["error_type"] == "RateLimitError"


@pytest.mark.parametrize(("span", "want", "span_kind"), [
    ("llm", "crash", "llm"), ("function", "crash", "other"), ("tool", "tool_error", "tool"), ("task", "crash", "other"),
])
def test_tf25_21_the_span_that_failed_gives_the_kind(tmp_path: Path, span: str, want: str, span_kind: str) -> None:
    """The candidate's c09, whose last step raised an error whose words say nothing: the
    failing span given each type in turn."""
    def edit(rows: list[dict[str, Any]]) -> None:
        failing = [r for r in work_spans(rows, "c09") if r.get("error")]
        assert len(failing) == 1
        failing[0]["span_attributes"]["type"] = span

    path = edited(tmp_path, "candidate", "fetch", edit)
    imported(by_error(path, tmp_path / "st", "r"))
    rec = recs(tmp_path / "st", "r")["c09"]
    assert rec["failure_kind"] == want and rec["error_span_kind"] == span_kind, rec
    assert rec["error_type"] == "ValueError"


@pytest.mark.parametrize("kind", ROW_EXPORTS)
@pytest.mark.parametrize(("counts", "want", "span_kind"), [
    ({"tool_errors": 1}, "tool_error", "tool"), ({"llm_errors": 1}, None, "llm"), ({}, None, None),
])
def test_tf25_21_the_rolled_up_error_counts_give_the_kind_of_the_span_that_failed(tmp_path: Path, kind: str, counts: dict[str, int], want: str | None, span_kind: str | None) -> None:
    def edit(rows: list[dict[str, Any]]) -> None:
        row = roots(rows)["c09"]
        row["metrics"] = {**row["metrics"], "tool_errors": 0, "llm_errors": 0, **counts}  # type: ignore[index]

    path = edited(tmp_path, "candidate", kind, edit)
    imported(by_error(path, tmp_path / "st", "r"))
    rec = recs(tmp_path / "st", "r")["c09"]
    assert rec["error_span_kind"] == span_kind, rec
    if want is not None:
        assert rec["failure_kind"] == want, rec
    else:
        # the words decide where they are whole (the page's rows: a ValueError, a crash)
        assert rec["failure_kind"] == ("unclassified_error" if kind == "summary" else "crash"), rec


@pytest.mark.parametrize("kind", ["fetch", "summary", "ui-json", "ui-csv"])
def test_tf25_21_a_classification_or_a_tag_names_the_kind_of_a_failed_row(tmp_path: Path, kind: str) -> None:
    page = kind in PAGE

    def label(items: list[dict[str, Any]]) -> Any:
        return json.dumps(items, separators=(",", ":")) if page else items

    def edit(rows: list[dict[str, Any]]) -> None:
        held = roots(rows)
        # c03 failed its score: its classification renamed; c06 failed: no classification, a tag
        held["c03"]["classifications"] = {"review": label([{"id": "guardrail_blocked"}])}  # type: ignore[index]
        held["c06"]["classifications"] = None  # type: ignore[index]
        held["c06"]["tags"] = ["baseline", "retrieval_error"]  # type: ignore[index]
        # c10 failed: two labels, the first in the kinds' order wins
        held["c10"]["classifications"] = {"a": label([{"id": "wrong_answer"}, {"id": "format_error"}])}  # type: ignore[index]
        # c01 passed: a label names no kind for a row that did not fail
        held["c01"]["classifications"] = {"review": label([{"id": "tool_error"}])}  # type: ignore[index]
        held["c01"]["tags"] = ["timeout"]  # type: ignore[index]
        # c02 passed and c05 is made to fail with a label that is no kind
        held["c05"]["classifications"] = {"review": label([{"id": "needs-review"}])}  # type: ignore[index]
        if kind == "fetch":
            for case in ("c05",):
                span = next(r for r in trace_rows(rows, case)[1:] if (r["scores"] or {}).get("exact") is not None)
                span["scores"] = {"exact": 0}
            for case in ("c03", "c06", "c10", "c01", "c05"):
                for r in trace_rows(rows, case)[1:]:
                    r["classifications"] = None
        else:
            held["c05"]["scores"] = {**held["c05"]["scores"], "exact": 0}  # type: ignore[index]

    path = edited(tmp_path, "baseline", kind, edit)
    imported(bt_argv(path, tmp_path / "st", "r"))
    stored = recs(tmp_path / "st", "r")
    assert stored["c03"]["failure_kind"] == "guardrail_blocked"
    assert stored["c06"]["failure_kind"] == "retrieval_error"
    assert stored["c10"]["failure_kind"] == "format_error"
    assert stored["c01"]["failure_kind"] is None and stored["c01"]["outcome"] == "pass"
    assert stored["c05"]["outcome"] == "fail" and stored["c05"]["failure_kind"] == "wrong_answer"
    assert stored["c05"]["feedback"] == {"review": "needs-review"}
    assert stored["c10"]["feedback"] == {"a": "wrong_answer,format_error"}


@pytest.mark.parametrize("kind", SPAN_EXPORTS)
def test_tf25_21_three_calls_in_a_row_to_one_tool_under_a_failed_score_is_a_loop(tmp_path: Path, kind: str) -> None:
    def edit(rows: list[dict[str, Any]]) -> None:
        for case in ("c06", "c01", "c03"):
            tool = next(r for r in work_spans(rows, case) if span_type(r) == "tool")
            for n in (1, 2):
                again = json.loads(json.dumps(tool))
                again["id"], again["span_id"] = again["id"][:-4] + f"ff0{n}", again["span_id"][:-4] + f"ff0{n}"
                again["metrics"]["start"] += n * 0.00001
                again["metrics"]["end"] = again["metrics"]["start"]
                rows.append(again)
        # c06 failed its score: with no classification naming a kind, the three calls say a loop
        for r in trace_rows(rows, "c06"):
            r["classifications"] = None

    path = edited(tmp_path, "baseline", kind, edit)
    imported(bt_argv(path, tmp_path / "st", "r"))
    stored = recs(tmp_path / "st", "r")
    assert stored["c06"]["tool_call_count"] == 3 and stored["c06"]["failure_kind"] == "loop_detected"
    # the classification's word is the source's own, and wins over the loop
    assert stored["c03"]["tool_call_count"] == 3 and stored["c03"]["failure_kind"] == "wrong_answer"
    # the same three calls under a row that passed give no kind, and no retry either: none failed
    assert stored["c01"]["tool_call_count"] == 3 and stored["c01"]["failure_kind"] is None
    assert stored["c01"]["retries"] == 0 and stored["c06"]["retries"] == 0


# ---------- TF25-22 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf25_22_the_scores_are_the_row_s_and_a_classification_is_feedback(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "error")
    stored, held = recs(root, RUN), metas(root, RUN)
    for case in CASES:
        scores = {} if EXACT[version][case] is None else {"exact": EXACT[version][case], "gave_answer": GAVE_ANSWER[version][case]}
        assert stored[case]["scores"] == scores, (case, stored[case]["scores"])
        feedback = {"failure_kind": CLASSIFIED[version][case]} if case in CLASSIFIED[version] else {}
        assert stored[case]["feedback"] == feedback, (case, stored[case]["feedback"])
        assert "feedback_sources" not in held[case]["import"] and "tags" not in held[case]["import"], held[case]["import"]


@pytest.mark.parametrize("kind", ["fetch", "summary", "ui-json"])
def test_tf25_22_a_comment_is_never_kept(tmp_path: Path, kind: str) -> None:
    said = "the reviewer wrote: this answer leaks the customer's address"

    def edit(rows: list[dict[str, Any]]) -> None:
        for r in rows:
            r["comments"] = [{"text": said, "created": "2026-11-09T21:00:00Z"}]

    path = edited(tmp_path, "baseline", kind, edit)
    result = run_import(by_error(path, tmp_path / "st", "r"))
    assert result.code == 0 and said not in result.out + result.err, result.err
    assert said.encode() not in stored_bytes(tmp_path / "st")
    assert all("comments" not in rec["feedback"] for rec in recs(tmp_path / "st", "r").values())


# ---------- TF25-23 ----------

KIND_OF = {"llm": "llm", "tool": "tool"}
#: The spans that grade a case: read for their scores and classifications, and left out of the
#: trace, so that a failure is placed on the agent's last step and never on its grader.
GRADING = ("score", "classifier")


@pytest.mark.parametrize(("version", "kind"), BOTH_SPANS)
def test_tf25_23_the_store_s_trace_is_the_spans(tmp_path_factory: Any, version: str, kind: str) -> None:
    from poisson_prove.store import Store

    root, _ = world(tmp_path_factory, version, kind, "error")
    rows = rows_of(export(version, kind)[0])
    df = Store(root).read(RUN, meta=False, trace="envelope")
    seen = 0
    from tf25_support import named

    for r in df.to_dict("records"):
        case = named(r["config"]["case"])
        trace = r["trace"]
        spans = trace["spans"] if isinstance(trace, dict) else json.loads(trace)["spans"]
        # the grading spans are read for their scores and are no part of the trace
        want = [r for r in trace_rows(rows, case) if span_type(r) not in GRADING]
        assert len(spans) == len(want), case
        by_id = {s["span_id"]: s for s in spans}
        for row in want:
            span = by_id[row["span_id"]]
            parents = row["span_parents"] or []
            assert span["parent_id"] == (parents[0] if parents else None), case
            assert span["kind"] == KIND_OF.get(span_type(row), "other"), (case, span_type(row), span["kind"])
            assert span["start_ns"] == round(row["metrics"]["start"] * 1e6) * 1000, case
            if span_type(row) == "llm":
                assert span["attrs"].get("llm.model_name") == "gpt-4.1-mini" or span["name"] == "gpt-4.1-mini", span
            seen += 1
    assert seen == len([r for r in rows if span_type(r) not in GRADING]) == {"baseline": 58, "candidate": 61}[version]


@pytest.mark.parametrize("version", VERSIONS)
def test_tf25_23_where_reads_the_imported_run(tmp_path_factory: Any, version: str) -> None:
    from tf0_support import trace

    root, _ = world(tmp_path_factory, version, "fetch", "error")
    ran = trace(["where", RUN, "--store", str(root), "--event", "missed"])
    assert ran.code == 0, ran.err
    line = next(line for line in ran.out.splitlines() if line.startswith("- placement: "))
    assert "placed 10 " in line and "died 1 " in line and line.rstrip().endswith("excluded 0"), line
    assert "import/braintrust" in ran.out
    # the errored case's last step is the agent's: the baseline's a tool call, the candidate's
    # a function span, which the store calls another kind of step
    said = ran.out.splitlines()[0]
    assert ("a tool call" in said) == (version == "baseline"), said


def test_tf25_23_a_failure_by_the_score_is_placed_on_the_agent_s_last_step(tmp_path_factory: Any) -> None:
    """The three cases the baseline failed by its score each end, in the fetch, with two score
    spans and a classifier span. Their last step in the store is the agent's last span."""
    root, _ = world(tmp_path_factory, "baseline", "fetch", "exact")
    rows = rows_of(export("baseline", "fetch")[0])
    for case in ("c03", "c06", "c10"):
        row = columns(root, RUN)[case]
        spans = (row["trace"] if isinstance(row["trace"], dict) else json.loads(row["trace"]))["spans"]
        last = max(spans, key=lambda s: s["start_ns"])
        assert last["span_id"] == work_spans(rows, case)[-1]["span_id"] and last["name"] == "parse_answer", (case, last["name"])


@pytest.mark.parametrize(("version", "kind"), BOTH_ROWS)
def test_tf25_23_the_summary_and_the_page_s_rows_write_no_trace(tmp_path_factory: Any, version: str, kind: str) -> None:
    from tf0_support import trace

    root, _ = world(tmp_path_factory, version, kind, "error")
    assert all("trace" not in meta for meta in metas(root, RUN).values())
    ran = trace(["where", RUN, "--store", str(root), "--event", "missed"])
    assert ran.code == 0 and "has no traces (it was imported from braintrust)" in ran.out, ran.out + ran.err


# ---------- TF25-24 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf25_24_the_columns_prove_reads(tmp_path_factory: Any, version: str, kind: str) -> None:
    from tf21_support import frame
    from tf25_support import named

    root, _ = world(tmp_path_factory, version, kind, "exact")
    df = frame(root, RUN)
    for _, row in df.iterrows():
        case = named(row["meta"]["trace_signals"]["case"])
        score = EXACT[version][case]
        if score is None:
            # a row with no outcome is placed nowhere: no step count and no score in its columns
            assert row["outcome"] is None or row["outcome"] != row["outcome"], case
            assert row["t"] != row["t"] and row["confidence"] != row["confidence"], case
        else:
            assert row["outcome"] == ("met" if score >= 0.5 else "missed"), case
            assert row["confidence"] == score
            assert row["t"] == (float(len(children(version, case))) if kind in SPAN_EXPORTS else 1.0), case
        assert approx(row["wall_time"], WALL[version][case], 1e-6)
        assert ("cost_usd" in row["meta"]) == (USAGE[version][case] is not None), case


# ---------- TF25-25 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf25_25_no_text_of_the_capture_is_kept_or_printed(tmp_path: Path, version: str, kind: str) -> None:
    files = export(version, kind)
    for argv in (bt_argv(files, tmp_path / "a", "r"), [*by_error(files, tmp_path / "b", "r"), "--json"]):
        result = run_import(argv)
        assert result.code == 0, result.err
        printed = result.out + result.err
        for text in CONTENT:
            assert text not in printed, text
    raw = b"".join(p.read_bytes() for p in files)
    assert sum(1 for text in CONTENT if text.encode() in raw) >= (8 if kind in SPAN_EXPORTS else 1), "the capture holds the texts looked for"
    for folder in ("a", "b"):
        held = stored_bytes(tmp_path / folder)
        for text in (*CONTENT, "caller_filename", "site-packages"):
            assert text.encode() not in held, text
        for item in ITEM.values():
            assert item.encode() not in held, item


# ---------- TF25-26 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf25_26_the_record_has_the_writer_s_keys_and_nothing_braintrust_does_not_record(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "error")
    for case, rec in recs(root, RUN).items():
        assert set(rec) == set(RECORD_KEYS), (case, set(rec) ^ set(RECORD_KEYS))
        assert rec["schema"] == "poisson.trace-signals/1" and rec["repeat"] == 0
        assert rec["horizon"] is None and rec["working_time_s"] is None


# ---------- TF25-27 ----------


def _second_reading(version: str, kind: str) -> dict[str, dict[str, Any]]:
    """Each case's wall time, steps and tool names, read off the export's rows by this file."""
    rows = rows_of(export(version, kind)[0])
    out: dict[str, dict[str, Any]] = {}
    for case, root in roots(rows).items():
        under = work_spans(rows, case)
        tools = [r for r in under if span_type(r) == "tool"]
        out[case] = {
            "wall": root["metrics"]["end"] - root["metrics"]["start"],
            "steps": len(under),
            "tools": [r["span_attributes"]["name"] for r in tools],
            "durations": [r["metrics"]["end"] - r["metrics"]["start"] for r in tools],
        }
    return out


@pytest.mark.parametrize(("version", "kind"), BOTH_SPANS)
def test_tf25_27_the_record_agrees_with_a_second_reading_of_the_file(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "error")
    stored, want = recs(root, RUN), _second_reading(version, kind)
    for case in CASES:
        assert approx(stored[case]["wall_time_s"], want[case]["wall"], 2e-6), case
        assert stored[case]["steps"] == want[case]["steps"] == len(children(version, case)), case
        assert [c["name"] for c in stored[case]["tool_calls"]] == want[case]["tools"], case
        for call, duration in zip(stored[case]["tool_calls"], want[case]["durations"], strict=True):
            assert approx(call["duration_s"], duration, 2e-6), case
    assert columns(root, RUN)
