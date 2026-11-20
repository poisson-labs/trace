"""Normalised rows as the plain per-case inputs ``stats/continuous.py`` takes.

Each normalised ``Row`` becomes one ``Try``: its value for every measure (``None`` where the
source did not record it; a recorded zero stays a zero), how it ended (its failure kind, or
``None`` for a try that finished), its behavioural signals and its repeat number (``None`` where
only the order read says which it is). Tries keep the order they were read in within a case. No
verb imports this module yet: nothing prints the continuous table.
"""

from __future__ import annotations

from collections.abc import Iterable

from poisson_trace.ingest.rows import Row
from poisson_trace.stats.continuous import MEASURES, Try, Version


def try_of(row: Row) -> Try:
    """``row`` as one try: every measure, how it ended, its signals and its repeat."""
    return Try(
        values={measure: getattr(row, measure) for measure in MEASURES},
        ending=row.failure_kind,
        signals=tuple(row.signals),
        repeat=row.repeat,
    )


def tries_of(rows: Iterable[Row]) -> dict[str, tuple[Try, ...]]:
    """The tries of each case, in the order read."""
    out: dict[str, list[Try]] = {}
    for row in rows:
        out.setdefault(row.case, []).append(try_of(row))
    return {case: tuple(tries) for case, tries in out.items()}


def version_of(
    rows: Iterable[Row], name: str, label: str = "old", cap_s: float | None = None
) -> Version:
    """The rows of one run as a ``Version``: its name, its cases' tries, a label for sentences
    and the cap on one try's time where the run had one."""
    return Version(name=name, cases=tries_of(rows), label=label, cap_s=cap_s)
