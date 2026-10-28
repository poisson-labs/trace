"""TR66 to TR69: the goldens on the committed fixtures. Every figure was recomputed from the
stored runs by the spec's definitions (sections 2 and 3) before it was pinned; the recomputation
and its comparison with the spec's section 6 are in the Session A log. Counts are exact; other
figures are to 1e-4 unless the invariant says otherwise. By-input p-values from seeded draws are
not pinned to a number (spec section 10)."""

from __future__ import annotations

import pytest

from conftest import TAU2, TAU2_A, TAU2_B, compare, norm
from fixcheck_support import (
    HE_A, HE_B, HE_EVENTS, HUMANEVAL, PILOT, TAU2_EVENTS, changes, counts_of, fix_check, ok,
    one_sentence,
)

ALL = ("--inputs", "all")


def _json(result, code):  # type: ignore[no-untyped-def]
    assert result.code == code, result.text
    return result.json()


# ---------- TR66 ----------


def test_tr66_tau2_pair_all_inputs() -> None:
    d = _json(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.10", "--json"), 0)  # R17
    assert (d["inputs"]["compared"], d["inputs"]["informative"], d["inputs"]["selected"]) == (50, 29, 50)
    assert sum(d["inputs"]["left_out"].values()) == 0
    assert (d["rows"]["old"]["failed"], d["rows"]["old"]["runs"]) == (110, 200)
    assert (d["rows"]["new"]["failed"], d["rows"]["new"]["runs"]) == (112, 200)
    assert (d["rows"]["old"]["mixed"], d["rows"]["new"]["mixed"]) == (21, 23)
    t = d["test"]
    assert t["observed_new"] == 112
    assert t["expected_new"] == pytest.approx(111.0, abs=1e-4)
    assert t["variance"] == pytest.approx(11.571429, abs=1e-4)
    assert t["weight"] == pytest.approx(100.0, abs=1e-4)
    assert t["p"] == pytest.approx(0.883073, abs=1e-4)
    diff = d["difference"]
    assert diff["points"] == pytest.approx(0.0100, abs=1e-4)
    # ST3 (ruled 2026-10-20): the stratified Miettinen-Nurminen interval (the statistics check's
    # simlib.mn_stratified on its dump F1-tau2-fixcheck-all)
    assert diff["lo"] == pytest.approx(-0.060441, abs=1e-4)
    assert diff["hi"] == pytest.approx(0.081196, abs=1e-4)
    c = d["consistency"]
    assert c["failure_share"] == pytest.approx(0.555, abs=1e-4)
    assert c["fails_again"] == pytest.approx(0.7915, abs=1e-4)
    assert c["kappa"] == pytest.approx(0.5315, abs=1e-4)
    assert c["within"] == pytest.approx(0.1157, abs=1e-4)
    assert c["pooled"] == pytest.approx(0.2470, abs=1e-4)
    assert d["limits"]["drop"] == pytest.approx(0.110854, abs=1e-4)
    assert d["limits"]["rise"] == pytest.approx(0.108253, abs=1e-4)
    # ST2 (ruled 2026-10-20): -6.0 to +8.1 lies inside plus or minus 10, so no significant
    # difference, though the drop limit is above 10; the guidance is for too small to tell only
    assert d["verdict"] == "no significant difference"
    assert d["guidance"] is None
    assert d["by_input"]["moved"] == 20 and d["by_input"]["method"] == "monte carlo"
    assert "no significant difference" in norm(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.10").out)
    tight = _json(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.075", "--json"), 0)
    assert tight["verdict"] == "too small to tell"
    assert tight["guidance"]["accepts_at"] == pytest.approx(0.0812, abs=1e-12)
    loose = fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.12")
    assert loose.code == 0 and "no significant difference" in norm(loose.out)
    assert _json(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.12", "--json"), 0)["guidance"] is None


# ---------- TR67 ----------


def test_tr67_tau2_pair_compare_guidance() -> None:
    tight = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.3, "--json")
    g = _json(tight, 0)["comparison"]["guidance"]  # R17
    # ST5 (ruled 2026-10-20): the tries per input whose expected log-rank information reaches the
    # asked ratio's (the statistics check's sim_compare.py search; 11, settled in the Session A log)
    assert g["repeats"] == 11
    assert g["accepts_at"] == pytest.approx(1.604, abs=1e-12)
    assert _json(compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.604, "--json"), 0)["comparison"]["guidance"] is None
    assert compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.604).code == 0


# ---------- TR68 ----------


def _pilot(*extra: str):  # type: ignore[no-untyped-def]
    return fix_check(TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.20", *extra)


def test_tr68_the_real_before_and_after() -> None:
    d = _json(_pilot("--json"), 0)  # R17
    assert (d["inputs"]["selected"], d["inputs"]["compared"]) == (37, 6)
    assert d["inputs"]["left_out"]["not re-run on the new version"] == 31
    assert sum(d["inputs"]["left_out"].values()) == 31
    assert (d["runs"]["old"]["declared_repeats"], d["runs"]["new"]["declared_repeats"]) == (4, 1)
    assert (d["rows"]["old"]["failed"], d["rows"]["old"]["runs"]) == (18, 24)
    assert (d["rows"]["new"]["failed"], d["rows"]["new"]["runs"]) == (3, 6)
    assert d["control"]["old_did_not_fail_share"] == pytest.approx(0.25, abs=1e-12)
    t = d["test"]
    assert t["observed_new"] == 3
    assert t["expected_new"] == pytest.approx(4.2, abs=1e-4)
    assert t["variance"] == pytest.approx(0.8, abs=1e-4)
    assert t["weight"] == pytest.approx(4.8, abs=1e-4)
    assert t["p"] == pytest.approx(0.2688, abs=1e-4)
    diff = d["difference"]
    assert diff["points"] == pytest.approx(-0.25, abs=1e-4)
    # ST3: simlib.mn_stratified on the dump tau2-fixcheck-failing-from
    assert diff["lo"] == pytest.approx(-0.615002, abs=1e-4)
    assert diff["hi"] == pytest.approx(0.113135, abs=1e-4)
    assert d["by_input"] == {"moved": 4, "p": 0.375, "method": "exact", "draws": None, "seed": None}
    assert d["limits"]["drop"] == pytest.approx(0.642939, abs=1e-4)
    assert d["limits"]["rise"] is None
    assert d["verdict"] == "too small to tell"
    assert d["guidance"] == {"repeats": 16, "inputs": 55, "accepts_at": pytest.approx(0.6430, abs=1e-12)}
    ch = d["changes"]
    assert (ch["tested"], ch["flagged"], ch["together"]) == (6, 0, None)
    tasks = sorted(r["config"]["task_id"] for r in ch["rows"])
    assert tasks == ["1", "2", "3", "5", "7", "9"]
    text = norm(ok(_pilot()).out)
    assert "too small to tell" in text and "no input can be flagged whatever happens" in text
    one_sentence(fix_check(TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_B, "--max-mde", "0.20"))


@pytest.mark.parametrize("old,failed,points,p,limit", [
    (TAU2_A, 17, -0.125, 0.4864, 0.366678),
    (TAU2_B, 20, -0.200, 0.1600, 0.416831),
])
def test_tr68_the_pilot_against_all_ten_tasks(old: str, failed: int, points: float, p: float, limit: float) -> None:
    d = _json(fix_check(TAU2, old, PILOT, TAU2_EVENTS, *ALL, "--max-mde", "0.20", "--json"), 0)  # R17
    assert d["inputs"]["compared"] == 10
    assert (d["rows"]["old"]["failed"], d["rows"]["old"]["runs"]) == (failed, 40)
    assert (d["rows"]["new"]["failed"], d["rows"]["new"]["runs"]) == (3, 10)
    assert d["difference"]["points"] == pytest.approx(points, abs=1e-4)
    assert d["test"]["p"] == pytest.approx(p, abs=1e-4)
    assert d["limits"]["drop"] == pytest.approx(limit, abs=1e-4)


# ---------- TR69 ----------


def test_tr69_humaneval_129_is_flagged_and_nothing_else() -> None:
    d = _json(changes(HUMANEVAL, HE_A, HE_B, HE_EVENTS, "--json"), 0)
    assert (d["tested"], d["flagged"]) == (328, 2)
    flagged = [r for r in d["rows"] if r["flag"] is not None]
    assert [r["config"] for r in flagged] == [
        {"task_id": "HumanEval/129", "temperature": 0.7},
        {"task_id": "HumanEval/129", "temperature": 0.0},
    ]
    assert all(r["flag"] == "failed more in B" for r in flagged)
    hot, cold = flagged
    assert (hot["failed_a"], hot["runs_a"], hot["failed_b"], hot["runs_b"]) == (12, 32, 32, 32)
    assert (cold["failed_a"], cold["runs_a"], cold["failed_b"], cold["runs_b"]) == (20, 32, 32, 32)
    # the spec's 2.301692e-8, 1.375019e-4, 7.549550e-6, 0.022550, recomputed to ten figures
    assert hot["p"] == pytest.approx(2.301692108e-8, rel=1e-9)
    assert cold["p"] == pytest.approx(1.375018751e-4, rel=1e-9)
    assert hot["q"] == pytest.approx(7.549550115e-6, rel=1e-9)
    assert cold["q"] == pytest.approx(2.255030752e-2, rel=1e-9)
    assert hot["change"] == pytest.approx(0.625, abs=1e-12) and cold["change"] == pytest.approx(0.375, abs=1e-12)


def test_tr69_the_humaneval_pair_reads_different_failed_more() -> None:
    """The numbers the post may quote (ruling 12 of 2026-09-29)."""
    d = _json(fix_check(HUMANEVAL, HE_A, HE_B, HE_EVENTS, *ALL, "--max-mde", "0.05", "--json"), 0)
    assert (d["rows"]["old"]["failed"], d["rows"]["old"]["runs"]) == (1338, 10496)
    assert (d["rows"]["new"]["failed"], d["rows"]["new"]["runs"]) == (1387, 10496)
    t = d["test"]
    assert t["observed_new"] == 1387
    assert t["expected_new"] == pytest.approx(1362.5, abs=1e-4)
    assert t["variance"] == pytest.approx(131.1389, abs=1e-4)
    assert t["p"] == pytest.approx(0.036024, abs=1e-6)
    assert (d["verdict"], d["direction"]) == ("different", "failed more in new")
    assert d["gap_seconds"] == pytest.approx(3361.826296, abs=1e-6)
    diff = d["difference"]
    assert diff["points"] == pytest.approx(0.004668, abs=1e-4)
    # ST3: simlib.mn_stratified on the dump he-fixcheck
    assert diff["lo"] == pytest.approx(0.000378, abs=1e-4)
    assert diff["hi"] == pytest.approx(0.009263, abs=1e-4)
    assert d["limits"]["drop"] == pytest.approx(0.006436, abs=1e-4)
    c = d["consistency"]
    assert (c["failure_share"], c["fails_again"], c["kappa"]) == (
        pytest.approx(0.1298, abs=1e-4), pytest.approx(0.8075, abs=1e-4), pytest.approx(0.7788, abs=1e-4))
    assert d["changes"]["flagged"] == 2
    text = norm(fix_check(HUMANEVAL, HE_A, HE_B, HE_EVENTS, *ALL, "--max-mde", "0.05").out)
    assert "different: the new version failed more on these inputs" in text
    assert "56 min" in text


def test_tr69_without_humaneval_129_the_paired_test_reads_no_difference() -> None:
    from poisson_trace.paired import paired_test

    d = _json(changes(HUMANEVAL, HE_A, HE_B, HE_EVENTS, "--json"), 0)
    rest = [(r["failed_a"], r["runs_a"], r["failed_b"], r["runs_b"]) for r in d["rows"]
            if r["config"]["task_id"] != "HumanEval/129"]
    assert len(rest) == 326
    assert paired_test(counts_of(rest)).p == pytest.approx(0.4745, abs=1e-4)
