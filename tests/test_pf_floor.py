"""PF-1 to PF-29: Trace declares the oldest Prove it reads, refuses only what is below it, and
reads every stored format from 1.0 to 1.2 alike (PV-2 to PV-7; ``pf_support``'s opening, items 1
to 3).

- PF-1: the declaration is a floor with no cap, and the floor Trace checks is read back from it:
  with the installed package declaring another floor, Trace checks for that one and names it.
- PF-2: a Prove at the floor or above it is read, whatever it states: the floor, a later patch,
  minor or major release, a version with more or fewer parts, a post-release. Trace prints the
  version it found, not the floor.
- PF-3: a Prove below the floor is refused by every command, word for word, with the one install
  line under it: an earlier release, however close, and a pre-release of the floor itself.
- PF-4: no Prove, and a Prove that states no version, are refused word for word.
- PF-5: ``doctor`` names the floor: when ready, when Prove is below it, absent or unversioned.
- PF-6: the install line is one a shell reads as written, and it installs a Prove Trace reads.
- PF-7: what needs no Prove still needs none: every help and the version line.
- PF-10: the store the floor made is the stored format's 1.2 and the store 0.1.3 made its 1.0,
  and they hold the same outcomes row for row.
- PF-11: every verb reads the 1.2 store as it reads the 1.0 store: the same exit code and, once
  what names the store's own runs and times is written out, the same report.
- PF-12: every write Trace makes into a 1.2 store leaves every key and file Prove wrote as it
  was, the 1.1 and 1.2 keys among them, and Prove reads the store after it.
- PF-13: the two stores are listed whole in the fixture's digests.
- PF-20: ``pin_support.as_pinned`` writes Prove's version as the pins hold it in the places
  Trace prints it, and nowhere else.
- PF-21: with a Prove stating a later version, the earlier pairs' pins of what main prints still
  hold: a case of each kind, run under a Prove that states 0.4.1.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from pf_support import (
    EVENT, IMPORT_WRITES, INIT_READS, JUNIT, NAMES, NOTES, READING, READS, REPO, RUNS, SAVING, STORE_1_0, STORE_1_2, STORES, absent, argv_of, below,
    copy, declaring, python, run, stating, tree, unversioned, with_fake_prove,
)
from pin_support import FORMAT_1_0, INSTALL, OR_LATER, RECORDED, REQUIREMENT, as_pinned, at_or_above_the_floor, installed, release

AT_OR_ABOVE = (RECORDED, "0.4.1", "0.5.0", "0.10.0", "1.0.0", "2.3.4", "0.4", "0.4.0.0", "0.4.0.post1", "1.0.0rc1")
BELOW = ("0.3.0", "0.3.99", "0.2.2", "0.1.3", "0.0.1", "0.3", "0.4.0rc1", "0.4.0a1", "0.4.0b2", "0.4.0.dev1")
#: A command of each family, the module that runs it, and what it does through Prove.
FAMILIES = {
    "runs": ("trace", ["runs", "--store", "STORE"], READS),
    "where": ("trace", ["where", "#1", "--store", "STORE", *EVENT], READS),
    "compare": ("trace", ["compare", "#2", "#1", "--store", "STORE", *EVENT, "--max-mde-hr", "1.5"], READS),
    "fix-check": ("trace", ["fix-check", "#2", "#1", "--store", "STORE", *EVENT, "--inputs", "all", "--max-mde", "0.5"], READS),
    "changes": ("trace", ["changes", "#2", "#1", "--store", "STORE", *EVENT], READS),
    "name": ("trace", ["name", "#1", "a name", "--store", "STORE"], READS),
    "ui": ("trace", ["ui", "--store", "STORE"], READS),
    "init": ("trace", ["init", "--yes"], INIT_READS),
    "import": ("trace", ["import", "junit", str(JUNIT), "--store", "NEWSTORE", "--run", "suite"], IMPORT_WRITES),
    "poisson-trace-import": ("import", ["junit", str(JUNIT), "--store", "NEWSTORE", "--run", "suite"], IMPORT_WRITES),
}


def _argv(family: str, work: Path) -> list[str]:
    if not (work / "store").exists():
        copy(STORE_1_2, work)
    swap = {"STORE": str(work / "store"), "NEWSTORE": str(work / "new-store")}
    return [swap.get(a, a) for a in FAMILIES[family][1]]


# ---------- PF-1 ----------


def test_pf_1_the_declaration_is_a_floor_and_nothing_more() -> None:
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    prove = [d for d in project["dependencies"] if re.match(r"\s*poisson[-_.]prove\b", d, re.IGNORECASE)]
    assert [d.replace(" ", "") for d in prove] == [REQUIREMENT] == ["poisson-prove>=0.4.0"], project["dependencies"]
    # no cap, no excluded version, no second clause, no marker
    assert not re.search(r"[<~!,;]|==", prove[0]), prove
    for wanted in project.get("optional-dependencies", {}).values():
        assert not [d for d in wanted if re.match(r"\s*poisson[-_.]prove\b", d, re.IGNORECASE)], wanted
    # the dependencies are written in the file, not worked out by the build, and Prove's old name is never asked for
    # (PIN-1's two lines, moved here on the ruling of 2026-11-18, AR-6)
    assert "dependencies" not in project.get("dynamic", []), project.get("dynamic")
    asked = [*project["dependencies"], *(d for wanted in project.get("optional-dependencies", {}).values() for d in wanted)]
    assert not [d for d in asked if re.match(r"\s*proofload\b", d, re.IGNORECASE)], asked


def test_pf_1_the_floor_trace_checks_is_the_declared_one() -> None:
    from poisson_trace import look

    assert look.PROVE_VERSION == RECORDED
    assert look.INSTALL_PROVE == INSTALL == 'pip install "poisson-prove>=0.4.0"'


@pytest.mark.parametrize(("requires", "floor"), [
    (["numpy", "poisson-prove>=0.4.0", "rich>=14.2.0"], "0.4.0"),
    (["poisson-prove>=0.5.1"], "0.5.1"),
    (["poisson_prove >= 1.2.3"], "1.2.3"),
    (['Poisson.Prove>=9.9.9; python_version >= "3.11"'], "9.9.9"),
])
def test_pf_1_the_floor_is_read_back_from_the_installed_packages_declaration(tmp_path: Path, requires: list[str], floor: str) -> None:
    """Whatever floor the installed poisson-trace declares is the one Trace checks and names:
    under a floor the installed Prove is below, the command refuses naming that floor and its
    install line; under one it meets, the command reads the store."""
    store = copy(STORE_1_2, tmp_path)
    ran = declaring(["runs", "--store", store], tmp_path, requires)
    if at_or_above_the_floor(installed()) and release(installed()) >= release(floor):
        assert ran.code == 0 and "pip install" not in ran.text, ran.text
    else:
        assert ran.code == 1 and ran.out == "", ran.text
        assert ran.lines() == [
            f"error: {READS} through Prove (the poisson-prove package, version {floor} or later) and found poisson-prove {installed()}",
            f'  next: pip install "poisson-prove>={floor}"',
        ], ran.err


def test_pf_1_a_package_that_declares_no_floor_does_not_run_as_if_it_did(tmp_path: Path) -> None:
    """The installed package's metadata with no Prove requirement at all: nothing is guessed. The
    command stops, and what it says names poisson-prove."""
    store = copy(STORE_1_2, tmp_path)
    before = tree(store)
    ran = declaring(["runs", "--store", store], tmp_path, ["numpy", "rich>=14.2.0"])
    assert ran.code != 0 and ran.out == "", ran.text
    assert "poisson-prove" in ran.err, ran.err
    assert tree(store) == before


# ---------- PF-2 ----------


@pytest.mark.parametrize("version", AT_OR_ABOVE)
def test_pf_2_a_prove_at_or_above_the_floor_is_read(tmp_path: Path, version: str) -> None:
    store = copy(STORE_1_2, tmp_path)
    listed = stating(["runs", "--store", store], tmp_path, version)
    assert listed.code == 0, listed.text
    assert "pip install" not in listed.text and "poisson-prove package" not in listed.text, listed.text
    assert all(name in listed.out for name in NAMES), listed.out
    said = stating(["--version"], tmp_path, version)
    assert said.code == 0 and f"(poisson-prove {version}, Python " in said.out, said.text


@pytest.mark.parametrize("version", [RECORDED, "0.4.1", "1.0.0"])
def test_pf_2_trace_prints_the_prove_it_found_not_the_floor(tmp_path: Path, version: str) -> None:
    store = copy(STORE_1_2, tmp_path)
    where = stating(argv_of(READING["where --json"], store, STORE_1_2), tmp_path, version)
    assert where.code == 0, where.text
    assert where.json()["prove"]["version"] == version
    saved = stating(argv_of(SAVING["fix-check --save"], store, STORE_1_2), tmp_path, version)
    assert saved.code == 0, saved.text
    (result,) = (store / ".poisson" / "artifacts" / "fix-check").glob("*/result.json")
    held = json.loads(result.read_text(encoding="utf-8"))
    assert held["prove"]["version"] == version and held["versions"]["prove"] == version


@pytest.mark.parametrize("family", [f for f in FAMILIES if f != "init"])
def test_pf_2_with_the_prove_installed_nothing_refuses(tmp_path: Path, family: str) -> None:
    command, _, _ = FAMILIES[family]
    ran = run(_argv(family, tmp_path), tmp_path, command)
    assert ran.code == 0, ran.text
    assert "pip install" not in ran.text and "poisson-prove package" not in ran.err, ran.err


# ---------- PF-3 ----------


@pytest.mark.parametrize("version", BELOW)
@pytest.mark.parametrize("family", ["runs", "fix-check", "import"])
def test_pf_3_a_prove_below_the_floor_is_refused_word_for_word(tmp_path: Path, family: str, version: str) -> None:
    command, _, does = FAMILIES[family]
    argv = _argv(family, tmp_path)
    before = tree(tmp_path)
    ran = with_fake_prove(argv, tmp_path, version, command)
    assert ran.code == 1, ran.text
    assert ran.out == "", ran.out
    assert ran.lines() == below(does, version), ran.err
    assert tree(tmp_path) == before


@pytest.mark.parametrize("version", ["0.3.0", "0.4.0rc1"])
@pytest.mark.parametrize("family", list(FAMILIES))
def test_pf_3_every_command_refuses_a_prove_below_the_floor(tmp_path: Path, family: str, version: str) -> None:
    command, _, does = FAMILIES[family]
    argv = _argv(family, tmp_path)
    before = tree(tmp_path)
    ran = with_fake_prove(argv, tmp_path, version, command)
    assert (ran.code, ran.out) == (1, ""), ran.text
    assert ran.lines() == below(does, version), ran.err
    assert tree(tmp_path) == before


@pytest.mark.parametrize("version", ["0.3.0", "0.3.99", "0.4.0rc1"])
def test_pf_3_the_installed_prove_stating_a_version_below_the_floor_is_refused_too(tmp_path: Path, version: str) -> None:
    """The check reads what Prove states, not whether its modules import: the Prove installed,
    whole, stating a version below the floor is refused as that version."""
    store = copy(STORE_1_2, tmp_path)
    before = tree(store)
    ran = stating(["runs", "--store", store], tmp_path, version)
    assert (ran.code, ran.out) == (1, ""), ran.text
    assert ran.lines() == below(READS, version), ran.err
    assert tree(store) == before


def test_pf_3_a_version_that_is_not_numbers_is_refused_as_found(tmp_path: Path) -> None:
    store = copy(STORE_1_2, tmp_path)
    for version in ("other", "v-next"):
        ran = stating(["runs", "--store", store], tmp_path, version)
        assert (ran.code, ran.out) == (1, ""), ran.text
        assert ran.lines() == below(READS, version), ran.err


def test_pf_3_no_refusal_tells_a_user_on_a_later_prove_to_go_back() -> None:
    """The install line names the floor as the least, never one exact version."""
    assert "==" not in INSTALL and f">={RECORDED}" in INSTALL
    for lines in (below(READS, "0.3.0"), absent(READS), unversioned(READS)):
        assert lines[1] == f"  next: {INSTALL}" and OR_LATER in lines[0]


# ---------- PF-4 ----------


@pytest.mark.parametrize("family", list(FAMILIES))
def test_pf_4_without_prove_every_command_refuses_word_for_word(tmp_path: Path, family: str) -> None:
    command, _, does = FAMILIES[family]
    argv = _argv(family, tmp_path)
    before = tree(tmp_path)
    ran = with_fake_prove(argv, tmp_path, "absent", command)
    assert (ran.code, ran.out) == (1, ""), ran.text
    assert ran.lines() == absent(does), ran.err
    assert tree(tmp_path) == before


@pytest.mark.parametrize("prove", ["unversioned", "unversioned:''", "unversioned:None", "unversioned:(0, 4, 0)"])
@pytest.mark.parametrize("family", ["runs", "fix-check", "init", "import", "poisson-trace-import"])
def test_pf_4_a_prove_that_states_no_version_is_refused_word_for_word(tmp_path: Path, family: str, prove: str) -> None:
    command, _, does = FAMILIES[family]
    argv = _argv(family, tmp_path)
    before = tree(tmp_path)
    ran = with_fake_prove(argv, tmp_path, prove, command)
    assert (ran.code, ran.out) == (1, ""), ran.text
    assert ran.lines() == unversioned(does), ran.err
    assert tree(tmp_path) == before


# ---------- PF-5 ----------


def _prove_check(ran) -> tuple[dict, dict]:  # type: ignore[no-untyped-def, type-arg]
    doc = ran.json()
    (check,) = [c for c in doc["checks"] if c["name"] == "prove"]
    return doc, check


@pytest.mark.parametrize("version", [RECORDED, "0.4.1", "1.0.0"])
def test_pf_5_doctor_names_the_prove_it_found_and_the_floor(tmp_path: Path, version: str) -> None:
    ran = stating(["doctor", "--json"], tmp_path, version)
    _, check = _prove_check(ran)
    assert check == {"name": "prove", "ok": True, "line": f"poisson-prove {version} (Trace reads version {OR_LATER})", "next": None}, check
    plain = stating(["doctor"], tmp_path, version)
    assert f"  prove     poisson-prove {version} (Trace reads version {OR_LATER})" in plain.out.splitlines(), plain.out


def test_pf_5_doctor_with_the_prove_installed(tmp_path: Path) -> None:
    _, check = _prove_check(run(["doctor", "--json"], tmp_path))
    assert check["ok"] is True and check["line"] == f"poisson-prove {installed()} (Trace reads version {OR_LATER})", check


@pytest.mark.parametrize(("prove", "line"), [
    ("0.3.0", f"poisson-prove 0.3.0 is installed, and Trace reads version {OR_LATER}"),
    ("0.1.3", f"poisson-prove 0.1.3 is installed, and Trace reads version {OR_LATER}"),
    ("0.4.0rc1", f"poisson-prove 0.4.0rc1 is installed, and Trace reads version {OR_LATER}"),
    ("absent", f"poisson-prove is not installed, and Trace reads stores through it (version {OR_LATER})"),
    ("unversioned", f"poisson-prove states no version, and Trace reads version {OR_LATER}"),
])
def test_pf_5_doctor_fails_its_prove_check_naming_the_floor_and_the_fix(tmp_path: Path, prove: str, line: str) -> None:
    ran = with_fake_prove(["doctor", "--json"], tmp_path, prove)
    assert ran.code == 4, ran.text
    doc, check = _prove_check(ran)
    assert check == {"name": "prove", "ok": False, "line": line, "next": INSTALL}, check
    assert doc["next"] == INSTALL
    plain = with_fake_prove(["doctor"], tmp_path, prove)
    assert plain.code == 4, plain.text
    assert f"  prove     {line}; run {INSTALL}" in plain.out.splitlines(), plain.out
    assert plain.out.splitlines()[-1] == f"next: {INSTALL}", plain.out


def test_pf_5_no_output_says_trace_reads_one_exact_version(tmp_path: Path) -> None:
    for prove in ("0.3.0", "absent", "unversioned"):
        for argv in (["doctor"], ["doctor", "--json"], ["runs", "--store", "nowhere"]):
            text = with_fake_prove(argv, tmp_path, prove).text
            assert "the version Trace reads" not in text and f"poisson-prove=={RECORDED}" not in text, text
            assert f"version {RECORDED})" not in text and f"version {RECORDED} and" not in text, text
    ready = run(["doctor"], tmp_path).out
    assert "(the version Trace reads)" not in ready, ready


# ---------- PF-6 ----------


def test_pf_6_the_install_line_is_one_a_shell_reads_as_written() -> None:
    """``>`` unquoted would send pip's output to a file named ``=0.4.0`` and install any Prove."""
    assert shlex.split(INSTALL) == ["pip", "install", f"poisson-prove>={RECORDED}"]
    shown = subprocess.run(["sh", "-c", f"printf '%s\\n' {INSTALL.removeprefix('pip install ')}"], capture_output=True, text=True, check=True)
    assert shown.stdout == f"poisson-prove>={RECORDED}\n"


def test_pf_6_the_install_line_installs_a_prove_trace_reads() -> None:
    (requirement,) = shlex.split(INSTALL)[2:]
    assert requirement == REQUIREMENT
    for version in ("0.4.0", "0.4.1", "1.0.0"):
        assert at_or_above_the_floor(version)
    for version in ("0.3.0", "0.3.99", FORMAT_1_0):
        assert not at_or_above_the_floor(version)


# ---------- PF-7 ----------


@pytest.mark.parametrize("prove", ["absent", "0.3.0", "unversioned"])
def test_pf_7_help_and_the_version_need_no_prove(tmp_path: Path, prove: str) -> None:
    for argv in (["--help"], ["runs", "--help"], ["fix-check", "--help"], ["import", "--help"], ["doctor", "--help"]):
        ran = with_fake_prove(argv, tmp_path, prove)
        assert ran.code == 0 and ran.out.strip() and ran.err == "", (argv, ran.text)
    said = with_fake_prove(["--version"], tmp_path, prove)
    assert said.code == 0 and said.err == "", said.text
    shown = {"absent": "poisson-prove not installed", "0.3.0": "poisson-prove 0.3.0", "unversioned": "poisson-prove of no version"}[prove]
    assert f"({shown}, Python " in said.out, said.out


# ---------- PF-10 ----------


def test_pf_10_the_two_stores_are_the_formats_1_0_and_1_2() -> None:
    for store, version in ((STORE_1_0, FORMAT_1_0), (STORE_1_2, RECORDED)):
        descriptor = json.loads((store / ".poisson" / "store.json").read_text(encoding="utf-8"))
        # the minor version is written nowhere: both descriptors say poisson.store/1
        assert descriptor["format"] == "poisson.store/1" and descriptor["created_by"]["version"] == version
        assert sorted(p.parent.name for p in store.glob("*/manifest.json")) == sorted(RUNS[store])
        for run_id, name in zip(RUNS[store], NAMES, strict=True):
            manifest = json.loads((store / run_id / "manifest.json").read_text(encoding="utf-8"))
            assert (manifest["name"], manifest["poisson_prove_version"], manifest["schema_version"]) == (name, version, 1)
    later = [json.loads((STORE_1_2 / run_id / "manifest.json").read_text(encoding="utf-8")) for run_id in RUNS[STORE_1_2]]
    earlier = [json.loads((STORE_1_0 / run_id / "manifest.json").read_text(encoding="utf-8")) for run_id in RUNS[STORE_1_0]]
    assert [m["note"] for m in later] == list(NOTES) and all("produced_by" in m for m in later)
    assert not any({"note", "produced_by", "stopped_by"} & set(m) for m in earlier)
    (comparison,) = (STORE_1_2 / ".poisson" / "artifacts" / "comparison").glob("*/comparison.json")
    held = json.loads(comparison.read_text(encoding="utf-8"))
    assert (held["note_a"], held["note_b"]) == NOTES


def test_pf_10_the_two_stores_hold_the_same_outcomes_row_for_row() -> None:
    from poisson_prove.store import Store

    def rows(root: Path, run_id: str) -> list[tuple]:  # type: ignore[type-arg]
        frame = Store(root).read(run_id)
        return sorted(zip(frame["config_hash"], frame["replicate_index"], frame["outcome"], frame["t"], strict=True))

    for old, new in zip(RUNS[STORE_1_0], RUNS[STORE_1_2], strict=True):
        assert rows(STORE_1_0, old) == rows(STORE_1_2, new), (old, new)
        assert len(rows(STORE_1_2, new)) == 160


# ---------- PF-11 ----------

_ID = re.compile(r"\b\d{8}T\d{6}Z-[0-9a-f]{4}\b")
_TIME = re.compile(r"\d{4}-\d\d-\d\d[T ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|\+00:00)?")
_DAY = re.compile(r"\b2026-11-(?:04|18)\b")


def _own_words_out(text: str, store: Path) -> str:
    """A report with what is the store's own written out: its path, its runs' ids, their times
    and days, and how far apart the two sweeps happened to start."""
    text = text.replace(str(store), "<STORE>")
    text = _TIME.sub("<TIME>", _ID.sub("<RUN>", text))
    text = _DAY.sub("<DAY>", text)
    text = re.sub(r"\bstarted \d+ s apart\b", "started <GAP> apart", text)
    return re.sub(r'"gap_seconds": [\d.]+', '"gap_seconds": <GAP>', text)


@pytest.mark.parametrize("by", ["id", "name"])
@pytest.mark.parametrize("label", list(READING))
def test_pf_11_every_verb_reads_the_1_2_store_as_it_reads_the_1_0_store(tmp_path: Path, label: str, by: str) -> None:
    got = []
    for source in (STORE_1_0, STORE_1_2):
        work = tmp_path / source.name
        store = copy(source, work)
        before = tree(store)
        ran = run(argv_of(READING[label], store, source, by), work)
        assert ran.code == 0, ran.text
        assert tree(store) == before, "a reading verb writes nothing"
        got.append((_own_words_out(ran.out, store), _own_words_out(ran.err, store)))
    assert got[0] == got[1], label


def test_pf_11_doctor_and_init_read_the_1_2_store(tmp_path: Path) -> None:
    store = copy(STORE_1_2, tmp_path)
    made = run(["init", "--store", "store", *EVENT, "--yes"], tmp_path)
    assert made.code == 0 and (tmp_path / "trace.toml").is_file(), made.text
    ready = run(["doctor"], tmp_path)
    assert ready.code == 0, ready.text
    assert "store store (2 runs, 2 complete, 0 partial), failures violated" in ready.out, ready.out
    read = run(["where", NAMES[0]], tmp_path)
    assert read.code == 0, read.text
    assert tree(store) == tree(STORE_1_2)


def test_pf_11_the_api_reads_the_1_2_store(tmp_path: Path) -> None:
    store = copy(STORE_1_2, tmp_path)
    code = ("import sys\nfrom poisson_trace import api\n"
            "store = api.open_store(sys.argv[1])\nprint(store.path)\n")
    ran = python(code, [store], tmp_path)
    assert ran.code == 0 and ran.out.strip() == str(store) and ran.err == "", ran.text


# ---------- PF-12 ----------


def test_pf_12_every_write_into_a_1_2_store_leaves_what_prove_wrote(tmp_path: Path) -> None:
    store = copy(STORE_1_2, tmp_path)
    before = tree(store)
    for label, words in SAVING.items():
        ran = run(argv_of(words, store, STORE_1_2), tmp_path)
        assert ran.code == 0, (label, ran.text)
    for argv in (["ui", "--store", store], ["name", RUNS[STORE_1_2][1], "the newer", "--store", store],
                 ["import", "junit", JUNIT, "--store", store, "--run", "imported"]):
        ran = run(argv, tmp_path)
        assert ran.code == 0, (argv, ran.text)
    after = tree(store)
    # every file Prove wrote is byte for byte as it was, but the descriptor, which gains Trace among its writers
    moved = sorted(name for name in before if after.get(name) != before[name])
    assert moved == [".poisson/store.json"], moved
    was = json.loads((STORE_1_2 / ".poisson" / "store.json").read_text(encoding="utf-8"))
    now = json.loads((store / ".poisson" / "store.json").read_text(encoding="utf-8"))
    assert [w["tool"] for w in now["writers"]] == ["poisson-prove", "poisson-trace"]
    assert {**now, "writers": now["writers"][:1]} == was
    added = sorted(name for name in after if name not in before)
    assert added and all(name.startswith((".poisson/artifacts/", ".poisson/ui/trace/", "imported/")) or name == "trace-names.toml"
                         for name in added), added
    for run_id, note in zip(RUNS[STORE_1_2], NOTES, strict=True):
        manifest = json.loads((store / run_id / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["note"] == note and "produced_by" in manifest


def test_pf_12_prove_reads_the_store_after_trace_wrote_into_it(tmp_path: Path) -> None:
    store = copy(STORE_1_2, tmp_path)
    for argv in (argv_of(SAVING["fix-check --save"], store, STORE_1_2), ["import", "junit", JUNIT, "--store", store, "--run", "imported"],
                 ["ui", "--store", store]):
        assert run(argv, tmp_path).code == 0
    from poisson_prove.core._artifacts import check_store
    from poisson_prove.store import Store

    check_store(store)
    held = Store(store)
    assert sorted(held.runs()) == sorted([*RUNS[STORE_1_2], "imported"])
    for run_id in RUNS[STORE_1_2]:
        assert len(held.read(run_id)) == 160 and held.manifest(run_id).status == "complete"
    listed = subprocess.run([sys.executable, "-m", "poisson_prove", "runs", "--store", str(store)], capture_output=True, text=True,
                            cwd=tmp_path, timeout=300)
    assert listed.returncode == 0 and all(name in listed.stdout for name in NAMES), listed.stdout + listed.stderr


# ---------- PF-13 ----------


def test_pf_13_both_stores_are_listed_whole_in_the_digests() -> None:
    import hashlib

    sums = {}
    for line in (STORES / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        sums[name.removeprefix("./")] = digest
    for store in (STORE_1_0, STORE_1_2):
        files = {str(p.relative_to(STORES)): p for p in store.rglob("*") if p.is_file()}
        assert files and set(files) == {name for name in sums if name.startswith(store.name + "/")}
        assert {name: hashlib.sha256(p.read_bytes()).hexdigest() for name, p in files.items()} == {name: sums[name] for name in files}
        for path in files.values():
            data = path.read_bytes()
            for word in (b"/Users/", b"/home/", b"/private/", b"/var/folders/"):
                assert word not in data, (path, word)


# ---------- PF-20 ----------


@pytest.mark.parametrize("found", [RECORDED, "0.4.1", "1.0.0", "0.10.2"])
def test_pf_20_as_pinned_writes_proves_version_as_the_pins_hold_it(found: str) -> None:
    old = FORMAT_1_0
    cases = {
        f'{{\n  "schema": "poisson-trace.where/1",\n  "prove": {{\n    "version": "{found}",\n    "store": "s"\n  }}\n}}\n':
            f'{{\n  "schema": "poisson-trace.where/1",\n  "prove": {{\n    "version": "{old}",\n    "store": "s"\n  }}\n}}\n',
        f'{{"prove": {{"installed": true, "version": "{found}"}}}}': f'{{"prove": {{"installed": true, "version": "{old}"}}}}',
        f'"versions": {{\n    "trace": "0.1.0a1",\n    "prove": "{found}"\n  }}': f'"versions": {{\n    "trace": "0.1.0a1",\n    "prove": "{old}"\n  }}',
        f"  prove     poisson-prove {found} (Trace reads version {OR_LATER})\n": f"  prove     poisson-prove {old} (the version Trace reads)\n",
        f'"line": "poisson-prove {found} (Trace reads version {OR_LATER})"': f'"line": "poisson-prove {old} (the version Trace reads)"',
        f"poisson-trace 0.1.0a1 (poisson-prove {found}, Python 3.12.13)\n": f"poisson-trace 0.1.0a1 (poisson-prove {old}, Python 3.12.13)\n",
        f'"poisson_prove_version":"{found}"': f'"poisson_prove_version":"{old}"',
        f'<dd>poisson-trace 0.1.0a1 <span class="dim">\u00b7</span> poisson-prove {found}</dd>':
            f'<dd>poisson-trace 0.1.0a1 <span class="dim">\u00b7</span> poisson-prove {old}</dd>',
        f"poisson-trace 0.1.0 \u00b7 poisson-prove {found}\n": f"poisson-trace 0.1.0 \u00b7 poisson-prove {old}\n",
        f'<text x="64" y="662" fill="#52514e">Poisson Trace \u00b7 Prove {found} \u00b7 leaf span index</text>':
            f'<text x="64" y="662" fill="#52514e">Poisson Trace \u00b7 Prove {old} \u00b7 leaf span index</text>',
    }
    for text, want in cases.items():
        assert as_pinned(text, found) == want, text
        assert as_pinned(want, found) == want, "what is pinned already is left as it is"


@pytest.mark.parametrize("found", [RECORDED, "0.4.1"])
def test_pf_20_as_pinned_moves_nothing_else(found: str) -> None:
    kept = (
        f"the rate fell from {found} to 0.1\n",
        f'"trace": {{"version": "{found}"}}',
        f'"version": "{found}"',
        f'"tool_version": "{found}"',
        f"poisson-tasks {found}\n",
        f"error: Poisson Trace reads stored runs through Prove (the poisson-prove package, version {OR_LATER}) and found poisson-prove 0.3.0\n",
        f'  next: pip install "poisson-prove>={RECORDED}"\n',
        f"poisson-prove {found} is installed, and Trace reads version {OR_LATER}\n",
        '"prove": {"version": "9.8.7"}',  # another version than the one installed
        "",
    )
    for text in kept:
        assert as_pinned(text, found) == text, text


def test_pf_20_as_pinned_reads_the_installed_prove_when_none_is_given() -> None:
    text = f'"prove": {{\n    "version": "{installed()}"'
    assert as_pinned(text) == f'"prove": {{\n    "version": "{FORMAT_1_0}"'


# ---------- PF-21 ----------


def _under(version: str):  # type: ignore[no-untyped-def]
    """The in-process Prove stating ``version`` for as long as the block runs."""
    import contextlib

    import poisson_prove

    @contextlib.contextmanager
    def stated():  # type: ignore[no-untyped-def]
        was = poisson_prove.__version__
        poisson_prove.__version__ = version
        try:
            yield
        finally:
            poisson_prove.__version__ = was

    return stated()


LATER = "0.4.1"
PL_CASES = ("verb: compare", "verb: changes", "save: fix-check", "save: compare", "import json: junit", "ui: store", "report: made",
            "refusal: a ceiling out of range")
SETUP_CASES = ("doctor: a config", "doctor: no config", "init: a store, json first")


def test_pf_21_the_cases_named_are_fast_cases_of_the_newest_pinned_corpus() -> None:
    from pl_pins import CHANGED, pin_corpus, pin_slow
    from tf20_pins import SETUP

    corpus = pin_corpus()
    assert [label for label in PL_CASES if label not in corpus or label in CHANGED or label in pin_slow()] == []
    assert [label for label in SETUP_CASES if label not in SETUP] == []
    # at least one of them prints Prove's version, or holding them under a later Prove would hold nothing
    assert any(kind == "trace" and "--json" in step for label in PL_CASES for kind in [corpus[label][1]] for step in corpus[label][2])


@pytest.mark.parametrize("label", PL_CASES)
def test_pf_21_under_a_later_prove_the_pins_of_what_main_prints_hold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, label: str) -> None:
    """A case of the newest pinned corpus, run in this process under a Prove that states a later
    version: with that version written as the pins hold it, every byte is main's."""
    import pin_support
    from pl_pins import PINS, pin_corpus
    from tf5_pins import ran_case
    from tf20_pins import digest_text_steps

    pinned = json.loads(PINS.read_text(encoding="utf-8"))["piped"]
    place, kind, steps = pin_corpus()[label]
    monkeypatch.setattr(pin_support, "installed", lambda: LATER)
    with _under(LATER):
        got = ran_case(tmp_path, place, kind, steps)
    assert digest_text_steps(got) == pinned[label], label


@pytest.mark.parametrize("label", SETUP_CASES)
def test_pf_21_under_a_later_prove_doctor_and_init_hold_as_pinned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, label: str) -> None:
    import pin_support
    from pl_pins import PINS
    from tf5_pins import machine, ran_case
    from tf20_pins import SETUP, digest_text_steps

    pinned = json.loads(PINS.read_text(encoding="utf-8"))["setup"]
    monkeypatch.setattr(pin_support, "installed", lambda: LATER)
    with _under(LATER):
        got = [(code, machine(out), machine(err)) for code, out, err in ran_case(tmp_path, *SETUP[label])]
    assert digest_text_steps(got) == pinned[label], label


def test_pf_21_a_later_prove_is_seen_before_it_is_written_as_pinned(tmp_path: Path) -> None:
    """The control: under a Prove that states a later version, Trace does print that version."""
    from tf13_support import cli, workspace

    work = workspace(tmp_path)
    with _under(LATER):
        said = cli(work, ["--version"])
    assert f"(poisson-prove {LATER}, Python " in said.out, said.out
    assert f"(poisson-prove {FORMAT_1_0}, Python " in as_pinned(said.out, LATER)
