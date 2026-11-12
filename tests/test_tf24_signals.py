"""TF24-16 to TF24-27: the signals, the failure kinds, feedback with its source, and what is kept
(spec sections 18.1 and 18.1.1 row 9, 18.4.1 and 18.4.2 as TF21's SA1 reads them, 18.5.2's
LangSmith row; SG2; IC7; the INT3 spec's IT11 to IT14 on the real captures).

- TF24-16: time. The wall time is the root's end less its start, to the microsecond the same as
  the latency the UI's CSV prints; the time to first token is the trace's first ``llm`` token
  less the root's start, and not recorded where the trace made no model call or the export has
  no such time (the CSV).
- TF24-17: lengths. The characters of every value in the root's input and output, keys and
  punctuation not counted; an errored root's null output is a recorded zero.
- TF24-18: tokens and cost, summed over the trace's ``llm`` runs: input, output and total
  tokens, cached and reasoning tokens where the export splits them (the API pulls: recorded
  zeros; the command's export does not: not recorded), and US dollars. Where a trace made no
  model call nothing is recorded, apart from the v1 pull, whose root says 0 tokens, and the CSV,
  which prints 0: each export's own fact, kept as it is. The CSV gives the total alone. Where
  each figure came from is kept beside the row.
- TF24-19: structure. Steps are the runs with no child; LLM calls the ``llm`` runs (a recorded
  zero where there is none); tool calls the ``tool`` runs in start order with their names, how
  each ended, its time and the class of its error; a call that follows a failed call of the
  same name is attempt 2 and one retry. The CSV records none of these.
- TF24-20: the kinds on the captures, through the one rule set: the baseline's failed tool
  call is a timeout, its two stale answers and its ``unknown`` wrong answers; the candidate's
  cut reply is a format error (the parser raised) from every export with the steps, and a crash
  from the CSV, which has the root alone; a passed row has no kind. Each agrees with TF21's
  reference on what the row records.
- TF24-21: the kinds section 18.5.2 names that the captures lack, on a capture edited in one
  place: an error saying a rate limit or a context overflow; a failed retriever, llm or chain
  step, a failed tool step; three calls in a row to one tool under a root that succeeded and
  failed its score (a loop).
- TF24-22: feedback with its source. A key all of whose sources are ``model`` is a score; one
  from ``api`` or ``app`` is feedback, a number or its word; the sources are kept beside the
  row, so the two thumbs made by hand in the UI (``app``) are told from the script's (``api``).
  Feedback records fill what the statistics lack and are counted; the CSV names no source.
- TF24-23: the store's trace: one span a run, the root's children under it, ids the runs' own
  without their dashes, kinds by run type (``llm``, ``tool``, ``retrieval`` for a retriever,
  ``other`` for a chain or a parser), the model's name beside an ``llm`` span; ``where`` reads
  the run. The CSV writes no trace.
- TF24-24: the columns Prove reads: ``t`` the steps, ``wall_time`` the wall time, ``confidence``
  the score read; ``meta["cost_usd"]`` only where a cost was recorded.
- TF24-25: no content. No prompt, input, output, error, traceback, comment or tag text of the
  captures is in any file of the store or in anything printed.
- TF24-26: every stored record has exactly the writer's keys; ``horizon``, ``working_time_s``
  and the signals no LangSmith export records are not recorded.
- TF24-27: the record is checked against a second reading of the files, written here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tf21_support import RECORD_KEYS, run_import
from tf24_support import (
    ANSWER, CASES, CONTENT, ERRORED, EXACT, EXPORTS, HUMAN_THUMBS, ITEM, JUDGE, LATE, LATENCY, REVIEW, RUN,
    TRACE_EXPORTS, USAGE, VERSIONS, approx, by_status, children, columns, export, feedback_file, imported, ls_argv, metas,
    parent_of, recs, roots, rows_of, run_id, seconds, set_error, stored_bytes, trace_rows, ttft, world, write_csv,
    write_rows,
)

BOTH = [(v, k) for v in VERSIONS for k in EXPORTS]
BOTH_TRACES = [(v, k) for v in VERSIONS for k in TRACE_EXPORTS]
SPLIT = ("v1", "v2", "v2-subtree")


# ---------- TF24-16 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf24_16_the_wall_time_is_the_root_s_and_the_latency_the_csv_prints(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "status")
    stored = recs(root, RUN)
    for case in CASES:
        assert approx(stored[case]["wall_time_s"], LATENCY[version][case], 5e-10), (case, stored[case]["wall_time_s"])
        assert stored[case]["working_time_s"] is None


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf24_16_the_time_to_first_token(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "status")
    stored = recs(root, RUN)
    want = ttft(version)
    assert sum(1 for v in want.values() if v is None) == (1 if version == "baseline" else 0)
    for case in CASES:
        got = stored[case]["ttft_s"]
        if kind == "ui" or want[case] is None:
            assert got is None, (case, got)
        else:
            assert approx(got, want[case], 2e-6), (case, got, want[case])
            assert 0 < got <= stored[case]["wall_time_s"]
    if version == "baseline" and kind != "ui":
        # 20:38:03.407429 less 20:38:02.951920
        assert approx(stored["c09"]["ttft_s"], 0.455509, 1e-9)


# ---------- TF24-17 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf24_17_the_lengths_are_the_characters_of_the_values(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "status")
    stored = recs(root, RUN)
    for case in CASES:
        assert stored[case]["input_chars"] == len(case) + len(ITEM[case]), case
        answer = ANSWER[version][case]
        assert stored[case]["output_chars"] == (0 if answer is None else len(answer)), case


def test_tf24_17_numbers_count_as_json_writes_them_and_a_missing_value_is_not_recorded(tmp_path: Path) -> None:
    def edit(rows: list[dict[str, Any]]) -> None:
        held = roots(rows)
        held["c01"]["inputs"] = {"n": 12, "ok": True, "nested": {"words": ["ab", "cde"], "none": None}, "x": 1.5}  # type: ignore[index]
        held["c02"]["outputs"] = "plain text"  # type: ignore[index]
        del held["c03"]["outputs"]  # type: ignore[attr-defined]
        held["c04"]["inputs"] = None  # type: ignore[index]

    path = write_rows(tmp_path / "runs.json", export("baseline", "v1")[0], edit)
    imported(by_status(path, tmp_path / "st", "r"))
    stored = recs(tmp_path / "st", "r")
    assert stored["c01"]["input_chars"] == 2 + 4 + 2 + 3 + 3  # 12, true, ab, cde, 1.5
    assert stored["c02"]["output_chars"] == 10
    assert stored["c03"]["output_chars"] is None and stored["c04"]["input_chars"] is None
    assert stored["c05"]["input_chars"] == 3 + len(ITEM["c05"])


# ---------- TF24-18 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH_TRACES)
def test_tf24_18_tokens_and_cost_are_the_llm_runs(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "status")
    stored, held = recs(root, RUN), metas(root, RUN)
    for case in CASES:
        usage, rec = USAGE[version][case], stored[case]
        if usage is None:
            continue
        assert (rec["input_tokens"], rec["output_tokens"], rec["total_tokens"]) == usage[:3], case
        assert approx(rec["cost_usd"], usage[3], 1e-12) and approx(held[case]["cost_usd"], usage[3], 1e-12), case
        if kind in SPLIT:
            assert rec["cached_tokens"] == 0 and rec["reasoning_tokens"] == 0, case
        else:
            assert rec["cached_tokens"] is None and rec["reasoning_tokens"] is None, case
        assert held[case]["import"]["tokens_from"] == "llm runs" and held[case]["import"]["cost_from"] == "llm runs"


@pytest.mark.parametrize("kind", EXPORTS)
def test_tf24_18_a_trace_with_no_model_call_records_what_its_export_says_and_no_more(tmp_path_factory: Any, kind: str) -> None:
    """The baseline's c08 stopped at its tool, before any model call. Its v2 rows and the
    command's hold no token count and no cost; the v1 root holds 0 tokens and no cost, and the
    CSV prints 0 tokens and an empty cost. Not recorded is kept apart from zero either way."""
    root, _ = world(tmp_path_factory, "baseline", kind, "status")
    rec, meta = recs(root, RUN)["c08"], metas(root, RUN)["c08"]
    assert rec["cost_usd"] is None and "cost_usd" not in meta and "cost_from" not in meta["import"]
    if kind == "v1":
        assert (rec["input_tokens"], rec["output_tokens"], rec["total_tokens"]) == (0, 0, 0)
        assert meta["import"]["tokens_from"] == "root run"
    elif kind == "ui":
        assert (rec["input_tokens"], rec["output_tokens"], rec["total_tokens"]) == (None, None, 0)
    else:
        assert (rec["input_tokens"], rec["output_tokens"], rec["total_tokens"]) == (None, None, None)
        assert "tokens_from" not in meta["import"]
    assert rec["cached_tokens"] is None and rec["reasoning_tokens"] is None


@pytest.mark.parametrize("version", VERSIONS)
def test_tf24_18_the_csv_gives_the_totals_alone(tmp_path_factory: Any, version: str) -> None:
    root, _ = world(tmp_path_factory, version, "ui", "status")
    stored, held = recs(root, RUN), metas(root, RUN)
    for case in CASES:
        usage, rec = USAGE[version][case], stored[case]
        assert rec["input_tokens"] is None and rec["output_tokens"] is None
        assert rec["cached_tokens"] is None and rec["reasoning_tokens"] is None
        if usage is not None:
            assert rec["total_tokens"] == usage[2] and approx(rec["cost_usd"], usage[3], 1e-12), case
            assert held[case]["import"]["tokens_from"] == "root run" and held[case]["import"]["cost_from"] == "root run"


def test_tf24_18_a_root_s_own_figures_are_read_when_its_steps_are_not_in_the_file(tmp_path: Path) -> None:
    """A v1 pull of the roots alone (``is_root``): the root carries the sums."""
    def only_roots(rows: list[dict[str, Any]]) -> None:
        rows[:] = [r for r in rows if r["parent_run_id"] is None]

    path = write_rows(tmp_path / "roots.json", export("candidate", "v1")[0], only_roots)
    imported(by_status(path, tmp_path / "st", "r"))
    stored, held = recs(tmp_path / "st", "r"), metas(tmp_path / "st", "r")
    for case in CASES:
        usage = USAGE["candidate"][case]
        assert usage is not None
        assert (stored[case]["input_tokens"], stored[case]["output_tokens"], stored[case]["total_tokens"]) == usage[:3]
        assert approx(stored[case]["cost_usd"], usage[3], 1e-12)
        assert held[case]["import"]["tokens_from"] == "root run" and held[case]["import"]["cost_from"] == "root run"
        assert stored[case]["steps"] == 1 and stored[case]["llm_calls"] == 0 and stored[case]["tool_calls"] == []
        assert stored[case]["ttft_s"] is not None


# ---------- TF24-19 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH_TRACES)
def test_tf24_19_steps_calls_and_retries_from_the_runs(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "status")
    stored = recs(root, RUN)
    for case in CASES:
        under, rec = children(version, case), stored[case]
        tools = [bad for run_type, bad in under if run_type == "tool"]
        assert rec["steps"] == len(under), case
        assert rec["llm_calls"] == sum(1 for run_type, _ in under if run_type == "llm"), case
        assert rec["horizon"] is None
        assert rec["tool_call_count"] == len(tools) and rec["tool_error_count"] == sum(tools), case
        assert [c["name"] for c in rec["tool_calls"]] == ["check_stock"] * len(tools), case
        assert [c["status"] for c in rec["tool_calls"]] == ["error" if bad else "ok" for bad in tools], case
        assert rec["retries"] == (1 if (version, case) == ("candidate", "c04") else 0), case
        for call in rec["tool_calls"]:
            assert call["duration_s"] is not None and 0 <= call["duration_s"] < 1, call
        assert rec["signals"] == (["over_budget"] if rec["failure_kind"] == "timeout" else []), (case, rec["signals"])


@pytest.mark.parametrize("kind", TRACE_EXPORTS)
def test_tf24_19_a_call_after_a_failed_call_of_the_same_name_is_the_next_attempt(tmp_path_factory: Any, kind: str) -> None:
    root, _ = world(tmp_path_factory, "candidate", kind, "status")
    stored = recs(root, RUN)
    calls = stored["c04"]["tool_calls"]
    assert [(c["status"], c["attempt"], c["error_type"]) for c in calls] == [("error", 1, "RuntimeError"), ("ok", 2, None)]
    assert all(c["attempt"] == 1 for case in CASES if case != "c04" for c in stored[case]["tool_calls"])
    failed = recs(world(tmp_path_factory, "baseline", kind, "status")[0], RUN)["c08"]["tool_calls"]
    assert [(c["status"], c["attempt"], c["error_type"]) for c in failed] == [("error", 1, "TimeoutError")]


@pytest.mark.parametrize("version", VERSIONS)
def test_tf24_19_the_csv_records_no_step_no_call_and_no_retry(tmp_path_factory: Any, version: str) -> None:
    root, _ = world(tmp_path_factory, version, "ui", "status")
    for case, rec in recs(root, RUN).items():
        for key in ("steps", "llm_calls", "tool_calls", "tool_call_count", "tool_error_count", "retries", "horizon"):
            assert rec[key] is None, (case, key)


# ---------- TF24-20 ----------


def _kinds(root: Path) -> dict[str, Any]:
    return {case: r["failure_kind"] for case, r in recs(root, RUN).items()}


@pytest.mark.parametrize(("version", "kind"), [(v, k) for v in VERSIONS for k in ("v1", "ui")])
def test_tf24_20_the_kinds_by_the_score(tmp_path_factory: Any, version: str, kind: str) -> None:
    """Read by the ``exact`` score, from the two exports whose statistics hold every score."""
    root, _ = world(tmp_path_factory, version, kind, "exact")
    want: dict[str, Any] = {case: None if EXACT[version][case] >= 0.5 else "wrong_answer" for case in CASES}
    bad, _, _, by_steps = ERRORED[version]
    want[bad] = by_steps if kind != "ui" else {"baseline": "timeout", "candidate": "crash"}[version]
    assert _kinds(root) == want
    assert want["c06"] == "wrong_answer"


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf24_20_the_kinds_by_the_status(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "status")
    bad, error_type, span_kind, by_steps = ERRORED[version]
    want: dict[str, Any] = {case: None for case in CASES}
    want[bad] = by_steps if kind != "ui" else {"baseline": "timeout", "candidate": "crash"}[version]
    assert _kinds(root) == want
    rec = recs(root, RUN)[bad]
    assert rec["error_type"] == error_type
    assert rec["error_span_kind"] == (None if kind == "ui" else span_kind)
    for case, other in recs(root, RUN).items():
        if case != bad:
            assert other["error_type"] is None and other["error_span_kind"] is None, case


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf24_20_every_kind_is_the_one_tf21_s_reference_gives_the_record(tmp_path_factory: Any, version: str, kind: str) -> None:
    from tf10_support import ref_kind_of

    for mode in ("status", "exact"):
        root, _ = world(tmp_path_factory, version, kind, mode)
        for case, rec in recs(root, RUN).items():
            assert rec["failure_kind"] == ref_kind_of(rec), (mode, case)


# ---------- TF24-21 ----------

TEXTS = {
    "rate_limit": "RateLimited('429 too many requests')\n\nTraceback (most recent call last):\nRateLimited: 429\n",
    "rate_limit by words": "RuntimeError('the provider said: rate limit exceeded')\n",
    "context_overflow": "BadRequestError(\"context_length_exceeded: this model's limit is 8192\")\n",
    "timeout by words": "RuntimeError('the call timed out')\n",
}


@pytest.mark.parametrize("kind", ["v1", "v2", "cli-runs"])
@pytest.mark.parametrize("label", list(TEXTS))
def test_tf24_21_an_error_s_first_line_gives_its_kind(tmp_path: Path, kind: str, label: str) -> None:
    def edit(rows: list[dict[str, Any]]) -> None:
        for row in trace_rows(rows, "c09"):
            if row.get("error"):
                set_error(row, TEXTS[label])

    name = "runs.jsonl" if kind == "cli-runs" else "runs.json"
    path = write_rows(tmp_path / name, export("candidate", kind)[0], edit)
    imported(by_status(path, tmp_path / "st", "r"))
    rec = recs(tmp_path / "st", "r")["c09"]
    assert rec["failure_kind"] == label.split()[0], rec
    assert rec["outcome"] == "fail"


def test_tf24_21_the_csv_s_error_text_gives_its_kind_too(tmp_path: Path) -> None:
    def edit(rows: list[dict[str, str]]) -> None:
        for row in rows:
            if row["status"] == "error":
                # the class says nothing; only the words do
                row["error"] = TEXTS["rate_limit by words"]

    path = write_csv(tmp_path / "x.csv", export("candidate", "ui")[0], edit)
    imported(by_status(path, tmp_path / "st", "r"))
    rec = recs(tmp_path / "st", "r")["c09"]
    assert rec["failure_kind"] == "rate_limit" and rec["error_type"] == "RuntimeError"


@pytest.mark.parametrize("kind", ["v1", "v2", "cli-runs"])
@pytest.mark.parametrize(("run_type", "want", "span_kind"), [
    ("retriever", "retrieval_error", "retriever"), ("llm", "crash", "llm"), ("chain", "crash", "other"),
    ("parser", "format_error", "parser"), ("tool", "tool_error", "tool"),
])
def test_tf24_21_the_step_that_failed_gives_the_kind(tmp_path: Path, kind: str, run_type: str, want: str, span_kind: str) -> None:
    """The candidate's c09, whose parser raised an error whose words say nothing: the failing
    step given each run type in turn."""
    def edit(rows: list[dict[str, Any]]) -> None:
        for row in trace_rows(rows, "c09")[1:]:
            if row.get("error"):
                row["run_type"] = run_type

    name = "runs.jsonl" if kind == "cli-runs" else "runs.json"
    path = write_rows(tmp_path / name, export("candidate", kind)[0], edit)
    imported(by_status(path, tmp_path / "st", "r"))
    rec = recs(tmp_path / "st", "r")["c09"]
    assert rec["failure_kind"] == want and rec["error_span_kind"] == span_kind, rec
    assert rec["error_type"] == "ValueError"


@pytest.mark.parametrize("kind", ["v1", "v2", "cli-runs"])
def test_tf24_21_three_calls_in_a_row_to_one_tool_under_a_failed_score_is_a_loop(tmp_path: Path, kind: str) -> None:
    def edit(rows: list[dict[str, Any]]) -> None:
        for case in ("c06", "c01"):
            tool = next(r for r in trace_rows(rows, case) if r["run_type"] == "tool")
            for n in (1, 2):
                again = json.loads(json.dumps(tool))
                key = "run_id" if "run_id" in again else "id"
                again[key] = again[key][:-4] + f"ff0{n}"
                again["start_time"] = tool["start_time"].rstrip("Z")[:-3] + f"9{n}9" + ("Z" if tool["start_time"].endswith("Z") else "")
                again["end_time"] = again["start_time"]
                rows.append(again)

    name = "runs.jsonl" if kind == "cli-runs" else "runs.json"
    path = write_rows(tmp_path / name, export("candidate", kind)[0], edit)
    imported(ls_argv([path, feedback_file("candidate")], tmp_path / "st", "r"))
    stored = recs(tmp_path / "st", "r")
    assert stored["c06"]["tool_call_count"] == 3 and stored["c06"]["failure_kind"] == "loop_detected"
    # the same three calls under a row that passed give no kind, and no retry either: none failed
    assert stored["c01"]["tool_call_count"] == 3 and stored["c01"]["failure_kind"] is None
    assert stored["c01"]["retries"] == 0 and stored["c06"]["retries"] == 0


# ---------- TF24-22 ----------


def _want_feedback(version: str, case: str, human: bool) -> dict[str, Any]:
    want: dict[str, Any] = {"thumbs": EXACT[version][case], "review": REVIEW[version][case]}
    if human and case in HUMAN_THUMBS[version]:
        want["human_thumbs"] = HUMAN_THUMBS[version][case]
    return want


@pytest.mark.parametrize(("version", "kind"), BOTH_TRACES)
@pytest.mark.parametrize("given", ["statistics", "records"])
def test_tf24_22_scores_are_the_model_s_and_feedback_the_rest_each_with_its_source(tmp_path_factory: Any, version: str, kind: str, given: str) -> None:
    root, data = world(tmp_path_factory, version, kind, "status", feedback=given == "records")
    stored, held = recs(root, RUN), metas(root, RUN)
    late = () if (given == "records" or kind == "v1") else LATE[version]
    for case in CASES:
        scores = {"exact": EXACT[version][case]} if case not in late else {}
        if case in JUDGE[version]:
            scores["judge_correct"] = JUDGE[version][case]
        assert stored[case]["scores"] == scores, (case, stored[case]["scores"])
        assert stored[case]["feedback"] == _want_feedback(version, case, True), (case, stored[case]["feedback"])
        sources = {key: ["model"] for key in scores} | {"thumbs": ["api"], "review": ["api"]}
        if case in HUMAN_THUMBS[version]:
            sources["human_thumbs"] = ["app"]
        assert held[case]["import"]["feedback_sources"] == sources, (case, held[case]["import"])
    lacked = len(LATE[version]) if (given == "records" and kind != "v1") else 0
    assert data["counts"]["scores the run statistics lacked"] == lacked
    assert data["counts"]["feedback records"] == ({"baseline": 39, "candidate": 41}[version] if given == "records" else 0)


@pytest.mark.parametrize("kind", ["v2", "v2-subtree", "cli-runs", "cli-traces"])
def test_tf24_22_the_feedback_records_fill_the_scores_the_statistics_lack(tmp_path: Path, kind: str) -> None:
    files = [*export("baseline", kind), feedback_file("baseline")]
    data = imported(ls_argv(files, tmp_path / "st", "r"))
    assert {k: v for k, v in data["outcomes"].items() if v} == {"met": 6, "missed": 4} and data["no_outcome"] == {}
    stored = recs(tmp_path / "st", "r")
    assert {case: r["score"] for case, r in stored.items()} == EXACT["baseline"]
    assert stored["c08"]["outcome"] == "fail" and stored["c08"]["failure_kind"] == "timeout"
    assert stored["c10"]["outcome"] == "fail" and stored["c10"]["failure_kind"] == "wrong_answer"


def test_tf24_22_a_feedback_record_of_a_run_not_in_the_files_changes_nothing(tmp_path: Path) -> None:
    """The candidate's records beside the baseline's runs: none belongs to a root here."""
    data = imported(ls_argv([*export("baseline", "v2"), feedback_file("candidate")], tmp_path / "st", "r"))
    assert data["no_outcome"] == {"no score": 2} and data["counts"]["feedback records"] == 41
    assert data["counts"]["scores the run statistics lacked"] == 0


@pytest.mark.parametrize("version", VERSIONS)
def test_tf24_22_the_csv_names_no_source_so_its_numbers_are_scores_and_its_words_feedback(tmp_path_factory: Any, version: str) -> None:
    root, _ = world(tmp_path_factory, version, "ui", "status")
    stored, held = recs(root, RUN), metas(root, RUN)
    for case in CASES:
        scores = {"exact": EXACT[version][case], "thumbs": EXACT[version][case]}
        if case in JUDGE[version]:
            scores["judge_correct"] = JUDGE[version][case]
        assert stored[case]["scores"] == scores, case
        assert stored[case]["feedback"] == {"review": REVIEW[version][case]}, case
        assert "feedback_sources" not in held[case]["import"], case


def test_tf24_22_a_key_of_two_sources_is_feedback_and_names_both(tmp_path: Path) -> None:
    records = write_rows(tmp_path / "feedback.json", feedback_file("candidate"), None)
    held = json.loads(records.read_text(encoding="utf-8"))
    twin = json.loads(json.dumps(next(r for r in held if r["key"] == "exact")))
    twin["id"] = twin["id"][:-4] + "ffff"
    twin["feedback_source"]["type"] = "app"
    twin["score"] = 0
    held.append(twin)
    records.write_text(json.dumps(held), encoding="utf-8")
    imported(by_status([*export("candidate", "v2"), records], tmp_path / "st", "r"))
    target = next(case for case, root in roots(rows_of(export("candidate", "v2")[0])).items() if run_id(root) == twin["run_id"])
    rec, meta = recs(tmp_path / "st", "r")[target], metas(tmp_path / "st", "r")[target]
    assert "exact" not in rec["scores"]
    assert approx(rec["feedback"]["exact"], (EXACT["candidate"][target] + 0) / 2)
    assert meta["import"]["feedback_sources"]["exact"] == ["app", "model"]


# ---------- TF24-23 ----------

KIND_OF = {"llm": "llm", "tool": "tool", "retriever": "retrieval", "parser": "other", "chain": "other"}


@pytest.mark.parametrize(("version", "kind"), BOTH_TRACES)
def test_tf24_23_the_store_s_trace_is_the_runs(tmp_path_factory: Any, version: str, kind: str) -> None:
    from poisson_prove.store import Store

    root, _ = world(tmp_path_factory, version, kind, "status")
    rows = [r for path in export(version, kind) for r in rows_of(path)]
    by_case = roots(rows)
    df = Store(root).read(RUN, meta=False, trace="envelope")
    seen = 0
    for r in df.to_dict("records"):
        case = r["config"]["case"]
        trace = r["trace"]
        spans = trace["spans"] if isinstance(trace, dict) else json.loads(trace)["spans"]
        want = trace_rows(rows, case)
        assert len(spans) == len(want), case
        by_id = {s["span_id"]: s for s in spans}
        for row in want:
            span = by_id[run_id(row).replace("-", "")]
            parent = parent_of(row)
            assert span["parent_id"] == (None if parent is None else parent.replace("-", "")), case
            assert span["kind"] == KIND_OF[row["run_type"]], (case, row["run_type"], span["kind"])
            assert span["start_ns"] == round(seconds(row["start_time"]) * 1e6) * 1000, case
            if row["run_type"] == "llm":
                assert span["attrs"].get("llm.model_name") == "gpt-4.1-mini" or span["name"] == "gpt-4.1-mini", span
            seen += 1
        assert by_case[case] is want[0]
    assert seen == len(rows)


@pytest.mark.parametrize("version", VERSIONS)
def test_tf24_23_where_reads_the_imported_run(tmp_path_factory: Any, version: str) -> None:
    from tf0_support import trace

    root, _ = world(tmp_path_factory, version, "v2", "status")
    ran = trace(["where", RUN, "--store", str(root), "--event", "missed"])
    assert ran.code == 0, ran.err
    line = next(line for line in ran.out.splitlines() if line.startswith("- placement: "))
    assert "placed 10 " in line and "died 1 " in line and line.rstrip().endswith("excluded 0"), line
    assert "import/langsmith" in ran.out


@pytest.mark.parametrize("version", VERSIONS)
def test_tf24_23_the_csv_writes_no_trace(tmp_path_factory: Any, version: str) -> None:
    from tf0_support import trace

    root, _ = world(tmp_path_factory, version, "ui", "status")
    assert all("trace" not in meta for meta in metas(root, RUN).values())
    ran = trace(["where", RUN, "--store", str(root), "--event", "missed"])
    assert ran.code == 0 and "has no traces (it was imported from langsmith)" in ran.out, ran.out + ran.err


# ---------- TF24-24 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf24_24_the_columns_prove_reads(tmp_path_factory: Any, version: str, kind: str) -> None:
    from tf21_support import frame

    root, _ = world(tmp_path_factory, version, kind, "exact", feedback=kind != "ui")
    df = frame(root, RUN)
    for _, row in df.iterrows():
        rec = row["meta"]["trace_signals"]
        case = rec["case"]
        assert row["outcome"] == ("met" if EXACT[version][case] >= 0.5 else "missed"), case
        assert row["confidence"] == EXACT[version][case]
        assert approx(row["wall_time"], LATENCY[version][case], 5e-10)
        assert row["t"] == (1.0 if kind == "ui" else float(len(children(version, case)))), case
        assert ("cost_usd" in row["meta"]) == (USAGE[version][case] is not None), case


# ---------- TF24-25 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf24_25_no_text_of_the_capture_is_kept_or_printed(tmp_path: Path, version: str, kind: str) -> None:
    files = [*export(version, kind), *([feedback_file(version)] if kind != "ui" else [])]
    for argv in (ls_argv(files, tmp_path / "a", "r"), [*by_status(files, tmp_path / "b", "r"), "--json"]):
        result = run_import(argv)
        assert result.code == 0, result.err
        printed = result.out + result.err
        for text in CONTENT:
            assert text not in printed, text
    raw = b"".join(p.read_bytes() for p in files)
    assert sum(1 for text in CONTENT if text.encode() in raw) >= (4 if kind != "ui" else 1), "the capture holds the texts looked for"
    for folder in ("a", "b"):
        held = stored_bytes(tmp_path / folder)
        for text in (*CONTENT, "no stock policy", "stale"):
            assert text.encode() not in held, text
        for item in ITEM.values():
            assert item.encode() not in held, item


def test_tf24_25_a_comment_on_a_thumb_is_not_kept(tmp_path: Path) -> None:
    held = json.loads(feedback_file("baseline").read_text(encoding="utf-8"))
    comments = sorted({f["comment"] for f in held if f["comment"]})
    assert comments, "the capture holds comments"
    imported(by_status([*export("baseline", "v2"), feedback_file("baseline")], tmp_path / "st", "r"))
    stored = stored_bytes(tmp_path / "st")
    for comment in comments:
        assert comment.encode() not in stored, comment


# ---------- TF24-26 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf24_26_the_record_has_the_writer_s_keys_and_nothing_langsmith_does_not_record(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "status")
    for case, rec in recs(root, RUN).items():
        assert set(rec) == set(RECORD_KEYS), (case, set(rec) ^ set(RECORD_KEYS))
        assert rec["schema"] == "poisson.trace-signals/1" and rec["repeat"] == 0
        assert rec["horizon"] is None and rec["working_time_s"] is None


# ---------- TF24-27 ----------


def _second_reading(version: str, kind: str) -> dict[str, dict[str, Any]]:
    """Each case's wall time, steps and tool names, read off the export's rows by this file."""
    rows = [r for path in export(version, kind) for r in rows_of(path)]
    out: dict[str, dict[str, Any]] = {}
    for case, root in roots(rows).items():
        under = [r for r in rows if r["trace_id"] == root["trace_id"] and r is not root]
        out[case] = {
            "wall": seconds(root["end_time"]) - seconds(root["start_time"]),
            "steps": len(under),
            "tools": [r["name"] for r in sorted(under, key=lambda r: r["start_time"]) if r["run_type"] == "tool"],
            "durations": [seconds(r["end_time"]) - seconds(r["start_time"]) for r in sorted(under, key=lambda r: r["start_time"]) if r["run_type"] == "tool"],
        }
    return out


@pytest.mark.parametrize(("version", "kind"), BOTH_TRACES)
def test_tf24_27_the_record_agrees_with_a_second_reading_of_the_file(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "status")
    stored, want = recs(root, RUN), _second_reading(version, kind)
    for case in CASES:
        assert approx(stored[case]["wall_time_s"], want[case]["wall"], 2e-6), case
        assert stored[case]["steps"] == want[case]["steps"], case
        assert [c["name"] for c in stored[case]["tool_calls"]] == want[case]["tools"], case
        for call, duration in zip(stored[case]["tool_calls"], want[case]["durations"], strict=True):
            assert approx(call["duration_s"], duration, 2e-6), case
    assert columns(root, RUN)
