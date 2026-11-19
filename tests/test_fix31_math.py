"""The math lane (FIX31-M): the statistics of a pair that never failed, over many designs.

- FIX31-M1: the range the package gives at zero failures is the closed form of the score
  interval, on every design of 1 to 12 inputs by 1 to 40 tries and on 300 seeded designs of
  unequal tries; and on a sample of them it is the interval found from the score with
  numerically constrained rates.
- FIX31-M2: what the range's high end leaves out, exactly. With equal tries of both versions
  and three inputs or more, a new version failing that share of tries on every input gives the
  clean run seen less than 2.5% of the time, on every such design; on one or two inputs the
  figure is above 2.5% and at most 11.6% (one input, one try each).
- FIX31-M3: on unequal tries the same figure against the least favourable spread of failures
  across inputs is larger: recorded here at its size, not gated. Where the
  tries differ only a little it stays near 2.5%.
- FIX31-M4: the tries and the inputs the guidance names are the smallest that bring the range
  inside the size asked, against a count upward from one.
- FIX31-M5: the rise limit, put to the exact test by full enumeration, is caught at least four
  times in five.
- FIX31-M6: the package's least favourable miss is the
  tests' own, and the range at zero is labelled rough exactly on fewer than three inputs or,
  from three inputs up, where that miss is above 5%.
- FIX31-M7: the simulation the 5% bar was set against, in terms of how unequal the tries are:
  6,000 seeded designs in four regimes. No design whose unequalness is at or under 1.35 misses
  above 5%; nearly every design above 2 does.
"""

from __future__ import annotations

import numpy as np
import pytest

from fix31_support import (
    MISS_BAR, clean, clean_chance, clean_inputs_needed, clean_miss, clean_range,
    clean_repeats_needed, exact_power_of_a_rise, limit, score_range, unequalness,
    worst_clean_chance,
)

pytestmark = pytest.mark.math


def _counts(design: list[tuple[int, int]]) -> list[object]:
    from poisson_trace.paired import Counts

    return [Counts(f"h{k}", 0, a, 0, b) for k, (a, b) in enumerate(design)]


def _seeded(n: int = 300) -> list[list[tuple[int, int]]]:
    rng = np.random.default_rng(31)
    return [[(int(rng.integers(1, 30)), int(rng.integers(1, 30))) for _ in range(int(rng.integers(1, 25)))]
            for _ in range(n)]


def test_fix31_m1_the_range_is_the_closed_form_on_every_equal_design() -> None:
    from poisson_trace import paired

    for inputs in range(1, 13):
        for tries in range(1, 41):
            design = [(tries, tries)] * inputs
            d, variance, lo, hi = paired.difference(_counts(design))  # type: ignore[arg-type]
            assert d == 0.0 and variance == 0.0
            assert (lo, hi) == pytest.approx(clean_range(design), abs=1e-9), design[:1]
            assert lo is not None and hi is not None and -1.0 < lo < 0.0 < hi < 1.0


def test_fix31_m1_the_range_is_the_closed_form_on_unequal_designs() -> None:
    from poisson_trace import paired

    for k, design in enumerate(_seeded()):
        for alpha in (0.05, 0.01):
            _, _, lo, hi = paired.difference(_counts(design), alpha=alpha)  # type: ignore[arg-type]
            assert (lo, hi) == pytest.approx(clean_range(design, alpha), abs=1e-9), design
        if k % 10 == 0:
            tab = [(0, a, 0, b) for a, b in design]
            _, _, lo, hi = paired.difference(_counts(design))  # type: ignore[arg-type]
            assert (lo, hi) == pytest.approx(score_range(tab), abs=1e-6), design


def test_fix31_m2_three_inputs_or_more_at_equal_tries_miss_under_one_in_forty() -> None:
    worst = 0.0
    for inputs in range(3, 41):
        for tries in range(1, 61):
            _, hi = clean_range([(tries, tries)] * inputs)
            worst = max(worst, clean_chance(inputs * tries, hi))
    assert 0.024 < worst < 0.025


def test_fix31_m2_one_or_two_inputs_miss_more_and_at_most_this() -> None:
    by_inputs = {}
    for inputs in (1, 2):
        by_inputs[inputs] = max(clean_chance(inputs * tries, clean_range([(tries, tries)] * inputs)[1])
                                for tries in range(1, 61))
    assert by_inputs[1] == pytest.approx(0.11517, abs=1e-5)  # one input, one try of each
    assert by_inputs[2] == pytest.approx(0.04266, abs=1e-5)  # two inputs, one try of each
    # where the range can read *no significant difference* for a size asked of 20 points or less
    small = [clean_chance(inputs * tries, hi) for inputs in (1, 2) for tries in range(1, 61)
             if (hi := clean_range([(tries, tries)] * inputs)[1]) <= 0.2]
    assert max(small) < 0.029


def test_fix31_m3_equal_tries_have_no_worse_spread_than_the_even_one() -> None:
    """With equal tries of both versions on every input, however many, the least favourable
    spread of the new version's failures is the even one: the worst case is the plain case."""
    rng = np.random.default_rng(7)
    for _ in range(200):
        design = [(n, n) for n in rng.integers(1, 20, size=int(rng.integers(3, 15))).tolist()]
        _, hi = clean_range(design)
        assert worst_clean_chance(design, hi) == pytest.approx(
            clean_chance(sum(n for n, _ in design), hi), rel=1e-6)
        assert worst_clean_chance(design, hi) < 0.025


def test_fix31_m3_unequal_tries_can_miss_far_more_against_the_least_favourable_spread() -> None:
    """The recorded limit of the range at zero (and of any range for the Mantel-Haenszel
    difference): where one input holds many old tries and few new ones, a new version that
    fails on that input alone moves the weighted difference past the high end while a clean
    run stays likely."""
    lopsided = [(6, 22), (4, 13), (16, 2), (12, 29), (6, 27), (1, 19), (9, 9), (3, 30), (5, 25), (7, 21), (2, 28)]
    _, hi = clean_range(lopsided)
    assert worst_clean_chance(lopsided, hi) > 0.10
    # against failures spread evenly it is ordinary
    assert clean_chance(sum(b for _, b in lopsided), hi) < 0.025
    one = [(12, 1)]
    assert worst_clean_chance(one, clean_range(one)[1]) == pytest.approx(0.1937, abs=1e-3)
    # 300 seeded designs, each version's tries on each input anywhere from 1 to 29
    found = sorted(worst_clean_chance(d, clean_range(d)[1]) for d in _seeded())
    assert found[len(found) // 2] == pytest.approx(0.0603, abs=1e-3)
    assert found[-1] == pytest.approx(0.1947, abs=1e-3)


def test_fix31_m3_a_few_tries_short_miss_little() -> None:
    """Tries that differ only a little, as when a few have no outcome: 2,000 seeded designs of 3
    to 39 inputs by 2 to 19 tries, 15% of the cells short by up to a third. Against the least
    favourable spread the miss has a median of 2.1% and is at most 3.3%."""
    rng = np.random.default_rng(3)
    found = []
    for _ in range(2000):
        inputs, tries = int(rng.integers(3, 40)), int(rng.integers(2, 20))
        design = []
        for _ in range(inputs):
            a = tries - int(rng.random() < 0.15) * int(rng.integers(1, max(2, tries // 3 + 1)))
            b = tries - int(rng.random() < 0.15) * int(rng.integers(1, max(2, tries // 3 + 1)))
            design.append((max(1, a), max(1, b)))
        found.append(worst_clean_chance(design, clean_range(design)[1]))
    found.sort()
    assert found[1000] == pytest.approx(0.0214, abs=1e-3)
    assert found[1900] == pytest.approx(0.0279, abs=1e-3)
    assert found[-1] == pytest.approx(0.0328, abs=1e-3)


def test_fix31_m4_the_guidance_is_the_smallest_that_reaches() -> None:
    from poisson_trace import paired

    for inputs in (1, 2, 3, 6, 12, 40):
        for tries in (1, 2, 5, 9):
            for ceiling in (0.02, 0.1, 0.2, 0.35, 0.6):
                design = [(tries, tries)] * inputs
                counts = _counts(design)
                assert paired.clean_repeats_needed(counts, ceiling) == clean_repeats_needed(inputs, ceiling)  # type: ignore[attr-defined]
                assert paired.clean_inputs_needed(counts, ceiling) == clean_inputs_needed(design, ceiling)  # type: ignore[attr-defined]
    for design in _seeded(40):
        counts = _counts(design)
        for ceiling in (0.05, 0.2):
            assert paired.clean_repeats_needed(counts, ceiling) == clean_repeats_needed(len(design), ceiling)  # type: ignore[attr-defined]
            assert paired.clean_inputs_needed(counts, ceiling) == clean_inputs_needed(design, ceiling)  # type: ignore[attr-defined]


@pytest.mark.parametrize(("inputs", "tries"), [(2, 8), (3, 4), (3, 8), (4, 3), (5, 5), (6, 5), (8, 3), (10, 2), (12, 2)])
def test_fix31_m5_the_rise_limit_is_caught_four_times_in_five(inputs: int, tries: int) -> None:
    from poisson_trace import paired

    rise = limit(clean(inputs, tries), "rise")
    assert rise is not None
    assert paired.detection_limit(_counts([(tries, tries)] * inputs), direction="rise") == pytest.approx(rise, abs=1e-9)  # type: ignore[arg-type]
    assert exact_power_of_a_rise([(tries, tries)] * inputs, rise) >= 0.8


def _regimes(n: int, seed: int) -> list[tuple[int, list[tuple[int, int]]]]:
    """Seeded designs of 3 to 40 inputs in four regimes: equal tries; a fifth of the cells short
    by up to half; every cell between half and all of the tries; every cell anywhere from 1 to
    30."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        inputs, tries, regime = int(rng.integers(3, 41)), int(rng.integers(1, 31)), int(rng.integers(0, 4))
        design = []
        for _ in range(inputs):
            if regime == 0:
                a = b = tries
            elif regime == 1:
                a = max(1, tries - int(rng.random() < 0.2) * int(rng.integers(1, max(2, tries // 2 + 1))))
                b = max(1, tries - int(rng.random() < 0.2) * int(rng.integers(1, max(2, tries // 2 + 1))))
            elif regime == 2:
                a, b = (int(rng.integers(max(1, tries // 2), tries + 1)) for _ in range(2))
            else:
                a, b = int(rng.integers(1, 31)), int(rng.integers(1, 31))
            design.append((a, b))
        out.append((regime, design))
    return out


def test_fix31_m6_the_label_is_fewer_than_three_inputs_or_a_miss_above_the_bar() -> None:
    from poisson_trace import paired

    designs = [d for _, d in _regimes(1500, 6)] + [[(n, n)] * k for k in (1, 2) for n in (1, 5, 30)]
    designs += [[(7, 3)] + [(3, 7)] * 4, [(8, 3)] + [(3, 8)] * 4, [(12, 1), (1, 12)]]
    labelled = 0
    for design in designs:
        counts = _counts(design)
        want = clean_miss(design)
        assert paired.clean_miss(counts) == pytest.approx(want, abs=1e-9), design  # type: ignore[attr-defined]
        why = paired.rough(counts, informative=0, disagree=False)  # type: ignore[arg-type]
        expected = []
        if len(design) < 3:
            expected.append("fewer than 3 inputs")
        elif abs(want - MISS_BAR) > 1e-6 and want > MISS_BAR:
            expected.append("unequal tries")
        if abs(want - MISS_BAR) > 1e-6:
            assert list(why) == expected, (design, want)
        labelled += bool(why)
    assert 0 < labelled < len(designs)


def test_fix31_m7_the_bar_in_terms_of_unequal_tries() -> None:
    found = [(regime, unequalness(d), clean_miss(d)) for regime, d in _regimes(6000, 314)]
    over = [u for _, u, miss in found if miss > MISS_BAR]
    assert min(over) > 1.35
    assert max(miss for _, u, miss in found if u <= 1.35) < MISS_BAR
    high = [miss > MISS_BAR for _, u, miss in found if u > 2.0]
    assert sum(high) / len(high) > 0.95
    # by regime: equal tries and a few short never cross; anything from 1 to 30 nearly always
    share = {r: (sum(m > MISS_BAR for g, _, m in found if g == r) / sum(g == r for g, _, _ in found)) for r in range(4)}
    assert share[0] == 0.0 and share[1] < 0.005 and share[2] < 0.02 and share[3] > 0.9
