"""TF26-16 to TF26-27: the signals, the failure kinds, scores and feedback, and what is kept.

- TF26-16: time. The wall time is Weave's own figure for the model's run
  (``output.model_latency``), the same from every export, and never the call's end less its
  start, which also holds the scorers; where a row holds no such figure it is the call's end
  less its start. Weave records no time to first token, and none is written.
- TF26-17: lengths. The characters of every value of the example (its reference left out) and
  of the model's output, keys and punctuation not counted. Where the file holds a reference in
  a value's place (the example in the service's plain answer, the lookup fixture's output
  everywhere) the length is not recorded; an errored case's null output is not recorded.
- TF26-18: tokens and cost. The call's own summary, the same from every export that holds them:
  the service's answers and the page's JSON hold input, output and total; the page's table
  holds the total alone. Cached and reasoning tokens are recorded zeros. A cost is recorded
  only where the answer was asked for costs (never from the plain answer or the page's
  downloads), and the rows that record tokens and no cost are counted. A case that called no
  model records no token and no cost. Where each was read from is kept beside the row.
- TF26-19: structure. From the calls under a row: steps are the calls under the model's call
  with no call under them, the scorers' calls left out; LLM calls the calls marked ``llm``;
  tool calls the calls marked ``tool`` (the captures mark none); a call that follows a failed
  call of the same op is the next attempt and one retry. From the page's rows: the count of
  model calls from the summary's requests, and nothing else of the structure.
- TF26-20: the kinds on the captures, through the one rule set. A failed case that did not
  error is a wrong answer. The baseline's failed stock check is a timeout and the candidate's
  cut reply a crash where the exception is in the file (the service's answers); from the
  page's rows, which hold no exception, each is unclassified. A passed row has no kind.
- TF26-21: the kinds the rule set names that the captures lack, on a capture edited in one
  place: an exception whose class or words say a rate limit, a context overflow or a timeout;
  the kind of the call that failed; three calls in a row to one tool under a case that
  answered and failed its score (a loop).
- TF26-22: scores and feedback. The scores are the scorers' outputs, the same from every
  export. A reaction on the row's call is its feedback, from the answers that were asked for
  feedback; a note is never read or kept; the scorers' outputs repeated as feedback on the
  model's call add nothing.
- TF26-23: the store's trace, from the calls: the row's call, the model's call and the calls
  under it (the scorers' calls left out, so a failure is placed on the agent's last step), ids
  the calls' own, kinds by the call's mark, the model's name beside a model call; ``where``
  reads the run. The page's rows write no trace.
- TF26-24: the columns Prove reads: ``t`` the steps (1 where none is recorded), ``wall_time``
  the wall time, ``confidence`` the score read; ``meta["cost_usd"]`` only where a cost was
  recorded.
- TF26-25: no content. No prompt, input, output, error, note or path text of the captures is in
  any file of the store or in anything printed.
- TF26-27: the record is checked against a second reading of the files, written here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tf21_support import run_import
from tf26_support import (
    ANSWER, API_EXPORTS, CASES, CONTENT, ERRORED, EXACT, EXPECTED, EXPORTS, GAVE_ANSWER, ITEM, LATENCY, LLM_OP, LOOKUP, LOOKUP_EXPECTED,
    MODEL, QUESTIONS, RETRIED, RUN, THUMBS_DOWN, UI_CALLS, UI_EXPORTS, UI_TABLES, USAGE, VERSIONS, WITH_ROW, approx, by_status,
    calls_of, columns, edited, edited_table, exception, export, imported, input_chars, metas, model_call, named, of, op, picked, recs,
    rows_by_case, span_id, steps, stored_bytes, stored_spans, table_rows, tries, under, work_calls, world, wv_argv,
)

BOTH = [(v, k) for v in VERSIONS for k in EXPORTS]
BOTH_API = [(v, k) for v in VERSIONS for k in API_EXPORTS]
BOTH_UI = [(v, k) for v in VERSIONS for k in UI_EXPORTS]
#: The candidate's answers, which add the one with neither include flag and the one in pages.
CANDIDATE = (*EXPORTS, "plain", "pages")
#: Every export of both versions: the plain answer and the pages are the candidate's alone.
EVERY = [*BOTH, ("candidate", "plain"), ("candidate", "pages")]
#: The exports asked for costs and feedback.
ASKED = ("pull", "expanded", "pages")
#: The kind each export reaches for the case that errored: where the exception is in the file,
#: and from the page's rows, which hold none.
UNCLASSIFIED = "unclassified_error"


def _case(kind: str) -> str:
    return "example:id" if kind in UI_TABLES else "example"


def _has_calls(kind: str) -> bool:
    return kind not in UI_EXPORTS


# ---------- TF26-16 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf26_16_the_wall_time_is_weave_s_own_figure_for_the_model_s_run(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "status")
    stored = recs(root, RUN)
    for case in CASES:
        assert stored[case]["wall_time_s"] == LATENCY[version][case], (case, stored[case]["wall_time_s"])
        assert stored[case]["working_time_s"] is None and stored[case]["ttft_s"] is None


@pytest.mark.parametrize("version", VERSIONS)
def test_tf26_16_the_call_s_end_less_its_start_is_not_the_wall_time(version: str) -> None:
    """The row's call also holds its scorers: it is longer than the model's run in every case."""
    from datetime import datetime

    for case, row in rows_by_case(calls_of(export(version, "pull")[0]), version).items():
        whole = (datetime.fromisoformat(row["ended_at"]) - datetime.fromisoformat(row["started_at"])).total_seconds()
        assert whole > LATENCY[version][case] and whole - LATENCY[version][case] > 1e-4, case


@pytest.mark.parametrize("kind", ["pull", "ui-json", "ui-csv"])
def test_tf26_16_a_row_with_no_figure_takes_its_call_s_end_less_its_start(tmp_path: Path, kind: str) -> None:
    if kind == "ui-csv":
        def drop(rows: list[dict[str, str]]) -> None:
            table_rows(rows, "baseline")["c02"]["output.model_latency"] = ""

        path = edited_table(tmp_path, kind, drop)
    else:
        def drop(calls: list[dict[str, Any]]) -> None:  # type: ignore[misc]
            del rows_by_case(calls, "baseline")["c02"]["output"]["model_latency"]

        path = edited(tmp_path, "baseline", kind, drop)
    imported(by_status(path, tmp_path / "st", "r", *picked("baseline", kind), case=_case(kind)))
    stored = recs(tmp_path / "st", "r")
    # 20:28:05.655914 to 20:28:06.441035
    assert approx(stored["c02"]["wall_time_s"], 0.785121, 1e-9), stored["c02"]["wall_time_s"]
    assert stored["c03"]["wall_time_s"] == LATENCY["baseline"]["c03"]


@pytest.mark.parametrize("name", LOOKUP)
@pytest.mark.parametrize("kind", EXPORTS)
def test_tf26_16_no_time_to_first_token_is_written(tmp_path_factory: Any, name: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, name, kind, "exact")
    assert all(rec["ttft_s"] is None and rec["wall_time_s"] > 0 for rec in tries(root, RUN).values())


# ---------- TF26-17 ----------


@pytest.mark.parametrize("kind", CANDIDATE)
def test_tf26_17_the_lengths_are_the_characters_of_the_values(tmp_path_factory: Any, kind: str) -> None:
    root, _ = world(tmp_path_factory, "candidate", kind, "status")
    stored = recs(root, RUN)
    for case in CASES:
        # the service's answer holds a reference where the row is, unless the example is expanded
        want = input_chars(case) if kind in WITH_ROW else None
        assert stored[case]["input_chars"] == want, (case, stored[case]["input_chars"])
        answer = ANSWER["candidate"][case]
        assert stored[case]["output_chars"] == (None if answer is None else len(answer)), case
    assert input_chars("c01") == len("c01") * 2 + len(ITEM["c01"]) + len(EXPECTED["c01"])


@pytest.mark.parametrize("kind", ["pull", "expanded", "ui-jsonl", "ui-csv"])
def test_tf26_17_a_reference_in_the_output_s_place_is_not_recorded(tmp_path_factory: Any, kind: str) -> None:
    """The lookup fixture's model answers with an attribute of itself, which Weave saves as a
    reference to it in every export: the output's text is not in the file."""
    root, _ = world(tmp_path_factory, "old", kind, "exact")
    for (question, _), rec in tries(root, RUN).items():
        assert rec["output_chars"] is None, question
        want = 2 * len(question) + len(LOOKUP_EXPECTED[question]) if kind in WITH_ROW else None
        assert rec["input_chars"] == want, question


@pytest.mark.parametrize("kind", ["expanded", "ui-json"])
def test_tf26_17_numbers_count_as_json_writes_them_and_a_missing_value_is_not_recorded(tmp_path: Path, kind: str) -> None:
    def edit(calls: list[dict[str, Any]]) -> None:
        held = rows_by_case(calls, "baseline")
        held["c01"]["output"]["output"] = {"n": 12, "ok": True, "nested": {"words": ["ab", "cde"], "none": None}, "x": 1.5}
        held["c02"]["output"]["output"] = 7
        held["c03"]["output"]["output"] = None
        held["c04"]["output"]["output"] = ""
        held["c05"]["inputs"]["example"] = {"_ref": held["c05"]["inputs"]["example"]["_ref"], "n": 12, "words": ["ab", "cde"], "none": None}

    path = edited(tmp_path, "baseline", kind, edit)
    imported(by_status(path, tmp_path / "st", "r", *picked("baseline", kind)))
    stored = recs(tmp_path / "st", "r")
    assert stored["c01"]["output_chars"] == 2 + 4 + 2 + 3 + 3  # 12, true, ab, cde, 1.5
    assert stored["c02"]["output_chars"] == 1
    assert stored["c03"]["output_chars"] is None
    assert stored["c04"]["output_chars"] == 0
    assert stored["c05"]["output_chars"] == len("reorder") and stored["c05"]["input_chars"] == 2 + 2 + 3
    assert stored["c06"]["input_chars"] == input_chars("c06")


@pytest.mark.parametrize("kind", UI_TABLES)
def test_tf26_17_an_output_spread_over_a_table_s_columns_is_measured_whole(tmp_path: Path, kind: str) -> None:
    """A model that answers an object: the page's table writes each of its values in a column of
    its own (``output.output.KEY``), and their characters are the output's length."""
    def spread(rows: list[dict[str, str]]) -> None:
        row = table_rows(rows, "baseline")["c01"]
        row["output.output"] = ""
        row["output.output.answer"], row["output.output.stock"] = "hold", "14"

    path = edited_table(tmp_path, kind, spread, header=lambda fields: [*fields, "output.output.answer", "output.output.stock"])
    imported(by_status(path, tmp_path / "st", "r", *picked("baseline", kind), case="example:id"))
    stored = recs(tmp_path / "st", "r")
    assert stored["c01"]["output_chars"] == len("hold") + len("14") and stored["c01"]["outcome"] == "pass"
    assert stored["c02"]["output_chars"] == len("reorder")


# ---------- TF26-18 ----------


@pytest.mark.parametrize(("version", "kind"), EVERY)
def test_tf26_18_tokens_and_cost_are_the_call_s_own_summary(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, data = world(tmp_path_factory, version, kind, "status")
    stored, held = recs(root, RUN), metas(root, RUN)
    with_tokens = 0
    for case in CASES:
        usage, rec = USAGE[version][case], stored[case]
        if usage is None:
            continue
        with_tokens += 1
        # the page's table holds a model's total and no prompt or completion count
        want = (None, None, usage[2]) if kind in UI_TABLES else usage[:3]
        assert (rec["input_tokens"], rec["output_tokens"], rec["total_tokens"]) == want, (case, kind)
        assert rec["cached_tokens"] == 0 and rec["reasoning_tokens"] == 0, case
        assert held[case]["import"]["tokens_from"] == "call summary", held[case]["import"]
        if kind in ASKED:
            assert rec["cost_usd"] == usage[3] and held[case]["cost_usd"] == usage[3], case
            assert held[case]["import"]["cost_from"] == "call summary"
        else:
            assert rec["cost_usd"] is None and "cost_usd" not in held[case] and "cost_from" not in held[case]["import"], case
    # an export that carries no cost says so: the rows that record tokens and no cost are counted
    assert data["counts"]["no cost recorded"] == (0 if kind in ASKED else with_tokens)
    assert with_tokens == {"baseline": 9, "candidate": 10}[version]


def test_tf26_18_a_cost_is_the_prompt_and_the_completion_costs_together() -> None:
    for version in VERSIONS:
        for case, row in rows_by_case(calls_of(export(version, "pull")[0]), version).items():
            usage = USAGE[version][case]
            if usage is None:
                assert "costs" not in row["summary"]["weave"] and "usage" not in row["summary"], case
                continue
            cost = row["summary"]["weave"]["costs"][MODEL]
            assert cost["prompt_tokens_total_cost"] + cost["completion_tokens_total_cost"] == usage[3], case
            assert (cost["prompt_tokens"], cost["completion_tokens"], cost["total_tokens"]) == usage[:3]


@pytest.mark.parametrize("kind", EXPORTS)
def test_tf26_18_a_case_that_called_no_model_records_no_token_and_no_cost(tmp_path_factory: Any, kind: str) -> None:
    """The baseline's c08 stopped at its stock check, before any model call: its call's summary
    holds no usage in any export. Not recorded is kept apart from zero."""
    root, _ = world(tmp_path_factory, "baseline", kind, "status")
    rec, meta = recs(root, RUN)["c08"], metas(root, RUN)["c08"]
    assert rec["cost_usd"] is None and "cost_usd" not in meta and "cost_from" not in meta["import"]
    tokens = (rec["input_tokens"], rec["output_tokens"], rec["total_tokens"], rec["cached_tokens"], rec["reasoning_tokens"])
    assert tokens == (None, None, None, None, None) and "tokens_from" not in meta["import"]
    # the calls under the row say there was no model call; the page's row alone cannot
    assert rec["llm_calls"] == (0 if _has_calls(kind) else None)


@pytest.mark.parametrize("name", LOOKUP)
@pytest.mark.parametrize("kind", EXPORTS)
def test_tf26_18_an_evaluation_that_called_no_model_has_no_cost(tmp_path_factory: Any, name: str, kind: str) -> None:
    root, data = world(tmp_path_factory, name, kind, "exact")
    for rec in tries(root, RUN).values():
        assert rec["cost_usd"] is None and rec["total_tokens"] is None
        assert rec["llm_calls"] == (0 if _has_calls(kind) else None)
    assert data["counts"]["no cost recorded"] == 0


@pytest.mark.parametrize("kind", ["pull", "ui-json", "ui-csv"])
def test_tf26_18_the_total_is_the_one_recorded_and_is_not_worked_out(tmp_path: Path, kind: str) -> None:
    """A total that is more than the input and output tokens together (a provider that counts
    its reasoning apart): the total the export wrote is the total kept."""
    if kind == "ui-csv":
        def edit(rows: list[dict[str, str]]) -> None:
            table_rows(rows, "candidate")["c02"][f"summary.usage.{MODEL}.total_tokens"] = "500"

        path = edited_table(tmp_path, kind, edit)
    else:
        def edit(calls: list[dict[str, Any]]) -> None:  # type: ignore[misc]
            rows_by_case(calls, "candidate")["c02"]["summary"]["usage"][MODEL]["total_tokens"] = 500

        path = edited(tmp_path, "candidate", kind, edit)
    imported(by_status(path, tmp_path / "st", "r", *picked("candidate", kind), case=_case(kind)))
    stored = recs(tmp_path / "st", "r")
    want = (None, None, 500) if kind == "ui-csv" else (86, 7, 500)
    assert (stored["c02"]["input_tokens"], stored["c02"]["output_tokens"], stored["c02"]["total_tokens"]) == want
    assert stored["c03"]["total_tokens"] == 93


def test_tf26_18_two_models_in_one_call_s_summary_are_summed(tmp_path: Path) -> None:
    def edit(calls: list[dict[str, Any]]) -> None:
        row = rows_by_case(calls, "candidate")["c02"]
        # a second model, whose provider names its counts the other way
        row["summary"]["usage"]["other-model"] = {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14, "requests": 2}
        row["summary"]["weave"]["costs"]["other-model"] = {"prompt_tokens_total_cost": 0.001, "completion_tokens_total_cost": 0.002, "requests": 2}

    path = edited(tmp_path, "candidate", "pull", edit)
    imported(by_status(path, tmp_path / "st", "r"))
    rec = recs(tmp_path / "st", "r")["c02"]
    usage = USAGE["candidate"]["c02"]
    assert usage is not None
    assert (rec["input_tokens"], rec["output_tokens"], rec["total_tokens"]) == (usage[0] + 10, usage[1] + 4, usage[2] + 14)
    assert approx(rec["cost_usd"], usage[3] + 0.003, 1e-12)
    # the second model recorded no cached and no reasoning count: the first's zeros stand
    assert rec["cached_tokens"] == 0 and rec["reasoning_tokens"] == 0


@pytest.mark.parametrize("kind", ["pull", "expanded"])
def test_tf26_18_costs_that_hold_no_figure_record_no_cost(tmp_path: Path, kind: str) -> None:
    """An answer asked for costs whose call holds none it can price (an unknown model): not
    recorded, never zero, and counted with the rows that record tokens and no cost."""
    def edit(calls: list[dict[str, Any]]) -> None:
        rows = rows_by_case(calls, "candidate")
        rows["c02"]["summary"]["weave"]["costs"] = {}
        rows["c03"]["summary"]["weave"]["costs"] = {MODEL: {"prompt_tokens": 86, "requests": 1}}

    path = edited(tmp_path, "candidate", kind, edit)
    data = imported(by_status(path, tmp_path / "st", "r"))
    stored, held = recs(tmp_path / "st", "r"), metas(tmp_path / "st", "r")
    for case in ("c02", "c03"):
        assert stored[case]["cost_usd"] is None and "cost_usd" not in held[case] and "cost_from" not in held[case]["import"], case
    assert stored["c04"]["cost_usd"] is not None and data["counts"]["no cost recorded"] == 2


@pytest.mark.parametrize("kind", UI_CALLS)
def test_tf26_18_a_summary_that_names_the_requests_gives_the_count_of_model_calls(tmp_path: Path, kind: str) -> None:
    def edit(calls: list[dict[str, Any]]) -> None:
        rows_by_case(calls, "candidate")["c02"]["summary"]["usage"][MODEL]["requests"] = 3

    path = edited(tmp_path, "candidate", kind, edit)
    imported(by_status(path, tmp_path / "st", "r", *picked("candidate", kind)))
    stored = recs(tmp_path / "st", "r")
    assert stored["c02"]["llm_calls"] == 3 and stored["c03"]["llm_calls"] == 1


# ---------- TF26-19 ----------


@pytest.mark.parametrize(("version", "kind"), [(v, k) for v, k in EVERY if k not in UI_EXPORTS])
def test_tf26_19_steps_calls_and_retries_from_the_calls_under_a_row(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "status")
    stored = recs(root, RUN)
    for case in CASES:
        held, rec = steps(version, case), stored[case]
        assert rec["steps"] == len(held), case
        assert rec["llm_calls"] == sum(1 for name, _ in held if name == LLM_OP), case
        assert rec["horizon"] is None
        # no op of the captures is marked a tool: no tool call is recorded, and that is a recorded none
        assert rec["tool_calls"] == [] and rec["tool_call_count"] == 0 and rec["tool_error_count"] == 0, case
        # a call after a failed call of the same op is the next attempt, whatever the op is
        assert rec["retries"] == (1 if (version, case) == RETRIED else 0), case
        assert rec["signals"] == (["over_budget"] if rec["failure_kind"] == "timeout" else []), (case, rec["signals"])


@pytest.mark.parametrize("kind", API_EXPORTS)
def test_tf26_19_the_calls_marked_tool_are_the_tool_calls(tmp_path: Path, kind: str) -> None:
    """The captures' ops carry no mark but the model call's. With the stock check marked a tool,
    as an op can be: its calls are the tool calls, in start order."""
    def mark(calls: list[dict[str, Any]]) -> None:
        for call in calls:
            if op(call) == "check_stock":
                call["attributes"]["weave"]["kind"] = "tool"

    for version in VERSIONS:
        path = edited(tmp_path / version, version, kind, mark)
        imported(by_status(path, tmp_path / "st", version))
    stored = recs(tmp_path / "st", "candidate")
    calls = stored["c04"]["tool_calls"]
    assert [(c["name"], c["status"], c["attempt"], c["error_type"]) for c in calls] == [
        ("check_stock", "error", 1, "RuntimeError"), ("check_stock", "ok", 2, None)]
    assert stored["c04"]["tool_call_count"] == 2 and stored["c04"]["tool_error_count"] == 1 and stored["c04"]["retries"] == 1
    assert all(len(stored[c]["tool_calls"]) == 1 and stored[c]["tool_calls"][0]["attempt"] == 1 for c in CASES if c != "c04")
    for call in calls:
        assert call["duration_s"] is not None and 0 <= call["duration_s"] < 1, call
    failed = recs(tmp_path / "st", "baseline")["c08"]
    assert [(c["status"], c["attempt"], c["error_type"]) for c in failed["tool_calls"]] == [("error", 1, "TimeoutError")]
    assert failed["error_span_kind"] == "tool"


@pytest.mark.parametrize("name", LOOKUP)
@pytest.mark.parametrize("kind", API_EXPORTS)
def test_tf26_19_the_scorers_calls_are_not_steps(tmp_path_factory: Any, name: str, kind: str) -> None:
    """A lookup row holds the model's call and a scorer's: one step, the model's call itself."""
    root, _ = world(tmp_path_factory, name, kind, "exact")
    for rec in tries(root, RUN).values():
        assert rec["steps"] == 1 and rec["tool_calls"] == [] and rec["retries"] == 0 and rec["llm_calls"] == 0


def test_tf26_19_the_model_s_call_is_the_one_made_on_the_row_s_model_whichever_started_first(tmp_path: Path) -> None:
    def early(calls: list[dict[str, Any]]) -> None:
        row = rows_by_case(calls, "candidate")["c02"]
        scorer = next(c for c in under(calls, row) if op(c) == "exact")
        scorer["started_at"] = row["started_at"]

    path = edited(tmp_path, "candidate", "pull", early)
    imported(by_status(path, tmp_path / "st", "r"))
    rec = recs(tmp_path / "st", "r")["c02"]
    assert rec["steps"] == 4 and rec["llm_calls"] == 1


@pytest.mark.parametrize(("version", "kind"), BOTH_UI)
def test_tf26_19_the_page_s_rows_give_the_count_of_model_calls_alone(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "status")
    for case, rec in recs(root, RUN).items():
        for key in ("steps", "tool_calls", "tool_call_count", "tool_error_count", "retries", "horizon"):
            assert rec[key] is None, (case, key)
        assert rec["llm_calls"] == (None if USAGE[version][case] is None else 1), case


# ---------- TF26-20 ----------


def _kinds(root: Path) -> dict[str, Any]:
    return {case: r["failure_kind"] for case, r in recs(root, RUN).items()}


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf26_20_the_kinds_by_the_score(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "exact")
    want: dict[str, Any] = dict.fromkeys(CASES)
    want.update({case: "wrong_answer" for case, score in EXACT[version].items() if score == 0.0})
    want[ERRORED[version][0]] = ERRORED[version][4] if _has_calls(kind) else UNCLASSIFIED
    assert _kinds(root) == want
    assert want["c06"] == "wrong_answer"


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf26_20_the_kinds_by_the_status(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "status")
    bad, error_type, _, span_kind, reached = ERRORED[version]
    want: dict[str, Any] = dict.fromkeys(CASES)
    want[bad] = reached if _has_calls(kind) else UNCLASSIFIED
    assert _kinds(root) == want
    rec = recs(root, RUN)[bad]
    # the page's rows hold no exception: the step that raised is not in that view
    assert rec["error_type"] == (error_type if _has_calls(kind) else None)
    assert rec["error_span_kind"] == (span_kind if _has_calls(kind) else None)
    for case, other in recs(root, RUN).items():
        if case != bad:
            assert other["error_type"] is None and other["error_span_kind"] is None, case


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf26_20_every_kind_is_the_one_tf21_s_reference_gives(tmp_path_factory: Any, version: str, kind: str) -> None:
    from tf10_support import ref_kind_of

    for mode in ("status", "exact"):
        root, _ = world(tmp_path_factory, version, kind, mode)
        for case, rec in recs(root, RUN).items():
            assert rec["failure_kind"] == ref_kind_of(rec), (mode, case)


def test_tf26_20_the_exception_is_on_the_step_that_raised_and_on_the_model_s_call() -> None:
    for version in VERSIONS:
        bad, error_type, raised_by, _, _ = ERRORED[version]
        calls = calls_of(export(version, "pull")[0])
        row = rows_by_case(calls, version)[bad]
        last = work_calls(calls, row)[-1]
        assert op(last) == raised_by and json.loads(last["exception"])["type"] == error_type
        assert json.loads(model_call(calls, row)["exception"])["type"] == error_type


# ---------- TF26-21 ----------

WORDS = {
    "rate_limit": ("RateLimited", "429 too many requests"),
    "rate_limit by words": ("RuntimeError", "the provider said: rate limit exceeded"),
    "context_overflow": ("BadRequestError", "context_length_exceeded: this model's limit is 8192"),
    "timeout by words": ("RuntimeError", "the call timed out"),
    "timeout by class": ("ReadTimeout", "no answer"),
}


def _raise(calls: list[dict[str, Any]], kind: str, message: str, case: str = "c09") -> None:
    """Give the candidate's errored case another exception, on the step that raised and on the
    model's call above it."""
    row = rows_by_case(calls, "candidate")[case]
    for call in (*work_calls(calls, row), model_call(calls, row)):
        if call["exception"]:
            call["exception"] = exception(kind, message)


@pytest.mark.parametrize("kind", API_EXPORTS)
@pytest.mark.parametrize("label", list(WORDS))
def test_tf26_21_an_exception_s_class_or_words_give_its_kind(tmp_path: Path, kind: str, label: str) -> None:
    path = edited(tmp_path, "candidate", kind, lambda calls: _raise(calls, *WORDS[label]))
    imported(by_status(path, tmp_path / "st", "r"))
    rec = recs(tmp_path / "st", "r")["c09"]
    assert rec["failure_kind"] == label.split()[0], rec
    assert rec["outcome"] == "fail" and rec["error_type"] == WORDS[label][0]


def test_tf26_21_a_path_in_the_traceback_is_not_the_exception_s_words(tmp_path: Path) -> None:
    """Only the class and the message name the error: a file of the traceback called
    ``timeout_utils.py`` does not make the case a timeout."""
    def edit(calls: list[dict[str, Any]]) -> None:
        row = rows_by_case(calls, "candidate")["c09"]
        for call in (*work_calls(calls, row), model_call(calls, row)):
            if call["exception"]:
                held = json.loads(call["exception"])
                held["traceback"] = [{"filename": "/x/timeout_utils.py", "line_number": 3, "function_name": "rate_limit", "text": "raise RateLimit('429')"}]
                call["exception"] = json.dumps(held)

    path = edited(tmp_path, "candidate", "pull", edit)
    imported(by_status(path, tmp_path / "st", "r"))
    rec = recs(tmp_path / "st", "r")["c09"]
    assert rec["failure_kind"] == "crash" and rec["error_type"] == "ValueError"


@pytest.mark.parametrize("kind", UI_CALLS)
def test_tf26_21_a_row_that_holds_its_own_exception_is_read(tmp_path: Path, kind: str) -> None:
    """The page's rows hold no exception in the captures. A row whose own call raised does:
    its class and its words are read as any call's."""
    def edit(calls: list[dict[str, Any]]) -> None:
        row = rows_by_case(calls, "candidate")["c09"]
        row["summary"]["weave"]["status"] = "error"
        row["exception"] = exception("RateLimitError", "429 too many requests")

    path = edited(tmp_path, "candidate", kind, edit)
    imported(by_status(path, tmp_path / "st", "r", *picked("candidate", kind)))
    rec = recs(tmp_path / "st", "r")["c09"]
    assert rec["failure_kind"] == "rate_limit" and rec["error_type"] == "RateLimitError" and rec["error_span_kind"] is None


@pytest.mark.parametrize(("mark", "want", "span_kind"), [("llm", "crash", "llm"), (None, "crash", "other"), ("tool", "tool_error", "tool"), ("agent", "crash", "other")])
def test_tf26_21_the_call_that_failed_gives_the_kind(tmp_path: Path, mark: str | None, want: str, span_kind: str) -> None:
    """The candidate's c09, whose last step raised an error whose words say nothing: the step
    given each mark in turn."""
    def edit(calls: list[dict[str, Any]]) -> None:
        failing = [c for c in work_calls(calls, rows_by_case(calls, "candidate")["c09"]) if c["exception"]]
        assert len(failing) == 1
        if mark is None:
            failing[0]["attributes"]["weave"].pop("kind", None)
        else:
            failing[0]["attributes"]["weave"]["kind"] = mark

    path = edited(tmp_path, "candidate", "pull", edit)
    imported(by_status(path, tmp_path / "st", "r"))
    rec = recs(tmp_path / "st", "r")["c09"]
    assert rec["failure_kind"] == want and rec["error_span_kind"] == span_kind, rec
    assert rec["error_type"] == "ValueError"


def test_tf26_21_the_step_that_failed_is_the_last_that_raised(tmp_path: Path) -> None:
    """Two steps of one case raised: the model call first, the parse after it. The class and
    the kind recorded are the last one's."""
    def edit(calls: list[dict[str, Any]]) -> None:
        llm = next(c for c in work_calls(calls, rows_by_case(calls, "candidate")["c09"]) if op(c) == LLM_OP)
        llm["exception"] = exception("APIError", "upstream said no")
        llm["summary"]["weave"]["status"] = "error"

    path = edited(tmp_path, "candidate", "pull", edit)
    imported(by_status(path, tmp_path / "st", "r"))
    rec = recs(tmp_path / "st", "r")["c09"]
    assert rec["error_type"] == "ValueError" and rec["error_span_kind"] == "other" and rec["failure_kind"] == "crash", rec


def test_tf26_21_the_model_s_call_is_what_failed_where_no_step_under_it_raised(tmp_path: Path) -> None:
    def edit(calls: list[dict[str, Any]]) -> None:
        for call in work_calls(calls, rows_by_case(calls, "candidate")["c09"]):
            call["exception"] = None
            call["summary"]["weave"]["status"] = "success"

    path = edited(tmp_path, "candidate", "pull", edit)
    imported(by_status(path, tmp_path / "st", "r"))
    rec = recs(tmp_path / "st", "r")["c09"]
    assert rec["outcome"] == "fail" and rec["error_type"] == "ValueError" and rec["failure_kind"] == "crash"
    assert rec["error_span_kind"] == "other"


@pytest.mark.parametrize("kind", API_EXPORTS)
def test_tf26_21_three_calls_in_a_row_to_one_tool_under_a_failed_score_is_a_loop(tmp_path: Path, kind: str) -> None:
    def edit(calls: list[dict[str, Any]]) -> None:
        rows = rows_by_case(calls, "baseline")
        # c03 and c10 failed their score too: one call to the tool, and two, are no loop
        for case in ("c03", "c10"):
            next(c for c in work_calls(calls, rows[case]) if op(c) == "check_stock")["attributes"]["weave"]["kind"] = "tool"
        twin = json.loads(json.dumps(next(c for c in work_calls(calls, rows["c10"]) if op(c) == "check_stock")))
        twin["id"] = twin["id"][:-4] + "ff09"
        calls.append(twin)
        for case in ("c06", "c01"):
            tool = next(c for c in work_calls(calls, rows[case]) if op(c) == "check_stock")
            tool["attributes"]["weave"]["kind"] = "tool"
            for n in (1, 2):
                again = json.loads(json.dumps(tool))
                again["id"] = again["id"][:-4] + f"ff0{n}"
                again["started_at"] = again["started_at"][:-2] + f"{n}Z"
                again["ended_at"] = again["started_at"]
                calls.append(again)

    path = edited(tmp_path, "baseline", kind, edit)
    imported(wv_argv(path, tmp_path / "st", "r"))
    stored = recs(tmp_path / "st", "r")
    assert stored["c06"]["tool_call_count"] == 3 and stored["c06"]["failure_kind"] == "loop_detected"
    # the same three calls under a row that passed give no kind, and no retry either: none failed
    assert stored["c01"]["tool_call_count"] == 3 and stored["c01"]["failure_kind"] is None
    assert stored["c01"]["retries"] == 0 and stored["c06"]["retries"] == 0
    assert stored["c03"]["tool_call_count"] == 1 and stored["c03"]["failure_kind"] == "wrong_answer"
    assert stored["c10"]["tool_call_count"] == 2 and stored["c10"]["failure_kind"] == "wrong_answer"


# ---------- TF26-22 ----------


@pytest.mark.parametrize(("version", "kind"), EVERY)
def test_tf26_22_the_scores_are_the_scorers_outputs_and_a_reaction_is_feedback(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "status")
    stored, held = recs(root, RUN), metas(root, RUN)
    for case in CASES:
        scores = {} if EXACT[version][case] is None else {"exact": EXACT[version][case], "gave_answer": GAVE_ANSWER[version][case]}
        assert stored[case]["scores"] == scores, (case, stored[case]["scores"])
        reaction = ":thumbs_down:" if case in THUMBS_DOWN[version] else ":thumbs_up:"
        # feedback is in the answers that were asked for it, and in no download of the page
        assert stored[case]["feedback"] == ({"reaction": reaction} if kind in ASKED else {}), (case, stored[case]["feedback"])
        assert "feedback_sources" not in held[case]["import"], held[case]["import"]


def test_tf26_22_the_thumbs_down_are_the_cases_that_did_not_pass() -> None:
    for version in VERSIONS:
        assert sorted(THUMBS_DOWN[version]) == sorted(case for case, score in EXACT[version].items() if not score)
        rows = rows_by_case(calls_of(export(version, "pull")[0]), version)
        for case, row in rows.items():
            types = sorted(f["feedback_type"] for f in row["summary"]["weave"]["feedback"])
            assert types == (["wandb.note.1", "wandb.reaction.1"] if case in THUMBS_DOWN[version] else ["wandb.reaction.1"]), case


@pytest.mark.parametrize("kind", API_EXPORTS)
def test_tf26_22_two_reactions_are_kept_in_the_order_they_were_made_and_a_note_never(tmp_path: Path, kind: str) -> None:
    said = "the reviewer wrote: this answer leaks the customer's address"

    def edit(calls: list[dict[str, Any]]) -> None:
        rows = rows_by_case(calls, "baseline")
        first = rows["c01"]["summary"]["weave"]["feedback"][0]
        later = json.loads(json.dumps(first))
        later["id"], later["created_at"] = first["id"][:-4] + "ffff", "2026-11-09T21:00:00.000000Z"
        later["payload"] = {"emoji": "\U0001f44e", "alias": ":thumbs_down:", "detoned": "\U0001f44e", "detoned_alias": ":thumbs_down:"}
        rows["c01"]["summary"]["weave"]["feedback"].insert(0, later)
        for row in rows.values():
            row["summary"]["weave"]["feedback"].append({"feedback_type": "wandb.note.1", "payload": {"note": said}, "created_at": "2026-11-09T21:00:01Z"})
            row["summary"]["weave"]["feedback"].append({"feedback_type": "wandb.annotation.review", "payload": {"value": said}, "created_at": "2026-11-09T21:00:02Z"})

    path = edited(tmp_path, "baseline", kind, edit)
    result = run_import(by_status(path, tmp_path / "st", "r"))
    assert result.code == 0 and said not in result.out + result.err, result.err
    stored = recs(tmp_path / "st", "r")
    assert stored["c01"]["feedback"] == {"reaction": ":thumbs_up:,:thumbs_down:"}
    assert stored["c02"]["feedback"] == {"reaction": ":thumbs_up:"}
    assert said.encode() not in stored_bytes(tmp_path / "st")


def test_tf26_22_the_scorers_outputs_repeated_on_the_model_s_call_add_nothing(tmp_path: Path) -> None:
    """Weave also saves each scorer's output as feedback on the model's call
    (``wandb.runnable.<scorer>``). The scores are read from the row's own output; with that
    feedback taken out, the run is the same."""
    def strip(calls: list[dict[str, Any]]) -> None:
        for call in calls:
            call["summary"]["weave"]["feedback"] = [f for f in call["summary"]["weave"]["feedback"] if not f["feedback_type"].startswith("wandb.runnable.")]

    held = calls_of(export("baseline", "pull")[0])
    assert sum(1 for c in held for f in c["summary"]["weave"]["feedback"] if f["feedback_type"].startswith("wandb.runnable.")) == 18
    path = edited(tmp_path, "baseline", "pull", strip)
    imported(wv_argv(path, tmp_path / "a", "r"))
    imported(wv_argv(export("baseline", "pull"), tmp_path / "b", "r"))
    assert recs(tmp_path / "a", "r") == recs(tmp_path / "b", "r")


# ---------- TF26-23 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH_API)
def test_tf26_23_the_store_s_trace_is_the_row_s_call_and_the_agent_s_calls(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "status")
    calls = calls_of(export(version, kind)[0])
    rows = rows_by_case(calls, version)
    seen = 0
    for case, stored in columns(root, RUN).items():
        row = rows[case]
        model = model_call(calls, row)
        want = [row, model, *work_calls(calls, row)]
        spans = stored_spans(stored)
        # the scorers' calls are read for nothing and are no part of the trace
        assert len(spans) == len(want), case
        by_id = {s["span_id"]: s for s in spans}
        for call in want:
            # a call's id is the span's, without the dashes Weave writes in it
            span = by_id[span_id(call["id"])]
            assert span["parent_id"] == (None if call is row else span_id(call["parent_id"])), case
            assert span["kind"] == ("llm" if op(call) == LLM_OP else "other"), (case, op(call), span["kind"])
            assert span["name"] == op(call)
            if op(call) == LLM_OP:
                assert span["attrs"].get("llm.model_name") == MODEL, span
            seen += 1
    assert seen == {"baseline": 58, "candidate": 61}[version]


@pytest.mark.parametrize("version", VERSIONS)
def test_tf26_23_where_reads_the_imported_run(tmp_path_factory: Any, version: str) -> None:
    from tf0_support import trace

    root, _ = world(tmp_path_factory, version, "pull", "status")
    ran = trace(["where", RUN, "--store", str(root), "--event", "missed"])
    assert ran.code == 0, ran.err
    line = next(line for line in ran.out.splitlines() if line.startswith("- placement: "))
    assert "placed 10 " in line and "died 1 " in line and line.rstrip().endswith("excluded 0"), line
    assert "import/weave" in ran.out


def test_tf26_23_a_failure_by_the_score_is_placed_on_the_agent_s_last_step(tmp_path_factory: Any) -> None:
    """Each row ends, in the file, with its scorers' calls. Its last step in the store is the
    agent's last call."""
    root, _ = world(tmp_path_factory, "baseline", "pull", "exact")
    calls = calls_of(export("baseline", "pull")[0])
    rows = rows_by_case(calls, "baseline")
    for case in ("c03", "c06", "c10"):
        spans = stored_spans(columns(root, RUN)[case])
        last = max(spans, key=lambda s: s["start_ns"])
        assert last["span_id"] == span_id(work_calls(calls, rows[case])[-1]["id"]) and last["name"] == "parse_answer", (case, last["name"])
        assert max(c["started_at"] for c in under(calls, rows[case])) > work_calls(calls, rows[case])[-1]["started_at"]


@pytest.mark.parametrize(("version", "kind"), BOTH_UI)
def test_tf26_23_the_page_s_rows_write_no_trace(tmp_path_factory: Any, version: str, kind: str) -> None:
    from tf0_support import trace

    root, _ = world(tmp_path_factory, version, kind, "status")
    assert all("trace" not in meta for meta in metas(root, RUN).values())
    ran = trace(["where", RUN, "--store", str(root), "--event", "missed"])
    assert ran.code == 0 and "has no traces (it was imported from weave)" in ran.out, ran.out + ran.err


# ---------- TF26-24 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf26_24_the_columns_prove_reads(tmp_path_factory: Any, version: str, kind: str) -> None:
    from tf21_support import frame

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
            assert row["t"] == (float(len(steps(version, case))) if _has_calls(kind) else 1.0), case
        assert row["wall_time"] == LATENCY[version][case]
        assert ("cost_usd" in row["meta"]) == (USAGE[version][case] is not None and kind in ASKED), case


# ---------- TF26-25 ----------


@pytest.mark.parametrize(("version", "kind"), EVERY)
def test_tf26_25_no_text_of_the_capture_is_kept_or_printed(tmp_path: Path, version: str, kind: str) -> None:
    files = export(version, kind)
    for argv in (of(version, kind, tmp_path / "a", "r"), [*of(version, kind, tmp_path / "b", "r", mode="status"), "--json"]):
        result = run_import(argv)
        assert result.code == 0, result.err
        printed = result.out + result.err
        for text in CONTENT:
            assert text not in printed, text
    raw = b"".join(p.read_bytes() for p in files)
    held_texts = sum(1 for text in CONTENT if text.encode() in raw)
    # the service's answers hold the prompts, the errors and the notes; the page's JSON the
    # machine's build strings; the page's table the rows' own values alone
    assert held_texts >= (8 if _has_calls(kind) else 1 if kind in UI_CALLS else 0), "the capture holds the texts looked for"
    assert all(item.encode() in raw for item in ITEM.values()) or kind in ("pull", "plain", "pages"), "the capture holds the rows' values"
    for folder in ("a", "b"):
        held = stored_bytes(tmp_path / folder)
        for text in (*CONTENT, "sys_version", "wb_user_id", "VXNlcjow"):
            assert text.encode() not in held, text
        for word in (*ITEM.values(), *LOOKUP_EXPECTED.values()):
            assert word.encode() not in held, word


# ---------- TF26-27 ----------


def _second_reading(version: str, kind: str) -> dict[str, dict[str, Any]]:
    """Each case's wall time, steps and retried ops, read off the export's calls by this file."""
    calls = calls_of(export(version, kind)[0])
    out: dict[str, dict[str, Any]] = {}
    for case, row in rows_by_case(calls, version).items():
        held = work_calls(calls, row)
        retried = sum(1 for a, b in zip(held, held[1:], strict=False) if op(a) == op(b) and a["exception"])
        out[case] = {
            "wall": row["output"]["model_latency"],
            "steps": [(op(c), bool(c["exception"])) for c in held],
            "retries": retried,
            "llm": sum(1 for c in held if c["attributes"]["weave"].get("kind") == "llm"),
        }
    return out


@pytest.mark.parametrize(("version", "kind"), BOTH_API)
def test_tf26_27_the_record_agrees_with_a_second_reading_of_the_file(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "status")
    stored, want = recs(root, RUN), _second_reading(version, kind)
    for case in CASES:
        assert stored[case]["wall_time_s"] == want[case]["wall"], case
        assert tuple(want[case]["steps"]) == steps(version, case), case
        assert stored[case]["steps"] == len(want[case]["steps"]), case
        assert stored[case]["retries"] == want[case]["retries"] and stored[case]["llm_calls"] == want[case]["llm"], case
    assert columns(root, RUN)
    assert sorted(QUESTIONS) == sorted(LOOKUP_EXPECTED)
