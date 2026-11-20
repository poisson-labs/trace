"""This fix moves one kind of fix-check output and no other: FIX31-U.

``tests/fixtures/no-failures/main-pins.json`` holds, for every invocation of
``no_failures_support.run_corpus``, the exit code and the digests of stdout and stderr as main printed
them at ``no_failures_support.MAIN`` before any change (``make_main_pins.py`` beside it took them).
The corpus is fix-check on every kind of pair but one, a pair in which the inputs compared hold
no failed run in either version:

- seventeen synthetic pairs, each asked twice, in plain and in ``--json``: a version that never
  failed beside one that did (both ways round, on one input and on several, at equal and at
  unequal tries, to every try failing), every try failing in both, pairs that vary, a clear drop
  and a clear rise, one try per input;
- names of events no run carries, on runs that hold failures (still refused);
- the store with inputs left out for each of the four reasons, by ``--failing-from`` and by
  ``--inputs all``;
- every fix-check invocation and fix-check refusal of TF13's workspace corpus;
- the committed tau2 and HumanEval stores; two JUnit folders;
- and ``changes``, ``where`` and ``runs`` on runs that never failed, which this fix leaves as
  they are.

Green on main by construction; it is here to stay green. Sixteen pins of the synthetic pairs
move with two sentences of the report, and with nothing else: where the old version
failed no try the caveat says there is no drop to look for, and where the difference has no range
the comparison says ``no range: Sato's formula gives none on these counts (its variance is zero)``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from no_failures_support import MAIN, PINS, TABLES, run_corpus


@pytest.fixture(scope="module")
def ran(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[object]]:
    return run_corpus(tmp_path_factory.mktemp("fix31").resolve())


def pins() -> dict[str, list[object]]:
    held = json.loads(PINS.read_text(encoding="utf-8"))
    assert held["main"] == MAIN
    out: dict[str, list[object]] = held["pins"]
    return out


def test_fix31_u_the_corpus_is_the_pinned_corpus(ran: dict[str, list[object]]) -> None:
    assert list(ran) == list(pins())
    assert len(ran) == 116


def test_fix31_u_no_pinned_pair_is_one_that_never_failed() -> None:
    """The pins leave out exactly what this fix changes: every pinned table holds a failure."""
    for label, tab in TABLES.items():
        assert any(xa or xb for xa, _, xb, _ in tab), label


@pytest.mark.parametrize("label", list(pins()))
def test_fix31_u_every_other_output_is_what_main_printed(ran: dict[str, list[object]], label: str) -> None:
    assert ran[label] == pins()[label]


def test_fix31_u_the_pins_hold_refusals_and_reports() -> None:
    codes = [code for code, _, _ in pins().values()]
    assert codes.count(1) == 14 and codes.count(0) == 102


def test_fix31_u_the_generator_names_the_same_commit() -> None:
    text = (Path(__file__).parent / "fixtures" / "no-failures" / "make_main_pins.py").read_text(encoding="utf-8")
    assert "no_failures_support import MAIN, PINS, run_corpus" in text
