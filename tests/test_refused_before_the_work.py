"""PB5-1 to PB5-6: what a command would refuse about where it writes is refused before it does its
work.

Checked late, a counting verb reads the store, counts and runs its bootstrap, and only then
looks at the path ``--out`` or ``--svg`` names; with both given, the picture is written before
``--out`` is looked at. An import reads every file, or pulls a whole experiment from its
service, and only then finds that the store already holds a run of that name or that
``store.json`` is not a descriptor. The rule these tests hold:

1. **The counting verbs.** ``--out DIR`` and ``--svg FILE`` are checked before any run is read.
   Each refusal is the sentence the command gives for that fault, word for word.
2. **The import.** The run's name, against the names the store's runs answer to, and the
   store's ``store.json``, are checked before any file is read and before any pull. Each refusal
   is the sentence the import gives for that fault. A name the store itself holds is among them:
   an import of files refuses it before a file is read, and a pull refuses it
   before it asks its service anything, in the pull's own words.
3. **Not ``ui`` and ``report``.** They are not held to this: their work is quick, and nothing is
   lost when they refuse.

How a test tells an early check from a late one: beside the fault in the path, the name or the
store, each command is given something its work would stumble on first, a run word that reaches
no run, or a file that is not there. Checked early, the refusal is the path's, the name's or the
store's. For a pull, the stand-in for the service counts the requests made: none.

- PB5-1: ``--out`` is refused before any run is read, on every counting verb and for every fault.
- PB5-2: ``--svg`` is refused before the run is read, for every fault.
- PB5-3: with ``--svg`` and ``--out`` together and ``--out`` refused, no picture is written.
- PB5-4: an import whose name the store holds, or another run of the store answers to, is refused
  before its files are read, and before a pull makes a request.
- PB5-5: an import into a store whose ``store.json`` is not a descriptor, or cannot be read, is
  refused before its files are read, and before a pull makes a request.
- PB5-6: what the early checks must not do: a store that is not there yet is not made by a refused
  import, and paths that are sound are written as usual.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from prove_floor_support import EVENT, JUNIT, RUNS, STORE_1_2, copy, descriptor_file, refused_one_line, run, tree, with_descriptor

A, B = RUNS[STORE_1_2]
#: A word no run of the store answers to: reading the store to find the run is the verb's work.
NO_RUN = "no-such-run"
VERBS = {
    "where": ["where", NO_RUN, *EVENT],
    "compare": ["compare", NO_RUN, A, *EVENT, "--max-mde-hr", "1.5"],
    "fix-check": ["fix-check", NO_RUN, A, *EVENT, "--inputs", "all", "--max-mde", "0.5"],
    "changes": ["changes", NO_RUN, A, *EVENT],
}
WHERE = ["where", A, *EVENT]
not_root = pytest.mark.skipif(os.geteuid() == 0, reason="the system refuses root nothing")


def _verb(verb: str, cwd: Path, *extra: str) -> list[str]:
    return [*VERBS[verb], "--store", str(cwd / "store"), *extra]


def _only(ran: object, sentence: str) -> None:
    """One ``error:`` line, the sentence given, and under it nothing but ``next:`` lines."""
    line = refused_one_line(ran)  # type: ignore[arg-type]
    assert line == f"error: {sentence}", line


# ---------- PB5-1 ----------


@pytest.mark.parametrize("verb", list(VERBS))
def test_pb5_1_out_at_a_folder_that_is_there_is_refused_before_any_run_is_read(tmp_path: Path, verb: str) -> None:
    copy(STORE_1_2, tmp_path)
    there = tmp_path / "there"
    there.mkdir()
    (there / "mine.txt").write_text("keep\n", encoding="utf-8")
    before = tree(tmp_path)
    ran = run(_verb(verb, tmp_path, "--out", str(there)), tmp_path)
    _only(ran, f"{there} exists; add --force to replace it with the bundle")
    assert "unknown run" not in ran.err, "the store was read before the path was looked at"
    assert tree(tmp_path) == before


def test_pb5_1_out_at_a_file_is_refused_before_any_run_is_read(tmp_path: Path) -> None:
    copy(STORE_1_2, tmp_path)
    (tmp_path / "f").write_text("x\n", encoding="utf-8")
    ran = run(_verb("fix-check", tmp_path, "--out", str(tmp_path / "f")), tmp_path)
    _only(ran, f"cannot write {tmp_path / 'f'}: it is a file, not a folder for a bundle")


def test_pb5_1_out_under_a_file_is_refused_before_any_run_is_read(tmp_path: Path) -> None:
    copy(STORE_1_2, tmp_path)
    (tmp_path / "f").write_text("x\n", encoding="utf-8")
    ran = run(_verb("fix-check", tmp_path, "--out", str(tmp_path / "f" / "bundle")), tmp_path)
    _only(ran, f"cannot write {tmp_path / 'f' / 'bundle'}: {tmp_path / 'f'} is not a folder")


@not_root
def test_pb5_1_out_in_a_folder_that_cannot_be_written_to_is_refused_before_any_run_is_read(tmp_path: Path) -> None:
    copy(STORE_1_2, tmp_path)
    shut = tmp_path / "shut"
    shut.mkdir()
    mode = stat.S_IMODE(shut.stat().st_mode)
    shut.chmod(0o555)
    try:
        ran = run(_verb("fix-check", tmp_path, "--out", str(shut / "bundle")), tmp_path)
    finally:
        shut.chmod(mode)
    _only(ran, f"cannot write {shut / 'bundle'}: the folder {shut} cannot be written to")


# ---------- PB5-2 ----------


def test_pb5_2_svg_in_a_folder_that_is_not_there_is_refused_before_the_run_is_read(tmp_path: Path) -> None:
    copy(STORE_1_2, tmp_path)
    path = tmp_path / "no-such-dir" / "c.svg"
    ran = run(_verb("where", tmp_path, "--svg", str(path)), tmp_path)
    _only(ran, f"cannot write {path}: the folder {path.parent} does not exist")
    assert "unknown run" not in ran.err, "the store was read before the path was looked at"


def test_pb5_2_svg_at_a_folder_is_refused_before_the_run_is_read(tmp_path: Path) -> None:
    copy(STORE_1_2, tmp_path)
    (tmp_path / "d").mkdir()
    ran = run(_verb("where", tmp_path, "--svg", str(tmp_path / "d")), tmp_path)
    _only(ran, f"cannot write {tmp_path / 'd'}: it is a folder")


def test_pb5_2_svg_under_a_file_is_refused_before_the_run_is_read(tmp_path: Path) -> None:
    copy(STORE_1_2, tmp_path)
    (tmp_path / "f").write_text("x\n", encoding="utf-8")
    ran = run(_verb("where", tmp_path, "--svg", str(tmp_path / "f" / "c.svg")), tmp_path)
    _only(ran, f"cannot write {tmp_path / 'f' / 'c.svg'}: the folder {tmp_path / 'f'} is not a folder")


def test_pb5_2_svg_at_a_file_that_is_there_is_refused_before_the_run_is_read(tmp_path: Path) -> None:
    copy(STORE_1_2, tmp_path)
    (tmp_path / "c.svg").write_text("mine\n", encoding="utf-8")
    ran = run(_verb("where", tmp_path, "--svg", str(tmp_path / "c.svg")), tmp_path)
    _only(ran, f"{tmp_path / 'c.svg'} exists; add --force to replace it")
    assert (tmp_path / "c.svg").read_text(encoding="utf-8") == "mine\n"


@not_root
def test_pb5_2_svg_in_a_folder_that_cannot_be_written_to_is_refused_before_the_run_is_read(tmp_path: Path) -> None:
    copy(STORE_1_2, tmp_path)
    shut = tmp_path / "shut"
    shut.mkdir()
    mode = stat.S_IMODE(shut.stat().st_mode)
    shut.chmod(0o555)
    try:
        ran = run(_verb("where", tmp_path, "--svg", str(shut / "c.svg")), tmp_path)
    finally:
        shut.chmod(mode)
    _only(ran, f"cannot write {shut / 'c.svg'}: the folder {shut} cannot be written to")


# ---------- PB5-3 ----------


def test_pb5_3_with_svg_and_out_and_out_refused_no_picture_is_written(tmp_path: Path) -> None:
    store = copy(STORE_1_2, tmp_path)
    there = tmp_path / "there"
    there.mkdir()
    before = tree(tmp_path)
    ran = run([*WHERE, "--store", str(store), "--svg", str(tmp_path / "c.svg"), "--out", str(there)], tmp_path)
    _only(ran, f"{there} exists; add --force to replace it with the bundle")
    assert not (tmp_path / "c.svg").exists(), "the picture was written before --out was looked at"
    assert tree(tmp_path) == before


# ---------- PB5-4 ----------

NO_FILE = "no-such-file.xml"


def _import(store: Path, name: str) -> list[str]:
    return ["import", "junit", NO_FILE, "--store", str(store), "--run", name]


@pytest.mark.parametrize("command", ["trace", "import"])
def test_pb5_4_a_name_the_store_holds_is_refused_before_a_file_is_read(tmp_path: Path, command: str) -> None:
    store = copy(STORE_1_2, tmp_path)
    before = tree(tmp_path)
    words = _import(store, A)
    ran = run(words if command == "trace" else words[1:], tmp_path, command)
    _only(ran, f"the store at {store} already holds a run named {A}; an import writes a new run and never adds to one, "
               "so give this one another name")
    assert tree(tmp_path) == before


def test_pb5_4_a_name_a_run_answers_to_is_refused_before_a_file_is_read(tmp_path: Path) -> None:
    store = copy(STORE_1_2, tmp_path)
    ran = run(_import(store, "agent before"), tmp_path)
    line = refused_one_line(ran, f'the store at {store} already has a run that answers to "agent before"',
                            "an import's name is the word for its run, so give this one another name")
    assert NO_FILE not in line


def test_pb5_4_a_name_a_run_answers_to_is_refused_before_a_pull_makes_a_request(tmp_path: Path) -> None:
    """A pull refuses a name the store holds before it asks its service anything, in words of its own
    (``... so pull under another name. Nothing was asked of LangSmith``). A name another run answers to is
    refused before the pull too, not once the experiment is pulled and read."""
    from signals_support import run_import
    from langsmith_support import address, by_status, export, imported, ls_argv, pulling, refused

    from poisson_trace import api

    store = tmp_path / "st"
    imported(by_status(export("baseline", "v2"), store, "held"))
    api.name(str(store), "held", "shipped")
    before = tree(tmp_path)
    with pulling() as (transport, waits):
        line = refused(run_import(ls_argv(address("candidate"), store, "shipped")))
        again = refused(run_import(ls_argv(address("candidate"), store, "held")))
    assert line.startswith(f'error: the store at {store} already has a run that answers to "shipped" (a name you gave of '), line
    assert line.endswith("; an import's name is the word for its run, so give this one another name"), line
    assert again == (f"error: the store {store} already holds a run named held; an import writes a new run and never adds to one, "
                     "so pull under another name. Nothing was asked of LangSmith")
    assert transport.calls == [] and waits == [], "the service was asked before the name was looked at"
    assert tree(tmp_path) == before


# ---------- PB5-5 ----------


def test_pb5_5_a_store_json_that_is_not_a_descriptor_is_refused_before_a_file_is_read(tmp_path: Path) -> None:
    store = with_descriptor(STORE_1_2, tmp_path, "{not json\n")
    before = tree(tmp_path)
    ran = run(_import(store, "new"), tmp_path)
    _only(ran, f"{descriptor_file(store)} is not a store descriptor (JSONDecodeError); nothing was written")
    assert tree(tmp_path) == before


@not_root
def test_pb5_5_a_store_json_that_cannot_be_read_is_refused_before_a_file_is_read(tmp_path: Path) -> None:
    store = copy(STORE_1_2, tmp_path)
    file = descriptor_file(store)
    mode = stat.S_IMODE(file.stat().st_mode)
    file.chmod(0)
    try:
        ran = run(_import(store, "new"), tmp_path)
    finally:
        file.chmod(mode)
    _only(ran, f"cannot read {file} (Permission denied); nothing was written")


def test_pb5_5_a_store_json_that_is_not_a_descriptor_is_refused_before_a_pull_makes_a_request(tmp_path: Path) -> None:
    from signals_support import run_import
    from langsmith_support import address, by_status, export, imported, ls_argv, pulling, refused

    store = tmp_path / "st"
    imported(by_status(export("baseline", "v2"), store, "held"))
    descriptor_file(store).write_text("[]\n", encoding="utf-8")
    before = tree(tmp_path)
    with pulling() as (transport, waits):
        line = refused(run_import(ls_argv(address("candidate"), store, "new")))
    assert line == f"error: {descriptor_file(store)} is not a store descriptor (not a JSON object); nothing was written"
    assert transport.calls == [] and waits == [], "the service was asked before the store was looked at"
    assert tree(tmp_path) == before


# ---------- PB5-6 ----------


def test_pb5_6_a_refused_import_does_not_make_the_store_it_names(tmp_path: Path) -> None:
    tmp_path.joinpath("work").mkdir()
    ran = run(_import(tmp_path / "work" / "new-store", "new"), tmp_path / "work")
    refused_one_line(ran, NO_FILE)
    assert tree(tmp_path / "work") == {} and not (tmp_path / "work" / "new-store").exists()


def test_pb5_6_an_import_into_a_store_that_is_not_there_yet_is_written(tmp_path: Path) -> None:
    store = tmp_path / "new-store"
    ran = run(["import", "junit", str(JUNIT), "--store", str(store), "--run", "suite"], tmp_path)
    assert ran.code == 0, ran.text
    assert (store / "suite" / "manifest.json").is_file() and descriptor_file(store).is_file()


def test_pb5_6_sound_paths_are_written_as_before(tmp_path: Path) -> None:
    store = copy(STORE_1_2, tmp_path)
    there = tmp_path / "there"
    there.mkdir()
    (tmp_path / "c.svg").write_text("old\n", encoding="utf-8")
    ran = run([*WHERE, "--store", str(store), "--svg", str(tmp_path / "c.svg"), "--out", str(there), "--force"], tmp_path)
    assert ran.code == 0, ran.text
    assert (tmp_path / "c.svg").read_text(encoding="utf-8").startswith("<svg") and (there / "handover.json").is_file()
