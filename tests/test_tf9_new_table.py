"""TF9: a table a later pair adds gets the same rules (spec section 17.1, read with sections 18.5 and
18.6: the failure breakdown and the continuous measures come in their own pairs, TF21 and TF23,
and inherit TF9's rules through its renderer).

The renderer has two faces, and every table goes through both:

- ``poisson_trace.look.table(header, rows) -> str``, standard library: the plain rendering, a
  markdown table exactly as the reports print theirs today (``| a | b |``, then ``|---|---|``,
  then one ``| … |`` line a row, each line ending in a newline).
- ``poisson_trace._pretty.table(header, rows, *, width) -> str``: the pretty rendering of the same
  table for a terminal ``width`` wide, drawn with escapes.

**TF9-8** A table nobody has printed before, of continuous measures keyed by inputs of three
fields with units in its cells, rendered through the renderer: plain is the markdown with no
escape; pretty, at every width from 60 to 160, has no line wider than the width, colours no
digit and draws only the escapes the look allows, and holds every word and number the plain
table holds, in the same row order; folded (at 60) it moves each unit every cell of a column
repeats into the header and prints the key one field per line; unfolded (at 160) it keeps the
key on its row's line.
"""

from __future__ import annotations

import re

import pytest

from tf9_support import cells, odd_escapes, strip, tokens

HEADER = ("input", "old median", "new median", "change", "p")
ROWS = (
    ('{"task":"search","seed":3,"temperature":0.7}', "1,210 ms", "1,530 ms", "+320 ms", "0.012"),
    ('{"task":"checkout","seed":3,"temperature":0.7}', "880 ms", "860 ms", "-20 ms", "0.640"),
    ('{"task":"refund","seed":11,"temperature":0.0}', "2,045 ms", "2,990 ms", "+945 ms", "2.3e-08"),
)


def test_tf9_8_the_plain_face_is_the_markdown_the_reports_print() -> None:
    from poisson_trace import look

    assert look.table(HEADER, ROWS) == (
        "| input | old median | new median | change | p |\n"
        "|---|---|---|---|---|\n"
        + "".join("| " + " | ".join(row) + " |\n" for row in ROWS)
    )


@pytest.mark.parametrize("width", [60, 80, 100, 120, 160])
def test_tf9_8_a_new_table_gets_the_rules(width: int) -> None:
    from poisson_trace import _pretty, look

    plain = look.table(HEADER, ROWS)
    assert "\x1b" not in plain
    drawn = _pretty.table(HEADER, ROWS, width=width)
    lines = strip(drawn).split("\n")
    assert [line for line in lines if len(line) > width] == []
    assert odd_escapes(drawn, live=False) == []
    assert not any(c.char.isdigit() and c.fg is not None for line in cells(drawn) for c in line), "a coloured digit"
    assert tokens(drawn) == tokens(plain)
    order = [next(i for i, line in enumerate(lines) if task in line) for task in ("search", "checkout", "refund")]
    assert order == sorted(order), "the rows are not in plain's order"


FIELDS = ("task", "seed", "temperature")


def _fields(line: str) -> list[str]:
    return [f for f in FIELDS if re.search(rf"\b{f}\b", line)]


def test_tf9_8_folded_the_unit_goes_to_the_header_and_the_key_one_field_a_line() -> None:
    from poisson_trace import _pretty

    lines = strip(_pretty.table(HEADER, ROWS, width=60)).split("\n")
    assert [line for line in lines if len(_fields(line)) > 1] == [], "two fields on one line"
    for field in FIELDS:
        assert sum(_fields(line) == [field] for line in lines) == len(ROWS), f"{field} is not on a line of its own once an input"
    assert [line for line in lines if re.search(r"\d\s*ms\b", line)] == [], "the unit is still in the cells"
    assert any(re.search(r"\bms\b", line) for line in lines), "the unit is not in the header"


def test_tf9_8_unfolded_the_key_stays_on_its_row() -> None:
    from poisson_trace import _pretty

    lines = strip(_pretty.table(HEADER, ROWS, width=160)).split("\n")
    for task in ("search", "checkout", "refund"):
        row = [line for line in lines if task in line]
        assert len(row) == 1 and _fields(row[0]) == list(FIELDS), f"{task}'s key is not on its row's line"
        assert re.search(r"\d\s*ms\b", row[0]), f"{task}'s row lost its unit"
