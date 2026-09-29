"""The console script ``poisson-trace-import``."""

from __future__ import annotations

from collections.abc import Sequence

READERS: tuple[str, ...] = ("deepeval", "ragas", "langsmith", "otel", "lemma")


def main(argv: Sequence[str] | None = None) -> int:
    raise NotImplementedError
