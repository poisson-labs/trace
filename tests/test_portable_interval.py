"""The fix check's exact test and range, held to exact references on the 400 seeded tables of
``portable_support.count_tables``.

- The exact test's p is within 1e-12 relative of the exact rational p, computed here in integers
  with the same tie rule (a value counts as no more probable than the observed one when it is
  at most ``1 + 1e-7`` times it), applied exactly.
- Each end of the range is the float at which the stratified Miettinen-Nurminen score
  (``paired.mn_score``) crosses the normal quantile: the low end ``lo`` has
  ``score(lo) <= z < score(the float below lo)``, and the high end ``hi`` has
  ``score(hi) >= -z > score(the float above hi)``, with ``z`` the build's
  ``portable.norm_isf(alpha / 2)``, at levels 0.05 and 0.1. An end at -1 or 1 is where the score
  never reaches the quantile, and is not searched.
- On the 20 smallest tables the ends are within 1e-12 of the roots of the same score evaluated in
  ``Decimal`` at 40 digits, each input's constrained rate found there by bisection, against the
  normal quantile at ``0.025`` (the float) to 37 digits. This check needs nothing of the build but
  the range it prints.

Tables on which no run failed in either version have a range in closed form and no search; they
are left out of the second and third checks.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

import pytest
from portable_support import count_tables, counts

LEVELS = (0.05, 0.1)


def exact_p(table: list[tuple[int, int, int, int]]) -> float:
    """The exact conditional test's two-sided p, correctly rounded: every input's
    hypergeometric distribution of the new arm's failures as integers over one common
    denominator, convolved exactly."""
    dist = [1]
    lowest = 0
    observed = 0
    denominator = 1
    for failed_old, runs_old, failed_new, runs_new in table:
        total, failed = runs_old + runs_new, failed_old + failed_new
        observed += failed_new
        low, high = max(0, failed - runs_old), min(failed, runs_new)
        lowest += low
        one = [math.comb(failed, k) * math.comb(total - failed, runs_new - k) for k in range(low, high + 1)]
        denominator *= math.comb(total, runs_new)
        out = [0] * (len(dist) + len(one) - 1)
        for i, a in enumerate(dist):
            if a:
                for j, b in enumerate(one):
                    out[i + j] += a * b
        dist = out
    at = dist[observed - lowest]
    held = sum(v for v in dist if v * 10_000_000 <= at * 10_000_001)
    return 1.0 if held >= denominator else held / denominator


def test_the_exact_test_p_is_within_1e_12_of_the_exact_rational() -> None:
    from poisson_trace import paired

    off = []
    for i, table in enumerate(count_tables()):
        got = paired.paired_test(counts(table)).p
        want = exact_p(table)
        if abs(got - want) > 1e-12 * want:
            off.append((i, got, want))
    assert not off, f"{len(off)} of 400 tables: (table, p, exact p) {off[:10]}"


def _searched(table: list[tuple[int, int, int, int]]) -> bool:
    return any(failed_old or failed_new for failed_old, _, failed_new, _ in table)


@pytest.mark.parametrize("alpha", LEVELS)
def test_each_end_of_the_range_is_the_float_where_the_score_crosses_the_quantile(alpha: float) -> None:
    from poisson_trace import paired
    from poisson_trace.stats import portable

    z = portable.norm_isf(alpha / 2.0)
    wrong = []
    ends = 0
    for i, table in enumerate(count_tables()):
        if not _searched(table):
            continue
        cs = counts(table)
        _, variance, lo, hi = paired.difference(cs, alpha=alpha)
        if variance is None:
            continue
        assert lo is not None and hi is not None
        if lo != -1.0:
            ends += 1
            below = math.nextafter(lo, -math.inf)
            if not paired.mn_score(cs, lo) <= z < paired.mn_score(cs, below):
                wrong.append((i, "lo", lo, paired.mn_score(cs, lo), paired.mn_score(cs, below)))
        if hi != 1.0:
            ends += 1
            above = math.nextafter(hi, math.inf)
            if not paired.mn_score(cs, hi) >= -z > paired.mn_score(cs, above):
                wrong.append((i, "hi", hi, paired.mn_score(cs, hi), paired.mn_score(cs, above)))
    assert ends > 400, ends
    assert not wrong, f"z = {z!r}; {len(wrong)} ends are not the score's crossing: {wrong[:8]}"


# ---------- the score in Decimal ----------

CTX = Context(prec=40, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999)
EDGE = Decimal("1e-9")
#: The upper normal quantile at the float nearest 0.025, which is 0.025000000000000001387...
Z_025 = Decimal("1.959963984540054211779584194227173968")


def _constrained(x1: int, n1: int, x2: int, n2: int, delta: Decimal) -> tuple[Decimal, Decimal]:
    """The new and old rates at their maximum likelihood under ``p1 - p2 = delta``: the middle
    real root of the likelihood's cubic, which lies between its two turning points where the
    cubic falls, found by bisection, and clipped to ``[max(0, delta), min(1, 1 + delta)]``."""
    p1, p2 = Decimal(x1) / n1, Decimal(x2) / n2
    theta = Decimal(n2) / n1
    a = 1 + theta
    b = -(1 + theta + p1 + theta * p2 + delta * (theta + 2))
    c = delta * delta + delta * (2 * p1 + theta + 1) + p1 + theta * p2
    d = -p1 * delta * (1 + delta)

    def cubic(q: Decimal) -> Decimal:
        return ((a * q + b) * q + c) * q + d

    centre = -b / (3 * a)
    gap = b * b - 3 * a * c
    if gap <= 0:
        q1 = centre
    else:
        half = gap.sqrt() / (3 * a)
        lo, hi = centre - half, centre + half
        if cubic(lo) < 0:
            q1 = lo
        elif cubic(hi) > 0:
            q1 = hi
        else:
            for _ in range(100):
                mid = (lo + hi) / 2
                if cubic(mid) > 0:
                    lo = mid
                else:
                    hi = mid
            q1 = (lo + hi) / 2
    q1 = min(max(q1, max(Decimal(0), delta)), min(Decimal(1), 1 + delta))
    q2 = min(max(q1 - delta, Decimal(0)), Decimal(1))
    return q1, q2


def decimal_score(table: list[tuple[int, int, int, int]], delta: Decimal) -> Decimal:
    num = Decimal(0)
    var = Decimal(0)
    for x2, n2, x1, n1 in table:
        total = n1 + n2
        w = Decimal(n1 * n2) / total
        num += w * (Decimal(x1) / n1 - Decimal(x2) / n2 - delta)
        q1, q2 = _constrained(x1, n1, x2, n2, delta)
        var += w * w * (q1 * (1 - q1) / n1 + q2 * (1 - q2) / n2) * Decimal(total) / (total - 1)
    return num / var.sqrt()


def _root(table: list[tuple[int, int, int, int]], target: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    """Where the score, which falls with ``delta``, meets ``target`` between ``lo`` and ``hi``."""
    for _ in range(64):
        mid = (lo + hi) / 2
        if decimal_score(table, mid) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def test_the_ends_of_the_range_are_within_1e_12_of_the_decimal_roots() -> None:
    from poisson_trace import paired

    # the 20 smallest tables a range is searched on, in their order, for the time Decimal takes
    searched = [t for t in count_tables() if _searched(t)]
    tables = sorted(searched, key=len)[:20]
    assert len(tables) == 20
    off = []
    for table in tables:
        cs = counts(table)
        estimate, variance, lo, hi = paired.difference(cs)
        assert variance is not None and lo is not None and hi is not None
        with localcontext(CTX):
            z = +Z_025
            point = Decimal(estimate)
            if lo != -1.0:
                root = _root(table, z, -1 + EDGE, point)
                if abs(Decimal(lo) - root) > Decimal("1e-12"):
                    off.append(("lo", lo, root))
            if hi != 1.0:
                root = _root(table, -z, point, 1 - EDGE)
                if abs(Decimal(hi) - root) > Decimal("1e-12"):
                    off.append(("hi", hi, root))
    assert not off, off
