"""TF1-1 to TF1-3: the names file beside the runs, the reader that refuses a damaged one, and the
name every run has from its manifest (spec section 5.2, ruling R3).

``poisson-trace name`` writes ``trace-names.toml`` at the store root, in the spec's form byte for
byte, entries sorted by name, any name a user can type kept whole. Every verb that reads names
refuses a file that is not one, in one line naming the file. A run with no entry is named from
its manifest: the target up to its first ``/``, the day it started in UTC, and a letter in
start order among the runs that would otherwise share that name, partial runs included. An
imported run is named by the name it was imported under. Names are read through the commands
only: ``runs --json`` for the name each run has, ``where --json`` for the run a name reaches."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tf0_support import run_sub, trace
from tf1_support import (
    NAMES_FILE, T_A, T_B, T_NAMES, T_PILOT, R, VERBS_THAT_READ_NAMES, import_he, make_runs, name,
    names_file, refused, resolved, run_id, runs_json, stamp, tau2_copy, write_names,
)

# ---------- TF1-1: the file ----------

SPEC_FILE = (
    "# Poisson Trace: your names for the runs in this store. Written by `poisson-trace name`.\n"
    "version = 1\n"
    "\n"
    "[names]\n"
    '"tau2 old re-run" = "20260915T211148Z-965d"\n'
    '"tau2 selecting run" = "20260915T210140Z-4847"\n'
)


def test_tf1_01_the_names_file_is_the_spec_form_byte_for_byte(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    # named in the other order from the file's: the entries are sorted by name
    assert name(store, T_A, "tau2 selecting run").code == 0
    assert name(store, T_B, "tau2 old re-run").code == 0
    assert (store / NAMES_FILE).read_bytes() == SPEC_FILE.encode("utf-8")


AWKWARD = {
    "quote": 'he said "ship it"',
    "backslash": "C:\\runs\\old",
    "equals and hash": "a = b # not a comment",
    "letters outside ASCII": "café crème ✓",
    "tab": "two\tparts",
    "dollar and backtick": "cost $5 `now`",
}


def test_tf1_01_any_name_a_user_types_is_kept_whole(tmp_path: Path) -> None:
    runs = [R(run_id(1, 9 + i, 0, f"{i:04x}"), stamp(1, 9 + i)) for i in range(len(AWKWARD))]
    store = make_runs(tmp_path / "store", runs)
    for r, text in zip(runs, AWKWARD.values(), strict=True):
        result = name(store, r.run_id, text)
        assert result.code == 0, result.text
    # read back by a TOML reader, every name is the text given, and each reaches its run
    assert names_file(store) == {"version": 1, "names": {text: r.run_id for r, text in zip(runs, AWKWARD.values(), strict=True)}}
    for r, text in zip(runs, AWKWARD.values(), strict=True):
        assert resolved(store, text) == r.run_id, text


# ---------- TF1-2: a file that is not a names file ----------


def _hand_written(store: Path, text: str) -> None:
    """A names file written by hand, as ``name`` would never write it."""
    (store / NAMES_FILE).write_text(text, encoding="utf-8")


DAMAGED = {
    "not TOML": 'version = 1\n[names\n"x" = "y"\n',
    "an unknown key": f'version = 1\ncolour = "red"\n\n[names]\n"old" = "{T_B}"\n',
    "an unknown table": f'version = 1\n\n[names]\n"old" = "{T_B}"\n\n[extra]\nx = 1\n',
    "a newer version": f'version = 2\n\n[names]\n"old" = "{T_B}"\n',
    "names that is not a table": 'version = 1\nnames = "old"\n',
    "no version": f'[names]\n"old" = "{T_B}"\n',
    "a value that is not a string": 'version = 1\n\n[names]\n"old" = 20260915\n',
    "two names that trim to one": f'version = 1\n\n[names]\n"old" = "{T_B}"\n" old " = "{T_A}"\n',
    "a name for a run the store does not hold": 'version = 1\n\n[names]\n"gone" = "20260101T000000Z-dead"\n',
}


def _argv(verb: str, store: Path) -> list[str]:
    s = str(store)
    return {
        "where": ["where", T_A, "--store", s, "--event", "unsolved"],
        "compare": ["compare", T_A, T_B, "--store", s, "--event", "unsolved", "--max-mde-hr", "1.5"],
        "fix-check": ["fix-check", T_A, T_B, "--store", s, "--event", "unsolved", "--inputs", "all", "--max-mde", "0.2"],
        "changes": ["changes", T_A, T_B, "--store", s, "--event", "unsolved"],
        "runs": ["runs", "--store", s],
        "name": ["name", T_PILOT, "pilot", "--store", s],
    }[verb]


@pytest.mark.parametrize("verb", VERBS_THAT_READ_NAMES)
@pytest.mark.parametrize("damage", DAMAGED, ids=list(DAMAGED))
def test_tf1_02_a_damaged_names_file_is_refused_naming_the_file(tmp_path: Path, damage: str, verb: str) -> None:
    store = tau2_copy(tmp_path)
    _hand_written(store, DAMAGED[damage])
    before = (store / NAMES_FILE).read_bytes()
    if verb == "name" and damage == "a name for a run the store does not hold":
        pytest.skip("name reads a stale entry to let it be forgotten (TF1-6)")
    line = refused(trace(_argv(verb, store)))
    assert NAMES_FILE in line, line
    assert (store / NAMES_FILE).read_bytes() == before


def test_tf1_02_a_stale_entry_names_itself_and_the_way_to_forget_it(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    _hand_written(store, DAMAGED["a name for a run the store does not hold"])
    result = trace(_argv("where", store))
    refused(result)
    assert '"gone"' in result.err or " gone " in result.err, result.err
    assert "--forget" in result.err, result.err


def test_tf1_02_a_name_in_the_file_is_read_trimmed(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    _hand_written(store, f'version = 1\n\n[names]\n"  padded name  " = "{T_B}"\n')
    assert resolved(store, "padded name", "unsolved") == T_B
    rows = {r["run_id"]: r for r in runs_json(store)["runs"]}
    assert rows[T_B]["name"] == "padded name" and rows[T_B]["named_by"] == "you"


# ---------- TF1-3: the name from the manifest ----------


def test_tf1_03_every_tau2_run_is_named_from_its_manifest(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    rows = runs_json(store)["runs"]
    assert {r["run_id"]: r["name"] for r in rows} == T_NAMES
    assert {r["named_by"] for r in rows} == {"manifest"}
    for run, computed in T_NAMES.items():
        assert resolved(store, computed, "unsolved") == run


def _names(store: Path) -> dict[str, str]:
    return {r["run_id"]: r["name"] for r in runs_json(store, "--all")["runs"]}


def test_tf1_03_letters_follow_the_start_time_not_the_id(tmp_path: Path) -> None:
    # the ids sort the other way round from the start times
    runs = [R("zz-first", stamp(1, 9)), R("mm-second", stamp(1, 10)), R("aa-third", stamp(1, 11, 30))]
    store = make_runs(tmp_path / "store", runs)
    assert _names(store) == {"zz-first": "agent-x 2026-10-01 a", "mm-second": "agent-x 2026-10-01 b", "aa-third": "agent-x 2026-10-01 c"}


def test_tf1_03_letters_go_on_past_z_as_aa_ab(tmp_path: Path) -> None:
    runs = [R(run_id(2, 0, i, f"{i:04x}"), stamp(2, 0, i), rows=("ok",), traced=False) for i in range(28)]
    store = make_runs(tmp_path / "store", runs)
    letters = [chr(ord("a") + i) for i in range(26)] + ["aa", "ab"]
    assert _names(store) == {r.run_id: f"agent-x 2026-10-02 {letter}" for r, letter in zip(runs, letters, strict=True)}


def test_tf1_03_a_partial_run_takes_its_letter(tmp_path: Path) -> None:
    runs = [R("r1", stamp(1, 9)), R("r2", stamp(1, 10), status="partial"), R("r3", stamp(1, 11))]
    store = make_runs(tmp_path / "store", runs)
    assert _names(store) == {"r1": "agent-x 2026-10-01 a", "r2": "agent-x 2026-10-01 b", "r3": "agent-x 2026-10-01 c"}


def test_tf1_03_each_target_and_each_day_letters_from_a(tmp_path: Path) -> None:
    runs = [
        R("x1", stamp(1, 9)), R("y1", stamp(1, 10), target_id="agent-y"), R("x2", stamp(1, 11)),
        R("x3", stamp(2, 8)), R("y2", stamp(2, 9), target_id="agent-y/m@v1"),
    ]
    store = make_runs(tmp_path / "store", runs)
    assert _names(store) == {
        "x1": "agent-x 2026-10-01 a", "y1": "agent-y 2026-10-01 a", "x2": "agent-x 2026-10-01 b",
        "x3": "agent-x 2026-10-02 a", "y2": "agent-y 2026-10-02 a",
    }


def test_tf1_03_two_targets_that_share_a_name_share_its_letters(tmp_path: Path) -> None:
    """Two models of one agent, the same day: the names stay apart, so neither is refused as
    ambiguous."""
    runs = [
        R("m1", stamp(3, 9), target_id="tau2-airline/gpt-4.1-mini@v0"),
        R("m2", stamp(3, 10), target_id="tau2-airline/gpt-4o@v0"),
    ]
    store = make_runs(tmp_path / "store", runs)
    assert _names(store) == {"m1": "tau2-airline 2026-10-03 a", "m2": "tau2-airline 2026-10-03 b"}
    assert resolved(store, "tau2-airline 2026-10-03 b") == "m2"


@pytest.mark.parametrize("zone", ["Pacific/Kiritimati", "America/Los_Angeles"])
def test_tf1_03_the_day_is_the_utc_day_in_any_time_zone(tmp_path: Path, zone: str) -> None:
    store = tau2_copy(tmp_path)
    env = dict(os.environ)
    env["TZ"] = zone
    result = run_sub("trace", ["runs", "--store", str(store), "--json"], env=env)
    assert result.code == 0, result.text
    assert {r["run_id"]: r["name"] for r in result.json()["runs"]} == T_NAMES


def test_tf1_03_an_imported_run_is_named_by_its_import_name(tmp_path: Path) -> None:
    store = tmp_path / "store"
    assert import_he(store, "before the fix").code == 0
    assert import_he(store, "after the fix", "b").code == 0
    rows = {r["run_id"]: r for r in runs_json(store)["runs"]}
    assert {k: (v["name"], v["named_by"], v["backend"]) for k, v in rows.items()} == {
        "before the fix": ("before the fix", "you", "import:deepeval"),
        "after the fix": ("after the fix", "you", "import:deepeval"),
    }


def test_tf1_03_a_run_of_prove_is_named_from_its_manifest_whatever_its_id(tmp_path: Path) -> None:
    store = make_runs(tmp_path / "store", [R("baseline", stamp(4, 12))])
    assert _names(store) == {"baseline": "agent-x 2026-10-04 a"}


def test_tf1_03_a_run_you_named_still_answers_to_its_name_from_the_manifest(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    write_names(store, {"old re-run": T_B})
    assert resolved(store, "old re-run", "unsolved") == T_B
    assert resolved(store, T_NAMES[T_B], "unsolved") == T_B
    rows = {r["run_id"]: r for r in runs_json(store)["runs"]}
    assert (rows[T_B]["name"], rows[T_B]["named_by"]) == ("old re-run", "you")
    assert (rows[T_A]["name"], rows[T_A]["named_by"]) == (T_NAMES[T_A], "manifest")
