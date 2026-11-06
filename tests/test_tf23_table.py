"""TF23-33 and TF23-34: the continuous-measures table (spec sections 17.1 and 18.6, SG14; TF9-8 holds
any new table to the clean look, and this is that table).

**TF23-33** ``continuous.table(comparison)`` gives a header and rows: the header opens with
``measure`` and ends with ``verdict``; one row a measure shown, in the order of ``MEASURES``, its
first cell the measure and its last the verdict word (``identical`` for a measure that did not
change on any case), followed by the direction after a comma when there is one (``different,
slower``: Taylor's DM3, 2026-11-05); a measure no case recorded is left out, and shown as
``not recorded`` with ``technical=True``.

**TF23-34** The table renders through ``look.table`` (plain: the markdown table, no escape) and
``_pretty.table`` under the clean look's rules: at every width from 60 to 160 no line is wider
than the width, no digit is coloured, only escapes the look allows are drawn, and the pretty face
holds every word and number of the plain one, rows in the same order; the one word it may
leave out is the key column's header, ``measure``, where it folds to one record per row (CT1).
"""

from __future__ import annotations

import numpy as np
import pytest

from tf23_support import MEASURES, cm, run, version
from tf9_support import cells, odd_escapes, strip, tokens


def _comparison():  # type: ignore[no-untyped-def]
    """Wall time different, output tokens quiet, input length identical, cost on 6 cases only
    (under the floor), working time and input tokens never recorded."""
    T = cm().Try
    k = 24
    rng = np.random.default_rng(33)
    wall = rng.lognormal(1.5, 0.5, k)
    out = rng.integers(200, 900, k).astype(float)
    va, vb = {}, {}
    for i in range(k):
        a = {"wall_time_s": float(wall[i]), "output_tokens": float(out[i]), "input_chars": 1840.0,
             "cost_usd": float(out[i] * 2e-5) if i < 6 else None, "total_tokens": float(out[i] + 600)}
        b = {"wall_time_s": float(wall[i] * 1.4 + 0.2), "output_tokens": float(out[i] + rng.integers(-40, 41)),
             "input_chars": 1840.0, "cost_usd": float(out[i] * 2.2e-5) if i < 6 else None,
             "total_tokens": float(out[i] + 600 + rng.integers(-40, 41))}
        va[f"case_{i:03d}"] = [T(values=a, repeat=0)]
        vb[f"case_{i:03d}"] = [T(values=b, repeat=0)]
    return run(version("20261103T101500Z-aa01", "old", va), version("20261103T113000Z-bb02", "new", vb),
               ceilings={"output_tokens": 0.2})


def test_tf23_33_the_rows() -> None:
    c = _comparison()
    header, rows = cm().table(c)
    assert header[0] == "measure" and header[-1] == "verdict"
    assert all(len(r) == len(header) for r in rows)
    shown = [r[0] for r in rows]
    recorded = [m for m in MEASURES if c.measures[m].status != "not_recorded"]
    assert shown == recorded
    assert "working_time_s" not in shown and "input_tokens" not in shown
    by = {r[0]: r[-1] for r in rows}
    assert by["wall_time_s"] == "different, slower"
    assert by["input_chars"] == "identical"
    assert by["cost_usd"] == "too small to tell"
    assert by["output_tokens"] in ("no significant difference", "too small to tell")


def test_tf23_33_not_recorded_under_technical() -> None:
    _, rows = cm().table(_comparison(), technical=True)
    assert [r[0] for r in rows] == list(MEASURES)
    by = {r[0]: r[-1] for r in rows}
    assert by["working_time_s"] == "not recorded" and by["input_tokens"] == "not recorded"


def test_tf23_34_plain_is_the_markdown() -> None:
    from poisson_trace import look

    header, rows = cm().table(_comparison())
    plain = look.table(header, rows)
    assert "\x1b" not in plain
    assert plain == (
        "| " + " | ".join(header) + " |\n" + "|---" * len(header) + "|\n"
        + "".join("| " + " | ".join(r) + " |\n" for r in rows)
    )


@pytest.mark.parametrize("width", [60, 80, 100, 120, 160])
def test_tf23_34_the_clean_looks_rules(width: int) -> None:
    from poisson_trace import _pretty, look

    header, rows = cm().table(_comparison())
    plain = look.table(header, rows)
    drawn = _pretty.table(header, rows, width=width)
    lines = strip(drawn).split("\n")
    assert [line for line in lines if len(line) > width] == []
    assert odd_escapes(drawn, live=False) == []
    assert not any(ch.char.isdigit() and ch.fg is not None for line in cells(drawn) for ch in line), "a coloured digit"
    # every word and number of plain, but one: folded to one record per row (here at 60 columns)
    # TF9's renderer prints each record under its key and leaves out the key column's header word,
    # "measure" (ruling CT1, log/trace-tf23-a/rulings.md)
    assert tokens(drawn) <= tokens(plain)
    assert tokens(plain) - tokens(drawn) <= {header[0]}
    order = [next(i for i, line in enumerate(lines) if r[0] in line) for r in rows]
    assert order == sorted(order), "the rows are not in plain's order"
