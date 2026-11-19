"""PF-30 to PF-59: a store Trace cannot read or write safely is refused in one line (PV-9 to
PV-13; ``pf_support``'s opening, items 4 to 6).

- PF-30: every command that reads a store refuses one marked as a newer format than Trace
  knows: exit 1, nothing on stdout, one ``error:`` line naming the format found and
  ``poisson.store/1``, and the store untouched.
- PF-31: every command that writes into a store refuses such a store too, before anything is
  written: no saved verdict, no page, no name, no bundle, and the descriptor's ``writers`` left
  alone.
- PF-32: ``init`` refuses to set such a store up, and writes no config.
- PF-33: ``doctor`` fails its config check (exit 4) naming both formats, when the config's store
  is such a store.
- PF-34: ``api.open_store`` refuses it; ``import`` goes on refusing it as it did.
- PF-36: the terminal app, opened on such a store, shows that refusal on its screen and lists
  none of the store's runs.
- PF-35: only a newer major is refused: the same major, an older one, and a store with no
  descriptor read as before.
- PF-40: ``--save`` on a store whose ``store.json`` is not JSON refuses in one line naming the
  file, exit 1, on every verb that saves; nothing is written, and no "unexpected failure".
- PF-41: ``--save`` on a store whose ``store.json`` is JSON and not an object refuses the same
  way, and nothing says ``the verdict was not saved: OSError``.
- PF-42: where a verdict is printed and cannot be saved, the note gives the system's own words.
- PF-43: a broken descriptor is not healed or replaced by a refused save.
- PF-44: ``import`` into a store whose ``store.json`` is there and cannot be read refuses in one
  line that names the file and gives the system's own words, exit 1, under both spellings of the
  command; nothing is written, and no "unexpected failure" (FB-5, ruled 2026-11-18).
- PF-50: a word that reaches no run, in a store with a run whose manifest cannot be read, is
  refused naming that run by its id and that Prove could not read it, not as an unknown run.
- PF-51: by its id, that run is refused as one Prove could not read; the readable run still
  reads; ``runs`` lists the readable one and names the other.
- PF-52: in a store whose every run reads, a word that reaches none is still an unknown run.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from pf_support import (
    EVENT, JUNIT, NAMES, NEWER, READING, RUNS, SAVING, STORE_1_0, STORE_1_2, STORE_FORMAT, WRITING, argv_of, copy, cut_manifest, descriptor_file,
    home_of, marked, python, refused_one_line, run, tree, with_descriptor,
)

SOURCES = {"1.0": STORE_1_0, "1.2": STORE_1_2}


def _files(cwd: Path) -> dict[str, str]:
    return tree(cwd)


# ---------- PF-30 ----------


@pytest.mark.parametrize(("label", "found"), [*[(label, NEWER[0]) for label in READING], ("runs", NEWER[1])])
def test_pf_30_every_reading_command_refuses_a_store_in_a_newer_format(tmp_path: Path, label: str, found: str) -> None:
    store = marked(STORE_1_2, tmp_path, found)
    before = _files(tmp_path)
    ran = run(argv_of(READING[label], store, STORE_1_2), tmp_path)
    refused_one_line(ran, found, STORE_FORMAT)
    assert _files(tmp_path) == before


@pytest.mark.parametrize("source", list(SOURCES))
@pytest.mark.parametrize("by", ["id", "name"])
def test_pf_30_whichever_prove_wrote_it_and_however_the_runs_are_named(tmp_path: Path, by: str, source: str) -> None:
    store = marked(SOURCES[source], tmp_path, NEWER[0])
    before = _files(tmp_path)
    for label in ("runs", "where", "fix-check --json"):
        ran = run(argv_of(READING[label], store, SOURCES[source], by), tmp_path)
        refused_one_line(ran, NEWER[0], STORE_FORMAT)
    assert _files(tmp_path) == before


def test_pf_30_the_store_a_config_names_is_refused_too(tmp_path: Path) -> None:
    store = copy(STORE_1_2, tmp_path)
    assert run(["init", "--store", "store", *EVENT, "--yes"], tmp_path).code == 0
    doc = json.loads(descriptor_file(store).read_text(encoding="utf-8"))
    doc["format"] = NEWER[0]
    descriptor_file(store).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    before = _files(tmp_path)
    for argv in (["runs"], ["where", NAMES[1]], ["fix-check", *NAMES, "--inputs", "all", "--max-mde", "0.5", "--json"]):
        refused_one_line(run(argv, tmp_path), NEWER[0], STORE_FORMAT)
    assert _files(tmp_path) == before


def test_pf_30_a_run_given_by_its_folder_inside_such_a_store_is_refused_too(tmp_path: Path) -> None:
    """With no ``--store``, a run is read by its folder; the store it sits in is still the store
    it is read from, and that store's descriptor says what format its runs are in."""
    store = marked(STORE_1_2, tmp_path, NEWER[0])
    older, newer = RUNS[STORE_1_2]
    before = _files(tmp_path)
    for argv in (["where", store / newer, *EVENT], ["where", store / newer, *EVENT, "--json"],
                 ["fix-check", store / older, store / newer, *EVENT, "--inputs", "all", "--max-mde", "0.5"]):
        refused_one_line(run(argv, tmp_path), NEWER[0], STORE_FORMAT)
    assert _files(tmp_path) == before


# ---------- PF-31 ----------


@pytest.mark.parametrize("found", NEWER[:1])
@pytest.mark.parametrize("label", list(WRITING))
def test_pf_31_every_writing_command_refuses_a_store_in_a_newer_format(tmp_path: Path, label: str, found: str) -> None:
    store = marked(STORE_1_2, tmp_path, found)
    before = _files(tmp_path)
    ran = run(argv_of(WRITING[label], store, STORE_1_2), tmp_path)
    refused_one_line(ran, found, STORE_FORMAT)
    # nothing saved, no page, no name, no bundle, and the descriptor as it was, its writers among it
    assert _files(tmp_path) == before
    assert not (store / "trace-names.toml").exists() and not (store / ".poisson" / "ui").exists() and not (tmp_path / "bundle").exists()
    assert [w["tool"] for w in json.loads(descriptor_file(store).read_text(encoding="utf-8"))["writers"]] == ["poisson-prove"]


def test_pf_31_a_name_already_given_is_not_listed_or_forgotten_either(tmp_path: Path) -> None:
    store = copy(STORE_1_2, tmp_path)
    assert run(["name", RUNS[STORE_1_2][1], "the newer", "--store", store], tmp_path).code == 0
    doc = json.loads(descriptor_file(store).read_text(encoding="utf-8"))
    doc["format"] = NEWER[0]
    descriptor_file(store).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    before = _files(tmp_path)
    for argv in (["name", "--list", "--store", store], ["name", "--forget", "the newer", "--store", store],
                 ["where", "the newer", "--store", store, *EVENT, "--save"]):
        refused_one_line(run(argv, tmp_path), NEWER[0], STORE_FORMAT)
    assert _files(tmp_path) == before


# ---------- PF-32 ----------


@pytest.mark.parametrize("found", NEWER[:1])
def test_pf_32_init_refuses_to_set_up_a_store_in_a_newer_format(tmp_path: Path, found: str) -> None:
    marked(STORE_1_2, tmp_path, found)
    before = _files(tmp_path)
    for argv in (["init", "--store", "store", *EVENT, "--yes"], ["init", "--store", "store", *EVENT, "--yes", "--json"]):
        ran = run(argv, tmp_path)
        refused_one_line(ran, found, STORE_FORMAT)
    assert _files(tmp_path) == before and not (tmp_path / "trace.toml").exists() and not (tmp_path / "project" / "trace.toml").exists()


@pytest.mark.parametrize("found", NEWER[:1])
def test_pf_32_init_refuses_such_a_store_when_it_finds_it_itself(tmp_path: Path, found: str) -> None:
    """``init`` with no ``--store`` looks for a store under the folder it runs in, and reads the
    one it finds to offer its failures: the one store here is in a newer format."""
    project = tmp_path / "project"
    marked(STORE_1_2, project, found, name="prove-runs")
    before = _files(tmp_path)
    for argv in (["init", "--yes"], ["init", "--yes", *EVENT]):
        ran = run(argv, project)
        assert ran.code == 1 and ran.out == "", ran.text
        errors = [line for line in ran.lines() if line.startswith("error: ")]
        assert len(errors) == 1 and found in errors[0] and STORE_FORMAT in errors[0], ran.err
        assert "Traceback" not in ran.err and "unexpected failure" not in ran.err
    assert _files(tmp_path) == before and not (tmp_path / "trace.toml").exists() and not (tmp_path / "project" / "trace.toml").exists()


# ---------- PF-33 ----------


@pytest.mark.parametrize("found", NEWER[:1])
def test_pf_33_doctor_fails_its_config_check_naming_both_formats(tmp_path: Path, found: str) -> None:
    store = copy(STORE_1_2, tmp_path)
    assert run(["init", "--store", "store", *EVENT, "--yes"], tmp_path).code == 0
    assert run(["doctor"], tmp_path).code == 0
    doc = json.loads(descriptor_file(store).read_text(encoding="utf-8"))
    doc["format"] = found
    descriptor_file(store).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    before = _files(tmp_path)
    ran = run(["doctor", "--json"], tmp_path)
    assert ran.code == 4, ran.text
    report = ran.json()
    (config,) = [c for c in report["checks"] if c["name"] == "config"]
    assert config["ok"] is False and found in config["line"] and STORE_FORMAT in config["line"], config
    (prove,) = [c for c in report["checks"] if c["name"] == "prove"]
    assert prove["ok"] is True, prove
    plain = run(["doctor"], tmp_path)
    assert plain.code == 4 and plain.out.splitlines()[0].startswith("not ready  config fails"), plain.out
    assert found in plain.out and STORE_FORMAT in plain.out and "Traceback" not in plain.text, plain.text
    assert _files(tmp_path) == before


# ---------- PF-34 ----------


@pytest.mark.parametrize("found", NEWER[:1])
def test_pf_34_the_api_refuses_to_open_it(tmp_path: Path, found: str) -> None:
    store = marked(STORE_1_2, tmp_path, found)
    before = _files(tmp_path)
    code = ("import sys\nfrom poisson_trace import api\n"
            "try:\n    api.open_store(sys.argv[1])\n"
            "except api.Refusal as e:\n    print(str(e))\n    sys.exit(0)\n"
            "sys.exit(9)\n")
    ran = python(code, [store], tmp_path)
    assert ran.code == 0, ran.text
    assert found in ran.out and STORE_FORMAT in ran.out, ran.out
    assert _files(tmp_path) == before


@pytest.mark.parametrize("found", NEWER[:1])
def test_pf_34_import_goes_on_refusing_it(tmp_path: Path, found: str) -> None:
    store = marked(STORE_1_2, tmp_path, found)
    before = _files(tmp_path)
    for command, argv in (("trace", ["import", "junit", JUNIT, "--store", store, "--run", "suite"]),
                          ("import", ["junit", JUNIT, "--store", store, "--run", "suite"])):
        refused_one_line(run(argv, tmp_path, command), found, STORE_FORMAT)
    assert _files(tmp_path) == before


# ---------- PF-36 ----------


def test_pf_36_the_terminal_app_shows_the_refusal_and_lists_no_run(tmp_path: Path) -> None:
    from tf19_support import Step, run_pty, strip_escapes

    store = marked(STORE_1_2, tmp_path, NEWER[0])
    before = tree(store)
    home = tmp_path / "home"
    home.mkdir()
    ran = run_pty(["--store", "store"], home=home, cwd=tmp_path, steps=(Step(b"q", until=NEWER[0]),), timeout=45)
    shown = strip_escapes(ran.out)
    assert NEWER[0] in shown and STORE_FORMAT in shown, shown[-2000:]
    assert not any(word in shown for word in (*NAMES, *RUNS[STORE_1_2])), "no run of the store is listed"
    assert "Traceback" not in shown and "unexpected failure" not in shown
    assert tree(store) == before


# ---------- PF-35 ----------


@pytest.mark.parametrize("found", ["poisson.store/1", "poisson.store/0"])
def test_pf_35_the_same_major_and_an_older_one_are_read_and_written(tmp_path: Path, found: str) -> None:
    store = marked(STORE_1_2, tmp_path, found)
    for label in ("runs", "where", "fix-check --json"):
        ran = run(argv_of(READING[label], store, STORE_1_2), tmp_path)
        assert ran.code == 0, (label, ran.text)
    saved = run(argv_of(SAVING["fix-check --save"], store, STORE_1_2), tmp_path)
    assert saved.code == 0 and list((store / ".poisson" / "artifacts" / "fix-check").glob("*/result.json")), saved.text
    doc = json.loads(descriptor_file(store).read_text(encoding="utf-8"))
    assert doc["format"] == found and [w["tool"] for w in doc["writers"]] == ["poisson-prove", "poisson-trace"]


def test_pf_35_a_store_with_no_descriptor_is_read_and_gains_one_on_a_save(tmp_path: Path) -> None:
    store = copy(STORE_1_2, tmp_path)
    descriptor_file(store).unlink()
    assert run(argv_of(READING["runs"], store, STORE_1_2), tmp_path).code == 0
    assert not descriptor_file(store).exists(), "a reading verb writes no descriptor"
    saved = run(argv_of(SAVING["where --save"], store, STORE_1_2), tmp_path)
    assert saved.code == 0, saved.text
    doc = json.loads(descriptor_file(store).read_text(encoding="utf-8"))
    assert doc["format"] == STORE_FORMAT and [w["tool"] for w in doc["writers"]] == ["poisson-trace"]


def test_pf_35_the_minor_versions_are_never_refused() -> None:
    """1.0, 1.1 and 1.2 are one major: the descriptor of the store each Prove made says
    ``poisson.store/1``, which is the format Trace knows."""
    for store in (STORE_1_0, STORE_1_2):
        assert json.loads(descriptor_file(store).read_text(encoding="utf-8"))["format"] == STORE_FORMAT


# ---------- PF-40 ----------

NOT_JSON = {"cut short": None, "not json": "{not json\n", "empty": ""}
NOT_AN_OBJECT = {"a list": "[]\n", "a string": '"poisson.store/1"\n', "a number": "7\n", "null": "null\n"}


def _broken(tmp_path: Path, text: str | None) -> Path:
    if text is None:
        text = descriptor_file(STORE_1_2).read_text(encoding="utf-8")[:40]
    return with_descriptor(STORE_1_2, tmp_path, text)


@pytest.mark.parametrize("how", list(NOT_JSON))
@pytest.mark.parametrize("label", list(SAVING))
def test_pf_40_save_on_a_descriptor_that_is_not_json_refuses_in_one_line(tmp_path: Path, label: str, how: str) -> None:
    store = _broken(tmp_path, NOT_JSON[how])
    before = _files(tmp_path)
    ran = run(argv_of(SAVING[label], store, STORE_1_2), tmp_path)
    assert ran.code == 1, ran.text  # refused, where main crashed with exit 3
    refused_one_line(ran, "store.json")
    assert _files(tmp_path) == before
    assert not (store / ".poisson" / "artifacts" / label.split()[0]).exists() and not (store / ".poisson" / "ui").exists()
    assert not (home_of(tmp_path) / ".cache").exists(), "a refusal is no failure to log"


# ---------- PF-41 ----------


@pytest.mark.parametrize("how", list(NOT_AN_OBJECT))
@pytest.mark.parametrize("label", list(SAVING))
def test_pf_41_save_on_a_descriptor_that_is_not_an_object_says_so(tmp_path: Path, label: str, how: str) -> None:
    store = _broken(tmp_path, NOT_AN_OBJECT[how])
    before = _files(tmp_path)
    ran = run(argv_of(SAVING[label], store, STORE_1_2), tmp_path)
    refused_one_line(ran, "store.json")
    assert "OSError" not in ran.text and "was not saved" not in ran.text, ran.text
    assert _files(tmp_path) == before


@pytest.mark.parametrize("how", [*NOT_JSON, *NOT_AN_OBJECT])
def test_pf_41_the_refusal_is_the_same_whatever_is_wrong_with_the_file(tmp_path: Path, how: str) -> None:
    """One sentence for a descriptor that is not one, with what is wrong with it in the
    sentence's own brackets; the sentence names the file by its path."""
    store = _broken(tmp_path, {**NOT_JSON, **NOT_AN_OBJECT}[how])
    ran = run(argv_of(SAVING["fix-check --save"], store, STORE_1_2), tmp_path)
    line = refused_one_line(ran, "store.json")
    assert str(descriptor_file(store)) in line or ".poisson/store.json" in line, line
    assert ran.lines() == [line], "no next line: the file is the user's to put right"


# ---------- PF-42 ----------


@pytest.mark.skipif(os.geteuid() == 0, reason="the system refuses root nothing")
@pytest.mark.parametrize("label", ["where --save", "fix-check --save"])
def test_pf_42_a_verdict_that_cannot_be_saved_says_why_in_the_systems_words(tmp_path: Path, label: str) -> None:
    store = copy(STORE_1_2, tmp_path)
    folder = store / ".poisson" / "artifacts"
    mode = stat.S_IMODE(folder.stat().st_mode)
    folder.chmod(0o555)
    try:
        ran = run(argv_of(SAVING[label], store, STORE_1_2), tmp_path)
    finally:
        folder.chmod(mode)
    assert ran.code == 0 and ran.out.strip(), ran.text
    notes = [line for line in ran.err.splitlines() if line.startswith("note: the verdict was not saved")]
    assert notes == ["note: the verdict was not saved: Permission denied"], ran.err
    assert not (folder / label.split()[0]).exists()


# ---------- PF-43 ----------


@pytest.mark.parametrize("how", ["cut short", "a list"])
def test_pf_43_a_refused_save_leaves_the_broken_descriptor_as_it_is(tmp_path: Path, how: str) -> None:
    store = _broken(tmp_path, {**NOT_JSON, **NOT_AN_OBJECT}[how])
    held = descriptor_file(store).read_bytes()
    for label in SAVING:
        assert run(argv_of(SAVING[label], store, STORE_1_2), tmp_path).code == 1
    assert descriptor_file(store).read_bytes() == held
    assert sorted(p.name for p in (store / ".poisson").iterdir()) == ["artifacts", "store.json"]


# ---------- PF-44 ----------


@pytest.mark.skipif(os.geteuid() == 0, reason="the system refuses root nothing")
@pytest.mark.parametrize("command", ["trace", "import"])
def test_pf_44_import_refuses_a_store_json_it_cannot_read_in_one_line(tmp_path: Path, command: str) -> None:
    store = copy(STORE_1_2, tmp_path)
    file = descriptor_file(store)
    before = _files(tmp_path)
    mode = stat.S_IMODE(file.stat().st_mode)
    file.chmod(0)
    words = ["junit", str(JUNIT), "--store", str(store), "--run", "suite"]
    try:
        ran = run(words if command == "import" else ["import", *words], tmp_path, command)
    finally:
        file.chmod(mode)
    assert ran.code == 1, ran.text  # refused, where main crashed with exit 3
    refused_one_line(ran, "store.json")
    assert ran.lines() == [f"error: cannot read {file} (Permission denied); nothing was written"], ran.err
    assert _files(tmp_path) == before
    assert not (store / "suite").exists()
    assert not (home_of(tmp_path) / ".cache").exists(), "a refusal is no failure to log"


# ---------- PF-50 ----------

UNREADABLE = {
    "where": ["where", NAMES[0], *EVENT],
    "where --json": ["where", NAMES[0], *EVENT, "--json"],
    "compare": ["compare", *NAMES, *EVENT, "--max-mde-hr", "2"],
    "fix-check": ["fix-check", *NAMES, *EVENT, "--inputs", "all", "--max-mde", "0.5"],
    "fix-check --save": ["fix-check", *NAMES, *EVENT, "--inputs", "all", "--max-mde", "0.5", "--save"],
    "changes": ["changes", *NAMES, *EVENT],
    "name": ["name", NAMES[0], "the older"],
}


@pytest.mark.parametrize("source", list(SOURCES))
@pytest.mark.parametrize("label", list(UNREADABLE))
def test_pf_50_a_run_whose_manifest_cannot_be_read_is_named_as_unreadable(tmp_path: Path, label: str, source: str) -> None:
    """The run's name was in the manifest Prove cannot read, so the name reaches no run. The
    refusal says which run Prove could not read, by its id, and does not call it unknown."""
    unread = RUNS[SOURCES[source]][0]
    store = cut_manifest(SOURCES[source], tmp_path, unread)
    before = _files(tmp_path)
    ran = run([*UNREADABLE[label], "--store", store], tmp_path)
    line = refused_one_line(ran, unread, "Prove could not read")
    assert "unknown run" not in ran.text, ran.text
    assert f'"{NAMES[0]}"' in line, line
    assert _files(tmp_path) == before


def test_pf_50_the_refusal_still_says_what_the_store_holds_and_how_to_list_it(tmp_path: Path) -> None:
    unread = RUNS[STORE_1_2][0]
    store = cut_manifest(STORE_1_2, tmp_path, unread)
    ran = run(["where", NAMES[0], "--store", store, *EVENT], tmp_path)
    line = refused_one_line(ran, unread, f'"{NAMES[1]}"')
    assert ran.lines()[1:] == [f"  next: poisson-trace runs --store {store}"], ran.err
    assert line.count(unread) == 1


# ---------- PF-51 ----------


def test_pf_51_by_its_id_the_run_is_one_prove_could_not_read(tmp_path: Path) -> None:
    unread, readable = RUNS[STORE_1_2]
    store = cut_manifest(STORE_1_2, tmp_path, unread)
    before = _files(tmp_path)
    for argv in (["where", unread, *EVENT], ["fix-check", unread, readable, *EVENT, "--inputs", "all", "--max-mde", "0.5"],
                 ["changes", unread, readable, *EVENT]):
        ran = run([*argv, "--store", store], tmp_path)
        line = refused_one_line(ran, unread, "Prove could not read")
        assert "unknown run" not in line, line
    named = run(["name", unread, "the older", "--store", store], tmp_path)
    refused_one_line(named, unread, "Prove could not read")
    assert _files(tmp_path) == before


def test_pf_51_the_readable_run_still_reads_and_runs_names_the_other(tmp_path: Path) -> None:
    unread, readable = RUNS[STORE_1_2]
    store = cut_manifest(STORE_1_2, tmp_path, unread)
    for word in (readable, NAMES[1]):
        ran = run(["where", word, "--store", store, *EVENT], tmp_path)
        assert ran.code == 0 and ran.out.strip(), ran.text
    listed = run(["runs", "--store", store], tmp_path)
    assert listed.code == 0 and NAMES[1] in listed.out and NAMES[0] not in listed.out, listed.text
    notes = [line for line in listed.err.splitlines() if line.startswith("note: ") and unread in line]
    assert len(notes) == 1 and "Prove could not read" in notes[0], listed.err


# ---------- PF-52 ----------


@pytest.mark.parametrize("source", list(SOURCES))
def test_pf_52_where_every_run_reads_a_word_that_reaches_none_is_still_unknown(tmp_path: Path, source: str) -> None:
    store = copy(SOURCES[source], tmp_path)
    older, newer = RUNS[SOURCES[source]]
    ran = run(["where", "no such run", "--store", store, *EVENT], tmp_path)
    line = refused_one_line(ran)
    assert line == f'error: unknown run "no such run"; the store holds "{NAMES[1]}" ({newer}), "{NAMES[0]}" ({older})', line
    assert "could not read" not in ran.text
