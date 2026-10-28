"""TF15-S20 to TF15-S39: compare's and where's statistics as ruled on 2026-10-20 (spec section
9.7, ST5, ST6 and ST8).

- ST5: compare's detection limit is exp((z_{1-a/2} + z_{0.8}) / sqrt(V)), V the stratified
  log-rank's own variance, in place of Schoenfeld's d/4; its "run each version N times" is the
  smallest number of tries per input per version whose expected V, under a per-input model fitted
  to the two runs (seeded), reaches ((z_{1-a/2} + z_{0.8}) / ln H)^2.
- ST6: compare prints the after-against-before hazard ratio from the log-rank's own numbers (the
  Peto one-step estimate) with its 95% range.
- ST8: where's curve is the share of tries not yet failed by each step, from the Aalen-Johansen
  estimator with "finished without failing" and "timed out" as ends of their own and only capped
  tries censored; the table by kind gives each kind's share failed by the last step; the band
  resamples inputs; the median is that of the failed tries' steps, and the step by which half of
  all tries had failed is printed when reached; compare's --at rows give the same share.

References: the statistics check's own scripts and dumps (sim_compare.py's V and limits, its
fixture_fixes.py Peto estimates, its episode dumps), lifelines' AalenJohansenFitter (0.30.3, the
dev extra) called here as the oracle, and counts over tries where nothing is censored (the
estimator then equals them). log/trace-tf15-a/evidence/references/ prints each number.
"""

from __future__ import annotations

import math
import re

import numpy as np
import pytest
from poisson_prove.store import Store

from conftest import (
    CS, CS_EVENTS, CS_RECORD, CS_REPLAY, SYNTH_EVENTS, TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, Row, compare,
    deaths_rows, norm, roots, span, where,
)
from tf15_support import draw_run, fit_cells, section, z_sum


def _json(result):  # type: ignore[no-untyped-def]
    assert result.code == 0, result.text
    return result.json()


# ---------- ST5: compare's limit and guidance from the test's own information ----------

# the statistics check's sim_compare.py (trace_numbers: V, and exp(2.8016 / sqrt(V))) and its
# fixture_fixes.py; the guidance by its search, settled with 2,000 draws per R in the Session A
# log (guidance_ev.md: expected V at 11 tries 114.437 against the target 114.025, se 0.06; at 10,
# 103.165; cs at 17 tries 16.658 against 16.336, se 0.02; at 16, 15.676)
TAU2_LIMIT, CS_LIMIT = 1.6032831137037962, 7.772177845064068


def test_tf15_s20_tau2_limit_and_guidance() -> None:
    c = _json(compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.3, "--json"))["comparison"]
    assert c["variance"] == pytest.approx(35.222914, abs=1e-5)
    assert c["mde_hazard_ratio"] == pytest.approx(TAU2_LIMIT, abs=1e-6)
    assert c["verdict"] == "too small to tell"
    g = c["guidance"]
    assert g["repeats"] == 11
    assert g["accepts_at"] == pytest.approx(1.604, abs=1e-12)
    out = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.3).out
    assert "--max-mde-hr 1.604" in out
    assert "Schoenfeld" not in out


def test_tf15_s21_tau2_at_one_and_a_half_is_too_small_to_tell_and_the_ceiling_is_accepted() -> None:
    loose = _json(compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.5, "--json"))["comparison"]
    assert loose["verdict"] == "too small to tell" and loose["guidance"] is not None
    accepted = _json(compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.604, "--json"))["comparison"]
    assert accepted["verdict"] == "no significant difference" and accepted["guidance"] is None
    below = _json(compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.603, "--json"))["comparison"]
    assert below["verdict"] == "too small to tell"


def test_tf15_s22_cs_limit_and_guidance() -> None:
    c = _json(compare(CS, CS_RECORD, CS_REPLAY, CS_EVENTS, 2.0, "--json"))["comparison"]
    assert c["variance"] == pytest.approx(1.866667, abs=1e-5)
    assert c["mde_hazard_ratio"] == pytest.approx(CS_LIMIT, abs=1e-6)
    assert c["guidance"]["repeats"] == 17
    assert c["guidance"]["accepts_at"] == pytest.approx(7.773, abs=1e-12)


@pytest.mark.parametrize("alpha", ["0.05", "0.01"])
def test_tf15_s23_the_limit_is_the_information_formula_at_the_stated_alpha(two_run_store, alpha) -> None:  # type: ignore[no-untyped-def]
    root = two_run_store(deaths_rows([2, 3, 5, 7, 9, 11]) + deaths_rows([4, 8], died=False, start_rep=20),
                         deaths_rows([3, 4, 6, 9, 11, 12, 13]) + deaths_rows([5], died=False, start_rep=20))
    c = _json(compare(root, "a", "b", ["fail"], 100.0, "--alpha", alpha, "--json"))["comparison"]
    assert c["variance"] > 0
    assert c["mde_hazard_ratio"] == pytest.approx(math.exp(z_sum(float(alpha)) / math.sqrt(c["variance"])), rel=1e-9)


def _tau2_rows(run: str) -> list[tuple[str, int, bool]]:
    from poisson_trace.clock import place

    store = Store(TAU2)
    placed = place(store.manifest(run), store.read(run, meta=False, trace="envelope"), store.tally(run),
                   events=frozenset(TAU2_EVENTS), by="kind")
    return [(p.config_hash, p.index, p.died) for p in placed.rows]


def test_tf15_s24_a_change_at_the_printed_limit_is_caught_about_four_times_in_five() -> None:
    """The statistics check's model fitted to the two tau2 runs (tf15_support.fit_cells), 4 tries
    per input per version, the after version's failing clock multiplied by the printed limit; 1,000
    seeded draws. Schoenfeld's 1.457 is caught 69-71% of the time there (the check: 71.3% at 4,000
    draws) and the information-based 1.603 88.6%. Monte Carlo se at 0.8 is 0.013; the floor 0.76 is
    4.5 se above Schoenfeld's rate and 9 below the information-based one."""
    from poisson_trace.survival import logrank_stratified

    limit = _json(compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.3, "--json"))["comparison"]["mde_hazard_ratio"]
    fit = fit_cells(_tau2_rows(TAU2_A) + _tau2_rows(TAU2_B))
    rng = np.random.default_rng(15)
    caught = 0
    reps = 1000
    for _ in range(reps):
        a = draw_run(rng, fit, 4)
        b = draw_run(rng, fit, 4, hr=limit)
        lr = logrank_stratified(a, b)
        caught += lr.p < 0.05 and lr.observed_a < lr.expected_a
    assert caught / reps >= 0.76, (limit, caught / reps)


# ---------- ST6: the estimate ----------

# the statistics check's fixture_fixes.py: exp(-(O_A - E_A) / V) and exp(that +- 1.96 / sqrt(V))
PETO = {"tau2": (1.114069, 0.800735, 1.550014), "cs": (1.0, 0.238223, 4.197742)}


@pytest.mark.parametrize("pair,argv", [
    ("tau2", (TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.3)),
    ("cs", (CS, CS_RECORD, CS_REPLAY, CS_EVENTS, 2.0)),
])
def test_tf15_s25_compare_prints_the_after_against_before_hazard_ratio(pair, argv) -> None:  # type: ignore[no-untyped-def]
    c = _json(compare(*argv, "--json"))["comparison"]
    h, lo, hi = PETO[pair]
    assert c["hazard_ratio"] == pytest.approx(h, abs=1e-5)
    assert c["hazard_ratio_lo"] == pytest.approx(lo, abs=1e-5)
    assert c["hazard_ratio_hi"] == pytest.approx(hi, abs=1e-5)
    line = f"hazard ratio, after against before: {h:.2f} ({lo:.2f} to {hi:.2f}, 95%)"
    assert line in norm(compare(*argv).out)


def test_tf15_s26_the_estimate_is_the_peto_one_step_from_the_printed_numbers(two_run_store) -> None:  # type: ignore[no-untyped-def]
    root = two_run_store(deaths_rows([2, 3, 5, 7, 9]) + deaths_rows([4, 8, 10], died=False, start_rep=20),
                         deaths_rows([2, 3, 4, 6, 7, 9, 10]) + deaths_rows([5], died=False, start_rep=20))
    c = _json(compare(root, "a", "b", ["fail"], 100.0, "--json"))["comparison"]
    log_h = -(c["observed_a"] - c["expected_a"]) / c["variance"]
    half = 1.959963984540054 / math.sqrt(c["variance"])
    assert c["hazard_ratio"] == pytest.approx(math.exp(log_h), rel=1e-9)
    assert c["hazard_ratio_lo"] == pytest.approx(math.exp(log_h - half), rel=1e-9)
    assert c["hazard_ratio_hi"] == pytest.approx(math.exp(log_h + half), rel=1e-9)
    assert c["hazard_ratio"] > 1.0  # b fails earlier: after against before is above 1


# ---------- ST8: where, finishing a competing end ----------

# counts over the tries in the statistics check's episode dumps (nothing is censored in these
# runs, so the Aalen-Johansen estimator equals them), cross-checked with lifelines 0.30.3 read
# between whole steps (log/trace-tf15-a/evidence/references/references.md)
WHERE = {
    TAU2_A: {"failed": 0.55, "median": 20, "half": 30, "at": {10: 0.965, 20: 0.695, 30: 0.490}, "last": 44},
    TAU2_B: {"failed": 0.56, "median": 19, "half": 30, "at": {10: 0.970, 20: 0.655, 30: 0.500}, "last": 40},
}


@pytest.mark.parametrize("run", [TAU2_A, TAU2_B])
def test_tf15_s27_tau2_where_ends_at_the_share_that_failed(run) -> None:  # type: ignore[no-untyped-def]
    """On tau2 b exactly half had failed by step 30 (100 of 200): "had failed by" counts a share
    within rounding of one half (1e-9) as half, so step 30 is the step, whatever order the
    estimator sums in."""
    want = WHERE[run]
    data = _json(where(TAU2, run, TAU2_EVENTS, "--at", "10", "--at", "20", "--at", "30", "--json"))
    assert [c["cause"] for c in data["causes"]] == ["llm"]
    assert data["causes"][0]["f"] == pytest.approx(want["failed"], abs=1e-12)
    assert data["curve"][-1]["step"] == want["last"]
    assert data["curve"][-1]["survival"] == pytest.approx(1 - want["failed"], abs=1e-12)
    assert data["median_step"] == want["median"]
    at = {r["step"]: r["survival"] for r in data["at"]}
    for step, value in want["at"].items():
        assert at[step] == pytest.approx(value, abs=1e-12), step
    out = where(TAU2, run, TAU2_EVENTS).out
    text = norm(out)
    assert f"median step of the failed tries: {want['median']}" in text
    assert f"half of all tries had failed by step {want['half']}" in text


def test_tf15_s28_cs_where_shares_by_kind_and_no_half_line() -> None:
    data = _json(where(CS, CS_RECORD, CS_EVENTS, "--json"))
    causes = {c["cause"]: c["f"] for c in data["causes"]}
    assert [c["cause"] for c in data["causes"]] == ["llm", "agent"]
    assert causes["llm"] == pytest.approx(4 / 24, abs=1e-12)
    assert causes["agent"] == pytest.approx(3 / 24, abs=1e-12)
    assert data["curve"][-1]["survival"] == pytest.approx(17 / 24, abs=1e-12)
    assert data["median_step"] == 35
    text = norm(where(CS, CS_RECORD, CS_EVENTS).out)
    # cs is counted in turns, and where says turn (S15, carried into this pair)
    assert "median turn of the failed tries: 35" in text
    assert "half of all tries had failed" not in text


def _chain_capped(cell, cap: int, leaves: int, rep: int) -> Row:  # type: ignore[no-untyped-def]
    """A try at the cap whose leaf count (its step) is ``leaves``: a chain of ``cap - leaves + 1``
    spans, one leaf, beside ``leaves - 1`` root spans."""
    chain = cap - leaves + 1
    spans = [span("c0", None, "agent", 1)] + [span(f"c{i}", f"c{i - 1}", "llm", 1 + i) for i in range(1, chain)]
    spans += [span(f"q{i}", None, "llm", 100 + i) for i in range(leaves - 1)]
    return Row(cell, "fail", spans, replicate_index=rep)


def _competing_rows() -> list[Row]:
    """Every end at its own step (no ties, so lifelines needs no jitter): failures of two kinds,
    finishes, a time-out, and two tries at the cap, one of them censored early at step 5."""
    cell = {"cell": "A"}
    rows = [
        *[Row(cell, "fail", roots(["llm"] * s), replicate_index=r) for r, s in enumerate([2, 7, 9])],
        *[Row(cell, "fail", roots(["tool"] * s), replicate_index=10 + r) for r, s in enumerate([4, 11])],
        *[Row(cell, "ok", roots(["llm"] * s), replicate_index=20 + r) for r, s in enumerate([3, 6, 10, 12])],
        Row(cell, None, roots(["llm"] * 8), error="timeout", replicate_index=30),
        _chain_capped(cell, 14, 5, 40),
        Row(cell, "fail", roots(["llm"] * 14), replicate_index=41),
    ]
    return rows


def test_tf15_s29_where_is_aalen_johansen_with_competing_ends_and_capped_tries_censored(make_store) -> None:  # type: ignore[no-untyped-def]
    from lifelines import AalenJohansenFitter

    root, run = make_store(_competing_rows(), cap=14)
    data = _json(where(root, run, ["fail"], "--json"))
    placement = data["run"]["placement"]
    assert (placement["died"], placement["ended"], placement["timed out"], placement["capped"]) == (5, 4, 1, 2)
    # lifelines: 1 llm, 2 tool, 3 finished, 4 timed out, 0 capped (censored)
    steps = np.array([2, 7, 9, 4, 11, 3, 6, 10, 12, 8, 5, 14])
    codes = np.array([1, 1, 1, 2, 2, 3, 3, 3, 3, 4, 0, 0])

    def cif(code: int) -> tuple[np.ndarray, np.ndarray]:
        f = AalenJohansenFitter(calculate_variance=False).fit(steps, codes, event_of_interest=code)
        return f.cumulative_density_.index.to_numpy(), f.cumulative_density_.iloc[:, 0].to_numpy()

    def at(curve: tuple[np.ndarray, np.ndarray], x: float) -> float:
        i = int(np.searchsorted(curve[0], x, side="right")) - 1
        return 0.0 if i < 0 else float(curve[1][i])

    llm, tool, timed = cif(1), cif(2), cif(4)
    causes = {c["cause"]: c["f"] for c in data["causes"]}
    assert causes["llm"] == pytest.approx(at(llm, 100), abs=1e-9)
    assert causes["tool"] == pytest.approx(at(tool, 100), abs=1e-9)
    assert [r["step"] for r in data["curve"]] == [2, 4, 7, 9, 11]
    for row in data["curve"]:
        assert row["survival"] == pytest.approx(1 - at(llm, row["step"]) - at(tool, row["step"]), abs=1e-9), row
    assert data["median_step"] == 7
    timed_rows = [line for line in section(where(root, run, ["fail"]).out, "Where they die, by kind of step")
                  if line.startswith("| timed out |")]
    assert len(timed_rows) == 1 and f"{at(timed, 100):.3f}" in timed_rows[0], timed_rows


def test_tf15_s30_the_tr36_store_with_a_time_out_and_a_capped_try(synth) -> None:  # type: ignore[no-untyped-def]
    """Four placed: a failure at 2, a finish at 3, a time-out at 2, a capped try at 6. With the
    time-out an end of its own, a quarter failed and a quarter timed out; the curve's one row is
    0.75; the median failed step is 2; no Greenwood variance is printed for this curve."""
    root, run = synth
    data = _json(where(root, run, SYNTH_EVENTS, "--json"))
    assert [(c["step"], c["at_risk"], c["died"]) for c in data["curve"]] == [(2, 4, 1)]
    assert data["curve"][0]["survival"] == pytest.approx(0.75, abs=1e-12)
    assert data["curve"][0]["var"] is None
    assert data["median_step"] == 2
    assert [(c["cause"], c["deaths"]) for c in data["causes"]] == [("llm", 1)]
    assert data["causes"][0]["f"] == pytest.approx(0.25, abs=1e-12)
    timed = [line for line in section(where(root, run, SYNTH_EVENTS).out, "Where they die, by kind of step")
             if line.startswith("| timed out |")]
    assert len(timed) == 1 and "0.250" in timed[0], timed


def test_tf15_s31_the_band_resamples_inputs(make_store) -> None:  # type: ignore[no-untyped-def]
    """Ten inputs of ten tries: five fail every try at step 5, five finish every try at step 7.
    Resampling inputs, the share failed is a binomial(10, 1/2) over 10, whose 2.5th and 97.5th
    percentiles are 0.2 and 0.8; resampling tries it would be a binomial(100, 1/2) over 100,
    0.40 and 0.60."""
    rows = []
    for k in range(10):
        cell = {"input": f"i{k}"}
        for r in range(10):
            fails = k < 5
            rows.append(Row(cell, "fail" if fails else "ok", roots(["llm"] * (5 if fails else 7)), replicate_index=r))
    root, run = make_store(rows)
    data = _json(where(root, run, ["fail"], "--json"))
    cause = data["causes"][0]
    assert cause["f"] == pytest.approx(0.5, abs=1e-12)
    assert 0.1 <= cause["lo"] <= 0.3 and 0.7 <= cause["hi"] <= 0.9, cause
    row = data["curve"][0]
    assert row["step"] == 5 and row["survival"] == pytest.approx(0.5, abs=1e-12)
    assert 0.1 <= row["lo"] <= 0.3 and 0.7 <= row["hi"] <= 0.9, row


def test_tf15_s32_where_names_its_estimator_and_not_the_old_ones() -> None:
    text = norm(where(TAU2, TAU2_A, TAU2_EVENTS).out)
    assert "Aalen-Johansen" in text
    assert "Kaplan" not in text and "Greenwood" not in text
    assert re.search(r"resampl\w* inputs", text), text


# ---------- ST8: compare's --at rows ----------


def test_tf15_s33_compare_at_rows_are_the_share_not_yet_failed() -> None:
    c = _json(compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.5, "--at", "10", "--at", "20", "--at", "30", "--json"))
    rows = {r["step"]: r for r in c["at"]}
    for step in (10, 20, 30):
        a, b = WHERE[TAU2_A]["at"][step], WHERE[TAU2_B]["at"][step]
        row = rows[step]
        assert row["survival_a"] == pytest.approx(a, abs=1e-12)
        assert row["survival_b"] == pytest.approx(b, abs=1e-12)
        assert row["diff"] == pytest.approx(b - a, abs=1e-12)
        assert row["lo"] <= row["diff"] <= row["hi"]


def test_tf15_s34_compare_says_its_test_and_its_curves_answer_different_questions() -> None:
    """One sentence under the test: the test compares the failure rate among tries still going,
    the curves the share failed by a step, and a version that finishes sooner can differ in one
    and not the other."""
    body = norm(" ".join(section(compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.5).out, "Comparison")))
    assert "still going" in body and "share" in body and "finish" in body, body
