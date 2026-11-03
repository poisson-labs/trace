"""Shared by TF16's tests (spec section 16.1, step 1): Trace reads Prove under its new name,
``poisson_prove``, in stores Prove 0.0.1 wrote and stores the published Prove writes, and takes a
run's name given at sweep time.

Nothing here imports ``proofload`` or another test module: these tests run where only
``poisson_prove`` is installed. Every store a test builds is written through Prove's own
``Store``; the two committed stores were written by Prove's own sweep (``fixtures/prove-stores``).
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pin_support import INSTALL, RECORDED

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
STORES = TESTS / "fixtures" / "prove-stores"
# written by proofload 0.0.1, Prove before it was published: no .poisson/, no events.jsonl, no names
OLD = STORES / "prove-0.0.1"
OLD_A = "20261028T154158Z-c830"  # the mock agent
OLD_B = "20261028T154200Z-9ace"  # the patched mock agent, paired with OLD_A
# written by poisson-prove 0.1.2 from PyPI (the Prove Trace pins), each run named at sweep time
NEW = STORES / f"prove-{RECORDED}"
NEW_BEFORE = "20261103T150857Z-24db"  # sweep --name "agent before", the mock agent
NEW_AFTER = "20261103T150859Z-81ef"  # sweep --name "agent after", the patched mock agent
SWEEP_NAMES = {NEW_BEFORE: "agent before", NEW_AFTER: "agent after"}
# the names Trace computes for runs of the target mock-agent on the day of each store (spec
# section 5.2): the old store's runs, and the new store's
COMPUTED = ("mock-agent 2026-10-28 a", "mock-agent 2026-10-28 b")
NEW_COMPUTED = ("mock-agent 2026-11-03 a", "mock-agent 2026-11-03 b")
EVENT = "violated"
POISSON = ".poisson"

# the Prove version Trace reads, and the one command that installs it (pin_support.py)
PROVE_VERSION = RECORDED
INSTALL_PROVE = INSTALL
RUN_ID = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{4}")


@pytest.fixture(autouse=True)
def scratch_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """``HOME`` is a folder of the test's own."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    return home


@dataclass(frozen=True)
class Ran:
    code: int
    out: str
    err: str

    @property
    def text(self) -> str:
        return self.out + self.err

    def json(self) -> Any:
        return json.loads(self.out)

    def err_lines(self) -> list[str]:
        return [line for line in self.err.splitlines() if line.strip()]


ESCAPED = -1  # anything but SystemExit left main: a traceback, not an answer


def trace(argv: Sequence[Any], cwd: Path | None = None) -> Ran:
    """``poisson-trace`` in-process, in ``cwd`` when given."""
    from poisson_trace.cli import main

    out, err = io.StringIO(), io.StringIO()
    with _in(cwd), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main([str(a) for a in argv])
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        except BaseException:  # noqa: BLE001
            traceback.print_exc()
            code = ESCAPED
    return Ran(int(code), out.getvalue(), err.getvalue())


@contextlib.contextmanager
def _in(folder: Path | None) -> Iterator[None]:
    if folder is None:
        yield
        return
    before = os.getcwd()
    os.chdir(folder)
    try:
        yield
    finally:
        os.chdir(before)


def fresh(argv: Sequence[Any], *, prove: str, cwd: Path | None = None) -> Ran:
    """``poisson-trace`` in a fresh interpreter, with Prove as ``prove`` says: ``absent`` (no
    ``poisson_prove``), ``old`` (no ``poisson_prove``, and ``proofload`` 0.0.1 importable, as
    the pin Trace had before this step), or a version string (a ``poisson_prove`` stating it)."""
    head = "import sys, types\n"
    if prove in ("absent", "old"):
        head += "sys.modules['poisson_prove'] = None\n"
    else:
        head += (
            f"fake = types.ModuleType('poisson_prove')\nfake.__version__ = {prove!r}\n"
            "sys.modules['poisson_prove'] = fake\n"
        )
    if prove == "old":
        head += (
            "old = types.ModuleType('proofload')\nold.__version__ = '0.0.1'\n"
            "sys.modules['proofload'] = old\n"
        )
    code = head + "from poisson_trace.cli import main\nsys.exit(main(sys.argv[1:]))\n"
    proc = subprocess.run(
        [sys.executable, "-c", code, *[str(a) for a in argv]], capture_output=True, cwd=cwd,
        timeout=120,
    )
    return Ran(proc.returncode, proc.stdout.decode("utf-8", "replace"),
               proc.stderr.decode("utf-8", "replace"))


def prove_cli(argv: Sequence[Any]) -> Ran:
    """``poisson-prove`` itself, in a fresh interpreter."""
    proc = subprocess.run(
        [sys.executable, "-m", "poisson_prove", *[str(a) for a in argv]], capture_output=True,
        timeout=120, env={**os.environ, "NO_COLOR": "1"},
    )
    return Ran(proc.returncode, proc.stdout.decode("utf-8", "replace"),
               proc.stderr.decode("utf-8", "replace"))


# ---------- stores ----------


def copy_store(source: Path, dest: Path, runs: Sequence[str] | None = None) -> Path:
    """A copy of the store ``source`` at ``dest``: the runs named, or all of it."""
    if runs is None:
        shutil.copytree(source, dest)
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    for run in runs:
        shutil.copytree(source / run, dest / run)
    return dest


def copies(tmp_path: Path) -> tuple[Path, Path]:
    """Copies of the two committed stores, 0.0.1's and 0.1.2's, so no build under test can write
    into the committed ones."""
    return copy_store(OLD, tmp_path / "prove-0.0.1"), copy_store(NEW, tmp_path / f"prove-{RECORDED}")


def snapshot(root: Path) -> dict[str, tuple[str, int]]:
    """Every file under ``root``: its digest and its modification time."""
    return {
        str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
        for p in sorted(root.rglob("*")) if p.is_file()
    }


@dataclass(frozen=True)
class Made:
    """One run a test writes through Prove's own store: its id, start and sweep-time name."""

    run_id: str
    created_at: str
    name: str | None = None
    target_id: str = "mock-agent"
    outcomes: tuple[str, ...] = ("violated", "completed")


def make_store(root: Path, runs: Sequence[Made]) -> Path:
    """A store written through ``poisson_prove.store``, one complete run per ``Made``."""
    from poisson_prove.store import EpisodeRecord, RunManifest, Store, config_hash

    store = Store(root)
    root.mkdir(parents=True, exist_ok=True)
    for made in runs:
        store.create_run(RunManifest(
            run_id=made.run_id, target_id=made.target_id, t_unit="steps", run_salt="00",
            axis_types={"case": "categorical"}, backend="local", environment={},
            created_at=made.created_at, name=made.name,
        ))
        records = []
        for i, outcome in enumerate(made.outcomes):
            config = {"case": f"c{i}"}
            records.append(EpisodeRecord(
                run_id=made.run_id, config_hash=config_hash(config), config=config, seed=i,
                replicate_index=0, outcome=outcome, t=1.0, horizon=3.0, confidence=None,
                meta={}, error=None, wall_time=0.0, backend_meta={},
            ))
        store.append(made.run_id, records)
        store.mark_complete(made.run_id)
    return root


def run_names(store: Path | str) -> dict[str, str]:
    """Each run's name, as ``poisson-trace runs --all --json`` gives it, by run id."""
    ran = trace(["runs", "--store", store, "--all", "--json"])
    assert ran.code == 0, ran.text
    return {row["run_id"]: row["name"] for row in ran.json()["runs"]}


def resolved(store: Path | str, word: str) -> str | None:
    """The run id ``where WORD`` reads, or None when the word is refused."""
    ran = trace(["where", word, "--store", store, "--event", EVENT, "--json"])
    if ran.code == 1 and not ran.out.strip():
        return None
    assert ran.code == 0, ran.text
    run_id: str = ran.json()["run"]["run_id"]
    return run_id
