"""BD-5: every other output stays byte for byte as main, before the breakdown, prints it.

Pinned on that main by ``fixtures/breakdown/make_main_pins.py`` (``main-pins.json``), each path
written ``<ROOT>``. The piped outputs are held whole by ``test_pl_unchanged.py`` (PL-51), which
runs each of those commands; their pins stay in ``main-pins.json`` under ``piped``.

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
    PINS, PTY_WIDTHS, normal, piped_corpus, pty_corpus,
)
from tf13_support import workspace
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
