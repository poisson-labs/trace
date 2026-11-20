"""BD-1f: the failure breakdown on a terminal, at the widths the mockups show (80 and 140
columns), pretty and ``--plain``, under the clean look's rules.

On a pseudo-terminal, ``fix-check`` on the committed Prove 0.1.3 store prints the section the
mockups draw (``tests/fixtures/breakdown/mockups/breakdown-prove-{80,140}-{plain,pretty}``),
every character the terminal received with the escapes removed, from its heading to its last
row. Pretty: the heading bold, each table's header and rule dim, nothing else styled, no digit
coloured, only the look's escapes. ``compare`` and ``changes`` hold the same rules with their own
labels: plain's words, one line a row, nothing wider than the terminal.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from breakdown_support import HEADING, LABELS, argv_of, mockup, prove_store
from terminal_support import cells, odd_escapes, role, strip, tokens
from terminal_support import run as pty

TITLE = HEADING.removeprefix("## ")


def _block(lines: list[str], heading: str, stop: tuple[str, ...]) -> list[str]:
    start = lines.index(heading)
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith(stop))
    out = lines[start:end]
    while out and not out[-1].strip():
        out.pop()
    return out


def _run(tmp: Path, verb: str, cols: int, plain: bool) -> tuple[str, list[str]]:
    store = prove_store(tmp)
    home = tmp / "home"
    home.mkdir()
    ran = pty([*argv_of(verb, store), *(["--plain"] if plain else [])], cwd=tmp, home=home, cols=cols)
    assert ran.code == 0, ran.err
    return ran.out, strip(ran.out).split("\n")


NEXT_PARTS = {
    "fix-check": ("The comparison", "## The comparison"),
    "compare": ("For the share of runs", "## What this cannot say", "What this cannot say", "Guidance", "## Guidance"),
    "changes": ("Inputs that changed", "## Inputs that changed"),
}


@pytest.mark.parametrize("cols", [80, 140])
@pytest.mark.parametrize("rendering", ["plain", "pretty"])
def test_bd_1f_fix_check_on_a_terminal_is_the_mockup(tmp_path: Path, cols: int, rendering: str) -> None:
    raw, lines = _run(tmp_path, "fix-check", cols, rendering == "plain")
    heading = HEADING if rendering == "plain" else TITLE
    got = _block(lines, heading, NEXT_PARTS["fix-check"])
    want = _block(mockup(f"breakdown-prove-{cols}-{rendering}"), heading, ("next:",))
    assert got == want


@pytest.mark.parametrize("cols", [80, 140])
def test_bd_1f_pretty_styles_only_the_heading_and_the_tables_headers(tmp_path: Path, cols: int) -> None:
    raw, lines = _run(tmp_path, "fix-check", cols, False)
    drawn = raw.replace("\r\n", "\n").split("\n")
    plain_lines = [strip(line) for line in drawn]
    start = plain_lines.index(TITLE)
    end = next(i for i in range(start + 1, len(plain_lines)) if plain_lines[i].startswith("The comparison"))
    part = "\n".join(drawn[start:end])
    assert odd_escapes(part, live=False) == []
    grid = cells(part)
    styled = {}
    for n, row in enumerate(grid):
        roles = {role(c) for c in row if c.char.strip()}
        styled[n] = roles
        assert not any(c.char.isdigit() and c.fg is not None for c in row), plain_lines[start + n]
    text = [plain_lines[start + n] for n in range(len(grid))]
    for n, line in enumerate(text):
        if n == 0:
            assert styled[n] == {"B"}, line  # the heading, bold
        elif line.startswith(("kind ", "signal ")) or (line and set(line) == {"─"}):
            assert styled[n] == {"D"}, line  # a table's header and its rule, dim
        elif line.strip():
            assert styled[n] == {" "}, line  # everything else plain


@pytest.mark.parametrize("verb", ["compare", "changes"])
@pytest.mark.parametrize("cols", [pytest.param(80), pytest.param(140, marks=pytest.mark.slow)])
def test_bd_1f_compare_and_changes_on_a_terminal(tmp_path: Path, verb: str, cols: int) -> None:
    _, pretty = _run(tmp_path / "p", verb, cols, False)
    _, plain = _run(tmp_path / "q", verb, cols, True)
    got = _block(pretty, TITLE, NEXT_PARTS[verb])
    words = _block(plain, HEADING, NEXT_PARTS[verb])
    assert tokens("\n".join(got)) == tokens("\n".join(words)) - {"##"}
    assert all(len(line) <= cols for line in got)
    a, b = LABELS[verb]
    head = next(line for line in got if line.startswith("kind "))
    assert head.split() == ["kind", a, a, "share", b, b, "share", "change"]
    rule = got.index(head) + 1
    rows = [line for line in got[rule + 1:] if line.strip()]
    assert rows[:4][-1].startswith("all failures"), rows
    assert len([r for r in rows[:4] if r]) == 4  # three kinds and all failures, a line each
