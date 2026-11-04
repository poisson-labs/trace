"""TF9, invariant 4: widths (spec sections 9.3 and 17.1; the look file's rule 16).

- **TF9-4a** The per-input table folds under 100 columns: on a terminal 80 wide, the unit every
  cell of a column repeats (``points``, in ``change``) moves into the header, and the input's key
  (a JSON object of the input's fields) is printed one field per line, each field's name and
  value on one line. On a terminal 160 wide the table is not folded: each input's key is on its
  row's one line, and the unit stays in the cells. Read on ``fix-check`` and ``changes`` over
  Prove's HumanEval store, whose inputs are keyed by two fields.
- **TF9-4b** No line of the pretty rendering's stdout is wider than the terminal, at 80 and at 120
  columns, but the first line (the verdict line, kept whole as plain's wrapping rule keeps it, so
  that TF9-7b reads it byte for byte: LB1, ruled 2026-11-03), a line that holds a command to copy,
  or a word that is itself wider than the terminal. (Stricter than "no table line": the pretty
  rendering wraps stdout's prose to the terminal too.) Stderr is held to the look's rule 4
  instead: each problem is one line, so an ``error:`` or ``note:`` line is never broken (TF9-7b
  reads a refusal's first line whole).
- **TF9-4c** A command to copy is never broken: each command the plain rendering prints for the
  user to copy (a ``next:`` line's, a command line, a ``label  command`` detail line's, a command in
  backquotes) is on one line of the pretty rendering, every character in place.
- **TF9-4d** No progress line is left on screen: when the command has ended, the stderr terminal
  shows nothing the plain stderr does not say, neither terminal shows a bar or a spinner, and
  stdout never redraws a line.

The tables the later pairs add (the failure breakdown, the continuous measures) inherit these
rules through the renderer: ``test_tf9_new_table.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tf9_support import CHANGES_HE, CORPUS, FIX_CHECK_HE, PROGRESS, Item, commands, piped, pretty, screen_text, shared_base, strip, tokens

WIDTHS = (80, 120)


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return shared_base(tmp_path_factory)


# ---------- TF9-4a ----------

#: The plain line just before the per-input table and the one just after it, as words that open
#: each (the pretty rendering may wrap them).
_BEFORE = "Fisher's exact test per input"
_AFTER = re.compile(r"\b\d+ of [\d,]+ inputs shown\b")


def _table(text: str) -> list[str]:
    """The pretty rendering's lines between the line before the per-input table and the line
    after it, escapes removed."""
    lines = strip(text).split("\n")
    start = next(i for i, line in enumerate(lines) if _BEFORE in line)
    end = next(i for i, line in enumerate(lines) if i > start and _AFTER.search(line))
    body = lines[start + 1 : end]
    # the line before may wrap: its continuation is prose, not the table
    while body and body[0].strip() and not re.search(r"input|task_id|change", body[0]):
        body.pop(0)
    return body


@pytest.mark.parametrize("item", [FIX_CHECK_HE, CHANGES_HE], ids=lambda i: i.label)
def test_tf9_4a_the_per_input_table_folds_under_100_columns(base: Path, item: Item) -> None:
    plain = piped(base, item)
    rows = [line for line in plain.out.split("\n") if line.startswith('| {"task_id"')]
    assert rows, "the plain rendering has no per-input rows"
    folded = _table(pretty(base, item, 80).out)
    with_id = [line for line in folded if "task_id" in line]
    with_temp = [line for line in folded if "temperature" in line]
    assert len(with_id) == len(rows) == len(with_temp), "not one line for each field of each input"
    assert not any("task_id" in line and "temperature" in line for line in folded), "two fields on one line"
    for row in rows:
        task = re.search(r'"task_id":"([^"]+)"', row).group(1)  # type: ignore[union-attr]
        assert any(task in line for line in with_id), f"{task} is not beside its field's name"
    header = [line for line in folded if "points" in line and "task_id" not in line and "temperature" not in line]
    cells_with_unit = [line for line in folded if re.search(r"\d\s*points", line)]
    assert header, "the unit is not in the header"
    assert cells_with_unit == [], "the unit is still in the cells"

    wide = _table(pretty(base, item, 160).out)
    one_line = [line for line in wide if "task_id" in line and "temperature" in line]
    assert len(one_line) == len(rows), "at 160 columns each input's key is not on its row's line"
    assert all(re.search(r"\d\s*points", line) for line in one_line), "at 160 columns the unit left the cells"


# ---------- TF9-4b ----------


def _too_wide(text: str, plain: str, cols: int) -> list[str]:
    copy = commands(plain)
    out = []
    # the first line is the verdict line, whole whatever its length (LB1)
    for line in strip(text).split("\n")[1:]:
        if len(line) <= cols:
            continue
        if any(c in line for c in copy):
            continue
        if any(len(w) > cols - (len(line) - len(line.lstrip())) for w in line.split()):
            continue
        out.append(line[:90])
    return out


@pytest.mark.parametrize("cols", WIDTHS)
@pytest.mark.parametrize("item", CORPUS, ids=lambda i: i.label)
def test_tf9_4b_no_line_wider_than_the_terminal(base: Path, item: Item, cols: int) -> None:
    plain = piped(base, item)
    r = pretty(base, item, cols)
    assert _too_wide(r.out, plain.out, cols) == []


# ---------- TF9-4c ----------


@pytest.mark.parametrize("item", CORPUS, ids=lambda i: i.label)
def test_tf9_4c_a_command_to_copy_is_never_broken(base: Path, item: Item) -> None:
    plain = piped(base, item)
    r = pretty(base, item, 80)
    lost = [c for c in commands(plain.out) if not any(c in line for line in strip(r.out).split("\n"))]
    lost += [c for c in commands(plain.err) if not any(c in line for line in strip(r.err).split("\n"))]
    assert lost == []


# ---------- TF9-4d ----------


@pytest.mark.parametrize("item", CORPUS, ids=lambda i: i.label)
def test_tf9_4d_no_progress_line_left_on_screen(base: Path, item: Item) -> None:
    """Progress is drawn on stderr and removed: what stays on the stderr terminal holds no word or
    number the plain stderr does not; neither terminal is left showing a bar or a spinner; stdout
    never redraws a line (no carriage return)."""
    plain = piped(base, item)
    r = pretty(base, item, 80)
    left = [line for line in (*r.out_screen, *r.err_screen) if PROGRESS.search(line)]
    assert left == []
    extra = tokens(screen_text(r.err_screen, 80)) - tokens(plain.err)
    assert extra == set(), f"left on the stderr terminal: {sorted(extra)[:10]}"
    assert "\r" not in r.out
