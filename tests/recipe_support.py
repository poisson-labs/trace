"""Shared helpers for TF20's tests: the recipe that runs Poisson Tasks, Poisson Prove and Poisson
Trace together, and its fixtures. Not collected.

What the recipe adds, in one place (each test file's opening says which invariant it holds):

``docs/recipes/with-tasks-and-prove.md``
    The recipe: one page like every other recipe, its every block run by the docs runner
    (``docs_support``'s marks) and by ``tools/docs_check.py``.
``examples/three-tools/``
    Its fixtures: ``tasks/depth-d1.jsonl`` and ``tasks/depth-d3.jsonl`` as Tasks' ``generate``
    writes them and nothing else in ``tasks/``; ``PROVENANCE.md``, naming the Tasks version
    and the command; ``agent.py``, the stand-in agent; ``prove_rollout.py``, Prove's wrapper;
    ``prove-before.toml`` and ``prove-after.toml``; and the team's pytest file, the one file
    named ``test_*.py`` in the folder.
the rest
    The README links the recipe; the CHANGELOG's count of recipes says sixteen; the
    development extra pins Tasks; ``tools/docs_check.py`` copies ``examples/`` beside the
    fixtures; the clean-install job installs Tasks at its pin and fetches its tokenizer file
    before the socket guard. Nothing else moves (``test_tf20_unchanged.py``).

The agent's contract (frozen here so that a test can call it)
-------------------------------------------------------------
``agent.before(task, seed)`` and ``agent.after(task, seed)``: ``task`` is one line of a task
file read as JSON, ``seed`` an integer. Each returns the tool calls the version made, in order,
as ``(name, arguments)`` pairs, ``arguments`` a dictionary. ``after`` makes the task's
reference calls. ``before`` makes them too, but on a step after the first, a seeded share of
the time, it passes a ``chain_token`` that is not the one the step before returned, and makes
no call after it.

Prove's wrapper (``prove_rollout``): ``before(cfg, seed)`` and ``after(cfg, seed)``, the two
targets, and ``task(value)``, the committed task (one line of a task file, read as JSON) an axis
value names. ``cfg`` holds the one axis of the spec files, whose value names one committed task;
the episode's outcome is the label the task's own checker (``poisson_tasks.tasks.verify``)
gives the calls the agent made; ``t`` is the number of calls; the horizon is the number of
model calls a Tasks run allows (``poisson_tasks.taskset.MAX_MODEL_CALLS``, 32), not the task's
own number of calls; ``meta["case_id"]`` is the axis value; and each call is a ``tool`` span
of the episode's trace, in order.
"""

from __future__ import annotations

import ast
import json
import os
import pickle
import re
import subprocess
import sys
import time
import traceback
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from docs_support import (
    DOCS, REPO, Block, Checked, page_env, parse, prose, read, recipe, run_page, sections, shims, trace_commands, words,
)

PAGE = recipe("with-tasks-and-prove.md")
NAME = "with-tasks-and-prove.md"
EXAMPLE = REPO / "examples" / "three-tools"
TASK_DIR = EXAMPLE / "tasks"
TASK_FILES = ("depth-d1.jsonl", "depth-d3.jsonl")
PROVENANCE = EXAMPLE / "PROVENANCE.md"
SPECS = {"before": EXAMPLE / "prove-before.toml", "after": EXAMPLE / "prove-after.toml"}
TARGETS = {"before": "prove_rollout:before", "after": "prove_rollout:after"}
RUNS = {"before": "agent before", "after": "agent after"}

#: The versions the recipe uses: Tasks pinned here (Tasks 0.4.2 from PyPI), Prove at the floor
#: Trace declares or above it.
TASKS_VERSION = "0.4.2"
PROVE_VERSION = "0.4.0"
TASKS_PIN = f"poisson-tasks=={TASKS_VERSION}"
HORIZON = 32  # the model calls a Tasks run allows: poisson_tasks.taskset.MAX_MODEL_CALLS at the pin
#: The page's ``generate`` command, word for word.
GENERATE = ("poisson-tasks", "generate", "--knob", "depth", "--levels", "1,3", "--tasks-per-level", "10", "--out", "tasks/")
LEVELS = {"depth-d1.jsonl": ("depth:d1", 1), "depth-d3.jsonl": ("depth:d3", 3)}
TASKS_PER_LEVEL = 10
#: The fix check the page runs, after the command's name.
FIX_CHECK = ("fix-check", RUNS["before"], RUNS["after"], "--inputs", "all", "--max-mde", "0.20")
#: The modules a stand-in that calls no model never imports: model clients, the network, and
#: the parts of Tasks that run a model.
NETWORK = ("openai", "anthropic", "litellm", "httpx", "requests", "urllib", "urllib3", "http", "socket", "aiohttp", "verifiers",
           "poisson_tasks.providers", "poisson_tasks.calibration", "poisson_tasks.calibration_run", "poisson_tasks.runs",
           "poisson_tasks.taskset", "poisson_tasks.export_verifiers", "ssl", "asyncio", "subprocess")


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def blocks() -> list[Block]:
    return parse(read(PAGE))[0]


def pytest_file() -> Path:
    found = sorted(EXAMPLE.glob("test_*.py"))
    assert len(found) == 1, f"examples/three-tools holds one pytest file, named test_*.py: {[p.name for p in found]}"
    return found[0]


def tasks(name: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (TASK_DIR / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def all_tasks() -> list[dict[str, Any]]:
    return [task for name in TASK_FILES for task in tasks(name)]


def toml(path: Path) -> dict[str, Any]:
    import tomllib

    return tomllib.loads(path.read_text(encoding="utf-8"))


def calls_of(task: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [(name, dict(arguments)) for name, arguments in task["reference_calls"]]


def imported(path: Path) -> set[str]:
    """Every module a file imports, by its full dotted name and each name above it."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__import__" and node.args \
                and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            names.add(node.args[0].value)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "import_module" and node.args \
                and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            names.add(node.args[0].value)
    out = set(names)
    for name in names:
        parts = name.split(".")
        out.update(".".join(parts[:k]) for k in range(1, len(parts)))
    return out


def load(name: str) -> Any:
    """A module of ``examples/three-tools/``, imported from that folder (as Prove imports it,
    with the spec's folder first on the import path)."""
    import importlib

    if str(EXAMPLE) not in sys.path:
        sys.path.insert(0, str(EXAMPLE))
    module = importlib.import_module(name)
    assert Path(module.__file__ or "").resolve().parent == EXAMPLE.resolve(), f"{name} is not the example's own module"
    return module


# ---------- the page, run once ----------


@dataclass(frozen=True)
class Ran:
    """The page run whole by the docs runner: what each shown block was checked against, and the
    folder the page ran in (laid out as a clone), kept for the tests that read what it left."""

    checked: list[Checked]
    root: Path
    home: Path
    bin_dir: Path

    def env(self, home: Path | None = None) -> dict[str, str]:
        """The page's environment; with ``home``, under that home folder and not the page's own."""
        return page_env(home or self.home, self.bin_dir, pull=False)

    def own_home(self, tmp: Path) -> Path:
        """A copy of the home the page ran under, for a test that runs a command of its own: the
        page's run is shared, so nothing but the page writes under its home."""
        import shutil

        return Path(shutil.copytree(self.home, tmp / "home-of-its-own"))

    def run(self, command: str, home: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", "-c", command], cwd=self.root, env=self.env(home), capture_output=True, text=True, timeout=600,
                              stdin=subprocess.DEVNULL)


def run_whole(tmp: Path) -> Ran:
    checked = run_page(PAGE, tmp)
    return Ran(checked, tmp / "clone", tmp / "home", shims(tmp / "bin"))


#: How long a process waits for the one run of the page another process is making (seconds).
SHARED_WAIT = 3600
_SHARED: dict[str, Ran] = {}


def shared_run(factory: Any) -> Ran:
    """The page run whole, once for the whole test session: every test that reads what the page
    printed or left reads this one run, whichever process it is in. ``factory`` is pytest's
    ``tmp_path_factory``.

    The run is made in a folder of the session's own temporary folder (the one above each
    worker's, under pytest-xdist). The process that makes that folder makes the run and then
    writes it down; any other waits for it. A run that failed fails every reader with what
    went wrong, and a wait that outlasts ``SHARED_WAIT`` fails too. No test writes under the
    run's folders: one that runs a command of its own does so in a copy, under ``own_home``."""
    base = Path(factory.getbasetemp())
    if os.environ.get("PYTEST_XDIST_WORKER"):
        base = base.parent
    folder = base / "tf20-page-shared"
    if str(folder) in _SHARED:
        return _SHARED[str(folder)]
    done, failed = folder / "ran.pickle", folder / "failed.txt"
    try:
        os.mkdir(folder)
    except FileExistsError:
        deadline = time.monotonic() + SHARED_WAIT
        while not done.exists() and not failed.exists():
            assert time.monotonic() < deadline, f"the one run of {NAME} in {folder} was not finished after {SHARED_WAIT} seconds"
            time.sleep(0.5)
    else:
        try:
            (folder / "run").mkdir()
            part = folder / "ran.pickle.part"
            part.write_bytes(pickle.dumps(run_whole(folder / "run")))
            os.replace(part, done)
        except BaseException:
            failed.write_text(traceback.format_exc(), encoding="utf-8")
            raise
    assert not failed.exists(), f"the one run of {NAME} failed in {folder}:\n{failed.read_text(encoding='utf-8')}"
    _SHARED[str(folder)] = pickle.loads(done.read_bytes())
    return _SHARED[str(folder)]


def shown_after(command_has: str, ran: Ran) -> list[Checked]:
    """The checked blocks under every command block whose text holds ``command_has``."""
    return [c for c in ran.checked if command_has in c.command]


def printed_by(ran: Ran, predicate: Any) -> list[Checked]:
    return [c for c in ran.checked if predicate(c.command)]


def store_of(root: Path, name: str) -> Path:
    """The run folder named ``name`` in any Prove store the page wrote under ``root``: found by
    its manifest. The committed fixtures (``tests/fixtures/``) are not the page's: TF16's Prove
    store there holds runs of the same two names."""
    found = []
    for manifest in root.rglob("manifest.json"):
        if manifest.is_relative_to(root / "tests"):
            continue
        try:
            if json.loads(manifest.read_text(encoding="utf-8")).get("name") == name:
                found.append(manifest.parent)
        except (OSError, ValueError):
            continue
    assert len(found) == 1, f"one run named {name!r} under the page's folder: {found}"
    return found[0]


def rows(run: Path) -> Any:
    import pandas as pd

    parts = sorted((run / "episodes").glob("*.parquet"))
    assert parts, f"{run} holds no episodes"
    return pd.concat([pd.read_parquet(part) for part in parts], ignore_index=True)


def sentences(text: str) -> list[str]:
    """The sentences of prose, paragraph by paragraph (a heading or a list item is a paragraph
    of its own)."""
    out: list[str] = []
    for paragraph in re.split(r"\n\s*\n|\n(?=#|- )", text):
        flat = re.sub(r"\s+", " ", paragraph).strip()
        if flat and not flat.startswith("#"):
            out += [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z`*\[])", flat) if s.strip()]
    return out


def page_prose() -> str:
    return prose(read(PAGE))


def page_sections() -> dict[str, str]:
    return sections(read(PAGE))


def trace_words() -> list[list[str]]:
    return trace_commands(read(PAGE))


def every_command() -> Iterator[tuple[int, Block, list[str]]]:
    """Each command of each run block of the page, in page order, with the ``cd`` and the
    environment assignments in front of it taken off, as words."""
    for at, block in enumerate(blocks()):
        if block.kind != "command":
            continue
        for line in words(block):
            command: list[str] = []
            for word in [*line, "&&"]:
                if word in ("&&", ";", "||"):
                    while command and (re.match(r"^[A-Z_]+=", command[0])):
                        command = command[1:]
                    if command and command[0] != "cd":
                        yield at, block, command
                    command = []
                else:
                    command.append(word)


def first_line(text: str) -> str:
    return text.strip("\n").split("\n")[0] if text.strip() else ""


@cache
def outcomes() -> tuple[str, ...]:
    from poisson_tasks.tasks import OUTCOMES

    return tuple(OUTCOMES)


__all__ = ["DOCS", "REPO"]
