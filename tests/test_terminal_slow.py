"""TF9 over the whole conformance corpus: the slow lane (``-m slow``), never on a pull request.

The fast lane holds each of these invariants on ``terminal_support.CORPUS``, one of each verb, verdict
word and problem line; this lane runs every invocation of ``look_support.corpus`` (every verb's
help, the version, the README's worked examples, every refusal and wrong command line) on two
terminals at 80 and at 120 columns, and holds it to the same readings: the colours and escapes
(TF9-3c, TF9-3d), the widths and the commands (TF9-4b, TF9-4c), the first line and exit code
(TF9-7b), and the same facts (TF9-7c, words and numbers).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from test_terminal_widths import _too_wide
from look_support import corpus
from terminal_support import MAY_BE, Item, cells, commands, odd_escapes, piped, pretty, runs_of, shared_base, strip, tokens

pytestmark = pytest.mark.slow

ITEMS = tuple(
    Item(i.label, i.command, i.argv, i.expect, "tf0-bare" if i.command == "import" and i.kind == "report" else "tf0")
    for i in corpus()
)


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return shared_base(tmp_path_factory)


@pytest.mark.parametrize("cols", [80, 120])
@pytest.mark.parametrize("item", ITEMS, ids=lambda i: i.label)
def test_tf9_slow_the_whole_corpus_both_ways(base: Path, item: Item, cols: int) -> None:
    plain = piped(base, item)
    r = pretty(base, item, cols)
    wrong: list[str] = []
    if (r.code, plain.code) != (item.expect, item.expect):
        wrong.append(f"exit {r.code} pretty, {plain.code} plain, {item.expect} called for")
    if item.expect in (1, 2):
        if strip(r.err).split("\n", 1)[0] != plain.err.split("\n", 1)[0]:
            wrong.append("the error line differs from plain's")
    elif strip(r.out).split("\n", 1)[0] != plain.out.split("\n", 1)[0]:
        wrong.append("the first line differs from plain's")
    for stream, drawn, said in (("stdout", r.out, plain.out), ("stderr", r.err, plain.err)):
        if tokens(drawn) != tokens(said):
            wrong.append(f"{stream}: not the same words and numbers")
        for line in cells(drawn):
            if any(c.char.isdigit() and c.fg is not None for c in line):
                wrong.append(f"{stream}: a coloured digit")
            wrong += [f"{stream}: {t!r} in {c}" for c, t in runs_of(line) if c == "O" or t not in MAY_BE[c]]
        wrong += [f"{stream}: {e}" for e in odd_escapes(drawn, live=stream == "stderr")]
        lines = strip(drawn).split("\n")
        wrong += [f"{stream}: broken {c[:40]!r}" for c in commands(said) if not any(c in line for line in lines)]
    # --json prints the piped bytes on a terminal too (TF9-6a), so its lines never wrap
    if "--json" not in item.argv:
        wrong += [f"too wide: {line!r}" for line in _too_wide(r.out, plain.out, cols)]
    assert wrong == [], wrong[:6]
