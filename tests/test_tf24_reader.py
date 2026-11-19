"""TF24-4 to TF24-15: the reader on every committed LangSmith capture: rows, cases and outcomes
(spec sections 6.3, 18.1.1 row 9, 18.3.1 and 18.3.2; the INT3 spec's sections 3.1 and 4, IT1, IT2
and IT5 to IT10, on the real captures; TF22's FI18 and FI19).

- TF24-4: every export of both versions (the v1 and v2 run queries, v2 with subtree usage, the
  command's run export and its trace folder's files, the UI's CSV) reads as ten rows, one a
  trace, on the ten cases, each once; the summary names the tool, the files with their digests
  and the shapes read.
- TF24-5: the case, four ways: the example's own ``case`` from the root's metadata (every
  export); the dataset example's id (the API pulls and the CSV, the same ids in both versions),
  refused on the command's exports in one sentence naming another way; a key of the root's
  input, ``input:`` and 12 hex characters, the same key from every export and what
  ``--verdicts`` joins by; ``none``, one case for every row, with its sentence among the counts.
- TF24-6: the outcome by the root's status: missed when the root ended in error, met otherwise,
  in every export, the command's too, whose ``status`` is empty and whose ``error`` says it. An
  error in a step does not fail a run whose root succeeded (the candidate's retried tool call).
- TF24-7: the outcome by a feedback score at a cut: ``exact`` under 0.5 missed, a score equal to
  the cut meeting it, ``--above`` the other way; the score read is the row's score.
- TF24-8: the outcome by a metadata key: missed when its value is one of ``--failed``, or its
  number at ``--cut``; a root without the key has no outcome.
- TF24-9: a root with no score for the key has no outcome and the reason ``no score``; it is
  censored when the root ended in error and unscored when it did not; a file where no root has
  the score writes nothing.
- TF24-10: the paged pulls read as the whole pull does, pages in any order; the containers
  (a list, ``runs``, ``items``, JSON Lines) read alike; one file may mix shapes.
- TF24-11: ``--select metadata:KEY=VALUE`` keeps the traces whose root holds every selection:
  both versions in one file come apart by ``version``; the counts say how many were read and
  kept; a selection that keeps nothing writes nothing.
- TF24-12: a trace whose root is not in the files is left out and counted; a run in two files
  given is refused naming it, and nothing is written. A run's parent is its nearest ancestor: the
  v2 shape's is the last of ``parent_run_ids`` (the captures nest one level, so a second level
  is built here from them).
- TF24-13: rows come in the order their roots started, whatever order the file holds them, so
  the tries of a case are its repeats in the order they ran.
- TF24-14: the start: the earliest run's start, read as UTC whether or not it carries a zone
  (v1 writes none), from ``earliest span``; the CSV carries no time, so its
  start is the file's time and the summary says so.
- TF24-15: a root still pending has no outcome under ``status`` and the reason ``pending``.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path
from typing import Any

import pytest

from tf21_support import run_import
from tf24_support import (
    CASES, ERRORED, EXACT, EXPORTS, ITEM, LATE, RUN, RUNS, TRACE_EXPORTS, VERSIONS, by_status, columns, example_ids,
    export, feedback_file, feedback_pages, imported, ls_argv, passed, recs, refused, roots, rows_of, run_id, trace_rows,
    tally, world, write_rows,
)

SHAPE = {"v1": "run", "v2": "query", "v2-subtree": "query", "cli-runs": "cli", "cli-traces": "cli", "ui": "ui"}
BOTH = [(v, k) for v in VERSIONS for k in EXPORTS]
BOTH_TRACES = [(v, k) for v in VERSIONS for k in TRACE_EXPORTS]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _outcomes(root: Path, run: str = RUN) -> dict[str, Any]:
    return {case: r["outcome"] for case, r in columns(root, run).items()}


def _input_key(case: str) -> str:
    text = json.dumps({"case": case, "item": ITEM[case]}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "input:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


# ---------- TF24-4 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf24_4_every_export_reads_as_ten_rows_on_the_ten_cases(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, data = world(tmp_path_factory, version, kind, "status")
    assert data["tool"] == "langsmith" and data["run"] == RUN
    assert data["rows"] == 10 and data["cases"] == 10 and data["repeats"] == {"min": 1, "max": 1}
    files = export(version, kind)
    assert [f["name"] for f in data["files"]] == [p.name for p in files]
    assert [f["sha256"] for f in data["files"]] == [_sha(p) for p in files]
    assert data["declared"]["shapes"] == [SHAPE[kind]]
    assert sorted(recs(root, RUN)) == list(CASES)
    assert data["counts"]["traces"] == 10
    if kind != "ui":
        assert data["counts"]["runs"] == RUNS[version]


# ---------- TF24-5 ----------


@pytest.mark.parametrize(("version", "kind"), [(v, k) for v in VERSIONS for k in ("v1", "v2", "v2-subtree", "ui")])
def test_tf24_5_the_example_s_id_is_the_case_where_the_export_carries_it(tmp_path: Path, version: str, kind: str) -> None:
    imported(by_status(export(version, kind), tmp_path / "st", "r", case="example"))
    examples = example_ids()
    got = _outcomes(tmp_path / "st", "r")
    assert sorted(got) == sorted(examples.values())
    bad = ERRORED[version][0]
    assert {case: got[examples[case]] for case in CASES} == {case: "missed" if case == bad else "met" for case in CASES}


@pytest.mark.parametrize("kind", ["cli-runs", "cli-traces"])
def test_tf24_5_example_is_refused_on_the_command_s_export_naming_another_way(tmp_path: Path, kind: str) -> None:
    line = refused(run_import(by_status(export("baseline", kind), tmp_path / "st", "r", case="example")))
    assert "example" in line and "--case-from metadata:" in line, line
    assert re.search(r"\bAPI\b", line), line
    assert not (tmp_path / "st").exists()
    imported(by_status(export("baseline", kind), tmp_path / "st", "r", case="metadata:ls_example_case"))


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf24_5_input_is_a_key_of_the_root_s_input_and_never_its_text(tmp_path: Path, version: str, kind: str) -> None:
    data = imported(by_status(export(version, kind), tmp_path / "st", "r", case="input"))
    got = _outcomes(tmp_path / "st", "r")
    assert sorted(got) == sorted(_input_key(case) for case in CASES)
    bad = ERRORED[version][0]
    assert got[_input_key(bad)] == "missed" and tally(data) == {"met": 9, "missed": 1}
    held = b"".join(p.read_bytes() for p in (tmp_path / "st").rglob("*") if p.is_file())
    for item in ITEM.values():
        assert item.encode() not in held, item


def test_tf24_5_input_is_refused_when_no_root_holds_an_input(tmp_path: Path) -> None:
    def drop(rows: list[dict[str, Any]]) -> None:
        for r in rows:
            r.pop("inputs", None)
            r.pop("inputs_preview", None)

    path = write_rows(tmp_path / "runs.json", export("baseline", "v2")[0], drop)
    line = refused(run_import(by_status(path, tmp_path / "st", "r", case="input")))
    assert "input" in line, line
    assert not (tmp_path / "st").exists()
    imported(by_status(path, tmp_path / "st", "r"))


@pytest.mark.parametrize("kind", ["v2", "cli-runs", "ui"])
def test_tf24_5_a_verdicts_file_joins_by_input(tmp_path: Path, kind: str) -> None:
    """The reader hands the import each case's input key, so a verdict that names an input and
    no case joins the row of that input (FI19), here filling the outcome the statistics lack."""
    verdicts = tmp_path / "v.jsonl"
    verdicts.write_text(json.dumps({"input": {"case": "c10", "item": ITEM["c10"]}, "outcome": "fail"}) + "\n", encoding="utf-8")
    argv = ls_argv(export("baseline", kind), tmp_path / "st", "r", "--verdicts", verdicts)
    if kind == "ui":
        # the CSV has every score, so give it a verdict that agrees with what it recorded
        data = imported(argv)
        assert data["verdicts"]["by_input"] == 1 and data["verdicts"]["by_case"] == 0, data["verdicts"]
        return
    data = imported(argv)
    assert data["verdicts"]["by_input"] == 1 and data["verdicts"]["unmatched"] == 0, data["verdicts"]
    assert _outcomes(tmp_path / "st", "r")["c10"] == "missed"
    assert data["no_outcome"] == {"no score": 1}


@pytest.mark.parametrize("kind", ["v1", "cli-runs", "ui"])
def test_tf24_5_none_reads_every_row_as_one_input_and_says_so(tmp_path: Path, kind: str) -> None:
    data = imported(by_status(export("candidate", kind), tmp_path / "st", "r", case="none"))
    assert data["cases"] == 1 and data["rows"] == 10 and data["repeats"] == {"min": 10, "max": 10}
    said = [label for label in data["counts"] if "mix of inputs" in label]
    assert len(said) == 1 and data["counts"][said[0]] == 10, data["counts"]
    other = imported(by_status(export("candidate", kind), tmp_path / "st2", "r"))
    assert not [label for label in other["counts"] if "mix of inputs" in label]


def test_tf24_5_a_root_without_the_metadata_key_has_no_case_and_is_counted(tmp_path: Path) -> None:
    def drop(rows: list[dict[str, Any]]) -> None:
        held = roots(rows)
        for case in ("c02", "c07"):
            del held[case]["metadata"]["ls_example_case"]  # type: ignore[attr-defined]
            del held[case]["extra"]["metadata"]["ls_example_case"]  # type: ignore[attr-defined]

    path = write_rows(tmp_path / "runs.json", export("baseline", "v2")[0], drop)
    data = imported(by_status(path, tmp_path / "st", "r"))
    assert data["rows"] == 8 and data["counts"]["no case"] == 2
    assert sorted(_outcomes(tmp_path / "st", "r")) == [c for c in CASES if c not in ("c02", "c07")]


# ---------- TF24-6 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf24_6_by_status_the_errored_root_is_the_one_missed(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, data = world(tmp_path_factory, version, kind, "status")
    bad = ERRORED[version][0]
    assert _outcomes(root) == {case: "missed" if case == bad else "met" for case in CASES}
    assert tally(data) == {"met": 9, "missed": 1} and data["no_outcome"] == {}
    assert data["declared"]["outcome_from"] == "status" and "cut" not in data["declared"]
    stored = recs(root, RUN)
    assert {case: r["outcome"] for case, r in stored.items()} == {case: "fail" if case == bad else "pass" for case in CASES}
    # a step that failed and was retried did not fail the run
    if version == "candidate":
        assert stored["c04"]["outcome"] == "pass" and stored["c04"]["failure_kind"] is None


def test_tf24_6_status_on_an_export_that_says_nothing_of_how_a_run_ended_is_refused(tmp_path: Path) -> None:
    """The command's export without ``--full`` (ruling 8 of INT3): no status and no error key."""
    def bare(rows: list[dict[str, Any]]) -> None:
        for r in rows:
            for key in ("status", "error", "inputs", "outputs", "events"):
                r.pop(key, None)

    path = write_rows(tmp_path / "runs.jsonl", export("baseline", "cli-runs")[0], bare)
    line = refused(run_import(by_status(path, tmp_path / "st", "r")))
    assert "status" in line and "--full" in line, line
    assert not (tmp_path / "st").exists()
    imported(ls_argv(path, tmp_path / "st", "r"))


# ---------- TF24-7 ----------


@pytest.mark.parametrize(("version", "kind"), [(v, k) for v in VERSIONS for k in ("v1", "ui")])
def test_tf24_7_by_a_feedback_score_at_a_cut(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, data = world(tmp_path_factory, version, kind, "exact")
    want = {case: "met" if ok else "missed" for case, ok in passed(version).items()}
    assert _outcomes(root) == want
    assert data["declared"]["outcome_from"] == "feedback:exact"
    assert data["declared"]["cut"] == 0.5 and data["declared"]["side"] == "below"
    stored = recs(root, RUN)
    assert {case: r["score"] for case, r in stored.items()} == EXACT[version]
    assert {case: r["outcome"] for case, r in stored.items()} == {case: "pass" if ok else "fail" for case, ok in passed(version).items()}


@pytest.mark.parametrize(("extra", "missed"), [
    (("--cut", "1", "--below"), 4), (("--cut", "0", "--below"), 0), (("--cut", "0", "--above"), 6), (("--cut", "1", "--above"), 0),
])
def test_tf24_7_a_score_equal_to_the_cut_meets_it_on_either_side(tmp_path: Path, extra: tuple[str, ...], missed: int) -> None:
    argv = ls_argv(export("baseline", "v1"), tmp_path / "st", "r", *extra, cut=None)
    data = imported(argv)
    assert data["outcomes"].get("missed", 0) == missed and data["outcomes"].get("met", 0) == 10 - missed


def test_tf24_7_another_key_is_read_the_same_way(tmp_path: Path) -> None:
    data = imported(ls_argv(export("candidate", "v1"), tmp_path / "st", "r", outcome="feedback:thumbs"))
    assert tally(data) == {"met": 8, "missed": 2}
    assert _outcomes(tmp_path / "st", "r")["c06"] == "missed"


def test_tf24_7_a_key_with_words_and_no_score_is_no_score(tmp_path: Path) -> None:
    line = refused(run_import(ls_argv(export("baseline", "v1"), tmp_path / "st", "r", outcome="feedback:review")))
    assert "outcome" in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF24-8 ----------


@pytest.mark.parametrize("kind", ["v1", "v2", "cli-runs", "ui"])
def test_tf24_8_by_a_metadata_value_named_as_failed(tmp_path: Path, kind: str) -> None:
    """Both versions' roots carry ``version`` in their metadata: naming one value failed reads
    every row of that version as missed, and of the other as met."""
    for version, want in (("baseline", "missed"), ("candidate", "met")):
        argv = ls_argv(export(version, kind), tmp_path / version, "r", "--failed", "baseline", "--failed", "other",
                       outcome="metadata:version", cut=None)
        data = imported(argv)
        assert tally(data) == {want: 10}
        assert data["declared"]["failed"] == ["baseline", "other"]


def test_tf24_8_by_a_metadata_number_at_a_cut(tmp_path: Path) -> None:
    def grade(rows: list[dict[str, Any]]) -> None:
        for case, root in roots(rows).items():
            root["extra"]["metadata"]["grade"] = EXACT["baseline"][case]

    path = write_rows(tmp_path / "runs.json", export("baseline", "v1")[0], grade)
    data = imported(ls_argv(path, tmp_path / "st", "r", outcome="metadata:grade"))
    assert tally(data) == {"met": 6, "missed": 4}
    assert {c: r["score"] for c, r in recs(tmp_path / "st", "r").items()} == EXACT["baseline"]


def test_tf24_8_a_root_without_the_key_has_no_outcome(tmp_path: Path) -> None:
    def drop(rows: list[dict[str, Any]]) -> None:
        root = roots(rows)["c05"]
        del root["extra"]["metadata"]["version"]

    path = write_rows(tmp_path / "runs.json", export("baseline", "v1")[0], drop)
    data = imported(ls_argv(path, tmp_path / "st", "r", "--failed", "candidate", outcome="metadata:version", cut=None))
    assert tally(data) == {"met": 9} and data["no_outcome"] == {"no outcome recorded": 1}
    assert columns(tmp_path / "st", "r")["c05"]["error"] == "no outcome recorded"


# ---------- TF24-9 ----------


@pytest.mark.parametrize("kind", ["v2", "v2-subtree", "cli-runs", "cli-traces"])
def test_tf24_9_a_root_with_no_score_has_no_outcome(tmp_path_factory: Any, kind: str) -> None:
    """The baseline's v2 pulls and the command's exports hold ``exact`` on 8 of the 10 roots
    (TC-11): the two without are rows with no outcome, never read as a pass or a failure."""
    root, data = world(tmp_path_factory, "baseline", kind, "exact")
    assert data["rows"] == 10 and tally(data) == {"met": 6, "missed": 2}
    assert data["no_outcome"] == {"no score": 2}
    got = columns(root, RUN)
    stored = recs(root, RUN)
    for case in LATE["baseline"]:
        assert got[case]["outcome"] is None and got[case]["error"] == "no score", got[case]
        assert stored[case]["score"] is None and "exact" not in stored[case]["scores"]
    # the errored root is censored, with its kind; the other is unscored
    assert stored["c08"]["outcome"] == "censored" and stored["c08"]["failure_kind"] == "timeout"
    assert stored["c10"]["outcome"] is None and stored["c10"]["failure_kind"] is None


def test_tf24_9_the_summary_says_how_to_get_the_scores_the_statistics_lack(tmp_path: Path) -> None:
    result = run_import(ls_argv(export("baseline", "v2"), tmp_path / "st", "r"))
    assert result.code == 0, result.err
    said = [line for line in result.out.splitlines() if "feedback" in line and "no score" in line]
    assert len(said) == 1 and said[0].startswith("- ") and " 2 " in said[0], result.out
    assert "langsmith:" in said[0] or "/api/v1/feedback" in said[0], said[0]
    whole = run_import(ls_argv(export("baseline", "v1"), tmp_path / "st1", "r"))
    assert whole.code == 0 and not [line for line in whole.out.splitlines() if "feedback" in line and "no score" in line]


def test_tf24_9_a_file_where_no_root_has_the_score_writes_nothing(tmp_path: Path) -> None:
    line = refused(run_import(ls_argv(export("baseline", "v2"), tmp_path / "st", "r", outcome="feedback:no_such_key")))
    assert "outcome" in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF24-10 ----------


@pytest.mark.parametrize("kind", ["v2-pages", "v1-pages"])
@pytest.mark.parametrize("order", ["as pulled", "reversed"])
def test_tf24_10_the_pages_read_as_the_whole_pull(tmp_path: Path, kind: str, order: str) -> None:
    pages = export("candidate", kind)
    if order == "reversed":
        pages = pages[::-1]
    data = imported(ls_argv([*pages, *feedback_pages()], tmp_path / "paged", "r"))
    whole = imported(ls_argv([*export("candidate", kind[:2]), feedback_file("candidate")], tmp_path / "whole", "r"))
    assert data["rows"] == 10 and data["counts"]["runs"] == 51 and data["counts"]["feedback records"] == 41
    assert recs(tmp_path / "paged", "r") == recs(tmp_path / "whole", "r")
    for key in ("outcomes", "no_outcome", "counts", "started", "declared"):
        assert data[key] == whole[key], key


def test_tf24_10_the_containers_read_alike(tmp_path: Path) -> None:
    rows = rows_of(export("candidate", "v2")[0])
    forms = {
        "items.json": json.dumps({"items": rows, "next_cursor": None}),
        "runs.json": json.dumps({"runs": rows}),
        "list.json": json.dumps(rows),
        "lines.jsonl": "".join(json.dumps(r) + "\n" for r in rows),
        "blank-lines.jsonl": "\n".join(json.dumps(r) + "\n" for r in rows),
    }
    seen = []
    for name, text in forms.items():
        folder = tmp_path / name.split(".")[0]
        folder.mkdir()
        (folder / name).write_text(text, encoding="utf-8")
        imported(ls_argv(folder / name, folder / "st", "r"))
        seen.append(recs(folder / "st", "r"))
    assert all(s == seen[0] for s in seen[1:])


def test_tf24_10_one_file_may_mix_shapes_row_by_row(tmp_path: Path) -> None:
    """Half the traces as the v1 query returns them, half as the command exports them, shuffled
    into one JSON Lines file: each row is read by its own keys."""
    v1, cli = rows_of(export("candidate", "v1")[0]), rows_of(export("candidate", "cli-runs")[0])
    mixed = []
    for i, case in enumerate(CASES):
        mixed += trace_rows(v1 if i % 2 == 0 else cli, case)
    random.Random(24).shuffle(mixed)
    path = tmp_path / "mixed.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in mixed), encoding="utf-8")
    data = imported(by_status(path, tmp_path / "st", "r"))
    assert data["rows"] == 10 and sorted(data["declared"]["shapes"]) == ["cli", "run"]
    assert _outcomes(tmp_path / "st", "r") == {case: "missed" if case == "c09" else "met" for case in CASES}


# ---------- TF24-11 ----------


def _both_versions(tmp_path: Path, kind: str = "v1") -> Path:
    rows = rows_of(export("baseline", kind)[0]) + rows_of(export("candidate", kind)[0])
    path = tmp_path / "both.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


@pytest.mark.parametrize("kind", ["v1", "v2", "cli-runs"])
def test_tf24_11_select_takes_one_version_out_of_a_file_that_holds_both(tmp_path: Path, kind: str) -> None:
    path = _both_versions(tmp_path, kind)
    for version in VERSIONS:
        data = imported(by_status(path, tmp_path / "st", version, "--select", f"metadata:version={version}"))
        assert data["rows"] == 10 and data["counts"]["traces"] == 20 and data["counts"]["selected"] == 10
        assert data["declared"]["select"] == [f"metadata:version={version}"]
        bad = ERRORED[version][0]
        assert _outcomes(tmp_path / "st", version) == {case: "missed" if case == bad else "met" for case in CASES}


def test_tf24_11_every_selection_must_hold_on_the_root(tmp_path: Path) -> None:
    path = _both_versions(tmp_path)
    data = imported(by_status(path, tmp_path / "st", "one", "--select", "metadata:version=candidate", "--select", "metadata:ls_example_case=c03"))
    assert data["rows"] == 1 and data["counts"]["selected"] == 1
    # the key is read on the root: the llm runs' ls_model_name selects nothing
    line = refused(run_import(by_status(path, tmp_path / "st", "none", "--select", "metadata:ls_model_name=gpt-4.1-mini")))
    assert "no row" in line or "select" in line, line
    assert not (tmp_path / "st" / "none").exists()


def test_tf24_11_select_reads_the_csv_s_root_too(tmp_path: Path) -> None:
    data = imported(by_status(export("candidate", "ui"), tmp_path / "st", "r", "--select", "metadata:ls_example_case=c09"))
    assert data["rows"] == 1 and tally(data) == {"missed": 1}


# ---------- TF24-12 ----------


@pytest.mark.parametrize("kind", ["v1", "v2", "cli-runs"])
def test_tf24_12_a_trace_with_no_root_is_left_out_and_counted(tmp_path: Path, kind: str) -> None:
    def drop(rows: list[dict[str, Any]]) -> None:
        held = roots(rows)
        for case in ("c03", "c08"):
            rows.remove(held[case])  # type: ignore[arg-type]

    path = write_rows(tmp_path / ("runs.jsonl" if kind == "cli-runs" else "runs.json"), export("baseline", kind)[0], drop)
    data = imported(by_status(path, tmp_path / "st", "r"))
    assert data["rows"] == 8 and data["counts"]["no root run"] == 2 and data["counts"]["traces"] == 10
    assert sorted(_outcomes(tmp_path / "st", "r")) == [c for c in CASES if c not in ("c03", "c08")]
    assert tally(data) == {"met": 8}


@pytest.mark.parametrize(("a", "b"), [("v1", "v2"), ("v2", "v2-subtree"), ("cli-runs", "cli-traces"), ("v2", "cli-runs")])
def test_tf24_12_a_run_in_two_of_the_files_is_refused(tmp_path: Path, a: str, b: str) -> None:
    files = [*export("baseline", a), *export("baseline", b)]
    line = refused(run_import(by_status(files, tmp_path / "st", "r")))
    ids = {run_id(r) for r in rows_of(export("baseline", a)[0])}
    assert any(i in line for i in ids), line
    assert files[0].name in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("kind", ["v1", "v2", "cli-runs"])
def test_tf24_12_a_run_s_parent_is_its_nearest_ancestor(tmp_path: Path, kind: str) -> None:
    """The candidate's c03 with its parser moved under its llm run: the llm run then wraps a step
    and is no step itself, the parser's span hangs under it, and it is still one model call."""
    def nest(rows: list[dict[str, Any]]) -> None:
        root, *under = trace_rows(rows, "c03")
        llm = next(r for r in under if r["run_type"] == "llm")
        parser = next(r for r in under if r["run_type"] == "parser")
        if "parent_run_ids" in parser:
            parser["parent_run_ids"] = [run_id(root), run_id(llm)]
        if "parent_run_id" in parser:
            parser["parent_run_id"] = run_id(llm)

    name = "runs.jsonl" if kind == "cli-runs" else "runs.json"
    path = write_rows(tmp_path / name, export("candidate", kind)[0], nest)
    imported(by_status(path, tmp_path / "st", "r"))
    rec = recs(tmp_path / "st", "r")
    assert rec["c03"]["steps"] == 3 and rec["c03"]["llm_calls"] == 1 and rec["c03"]["total_tokens"] == 93
    assert rec["c02"]["steps"] == 4
    row = columns(tmp_path / "st", "r")["c03"]
    spans = (row["trace"] if isinstance(row["trace"], dict) else json.loads(row["trace"]))["spans"]
    rows = rows_of(export("candidate", kind)[0])
    _, *under = trace_rows(rows, "c03")
    llm = next(run_id(r) for r in under if r["run_type"] == "llm").replace("-", "")
    parser = next(run_id(r) for r in under if r["run_type"] == "parser").replace("-", "")
    by_id = {span["span_id"]: span for span in spans}
    assert by_id[parser]["parent_id"] == llm and by_id[llm]["parent_id"] == run_id(trace_rows(rows, "c03")[0]).replace("-", "")
    assert row["t"] == 3.0


def test_tf24_12_the_csv_and_run_exports_are_not_one_import(tmp_path: Path) -> None:
    files = [*export("baseline", "ui"), *export("baseline", "v2")]
    line = refused(run_import(by_status(files, tmp_path / "st", "r")))
    assert "CSV" in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF24-13 ----------


@pytest.mark.parametrize("kind", ["v1", "v2", "cli-runs"])
def test_tf24_13_the_tries_of_a_case_are_in_the_order_they_ran(tmp_path: Path, kind: str) -> None:
    """Both versions in one file, the later one written first: each example is a case with two
    tries, the baseline's (which ran first) the first."""
    from tf21_support import records

    rows = rows_of(export("candidate", kind)[0]) + rows_of(export("baseline", kind)[0])
    random.Random(7).shuffle(rows)
    path = tmp_path / "both.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    data = imported(ls_argv(path, tmp_path / "st", "r", outcome="feedback:thumbs"))
    assert data["rows"] == 20 and data["cases"] == 10 and data["repeats"] == {"min": 2, "max": 2}
    got = {(r["case"], r["repeat"]): r["score"] for r in records(tmp_path / "st", "r")}
    for case in CASES:
        assert got[(case, 0)] == EXACT["baseline"][case], case
        assert got[(case, 1)] == EXACT["candidate"][case], case


# ---------- TF24-14 ----------

EARLIEST = {"baseline": "2026-11-09T20:38:00.809772", "candidate": "2026-11-09T20:38:19.330259"}


@pytest.mark.parametrize(("version", "kind"), BOTH_TRACES)
def test_tf24_14_the_start_is_the_earliest_run_s_read_as_utc(tmp_path_factory: Any, version: str, kind: str) -> None:
    _, data = world(tmp_path_factory, version, kind, "status")
    assert data["started"]["from"] == "earliest span"
    assert data["started"]["at"].rstrip("Z").startswith(EARLIEST[version][:19]), data["started"]
    assert data["started"]["at"].endswith("Z")


def test_tf24_14_the_earliest_start_is_the_file_s_own() -> None:
    for version in VERSIONS:
        for kind in ("v1", "v2", "cli-runs"):
            starts = [r["start_time"].rstrip("Z").ljust(26, "0") for r in rows_of(export(version, kind)[0])]
            assert min(starts) == EARLIEST[version], (version, kind)


def test_tf24_14_a_time_with_no_zone_is_utc_whatever_the_machine_s_zone(tmp_path: Path) -> None:
    """v1 writes its times with no zone. Run in a subprocess at New York's zone, where a
    reading in the machine's zone would be five hours off."""
    import os
    import subprocess
    import sys

    argv = by_status(export("baseline", "v1"), tmp_path / "st", "r", "--json")
    code = "import sys; from poisson_trace.ingest.cli import main; raise SystemExit(main(sys.argv[1:]))"
    ran = subprocess.run([sys.executable, "-c", code, *argv], capture_output=True, text=True, env={**os.environ, "TZ": "America/New_York"}, check=False)
    assert ran.returncode == 0, ran.stderr
    assert json.loads(ran.stdout)["started"]["at"].startswith("2026-11-09T20:38:00"), ran.stdout


@pytest.mark.parametrize("version", VERSIONS)
def test_tf24_14_the_csv_carries_no_time_so_its_start_is_the_file_s(tmp_path_factory: Any, version: str) -> None:
    _, data = world(tmp_path_factory, version, "ui", "status")
    assert data["started"]["from"] == "file time"


# ---------- TF24-15 ----------


@pytest.mark.parametrize("kind", ["v1", "v2"])
def test_tf24_15_a_root_still_pending_has_no_outcome(tmp_path: Path, kind: str) -> None:
    def pend(rows: list[dict[str, Any]]) -> None:
        root = roots(rows)["c02"]
        root["status"] = "pending"
        root.pop("end_time", None)
        if kind == "v1":
            root["end_time"] = None

    path = write_rows(tmp_path / "runs.json", export("baseline", kind)[0], pend)
    data = imported(by_status(path, tmp_path / "st", "r"))
    assert data["no_outcome"] == {"pending": 1} and tally(data) == {"met": 8, "missed": 1}
    got = columns(tmp_path / "st", "r")["c02"]
    assert got["outcome"] is None and got["error"] == "pending"
    rec = recs(tmp_path / "st", "r")["c02"]
    assert rec["outcome"] is None and rec["wall_time_s"] is None
