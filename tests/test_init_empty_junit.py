"""init leaves out a JUnit report that holds no test case.

A runner that collected no test still writes a report: pytest's ``--junitxml`` writes one suite with
``tests="0"`` and no ``<testcase>``. init lists it with the other reports it finds, then leaves it
out with one line on stderr naming it, and imports the rest, rather than refusing them all. The
line comes before anything is asked, and before init decides which tool's files it found, so a
report with nothing in it neither blocks the import nor counts as a second tool. A report that is
damaged still stops the import, naming it: only the empty one is left out. ``poisson-trace import
junit`` given such a report still refuses it (TF3-18).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from conftest import TAU2
from poisson_prove.store import Store

from setup_support import CONFIG, NUMBERED, config, copy_tree, here, init_yes, refused, scratch_home, summary_command, tty, work  # noqa: F401
from junit_table_support import SUITE_1, SUITE_2, TABLE_A, TABLE_B

# what pytest 9.1.1 writes with --junitxml when it collects no test (exit 5), its host name changed
EMPTY = (
    '<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests"><testsuite name="pytest" '
    'errors="0" failures="0" skipped="0" tests="0" time="0.003" '
    'timestamp="2026-10-19T15:36:17.379972-04:00" hostname="localhost" /></testsuites>'
)
LEFT_OUT = "Leaving out {}: a JUnit report with no test case in it, as a runner writes when it collected no test."
TABLE_ANSWERS = ["--case-column", "case", "--outcome-column", "outcome", "--failed", "failed_assertion", "--failed", "crashed"]


def _reports(folder: Path) -> None:
    (folder / "reports").mkdir(parents=True, exist_ok=True)
    shutil.copy(SUITE_1, folder / "reports" / "suite-1.xml")
    shutil.copy(SUITE_2, folder / "reports" / "suite-2.xml")
    (folder / "reports" / "suite-0.xml").write_text(EMPTY, encoding="utf-8")


def _runs(folder: Path) -> list[str]:
    store = folder / "trace-store"
    return sorted(Store(store).runs()) if store.exists() else []


def _said(err: str, path: str) -> list[str]:
    """The lines of stderr naming ``path``, but its line in the numbered listing."""
    return [line for line in err.splitlines() if path in line and not NUMBERED.match(line)]


def test_an_empty_report_is_left_out_in_one_line_and_the_others_are_imported(tmp_path: Path) -> None:
    folder = work(tmp_path, "source")
    _reports(folder)
    pristine = copy_tree(folder, tmp_path / "pristine")
    result = init_yes(folder)
    assert result.code == 0 and result.out.startswith("ok  wrote trace.toml and imported 2 runs"), result.text
    assert _runs(folder) == ["suite-1", "suite-2"]
    assert _said(result.err, "reports/suite-0.xml") == [LEFT_OUT.format("reports/suite-0.xml")], result.err
    assert "suite-0" not in result.out
    assert config(folder)["store"]["path"] == "trace-store"
    # the setup as one command leaves it out again, and writes the same file and runs
    again = copy_tree(pristine, tmp_path / "again")
    replayed = here(again, summary_command(result.out)[1:])
    assert replayed.code == 0 and _said(replayed.err, "reports/suite-0.xml") == [LEFT_OUT.format("reports/suite-0.xml")]
    assert (again / CONFIG).read_bytes() == (folder / CONFIG).read_bytes() and _runs(again) == _runs(folder)


def test_an_empty_report_is_said_before_the_import_is_asked(tmp_path: Path) -> None:
    folder = work(tmp_path)
    _reports(folder)
    result = tty(["init"], ["", ""], cwd=folder)
    assert result.code == 0, result.text
    left = result.err.index(LEFT_OUT.format("reports/suite-0.xml"))
    assert left < result.err.index("Import them as runs Trace can read?"), result.err
    assert _runs(folder) == ["suite-1", "suite-2"]


def test_an_empty_report_beside_another_tool_s_files_is_not_a_second_tool(tmp_path: Path) -> None:
    folder = work(tmp_path)
    (folder / "results").mkdir()
    shutil.copy(TABLE_A, folder / "results" / "he-a.csv")
    shutil.copy(TABLE_B, folder / "results" / "he-b.csv")
    (folder / "results" / "pytest.xml").write_text(EMPTY, encoding="utf-8")
    result = init_yes(folder, *TABLE_ANSWERS)
    assert result.code == 0, result.text
    assert _runs(folder) == ["he-a", "he-b"]
    assert _said(result.err, "results/pytest.xml") == [LEFT_OUT.format("results/pytest.xml")], result.err


def test_with_only_empty_reports_nothing_is_imported_or_asked(tmp_path: Path) -> None:
    folder = work(tmp_path)
    (folder / "a.xml").write_text(EMPTY, encoding="utf-8")
    (folder / "b.xml").write_text(EMPTY.replace("<testsuites", "<testsuites ").replace(' /></testsuites>', "></testsuite></testsuites>"), encoding="utf-8")
    result = tty(["init"], [""], cwd=folder)
    assert result.code == 0, result.text
    assert _said(result.err, "a.xml") == [LEFT_OUT.format("a.xml")] and _said(result.err, "b.xml") == [LEFT_OUT.format("b.xml")], result.err
    assert "Import them" not in result.err and not (folder / "trace-store").exists()
    assert result.out.startswith("ok  wrote trace.toml with no store yet"), result.out
    assert "store" not in config(folder)


def test_a_damaged_report_still_stops_the_import_naming_it(tmp_path: Path) -> None:
    """Only a report read whole with no test case in it is left out; one that cannot be read is
    refused, and nothing is written."""
    folder = work(tmp_path)
    _reports(folder)
    (folder / "reports" / "suite-3.xml").write_text(SUITE_1.read_text(encoding="utf-8")[:-40], encoding="utf-8")
    result = init_yes(folder)
    assert "reports/suite-3.xml" in refused(result)
    assert not (folder / CONFIG).exists() and not (folder / "trace-store").exists()


def test_beside_a_store_no_report_is_imported_so_none_is_said_left_out(tmp_path: Path) -> None:
    """With a Prove store found, init sets up the store and imports no result file, so it has no
    report to leave out."""
    folder = work(tmp_path)
    shutil.copytree(TAU2, folder / "proofload-runs")
    _reports(folder)
    result = init_yes(folder)
    assert result.code == 0 and "proofload-runs" in result.out, result.text
    assert "Leaving out" not in result.err and not (folder / "trace-store").exists()
