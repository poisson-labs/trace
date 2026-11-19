"""BD-4: a verdict word in a terminal table cell is drawn in its meaning, under the clean look's
rules (the Colour part of the terminal app section of ``docs/cli-look.md``).

**BD-4a** In the pretty face of a table, a cell of the column headed ``verdict`` is drawn by its
verdict word: ``too small to tell``, ``no significant difference`` and ``unconfirmed`` yellow;
``different`` bold with no colour; ``identical``, ``not tested``, ``not recorded`` and a dash
plain. A direction after the word (``, slower``) stays plain. In every form the renderer draws:
aligned, folded and one record a row.

**BD-4b** Only there: the same words in another column, and every other cell, are plain as
before; no digit is ever coloured; only the look's escapes are drawn; the text under the escapes
is the plain table's.

**BD-4c** Through the verb: ``fix-check --measures`` on a terminal colours the table's verdict
words; ``--plain``, ``NO_COLOR``, a pipe and ``--json`` carry no escape at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from breakdown_support import INSPECT_ARGV, inspect_store
from tf9_support import cells, odd_escapes, role, strip
from tf9_support import run as pty

HEADER = ["measure", "old", "new", "change", "verdict"]
ROWS = [
    ["wall_time_s", "2.05 s", "2.41 s", "+18%", "different, slower"],
    ["working_time_s", "0.331 s", "0.29 s", "-12%", "unconfirmed, faster"],
    ["input_chars", "10 chars", "10 chars", "none", "identical"],
    ["output_chars", "4.83 chars", "5 chars", "+3.4%", "too small to tell"],
    ["input_tokens", "300 tokens", "301 tokens", "+0.33%", "no significant difference"],
    ["total_tokens", "7.83 tokens", "8 tokens", "+2.1%", "not tested"],
    ["cost_usd", "-", "-", "-", "not recorded"],
    ["output_tokens", "4 tokens", "4 tokens", "-", "-"],
]
#: Each verdict word's role, as tf9_support reads a cell: Y yellow, B bold, blank plain.
EXPECT = {
    "different": "B", "unconfirmed": "Y", "identical": " ", "too small to tell": "Y",
    "no significant difference": "Y", "not tested": " ", "not recorded": " ", "-": " ",
}


def _roles_of(drawn: str, text: str) -> list[set[str]]:
    """For each place ``text`` stands in the drawn table, the roles of its characters."""
    out = []
    for row in cells(drawn):
        line = "".join(c.char for c in row)
        at = line.find(text)
        while at >= 0:
            out.append({role(c) for c in row[at:at + len(text)] if c.char.strip()})
            at = line.find(text, at + 1)
    return out


def _form(drawn: str) -> str:
    lines = strip(drawn).split("\n")
    return "aligned" if len(lines) > 1 and lines[1] and set(lines[1]) == {"─"} else "records"


@pytest.mark.parametrize("width", [40, 60, 80, 120])
def test_bd_4a_each_verdict_word_in_its_meaning(width: int) -> None:
    from poisson_trace import _pretty

    drawn = _pretty.table(HEADER, ROWS, width=width)
    for row in ROWS:
        word = row[-1].partition(", ")[0]
        found = _roles_of(drawn, row[-1].partition(", ")[0])
        assert found, (width, word, strip(drawn))
        assert {EXPECT[word]} in found, (width, word, found)
        if ", " in row[-1]:
            direction = row[-1].partition(", ")[2]
            assert all(r <= {" "} for r in _roles_of(drawn, ", " + direction)), (width, direction)


def test_bd_4a_both_forms_are_reached() -> None:
    from poisson_trace import _pretty

    assert _form(_pretty.table(HEADER, ROWS, width=120)) == "aligned"
    assert _form(_pretty.table(HEADER, ROWS, width=40)) == "records"


@pytest.mark.parametrize("width", [40, 60, 80, 120])
def test_bd_4b_nothing_else_is_coloured(width: int) -> None:
    from poisson_trace import _pretty, look

    drawn = _pretty.table(HEADER, ROWS, width=width)
    assert odd_escapes(drawn, live=False) == []
    assert not any(c.char.isdigit() and (c.fg is not None or c.bold) for row in cells(drawn) for c in row)
    # the cells of the other columns: plain (the headers and the record form's names are dim)
    for row in ROWS:
        for cell in row[:-1]:
            for found in _roles_of(drawn, cell):
                assert found <= {" ", "D"}, (width, cell, found)
    # the text under the escapes holds plain's words
    from tf9_support import tokens

    assert tokens(drawn) <= tokens(look.table(HEADER, ROWS))


def test_bd_4b_only_the_verdict_column() -> None:
    """The same words under another header are cells like any other."""
    from poisson_trace import _pretty

    header = ["measure", "old", "new", "change", "note"]
    drawn = _pretty.table(header, ROWS, width=120)
    for row in ROWS:
        for found in _roles_of(drawn, row[-1]):
            assert found <= {" "}, (row[-1], found)


def test_bd_4b_the_breakdown_and_the_per_input_table_stay_uncoloured() -> None:
    from poisson_trace import _pretty

    header = ["input", "A failed/runs", "B failed/runs", "change", "p", "q", "flag"]
    rows = [['{"task_id":"search"}', "32/40", "10/40", "-55.0 points", "1.45e-06", "5.80e-06", "failed less in B"]]
    drawn = _pretty.table(header, rows, width=160)
    body = cells(drawn)[2:]
    assert all(role(c) == " " for row in body for c in row if c.char.strip())


# ---------- BD-4c ----------


@pytest.fixture(scope="module")
def inspect(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return inspect_store(tmp_path_factory.mktemp("insp"))


def _measures_table(raw: str) -> str:
    lines = raw.replace("\r\n", "\n").split("\n")
    texts = [strip(line) for line in lines]
    start = next(i for i, t in enumerate(texts) if t.startswith("measure "))
    end = texts.index("", start)
    return "\n".join(lines[start:end]) + "\n"


def test_bd_4c_through_the_verb(inspect: Path, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    ran = pty([*INSPECT_ARGV, "--store", str(inspect)], cwd=tmp_path, home=home, cols=100)
    assert ran.code == 0
    table = _measures_table(ran.out)
    assert {"Y"} in _roles_of(table, "too small to tell")
    tested = _roles_of(table, "not tested")
    assert tested and all(r <= {" "} for r in tested)
    assert not any(c.char.isdigit() and c.fg is not None for row in cells(table) for c in row)


@pytest.mark.parametrize("how", ["--plain", "NO_COLOR", "pipe", "--json"])
def test_bd_4c_plain_underneath(inspect: Path, tmp_path: Path, how: str) -> None:
    home = tmp_path / "home"
    home.mkdir()
    argv = [*INSPECT_ARGV, "--store", str(inspect)]
    env: dict[str, str | None] = {}
    stdout = "pty"
    if how in ("--plain", "--json"):
        argv.append(how)
    elif how == "NO_COLOR":
        env["NO_COLOR"] = "1"
    else:
        stdout = "pipe"
    ran = pty(argv, cwd=tmp_path, home=home, cols=100, env=env, stdout=stdout)
    assert ran.code == 0
    assert "\x1b" not in ran.out
