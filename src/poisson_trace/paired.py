"""The fix check's statistics: the per-input counts, the exact conditional
Cochran-Mantel-Haenszel test stratified by input, the Mantel-Haenszel difference with Sato's
interval, the by-input sign-flip reading, consistency, the detection limits, the guidance, and
the per-input flags.

numpy and scipy only.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from typing import Literal

import numpy as np
from scipy import stats

from poisson_trace.survival import bh

# The four reasons an input is left out, in the order they are tried, and the six sentences
# printed under every report of the two verbs.
LEFT_OUT: tuple[str, ...] = (
    "not re-run on the old version",
    "not re-run on the new version",
    "no outcome on the old version",
    "no outcome on the new version",
)
CANNOT_SAY: tuple[str, ...] = (
    "A difference between two stored runs is a difference between the runs. The version, the "
    "provider and the hour changed together unless the two were run side by side, and this "
    "test cannot separate them.",
    "Repeat runs of one input are read as separate draws and never as replays: a served model "
    "is not bit-identical on repeat, so nothing here matches a run of the old version to a run "
    "of the new by seed.",
    "If repeat runs of one input are near copies of one another, the run-level test overstates "
    "its confidence. The by-input line does not depend on that.",
    "Rows with no outcome are left out of both arms and counted in the header. A new version "
    "that times out where the old one failed does not show as a failure here.",
    "Trace reads the runs it is given. If the inputs were chosen by the old arm's own outcomes, "
    "or the more favourable of several runs was handed over, the confidence printed does not "
    "hold.",
    "The detection limit and the run counts are computed from these runs' own failure rates, "
    "which are estimates. They are a guide to the next design, not a promise about it.",
)

# Ties in the exact distribution are taken at this relative tolerance (Fisher's convention,
# and scipy's).
_TIE = 1e-7
# The by-input reading enumerates every sign assignment up to this many moved inputs.
_EXACT_MOVED = 14
_BLOCK = 10_000
# A guidance search doubles its bracket until it succeeds or goes beyond this.
_SEARCH_CEILING = 2**30
_BISECTION_WIDTH = 1e-12


@dataclass(frozen=True)
class Counts:
    config_hash: str
    failed_old: int
    runs_old: int
    failed_new: int
    runs_new: int


@dataclass(frozen=True)
class PairedTest:
    inputs: int
    informative: int
    observed_new: int
    expected_new: float
    variance: float
    weight: float
    p: float


@dataclass(frozen=True)
class Flag:
    config_hash: str
    change: float
    p: float
    q: float
    flag: str | None
    limit_rise: float


def _checked(counts: Sequence[Counts]) -> Sequence[Counts]:
    for c in counts:
        if c.runs_old < 1 or c.runs_new < 1:
            raise ValueError(f"input {c.config_hash} holds no run in one arm")
        if not (0 <= c.failed_old <= c.runs_old and 0 <= c.failed_new <= c.runs_new):
            raise ValueError(f"input {c.config_hash} holds more failures than runs")
    return counts


# ---------- the exact test ----------


def _hypergeometric(runs_old: int, runs_new: int, failed: int) -> tuple[int, np.ndarray]:
    """The null distribution of the new arm's failures on one input, given the input's total:
    ``(lowest value, probabilities from there up)``. Exact integer counts, divided once."""
    total = runs_old + runs_new
    lowest = max(0, failed - runs_old)
    highest = min(failed, runs_new)
    tables = math.comb(total, runs_new)
    pmf = [
        math.comb(failed, k) * math.comb(total - failed, runs_new - k) / tables
        for k in range(lowest, highest + 1)
    ]
    return lowest, np.array(pmf, dtype=np.float64)


def _two_sided(pmf: np.ndarray, at: int) -> float:
    """The total probability of every value no more probable than the one observed."""
    return float(min(1.0, pmf[pmf <= pmf[at] * (1.0 + _TIE)].sum()))


def paired_test(counts: Sequence[Counts]) -> PairedTest:
    """The exact conditional Cochran-Mantel-Haenszel test, stratified by input. Given each
    input's total failures, the new arm's count on it is hypergeometric under the null; the
    distribution of the sum is their convolution, computed in full. An input whose runs all
    failed or all did not is a single point and adds nothing."""
    observed = informative = 0
    expected = variance = weight = 0.0
    lowest = 0
    pmf = np.array([1.0], dtype=np.float64)
    for c in _checked(counts):
        n_a, n_b = c.runs_old, c.runs_new
        total, failed = n_a + n_b, c.failed_old + c.failed_new
        observed += c.failed_new
        expected += n_b * failed / total
        weight += n_a * n_b / total
        if 0 < failed < total:
            informative += 1
            variance += n_a * n_b * failed * (total - failed) / (total * total * (total - 1))
            low, one = _hypergeometric(n_a, n_b, failed)
            lowest += low
            pmf = np.convolve(pmf, one)
        else:
            lowest += c.failed_new
    return PairedTest(
        inputs=len(counts),
        informative=informative,
        observed_new=observed,
        expected_new=expected,
        variance=variance,
        weight=weight,
        p=_two_sided(pmf, observed - lowest),
    )


# ---------- the difference and its interval ----------


def difference(
    counts: Sequence[Counts], *, alpha: float = 0.05
) -> tuple[float, float | None, float | None, float | None]:
    """``(points, variance, lo, hi)``: the Mantel-Haenszel risk difference, new minus old, as a
    fraction, with Sato's variance and the large-sample interval clipped to ``[-1, 1]``. The
    last three are ``None`` when the variance is not positive."""
    rows = [(c.failed_old, c.runs_old, c.failed_new, c.runs_new) for c in _checked(counts)]
    w = sum(na * nb / (na + nb) for _, na, _, nb in rows)
    d = sum((xb * na - xa * nb) / (na + nb) for xa, na, xb, nb in rows) / w
    p_sum = sum(
        (nb * nb * xa - na * na * xb + na * nb * (na - nb) / 2) / (na + nb) ** 2
        for xa, na, xb, nb in rows
    )
    q_sum = sum((xb * (na - xa) + xa * (nb - xb)) / (2 * (na + nb)) for xa, na, xb, nb in rows)
    variance = (d * p_sum + q_sum) / w**2
    if not variance > 0.0:
        return d, None, None, None
    half = float(stats.norm.isf(alpha / 2.0)) * math.sqrt(variance)
    return d, variance, max(-1.0, d - half), min(1.0, d + half)


# ---------- the by-input reading ----------


def _moves(counts: Sequence[Counts]) -> list[int]:
    """Each moved input's weighted move ``w_i d_i`` as an integer, on one common scale: the
    move is ``(x_B n_A - x_A n_B) / N``, and the scale is the least common multiple of the
    ``N``. Integers, so that a tie between two sign assignments is a tie."""
    moved = [
        (c.failed_new * c.runs_old - c.failed_old * c.runs_new, c.runs_old + c.runs_new)
        for c in _checked(counts)
        if c.failed_new * c.runs_old != c.failed_old * c.runs_new
    ]
    scale = math.lcm(*(total for _, total in moved)) if moved else 1
    return [a * (scale // total) for a, total in moved]


def by_input(
    counts: Sequence[Counts], *, seed: int = 0, draws: int = 100_000
) -> tuple[float, int, str]:
    """``(p, moved, method)``: each input is one observation, its sign flipped under the null.
    Every assignment of signs is enumerated up to 14 moved inputs; beyond that ``draws`` seeded
    assignments are drawn and ``p = (1 + c) / (1 + draws)``."""
    moves = _moves(counts)
    if not moves:
        return 1.0, 0, "exact"
    observed = abs(sum(moves))
    if len(moves) <= _EXACT_MOVED:
        sums = [0]
        for move in moves:
            sums = [s + move for s in sums] + [s - move for s in sums]
        hits = sum(1 for s in sums if abs(s) >= observed)
        return hits / len(sums), len(moves), "exact"
    if draws < 1:
        raise ValueError("the by-input reading needs at least one draw")
    reach = sum(abs(m) for m in moves)
    if reach < 2**62:
        values = np.array(moves, dtype=np.int64)
        bar: float = observed
    else:
        # Integers this large do not fit a machine word; the comparison is then in floating
        # point, with ties taken at the exact test's tolerance.
        values = np.array([m / reach for m in moves], dtype=np.float64)
        bar = (observed / reach) * (1.0 - _TIE)
    rng = np.random.default_rng(seed)
    hits, left = 0, draws
    while left > 0:
        block = min(_BLOCK, left)
        signs = 2 * rng.integers(0, 2, size=(block, len(moves)), dtype=np.int8) - 1
        hits += int(np.count_nonzero(np.abs(signs.astype(values.dtype) @ values) >= bar))
        left -= block
    return (1 + hits) / (1 + draws), len(moves), "monte carlo"


# ---------- consistency ----------


def consistency(counts: Sequence[Counts]) -> tuple[float, float, float, float, float]:
    """``(p, C, kappa, within, pooled)`` from the two arms together: the failure share, the
    chance an input that failed once fails on another run, their ratio kappa, the mean
    within-input variance and the pooled variance. ``C`` and ``kappa`` are NaN when no run
    failed or every run did, where neither is defined."""
    failed = np.array([c.failed_old + c.failed_new for c in _checked(counts)], dtype=np.float64)
    total = np.array([c.runs_old + c.runs_new for c in counts], dtype=np.float64)
    if len(failed) == 0:
        raise ValueError("consistency needs at least one input")
    share = float(failed.sum() / total.sum())
    within = float(np.mean(failed * (total - failed) / (total * (total - 1.0))))
    pooled = share * (1.0 - share)
    if failed.sum() == 0.0 or failed.sum() == total.sum():
        return share, math.nan, math.nan, within, pooled
    again = float(np.sum(failed * (failed - 1.0)) / np.sum(failed * (total - 1.0)))
    return share, again, (again - share) / (1.0 - share), within, pooled


# ---------- what the comparison could not have detected ----------


@dataclass(frozen=True)
class _Design:
    """Each input's measured moments (from both arms together) and the runs per arm the limit
    is computed at; ``scale`` multiplies the number of inputs like these."""

    rate: np.ndarray  # t / N
    spread: np.ndarray  # t (N - t) / (N (N - 1)), unbiased for p (1 - p)
    square: np.ndarray  # t (t - 1) / (N (N - 1)), unbiased for p^2
    runs_old: np.ndarray
    runs_new: np.ndarray
    scale: float


def _design(counts: Sequence[Counts], repeats: int | None, scale: float) -> _Design:
    if len(counts) == 0:
        raise ValueError("a detection limit needs at least one input")
    if repeats is not None and repeats < 1:
        raise ValueError("repeats must be at least 1")
    if not scale > 0.0:
        raise ValueError("scale must be positive")
    failed = np.array([c.failed_old + c.failed_new for c in _checked(counts)], dtype=np.float64)
    total = np.array([c.runs_old + c.runs_new for c in counts], dtype=np.float64)
    if repeats is None:
        runs_old = np.array([c.runs_old for c in counts], dtype=np.float64)
        runs_new = np.array([c.runs_new for c in counts], dtype=np.float64)
    else:
        runs_old = runs_new = np.full(len(counts), float(repeats))
    return _Design(
        rate=failed / total,
        spread=failed * (total - failed) / (total * (total - 1.0)),
        square=failed * (failed - 1.0) / (total * (total - 1.0)),
        runs_old=runs_old,
        runs_new=runs_new,
        scale=scale,
    )


def _power(design: _Design, r: float, direction: str, alpha: float) -> tuple[float, float]:
    """``(power, shift in failure share)`` under a proportional change ``r`` on every input:
    the chance the test calls a difference in the stated direction. The threshold uses the
    expected value of the test's own reference variance under the alternative, the spread is
    the variance of the statistic under it, and one half is the continuity correction."""
    p, s, m = design.rate, design.spread, design.square
    n_a, n_b = design.runs_old, design.runs_new
    total = n_a + n_b
    w = n_a * n_b / total
    if direction == "drop":
        mean_b = (1.0 - r) * p
        second_b = (1.0 - r) ** 2 * m
        cross = (1.0 - r) * m
        shift = w * (p - mean_b)
    elif direction == "rise":
        q, q2 = 1.0 - p, 1.0 - 2.0 * p + m
        mean_b = 1.0 - (1.0 - r) * q
        second_b = 1.0 - 2.0 * (1.0 - r) * q + (1.0 - r) ** 2 * q2
        cross = p - (1.0 - r) * (p - m)
        shift = w * (mean_b - p)
    else:
        raise ValueError(f"direction must be drop or rise, not {direction}")
    s_b = mean_b - second_b
    together = (n_a * p + n_b * mean_b) / total
    together_sq = (n_a * n_a * m + n_b * n_b * second_b + 2.0 * n_a * n_b * cross) / total**2
    ref = (
        w
        * np.maximum(total * total * (together - together_sq) - n_a * s - n_b * s_b, 0.0)
        / (total * (total - 1.0))
    )
    spread = w * w * (s / n_a + s_b / n_b)
    delta = float(shift.sum()) * design.scale
    v_ref = float(ref.sum()) * design.scale
    v_one = float(spread.sum()) * design.scale
    weight = float(w.sum()) * design.scale
    edge = float(stats.norm.isf(alpha / 2.0)) * math.sqrt(v_ref)
    if v_one <= 0.0:
        return (1.0 if delta - 0.5 > edge else 0.0), delta / weight
    return float(stats.norm.sf((edge + 0.5 - delta) / math.sqrt(v_one))), delta / weight


def power_at(
    counts: Sequence[Counts],
    r: float,
    *,
    direction: Literal["drop", "rise"],
    alpha: float = 0.05,
) -> float:
    return _power(_design(counts, None, 1.0), r, direction, alpha)[0]


def detection_limit(
    counts: Sequence[Counts],
    *,
    direction: Literal["drop", "rise"],
    alpha: float = 0.05,
    power: float = 0.8,
    repeats: int | None = None,
    scale: float = 1.0,
) -> float | None:
    """The smallest change in failure share, as a fraction, the test would have detected at
    ``power``: the shift at the smallest proportional change ``r`` in (0, 1] reaching it, by
    bisection. ``None`` when even ``r = 1`` falls short. ``repeats`` puts that many runs in
    each arm of every input and ``scale`` multiplies the number of inputs, the measured rates
    held."""
    design = _design(counts, repeats, scale)
    if _power(design, 1.0, direction, alpha)[0] < power:
        return None
    lo, hi = 0.0, 1.0
    while hi - lo >= _BISECTION_WIDTH:
        mid = (lo + hi) / 2.0
        if _power(design, mid, direction, alpha)[0] >= power:
            hi = mid
        else:
            lo = mid
    return _power(design, hi, direction, alpha)[1]


# ---------- guidance ----------


def _smallest_reaching(reaches: Callable[[int], bool]) -> int | None:
    """The smallest positive integer at which ``reaches`` holds with the one below it failing:
    the bracket doubles until it succeeds or goes beyond the ceiling, then is bisected."""
    hi = 1
    while not reaches(hi):
        hi *= 2
        if hi > _SEARCH_CEILING:
            return None
    lo = hi // 2  # fails, or is 0
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if reaches(mid):
            hi = mid
        else:
            lo = mid
    return hi


def repeats_needed(
    counts: Sequence[Counts], max_mde: float, *, alpha: float = 0.05, power: float = 0.8
) -> int | None:
    """The smallest number of runs per arm on these inputs at which the drop limit is at most
    ``max_mde``, computed with the function that states the limit."""

    def reaches(n: int) -> bool:
        limit = detection_limit(counts, direction="drop", alpha=alpha, power=power, repeats=n)
        return limit is not None and limit <= max_mde

    return _smallest_reaching(reaches)


def inputs_needed(
    counts: Sequence[Counts], max_mde: float, *, alpha: float = 0.05, power: float = 0.8
) -> int | None:
    """The smallest number of inputs like these, at the present repeats, at which the drop
    limit is at most ``max_mde``."""
    present = len(counts)

    def reaches(k: int) -> bool:
        limit = detection_limit(
            counts, direction="drop", alpha=alpha, power=power, scale=k / present
        )
        return limit is not None and limit <= max_mde

    return _smallest_reaching(reaches)


def accepts_at(limit: float, *, decimals: int) -> float:
    """``limit`` rounded up at ``decimals``, and never below it: the ceiling that accepts the
    design as it stands."""
    unit = Decimal(1).scaleb(-decimals)
    offered = Decimal(repr(float(limit))).quantize(unit, rounding=ROUND_CEILING)
    while float(offered) < limit:
        offered += unit
    return float(offered)


# ---------- the per-input flags ----------


def _fisher(c: Counts) -> float:
    """Fisher's exact test on one input, two-sided, computed as Prove computes it (scipy's
    ``fisher_exact``). The exact test above gives the same number to 1e-12 on one input; the
    flags use this one so that an input whose adjusted value sits exactly on the level is
    flagged, or not, as Prove's ``diff`` flags it."""
    table = [[c.failed_old, c.runs_old - c.failed_old], [c.failed_new, c.runs_new - c.failed_new]]
    return float(stats.fisher_exact(table, alternative="two-sided")[1])


def flags(counts: Sequence[Counts], *, alpha: float = 0.05, power: float = 0.8) -> tuple[Flag, ...]:
    """One row per input, in the order given: Fisher's exact test on its own table, then
    Benjamini-Hochberg over all the inputs as one family. An input is flagged when its
    adjusted value is below ``alpha``."""
    ps = np.array([_fisher(c) for c in _checked(counts)], dtype=np.float64)
    qs = bh(ps, alpha)
    out = []
    for c, p, q in zip(counts, ps, qs, strict=True):
        rate_old = c.failed_old / c.runs_old
        change = c.failed_new / c.runs_new - rate_old
        flag = None
        if q < alpha:
            flag = "failed more in B" if change > 0 else "failed less in B"
        out.append(
            Flag(
                config_hash=c.config_hash,
                change=change,
                p=float(p),
                q=float(q),
                flag=flag,
                limit_rise=limit_rise(rate_old, c.runs_old, c.runs_new, alpha=alpha, power=power),
            )
        )
    return tuple(out)


def _power_two_proportion(
    delta: float, rate: float, runs_old: int, runs_new: int, alpha: float
) -> float:
    """Two-sided normal-approximation power to detect ``rate + delta`` against ``rate``: the
    pooled standard error under the null, separate ones under the alternative."""
    raised = rate + delta
    pooled = (raised * runs_old + rate * runs_new) / (runs_old + runs_new)
    se_null = math.sqrt(pooled * (1.0 - pooled) * (1.0 / runs_old + 1.0 / runs_new))
    se_alt = math.sqrt(raised * (1.0 - raised) / runs_old + rate * (1.0 - rate) / runs_new)
    z = float(stats.norm.isf(alpha / 2.0))
    if se_alt == 0.0:
        return 1.0 if delta > z * se_null else 0.0
    upper = float(stats.norm.sf((z * se_null - delta) / se_alt))
    lower = float(stats.norm.cdf((-z * se_null - delta) / se_alt))
    return upper + lower


def limit_rise(
    rate_old: float, runs_old: int, runs_new: int, *, alpha: float = 0.05, power: float = 0.8
) -> float:
    """The smallest rise in failure share from ``rate_old`` that one input's own test detects
    at ``power``, two-sided at ``alpha``: Prove's per-cell limit, number for number. A rate of
    exactly 0 or 1 is moved in by half a run; when even the largest rise is not detectable the
    largest rise is returned."""
    if runs_old <= 0 or runs_new <= 0:
        raise ValueError("the per-input limit needs at least one run in each arm")
    if not 0.0 <= rate_old <= 1.0:
        raise ValueError("rate_old must lie in [0, 1]")
    guarded = rate_old
    if rate_old <= 0.0:
        guarded = 0.5 / runs_old
    elif rate_old >= 1.0:
        guarded = 1.0 - 0.5 / runs_old
    cap = 1.0 - guarded
    if _power_two_proportion(cap, guarded, runs_old, runs_new, alpha) < power:
        return (1.0 - rate_old) if rate_old < 1.0 else cap
    lo, hi = 0.0, cap
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _power_two_proportion(mid, guarded, runs_old, runs_new, alpha) >= power:
            hi = mid
        else:
            lo = mid
        if hi - lo < _BISECTION_WIDTH:
            break
    return hi
