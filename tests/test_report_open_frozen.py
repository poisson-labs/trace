"""RO-8: the report open fix's tests are frozen. Green by construction: the digest of its test
file as it was pushed on ``trace-report-open`` at 06d4142, as TF18-24, TF13-37 and TF6-36 hold
theirs. RO-Y4 (ruled no by Taylor 2026-11-08) asked for this guard. A ruled change to the file
moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "test_report_open.py": "bef4edf86e7a5b6df502ecf8d0d897cd667fecb97f938a195858f5b9f706153e",
}


def test_ro_8_no_frozen_report_open_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN


def test_ro_8_every_file_of_the_fix_is_frozen() -> None:
    mine = {p.name for p in TESTS.glob("test_report_open*.py")} - {"test_report_open_frozen.py"}
    assert mine == set(FROZEN)
