"""The cut: a score becomes an outcome at a cut the user declares, with its side.

Standard library only; the local product's judges import it as well.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MET: str = "met"
MISSED: str = "missed"


@dataclass(frozen=True)
class Cut:
    """``Cut(0.7, "below")``: a score under 0.7 missed the cut; a score equal to it met it."""

    cut: float
    side: Literal["below", "above"]

    def missed(self, score: float) -> bool:
        raise NotImplementedError

    def outcome(self, score: float) -> str:
        raise NotImplementedError
