"""TR43 to TR53, and the function-level halves of TR55 to TR58: the statistics in
``poisson_trace.paired`` (and ``survival.deaths_needed``) against oracles written here from the
spec's section 2: full enumeration in exact fractions, the section's own formulas restated, and
Prove's private functions and scipy imported inside the tests as dev oracles."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from scipy import stats

from fixcheck_support import WORKED, counts_of, exact_p_enumerated, moves, sign_flip_enumerated
from poisson_trace.paired import (
    Counts, accepts_at, by_input, consistency, detection_limit, difference, flags, inputs_needed,
    limit_rise, paired_test, power_at, repeats_needed,
)

SETTINGS = settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@st.composite
def tables(draw, min_inputs: int = 1, max_inputs: int = 4, max_runs: int = 4):  # type: ignore[no-untyped-def]
    k = draw(st.integers(min_inputs, max_inputs))
    out = []
    for _ in range(k):
        na = draw(st.integers(1, max_runs))
        nb = draw(st.integers(1, max_runs))
        out.append((draw(st.integers(0, na)), na, draw(st.integers(0, nb)), nb))
    return out


def _cmh_parts(tab):  # type: ignore[no-untyped-def]
    e = v = w = 0.0
    for xa, na, xb, nb in tab:
        n, t = na + nb, xa + xb
        e += nb * t / n
        w += na * nb / n
        v += na * nb * t * (n - t) / (n * n * (n - 1))
    return sum(r[2] for r in tab), e, v, w


# ---------- TR43 ----------


def test_tr43_the_statistic_on_the_worked_example() -> None:
    t = paired_test(counts_of(WORKED))
    assert t.observed_new == 8
    assert t.expected_new == pytest.approx(10.5, abs=1e-6)
    assert t.variance == pytest.approx(1.678571, abs=1e-6)
    assert t.weight == pytest.approx(10.0, abs=1e-6)
    assert (t.inputs, t.informative) == (5, 4)


@SETTINGS
@given(tables(max_inputs=8, max_runs=8))
def test_tr43_observed_expected_variance_and_weight_are_the_sums(tab) -> None:  # type: ignore[no-untyped-def]
    t = paired_test(counts_of(tab))
    o, e, v, w = _cmh_parts(tab)
    assert t.observed_new == o
    assert t.expected_new == pytest.approx(e, abs=1e-9)
    assert t.variance == pytest.approx(v, abs=1e-9)
    assert t.weight == pytest.approx(w, abs=1e-9)
    assert t.inputs == len(tab)
    assert t.informative == sum(1 for xa, na, xb, nb in tab if 0 < xa + xb < na + nb)


# ---------- TR44 ----------


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(tables())
def test_tr44_the_exact_p_equals_full_enumeration(tab) -> None:  # type: ignore[no-untyped-def]
    p = paired_test(counts_of(tab)).p
    assert 0.0 <= p <= 1.0
    assert p == pytest.approx(exact_p_enumerated(tab), abs=1e-12)


def test_tr44_p_is_one_when_no_input_is_informative() -> None:
    assert paired_test(counts_of([(0, 3, 0, 2), (4, 4, 1, 1), (0, 1, 0, 5)])).p == 1.0
    assert paired_test(counts_of([(2, 2, 3, 3)])).p == 1.0


def test_tr44_the_worked_example() -> None:
    p = paired_test(counts_of(WORKED)).p
    assert p == pytest.approx(0.114869, abs=1e-6)
    assert p == pytest.approx(exact_p_enumerated(WORKED), abs=1e-12)


# ---------- TR45 ----------


@SETTINGS
@given(st.integers(1, 40).flatmap(lambda na: st.tuples(st.integers(0, na), st.just(na))),
       st.integers(1, 40).flatmap(lambda nb: st.tuples(st.integers(0, nb), st.just(nb))))
def test_tr45_one_input_is_fisher(a, b) -> None:  # type: ignore[no-untyped-def]
    from poisson_prove.diff import _fisher

    (xa, na), (xb, nb) = a, b
    p = paired_test([Counts("h", xa, na, xb, nb)]).p
    scipy_p = stats.fisher_exact([[xa, na - xa], [xb, nb - xb]], alternative="two-sided")[1]
    assert p == pytest.approx(float(scipy_p), abs=1e-12)
    assert p == pytest.approx(_fisher(xa, na, xb, nb)[1], abs=1e-12)


# ---------- TR46 ----------


@SETTINGS
@given(st.lists(st.tuples(st.booleans(), st.booleans()), min_size=1, max_size=40))
def test_tr46_one_run_per_arm_is_mcnemar(pairs) -> None:  # type: ignore[no-untyped-def]
    from poisson_prove.diff import _mcnemar

    cell_a = pd.DataFrame({"replicate_index": range(len(pairs)), "observed": [a for a, _ in pairs]})
    cell_b = pd.DataFrame({"replicate_index": range(len(pairs)), "observed": [b for _, b in pairs]})
    expected = _mcnemar(cell_a, cell_b, "pairs")[1]
    tab = [(int(a), 1, int(b), 1) for a, b in pairs]
    assert paired_test(counts_of(tab)).p == pytest.approx(expected, abs=1e-12)


# ---------- TR47 ----------


@SETTINGS
@given(tables(max_inputs=5, max_runs=5), st.integers(1, 5), st.integers(1, 5), st.booleans(), st.randoms())
def test_tr47_swap_complement_order_and_constant_inputs(tab, na, nb, all_fail, rnd) -> None:  # type: ignore[no-untyped-def]
    base = paired_test(counts_of(tab))
    d = difference(counts_of(tab))[0]
    swapped = [(xb, nb_, xa, na_) for xa, na_, xb, nb_ in tab]
    assert paired_test(counts_of(swapped)).p == pytest.approx(base.p, abs=1e-12)
    assert difference(counts_of(swapped))[0] == pytest.approx(-d, abs=1e-12)
    complement = [(na_ - xa, na_, nb_ - xb, nb_) for xa, na_, xb, nb_ in tab]
    assert paired_test(counts_of(complement)).p == pytest.approx(base.p, abs=1e-12)
    assert difference(counts_of(complement))[0] == pytest.approx(-d, abs=1e-12)
    shuffled = list(counts_of(tab))
    rnd.shuffle(shuffled)
    moved = paired_test(shuffled)
    assert moved.p == pytest.approx(base.p, abs=1e-12)
    assert moved.variance == pytest.approx(base.variance, abs=1e-12)
    assert difference(shuffled)[0] == pytest.approx(d, abs=1e-12)
    extra = (na, na, nb, nb) if all_fail else (0, na, 0, nb)
    more = paired_test(counts_of([*tab, extra]))
    assert more.p == pytest.approx(base.p, abs=1e-12)
    assert more.variance == pytest.approx(base.variance, abs=1e-12)
    assert more.observed_new - more.expected_new == pytest.approx(base.observed_new - base.expected_new, abs=1e-9)


# ---------- TR48 ----------


def _rates(rng: np.random.Generator, k: int, mean: float, kappa: float) -> np.ndarray:
    if kappa == 0:
        return np.full(k, mean)
    total = 1.0 / kappa - 1.0
    return rng.beta(mean * total, (1.0 - mean) * total, size=k)


@pytest.mark.parametrize("k,n", [(10, 3), (50, 4), (50, 1)])
def test_tr48_level_under_the_null(k: int, n: int) -> None:
    rng = np.random.default_rng(4800 + 10 * k + n)
    rejections = 0
    for _ in range(2000):
        p = _rates(rng, k, 0.75, 0.5)
        xa, xb = rng.binomial(n, p), rng.binomial(n, p)
        tab = [(int(a), n, int(b), n) for a, b in zip(xa, xb)]
        rejections += paired_test(counts_of(tab)).p < 0.05
    assert rejections / 2000 <= 0.0646, rejections / 2000


# ---------- TR49 ----------


def _sato(tab):  # type: ignore[no-untyped-def]
    w = sum(na * nb / (na + nb) for _, na, _, nb in tab)
    d = sum((xb * na - xa * nb) / (na + nb) for xa, na, xb, nb in tab) / w
    p_sum = sum((nb * nb * xa - na * na * xb + na * nb * (na - nb) / 2) / (na + nb) ** 2 for xa, na, xb, nb in tab)
    q_sum = sum((xb * (na - xa) + xa * (nb - xb)) / (2 * (na + nb)) for xa, na, xb, nb in tab)
    return d, (d * p_sum + q_sum) / w**2


def _mn_oracle(tab, alpha):  # type: ignore[no-untyped-def]
    """The stratified Miettinen-Nurminen score interval for new minus old, written here from its
    definition (Miettinen & Nurminen 1985): Mantel-Haenszel weights; each input's variance at the
    constrained maximum likelihood (found numerically, not by the closed-form cubic), times
    N / (N - 1); the interval is every difference the score test at ``alpha`` does not reject."""
    from scipy import optimize, special

    rows = [(xb, nb, xa, na) for xa, na, xb, nb in tab]  # 1 is new, 2 is old
    w = [n1 * n2 / (n1 + n2) for _, n1, _, n2 in rows]
    dhat = [x1 / n1 - x2 / n2 for x1, n1, x2, n2 in rows]
    est = sum(wi * di for wi, di in zip(w, dhat)) / sum(w)

    def constrained(x1, n1, x2, n2, delta):  # type: ignore[no-untyped-def]
        lo, hi = max(0.0, -delta), min(1.0, 1.0 - delta)

        def nll(p2: float) -> float:
            p1 = p2 + delta
            return -float(special.xlogy(x1, p1) + special.xlogy(n1 - x1, 1 - p1) + special.xlogy(x2, p2) + special.xlogy(n2 - x2, 1 - p2))

        r = optimize.minimize_scalar(nll, bounds=(lo, hi), method="bounded", options={"xatol": 1e-13})
        p2 = min([(nll(lo), lo), (nll(hi), hi), (float(r.fun), float(r.x))])[1]
        return p2 + delta, p2

    def score(delta: float) -> float:
        num = sum(wi * (di - delta) for wi, di in zip(w, dhat))
        tot = 0.0
        for wi, (x1, n1, x2, n2) in zip(w, rows):
            p1, p2 = constrained(x1, n1, x2, n2, delta)
            tot += wi * wi * (p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2) * (n1 + n2) / (n1 + n2 - 1)
        return num / math.sqrt(tot) if tot > 0 else math.copysign(math.inf, num) if num else 0.0

    z = float(stats.norm.isf(alpha / 2))
    eps = 1e-9
    lo = -1.0 if score(-1 + eps) <= z else optimize.brentq(lambda d: score(d) - z, -1 + eps, est, xtol=1e-13)
    hi = 1.0 if score(1 - eps) >= -z else optimize.brentq(lambda d: score(d) + z, est, 1 - eps, xtol=1e-13)
    return lo, hi


@SETTINGS
@given(tables(max_inputs=8, max_runs=8), st.sampled_from([0.05, 0.1, 0.01]))
def test_tr49_the_difference_is_mantel_haenszel_with_sato_variance(tab, alpha) -> None:  # type: ignore[no-untyped-def]
    """ST3 (ruled 2026-10-20): the estimate is still Mantel-Haenszel's and the JSON's variance
    still Sato's; the interval is the stratified Miettinen-Nurminen score interval, printed where
    Sato's variance is positive, as the interval was before."""
    points, var, lo, hi = difference(counts_of(tab), alpha=alpha)
    t = paired_test(counts_of(tab))
    assert points == pytest.approx((t.observed_new - t.expected_new) / t.weight, abs=1e-12)
    d, v = _sato(tab)
    assert points == pytest.approx(d, abs=1e-12)
    if v > 0:
        assert var == pytest.approx(v, abs=1e-12)
        want_lo, want_hi = _mn_oracle(tab, alpha)
        assert lo == pytest.approx(want_lo, abs=1e-6)
        assert hi == pytest.approx(want_hi, abs=1e-6)
        assert lo <= points <= hi
    else:
        assert var is None and lo is None and hi is None


@SETTINGS
@given(st.integers(1, 6), st.integers(1, 6), st.lists(st.tuples(st.integers(0, 6), st.integers(0, 6)), min_size=1, max_size=8))
def test_tr49_equal_sizes_give_the_plain_difference(na, nb, xs) -> None:  # type: ignore[no-untyped-def]
    tab = [(min(a, na), na, min(b, nb), nb) for a, b in xs]
    plain = sum(r[2] for r in tab) / (nb * len(tab)) - sum(r[0] for r in tab) / (na * len(tab))
    assert difference(counts_of(tab))[0] == pytest.approx(plain, abs=1e-12)


@SETTINGS
@given(st.integers(1, 30).flatmap(lambda na: st.tuples(st.integers(0, na), st.just(na))),
       st.integers(1, 30).flatmap(lambda nb: st.tuples(st.integers(0, nb), st.just(nb))))
def test_tr49_one_input_is_the_unpooled_variance(a, b) -> None:  # type: ignore[no-untyped-def]
    (xa, na), (xb, nb) = a, b
    pa, pb = xa / na, xb / nb
    unpooled = pa * (1 - pa) / na + pb * (1 - pb) / nb
    _, var, _, _ = difference([Counts("h", xa, na, xb, nb)])
    if unpooled > 0:
        assert var == pytest.approx(unpooled, abs=1e-12)


def test_tr49_the_worked_example_and_a_variance_that_is_not_positive() -> None:
    points, var, lo, hi = difference(counts_of(WORKED))
    assert points == pytest.approx(-0.25, abs=1e-4)
    assert var == pytest.approx(0.015625, abs=1e-4)
    # ST3 (ruled 2026-10-20): the statistics check's simlib.mn_stratified on WORKED
    assert lo == pytest.approx(-0.501442, abs=1e-4)
    assert hi == pytest.approx(0.004307, abs=1e-4)
    points, var, lo, hi = difference(counts_of([(4, 4, 0, 4)] * 3))
    assert points == pytest.approx(-1.0, abs=1e-12)
    assert var is None and lo is None and hi is None


# ---------- TR50 ----------


@SETTINGS
@given(tables(max_inputs=8, max_runs=4))
def test_tr50_the_exact_by_input_p_equals_every_sign_assignment(tab) -> None:  # type: ignore[no-untyped-def]
    p, moved, method = by_input(counts_of(tab))
    assert moved == len(moves(tab))
    assert p == pytest.approx(sign_flip_enumerated(tab), abs=1e-12)
    if moved:
        assert method == "exact"


def _moved_design(k: int) -> list[tuple[int, int, int, int]]:
    """``k`` moved inputs, alternating directions, one more up than down when ``k`` is odd."""
    return [(1, 4, 2, 4) if i % 2 == 0 else (2, 4, 1, 4) for i in range(k)] + [(3, 4, 3, 4)]


def test_tr50_fourteen_moved_inputs_are_enumerated_and_fifteen_are_drawn() -> None:
    tab14 = _moved_design(14)
    p, moved, method = by_input(counts_of(tab14))
    assert (moved, method) == (14, "exact")
    assert p == pytest.approx(sign_flip_enumerated(tab14), abs=1e-12)
    p15, moved15, method15 = by_input(counts_of(_moved_design(15)), draws=1000)
    assert (moved15, method15) == (15, "monte carlo")
    assert abs(p15 * 1001 - round(p15 * 1001)) < 1e-6 and 1 <= round(p15 * 1001) <= 1001


def test_tr50_draws_are_seeded() -> None:
    tab = [(1, 4, 2, 4)] * 12 + [(2, 4, 1, 4)] * 5  # 17 moved, by-input p near 0.14
    a = by_input(counts_of(tab), seed=0)
    b = by_input(counts_of(tab), seed=0)
    assert a == b
    c = by_input(counts_of(tab), seed=1)
    d = by_input(counts_of(tab), seed=2)
    assert len({a[0], c[0], d[0]}) > 1
    for p, _, _ in (a, c, d):
        assert abs(p * 100_001 - round(p * 100_001)) < 1e-6


def test_tr50_no_moved_input_gives_one() -> None:
    p, moved, _ = by_input(counts_of([(1, 2, 2, 4), (0, 3, 0, 1), (2, 2, 1, 1)]))
    assert (p, moved) == (1.0, 0)


# ---------- TR51 ----------


@SETTINGS
@given(tables(max_inputs=8, max_runs=8))
def test_tr51_consistency_is_the_unbiased_estimate(tab) -> None:  # type: ignore[no-untyped-def]
    t = np.array([xa + xb for xa, _, xb, _ in tab], dtype=float)
    n = np.array([na + nb for _, na, _, nb in tab], dtype=float)
    if t.sum() == 0 or t.sum() == n.sum():
        return
    p = t.sum() / n.sum()
    c = float(np.sum(t * (t - 1)) / np.sum(t * (n - 1)))
    got = consistency(counts_of(tab))
    assert got[0] == pytest.approx(p, abs=1e-12)
    assert got[1] == pytest.approx(c, abs=1e-12)
    assert got[2] == pytest.approx((c - p) / (1 - p), abs=1e-12)
    assert got[3] == pytest.approx(float(np.mean(t * (n - t) / (n * (n - 1)))), abs=1e-12)
    assert got[4] == pytest.approx(p * (1 - p), abs=1e-12)


def test_tr51_the_worked_example() -> None:
    p, c, kappa, within, pooled = consistency(counts_of(WORKED))
    assert (p, c, kappa) == (pytest.approx(0.525, abs=1e-4), pytest.approx(0.6803, abs=1e-4), pytest.approx(0.3269, abs=1e-4))
    assert within == pytest.approx(0.167857, abs=1e-4)
    assert pooled == pytest.approx(0.525 * 0.475, abs=1e-12)


# ---------- TR52 ----------


def _power_oracle(tab, r, direction, alpha):  # type: ignore[no-untyped-def]
    """Section 2.5 restated: the moments from both arms together, the reference variance and the
    spread under a proportional change, the continuity correction, one direction only."""
    z = float(stats.norm.isf(alpha / 2))
    delta = v_ref = v_one = 0.0
    for xa, na, xb, nb in tab:
        n, t = na + nb, xa + xb
        w = na * nb / n
        pbar, s, m = t / n, t * (n - t) / (n * (n - 1)), t * (t - 1) / (n * (n - 1))
        if direction == "drop":
            mean_b, second_b, cross = (1 - r) * pbar, (1 - r) ** 2 * m, (1 - r) * m
            delta += w * (pbar - mean_b)
        else:
            q, q2 = 1 - pbar, 1 - 2 * pbar + m
            mean_b = 1 - (1 - r) * q
            second_b = 1 - 2 * (1 - r) * q + (1 - r) ** 2 * q2
            cross = pbar - (1 - r) * (pbar - m)
            delta += w * (mean_b - pbar)
        s_b = mean_b - second_b
        pt = (na * pbar + nb * mean_b) / n
        pt2 = (na * na * m + nb * nb * second_b + 2 * na * nb * cross) / n**2
        v_ref += w * max(n * n * (pt - pt2) - na * s - nb * s_b, 0.0) / (n * (n - 1))
        v_one += w * w * (s / na + s_b / nb)
    if v_one <= 0:
        return 1.0 if delta - 0.5 > z * math.sqrt(v_ref) else 0.0
    return float(stats.norm.sf((z * math.sqrt(v_ref) + 0.5 - delta) / math.sqrt(v_one)))


def test_tr52_the_worked_example() -> None:
    c = counts_of(WORKED)
    assert power_at(c, 0.5, direction="drop") == pytest.approx(0.3177, abs=1e-4)
    assert detection_limit(c, direction="drop") == pytest.approx(0.4192, abs=1e-4)
    assert detection_limit(c, direction="rise") == pytest.approx(0.4034, abs=1e-4)
    six = counts_of(WORKED * 6)
    assert detection_limit(six, direction="drop") == pytest.approx(0.1647, abs=1e-4)
    assert detection_limit(six, direction="rise") == pytest.approx(0.1621, abs=1e-4)


@SETTINGS
@given(tables(min_inputs=1, max_inputs=6, max_runs=6), st.floats(0.01, 1.0), st.sampled_from(["drop", "rise"]), st.sampled_from([0.05, 0.1]))
def test_tr52_power_is_the_formula_of_section_2_5(tab, r, direction, alpha) -> None:  # type: ignore[no-untyped-def]
    got = power_at(counts_of(tab), r, direction=direction, alpha=alpha)
    assert got == pytest.approx(_power_oracle(tab, r, direction, alpha), abs=1e-9)


@pytest.mark.parametrize("direction", ["drop", "rise"])
def test_tr52_the_limit_is_at_the_smallest_r_reaching_the_power(direction: str) -> None:
    c = counts_of(WORKED)
    limit = detection_limit(c, direction=direction)  # type: ignore[arg-type]
    assert limit is not None
    per_r = 0.525 if direction == "drop" else 0.475  # Δ(r) / W = r · (weighted mean of p̄ or 1 − p̄)
    r_star = limit / per_r
    assert power_at(c, r_star, direction=direction) >= 0.8 - 1e-9  # type: ignore[arg-type]
    assert power_at(c, r_star - 1e-6, direction=direction) < 0.8  # type: ignore[arg-type]


def test_tr52_limits_shrink_with_repeats_and_inputs() -> None:
    c = counts_of(WORKED)
    for direction in ("drop", "rise"):
        base = detection_limit(c, direction=direction)  # type: ignore[arg-type]
        assert base is not None
        assert detection_limit(c, direction=direction, repeats=4) == pytest.approx(base, abs=1e-12)  # type: ignore[arg-type]
        doubled = detection_limit(c, direction=direction, repeats=8)  # type: ignore[arg-type]
        assert doubled is not None and doubled < base
        wider = detection_limit(c, direction=direction, scale=2.0)  # type: ignore[arg-type]
        assert wider is not None and wider < base
        twice = detection_limit(counts_of(WORKED * 2), direction=direction)  # type: ignore[arg-type]
        assert twice is not None and twice < base
        assert twice == pytest.approx(wider, abs=1e-9)


def test_tr52_no_limit_when_even_the_largest_change_is_short_of_the_power() -> None:
    tiny = counts_of([(1, 1, 0, 1)])
    assert power_at(tiny, 1.0, direction="drop") < 0.8
    assert detection_limit(tiny, direction="drop") is None
    assert detection_limit(counts_of([(0, 1, 0, 1), (1, 2, 0, 1)]), direction="rise") is None


# ---------- TR53 ----------


@pytest.mark.parametrize("k,n,mean,kappa", [(20, 5, 0.75, 0.5), (50, 4, 0.75, 0.5), (50, 4, 0.55, 0.0)])
def test_tr53_the_limit_means_what_it_says(k: int, n: int, mean: float, kappa: float) -> None:
    rng = np.random.default_rng(5300 + k + n + int(100 * mean))
    rates = _rates(rng, k, mean, kappa)
    big = 2000  # the rates as a pilot of 2 x 2000 runs per input, so the limit is read with them known
    t = np.clip(np.round(rates * 2 * big).astype(int), 0, 2 * big)
    pilot = [Counts(f"h{i}", int(ti // 2), big, int(ti - ti // 2), big) for i, ti in enumerate(t)]
    p = t / (2 * big)
    limit = detection_limit(pilot, direction="drop", repeats=n)
    assert limit is not None
    r_star = limit / float(p.mean())
    hits = 0
    for _ in range(1500):
        xa, xb = rng.binomial(n, p), rng.binomial(n, (1 - r_star) * p)
        res = paired_test(counts_of([(int(a), n, int(b), n) for a, b in zip(xa, xb)]))
        hits += res.p < 0.05 and res.observed_new < res.expected_new
    assert 0.75 <= hits / 1500 <= 0.95, hits / 1500


# ---------- TR55 (the functions) ----------


def _limit(counts, **kw):  # type: ignore[no-untyped-def]
    return detection_limit(counts, direction="drop", **kw)


@pytest.mark.parametrize("x,repeats,inputs", [(0.15, 5, 36), (0.10, 11, 77)])
def test_tr55_guidance_on_six_copies_of_the_worked_example(x: float, repeats: int, inputs: int) -> None:
    six = counts_of(WORKED * 6)
    assert repeats_needed(six, x) == repeats
    assert inputs_needed(six, x) == inputs


@pytest.mark.parametrize("x", [0.12, 0.2, 0.3, 0.45])
def test_tr55_repeats_and_inputs_are_minimal(x: float) -> None:
    for tab in (WORKED, WORKED * 3, [(3, 4, 1, 1), (4, 4, 1, 1), (2, 4, 0, 1)]):
        c = counts_of(tab)
        r = repeats_needed(c, x)
        assert r is not None
        at = _limit(c, repeats=r)
        assert at is not None and at <= x
        if r > 1:
            below = _limit(c, repeats=r - 1)
            assert below is None or below > x
        k = inputs_needed(c, x)
        assert k is not None
        at = _limit(c, scale=k / len(c))
        assert at is not None and at <= x
        if k > 1:
            below = _limit(c, scale=(k - 1) / len(c))
            assert below is None or below > x


def test_tr55_a_search_that_cannot_succeed_is_none() -> None:
    c = counts_of(WORKED)
    assert repeats_needed(c, 1e-9) is None
    assert inputs_needed(c, 1e-9) is None


@SETTINGS
@given(st.floats(1e-6, 0.999), st.sampled_from([3, 4]))
def test_tr55_accepts_at_rounds_up(limit: float, decimals: int) -> None:
    got = accepts_at(limit, decimals=decimals)
    unit = 10.0**-decimals
    assert got >= limit
    assert abs(got / unit - round(got / unit)) < 1e-6
    assert got - unit < limit + 1e-12


# ---------- TR56 (the function) ----------


@SETTINGS
@given(st.floats(1.02, 3.0), st.floats(0.05, 0.95), st.sampled_from([0.05, 0.1]))
def test_tr56_deaths_needed_is_the_smallest_reaching_count(x: float, share: float, alpha: float) -> None:
    from poisson_trace.survival import deaths_needed, mde_hazard_ratio

    d = deaths_needed(x, share, alpha=alpha)
    assert mde_hazard_ratio(d, share, alpha=alpha) <= x
    assert d == 1 or mde_hazard_ratio(d - 1, share, alpha=alpha) > x


def test_tr56_deaths_needed_on_the_tau2_pair() -> None:
    from poisson_trace.survival import deaths_needed

    assert deaths_needed(1.3, 0.5) == 457


# ---------- TR57, TR58 (the functions) ----------


def _prove_0_0_1_limit(p_a: float, n_a: int, n_b: int, *, alpha: float, power: float) -> float:
    """Prove 0.0.1's per-cell limit (``proofload.diff.mde_two_proportion`` at 98dc6af, its power
    function inlined), the number ``limit_rise`` gives. Prove's main pairs the two arms' sizes the
    other way round and gives NaN at a share of 1, which Trace has not followed (TF16 Session A
    yes/no 7); with ``proofload`` no longer installed, the reference is kept here."""

    def power_at(delta: float, p: float) -> float:
        p_alt = p + delta
        pooled = (p_alt * n_a + p * n_b) / (n_a + n_b)
        se_null = math.sqrt(pooled * (1.0 - pooled) * (1.0 / n_a + 1.0 / n_b))
        se_alt = math.sqrt(p_alt * (1.0 - p_alt) / n_a + p * (1.0 - p) / n_b)
        z = float(stats.norm.isf(alpha / 2.0))
        if se_alt == 0.0:
            return 1.0 if delta > z * se_null else 0.0
        return float(stats.norm.sf((z * se_null - delta) / se_alt)) + float(stats.norm.cdf((-z * se_null - delta) / se_alt))

    guarded = 0.5 / n_a if p_a <= 0.0 else (1.0 - 0.5 / n_a if p_a >= 1.0 else p_a)
    cap = 1.0 - guarded
    if power_at(cap, guarded) < power:
        return (1.0 - p_a) if p_a < 1.0 else cap
    lo, hi = 0.0, cap
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if power_at(mid, guarded) >= power:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1e-12:
            break
    return hi


@SETTINGS
@given(tables(min_inputs=1, max_inputs=12, max_runs=12), st.sampled_from([0.05, 0.1, 0.2]))
def test_tr57_flags_are_fisher_then_benjamini_hochberg(tab, alpha) -> None:  # type: ignore[no-untyped-def]
    from poisson_prove.diff import _fisher, bh

    c = counts_of(tab)
    got = {f.config_hash: f for f in flags(c, alpha=alpha)}
    assert set(got) == {x.config_hash for x in c}
    p = np.array([_fisher(x.failed_old, x.runs_old, x.failed_new, x.runs_new)[1] for x in c])
    q = bh(p, alpha)
    for x, pi, qi in zip(c, p, q):
        f = got[x.config_hash]
        change = x.failed_new / x.runs_new - x.failed_old / x.runs_old
        assert f.p == pytest.approx(float(pi), abs=1e-12)
        assert f.q == pytest.approx(float(qi), abs=1e-12)
        assert f.change == pytest.approx(change, abs=1e-12)
        if qi < alpha:
            assert f.flag == ("failed more in B" if change > 0 else "failed less in B")
        else:
            assert f.flag is None
        assert f.limit_rise == pytest.approx(
            _prove_0_0_1_limit(x.failed_old / x.runs_old, x.runs_old, x.runs_new, alpha=alpha, power=0.8), abs=1e-12)


def test_tr57_a_real_flag_fires_in_each_direction() -> None:
    c = counts_of([(0, 20, 20, 20), (20, 20, 0, 20)] + [(5, 10, 5, 10)] * 10)
    got = {f.config_hash: f.flag for f in flags(c)}
    assert got["h000"] == "failed more in B"
    assert got["h001"] == "failed less in B"
    assert sum(v is not None for v in got.values()) == 2


@SETTINGS
@given(st.integers(1, 60).flatmap(lambda n: st.tuples(st.integers(0, n), st.just(n))), st.integers(1, 60),
       st.sampled_from([0.01, 0.05, 0.1]), st.sampled_from([0.8, 0.9]))
def test_tr58_limit_rise_is_proves_mde_two_proportion(old, runs_new, alpha, power) -> None:  # type: ignore[no-untyped-def]
    failed, runs = old
    got = limit_rise(failed / runs, runs, runs_new, alpha=alpha, power=power)
    assert got == pytest.approx(_prove_0_0_1_limit(failed / runs, runs, runs_new, alpha=alpha, power=power), abs=1e-12)
