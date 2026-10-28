"""TF15-S43 (PENDING Taylor's yes/no, Session A log rulings.md): compare's per-kind column "could
not have detected a hazard ratio below" comes from each kind's own log-rank information, as ST5
makes the overall limit do: exp((z_{1-a/2} + z_{0.8}) / sqrt(V_k)), V_k the cause-specific
stratified log-rank's variance, in place of Schoenfeld's d_k / 4.

Revert this file's commit if the answer is no; the per-kind column then keeps Schoenfeld's number.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from conftest import TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, compare, deaths_rows
from tf15_support import z_sum


def _variance(a, b) -> float:  # type: ignore[no-untyped-def]
    """The stratified log-rank's variance by the textbook formula, cell by cell: a test-local
    oracle (the same sums as test_survival's ``_cell_terms``)."""
    v = 0.0
    for cell in sorted({c for c, _, _ in a} & {c for c, _, _ in b}):
        t_a = np.array([s for c, s, _ in a if c == cell]); o_a = np.array([d for c, _, d in a if c == cell])
        t_b = np.array([s for c, s, _ in b if c == cell]); o_b = np.array([d for c, _, d in b if c == cell])
        for x in np.unique(np.concatenate([t_a[o_a], t_b[o_b]])):
            n_a, n_b = int(np.sum(t_a >= x)), int(np.sum(t_b >= x))
            n = n_a + n_b
            d = int(np.sum((t_a == x) & o_a)) + int(np.sum((t_b == x) & o_b))
            if n > 1 and d:
                v += n_a * n_b * d * (n - d) / (n * n * (n - 1))
    return v


def test_tf15_s43_tau2_one_kind_has_the_overall_limit() -> None:
    d = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.3, "--json").json()
    assert d["per_cause"][0]["mde_hazard_ratio"] == pytest.approx(d["comparison"]["mde_hazard_ratio"], rel=1e-9)
    assert d["per_cause"][0]["mde_hazard_ratio"] == pytest.approx(1.6032831137037962, abs=1e-6)


def test_tf15_s43_each_kind_from_its_own_information(two_run_store) -> None:  # type: ignore[no-untyped-def]
    llm_a, tool_a = [2, 3, 5, 7, 9, 11], [4, 6, 8]
    llm_b, tool_b = [3, 4, 6, 9, 10], [2, 5, 7, 12]
    root = two_run_store(deaths_rows(llm_a) + deaths_rows(tool_a, kind="tool", start_rep=10),
                         deaths_rows(llm_b) + deaths_rows(tool_b, kind="tool", start_rep=10))
    d = compare(root, "a", "b", ["fail"], 100.0, "--json").json()
    rows = {r["cause"]: r for r in d["per_cause"]}
    for kind, (mine_a, mine_b) in {"llm": (llm_a, llm_b), "tool": (tool_a, tool_b)}.items():
        # a death of the other kind is censored at its step
        a = [("A", s, s in mine_a) for s in llm_a + tool_a]
        b = [("A", s, s in mine_b) for s in llm_b + tool_b]
        v = _variance(a, b)
        assert rows[kind]["mde_hazard_ratio"] == pytest.approx(math.exp(z_sum() / math.sqrt(v)), rel=1e-9), kind
