"""The cut: a score becomes an outcome at a cut the user declares, with its side.

Standard library only; the local product's judges import it as well.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

MET: str = "met"
MISSED: str = "missed"

_SIDES = ("below", "above")


@dataclass(frozen=True)
class Cut:
    """``Cut(0.7, "below")``: a score under 0.7 missed the cut; a score equal to it met it."""

    cut: float
    side: Literal["below", "above"]

    def __post_init__(self) -> None:
        if not isinstance(self.side, str) or self.side not in _SIDES:
            raise ValueError(f"the side of a cut is below or above, not {self.side!r}")
        if math.isnan(self.cut):
            raise ValueError("the cut is not a number")

    def missed(self, score: float) -> bool:
        if math.isnan(score):
            raise ValueError("the score is not a number")
        if self.side == "below":
            return bool(score < self.cut)
        return bool(score > self.cut)

    def outcome(self, score: float) -> str:
        return MISSED if self.missed(score) else MET
