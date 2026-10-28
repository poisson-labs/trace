"""Guidance that would not work is not offered (the statistician's audit of TF15, findings 1a and
2): fix-check never says no value of --max-mde accepts a design that a value does accept, and
compare never advises the number of tries per input that has just fallen short."""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path

import numpy as np

from conftest import Row, build_store, compare, roots
from fixcheck_support import fix_check, pair_store

ALL = ("--inputs", "all")

# 14 inputs of 3 tries a side: the range, -25.0 to +11.1 points, is reliable, and no drop limit
# exists; at --max-mde 0.2 the range alone reads too small to tell, and 0.2504 reads otherwise
NO_DROP_LIMIT = [
    (0, 3, 0, 3), (2, 3, 0, 3), (0, 3, 1, 3), (0, 3, 0, 3), (1, 3, 0, 3), (0, 3, 1, 3), (2, 3, 1, 3),
    (1, 3, 0, 3), (1, 3, 0, 3), (1, 3, 0, 3), (0, 3, 2, 3), (0, 3, 1, 3), (1, 3, 0, 3), (1, 3, 1, 3),
]


def test_fix_check_offers_the_ceiling_a_reliable_range_accepts(tmp_path: Path) -> None:
    root = pair_store(tmp_path, NO_DROP_LIMIT)
    d = fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", "0.2", "--json").json()
    assert d["verdict"] == "too small to tell" and d["limits"]["drop"] is None, (d["verdict"], d["limits"])
    offered = d["guidance"]["accepts_at"]
    assert offered is not None, d["guidance"]
    assert offered == math.ceil(max(-d["difference"]["lo"], d["difference"]["hi"]) * 1e4) / 1e4
    again = fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", repr(offered), "--json").json()
    assert again["verdict"] == "no significant difference", again["difference"]
    out = fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", "0.2").out
    assert "no value of --max-mde accepts" not in out


def _short_design(rng: np.random.Generator) -> tuple[list[tuple[str, int, bool]], list[tuple[str, int, bool]], float]:
    """Two runs of 3 tries on each of 20 inputs, drawn from the guidance's own model, that fall
    just short of a ratio the model's expected information at 3 tries reaches."""
    from poisson_trace.survival import fit_cells, information_limit, logrank_stratified, tries_needed

    while True:
        runs: list[list[tuple[str, int, bool]]] = [[], []]
        for cell in range(20):
            for arm in runs:
                fail, end = rng.exponential(1 / 0.3, 3), rng.exponential(1 / 0.3, 3)
                for t, died in zip(np.minimum(fail, end), fail < end, strict=True):
                    arm.append((f"i{cell}", 5 + max(1, math.ceil(t)), bool(died)))
        lr = logrank_stratified(runs[0], runs[1])
        if lr.p < 0.05 or not lr.variance > 0:
            continue
        asked = round(information_limit(lr.variance) * 0.98, 3)
        needed = tries_needed(fit_cells(runs[0] + runs[1]), asked)
        if needed is not None and needed <= 3:
            return runs[0], runs[1], asked


def test_compare_never_advises_the_tries_that_fell_short(tmp_path: Path) -> None:
    a, b, asked = _short_design(np.random.default_rng(7))
    for run, rows in (("a", a), ("b", b)):
        build_store(tmp_path, run, [
            dataclasses.replace(Row({"cell": cell}, "fail" if died else "ok", roots(["tool"] * step)),
                                replicate_index=j)
            for j, (cell, step, died) in enumerate(rows)
        ])
    c = compare(tmp_path, "a", "b", ["fail"], asked, "--json").json()["comparison"]
    assert c["verdict"] == "too small to tell", c
    assert c["guidance"]["repeats"] is not None and c["guidance"]["repeats"] > 3, c["guidance"]
