"""TF3-21 and TF3-22: the table and JUnit readers say which files look like theirs (spec sections
4.3 and 6.3: each reader exposes ``looks_like(path) -> str | None`` for init).

- TF3-21: ``table.looks_like`` names a ``.csv``, ``.jsonl`` or ``.json`` table (a ``.json`` file being
  a list of rows) with a column named exactly one of ``table.OUTCOME_COLUMNS`` within its first 4 KB,
  and no column named like a Ragas metric; ``junit.looks_like`` names a ``.xml`` file whose root
  element, within its first 4 KB, is ``testsuites`` or ``testsuite``, and that declares no document
  type. Each gives one line, or None, and never raises.
- TF3-22: no file is claimed by two readers of the install: a table both could read is the Ragas
  reader's.

The names are looked up when called, so the tests reach each reader through its module.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest

from tf2_support import deepeval_file, ragas_file, scratch_home  # noqa: F401
from tf3_support import OWN_1, OWN_2, PRESENT, SUITE_1, SUITE_2, TABLE_A, TABLE_B, Case, report, suite, write_report, write_table


def looks_like(tool: str, path: Path) -> Any:
    return import_module(f"poisson_trace.ingest.{tool}").looks_like(path)


def outcome_columns() -> tuple[str, ...]:
    columns: tuple[str, ...] = import_module("poisson_trace.ingest.table").OUTCOME_COLUMNS
    return columns


def _one_line(said: Any) -> str:
    assert isinstance(said, str) and said.strip() and "\n" not in said, said
    return said


# ---------- TF3-21: the table reader ----------


def test_tf3_21_the_committed_tables_are_named_with_their_outcome_column() -> None:
    assert "outcome" in outcome_columns()
    for path in (TABLE_A, TABLE_B):
        assert "outcome" in _one_line(looks_like("table", path))


@pytest.mark.parametrize("name", ["t.csv", "t.jsonl", "t.json"])
def test_tf3_21_every_outcome_column_names_a_table(tmp_path: Path, name: str) -> None:
    columns = outcome_columns()
    assert columns and all(isinstance(c, str) and c for c in columns) and len(set(columns)) == len(columns)
    for column in columns:
        path = write_table(tmp_path / column / name, [{"case": "a", column: "x"}])
        assert column in _one_line(looks_like("table", path)), (column, name)


def test_tf3_21_an_outcome_column_is_a_column_named_exactly(tmp_path: Path) -> None:
    column = outcome_columns()[0]
    cases = {
        "a column only beginning with the word": f"case,{column}_note\na,1\n",
        "the word in a cell": f"case,score\n{column},1\n",
        "the word in another case": f"case,{column.upper()}\na,1\n",
        "no outcome column": "case,score\na,1\n",
    }
    for label, body in cases.items():
        path = tmp_path / f"{len(label)}.csv"
        path.write_text(body, encoding="utf-8")
        assert looks_like("table", path) is None, label
    one = tmp_path / "one.json"
    one.write_text(json.dumps({"case": "a", column: "x"}), encoding="utf-8")
    assert looks_like("table", one) is None


def test_tf3_21_a_column_past_the_first_4_kb_is_not_looked_for(tmp_path: Path) -> None:
    column = outcome_columns()[0]
    late = tmp_path / "late.jsonl"
    late.write_text(json.dumps({"case": "a", "notes": "x" * 5000, column: "x"}) + "\n", encoding="utf-8")
    assert looks_like("table", late) is None
    early = tmp_path / "early.jsonl"
    early.write_text(json.dumps({"case": "a", column: "x", "notes": "x" * 5000}) + "\n", encoding="utf-8")
    _one_line(looks_like("table", early))
    wide = tmp_path / "wide.csv"
    wide.write_text(",".join(f"c{i:04d}" for i in range(1000)) + f",{column}\n" + ",".join("1" * 1001) + "\n", encoding="utf-8")
    assert looks_like("table", wide) is None


@pytest.mark.parametrize("name", ["t.csv.gz", "t.jsonl.gz", "t.parquet", "t.txt", "t.tsv", "t.xml"])
def test_tf3_21_a_table_the_search_does_not_open_is_none(tmp_path: Path, name: str) -> None:
    path = write_table(tmp_path / name, [{"case": "a", "outcome": "x"}]) if not name.endswith((".txt", ".tsv", ".xml")) else tmp_path / name
    if not path.exists():
        path.write_text("case,outcome\na,x\n", encoding="utf-8")
    assert looks_like("table", path) is None


def test_tf3_21_a_ragas_table_is_never_the_table_reader_s(tmp_path: Path) -> None:
    column = outcome_columns()[0]
    for name in ("r.csv", "r.jsonl", "r.json"):
        path = write_table(tmp_path / name, [{"case": "a", "faithfulness": 0.5, column: "x"}])
        assert looks_like("table", path) is None, name
        _one_line(looks_like("ragas", path))


def test_tf3_21_a_promptfoo_record_is_not_a_table_of_results(tmp_path: Path) -> None:
    """promptfoo's ``-o results.jsonl`` row (promptfoo 0.120.19: these keys, in this order) holds
    every prompt's results in one file; it is the promptfoo reader's to pick one, never one run of
    the table reader's."""
    row = {"cost": 0, "error": None, "gradingResult": None, "id": "x", "latencyMs": 1, "namedScores": {},
           "prompt": {"raw": "p", "label": "p"}, "promptId": "y", "promptIdx": 0, "provider": {"id": "echo"},
           "response": {"output": "o"}, "score": 1, "success": True, "testCase": {"vars": {}}, "testIdx": 0,
           "vars": {"case": "a"}, "metadata": {}, "failureReason": 0}
    path = tmp_path / "results.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert looks_like("table", path) is None


# ---------- TF3-21: the JUnit reader ----------


def test_tf3_21_the_committed_reports_are_named() -> None:
    for path in (SUITE_1, SUITE_2, OWN_1, OWN_2):
        _one_line(looks_like("junit", path))


@pytest.mark.parametrize("shape", ["testsuites", "testsuite", "a comment first", "no declaration", "a byte order mark"])
def test_tf3_21_a_junit_root_is_named(tmp_path: Path, shape: str) -> None:
    body = suite([Case("test_a"), Case("test_b", result="failure")])
    text = {
        "testsuites": report(body),
        "testsuite": report(body, root="testsuite"),
        "a comment first": report(body).replace("?>", "?>\n<!-- written by a runner -->\n", 1),
        "no declaration": report(body, head=""),
        "a byte order mark": "﻿" + report(body),
    }[shape]
    path = write_report(tmp_path / "r.xml", text)
    _one_line(looks_like("junit", path))


def test_tf3_21_another_xml_or_another_name_is_none(tmp_path: Path) -> None:
    junit = report(suite([Case("test_a")]))
    files = {
        "pom.xml": '<?xml version="1.0"?><project><modelVersion>4.0.0</modelVersion></project>',
        "page.xml": "<html><body>testsuites</body></html>",
        "r.junit": junit,
        "r.txt": junit,
        "r.xml.gz": junit,
        "doctype.xml": '<?xml version="1.0"?><!DOCTYPE testsuites [<!ENTITY x "y">]>' + junit.split("?>", 1)[1],
        "late.xml": '<?xml version="1.0"?>' + "<!--" + "x" * 5000 + "-->" + junit.split("?>", 1)[1],
        "child.xml": '<?xml version="1.0"?><results><testsuite name="a"><testcase name="b"/></testsuite></results>',
    }
    for name, text in files.items():
        path = write_report(tmp_path / name, text)
        assert looks_like("junit", path) is None, name


# ---------- TF3-21: never raises ----------


@pytest.mark.parametrize("tool", ["table", "junit"])
def test_tf3_21_never_raises(tmp_path: Path, tool: str) -> None:
    ext = "csv" if tool == "table" else "xml"
    folder = tmp_path / f"folder.{ext}"
    folder.mkdir()
    missing = tmp_path / f"missing.{ext}"
    binary = tmp_path / f"binary.{ext}"
    binary.write_bytes(b"\xff\xfe\x00\x81" * 4000)
    empty = tmp_path / f"empty.{ext}"
    empty.write_bytes(b"")
    locked = tmp_path / f"locked.{ext}"
    locked.write_text("case,outcome\na,x\n" if tool == "table" else report(suite([Case("a")])), encoding="utf-8")
    locked.chmod(0o000)
    cut = tmp_path / f"cut.{ext}"
    cut.write_bytes(('{"case": "a", "outc' if tool == "table" else '<?xml version="1.0"?><testsu').encode("utf-8"))
    try:
        for path in (folder, missing, binary, empty, locked, cut, str(empty)):
            assert looks_like(tool, path) is None, path
    finally:
        locked.chmod(0o600)


# ---------- TF3-22: one reader per file ----------


def test_tf3_22_no_file_is_claimed_by_two_readers(tmp_path: Path) -> None:
    column = outcome_columns()[0]
    files = [
        TABLE_A, SUITE_1, OWN_1,
        deepeval_file(tmp_path / "results" / "test_run_20261002_101500.json"),
        ragas_file(tmp_path / "scores" / "base.jsonl"), ragas_file(tmp_path / "scores" / "base.csv"),
        write_table(tmp_path / "both.csv", [{"case": "a", "faithfulness": 0.5, column: "x"}]),
        write_table(tmp_path / "both.json", [{"case": "a", "answer_relevancy": 0.5, column: "x"}]),
        write_table(tmp_path / "mine.jsonl", [{"case": "a", column: "x"}]),
    ]
    for path in files:
        claimed = [tool for tool in PRESENT if looks_like(tool, path) is not None]
        assert len(claimed) == 1, (path.name, claimed)
