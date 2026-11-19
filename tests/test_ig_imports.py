"""IG-1 to IG-9: a Prove at or above the floor that lacks a name Trace imports from it is refused
in one line, by every command that reads through Prove, before anything is written.

Trace accepts any ``poisson-prove`` at or above its floor, with no upper cap. A later Prove that
drops or renames a module or a name Trace imports would otherwise crash every command with exit
3 and a traceback, and write the errors log. The rule these tests hold:

1. **What counts.** Every module and every name Trace imports from ``poisson_prove``, wherever in
   the package it is imported, read from the source itself (``imported``), so that an import
   added later is held without a test changing.
2. **The refusal.** Each command that refuses a Prove below the floor refuses such a Prove too,
   exit 1, nothing on stdout, nothing written (the errors log included), in one ``error:`` line
   in the below-floor refusal's words, which then names what is missing, in the order of its
   dotted name: ``… through Prove (the poisson-prove package, version 0.4.0 or later) and found
   poisson-prove 0.9.0, which has no poisson_prove.store.RunTally``. A module that cannot be
   imported is named as the module, not as its names. Several are named ``A and B`` or ``A, B
   and C``. No ``next:`` line: the install line under the below-floor refusal would change
   nothing, since pip holds the Prove found to meet it.
3. **doctor.** Its prove check fails, ``poisson-prove 0.9.0 is installed and has no
   poisson_prove.store.RunTally, which Trace imports from it``, with no command of its own;
   ``doctor`` exits 4.
4. **The floor's refusals stand.** A Prove below the floor, absent or stating no version is
   refused as such. ``--help`` and ``--version`` need nothing from Prove.

The stand-in: the installed Prove, loaded whole at the interpreter's start by a
``sitecustomize`` module in a scratch folder put on ``PYTHONPATH``, then stripped in memory of
what a test names. The installed package is never edited.

- IG-1: the source scan finds what Trace imports, and every name it finds is in the installed Prove.
- IG-2: each name Trace imports, missing alone, is refused word for word.
- IG-3: each module Trace imports, missing whole, is refused naming the module.
- IG-4: every command refuses, for a name ``runs`` itself never imports; ``import`` for a module too.
- IG-5: several missing are all named, in order.
- IG-6: the refusal names the version the Prove states.
- IG-7: ``doctor`` fails its prove check and exits 4.
- IG-8: the API and the terminal app refuse too.
- IG-9: help and the version line need nothing; the floor's own refusals come first.
"""

from __future__ import annotations

import ast
import importlib
import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest
from pf_support import (
    EVENT, IMPORT_WRITES, INIT_READS, JUNIT, MODULES, NAMES, READS, REPO, RUNS, STORE_1_2, Ran, below, copy, env_of, home_of, tree,
)
from pin_support import INSTALL, OR_LATER, installed

SRC = REPO / "src" / "poisson_trace"
PACKAGE = "poisson_prove"


def imported() -> list[str]:
    """Every module and name the package imports from ``poisson_prove``, dotted, in order:
    ``poisson_prove.store.Store`` for ``from poisson_prove.store import Store``, and
    ``poisson_prove.store`` for ``import poisson_prove.store``. ``import poisson_prove`` alone is
    the package, which the floor's own refusals hold."""
    found: set[str] = set()
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
                if node.module == PACKAGE or node.module.startswith(PACKAGE + "."):
                    found.update(f"{node.module}.{alias.name}" for alias in node.names)
            elif isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names if alias.name.startswith(PACKAGE + "."))
    return sorted(found)


IMPORTED = imported()


def _is_module(dotted: str) -> bool:
    try:
        importlib.import_module(dotted)
    except ImportError:
        return False
    return True


#: Prove's modules that Trace imports, or imports names from.
MODULES_USED = sorted({d for d in IMPORTED if _is_module(d)} | {d.rpartition(".")[0] for d in IMPORTED if not _is_module(d)} - {PACKAGE})
#: The names Trace imports that are not modules.
NAMES_USED = [d for d in IMPORTED if not _is_module(d)]

#: A name ``runs`` never imports on its own way through: a command that went on without the
#: check would not meet its absence.
UNUSED_BY_RUNS = "poisson_prove.store.RunTally"

#: A command of each family, the module that runs it, and what it does through Prove (as PF-3).
FAMILIES = {
    "runs": ("trace", ["runs", "--store", "STORE"], READS),
    "runs --json": ("trace", ["runs", "--store", "STORE", "--json"], READS),
    "where": ("trace", ["where", "#1", "--store", "STORE", *EVENT], READS),
    "where --save": ("trace", ["where", "#1", "--store", "STORE", *EVENT, "--save"], READS),
    "compare": ("trace", ["compare", "#2", "#1", "--store", "STORE", *EVENT, "--max-mde-hr", "1.5"], READS),
    "fix-check": ("trace", ["fix-check", "#2", "#1", "--store", "STORE", *EVENT, "--inputs", "all", "--max-mde", "0.5"], READS),
    "fix-check --out": ("trace", ["fix-check", "#2", "#1", "--store", "STORE", *EVENT, "--inputs", "all", "--max-mde", "0.5", "--out", "bundle"], READS),
    "changes": ("trace", ["changes", "#2", "#1", "--store", "STORE", *EVENT], READS),
    "name": ("trace", ["name", "#1", "a name", "--store", "STORE"], READS),
    "name --list": ("trace", ["name", "--list", "--store", "STORE"], READS),
    "ui": ("trace", ["ui", "--store", "STORE"], READS),
    "init": ("trace", ["init", "--yes"], INIT_READS),
    "import": ("trace", ["import", "junit", str(JUNIT), "--store", "NEWSTORE", "--run", "suite"], IMPORT_WRITES),
    "poisson-trace-import": ("import", ["junit", str(JUNIT), "--store", "NEWSTORE", "--run", "suite"], IMPORT_WRITES),
}


def said(names: Sequence[str]) -> str:
    """``A``, ``A and B``, ``A, B and C``: the names in order."""
    ordered = sorted(names)
    return ordered[0] if len(ordered) == 1 else f"{', '.join(ordered[:-1])} and {ordered[-1]}"


def missing(does: str, found: str, names: Sequence[str]) -> list[str]:
    return [f"error: {does} through Prove (the poisson-prove package, version {OR_LATER}) and found poisson-prove {found}, which has no {said(names)}"]


def doctor_line(found: str, names: Sequence[str]) -> str:
    return f"poisson-prove {found} is installed and has no {said(names)}, which Trace imports from it"


# ---------- the stand-in ----------


def standin(cwd: Path, gone: Sequence[str], states: str | None = None) -> Path:
    """A scratch folder beside ``cwd`` holding a ``sitecustomize`` that loads the installed Prove
    whole, then removes each of ``gone`` from it in memory (a module from ``sys.modules`` and its
    package, a name from its module) and, given ``states``, has it state that version."""
    folder = cwd.parent / f"{cwd.name}.prove"
    folder.mkdir(exist_ok=True)
    code = (
        "import importlib, sys\n"
        f"for _m in {MODULES_USED!r}:\n"
        "    importlib.import_module(_m)\n"
        f"for _d in {list(gone)!r}:\n"
        "    _parent, _, _last = _d.rpartition('.')\n"
        "    if _d in sys.modules:\n"
        "        for _k in [k for k in sys.modules if k == _d or k.startswith(_d + '.')]:\n"
        "            sys.modules[_k] = None\n"
        "    if hasattr(sys.modules[_parent], _last):\n"
        "        delattr(sys.modules[_parent], _last)\n"
    )
    if states is not None:
        code += f"sys.modules['poisson_prove'].__version__ = {states!r}\n"
    (folder / "sitecustomize.py").write_text(code, encoding="utf-8")
    return folder


def without(argv: Sequence[object], cwd: Path, gone: Sequence[str], command: str = "trace", states: str | None = None,
            code: str | None = None) -> Ran:
    """The command, or ``code``, in an interpreter whose Prove lacks each of ``gone``."""
    env = env_of(cwd)
    env["PYTHONPATH"] = str(standin(cwd, gone, states))
    script = code if code is not None else f"import sys\nfrom {MODULES[command]} import main\nsys.exit(main(sys.argv[1:]))\n"
    return Ran(subprocess.run([sys.executable, "-c", script, *[str(a) for a in argv]], capture_output=True, text=True, cwd=cwd, env=env,
                              timeout=300))


def _argv(family: str, work: Path) -> list[str]:
    if not (work / "store").exists():
        copy(STORE_1_2, work)
    swap = {"STORE": str(work / "store"), "NEWSTORE": str(work / "new-store")}
    return [swap.get(a, a) for a in FAMILIES[family][1]]


def _no_errors_log(cwd: Path) -> None:
    log = home_of(cwd) / ".cache" / "poisson-trace" / "errors.log"
    assert not log.exists(), log.read_text(encoding="utf-8")


def _refused(ran: Ran, lines: list[str]) -> None:
    assert (ran.code, ran.out) == (1, ""), ran.text
    assert ran.lines() == lines, ran.err
    assert "Traceback" not in ran.err and "unexpected failure" not in ran.err, ran.err


# ---------- IG-1 ----------


def test_ig_1_the_scan_finds_what_trace_imports() -> None:
    assert {"poisson_prove.store", "poisson_prove.steps", "poisson_prove.trace"} <= set(MODULES_USED), MODULES_USED
    assert {"poisson_prove.store.Store", "poisson_prove.store.RunManifest", "poisson_prove.store.RunTally", "poisson_prove.store.EpisodeRecord",
            "poisson_prove.store.config_hash", "poisson_prove.steps.declaration_check", "poisson_prove.trace.KINDS",
            "poisson_prove.trace.CONTENT_KEYS", "poisson_prove.trace.OBSERVATION_KEYS", "poisson_prove.trace.Trace",
            "poisson_prove.trace.from_otel"} <= set(NAMES_USED), NAMES_USED
    assert UNUSED_BY_RUNS in NAMES_USED


def test_ig_1_every_name_found_is_in_the_installed_prove() -> None:
    for dotted in NAMES_USED:
        module, _, name = dotted.rpartition(".")
        assert hasattr(importlib.import_module(module), name), dotted


def test_ig_1_the_stand_in_lacks_what_it_is_told_to_and_nothing_else(tmp_path: Path) -> None:
    code = ("import importlib, sys\n"
            f"for d in {IMPORTED!r}:\n"
            "    m, _, n = d.rpartition('.')\n"
            "    try:\n        ok = hasattr(importlib.import_module(m), n)\n    except ImportError:\n        ok = False\n"
            "    print(d, ok)\n")
    ran = without([], tmp_path, [UNUSED_BY_RUNS, "poisson_prove.steps"], code=code)
    assert ran.code == 0, ran.text
    shown = dict(line.split() for line in ran.out.splitlines())
    gone = {d for d in IMPORTED if d == UNUSED_BY_RUNS or d.startswith("poisson_prove.steps")}
    assert {d for d, ok in shown.items() if ok == "False"} == gone, shown
    whole = without([], tmp_path, [], code=code)
    assert all(line.endswith(" True") for line in whole.out.splitlines()), whole.out


# ---------- IG-2, IG-3 ----------


@pytest.mark.parametrize("name", NAMES_USED)
def test_ig_2_each_name_missing_alone_is_refused_word_for_word(tmp_path: Path, name: str) -> None:
    store = copy(STORE_1_2, tmp_path)
    before = tree(tmp_path)
    ran = without(["runs", "--store", store], tmp_path, [name])
    _refused(ran, missing(READS, installed(), [name]))
    assert tree(tmp_path) == before
    _no_errors_log(tmp_path)


@pytest.mark.parametrize("module", MODULES_USED)
def test_ig_3_each_module_missing_whole_is_refused_naming_the_module(tmp_path: Path, module: str) -> None:
    store = copy(STORE_1_2, tmp_path)
    before = tree(tmp_path)
    ran = without(["fix-check", "#2", "#1", "--store", store, *EVENT, "--inputs", "all", "--max-mde", "0.5"], tmp_path, [module])
    _refused(ran, missing(READS, installed(), [module]))
    assert tree(tmp_path) == before
    _no_errors_log(tmp_path)


# ---------- IG-4 ----------


@pytest.mark.parametrize(("family", "gone"), [*[(family, UNUSED_BY_RUNS) for family in FAMILIES], ("import", "poisson_prove.trace")])
def test_ig_4_every_command_refuses(tmp_path: Path, family: str, gone: str) -> None:
    command, _, does = FAMILIES[family]
    argv = _argv(family, tmp_path)
    before = tree(tmp_path)
    ran = without(argv, tmp_path, [gone], command)
    _refused(ran, missing(does, installed(), [gone]))
    assert tree(tmp_path) == before
    _no_errors_log(tmp_path)


def test_ig_4_every_command_refuses_by_name_too(tmp_path: Path) -> None:
    store = copy(STORE_1_2, tmp_path)
    before = tree(tmp_path)
    a, b = NAMES
    for argv in (["where", b, "--store", store, *EVENT], ["fix-check", a, b, "--store", store, *EVENT, "--inputs", "all", "--max-mde", "0.5"],
                 ["changes", RUNS[STORE_1_2][0], RUNS[STORE_1_2][1], "--store", store, *EVENT]):
        _refused(without(argv, tmp_path, [UNUSED_BY_RUNS]), missing(READS, installed(), [UNUSED_BY_RUNS]))
    assert tree(tmp_path) == before


# ---------- IG-5, IG-6 ----------


def test_ig_5_several_missing_are_all_named_in_order(tmp_path: Path) -> None:
    store = copy(STORE_1_2, tmp_path)
    two = ["poisson_prove.trace.KINDS", "poisson_prove.store.RunTally"]
    _refused(without(["runs", "--store", store], tmp_path, two), missing(READS, installed(), two))
    three = [*two, "poisson_prove.steps"]
    line = without(["runs", "--store", store], tmp_path, three).lines()
    assert line == missing(READS, installed(), three), line
    assert line[0].endswith("which has no poisson_prove.steps, poisson_prove.store.RunTally and poisson_prove.trace.KINDS"), line


@pytest.mark.parametrize("states", ["0.9.0", "1.0.0", "0.4.0.post1"])
def test_ig_6_the_refusal_names_the_version_the_prove_states(tmp_path: Path, states: str) -> None:
    store = copy(STORE_1_2, tmp_path)
    ran = without(["runs", "--store", store], tmp_path, [UNUSED_BY_RUNS], states=states)
    _refused(ran, missing(READS, states, [UNUSED_BY_RUNS]))


# ---------- IG-7 ----------


def _prove_check(ran: Ran) -> tuple[dict, dict]:  # type: ignore[type-arg]
    doc = ran.json()
    (check,) = [c for c in doc["checks"] if c["name"] == "prove"]
    return doc, check


@pytest.mark.parametrize("gone", [[UNUSED_BY_RUNS], ["poisson_prove.steps"], ["poisson_prove.store.Store", "poisson_prove.trace.KINDS"]])
def test_ig_7_doctor_fails_its_prove_check_and_exits_4(tmp_path: Path, gone: list[str]) -> None:
    ran = without(["doctor", "--json"], tmp_path, gone, states="0.9.0")
    assert ran.code == 4, ran.text
    assert "Traceback" not in ran.text and "unexpected failure" not in ran.text, ran.text
    doc, check = _prove_check(ran)
    assert check == {"name": "prove", "ok": False, "line": doctor_line("0.9.0", gone), "next": None}, check
    # with no trace.toml here the config check fails too; the prove check is named first
    assert doc["verdict"] == "not ready" and doc["sentence"].startswith("prove "), doc
    assert doc["sentence"].endswith(f": {doctor_line('0.9.0', gone)}") and INSTALL not in json.dumps(doc), doc
    plain = without(["doctor"], tmp_path, gone, states="0.9.0")
    assert plain.code == 4, plain.text
    assert f"  prove     {doctor_line('0.9.0', gone)}" in plain.out.splitlines(), plain.out
    assert "Traceback" not in plain.text and "unexpected failure" not in plain.text, plain.text
    _no_errors_log(tmp_path)


def test_ig_7_doctor_reads_no_store_through_the_prove_it_refused(tmp_path: Path) -> None:
    """With a config naming a store, doctor goes on to its other checks without crashing."""
    copy(STORE_1_2, tmp_path)
    (tmp_path / "trace.toml").write_text('version = 1\n\n[store]\npath = "store"\n', encoding="utf-8")
    before = tree(tmp_path)
    for argv in (["doctor"], ["doctor", "--json"]):
        ran = without(argv, tmp_path, ["poisson_prove.store.Store"])
        assert ran.code == 4, ran.text
        assert "Traceback" not in ran.text and "unexpected failure" not in ran.text, ran.text
    assert tree(tmp_path) == before
    _no_errors_log(tmp_path)


def test_ig_7_doctor_setup_reads_no_import_through_the_prove_it_refused(tmp_path: Path) -> None:
    """``doctor --setup`` fails its prove check the same way, and says each ``[[import]]`` file
    is not read because of what Prove lacks, naming no install line."""
    copy(STORE_1_2, tmp_path)
    shutil.copy(JUNIT, tmp_path / "suite.xml")
    (tmp_path / "trace.toml").write_text('version = 1\n\n[store]\npath = "store"\n\n'
                                         '[[import]]\nfile = "suite.xml"\ntool = "junit"\nname = "suite"\n', encoding="utf-8")
    before = tree(tmp_path)
    ran = without(["doctor", "--setup", "--json"], tmp_path, [UNUSED_BY_RUNS])
    assert "Traceback" not in ran.text and "unexpected failure" not in ran.text, ran.text
    assert ran.code == 1, ran.text
    doc = ran.json()
    (check,) = [c for c in doc["checks"] if c["name"] == "prove"]
    assert check == {"name": "prove", "ok": False, "line": doctor_line(installed(), [UNUSED_BY_RUNS]), "next": None}, check
    (imp,) = [c for c in doc["checks"] if c["name"] == "import"]
    assert imp == {"name": "import", "ok": False, "line": "suite.xml: not read, since poisson-prove lacks what Trace imports from it", "next": None}, imp
    assert INSTALL not in ran.out, ran.out
    plain = without(["doctor", "--setup"], tmp_path, [UNUSED_BY_RUNS])
    assert plain.code == 1 and "Traceback" not in plain.text and "unexpected failure" not in plain.text, plain.text
    assert INSTALL not in plain.text, plain.text
    assert tree(tmp_path) == before
    _no_errors_log(tmp_path)


# ---------- IG-8 ----------


def test_ig_8_the_api_refuses_to_open_a_store(tmp_path: Path) -> None:
    store = copy(STORE_1_2, tmp_path)
    before = tree(tmp_path)
    code = ("import sys\nfrom poisson_trace import api\n"
            "try:\n    api.open_store(sys.argv[1])\n"
            "except api.Refusal as e:\n    print(str(e))\n    sys.exit(0)\n"
            "sys.exit(9)\n")
    ran = without([store], tmp_path, [UNUSED_BY_RUNS], code=code)
    assert ran.code == 0, ran.text
    assert ran.out.strip() == missing(READS, installed(), [UNUSED_BY_RUNS])[0].removeprefix("error: "), ran.out
    assert tree(tmp_path) == before


def test_ig_8_the_terminal_app_shows_the_refusal_and_lists_no_run(tmp_path: Path) -> None:
    from tf19_support import Step, run_pty, strip_escapes

    store = copy(STORE_1_2, tmp_path)
    before = tree(store)
    home = tmp_path.parent / f"{tmp_path.name}.apphome"
    home.mkdir()
    ran = run_pty(["--store", "store"], home=home, cwd=tmp_path, steps=(Step(b"q", until="which has no"),), timeout=45,
                  python_path=[standin(tmp_path, [UNUSED_BY_RUNS])])
    shown = " ".join(strip_escapes(ran.out).split())
    assert "which has no" in shown and UNUSED_BY_RUNS in shown, shown[-2000:]
    assert not any(word in shown for word in (*NAMES, *RUNS[STORE_1_2])), "no run of the store is listed"
    assert "Traceback" not in shown and "unexpected failure" not in shown
    assert tree(store) == before


# ---------- IG-9 ----------


def test_ig_9_help_and_the_version_need_nothing_from_prove(tmp_path: Path) -> None:
    for argv in (["--help"], ["runs", "--help"], ["fix-check", "--help"], ["import", "--help"], ["doctor", "--help"]):
        ran = without(argv, tmp_path, [UNUSED_BY_RUNS, "poisson_prove.steps"])
        assert ran.code == 0 and ran.out.strip() and ran.err == "", (argv, ran.text)
    said_ = without(["--version"], tmp_path, [UNUSED_BY_RUNS, "poisson_prove.steps"], states="0.9.0")
    assert said_.code == 0 and said_.err == "" and "(poisson-prove 0.9.0, Python " in said_.out, said_.text


@pytest.mark.parametrize("states", ["0.3.0", "0.4.0rc1"])
def test_ig_9_a_prove_below_the_floor_is_refused_as_below_it_first(tmp_path: Path, states: str) -> None:
    store = copy(STORE_1_2, tmp_path)
    ran = without(["runs", "--store", store], tmp_path, [UNUSED_BY_RUNS], states=states)
    assert (ran.code, ran.out) == (1, ""), ran.text
    assert ran.lines() == below(READS, states), ran.err


def test_ig_9_the_whole_prove_is_read_and_doctor_is_ready(tmp_path: Path) -> None:
    store = copy(STORE_1_2, tmp_path)
    ran = without(["runs", "--store", store, "--json"], tmp_path, [])
    assert ran.code == 0, ran.text
    json.loads(ran.out)
    doctor = without(["doctor", "--json"], tmp_path, [])
    check = [c for c in doctor.json()["checks"] if c["name"] == "prove"][0]
    assert check["ok"] is True, check
