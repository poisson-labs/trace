"""The pretty rendering: the look's styles and tables, drawn with Rich (``docs/cli-look.md``,
rule 16).

The one module of this package that imports Rich. ``look`` imports it only when the switch says
the rendering is pretty, and a Trace that cannot import Rich prints plain and says nothing: the
``ImportError`` this module raises is caught there.

Three faces, and nothing else draws an escape sequence:

- :func:`style` draws a piece of text in one of the look's five styles: ``green``, ``yellow``,
  ``red`` (the three meanings), ``bold`` (a verdict that is a result, a heading) and ``dim``
  (secondary text). Only the terminal's 16 named colours, bold and dim: no background, no 256 or
  true colour, no italic, underline or reverse.
- :func:`verdict` draws a verdict line, ``word  sentence``, the word in its meaning.
- :func:`table` draws a table for a terminal of a given width: aligned when it fits; when it is
  too wide, a unit every cell of a column repeats moves into the header and a cell that is a JSON
  object (an input's key) is printed one field per line; when even that is too wide, one record
  per row. No cell is broken across lines and no word is cut, so the table holds every word and
  number plain's table holds, in the same row order; a number is never coloured, and in the
  column headed ``verdict`` each cell's verdict word is drawn in its meaning.

Every table a later verb adds goes through :func:`table` and ``look.table`` (its plain face), and
so gets the same rules.
"""

from __future__ import annotations

import io
import json
import re
from collections.abc import Sequence

from rich.cells import cell_len
from rich.console import Console
from rich.text import Text

from poisson_trace import look

__all__ = ["style", "table", "verdict"]

#: The styles the look allows, as Rich names them.
_STYLES = {
    "green": "green",
    "yellow": "yellow",
    "red": "red",
    "bold": "bold",
    "dim": "dim",
}

_console: Console | None = None


def _rich() -> Console:
    """One console held to the 16 named colours, writing nowhere: it draws text into a capture."""
    global _console
    if _console is None:
        _console = Console(
            file=io.StringIO(),
            force_terminal=True,
            color_system="standard",
            no_color=False,
            width=1_000_000,
            highlight=False,
            markup=False,
            emoji=False,
            soft_wrap=True,
            legacy_windows=False,
            _environ={},
        )
    return _console


def style(text: str, meaning: str) -> str:
    """``text`` drawn in ``meaning`` (``green``, ``yellow``, ``red``, ``bold`` or ``dim``); plain
    text for an empty string or a meaning that is none of them."""
    if not text or meaning not in _STYLES:
        return text
    console = _rich()
    with console.capture() as captured:
        console.print(Text(text, style=_STYLES[meaning]), end="")
    return captured.get()


def verdict(word: str, sentence: str) -> str:
    """A verdict line, ``word  sentence``, drawn with escapes and no newline: the word in its
    meaning's style (``look.meaning``), the sentence as it is."""
    return style(word, look.meaning(word)) + "  " + sentence


# ---------- tables ----------

#: What a column of numbers holds: a number as rule 10 prints it (a count, a rate, a p-value, a
#: percentage, a signed change), a ratio ``12/32``, or a dash for none.
_NUMBER = re.compile(r"^[+\-−]?[\d,]*\.?\d+(?:e[+\-]?\d+)?%?$|^\d[\d,]*/\d[\d,]*$|^[–-]$")
#: A cell that ends in a unit: a number, a space, then a word (``+3.2 points``, ``1,210 ms``).
_UNIT = re.compile(r"^([+\-−]?[\d,]*\.?\d+(?:e[+\-]?\d+)?) ([A-Za-z%][A-Za-z%]*)$")
_GAP = 2
_RULE = "─"


def _key(cell: str) -> list[tuple[str, str]] | None:
    """A cell that is a JSON object (an input's key, as the reports print it) as its fields, each
    value spelt as the JSON spells it; None for any other cell."""
    if not cell.startswith("{"):
        return None
    try:
        fields = json.loads(cell, parse_float=str, parse_int=str)
    except ValueError:
        return None
    if not isinstance(fields, dict) or not fields:
        return None
    out = []
    for name, value in fields.items():
        if isinstance(value, str):
            spelt = value  # a number is read as its own text, so it is spelt as the JSON spells it
        elif value is None:
            spelt = "null"
        elif isinstance(value, bool):
            spelt = "true" if value else "false"
        else:
            return None  # a nested value: the cell stays as the report prints it
        out.append((str(name), spelt))
    return out


def _axes(fields: Sequence[tuple[str, str]]) -> str:
    """A key on one line: ``task_id HumanEval/129 · temperature 0.7``."""
    return " · ".join(f"{name} {value}" for name, value in fields)


def _units(
    header: Sequence[str], rows: Sequence[Sequence[str]]
) -> tuple[list[str], list[list[str]]]:
    """The header and rows with every unit that every cell of a column repeats moved into the
    column's header: ``change`` over ``+3.2 points`` becomes ``change (points)`` over ``+3.2``."""
    head, body = list(header), [list(r) for r in rows]
    for i in range(len(head)):
        units: set[str] = set()
        for row in body:
            m = _UNIT.match(row[i]) if i < len(row) else None
            if m is None:
                units = set()
                break
            units.add(m.group(2))
        if len(units) == 1 and body:
            unit = units.pop()
            head[i] = f"{head[i]} ({unit})"
            for row in body:
                row[i] = row[i][: -len(unit) - 1]
    return head, body


def _words(text: str) -> list[str]:
    return text.split(" ")


def _wrap(text: str, width: int) -> list[str]:
    """``text`` broken at spaces into lines no wider than ``width`` where its words allow; a word
    wider than ``width`` stands on a line of its own, whole."""
    lines: list[str] = []
    line = ""
    for w in _words(text):
        if not line:
            line = w
        elif cell_len(line) + 1 + cell_len(w) <= width:
            line += " " + w
        else:
            lines.append(line)
            line = w
    lines.append(line)
    return lines


def _pad(text: str, width: int, right: bool) -> str:
    fill = " " * max(0, width - cell_len(text))
    return fill + text if right else text + fill


def _aligned(
    header: Sequence[str],
    rows: Sequence[Sequence[str]],
    width: int,
    *,
    stacked: dict[int, list[list[tuple[str, str]]]] | None = None,
    styled: int | None = None,
) -> str | None:
    """The table aligned in columns two spaces apart, the header dim over a dim rule, numbers to
    the right; None when its columns cannot fit ``width`` with every body cell whole on one line
    and every header on two at most. ``stacked`` gives, for a column, each row's cell as
    fields printed one ``name  value`` a line, the name dim. ``styled`` is the column headed
    ``verdict``, each cell's verdict word drawn in its meaning."""
    n = len(header)
    stacked = stacked or {}
    cells: list[list[list[str]]] = []  # [row][column] -> lines

    def lines_of(i: int, cell: str, r: int) -> list[str]:
        if i in stacked:
            return [f"{name}  {value}" for name, value in stacked[i][r]]
        return [cell]

    for r, row in enumerate(rows):
        cells.append([lines_of(i, row[i] if i < len(row) else "", r) for i in range(n)])
    # the least each column can take: its widest body line, since a cell is never broken, and
    # the header's longest word; the most, its widest line, the header included
    least = []
    most = []
    for i in range(n):
        body = [line for row in cells for line in row[i]]
        least.append(max((cell_len(t) for t in [*body, *_words(header[i])]), default=0))
        most.append(max((cell_len(t) for t in [header[i], *body]), default=0))
    room = width - _GAP * (n - 1)
    if sum(least) > room:
        return None
    # what is left is shared evenly among the columns whose header would otherwise wrap, none
    # past the widest line it holds
    widths = list(least)
    while sum(widths) < room and any(widths[i] < most[i] for i in range(n)):
        for i in range(n):
            if widths[i] < most[i] and sum(widths) < room:
                widths[i] += 1
    heads = [_wrap(h, widths[i]) for i, h in enumerate(header)]
    if any(len(h) > 2 for h in heads):
        return None  # a header broken over three lines: the next fold reads more easily
    numeric = [
        i not in stacked
        and bool(rows)
        and all(
            _NUMBER.match(row[i].strip()) is not None or _UNIT.match(row[i].strip()) is not None
            for row in rows
            if i < len(row) and row[i].strip()
        )
        for i in range(n)
    ]
    out: list[str] = []

    def emit(parts: list[list[str]], styles: list[str | None]) -> None:
        height = max(len(p) for p in parts)
        for k in range(height):
            pieces = []
            for i, p in enumerate(parts):
                text = p[k] if k < len(p) else ""
                padded = _pad(text, widths[i], numeric[i])
                if i in stacked and text:
                    name, _, value = text.partition("  ")
                    padded = style(name, "dim") + padded[len(name) :]
                elif text and (styles[i] is not None or i == styled):
                    lead = len(padded) - len(padded.lstrip(" "))
                    trail = len(padded) - len(padded.rstrip(" "))
                    meaning = styles[i]
                    drawn = _verdict_cell(text) if meaning is None else style(text, meaning)
                    padded = padded[:lead] + drawn + padded[len(padded) - trail :]
                pieces.append(padded)
            out.append(("  ".join(pieces)).rstrip() + "\n")

    emit(heads, ["dim"] * n)
    out.append(style(_RULE * min(width, sum(widths) + _GAP * (n - 1)), "dim") + "\n")
    for drawn_row in cells:
        emit([list(lines) for lines in drawn_row], [None] * n)
    return "".join(out)


def _records(
    header: Sequence[str],
    rows: Sequence[Sequence[str]],
    width: int,
    key: int,
    keys: Sequence[Sequence[tuple[str, str]] | None],
    styled: int | None = None,
) -> str:
    """One record per row, a blank line between records: the key's fields one ``name  value`` a
    line (or the key cell), then every other cell as ``column value``, the column dim, as many
    whole pieces to a line as fit; the ``styled`` column's verdict word in its meaning."""
    out: list[str] = []
    lead = "  "
    for r, row in enumerate(rows):
        if r:
            out.append("\n")
        fields = keys[r]
        if fields:
            out += [f"{style(name, 'dim')}  {value}\n" for name, value in fields]
        else:
            out.append(f"{row[key] if key < len(row) else ''}\n")
        line, drawn = "", ""
        for i, column in enumerate(header):
            cell = row[i] if i < len(row) else ""
            if i == key or not cell.strip():
                continue
            piece = f"{column} {cell}"
            if line and cell_len(line) + 2 + cell_len(piece) > width:
                out.append(drawn + "\n")
                line, drawn = "", ""
            sep = "  " if line else lead
            line += sep + piece
            shown = _verdict_cell(cell) if i == styled else cell
            drawn += sep + style(column, "dim") + " " + shown
        if line:
            out.append(drawn + "\n")
    return "".join(out)


#: The verdict words a table cell may hold that are drawn in their meaning: the
#: continuous measures' calls. A cell holding any other word (``identical``, ``not tested``,
#: ``not recorded``, a dash) stays plain, and a direction after the word (``, slower``) is plain.
_VERDICT_WORDS = ("different", "unconfirmed", "too small to tell", "no significant difference")


def _verdict_cell(text: str) -> str:
    """A cell of the column headed ``verdict``: its verdict word in its meaning's style
    (``look.meaning``), the comma and the direction after it as they are."""
    word, comma, direction = text.partition(", ")
    if word not in _VERDICT_WORDS:
        return text
    return style(word, look.meaning(word)) + comma + direction


def table(header: Sequence[str], rows: Sequence[Sequence[str]], *, width: int) -> str:
    """The pretty face of ``look.table(header, rows)`` for a terminal ``width`` wide, drawn with
    escapes, each line ended. Aligned when it fits; folded when it is too wide: a unit every cell
    of a column repeats moves into the header, and a key (a JSON object) is printed one field per
    line; one record per row when even the fold is too wide. No cell is broken across lines (a
    header may take two), no word cut and no digit coloured; in the column headed ``verdict`` a
    verdict word is drawn in its meaning."""
    width = max(20, width)
    header = [str(h) for h in header]
    rows = [[str(c) for c in row] for row in rows]
    n = len(header)
    styled = header.index("verdict") if "verdict" in header else None
    key_columns: list[int]
    keys = [[_key(row[i]) if i < len(row) else None for i in range(n)] for row in rows]
    key_columns = [i for i in range(n) if rows and all(k[i] is not None for k in keys)]
    # unfolded: a key on one line, as its axes, never broken
    flat = [
        [_axes(keys[r][i] or []) if i in key_columns else row[i] for i in range(n)]
        for r, row in enumerate(rows)
    ]
    drawn = _aligned(header, flat, width, styled=styled)
    if drawn is not None:
        return drawn
    # folded: the units into the header, each key one field per line
    head, body = _units(header, rows)
    stacked = {i: [keys[r][i] or [] for r in range(len(rows))] for i in key_columns}
    drawn = _aligned(head, body, width, stacked=stacked, styled=styled)
    if drawn is not None:
        return drawn
    key = key_columns[0] if key_columns else 0
    return _records(head, body, width, key, [k[key] for k in keys], styled)
