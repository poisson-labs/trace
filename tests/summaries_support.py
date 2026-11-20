"""Shared helpers for the TF15 tests (the statistics of fix-check, compare and where, and the
plain summaries): the parts of a printed report by heading, the
summary's labelled lines, and a test-local model of a traced run for compare's detection limit.

Not a test module and not collected. Every number a TF15 test pins is named in the test with the
reference it comes from (an independent statistics check, lifelines, or a
published worked example).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from conftest import norm


def lines_of(out: str) -> list[str]:
    return out.splitlines()


def section(out: str, heading: str) -> list[str]:
    """The lines under ``## {heading}`` up to the next ``## `` heading, blank lines dropped."""
    lines = out.splitlines()
    start = next((i for i, line in enumerate(lines) if line == f"## {heading}"), None)
    assert start is not None, f"no ## {heading} in:\n{out}"
    body = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        if line.strip():
            body.append(line)
    return body


def summary(out: str) -> dict[str, str]:
    """The four labelled lines of ``## Summary`` (``- Label: text``), by label, in order."""
    found: dict[str, str] = {}
    for line in section(out, "Summary"):
        assert line.startswith("- "), line
        label, _, text = line[2:].partition(": ")
        assert text, line
        found[label] = text
    return found


def caveats(out: str) -> list[str]:
    """The bullets of ``## Before you act on this``, each with its continuation lines joined."""
    bullets: list[str] = []
    for line in section(out, "Before you act on this"):
        if line.startswith("- "):
            bullets.append(line[2:])
        else:
            assert bullets, line
            bullets[-1] += " " + line.strip()
    return bullets


def bold_line(out: str) -> str:
    """The one bold verdict line inside the report, without its asterisks."""
    bold = [line for line in out.splitlines() if line.startswith("**") and line.endswith("**")]
    assert len(bold) == 1, bold
    return bold[0][2:-2]


def first_line(out: str) -> tuple[str, str]:
    """The verdict word and the sentence after its two spaces, from the first stdout line."""
    head = out.splitlines()[0]
    for word in ("no significant difference", "too small to tell", "different", "ok"):
        if head.startswith(word + "  "):
            return word, head[len(word) + 2:]
    raise AssertionError(head)


def has(out: str, phrase: str) -> bool:
    return norm(phrase) in norm(out)


# ---------- a test-local model of a traced run, for compare's detection limit ----------
#
# The independent statistics check's model of a traced run, copied: each
# input gets an offset one below its smallest step and
# two exponential clocks per step after it, failing and finishing, fitted from both runs pooled;
# the after run's failing clock is multiplied by the hazard ratio. Its information per failure
# under no change, 0.165 on tau2, matches the fixture's 0.159.


def fit_cells(rows: Sequence[tuple[str, int, bool]]) -> dict[str, tuple[int, float, float]]:
    cells: dict[str, list[tuple[int, bool]]] = {}
    for cell, step, died in rows:
        cells.setdefault(cell, []).append((int(step), bool(died)))
    fit = {}
    for cell, tries in cells.items():
        m = min(s for s, _ in tries) - 1
        exposure = sum(s - m for s, _ in tries)
        died = sum(1 for _, d in tries if d)
        fit[cell] = (m, died / exposure, (len(tries) - died) / exposure)
    return fit


def draw_run(
    rng: np.random.Generator, fit: Mapping[str, tuple[int, float, float]], per_cell: int, hr: float = 1.0
) -> list[tuple[str, int, bool]]:
    out: list[tuple[str, int, bool]] = []
    for cell, (m, lam_f, lam_e) in fit.items():
        lam = lam_f * hr
        total = lam + lam_e
        if total <= 0:
            continue
        t = rng.exponential(1.0 / total, per_cell)
        died = rng.random(per_cell) < lam / total
        steps = m + np.maximum(1, np.ceil(t)).astype(int)
        out.extend((cell, int(s), bool(d)) for s, d in zip(steps, died, strict=True))
    return out


def z_sum(alpha: float = 0.05, power: float = 0.8) -> float:
    from scipy import stats

    return float(stats.norm.isf(alpha / 2.0)) + float(stats.norm.ppf(power))


def ln(x: float) -> float:
    return math.log(x)


def rows_of(data: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list(data["rows"])
