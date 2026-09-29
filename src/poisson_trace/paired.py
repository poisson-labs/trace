"""The fix check's statistics: the per-input counts, the exact conditional
Cochran-Mantel-Haenszel test stratified by input, the Mantel-Haenszel difference with Sato's
interval, the by-input sign-flip reading, consistency, the detection limits, the guidance, and
the per-input flags.

numpy and scipy only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

# The four reasons an input is left out (spec section 3.3) and the six sentences of section
# 4.4, in that order. Filled by the build.
LEFT_OUT: tuple[str, ...] = ()
CANNOT_SAY: tuple[str, ...] = ()


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


def paired_test(counts: Sequence[Counts]) -> PairedTest:
    raise NotImplementedError


def difference(
    counts: Sequence[Counts], *, alpha: float = 0.05
) -> tuple[float, float | None, float | None, float | None]:
    raise NotImplementedError


def by_input(
    counts: Sequence[Counts], *, seed: int = 0, draws: int = 100_000
) -> tuple[float, int, str]:
    raise NotImplementedError


def consistency(counts: Sequence[Counts]) -> tuple[float, float, float, float, float]:
    raise NotImplementedError


def power_at(
    counts: Sequence[Counts],
    r: float,
    *,
    direction: Literal["drop", "rise"],
    alpha: float = 0.05,
) -> float:
    raise NotImplementedError


def detection_limit(
    counts: Sequence[Counts],
    *,
    direction: Literal["drop", "rise"],
    alpha: float = 0.05,
    power: float = 0.8,
    repeats: int | None = None,
    scale: float = 1.0,
) -> float | None:
    raise NotImplementedError


def repeats_needed(
    counts: Sequence[Counts], max_mde: float, *, alpha: float = 0.05, power: float = 0.8
) -> int | None:
    raise NotImplementedError


def inputs_needed(
    counts: Sequence[Counts], max_mde: float, *, alpha: float = 0.05, power: float = 0.8
) -> int | None:
    raise NotImplementedError


def accepts_at(limit: float, *, decimals: int) -> float:
    raise NotImplementedError


def flags(counts: Sequence[Counts], *, alpha: float = 0.05, power: float = 0.8) -> tuple[Flag, ...]:
    raise NotImplementedError


def limit_rise(
    rate_old: float, runs_old: int, runs_new: int, *, alpha: float = 0.05, power: float = 0.8
) -> float:
    raise NotImplementedError
