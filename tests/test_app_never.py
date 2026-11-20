"""TF19-7: what the app never does (``docs/app.md``, What it never does).

**TF19-7** No network call: while the app opens every screen, opens a link, copies one, saves,
names and imports, no socket connects and no name is looked up; the app's modules import no
networking module. No key read: with keys planted in the environment, no variable whose name holds
``KEY``, ``TOKEN``, ``SECRET`` or ``PASSWORD`` is read, and no planted value is on any screen or in
any file. No write outside the core: the app's modules hold no call that writes a file, removes
one or makes a folder (writes are the core's: ``api.save``, ``api.build_pages``, ``api.name``,
``api.import_run``), and a whole session writes nothing outside the stores' ``.poisson/`` but the
import's run and the name the user said yes to.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from app_support import (
    KEY_NAME,
    PLANTED_KEYS,
    Session,
    Type,
    app_files,
    app_world,
    changed,
    copy_world,
    drive,
    found_steps,
    imports_of,
    snapshot,
)

NETWORK = ("socket", "ssl", "http", "urllib", "requests", "httpx", "aiohttp", "urllib3", "ftplib", "smtplib", "telnetlib",
           "xmlrpc", "websockets")
#: Calls that write, remove or make a file or folder: by the method's name, by the module's
#: function, or the builtin ``open``.
WRITING = frozenset({"write_text", "write_bytes", "mkdir", "makedirs", "unlink", "rmdir", "rmtree", "chmod", "touch",
                     "copy2", "copyfile", "copytree", "symlink_to", "hardlink_to", "mkstemp", "mkdtemp",
                     "NamedTemporaryFile", "TemporaryDirectory", "SpooledTemporaryFile"})
WRITING_CALLS = frozenset({"os.replace", "os.remove", "os.rename", "os.open", "os.truncate", "shutil.move",
                           "shutil.copy", "json.dump", "pickle.dump", "io.open", "Path.open", "codecs.open"})


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return app_world(tmp_path_factory)


@pytest.fixture
def work(world: Path, tmp_path: Path) -> Path:
    return copy_world(world, tmp_path)


def _tour() -> list[object]:
    """Every screen, a link opened and copied, a verdict of each kind shown (and saved)."""
    return ["r", "enter", "tab", "enter", "y", "escape", "escape", "i", "s", "escape", "c", "enter", "k", "d", "escape",
            "escape", "escape", "f", "enter", "t", "g", "escape", "d", "escape", "escape", "escape", "?", "escape"]


@pytest.fixture(scope="module")
def toured(world: Path, tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Session, list[str]]:
    """One tour of the app in a copy of its own, read by the tests that only read what it did:
    the folder, the session, and the files the tour changed."""
    work = copy_world(world, tmp_path_factory.mktemp("tf19-never-tour"))
    before = snapshot(work)
    s = drive(work, _tour(), size=(120, 40))
    return work, s, sorted(changed(before, snapshot(work)))


@pytest.mark.slow
def test_tf19_7_no_network_call(toured: tuple[Path, Session, list[str]]) -> None:
    _work, s, _moved = toured
    assert s.fakes.connects == []
    assert s.fakes.opened and s.fakes.copied


@pytest.mark.parametrize("path", [p.name for p in app_files()] or ["_app.py"])
def test_tf19_7_the_app_imports_no_network_module(path: str) -> None:
    from app_support import PACKAGE

    names = imports_of(PACKAGE / path)
    used = sorted(n for n in names if n.split(".")[0] in NETWORK)
    assert used == [], used


@pytest.mark.slow
def test_tf19_7_no_key_read(toured: tuple[Path, Session, list[str]]) -> None:
    _work, s, _moved = toured
    keys = sorted({k for k in s.fakes.env_read if KEY_NAME.search(k) or k == "*"})
    assert keys == [], keys
    for g in s.grids:
        for value in PLANTED_KEYS.values():
            assert value not in g.text()


@pytest.mark.slow
def test_tf19_7_no_planted_key_in_a_file(toured: tuple[Path, Session, list[str]]) -> None:
    work, _s, moved = toured
    for name in moved:
        path = work / name
        if path.is_file():
            data = path.read_bytes()
            for value in PLANTED_KEYS.values():
                assert value.encode() not in data, name


@pytest.mark.parametrize("path", [p.name for p in app_files()] or ["_app.py"])
def test_tf19_7_no_write_in_the_app_s_own_code(path: str) -> None:
    from app_support import PACKAGE

    tree = ast.parse((PACKAGE / path).read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in ("open", *WRITING):
                found.append(f"{f.id} at line {node.lineno}")
            elif isinstance(f, ast.Attribute) and (f.attr in WRITING or ast.unparse(f) in WRITING_CALLS):
                found.append(f"{ast.unparse(f)} at line {node.lineno}")
    assert found == [], found


@pytest.mark.parametrize("path", [p.name for p in app_files()] or ["_app.py"])
def test_tf19_7_no_environment_read_in_the_app_s_own_code_but_its_switches(path: str) -> None:
    """The app's modules read only ``NO_COLOR`` of the environment (the switch ``docs/cli-look.md``
    names); ``CI`` and ``TERM`` are the command line's, which decides whether the app opens."""
    from app_support import PACKAGE

    tree = ast.parse((PACKAGE / path).read_text(encoding="utf-8"))
    read = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("get", "getenv"):
            target = node.func.value
            text = ast.unparse(target)
            if text in ("os.environ", "os", "environ") and node.args:
                read.append(ast.unparse(node.args[0]))
        if isinstance(node, ast.Subscript) and ast.unparse(node.value) in ("os.environ", "environ"):
            read.append(ast.unparse(node.slice))
    assert set(read) <= {"'NO_COLOR'"}, read


@pytest.mark.slow
def test_tf19_7_a_session_writes_only_through_the_core(work: Path) -> None:
    from poisson_trace import core

    found = [f for f in core.found_results(work, store="jstore") if not f.imported]
    i = next(k for k, f in enumerate(found) if not f.fill)
    before = snapshot(work)
    s = drive(work, [*_tour(), "r", "n", Type("tour name"), "enter", "y", "escape", *found_steps(work, i), "y"],
              size=(120, 40))
    moved = changed(before, snapshot(work))
    imported = {c[0][0] for c in s.spy.called("api.import_run")}
    assert imported, s.spy.names()
    new_runs = {m.split("/")[1] for m in moved if m.startswith("jstore/") and not m.startswith("jstore/.poisson/")}
    assert len(new_runs) == 1, sorted(moved)
    for m in moved:
        top = m.split("/")[0]
        assert top in ("store", "jstore", "tables"), m
        inside = m.split("/", 1)[1]
        assert inside.startswith(".poisson/") or inside.split("/")[0] in new_runs or "names" in inside, m
    assert not any(m.startswith(("trace.toml", "results/", "files/", "conf/")) for m in moved)


def test_tf19_7_a_verdict_shown_writes_no_key(work: Path) -> None:
    """Fast twin of the tour's file check: a compare shown and saved, its files hold no planted key."""
    before = snapshot(work)
    s = drive(work, ["c", "enter", "tab", "enter", "y"], size=(120, 40))
    assert s.fakes.connects == [] and s.fakes.opened and s.fakes.copied
    moved = changed(before, snapshot(work))
    assert moved
    for name in moved:
        data = (work / name).read_bytes()
        assert not any(v.encode() in data for v in PLANTED_KEYS.values()), name

