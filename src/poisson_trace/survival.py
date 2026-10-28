"""The estimators: Aalen-Johansen with competing ends and a band from resampling inputs, the
stratified log-rank with its own information, the detection limit and the tries it takes, the
one-step hazard ratio, and Benjamini-Hochberg. Kaplan-Meier, the try-level bootstrap and
Schoenfeld's formula stay as functions; no report prints them.

numpy and scipy only.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping, Sequence
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


# ---------- where: competing ends, banded by resampling inputs ----------

# How a placed try ended, beside the kinds of step it failed at: finishing without failing and
# timing out are ends of their own; a try at the cap is censored at its step.
DIED, FINISHED, TIMED_OUT, CAPPED = "died", "ended", "timed out", "capped"
# A share within this of one half counts as one half.
_HALF_TOLERANCE = 1e-9
# Bootstrap resamples are summed this many at a time.
_BOOT_BLOCK = 1_000

# One placed try: its input, its step, how it ended, and the kind of step it failed at.
Try = tuple[str, int, str, str]


@dataclass(frozen=True)
class _Ends:
    """One run's tries as counts per input and step: ``at_risk[c, t]`` tries of input ``c`` at
    or past ``steps[t]``, ``ends[c, j, t]`` of them ending there by end ``j`` (the failure kinds
    in order, then timed out, then finished). A capped try is at risk up to its step and ends
    nowhere."""

    steps: np.ndarray
    at_risk: np.ndarray
    ends: np.ndarray
    kinds: int


def _ends(cells: Sequence[str], rows: Sequence[Try], causes: Sequence[str]) -> _Ends:
    kinds = len(causes)
    code = {c: i for i, c in enumerate(causes)}
    steps = np.unique(np.array([r[1] for r in rows], dtype=np.int64))
    where_cell = {c: i for i, c in enumerate(cells)}
    at_risk = np.zeros((len(cells), len(steps)), dtype=np.float64)
    ends = np.zeros((len(cells), kinds + 2, len(steps)), dtype=np.float64)
    for cell, step, end, cause in rows:
        c = where_cell[cell]
        t = int(np.searchsorted(steps, step))
        at_risk[c, : t + 1] += 1.0
        if end == DIED:
            ends[c, code[cause], t] += 1.0
        elif end == TIMED_OUT:
            ends[c, kinds, t] += 1.0
        elif end == FINISHED:
            ends[c, kinds + 1, t] += 1.0
        elif end != CAPPED:
            raise ValueError(f"unknown end {end!r}")
    return _Ends(steps=steps, at_risk=at_risk, ends=ends, kinds=kinds)


def _cumulative(at_risk: np.ndarray, ends: np.ndarray) -> np.ndarray:
    """Aalen-Johansen from counts summed over inputs: ``at_risk`` is ``(..., T)`` and ``ends``
    ``(..., J, T)``; each end's cumulative incidence, ``(..., J, T)``."""
    risk = at_risk[..., None, :]
    with np.errstate(divide="ignore", invalid="ignore"):
        hazard = np.where(risk > 0, ends / np.where(risk > 0, risk, 1.0), 0.0)
    going = np.cumprod(1.0 - hazard.sum(axis=-2), axis=-1)
    before = np.concatenate([np.ones_like(going[..., :1]), going[..., :-1]], axis=-1)
    out: np.ndarray = np.cumsum(before[..., None, :] * hazard, axis=-1)
    return out


def _at(steps: np.ndarray, values: np.ndarray, at: Sequence[int], start: float) -> np.ndarray:
    """The right-continuous step function ``values`` (last axis over ``steps``) at each of
    ``at``; ``start`` before the first step."""
    # a step asked beyond a machine word reads as the far end; no try's step comes near it
    held = [min(max(int(q), -(2**62)), 2**62) for q in at]
    positions = np.searchsorted(steps, np.asarray(held, dtype=np.int64), side="right") - 1
    if values.shape[-1] == 0:
        return np.full(values.shape[:-1] + (len(positions),), start)
    out = np.take(values, np.maximum(positions, 0), axis=-1)
    return np.where(positions >= 0, out, start)


def _not_failed(incidence: np.ndarray, kinds: int) -> np.ndarray:
    out: np.ndarray = 1.0 - incidence[..., :kinds, :].sum(axis=-2)
    return out


@dataclass(frozen=True)
class Competing:
    """The share of tries not yet failed, by step, with finishing and timing out as ends of
    their own and only capped tries censored (Aalen-Johansen). ``steps`` are the steps where a
    try failed; ``final`` holds each kind's share failed by the run's last step, and
    ``timed_out`` the share that timed out."""

    steps: np.ndarray
    at_risk: np.ndarray
    failed: np.ndarray
    share: np.ndarray
    causes: tuple[str, ...]
    incidence: Mapping[str, np.ndarray]
    final: Mapping[str, float]
    timed_out: float
    grid: np.ndarray
    not_failed: np.ndarray

    def at(self, steps: Sequence[int]) -> np.ndarray:
        """The share not yet failed at each of ``steps``."""
        return _at(self.grid, self.not_failed, steps, 1.0)

    def half(self) -> int | None:
        """The first step by which half of all tries had failed, or ``None``."""
        hits = np.flatnonzero(1.0 - self.share >= 0.5 - _HALF_TOLERANCE)
        return None if len(hits) == 0 else int(self.steps[hits[0]])


def competing(rows: Sequence[Try], causes: Sequence[str]) -> Competing:
    """Aalen-Johansen over ``rows``, the failure kinds ``causes`` in order."""
    keys = tuple(dict.fromkeys(causes))
    e = _ends(sorted({r[0] for r in rows}), rows, keys)
    at_risk, ends = e.at_risk.sum(axis=0), e.ends.sum(axis=0)
    incidence = _cumulative(at_risk, ends)
    not_failed = _not_failed(incidence, e.kinds)
    failed = ends[: e.kinds].sum(axis=0)
    hit = failed > 0
    last = incidence[:, -1] if len(e.steps) else np.zeros(e.kinds + 2)
    return Competing(
        steps=e.steps[hit],
        at_risk=at_risk[hit].astype(np.int64),
        failed=failed[hit].astype(np.int64),
        share=not_failed[hit],
        causes=keys,
        incidence={k: incidence[i, hit] for i, k in enumerate(keys)},
        final={k: float(last[i]) for i, k in enumerate(keys)},
        timed_out=float(last[e.kinds]),
        grid=e.steps,
        not_failed=not_failed,
    )


def _percentiles(draws: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return np.percentile(draws, 2.5, axis=0), np.percentile(draws, 97.5, axis=0)


def _resampled(cells: int, b: int, seed: int) -> Iterator[np.ndarray]:
    """``b`` resamples of the inputs, with replacement, as counts per input, a block at a
    time."""
    rng = np.random.default_rng(seed)
    left = b
    while left > 0:
        block = min(_BOOT_BLOCK, left)
        yield rng.multinomial(cells, np.full(cells, 1.0 / cells), size=block).astype(np.float64)
        left -= block


def _resampled_incidence(e: _Ends, weights: np.ndarray) -> np.ndarray:
    return _cumulative(weights @ e.at_risk, np.einsum("bc,cjt->bjt", weights, e.ends))


@dataclass(frozen=True)
class CompetingBand:
    """95% percentile bands from resampling inputs: the share not yet failed at the curve's
    failure steps and at the steps asked, and each kind's share, and timed out's, at the
    end."""

    curve: tuple[np.ndarray, np.ndarray]
    at: tuple[np.ndarray, np.ndarray]
    final: Mapping[str, tuple[float, float]]
    timed_out: tuple[float, float]


def competing_band(
    rows: Sequence[Try], causes: Sequence[str], at: Sequence[int], *, b: int, seed: int
) -> CompetingBand:
    """The bootstrap that resamples inputs: each input drawn brings all its tries."""
    keys = tuple(dict.fromkeys(causes))
    cells = sorted({r[0] for r in rows})
    e = _ends(cells, rows, keys)
    hit = np.flatnonzero(e.ends[:, : e.kinds].sum(axis=(0, 1)) > 0)
    curve, asked, final = [], [], []
    for weights in _resampled(len(cells), b, seed):
        incidence = _resampled_incidence(e, weights)
        not_failed = _not_failed(incidence, e.kinds)
        curve.append(not_failed[:, hit])
        asked.append(_at(e.steps, not_failed, at, 1.0))
        final.append(incidence[:, :, -1] if len(e.steps) else np.zeros((len(weights), e.kinds + 2)))
    lo_f, hi_f = _percentiles(np.concatenate(final))
    return CompetingBand(
        curve=_percentiles(np.concatenate(curve)),
        at=_percentiles(np.concatenate(asked)),
        final={k: (float(lo_f[i]), float(hi_f[i])) for i, k in enumerate(keys)},
        timed_out=(float(lo_f[e.kinds]), float(hi_f[e.kinds])),
    )


def difference_band(
    a: Sequence[Try],
    b: Sequence[Try],
    causes: Sequence[str],
    at: Sequence[int],
    *,
    draws: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """The 95% band of ``b``'s share not yet failed minus ``a``'s at each of ``at``, from
    resampling the inputs of the two runs together: an input drawn brings both runs' tries on
    it, so an input the runs share is drawn for both at once."""
    keys = tuple(dict.fromkeys(causes))
    cells = sorted({r[0] for r in a} | {r[0] for r in b})
    e_a, e_b = _ends(cells, a, keys), _ends(cells, b, keys)
    out = []
    for weights in _resampled(len(cells), draws, seed):
        share_a = _at(
            e_a.steps, _not_failed(_resampled_incidence(e_a, weights), e_a.kinds), at, 1.0
        )
        share_b = _at(
            e_b.steps, _not_failed(_resampled_incidence(e_b, weights), e_b.kinds), at, 1.0
        )
        out.append(share_b - share_a)
    return _percentiles(np.concatenate(out))


# ---------- compare: the log-rank's own information ----------


def _z(alpha: float, power: float) -> float:
    return float(stats.norm.isf(alpha / 2.0)) + float(stats.norm.ppf(power))


def information_limit(variance: float, *, alpha: float = 0.05, power: float = 0.8) -> float | None:
    """The smallest hazard ratio the stratified log-rank detects at ``power``, two-sided at
    ``alpha``, from its own information ``V``: ``exp((z_{1-alpha/2} + z_power) / sqrt(V))``.
    ``None`` where ``V`` is not positive."""
    if not variance > 0.0:
        return None
    return math.exp(_z(alpha, power) / math.sqrt(variance))


def one_step(lr: LogRank, *, level: float = 0.95) -> tuple[float, float, float] | None:
    """The hazard ratio of arm B against arm A from the log-rank's own numbers, Peto's one-step
    estimate ``exp(-(O_A - E_A) / V)``, and its range ``exp(log H -+ z / sqrt(V))``. ``None``
    where ``V`` is not positive."""
    if not lr.variance > 0.0:
        return None
    log_h = -(lr.observed_a - lr.expected_a) / lr.variance
    half = float(stats.norm.isf((1.0 - level) / 2.0)) / math.sqrt(lr.variance)
    return math.exp(log_h), math.exp(log_h - half), math.exp(log_h + half)


def fit_cells(rows: Sequence[tuple[str, int, bool]]) -> dict[str, tuple[int, float, float]]:
    """The per-input model the tries guidance reads: each input an offset one below its
    smallest step and two exponential clocks per step after it, failing and ending otherwise,
    their rates fitted from ``rows`` (``(cell, step, died)``, both runs pooled)."""
    cells: dict[str, list[tuple[int, bool]]] = {}
    for cell, step, died in rows:
        cells.setdefault(cell, []).append((int(step), bool(died)))
    fit = {}
    for cell, tries in cells.items():
        offset = min(s for s, _ in tries) - 1
        exposure = sum(s - offset for s, _ in tries)
        failed = sum(1 for _, d in tries if d)
        fit[cell] = (offset, failed / exposure, (len(tries) - failed) / exposure)
    return fit


# The sum over steps in the expected information stops where what is left is below this.
_TAIL = 1e-13
_MOST_STEPS = 1_000_000


def expected_information(fit: Mapping[str, tuple[int, float, float]], repeats: int) -> float:
    """The stratified log-rank's expected variance under no change, ``repeats`` tries per input
    in each run drawn from ``fit``, each try's step rounded up to a whole step after its
    input's offset. In closed form, the limit of drawing such runs without end: at the ``k``-th
    step after the offset each run's tries still going are binomial with ``p = q^(k-1)``,
    ``q = exp(-(failing + ending))``; a try going fails there with
    ``h = (1 - q) failing / (failing + ending)``; and the variance's term at that step has
    expectation ``h (1 - h) R / (2 (2R - 1)) (2Rp - 1 + (1 - p)^(2R))``."""
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    r = float(repeats)
    total = 0.0
    for _, failing, ending in fit.values():
        rate = failing + ending
        if not failing > 0.0 or not rate > 0.0:
            continue
        q = math.exp(-rate)
        h = (1.0 - q) * failing / rate
        if q > 0.0:
            # what is left after k steps is below (2R q^k)^2 / (2 (1 - q^2))
            room = math.log(_TAIL * 2.0 * max(-math.expm1(2.0 * math.log(q)), 1e-300)) / 2.0
            k = math.ceil((room - math.log(2.0 * r)) / math.log(q)) + 1
            k = min(_MOST_STEPS, max(1, k))
        else:
            k = 1
        p = q ** np.arange(k, dtype=np.float64)
        with np.errstate(divide="ignore"):
            terms = 2.0 * r * p + np.expm1(2.0 * r * np.log1p(-p))
        total += h * (1.0 - h) * r / (2.0 * (2.0 * r - 1.0)) * float(terms.sum())
    return total


def information_needed(ratio: float, *, alpha: float = 0.05, power: float = 0.8) -> float | None:
    """The log-rank information that detects ``ratio`` at ``power``: ``(z / ln ratio)^2``;
    ``None`` for a ratio of 1 or below."""
    if not ratio > 1.0:
        return None
    return (_z(alpha, power) / math.log(ratio)) ** 2


_TRIES_CEILING = 2**30


def tries_needed(
    fit: Mapping[str, tuple[int, float, float]],
    ratio: float,
    *,
    alpha: float = 0.05,
    power: float = 0.8,
) -> int | None:
    """The smallest number of tries per input per run whose expected information under no
    change reaches what ``ratio`` needs; ``None`` where no number does."""
    target = information_needed(ratio, alpha=alpha, power=power)
    if target is None:
        return None

    def reaches(n: int) -> bool:
        return expected_information(fit, n) >= target

    hi = 1
    while not reaches(hi):
        hi *= 2
        if hi > _TRIES_CEILING:
            return None
    lo = hi // 2
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if reaches(mid):
            hi = mid
        else:
            lo = mid
    return hi
