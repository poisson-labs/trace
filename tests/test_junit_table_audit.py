"""Edge cases of the import verb and its readers, each a test: an XML encoding the parser does not
take is a refusal, not a failure; "import" as an option's value before no verb is a wrong command
line; a CSV header cell with a space around its name is not listed as the column it is not; an
option nobody knows before the verb leaves the verb to the words after it, an option's value
skipped; and a test case inside a test case refuses the report."""

from __future__ import annotations

from pathlib import Path

import pytest

from look_support import chdir, trace
from names_support import shell_words
from setup_support import config, init_yes, scratch_home, work  # noqa: F401
from junit_table_support import alias, junit_argv, refusal, verb, write_report
from poisson_trace.ingest import table


@pytest.mark.parametrize("encoding", ["bogus", "Shift_JIS"])
def test_an_encoding_the_parser_does_not_take_is_refused_naming_the_file(tmp_path: Path, encoding: str) -> None:
    write_report(tmp_path / "r.xml", f'<?xml version="1.0" encoding="{encoding}"?><testsuite><testcase name="a"/></testsuite>')
    with chdir(tmp_path):
        line = refusal(verb(junit_argv("r.xml", "st", "r")))
    assert "r.xml" in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("option", ["--store", "--event", "--config"])
def test_import_as_an_option_s_value_before_no_verb_is_a_wrong_command_line(tmp_path: Path, option: str) -> None:
    with chdir(work(tmp_path)):
        result = trace([option, "import"])
    assert result.code == 2 and result.out == "", result.text
    assert result.lines()[0].startswith("error: "), result.err


def test_a_csv_header_cell_with_a_space_around_its_name_is_not_that_column(tmp_path: Path) -> None:
    folder = work(tmp_path)
    (folder / "r.csv").write_text("case, outcome\na, FAIL\nb, ok\n", encoding="utf-8")
    assert table.looks_like(folder / "r.csv") is None
    result = init_yes(folder, "--case-column", "case", "--outcome-column", "outcome", "--failed", "FAIL")
    assert result.code == 0, result.text
    assert "store" not in config(folder)


def test_after_an_option_nobody_knows_an_option_s_value_does_not_decide_the_verb(tmp_path: Path) -> None:
    with chdir(work(tmp_path)):
        a = trace(["--bogus", "--run", "where", "import", "table", "x.csv"])
        b = alias(["--bogus", "--run", "where", "table", "x.csv"])
    assert a.code == b.code == 2 and (a.out, a.err) == (b.out, b.err), (a.text, b.text)
    nexts = [line[len("  next: "):] for line in a.lines() if line.startswith("  next: ")]
    assert shell_words(nexts[0])[:3] == ["poisson-trace", "import", "--help"], a.err


def test_a_test_case_inside_a_test_case_refuses_the_report(tmp_path: Path) -> None:
    write_report(tmp_path / "r.xml", '<testsuite><testcase name="a"><testcase name="b"><failure/></testcase></testcase></testsuite>')
    with chdir(tmp_path):
        line = refusal(verb(junit_argv("r.xml", "st", "r")))
    assert "r.xml" in line, line
    assert not (tmp_path / "st").exists()
