"""IC1: a score becomes an outcome at a declared cut, with its side, in two words."""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from poisson_trace.ingest.cut import MET, MISSED, Cut

FINITE = st.floats(allow_nan=False, allow_infinity=False)
SIDES = ("below", "above")


def test_ic1_below_misses_under_the_cut_and_meets_it_at_and_over() -> None:
    c = Cut(0.7, "below")
    assert (c.cut, c.side) == (0.7, "below")
    assert [c.missed(s) for s in (0.69, 0.7, 0.71)] == [True, False, False]
    assert [c.outcome(s) for s in (0.69, 0.7, 0.71)] == ["missed", "met", "met"]


def test_ic1_above_misses_over_the_cut_and_meets_it_at_and_under() -> None:
    c = Cut(0.3, "above")
    assert (c.cut, c.side) == (0.3, "above")
    assert [c.missed(s) for s in (0.29, 0.3, 0.31)] == [False, False, True]
    assert [c.outcome(s) for s in (0.29, 0.3, 0.31)] == ["met", "met", "missed"]


@settings(max_examples=400, deadline=None)
@given(FINITE, FINITE, st.sampled_from(SIDES))
def test_ic1_missed_is_the_strict_comparison_on_its_side(cut: float, score: float, side: str) -> None:
    c = Cut(cut, side)  # type: ignore[arg-type]
    expected = score < cut if side == "below" else score > cut
    got = c.missed(score)
    assert isinstance(got, bool) and got == expected
    assert c.outcome(score) == ("missed" if expected else "met")


@settings(max_examples=200, deadline=None)
@given(FINITE, st.sampled_from(SIDES))
def test_ic1_a_score_equal_to_the_cut_met_it_on_either_side(cut: float, side: str) -> None:
    c = Cut(cut, side)  # type: ignore[arg-type]
    assert c.missed(cut) is False
    assert c.outcome(cut) == "met"


def test_ic1_the_two_words_are_met_and_missed_and_nothing_else() -> None:
    assert (MET, MISSED) == ("met", "missed")
    seen = {Cut(0.5, side).outcome(s) for side in SIDES for s in (-1.0, 0.0, 0.5, 1.0, 2.0)}  # type: ignore[arg-type]
    assert seen == {MET, MISSED}


@pytest.mark.parametrize("side", ["under", "over", "Below", "ABOVE", "", None, "<"])
def test_ic1_a_side_other_than_the_two_raises(side: object) -> None:
    with pytest.raises(ValueError):
        Cut(0.5, side).missed(0.4)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Cut(0.5, side).outcome(0.6)  # type: ignore[arg-type]


@pytest.mark.parametrize("side", SIDES)
def test_ic1_a_nan_cut_raises(side: str) -> None:
    with pytest.raises(ValueError):
        Cut(math.nan, side).missed(0.4)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Cut(math.nan, side).outcome(0.4)  # type: ignore[arg-type]


@pytest.mark.parametrize("side", SIDES)
def test_ic1_a_nan_score_raises(side: str) -> None:
    c = Cut(0.5, side)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        c.missed(math.nan)
    with pytest.raises(ValueError):
        c.outcome(math.nan)
