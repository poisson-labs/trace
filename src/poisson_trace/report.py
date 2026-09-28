"""The two reports: markdown to stdout, the JSON structure, and the one SVG. Stdlib only."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WhereReport:
    def to_markdown(self) -> str:
        raise NotImplementedError

    def to_json(self) -> str:
        raise NotImplementedError

    def to_svg(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class CompareReport:
    def to_markdown(self) -> str:
        raise NotImplementedError

    def to_json(self) -> str:
        raise NotImplementedError
