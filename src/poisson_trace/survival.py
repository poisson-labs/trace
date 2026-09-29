"""The estimators: Kaplan-Meier with Greenwood, Aalen-Johansen with a bootstrap band, the
stratified log-rank, Schoenfeld's minimum detectable hazard ratio, and Benjamini-Hochberg.

numpy and scipy only.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from scipy import stats

_Z95 = 1.96


@dataclass(frozen=True)
class KMCurve:
    steps: np.ndarray
    at_risk: np.ndarray
    deaths: np.ndarray
    survival: np.ndarray
    var: np.ndarray

    def at(self, step: int) -> tuple[float, float]:
        """``(S, var)`` at ``step``: the right-continuous value, ``(1, 0)`` before the first
        death."""
        i = int(np.searchsorted(self.steps, step, side="right")) - 1
        if i < 0:
            return 1.0, 0.0
        return float(self.survival[i]), float(self.var[i])

    def median(self) -> int | None:
        hits = np.flatnonzero(self.survival <= 0.5)
        return None if len(hits) == 0 else int(self.steps[hits[0]])


@dataclass(frozen=True)
class AJCurve:
    steps: np.ndarray
    causes: tuple[str, ...]
    incidence: Mapping[str, np.ndarray]
    survival: np.ndarray


@dataclass(frozen=True)
class LogRank:
    cells: int
    observed_a: float
    expected_a: float
    variance: float
    statistic: float
    p: float


def _band(s: float, var: float) -> tuple[float, float]:
    """The plain Greenwood 95% band, clipped to ``[0, 1]``."""
    half = _Z95 * math.sqrt(var)
    return max(0.0, s - half), min(1.0, s + half)


def kaplan_meier(index: np.ndarray, died: np.ndarray) -> KMCurve:
    idx = np.asarray(index, dtype=np.int64)
    obs = np.asarray(died, dtype=bool)
    steps = np.unique(idx[obs])
    at_risk = np.array([np.sum(idx >= x) for x in steps], dtype=np.int64)
    deaths = np.array([np.sum((idx == x) & obs) for x in steps], dtype=np.int64)
    n = at_risk.astype(np.float64)
    d = deaths.astype(np.float64)
    survival = np.cumprod((n - d) / n, dtype=np.float64)
    # Greenwood: sum d / (n (n - d)); the n == d term is taken as 0, which holds the sum at
    # its last finite value.
    with np.errstate(divide="ignore", invalid="ignore"):
        term = np.where(n > d, d / (n * (n - d)), 0.0)
    var = survival**2 * np.cumsum(term)
    return KMCurve(steps=steps, at_risk=at_risk, deaths=deaths, survival=survival, var=var)


def _incidence(
    idx: np.ndarray, obs: np.ndarray, code: np.ndarray, k: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(steps, F, S)``: ``F`` is ``k`` rows of cumulative incidence, one per cause code,
    and ``S`` the all-cause survival, both over the distinct death steps."""
    steps = np.unique(idx[obs])
    m = len(steps)
    if m == 0:
        return steps, np.zeros((k, 0), dtype=np.float64), np.zeros(0, dtype=np.float64)
    n = (len(idx) - np.searchsorted(np.sort(idx), steps, side="left")).astype(np.float64)
    pos = np.searchsorted(steps, idx[obs])
    d_total = np.bincount(pos, minlength=m).astype(np.float64)
    tracked = obs & (code >= 0)
    flat = code[tracked] * m + np.searchsorted(steps, idx[tracked])
    d_k = np.bincount(flat, minlength=k * m).reshape(k, m).astype(np.float64)
    survival = np.cumprod((n - d_total) / n, dtype=np.float64)
    s_prev = np.concatenate([[1.0], survival[:-1]])
    incidence = np.cumsum(s_prev * d_k / n, axis=1)
    return steps, incidence, survival


def _codes(cause: np.ndarray, causes: Sequence[str]) -> np.ndarray:
    lookup = {c: i for i, c in enumerate(causes)}
    return np.array([lookup.get(c, -1) for c in cause], dtype=np.int64)


def aalen_johansen(
    index: np.ndarray, died: np.ndarray, cause: np.ndarray, causes: Sequence[str]
) -> AJCurve:
    idx = np.asarray(index, dtype=np.int64)
    obs = np.asarray(died, dtype=bool)
    keys = tuple(dict.fromkeys(causes))
    steps, incidence, survival = _incidence(idx, obs, _codes(np.asarray(cause), keys), len(keys))
    return AJCurve(
        steps=steps,
        causes=keys,
        incidence={key: incidence[i] for i, key in enumerate(keys)},
        survival=survival,
    )


def _value_at(steps: np.ndarray, values: np.ndarray, at: Sequence[int]) -> np.ndarray:
    """The right-continuous step function ``values`` over ``steps``, at each of ``at``; 0 before
    the first step."""
    positions = np.searchsorted(steps, np.asarray(at, dtype=np.int64), side="right") - 1
    out = np.zeros(len(at), dtype=np.float64)
    hit = positions >= 0
    out[hit] = values[positions[hit]]
    return out


def bootstrap_band(
    index: np.ndarray,
    died: np.ndarray,
    cause: np.ndarray,
    causes: Sequence[str],
    at: Sequence[int],
    *,
    b: int,
    seed: int,
) -> Mapping[str, tuple[np.ndarray, np.ndarray]]:
    idx = np.asarray(index, dtype=np.int64)
    obs = np.asarray(died, dtype=bool)
    keys = tuple(dict.fromkeys(causes))
    code = _codes(np.asarray(cause), keys)
    n = len(idx)
    rng = np.random.default_rng(seed)
    draws = np.zeros((b, len(keys), len(at)), dtype=np.float64)
    for r in range(b):
        pick = rng.integers(0, n, n)
        steps, incidence, _ = _incidence(idx[pick], obs[pick], code[pick], len(keys))
        for i in range(len(keys)):
            draws[r, i] = _value_at(steps, incidence[i], at)
    return {
        key: (np.percentile(draws[:, i], 2.5, axis=0), np.percentile(draws[:, i], 97.5, axis=0))
        for i, key in enumerate(keys)
    }


def _by_cell(rows: Sequence[tuple[str, int, bool]]) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    cells: dict[str, tuple[list[int], list[bool]]] = {}
    for cell, index, died in rows:
        t, o = cells.setdefault(cell, ([], []))
        t.append(int(index))
        o.append(bool(died))
    return {
        cell: (np.array(t, dtype=np.int64), np.array(o, dtype=bool))
        for cell, (t, o) in cells.items()
    }


def logrank_stratified(
    a: Sequence[tuple[str, int, bool]], b: Sequence[tuple[str, int, bool]]
) -> LogRank:
    """The two-sample log-rank stratified by cell over the cells both arms carry: within each
    cell, at each distinct death step, the observed deaths in ``a`` minus the expected under a
    common hazard, and the hypergeometric variance, summed over steps and cells."""
    arm_a, arm_b = _by_cell(a), _by_cell(b)
    cells = sorted(set(arm_a) & set(arm_b))
    observed = expected = variance = 0.0
    for cell in cells:
        t_a, o_a = arm_a[cell]
        t_b, o_b = arm_b[cell]
        for x in np.unique(np.concatenate([t_a[o_a], t_b[o_b]])):
            n_a = int(np.sum(t_a >= x))
            n_b = int(np.sum(t_b >= x))
            n = n_a + n_b
            d_a = int(np.sum((t_a == x) & o_a))
            d_b = int(np.sum((t_b == x) & o_b))
            d = d_a + d_b
            if n == 0 or d == 0:
                continue
            observed += d_a
            expected += n_a * d / n
            if n > 1:
                variance += n_a * n_b * d * (n - d) / (n * n * (n - 1))
    if variance <= 0.0:
        statistic, p = 0.0, 1.0
    else:
        statistic = (observed - expected) ** 2 / variance
        p = float(stats.chi2.sf(statistic, 1))
    return LogRank(
        cells=len(cells),
        observed_a=observed,
        expected_a=expected,
        variance=variance,
        statistic=float(statistic),
        p=p,
    )


def mde_hazard_ratio(
    deaths: int, share_a: float, *, alpha: float = 0.05, power: float = 0.8
) -> float:
    """Schoenfeld: the smallest hazard ratio a two-sample log-rank with ``deaths`` deaths and a
    share ``share_a`` of rows in arm A detects at ``power``, two-sided at ``alpha``."""
    if deaths <= 0:
        raise ValueError("the minimum detectable hazard ratio needs at least one death")
    if not 0.0 < share_a < 1.0:
        raise ValueError("share_a must be strictly between 0 and 1")
    z = float(stats.norm.isf(alpha / 2.0)) + float(stats.norm.ppf(power))
    return math.exp(z / math.sqrt(deaths * share_a * (1.0 - share_a)))


def bh(p: np.ndarray, q: float) -> np.ndarray:
    """Benjamini-Hochberg adjusted q-values, the same shape as ``p``. ``q`` names the level the
    caller reports against; the adjusted values do not depend on it."""
    arr = np.asarray(p, dtype=np.float64)
    m = arr.size
    if m == 0:
        return np.empty(0, dtype=np.float64)
    flat = arr.reshape(-1)
    order = np.argsort(flat, kind="stable")
    ranked = flat[order]
    raw = ranked * m / np.arange(1, m + 1, dtype=np.float64)
    adjusted = np.minimum.accumulate(raw[::-1])[::-1]
    adjusted = np.minimum(adjusted, 1.0)
    out = np.empty(m, dtype=np.float64)
    out[order] = adjusted
    return out.reshape(arr.shape)


def deaths_needed(
    max_mde_hr: float, share_a: float, *, alpha: float = 0.05, power: float = 0.8
) -> int:
    """Schoenfeld inverted: the smallest number of deaths whose minimum detectable hazard
    ratio is at most ``max_mde_hr``. The closed form gives the neighbourhood and
    ``mde_hazard_ratio`` itself settles the integer, so the two cannot disagree."""
    if not max_mde_hr > 1.0:
        raise ValueError("no number of deaths detects a hazard ratio of 1 or below")
    if not 0.0 < share_a < 1.0:
        raise ValueError("share_a must be strictly between 0 and 1")
    z = float(stats.norm.isf(alpha / 2.0)) + float(stats.norm.ppf(power))
    deaths = max(1, math.ceil((z / math.log(max_mde_hr)) ** 2 / (share_a * (1.0 - share_a))))
    while mde_hazard_ratio(deaths, share_a, alpha=alpha, power=power) > max_mde_hr:
        deaths += 1
    while deaths > 1 and mde_hazard_ratio(deaths - 1, share_a, alpha=alpha, power=power) <= (
        max_mde_hr
    ):
        deaths -= 1
    return deaths
