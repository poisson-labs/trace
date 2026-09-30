"""What a reader hands the writer: one row per case read, and the run they make.

Standard library only.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

STARTED_FROM: tuple[str, ...] = ("given", "file name", "earliest span", "file time")

# The longest text that is its own case id.
_OWN_ID = 80


class Refusal(Exception):
    """One sentence, exit 1, nothing written."""


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
    counts: Mapping[str, int] = field(default_factory=dict)  # the reader's own, as printed


def digest_id(text: str) -> str:
    """``sha256:`` and the first 16 hex characters of the SHA-256 of the text's UTF-8 bytes:
    an identity that holds nothing of the text."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def case_id(text: str) -> str:
    """The text itself when it is printable and at most 80 characters, else its digest. An
    empty text identifies nothing and raises ``ValueError``."""
    if text == "":
        raise ValueError("an empty text is not a case")
    if len(text) <= _OWN_ID and text.isprintable():
        return text
    return digest_id(text)
