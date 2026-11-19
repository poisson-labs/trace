"""TF25-4 to TF25-15: the reader on every committed Braintrust capture: rows, cases and outcomes
(spec sections 6.3, 18.1.1 row 10, 18.3.1 and 18.3.2; TF22's FI18 and FI19; the LangSmith pair's
LS-1 to LS-5 and LS-15, in Braintrust's words).

- TF25-4: every export of all four experiments (the fetch, BTQL's spans, traces and summary
  shapes, the page's JSON and its CSV) reads as one row a trace: ten rows on ten cases for the
  slice, six rows on three cases (two tries each) for the lookup fixture; the summary names the
  tool, the files with their digests and the shape read.
- TF25-5: the case, four ways: the dataset record's id (the API's answers of the slice, the
  same ids in both versions), refused in one sentence naming another way on the page's
  downloads, which carry no id, and on the lookup fixture, whose inline data has no record; a
  metadata key, which an errored root does not hold (Braintrust saves no metadata on a case
  that errored), so that root has no case and is counted; a key of the root's input, ``input:``
  and 12 hex characters, the same key from every export and both versions, and what
  ``--verdicts`` joins by; ``none``, one case for every row, with its sentence among the counts.
- TF25-6: the outcome by the root's error: missed when the root ended in error, met otherwise,
  in every export. An error in a step does not fail a case whose root succeeded (the
  candidate's retried tool call).
- TF25-7: the outcome by a score at a cut: ``exact`` under 0.5 missed, a score equal to the cut
  meeting it, ``--above`` the other way; the score read is the row's score; another key reads
  the same way.
- TF25-8: the outcome by a metadata key: missed when its value is one of ``--failed``, or its
  number at ``--cut``; a root without the key (an errored one) has no outcome.
- TF25-9: a root with no score for the key has no outcome and the reason ``no score``; it is
  censored when the root ended in error (every errored case: it has no score span) and unscored
  when it did not; a score on the root itself is read, and a key two spans hold reads as their
  mean; a file where no root has the score writes nothing.
- TF25-10: the paged answers read as the whole answer does, pages in any order, the empty last
  page among them; the containers (``events``, ``data``, a list, JSON Lines) read alike; one
  file may mix the span and summary shapes row by row.
- TF25-11: ``--select metadata:KEY=VALUE`` keeps the traces whose root holds every selection;
  the counts say how many were read and kept; an errored root holds no metadata and is not
  selected; a selection that keeps nothing writes nothing.
- TF25-12: a trace whose root is not in the files is left out and counted; an event in two
  files given is refused naming it, and nothing is written; the page's download beside the
  API's answers is refused, and so are two of the page's downloads. A span's parent is the
  first of ``span_parents`` (a second level under the task is built here from the captures).
- TF25-13: rows come in the order their roots started, whatever order the file holds them, so
  the tries of a case are its repeats in the order they ran.
- TF25-14: the start is the earliest span's start, from every export (the page's rows carry
  their root's start too); rows with no start take the file's time.
- TF25-15: a root that has not ended has no outcome under ``error`` and the reason ``pending``.
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
from tf25_support import (
    CASES, EARLIEST, ERRORED, EVENTS, EXACT, EXPERIMENTS, EXPORTS, ITEM, KEY, LOOKUP, LOOKUP_EXACT, PAGED, QUESTIONS,
    RUN, SHAPE, SPAN_EXPORTS, VERSIONS, approx, bt_argv, by_error, columns, edited, experiment, export,
    imported, is_root, outcomes, passed, recs, refused, roots, rows_of, span_type, tally, trace_rows, tries, work_spans,
    world,
)

BOTH = [(v, k) for v in VERSIONS for k in EXPORTS]
BOTH_SPANS = [(v, k) for v in VERSIONS for k in SPAN_EXPORTS]
WITH_RECORD = (*SPAN_EXPORTS, "summary")
PAGE = ("ui-json", "ui-csv")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _by_error(version: str) -> dict[str, str]:
    return {case: "missed" if case == ERRORED[version][0] else "met" for case in CASES}


# ---------- TF25-4 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf25_4_every_export_of_the_slice_reads_as_ten_rows_on_the_ten_cases(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, data = world(tmp_path_factory, version, kind, "error")
    assert data["tool"] == "braintrust" and data["run"] == RUN
    assert data["rows"] == 10 and data["cases"] == 10 and data["repeats"] == {"min": 1, "max": 1}
    files = export(version, kind)
    assert [f["name"] for f in data["files"]] == [p.name for p in files]
    assert [f["sha256"] for f in data["files"]] == [_sha(p) for p in files]
    assert data["declared"]["shapes"] == [SHAPE[kind]]
    assert sorted(recs(root, RUN)) == list(CASES)
    assert data["counts"]["traces"] == 10
    if kind in SPAN_EXPORTS:
        assert data["counts"]["events"] == EVENTS[experiment(version)] and data["counts"]["no root span"] == 0
    else:
        assert "events" not in data["counts"] and "no root span" not in data["counts"]


@pytest.mark.parametrize("name", LOOKUP)
@pytest.mark.parametrize("kind", EXPORTS)
def test_tf25_4_every_export_of_the_lookup_fixture_reads_as_two_tries_of_three_cases(tmp_path_factory: Any, name: str, kind: str) -> None:
    root, data = world(tmp_path_factory, name, kind, "exact")
    assert data["rows"] == 6 and data["cases"] == 3 and data["repeats"] == {"min": 2, "max": 2}
    failed = sum(2 for q in QUESTIONS if LOOKUP_EXACT[name][q] < 0.5)
    assert tally(data) == ({"met": 6 - failed, "missed": failed} if failed else {"met": 6})
    got = tries(root, RUN)
    assert sorted(got) == [(q, n) for q in QUESTIONS for n in (0, 1)]
    assert {key: rec["score"] for key, rec in got.items()} == {(q, n): LOOKUP_EXACT[name][q] for q in QUESTIONS for n in (0, 1)}


# ---------- TF25-5 ----------


@pytest.mark.parametrize(("version", "kind"), [(v, k) for v in VERSIONS for k in WITH_RECORD])
def test_tf25_5_the_record_s_id_is_the_case_where_the_export_carries_it(tmp_path: Path, version: str, kind: str) -> None:
    data = imported(by_error(export(version, kind), tmp_path / "st", "r", case="record"))
    assert data["declared"]["case_from"] == "record"
    assert outcomes(tmp_path / "st", "r") == _by_error(version)
    # the record's own id is the case: nothing of the input is in it
    from tf21_support import records

    assert sorted(r["case"] for r in records(tmp_path / "st", "r")) == list(CASES)


@pytest.mark.parametrize("kind", PAGE)
def test_tf25_5_record_is_refused_on_the_page_s_download_naming_another_way(tmp_path: Path, kind: str) -> None:
    line = refused(run_import(by_error(export("baseline", kind), tmp_path / "st", "r", case="record")))
    assert "record" in line and "--case-from input" in line, line
    assert re.search(r"\bpage\b|\bdownload\b", line), line
    assert not (tmp_path / "st").exists()
    imported(by_error(export("baseline", kind), tmp_path / "st", "r", case="input"))


@pytest.mark.parametrize("kind", WITH_RECORD)
def test_tf25_5_record_is_refused_where_no_root_carries_one(tmp_path: Path, kind: str) -> None:
    """The lookup fixture's data is inline: its roots' ``origin`` is null."""
    line = refused(run_import(bt_argv(export("old", kind), tmp_path / "st", "r", case="record")))
    assert "record" in line and "--case-from input" in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("kind", ["fetch", "summary"])
def test_tf25_5_a_root_without_a_record_among_roots_that_have_one_has_no_case(tmp_path: Path, kind: str) -> None:
    def drop(rows: list[dict[str, Any]]) -> None:
        held = roots(rows)
        held["c02"]["origin"] = None  # type: ignore[index]
        held["c07"]["origin"] = {"id": None}  # type: ignore[index]

    path = edited(tmp_path, "baseline", kind, drop)
    data = imported(by_error(path, tmp_path / "st", "r", case="record"))
    assert data["rows"] == 8 and data["counts"]["no case"] == 2
    assert sorted(outcomes(tmp_path / "st", "r")) == [c for c in CASES if c not in ("c02", "c07")]


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf25_5_a_metadata_key_is_the_case_and_an_errored_root_holds_none(tmp_path: Path, version: str, kind: str) -> None:
    """Braintrust saves no metadata on a case that errored, in any export, so that root has no
    case by a metadata key: nine rows, and the tenth counted."""
    data = imported(by_error(export(version, kind), tmp_path / "st", "r", case="metadata:case"))
    bad = ERRORED[version][0]
    assert data["rows"] == 9 and data["counts"]["no case"] == 1
    assert outcomes(tmp_path / "st", "r") == {case: "met" for case in CASES if case != bad}


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf25_5_input_is_a_key_of_the_root_s_input_and_never_its_text(tmp_path_factory: Any, version: str, kind: str) -> None:
    # the import the shared store was made by: by the root's error, the case the input's key
    root, data = world(tmp_path_factory, version, kind, "error")
    from tf21_support import records

    assert data["declared"]["case_from"] == "input"
    got = sorted(r["case"] for r in records(root, RUN))
    assert got == sorted(KEY[case] for case in CASES)
    assert all(re.fullmatch(r"input:[0-9a-f]{12}", case) for case in got)
    assert tally(data) == {"met": 9, "missed": 1} and outcomes(root, RUN)[ERRORED[version][0]] == "missed"
    held = b"".join(p.read_bytes() for p in root.rglob("*") if p.is_file())
    for item in ITEM.values():
        assert item.encode() not in held, item


@pytest.mark.parametrize("kind", ["fetch", "summary", "ui-json", "ui-csv"])
def test_tf25_5_input_is_refused_when_no_root_holds_an_input(tmp_path: Path, kind: str) -> None:
    def drop(rows: list[dict[str, Any]]) -> None:
        for r in rows:
            r["input"] = None

    path = edited(tmp_path, "baseline", kind, drop)
    line = refused(run_import(by_error(path, tmp_path / "st", "r", case="input")))
    assert "input" in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("kind", ["fetch", "summary", "ui-json", "ui-csv"])
def test_tf25_5_a_verdicts_file_joins_by_input(tmp_path: Path, kind: str) -> None:
    """The reader hands the import each case's input key, so a verdict that names an input and
    no case joins the row of that input (FI19). Here it agrees with what the file recorded."""
    verdicts = tmp_path / "v.jsonl"
    verdicts.write_text(json.dumps({"input": {"case": "c10", "item": ITEM["c10"]}, "outcome": "fail"}) + "\n", encoding="utf-8")
    data = imported(bt_argv(export("baseline", kind), tmp_path / "st", "r", "--verdicts", verdicts, case="record" if kind in WITH_RECORD else "input"))
    assert data["verdicts"]["by_input"] == 1 and data["verdicts"]["by_case"] == 0 and data["verdicts"]["unmatched"] == 0, data["verdicts"]
    assert outcomes(tmp_path / "st", "r")["c10"] == "missed"


@pytest.mark.parametrize("kind", ["fetch", "summary", "ui-csv"])
def test_tf25_5_none_reads_every_row_as_one_input_and_says_so(tmp_path: Path, kind: str) -> None:
    data = imported(by_error(export("candidate", kind), tmp_path / "st", "r", case="none"))
    assert data["cases"] == 1 and data["rows"] == 10 and data["repeats"] == {"min": 10, "max": 10}
    said = [label for label in data["counts"] if "mix of inputs" in label]
    assert len(said) == 1 and data["counts"][said[0]] == 10, data["counts"]
    other = imported(by_error(export("candidate", kind), tmp_path / "st2", "r"))
    assert not [label for label in other["counts"] if "mix of inputs" in label]


# ---------- TF25-6 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf25_6_by_error_the_errored_root_is_the_one_missed(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, data = world(tmp_path_factory, version, kind, "error")
    bad = ERRORED[version][0]
    assert outcomes(root, RUN) == _by_error(version)
    assert tally(data) == {"met": 9, "missed": 1} and data["no_outcome"] == {}
    assert data["declared"]["outcome_from"] == "error" and "cut" not in data["declared"]
    stored = recs(root, RUN)
    assert {case: r["outcome"] for case, r in stored.items()} == {case: "fail" if case == bad else "pass" for case in CASES}
    # a row with an outcome carries no error word (Prove refuses a row with both)
    assert all(r["error"] is None for r in columns(root, RUN).values())
    # a step that failed and was retried did not fail the case
    if version == "candidate":
        assert stored["c04"]["outcome"] == "pass" and stored["c04"]["failure_kind"] is None


# ---------- TF25-7 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf25_7_by_a_score_at_a_cut(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, data = world(tmp_path_factory, version, kind, "exact")
    want = {case: None if ok is None else ("met" if ok else "missed") for case, ok in passed(version).items()}
    assert outcomes(root, RUN) == want
    assert data["declared"]["outcome_from"] == "score:exact"
    assert data["declared"]["cut"] == 0.5 and data["declared"]["side"] == "below"
    assert tally(data) == {"baseline": {"met": 6, "missed": 3}, "candidate": {"met": 8, "missed": 1}}[version]
    assert data["no_outcome"] == {"no score": 1}
    stored = recs(root, RUN)
    assert {case: r["score"] for case, r in stored.items()} == EXACT[version]


@pytest.mark.parametrize(("extra", "missed"), [
    (("--cut", "1", "--below"), 3), (("--cut", "0", "--below"), 0), (("--cut", "0", "--above"), 6), (("--cut", "1", "--above"), 0),
])
@pytest.mark.parametrize("kind", ["fetch", "ui-json"])
def test_tf25_7_a_score_equal_to_the_cut_meets_it_on_either_side(tmp_path: Path, kind: str, extra: tuple[str, ...], missed: int) -> None:
    data = imported(bt_argv(export("baseline", kind), tmp_path / "st", "r", *extra, cut=None))
    assert data["outcomes"].get("missed", 0) == missed and data["outcomes"].get("met", 0) == 9 - missed
    assert data["no_outcome"] == {"no score": 1}


@pytest.mark.parametrize("kind", ["fetch", "summary", "ui-csv"])
def test_tf25_7_another_key_is_read_the_same_way(tmp_path: Path, kind: str) -> None:
    data = imported(bt_argv(export("baseline", kind), tmp_path / "st", "r", outcome="score:gave_answer"))
    assert tally(data) == {"met": 8, "missed": 1} and data["no_outcome"] == {"no score": 1}
    assert outcomes(tmp_path / "st", "r")["c10"] == "missed"


# ---------- TF25-8 ----------


@pytest.mark.parametrize("kind", ["fetch", "summary", "ui-json", "ui-csv"])
def test_tf25_8_by_a_metadata_value_named_as_failed(tmp_path: Path, kind: str) -> None:
    """Every root but the errored one carries ``version`` in its metadata: naming one value
    failed reads those rows of that version as missed, and of the other as met. The errored
    root holds no metadata, so it has no outcome and says so."""
    for version, want in (("baseline", "missed"), ("candidate", "met")):
        argv = bt_argv(export(version, kind), tmp_path / version, "r", "--failed", "baseline", "--failed", "other",
                       outcome="metadata:version", cut=None)
        data = imported(argv)
        assert tally(data) == {want: 9} and data["no_outcome"] == {"no outcome recorded": 1}
        assert data["declared"]["failed"] == ["baseline", "other"]
        bad = columns(tmp_path / version, "r")[ERRORED[version][0]]
        assert bad["outcome"] is None and bad["error"] == "no outcome recorded"


@pytest.mark.parametrize("kind", ["fetch", "summary", "ui-csv"])
def test_tf25_8_by_a_metadata_number_at_a_cut(tmp_path: Path, kind: str) -> None:
    def grade(rows: list[dict[str, Any]]) -> None:
        for case, root in roots(rows).items():
            root["metadata"] = {**(root["metadata"] or {}), "grade": 0.25 if case in ("c02", "c05") else 0.75}  # type: ignore[index]

    path = edited(tmp_path, "baseline", kind, grade)
    data = imported(bt_argv(path, tmp_path / "st", "r", outcome="metadata:grade"))
    assert tally(data) == {"met": 8, "missed": 2} and data["no_outcome"] == {}
    assert {c: r["score"] for c, r in recs(tmp_path / "st", "r").items()} == {c: 0.25 if c in ("c02", "c05") else 0.75 for c in CASES}


def test_tf25_8_a_metadata_value_that_is_no_number_is_refused_at_a_cut(tmp_path: Path) -> None:
    line = refused(run_import(bt_argv(export("baseline", "fetch"), tmp_path / "st", "r", outcome="metadata:version")))
    assert "metadata:version" in line and "number" in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF25-9 ----------


@pytest.mark.parametrize(("version", "kind"), BOTH)
def test_tf25_9_an_errored_case_has_no_score_and_is_censored(tmp_path_factory: Any, version: str, kind: str) -> None:
    root, data = world(tmp_path_factory, version, kind, "exact")
    bad = ERRORED[version][0]
    got, stored = columns(root, RUN)[bad], recs(root, RUN)[bad]
    assert got["outcome"] is None and got["error"] == "no score", got
    assert stored["outcome"] == "censored" and stored["score"] is None and stored["scores"] == {}
    assert stored["failure_kind"] is not None


@pytest.mark.parametrize("kind", ["fetch", "summary", "ui-json", "ui-csv"])
def test_tf25_9_a_root_that_did_not_error_and_has_no_score_is_unscored(tmp_path: Path, kind: str) -> None:
    def unscore(rows: list[dict[str, Any]]) -> None:
        if kind == "fetch":
            gone = [r for r in trace_rows(rows, "c10")[1:] if span_type(r) == "score" and "exact" in (r["scores"] or {})]
            assert len(gone) == 1
            rows.remove(gone[0])
        else:
            del roots(rows)["c10"]["scores"]["exact"]  # type: ignore[attr-defined]

    path = edited(tmp_path, "baseline", kind, unscore)
    data = imported(bt_argv(path, tmp_path / "st", "r"))
    assert tally(data) == {"met": 6, "missed": 2} and data["no_outcome"] == {"no score": 2}
    stored = recs(tmp_path / "st", "r")
    assert stored["c10"]["outcome"] is None and stored["c10"]["failure_kind"] is None and "exact" not in stored["c10"]["scores"]
    assert stored["c10"]["scores"] == {"gave_answer": 0.0}
    assert stored["c08"]["outcome"] == "censored"
    # a verdicts file fills the unscored row, and cannot overturn the censored one (TF22)
    verdicts = tmp_path / "v.csv"
    verdicts.write_text(f"case,outcome\n{KEY['c10']},fail\n", encoding="utf-8")
    filled = imported(bt_argv(path, tmp_path / "st", "r2", "--verdicts", verdicts))
    assert filled["verdicts"]["by_case"] == 1 and tally(filled) == {"met": 6, "missed": 3}
    verdicts.write_text(f"case,outcome\n{KEY['c08']},fail\n", encoding="utf-8")
    line = refused(run_import(bt_argv(path, tmp_path / "st", "r3", "--verdicts", verdicts)))
    assert "censored" in line, line


def test_tf25_9_a_score_on_the_root_is_read_and_two_spans_of_one_key_read_as_their_mean(tmp_path: Path) -> None:
    def edit(rows: list[dict[str, Any]]) -> None:
        # c01: the score logged on the root itself, and no score span
        root, *under = trace_rows(rows, "c01")
        for r in under:
            if span_type(r) == "score":
                rows.remove(r)
        root["scores"] = {"exact": 0}
        # c02: a second span holding exact, at 0: the mean of 1 and 0
        twin = json.loads(json.dumps(next(r for r in trace_rows(rows, "c02")[1:] if (r["scores"] or {}).get("exact") is not None)))
        twin["id"], twin["span_id"], twin["scores"] = twin["id"][:-4] + "ffff", twin["span_id"][:-4] + "ffff", {"exact": 0}
        rows.append(twin)

    path = edited(tmp_path, "baseline", "fetch", edit)
    data = imported(bt_argv(path, tmp_path / "st", "r", "--cut", "0.5", "--below", cut=None))
    stored = recs(tmp_path / "st", "r")
    assert stored["c01"]["score"] == 0.0 and stored["c01"]["outcome"] == "fail" and stored["c01"]["scores"] == {"exact": 0.0}
    assert stored["c02"]["score"] == 0.5 and stored["c02"]["outcome"] == "pass"
    assert tally(data) == {"met": 5, "missed": 4}


@pytest.mark.parametrize("kind", ["fetch", "summary", "ui-json"])
def test_tf25_9_a_file_where_no_root_has_the_score_writes_nothing(tmp_path: Path, kind: str) -> None:
    line = refused(run_import(bt_argv(export("baseline", kind), tmp_path / "st", "r", outcome="score:no_such_key")))
    assert "outcome" in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF25-10 ----------


@pytest.mark.parametrize("kind", PAGED)
@pytest.mark.parametrize("order", ["as pulled", "reversed", "without the empty page"])
def test_tf25_10_the_pages_read_as_the_whole_answer(tmp_path: Path, kind: str, order: str) -> None:
    pages = export("candidate", kind)
    if order == "reversed":
        pages = pages[::-1]
    if order == "without the empty page":
        pages = pages[:4]
    data = imported(bt_argv(pages, tmp_path / "paged", "r"))
    whole = imported(bt_argv(export("candidate", "fetch"), tmp_path / "whole", "r"))
    assert data["rows"] == 10 and data["counts"]["events"] == 88
    assert recs(tmp_path / "paged", "r") == recs(tmp_path / "whole", "r")
    for key in ("outcomes", "no_outcome", "counts", "started", "declared"):
        assert data[key] == whole[key], key
    assert len(data["files"]) == len(pages)


def test_tf25_10_the_containers_read_alike(tmp_path: Path) -> None:
    rows = rows_of(export("candidate", "fetch")[0])
    forms = {
        "events.json": json.dumps({"events": rows, "cursor": "x"}),
        "data.json": json.dumps({"data": rows, "schema": {}, "cursor": None}),
        "list.json": json.dumps(rows),
        "lines.jsonl": "".join(json.dumps(r) + "\n" for r in rows),
        "blank-lines.jsonl": "\n".join(json.dumps(r) + "\n" for r in rows),
    }
    seen = []
    for name, text in forms.items():
        folder = tmp_path / name.split(".")[0]
        folder.mkdir()
        (folder / name).write_text(text, encoding="utf-8")
        imported(bt_argv(folder / name, folder / "st", "r"))
        seen.append(recs(folder / "st", "r"))
    assert all(s == seen[0] for s in seen[1:])


def test_tf25_10_one_file_may_mix_the_span_and_summary_shapes_row_by_row(tmp_path: Path) -> None:
    """Half the traces as the fetch returns them, half as the summary query does, shuffled into
    one JSON Lines file: each row is read by its own keys."""
    spans, summary = rows_of(export("candidate", "fetch")[0]), roots(rows_of(export("candidate", "summary")[0]))
    mixed: list[Any] = []
    for i, case in enumerate(CASES):
        mixed += trace_rows(spans, case) if i % 2 == 0 else [summary[case]]
    random.Random(25).shuffle(mixed)
    path = tmp_path / "mixed.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in mixed), encoding="utf-8")
    data = imported(by_error(path, tmp_path / "st", "r"))
    assert data["rows"] == 10 and sorted(data["declared"]["shapes"]) == ["span", "summary"]
    assert outcomes(tmp_path / "st", "r") == _by_error("candidate")


# ---------- TF25-11 ----------


def _both_versions(tmp_path: Path, kind: str = "fetch") -> Path:
    rows = rows_of(export("baseline", kind)[0]) + rows_of(export("candidate", kind)[0])
    path = tmp_path / "both.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


@pytest.mark.parametrize("kind", ["fetch", "summary"])
def test_tf25_11_select_takes_one_version_out_of_a_file_that_holds_both(tmp_path: Path, kind: str) -> None:
    path = _both_versions(tmp_path, kind)
    for version in VERSIONS:
        data = imported(by_error(path, tmp_path / "st", version, "--select", f"metadata:version={version}", case="record"))
        # an errored root holds no metadata, so no selection by metadata keeps it
        assert data["rows"] == 9 and data["counts"]["traces"] == 20 and data["counts"]["selected"] == 9
        assert data["declared"]["select"] == [f"metadata:version={version}"]
        assert outcomes(tmp_path / "st", version) == {case: "met" for case in CASES if case != ERRORED[version][0]}


def test_tf25_11_every_selection_must_hold_on_the_root(tmp_path: Path) -> None:
    path = _both_versions(tmp_path)
    data = imported(by_error(path, tmp_path / "st", "one", "--select", "metadata:version=candidate", "--select", "metadata:case=c03"))
    assert data["rows"] == 1 and data["counts"]["selected"] == 1
    # the key is read on the root: the llm spans' model selects nothing
    line = refused(run_import(by_error(path, tmp_path / "st", "none", "--select", "metadata:model=gpt-4.1-mini")))
    assert "no row" in line or "select" in line, line
    assert not (tmp_path / "st" / "none").exists()


@pytest.mark.parametrize("kind", PAGE)
def test_tf25_11_select_reads_the_page_s_rows_too(tmp_path: Path, kind: str) -> None:
    data = imported(by_error(export("candidate", kind), tmp_path / "st", "r", "--select", "metadata:case=c06"))
    assert data["rows"] == 1 and data["counts"]["selected"] == 1 and tally(data) == {"met": 1}


# ---------- TF25-12 ----------


@pytest.mark.parametrize("kind", SPAN_EXPORTS)
def test_tf25_12_a_trace_with_no_root_is_left_out_and_counted(tmp_path: Path, kind: str) -> None:
    def drop(rows: list[dict[str, Any]]) -> None:
        held = roots(rows)
        for case in ("c03", "c08"):
            rows.remove(held[case])  # type: ignore[arg-type]

    path = edited(tmp_path, "baseline", kind, drop)
    data = imported(by_error(path, tmp_path / "st", "r"))
    assert data["rows"] == 8 and data["counts"]["no root span"] == 2 and data["counts"]["traces"] == 10
    assert sorted(outcomes(tmp_path / "st", "r")) == [c for c in CASES if c not in ("c03", "c08")]
    assert tally(data) == {"met": 8}


@pytest.mark.parametrize(("a", "b"), [("fetch", "btql-spans"), ("btql-spans", "btql-traces"), ("fetch", "summary"), ("summary", "btql-traces")])
def test_tf25_12_an_event_in_two_of_the_files_is_refused(tmp_path: Path, a: str, b: str) -> None:
    files = [*export("baseline", a), *export("baseline", b)]
    line = refused(run_import(by_error(files, tmp_path / "st", "r")))
    ids = {r["id"] for r in rows_of(export("baseline", a)[0])}
    assert any(i in line for i in ids), line
    assert files[0].name in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("page", PAGE)
@pytest.mark.parametrize("other", ["fetch", "summary"])
def test_tf25_12_the_page_s_download_and_the_api_s_answers_are_not_one_import(tmp_path: Path, page: str, other: str) -> None:
    files = [*export("baseline", page), *export("baseline", other)]
    line = refused(run_import(by_error(files, tmp_path / "st", "r")))
    assert "page" in line and "twice" in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize(("a", "b"), [(("baseline", "ui-json"), ("baseline", "ui-csv")), (("baseline", "ui-json"), ("candidate", "ui-json"))])
def test_tf25_12_two_of_the_page_s_downloads_are_refused(tmp_path: Path, a: tuple[str, str], b: tuple[str, str]) -> None:
    """The page's download carries no id, so the same experiment given twice (its JSON and its
    CSV) cannot be told from two experiments: one import reads one of them."""
    files = [*export(*a), *export(*b)]
    line = refused(run_import(by_error(files, tmp_path / "st", "r")))
    assert files[0].name in line and files[1].name in line and "one file" in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("kind", SPAN_EXPORTS)
def test_tf25_12_a_span_s_parent_is_the_first_of_its_parents(tmp_path: Path, kind: str) -> None:
    """The candidate's c03 with its last step (``parse_answer``) moved under its model call:
    the model call then wraps a step and is no step itself, the step's span hangs under it, and
    it is still one model call."""
    def nest(rows: list[dict[str, Any]]) -> None:
        steps = work_spans(rows, "c03")
        llm = next(r for r in steps if span_type(r) == "llm")
        # two parents named, the model call first: the captures name one each, so which of
        # several is the parent is frozen here
        steps[-1]["span_parents"] = [llm["span_id"], steps[-1]["span_parents"][0]]

    path = edited(tmp_path, "candidate", kind, nest)
    imported(by_error(path, tmp_path / "st", "r"))
    rec = recs(tmp_path / "st", "r")
    assert rec["c03"]["steps"] == 3 and rec["c03"]["llm_calls"] == 1 and rec["c03"]["total_tokens"] == 93
    assert rec["c02"]["steps"] == 4
    row = columns(tmp_path / "st", "r")["c03"]
    spans = (row["trace"] if isinstance(row["trace"], dict) else json.loads(row["trace"]))["spans"]
    rows = rows_of(export("candidate", kind)[0])
    steps = work_spans(rows, "c03")
    llm = next(r["span_id"] for r in steps if span_type(r) == "llm")
    by_id = {span["span_id"]: span for span in spans}
    assert by_id[steps[-1]["span_id"]]["parent_id"] == llm
    task = next(r["span_id"] for r in trace_rows(rows, "c03")[1:] if span_type(r) == "task")
    assert by_id[llm]["parent_id"] == task and by_id[task]["parent_id"] == trace_rows(rows, "c03")[0]["span_id"]
    assert row["t"] == 3.0


# ---------- TF25-13 ----------


@pytest.mark.parametrize("kind", EXPORTS)
def test_tf25_13_the_tries_of_a_case_are_in_the_order_they_ran(tmp_path_factory: Any, kind: str) -> None:
    """The lookup fixture ran each question twice. Whatever order the export holds them in
    (the fetch holds the latest first), try 0 of a question is the one that started first."""
    root, _ = world(tmp_path_factory, "old", kind, "exact")
    spans = rows_of(export("old", "fetch")[0])
    started: dict[str, list[tuple[float, float]]] = {}
    for r in spans:
        if is_root(r):
            started.setdefault(r["input"], []).append((r["metrics"]["start"], r["metrics"]["end"] - r["metrics"]["start"]))
    got = tries(root, RUN)
    for question, runs in started.items():
        first, second = sorted(runs)
        assert first[1] != second[1]
        assert approx(got[(question, 0)]["wall_time_s"], first[1], 2e-6) and approx(got[(question, 1)]["wall_time_s"], second[1], 2e-6), question


def test_tf25_13_rows_come_in_the_order_their_roots_started_whatever_the_file_s(tmp_path: Path) -> None:
    rows = rows_of(export("old", "fetch")[0])
    random.Random(7).shuffle(rows)
    path = tmp_path / "shuffled.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    imported(bt_argv(path, tmp_path / "a", "r"))
    imported(bt_argv(export("old", "fetch"), tmp_path / "b", "r"))
    assert tries(tmp_path / "a", "r") == tries(tmp_path / "b", "r")


# ---------- TF25-14 ----------


@pytest.mark.parametrize("name", EXPERIMENTS)
@pytest.mark.parametrize("kind", EXPORTS)
def test_tf25_14_the_start_is_the_earliest_span_s(tmp_path_factory: Any, name: str, kind: str) -> None:
    _, data = world(tmp_path_factory, name, kind, "exact")
    assert data["started"] == {"at": EARLIEST[name], "from": "earliest span"}


def test_tf25_14_the_earliest_start_is_the_file_s_own() -> None:
    from datetime import UTC, datetime

    for name in EXPERIMENTS:
        first = min(r["metrics"]["start"] for r in rows_of(export(name, "fetch")[0]))
        at = datetime.fromtimestamp(int(first), UTC).strftime("%Y-%m-%dT%H:%M:%S")
        assert EARLIEST[name].startswith(at) and EARLIEST[name].endswith("Z"), name
        assert abs(float("0" + EARLIEST[name][19:-1]) - (first - int(first))) < 1e-6, name


@pytest.mark.parametrize("kind", SPAN_EXPORTS)
def test_tf25_14_the_earliest_span_need_not_be_the_first_root_s(tmp_path: Path, kind: str) -> None:
    """A step of the trace that started last, stamped ten seconds before anything else: the
    start is that span's, and no root's."""
    def early(rows: list[dict[str, Any]]) -> None:
        last = max((r for r in rows if is_root(r)), key=lambda r: r["metrics"]["start"])
        step = work_spans(rows, last["input"]["case"])[0]
        step["metrics"]["start"] = 1794255845.25

    path = edited(tmp_path, "baseline", kind, early)
    data = imported(by_error(path, tmp_path / "st", "r"))
    assert data["started"] == {"at": "2026-11-09T20:24:05.250000Z", "from": "earliest span"}


@pytest.mark.parametrize("kind", ["summary", "ui-json"])
def test_tf25_14_rows_with_no_start_take_the_file_s_time(tmp_path: Path, kind: str) -> None:
    def untimed(rows: list[dict[str, Any]]) -> None:
        for r in rows:
            r["metrics"] = {k: v for k, v in r["metrics"].items() if k not in ("start", "end")}

    path = edited(tmp_path, "baseline", kind, untimed)
    data = imported(bt_argv(path, tmp_path / "st", "r"))
    assert data["started"]["from"] == "file time"
    assert all(r["wall_time_s"] is None for r in recs(tmp_path / "st", "r").values())


# ---------- TF25-15 ----------


@pytest.mark.parametrize("kind", ["fetch", "summary", "ui-json"])
def test_tf25_15_a_root_that_has_not_ended_has_no_outcome(tmp_path: Path, kind: str) -> None:
    def pend(rows: list[dict[str, Any]]) -> None:
        root = roots(rows)["c02"]
        root["metrics"] = {k: v for k, v in root["metrics"].items() if k not in ("end", "duration")}  # type: ignore[index]

    path = edited(tmp_path, "baseline", kind, pend)
    data = imported(by_error(path, tmp_path / "st", "r"))
    assert data["no_outcome"] == {"pending": 1} and tally(data) == {"met": 8, "missed": 1}
    got = columns(tmp_path / "st", "r")["c02"]
    assert got["outcome"] is None and got["error"] == "pending"
    rec = recs(tmp_path / "st", "r")["c02"]
    assert rec["outcome"] is None and rec["wall_time_s"] is None
