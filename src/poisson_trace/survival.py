"""The estimators: Kaplan-Meier with Greenwood, Aalen-Johansen with a bootstrap band, the
stratified log-rank, Schoenfeld's minimum detectable hazard ratio, and Benjamini-Hochberg.

numpy and scipy only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class KMCurve:
    steps: np.ndarray
    at_risk: np.ndarray
    deaths: np.ndarray
    survival: np.ndarray
    var: np.ndarray

    def at(self, step: int) -> tuple[float, float]:
        raise NotImplementedError

    def median(self) -> int | None:
        raise NotImplementedError


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


def kaplan_meier(index: np.ndarray, died: np.ndarray) -> KMCurve:
    raise NotImplementedError


def aalen_johansen(
    index: np.ndarray, died: np.ndarray, cause: np.ndarray, causes: Sequence[str]
) -> AJCurve:
    raise NotImplementedError


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
    raise NotImplementedError


def logrank_stratified(
    a: Sequence[tuple[str, int, bool]], b: Sequence[tuple[str, int, bool]]
) -> LogRank:
    raise NotImplementedError


def mde_hazard_ratio(
    deaths: int, share_a: float, *, alpha: float = 0.05, power: float = 0.8
) -> float:
    raise NotImplementedError


def bh(p: np.ndarray, q: float) -> np.ndarray:
    raise NotImplementedError
