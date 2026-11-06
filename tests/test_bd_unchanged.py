"""BD-5: every other output stays byte for byte as main prints it (rule 5 of the pair's brief).

Pinned on main 7e6fef6 by ``fixtures/breakdown/make_main_pins.py`` (``main-pins.json``), each
path written ``<ROOT>``:

**BD-5a** Piped: TF13-32's corpus (each verb on each kind of store with each option, the
refusals, every reader's import, the names) and TF6-1's larger fixtures, plain and ``--json``:
the exit code, stderr, and stdout. On ``fix-check``, ``compare`` and ``changes`` stdout is held
with the two parts this pair changes taken out: the failure breakdown and the continuous-measures
section from the report (DM1, DM3), ``failure_taxonomy_diff`` from the JSON (rule 2). Every
other verb's stdout is held whole.

**BD-5b** On a terminal: ``where`` and ``runs`` in TF13's workspace, pretty and ``--plain``, at
60, 80, 100, 120, 140 and 160 columns: every byte both terminals received, escapes and all.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from breakdown_support import (
    PINS, PTY_WIDTHS, SLOW_PIPED, normal, outside_new_parts, piped_corpus, pty_corpus,
)
from tf0_support import REPO, chdir, trace
from tf13_support import cli, cli_import, workspace
from tf9_support import run as pty

PINNED: dict[str, Any] = json.loads(PINS.read_text(encoding="utf-8"))
PIPED = piped_corpus()
PTY = pty_corpus()


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_bd_5_every_case_is_pinned() -> None:
    assert PINNED["main"] == "7e6fef6"
    assert set(PINNED["piped"]) == set(PIPED)
    assert set(PINNED["pty"]) == set(PTY)
    assert all(set(v) == {f"{w} {r}" for w in PTY_WIDTHS for r in ("pretty", "plain")} for v in PINNED["pty"].values())


@pytest.mark.parametrize("label", [pytest.param(k, marks=pytest.mark.slow) if k in SLOW_PIPED else k for k in PIPED])
def test_bd_5a_piped_as_main(tmp_path: Path, label: str) -> None:
    place, kind, steps = PIPED[label]
    work = workspace(tmp_path) if place == "work" else REPO
    got = []
    for step in steps:
        if place == "work":
            ran = (cli if kind == "trace" else cli_import)(work, step)
        else:
            with chdir(REPO):
                ran = trace(step)
        out = normal(outside_new_parts(step if kind == "trace" else ["import", *step], ran.out), work)
        got.append([ran.code, _digest(out), _digest(normal(ran.err, work))])
    assert got == PINNED["piped"][label], label


def _pty_params() -> list[Any]:
    fast = {("where", 80), ("runs", 80)}
    out = []
    for label in PTY:
        for cols in PTY_WIDTHS:
            mark = () if (label, cols) in fast else (pytest.mark.slow,)
            out.append(pytest.param(label, cols, marks=mark, id=f"{label}-{cols}"))
    return out


@pytest.mark.parametrize("label,cols", _pty_params())
def test_bd_5b_on_a_terminal_as_main(tmp_path: Path, label: str, cols: int) -> None:
    work = workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    for rendering, extra in (("pretty", []), ("plain", ["--plain"])):
        ran = pty([*PTY[label], *extra], cwd=work, home=home, cols=cols)
        got = [ran.code, _digest(normal(ran.out, work)), _digest(normal(ran.err, work))]
        assert got == PINNED["pty"][label][f"{cols} {rendering}"], (label, cols, rendering)
