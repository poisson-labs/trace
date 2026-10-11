"""Choices about names and runs that the frozen tests leave to the build, pinned where a
plausible wrong build would harm a user.

- A names file that gives one run two names of yours is refused by every verb, with the
  command that takes one back on its own next line; that command runs as written, and after
  it the other name still reaches the run. One wrong build reads such a file and picks a name
  silently; another refuses it in ``name`` too, so the command it points to can never run.
- ``name RUN --forget`` on a run with no name of yours is refused, and makes no names file.
  The wrong build reports a name forgotten and writes an empty file into the store.
- A names file holding a name no command could give back to a verb (``latest``, a name
  beginning ``#``) is refused, naming the file. The wrong build reads it, so the listing and
  every next: line call the run ``latest``, a word that reaches another run.
- ``runs --event`` with a name no listed run carries is refused, naming the outcomes the runs
  do carry. The wrong build lists every run with 0 failed, which reads as a clean store.
- A run whose record Prove cannot read does not stop the other runs being named and read:
  ``runs`` lists the rest with a note naming it, and every verb takes the others. The wrong
  build lets the failure through, so one damaged run makes every verb an unexpected failure.
- ``where`` on a run with no traces points next: at the fix check on the run before it and
  this one, which reads outcomes alone. The wrong build points at ``compare``, which reads
  traces and refuses those two runs whatever ceiling is given.
- Ctrl-C under ``--json`` stops an import with one JSON document, verdict ``stopped``. The
  wrong build prints the stopped line as text, and stdout is not JSON.
- A name holding a line separator a terminal or a listing breaks at (U+2028, U+2029) is
  refused as a name of two lines. The wrong build checks the newline and the control
  characters alone, and takes it, so the listing and next: lines break in two.
- A names file whose value is a number is refused even when the number is a run's id (an
  import named with digits). The wrong build reads the number as text, which the frozen
  test's number cannot show: it names no run, so the file is refused as stale either way.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from proofload.store import Store

from tf0_support import chdir, deepeval_import, trace, trace_import
from tf1_support import (
    NAMES_FILE, T_A, T_B, T_NAMES, R, import_he, make_runs, name, next_line, refused, resolved,
    runs_json, shell_words, stamp, tau2_copy, write_names,
)


def test_two_names_for_one_run_are_refused_and_the_next_line_takes_one_back(tmp_path: Path) -> None:
    tau2_copy(tmp_path)
    store = tmp_path / "proofload-runs"
    # written by hand: name never gives one run two names
    (store / NAMES_FILE).write_text(f'version = 1\n\n[names]\n"first" = "{T_B}"\n"second" = "{T_B}"\n', encoding="utf-8")
    with chdir(tmp_path):
        result = trace(["where", "first", "--store", "proofload-runs", "--event", "unsolved"])
        line = refused(result)
        assert NAMES_FILE in line, line
        nexts = [n[len("  next: "):] for n in result.lines()[1:]]
        assert len(nexts) == 1, result.err
        words = shell_words(nexts[0])
        assert words[:2] == ["poisson-trace", "name"] and "--forget" in words, nexts
        assert trace(words[1:]).code == 0
        kept = trace(["where", "first", "--store", "proofload-runs", "--event", "unsolved", "--json"])
    assert kept.code == 0, kept.text
    assert kept.json()["run"]["run_id"] == T_B


def test_forget_on_a_run_with_no_name_of_yours_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    refused(name(store, T_B, "--forget"))
    assert not (store / NAMES_FILE).exists()
    assert name(store, T_A, "selecting").code == 0
    before = (store / NAMES_FILE).read_bytes()
    refused(name(store, T_B, "--forget"))
    assert (store / NAMES_FILE).read_bytes() == before


@pytest.mark.parametrize("held", ["latest", "#1"])
def test_a_name_no_command_could_give_back_is_refused_in_the_file(tmp_path: Path, held: str) -> None:
    store = tau2_copy(tmp_path)
    write_names(store, {held: T_A})
    for argv in (["runs", "--store", str(store)], ["where", T_NAMES[T_B], "--store", str(store), "--event", "unsolved"]):
        line = refused(trace(argv))
        assert NAMES_FILE in line, line


def test_runs_refuses_an_event_no_listed_run_carries(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    result = trace(["runs", "--store", str(store), "--event", "unsolvd"])
    line = refused(result)
    assert "unsolvd" in line and "unsolved" in line, line
    # one event the runs carry is enough: the other counts nothing on every row
    doc = runs_json(store, "--event", "unsolved", "--event", "unsolvd")
    assert [r["failed"] for r in doc["runs"]] == [3, 112, 110]


def test_a_run_prove_cannot_read_does_not_stop_the_others(tmp_path: Path) -> None:
    store = make_runs(tmp_path / "store", [R("good-old", stamp(3, 9)), R("good-new", stamp(3, 10)), R("damaged", stamp(3, 11))])
    # written by hand: a record Prove would never write
    (store / "damaged" / "manifest.json").write_text("{ not json", encoding="utf-8")
    listed = trace(["runs", "--store", str(store), "--event", "fail"])
    assert listed.code == 0, listed.text
    notes = [line for line in listed.lines() if line.startswith("note: ")]
    assert len(notes) == 1 and "damaged" in notes[0], listed.err
    assert [r["run_id"] for r in runs_json(store, "--event", "fail")["runs"]] == ["good-new", "good-old"]
    assert resolved(store, "latest") == "good-new"
    assert resolved(store, "agent-x 2026-10-03 a") == "good-old"
    # the damaged run is still reached by its id, and refused when it is read
    assert refused(trace(["where", "damaged", "--store", str(store), "--event", "fail"]))


def test_where_on_a_run_with_no_traces_points_at_the_fix_check(tmp_path: Path) -> None:
    with chdir(tmp_path):
        assert import_he("store", "he-a").code == 0
        assert import_he("store", "he-b", "b").code == 0
        result = trace(["where", "he-b", "--store", "store", "--event", "missed"])
        assert result.code == 0, result.text
        words = shell_words(next_line(result))
        ceiling = {"fix-check": ["--max-mde", "0.05"], "compare": ["--max-mde-hr", "2"]}.get(words[1], [])
        followed = trace([*words[1:], *ceiling])
    assert words[1:4] == ["fix-check", "he-a", "he-b"], words
    assert followed.code == 0, followed.text


def test_ctrl_c_under_json_stops_an_import_with_one_json_document(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def stop(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(Store, "append", stop)
    result = trace_import([*deepeval_import(tmp_path / "store", "he-a"), "--json"])
    assert result.code == 130, result.text
    doc = json.loads(result.out)
    assert list(doc)[:3] == ["schema", "verdict", "sentence"], doc
    assert (doc["schema"], doc["verdict"]) == ("poisson-trace.import/1", "stopped")
    assert "he-a" in doc["sentence"], doc


def test_a_number_in_the_names_file_is_refused_even_when_it_is_a_runs_id(tmp_path: Path) -> None:
    store = tmp_path / "store"
    assert import_he(store, "20260915").code == 0
    # written by hand: name writes every value as a string
    (store / NAMES_FILE).write_text('version = 1\n\n[names]\n"old" = 20260915\n', encoding="utf-8")
    for argv in (["runs", "--store", str(store)], ["where", "old", "--store", str(store), "--event", "missed"]):
        line = refused(trace(argv))
        assert NAMES_FILE in line, line


@pytest.mark.parametrize("separator", ["\u2028", "\u2029"], ids=["line separator", "paragraph separator"])
def test_a_name_holding_a_line_separator_is_refused(tmp_path: Path, separator: str) -> None:
    store = tau2_copy(tmp_path)
    refused(name(store, T_B, f"one{separator}two"))
    assert not (store / NAMES_FILE).exists()
