"""TF3-29 and TF3-30: the two sentences every import's store gets (spec section 6.4).

- TF3-29: ``where`` on a run with no traces prints, under the report's header, one line saying the
  run has no traces and which tool it was imported from, and leaves out the empty curve and the
  causes; exit 0. Its JSON keeps ``curve`` and ``causes`` empty and ``placement.excluded["no trace"]``,
  and ``note`` holds the same line. A run with traces is unchanged.
- TF3-30: ``compare`` on runs with no traces is refused, measured (the spec left it to this
  pair): two imported runs share their cells, so the refusal is not the one for runs with no common
  cell, and today's sentence ("no death in either run") is not why. The refusal names the tool the
  run was imported from, writes nothing, and points next at ``fix-check`` on the two runs, which
  reads them.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import CS, CS_EVENTS, CS_RECORD, events_args
from tf0_support import chdir, trace
from tf1_support import positionals, shell_words, snapshot
from tf2_support import deepeval_file, scratch_home, work  # noqa: F401
from tf3_support import Case, junit_argv, outcome_rows, report, suite, table_argv, verb, write_report, write_table


def _two_imported(folder: Path, tool: str) -> tuple[str, str]:
    """Two runs of one tool, ``old`` and ``new``, on the same cases, in ``folder/st``."""
    with chdir(folder):
        for n, run in enumerate(("old", "new")):
            started = ["--started", f"2026-10-0{n + 1}T09:00:00Z"]
            if tool == "deepeval":
                deepeval_file(folder / f"{run}.json", cases=24)
                argv = ["deepeval", f"{run}.json", "--store", "st", "--run", run, "--metric", "Tests Passed", "--cut", "recorded", "--case", "name", *started]
            elif tool == "table":
                write_table(folder / f"{run}.csv", outcome_rows([(c, "fail" if (c + run)[0] in "ab" else "ok") for c in "abcdef" for _ in range(3)]))
                argv = table_argv(f"{run}.csv", "st", run, *started)
            else:
                cases = [Case(f"test_{c}", result="failure" if c in ("a", run[0]) else "pass") for c in "abcdef" for _ in range(3)]
                write_report(folder / f"{run}.xml", report(suite(cases)))
                argv = junit_argv(f"{run}.xml", "st", run, *started)
            assert verb(argv).code == 0
    return "old", "new"


TOOLS = ["deepeval", "table", "junit"]


# ---------- TF3-29: where ----------


@pytest.mark.parametrize("tool", TOOLS)
def test_tf3_29_where_on_a_run_with_no_traces_says_so_in_one_line(tmp_path: Path, tool: str) -> None:
    folder = work(tmp_path)
    old, _ = _two_imported(folder, tool)
    with chdir(folder):
        text = trace(["where", old, "--store", "st", "--event", "missed"])
        data = trace(["where", old, "--store", "st", "--event", "missed", "--json"])
    assert text.code == 0 and data.code == 0, text.text + data.text
    doc = json.loads(data.out)
    note = doc.get("note")
    assert isinstance(note, str) and note.strip() and "\n" not in note and tool in note, doc.get("note")
    assert doc["curve"] == [] and doc["causes"] == []
    placement = doc["run"]["placement"]
    assert placement["placed"] == 0 and placement["excluded"]["no trace"] > 0
    lines = text.out.splitlines()
    h1 = next(i for i, line in enumerate(lines) if line.startswith("# "))
    assert note in lines[h1 + 1 :], text.out
    assert not any(line.startswith(("| step", "| turn", "| kind")) for line in lines), text.out
    # of a traced run's sections, only the first and the last remain: the run, and what it cannot say
    # (S6, ruled 2026-10-20: both open with the summary, kept out of the comparison; the traced run's
    # caveats section is the summary's too)
    traced = trace(["where", CS_RECORD, "--store", str(CS), *events_args(CS_EVENTS)]).out.splitlines()
    plain = ("## Summary", "## Before you act on this")
    headings = [line for line in traced if line.startswith("## ") and line not in plain]
    assert [line for line in lines if line.startswith("## ")][0] == "## Summary", text.out
    assert [line for line in lines if line.startswith("## ") and line not in plain] == [headings[0], headings[-1]], text.out


@pytest.mark.parametrize("tool", TOOLS)
def test_tf3_29_no_chart_is_drawn_of_a_run_with_no_traces(tmp_path: Path, tool: str) -> None:
    folder = work(tmp_path)
    old, _ = _two_imported(folder, tool)
    before = snapshot(folder)
    with chdir(folder):
        result = trace(["where", old, "--store", "st", "--event", "missed", "--svg", "chart.svg"])
    assert result.code == 1 and result.out == "", result.text
    assert result.lines()[0].startswith("error: ") and tool in result.lines()[0], result.err
    assert not (folder / "chart.svg").exists() and snapshot(folder) == before


def test_tf3_29_a_run_with_traces_keeps_its_curve_and_has_no_note(tmp_path: Path) -> None:
    data = trace(["where", CS_RECORD, "--store", str(CS), *events_args(CS_EVENTS), "--json"])
    text = trace(["where", CS_RECORD, "--store", str(CS), *events_args(CS_EVENTS)])
    assert data.code == 0 and text.code == 0
    doc = json.loads(data.out)
    assert doc.get("note") is None and doc["curve"], doc.get("note")
    # cs is counted in turns, and where says turn (S15, carried into TF15 on 2026-10-20)
    assert any(line.startswith("| turn") for line in text.out.splitlines())


# ---------- TF3-30: compare ----------


@pytest.mark.parametrize("tool", TOOLS)
def test_tf3_30_compare_on_two_imported_runs_is_refused_pointing_at_fix_check(tmp_path: Path, tool: str) -> None:
    folder = work(tmp_path)
    old, new = _two_imported(folder, tool)
    before = snapshot(folder)
    with chdir(folder):
        result = trace(["compare", old, new, "--store", "st", "--event", "missed", "--max-mde-hr", "1.5"])
    assert result.code == 1 and result.out == "", result.text
    lines = result.lines()
    assert lines[0].startswith("error: ") and tool in lines[0], result.err
    nexts = [line[len("  next: "):] for line in lines[1:] if line.startswith("  next: ")]
    assert nexts and len(nexts) == len(lines) - 1, result.err
    assert shell_words(nexts[0])[:2] == ["poisson-trace", "fix-check"], nexts
    assert sorted(positionals(nexts[0], "fix-check")) == sorted([old, new]), nexts
    assert snapshot(folder) == before


def test_tf3_30_compare_with_one_imported_run_names_it(tmp_path: Path) -> None:
    folder = work(tmp_path)
    store = shutil.copytree(CS, folder / "st")
    write_table(folder / "t.csv", outcome_rows([(c, "fail") for c in "abc"]))
    with chdir(folder):
        assert verb(table_argv("t.csv", "st", "imported-run", "--started", "2026-10-01T09:00:00Z")).code == 0
        before = snapshot(store)
        result = trace(["compare", CS_RECORD, "imported-run", "--store", "st", *events_args(CS_EVENTS), "--max-mde-hr", "1.5"])
    assert result.code == 1 and result.out == "", result.text
    first = result.lines()[0]
    assert first.startswith("error: ") and "imported-run" in first and "table" in first, result.err
    assert snapshot(store) == before
