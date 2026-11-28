"""Numeric functions that give the same bits on every platform.

The platform's math library, numpy's vectorised loops and BLAS each compute exp, log, the
trigonometric functions and dot products in their own way, and their last bits differ between
macOS and Linux, and between Linux machines with different CPUs. Every number Trace prints or
writes is computed from the functions here, which use only:

- IEEE-754 basic operations (``+ - * /`` and the square root), one at a time, on Python floats
  or elementwise on numpy arrays; comparisons; ``math.floor`` and ``math.ldexp``; table lookups
  and searches over a fixed table of powers of two;
- Python integers, which are exact;
- ``decimal.Decimal`` in an explicit local context, whose operations, ``exp``, ``ln`` and
  ``sqrt`` included, are correctly rounded and so the same everywhere.

Each function is within 1e-13 relative of its exact value over the range Trace calls it on.

- ``exp``, ``log``, ``log1p`` and ``expm1`` take a float or a numpy array, elementwise, by
  argument reduction and a polynomial in plain floats, within a few units in the last place.
- ``erfc``, the normal tails and quantiles, the chi-square tail with one degree of freedom and
  Student's t take a float and are computed in ``Decimal`` at 34 digits or more, then rounded
  to the nearest float once.
- ``fisher_two_sided`` is exact rational arithmetic in integers, rounded once.
- ``isum`` adds integers and refuses anything else, so a float sum never passes as one.
- ``bisect_root`` finds where a falling function crosses a level, to adjacent floats.
"""

from __future__ import annotations

import math
import numbers
import struct
from collections.abc import Callable, Iterable
from decimal import ROUND_HALF_EVEN, Context, Decimal, getcontext, localcontext
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

    FloatArray = npt.NDArray[np.float64]

__all__ = [
    "bisect_root",
    "chi2_sf_1",
    "erfc",
    "exp",
    "expm1",
    "fisher_two_sided",
    "isum",
    "log",
    "log1p",
    "norm_cdf",
    "norm_isf",
    "norm_ppf",
    "norm_sf",
    "t_cdf",
    "t_ppf",
]

# ---------- exp, log, log1p and expm1, elementwise in plain floats ----------

# ln 2 split in two: the first part has 32 significant bits, so that ``n * _LN2_HI`` is exact for
# every whole ``n`` up to 2**21; the two together are ln 2 to about 1e-26.
_LN2_HI = float.fromhex("0x1.62e42fee00000p-1")
_LN2_LO = float.fromhex("0x1.a39ef35793c76p-33")
_INV_LN2 = float.fromhex("0x1.71547652b82fep0")
_SQRT2 = float.fromhex("0x1.6a09e667f3bcdp0")
# Adding then subtracting 1.5 * 2**52 rounds a float of size below 2**51 to the nearest whole
# number, ties to even, with two IEEE additions.
_ROUNDER = 6755399441055744.0
_POW2_LOW = -1074
# 1/k! for k = 0 .. 17, each the float nearest the exact fraction.
_INV_FACTORIAL = tuple(1 / math.factorial(k) for k in range(18))
# 1/(2k + 1) for the series of atanh.
_INV_ODD = tuple(1 / (2 * k + 1) for k in range(12))


@lru_cache(maxsize=1)
def _numpy() -> tuple[Any, FloatArray]:
    """numpy, imported the first time an elementwise function runs so that a command that
    computes nothing does not load it; and every power of two a float can hold, 2**-1074 to
    2**1023, each made by ``math.ldexp`` (exact)."""
    import numpy

    powers = numpy.array([math.ldexp(1.0, k) for k in range(_POW2_LOW, 1024)], dtype=numpy.float64)
    return numpy, powers


def _scaled(p: FloatArray, n: FloatArray) -> FloatArray:
    """``p * 2**n`` for whole ``n`` in ``[-1100, 1100]``: two exact multiplications by powers of
    two, the second rounding only where the result leaves the normal range."""
    np, pow2 = _numpy()
    first = np.clip(n, -1000.0, 1000.0)
    second = n - first
    head: FloatArray = p * pow2[(first - _POW2_LOW).astype(np.int64)]
    out: FloatArray = head * pow2[(second - _POW2_LOW).astype(np.int64)]
    return out


def _exp(x: FloatArray) -> FloatArray:
    """e**x: ``x = n ln 2 + r`` with ``|r| <= ln 2 / 2``, then ``e**r`` by its Taylor polynomial
    to the 13th power (the rest is below 1e-17 of it), then scaled by ``2**n``."""
    np, _ = _numpy()
    nan = x != x
    held = np.clip(np.where(nan, 0.0, x), -746.0, 710.0)
    n = (held * _INV_LN2 + _ROUNDER) - _ROUNDER
    r = (held - n * _LN2_HI) - n * _LN2_LO
    poly = np.full_like(r, _INV_FACTORIAL[13])
    for k in range(12, 0, -1):
        poly = poly * r + _INV_FACTORIAL[k]
    out = _scaled(poly * r + 1.0, n)
    done: FloatArray = np.where(nan, math.nan, out)
    return done


def _log(x: FloatArray) -> FloatArray:
    """ln x: ``x = m 2**e`` with ``m`` in ``[sqrt(1/2), sqrt(2))``, found in the table of powers of
    two; ``ln m = 2 atanh(s)`` with ``s = (m - 1) / (m + 1)``, ``|s| < 0.172``, by its series to the
    23rd power (the rest is below 1e-19 of it); then ``e ln 2`` added in two parts."""
    np, pow2 = _numpy()
    positive = (x > 0.0) & (x < math.inf)
    held = np.where(positive, x, 1.0)
    at = np.searchsorted(pow2, held, side="right") - 1
    e = (at + _POW2_LOW).astype(np.float64)
    m = held / pow2[at]
    big = m > _SQRT2
    m = np.where(big, m * 0.5, m)
    e = np.where(big, e + 1.0, e)
    f = m - 1.0
    s = f / (2.0 + f)
    z = s * s
    series = np.full_like(z, _INV_ODD[11])
    for k in range(10, -1, -1):
        series = series * z + _INV_ODD[k]
    out = e * _LN2_HI + (e * _LN2_LO + 2.0 * s * series)
    out = np.where(positive, out, math.nan)
    out = np.where(x == 0.0, -math.inf, out)
    done: FloatArray = np.where(x == math.inf, math.inf, out)
    return done


def _log1p(x: FloatArray) -> FloatArray:
    """ln(1 + x): ``u = 1 + x`` rounded, then ``ln u`` less the part of ``u - 1`` that is not ``x``,
    divided by ``u``; where ``1 + x`` rounds to 1, ``x`` itself."""
    np, _ = _numpy()
    u = 1.0 + x
    out = _log(u) - ((u - 1.0) - x) / u
    out = np.where(u == 1.0, x, out)
    out = np.where(x == -1.0, -math.inf, out)
    done: FloatArray = np.where(x == math.inf, math.inf, out)
    return done


def _expm1(x: FloatArray) -> FloatArray:
    """e**x - 1: within 1/2 of 0 by its Taylor polynomial to the 17th power (the rest is below
    1e-19 of it), so that no digit is lost to the subtraction; elsewhere ``e**x - 1``, which loses
    less than a bit there."""
    np, _ = _numpy()
    poly = np.full_like(x, _INV_FACTORIAL[17])
    for k in range(16, 0, -1):
        poly = poly * x + _INV_FACTORIAL[k]
    near = poly * x
    far = _exp(x) - 1.0
    done: FloatArray = np.where(np.abs(x) <= 0.5, near, far)
    return done


def _elementwise(fn: Callable[[FloatArray], FloatArray], x: Any) -> Any:
    """``fn`` of a float, as a float, or elementwise of an array, as an array of its shape."""
    np, _ = _numpy()
    held = np.asarray(x, dtype=np.float64)
    with np.errstate(all="ignore"):
        out = fn(np.atleast_1d(held))
    if held.ndim == 0:
        return float(out[0])
    return out.reshape(held.shape)


def exp(x: Any) -> Any:
    """e**x, of a float or elementwise of an array."""
    return _elementwise(_exp, x)


def log(x: Any) -> Any:
    """The natural logarithm, of a float or elementwise of an array: -inf at 0, NaN below."""
    return _elementwise(_log, x)


def log1p(x: Any) -> Any:
    """ln(1 + x), of a float or elementwise of an array, without the digits ``1 + x`` loses."""
    return _elementwise(_log1p, x)


def expm1(x: Any) -> Any:
    """e**x - 1, of a float or elementwise of an array, without the digits the subtraction
    loses near 0."""
    return _elementwise(_expm1, x)


# ---------- erfc and the normal distribution, in Decimal ----------

# The working precision in decimal digits; the result is rounded to a float once, at the end.
_DIGITS = 34
_PI = Decimal("3.141592653589793238462643383279502884197169399375105820974944592307816406286209")


def _context(digits: int) -> Context:
    return Context(prec=digits, rounding=ROUND_HALF_EVEN, Emin=-999_999_999, Emax=999_999_999)


def _float(x: Decimal) -> float:
    """The float nearest ``x``, read from its digits (CPython's own correctly rounded reading)."""
    return float(x)


def _erfc_decimal(y: Decimal) -> Decimal:
    """erfc(y) for ``y >= 0`` to about ``_DIGITS`` digits: below 2 as ``1 - erf(y)``, with erf from
    its series of positive terms ``2/sqrt(pi) e**(-y^2) sum 2^k y^(2k+1) / (1 3 5 ... (2k+1))`` and
    the digits the subtraction loses carried; from 2 up by its continued fraction
    ``e**(-y^2) / sqrt(pi) / (y + (1/2) / (y + 1 / (y + (3/2) / (y + ...))))``, evaluated from the
    far end with enough terms for the digits asked."""
    if y < 2:
        # erfc(y) is above 0.004 here, so the subtraction loses at most three digits
        with localcontext(_context(_DIGITS + 6)) as ctx:
            y2 = y * y
            term = total = y
            n = 0
            stop = Decimal(1).scaleb(-(ctx.prec + 2))
            while term > total * stop:
                term = term * 2 * y2 / (2 * n + 3)
                total += term
                n += 1
            return 1 - 2 / _PI.sqrt() * (-y2).exp() * total
    with localcontext(_context(_DIGITS + 4)):
        # the fraction gains about y sqrt(N) digits with N terms
        reach = Decimal(_DIGITS + 4) / y
        terms = int(reach * reach) + 20
        r = Decimal(0)
        for k in range(terms, 0, -1):
            r = (Decimal(k) / 2) / (y + r)
        return (-(y * y)).exp() / _PI.sqrt() / (y + r)


def _erfc_signed(y: Decimal) -> Decimal:
    if y < 0:
        with localcontext(_context(_DIGITS + 4)):
            return 2 - _erfc_decimal(-y)
    return _erfc_decimal(y)


def _checked_float(x: float, name: str) -> float:
    x = float(x)
    if x != x:
        raise ValueError(f"{name} of NaN")
    return x


def erfc(x: float) -> float:
    """The complementary error function, ``1 - erf(x)``."""
    x = _checked_float(x, "erfc")
    if x == math.inf:
        return 0.0
    if x == -math.inf:
        return 2.0
    return _float(_erfc_signed(Decimal(x)))


def _norm_sf_decimal(x: Decimal) -> Decimal:
    """P(Z > x) for a standard normal Z: ``erfc(x / sqrt(2)) / 2``, with the division done in
    Decimal so that it rounds nothing a float would."""
    with localcontext(_context(_DIGITS + 6)):
        y = x / Decimal(2).sqrt()
    out = _erfc_signed(y)
    with localcontext(_context(_DIGITS + 4)):
        return out / 2


def _norm_pdf_decimal(x: Decimal) -> Decimal:
    with localcontext(_context(_DIGITS + 4)):
        return (-(x * x) / 2).exp() / (2 * _PI).sqrt()


def norm_sf(x: float) -> float:
    """P(Z > x) for a standard normal Z."""
    x = _checked_float(x, "norm_sf")
    if x == math.inf:
        return 0.0
    if x == -math.inf:
        return 1.0
    return _float(_norm_sf_decimal(Decimal(x)))


def norm_cdf(x: float) -> float:
    """P(Z <= x) for a standard normal Z."""
    x = _checked_float(x, "norm_cdf")
    if x == math.inf:
        return 1.0
    if x == -math.inf:
        return 0.0
    return _float(_norm_sf_decimal(-Decimal(x)))


def _norm_upper(tail: Decimal) -> Decimal:
    """The x >= 0 with P(Z > x) = ``tail``, for ``0 < tail <= 1/2``: a start within 4.5e-4 of it
    (Abramowitz and Stegun 26.2.23), then Newton's steps on the tail in Decimal until a step no
    longer moves the digits kept."""
    with localcontext(_context(_DIGITS + 4)):
        t = (-2 * tail.ln()).sqrt()
        above = Decimal("2.515517") + Decimal("0.802853") * t + Decimal("0.010328") * t * t
        below = 1 + (Decimal("1.432788") + (Decimal("0.189269") + Decimal("0.001308") * t) * t) * t
        x = t - above / below
        if x < 0:
            x = Decimal(0)
        # Newton's steps square the error, so once a step is below 1e-20 of x the next would be
        # far below the digits kept
        small = Decimal("1e-20")
        for _ in range(60):
            step = (_norm_sf_decimal(x) - tail) / _norm_pdf_decimal(x)
            x += step
            if step == 0 or abs(step) <= abs(x) * small:
                break
        return x


@lru_cache(maxsize=256)
def norm_isf(q: float) -> float:
    """The x with P(Z > x) = ``q`` for a standard normal Z, ``0 < q < 1``: +inf at 0, -inf at 1."""
    q = _checked_float(q, "norm_isf")
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"norm_isf needs a probability in [0, 1], not {q!r}")
    if q == 0.0:
        return math.inf
    if q == 1.0:
        return -math.inf
    if q == 0.5:
        return 0.0
    p = Decimal(q)
    if p < Decimal("0.5"):
        return _float(_norm_upper(p))
    with localcontext(_context(_DIGITS + 4)):
        tail = 1 - p  # exact: q is a float between 1/2 and 1
    return _float(-_norm_upper(tail))


def norm_ppf(q: float) -> float:
    """The x with P(Z <= x) = ``q`` for a standard normal Z, ``0 < q < 1``: -inf at 0, +inf at 1."""
    return 0.0 - norm_isf(q)


def chi2_sf_1(x: float) -> float:
    """P(X > x) for X chi-square with one degree of freedom: ``erfc(sqrt(x / 2))``."""
    x = _checked_float(x, "chi2_sf_1")
    if x <= 0.0:
        return 1.0
    if x == math.inf:
        return 0.0
    with localcontext(_context(_DIGITS + 6)):
        y = (Decimal(x) / 2).sqrt()
    return _float(_erfc_decimal(y))


# ---------- Student's t, in Decimal ----------


def _atan_decimal(z: Decimal) -> Decimal:
    """atan(z) for ``z >= 0`` in the current context: above 1 through ``pi/2 - atan(1/z)``, then
    the angle halved four times (``z / (1 + sqrt(1 + z^2))``) and its series."""
    if z > 1:
        return _PI / 2 - _atan_decimal(1 / z)
    for _ in range(4):
        z = z / (1 + (1 + z * z).sqrt())
    stop = Decimal(1).scaleb(-(getcontext().prec + 2))
    z2 = z * z
    total = term = z
    k = 1
    while True:
        term = -term * z2
        add = term / (2 * k + 1)
        if abs(add) <= stop * abs(total):
            break
        total += add
        k += 1
    return 16 * total


def _digits_lost(t: Decimal, df: int) -> int:
    """About how many leading digits ``1 - P(|T| <= t)`` cancels: ``log10`` of one over the tail,
    which ``((df + 1) / 2) log10(1 + t^2 / df)`` bounds from above."""
    with localcontext(_context(12)):
        lost = (Decimal(df) + 1) / 2 * (1 + t * t / df).log10()
    return int(lost) + 1


def _t_sf_decimal(t: Decimal, df: int, digits: int = _DIGITS) -> Decimal:
    """P(T > t) for ``t >= 0`` and T Student's t with whole ``df``, to about ``digits`` digits,
    from the closed forms for whole degrees of freedom. With ``c = df / (df + t^2)`` and
    ``s = t / sqrt(df + t^2)``:

    - even df: ``(1 - s sum_{k<df/2} a_k c^k) / 2``, ``a_0 = 1``, ``a_k = a_{k-1} (2k - 1) / (2k)``;
    - odd df: ``(1 - (2/pi) (atan(t / sqrt(df)) + s sqrt(c) sum_{k<(df-1)/2} b_k c^k)) / 2``,
      ``b_0 = 1``, ``b_k = b_{k-1} (2k) / (2k + 1)``.

    Where the leading digits cancel and the terms past the finite sum fall fast, the tail is
    summed instead, a sum of positive terms that is the finite form's complement:
    ``(s / 2) sum_{k>=df/2} a_k c^k`` for even df, ``(s sqrt(c) / pi) sum_{k>=(df-1)/2} b_k c^k``
    for odd df. Otherwise the finite form is computed with the digits it cancels added."""
    if t == 0:
        return Decimal("0.5")
    lost = _digits_lost(t, df)
    even = df % 2 == 0
    n = df // 2 if even else (df - 1) // 2
    with localcontext(_context(12)):
        # the tail's terms fall by about a factor c each, so it needs about digits / log10(1/c)
        rate = (1 + t * t / df).log10()
        tail_terms = (digits + 4) / rate if rate > 0 else Decimal("Infinity")
    use_tail = lost > 3 and tail_terms < n * (1 + Decimal(lost) / digits)
    precision = digits + 6 + (0 if use_tail else lost)
    with localcontext(_context(precision)) as ctx:
        d = Decimal(df)
        w = d + t * t
        c = d / w
        s = t / w.sqrt()
        stop = Decimal(1).scaleb(-(ctx.prec + 2))
        if even:
            term, k, finite = Decimal(1), 0, Decimal(0)
            while k < n:
                finite += term
                k += 1
                term = term * (2 * k - 1) / (2 * k) * c
            if not use_tail:
                return (1 - s * finite) / 2
            total = Decimal(0)
            while term > total * stop:
                total += term
                k += 1
                term = term * (2 * k - 1) / (2 * k) * c
            return s * total / 2
        root_c = c.sqrt()
        term, k, finite = Decimal(1), 0, Decimal(0)
        while k < n:
            finite += term
            k += 1
            term = term * (2 * k) / (2 * k + 1) * c
        if not use_tail:
            inside = 2 / _PI * (_atan_decimal(t / d.sqrt()) + s * root_c * finite)
            return (1 - inside) / 2
        total = Decimal(0)
        while term > total * stop:
            total += term
            k += 1
            term = term * (2 * k) / (2 * k + 1) * c
        return s * root_c * total / _PI


def _checked_df(df: int) -> int:
    if isinstance(df, bool) or not isinstance(df, numbers.Integral) or df < 1:
        raise ValueError(f"Student's t needs whole degrees of freedom of at least 1, not {df!r}")
    return int(df)


def t_cdf(x: float, df: int) -> float:
    """P(T <= x) for T Student's t with ``df`` degrees of freedom, a whole number from 1 up."""
    x = _checked_float(x, "t_cdf")
    df = _checked_df(df)
    if x == math.inf:
        return 1.0
    if x == -math.inf:
        return 0.0
    if x < 0.0:
        return _float(_t_sf_decimal(-Decimal(x), df))
    sf = _t_sf_decimal(Decimal(x), df)
    with localcontext(_context(_DIGITS + 4)):
        return _float(1 - sf)


def _t_pdf_decimal(t: Decimal, df: int) -> Decimal:
    """The density of Student's t at ``t``: ``Gamma((df + 1) / 2) / (sqrt(df pi) Gamma(df / 2))``
    by the ratio's recurrence, times ``(1 + t^2 / df) ** (-(df + 1) / 2)``."""
    with localcontext(_context(_DIGITS + 6)):
        d = Decimal(df)
        return _t_constant(df) * ((-(d + 1) / 2) * (1 + t * t / d).ln()).exp()


@lru_cache(maxsize=64)
def _t_constant(df: int) -> Decimal:
    with localcontext(_context(_DIGITS + 8)):
        ratio, k = (1 / _PI.sqrt(), 1) if df % 2 else (_PI.sqrt() / 2, 2)
        while k < df:
            ratio = ratio * (k + 1) / k
            k += 2
        return ratio / (Decimal(df) * _PI).sqrt()


def _t_upper(tail: Decimal, df: int) -> Decimal:
    """The t > 0 with P(T > t) = ``tail``, ``0 < tail < 1/2``: Newton's steps on the logarithm of
    the tail against the logarithm of t, which is close to a straight line in both far tails.
    It starts at the normal quantile, below the root; the first step lands above it, and every
    later step falls toward it from above. A step that would leave the bracket kept so far is
    replaced by halving the bracket, so the search always closes."""
    with localcontext(_context(_DIGITS + 6)):
        target = tail.ln()
        t = _norm_upper(tail)
        low, high = Decimal(0), Decimal("Infinity")
        # as in _norm_upper: past a step of 1e-20 of t, the next is beyond the digits kept
        small = Decimal("1e-20")
        for _ in range(200):
            sf = _t_sf_decimal(t, df)
            if sf > tail:
                low = max(low, t)
            elif sf < tail:
                high = min(high, t)
            else:
                return t
            slope = -t * _t_pdf_decimal(t, df) / sf  # d ln sf / d ln t
            step = (target - sf.ln()) / slope
            following = t * step.exp()
            if not low < following < high:
                following = (low + high) / 2 if high.is_finite() else 2 * t
            moved = abs(following - t)
            t = following
            if moved == 0 or moved <= t * small:
                break
        return t


def t_ppf(q: float, df: int) -> float:
    """The x with P(T <= x) = ``q`` for T Student's t with ``df`` degrees of freedom, a whole
    number from 1 up, and ``0 < q < 1``."""
    q = _checked_float(q, "t_ppf")
    df = _checked_df(df)
    if not 0.0 < q < 1.0:
        if q == 0.0:
            return -math.inf
        if q == 1.0:
            return math.inf
        raise ValueError(f"t_ppf needs a probability in [0, 1], not {q!r}")
    if q == 0.5:
        return 0.0
    p = Decimal(q)
    if p > Decimal("0.5"):
        with localcontext(_context(_DIGITS + 4)):
            tail = 1 - p  # exact: q is a float between 1/2 and 1
        return _float(_t_upper(tail, df))
    return _float(-_t_upper(p, df))


# ---------- Fisher's exact test, in integers ----------

# Two tables are taken as equally probable when one is at most this many parts in ten million more
# probable than the other: Fisher's convention, and the exact test's in ``paired``.
_TIE_PARTS = 10_000_000


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """The two-sided Fisher exact p of the 2x2 table ``[[a, b], [c, d]]``: the share of tables with
    its margins that are no more probable than it, a table counting as no more probable when its
    probability is at most ``1 + 1e-7`` times the observed one's. Every count is an integer and
    the share is rounded once."""
    counts = (a, b, c, d)
    if any(isinstance(v, bool) or not isinstance(v, numbers.Integral) or v < 0 for v in counts):
        raise ValueError(f"a 2x2 table holds counts of zero or more, not {counts!r}")
    a, b, c, d = (int(v) for v in counts)
    row_a, row_b, column = a + b, c + d, a + c
    lowest, highest = max(0, column - row_b), min(column, row_a)
    tables = [
        math.comb(row_a, k) * math.comb(row_b, column - k) for k in range(lowest, highest + 1)
    ]
    observed = tables[a - lowest]
    held = isum(t for t in tables if t * _TIE_PARTS <= observed * (_TIE_PARTS + 1))
    whole = math.comb(row_a + row_b, column)
    return 1.0 if held >= whole else held / whole


# ---------- integer sums ----------


def isum(values: Iterable[Any]) -> int:
    """The exact sum of integers (Python's, numpy's, or booleans); a ``TypeError`` on anything
    else, so that a float sum is never added as one."""
    total = 0
    for v in values:
        # Python's integers, booleans among them, and numpy's, which register as Integral
        if isinstance(v, numbers.Integral):
            total += int(v)
        else:
            raise TypeError(f"isum adds integers only, not {type(v).__name__} {v!r}")
    return total


# ---------- a crossing, to adjacent floats ----------

_ORDER = struct.Struct("<q")
_FLOAT = struct.Struct("<d")
_SIGN = 1 << 63


def _key(x: float) -> int:
    """An integer that orders floats as their values do: 0 for both zeros."""
    bits: int = _ORDER.unpack(_FLOAT.pack(x))[0]
    return bits if bits >= 0 else -(bits + _SIGN)


def _from_key(k: int) -> float:
    bits = k if k >= 0 else -k - _SIGN
    value: float = _FLOAT.unpack(_ORDER.pack(bits))[0]
    return value


def bisect_root(f: Callable[[float], float], lo: float, hi: float, target: float) -> float:
    """For ``f`` falling across ``[lo, hi]`` with ``f(lo) >= target > f(hi)``: the float ``x`` in
    ``[lo, hi)`` with ``f(x) >= target > f(next float above x)``, the last float at or above the
    level. The bracket is halved in the order of the floats, not of their values, so it closes
    on two adjacent floats within 64 halvings wherever it lies."""
    if not lo < hi:
        raise ValueError(f"bisect_root needs lo below hi, not {lo!r} and {hi!r}")
    low, high = _key(lo), _key(hi)
    while high - low > 1:
        mid = (low + high) // 2
        if f(_from_key(mid)) >= target:
            low = mid
        else:
            high = mid
    return _from_key(low)
