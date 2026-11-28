"""The portable functions are accurate: each within 1e-13 relative of a reference computed with
``decimal.Decimal`` at 50 digits, on at least 10,000 points spanning the range Trace calls it
on (spaced by decade in the tails), except where the reference is below 1e-300.

``fisher_two_sided`` equals the correctly rounded exact rational on every 2x2 table with at most
30 tries in each arm. ``isum`` adds integers exactly and refuses a float. The Student t quantile
at the levels Trace uses and the normal quantile at 0.025 also agree with scipy's to 1e-13
(scipy as a reference in this test only).

The references here are written from the functions' definitions and share no code with
``poisson_trace.stats.portable``.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from decimal import ROUND_HALF_EVEN, Context, Decimal, getcontext, localcontext
from functools import cache

import numpy as np
import pytest

PI = Decimal("3.14159265358979323846264338327950288419716939937510582097494459230781640628620899")
CTX = Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-9999999, Emax=9999999)
TOLERANCE = Decimal("1e-13")
FLOOR = Decimal("1e-300")


def _portable() -> object:
    from poisson_trace.stats import portable

    return portable


# ---------- the grids ----------


def spread(lo: float, hi: float, n: int) -> list[float]:
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)]


def decades(first: float, last: float, n: int, sign: float = 1.0) -> list[float]:
    """``n`` points from ``10**first`` to ``10**last``, even in the exponent, read from text."""
    out = []
    for i in range(n):
        e = first + (last - first) * i / (n - 1)
        whole = math.floor(e)
        mantissa = round(1.0 + 9.0 * (e - whole), 9)
        out.append(sign * float(f"{mantissa}e{whole}"))
    return out


T_DF = [*range(1, 21), 25, 30, 40, 50, 75, 100, 150, 200, 300, 500, 1000, 2000, 3000, 5000, 7500, 10000]


def t_x_grid() -> list[tuple[float, int]]:
    xs = spread(-40.0, 40.0, 180) + decades(-3, 6, 60) + decades(-3, 6, 60, -1.0)
    return [(x, df) for df in T_DF for x in xs]


def t_q_grid() -> list[tuple[float, int]]:
    qs = spread(0.005, 0.995, 140) + decades(-12, -2.5, 80) + [1.0 - q for q in decades(-12, -2.5, 80)]
    return [(q, df) for df in T_DF for q in qs]


# ---------- the references, at 50 digits ----------


def ref_exp(x: float) -> Decimal:
    with localcontext(CTX):
        return Decimal(x).exp()


def ref_log(x: float) -> Decimal:
    with localcontext(CTX):
        return Decimal(x).ln()


def ref_log1p(x: float) -> Decimal:
    d = Decimal(x)
    with localcontext(CTX) as ctx:
        if abs(x) < 1e-20:
            return d - d * d / 2 + d * d * d / 3
        ctx.prec = 400
        s = 1 + d
        ctx.prec = 50
        return s.ln()


def ref_expm1(x: float) -> Decimal:
    d = Decimal(x)
    with localcontext(CTX) as ctx:
        if abs(x) < 1e-20:
            return d + d * d / 2 + d * d * d / 6
        ctx.prec = 80
        out = d.exp() - 1
        ctx.prec = 50
        return +out


def ref_erfc(y: Decimal) -> Decimal:
    """erfc by its power series below 3, with the digits the subtraction loses added, and by
    its continued fraction from 3 up."""
    if y < 0:
        with localcontext(CTX) as ctx:
            ctx.prec = 70
            return 2 - ref_erfc(-y)
    with localcontext(CTX) as ctx:
        if y < 3:
            ctx.prec = 70 + int(y * y)
            y2 = y * y
            term = total = y
            n = 0
            stop = Decimal(1).scaleb(-(ctx.prec + 2))
            while term > total * stop:
                term = term * 2 * y2 / (2 * n + 3)
                total += term
                n += 1
            return 1 - 2 / PI.sqrt() * (-y2).exp() * total
        ctx.prec = 70
        r = Decimal(0)
        for k in range(60 + int(3000 / (y * y)), 0, -1):
            r = (Decimal(k) / 2) / (y + r)
        return (-(y * y)).exp() / PI.sqrt() / (y + r)


def ref_norm_sf(x: Decimal) -> Decimal:
    with localcontext(CTX) as ctx:
        ctx.prec = 70
        return ref_erfc(x / Decimal(2).sqrt()) / 2


def ref_norm_pdf(x: Decimal) -> Decimal:
    with localcontext(CTX) as ctx:
        ctx.prec = 70
        return (-(x * x) / 2).exp() / (2 * PI).sqrt()


def ref_norm_isf(q: float, start: float) -> Decimal:
    """The root of ``sf(x) = q`` by Newton's method from ``start``, at 70 digits."""
    assert math.isfinite(start), start
    target = Decimal(q)
    x = Decimal(start)
    with localcontext(CTX) as ctx:
        ctx.prec = 70
        for _ in range(30):
            step = (ref_norm_sf(x) - target) / ref_norm_pdf(x)
            x += step
            if abs(step) <= abs(x) * Decimal("1e-60") or step == 0:
                return x
    raise AssertionError(f"Newton did not settle for q={q!r} from {start!r}")


def ref_chi2_sf_1(x: float) -> Decimal:
    with localcontext(CTX) as ctx:
        ctx.prec = 70
        return ref_erfc((Decimal(x) / 2).sqrt())


def _atan(z: Decimal) -> Decimal:
    """atan(z) for z >= 0 in the current context: halved twice, then its series."""
    if z > 1:
        return PI / 2 - _atan(1 / z)
    for _ in range(3):
        z = z / (1 + (1 + z * z).sqrt())
    total = term = z
    z2 = z * z
    n = 1
    stop = Decimal(1).scaleb(-(getcontext().prec + 2))
    while True:
        term = -term * z2
        add = term / (2 * n + 1)
        if abs(add) < stop:
            break
        total += add
        n += 1
    return 8 * total


def ref_t_sf(t: Decimal, df: int) -> Decimal:
    """P(T > t), t >= 0, from the closed forms for whole degrees of freedom: the finite sum where
    it loses few digits, otherwise the tail that is its complement, which is a sum of positive
    terms."""
    if t == 0:
        return Decimal("0.5")
    d = Decimal(df)
    with localcontext(CTX) as ctx:
        ctx.prec = 60
        lost = int((d + 1) / 2 * (1 + t * t / d).log10())
        tail = lost > 8
        ctx.prec = 70 + (0 if tail else lost)
        root = (d + t * t).sqrt()
        c2 = d / (d + t * t)
        stop = Decimal(1).scaleb(-(ctx.prec + 3))
        if df % 2 == 0:
            n = df // 2
            s = t / root
            terms = [Decimal(1)]
            for k in range(1, n):
                terms.append(terms[-1] * (2 * k - 1) / (2 * k) * c2)
            if not tail:
                return (1 - s * sum(terms, Decimal(0))) / 2
            term = (terms[-1] * (2 * n - 1) / (2 * n) * c2) if n else Decimal(1)
            total, k = Decimal(0), n
            while term > total * stop:
                total += term
                k += 1
                term = term * (2 * k - 1) / (2 * k) * c2
            return s * total / 2
        n = (df - 1) // 2
        sin, cos = t / root, d.sqrt() / root
        terms = [Decimal(1)]
        for k in range(1, n):
            terms.append(terms[-1] * (2 * k) / (2 * k + 1) * c2)
        if not tail:
            inside = 2 / PI * (_atan(t / d.sqrt()) + sin * cos * (sum(terms, Decimal(0)) if n else 0))
            return (1 - inside) / 2
        term = (terms[-1] * (2 * n) / (2 * n + 1) * c2) if n else Decimal(1)
        total, k = Decimal(0), n
        while term > total * stop:
            total += term
            k += 1
            term = term * (2 * k) / (2 * k + 1) * c2
        return sin * cos * total / PI


def ref_t_cdf(x: float, df: int) -> Decimal:
    t = Decimal(x)
    with localcontext(CTX) as ctx:
        ctx.prec = 70
        return ref_t_sf(-t, df) if t < 0 else 1 - ref_t_sf(t, df)


@cache
def _t_constant(df: int) -> Decimal:
    """Gamma((df + 1) / 2) / (sqrt(df pi) Gamma(df / 2)), by the ratio's recurrence."""
    with localcontext(CTX) as ctx:
        ctx.prec = 70
        ratio, k = (1 / PI.sqrt(), 1) if df % 2 else (PI.sqrt() / 2, 2)
        while k < df:
            ratio = ratio * (k + 1) / k
            k += 2
        return ratio / (Decimal(df) * PI).sqrt()


def ref_t_ppf(q: float, df: int, start: float) -> Decimal:
    """The root of ``cdf(t) = q`` by Newton's method from ``start``."""
    assert math.isfinite(start), start
    target = Decimal(q)
    t = Decimal(start)
    with localcontext(CTX) as ctx:
        ctx.prec = 70
        d = Decimal(df)
        for _ in range(40):
            density = _t_constant(df) * ((-(d + 1) / 2) * (1 + t * t / d).ln()).exp()
            step = (_cdf_exact(t, df) - target) / density
            t -= step
            if abs(step) <= abs(t) * Decimal("1e-55") or step == 0:
                return t
    raise AssertionError(f"Newton did not settle for q={q!r}, df={df} from {start!r}")


def _cdf_exact(t: Decimal, df: int) -> Decimal:
    with localcontext(CTX) as ctx:
        ctx.prec = 70
        return ref_t_sf(-t, df) if t < 0 else 1 - ref_t_sf(t, df)


# ---------- the comparison ----------


def _far(got: float, want: Decimal) -> Decimal | None:
    """How far ``got`` is from ``want`` relative to it, or None where the reference is below
    1e-300 in size."""
    if abs(want) < FLOOR:
        return None
    if not math.isfinite(got):
        return Decimal("Infinity")
    with localcontext(CTX):
        return abs(Decimal(got) - want) / abs(want)


def _check(name: str, points: Iterable[object], call: Callable[..., float], ref: Callable[..., Decimal]) -> int:
    worst: list[tuple[Decimal, object, float, Decimal]] = []
    checked = 0
    for p in points:
        args = p if isinstance(p, tuple) else (p,)
        got = call(*args)
        want = ref(*args, got)
        far = _far(got, want)
        if far is None:
            continue
        checked += 1
        if far > TOLERANCE:
            worst.append((far, p, got, want))
    worst.sort(key=lambda w: w[0], reverse=True)
    shown = "\n".join(f"  {name}{w[1]!r} = {w[2]!r}, reference {w[3]:.20e}, off {w[0]:.2e} relative" for w in worst[:10])
    assert not worst, f"{len(worst)} of {checked} points are off by more than 1e-13 relative:\n{shown}"
    return checked


def _with(fn: Callable[..., Decimal]) -> Callable[..., Decimal]:
    """A reference that ignores the value under test."""
    return lambda *args: fn(*args[:-1])


CASES: dict[str, tuple[Callable[[], list[object]], Callable[..., Decimal]]] = {
    "exp": (lambda: spread(-745.0, 709.7, 9000) + decades(-300, -0.5, 1000) + decades(-300, -0.5, 1000, -1.0),
            _with(ref_exp)),
    "log": (lambda: decades(-323, 308, 10000) + spread(0.5, 2.0, 1001), _with(ref_log)),
    "log1p": (lambda: decades(-300, 300, 5500) + [-q for q in decades(-300, -0.0000001, 5500)], _with(ref_log1p)),
    "expm1": (lambda: spread(-745.0, 709.7, 7000) + decades(-300, 0.3, 2000) + decades(-300, 0.3, 2000, -1.0),
              _with(ref_expm1)),
    "erfc": (lambda: spread(-6.0, 27.0, 9000) + decades(-300, 0.4, 1000) + decades(-300, 0.4, 1000, -1.0),
             _with(lambda x: ref_erfc(Decimal(x)))),
    "norm_sf": (lambda: spread(-38.0, 38.0, 9000) + decades(-300, 1.5, 1000) + decades(-300, 1.5, 1000, -1.0),
                _with(lambda x: ref_norm_sf(Decimal(x)))),
    "norm_cdf": (lambda: spread(-38.0, 38.0, 9000) + decades(-300, 1.5, 1000) + decades(-300, 1.5, 1000, -1.0),
                 _with(lambda x: ref_norm_sf(-Decimal(x)))),
    "norm_isf": (lambda: decades(-300, -0.302, 6500) + spread(0.01, 0.99, 2500) + [1.0 - q for q in decades(-16, -0.302, 2000)],
                 ref_norm_isf),
    "norm_ppf": (lambda: decades(-300, -0.302, 6500) + spread(0.01, 0.99, 2500) + [1.0 - q for q in decades(-16, -0.302, 2000)],
                 lambda q, got: -ref_norm_isf(q, -got)),
    "chi2_sf_1": (lambda: decades(-12, 3.18, 9000) + spread(0.0, 1500.0, 2000), _with(ref_chi2_sf_1)),
    "t_cdf": (t_x_grid, _with(ref_t_cdf)),
    "t_ppf": (t_q_grid, ref_t_ppf),
}


@pytest.mark.parametrize("name", list(CASES))
def test_each_portable_function_is_within_1e_13_of_its_reference(name: str) -> None:
    points_of, ref = CASES[name]
    points = points_of()
    call = getattr(_portable(), name)
    checked = _check(name, points, call, ref)
    assert checked >= 10_000, f"{name}: only {checked} points checked; at least 10,000 are"


# ---------- Fisher, isum, and scipy's values ----------


def _hypergeometric_rows(runs_a: int, runs_b: int, failed: int) -> list[int]:
    lowest, highest = max(0, failed - runs_b), min(failed, runs_a)
    return [math.comb(runs_a, k) * math.comb(runs_b, failed - k) for k in range(lowest, highest + 1)]


def test_fisher_is_the_correctly_rounded_exact_p_on_every_small_table() -> None:
    fisher = _portable().fisher_two_sided  # type: ignore[attr-defined]
    wrong = []
    checked = 0
    for runs_a in range(1, 31):
        for runs_b in range(1, 31):
            for failed in range(runs_a + runs_b + 1):
                whole = math.comb(runs_a + runs_b, failed)
                terms = _hypergeometric_rows(runs_a, runs_b, failed)
                lowest = max(0, failed - runs_b)
                for a in range(lowest, lowest + len(terms)):
                    at = terms[a - lowest]
                    held = sum(t for t in terms if t * 10_000_000 <= at * 10_000_001)
                    want = 1.0 if held >= whole else held / whole
                    c = failed - a
                    got = fisher(a, runs_a - a, c, runs_b - c)
                    checked += 1
                    if got != want:
                        wrong.append(((a, runs_a - a, c, runs_b - c), got, want))
    assert checked == sum((n + 1) for n in range(1, 31)) ** 2
    assert not wrong, f"{len(wrong)} of {checked} tables differ from the exact p, first: {wrong[:5]}"


def test_isum_adds_integers_exactly_and_refuses_a_float() -> None:
    isum = _portable().isum  # type: ignore[attr-defined]
    big = [2**80 + k for k in range(100)] + [-(2**80)] * 100 + [True, False, np.int64(7), np.int32(-3)]
    assert isum(big) == sum(2**80 + k for k in range(100)) - 100 * 2**80 + 1 + 7 - 3
    assert isum(iter([])) == 0
    assert isum(x for x in (1, 2, 3)) == 6
    for bad in ([1, 2.0], [1.5], [np.float64(1.0)], [1, np.float32(2.0)], ["1"], [None]):
        with pytest.raises(TypeError):
            isum(bad)


@pytest.mark.parametrize("df", [1, 2, 3, 10, 30, 100, 1000])
def test_the_t_quantile_agrees_with_scipy(df: int) -> None:
    from scipy import stats

    t_ppf = _portable().t_ppf  # type: ignore[attr-defined]
    for q in (0.6, 0.8, 0.9, 0.95, 0.975, 0.99, 0.995, 0.9995):
        got, want = t_ppf(q, df), float(stats.t.ppf(q, df))
        assert abs(got - want) <= 1e-13 * abs(want), (q, df, got, want)


def test_the_normal_quantile_at_0_025_agrees_with_scipy() -> None:
    from scipy import stats

    portable = _portable()
    want = float(stats.norm.isf(0.025))
    assert abs(portable.norm_isf(0.025) - want) <= 1e-13 * want  # type: ignore[attr-defined]
    assert abs(portable.norm_ppf(0.975) - want) <= 1e-13 * want  # type: ignore[attr-defined]
