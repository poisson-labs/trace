"""The continuous measures: whether time, length, tokens or cost changed between two runs.

For each measure the two runs are paired by case. Within a case the tries are averaged, the
paired case difference is new minus old, and the difference is read three ways: a sign-flip test
(exact to 20 changed cases, then 100,000 drawn flips), the Student t range for the mean change,
and the Hodges-Lehmann estimate for the typical case with its Walsh-average range. Holm's
step-down holds the measures that can be called to one family. A measure that cannot be called
says what happened instead: *identical*, *changed on n of K cases*, or *too small to tell*.

Spec section 18.6 as ruled on 2026-11-03 (CS1 to CS14) is what this module implements; the
reading of each ruling is noted beside the code that carries it. The inputs are plain, so that
the readers that fill them from a store (TF21) can come later: a :class:`Version` holds, per
case, its :class:`Try` objects, each with its value per measure, how it ended, its behavioural
signals and its repeat number.

Nothing here writes, prints or reads a file. :func:`table` gives a header and rows for
``look.table``; no verb prints it yet.

numpy and scipy only.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np
import numpy.typing as npt
from scipy import stats

FloatArray = npt.NDArray[np.float64]

#: The measures, in the order they are reported.
MEASURES: tuple[str, ...] = (
    "wall_time_s",
    "working_time_s",
    "input_chars",
    "output_chars",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cost_usd",
)
#: Compared only on the cases both versions finished (CS7): time, and output length.
FINISHED_ONLY: tuple[str, ...] = ("wall_time_s", "working_time_s", "output_chars")
#: The measures a timeout cap cuts.
TIMES: tuple[str, ...] = ("wall_time_s", "working_time_s")
#: The one measure that is shown and never tested: the sum of the other two token counts (CS5).
SHOWN_ONLY = "total_tokens"
#: How a try can end early without doing the work (CS7); the ``gave_up`` signal is the fifth.
EARLY: tuple[str, ...] = ("crash", "rate_limit", "abstained", "guardrail_blocked")
GAVE_UP = "gave_up"
TIMEOUT = "timeout"

#: Each measure's two direction words, the lower first (section 18.6.1 item 3).
WORDS: dict[str, tuple[str, str]] = {
    "wall_time_s": ("faster", "slower"),
    "working_time_s": ("faster", "slower"),
    "input_chars": ("shorter", "longer"),
    "output_chars": ("shorter", "longer"),
    "input_tokens": ("fewer tokens", "more tokens"),
    "output_tokens": ("fewer tokens", "more tokens"),
    "total_tokens": ("fewer tokens", "more tokens"),
    "cost_usd": ("cheaper", "costlier"),
}

#: The sign-flip test is exact up to this many changed cases, and draws this many flips above
#: it (CS12).
EXACT_MAX = 20
FLIPS = 100_000
#: A *different* call needs this many changed cases and this many paired cases (CS1).
FLOOR_CHANGED = 9
FLOOR_PAIRED = 10
#: The smallest catchable change is printed from this many paired cases (CS6); the quantiles
#: P90 and P95 are given from this many (CS11).
MDE_SIZE_FROM = 15
QUANTILES_FROM = 20
#: The tail-spike label needs the typical case's range inside this share of the old P50 (CS11).
TAIL_SHARE = 0.05
#: The exact table for the typical case's range is built to this many cases; above, the large-
#: sample formula stands in.
HL_EXACT_MAX = 1000

_BLOCK = 10_000
_TIE = 1e-12
#: A share of the old mean (the relative change, the smallest catchable change's share, the
#: cases needed) is left out of the lines when it is not finite or is at least this large,
#: past which it prints as hundreds of digits and says nothing (HY1, SV11).
PRINTABLE = 1e12


# ---------- the estimators ----------


def seed(run_a: str, run_b: str, measure: str) -> int:
    """The seed every random step of a comparison draws from: the SHA-256 of
    ``run_a:run_b:measure`` read as a whole number (the seed rule, IC5)."""
    return int(hashlib.sha256(f"{run_a}:{run_b}:{measure}".encode()).hexdigest(), 16)


def _array(d: npt.ArrayLike) -> FloatArray:
    return np.asarray(d, dtype=np.float64).ravel()


def _reach(nz: FloatArray) -> float:
    """What a sign vector's absolute sum must reach to count as at least the observed one, a
    hair below it so that sums equal up to rounding are ties."""
    observed = abs(float(nz.sum()))
    return observed - _TIE * (observed + float(np.abs(nz).sum()))


def _subset_sums(x: FloatArray) -> FloatArray:
    sums = np.zeros(1)
    for v in x:
        sums = np.concatenate((sums + v, sums - v))
    return sums


def _exact_count(nz: FloatArray, reach: float) -> int:
    """How many of the 2^k sign vectors have an absolute sum of at least ``reach``, counted
    from the two halves' signed sums so that 20 differences cost two thousand sums, not a
    million."""
    half = nz.size // 2
    left = _subset_sums(nz[:half])
    right = np.sort(_subset_sums(nz[half:]))
    if reach <= 0.0:
        return int(left.size * right.size)
    above = right.size - np.searchsorted(right, reach - left, side="left")
    below = np.searchsorted(right, -reach - left, side="right")
    return int(above.sum() + below.sum())


def signflip_p(d: npt.ArrayLike, seed: int) -> float:
    """The two-sided sign-flip p of the case differences ``d``, over the changed cases only
    (a zero difference moves with no sign). Exact up to :data:`EXACT_MAX` changed cases; above,
    ``(1 + count) / (1 + FLIPS)`` over :data:`FLIPS` random sign vectors from ``seed`` (CS12),
    so never 0. The studentized statistic of the spec gives this p: on every sign vector its
    size rises with the size of the sum."""
    nz = _array(d)
    nz = nz[nz != 0.0]
    k = int(nz.size)
    if k == 0:
        return 1.0
    reach = _reach(nz)
    if k <= EXACT_MAX:
        return _exact_count(nz, reach) / 2.0**k
    rng = np.random.default_rng(seed)
    count = 0
    left = FLIPS
    while left > 0:
        n = min(_BLOCK, left)
        bits = rng.integers(0, 2, size=(n, k), dtype=np.int8)
        sums = 2.0 * (bits @ nz) - float(nz.sum())
        count += int((np.abs(sums) >= reach).sum())
        left -= n
    return (1 + count) / (1 + FLIPS)


def p_floor(k_nonzero: int) -> float:
    """The smallest two-sided p a sign-flip test can reach with ``k_nonzero`` changed cases:
    both unanimous flips are always as extreme as the observed one. 1 at no change."""
    if k_nonzero <= 0:
        return 1.0
    return 2.0 ** (1 - k_nonzero)


def t_range(d: npt.ArrayLike, alpha: float = 0.05) -> tuple[float, float]:
    """The Student t range for the mean of ``d`` (CS3), at level ``1 - alpha``."""
    x = _array(d)
    k = int(x.size)
    if k < 2:
        raise ValueError("a range for the mean needs at least two cases")
    half = float(stats.t.ppf(1.0 - alpha / 2.0, k - 1)) * float(x.std(ddof=1)) / math.sqrt(k)
    mean = float(x.mean())
    return mean - half, mean + half


def _walsh(x: FloatArray) -> FloatArray:
    i, j = np.triu_indices(x.size)
    return np.sort((x[i] + x[j]) / 2.0)


def hodges_lehmann(d: npt.ArrayLike) -> float:
    """The typical case's change (CS11): the median of the Walsh averages, the mean of every
    pair of differences (a case with itself included)."""
    return float(np.median(_walsh(_array(d))))


@lru_cache(maxsize=16)
def _signed_rank_cdf(n: int) -> FloatArray:
    """P(W+ <= w) for the Wilcoxon signed-rank statistic of ``n`` cases with no ties, for
    w = 0 .. n(n+1)/2."""
    top = n * (n + 1) // 2
    p = np.zeros(top + 1)
    p[0] = 1.0
    for r in range(1, n + 1):
        shifted = p[:-r].copy()
        p[r:] = 0.5 * (p[r:] + shifted)
        p[:r] = 0.5 * p[:r]
    return np.cumsum(p)


def hl_range(d: npt.ArrayLike, alpha: float = 0.05) -> tuple[float, float]:
    """The exact Walsh-average range for the typical case's change (Hollander, Wolfe and
    Chicken 2014, section 3.3): the C-th smallest and C-th largest Walsh average, C - 1 the
    largest w with P(W+ <= w) <= alpha / 2. Unbounded where that does not exist (fewer than six
    cases). Above :data:`HL_EXACT_MAX` cases the table is not built and C comes from the normal
    approximation to W+."""
    x = _array(d)
    n = int(x.size)
    w = _walsh(x)
    if n <= HL_EXACT_MAX:
        below = np.nonzero(_signed_rank_cdf(n) <= alpha / 2.0)[0]
        if below.size == 0:
            return -math.inf, math.inf
        c = int(below[-1])
    else:
        z = float(stats.norm.ppf(1.0 - alpha / 2.0))
        spread = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
        c = max(0, math.floor(n * (n + 1) / 4.0 - z * spread))
    return float(w[c]), float(w[w.size - 1 - c])


def mde(d: npt.ArrayLike, alpha: float = 0.05) -> float:
    """The smallest change the test would catch 4 times in 5 at level ``alpha``, from the
    spread of ``d``: ``(t(1 - alpha/2) + t(0.80)) * s / sqrt(K)`` with K - 1 degrees of freedom
    (section 18.6.1 item 3). The caller gives the level the test is held to (CS5)."""
    x = _array(d)
    k = int(x.size)
    if k < 2:
        raise ValueError("a smallest catchable change needs at least two cases")
    factor = float(stats.t.ppf(1.0 - alpha / 2.0, k - 1)) + float(stats.t.ppf(0.8, k - 1))
    return factor * float(x.std(ddof=1)) / math.sqrt(k)


def k_needed(k: int, mde: float, delta: float) -> int | None:
    """The cases a run would need to catch a change of ``delta`` when ``k`` cases caught
    ``mde``: ``ceil(k (mde / delta)^2)``. None where that is not a finite number a run could
    hold (a ceiling set against a near-zero old mean, HY1 as SV11 reads it)."""
    if delta <= 0.0:
        raise ValueError("the change to catch must be above zero")
    try:
        x = k * (mde / delta) ** 2
    except (OverflowError, ZeroDivisionError):
        return None
    if not math.isfinite(x) or x >= PRINTABLE:
        return None
    return max(1, math.ceil(x - 1e-9 * max(1.0, x)))


def share_of(part: float, whole: float) -> float | None:
    """``part / whole`` where that is a finite share a line can print; None where ``whole`` is
    zero or the share is not finite or too large to print (HY1)."""
    if whole == 0.0:
        return None
    try:
        share = part / whole
    except (OverflowError, ZeroDivisionError):
        return None
    if not math.isfinite(share) or abs(share) >= PRINTABLE:
        return None
    return share


def _holm_steps(p: Mapping[str, float], alpha: float) -> dict[str, tuple[bool, float]]:
    order = sorted(p, key=lambda name: p[name])
    m = len(order)
    steps: dict[str, tuple[bool, float]] = {}
    stopped = False
    for i, name in enumerate(order):
        threshold = alpha / (m - i)
        called = not stopped and p[name] < threshold
        stopped = stopped or not called
        steps[name] = (called, threshold)
    return {name: steps[name] for name in p}


def holm(p: Mapping[str, float], alpha: float = 0.05) -> dict[str, bool]:
    """Holm's step-down: the i-th smallest p of m is held to ``alpha / (m - i + 1)``, and the
    first that misses stops it (CS5)."""
    return {name: called for name, (called, _) in _holm_steps(p, alpha).items()}


_CEILING = re.compile(r"^(\d+(?:\.\d+)?)%$")


def parse_max_change(text: str) -> tuple[str, float]:
    """``measure=N%`` as the measure and a fraction: ``wall_time_s=10%`` is
    ``("wall_time_s", 0.10)`` (CS10). Anything else is refused with a ValueError saying why."""
    measure, sep, value = text.strip().partition("=")
    measure, value = measure.strip(), value.strip()
    if not sep:
        raise ValueError(f"{text!r} is not measure=N%, for example wall_time_s=10%")
    if measure not in MEASURES:
        raise ValueError(f"{measure!r} is not a measure; the measures are {', '.join(MEASURES)}")
    if measure == SHOWN_ONLY:
        raise ValueError(
            "total_tokens is shown, not tested, so it takes no ceiling; "
            "name input_tokens or output_tokens"
        )
    m = _CEILING.match(value)
    if m is None:
        raise ValueError(f"{value!r} is not a percentage of the old mean, for example 10%")
    fraction = float(m.group(1)) / 100.0
    if fraction <= 0.0:
        raise ValueError("a ceiling of 0% can never be met; give a share above 0%")
    return measure, fraction


# ---------- the inputs ----------


@dataclass(frozen=True)
class Try:
    """One try of one case: its value per measure (``None`` where the source did not record
    it), how it ended (a failure kind, or ``None`` for a try that finished), its behavioural
    signals, and its repeat number (``None`` where no order was recorded)."""

    values: Mapping[str, float | None]
    ending: str | None = None
    signals: Sequence[str] = ()
    repeat: int | None = None


@dataclass(frozen=True)
class Version:
    """One run: its id, the tries of each case, a label for sentences, and the cap on one try's
    time in seconds where the run had one."""

    name: str
    cases: Mapping[str, Sequence[Try]]
    label: str = "old"
    cap_s: float | None = None


def _value(t: Try, measure: str) -> float | None:
    v = t.values.get(measure)
    if v is None:
        return None
    x = float(v)
    return x if math.isfinite(x) else None


def _ordered(version: Version, case: str, measure: str) -> list[Try]:
    """A case's tries in the order recorded; tries with no recorded order follow, drawn by the
    seed rule keyed on the run, the case and the measure (CS14)."""
    tries = list(version.cases[case])
    known = sorted((t for t in tries if t.repeat is not None), key=lambda t: t.repeat or 0)
    loose = [t for t in tries if t.repeat is None]
    if len(loose) > 1:
        rng = np.random.default_rng(seed(version.name, case, measure))
        loose = [loose[i] for i in rng.permutation(len(loose))]
    return known + loose


def _early_kind(tries: Sequence[Try]) -> str | None:
    """How a case ended early in one version, if any of its tries did (CS7)."""
    for t in tries:
        if t.ending in EARLY:
            return str(t.ending)
        signals = (t.signals,) if isinstance(t.signals, str) else t.signals
        if GAVE_UP in signals:
            return GAVE_UP
    return None


# ---------- one measure's reading of the pairs ----------


@dataclass
class _Gathered:
    cases: list[str] = field(default_factory=list)
    old: list[float] = field(default_factory=list)
    new: list[float] = field(default_factory=list)
    tries_old: list[int] = field(default_factory=list)
    tries_new: list[int] = field(default_factory=list)
    finished: list[bool] = field(default_factory=list)
    unfinished_old: dict[str, int] = field(default_factory=dict)
    unfinished_new: dict[str, int] = field(default_factory=dict)
    timed_out_old: int = 0
    timed_out_new: int = 0
    k_total: int = 0
    left_out: int = 0
    no_value: int = 0
    recorded: bool = False


def _gather(
    measure: str, a: Version, b: Version, shared: Sequence[str], cap_low: float | None
) -> _Gathered:
    """Pair the shared cases for one measure (section 18.6.1 items 1 and 4)."""
    g = _Gathered(k_total=len(shared))
    cut_at = cap_low if measure in TIMES else None
    for case in shared:
        ea, eb = _early_kind(a.cases[case]), _early_kind(b.cases[case])
        if ea is not None:
            g.unfinished_old[ea] = g.unfinished_old.get(ea, 0) + 1
        if eb is not None:
            g.unfinished_new[eb] = g.unfinished_new.get(eb, 0) + 1
        va = [(t, x) for t in _ordered(a, case, measure) if (x := _value(t, measure)) is not None]
        vb = [(t, x) for t in _ordered(b, case, measure) if (x := _value(t, measure)) is not None]
        both = bool(va) and bool(vb)
        g.recorded = g.recorded or both
        early = ea is not None or eb is not None
        if early and measure in FINISHED_ONLY:
            g.left_out += 1
            continue
        if not both:
            g.no_value += 1
            continue
        n = min(len(va), len(vb))
        means = []
        for used in (va[:n], vb[:n]):
            values = []
            timed = False
            for t, x in used:
                cut = cut_at is not None and x > cut_at
                values.append(cut_at if cut and cut_at is not None else x)
                timed = timed or cut or t.ending == TIMEOUT
            means.append((math.fsum(values) / n, timed))
        g.cases.append(case)
        g.old.append(means[0][0])
        g.new.append(means[1][0])
        g.timed_out_old += int(means[0][1])
        g.timed_out_new += int(means[1][1])
        g.tries_old.append(len(va))
        g.tries_new.append(len(vb))
        g.finished.append(not early)
    return g


# ---------- the result ----------


def _clean(x: float | None) -> float | None:
    return None if x is None or not math.isfinite(x) else float(x)


@dataclass
class Measure:
    """What the comparison says of one measure. ``status`` is ``not_recorded`` (no shared case
    has it in both versions), ``under_floor`` (fewer than 10 paired cases), ``identical`` (every
    difference zero), ``few_changed`` (1 to 8 changed cases), ``not_tested`` (total tokens),
    or ``tested``. ``verdict`` is ``different``, ``unconfirmed``, ``no significant difference``
    or ``too small to tell``, and ``None`` where there is none to give. ``lines`` is what the
    measure says, in words."""

    measure: str
    status: str
    verdict: str | None = None
    direction: str | None = None
    k_total: int = 0
    k_paired: int = 0
    k_nonzero: int = 0
    mean_a: float | None = None
    mean_b: float | None = None
    p50_a: float | None = None
    p50_b: float | None = None
    p90_a: float | None = None
    p90_b: float | None = None
    p95_a: float | None = None
    p95_b: float | None = None
    change: float | None = None
    relative: float | None = None
    lo: float | None = None
    hi: float | None = None
    rough: bool | None = None
    p_value: float | None = None
    p_floor: float | None = None
    threshold: float | None = None
    hl: float | None = None
    hl_lo: float | None = None
    hl_hi: float | None = None
    mde: float | None = None
    k_needed: int | None = None
    tail_spike: bool | None = None
    unfinished: dict[str, tuple[tuple[str, int], ...]] = field(default_factory=dict)
    timed_out: dict[str, int] = field(default_factory=dict)
    changes: list[tuple[str, float]] = field(default_factory=list)
    cases: list[str] = field(default_factory=list)
    d: list[float] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """The measure as plain JSON values: no NaN, no infinity."""
        return {
            "measure": self.measure,
            "status": self.status,
            "verdict": self.verdict,
            "direction": self.direction,
            "k_total": self.k_total,
            "k_paired": self.k_paired,
            "k_nonzero": self.k_nonzero,
            "mean_a": _clean(self.mean_a),
            "mean_b": _clean(self.mean_b),
            "p50_a": _clean(self.p50_a),
            "p50_b": _clean(self.p50_b),
            "p90_a": _clean(self.p90_a),
            "p90_b": _clean(self.p90_b),
            "p95_a": _clean(self.p95_a),
            "p95_b": _clean(self.p95_b),
            "change": _clean(self.change),
            "relative": _clean(self.relative),
            "lo": _clean(self.lo),
            "hi": _clean(self.hi),
            "rough": self.rough,
            "p_value": _clean(self.p_value),
            "p_floor": _clean(self.p_floor),
            "threshold": _clean(self.threshold),
            "hl": _clean(self.hl),
            "hl_lo": _clean(self.hl_lo),
            "hl_hi": _clean(self.hl_hi),
            "mde": _clean(self.mde),
            "k_needed": self.k_needed,
            "tail_spike": self.tail_spike,
            "unfinished": {
                label: {kind: n for kind, n in kinds} for label, kinds in self.unfinished.items()
            },
            "timed_out": dict(self.timed_out),
            "changes": [[case, _clean(v)] for case, v in self.changes],
            "cases": list(self.cases),
            "d": [_clean(x) for x in self.d],
            "lines": list(self.lines),
        }


@dataclass
class Comparison:
    """Two versions compared on every measure. ``family`` is the measures that could be
    called on this pair, in the order of :data:`MEASURES`."""

    old: Version
    new: Version
    alpha: float
    ceilings: dict[str, float]
    measures: dict[str, Measure]
    family: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "versions": [
                {"name": v.name, "label": v.label, "cap_s": v.cap_s} for v in (self.old, self.new)
            ],
            "alpha": self.alpha,
            "ceilings": dict(self.ceilings),
            "family": list(self.family),
            "measures": [m.to_dict() for m in self.measures.values()],
        }


# ---------- the words ----------

_NAMES = {
    "wall_time_s": "wall time",
    "working_time_s": "working time",
    "input_chars": "input length",
    "output_chars": "output length",
    "input_tokens": "input tokens",
    "output_tokens": "output tokens",
    "total_tokens": "total tokens",
    "cost_usd": "cost",
}
_SUFFIX = {
    "wall_time_s": " s",
    "working_time_s": " s",
    "input_chars": " chars",
    "output_chars": " chars",
    "input_tokens": " tokens",
    "output_tokens": " tokens",
    "total_tokens": " tokens",
    "cost_usd": "",
}
# what a few cases doing far more would do to the range (CS4): "If a few cases {this} than the
# rest, this range can miss a rise."
_FAR = {
    "wall_time_s": "took far longer",
    "working_time_s": "took far longer",
    "input_chars": "were far longer",
    "output_chars": "were far longer",
    "input_tokens": "used far more tokens",
    "output_tokens": "used far more tokens",
    "total_tokens": "used far more tokens",
    "cost_usd": "cost far more",
}


def _num(x: float, digits: int = 3) -> str:
    """``x`` to ``digits`` significant figures, with thousands separators and no trailing
    zeros."""
    if x == 0.0:
        return "0"
    places = min(12, max(0, digits - 1 - math.floor(math.log10(abs(x)))))
    text = f"{abs(x):,.{places}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return ("-" if x < 0 and text != "0" else "") + text


def _amount(measure: str, x: float, *, signed: bool = False, unit: bool = True) -> str:
    body = _num(abs(x))
    sign = "" if body == "0" else ("-" if x < 0 else ("+" if signed else ""))
    if measure == "cost_usd":
        return f"{sign}${body}"
    return f"{sign}{body}{_SUFFIX[measure] if unit else ''}"


def _pct(x: float) -> str:
    text = _num(x * 100.0, 2)
    return f"{'+' if x > 0 and text != '0' else ''}{text}%"


def _p(p: float) -> str:
    return _num(p) if p >= 0.001 else f"{p:.2e}"


def _span(measure: str, lo: float, hi: float) -> str:
    """A range in words: ``from 0.3 s faster to 0.5 s slower``."""
    low, high = WORDS[measure]
    unit = not measure.endswith("tokens")  # "120 fewer tokens", not "120 tokens fewer tokens"

    def side(x: float) -> str:
        return f"{_amount(measure, abs(x), unit=unit)} {low if x < 0 else high}"

    return f"from {side(lo)} to {side(hi)}"


def _between(measure: str, lo: float, hi: float) -> str:
    """A range as signed amounts: ``-0.1 s to +0.4 s``."""
    return f"{_amount(measure, lo, signed=True)} to {_amount(measure, hi, signed=True)}"


def _kinds(counts: Mapping[str, int]) -> str:
    return ", ".join(f"{n} {kind}" for kind, n in sorted(counts.items()))


def _level(alpha: float) -> str:
    return f"{_num((1.0 - alpha) * 100.0, 3)}%"


# ---------- the comparison ----------


def _check_ceilings(ceilings: Mapping[str, float] | None) -> dict[str, float]:
    out: dict[str, float] = {}
    for measure, fraction in (ceilings or {}).items():
        if measure not in MEASURES or measure == SHOWN_ONLY:
            raise ValueError(f"{measure!r} takes no ceiling")
        if not (math.isfinite(fraction) and fraction > 0.0):
            raise ValueError(f"the ceiling for {measure} must be a share above 0")
        out[measure] = float(fraction)
    return out


def _described(measure: str, g: _Gathered, status: str) -> Measure:
    """The measure with its counts and descriptive summary, from the paired cases."""
    ya, yb = np.array(g.old), np.array(g.new)
    d = yb - ya
    k = int(d.size)
    m = Measure(measure=measure, status=status, k_total=g.k_total, k_paired=k)
    m.k_nonzero = int((d != 0.0).sum())
    m.cases = list(g.cases)
    m.d = [float(x) for x in d]
    if k:
        m.mean_a, m.mean_b = float(ya.mean()), float(yb.mean())
        m.change = float(d.mean())
        m.relative = share_of(m.change, m.mean_a)
        m.p50_a, m.p50_b = float(np.median(ya)), float(np.median(yb))
        if k >= QUANTILES_FROM:
            m.p90_a, m.p90_b = (float(np.quantile(v, 0.9)) for v in (ya, yb))
            m.p95_a, m.p95_b = (float(np.quantile(v, 0.95)) for v in (ya, yb))
    return m


def _summary_line(m: Measure) -> str:
    assert m.mean_a is not None and m.mean_b is not None and m.change is not None
    assert m.p50_a is not None and m.p50_b is not None
    rel = f", {_pct(m.relative)}" if m.relative is not None else ""
    text = (
        f"Over {m.k_paired} paired cases: old mean {_amount(m.measure, m.mean_a)}, new mean "
        f"{_amount(m.measure, m.mean_b)} (change {_amount(m.measure, m.change, signed=True)}"
        f"{rel}); middle case (P50) {_amount(m.measure, m.p50_a)} old, "
        f"{_amount(m.measure, m.p50_b)} new"
    )
    if m.p90_a is not None and m.p90_b is not None:
        text += f"; P90 {_amount(m.measure, m.p90_a)} old, {_amount(m.measure, m.p90_b)} new"
    return text + "."


def _tries_line(a: Version, b: Version, g: _Gathered) -> str | None:
    """Say so when the two versions had different numbers of tries per case (CS14)."""
    if g.tries_old == g.tries_new:
        return None
    sa, sb = set(g.tries_old), set(g.tries_new)
    if len(sa) == 1 and len(sb) == 1:
        x, y = g.tries_old[0], g.tries_new[0]
        noun = "try" if x == 1 else "tries"
        return (
            f"Tries: {a.label} had {x} {noun} per case, {b.label} had {y}; "
            f"compared on {min(x, y)} each."
        )

    def spread(counts: set[int]) -> str:
        return f"{min(counts)} to {max(counts)}" if min(counts) != max(counts) else f"{min(counts)}"

    return (
        f"Tries per case differed ({a.label} {spread(sa)}, {b.label} {spread(sb)}); each case "
        f"was compared on as many tries of each as the version with fewer had."
    )


def _left_out_lines(measure: str, a: Version, b: Version, g: _Gathered) -> list[str]:
    """What was left out of the comparison, and the caveat that goes with it (CS8)."""
    lines: list[str] = []
    if measure in FINISHED_ONLY and (g.left_out or g.unfinished_old or g.unfinished_new):
        both = g.k_total - g.left_out
        text = f"This reading is on the {both} of {g.k_total} cases both versions finished"
        for v, counts in ((a, g.unfinished_old), (b, g.unfinished_new)):
            if counts:
                n = sum(counts.values())
                noun = "case" if n == 1 else "cases"
                text += f"; {v.label} did not finish {n} {noun} ({_kinds(counts)})"
        lines.append(text + ".")
        if g.left_out:
            lines.append(
                "Nothing here can catch a change hidden in cases a version did not finish, "
                "when those cases look like the rest."
            )
    if g.no_value:
        lines.append(
            f"{g.no_value} of the {g.k_total} shared cases had no measurement of "
            f"{_NAMES[measure]} in one version."
        )
    if measure in TIMES and (g.timed_out_old or g.timed_out_new):
        lines.append(
            f"Timeouts stay in, at the lower cap where the caps differ: {a.label} timed out on "
            f"{g.timed_out_old} {'case' if g.timed_out_old == 1 else 'cases'}, {b.label} on "
            f"{g.timed_out_new}."
        )
    tries = _tries_line(a, b, g)
    if tries:
        lines.append(tries)
    return lines


def compare(
    a: Version,
    b: Version,
    *,
    ceilings: Mapping[str, float] | None = None,
    alpha: float = 0.05,
) -> Comparison:
    """Compare ``a`` (the old version) with ``b`` (the new) on every measure.

    ``ceilings`` gives, per measure, the share of the old mean that a change may reach and still
    count as no difference, chosen before looking (CS10). ``alpha`` is the level of the tests
    and ranges."""
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between 0 and 1")
    if a.label == b.label:
        raise ValueError("the two versions need different labels")
    ceil = _check_ceilings(ceilings)
    shared = sorted(c for c in a.cases if c in b.cases and a.cases[c] and b.cases[c])
    cap_low = None
    if a.cap_s is not None and b.cap_s is not None and a.cap_s != b.cap_s:
        cap_low = min(a.cap_s, b.cap_s)

    gathered = {m: _gather(m, a, b, shared, cap_low) for m in MEASURES}
    readings: dict[str, Measure] = {}
    pending: dict[str, float] = {}
    for measure in MEASURES:
        g = gathered[measure]
        if not g.recorded:
            m = _described(measure, g, "not_recorded")
            m.lines = ["not recorded"]
        elif measure == SHOWN_ONLY:
            m = _described(measure, g, "not_tested")
        elif len(g.cases) < FLOOR_PAIRED:
            m = _described(measure, g, "under_floor")
        else:
            m = _described(measure, g, "tested")
            if m.k_nonzero == 0:
                m.status = "identical"
            elif m.k_nonzero < FLOOR_CHANGED:
                m.status = "few_changed"
            else:
                pending[measure] = signflip_p(m.d, seed(a.name, b.name, measure))
                m.p_value = pending[measure]
        m.unfinished = {
            a.label: tuple(sorted(g.unfinished_old.items())),
            b.label: tuple(sorted(g.unfinished_new.items())),
        }
        m.timed_out = {a.label: g.timed_out_old, b.label: g.timed_out_new}
        readings[measure] = m

    steps = _holm_steps(pending, alpha)
    family = tuple(m for m in MEASURES if m in pending)
    for measure in MEASURES:
        m = readings[measure]
        g = gathered[measure]
        if m.status == "not_recorded":
            continue
        _speak(m, g, a, b, ceil.get(measure), alpha, steps.get(measure), len(family))
    return Comparison(old=a, new=b, alpha=alpha, ceilings=ceil, measures=readings, family=family)


def _speak(
    m: Measure,
    g: _Gathered,
    a: Version,
    b: Version,
    fraction: float | None,
    alpha: float,
    step: tuple[bool, float] | None,
    family: int,
) -> None:
    """Fill in the verdict and the words of one measure."""
    measure = m.measure
    lines: list[str] = []
    if m.status == "under_floor":
        m.verdict = "too small to tell"
        m.p_floor = p_floor(m.k_nonzero)
        lines.append(
            f"too small to tell (K_paired = {m.k_paired}, K_nonzero = {m.k_nonzero}; exact "
            f"sign-flip floor is p = {_p(m.p_floor)}, so a two-sided test cannot call a change "
            f"below {FLOOR_CHANGED} changed cases and {FLOOR_PAIRED} paired cases; at "
            f"{FLOOR_CHANGED} every changed case must move the same way, at {FLOOR_PAIRED} at "
            f"most one may go the other way)."
        )
        if m.k_paired:
            lines.append(_summary_line(m))
    elif m.status == "not_tested":
        lines.append(
            "shown, not tested: total tokens is the sum of input tokens and output tokens, "
            "which are tested."
        )
        lines.append(_summary_line(m))
    elif m.status == "identical":
        k = m.k_paired
        lines.append(
            f"identical on all {k} cases; a change touching more than about 3 in {k} cases like "
            f"these would usually have shown up."
        )
    elif m.status == "few_changed":
        m.verdict = "too small to tell"
        m.changes = [(c, x) for c, x in zip(m.cases, m.d, strict=True) if x != 0.0]
        shown = ", ".join(f"{c} {_amount(measure, x, signed=True)}" for c, x in m.changes)
        # math.fsum, not sum(): the same bytes on every Python (3.12's sum() differs from 3.11's)
        total = _amount(measure, math.fsum(x for _, x in m.changes), signed=True)
        lines.append(
            f"changed on {m.k_nonzero} of {m.k_paired} cases ({shown}; together {total}); "
            f"too small to tell."
        )
        lines.append(
            f"A test needs {FLOOR_CHANGED} changed cases before it can call a difference, so "
            f"this says what happened and nothing more."
        )
        lines.append(_summary_line(m))
    else:
        assert step is not None
        _speak_tested(m, g, a, b, fraction, alpha, step, family, lines)
    m.lines = lines if m.status == "not_tested" else [*lines, *_left_out_lines(measure, a, b, g)]


def _speak_tested(
    m: Measure,
    g: _Gathered,
    a: Version,
    b: Version,
    fraction: float | None,
    alpha: float,
    step: tuple[bool, float],
    family: int,
    lines: list[str],
) -> None:
    measure = m.measure
    called, m.threshold = step
    assert m.p_value is not None and m.mean_a is not None and m.change is not None
    d = np.array(m.d)
    level = _level(alpha)
    m.lo, m.hi = t_range(d, alpha)
    m.rough = (m.lo > 0.0 or m.hi < 0.0) != (m.p_value < alpha)
    m.hl, (m.hl_lo, m.hl_hi) = hodges_lehmann(d), hl_range(d, alpha)
    m.mde = mde(d, alpha / family)
    rel = f" ({_pct(m.relative)})" if m.relative is not None else ""
    typical = (
        f"For the typical case (Hodges-Lehmann estimate) the change is "
        f"{_amount(measure, m.hl, signed=True)} ({level} range "
        f"{_between(measure, m.hl_lo, m.hl_hi)})."
    )
    low, high = WORDS[measure]
    if called:
        up = m.change > 0.0
        m.direction = high if up else low
        favoured, other = ("a", "b") if up else ("b", "a")
        unf = {"a": sum(g.unfinished_old.values()), "b": sum(g.unfinished_new.values())}
        timed = {"a": g.timed_out_old, "b": g.timed_out_new}
        who = {"a": a, "b": b}
        hidden = measure in FINISHED_ONLY and (
            unf[favoured] > unf[other] or timed[favoured] > timed[other]
        )
        n_way = sum(1 for x in m.d if (x > 0.0) == up and x != 0.0)
        excludes = m.lo > 0.0 if up else m.hi < 0.0
        if hidden:
            m.verdict = "unconfirmed"
            lines.append(
                f"unconfirmed: the test reads {m.direction} (p = {_p(m.p_value)}), but "
                f"{who[favoured].label} left more cases unfinished or timed out on more than "
                f"{who[other].label} did. A version that stops on its hard cases looks better "
                f"on the cases it finished, so the call is not confirmed."
            )
        else:
            m.verdict = "different"
            if excludes:
                lines.append(
                    f"different: {m.direction}. The mean changed by "
                    f"{_amount(measure, m.change, signed=True)}{rel}; {level} range "
                    f"{_between(measure, m.lo, m.hi)}; p = {_p(m.p_value)}."
                )
            else:
                # the sign-flip test saw a change the mean's range does not (CS13): say what moved
                where = (
                    f"on most cases ({n_way} of {m.k_paired})"
                    if 2 * n_way > m.k_paired
                    else f"on {n_way} of {m.k_paired} cases"
                )
                lines.append(
                    f"different: {m.direction} {where}; the mean did not clearly move "
                    f"({_span(measure, m.lo, m.hi)}; p = {_p(m.p_value)})."
                )
            stopped = unf[favoured]
            if measure not in FINISHED_ONLY and stopped > unf[other]:
                both = [x for x, f in zip(m.d, g.finished, strict=True) if f]
                if len(both) >= 2:
                    seen = _between(measure, *t_range(both, alpha))
                else:
                    seen = "too few cases to give a range"
                lines.append(
                    f"This reads {m.direction}, partly because {who[favoured].label} stopped "
                    f"early on {stopped} cases (on the {len(both)} cases both finished: {seen})."
                )
        lines.append(typical)
        if m.verdict == "different":
            half = TAIL_SHARE * (m.p50_a or 0.0)
            m.tail_spike = (
                m.p50_a is not None and m.p50_a > 0.0 and -half <= m.hl_lo and m.hl_hi <= half
            )
            if m.tail_spike:
                lines.append(
                    "tail spike (mean shifted, median flat): the typical case's range lies "
                    f"inside {_num(TAIL_SHARE * 100)}% of the old middle case."
                )
        else:
            m.tail_spike = False
    else:
        quiet = f"the test is quiet (p = {_p(m.p_value)}; a call needs p below {_p(m.threshold)})"
        delta = fraction * m.mean_a if fraction is not None and m.mean_a > 0.0 else None
        inside = delta is not None and m.lo >= -delta and m.hi <= delta
        if inside and not m.rough:
            assert delta is not None and fraction is not None
            m.verdict = "no significant difference"
            lines.append(
                f"no significant difference: {quiet} and the {level} range for the mean "
                f"change, {_between(measure, m.lo, m.hi)}, lies inside the ceiling you set, "
                f"±{_amount(measure, delta)} ({_num(fraction * 100.0, 3)}% of the old mean)."
            )
            lines.append(
                f"If a few cases {_FAR[measure]} than the rest, this range can miss a rise."
            )
        else:
            m.verdict = "too small to tell"
            if m.k_paired >= MDE_SIZE_FROM:
                mde_share = share_of(m.mde, m.mean_a) if m.mean_a > 0.0 else None
                pct = f" ({_num(mde_share * 100.0, 2)}%)" if mde_share is not None else ""
                lines.append(
                    f"too small to tell: {quiet}, and changes smaller than about "
                    f"±{_amount(measure, m.mde)}{pct} could easily go unseen in a run like this."
                )
            else:
                lines.append(f"too small to tell: {quiet}.")
            lines.append(f"In words, these results fit anything {_span(measure, m.lo, m.hi)}.")
            if m.rough:
                lines.append(
                    f"The {level} range is rough: it and the test disagree about whether "
                    f"anything changed, so it is not read against the ceiling."
                )
            if delta is not None and fraction is not None:
                m.k_needed = k_needed(m.k_paired, m.mde, delta)
                if m.k_needed is not None:
                    lines.append(
                        f"To tell a change of ±{_amount(measure, delta)} "
                        f"({_num(fraction * 100.0, 3)}% of the old mean) from none, about "
                        f"{m.k_needed} cases would be needed. Runs built to an estimate like "
                        f"this often end up a little too small."
                    )
                else:
                    # the ceiling is a share of an old mean so near zero that no run could
                    # hold the cases needed (HY1, SV11)
                    lines.append(
                        f"To tell a change of ±{_amount(measure, delta)} "
                        f"({_num(fraction * 100.0, 3)}% of the old mean) from none would take "
                        f"more cases than a run could hold: the old mean is too near zero for "
                        f"a share of it to be caught."
                    )
            else:
                lines.append(
                    f"To decide, choose how much change would not matter before you look, as a "
                    f"share of the old mean: --max-change {measure}=X%."
                )
        lines.append(typical)
    lines.append(_summary_line(m))


# ---------- the table ----------


def table(comparison: Comparison, technical: bool = False) -> tuple[list[str], list[list[str]]]:
    """The comparison as a header and rows for ``look.table``: one row a measure shown, in the
    order of :data:`MEASURES`, its first cell the measure, its ``change`` the relative change
    alone (``none`` for no change, ``-`` for none to give), and its last the verdict word with
    its direction after a comma when there is one (``different, slower``; DM3). The absolute
    change stays in the measure's lines. A measure no case recorded is left out, and shown as
    ``not recorded`` with ``technical``, which also adds the range and the p."""
    header = ["measure", "old", "new", "change"]
    if technical:
        header += ["95% range", "p"]
    header.append("verdict")
    rows: list[list[str]] = []
    for name in MEASURES:
        m = comparison.measures[name]
        if m.status == "not_recorded" and not technical:
            continue
        rows.append(_row(m, technical))
    return header, rows


_WORD = {
    "not_recorded": "not recorded",
    "not_tested": "not tested",
    "identical": "identical",
}


def _row(m: Measure, technical: bool) -> list[str]:
    name = m.measure
    dash = "-"
    if m.status == "not_recorded":
        old = new = change = dash
    else:
        old = _amount(name, m.mean_a) if m.mean_a is not None else dash
        new = _amount(name, m.mean_b) if m.mean_b is not None else dash
        if m.change is None:
            change = dash
        elif m.status == "identical" or m.change == 0.0:
            change = "none"
        elif m.relative is not None:
            change = _pct(m.relative)
        else:
            change = dash  # the old mean too near zero for a share of it (HY1)
    cells = [name, old, new, change]
    if technical:
        cells.append(
            f"{_amount(name, m.lo, signed=True)} to {_amount(name, m.hi, signed=True)}"
            if m.lo is not None and m.hi is not None
            else dash
        )
        cells.append(_p(m.p_value) if m.p_value is not None else dash)
    word = _WORD.get(m.status) or m.verdict or dash
    cells.append(f"{word}, {m.direction}" if m.direction else word)
    return cells
