"""TF22-24 to TF22-32: ``compare``, ``fix-check``, ``changes`` and ``where`` given folders (spec
section 18.3.1, SG8).

A run word that reaches no stored run and names a folder is that folder. A tool folder is read
through its reader, with the reader's own flags on the verb's command line, into a store that
does not outlive the command; a Prove folder is read where it is. Outside its commands, what the
verb prints is byte for byte what it prints on the same folders imported one by one into an
empty store, each under its folder's name (TF22-24, TF22-26). The commands name each folder by
the path typed, carry no ``--store``, carry the reader's flags, and run as printed (TF22-25).
Nothing is written that stays (TF22-27). The refusals are plain, named and exit 1 (TF22-30,
TF22-31).
"""

from __future__ import annotations

import shlex
import tempfile
from pathlib import Path
from typing import Any

import pytest
from conftest import CS, TAU2
from tf22_support import (
    CS_RUNS,
    EVENTS,
    FLAGS,
    JUNIT,
    NEW,
    OLD,
    RAGAS,
    TABLE,
    TAU2_RUNS,
    Ran,
    chdir,
    commands_of,
    copy_into,
    deepeval_folder,
    json_commands,
    junit_shards,
    masked,
    masked_json,
    names,
    one_run_store,
    plain_refusal,
    ragas_parts,
    runnable,
    stores_of,
    strip_flags,
    strip_store,
    table_parts,
    trace,
    trace_import,
    tree,
    without_store,
)

# the verbs, each with its own flags and how many runs it takes
VERBS: dict[str, tuple[int, list[str]]] = {
    "fix-check": (2, ["--inputs", "all", "--max-mde", "0.2"]),
    "changes": (2, []),
    "where": (1, []),
    "compare": (2, ["--max-mde-hr", "1.5"]),
}


def _pair(tool: str, here: Path, prefix: str = "") -> tuple[Path, Path]:
    """Two folders of ``tool`` built from the committed pair, the older version first."""
    old, new = here / prefix / OLD, here / prefix / NEW
    if tool == "junit":
        junit_shards(old)  # the old version as parallel workers wrote it
        copy_into(new, JUNIT / "humaneval-b.xml")
    elif tool == "table":
        table_parts(old)
        copy_into(new, TABLE / "humaneval-b.csv")
    elif tool == "ragas":
        ragas_parts(old)
        copy_into(new, RAGAS / "rag-raft.jsonl")
    elif tool == "deepeval":
        deepeval_folder(old, "a")
        deepeval_folder(new, "b")
    else:
        raise AssertionError(tool)
    return old, new


def _files(folder: Path) -> list[Path]:
    return sorted((p for p in folder.iterdir() if p.is_file()), key=lambda p: p.name)


def _one_by_one(tool: str, folders: list[Path], store: Path) -> None:
    for folder in folders:
        ran = trace_import(tool, *_files(folder), "--store", store, "--run", folder.name, *FLAGS[tool])
        assert ran.code == 0, ran.text


def _routes(tool: str, verb: str, here: Path, form: str) -> tuple[Ran, Ran, list[str], list[str]]:
    """``(by store, by folder, run words by store, run words by folder)`` for a verb on a built
    pair, run from ``here`` with the folders typed relative to it."""
    count, own = VERBS[verb]
    old, new = _pair(tool, here)
    folders = [old, new][-count:]
    store = here / "st"
    with chdir(here):
        _one_by_one(tool, folders, Path("st"))
        extra = ["--json"] if form == "json" else ["--plain"]
        by_store = trace(verb, *[f.name for f in folders], "--store", "st", *EVENTS[tool], *own, *extra)
        before = tree(here)
        typed = [str(f.relative_to(here)) for f in folders]
        by_folder = trace(verb, *typed, *EVENTS[tool], *own, *FLAGS[tool], *extra)
        assert tree(here) == before  # TF22-27, here too
    assert store.is_dir()
    return by_store, by_folder, [f.name for f in folders], typed


def _same(by_store: Ran, by_folder: Ran, form: str) -> None:
    assert by_folder.code == by_store.code, by_folder.text + "\n---\n" + by_store.text
    if form == "json" and by_store.out:
        a, b = by_store.json(), by_folder.json()
        # the store is not one the user has: every store the JSON names is null
        assert stores_of(a) and stores_of(b) == [None] * len(stores_of(a))
        assert masked_json(without_store(b)) == masked_json(without_store(a))
    else:
        assert masked(by_folder.out) == masked(by_store.out)
    assert masked(by_folder.err) == masked(by_store.err)


# ---------- TF22-24: the same report ----------


@pytest.mark.parametrize("verb", list(VERBS))
@pytest.mark.parametrize("form", ["plain", "json"])
def test_tf22_24_a_verb_on_folders_prints_what_it_prints_on_them_imported(
    tmp_path: Path, verb: str, form: str
) -> None:
    by_store, by_folder, _, _ = _routes("junit", verb, tmp_path, form)
    _same(by_store, by_folder, form)
    if (verb, form) == ("fix-check", "json"):
        # the fast twin is not two refusals that agree: fix-check on the JUnit pair answers
        assert by_store.code == 0, by_store.text


@pytest.mark.slow
@pytest.mark.parametrize("tool", ["table", "ragas", "deepeval"])  # junit is the fast test above
@pytest.mark.parametrize("verb", list(VERBS))
@pytest.mark.parametrize("form", ["plain", "json"])
def test_tf22_24_every_tool_and_verb_prints_the_same(tmp_path: Path, tool: str, verb: str, form: str) -> None:
    by_store, by_folder, _, _ = _routes(tool, verb, tmp_path, form)
    _same(by_store, by_folder, form)


# ---------- TF22-25: the commands ----------


def _check_commands(by_store: Ran, by_folder: Ran, store_words: list[str], typed: list[str],
                    flags: list[str], here: Path, form: str) -> int:
    if form == "json" and by_store.out:
        a, b = json_commands(by_store.json()), json_commands(by_folder.json())
        a += commands_of(by_store.err)
        b += commands_of(by_folder.err)
    else:
        a, b = commands_of(by_store.text), commands_of(by_folder.text)
    assert len(a) == len(b), (a, b)
    ran = 0
    for store_cmd, folder_cmd in zip(a, b, strict=True):
        words = shlex.split(folder_cmd)
        assert "--store" not in words and not any(w.startswith("--store=") for w in words)
        expected = [typed[store_words.index(w)] if w in store_words else w
                    for w in strip_store(shlex.split(store_cmd))]
        # a command that names a folder carries the reader's flags (strip_flags asserts each)
        got = strip_flags(words, flags) if any(t in words for t in typed) else words
        assert got == expected, (folder_cmd, store_cmd)
        if runnable(folder_cmd) and words[1] in VERBS:
            with chdir(here):
                again_folder = trace(*words[1:], "--plain")
                again_store = trace(*shlex.split(store_cmd)[1:], "--plain")
            assert again_folder.code == again_store.code, again_folder.text
            ran += 1
    return ran


@pytest.mark.parametrize("verb", ["fix-check", "where", "compare"])
def test_tf22_25_the_commands_name_the_folders_and_run_as_printed(tmp_path: Path, verb: str) -> None:
    by_store, by_folder, store_words, typed = _routes("junit", verb, tmp_path, "plain")
    _check_commands(by_store, by_folder, store_words, typed, FLAGS["junit"], tmp_path, "plain")


def test_tf22_25_a_command_is_run_at_least_once(tmp_path: Path) -> None:
    by_store, by_folder, store_words, typed = _routes("junit", "changes", tmp_path, "plain")
    assert _check_commands(by_store, by_folder, store_words, typed, [], tmp_path, "plain") >= 1


def test_tf22_25_the_readers_flags_are_carried(tmp_path: Path) -> None:
    by_store, by_folder, store_words, typed = _routes("table", "changes", tmp_path, "plain")
    assert by_folder.code == 0, by_folder.text
    commands = commands_of(by_folder.text)
    assert commands
    for c in commands:
        words = shlex.split(c)
        if len(words) > 2 and words[1] in VERBS:
            strip_flags(words, FLAGS["table"])  # every reader flag is there
    _check_commands(by_store, by_folder, store_words, typed, FLAGS["table"], tmp_path, "plain")


def test_tf22_25_a_folder_is_named_by_the_path_typed(tmp_path: Path) -> None:
    old, new = _pair("junit", tmp_path, prefix="results")
    with chdir(tmp_path):
        ran = trace("changes", "results/tf22-old", "./results/tf22-new", "--event", "missed", "--plain")
    assert ran.code == 0, ran.text
    commands = [shlex.split(c) for c in commands_of(ran.out)]
    assert any("results/tf22-old" in c and "./results/tf22-new" in c for c in commands), commands


@pytest.mark.slow
@pytest.mark.parametrize("tool", ["table", "ragas", "deepeval"])
@pytest.mark.parametrize("verb", list(VERBS))
def test_tf22_25_every_tools_commands_run_as_printed(tmp_path: Path, tool: str, verb: str) -> None:
    by_store, by_folder, store_words, typed = _routes(tool, verb, tmp_path, "plain")
    _check_commands(by_store, by_folder, store_words, typed, FLAGS[tool], tmp_path, "plain")


# ---------- TF22-26: a Prove folder is read where it is ----------

PROVE_CASES: dict[str, tuple[Path, list[str], list[str], list[str]]] = {
    "where-cs": (CS, [CS_RUNS[1]], ["where"], ["--event", "unresolved"]),
    "compare-cs": (CS, list(CS_RUNS), ["compare"], ["--event", "unresolved", "--max-mde-hr", "3"]),
    "changes-tau2": (TAU2, list(TAU2_RUNS[:2]), ["changes"], ["--event", "unsolved"]),
    "fix-check-tau2": (TAU2, list(TAU2_RUNS[:2]), ["fix-check"],
                       ["--event", "unsolved", "--inputs", "all", "--max-mde", "0.3"]),
}


@pytest.mark.parametrize("case", list(PROVE_CASES))
@pytest.mark.parametrize("form", ["plain", "json"])
def test_tf22_26_a_prove_run_folder_reads_as_its_run_in_its_store(tmp_path: Path, case: str, form: str) -> None:
    store, runs, verb, own = PROVE_CASES[case]
    extra = ["--json"] if form == "json" else ["--plain"]
    before = tree(store)
    by_store = trace(*verb, *runs, "--store", store, *own, *extra)
    by_folder = trace(*verb, *[store / r for r in runs], *own, *extra)
    assert by_store.code in (0, 1), by_store.text
    if form == "json" and by_store.out:
        assert by_folder.code == by_store.code, by_folder.text
        assert stores_of(by_folder.json()) == [None] * len(stores_of(by_store.json()))
        assert masked_json(without_store(by_folder.json())) == masked_json(without_store(by_store.json()))
    else:
        _same(by_store, by_folder, form)
    assert tree(store) == before
    for c in commands_of(by_folder.text if form == "plain" else by_folder.err):
        assert "--store" not in shlex.split(c)


def test_tf22_26_a_store_of_one_run_reads_as_that_run(tmp_path: Path) -> None:
    one = one_run_store(tmp_path / "one", CS, CS_RUNS[1])
    by_store = trace("where", CS_RUNS[1], "--store", one, "--event", "unresolved", "--plain")
    by_folder = trace("where", one, "--event", "unresolved", "--plain")
    assert by_store.code == 0, by_store.text
    _same(by_store, by_folder, "plain")


# ---------- TF22-27: nothing is written that stays ----------


def test_tf22_27_a_verb_on_folders_leaves_no_file_anywhere(tmp_path: Path, monkeypatch: Any) -> None:
    here = tmp_path / "here"
    here.mkdir()
    old, new = _pair("junit", here)
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setenv("TMPDIR", str(temp))
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    before = tree(tmp_path)
    with chdir(here):
        for verb, (count, own) in VERBS.items():
            words = [OLD, NEW][-count:]
            ran = trace(verb, *words, "--event", "missed", *own, "--plain")
            assert ran.code in (0, 1), ran.text
    assert tree(tmp_path) == before
    assert list(temp.iterdir()) == []


# ---------- TF22-28: no store is needed ----------


def test_tf22_28_folders_need_no_store_and_leave_the_configs_alone(tmp_path: Path) -> None:
    here = tmp_path / "here"
    here.mkdir()
    _pair("junit", here)
    with chdir(here):
        bare = trace("changes", OLD, NEW, "--event", "missed", "--plain")
    assert bare.code == 0, bare.text
    # a trace.toml naming a store: the store is not read or written, and the report is the same
    held = one_run_store(tmp_path / "held", CS, CS_RUNS[0])
    (here / "trace.toml").write_text(f'version = 1\n\n[store]\npath = "{held}"\n', encoding="utf-8")
    before = tree(held)
    with chdir(here):
        configured = trace("changes", OLD, NEW, "--event", "missed", "--plain")
    assert configured.code == 0, configured.text
    assert masked(configured.out) == masked(bare.out)
    assert tree(held) == before


# ---------- TF22-29: a stored run's word is still the stored run ----------


def test_tf22_29_a_word_that_reaches_a_stored_run_is_that_run(tmp_path: Path) -> None:
    here = tmp_path / "here"
    here.mkdir()
    with chdir(here):
        ok = trace_import("junit", JUNIT / "humaneval-a.xml", "--store", "st", "--run", OLD)
        assert ok.code == 0, ok.text
        alone = trace("where", OLD, "--store", "st", "--event", "missed", "--plain")
        copy_into(here / OLD, JUNIT / "humaneval-b.xml")  # a folder of the same name
        beside = trace("where", OLD, "--store", "st", "--event", "missed", "--plain")
    assert alone.code == 0, alone.text
    assert (beside.code, beside.out, beside.err) == (alone.code, alone.out, alone.err)


# ---------- TF22-30 and TF22-31: refused, plain and named ----------


def _bad(kind: str, here: Path) -> Path:
    folder = here / f"bad-{kind}"
    if kind == "empty":
        folder.mkdir()
    elif kind == "two-runs":
        copy_into(folder, JUNIT / "trace-suite-1.xml", JUNIT / "trace-suite-2.xml")
    elif kind == "two-tools":
        copy_into(folder, JUNIT / "humaneval-a.xml", RAGAS / "rag-base.jsonl")
    elif kind == "store":
        import shutil

        shutil.copytree(CS, folder)
    else:
        raise AssertionError(kind)
    return folder


@pytest.mark.parametrize("kind", ["empty", "two-runs", "two-tools", "store"])
@pytest.mark.parametrize("verb", ["fix-check", "changes", "where"])
def test_tf22_30_a_folder_that_is_not_one_run_is_refused(tmp_path: Path, kind: str, verb: str) -> None:
    here = tmp_path / "here"
    here.mkdir()
    _pair("junit", here)
    bad = _bad(kind, here)
    count, own = VERBS[verb]
    words = [bad.name, NEW][-count:] if count == 2 else [bad.name]
    before = tree(here)
    with chdir(here):
        # control: the good folders in the same places are read
        good = trace(verb, *[OLD, NEW][-count:], "--event", "missed", *own, "--plain")
        ran = trace(verb, *words, "--event", "missed", *own, "--plain")
    assert good.code == 0, good.text
    sentence = plain_refusal(ran)
    assert names(sentence, bad.name, tmp=tmp_path)
    assert tree(here) == before


def test_tf22_31_two_folders_of_one_name_are_refused(tmp_path: Path) -> None:
    here = tmp_path / "here"
    copy_into(here / "a" / "results", JUNIT / "humaneval-a.xml")
    copy_into(here / "b" / "results", JUNIT / "humaneval-b.xml")
    with chdir(here):
        ran = trace("changes", "a/results", "b/results", "--event", "missed", "--plain")
    assert names(plain_refusal(ran), "a/results", "b/results")


def test_tf22_31_folders_of_two_tools_are_refused(tmp_path: Path) -> None:
    here = tmp_path / "here"
    copy_into(here / OLD, JUNIT / "humaneval-a.xml")
    copy_into(here / NEW, RAGAS / "rag-base.jsonl")
    with chdir(here):
        ran = trace("changes", OLD, NEW, "--event", "missed", *FLAGS["ragas"], "--plain")
    assert names(plain_refusal(ran), OLD, NEW, "junit", "ragas")


def test_tf22_31_a_folder_beside_a_stored_run_is_refused(tmp_path: Path) -> None:
    here = tmp_path / "here"
    here.mkdir()
    copy_into(here / NEW, JUNIT / "humaneval-b.xml")
    copy_into(here / OLD, JUNIT / "humaneval-a.xml")
    with chdir(here):
        # control: the same folder beside another folder is read
        assert trace("changes", OLD, NEW, "--event", "missed", "--plain").code == 0
        assert trace_import("junit", JUNIT / "humaneval-a.xml", "--store", "st", "--run", "stored-old").code == 0
        before = tree(here)
        ran = trace("changes", "stored-old", NEW, "--store", "st", "--event", "missed", "--plain")
    assert names(plain_refusal(ran), NEW)
    assert tree(here) == before


def test_tf22_31_a_folder_missing_its_readers_flags_is_a_wrong_command_line(tmp_path: Path) -> None:
    here = tmp_path / "here"
    here.mkdir()
    _pair("table", here)
    with chdir(here):
        ran = trace("changes", OLD, NEW, "--event", "missed", "--plain")
        given = trace("changes", OLD, NEW, "--event", "missed", *FLAGS["table"], "--plain")
    assert given.code == 0, given.text
    assert ran.code == 2, ran.text


# ---------- TF22-32: what was there before is unchanged ----------


def test_tf22_32_a_word_that_is_neither_still_reads_as_before(tmp_path: Path) -> None:
    """A word that reaches no stored run and names no folder is refused as it was before TF22."""
    here = tmp_path / "here"
    here.mkdir()
    with chdir(here):
        assert trace_import("junit", JUNIT / "humaneval-a.xml", "--store", "st", "--run", "v1").code == 0
        ran = trace("where", "no-such-run", "--store", "st", "--event", "missed", "--plain")
    assert ran.code == 1, ran.text
    assert "no-such-run" in ran.err


def test_tf22_32_unknown_flags_on_stored_runs_are_still_refused(tmp_path: Path) -> None:
    here = tmp_path / "here"
    here.mkdir()
    with chdir(here):
        assert trace_import("junit", JUNIT / "humaneval-a.xml", "--store", "st", "--run", "v1").code == 0
        ran = trace("where", "v1", "--store", "st", "--event", "missed", "--case-column", "case")
    assert ran.code == 2, ran.text
