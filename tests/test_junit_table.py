"""TF3-8 to TF3-14: the ``table`` reader.

- TF3-8: ``.csv``, ``.jsonl``, ``.json`` (a list of objects), each also ``.gz``, and ``.parquet``,
  told by the extension; the same table in each gives the same run. Any other name is refused.
- TF3-9: by outcome, a cell equal to a ``--failed`` value is ``missed``, any other non-empty cell
  ``met``, an empty cell a row with no outcome. Equal means the same text as written; a JSON or
  Parquet true, false or whole number is compared as JSON spells it.
- TF3-10: by score, the Ragas rule: a score equal to the cut met it on either side, and a cell that
  holds no number is a row with no outcome.
- TF3-11: the command line: ``--case-column`` and exactly one of the two forms, each with its own
  flags; a form's flags given with the other, or without their column, are a wrong command line
  (exit 2); the side, the cut's number and the two columns being one are refusals (exit 1), as the
  Ragas reader's.
- TF3-12: the Ragas reader's refusals: a named column absent lists the file's columns, a column
  named twice, an empty case cell names its row, text that is not UTF-8, a broken CSV line, a JSON
  Lines line that is not an object, a JSON file that is not a list of objects, a damaged ``.gz``, no
  row. Nothing is written by any.
- TF3-13: the case is the cell's text as written; rows sharing a case are repeats in the order read,
  across the files of one import; no value of any other column is kept, and of the outcome column
  only met or missed.
- TF3-14: the summary: ``poisson-trace.import/1``, tool ``table``, each file's sha256, the columns
  and the failure values or the cut declared, the start from the first file's time or
  ``--started``; the store is Prove's, ``backend`` ``import:table``, ``--event missed`` its event.
"""

from __future__ import annotations

import gzip
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from poisson_prove.store import Store

from look_support import chdir, trace
from setup_support import scratch_home, work  # noqa: F401
from junit_table_support import (
    by_case, holds, imported, no_outcome_total, outcome_rows, read_rows, refusal, scalars, sha256, table_argv,
    usage_error, verb, write_table,
)

ROWS = outcome_rows([("a", "fail"), ("a", "ok"), ("b", "fail"), ("c", None), ("c", "ok"), ("d", "error")])
WANT = {"a": ["missed", "met"], "b": ["missed"], "c": [None, "met"], "d": ["missed"]}
FORMATS = ["t.csv", "t.jsonl", "t.json", "t.csv.gz", "t.jsonl.gz", "t.json.gz", "t.parquet"]


def _import(tmp_path: Path, argv: list[str]) -> dict:
    with chdir(tmp_path):
        return imported(verb([*argv, "--json"]))


# ---------- TF3-8: formats ----------


@pytest.mark.parametrize("name", FORMATS)
def test_tf3_08_every_format_gives_the_same_run(tmp_path: Path, name: str) -> None:
    write_table(tmp_path / name, ROWS)
    doc = _import(tmp_path, table_argv(name, "st", "r", failed=("fail", "error")))
    assert by_case(read_rows(tmp_path / "st", "r")) == WANT
    assert doc["rows"] == 6 and doc["cases"] == 4 and doc["outcomes"] == {"met": 2, "missed": 3}
    assert no_outcome_total(doc) == 1


@pytest.mark.parametrize("name", ["t.txt", "t.tsv", "t.parquet.gz", "t.xlsx", "t", "t.csv.bz2"])
def test_tf3_08_a_name_the_reader_does_not_take_is_refused(tmp_path: Path, name: str) -> None:
    (tmp_path / name).write_bytes(b"case,outcome\na,fail\n")
    with chdir(tmp_path):
        line = refusal(verb(table_argv(name, "st", "r")))
    assert name in line
    assert not (tmp_path / "st").exists()


def test_tf3_08_the_extension_tells_the_format_not_the_bytes(tmp_path: Path) -> None:
    """A CSV named ``.json`` is not read as CSV, and JSON Lines named ``.csv`` is not read as
    JSON: each is refused as what its name says it is."""
    (tmp_path / "csv.json").write_bytes(b"case,outcome\na,fail\n")
    write_table(tmp_path / "rows.jsonl", ROWS)
    (tmp_path / "lines.csv").write_bytes((tmp_path / "rows.jsonl").read_bytes())
    with chdir(tmp_path):
        refusal(verb(table_argv("csv.json", "st", "r")))
        refusal(verb(table_argv("lines.csv", "st", "r")))
    assert not (tmp_path / "st").exists()


# ---------- TF3-9: by outcome ----------


def test_tf3_09_each_failure_value_is_missed_and_every_other_value_met(tmp_path: Path) -> None:
    rows = outcome_rows([("a", "crashed"), ("a", "failed_assertion"), ("a", "passed"), ("b", "timeout"), ("b", "passed")])
    write_table(tmp_path / "t.csv", rows)
    _import(tmp_path, table_argv("t.csv", "st", "r", failed=("crashed", "failed_assertion")))
    assert by_case(read_rows(tmp_path / "st", "r")) == {"a": ["missed", "missed", "met"], "b": ["met", "met"]}


@pytest.mark.parametrize("name", ["t.csv", "t.jsonl", "t.parquet"])
def test_tf3_09_an_empty_cell_has_no_outcome(tmp_path: Path, name: str) -> None:
    rows = [{"case": "a", "outcome": "fail"}, {"case": "a", "outcome": None}, {"case": "b", "outcome": ""}, {"case": "b", "outcome": "ok"}]
    if name.endswith(".jsonl"):
        rows.append({"case": "c"})  # the key left out of the row
        rows.append({"case": "c", "outcome": "ok"})
    write_table(tmp_path / name, rows)
    doc = _import(tmp_path, table_argv(name, "st", "r", failed=("fail",)))
    got = by_case(read_rows(tmp_path / "st", "r"))
    assert got["a"] == ["missed", None] and got["b"] == [None, "met"], got
    assert no_outcome_total(doc) == (3 if name.endswith(".jsonl") else 2)


def test_tf3_09_a_value_is_the_text_as_written(tmp_path: Path) -> None:
    """Case and spaces count: ``FAIL`` and `` fail`` are not ``fail``."""
    write_table(tmp_path / "t.csv", outcome_rows([("a", "fail"), ("b", "FAIL"), ("c", " fail"), ("d", "fail ")]))
    _import(tmp_path, table_argv("t.csv", "st", "r", failed=("fail",)))
    assert by_case(read_rows(tmp_path / "st", "r")) == {"a": ["missed"], "b": ["met"], "c": ["met"], "d": ["met"]}


@pytest.mark.parametrize("name", ["t.jsonl", "t.json", "t.parquet"])
def test_tf3_09_a_true_false_or_whole_number_is_compared_as_json_spells_it(tmp_path: Path, name: str) -> None:
    write_table(tmp_path / name, [{"case": "a", "passed": True}, {"case": "a", "passed": False}, {"case": "b", "passed": False}])
    _import(tmp_path, table_argv(name, "st", "r", outcome="passed", failed=("false",)))
    assert by_case(read_rows(tmp_path / "st", "r")) == {"a": ["met", "missed"], "b": ["missed"]}
    write_table(tmp_path / f"n-{name}", [{"case": "a", "code": 0}, {"case": "a", "code": 1}, {"case": "b", "code": 2}])
    _import(tmp_path, table_argv(f"n-{name}", "st", "n", outcome="code", failed=("1", "2")))
    assert by_case(read_rows(tmp_path / "st", "n")) == {"a": ["met", "missed"], "b": ["missed"]}


# ---------- TF3-10: by score ----------


@pytest.mark.parametrize("side,want", [("below", ["missed", "met", "met"]), ("above", ["met", "met", "missed"])])
def test_tf3_10_a_score_equal_to_the_cut_met_it_on_either_side(tmp_path: Path, side: str, want: list[str]) -> None:
    write_table(tmp_path / "t.csv", [{"case": "a", "s": 0.4}, {"case": "a", "s": 0.5}, {"case": "a", "s": 0.6}])
    _import(tmp_path, table_argv("t.csv", "st", "r", score="s", cut="0.5", side=side))
    assert by_case(read_rows(tmp_path / "st", "r")) == {"a": want}


@pytest.mark.parametrize("name", ["t.csv", "t.jsonl", "t.parquet"])
def test_tf3_10_a_cell_with_no_number_has_no_outcome_and_never_reads_as_zero(tmp_path: Path, name: str) -> None:
    cells = [0.9, None, "n/a", "", 0.1] if not name.endswith(".parquet") else [0.9, None, None, None, 0.1]
    write_table(tmp_path / name, [{"case": "a", "s": c} for c in cells])
    doc = _import(tmp_path, table_argv(name, "st", "r", score="s", cut="0.5", side="below"))
    assert by_case(read_rows(tmp_path / "st", "r")) == {"a": ["met", None, None, None, "missed"]}
    assert no_outcome_total(doc) == 3 and doc["outcomes"] == {"met": 1, "missed": 1}


# ---------- TF3-11: the command line ----------

BASE = ["table", "t.csv", "--store", "st", "--run", "r", "--case-column", "case"]
WRONG = {
    "neither column": [],
    "both columns": ["--outcome-column", "outcome", "--failed", "fail", "--score-column", "s", "--cut", "0.5", "--below"],
    "an outcome column with no failure value": ["--outcome-column", "outcome"],
    "a failure value with no outcome column": ["--failed", "fail"],
    "a failure value beside a score column": ["--score-column", "s", "--cut", "0.5", "--below", "--failed", "fail"],
    "a score column with no cut": ["--score-column", "s", "--below"],
    "a cut beside an outcome column": ["--outcome-column", "outcome", "--failed", "fail", "--cut", "0.5"],
    "a side beside an outcome column": ["--outcome-column", "outcome", "--failed", "fail", "--below"],
}


@pytest.mark.parametrize("label", list(WRONG))
def test_tf3_11_a_form_given_wrong_is_a_wrong_command_line(tmp_path: Path, label: str) -> None:
    write_table(tmp_path / "t.csv", [{"case": "a", "outcome": "fail", "s": 0.2}])
    with chdir(tmp_path):
        words = usage_error(verb([*BASE, *WRONG[label]]))
    assert words == ["poisson-trace", "import", "table", "--help"], words
    assert not (tmp_path / "st").exists()


def test_tf3_11_the_case_column_is_required(tmp_path: Path) -> None:
    write_table(tmp_path / "t.csv", [{"case": "a", "outcome": "fail"}])
    with chdir(tmp_path):
        words = usage_error(verb(["table", "t.csv", "--store", "st", "--run", "r", "--outcome-column", "outcome", "--failed", "fail"]))
    assert words == ["poisson-trace", "import", "table", "--help"], words
    assert not (tmp_path / "st").exists()


REFUSED = {
    "no side": dict(score="s", cut="0.5"),
    "both sides": dict(score="s", cut="0.5", side="below"),  # --above added below
    "a cut that is no number": dict(score="s", cut="half", side="below"),
    "an infinite cut": dict(score="s", cut="inf", side="below"),
    "the score column is the case column": dict(score="case", cut="0.5", side="below"),
    "the outcome column is the case column": dict(outcome="case"),
}


@pytest.mark.parametrize("label", list(REFUSED))
def test_tf3_11_what_the_ragas_reader_refuses_is_refused(tmp_path: Path, label: str) -> None:
    write_table(tmp_path / "t.csv", [{"case": "a", "outcome": "fail", "s": 0.2}])
    argv = table_argv("t.csv", "st", "r", **REFUSED[label])
    if label == "both sides":
        argv.append("--above")
    with chdir(tmp_path):
        refusal(verb(argv))
    assert not (tmp_path / "st").exists()


# ---------- TF3-12: the Ragas reader's refusals ----------


def test_tf3_12_a_column_the_file_does_not_hold_is_refused_listing_its_columns(tmp_path: Path) -> None:
    write_table(tmp_path / "t.csv", [{"case": "a", "outcome": "fail", "tokens": 3}])
    for argv in (table_argv("t.csv", "st", "r", outcome="status"), table_argv("t.csv", "st", "r", case="id"),
                 table_argv("t.csv", "st", "r", score="score", cut="0.5", side="below")):
        with chdir(tmp_path):
            line = refusal(verb(argv))
        assert all(column in line for column in ("case", "outcome", "tokens")), line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("name,body", [
    ("t.csv", b"case,outcome,outcome\na,fail,ok\n"),
    ("t.csv", b"case,case,outcome\na,b,fail\n"),
])
def test_tf3_12_a_column_named_twice_is_refused(tmp_path: Path, name: str, body: bytes) -> None:
    (tmp_path / name).write_bytes(body)
    with chdir(tmp_path):
        refusal(verb(table_argv(name, "st", "r")))
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("name", ["t.csv", "t.jsonl", "t.parquet"])
def test_tf3_12_an_empty_case_cell_is_refused_naming_its_row(tmp_path: Path, name: str) -> None:
    write_table(tmp_path / name, [{"case": "a", "outcome": "ok"}, {"case": "b", "outcome": "ok"}, {"case": None, "outcome": "fail"}])
    with chdir(tmp_path):
        line = refusal(verb(table_argv(name, "st", "r")))
    assert "3" in line.replace(name, ""), line
    assert not (tmp_path / "st").exists()


DAMAGED = {
    "text that is not UTF-8": ("t.csv", "case,outcome\na,f\xe9il\n".encode("latin-1")),
    "a CSV line that cannot be read": ("t.csv", b'case,outcome\n"a,fail\n'),
    "a CSV row longer than its header": ("t.csv", b"case,outcome\na,fail,extra\n"),
    "a JSON Lines line that is not JSON": ("t.jsonl", b'{"case": "a", "outcome": "fail"}\n{"case": "b",\n'),
    "a JSON Lines line that is not an object": ("t.jsonl", b'{"case": "a", "outcome": "fail"}\n["b", "fail"]\n'),
    "a JSON file that is an object": ("t.json", b'{"case": "a", "outcome": "fail"}'),
    "a JSON list holding a non-object": ("t.json", b'[{"case": "a", "outcome": "fail"}, 3]'),
    "a gzip file that is damaged": ("t.csv.gz", gzip.compress(b"case,outcome\na,fail\n")[:-6]),
    "a gzip name on a plain file": ("t.csv.gz", b"case,outcome\na,fail\n"),
    "a header and no row": ("t.csv", b"case,outcome\n"),
    "an empty file": ("t.csv", b""),
    "an empty JSON list": ("t.json", b"[]"),
    "a Parquet name on a CSV": ("t.parquet", b"case,outcome\na,fail\n"),
}


@pytest.mark.parametrize("label", list(DAMAGED))
def test_tf3_12_a_file_that_is_not_a_table_is_refused_naming_it(tmp_path: Path, label: str) -> None:
    name, body = DAMAGED[label]
    (tmp_path / name).write_bytes(body)
    with chdir(tmp_path):
        line = refusal(verb(table_argv(name, "st", "r")))
    assert name in line, line
    assert not (tmp_path / "st").exists()


def test_tf3_12_one_bad_file_writes_nothing_of_the_others(tmp_path: Path) -> None:
    write_table(tmp_path / "good.csv", ROWS)
    (tmp_path / "bad.csv").write_bytes(b"case,outcome\n,fail\n")
    with chdir(tmp_path):
        refusal(verb(table_argv(["good.csv", "bad.csv"], "st", "r")))
    assert not (tmp_path / "st").exists()


def test_tf3_12_no_row_with_an_outcome_writes_no_run(tmp_path: Path) -> None:
    write_table(tmp_path / "t.csv", [{"case": "a", "outcome": ""}, {"case": "b", "outcome": ""}])
    with chdir(tmp_path):
        refusal(verb(table_argv("t.csv", "st", "r")))
    assert not (tmp_path / "st" / "r").exists()


# ---------- TF3-13: cases, repeats, and nothing else kept ----------


def test_tf3_13_the_case_is_the_cell_as_written(tmp_path: Path) -> None:
    long = "q" * 81
    write_table(tmp_path / "t.csv", outcome_rows([("007", "fail"), ("7", "ok"), ("7.0", "ok"), (long, "fail"), ("a b", "ok")]))
    _import(tmp_path, table_argv("t.csv", "st", "r"))
    cases = set(by_case(read_rows(tmp_path / "st", "r")))
    assert {"007", "7", "7.0", "a b"} <= cases and long not in cases and len(cases) == 5, cases
    write_table(tmp_path / "n.jsonl", [{"case": 7, "outcome": "fail"}, {"case": 7, "outcome": "ok"}, {"case": 2.5, "outcome": "ok"}])
    _import(tmp_path, table_argv("n.jsonl", "st", "n"))
    assert by_case(read_rows(tmp_path / "st", "n")) == {"7": ["missed", "met"], "2.5": ["met"]}


def test_tf3_13_rows_sharing_a_case_are_repeats_in_the_order_read_across_files(tmp_path: Path) -> None:
    write_table(tmp_path / "one.csv", outcome_rows([("a", "fail"), ("b", "ok"), ("a", "ok")]))
    write_table(tmp_path / "two.jsonl", outcome_rows([("a", "fail"), ("b", "fail")]))
    doc = _import(tmp_path, table_argv(["two.jsonl", "one.csv"], "st", "r"))
    assert by_case(read_rows(tmp_path / "st", "r")) == {"a": ["missed", "missed", "met"], "b": ["missed", "met"]}
    assert doc["repeats"] == {"min": 2, "max": 3}


@pytest.mark.parametrize("form", ["outcome", "score"])
def test_tf3_13_no_value_of_another_column_is_kept(tmp_path: Path, form: str) -> None:
    secret, said = "SENTINEL-PROMPT-31337", "SENTINEL-OUTCOME-WORD"
    rows = [
        {"case": "a", "outcome": "fail", "s": 0.2, "prompt": secret, "answer": f"{secret} answer"},
        {"case": "b", "outcome": said, "s": 0.8, "prompt": secret, "answer": "x"},
    ]
    write_table(tmp_path / "t.jsonl", rows)
    argv = table_argv("t.jsonl", "st", "r") if form == "outcome" else table_argv("t.jsonl", "st", "r", score="s", cut="0.5", side="below")
    with chdir(tmp_path):
        result = verb(argv)
    assert result.code == 0, result.text
    assert holds(tmp_path / "st", secret) == [] and holds(tmp_path / "st", said) == []
    # the outcome column's own values are listed with their rows under the import's "What was
    # written"; no other column's value is printed or kept
    assert secret not in result.text
    assert said not in result.err
    assert said not in result.out if form == "score" else said not in result.out.split("## What was written")[0]


# ---------- TF3-14: the summary and the store ----------


def test_tf3_14_the_summary_declares_what_was_read(tmp_path: Path) -> None:
    write_table(tmp_path / "t.csv", ROWS)
    write_table(tmp_path / "u.csv.gz", ROWS)
    doc = _import(tmp_path, table_argv(["t.csv", "u.csv.gz"], "st", "r", failed=("fail", "error")))
    assert doc["tool"] == "table" and doc["run"] == "r"
    assert [f["sha256"] for f in doc["files"]] == [sha256(tmp_path / "t.csv"), sha256(tmp_path / "u.csv.gz")]
    assert {"case", "outcome", "fail", "error"} <= set(scalars(doc["declared"])), doc["declared"]
    write_table(tmp_path / "s.csv", [{"case": "a", "s": 0.1}, {"case": "b", "s": 0.9}])
    by_score = _import(tmp_path, table_argv("s.csv", "st", "s", score="s", cut="0.25", side="above"))
    declared = scalars(by_score["declared"])
    assert {"case", "s", "above"} <= set(declared) and 0.25 in declared, by_score["declared"]


def test_tf3_14_the_start_is_the_first_file_s_time_unless_given(tmp_path: Path) -> None:
    write_table(tmp_path / "first.csv", ROWS)
    write_table(tmp_path / "second.csv", ROWS)
    first, second = 1_757_098_447, 1_757_198_447
    os.utime(tmp_path / "first.csv", (first, first))
    os.utime(tmp_path / "second.csv", (second, second))
    doc = _import(tmp_path, table_argv(["second.csv", "first.csv"], "st", "r"))
    m = Store(tmp_path / "st").manifest("r")
    assert m.created_at == datetime.fromtimestamp(second, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert m.environment["import"]["started_from"] == "file time" == doc["started"]["from"]
    given = _import(tmp_path, table_argv("first.csv", "st", "g", "--started", "2026-01-02T05:04:05+02:00"))
    assert Store(tmp_path / "st").manifest("g").created_at == "2026-01-02T03:04:05Z" and given["started"]["from"] == "given"


def test_tf3_14_the_store_is_prove_s_and_missed_is_its_event(tmp_path: Path) -> None:
    old = outcome_rows([(c, "fail" if c in "ab" else "ok") for c in "abcdef" for _ in range(4)])
    new = outcome_rows([(c, "fail" if c == "a" else "ok") for c in "abcdef" for _ in range(4)])
    write_table(tmp_path / "old.csv", old)
    write_table(tmp_path / "new.csv", new)
    doc = _import(tmp_path, table_argv("old.csv", "st", "old", "--started", "2026-10-01T09:00:00Z"))
    _import(tmp_path, table_argv("new.csv", "st", "new", "--started", "2026-10-02T09:00:00Z"))
    m = Store(tmp_path / "st").manifest("old")
    assert (m.backend, m.target_id, m.status) == ("import:table", "import/table", "complete")
    rows = read_rows(tmp_path / "st", "old")
    assert {r["seed"] for r in rows} == {0} and all(set(r["config"]) == {"case"} for r in rows)
    assert "--event missed" in doc["next"]
    with chdir(tmp_path):
        checked = trace(["fix-check", "old", "new", "--store", "st", "--event", "missed", "--inputs", "all", "--max-mde", "0.9", "--json"])
    assert checked.code == 0, checked.text
    data = json.loads(checked.out)
    assert data["schema"] == "poisson-trace.fix-check/2"  # the fix-check JSON's own schema
