"""A run's note is shown where Trace shows the run's details.

Prove's stored format 1.2 adds a run's note: one line of 1 to 200 characters, what ``sweep --note``
recorded as having changed for that run. Prove's ``inspect`` prints it on a ``note`` line directly
under the run's first line, and ``diff`` and ``check`` on a line under each run's (Prove 0.4.0's
``docs/commands/``). Trace's reports name their runs in their run sections, and a note goes on a
line of its own directly under the run's line there:

- ``where``: ``- note: <the note>`` under ``- run: …`` in ``## Run``;
- ``compare``: the same under each run's line, in ``## Run A (before)`` and ``## Run B (after)``;
- ``fix-check``: ``- note (old): …`` under ``- old: …`` and ``- note (new): …`` under ``- new: …``,
  naming the run as the tally line under it does;
- ``changes``: ``- note (A): …`` and ``- note (B): …`` the same way.

The note is the one Prove reads from the run's manifest: one Prove's own rule reads as none (on
more than one line, holding a control character, blank, or over 200 characters) shows nothing. A
run with no note gains no line. The HTML report, drawn from the same report, shows the note too.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from prove_floor_support import EVENT, NAMES, NOTES, READING, RUNS, STORE_1_0, STORE_1_2, argv_of, copy, run

from poisson_trace import api

#: For each report, the two runs' lines as each opens and the line each note goes on.
LABELS = {
    "where": [("- run: ", "- note: ")],
    "compare": [("- run: ", "- note: "), ("- run: ", "- note: ")],
    "fix-check": [("- old: ", "- note (old): "), ("- new: ", "- note (new): ")],
    "changes": [("- A: ", "- note (A): "), ("- B: ", "- note (B): ")],
}


def _report(store: Path, source: Path, label: str, cwd: Path) -> list[str]:
    ran = run(argv_of(READING[label], store, source), cwd)
    assert ran.code == 0, ran.text
    return ran.out.splitlines()


def _under(lines: list[str], opens: str) -> list[str]:
    """The line under each line that opens so."""
    return [lines[i + 1] for i, line in enumerate(lines) if line.startswith(opens)]


@pytest.mark.parametrize("label", list(LABELS))
def test_each_report_shows_each_run_s_note_under_the_run_s_line(tmp_path: Path, label: str) -> None:
    store = copy(STORE_1_2, tmp_path)
    lines = _report(store, STORE_1_2, label, tmp_path)
    notes = (NOTES[1],) if label == "where" else NOTES
    shown = []
    for (opens, says), note in zip(LABELS[label], notes, strict=True):
        under = _under(lines, opens)
        assert f"{says}{note}" in under, (label, opens, under)
        shown.append(f"{says}{note}")
    assert [line for line in lines if line.startswith("- note")] == shown, label


@pytest.mark.parametrize("label", list(LABELS))
def test_a_run_with_no_note_gains_no_line(tmp_path: Path, label: str) -> None:
    store = copy(STORE_1_0, tmp_path)
    lines = _report(store, STORE_1_0, label, tmp_path)
    assert not [line for line in lines if line.startswith("- note")], label


@pytest.mark.parametrize("stored", ["two\nlines", "a\ttab", "   ", "x" * 201, 7])
def test_a_note_prove_reads_as_none_shows_nothing(tmp_path: Path, stored: object) -> None:
    store = copy(STORE_1_2, tmp_path)
    manifest = store / RUNS[STORE_1_2][1] / "manifest.json"
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    doc["note"] = stored
    manifest.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    lines = _report(store, STORE_1_2, "where", tmp_path)
    assert not [line for line in lines if line.startswith("- note")], lines[:30]


def test_the_note_is_trimmed_as_prove_reads_it(tmp_path: Path) -> None:
    store = copy(STORE_1_2, tmp_path)
    manifest = store / RUNS[STORE_1_2][1] / "manifest.json"
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    doc["note"] = f"  {NOTES[1]}  "
    manifest.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    assert f"- note: {NOTES[1]}" in _under(_report(store, STORE_1_2, "where", tmp_path), "- run: ")


def test_the_html_report_shows_the_note(tmp_path: Path) -> None:
    store = copy(STORE_1_2, tmp_path)
    html = api.where(str(store), NAMES[1], event=EVENT[1:]).to_html()
    assert NOTES[1] in html
