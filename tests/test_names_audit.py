"""Faults in the names code, each held where the wrong build goes wrong (the code without the
fix, which every test here fails on):

- a name with a byte the command line could not read as UTF-8 is refused, where the wrong build
  ends in a traceback the errors log cannot hold;
- ``#`` and a number too long to read as one is past the last row, where the wrong build fails
  unexpectedly;
- the import refuses the names file's own name as a run name, where in the wrong build a run of
  that name makes the store unreadable to every verb;
- a run whose start, read as UTC, falls outside the years 1 to 9999 is set aside like one with
  no start, where the wrong build fails unexpectedly on every verb;
- a names file nested too deep for a reader is refused as not a names file, where the wrong
  build fails unexpectedly;
- a ``next:`` command gives a run by a word that reaches it alone, where the wrong build gives a
  name two runs answer to, so the command is refused;
- ``runs`` lists every run it can read when the rows of one cannot be read, where the wrong
  build refuses the listing whole;
- a run whose target would give a name no verb could take back goes by its id, where the wrong
  build lists it under a name that reaches no run;
- a control character in a name is refused, and shown escaped in the refusal, where the wrong
  build takes it and prints it raw to the terminal;
- a ``next:`` command keeps a store that begins with a dash as the store's value, where the
  wrong build reads it as an option;
- an entry of the names file that cannot be a name is taken back by the command its refusal
  gives, where in the wrong build no command can remove it;
- the fix check reads a start with no zone as UTC beside one with a zone, where the wrong build
  fails unexpectedly.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from look_support import chdir, ragas_import, trace, trace_import
from names_support import (
    NAMES_FILE, T_B, R, make_runs, name, next_line, refused, resolved, runs_json, shell_words, stamp,
    tau2_copy,
)


def _no_failure(result) -> None:  # type: ignore[no-untyped-def]
    assert result.code in (0, 1, 2), result.text
    assert "Traceback" not in result.text and "unexpected failure" not in result.text, result.text


def test_a_name_that_is_not_text_is_refused(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    for text in ("b\udcff", "red\x1b[31mX\x07"):
        result = name(store, "latest", text)
        line = refused(result)
        assert "\x1b" not in result.err and "\x07" not in result.err, result.err
        _no_failure(result)
        assert line.startswith("error: ")
    assert not (store / NAMES_FILE).exists()


def test_a_row_number_too_long_to_read_is_past_the_last_row(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    result = trace(["where", "#" + "9" * 5000, "--store", str(store), "--event", "unsolved"])
    refused(result)
    _no_failure(result)


def test_the_import_refuses_the_names_files_name(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    for run in (NAMES_FILE, NAMES_FILE + ".partial"):
        refused(trace_import(ragas_import(store, run)))
        assert not (store / NAMES_FILE).exists() and not (store / (NAMES_FILE + ".partial")).exists()
    assert trace(["runs", "--store", str(store)]).code == 0


def test_a_start_outside_the_years_in_utc_is_set_aside(tmp_path: Path) -> None:
    store = make_runs(tmp_path / "store", [R("early", "0001-01-01T00:30:00+01:00"), R("good", stamp(3, 10))])
    for argv in (["runs", "--store", str(store), "--event", "fail"], ["where", "latest", "--store", str(store), "--event", "fail"]):
        result = trace(argv)
        _no_failure(result)
        assert result.code == 0, result.text
    assert resolved(store, "latest") == "good"


def test_a_names_file_nested_too_deep_is_not_a_names_file(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    (store / NAMES_FILE).write_text("version = 1\nx = " + "[" * 3000 + "]" * 3000 + "\n", encoding="utf-8")
    result = trace(["runs", "--store", str(store)])
    assert NAMES_FILE in refused(result)
    _no_failure(result)


def test_next_gives_each_run_by_a_word_that_reaches_it_alone(tmp_path: Path) -> None:
    store = make_runs(tmp_path / "store", [R("old", stamp(3, 10))])
    # a name of yours given before a run that is later named so from its manifest
    assert name(store, "old", "agent-x 2026-10-04 a").code == 0
    make_runs(store, [R("new", stamp(4, 10))])
    with chdir(tmp_path):
        command = next_line(trace(["where", "new", "--store", "store", "--event", "fail"]))
        words = shell_words(command)
        assert [resolved("store", w) for w in words[2:4]] == ["old", "new"], command


def test_runs_lists_the_others_when_one_runs_rows_cannot_be_read(tmp_path: Path) -> None:
    store = make_runs(tmp_path / "store", [R("a", stamp(3, 10)), R("b", stamp(3, 11))])
    # written by hand: a part Prove would never write
    for part in (store / "b" / "episodes").iterdir():
        part.write_bytes(b"not parquet")
    result = trace(["runs", "--store", str(store), "--event", "fail"])
    assert result.code == 0, result.text
    assert [r["run_id"] for r in runs_json(store, "--event", "fail")["runs"]] == ["a"]
    assert any(line.startswith("note: ") and "b" in line for line in result.lines()), result.err


def test_a_target_that_gives_no_name_a_verb_could_take_goes_by_its_id(tmp_path: Path) -> None:
    store = make_runs(tmp_path / "store", [
        R("hash", stamp(5, 10), target_id="#1/x"), R("spaced", stamp(5, 11), target_id=" tau2/x"),
        R("empty", stamp(5, 12), target_id="/model"),
    ])
    rows = runs_json(store, "--event", "fail")["runs"]
    for row in rows:
        assert resolved(store, row["name"]) == row["run_id"], row


def test_a_store_that_begins_with_a_dash_stays_the_stores_value(tmp_path: Path) -> None:
    shutil.copytree(tau2_copy(tmp_path), tmp_path / "-dash")
    with chdir(tmp_path):
        command = next_line(trace(["runs", "--store=-dash", "--event", "unsolved"]))
        assert trace(shell_words(command)[1:]).code == 0, command


def test_an_entry_that_cannot_be_a_name_is_taken_back_by_the_command_given(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    (store / NAMES_FILE).write_text(f'version = 1\n\n[names]\n"-old" = "{T_B}"\n', encoding="utf-8")
    with chdir(tmp_path):
        result = trace(["runs", "--store", store.name])
        refused(result)
        nexts = [line[len("  next: "):] for line in result.lines()[1:]]
        assert len(nexts) == 1, result.err
        assert trace(shell_words(nexts[0])[1:]).code == 0, nexts
        assert trace(["runs", "--store", store.name]).code == 0


def test_a_start_with_no_zone_is_read_as_utc_beside_one_with_a_zone(tmp_path: Path) -> None:
    store = make_runs(tmp_path / "store", [R("naive", "2026-10-03T23:30:00"), R("aware", "2026-10-04T03:30:00+02:00")])
    result = trace(["fix-check", "naive", "aware", "--store", str(store), "--event", "fail", "--inputs", "all", "--max-mde", "0.5", "--json"])
    _no_failure(result)
    assert result.json()["gap_seconds"] == 7200.0

