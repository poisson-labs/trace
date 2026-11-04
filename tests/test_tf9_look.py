"""TF9, invariant 7: what else the look file requires (spec sections 9.2 and 17.1; the look file's
rules 15 and 16).

- **TF9-7a** ``docs/cli-look.md`` is Prove's look file byte for byte, as poisson-prove 0.1.2
  publishes it (tag ``v0.1.2``): 275 lines, the digest below. When Prove's file moves, the session
  that moves Trace's pin copies the new bytes and moves this digest in one commit.
- **TF9-7b** In a pseudo-terminal, with escapes removed, the first line carries the same verdict
  word and sentence as plain's, and the exit code is plain's.
- **TF9-7c** The same facts, in the same order: on each stream, the pretty rendering holds the
  same words and numbers as the plain rendering, none added and none lost, and the report's
  headings come in plain's order. (So questions and progress stay where plain puts them: on
  stderr.)
- **TF9-7d** Plain on a terminal wraps its own long lines at the terminal's width with a hanging
  indent, and keeps each line's words in order; the verdict line, a table row and a line holding
  a command are printed whole. Stderr is printed as on a pipe: each problem is one line (rule 4).
  Piped, it prints one line per fact (TF9-1b).
- **TF9-7e** A Trace that cannot import Rich prints plain, and says nothing about it.

``NO_COLOR`` turning off the whole pretty rendering, not only its colour, is TF9-2b (its output is
``--plain``'s, byte for byte).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tf9_support import (
    CORPUS, LOOK, LOOK_LINES, LOOK_SHA256, REPORTS, Item, piped, plain_on_terminal, pretty, sha256_of, shared_base, shared_run, strip,
    tokens, unwrap,
)


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return shared_base(tmp_path_factory)


def test_tf9_7a_the_look_file_is_prove_0_1_2s_byte_for_byte() -> None:
    assert sha256_of(LOOK) == LOOK_SHA256
    assert len(LOOK.read_bytes().split(b"\n")) - 1 == LOOK_LINES


@pytest.mark.parametrize("item", CORPUS, ids=lambda i: i.label)
def test_tf9_7b_the_first_line_and_the_exit_code_are_plains(base: Path, item: Item) -> None:
    plain = piped(base, item)
    r = pretty(base, item)
    assert r.code == plain.code == item.expect
    if item.expect in (1, 2):
        assert r.out == plain.out == ""
        assert strip(r.err).split("\n", 1)[0] == plain.err.split("\n", 1)[0]
    else:
        assert strip(r.out).split("\n", 1)[0] == plain.out.split("\n", 1)[0]


def _headings(text: str) -> list[str]:
    return [line.lstrip("#").strip() for line in text.split("\n") if line.startswith("#")]


@pytest.mark.parametrize("item", CORPUS, ids=lambda i: i.label)
def test_tf9_7c_the_same_facts_in_the_same_order(base: Path, item: Item) -> None:
    plain = piped(base, item)
    r = pretty(base, item)
    for stream, drawn, said in (("stdout", r.out, plain.out), ("stderr", r.err, plain.err)):
        added, lost = tokens(drawn) - tokens(said), tokens(said) - tokens(drawn)
        assert (added, lost) == (set(), set()), f"{stream}: added {sorted(added)[:8]}, lost {sorted(lost)[:8]}"
    shown = " ".join(strip(r.out).split())
    at = 0
    for heading in _headings(plain.out):
        found = shown.find(" ".join(heading.split()), at)
        assert found >= 0, f"the heading {heading!r} is missing or out of order"
        at = found


@pytest.mark.parametrize("cols", [80, 120])
@pytest.mark.parametrize("item", REPORTS, ids=lambda i: i.label)
def test_tf9_7d_plain_on_a_terminal_wraps_with_a_hanging_indent(base: Path, item: Item, cols: int) -> None:
    plain = piped(base, item)
    r = plain_on_terminal(base, item, cols)
    assert r.code == plain.code
    assert "\x1b" not in r.out and "\x1b" not in r.err
    assert unwrap(plain.out, r.out, cols) == []
    assert r.err == plain.err, "plain on a terminal changed stderr: each problem is one line (rule 4)"


NO_RICH = "import sys\nfor _m in [m for m in sys.modules if m == 'rich' or m.startswith('rich.')]:\n    del sys.modules[_m]\nsys.modules['rich'] = None\n"


@pytest.mark.parametrize("item", [i for i in CORPUS if i.label in ("compare, too small to tell", "a refusal", "doctor, not ready")], ids=lambda i: i.label)
def test_tf9_7e_without_rich_it_prints_plain_and_says_nothing(base: Path, item: Item) -> None:
    got = shared_run(base, item, stdout="pty", stderr="own", prelude=NO_RICH)
    want = plain_on_terminal(base, item)
    assert (got.code, got.out, got.err) == (want.code, want.out, want.err)
