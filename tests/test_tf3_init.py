"""TF3-23 to TF3-27: the table and JUnit readers join init's search and its import.

- TF3-23: init lists the JUnit reports and the outcome tables it finds as result files, and no
  other XML or table; the bound of 200 candidate files opened counts ``.xml`` files with the rest.
- TF3-24: JUnit reports alone are imported with no question asked of the reader: one run per
  file into ``trace-store``, named after the file without ``.xml``, failures ``missed``; the import
  lines init prints, and the setup as one command, replay as written.
- TF3-25: outcome tables alone are imported after the table reader's questions, in its flags'
  order: the case column, the outcome column, the failure values; ``--yes`` takes them from
  ``--case-column``, ``--outcome-column`` and ``--failed`` and refuses without them.
- TF3-26: when the files found were written by more than one tool, whichever of the four, init
  imports none: it says so before asking anything, writes nothing, and points to ``--no-import``
  and ``poisson-trace import``; ``--no-import`` writes the config with no store.
- TF3-27: a file is listed once, as its one reader's: a Ragas table with an outcome column is the
  Ragas reader's, and imports as one tool's file.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from poisson_prove.store import Store

from tf0_support import Ran
from tf2_support import (
    CONFIG, config, copy_tree, deepeval_file, here, init_yes, numbered, ragas_file, refused,
    summary_command, tree, tty, work,
)  # noqa: F401
from tf1_support import shell_words
from tf3_support import HE_FAILED, SUITE_1, SUITE_2, TABLE_A, TABLE_B, by_case, read_rows, write_table

TABLE_ANSWERS = ["--case-column", "case", "--outcome-column", "outcome", "--failed", "failed_assertion", "--failed", "crashed"]


def _listed(err: str) -> list[str]:
    return [line.split()[0].rstrip("/") for _, line in sorted(numbered(err).items())]


def _ok(result: Ran) -> Ran:
    assert result.code == 0, result.text
    assert result.out.startswith("ok  "), result.out
    return result


def _junit_files(folder: Path) -> None:
    (folder / "reports").mkdir(parents=True, exist_ok=True)
    shutil.copy(SUITE_1, folder / "reports" / "suite-1.xml")
    shutil.copy(SUITE_2, folder / "reports" / "suite-2.xml")


def _table_files(folder: Path) -> None:
    (folder / "results").mkdir(parents=True, exist_ok=True)
    shutil.copy(TABLE_A, folder / "results" / "he-a.csv")
    shutil.copy(TABLE_B, folder / "results" / "he-b.csv")


def _import_lines(out: str, tool: str) -> list[list[str]]:
    found = []
    for line in out.splitlines():
        at = line.find(f"poisson-trace import {tool} ")
        if at >= 0:
            found.append(shell_words(line[at:]))
    return found


def _runs(folder: Path) -> dict[str, dict[str, list[str | None]]]:
    store = folder / "trace-store"
    return {run: by_case(read_rows(store, run)) for run in Store(store).runs()}


# ---------- TF3-23: what the search lists ----------


def test_tf3_23_reports_and_outcome_tables_are_listed_and_nothing_else(tmp_path: Path) -> None:
    folder = work(tmp_path)
    _junit_files(folder)
    _table_files(folder)
    (folder / "build").mkdir()
    (folder / "build" / "pom.xml").write_text('<?xml version="1.0"?><project><modelVersion>4.0.0</modelVersion></project>', encoding="utf-8")
    (folder / "build" / "page.xml").write_text("<html><body><testsuites/></body></html>", encoding="utf-8")
    (folder / "notes").mkdir()
    (folder / "notes" / "plain.csv").write_text("case,score\na,1\n", encoding="utf-8")
    (folder / "notes" / "word.csv").write_text("case,score\noutcome,1\n", encoding="utf-8")
    result = _ok(init_yes(folder, "--no-import"))
    assert sorted(_listed(result.err)) == sorted(["reports/suite-1.xml", "reports/suite-2.xml", "results/he-a.csv", "results/he-b.csv"]), result.err
    assert "store" not in config(folder)


@pytest.mark.parametrize("decoys,kind,found", [
    (198, "xml", True), (199, "xml", False), (198, "both", True), (199, "both", False),
])
def test_tf3_23_xml_files_count_toward_the_200_opened(tmp_path: Path, decoys: int, kind: str, found: bool) -> None:
    """A report read first, then the decoys, then a report that is the 200th file opened or the
    201st: the first is always listed, the last only when it was opened."""
    folder = work(tmp_path)
    shutil.copy(SUITE_1, folder / "aa-suite.xml")
    for i in range(decoys):
        if kind == "xml" or i % 2:
            (folder / f"c{i:03d}.xml").write_text('<?xml version="1.0"?><project/>', encoding="utf-8")
        else:
            (folder / f"c{i:03d}.csv").write_text("case,score\na,1\n", encoding="utf-8")
    shutil.copy(SUITE_1, folder / "zz-suite.xml")
    result = _ok(init_yes(folder, "--no-import"))
    listed = _listed(result.err)
    assert "aa-suite.xml" in listed and ("zz-suite.xml" in listed) is found, result.err


# ---------- TF3-24: JUnit reports alone ----------


def _junit_imported(folder: Path, result: Ran) -> None:
    _ok(result)
    runs = _runs(folder)
    assert sorted(runs) == ["suite-1", "suite-2"]
    missed = {run: sum(o == "missed" for outs in got.values() for o in outs) for run, got in runs.items()}
    assert missed == {"suite-1": 87, "suite-2": 83}
    assert all(len(got) == 656 for got in runs.values())
    written = config(folder)
    assert written["store"]["path"] == "trace-store" and written["events"]["failed"] == ["missed"]


def test_tf3_24_junit_reports_are_imported_with_no_question(tmp_path: Path) -> None:
    folder = work(tmp_path, "source")
    _junit_files(folder)
    pristine = copy_tree(folder, tmp_path / "pristine")
    result = init_yes(folder)
    _junit_imported(folder, result)
    lines = _import_lines(result.out, "junit")
    assert len(lines) == 2, result.out
    # each import line, run as written, writes the run init wrote
    replayed = copy_tree(pristine, tmp_path / "lines")
    for words in lines:
        assert words[:3] == ["poisson-trace", "import", "junit"], words
        assert here(replayed, words[1:]).code == 0
    assert _runs(replayed) == _runs(folder)
    # the setup as one command
    command = summary_command(result.out)
    again = copy_tree(pristine, tmp_path / "again")
    assert here(again, command[1:]).code == 0
    assert (again / CONFIG).read_bytes() == (folder / CONFIG).read_bytes() and _runs(again) == _runs(folder)


def test_tf3_24_on_a_terminal_only_the_import_and_the_failures_are_asked(tmp_path: Path) -> None:
    folder = work(tmp_path)
    _junit_files(folder)
    result = tty(["init"], ["", ""], cwd=folder)
    _junit_imported(folder, result)
    assert "[Y/n]" in result.err


# ---------- TF3-25: outcome tables alone ----------


def _table_imported(folder: Path, result: Ran) -> None:
    _ok(result)
    runs = _runs(folder)
    assert sorted(runs) == ["he-a", "he-b"]
    missed = {run: sum(o == "missed" for outs in got.values() for o in outs) for run, got in runs.items()}
    assert missed == {"he-a": 1_338, "he-b": 1_387}
    assert all(len(got) == 328 for got in runs.values())
    assert config(folder)["events"]["failed"] == ["missed"]


def test_tf3_25_tables_are_imported_from_the_flags(tmp_path: Path) -> None:
    folder = work(tmp_path, "source")
    _table_files(folder)
    pristine = copy_tree(folder, tmp_path / "pristine")
    result = init_yes(folder, *TABLE_ANSWERS)
    _table_imported(folder, result)
    lines = _import_lines(result.out, "table")
    assert len(lines) == 2, result.out
    replayed = copy_tree(pristine, tmp_path / "lines")
    for words in lines:
        assert here(replayed, words[1:]).code == 0
    assert _runs(replayed) == _runs(folder)
    command = summary_command(result.out)
    for flag in ("--case-column", "--outcome-column", "--failed"):
        assert flag in command, command
    again = copy_tree(pristine, tmp_path / "again")
    assert here(again, command[1:]).code == 0
    assert (again / CONFIG).read_bytes() == (folder / CONFIG).read_bytes() and _runs(again) == _runs(folder)


@pytest.mark.parametrize("left_out", ["--case-column", "--outcome-column", "--failed"])
def test_tf3_25_yes_without_the_table_answers_is_refused(tmp_path: Path, left_out: str) -> None:
    folder = work(tmp_path)
    _table_files(folder)
    before = tree(folder)
    answers = list(TABLE_ANSWERS)
    while left_out in answers:
        at = answers.index(left_out)
        del answers[at : at + 2]
    line = refused(init_yes(folder, *answers))
    assert left_out in line, line
    assert tree(folder) == before


def test_tf3_25_on_a_terminal_the_table_questions_are_asked_in_its_flags_order(tmp_path: Path) -> None:
    folder = work(tmp_path, "source")
    _table_files(folder)
    pristine = copy_tree(folder, tmp_path / "pristine")
    result = tty(["init"], ["", "case", "outcome", "failed_assertion, crashed", ""], cwd=folder)
    _table_imported(folder, result)
    command = summary_command(result.out)
    failed = [command[i + 1] for i, w in enumerate(command) if w == "--failed"]
    assert sorted(failed) == sorted(HE_FAILED), command
    again = copy_tree(pristine, tmp_path / "again")
    assert here(again, command[1:]).code == 0
    assert (again / CONFIG).read_bytes() == (folder / CONFIG).read_bytes()


def test_tf3_24_the_case_given_to_init_is_the_case_the_reports_are_read_by(tmp_path: Path) -> None:
    """``--case name`` is a JUnit case form and is used; ``--case position`` is not one, and init
    refuses it before writing, rather than record a case form the reader did not use."""
    folder = work(tmp_path, "source")
    _junit_files(folder)
    pristine = copy_tree(folder, tmp_path / "pristine")
    result = _ok(init_yes(folder, "--case", "name"))
    runs = _runs(folder)
    assert all(len(got) == 164 for got in runs.values()), {r: len(g) for r, g in runs.items()}
    replayed = copy_tree(pristine, tmp_path / "lines")
    for words in _import_lines(result.out, "junit"):
        assert here(replayed, words[1:]).code == 0
    assert _runs(replayed) == runs
    other = copy_tree(pristine, tmp_path / "position")
    before = tree(other)
    refused(init_yes(other, "--case", "position"))
    assert tree(other) == before


# ---------- TF3-26: more than one tool ----------

MAKERS = {
    "deepeval": lambda f: deepeval_file(f / "results" / "test_run_20261002_101500.json"),
    "ragas": lambda f: ragas_file(f / "scores" / "base.jsonl"),
    "table": lambda f: shutil.copy(TABLE_A, f / "he-a.csv"),
    "junit": lambda f: shutil.copy(SUITE_1, f / "suite-1.xml"),
}
COMBOS = [("deepeval", "junit"), ("ragas", "table"), ("ragas", "junit"), ("deepeval", "table"), ("table", "junit"),
          ("deepeval", "ragas", "table", "junit")]


def _made(folder: Path, tools: tuple[str, ...]) -> None:
    for tool in tools:
        MAKERS[tool](folder)


@pytest.mark.parametrize("tools", COMBOS, ids=["+".join(c) for c in COMBOS])
def test_tf3_26_files_of_two_tools_import_none(tmp_path: Path, tools: tuple[str, ...]) -> None:
    folder = work(tmp_path)
    _made(folder, tools)
    before = tree(folder)
    answers = ["--metric", "faithfulness", "--cut", "0.5", "--below", *TABLE_ANSWERS] if "ragas" in tools else TABLE_ANSWERS
    result = init_yes(folder, *answers)
    line = refused(result)
    assert all(tool in line for tool in tools) and "--no-import" in line, line
    nexts = [shell_words(n[len("  next: "):]) for n in result.lines() if n.startswith("  next: ")]
    assert ["poisson-trace", "import", "--help"] in nexts, result.err
    assert tree(folder) == before
    # asking for the import does not make files of two tools importable
    insisted = init_yes(folder, "--import", *answers)
    refused(insisted)
    assert tree(folder) == before
    declined = init_yes(folder, "--no-import")
    assert declined.code == 0 and "store" not in config(folder), declined.text
    assert not (folder / "trace-store").exists()


@pytest.mark.parametrize("tools", [("deepeval", "junit"), ("table", "junit")], ids=["deepeval+junit", "table+junit"])
def test_tf3_26_on_a_terminal_it_refuses_before_asking(tmp_path: Path, tools: tuple[str, ...]) -> None:
    folder = work(tmp_path)
    _made(folder, tools)
    before = tree(folder)
    result = tty(["init"], [], cwd=folder, timeout=60)
    # a question would wait for an answer that never comes, and the command would be killed
    assert result.code == 1, result.text
    assert "[Y/n]" not in result.err and "error: " in result.err, result.err
    assert tree(folder) == before


# ---------- TF3-27: one reader per file ----------


def test_tf3_27_a_ragas_table_with_an_outcome_column_is_one_tool_s(tmp_path: Path) -> None:
    folder = work(tmp_path)
    write_table(folder / "scores" / "base.csv", [
        {"case": f"q{i}", "faithfulness": (i % 10) / 10, "outcome": "fail" if i % 3 == 0 else "ok"} for i in range(30)
    ])
    result = _ok(init_yes(folder, "--metric", "faithfulness", "--cut", "0.5", "--below", "--case-column", "case"))
    assert _listed(result.err) == ["scores/base.csv"], result.err
    store = Store(folder / "trace-store")
    assert store.runs() == ["base"] and store.manifest("base").backend == "import:ragas"
