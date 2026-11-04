"""What the continuous-measures tests (TF23) share: builders for two versions' tries, the
continuous statistics check's own methods and data generators, copied here as the outside
reference, and small readers of a measure's words.

Not a test module and not collected.

**The reference.** Every function under "the check's methods" and "the check's generators" is
copied, unchanged but for names and the removal of what these tests do not use, from the
continuous statistics check (vault ``poisson labs/projects/trace/log/trace-continuous-statistics-check/``,
on vault main at 1569790d): ``evidence/scripts/cslib.py``, ``evidence/scripts/sim_crash.py`` and
``evidence/review/scripts/r1_shape_null.py`` and ``r3_tip_stress.py``. They are the code that
produced the check's tables, at the check's seeds, so a test that rebuilds a table's row from
them and gets the row the check printed shows the data here are the check's data. Nothing in
this file is Trace code, and nothing in it reads ``poisson_trace``.

**The contract under test** is ``poisson_trace.stats.continuous`` (spec section 18.6 as ruled on
2026-11-03, CS1 to CS14). Its inputs are plain: a :class:`Version` of a run holds, per case, the
tries of that case, and each try holds its value per measure (``None`` where the source did not
record it), how it ended (a failure kind of section 18.5, or ``None``), its behavioural signals,
and its repeat index. The readers that fill these from a store are TF21's; these tests build
them by hand.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Mapping, Sequence
from functools import cache
from typing import Any

import numpy as np

MEASURES = (
    "wall_time_s", "working_time_s", "input_chars", "output_chars",
    "input_tokens", "output_tokens", "total_tokens", "cost_usd",
)
# compared only on cases both versions finished (CS7)
FINISHED_ONLY = ("wall_time_s", "working_time_s", "output_chars")
# compared on every shared case with a value (section 18.6.1 item 4, CS9)
ALL_PAIRS = ("input_chars", "input_tokens", "output_tokens", "total_tokens", "cost_usd")
EARLY_KINDS = ("crash", "rate_limit", "abstained", "guardrail_blocked")
# each measure's two direction words, the lower first
WORDS = {
    "wall_time_s": ("faster", "slower"), "working_time_s": ("faster", "slower"),
    "input_chars": ("shorter", "longer"), "output_chars": ("shorter", "longer"),
    "input_tokens": ("fewer tokens", "more tokens"), "output_tokens": ("fewer tokens", "more tokens"),
    "total_tokens": ("fewer tokens", "more tokens"), "cost_usd": ("cheaper", "costlier"),
}


def cm():  # type: ignore[no-untyped-def]
    """The module under test, imported late so a missing module fails each test on its own."""
    from poisson_trace.stats import continuous

    return continuous


def norm(text: str) -> str:
    return " ".join(text.replace("–", "-").replace("—", "-").replace("−", "-").split())


def words(measure: Any) -> str:
    """Every line a measure prints, as one normalised text."""
    return norm(" ".join(measure.lines))


# ---------- building two versions ----------


def tries(values: Sequence[float | None], measure: str = "wall_time_s", **kw: Any) -> list[Any]:
    """One try per value, repeats 0, 1, ... in order, every other field from ``kw``."""
    T = cm().Try
    return [T(values={measure: v}, repeat=i, **kw) for i, v in enumerate(values)]


def version(
    name: str,
    label: str,
    per_case: Mapping[str, Sequence[Any]],
    cap_s: float | None = None,
) -> Any:
    return cm().Version(name=name, label=label, cases=dict(per_case), cap_s=cap_s)


def one_measure(
    a: Sequence[float | None],
    b: Sequence[float | None],
    measure: str = "wall_time_s",
    *,
    ends_a: Sequence[str | None] | None = None,
    ends_b: Sequence[str | None] | None = None,
    names: tuple[str, str] = ("run-a", "run-b"),
) -> tuple[Any, Any]:
    """Two versions with one try per case on cases ``c00, c01, ...``, one measure recorded."""
    T = cm().Try
    ea = ends_a or [None] * len(a)
    eb = ends_b or [None] * len(b)
    va = {f"c{i:02d}": [T(values={measure: v}, ending=e, repeat=0)] for i, (v, e) in enumerate(zip(a, ea))}
    vb = {f"c{i:02d}": [T(values={measure: v}, ending=e, repeat=0)] for i, (v, e) in enumerate(zip(b, eb))}
    return version(names[0], "old", va), version(names[1], "new", vb)


def from_differences(d: Sequence[float], measure: str = "wall_time_s", base: float = 100.0) -> tuple[Any, Any]:
    """Two versions whose per-case differences, new minus old, are ``d`` exactly: old is ``base``
    on every case and new is ``base + d_i``. ``base`` keeps every value positive."""
    return one_measure([base] * len(d), [base + x for x in d], measure)


def several(
    columns: Mapping[str, tuple[Sequence[float], Sequence[float]]],
    names: tuple[str, str] = ("run-a", "run-b"),
) -> tuple[Any, Any]:
    """Two versions, one try per case, several measures: ``{measure: (old values, new values)}``,
    every column the same length."""
    T = cm().Try
    k = len(next(iter(columns.values()))[0])
    va = {f"c{i:02d}": [T(values={m: float(v[0][i]) for m, v in columns.items()}, repeat=0)] for i in range(k)}
    vb = {f"c{i:02d}": [T(values={m: float(v[1][i]) for m, v in columns.items()}, repeat=0)] for i in range(k)}
    return version(names[0], "old", va), version(names[1], "new", vb)


def run(a: Any, b: Any, **kw: Any) -> Any:
    return cm().compare(a, b, **kw)


# ---------- the check's methods (cslib.py) ----------


@cache
def ref_all_flips(k: int) -> np.ndarray:
    if k == 0:
        return np.ones((1, 0))
    return np.array(list(itertools.product((1.0, -1.0), repeat=k)))


def ref_signflip_p(d: np.ndarray, rng: np.random.Generator, plus_one: bool = False,
                   exact_max: int = 14, flips: int = 10_000) -> float:
    """cslib.signflip_p: the sign-flip p through the sum, exact over the non-zero differences up
    to ``exact_max`` of them, else ``flips`` random sign vectors from ``rng``."""
    nz = d[d != 0]
    k = len(nz)
    if k == 0:
        return 1.0
    if k <= exact_max:
        f, exact = ref_all_flips(k), True
    else:
        f, exact = rng.choice((-1.0, 1.0), size=(flips, k)), False
    s = f @ nz
    s0 = abs(nz.sum())
    count = int((np.abs(s) >= s0 * (1 - 1e-12) - 1e-12).sum())
    n = len(f)
    if not exact and plus_one:
        return (count + 1) / (n + 1)
    return count / n


def ref_exact_signflip_p(d: Iterable[float]) -> float:
    """The exact sign-flip p by brute force over every sign vector, in blocks so 2^21 fits."""
    nz = np.array([x for x in d if x != 0], dtype=float)
    k = len(nz)
    if k == 0:
        return 1.0
    s0 = abs(nz.sum()) * (1 - 1e-12) - 1e-12
    head, tail = nz[: min(k, 12)], nz[min(k, 12):]
    hs = ref_all_flips(len(head)) @ head
    count = 0
    for signs in (ref_all_flips(len(tail)) if len(tail) else np.ones((1, 0))):
        count += int((np.abs(hs + signs @ tail) >= s0).sum())
    return count / 2.0**k


def ref_walsh(d: np.ndarray) -> np.ndarray:
    i, j = np.triu_indices(len(d))
    return np.sort((d[i] + d[j]) / 2.0)


@cache
def ref_signed_rank_cdf(n: int) -> np.ndarray:
    top = n * (n + 1) // 2
    counts = np.zeros(top + 1)
    counts[0] = 1.0
    for r in range(1, n + 1):
        counts[r:] = counts[r:] + counts[:-r].copy() if r <= top else counts[r:]
    return np.cumsum(counts) / 2.0**n


def ref_hl_interval(d: np.ndarray, alpha: float = 0.05) -> tuple[float, float]:
    """cslib.hl_interval: order statistics C and M + 1 - C of the M Walsh averages, C - 1 the
    largest w with P(W+ <= w) <= alpha / 2 (Hollander, Wolfe & Chicken 2014, section 3.3)."""
    w = ref_walsh(d)
    cdf = ref_signed_rank_cdf(len(d))
    below = np.nonzero(cdf <= alpha / 2)[0]
    if len(below) == 0:
        return -np.inf, np.inf
    c = int(below[-1])
    return float(w[c]), float(w[len(w) - 1 - c])


def ref_draw(shape: str, rng: np.random.Generator, size: int) -> np.ndarray:
    """cslib.draw, the shapes the validation data sets use."""
    if shape == "normal":
        return rng.standard_normal(size)
    if shape == "t3":
        return rng.standard_t(3, size)
    if shape == "lognormal15":
        return rng.lognormal(0.0, 1.5, size) - np.exp(1.125)
    if shape == "pareto25":
        return rng.pareto(2.5, size) - 1.0 / 1.5
    if shape == "zeroinf_skew":
        keep = rng.random(size) < 0.5
        return np.where(keep, rng.lognormal(0.0, 1.0, size) - np.exp(0.5), 0.0)
    if shape == "integer":
        return (rng.poisson(2.0, size) - rng.poisson(2.0, size)).astype(float)
    raise KeyError(shape)


def ref_seed_for(*parts: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([20261103, *parts]))


def validate_data() -> list[np.ndarray]:
    """The six data sets of the check's validate.py, item 1 (sims/00-validate.txt)."""
    rng = ref_seed_for(0)
    return [
        np.array([1.83, 0.50, 1.62, 2.48, 1.68, 1.88, 1.55, 3.06, 1.30, -0.4]),
        ref_draw("lognormal15", rng, 12) + 0.3,
        ref_draw("pareto25", rng, 15),
        ref_draw("zeroinf_skew", rng, 11) + 0.1,
        ref_draw("integer", rng, 13),
        ref_draw("t3", rng, 30),
    ]


# ---------- the check's generators ----------

STORM_P, STORM_X = 0.03, 6.0


def r1_lat(rng: np.random.Generator, base: float, reps: int, sd: float = 0.4, storms: bool = True,
           mult: float = 1.0, all_tries: bool = False) -> Any:
    """r1_shape_null.lat: one case's tries on one version, run-shaped latency; their mean, or the
    tries themselves with ``all_tries``."""
    y = base * mult * np.exp(rng.normal(0, sd, reps))
    if storms:
        y = y * np.where(rng.random(reps) < STORM_P, STORM_X, 1.0)
    return y if all_tries else y.mean()


def r1_reps(scenario: str, k: int, reps: int):  # type: ignore[no-untyped-def]
    """r1_shape_null.cell's draws for ``scenario`` at ``k`` cases, rep by rep, the generator moved
    on exactly as r1 moves it (its sign-flip p draws from the same stream). Yields, per rep, the
    tries per case of each version and r1's own reading of that rep: its sign-flip p (10,000 flips,
    plus one) and whether its t-test called it at 0.05."""
    from scipy import stats

    si = ("unequal_1v5", "mixed_reps", "steadier_B").index(scenario)
    rng = np.random.default_rng(np.random.SeedSequence([20261103, 901, si, k]))
    for _ in range(reps):
        base = np.exp(rng.normal(np.log(5.0), 1.0, k))
        if scenario == "unequal_1v5":
            ta = [r1_lat(rng, x, 1, all_tries=True) for x in base]
            tb = [r1_lat(rng, x, 5, all_tries=True) for x in base]
        elif scenario == "steadier_B":
            m = (1 - STORM_P + STORM_P * STORM_X) * np.exp(0.4**2 / 2 - 0.1**2 / 2)
            ta = [r1_lat(rng, x, 1, all_tries=True) for x in base]
            tb = [r1_lat(rng, x, 1, sd=0.1, storms=False, mult=m, all_tries=True) for x in base]
        else:
            raise KeyError(scenario)
        d = np.array([y.mean() for y in tb]) - np.array([y.mean() for y in ta])
        p = ref_signflip_p(d, rng, plus_one=True)
        yield ta, tb, p, stats.ttest_1samp(d, 0).pvalue < 0.05


# sim_crash.py's kinds
SIM_EARLY = {"crash", "rate_limit", "abstained", "guardrail_blocked"}
SIM_SPEC_DROP = {"crash", "rate_limit", "timeout"}


def sim_call(d: np.ndarray, rng: np.random.Generator) -> str:
    """sim_crash.call: the check's call at 0.05 on one measure, floor 8 (before CS1)."""
    if len(d) < 10 or (d != 0).sum() < 8:
        return "too small"
    p = ref_signflip_p(d, rng)
    if p >= 0.05:
        return "none"
    return "B lower" if d.mean() < 0 else "B higher"


def sim_count_rule(v: str, ka: np.ndarray, kb: np.ndarray, keep: np.ndarray) -> str:
    """sim_crash.count_rule with timeouts counted: CS8's rule as the check simulated it."""
    early_a = sum(1 for a in ka if a in SIM_EARLY)
    early_b = sum(1 for b in kb if b in SIM_EARLY)
    to_a = sum(1 for a, kp in zip(ka, keep) if kp and a == "timeout")
    to_b = sum(1 for b, kp in zip(kb, keep) if kp and b == "timeout")
    if v == "B lower" and (early_b > early_a or to_b > to_a):
        return "unconfirmed"
    if v == "B higher" and (early_a > early_b or to_a > to_b):
        return "unconfirmed"
    return v


def sim_spec_guard(d: np.ndarray, m: int, verdict: str) -> str:
    """sim_crash.spec_guard: the 10th/90th-percentile guard CS8 replaces."""
    if verdict not in ("B lower", "B higher") or m == 0:
        return verdict
    p10, p90 = np.quantile(d, [0.1, 0.9])
    for fill in (p10, p90):
        bound = (d.sum() + m * fill) / (len(d) + m)
        if np.sign(bound) != np.sign(d.mean()):
            return "unconfirmed"
    return verdict


R3_SCENARIOS = {  # r3_tip_stress.SCN, by index: (noise sd, hidden factor or None)
    1: (0.15, 1.6),  # "hidden h1.6 s0.15": the low-noise hidden slowdown (fresh read A3)
}


def r3_reps(index: int, k: int, reps: int):  # type: ignore[no-untyped-def]
    """r3_tip_stress.cell's draws for scenario ``index`` at ``k`` cases, the generator moved on as
    r3 moves it. Yields, per rep, one try per case of each version (latency, the ending kind of
    each) and r3's spec and count readings of that rep."""
    s, h = R3_SCENARIOS[index]
    rng = np.random.default_rng(np.random.SeedSequence([20261103, 903, index, k]))
    for _ in range(reps):
        b = np.exp(rng.normal(np.log(5.0), 1.0, k))
        hard = np.zeros(k, bool)
        hard[np.argsort(b)[-round(0.18 * k):]] = True
        rb = np.where(hard, h, 0.85)
        hit = hard
        ya = b * np.exp(rng.normal(0, s, k))
        ybw = b * rb * np.exp(rng.normal(0, s, k))
        yb = np.where(hit, 0.05, ybw)
        ka = np.array(["pass"] * k, dtype=object)
        kb = ka.copy()
        kb[hit] = "crash"
        d = yb - ya
        keep = np.array([not (x in SIM_SPEC_DROP or y in SIM_SPEC_DROP) for x, y in zip(ka, kb)])
        spec = sim_spec_guard(d[keep], int((~keep).sum()), sim_call(d[keep], rng))
        keep = np.array([not (x in SIM_EARLY or y in SIM_EARLY) for x, y in zip(ka, kb)])
        count = sim_count_rule(sim_call(d[keep], rng), ka, kb, keep)
        yield ya, yb, ka, kb, spec, count


def crash_reps(scenario: str, r: float, k: int, reps: int):  # type: ignore[no-untyped-def]
    """sim_crash.draw for ``scenario`` at ratio ``r`` and ``k`` cases, from the check's seed for
    that cell. Only the draws are reproduced (the cell's other readings are not replayed, so
    from the second rep on the stream is this file's own, at the check's seed)."""
    scenarios = ("random_crash", "hard_crash", "hard_giveup", "timeout", "hidden_slow")
    rng = ref_seed_for(4, scenarios.index(scenario), int(r * 100), k)
    for _ in range(reps):
        b = np.exp(rng.normal(np.log(5.0), 1.0, k))
        hard = np.zeros(k, bool)
        hard[np.argsort(b)[-round(0.18 * k):]] = True
        rb = np.where(hard, 1.6, 0.85) if scenario == "hidden_slow" else np.full(k, r)
        ya = b * np.exp(rng.normal(0, 0.4, k))
        ybw = b * rb * np.exp(rng.normal(0, 0.4, k))
        ta = np.round(80 * ya * np.exp(rng.normal(0, 0.2, k)))
        tbw = np.round(80 * ybw * np.exp(rng.normal(0, 0.2, k)))
        ka = np.array(["pass"] * k, dtype=object)
        kb = ka.copy()
        yb, tb = ybw.copy(), tbw.copy()
        hit = hard if scenario in ("hard_crash", "hidden_slow", "hard_giveup") else (
            rng.random(k) < 0.18 if scenario == "random_crash" else np.zeros(k, bool))
        if scenario == "hard_giveup":
            yb = np.where(hit, 0.1 * ybw, yb)
            tb = np.where(hit, np.round(0.1 * tbw), tb)
            kb[hit] = "abstained"
        elif scenario != "timeout":
            yb = np.where(hit, 0.05, yb)
            tb = np.where(hit, np.round(0.05 * tbw), tb)
            kb[hit] = "crash"
        yield ya, yb, ta, tb, ka, kb


def versions_from_runs(
    ya: Sequence[Any], yb: Sequence[Any], ka: Sequence[str] | None = None,
    kb: Sequence[str] | None = None, *, measure: str = "wall_time_s",
    extra: Mapping[str, tuple[Sequence[float], Sequence[float]]] | None = None,
    names: tuple[str, str] = ("run-a", "run-b"),
) -> tuple[Any, Any]:
    """Two versions from simulated draws. Each entry of ``ya``/``yb`` is one case: a number (one
    try) or an array (its tries, in order). ``ka``/``kb`` give each case's ending kind ("pass"
    is a finished try, recorded as no ending); ``extra`` adds more measures, one try per case."""
    T = cm().Try

    def build(ys: Sequence[Any], kinds: Sequence[str] | None, side: int) -> dict[str, list[Any]]:
        out: dict[str, list[Any]] = {}
        for i, y in enumerate(ys):
            kind = None if kinds is None or kinds[i] == "pass" else str(kinds[i])
            vals = np.atleast_1d(np.asarray(y, dtype=float))
            got = []
            for j, v in enumerate(vals):
                values: dict[str, float | None] = {measure: float(v)}
                if extra and j == 0:
                    values.update({m: float(cols[side][i]) for m, cols in extra.items()})
                got.append(T(values=values, ending=kind, repeat=j))
            out[f"c{i:03d}"] = got
        return out

    return (version(names[0], "old", build(ya, ka, 0)), version(names[1], "new", build(yb, kb, 1)))
