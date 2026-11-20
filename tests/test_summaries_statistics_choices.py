"""Choices the statistics make where the frozen tests leave room: where a
reliable range decides too small to tell and the tries were short of the size asked, the ceiling
offered holds the range as well as the drop limit, so that given, it reads otherwise; and the
tries compare offers are those whose expected log-rank information, in closed form under the
per-input model, reaches what the ratio asked for needs, which a seeded draw of that model agrees
with."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from fixcheck_support import fix_check, pair_store
from summaries_support import draw_run, fit_cells

ALL = ("--inputs", "all")

# 12 inputs, 11 vary, the exact test does not call it (p 0.160); the range, -3.0 to +31.2, reaches
# past the drop limit, 27.8: a ceiling of the drop limit rounded up would read too small to tell
RANGE_PAST_THE_LIMIT = [
    (0, 4, 2, 4), (3, 4, 4, 4), (1, 4, 1, 4), (0, 4, 2, 4), (2, 4, 1, 4), (1, 4, 2, 4), (2, 4, 2, 4),
    (1, 4, 0, 4), (3, 4, 4, 4), (2, 4, 4, 4), (4, 4, 3, 4), (3, 4, 4, 4),
]


def test_the_ceiling_offered_holds_a_reliable_range_reaching_past_the_drop_limit(tmp_path: Path) -> None:
    root = pair_store(tmp_path, RANGE_PAST_THE_LIMIT)
    d = fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", "0.2", "--json").json()
    assert d["verdict"] == "too small to tell"
    drop, hi = d["limits"]["drop"], d["difference"]["hi"]
    assert 0.2 < drop < hi, (drop, d["difference"])
    offered = d["guidance"]["accepts_at"]
    assert offered >= hi, (offered, hi)
    again = fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", repr(offered), "--json").json()
    assert again["verdict"] == "no significant difference", again["difference"]
    # the drop limit alone, rounded up, would not have moved the verdict
    limit_only = fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", repr(math.ceil(drop * 1e4) / 1e4), "--json")
    assert limit_only.json()["verdict"] == "too small to tell"


@pytest.mark.math
def test_the_expected_information_is_the_mean_of_seeded_draws_of_the_model() -> None:
    from poisson_trace.survival import expected_information, logrank_stratified

    rows = [("A", s, True) for s in range(2, 12)] + [("A", s, False) for s in (12, 13, 14)]
    rows += [("B", s, s % 3 == 0) for s in range(1, 9)] + [("B", s, True) for s in (4, 6)]
    fit = fit_cells(rows)
    for repeats in (1, 3, 8):
        rng = np.random.default_rng(repeats)
        draws = np.array([logrank_stratified(draw_run(rng, fit, repeats), draw_run(rng, fit, repeats)).variance
                          for _ in range(4000)])
        se = draws.std() / math.sqrt(len(draws))
        assert abs(expected_information(fit, repeats) - draws.mean()) < 4.5 * se, (repeats, draws.mean(), se)


def test_where_s_median_of_an_even_number_of_failed_tries_is_the_lower_middle_step(make_store) -> None:  # type: ignore[no-untyped-def]
    """Two failed tries, at steps 2 and 7, and one that finished: the median step of the failed
    tries is a step a try reached, the lower of the two middle ones."""
    from conftest import Row, roots, where

    cell = {"cell": "A"}
    rows = [Row(cell, "fail", roots(["llm"] * 2), replicate_index=0),
            Row(cell, "fail", roots(["llm"] * 7), replicate_index=1),
            Row(cell, "ok", roots(["llm"] * 9), replicate_index=2)]
    root, run = make_store(rows)
    assert where(root, run, ["fail"], "--json").json()["median_step"] == 2
