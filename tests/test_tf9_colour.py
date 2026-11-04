"""TF9, invariant 3: colour by meaning (spec section 17.1, AD2; the look file's rule 16).

Green ``ok`` and ``done``; yellow ``stopped``, ``refused``, ``too small to tell``, ``no significant
difference``, ``no control`` and ``note:``; red ``error:``, ``not ready`` and ``not whole``; dim for
secondary text; ``different`` and ``plan`` bold with no colour. A number is never coloured. Only
the 16 named colours, bold and dim.

- **TF9-3a** Each of Trace's verdict words, drawn by the renderer as a verdict line, takes its
  meaning, and its sentence carries no colour on any digit; with escapes removed the line is the
  plain line. This covers the words no verb on main reaches without timing (``done``,
  ``refused``, ``no control``, ``not whole``, ``plan``, and ``stopped``, which needs a Ctrl-C) as
  well as the rest. The renderer is ``poisson_trace._pretty.verdict(word, sentence)``, which
  returns the line drawn with escapes and no newline.
- **TF9-3b** On every command of the corpus, on two terminals: the first line's verdict word has
  its meaning; ``error:`` opens a refusal's line in red; ``note:`` opens a note's line in yellow.
- **TF9-3c** On every command of the corpus: colour is drawn only on the words that carry a
  meaning (each run of green, yellow or red text is one of them), never on a digit, and no colour
  but green, yellow and red is drawn.
- **TF9-3d** On every command of the corpus: no escape the look does not allow (a background,
  256 or true colour, italic, underline, reverse, blink, a hyperlink, a cursor movement on
  stdout); stderr may carry only the controls a live display needs to remove itself.

Which text is secondary, and so dim, is left to the build (the rendering's design); dim is held
only to what these tests hold every style to.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tf9_support import CORPUS, MAY_BE, ROLE, VERDICT, Item, cells, odd_escapes, pretty, role, runs_of, shared_base, strip

SENTENCE = "the new version failed 1,387 of 10,496 tries and the old 1,338 (p = 0.036, 2.30e-08)"


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return shared_base(tmp_path_factory)


# ---------- TF9-3a ----------


@pytest.mark.parametrize("word", sorted(ROLE), ids=str)
def test_tf9_3a_each_verdict_word_takes_its_meaning(word: str) -> None:
    from poisson_trace import _pretty

    drawn = _pretty.verdict(word, SENTENCE)
    assert "\n" not in drawn
    assert strip(drawn) == f"{word}  {SENTENCE}"
    line = cells(drawn)[0]
    head = line[: len(word)]
    want = ROLE[word]
    roles = {role(c) for c in head if c.char != " "}
    assert roles == {want}, f"{word}: drawn {roles}, where {want} is its meaning"
    if want == "B":
        assert all(c.bold and c.fg is None for c in head if c.char != " ")
    digits = [c for c in line if c.char.isdigit()]
    assert digits and all(c.fg is None for c in digits), "a digit of the sentence is coloured"
    assert odd_escapes(drawn, live=False) == []


# ---------- TF9-3b ----------


@pytest.mark.parametrize("item", [i for i in CORPUS if i.expect in (0, 4) and "help" not in i.label and i.label != "version"], ids=lambda i: i.label)
def test_tf9_3b_the_verdict_word_on_screen_takes_its_meaning(base: Path, item: Item) -> None:
    r = pretty(base, item)
    assert r.code == item.expect
    first = cells(r.out)[0]
    m = VERDICT.match("".join(c.char for c in first))
    assert m, "the first stdout line is not a verdict line"
    word = m.group(1)
    assert word in ROLE, word
    head = [c for c in first[: len(word)] if c.char != " "]
    assert {role(c) for c in head} == {ROLE[word]}, f"{word} is not drawn as {ROLE[word]}"


@pytest.mark.parametrize(
    "item, prefix, colour",
    [(next(i for i in CORPUS if i.label == "a refusal"), "error:", "R"), (next(i for i in CORPUS if i.label == "a wrong command line"), "error:", "R"), (next(i for i in CORPUS if i.label == "runs with a note"), "note:", "Y")],
    ids=["a refusal", "a wrong command line", "a note"],
)
def test_tf9_3b_problem_lines_open_in_their_colour(base: Path, item: Item, prefix: str, colour: str) -> None:
    r = pretty(base, item)
    assert r.code == item.expect
    opened = [line for line in cells(r.err) if "".join(c.char for c in line).startswith(prefix)]
    assert opened, f"no {prefix} line on stderr"
    for line in opened:
        assert {role(c) for c in line[: len(prefix)]} == {colour}, f"{prefix} is not drawn as {colour}"


# ---------- TF9-3c ----------


@pytest.mark.parametrize("item", CORPUS, ids=lambda i: i.label)
def test_tf9_3c_colour_only_on_the_words_that_carry_a_meaning(base: Path, item: Item) -> None:
    r = pretty(base, item)
    wrong: list[str] = []
    for stream, text in (("stdout", r.out), ("stderr", r.err)):
        for line in cells(text):
            for c in line:
                if c.char.isdigit() and c.fg is not None:
                    wrong.append(f"{stream}: a coloured digit in {''.join(x.char for x in line)[:70]!r}")
                    break
            for colour, run_text in runs_of(line):
                if colour == "O":
                    wrong.append(f"{stream}: a colour outside the four meanings on {run_text!r}")
                elif run_text not in MAY_BE[colour]:
                    wrong.append(f"{stream}: {run_text!r} drawn in {colour}")
    assert wrong == [], wrong[:5]


# ---------- TF9-3d ----------


@pytest.mark.parametrize("item", CORPUS, ids=lambda i: i.label)
def test_tf9_3d_only_the_escapes_the_look_allows(base: Path, item: Item) -> None:
    r = pretty(base, item)
    assert odd_escapes(r.out, live=False) == []
    assert odd_escapes(r.err, live=True) == []
