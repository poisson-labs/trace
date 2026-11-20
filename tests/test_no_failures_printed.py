"""FIX31-P: what fix-check prints for the pairs that never failed, byte for byte.

``tests/fixtures/no-failures/printed/`` holds the stdout of nine invocations as fix-check
prints them (``make_printed.py`` beside it): Break's case on the committed fixture as Break
asks it and in plain, the candidate with the planted weakness beside it, a pair too small for
the size asked (three inputs by four tries), a pair of two inputs, whose range is rough,
and the pair whose only failure is on an input not compared. Their numbers are
checked independently in ``test_no_failures.py``; this test keeps every other byte, so
that a change to the wording is made on purpose and seen whole. The files carry the version of
Prove that Trace pins, so a move of that pin moves them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from no_failures_support import PRINTED, printed

NAMES = ("break-case.json", "break-case.md", "break-case-weak-candidate.json", "three-by-four.md",
         "three-by-four.json", "two-by-five.md", "two-by-five.json", "stray.md", "stray.json")


@pytest.fixture(scope="module")
def ran(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    return printed(tmp_path_factory.mktemp("printed").resolve())


def test_fix31_p_the_files_are_the_nine() -> None:
    assert sorted(p.name for p in PRINTED.iterdir()) == sorted(NAMES)


@pytest.mark.parametrize("name", NAMES)
def test_fix31_p_printed_byte_for_byte(ran: dict[str, str], name: str) -> None:
    assert ran[name] == (PRINTED / name).read_text(encoding="utf-8")


def test_fix31_p_no_path_of_a_machine_is_in_the_record() -> None:
    for name in NAMES:
        text = (PRINTED / name).read_text(encoding="utf-8")
        assert "/Users/" not in text and "/tmp/" not in text and "/var/" not in text, name
        assert Path(PRINTED / name).stat().st_size > 0
