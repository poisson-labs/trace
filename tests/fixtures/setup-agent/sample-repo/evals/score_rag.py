"""Scoring for the retrieval evaluation.

``ragas`` scores each question's answer for faithfulness, answer relevancy and answer
correctness and writes one row per question (``case``) into ``evals/results/``. The team reads
faithfulness alone: a row passes when its faithfulness reaches ``FAITHFULNESS_CUT``, and a
score below the cut misses it.
"""

from __future__ import annotations

FAITHFULNESS_CUT = 0.5
METRIC = "faithfulness"


def passes(row: dict[str, float]) -> bool:
    """Whether a scored row passes: its faithfulness is at the cut or above it."""
    return row[METRIC] >= FAITHFULNESS_CUT
