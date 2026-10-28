"""TR12 to TR20, TR22, TR24, TR25: the estimators, against hand-computed answers, Prove, and
lifelines (a development oracle, skipped when absent)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from conftest import (
    CS, CS_EVENTS, CS_RECORD, TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, compare, deaths_rows, where,
)

lifelines = pytest.importorskip("lifelines")
from lifelines import AalenJohansenFitter, KaplanMeierFitter  # noqa: E402
from lifelines.statistics import logrank_test  # noqa: E402

SLOW = settings(max_examples=60, deadline=None)


@st.composite
def samples(draw, min_size: int = 1, max_size: int = 60):  # type: ignore[no-untyped-def]
    n = draw(st.integers(min_size, max_size))
    index = draw(st.lists(st.integers(1, 30), min_size=n, max_size=n))
    died = draw(st.lists(st.booleans(), min_size=n, max_size=n))
    assume(any(died))
    return np.array(index, dtype=np.int64), np.array(died, dtype=bool)


def _placed(root, run, events):  # type: ignore[no-untyped-def]
    from poisson_prove.store import Store

    from poisson_trace.clock import place

    store = Store(root)
    placed = place(store.manifest(run), store.read(run, meta=False, trace="envelope"), store.tally(run),
                   events=frozenset(events), by="kind")
    index = np.array([p.index for p in placed.rows], dtype=np.int64)
    died = np.array([p.died for p in placed.rows], dtype=bool)
    cause = np.array([p.cause for p in placed.rows], dtype=object)
    return index, died, cause


# ---------- TR12 ----------


def test_tr12_no_censoring_equals_the_empirical_survival_function() -> None:
    from poisson_trace.survival import kaplan_meier

    index = np.array([3, 5, 5, 7, 9, 9, 12, 15, 2, 4])
    km = kaplan_meier(index, np.ones(len(index), dtype=bool))
    assert km.steps.tolist() == [2, 3, 4, 5, 7, 9, 12, 15]
    for step, s in zip(km.steps, km.survival):
        assert s == pytest.approx(np.mean(index > step), abs=1e-12)


def test_tr12_starts_at_one_is_non_increasing_and_right_continuous() -> None:
    from poisson_trace.survival import kaplan_meier

    km = kaplan_meier(np.array([2, 4, 4, 6, 8]), np.array([True, True, False, True, False]))
    assert km.at(0) == (1.0, 0.0)
    assert km.at(1) == (1.0, 0.0)
    assert np.all(np.diff(km.survival) <= 0)
    assert km.at(4)[0] == km.survival[1]
    assert km.at(5)[0] == km.survival[1]
    assert km.at(100)[0] == km.survival[-1]


def test_tr12_ties_at_one_step_are_one_factor() -> None:
    from poisson_trace.survival import kaplan_meier

    km = kaplan_meier(np.array([3, 3, 3, 5]), np.array([True, True, True, True]))
    assert km.steps.tolist() == [3, 5]
    assert km.deaths.tolist() == [3, 1]
    assert km.at_risk.tolist() == [4, 1]
    assert km.survival.tolist() == [0.25, 0.0]


# ---------- TR13 ----------


@SLOW
@given(samples())
def test_tr13_kaplan_meier_matches_prove_and_lifelines(sample) -> None:  # type: ignore[no-untyped-def]
    from poisson_prove.survival import kaplan_meier as prove_km

    from poisson_trace.survival import kaplan_meier

    index, died = sample
    ours = kaplan_meier(index, died)
    prove = prove_km(index.astype(np.float64), died)
    assert ours.steps.tolist() == prove.times.tolist()
    np.testing.assert_allclose(ours.survival, prove.survival, rtol=0, atol=1e-12)
    np.testing.assert_allclose(ours.var, prove.var, rtol=0, atol=1e-9)
    kmf = KaplanMeierFitter().fit(index, died)
    sf = kmf.survival_function_at_times(ours.steps).to_numpy()
    np.testing.assert_allclose(ours.survival, sf, rtol=0, atol=1e-12)
    cumsq = kmf._cumulative_sq_.reindex(kmf.timeline).ffill().loc[ours.steps].to_numpy()
    np.testing.assert_allclose(ours.var, sf**2 * cumsq, rtol=0, atol=1e-9)


# ---------- TR14 ----------


@pytest.mark.parametrize("root,run,events", [(TAU2, TAU2_A, TAU2_EVENTS), (CS, CS_RECORD, CS_EVENTS)])
def test_tr14_band_is_plain_greenwood_clipped(root, run, events) -> None:  # type: ignore[no-untyped-def]
    result = where(root, run, events, "--at", "1", "--at", "500", "--json")
    assert result.code == 0, result.text
    for row in result.json()["curve"] + result.json()["at"]:
        s, var = row["survival"], row.get("var")
        if var is None:
            continue
        half = 1.96 * math.sqrt(var)
        assert row["lo"] == pytest.approx(max(0.0, s - half), abs=1e-12)
        assert row["hi"] == pytest.approx(min(1.0, s + half), abs=1e-12)
        assert row["lo"] <= s <= row["hi"]
    first, last = result.json()["at"]
    assert (first["survival"], first["lo"], first["hi"]) == (1.0, 1.0, 1.0)
    assert last["lo"] <= last["survival"] <= last["hi"]


# ---------- TR15 ----------


def _identity(index, died, cause) -> None:  # type: ignore[no-untyped-def]
    from poisson_trace.survival import aalen_johansen, kaplan_meier

    causes = sorted({c for c, d in zip(cause, died) if d})
    aj = aalen_johansen(index, died, cause, causes)
    km = kaplan_meier(index, died)
    assert aj.steps.tolist() == km.steps.tolist()
    total = sum(aj.incidence[k] for k in causes)
    np.testing.assert_allclose(total, 1.0 - km.survival, rtol=0, atol=1e-12)
    np.testing.assert_allclose(aj.survival, km.survival, rtol=0, atol=1e-12)
    for k in causes:
        assert np.all(np.diff(aj.incidence[k]) >= -1e-15)


@pytest.mark.parametrize("root,run,events", [(TAU2, TAU2_A, TAU2_EVENTS), (TAU2, TAU2_B, TAU2_EVENTS), (CS, CS_RECORD, CS_EVENTS)])
def test_tr15_competing_risks_identity_on_the_fixtures(root, run, events) -> None:  # type: ignore[no-untyped-def]
    _identity(*_placed(root, run, events))


@SLOW
@given(samples(), st.lists(st.sampled_from(["a", "b", "c"]), min_size=60, max_size=60))
def test_tr15_competing_risks_identity_on_random_data(sample, labels) -> None:  # type: ignore[no-untyped-def]
    index, died = sample
    cause = np.array(labels[: len(index)], dtype=object)
    _identity(index, died, cause)


def test_tr15_one_cause_equals_one_minus_survival() -> None:
    from poisson_trace.survival import aalen_johansen, kaplan_meier

    index = np.array([2, 3, 3, 5, 8, 8, 9])
    died = np.array([1, 1, 0, 1, 1, 0, 1], dtype=bool)
    cause = np.array(["llm"] * 7, dtype=object)
    aj = aalen_johansen(index, died, cause, ["llm"])
    km = kaplan_meier(index, died)
    np.testing.assert_allclose(aj.incidence["llm"], 1.0 - km.survival, rtol=0, atol=1e-12)


# ---------- TR16 ----------


@st.composite
def distinct_samples(draw):  # type: ignore[no-untyped-def]
    n = draw(st.integers(6, 40))
    times = sorted(draw(st.sets(st.integers(1, 200), min_size=n, max_size=n)))
    labels = draw(st.lists(st.sampled_from(["a", "b", "c", None]), min_size=n, max_size=n))
    assume(all(k in labels for k in ("a", "b", "c")))
    index = np.array(times, dtype=np.int64)
    died = np.array([lab is not None for lab in labels], dtype=bool)
    cause = np.array([lab if lab is not None else "none" for lab in labels], dtype=object)
    return index, died, cause


@settings(max_examples=25, deadline=None)
@given(distinct_samples())
def test_tr16_aalen_johansen_matches_lifelines_on_distinct_death_steps(sample) -> None:  # type: ignore[no-untyped-def]
    from poisson_trace.survival import aalen_johansen

    index, died, cause = sample
    aj = aalen_johansen(index, died, cause, ["a", "b", "c"])
    codes = {"a": 1, "b": 2, "c": 3}
    observed = np.array([codes[c] if d else 0 for c, d in zip(cause, died)])
    for k, code in codes.items():
        fitter = AalenJohansenFitter(calculate_variance=False).fit(index, observed, event_of_interest=code)
        cd = fitter.cumulative_density_.iloc[:, 0]
        for step, value in zip(aj.steps, aj.incidence[k]):
            expected = float(cd[cd.index <= step].iloc[-1])
            assert value == pytest.approx(expected, abs=1e-9), (k, step)


# ---------- TR17 ----------


def test_tr17_bootstrap_band_is_deterministic_and_seed_sensitive() -> None:
    from poisson_trace.survival import aalen_johansen, bootstrap_band

    index, died, cause = _placed(CS, CS_RECORD, CS_EVENTS)
    causes = ["llm", "agent"]
    aj = aalen_johansen(index, died, cause, causes)
    at = [int(x) for x in aj.steps[::2]] + [int(aj.steps[-1])]
    one = bootstrap_band(index, died, cause, causes, at, b=300, seed=0)
    two = bootstrap_band(index, died, cause, causes, at, b=300, seed=0)
    other = bootstrap_band(index, died, cause, causes, at, b=300, seed=1)
    for k in causes:
        assert one[k][0].tolist() == two[k][0].tolist()
        assert one[k][1].tolist() == two[k][1].tolist()
    assert any(one[k][0].tolist() != other[k][0].tolist() or one[k][1].tolist() != other[k][1].tolist() for k in causes)
    for k in causes:
        for j, q in enumerate(at):
            i = int(np.searchsorted(aj.steps, q, side="right")) - 1
            point = float(aj.incidence[k][i])
            assert one[k][0][j] <= point + 1e-12
            assert one[k][1][j] >= point - 1e-12


def test_tr17_bootstrap_band_via_the_cli_is_byte_stable_and_contains_the_point() -> None:
    a = where(CS, CS_RECORD, CS_EVENTS, "--boot", "200", "--seed", "7", "--json")
    b = where(CS, CS_RECORD, CS_EVENTS, "--boot", "200", "--seed", "7", "--json")
    c = where(CS, CS_RECORD, CS_EVENTS, "--boot", "200", "--seed", "8", "--json")
    assert a.code == b.code == c.code == 0, a.text + c.text
    assert a.out == b.out
    assert a.out != c.out
    assert a.json()["bootstrap"] == {"b": 200, "seed": 7}
    for row in a.json()["causes"]:
        assert row["lo"] - 1e-12 <= row["f"] <= row["hi"] + 1e-12


def test_tr17_identical_rows_give_a_degenerate_band() -> None:
    from poisson_trace.survival import bootstrap_band

    index = np.full(9, 5, dtype=np.int64)
    died = np.ones(9, dtype=bool)
    cause = np.array(["llm"] * 9, dtype=object)
    band = bootstrap_band(index, died, cause, ["llm"], [5, 7], b=50, seed=3)
    assert band["llm"][0].tolist() == [1.0, 1.0]
    assert band["llm"][1].tolist() == [1.0, 1.0]


# ---------- TR18 ----------


def test_tr18_median_is_the_first_step_at_or_below_one_half() -> None:
    from poisson_trace.survival import kaplan_meier

    exactly_half = kaplan_meier(np.array([3, 3, 4, 4]), np.array([True, True, False, False]))
    assert exactly_half.survival.tolist() == [0.5]
    assert exactly_half.median() == 3
    two_steps = kaplan_meier(np.array([2, 2, 2, 5, 5, 6, 7, 8]), np.array([1, 1, 1, 1, 1, 0, 0, 0], dtype=bool))
    assert two_steps.survival[0] == pytest.approx(0.625)
    assert two_steps.median() == 5


def test_tr18_median_is_none_when_survival_never_reaches_one_half() -> None:
    from poisson_trace.survival import kaplan_meier

    km = kaplan_meier(np.array([2, 4, 6, 8, 9]), np.array([True, False, False, False, False]))
    assert km.median() is None
    result = where(CS, CS_RECORD, CS_EVENTS, "--json")
    assert result.code == 0, result.text
    # ST8 (ruled 2026-10-20): the median step of the failed tries (35 to 59 on cs record, 7 failed)
    assert result.json()["median_step"] == 35
    assert "median_step" in result.json()


# ---------- TR19 ----------


def _cell_terms(t_a, o_a, t_b, o_b):  # type: ignore[no-untyped-def]
    """Per-cell O_A, E_A, V by the textbook formula; a test-local oracle for the sums."""
    o = e = v = 0.0
    for x in np.unique(np.concatenate([t_a[o_a], t_b[o_b]])):
        n_a, n_b = int(np.sum(t_a >= x)), int(np.sum(t_b >= x))
        n = n_a + n_b
        d_a, d_b = int(np.sum((t_a == x) & o_a)), int(np.sum((t_b == x) & o_b))
        d = d_a + d_b
        if n == 0 or d == 0:
            continue
        o += d_a
        e += n_a * d / n
        if n > 1:
            v += n_a * n_b * d * (n - d) / (n * n * (n - 1))
    return o, e, v


def _arm(cells, rng):  # type: ignore[no-untyped-def]
    out = []
    for c in cells:
        for _ in range(rng.integers(3, 9)):
            out.append((c, int(rng.integers(1, 15)), bool(rng.integers(0, 2))))
    return out


def test_tr19_stratified_statistic_is_the_sum_over_cells() -> None:
    from poisson_trace.survival import logrank_stratified

    rng = np.random.default_rng(19)
    a = _arm(["c1", "c2", "c3"], rng)
    b = _arm(["c1", "c2", "c3"], rng)
    result = logrank_stratified(a, b)
    o = e = v = 0.0
    for c in ("c1", "c2", "c3"):
        t_a = np.array([i for cc, i, _ in a if cc == c]); o_a = np.array([d for cc, _, d in a if cc == c], dtype=bool)
        t_b = np.array([i for cc, i, _ in b if cc == c]); o_b = np.array([d for cc, _, d in b if cc == c], dtype=bool)
        oo, ee, vv = _cell_terms(t_a, o_a, t_b, o_b)
        o, e, v = o + oo, e + ee, v + vv
    assert result.cells == 3
    assert result.observed_a == pytest.approx(o, abs=1e-12)
    assert result.expected_a == pytest.approx(e, abs=1e-12)
    assert result.variance == pytest.approx(v, abs=1e-12)
    assert result.statistic == pytest.approx((o - e) ** 2 / v, abs=1e-12)


def test_tr19_a_cell_in_one_run_only_contributes_nothing() -> None:
    from poisson_trace.survival import logrank_stratified

    rng = np.random.default_rng(20)
    a = _arm(["c1", "c2"], rng)
    b = _arm(["c1", "c2"], rng)
    base = logrank_stratified(a, b)
    extra = logrank_stratified(a + _arm(["only_a"], rng), b + _arm(["only_b"], rng))
    assert extra == base
    assert extra.cells == 2


def test_tr19_excluded_cells_are_counted_in_the_comparison(two_run_store) -> None:  # type: ignore[no-untyped-def]
    from conftest import CELL_A, CELL_B, Row, roots

    rows_a = deaths_rows([2, 3, 5, 7]) + [Row({"cell": "only_a"}, "fail", roots(["llm"] * 3), replicate_index=9)]
    rows_b = deaths_rows([3, 4, 6, 9, 11], cell=CELL_A) + [Row(CELL_B, "fail", roots(["llm"] * 3), replicate_index=9)]
    root = two_run_store(rows_a, rows_b)
    result = compare(root, "a", "b", ["fail"], 100.0, "--json")
    assert result.code in (0, 2), result.text
    comparison = result.json()["comparison"]
    assert comparison["cells"] == 1
    assert comparison["excluded_cells"] == {"a_only": 1, "b_only": 1}
    # ST5 (ruled 2026-10-20): the minimum detectable hazard ratio is the common cell's log-rank
    # information, exp((z_0.975 + z_0.8) / sqrt(V)), V by the textbook formula over that cell alone
    t_a, o_a = np.array([2, 3, 5, 7]), np.ones(4, dtype=bool)
    t_b, o_b = np.array([3, 4, 6, 9, 11]), np.ones(5, dtype=bool)
    _, _, v = _cell_terms(t_a, o_a, t_b, o_b)
    assert comparison["variance"] == pytest.approx(v, abs=1e-12)
    from scipy import stats

    z = float(stats.norm.isf(0.025)) + float(stats.norm.ppf(0.8))
    assert comparison["mde_hazard_ratio"] == pytest.approx(math.exp(z / math.sqrt(v)), abs=1e-12)


def test_tr19_one_cell_equals_the_pooled_test() -> None:
    from poisson_prove.diff import _logrank

    from poisson_trace.survival import logrank_stratified

    rng = np.random.default_rng(21)
    a = _arm(["one"], rng)
    b = _arm(["one"], rng)
    result = logrank_stratified(a, b)
    t_a = np.array([i for _, i, _ in a], dtype=np.float64); o_a = np.array([d for _, _, d in a], dtype=bool)
    t_b = np.array([i for _, i, _ in b], dtype=np.float64); o_b = np.array([d for _, _, d in b], dtype=bool)
    stat, p = _logrank(t_a, o_a, t_b, o_b)
    assert result.cells == 1
    assert result.statistic == pytest.approx(stat, abs=1e-12)
    assert result.p == pytest.approx(p, abs=1e-12)


# ---------- TR20 ----------


@SLOW
@given(samples(min_size=2), samples(min_size=2))
def test_tr20_one_cell_logrank_matches_prove_and_lifelines(sa, sb) -> None:  # type: ignore[no-untyped-def]
    from poisson_prove.diff import _logrank

    from poisson_trace.survival import logrank_stratified

    (ia, da), (ib, db) = sa, sb
    ours = logrank_stratified([("c", int(i), bool(d)) for i, d in zip(ia, da)],
                              [("c", int(i), bool(d)) for i, d in zip(ib, db)])
    stat, p = _logrank(ia.astype(np.float64), da, ib.astype(np.float64), db)
    assert ours.statistic == pytest.approx(stat, abs=1e-12)
    assert ours.p == pytest.approx(p, abs=1e-12)
    if ours.variance > 0:
        ll = logrank_test(ia, ib, da, db)
        assert ours.statistic == pytest.approx(ll.test_statistic, abs=1e-9)
        assert ours.p == pytest.approx(ll.p_value, abs=1e-9)


# ---------- TR22 ----------


def test_tr22_schoenfeld_minimum_detectable_hazard_ratio() -> None:
    from poisson_trace.survival import mde_hazard_ratio

    assert mde_hazard_ratio(100, 0.5, alpha=0.05, power=0.8) == pytest.approx(1.7512, abs=1e-4)
    assert mde_hazard_ratio(25, 0.5) == pytest.approx(3.0668, abs=1e-4)
    values = [mde_hazard_ratio(d, 0.5) for d in (10, 20, 50, 100, 400)]
    assert values == sorted(values, reverse=True)
    shares = [mde_hazard_ratio(100, p) for p in (0.1, 0.3, 0.5, 0.7, 0.9)]
    assert min(shares) == shares[2]
    with pytest.raises(ValueError):
        mde_hazard_ratio(0, 0.5)


# ---------- TR24 ----------


@SLOW
@given(st.lists(st.floats(0.0, 1.0), min_size=1, max_size=12))
def test_tr24_benjamini_hochberg_matches_prove_and_is_monotone(p) -> None:  # type: ignore[no-untyped-def]
    from poisson_prove.diff import bh as prove_bh

    from poisson_trace.survival import bh

    arr = np.array(p, dtype=np.float64)
    ours = bh(arr, 0.05)
    np.testing.assert_allclose(ours, prove_bh(arr, 0.05), rtol=0, atol=1e-12)
    order = np.argsort(arr, kind="stable")
    assert np.all(np.diff(ours[order]) >= -1e-12)


def test_tr24_per_cause_q_values_are_benjamini_hochberg_of_the_raw_p() -> None:
    from poisson_trace.survival import bh

    from conftest import CS_REPLAY

    result = compare(CS, CS_RECORD, CS_REPLAY, CS_EVENTS, 100.0, "--json")
    assert result.code in (0, 2), result.text
    per = result.json()["per_cause"]
    assert [row["cause"] for row in per] == ["llm", "agent"]
    raw = np.array([row["p"] for row in per])
    np.testing.assert_allclose([row["q"] for row in per], bh(raw, 0.05), rtol=0, atol=1e-12)
    assert all(row["q"] >= row["p"] - 1e-12 for row in per)


# ---------- TR25 ----------


def test_tr25_survival_at_a_step_with_no_death_is_the_last_death_before_it() -> None:
    result = where(TAU2, TAU2_A, TAU2_EVENTS, "--at", "31", "--at", "8", "--at", "44", "--at", "45", "--json")
    assert result.code == 0, result.text
    data = result.json()
    curve = {row["step"]: row for row in data["curve"]}
    at = {row["step"]: row for row in data["at"]}
    assert 31 not in curve and 30 in curve
    assert at[31]["survival"] == curve[30]["survival"]
    assert at[31]["lo"] == curve[30]["lo"] and at[31]["hi"] == curve[30]["hi"]
    assert at[8] == {"step": 8, "survival": 1.0, "lo": 1.0, "hi": 1.0}
    assert at[44]["survival"] == curve[44]["survival"] == at[45]["survival"]


def test_tr25_compare_diff_rows_are_the_difference_with_a_wald_interval() -> None:
    """ST8 (ruled 2026-10-20): compare's --at rows give, for each run, the share of tries not yet
    failed by the step, as where prints it, and their difference; Greenwood's variance, which the
    Wald interval was built from, belongs to the curve that was retired, so the interval is held
    only to contain the difference here (spec section 9.7 item 8 names no method for it)."""
    a = where(TAU2, TAU2_A, TAU2_EVENTS, "--at", "10", "--at", "20", "--at", "31", "--json")
    b = where(TAU2, TAU2_B, TAU2_EVENTS, "--at", "10", "--at", "20", "--at", "31", "--json")
    c = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.5, "--at", "10", "--at", "20", "--at", "31", "--json")
    assert a.code == b.code == 0 and c.code == 0, a.text + b.text + c.text
    s_a = {r["step"]: r["survival"] for r in a.json()["at"]}
    s_b = {r["step"]: r["survival"] for r in b.json()["at"]}
    rows = c.json()["at"]
    assert [r["step"] for r in rows] == [10, 20, 31]
    for row in rows:
        q = row["step"]
        assert row["survival_a"] == pytest.approx(s_a[q], abs=1e-12)
        assert row["survival_b"] == pytest.approx(s_b[q], abs=1e-12)
        diff = s_b[q] - s_a[q]
        assert row["diff"] == pytest.approx(diff, abs=1e-12)
        assert row["lo"] <= row["diff"] <= row["hi"]


def test_tr24_per_cause_correction_moves_a_q_value_when_it_must(two_run_store) -> None:  # type: ignore[no-untyped-def]
    # Two causes: llm differs between the arms (tiny p), tool is the same rows in both (its
    # cause-specific p is not 1, since the llm deaths it censors differ). With two causes BH
    # gives q_llm = min(2 p_llm, p_tool), which is not p_llm, so a build that skips the
    # correction is caught here.
    from poisson_trace.survival import bh

    tool_rows = deaths_rows(list(range(1, 11)), kind="tool", start_rep=100)
    root = two_run_store(deaths_rows(list(range(1, 16))) + tool_rows, deaths_rows(list(range(16, 31))) + tool_rows)
    result = compare(root, "a", "b", ["fail"], 100.0, "--json")
    assert result.code in (0, 2), result.text
    per = {row["cause"]: row for row in result.json()["per_cause"]}
    assert set(per) == {"llm", "tool"}
    raw = np.array([per["llm"]["p"], per["tool"]["p"]])
    np.testing.assert_allclose([per["llm"]["q"], per["tool"]["q"]], bh(raw, 0.05), rtol=0, atol=1e-12)
    # the correction moves the smaller p: q_llm = min(2 p_llm, p_tool) with p_llm tiny
    assert per["llm"]["p"] < 0.01 < per["tool"]["p"]
    assert per["llm"]["q"] == pytest.approx(min(1.0, 2 * per["llm"]["p"], per["tool"]["p"]), abs=1e-12)
    assert per["llm"]["q"] != per["llm"]["p"]
