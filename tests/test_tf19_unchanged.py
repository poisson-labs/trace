"""TF19-10, TF19-11 and TF19-12: nothing else moves (rule 10 of the pair's brief; A2, A3).

**TF19-10** Every invocation of ``tf19_support.pin_corpus()`` prints, piped, what main b988bd3
printed, byte for byte: the exit code, stdout and stderr of each step. That is TF18's corpus
whole (the breakdown pair's corpus, every verb's help, the four counting verbs with ``--save``,
``--out``, ``--svg``, ``handover``), the outputs TF18 changed as main now prints them, ``ui`` and
``report`` with their helps and refusals, and the bare command on a pipe with no argument and with
``--plain``, ``--json``, ``--debug`` and ``--config=PATH``. Pinned by
``fixtures/tf19/make_main_pins.py``; the pins taken on Python 3.12.13 and checked on 3.11 too.

**TF19-11** The outputs TF19 changes, changed exactly so: the top ``--help`` is main's with two
rows added among its options, ``--store PATH`` and ``--config PATH`` (and their wrapped
continuations), and nothing else (A3); on a pipe, ``--config PATH`` or ``--store PATH`` with no
verb, alone, together or with ``--plain``, is the no-verb refusal main prints for no argument,
exit 2 (A2).

**TF19-12** The pages, as TF18 built them: ``ui`` over the app's workspace writes every page
file main wrote, byte for byte once the save times are set aside, and no other.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tf0_support import REPO
from tf13_support import workspace
from tf19_support import CHANGED, MAIN, NO_VERB, PINS, digest, make_world, normal, pages_pins, pin_corpus, run_steps, slow

PINNED: dict[str, Any] = json.loads(PINS.read_text(encoding="utf-8"))
CORPUS = pin_corpus()
SLOW = slow()


def _ran(tmp: Path, place: str, kind: str, steps: list[list[str]]) -> list[tuple[int, str, str]]:
    work = workspace(tmp) if place == "work" else REPO
    return [(r.code, normal(r.out, work), normal(r.err, work)) for r in run_steps(work, place, kind, steps)]


def test_tf19_10_every_case_is_pinned_on_main() -> None:
    assert PINNED["main"] == MAIN
    assert set(PINNED["piped"]) == set(CORPUS)
    assert set(PINNED["changed"]) == set(CHANGED)
    assert PINNED["pages"]


@pytest.mark.parametrize("label", [pytest.param(k, marks=pytest.mark.slow) if k in SLOW else k for k in CORPUS])
def test_tf19_10_as_main_prints_it(tmp_path: Path, label: str) -> None:
    place, kind, steps = CORPUS[label]
    from tf5_pins import as_main_printed

    # the docs pair (TF5) renamed the helps' example store and made the top help's list of tools whole;
    # TF5-3 holds those two changes, and this goes on holding every other byte of each help
    # the docs pair (TF5) also lists the bare command's verbs in the top help's order (ruled 2026-11-13, DOC-33);
    # TF5-3 holds that, and this goes on holding every other byte of the refusal
    # the Prove label kinds pair names, in these five, the labels that have no kind (test_pl_unchanged.py, PL-52, holds
    # that); this goes on holding every other byte of them
    from pl_pins import MOVED_SHARED, unmoved

    ran = _ran(tmp_path, place, kind, steps)
    ran = unmoved(ran) if label in MOVED_SHARED else ran
    got = [[code, digest(as_main_printed(label, out)), digest(as_main_printed(label, err) if not label.startswith("help") else err)]
           for code, out, err in ran]
    assert got == PINNED["piped"][label], label


# ---------- TF19-11: the ones that change ----------


def _help_parts(text: str) -> tuple[str, list[str], dict[str, str], list[str]]:
    """A top help as its parts: the usage (whitespace collapsed), the description's lines, the
    options (each option's invocation to its help's words, whitespace collapsed), and every line
    from ``verbs:`` on."""
    lines = text.splitlines()
    blank = lines.index("")
    start, end = lines.index("options:"), lines.index("verbs:")
    options: dict[str, str] = {}
    current = None
    for line in lines[start + 1:end]:
        if not line.strip():
            continue
        if line.startswith("  -"):
            invocation, _, words = line.strip().partition("  ")
            current = invocation.strip()
            options[current] = words.strip()
        else:
            assert current is not None, line
            options[current] = (options[current] + " " + line.strip()).strip()
    return " ".join(" ".join(lines[:blank]).split()), lines[blank:start], options, lines[end:]


def test_tf19_11_the_top_help_gains_the_two_options_and_nothing_else(tmp_path: Path) -> None:
    """The usage gains ``[--store PATH] [--config PATH]``; the options gain the two rows, every
    other option's words as main prints them (the column the helps start at may move, as
    argparse sets it by the longest option); the description and everything from ``verbs:`` on
    are main's byte for byte."""
    from tf5_pins import as_main_printed

    (code, out, err), = _ran(tmp_path, *CHANGED["help: top"])
    # the docs pair (TF5) renamed the helps' example store and made the top help's list of tools whole;
    # TF5-3 holds those two changes, and this goes on holding every other byte of each help
    out = as_main_printed("help: top", out)
    (main_code, main_out, main_err), = PINNED["changed"]["help: top"]
    assert (code, err) == (main_code, main_err)
    usage, description, options, rest = _help_parts(out)
    m_usage, m_description, m_options, m_rest = _help_parts(main_out)
    assert (description, rest) == (m_description, m_rest)
    assert "[--store PATH]" in usage and "[--config PATH]" in usage, usage
    assert " ".join(usage.replace("[--store PATH]", "").replace("[--config PATH]", "").split()) == m_usage
    added = {k: v for k, v in options.items() if k not in m_options}
    assert sorted(added) == ["--config PATH", "--store PATH"], options
    assert all(added.values()), added
    assert {k: v for k, v in options.items() if k in m_options} == m_options


@pytest.mark.parametrize("label", ["bare: config", "bare: store", "bare: both", "bare: plain config"])
def test_tf19_11_the_bare_options_on_a_pipe_are_the_no_verb_refusal(tmp_path: Path, label: str) -> None:
    (code, out, err), = _ran(tmp_path, *CHANGED[label])
    none = PINNED["piped"]["verb: none"]
    assert code == 2 == none[0][0]
    assert out == ""
    assert err == f"{NO_VERB}\n  next: poisson-trace --help\n"
    from tf5_pins import as_main_printed

    # main's refusal but for the order of its verbs, which the docs pair (TF5) made the top help's (ruled 2026-11-13, DOC-33)
    assert digest(as_main_printed("verb: none", err)) == none[0][2]


# ---------- TF19-12: the pages ----------


def test_tf19_12_the_pages_as_tf18_built_them(tmp_path: Path) -> None:
    got = pages_pins(make_world(tmp_path))
    assert got == PINNED["pages"]
