"""PACE-20: the pacing pair's tests are frozen. Green by construction: the digests of its files
as its Session A froze them on ``trace-pacing-a``, as RUNREC-50 holds the run record's. A ruled
change to one of them moves its digest here in the same commit, with the ruling named."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "pacing_support.py": "e36d6b5f3a8b64af5d18c1982b422b224b6cee2649bfa5f5db6781e8c9b96448",
    "test_pacing.py": "466b58f63e8c03fc29f1e26b63e7c0c9bed6a134518cc6d0b56f780bb19bf5a8",
    "pacing_pins.py": "c6357b08921fcddc320afdbf9915d63e438ed5cce4c881348b30b20076a1b50e",
    "test_pacing_unchanged.py": "2a64d89d2c2738308df50622f2fa22888b2d4acf66e49100458a66624600997b",
    "fixtures/pacing/make_main_pins.py": "388b49551914da0f9cfe584e9fcf126ede958bce1b6eca9abc1f26eb0871a8ed",
    "fixtures/pacing/main-pins.json": "63e452a2007dec2e5743b56ebd256a2ac1316af8e70b09cab87ff36c4529aa01",
}


def test_pace_20_no_frozen_pacing_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN


def test_pace_20_runrec_11_and_12_are_as_main_has_them_and_their_check_as_s_3_moved_it() -> None:
    """RUNREC-11 and RUNREC-12 are not moved by this pair (P-2): the run record's own guard
    still holds the digest main 2ff191b has for them. The check they share,
    ``runrec_support.py``, was moved by this pair (S-3: ``seconds`` reads the log's times as
    UTC), and the guard holds its new digest."""
    from test_runrec_frozen import FROZEN as RUNREC

    assert RUNREC["test_runrec_events.py"] == "24c985de9935630787e2f4780c6a8840740609c9ea68b9014a02c816cb405298"
    assert RUNREC["runrec_support.py"] == "3c0e83d480641d33a673a07d94d4d7b5c222b9413b4565739a39672fd86bc338"
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in ("test_runrec_events.py", "runrec_support.py")}
    assert got == {name: RUNREC[name] for name in got}
