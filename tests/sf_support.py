"""The statistics follow-up's reference: the per-input limit worked out from first principles.

One input's own test compares a baseline arm (the old version: share ``p`` failed over ``runs_old``
tries) with a changed arm (the new version: share ``p + delta`` over ``runs_new`` tries), two-sided
at ``alpha``, by the normal approximation: the pooled standard error under the null, separate ones
under the alternative. Each arm's share is weighted by, and divided by, its own number of tries:

    pooled = (runs_old * p + runs_new * (p + delta)) / (runs_old + runs_new)
    se_null = sqrt(pooled * (1 - pooled) * (1 / runs_old + 1 / runs_new))
    se_alt = sqrt(p * (1 - p) / runs_old + (p + delta) * (1 - p - delta) / runs_new)
    power = Phi((delta - z * se_null) / se_alt) + Phi((-delta - z * se_null) / se_alt)

with ``z`` the upper ``alpha / 2`` point. Prove 0.0.1 (and Trace's ``limit_rise`` with it) gave the
raised share the old arm's tries and the baseline the new arm's; Prove's main pairs them as above
(``poisson_prove.stats.mde_two_proportion``, fixed at Prove ``b6d6292``).

The limit is the smallest ``delta`` in ``(0, 1 - p]`` whose power reaches ``power``, with Prove's
conventions: a share of exactly 0 is measured from ``0.5 / runs_old``; when even the largest rise
does not reach the power the answer is ``1 - p``; at a share of 1 no rise is possible. It is found
here by scanning for the first crossing and refining it with Brent's method, not by bisection, so
it shares no search with the function it checks. On every design with up to 60 tries a side, at
alpha 0.01 to 0.2 and power 0.8 and 0.9, the power curve crosses its target once (checked on a
4,001-point scan of each), so the first crossing is the only one.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import optimize, stats

#: The scan that brackets the first crossing; Brent's method then refines it to ``XTOL``.
SCAN = 2001
XTOL = 1e-14


def power(delta, p: float, runs_old: int, runs_new: int, alpha: float):  # type: ignore[no-untyped-def]
    """The power of one input's two-sided test to see the share move from ``p`` to ``p + delta``;
    ``delta`` a number or an array of them."""
    raised = p + np.asarray(delta, dtype=np.float64)
    pooled = (runs_old * p + runs_new * raised) / (runs_old + runs_new)
    se_null = np.sqrt(pooled * (1.0 - pooled) * (1.0 / runs_old + 1.0 / runs_new))
    se_alt = np.sqrt(p * (1.0 - p) / runs_old + raised * (1.0 - raised) / runs_new)
    z = stats.norm.ppf(1.0 - alpha / 2.0)
    return stats.norm.cdf((delta - z * se_null) / se_alt) + stats.norm.cdf((-delta - z * se_null) / se_alt)


def limit(p: float, runs_old: int, runs_new: int, *, alpha: float, power_wanted: float) -> float:
    """The smallest rise from ``p`` that one input's own test catches with ``power_wanted``."""
    if p >= 1.0:
        return math.nan
    base = 0.5 / runs_old if p <= 0.0 else p
    top = 1.0 - base
    grid = np.linspace(0.0, top, SCAN)
    reached = power(grid, base, runs_old, runs_new, alpha) >= power_wanted
    if not reached[-1]:
        return 1.0 - p
    first = int(np.argmax(reached))
    return float(optimize.brentq(
        lambda d: float(power(d, base, runs_old, runs_new, alpha)) - power_wanted,
        float(grid[first - 1]), float(grid[first]), xtol=XTOL,
    ))
