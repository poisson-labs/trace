"""The clock and the placement: leaves, step index, cause labels, and where each row lands.

Reads a run only through ``proofload.store.Store``, ``proofload.steps.declaration_check`` and
``proofload.trace.KINDS``. Spans are walked as plain mappings off the envelope.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import pandas as pd
from proofload.store import RunManifest, RunTally

REASONS: tuple[str, ...] = ("died", "ended", "timed out", "capped")
EXCLUSIONS: tuple[str, ...] = (
    "no trace",
    "unreadable trace",
    "no leaf span",
    "no outcome, not a timeout",
)


@dataclass(frozen=True)
class Placed:
    config_hash: str
    index: int
    died: bool
    cause: str
    reason: str


@dataclass(frozen=True)
class Placement:
    rows: tuple[Placed, ...]
    excluded: Mapping[str, int]
    tally: RunTally
    cap: int | None


def place(
    manifest: RunManifest,
    frame: pd.DataFrame,
    tally: RunTally,
    *,
    events: frozenset[str],
    by: Literal["kind", "step"],
) -> Placement:
    raise NotImplementedError
