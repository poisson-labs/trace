"""The agent's own tests, one per case and repeat. ``pytest --junitxml=reports/junit-new.xml``
writes the report the team keeps; the earlier report, ``reports/junit-old.xml``, was written
the same way before the parser fix. A test passes when its case resolved."""

from __future__ import annotations

import pytest

from agent import run_case

CASES = ("refund-late", "address-change")


@pytest.mark.parametrize("case_id", CASES)
def test_solves(case_id: str) -> None:
    assert run_case(case_id) == "resolved"
