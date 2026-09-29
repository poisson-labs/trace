"""What a reader hands the writer: one row per case read, and the run they make.

Standard library only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

STARTED_FROM: tuple[str, ...] = ("given", "file name", "earliest span", "file time")


@dataclass(frozen=True)
class Row:
    case: str
    outcome: str | None
    error: str | None
    score: float | None = None
    spans: tuple[Mapping[str, Any], ...] | None = None
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Run:
    name: str
    tool: str
    rows: tuple[Row, ...]
    started: str
    started_from: str
    declared: Mapping[str, Any]
    files: tuple[Mapping[str, str], ...]


def case_id(text: str) -> str:
    raise NotImplementedError
