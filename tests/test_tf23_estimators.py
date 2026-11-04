"""TF23-1 to TF23-8: the continuous measures' estimators, each against an outside reference (spec
section 18.6.1 as ruled on 2026-11-03; vault log/trace-continuous-statistics-check/rulings.md).

**TF23-1** The sign-flip p (item 5, CS3 keeps it as the test) is exact over the non-zero case
differences: it equals scipy's paired ``permutation_test`` where that is exact, the check's own
p on its validation data (``sims/00-validate.txt``), and brute force; it ignores zero
differences; the "studentized" statistic of item 5 gives the same p as the sum (Efron 1969).

**TF23-2** The floor (item 2, CS1): with ``n`` non-zero differences all one way the p is
``2^(1 - n)`` whatever their sizes, and with ``j`` of the smallest the other way it is
``2^(1 + j - n)`` (``sims/06-floors.txt``); ``p_floor(n)`` is ``2^(1 - n)``, and 1 at no change.

**TF23-3** Exact enumeration runs to 20 non-zero differences; above 20 the p is
``(1 + count) / (1 + 100,000)`` over 100,000 random sign vectors, never 0, at least
``1 / 100,001``, a whole number of 100,001ths (CS12). The draws are seeded from
``sha256(run_a + ":" + run_b + ":" + measure)`` (IC5): the same key gives the same p, and the
seed is that hash read as a whole number.

**TF23-4** The 95% range for the mean change is the Student t interval on the per-case
differences (CS3), equal to scipy's ``ttest_1samp(...).confidence_interval``; nothing called BCa
is printed or saved (TF23-14).

**TF23-5** The typical case's change (item 6, CS11) is the Hodges-Lehmann estimate, the median of
the Walsh averages; its 95% range is the exact Walsh-average interval, equal to the check's
``hl_interval`` and to the inversion of scipy's exact Wilcoxon test.

**TF23-6** The smallest catchable change (item 3, CS5) is ``(t_{K-1, 1 - a/2} + t_{K-1, 0.80})
s_d / sqrt(K)`` at the level ``a`` it is asked for, and ``K_needed`` is
``ceil(K (MDE / delta)^2)``.

**TF23-7** Holm's procedure over the measures that can be called (CS5) steps down: the i-th
smallest p is held to ``alpha / (m - i + 1)``, and the first that misses stops it.

**TF23-8** The ceiling flag (CS10) reads ``measure=N%`` into the measure and a fraction, and
refuses anything else.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pytest
from scipy import stats

from tf23_support import (
    MEASURES, cm, ref_exact_signflip_p, ref_hl_interval, ref_seed_for, ref_signflip_p, ref_walsh,
    validate_data,
)

KEY = 12345

# sims/00-validate.txt, item 1: the check's exact p on its six data sets (the K=15 and K=30 rows
# there were drawn, 10,000 flips; they are exact here, from brute force)
VALIDATE_EXACT = {0: 0.003906, 1: 0.311035, 3: 0.115234, 4: 0.541992}


# ---------- TF23-1 ----------


@pytest.mark.parametrize("i", [0, 1, 3, 4])
def test_tf23_1_signflip_p_is_the_checks_exact_p_and_scipys(i: int) -> None:
    d = validate_data()[i]
    p = cm().signflip_p(d, seed=KEY)
    assert p == pytest.approx(VALIDATE_EXACT[i], abs=5e-7)
    sp = stats.permutation_test(
        (d,), lambda x, axis: np.mean(x, axis=axis), permutation_type="samples",
        n_resamples=np.inf, alternative="two-sided",
    ).pvalue
    assert p == pytest.approx(sp, rel=1e-9, abs=1e-12)


def test_tf23_1_fifteen_differences_are_exact_now() -> None:
    d = validate_data()[2]  # K = 15, every difference non-zero: drawn in the check, exact under CS12
    assert cm().signflip_p(d, seed=KEY) == pytest.approx(ref_exact_signflip_p(d), rel=1e-12)


def test_tf23_1_zero_differences_do_not_count() -> None:
    d = [1.2, 0.0, 0.7, 0.0, -0.3, 2.2, 0.0, 0.9, 1.1, 0.4]
    nz = [x for x in d if x != 0]
    assert cm().signflip_p(d, seed=KEY) == pytest.approx(ref_exact_signflip_p(nz), rel=1e-12)
    assert cm().signflip_p([0.0] * 12, seed=KEY) == 1.0


def test_tf23_1_the_studentized_statistic_gives_the_sums_p() -> None:
    """Item 5 writes the test with the studentized T; on every sign vector |T| rises with |sum|,
    so the p is the sum's (the check's validate.py item 1)."""
    rng = np.random.default_rng(7)
    d = rng.lognormal(0, 1, 11) - 1.0
    k = len(d)
    signs = np.array(np.meshgrid(*[[1.0, -1.0]] * k)).reshape(k, -1).T
    x = signs * d
    m = x.mean(axis=1)
    se = np.sqrt(((x - m[:, None]) ** 2).sum(axis=1) / (k * (k - 1)))
    t = np.abs(m / se)
    t0 = abs(d.mean() / np.sqrt(((d - d.mean()) ** 2).sum() / (k * (k - 1))))
    p_t = float((t >= t0 * (1 - 1e-12)).mean())
    assert cm().signflip_p(d, seed=KEY) == pytest.approx(p_t, rel=1e-12)


# ---------- TF23-2 ----------


@pytest.mark.parametrize("n", [5, 6, 7, 8, 9, 10, 12, 16, 20])
def test_tf23_2_all_one_way_is_the_floor_whatever_the_sizes(n: int) -> None:
    rng = ref_seed_for(2, n)
    d = np.abs(rng.lognormal(0, 2.5, n)) + 0.01  # sizes spread over orders of magnitude
    assert cm().signflip_p(d, seed=KEY) == pytest.approx(2.0 ** (1 - n), rel=1e-12)
    assert cm().signflip_p(-d, seed=KEY) == pytest.approx(2.0 ** (1 - n), rel=1e-12)
    assert cm().p_floor(n) == pytest.approx(2.0 ** (1 - n), rel=1e-15)


@pytest.mark.parametrize("n,j", [(8, 1), (10, 1), (12, 1), (10, 2)])
def test_tf23_2_the_smallest_going_the_other_way(n: int, j: int) -> None:
    """sims/06-floors.txt: one case the other way, the smallest, gives exactly 2^(2 - n); two give at
    least 2^(3 - n)."""
    d = np.sort(ref_seed_for(6, n, j).lognormal(0, 1, n))
    d[:j] *= -1
    p = cm().signflip_p(d, seed=KEY)
    assert p == pytest.approx(ref_exact_signflip_p(d), rel=1e-12)
    if j == 1:
        assert p == pytest.approx(2.0 ** (2 - n), rel=1e-12)
    assert p >= 2.0 ** (1 + j - n) * (1 - 1e-12)


def test_tf23_2_at_no_change_the_floor_is_one() -> None:
    assert cm().p_floor(0) == 1.0


# ---------- TF23-3 ----------


def test_tf23_3_the_constants() -> None:
    assert cm().EXACT_MAX == 20
    assert cm().FLIPS == 100_000


def test_tf23_3_twenty_differences_are_enumerated() -> None:
    d = ref_seed_for(3, 20).standard_normal(20) + 0.3
    p1 = cm().signflip_p(d, seed=1)
    assert p1 == pytest.approx(ref_exact_signflip_p(d), rel=1e-12)
    assert cm().signflip_p(d, seed=2) == p1  # nothing drawn: the seed does not matter


def test_tf23_3_above_twenty_the_p_counts_the_observed_pattern() -> None:
    d = ref_seed_for(3, 40).standard_normal(40) + 0.25
    p = cm().signflip_p(d, seed=KEY)
    assert 0.0 < p <= 1.0
    assert p >= 1 / 100_001
    whole = p * 100_001
    assert whole == pytest.approx(round(whole), abs=1e-6), "p is not (1 + count) / (1 + 100,000)"
    assert cm().signflip_p(d, seed=KEY) == p  # the same key, the same p


def test_tf23_3_never_zero_when_nothing_is_more_extreme() -> None:
    d = np.full(30, 1.0)  # every case moved one way by the same amount: only the observed pattern
    p = cm().signflip_p(d, seed=KEY)  # and its mirror reach it, so a raw count / B is about 0
    assert p == pytest.approx(1 / 100_001, rel=1e-9)


def test_tf23_3_the_seed_is_the_hash_of_the_run_ids_and_the_measure() -> None:
    want = int(hashlib.sha256(b"20260915T210140Z-4847:20260915T211148Z-965d:wall_time_s").hexdigest(), 16)
    assert cm().seed("20260915T210140Z-4847", "20260915T211148Z-965d", "wall_time_s") == want
    assert cm().seed("a", "b", "cost_usd") != cm().seed("b", "a", "cost_usd")


def test_tf23_3_different_keys_draw_differently() -> None:
    d = ref_seed_for(3, 60).standard_normal(60) + 0.05
    ps = {cm().signflip_p(d, seed=cm().seed("a", "b", m)) for m in MEASURES}
    assert len(ps) > 1, "every key gave the same drawn p: the draws do not follow the key"


@pytest.mark.slow
@pytest.mark.parametrize("n", [21, 24])
def test_tf23_3_slow_the_drawn_p_agrees_with_the_exact_p(n: int) -> None:
    """Slow twin of the above: above 20 the drawn p is within four of its standard errors of
    the exact p by brute force."""
    d = ref_seed_for(3, n, 1).standard_normal(n) + 0.35
    exact = ref_exact_signflip_p(d)
    p = cm().signflip_p(d, seed=KEY)
    se = np.sqrt(exact * (1 - exact) / 100_000) + 1 / 100_001
    assert abs(p - exact) <= 4 * se, (p, exact)


@pytest.mark.slow
def test_tf23_3_slow_the_check_drawn_validation_rows_are_close() -> None:
    """sims/00-validate.txt drew the K=30 row (0.607100, 10,000 flips); the module's 100,000 draws
    land within the check's own Monte Carlo error of it."""
    d = validate_data()[5]
    p = cm().signflip_p(d, seed=KEY)
    assert abs(p - 0.607100) <= 4 * np.sqrt(0.6071 * 0.3929 / 10_000)
    # and the check's own reading with its stream, re-run here, is that row
    assert ref_signflip_p(d, ref_seed_for(1)) == pytest.approx(0.607100, abs=5e-7)


# ---------- TF23-4 ----------


@pytest.mark.parametrize("i", range(6))
def test_tf23_4_the_range_is_the_student_t_interval(i: int) -> None:
    d = validate_data()[i]
    lo, hi = cm().t_range(d)
    ci = stats.ttest_1samp(d, 0.0).confidence_interval(0.95)
    assert (lo, hi) == pytest.approx((ci.low, ci.high), rel=1e-9, abs=1e-12)


def test_tf23_4_the_checks_t_rows() -> None:
    """sims/00-validate.txt item 4 (statsmodels tconfint_mean), the first data set."""
    assert cm().t_range(validate_data()[0]) == pytest.approx((0.862132, 2.237868), abs=5e-7)


# ---------- TF23-5 ----------


@pytest.mark.parametrize("i", range(6))
def test_tf23_5_hodges_lehmann_and_its_range(i: int) -> None:
    d = validate_data()[i]
    assert cm().hodges_lehmann(d) == pytest.approx(float(np.median(ref_walsh(d))), rel=1e-12, abs=1e-12)
    assert cm().hl_range(d) == pytest.approx(ref_hl_interval(d), rel=1e-12, abs=1e-12)


def test_tf23_5_the_checks_worked_numbers() -> None:
    """sims/00-validate.txt item 8: HL +1.6200, Walsh (+0.7400, +2.1800), the inversion of scipy's
    exact Wilcoxon on a grid (+0.7401, +2.1794)."""
    d = validate_data()[0]
    assert cm().hodges_lehmann(d) == pytest.approx(1.62, abs=5e-5)
    lo, hi = cm().hl_range(d)
    assert (lo, hi) == pytest.approx((0.74, 2.18), abs=5e-5)


def test_tf23_5_the_range_inverts_scipys_exact_wilcoxon() -> None:
    d = ref_seed_for(9).standard_normal(12)
    lo, hi = cm().hl_range(d)
    grid = np.linspace(d.min(), d.max(), 2001)
    accepted = [th for th in grid if stats.wilcoxon(d - th, method="exact").pvalue > 0.05]
    step = grid[1] - grid[0]
    assert lo == pytest.approx(min(accepted), abs=step)
    assert hi == pytest.approx(max(accepted), abs=step)


# ---------- TF23-6 ----------


@pytest.mark.parametrize("k,alpha", [(10, 0.05), (15, 0.05 / 7), (20, 0.05 / 3), (100, 0.05 / 7)])
def test_tf23_6_the_smallest_catchable_change(k: int, alpha: float) -> None:
    d = ref_seed_for(10, k).lognormal(0, 1, k)
    want = (stats.t.ppf(1 - alpha / 2, k - 1) + stats.t.ppf(0.8, k - 1)) * d.std(ddof=1) / np.sqrt(k)
    assert cm().mde(d, alpha) == pytest.approx(want, rel=1e-9)


def test_tf23_6_the_checks_factor() -> None:
    """sims/00-validate.txt item 9: at K = 10, t_.975 + t_.80 = 3.1456."""
    d = np.array([1.0, -1.0] * 5)
    assert cm().mde(d, 0.05) * np.sqrt(10) / d.std(ddof=1) == pytest.approx(3.1456, abs=5e-5)


@pytest.mark.parametrize("k,mde,delta,want", [(10, 0.42, 0.21, 40), (20, 0.5, 0.6, 14), (12, 1.0, 0.3, 134)])
def test_tf23_6_cases_needed(k: int, mde: float, delta: float, want: int) -> None:
    assert cm().k_needed(k, mde, delta) == want


# ---------- TF23-7 ----------


def test_tf23_7_holm_steps_down() -> None:
    called = cm().holm({"a": 0.004, "b": 0.03, "c": 0.2})
    # 0.004 < 0.05/3, 0.03 < 0.05/2? no: stops; b and c not called
    assert dict(called) == {"a": True, "b": False, "c": False}
    called = cm().holm({"a": 0.004, "b": 0.02, "c": 0.04})
    # 0.004 < 0.0167, 0.02 < 0.025, 0.04 < 0.05: all three (Bonferroni would call only a)
    assert dict(called) == {"a": True, "b": True, "c": True}
    called = cm().holm({"a": 0.03, "b": 0.001})
    assert dict(called) == {"a": True, "b": True}
    assert dict(cm().holm({"x": 0.0499})) == {"x": True}
    assert dict(cm().holm({"x": 0.05})) == {"x": False}


# ---------- TF23-8 ----------


@pytest.mark.parametrize("text,want", [
    ("wall_time_s=10%", ("wall_time_s", 0.10)),
    ("cost_usd=2.5%", ("cost_usd", 0.025)),
    ("output_tokens=20%", ("output_tokens", 0.20)),
])
def test_tf23_8_the_ceiling_flag(text: str, want: tuple[str, float]) -> None:
    measure, fraction = cm().parse_max_change(text)
    assert measure == want[0] and fraction == pytest.approx(want[1])


@pytest.mark.parametrize("text", ["wall_time_s=0.1", "wall_time_s=10", "speed=10%", "wall_time_s=0%", "10%", ""])
def test_tf23_8_the_ceiling_flag_refuses(text: str) -> None:
    with pytest.raises(ValueError):
        cm().parse_max_change(text)
