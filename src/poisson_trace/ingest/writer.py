"""The one module under ``ingest/`` that imports ``proofload``: a Run becomes one new run."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from poisson_trace.ingest.rows import Run


@dataclass(frozen=True)
class Written:
    run: str
    rows: int
    cases: int
    repeats_min: int
    repeats_max: int
    outcomes: Mapping[str, int]
    no_outcome: Mapping[str, int]


def write(run: Run, root: Path) -> Written:
    raise NotImplementedError
