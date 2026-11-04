"""HY1 to HY11: the properties of spec section 17.5 that no test held as a property before
(test standard pass, yes/no 9, ruled yes 2026-10-29), for the statistics compare, where,
fix-check and the continuous measures use.

Each property is one body run twice: a fast test in the pull-request lane (a fixed seed through
``derandomize`` and a bounded example count) and a wide twin of the same body in the slow lane and the math lane (HY2).
Already held elsewhere, and not repeated here: the stratified test equals the unstratified on one
input (TR19, TR20); Aalen-Johansen's ends sum to one minus Kaplan-Meier (TR15); the per-input
limit does not grow with tries (SF2); fix-check's exact p is unchanged by swapping (TR47).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from poisson_trace.paired import Counts, by_input, detection_limit, difference, flags, paired_test
from poisson_trace.stats.continuous import (
    FLIPS, Try, Version, compare, hl_range, hodges_lehmann, mde, p_floor, signflip_p, t_range,
)
from poisson_trace.survival import (
    CAPPED, DIED, FINISHED, TIMED_OUT, _band, competing, competing_band, difference_band,
    expected_information, fit_cells, information_limit, kaplan_meier, logrank_stratified, one_step,
)

_COMMON: dict[str, Any] = dict(deadline=None, derandomize=True, database=None,
                               suppress_health_check=[HealthCheck.too_slow])
FAST = settings(max_examples=40, **_COMMON)
WIDE = settings(max_examples=500, **_COMMON)
EPS = 1e-9


def twin(*strategies: Any) -> Callable[[Callable[..., None]], tuple[Any, Any]]:
    """The property as two tests: the fast one for every pull request, the wide one in the slow
    lane and the math lane (yes/no HY2, ruled yes 2026-11-04)."""
    def make(body: Callable[..., None]) -> tuple[Any, Any]:
        fast = FAST(given(*strategies)(body))
        wide = pytest.mark.math(pytest.mark.slow(WIDE(given(*strategies)(body))))
        return fast, wide
    return make


# ---------- strategies ----------

CELLS = ["a", "b", "c"]
CAUSES = ["llm", "tool"]

arm = st.lists(st.tuples(st.sampled_from(CELLS), st.integers(1, 20), st.booleans()),
               min_size=1, max_size=30)


@st.composite
def samples(draw):  # type: ignore[no-untyped-def]
    n = draw(st.integers(1, 40))
    index = draw(st.lists(st.integers(1, 30), min_size=n, max_size=n))
    died = draw(st.lists(st.booleans(), min_size=n, max_size=n))
    return np.array(index, dtype=np.int64), np.array(died, dtype=bool)


@st.composite
def placed(draw, min_size: int = 1, max_size: int = 30):  # type: ignore[no-untyped-def]
    """Tries as ``where`` places them: input, step, how it ended, the kind it failed at."""
    n = draw(st.integers(min_size, max_size))
    out = []
    for _ in range(n):
        end = draw(st.sampled_from([DIED, DIED, FINISHED, TIMED_OUT, CAPPED]))
        cause = draw(st.sampled_from(CAUSES)) if end == DIED else ""
        out.append((draw(st.sampled_from(CELLS)), draw(st.integers(1, 15)), end, cause))
    return out


@st.composite
def tables(draw, max_inputs: int = 6, max_runs: int = 5):  # type: ignore[no-untyped-def]
    k = draw(st.integers(1, max_inputs))
    out = []
    for i in range(k):
        na, nb = draw(st.integers(1, max_runs)), draw(st.integers(1, max_runs))
        out.append(Counts(f"h{i}", draw(st.integers(0, na)), na, draw(st.integers(0, nb)), nb))
    return out


def swapped(counts: list[Counts]) -> list[Counts]:
    return [Counts(c.config_hash, c.failed_new, c.runs_new, c.failed_old, c.runs_old) for c in counts]


def twice_the_inputs(counts: list[Counts]) -> list[Counts]:
    return [*counts, *(Counts(c.config_hash + "'", c.failed_old, c.runs_old, c.failed_new, c.runs_new)
                       for c in counts)]


def twice_the_tries(counts: list[Counts]) -> list[Counts]:
    return [Counts(c.config_hash, 2 * c.failed_old, 2 * c.runs_old, 2 * c.failed_new, 2 * c.runs_new)
            for c in counts]


differences = st.lists(
    st.one_of(st.integers(-50, 50).map(float),
              st.floats(-1e6, 1e6, allow_nan=False, allow_infinity=False)),
    min_size=2, max_size=40)


def width(lo: float, hi: float) -> float:
    return hi - lo


# ---------- HY1: a survival curve never rises and stays between 0 and 1 (Kaplan-Meier) ----------


def _hy1(sample) -> None:  # type: ignore[no-untyped-def]
    km = kaplan_meier(*sample)
    assert np.all((km.survival >= 0.0) & (km.survival <= 1.0))
    assert np.all(np.diff(km.survival) <= 0.0)
    assert np.all(km.var >= 0.0)
    for s, v in zip(km.survival, km.var):
        lo, hi = _band(float(s), float(v))
        assert 0.0 <= lo <= s <= hi <= 1.0


test_hy1_kaplan_meier_never_rises_and_holds_its_band, test_hy1_wide = twin(samples())(_hy1)


# ---------- HY2: where's curve never rises, and its competing ends never sum above 1 ----------


def _hy2(rows) -> None:  # type: ignore[no-untyped-def]
    aj = competing(rows, CAUSES)
    for curve in (aj.not_failed, aj.share):
        assert np.all((curve >= -EPS) & (curve <= 1.0 + EPS))
        assert np.all(np.diff(curve) <= EPS)
    shares = aj.at(list(range(0, 17)))
    assert np.all((shares >= -EPS) & (shares <= 1.0 + EPS)) and np.all(np.diff(shares) <= EPS)
    for k in CAUSES:
        assert np.all(np.diff(aj.incidence[k]) >= -EPS)
        assert -EPS <= aj.final[k] <= 1.0 + EPS
    assert -EPS <= aj.timed_out <= 1.0 + EPS
    assert sum(aj.final.values()) + aj.timed_out <= 1.0 + EPS
    np.testing.assert_allclose(1.0 - aj.share, sum(aj.incidence[k] for k in CAUSES), atol=1e-9)


test_hy2_where_never_rises_and_its_ends_never_sum_above_one, test_hy2_wide = twin(placed())(_hy2)


# ---------- HY3: compare's hazard ratio inverts on a swap; its p is in [0, 1] and symmetric ----------


def _hy3(a, b) -> None:  # type: ignore[no-untyped-def]
    ab, ba = logrank_stratified(a, b), logrank_stratified(b, a)
    for lr in (ab, ba):
        assert 0.0 <= lr.p <= 1.0
    assert ba.p == pytest.approx(ab.p, abs=1e-12)
    assert ba.statistic == pytest.approx(ab.statistic, rel=1e-9, abs=1e-12)
    assert ba.variance == pytest.approx(ab.variance, rel=1e-12, abs=1e-12)
    one, other = one_step(ab), one_step(ba)
    assert (one is None) == (other is None)
    if one is not None and other is not None:
        hr, lo, hi = one
        assert lo <= hr <= hi
        assert other[0] == pytest.approx(1.0 / hr, rel=1e-9)
        assert other[1] == pytest.approx(1.0 / hi, rel=1e-9)
        assert other[2] == pytest.approx(1.0 / lo, rel=1e-9)


test_hy3_the_hazard_ratio_inverts_and_p_is_symmetric, test_hy3_wide = twin(arm, arm)(_hy3)


# ---------- HY4: compare's limit does not grow, nor its range narrow, as tries grow ----------


def _hy4(a, b) -> None:  # type: ignore[no-untyped-def]
    base, more = logrank_stratified(a, b), logrank_stratified(a + a, b + b)
    assert more.variance >= base.variance - EPS
    lim, lim_more = information_limit(base.variance), information_limit(more.variance)
    if lim is not None:
        assert lim_more is not None and lim_more <= lim * (1 + EPS)
        r_base, r_more = one_step(base), one_step(more)
        assert r_base is not None and r_more is not None
        assert math.log(r_more[2] / r_more[1]) <= math.log(r_base[2] / r_base[1]) + EPS
    fit = fit_cells([*a, *b])
    info = [expected_information(fit, r) for r in range(1, 7)]
    assert all(y >= x - EPS * max(1.0, x) for x, y in zip(info, info[1:]))
    limits = [information_limit(v) for v in info]
    for x, y in zip(limits, limits[1:]):
        if x is not None:
            assert y is not None and y <= x * (1 + EPS)


test_hy4_compares_limit_does_not_grow_as_tries_grow, test_hy4_wide = twin(arm, arm)(_hy4)


# ---------- HY5: the resampled bands hold their own estimate ----------


def _hy5(a, b) -> None:  # type: ignore[no-untyped-def]
    at = [1, 3, 6, 10, 15]
    aj = competing(a, CAUSES)
    band = competing_band(a, CAUSES, at, b=200, seed=0)
    lo, hi = band.curve
    assert np.all(lo <= aj.share + EPS) and np.all(aj.share <= hi + EPS)
    lo, hi = band.at
    assert np.all(lo <= aj.at(at) + EPS) and np.all(aj.at(at) <= hi + EPS)
    for k in CAUSES:
        assert band.final[k][0] - EPS <= aj.final[k] <= band.final[k][1] + EPS
    estimate = competing(b, CAUSES).at(at) - aj.at(at)
    lo, hi = difference_band(a, b, CAUSES, at, draws=200, seed=0)
    assert np.all(lo <= estimate + EPS) and np.all(estimate <= hi + EPS)


test_hy5_the_resampled_bands_hold_their_estimate, test_hy5_wide = twin(placed(), placed())(_hy5)


# ---------- HY6: every p of fix-check's tests is in [0, 1] and unchanged by a swap ----------


def _hy6(counts) -> None:  # type: ignore[no-untyped-def]
    other = swapped(counts)
    p, p_swap = paired_test(counts).p, paired_test(other).p
    assert 0.0 <= p <= 1.0 and 0.0 <= p_swap <= 1.0
    q, _, _ = by_input(counts, draws=2_000)
    q_swap, _, _ = by_input(other, draws=2_000)
    assert 0.0 <= q <= 1.0
    assert q_swap == pytest.approx(q, abs=1e-12)
    for f, g in zip(flags(counts), flags(other), strict=True):
        assert 0.0 <= f.p <= 1.0 and 0.0 <= f.q <= 1.0
        assert g.p == pytest.approx(f.p, abs=1e-12)
        assert g.q == pytest.approx(f.q, abs=1e-12)


test_hy6_fix_checks_p_values_are_in_range_and_symmetric, test_hy6_wide = twin(tables())(_hy6)


# ---------- HY7: fix-check's range holds its estimate and does not narrow as tries fall ----------


def _hy7(counts) -> None:  # type: ignore[no-untyped-def]
    d, variance, lo, hi = difference(counts)
    if lo is None or hi is None:
        return
    assert lo - EPS <= d <= hi + EPS
    for more in (twice_the_inputs(counts), twice_the_tries(counts)):
        _, _, lo2, hi2 = difference(more)
        assert lo2 is not None and hi2 is not None
        assert width(lo2, hi2) <= width(lo, hi) + EPS


test_hy7_fix_checks_range_holds_its_estimate_and_narrows_with_tries, test_hy7_wide = twin(tables())(_hy7)


# ---------- HY8: fix-check's detection limit does not grow as tries grow ----------


def _hy8(counts, direction) -> None:  # type: ignore[no-untyped-def]
    base = detection_limit(counts, direction=direction)
    if base is None:
        return
    for more in (detection_limit(twice_the_inputs(counts), direction=direction),
                 detection_limit(counts, direction=direction, repeats=2 * max(
                     max(c.runs_old, c.runs_new) for c in counts))):
        assert more is not None and more <= base + EPS


test_hy8_fix_checks_detection_limit_does_not_grow_as_tries_grow, test_hy8_wide = twin(
    tables(max_inputs=5, max_runs=4), st.sampled_from(["drop", "rise"]))(_hy8)


# ---------- HY9: the continuous p is never 0, in (0, 1], and unchanged by a swap ----------


def _hy9(d, seed) -> None:  # type: ignore[no-untyped-def]
    p = signflip_p(d, seed)
    k = sum(1 for x in d if x != 0.0)
    assert 0.0 < p <= 1.0
    assert p >= (p_floor(k) if k <= 20 else 1.0 / (1 + FLIPS)) * (1 - 1e-12)
    assert signflip_p([-x for x in d], seed) == pytest.approx(p, abs=1e-12)


test_hy9_the_continuous_p_is_never_zero, test_hy9_wide = twin(
    st.lists(st.one_of(st.integers(-5, 5).map(float), st.floats(-1e6, 1e6)), min_size=0, max_size=24),
    st.integers(0, 2**32 - 1))(_hy9)


# ---------- HY10: a continuous range holds its estimate, and does not narrow as cases fall ----------


def _hy10(d) -> None:  # type: ignore[no-untyped-def]
    mean = float(np.mean(d))
    lo, hi = t_range(d)
    assert lo - EPS * (1 + abs(mean)) <= mean <= hi + EPS * (1 + abs(mean))
    hl = hodges_lehmann(d)
    hl_lo, hl_hi = hl_range(d)
    assert hl_lo <= hl <= hl_hi
    more = d + d
    slack = EPS * (1 + max(abs(x) for x in d))
    assert width(*t_range(more)) <= width(lo, hi) + slack
    assert width(*hl_range(more)) <= width(hl_lo, hl_hi) + slack
    assert mde(more) <= mde(d) + slack


test_hy10_the_continuous_ranges_hold_their_estimate, test_hy10_wide = twin(differences)(_hy10)


# ---------- HY11: compare's continuous reading is deterministic and holds its own estimates ----------

ENDINGS = [None, None, None, "timeout", "crash", "wrong_answer"]
# Positive amounts start at a nanosecond (or a billionth of a dollar): below that the relative
# change can overflow and compare raises, which is finding HY1, held by the example test below.
seconds = st.one_of(st.just(0.0), st.floats(1e-9, 600))
dollars = st.one_of(st.just(0.0), st.floats(1e-9, 2))


@st.composite
def versions(draw, max_cases: int = 14):  # type: ignore[no-untyped-def]
    k = draw(st.integers(0, max_cases))
    out = []
    for label in ("old", "new"):
        cases: dict[str, list[Try]] = {}
        for i in range(k):
            tries = []
            n = draw(st.integers(1, 3))
            ordered = draw(st.booleans())
            for r in range(n):
                values = {
                    "wall_time_s": draw(st.one_of(st.none(), seconds)),
                    "output_chars": draw(st.one_of(st.none(), st.integers(0, 4000))),
                    "input_tokens": draw(st.one_of(st.none(), st.integers(0, 50).map(lambda x: 100 + x))),
                    "cost_usd": draw(st.one_of(st.none(), dollars)),
                }
                tries.append(Try(values=values, ending=draw(st.sampled_from(ENDINGS)),
                                 signals=draw(st.sampled_from([(), (), ("gave_up",)])),
                                 repeat=r if ordered else None))
            cases[f"c{i}"] = tries
        out.append(Version(name=f"run-{label}", cases=cases, label=label))
    return out[0], out[1], draw(st.randoms(use_true_random=False))


def _hy11(v) -> None:  # type: ignore[no-untyped-def]
    a, b, rnd = v
    one, two = compare(a, b).to_dict(), compare(a, b).to_dict()
    assert one == two
    keys = list(b.cases)
    rnd.shuffle(keys)
    shuffled = Version(name=b.name, cases={k: b.cases[k] for k in keys}, label=b.label)
    assert compare(a, shuffled).to_dict() == one
    for m in compare(a, b).measures.values():
        if m.p_value is not None:
            assert 0.0 < m.p_value <= 1.0
        if m.lo is not None and m.hi is not None and m.change is not None:
            assert m.lo - EPS * (1 + abs(m.change)) <= m.change <= m.hi + EPS * (1 + abs(m.change))
        if m.hl is not None and m.hl_lo is not None and m.hl_hi is not None:
            assert m.hl_lo <= m.hl <= m.hl_hi


test_hy11_the_continuous_reading_is_deterministic_and_order_free, test_hy11_wide = twin(versions())(_hy11)


def _one_case(cost_old: float, cost_new: float) -> tuple[Version, Version]:
    def version(label: str, cost: float) -> Version:
        values = {"wall_time_s": None, "output_chars": None, "input_tokens": None, "cost_usd": cost}
        return Version(name=f"run-{label}", cases={"c0": [Try(values=values)]}, label=label)
    return version("old", cost_old), version("new", cost_new)


@pytest.mark.xfail(raises=OverflowError, strict=True,
                   reason="finding HY1: compare raises when the old mean is so near zero that the "
                          "relative change overflows to infinity")
def test_hy11_finding_hy1_a_near_zero_old_mean_does_not_crash_compare() -> None:
    # HY11's wide run, shrunk by Hypothesis: one case, an old cost of 2.2e-309 dollars (a
    # subnormal float), a new cost of 1 dollar. The relative change 1 / 2.2e-309 is infinite and
    # the summary line's number formatting raises OverflowError.
    a, b = _one_case(2.225073858507203e-309, 1.0)
    m = compare(a, b).measures["cost_usd"]
    assert m.relative is None or math.isfinite(m.relative)
