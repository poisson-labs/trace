"""BD-3: the continuous-measures table's new shape (Taylor's DM3 of 2026-11-05) and the renderer's
rule that a cell is never broken across rows (DM4); FD9 to FD11, ``log/trace-breakdown-a/rulings.md``.

**BD-3a** ``continuous.table`` gives ``measure | old | new | change | verdict`` (``technical``:
``measure | old | new | change | 95% range | p | verdict``): the change cell the relative change
alone, as the measure's lines spell it (``+0.88%``); ``none`` when the measure did not change
(identical, or a change of exactly zero); ``-`` when there is no relative change to give (no old
mean to read a share of, HY1, or nothing recorded); the verdict cell the verdict word, and when
there is a direction, the word, a comma and the direction (``different, slower``). The absolute
change stays in the measure's lines.

**BD-3b** ``fix-check --measures`` on the design session's two pairs (the DeepEval import of the
committed HumanEval files, the Inspect import of the committed logs): the table's plain rows, and
on a terminal at 80 and 140 columns its pretty lines, are the mockups'
(``continuous-proposed-*``), with one correction: the Inspect pair's ``total_tokens`` reads
``not tested``, the word the build prints, where the drawing script printed a dash (FD10).

**BD-3c** DM4: at every width from 60 to 160, in every table the renderer draws, each body cell
stands whole on one line, and the clean look's rules hold (no line wider than the width, no
digit coloured, only the look's escapes, plain's words in plain's order). A key folded one field
a line is the fold's form, not a broken cell; a header may still take two lines (FD11).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from breakdown_support import (
    DEEPEVAL_ARGV, INSPECT_ARGV, MEASURES_HEADING, deepeval_store, inspect_store, mockup, ok, section,
    table_rows,
)
from tf9_support import cells, odd_escapes, strip, tokens

HEADER = ["measure", "old", "new", "change", "verdict"]
TECHNICAL = ["measure", "old", "new", "change", "95% range", "p", "verdict"]
WIDTHS = list(range(60, 161))


def cm() -> Any:
    from poisson_trace.stats import continuous

    return continuous


def _versions(columns: dict[str, tuple[Sequence[float | None], Sequence[float | None]]],
              ends_b: dict[int, str] | None = None) -> tuple[Any, Any]:
    T = cm().Try
    k = len(next(iter(columns.values()))[0])
    va = {f"c{i:02d}": [T(values={m: v[0][i] for m, v in columns.items()}, repeat=0)] for i in range(k)}
    vb = {f"c{i:02d}": [T(values={m: v[1][i] for m, v in columns.items()}, ending=(ends_b or {}).get(i), repeat=0)]
          for i in range(k)}
    return cm().Version("run-a", va, "old"), cm().Version("run-b", vb, "new")


def _mixed() -> Any:
    """Wall time different (slower), output tokens quiet, input length identical, input tokens a
    change of exactly zero on few cases, cost on 6 cases only, working time never recorded."""
    rng = np.random.default_rng(33)
    k = 24
    wall = rng.lognormal(1.5, 0.5, k)
    out = rng.integers(200, 900, k).astype(float)
    noise = rng.integers(-40, 41, k)
    cols: dict[str, tuple[Sequence[float | None], Sequence[float | None]]] = {
        "wall_time_s": (list(wall), list(wall * 1.4 + 0.2)),
        "output_tokens": (list(out), list(out + noise)),
        "input_chars": ([1840.0] * k, [1840.0] * k),
        "input_tokens": ([300.0] * k, [300.0 + (5 if i == 0 else -5 if i == 1 else 0) for i in range(k)]),
        "cost_usd": ([float(x * 2e-5) if i < 6 else None for i, x in enumerate(out)],
                     [float(x * 2.2e-5) if i < 6 else None for i, x in enumerate(out)]),
    }
    return cm().compare(*_versions(cols), ceilings={"output_tokens": 0.2})


def _unconfirmed() -> Any:
    """New is 20% faster and timed out twice where old did not: faster, unconfirmed (CS8)."""
    rng = np.random.default_rng(6)
    ya = rng.lognormal(1.5, 0.4, 30)
    yb = ya * 0.8 * np.exp(rng.normal(0, 0.02, 30))
    return cm().compare(*_versions({"wall_time_s": (list(ya), list(yb))}, ends_b={0: "timeout", 1: "timeout"}))


def _near_zero() -> Any:
    """An old cost too near zero to read a share of (HY1): the change has no relative form."""
    old = [1e-310 * (i + 1) for i in range(12)]
    new = [1.0 + 0.01 * i for i in range(12)]
    return cm().compare(*_versions({"cost_usd": (old, new)}))


# ---------- BD-3a ----------


def test_bd_3a_the_header() -> None:
    header, _ = cm().table(_mixed())
    assert header == HEADER
    header, _ = cm().table(_mixed(), technical=True)
    assert header == TECHNICAL


def test_bd_3a_the_change_is_the_relative_change_alone() -> None:
    c = _mixed()
    _, rows = cm().table(c)
    by = {r[0]: r for r in rows}
    for name, row in by.items():
        m = c.measures[name]
        assert len(row) == len(HEADER), row
        if m.status == "identical" or m.change == 0.0:
            assert row[3] == "none", (name, row)
        elif m.relative is None:
            assert row[3] == "-", (name, row)
        else:
            assert re.fullmatch(r"[+\-]?[\d.]+(?:e[+\-]?\d+)?%", row[3]), (name, row)
            # the same share the measure's lines spell
            assert f"{row[3]})" in " ".join(m.lines) or f"{row[3]}," in " ".join(m.lines), (name, row[3], m.lines)
            assert " " not in row[3]
    assert by["input_chars"][3] == "none" and by["input_chars"][4] == "identical"
    assert by["input_tokens"][3] == "none"


def test_bd_3a_the_direction_joins_the_verdict() -> None:
    c = _mixed()
    _, rows = cm().table(c)
    by = {r[0]: r[-1] for r in rows}
    assert c.measures["wall_time_s"].direction == "slower"
    assert by["wall_time_s"] == "different, slower"
    for name, cell in by.items():
        m = c.measures[name]
        if m.direction is None:
            assert "," not in cell, (name, cell)
    assert by["cost_usd"] == "too small to tell"
    assert by["output_tokens"] in ("no significant difference", "too small to tell")


def test_bd_3a_an_unconfirmed_call_keeps_its_direction() -> None:
    c = _unconfirmed()
    m = c.measures["wall_time_s"]
    assert (m.verdict, m.direction) == ("unconfirmed", "faster")
    _, rows = cm().table(c)
    assert rows[0][0] == "wall_time_s" and rows[0][-1] == "unconfirmed, faster"


def test_bd_3a_no_share_to_give() -> None:
    c = _near_zero()
    m = c.measures["cost_usd"]
    assert m.relative is None and m.change not in (None, 0.0)
    _, rows = cm().table(c)
    assert rows[0][3] == "-"


def test_bd_3a_technical_shows_the_unrecorded_and_the_range() -> None:
    c = _mixed()
    _, rows = cm().table(c, technical=True)
    by = {r[0]: r for r in rows}
    assert by["working_time_s"] == ["working_time_s", "-", "-", "-", "-", "-", "not recorded"]
    wall = c.measures["wall_time_s"]
    assert by["wall_time_s"][4].count(" to ") == 1 and by["wall_time_s"][4] != "-"
    assert by["wall_time_s"][5] != "-" and wall.p_value is not None
    assert by["wall_time_s"][6] == "different, slower"


def test_bd_3a_the_absolute_change_stays_in_the_lines() -> None:
    c = _mixed()
    m = c.measures["wall_time_s"]
    assert "The mean changed by +" in " ".join(m.lines) or "Over 24 paired cases" in " ".join(m.lines)
    assert "(change +" in " ".join(m.lines)


# ---------- BD-3b ----------

DEEPEVAL_ROWS = [
    ["wall_time_s", "0.000354 s", "0.000357 s", "+0.88%", "too small to tell"],
    ["input_chars", "31.3 chars", "31.3 chars", "none", "identical"],
    ["output_chars", "7.27 chars", "7.31 chars", "+0.61%", "too small to tell"],
]
INSPECT_ROWS = [
    ["wall_time_s", "2.05 s", "0.0105 s", "-99%", "too small to tell"],
    ["working_time_s", "0.331 s", "0.007 s", "-98%", "too small to tell"],
    ["input_chars", "10 chars", "10 chars", "none", "too small to tell"],
    ["output_chars", "4.83 chars", "5 chars", "+3.4%", "too small to tell"],
    ["input_tokens", "3 tokens", "3 tokens", "none", "too small to tell"],
    ["output_tokens", "4.83 tokens", "5 tokens", "+3.4%", "too small to tell"],
    ["total_tokens", "7.83 tokens", "8 tokens", "+2.1%", "not tested"],
]


@pytest.fixture(scope="module")
def deepeval(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return deepeval_store(tmp_path_factory.mktemp("de"))


@pytest.fixture(scope="module")
def inspect(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return inspect_store(tmp_path_factory.mktemp("insp"))


def test_bd_3b_deepeval_plain(deepeval: Path) -> None:
    out = ok([*DEEPEVAL_ARGV, "--store", str(deepeval)]).out
    got = section(out, MEASURES_HEADING)
    assert got[2] == "| " + " | ".join(HEADER) + " |"
    assert table_rows(got) == DEEPEVAL_ROWS


def test_bd_3b_inspect_plain(inspect: Path) -> None:
    out = ok([*INSPECT_ARGV, "--store", str(inspect)]).out
    got = section(out, MEASURES_HEADING)
    assert got[2] == "| " + " | ".join(HEADER) + " |"
    assert table_rows(got) == INSPECT_ROWS


def mockup_table(name: str, correct: dict[str, str] | None = None) -> list[str]:
    """The proposed table's lines in a mockup capture: its header, its rule and its rows, a cell
    corrected where the drawing differs from the build's word (FD10)."""
    lines = mockup(name)
    start = next(i for i, line in enumerate(lines) if line.startswith("measure "))
    end = lines.index("", start)
    table = lines[start:end]
    for measure, word in (correct or {}).items():
        table = [re.sub(r"–$", word, line) if line.startswith(measure + " ") else line for line in table]
    return table


INSPECT_FIX = {"total_tokens": "not tested"}


def _pty_table(argv: list[str], store: Path, cols: int, tmp: Path, extra: Sequence[str] = ()) -> list[str]:
    from tf9_support import run as pty

    home = tmp / "home"
    home.mkdir(exist_ok=True)
    ran = pty([*argv, "--store", str(store), *extra], cwd=tmp, home=home, cols=cols)
    assert ran.code == 0, ran.err
    lines = strip(ran.out).split("\n")
    start = next(i for i, line in enumerate(lines) if line.startswith("measure "))
    return lines[start:lines.index("", start)]


@pytest.mark.parametrize("cols", [80, 140])
def test_bd_3b_inspect_on_a_terminal_is_the_mockup(inspect: Path, cols: int, tmp_path: Path) -> None:
    assert _pty_table(INSPECT_ARGV, inspect, cols, tmp_path) == mockup_table(
        f"continuous-proposed-inspect-{cols}-pretty", INSPECT_FIX)


@pytest.mark.slow
@pytest.mark.parametrize("cols", [80, 140])
def test_bd_3b_deepeval_on_a_terminal_is_the_mockup(deepeval: Path, cols: int, tmp_path: Path) -> None:
    assert _pty_table(DEEPEVAL_ARGV, deepeval, cols, tmp_path) == mockup_table(f"continuous-proposed-deepeval-{cols}-pretty")


def test_bd_3b_deepeval_drawn_is_the_mockup(deepeval: Path) -> None:
    """The fast twin of the terminal test: the rows drawn by the renderer at 80 and 140 columns."""
    from poisson_trace import _pretty

    for cols in (80, 140):
        drawn = strip(_pretty.table(HEADER, DEEPEVAL_ROWS, width=cols)).rstrip("\n").split("\n")
        assert drawn == mockup_table(f"continuous-proposed-deepeval-{cols}-pretty"), cols
    for cols in (80, 140):
        drawn = strip(_pretty.table(HEADER, INSPECT_ROWS, width=cols)).rstrip("\n").split("\n")
        assert drawn == mockup_table(f"continuous-proposed-inspect-{cols}-pretty", INSPECT_FIX), cols


# ---------- BD-3c ----------


def _tables() -> dict[str, tuple[list[str], list[list[str]]]]:
    """Tables of every shape the renderer is given: the continuous tables (plain and technical),
    the breakdown's two, a per-input table keyed by JSON, compare's per-kind table, and two made
    to break: long words in a narrow column, and a phrase in every cell."""
    out: dict[str, tuple[list[str], list[list[str]]]] = {}
    for name, c in (("mixed", _mixed()), ("unconfirmed", _unconfirmed()), ("near zero", _near_zero())):
        out[f"continuous {name}"] = cm().table(c)
        out[f"continuous {name} technical"] = cm().table(c, technical=True)
    out["deepeval"] = (HEADER, DEEPEVAL_ROWS)
    out["inspect"] = (HEADER, INSPECT_ROWS)
    out["breakdown"] = (["kind", "old", "old share", "new", "new share", "change"], [
        ["tool_error", "66", "41.2%", "21", "13.1%", "-28.1 points"],
        ["loop_detected", "6", "3.8%", "15", "9.4%", "+5.6 points"],
        ["step_limit", "0", "0.0%", "5", "3.1%", "+3.1 points"],
        ["all failures", "72", "45.0%", "41", "25.6%", "-19.4 points"]])
    out["signals"] = (["signal", "old", "old share", "new", "new share"], [
        ["retry_storm", "78", "48.8%", "50", "31.2%"], ["over_budget", "6", "3.8%", "23", "14.4%"]])
    out["per input"] = (["input", "A failed/runs", "B failed/runs", "change", "p", "q", "flag"], [
        ['{"task_id":"search","tool_fail_rate":0.55}', "32/40", "10/40", "-55.0 points", "1.45e-06", "5.80e-06", "failed less in B"],
        ['{"task_id":"refund","tool_fail_rate":0.55}', "40/40", "31/40", "-22.5 points", "0.002", "0.005", "failed less in B"],
        ['{"task_id":"refund","tool_fail_rate":0.0}', "0/40", "0/40", "0.0 points", "1.000", "1.000", "–"]])
    out["per kind"] = (["kind", "deaths A", "deaths B", "χ²", "p", "q", "could not have detected a hazard ratio below"], [
        ["tool", "72", "41", "43.174", "5.01e-11", "5.01e-11", "1.890"]])
    out["phrases"] = (["what", "when", "verdict"], [
        ["the old version failed more often on hard inputs", "after the second deploy of the week", "no significant difference"],
        ["a short one", "now", "too small to tell"]])
    return out


TABLES = _tables()


def _cells_whole(drawn: str, header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    """Each body cell that is not a key, and is not shown elsewhere on its row's lines, found whole
    on one line of its row's block. Returns the cells found broken."""
    from poisson_trace import _pretty

    lines = strip(drawn).split("\n")
    broken = []
    keyed = [i for i in range(len(header)) if rows and all(_pretty._key(r[i]) is not None for r in rows)]
    folded = _pretty._units(header, rows)[0]
    for row in rows:
        for i, cell in enumerate(row):
            if i in keyed or not cell.strip():
                continue
            # a unit every cell of the column repeats may move into the header (the fold)
            unit = _pretty._UNIT.match(cell)
            moved = unit is not None and folded[i] == f"{header[i]} ({unit.group(2)})"
            shown = (cell, unit.group(1)) if moved and unit is not None else (cell,)
            if not any(any(text in line for text in shown) for line in lines):
                broken.append(cell)
    return broken


def _one_line_a_row(drawn: str, header: Sequence[str], rows: Sequence[Sequence[str]]) -> bool:
    """In the aligned form (a rule under the header) with no key folded, each row takes one line."""
    lines = strip(drawn).rstrip("\n").split("\n")
    rule = next((i for i, line in enumerate(lines) if line and set(line) == {"─"}), None)
    if rule is None:
        return True
    body = lines[rule + 1:]
    if any(line.startswith(("task_id", "tool_fail_rate")) or line.startswith(" ") for line in body):
        return len(body) >= len(rows)
    return len(body) == len(rows)


@pytest.mark.parametrize("name", list(TABLES))
def test_bd_3c_no_cell_is_broken_at_any_width(name: str) -> None:
    from poisson_trace import _pretty, look

    header, rows = TABLES[name]
    plain = look.table(header, rows)
    for width in WIDTHS:
        drawn = _pretty.table(header, rows, width=width)
        assert _cells_whole(drawn, header, rows) == [], (name, width, strip(drawn))
        assert _one_line_a_row(drawn, header, rows), (name, width, strip(drawn))
        lines = strip(drawn).split("\n")
        assert [line for line in lines if len(line) > width] == [], (name, width)
        assert odd_escapes(drawn, live=False) == [], (name, width)
        assert not any(ch.char.isdigit() and ch.fg is not None for line in cells(drawn) for ch in line), (name, width)
        # plain's words, but the key column's header where it folds to records (CT1)
        assert tokens(drawn) <= tokens(plain), (name, width)
        assert tokens(plain) - tokens(drawn) <= set(re.findall(r"[A-Za-z0-9]+", header[0])), (name, width)


@pytest.mark.parametrize("name", ["deepeval", "inspect", "breakdown", "signals"])
def test_bd_3c_these_fit_aligned_at_80(name: str) -> None:
    """The tables the mockups draw at 80 columns stand aligned there, one line a row."""
    from poisson_trace import _pretty

    header, rows = TABLES[name]
    lines = strip(_pretty.table(header, rows, width=80)).rstrip("\n").split("\n")
    assert len(lines) == 2 + len(rows) and set(lines[1]) == {"─"}


def test_bd_3c_a_header_may_take_two_lines() -> None:
    """FD11: the rule is about the body; compare's long header still wraps under its column."""
    from poisson_trace import _pretty

    header, rows = TABLES["per kind"]
    drawn = strip(_pretty.table(header, rows, width=80)).rstrip("\n").split("\n")
    rule = next(i for i, line in enumerate(drawn) if line and set(line) == {"─"})
    assert rule in (1, 2)
    assert len(drawn) - rule - 1 == len(rows)


def test_bd_3c_the_rows_keep_plains_order() -> None:
    from poisson_trace import _pretty

    for name, (header, rows) in TABLES.items():
        if any(_pretty._key(r[0]) is not None for r in rows):
            continue
        for width in (60, 80, 120):
            lines = strip(_pretty.table(header, rows, width=width)).split("\n")
            order = [next(i for i, line in enumerate(lines) if line.startswith(r[0]) or f" {r[0]}" in line) for r in rows]
            assert order == sorted(order), (name, width)


def _pty_widths() -> list[Any]:
    fast = (60, 80, 100)
    return [w if w in fast else pytest.param(w, marks=pytest.mark.slow) for w in WIDTHS]


@pytest.mark.parametrize("cols", _pty_widths())
def test_bd_3c_through_the_verb_at_every_width(inspect: Path, cols: int, tmp_path: Path) -> None:
    """fix-check --measures on a terminal: each table's cells whole, every line within the
    terminal but the verdict line and a line holding a command (LB1)."""
    from tf9_support import run as pty

    home = tmp_path / "home"
    home.mkdir()
    ran = pty([*INSPECT_ARGV, "--store", str(inspect)], cwd=tmp_path, home=home, cols=cols)
    assert ran.code == 0
    text = strip(ran.out)
    for row in INSPECT_ROWS:
        for cell in row:
            assert any(cell in line for line in text.split("\n")), (cols, cell)
    for line in text.split("\n")[1:]:
        assert len(line) <= cols or "poisson-trace" in line, (cols, line)
