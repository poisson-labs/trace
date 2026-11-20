"""TF26-4 to TF26-15: the reader on every committed Weave capture: rows, cases and outcomes.

- TF26-4: every export of all four evaluations (the service's answer with costs and feedback,
  the same with the example expanded, the page's JSON, JSON Lines, CSV and TSV) reads as one row
  a ``predict_and_score`` call: ten rows on ten cases for the slice, six rows on three cases
  (two tries each) for the lookup fixture; so do the candidate's answer with neither include
  flag and its answer in pages. The summary names the tool, the files with their digests and
  the shape read.
- TF26-5: the case, four ways: the dataset row by the digest in its reference (the same in both
  versions; refused in one sentence naming another way on the page's table, which leaves the
  reference out); a key of the row (wherever the file holds the row; refused naming ``example``
  where it holds only the reference); the input key of the row's values, ``input:`` and 12 hex
  characters, the same from every export that holds the row and what ``--verdicts`` joins by;
  ``none``, one case for every row, with its sentence among the counts. A row that lacks what
  the others have has no case and is counted.
- TF26-6: the outcome by the status: missed when the case errored, met otherwise, in every
  export. A step that failed under a case that answered does not fail it (the candidate's
  retried stock check, whose call says ``descendant_error``).
- TF26-7: the outcome by a score at a cut: ``exact`` under 0.5 missed, a score equal to the cut
  meeting it, ``--above`` the other way. True is 1 and false is 0, and the summary counts the
  rows read so; a number is read as it is. A score is named by its dotted path, and by its
  scorer alone where the scorer gave a value under its own name (``exact.exact`` is ``exact``,
  asked for by either); a scorer's other values are named by their paths. A scorer's text is
  never kept.
- TF26-8: files that hold more than one evaluation are refused naming each; ``--evaluation``
  picks one by the evaluation's name, by the id of its call, or by the name Weave shows for the
  call where the files hold that call; a name the files do not hold, and a name two runs share,
  are refused. The counts say how many calls were read and how many rows kept.
- TF26-9: a case that errored has no score and is censored; a case that did not error and has
  no score for the key is unscored, which a verdicts file may fill; a file where no row has
  the score writes nothing.
- TF26-10: the paged answer reads as the whole answer does, pages in any order, the empty last
  page among them or not; a list of calls reads as a call a line does.
- TF26-11: a file that holds nothing but ``Evaluation.evaluate`` calls (the Traces page with no
  filter, in each of its four formats, and the service's root calls) is refused saying how to
  get the rows; a page of an answer read alone is no such file: it reads to the rows it holds,
  and to none where it holds none.
- TF26-12: a call in two of the files given is refused naming it, and nothing is written: two
  answers of one evaluation, an answer beside the page's download, two of the page's downloads.
- TF26-13: rows come in the order their calls started, whatever order the file holds them, so
  the tries of a case are its repeats in the order they ran.
- TF26-14: the start is the first row's start, the same from every export;
  rows with no start take the file's time.
- TF26-15: a row whose call has not ended has no outcome under ``status`` and the reason
  ``pending``.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path
from typing import Any

import pytest

from signals_support import records, run_import
from weave_support import (
    API_EXPORTS, CALL_ID, CALLS, CANDIDATE_ONLY, CASES, DIGEST, EARLIEST, ERRORED, EVALUATION, EXACT, EXPORTS, ITEM, KEY, LOOKUP,
    LOOKUP_EXACT, NAMES, QUESTIONS, RETRIED, ROOTS_ONLY, RUN, SHAPE, SHOWN, UI_CALLS, UI_EXPORTS, UI_TABLES, VERSIONS, WITH_REF,
    WITH_ROW, by_status, calls_of, columns, edited, edited_table, evaluation, export, imported, of, of_evaluation, outcomes, passed,
    picked, recs, refused, rows_by_case, table_rows, tally, tries, world, write_calls, wv_argv,
)

BOTH = [(v, k) for v in VERSIONS for k in EXPORTS]
ONLY_REF = ("pull", "plain", "pages")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _by_status(version: str) -> dict[str, str]:
    return {case: "missed" if case == ERRORED[version][0] else "met" for case in CASES}


# ---------- TF26-4 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf26_4_every_export_of_the_slice_reads_as_ten_rows_on_the_ten_cases(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, data = world(tmp_path_factory, version, kind, "status")
    assert data["tool"] == "weave" and data["run"] == RUN
    assert data["rows"] == 10 and data["cases"] == 10 and data["repeats"] == {"min": 1, "max": 1}
    files = export(version, kind)
    assert [f["name"] for f in data["files"]] == [p.name for p in files]
    assert [f["sha256"] for f in data["files"]] == [_sha(p) for p in files]
    assert data["declared"]["shapes"] == [SHAPE[kind]]
    assert sorted(recs(root, RUN)) == list(CASES)
    assert data["counts"]["selected"] == 10 and data["counts"]["no case"] == 0
    if kind in API_EXPORTS:
        assert data["counts"]["calls"] == CALLS[version] and data["counts"]["predict_and_score calls"] == 10
    else:
        assert data["counts"]["calls"] == 32 and data["counts"]["predict_and_score calls"] == 32


@pytest.mark.parametrize("name", LOOKUP)
@pytest.mark.parametrize("kind", EXPORTS)
def test_tf26_4_every_export_of_the_lookup_fixture_reads_as_two_tries_of_three_cases(tmp_path_factory: Any, name: str, kind: str) -> None:
    root, data = world(tmp_path_factory, name, kind, "exact")
    assert data["rows"] == 6 and data["cases"] == 3 and data["repeats"] == {"min": 2, "max": 2}
    failed = sum(2 for q in QUESTIONS if LOOKUP_EXACT[name][q] < 0.5)
    assert tally(data) == ({"met": 6 - failed, "missed": failed} if failed else {"met": 6})
    got = tries(root, RUN)
    assert sorted(got) == [(q, n) for q in QUESTIONS for n in (0, 1)]
    assert {key: rec["score"] for key, rec in got.items()} == {(q, n): LOOKUP_EXACT[name][q] for q in QUESTIONS for n in (0, 1)}


@pytest.mark.parametrize("kind", CANDIDATE_ONLY)
def test_tf26_4_the_candidate_s_plain_answer_and_its_pages_read_as_its_answer_does(tmp_path_factory: Any, kind: str) -> None:
    root, data = world(tmp_path_factory, "candidate", kind, "exact")
    whole_root, whole = world(tmp_path_factory, "candidate", "pull", "exact")
    assert data["rows"] == 10 and data["counts"]["calls"] == 81 and data["declared"]["shapes"] == ["call"]
    assert outcomes(root, RUN) == outcomes(whole_root, RUN)
    assert len(data["files"]) == (4 if kind == "pages" else 1)
    for key in ("outcomes", "no_outcome", "started", "declared"):
        assert data[key] == whole[key], key


def test_tf26_4_the_reader_names_its_shapes() -> None:
    from poisson_trace.ingest import weave

    assert tuple(weave.SHAPES) == ("call", "table")
    assert weave.ADDRESS == "weave:"


# ---------- TF26-5 ----------


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("kind", [k for k in EXPORTS if k in WITH_REF])
def test_tf26_5_the_dataset_row_s_digest_is_the_case_where_the_export_carries_its_reference(tmp_path: Path, version: str, kind: str) -> None:
    data = imported(of(version, kind, tmp_path / "st", "r", mode="status", case="example"))
    assert data["declared"]["case_from"] == "example"
    assert outcomes(tmp_path / "st", "r") == _by_status(version)
    # the row's own digest is the case, the same in both versions: nothing of the row is in it
    assert sorted(r["case"] for r in records(tmp_path / "st", "r")) == sorted(DIGEST[case] for case in CASES)


@pytest.mark.parametrize("kind", UI_TABLES)
def test_tf26_5_example_is_refused_on_the_page_s_table_naming_another_way(tmp_path: Path, kind: str) -> None:
    line = refused(run_import(of("baseline", kind, tmp_path / "st", "r", mode="status", case="example")))
    assert "--case-from example" in line and "example:" in line and "--case-from input" in line, line
    assert "table" in line, line
    assert not (tmp_path / "st").exists()
    imported(of("baseline", kind, tmp_path / "st", "r", mode="status", case="input"))


@pytest.mark.parametrize("kind", ["pull", "ui-json"])
def test_tf26_5_a_row_without_a_reference_among_rows_that_have_one_has_no_case(tmp_path: Path, kind: str) -> None:
    def drop(calls: list[dict[str, Any]]) -> None:
        held = rows_by_case(calls, "baseline")
        held["c02"]["inputs"]["example"] = None
        if kind == "pull":
            del held["c07"]["inputs"]["example"]
        else:
            del held["c07"]["inputs"]["example"]["_ref"]

    path = edited(tmp_path, "baseline", kind, drop)
    data = imported(by_status(path, tmp_path / "st", "r", *picked("baseline", kind)))
    assert data["rows"] == 8 and data["counts"]["no case"] == 2 and data["counts"]["selected"] == 10
    assert sorted(outcomes(tmp_path / "st", "r")) == [c for c in CASES if c not in ("c02", "c07")]


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("kind", WITH_ROW)
@pytest.mark.parametrize("key", ["case", "id"])
def test_tf26_5_a_key_of_the_row_is_the_case_where_the_export_holds_the_row(tmp_path: Path, version: str, kind: str, key: str) -> None:
    data = imported(of(version, kind, tmp_path / "st", "r", mode="status", case=f"example:{key}"))
    assert data["declared"]["case_from"] == f"example:{key}"
    assert sorted(r["case"] for r in records(tmp_path / "st", "r")) == list(CASES)
    assert outcomes(tmp_path / "st", "r") == _by_status(version)


@pytest.mark.parametrize("kind", ONLY_REF)
def test_tf26_5_a_key_of_the_row_is_refused_where_the_export_holds_only_its_reference(tmp_path: Path, kind: str) -> None:
    line = refused(run_import(of("candidate", kind, tmp_path / "st", "r", mode="status", case="example:case")))
    assert "example:case" in line and "reference" in line and "--case-from example" in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("kind", ["expanded", "ui-jsonl", "ui-csv"])
def test_tf26_5_a_row_that_lacks_the_key_has_no_case_and_is_counted(tmp_path: Path, kind: str) -> None:
    if kind == "ui-csv":
        def blank(rows: list[dict[str, str]]) -> None:
            held = table_rows(rows, "baseline")
            for case in ("c02", "c05", "c07"):
                held[case]["inputs.example.case"] = ""

        path = edited_table(tmp_path, kind, blank)
    else:
        def drop(calls: list[dict[str, Any]]) -> None:
            held = rows_by_case(calls, "baseline")
            # no key, an empty value and a null: each names no case
            del held["c02"]["inputs"]["example"]["case"]
            held["c05"]["inputs"]["example"]["case"] = ""
            held["c07"]["inputs"]["example"]["case"] = None

        path = edited(tmp_path, "baseline", kind, drop)
    data = imported(by_status(path, tmp_path / "st", "r", *picked("baseline", kind), case="example:case"))
    assert data["rows"] == 7 and data["counts"]["no case"] == 3
    assert sorted(outcomes(tmp_path / "st", "r")) == [c for c in CASES if c not in ("c02", "c05", "c07")]


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("kind", WITH_ROW)
def test_tf26_5_input_is_a_key_of_the_row_s_values_and_never_their_text(tmp_path: Path, version: str, kind: str) -> None:
    data = imported(of(version, kind, tmp_path / "st", "r", mode="status", case="input"))
    got = sorted(r["case"] for r in records(tmp_path / "st", "r"))
    # the same key from the service's answer, the page's JSON and the page's table
    assert got == sorted(KEY[case] for case in CASES)
    assert all(re.fullmatch(r"input:[0-9a-f]{12}", case) for case in got)
    assert tally(data) == {"met": 9, "missed": 1} and outcomes(tmp_path / "st", "r")[ERRORED[version][0]] == "missed"
    held = b"".join(p.read_bytes() for p in (tmp_path / "st").rglob("*") if p.is_file())
    for item in ITEM.values():
        assert item.encode() not in held, item


@pytest.mark.parametrize("kind", ONLY_REF)
def test_tf26_5_input_is_refused_where_the_export_holds_only_the_reference(tmp_path: Path, kind: str) -> None:
    line = refused(run_import(of("candidate", kind, tmp_path / "st", "r", mode="status", case="input")))
    assert "--case-from input" in line and "reference" in line and "--case-from example" in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("kind", ["expanded", "ui-json", "ui-csv"])
def test_tf26_5_a_verdicts_file_joins_by_input(tmp_path: Path, kind: str) -> None:
    """The reader hands the import each case's input key, so a verdict that names an input and
    no case joins the row of that input. Here it agrees with what the file recorded."""
    verdicts = tmp_path / "v.jsonl"
    row = {"id": "c10", "case": "c10", "item": ITEM["c10"], "expected": "reorder"}
    verdicts.write_text(json.dumps({"input": row, "outcome": "fail"}) + "\n", encoding="utf-8")
    data = imported(of("baseline", kind, tmp_path / "st", "r", "--verdicts", verdicts))
    assert data["verdicts"]["by_input"] == 1 and data["verdicts"]["by_case"] == 0 and data["verdicts"]["unmatched"] == 0, data["verdicts"]
    assert outcomes(tmp_path / "st", "r")["c10"] == "missed"


@pytest.mark.parametrize("kind", ["pull", "ui-json", "ui-tsv"])
def test_tf26_5_none_reads_every_row_as_one_input_and_says_so(tmp_path: Path, kind: str) -> None:
    data = imported(of("candidate", kind, tmp_path / "st", "r", mode="status", case="none"))
    assert data["cases"] == 1 and data["rows"] == 10 and data["repeats"] == {"min": 10, "max": 10}
    said = [label for label in data["counts"] if "mix of inputs" in label]
    assert len(said) == 1 and data["counts"][said[0]] == 10, data["counts"]
    other = imported(of("candidate", kind, tmp_path / "st2", "r", mode="status"))
    assert not [label for label in other["counts"] if "mix of inputs" in label]


# ---------- TF26-6 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf26_6_by_the_status_the_case_that_errored_is_the_one_missed(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, data = world(tmp_path_factory, version, kind, "status")
    bad = ERRORED[version][0]
    assert outcomes(root, RUN) == _by_status(version)
    assert tally(data) == {"met": 9, "missed": 1} and data["no_outcome"] == {}
    assert data["declared"]["outcome_from"] == "status" and "cut" not in data["declared"]
    stored = recs(root, RUN)
    assert {case: r["outcome"] for case, r in stored.items()} == {case: "fail" if case == bad else "pass" for case in CASES}
    # a row with an outcome carries no error word (Prove refuses a row with both)
    assert all(r["error"] is None for r in columns(root, RUN).values())
    # a step that failed and was retried did not fail the case: descendant_error alone is no error
    if version == RETRIED[0]:
        assert stored[RETRIED[1]]["outcome"] == "pass" and stored[RETRIED[1]]["failure_kind"] is None


@pytest.mark.parametrize("kind", ["pull", "ui-json", "ui-csv"])
def test_tf26_6_a_call_that_raised_itself_is_an_error(tmp_path: Path, kind: str) -> None:
    """No capture holds a row whose own status is ``error``; one is made here from a row that
    passed, its output and its scores left in place."""
    if kind == "ui-csv":
        def raise_(rows: list[dict[str, str]]) -> None:
            table_rows(rows, "candidate")["c02"]["summary.weave.status"] = "error"

        path = edited_table(tmp_path, kind, raise_)
    else:
        def raise_(calls: list[dict[str, Any]]) -> None:  # type: ignore[misc]
            rows_by_case(calls, "candidate")["c02"]["summary"]["weave"]["status"] = "error"

        path = edited(tmp_path, "candidate", kind, raise_)
    imported(by_status(path, tmp_path / "st", "r", *picked("candidate", kind), case="example" if kind != "ui-csv" else "example:id"))
    assert outcomes(tmp_path / "st", "r") == {**_by_status("candidate"), "c02": "missed"}


@pytest.mark.parametrize("kind", ["pull", "ui-json", "ui-csv"])
def test_tf26_6_something_raised_under_a_case_that_holds_an_output_or_a_score_is_no_error(tmp_path: Path, kind: str) -> None:
    """``descendant_error`` with an output, or with a score, is a case that answered."""
    if kind == "ui-csv":
        def edit(rows: list[dict[str, str]]) -> None:
            held = table_rows(rows, "baseline")
            held["c08"]["output.output"] = "reorder"
            held["c02"]["summary.weave.status"] = "descendant_error"
            held["c02"]["output.output"] = ""

        path = edited_table(tmp_path, kind, edit)
    else:
        def edit(calls: list[dict[str, Any]]) -> None:  # type: ignore[misc]
            held = rows_by_case(calls, "baseline")
            # c08 errored in the capture: given an output, it answered
            held["c08"]["output"]["output"] = "reorder"
            for call in calls:
                if call["parent_id"] == held["c08"]["id"]:
                    call["summary"]["weave"]["status"] = "descendant_error"
                    call["exception"] = None
            # c02 passed: with something raised under it and no output, its scores still say it answered
            held["c02"]["summary"]["weave"]["status"] = "descendant_error"
            held["c02"]["output"]["output"] = None

        path = edited(tmp_path, "baseline", kind, edit)
    imported(by_status(path, tmp_path / "st", "r", *picked("baseline", kind), case="example" if kind != "ui-csv" else "example:id"))
    assert outcomes(tmp_path / "st", "r") == dict.fromkeys(CASES, "met")


# ---------- TF26-7 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf26_7_by_a_score_at_a_cut(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, data = world(tmp_path_factory, version, kind, "exact")
    want = {case: None if ok is None else ("met" if ok else "missed") for case, ok in passed(version).items()}
    assert outcomes(root, RUN) == want
    assert data["declared"]["outcome_from"] == "score:exact"
    assert data["declared"]["cut"] == 0.5 and data["declared"]["side"] == "below"
    assert tally(data) == {"baseline": {"met": 6, "missed": 3}, "candidate": {"met": 8, "missed": 1}}[version]
    assert data["no_outcome"] == {"no score": 1}
    stored = recs(root, RUN)
    assert {case: r["score"] for case, r in stored.items()} == EXACT[version]


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf26_7_true_is_1_and_false_is_0_and_the_summary_says_so(tmp_path_factory: Any, version: str, kind: str) -> None:
    _, data = world(tmp_path_factory, version, kind, "exact")
    said = [label for label in data["counts"] if "true or false" in label]
    assert len(said) == 1 and " 1 " in f" {said[0]} " and " 0" in said[0], data["counts"]
    assert data["counts"][said[0]] == 9, "the nine rows that hold the score"
    _, by = world(tmp_path_factory, version, kind, "status")
    assert not [label for label in by["counts"] if "true or false" in label], "nothing is said where no score is read"


@pytest.mark.parametrize(("extra", "missed"), [
    (("--cut", "1", "--below"), 3), (("--cut", "0", "--below"), 0), (("--cut", "0", "--above"), 6), (("--cut", "1", "--above"), 0),
])
@pytest.mark.parametrize("kind", ["pull", "ui-csv"])
def test_tf26_7_a_score_equal_to_the_cut_meets_it_on_either_side(tmp_path: Path, kind: str, extra: tuple[str, ...], missed: int) -> None:
    data = imported(of("baseline", kind, tmp_path / "st", "r", *extra, cut=None))
    assert data["outcomes"].get("missed", 0) == missed and data["outcomes"].get("met", 0) == 9 - missed
    assert data["no_outcome"] == {"no score": 1}


@pytest.mark.parametrize("kind", ["pull", "ui-jsonl", "ui-tsv"])
@pytest.mark.parametrize("key", ["gave_answer", "gave_answer.gave_answer"])
def test_tf26_7_another_scorer_is_read_the_same_way_by_its_name_or_its_dotted_path(tmp_path: Path, kind: str, key: str) -> None:
    data = imported(of("baseline", kind, tmp_path / "st", "r", outcome=f"score:{key}"))
    assert tally(data) == {"met": 8, "missed": 1} and data["no_outcome"] == {"no score": 1}
    assert outcomes(tmp_path / "st", "r")["c10"] == "missed"
    assert data["declared"]["outcome_from"] == f"score:{key}"
    # however it is asked for, the score is kept under the scorer's name
    assert recs(tmp_path / "st", "r")["c10"]["scores"] == {"exact": 0.0, "gave_answer": 0.0}


@pytest.mark.parametrize("kind", ["pull", "ui-json", "ui-csv"])
def test_tf26_7_a_number_is_read_as_it_is(tmp_path: Path, kind: str) -> None:
    grades = {case: 0.25 if case in ("c02", "c05") else 0.75 for case in CASES}
    if kind == "ui-csv":
        def grade(rows: list[dict[str, str]]) -> None:
            for case, row in table_rows(rows, "baseline").items():
                if row["output.scores.exact.exact"]:
                    row["output.scores.exact.exact"] = str(grades[case])

        path = edited_table(tmp_path, kind, grade)
    else:
        def grade(calls: list[dict[str, Any]]) -> None:  # type: ignore[misc]
            for case, row in rows_by_case(calls, "baseline").items():
                if row["output"]["scores"]:
                    row["output"]["scores"]["exact"] = {"exact": grades[case]}

        path = edited(tmp_path, "baseline", kind, grade)
    data = imported(wv_argv(path, tmp_path / "st", "r", *picked("baseline", kind), case="example" if kind != "ui-csv" else "example:id"))
    assert tally(data) == {"met": 7, "missed": 2} and data["no_outcome"] == {"no score": 1}
    assert {c: r["score"] for c, r in recs(tmp_path / "st", "r").items()} == {c: None if c == "c08" else grades[c] for c in CASES}
    assert not [label for label in data["counts"] if "true or false" in label], "no score read was true or false"


@pytest.mark.parametrize("kind", ["pull", "ui-json", "ui-csv"])
def test_tf26_7_a_scorer_s_other_values_are_named_by_their_paths_and_its_text_is_never_kept(tmp_path: Path, kind: str) -> None:
    reason = "the judge wrote: the answer repeats the customer's order number"
    if kind == "ui-csv":
        def judge(rows: list[dict[str, str]]) -> None:
            for case, row in table_rows(rows, "baseline").items():
                if row["output.scores.exact.exact"]:
                    row["output.scores.judge.correct"] = "False" if case == "c02" else "True"
                    row["output.scores.judge.confidence"] = "0.9"
                    row["output.scores.judge.reason"] = reason

        path = edited_table(tmp_path, kind, judge, header=lambda fields: [*fields, "output.scores.judge.correct", "output.scores.judge.confidence", "output.scores.judge.reason"])
    else:
        def judge(calls: list[dict[str, Any]]) -> None:  # type: ignore[misc]
            for case, row in rows_by_case(calls, "baseline").items():
                if row["output"]["scores"]:
                    row["output"]["scores"]["judge"] = {"correct": case != "c02", "confidence": 0.9, "reason": reason}

        path = edited(tmp_path, "baseline", kind, judge)
    extra = picked("baseline", kind)
    case = "example" if kind != "ui-csv" else "example:id"
    result = run_import(wv_argv(path, tmp_path / "st", "r", *extra, case=case, outcome="score:judge.correct"))
    assert result.code == 0 and reason not in result.out + result.err, result.err
    stored = recs(tmp_path / "st", "r")
    assert stored["c02"]["outcome"] == "fail" and stored["c01"]["outcome"] == "pass"
    assert stored["c01"]["scores"] == {"exact": 1.0, "gave_answer": 1.0, "judge.correct": 1.0, "judge.confidence": 0.9}
    held = b"".join(p.read_bytes() for p in (tmp_path / "st").rglob("*") if p.is_file())
    assert b"the judge wrote" not in held and b"order number" not in held
    # the scorer's own name names no one value of it
    line = refused(run_import(wv_argv(path, tmp_path / "st", "r2", *extra, case=case, outcome="score:judge")))
    assert "outcome" in line, line
    by_number = imported(wv_argv(path, tmp_path / "st", "r3", *extra, "--cut", "0.95", "--below", case=case, outcome="score:judge.confidence", cut=None))
    assert tally(by_number) == {"missed": 9}


# ---------- TF26-8 ----------


def _two_answers(tmp_path: Path) -> Path:
    """Both versions' answers in one file, the calls shuffled."""
    calls = calls_of(export("baseline", "pull")[0]) + calls_of(export("candidate", "pull")[0])
    random.Random(26).shuffle(calls)
    return write_calls(tmp_path / "both.jsonl", calls)


@pytest.mark.parametrize("kind", UI_EXPORTS)
def test_tf26_8_a_file_of_several_evaluations_is_refused_naming_each(tmp_path: Path, kind: str) -> None:
    case = "example" if kind in UI_CALLS else "example:id"
    line = refused(run_import(by_status(export("baseline", kind), tmp_path / "st", "r", case=case)))
    assert "4 evaluations" in line and "--evaluation" in line, line
    for name in NAMES:
        assert EVALUATION[name] in line and CALL_ID[name] in line, (name, line)
    assert "6 rows" in line and "10 rows" in line, line
    assert not (tmp_path / "st").exists()


# by its name a slice evaluation is the command TF26-4 and TF26-14 read, so one page format of each shape holds it here
PICKED = [(by, name, kind) for kind in UI_EXPORTS for name in NAMES for by in ("name", "id")
          if by == "id" or name in LOOKUP or (name, kind) in (("baseline", "ui-json"), ("baseline", "ui-csv"))]


@pytest.mark.parametrize(("by", "name", "kind"), PICKED)
def test_tf26_8_evaluation_picks_one_by_its_name_or_by_the_id_of_its_call(tmp_path: Path, kind: str, name: str, by: str) -> None:
    word = EVALUATION[name] if by == "name" else CALL_ID[name]
    case = "example" if kind in UI_CALLS else "example:id"
    data = imported(by_status(export(name, kind), tmp_path / "st", "r", "--evaluation", word, case=case))
    assert data["declared"]["evaluation"] == word
    assert data["rows"] == (10 if name in VERSIONS else 6)
    assert data["counts"]["predict_and_score calls"] == 32 and data["counts"]["selected"] == data["rows"]
    assert data["started"]["at"] == EARLIEST[name]


def test_tf26_8_the_name_weave_shows_picks_one_where_the_files_hold_its_call(tmp_path: Path) -> None:
    path = _two_answers(tmp_path)
    line = refused(run_import(by_status(path, tmp_path / "st", "r")))
    assert "2 evaluations" in line and EVALUATION["baseline"] in line and EVALUATION["candidate"] in line, line
    for version in VERSIONS:
        for word in (SHOWN[version], EVALUATION[version], CALL_ID[version]):
            run = f"{version}-{len(word)}"
            data = imported(by_status(path, tmp_path / "st", run, "--evaluation", word))
            assert data["rows"] == 10 and data["counts"]["calls"] == 159 and data["counts"]["predict_and_score calls"] == 20
            assert outcomes(tmp_path / "st", run) == _by_status(version)
    # the page's download does not hold the evaluations' own calls, so their shown names pick nothing there
    line = refused(run_import(by_status(export("baseline", "ui-json"), tmp_path / "st", "x", "--evaluation", SHOWN["baseline"])))
    assert SHOWN["baseline"] in line, line


@pytest.mark.parametrize("kind", ["pull", "ui-json", "ui-csv"])
def test_tf26_8_a_name_the_files_do_not_hold_is_refused_naming_what_they_hold(tmp_path: Path, kind: str) -> None:
    case = "example" if kind != "ui-csv" else "example:id"
    line = refused(run_import(by_status(export("baseline", kind), tmp_path / "st", "r", "--evaluation", "trace-fixture", case=case)))
    assert "no evaluation named trace-fixture" in line and EVALUATION["baseline"] in line, line
    assert not (tmp_path / "st").exists()


def test_tf26_8_a_name_two_runs_share_is_refused_and_the_call_s_id_picks_one(tmp_path: Path) -> None:
    """One evaluation run against two models is two ``Evaluation.evaluate`` calls of one name.
    Built here: the candidate's rows renamed to the baseline's evaluation."""
    def rename(calls: list[dict[str, Any]]) -> None:
        for call in of_evaluation(calls, "candidate"):
            call["inputs"]["self"] = call["inputs"]["self"].replace(EVALUATION["candidate"], EVALUATION["baseline"])

    path = edited(tmp_path, "baseline", "ui-json", rename)
    line = refused(run_import(by_status(path, tmp_path / "st", "r", "--evaluation", EVALUATION["baseline"])))
    assert "2 times" in line and CALL_ID["baseline"] in line and CALL_ID["candidate"] in line, line
    data = imported(by_status(path, tmp_path / "st", "r", "--evaluation", CALL_ID["candidate"]))
    assert outcomes(tmp_path / "st", "r") == _by_status("candidate") and data["rows"] == 10


@pytest.mark.parametrize("kind", API_EXPORTS)
def test_tf26_8_a_file_of_one_evaluation_needs_no_name_and_takes_its_own(tmp_path: Path, kind: str) -> None:
    plain = imported(by_status(export("baseline", kind), tmp_path / "st", "a"))
    assert "evaluation" not in plain["declared"]
    for word in (EVALUATION["baseline"], CALL_ID["baseline"], SHOWN["baseline"]):
        named = imported(by_status(export("baseline", kind), tmp_path / "st", f"b{len(word)}", "--evaluation", word))
        assert named["declared"]["evaluation"] == word and named["outcomes"] == plain["outcomes"]


# ---------- TF26-9 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf26_9_a_case_that_errored_has_no_score_and_is_censored(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, _ = world(tmp_path_factory, version, kind, "exact")
    bad = ERRORED[version][0]
    got, stored = columns(root, RUN)[bad], recs(root, RUN)[bad]
    assert got["outcome"] is None and got["error"] == "no score", got
    assert stored["outcome"] == "censored" and stored["score"] is None and stored["scores"] == {}
    assert stored["failure_kind"] is not None


@pytest.mark.parametrize("kind", ["expanded", "ui-json", "ui-csv"])
def test_tf26_9_a_case_that_did_not_error_and_has_no_score_is_unscored(tmp_path: Path, kind: str) -> None:
    if kind == "ui-csv":
        def unscore(rows: list[dict[str, str]]) -> None:
            table_rows(rows, "baseline")["c10"]["output.scores.exact.exact"] = ""

        path = edited_table(tmp_path, kind, unscore)
    else:
        def unscore(calls: list[dict[str, Any]]) -> None:  # type: ignore[misc]
            del rows_by_case(calls, "baseline")["c10"]["output"]["scores"]["exact"]

        path = edited(tmp_path, "baseline", kind, unscore)
    extra = picked("baseline", kind)
    data = imported(wv_argv(path, tmp_path / "st", "r", *extra, case="input"))
    assert tally(data) == {"met": 6, "missed": 2} and data["no_outcome"] == {"no score": 2}
    stored = recs(tmp_path / "st", "r")
    assert stored["c10"]["outcome"] is None and stored["c10"]["failure_kind"] is None
    assert stored["c10"]["scores"] == {"gave_answer": 0.0}
    assert stored["c08"]["outcome"] == "censored"
    # a verdicts file fills the unscored row, and cannot overturn the censored one (TF22-35)
    verdicts = tmp_path / "v.csv"
    verdicts.write_text(f"case,outcome\n{KEY['c10']},fail\n", encoding="utf-8")
    filled = imported(wv_argv(path, tmp_path / "st", "r2", *extra, "--verdicts", verdicts, case="input"))
    assert filled["verdicts"]["by_case"] == 1 and tally(filled) == {"met": 6, "missed": 3}
    verdicts.write_text(f"case,outcome\n{KEY['c08']},fail\n", encoding="utf-8")
    line = refused(run_import(wv_argv(path, tmp_path / "st", "r3", *extra, "--verdicts", verdicts, case="input")))
    assert "censored" in line, line


@pytest.mark.parametrize("kind", ["pull", "ui-json", "ui-tsv"])
def test_tf26_9_a_file_where_no_row_has_the_score_writes_nothing(tmp_path: Path, kind: str) -> None:
    line = refused(run_import(of("baseline", kind, tmp_path / "st", "r", outcome="score:no_such_scorer")))
    assert "outcome" in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF26-10 ----------


@pytest.mark.parametrize("order", ["as pulled", "reversed", "without the empty page"])
def test_tf26_10_the_pages_read_as_the_whole_answer(tmp_path: Path, order: str) -> None:
    pages = export("candidate", "pages")
    if order == "reversed":
        pages = pages[::-1]
    if order == "without the empty page":
        pages = pages[:3]
    data = imported(wv_argv(pages, tmp_path / "paged", "r"))
    whole = imported(wv_argv(export("candidate", "pull"), tmp_path / "whole", "r"))
    assert data["rows"] == 10 and data["counts"]["calls"] == 81
    assert recs(tmp_path / "paged", "r") == recs(tmp_path / "whole", "r")
    for key in ("outcomes", "no_outcome", "counts", "started", "declared"):
        assert data[key] == whole[key], key
    assert len(data["files"]) == len(pages)


def test_tf26_10_a_list_of_calls_reads_as_a_call_a_line(tmp_path: Path) -> None:
    calls = calls_of(export("candidate", "expanded")[0])
    forms = {
        "list.json": json.dumps(calls),
        "lines.jsonl": "".join(json.dumps(c) + "\n" for c in calls),
        "blank-lines.jsonl": "\n".join(json.dumps(c) + "\n" for c in calls),
        "bom.jsonl": "﻿" + "".join(json.dumps(c) + "\n" for c in calls),
    }
    seen = []
    for name, text in forms.items():
        folder = tmp_path / name.split(".")[0]
        folder.mkdir()
        (folder / name).write_text(text, encoding="utf-8")
        imported(wv_argv(folder / name, folder / "st", "r"))
        seen.append(recs(folder / "st", "r"))
    assert all(s == seen[0] for s in seen[1:])


# ---------- TF26-11 ----------


@pytest.mark.parametrize("path", ROOTS_ONLY, ids=[p.name for p in ROOTS_ONLY])
def test_tf26_11_a_file_of_evaluations_alone_is_refused_saying_how_to_get_the_rows(tmp_path: Path, path: Path) -> None:
    line = refused(run_import(by_status(path, tmp_path / "st", "r")))
    assert path.name in line and "4 Evaluation.evaluate calls" in line, line
    assert "Evaluation.predict_and_score" in line and "filter" in line.lower(), line
    assert "weave:ENTITY/PROJECT/EVALUATION" in line, line
    assert not (tmp_path / "st").exists()
    # naming an evaluation does not make rows of it
    line = refused(run_import(by_status(path, tmp_path / "st", "r", "--evaluation", EVALUATION["baseline"])))
    assert "Evaluation.predict_and_score" in line, line


@pytest.mark.parametrize("page", [1, 2, 3, 4])
def test_tf26_11_a_page_alone_reads_to_the_rows_it_holds_and_is_never_such_a_file(tmp_path: Path, page: int) -> None:
    """The candidate's answer in pages of 40: the first page holds nine rows, the second the
    tenth (it started last) among calls whose rows are on the first, the third one call and no
    row, the fourth nothing. Each alone reads to the rows it holds, and none is refused as a
    file of evaluations: a folder's files are each read alone to check that they are one run."""
    from argparse import Namespace

    from poisson_trace.ingest import weave
    from poisson_trace.ingest.importing import reader_defaults

    path = export("candidate", "pages")[page - 1]
    run = weave.read(Namespace(**{**reader_defaults("weave"), "files": [str(path)], "run": "r", "store": str(tmp_path / "st"),
                                  "case_from": "example", "outcome_from": "status", "signals": {}}))
    assert len(run.rows) == {1: 9, 2: 1, 3: 0, 4: 0}[page]
    assert run.counts["calls"] == {1: 40, 2: 40, 3: 1, 4: 0}[page]
    result = run_import(by_status(path, tmp_path / "st", "r"))
    if page in (1, 2):
        assert result.code == 0, result.err
    else:
        line = refused(result)
        assert "no row" in line and "Evaluation.evaluate" not in line, line
        assert not (tmp_path / "st").exists()


# ---------- TF26-12 ----------


@pytest.mark.parametrize(("a", "b"), [("pull", "expanded"), ("pull", "ui-json"), ("ui-json", "ui-csv"), ("ui-csv", "ui-tsv"), ("expanded", "ui-tsv")])
def test_tf26_12_a_call_in_two_of_the_files_is_refused(tmp_path: Path, a: str, b: str) -> None:
    files = [*export("baseline", a), *export("baseline", b)]
    line = refused(run_import(by_status(files, tmp_path / "st", "r", "--evaluation", evaluation("baseline"), case="none")))
    ids = {c["id"] for c in calls_of(export("baseline", "ui-json")[0])} | {c["id"] for c in calls_of(export("baseline", "pull")[0])}
    assert any(i in line for i in ids), line
    assert files[0].name in line and files[1].name in line and "twice" in line, line
    assert not (tmp_path / "st").exists()


def test_tf26_12_a_call_twice_in_one_file_is_refused(tmp_path: Path) -> None:
    calls = calls_of(export("baseline", "pull")[0])
    path = write_calls(tmp_path / "doubled.jsonl", [*calls, calls[5]])
    line = refused(run_import(by_status(path, tmp_path / "st", "r")))
    assert calls[5]["id"] in line and "doubled.jsonl twice" in line, line


# ---------- TF26-13 ----------


@pytest.mark.parametrize("kind", EXPORTS)
def test_tf26_13_the_tries_of_a_case_are_in_the_order_they_ran(tmp_path_factory: Any, kind: str) -> None:
    """The lookup fixture ran each question twice. Whatever order the export holds them in
    (the page's download holds the latest first), try 0 of a question is the one that started
    first."""
    root, _ = world(tmp_path_factory, "old", kind, "exact")
    started: dict[str, list[tuple[str, float]]] = {}
    for call in of_evaluation(calls_of(export("old", "expanded")[0]), "old"):
        started.setdefault(call["inputs"]["example"]["id"], []).append((call["started_at"], call["output"]["model_latency"]))
    got = tries(root, RUN)
    for question, runs in started.items():
        first, second = sorted(runs)
        assert first[1] != second[1]
        assert got[(question, 0)]["wall_time_s"] == first[1] and got[(question, 1)]["wall_time_s"] == second[1], question


def test_tf26_13_rows_come_in_the_order_their_calls_started_whatever_the_file_s(tmp_path: Path) -> None:
    calls = calls_of(export("old", "pull")[0])
    random.Random(7).shuffle(calls)
    path = write_calls(tmp_path / "shuffled.jsonl", calls)
    imported(wv_argv(path, tmp_path / "a", "r"))
    imported(wv_argv(export("old", "pull"), tmp_path / "b", "r"))
    assert tries(tmp_path / "a", "r") == tries(tmp_path / "b", "r")
    # the page's download holds its rows latest first, and reads to the same tries
    page = [c["started_at"] for c in of_evaluation(calls_of(export("old", "ui-json")[0]), "old")]
    held = [c["started_at"] for c in calls_of(export("old", "ui-json")[0]) if c["parent_id"] == CALL_ID["old"]]
    assert held == page[::-1]


# ---------- TF26-14 ----------


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("kind", EXPORTS)
def test_tf26_14_the_start_is_the_first_row_s_from_every_export(tmp_path_factory: Any, name: str, kind: str) -> None:
    _, data = world(tmp_path_factory, name, kind, "exact")
    assert data["started"] == {"at": EARLIEST[name], "from": "earliest span"}


def test_tf26_14_the_first_row_s_start_is_the_file_s_own() -> None:
    for name in NAMES:
        calls = calls_of(export(name, "pull")[0])
        assert min(c["started_at"] for c in of_evaluation(calls, name)) == EARLIEST[name]
        # the evaluation's own call started earlier still, and only the service's answers hold it
        assert calls[0]["started_at"] < EARLIEST[name]


@pytest.mark.parametrize("kind", ["pull", "ui-json", "ui-csv"])
def test_tf26_14_rows_with_no_start_take_the_file_s_time(tmp_path: Path, kind: str) -> None:
    if kind == "ui-csv":
        def untimed(rows: list[dict[str, str]]) -> None:
            for row in rows:
                row["started_at"] = ""

        path = edited_table(tmp_path, kind, untimed)
    else:
        def untimed(calls: list[dict[str, Any]]) -> None:  # type: ignore[misc]
            for call in calls:
                call["started_at"] = None

        path = edited(tmp_path, "baseline", kind, untimed)
    data = imported(wv_argv(path, tmp_path / "st", "r", *picked("baseline", kind), case="example" if kind != "ui-csv" else "example:id"))
    assert data["started"]["from"] == "file time" and data["rows"] == 10


# ---------- TF26-15 ----------


@pytest.mark.parametrize("kind", ["pull", "ui-json", "ui-csv"])
def test_tf26_15_a_row_whose_call_has_not_ended_has_no_outcome(tmp_path: Path, kind: str) -> None:
    if kind == "ui-csv":
        def pend(rows: list[dict[str, str]]) -> None:
            table_rows(rows, "baseline")["c02"]["ended_at"] = ""

        path = edited_table(tmp_path, kind, pend)
    else:
        def pend(calls: list[dict[str, Any]]) -> None:  # type: ignore[misc]
            rows_by_case(calls, "baseline")["c02"]["ended_at"] = None

        path = edited(tmp_path, "baseline", kind, pend)
    data = imported(by_status(path, tmp_path / "st", "r", *picked("baseline", kind), case="example" if kind != "ui-csv" else "example:id"))
    assert data["no_outcome"] == {"pending": 1} and tally(data) == {"met": 8, "missed": 1}
    got = columns(tmp_path / "st", "r")["c02"]
    assert got["outcome"] is None and got["error"] == "pending"
    assert recs(tmp_path / "st", "r")["c02"]["outcome"] is None
