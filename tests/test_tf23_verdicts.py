"""TF23-9 to TF23-22: what ``continuous.compare`` decides and says for each measure (spec section
18.6.1 as ruled on 2026-11-03, CS1 to CS6, CS10, CS11 and CS13; vault
log/trace-continuous-statistics-check/rulings.md).

**TF23-9** Pairing (item 1): only cases both versions ran are shared (``k_total``); a case is
paired when both versions recorded the measure on it (``k_paired``); within a case the tries
are averaged and ``d_i`` is new minus old; ``k_nonzero`` counts the cases that changed; the
means, P50s and the change are over the paired cases' per-case means.

**TF23-10** Not recorded (``k_paired`` 0): status ``not_recorded``, no verdict, ``p_value``
null, ``k_paired`` 0 in JSON.

**TF23-11** Fewer than 10 paired cases: status ``under_floor``, *too small to tell*, the
descriptive summary, ``p_value`` null and ``p_floor`` ``2^(1 - k_nonzero)``; the sentence names
both counts, the floor p, and that a call needs 9 changed and 10 paired cases, at 9 every changed
case the same way, at 10 at most one the other way (CS1).

**TF23-12** CS1: a *different* call needs 9 changed cases. With 10 paired cases and 8 changed,
all one way, no test runs (no p) and nothing is called, even with seven measures; with 9, all one
way, every one of seven measures is called (``2^-8 < 0.05/7``).

**TF23-13** CS2: from 10 paired cases, every difference zero reads "identical on all K cases"
with the rule-of-three bound, no verdict and no range; 1 to 8 changed cases read "changed on n
of K cases", each change and their sum, *too small to tell*, never *no significant difference*
however wide the ceiling, and no smallest catchable change.

**TF23-14** CS3: a tested measure's range is the t range of its differences; it is rough when it
and the test read at 0.05 disagree, and a rough range never reads *no significant difference*;
nothing printed or saved names BCa.

**TF23-15** CS4: every *no significant difference* carries "If a few cases took far longer (cost
far more) than the rest, this range can miss a rise.", at 10 cases and at 100.

**TF23-16** CS5: the family is the measures that can be called on this pair (10 paired, 9
changed), ``total_tokens`` never among them, never tested and never called; the smallest
catchable change and ``K_needed`` are at Holm's first threshold ``alpha / m``; Holm steps down
across the family.

**TF23-17** CS6: the *too small to tell* line reads "changes smaller than about ±X (Y%) could
easily go unseen in a run like this", printed from 15 paired cases and not below; with a ceiling,
"about N cases would be needed" from 10, with the caveat that such runs often end up a little
too small; no line anywhere says "4 times in 5".

**TF23-18** CS10: the ceiling is a percentage of the old version's mean over the paired cases;
*no significant difference* exactly when the test is quiet, the range is not rough and lies
inside plus or minus that much; without a ceiling a quiet result is *too small to tell*, gives
the range in words ("these results fit anything from X faster to Y slower") and names the
setting.

**TF23-19** CS11: the Hodges-Lehmann line speaks of "the typical case", never of a median shift;
the tail-spike label needs a *different* call and the typical case's 95% range inside plus or
minus 5% of the old P50; P50 and P90 are over per-case means, P90 and P95 only from 20 paired
cases.

**TF23-20** CS13: a direction word stands alone only when the t range for the mean excludes 0 on
its side; otherwise the call reads "different: {word} on most cases (n of K); the mean did not
clearly move".

**TF23-21** Each measure's direction words: faster/slower, shorter/longer, fewer/more tokens,
cheaper/costlier.

**TF23-22** The same input gives the same result, and the result's JSON has no NaN or infinity.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from tf23_support import (
    MEASURES, WORDS, cm, from_differences, norm, one_measure, run, several, tries, version, words,
)

# hand-found differences (exact sign-flip p beside each, from the module's own enumeration,
# which TF23-1 holds to scipy and brute force)
MOST = [3.63, 0.51, 5.54, 0.41, -0.17, 1.19, 0.33, -0.36, -0.24, 7.75, 0.95]  # p 0.0205, t range -0.03 to 3.58
ROUGH_QUIET = [2.77, -0.37, 1.83, 0.42, 2.59, 0.28, 0.27, -0.49, 0.19, -0.34, 1.77]  # p 0.0654, t range 0.002 to 1.62
HOLM_SECOND = [0.2, 0.4, 0.3, 0.7, 0.3, 1.4, 0.3, 0.5, -0.1, 0.1, -0.7, 1.1]  # p 0.0391, t range 0.03 to 0.72
SEVEN = ("wall_time_s", "working_time_s", "input_chars", "output_chars", "input_tokens", "output_tokens", "cost_usd")


def quiet(k: int, seed: int = 0, scale: float = 1.0) -> list[float]:
    """``k`` symmetric differences, nothing moved: a quiet test."""
    x = np.random.default_rng(seed).standard_normal(k) * scale
    return list(x - x.mean() + 0.01 * scale)


# ---------- TF23-9 ----------


def test_tf23_9_pairing_and_per_case_means() -> None:
    T = cm().Try
    a = version("ra", "old", {
        "c1": [T(values={"wall_time_s": 1.0}, repeat=0), T(values={"wall_time_s": 3.0}, repeat=1)],
        "c2": [T(values={"wall_time_s": 4.0}, repeat=0), T(values={"wall_time_s": 6.0}, repeat=1)],
        "c3": [T(values={"wall_time_s": None}, repeat=0)],  # measure not recorded on c3 in old
        "only_old": [T(values={"wall_time_s": 9.0}, repeat=0)],
    })
    b = version("rb", "new", {
        "c1": [T(values={"wall_time_s": 2.0}, repeat=0), T(values={"wall_time_s": 4.0}, repeat=1)],
        "c2": [T(values={"wall_time_s": 5.0}, repeat=0), T(values={"wall_time_s": 5.0}, repeat=1)],
        "c3": [T(values={"wall_time_s": 1.0}, repeat=0)],
        "only_new": [T(values={"wall_time_s": 9.0}, repeat=0)],
    })
    m = run(a, b).measures["wall_time_s"]
    assert m.k_total == 3
    assert m.k_paired == 2
    assert m.k_nonzero == 1
    assert list(m.cases) == ["c1", "c2"]
    assert list(m.d) == pytest.approx([1.0, 0.0])
    assert m.mean_a == pytest.approx(3.5) and m.mean_b == pytest.approx(4.0)
    assert m.change == pytest.approx(0.5)
    assert m.relative == pytest.approx(0.5 / 3.5)
    assert m.p50_a == pytest.approx(3.5) and m.p50_b == pytest.approx(4.0)


def test_tf23_9_every_measure_is_reported_in_order() -> None:
    a, b = from_differences(quiet(12))
    c = run(a, b)
    assert tuple(c.measures) == MEASURES
    assert tuple(cm().MEASURES) == MEASURES


# ---------- TF23-10 ----------


def test_tf23_10_not_recorded() -> None:
    a, b = from_differences(quiet(12))
    m = run(a, b).measures["cost_usd"]
    assert m.status == "not_recorded"
    assert m.verdict is None
    assert m.k_paired == 0
    j = m.to_dict()
    assert j["status"] == "not_recorded" and j["k_paired"] == 0 and j["p_value"] is None


# ---------- TF23-11 ----------


@pytest.mark.parametrize("k,nz", [(5, 5), (9, 9), (9, 3), (1, 1)])
def test_tf23_11_under_ten_paired_cases(k: int, nz: int) -> None:
    d = [1.0 + i for i in range(nz)] + [0.0] * (k - nz)
    a, b = from_differences(d)
    m = run(a, b).measures["wall_time_s"]
    assert m.status == "under_floor"
    assert m.verdict == "too small to tell"
    assert m.k_paired == k and m.k_nonzero == nz
    for key in ("mean_a", "mean_b", "p50_a", "p50_b"):
        assert getattr(m, key) is not None, key
    assert m.p_value is None
    assert m.p_floor == pytest.approx(2.0 ** (1 - nz))
    j = m.to_dict()
    assert j["status"] == "under_floor" and j["p_value"] is None
    assert j["p_floor"] == pytest.approx(2.0 ** (1 - nz))
    for key in ("mean_a", "mean_b", "p50_a", "p50_b", "k_paired", "k_nonzero"):
        assert key in j
    text = words(m)
    assert "too small to tell" in text
    assert f"K_paired = {k}" in text and f"K_nonzero = {nz}" in text
    assert "9 changed cases" in text and "10 paired cases" in text
    assert "every changed case must move the same way" in text
    assert "at most one may go the other way" in text


# ---------- TF23-12 ----------


def test_tf23_12_eight_changed_cases_are_never_called() -> None:
    d = [1.0, 2.0, 1.5, 3.0, 2.5, 1.2, 0.8, 2.2, 0.0, 0.0]
    cols = {m: ([100.0] * 10, [100.0 + x for x in d]) for m in SEVEN}
    c = run(*several(cols))
    assert c.family == ()
    for m in SEVEN:
        got = c.measures[m]
        assert got.k_paired == 10 and got.k_nonzero == 8
        assert got.p_value is None, m
        assert got.verdict == "too small to tell", m


def test_tf23_12_nine_changed_cases_are_called_under_seven_measures() -> None:
    d = [1.0, 2.0, 1.5, 3.0, 2.5, 1.2, 0.8, 2.2, 0.4, 0.0]
    cols = {m: ([100.0] * 10, [100.0 + x for x in d]) for m in SEVEN}
    c = run(*several(cols))
    assert c.family == SEVEN
    for m in SEVEN:
        got = c.measures[m]
        assert got.p_value == pytest.approx(2.0**-8)
        assert got.verdict == "different", m
        assert got.direction == WORDS[m][1], m


def test_tf23_12_the_floor_constants() -> None:
    assert cm().FLOOR_CHANGED == 9
    assert cm().FLOOR_PAIRED == 10


# ---------- TF23-13 ----------


@pytest.mark.parametrize("k", [10, 100])
def test_tf23_13_identical_on_every_case(k: int) -> None:
    a, b = one_measure([float(500 + i) for i in range(k)], [float(500 + i) for i in range(k)], "input_chars")
    m = run(a, b, ceilings={"input_chars": 0.1}).measures["input_chars"]
    assert m.status == "identical"
    assert m.verdict is None
    assert m.lo is None and m.hi is None and m.p_value is None
    text = words(m)
    assert f"identical on all {k} cases" in text
    assert f"a change touching more than about 3 in {k} cases like these would usually have shown up" in text
    assert "too small to tell" not in text


@pytest.mark.parametrize("n", [1, 4, 8])
def test_tf23_13_few_changed_cases_are_listed(n: int) -> None:
    k = 40
    d = [0.0] * k
    for i in range(n):
        d[3 * i] = 0.5 + i
    a, b = from_differences(d, "output_tokens", base=400.0)
    m = run(a, b, ceilings={"output_tokens": 50.0}).measures["output_tokens"]  # a ceiling of 5000%
    assert m.status == "few_changed"
    assert m.verdict == "too small to tell"
    assert m.mde is None and m.p_value is None
    text = words(m)
    assert f"changed on {n} of {k} cases" in text
    assert "no significant difference" not in text
    changed = {f"c{3 * i:02d}" for i in range(n)}
    assert {c for c, _ in m.changes} == changed
    assert [v for _, v in m.changes] == pytest.approx([0.5 + i for i in range(n)])
    for c in changed:
        assert c in text, f"{c}'s change is not shown"
    total = sum(0.5 + i for i in range(n))
    assert f"{total:g}" in text, "the sum of the changes is not shown"


# ---------- TF23-14 ----------


def test_tf23_14_the_range_is_the_t_range_of_the_differences() -> None:
    a, b = from_differences(HOLM_SECOND)
    m = run(a, b).measures["wall_time_s"]
    assert m.status == "tested"
    assert (m.lo, m.hi) == pytest.approx(cm().t_range(HOLM_SECOND))


def test_tf23_14_a_range_that_disagrees_with_the_test_is_rough_and_reads_no_ceiling() -> None:
    a, b = from_differences(ROUGH_QUIET)
    m = run(a, b, ceilings={"wall_time_s": 10.0}).measures["wall_time_s"]  # the range is well inside
    assert m.p_value == pytest.approx(0.0654296875)
    assert m.lo > 0
    assert m.rough is True
    assert m.verdict == "too small to tell"
    assert "rough" in words(m)


def test_tf23_14_a_range_that_agrees_is_not_rough() -> None:
    a, b = from_differences(HOLM_SECOND)
    assert run(a, b).measures["wall_time_s"].rough is False


def test_tf23_14_nothing_names_bca() -> None:
    a, b = from_differences(quiet(30))
    c = run(a, b, ceilings={"wall_time_s": 0.5})
    assert "bca" not in json.dumps(c.to_dict()).lower()
    assert "bca" not in " ".join(words(m) for m in c.measures.values()).lower()


# ---------- TF23-15 ----------

CAVEAT = {
    "wall_time_s": "If a few cases took far longer than the rest, this range can miss a rise.",
    "cost_usd": "If a few cases cost far more than the rest, this range can miss a rise.",
}


@pytest.mark.parametrize("measure", [m for m in MEASURES if m != "total_tokens"])  # shown, not tested
@pytest.mark.parametrize("k", [10, 100])
def test_tf23_15_every_quiet_reading_warns_of_a_missed_rise(measure: str, k: int) -> None:
    a, b = from_differences(quiet(k, seed=k, scale=0.2), measure, base=100.0)
    m = run(a, b, ceilings={measure: 0.5}).measures[measure]
    assert m.verdict == "no significant difference", words(m)
    text = words(m)
    assert "If a few cases" in text and "this range can miss a rise." in text
    if measure in CAVEAT:
        assert CAVEAT[measure] in text


# ---------- TF23-16 ----------


def test_tf23_16_the_family_and_the_level() -> None:
    k = 20
    rng = np.random.default_rng(16)
    it, ot = rng.integers(300, 900, k).astype(float), rng.integers(50, 400, k).astype(float)
    it2, ot2 = it + np.round(rng.normal(0, 30, k)), ot + np.round(rng.normal(0, 30, k))
    wall = rng.lognormal(1.5, 0.5, k)
    wall2 = wall * np.exp(rng.normal(0, 0.2, k))
    cols = {
        "wall_time_s": (wall, wall2),
        "input_tokens": (it, it2),
        "output_tokens": (ot, ot2),
        "total_tokens": (it + ot, it2 + ot2),
        "input_chars": (np.full(k, 800.0), np.full(k, 800.0)),  # identical: never in the family
    }
    c = run(*several(cols), ceilings={"wall_time_s": 0.05, "input_tokens": 0.01, "output_tokens": 0.01})
    assert c.family == ("wall_time_s", "input_tokens", "output_tokens")
    tt = c.measures["total_tokens"]
    assert tt.status == "not_tested"
    assert tt.p_value is None and tt.verdict is None
    quiet_ones = [m for m in c.family if c.measures[m].verdict == "too small to tell"]
    assert quiet_ones, "no measure read too small to tell: the level is not exercised"
    for m in quiet_ones:
        got = c.measures[m]
        assert got.mde == pytest.approx(cm().mde(np.array(got.d), 0.05 / 3), rel=1e-9), m
        delta = {"wall_time_s": 0.05, "input_tokens": 0.01, "output_tokens": 0.01}[m] * got.mean_a
        assert got.k_needed == cm().k_needed(k, got.mde, delta), m


def test_tf23_16_holm_steps_down_across_the_family() -> None:
    """wall time's p is 2^-9, cost's 0.039: Holm calls both (0.0020 < 0.025, then 0.039 < 0.05);
    holding each to 0.05/2 would call only wall time."""
    k = 12
    wall = [1.0 + 0.1 * i for i in range(10)] + [0.0, 0.0]
    cols = {
        "wall_time_s": ([10.0] * k, [10.0 + x for x in wall]),
        "cost_usd": ([5.0] * k, [5.0 + x for x in HOLM_SECOND]),
    }
    c = run(*several(cols))
    assert c.family == ("wall_time_s", "cost_usd")
    assert c.measures["wall_time_s"].p_value == pytest.approx(2.0**-9)
    assert c.measures["cost_usd"].p_value == pytest.approx(0.0390625)
    assert c.measures["wall_time_s"].verdict == "different"
    assert c.measures["cost_usd"].verdict == "different"
    assert c.measures["wall_time_s"].threshold == pytest.approx(0.025)
    assert c.measures["cost_usd"].threshold == pytest.approx(0.05)


# ---------- TF23-17 ----------


@pytest.mark.parametrize("k", [15, 30])
def test_tf23_17_the_smallest_catchable_change_line(k: int) -> None:
    a, b = from_differences(quiet(k, seed=k, scale=3.0))
    m = run(a, b).measures["wall_time_s"]
    assert m.verdict == "too small to tell"
    text = words(m)
    assert "changes smaller than about ±" in text
    assert "could easily go unseen in a run like this" in text
    assert "4 times in 5" not in text


def test_tf23_17_not_printed_below_fifteen() -> None:
    a, b = from_differences(quiet(14, seed=3, scale=3.0))
    m = run(a, b, ceilings={"wall_time_s": 0.01}).measures["wall_time_s"]
    assert m.verdict == "too small to tell"
    assert "could easily go unseen" not in words(m)
    assert "about " in words(m) and " cases would be needed" in words(m)  # the planning count is kept from 10


def test_tf23_17_the_planning_count_and_its_caveat() -> None:
    a, b = from_differences(quiet(10, seed=5, scale=3.0))
    m = run(a, b, ceilings={"wall_time_s": 0.01}).measures["wall_time_s"]
    text = words(m)
    assert m.k_needed is not None
    assert f"about {m.k_needed} cases would be needed" in text
    assert "end up a little too small" in text


def test_tf23_17_no_line_says_four_times_in_five() -> None:
    for k in (10, 15, 20, 50):
        a, b = from_differences(quiet(k, seed=k, scale=3.0))
        c = run(a, b, ceilings={"wall_time_s": 0.02})
        assert "4 times in 5" not in json.dumps(c.to_dict())


# ---------- TF23-18 ----------


def test_tf23_18_the_ceiling_is_a_share_of_the_old_mean() -> None:
    d = quiet(30, seed=8, scale=0.5)
    a, b = from_differences(d, base=50.0)
    lo, hi = cm().t_range(d)
    edge = max(abs(lo), abs(hi)) / 50.0  # the smallest share of the old mean the range lies inside
    inside = run(a, b, ceilings={"wall_time_s": edge * 1.01}).measures["wall_time_s"]
    outside = run(a, b, ceilings={"wall_time_s": edge * 0.99}).measures["wall_time_s"]
    assert inside.verdict == "no significant difference"
    assert outside.verdict == "too small to tell"


def test_tf23_18_without_a_ceiling_the_range_in_words() -> None:
    a, b = from_differences(quiet(20, seed=9, scale=0.5))
    m = run(a, b).measures["wall_time_s"]
    assert m.verdict == "too small to tell"
    text = words(m)
    assert "these results fit anything from" in text
    assert "faster to" in text and "slower" in text
    assert "--max-change wall_time_s=" in text


# ---------- TF23-19 ----------


def test_tf23_19_the_typical_case() -> None:
    a, b = from_differences(HOLM_SECOND)
    m = run(a, b).measures["wall_time_s"]
    assert m.hl == pytest.approx(cm().hodges_lehmann(HOLM_SECOND))
    assert (m.hl_lo, m.hl_hi) == pytest.approx(cm().hl_range(HOLM_SECOND))
    text = words(m)
    assert "the typical case" in text
    assert "median shift" not in text


def _spike(tail: float) -> list[float]:
    return [0.1 + 0.01 * i for i in range(18)] + [tail, tail * 1.1]


def test_tf23_19_a_tail_spike_needs_the_typical_range_inside_five_percent() -> None:
    a, b = from_differences(_spike(200.0), base=100.0)  # P50 old 100: 5% is 5
    m = run(a, b).measures["wall_time_s"]
    assert m.verdict == "different"
    assert -5.0 <= m.hl_lo and m.hl_hi <= 5.0
    assert m.tail_spike is True
    assert "tail spike (mean shifted, median flat)" in words(m)


def test_tf23_19_no_tail_spike_when_the_typical_case_may_have_moved() -> None:
    d = [1.0 + 0.8 * i for i in range(18)] + [200.0, 220.0]  # the typical range runs past +5
    a, b = from_differences(d, base=100.0)
    m = run(a, b).measures["wall_time_s"]
    assert m.verdict == "different"
    assert m.hl_hi > 5.0
    assert m.tail_spike is False
    assert "tail spike" not in words(m)


@pytest.mark.parametrize("k", [19, 20, 40])
def test_tf23_19_quantiles_are_over_per_case_means(k: int) -> None:
    T = cm().Try
    rng = np.random.default_rng(k)
    tr_a = {f"c{i:02d}": [T(values={"wall_time_s": float(v)}, repeat=j) for j, v in enumerate(rng.lognormal(1, 1, 3))] for i in range(k)}
    tr_b = {f"c{i:02d}": [T(values={"wall_time_s": float(v)}, repeat=j) for j, v in enumerate(rng.lognormal(1, 1, 3))] for i in range(k)}
    m = run(version("x", "old", tr_a), version("y", "new", tr_b)).measures["wall_time_s"]
    ya = np.array([np.mean([t.values["wall_time_s"] for t in tr_a[c]]) for c in sorted(tr_a)])
    yb = np.array([np.mean([t.values["wall_time_s"] for t in tr_b[c]]) for c in sorted(tr_b)])
    assert m.p50_a == pytest.approx(np.median(ya)) and m.p50_b == pytest.approx(np.median(yb))
    if k < 20:
        assert m.p90_a is None and m.p90_b is None and m.p95_a is None and m.p95_b is None
    else:
        assert m.p90_a == pytest.approx(np.quantile(ya, 0.9)) and m.p90_b == pytest.approx(np.quantile(yb, 0.9))
        assert m.p95_a == pytest.approx(np.quantile(ya, 0.95)) and m.p95_b == pytest.approx(np.quantile(yb, 0.95))


# ---------- TF23-20 ----------


def test_tf23_20_the_typical_case_moved_the_mean_did_not_clearly() -> None:
    a, b = from_differences(MOST)
    m = run(a, b).measures["wall_time_s"]
    assert m.p_value == pytest.approx(0.0205078125)
    assert m.lo < 0 < m.hi
    assert m.verdict == "different"
    text = words(m)
    assert "different: slower on most cases (8 of 11)" in text
    assert "the mean did not clearly move" in text


def test_tf23_20_the_bare_word_when_the_mean_agrees() -> None:
    a, b = from_differences(HOLM_SECOND)
    m = run(a, b).measures["wall_time_s"]
    assert m.verdict == "different" and m.lo > 0
    text = words(m)
    assert "different: slower" in text
    assert "on most cases" not in text and "did not clearly move" not in text


# ---------- TF23-21 ----------


@pytest.mark.parametrize("measure", [m for m in MEASURES if m != "total_tokens"])
@pytest.mark.parametrize("sign", [1, -1])
def test_tf23_21_direction_words(measure: str, sign: int) -> None:
    a, b = from_differences([sign * x for x in HOLM_SECOND], measure, base=100.0)
    m = run(a, b).measures[measure]
    assert m.verdict == "different"
    want = WORDS[measure][1 if sign > 0 else 0]
    assert m.direction == want
    assert f"different: {want}" in words(m)


# ---------- TF23-22 ----------


def test_tf23_22_the_same_input_the_same_result_and_clean_json() -> None:
    k = 40
    rng = np.random.default_rng(22)
    cols = {m: (rng.lognormal(3, 1, k), rng.lognormal(3, 1, k)) for m in MEASURES}
    a, b = several(cols)
    first = run(a, b, ceilings={"wall_time_s": 0.1}).to_dict()
    again = run(a, b, ceilings={"wall_time_s": 0.1}).to_dict()
    assert first == again
    text = json.dumps(first, allow_nan=False)
    assert "NaN" not in text and "Infinity" not in text
    assert [m["measure"] for m in first["measures"]] == list(MEASURES)


def test_tf23_22_tries_with_no_order_are_drawn_by_the_seed_rule() -> None:
    T = cm().Try
    a = version("ra", "old", {f"c{i:02d}": [T(values={"wall_time_s": float(10 * i + j)}, repeat=None) for j in range(5)] for i in range(12)})
    b = version("rb", "new", {f"c{i:02d}": [T(values={"wall_time_s": float(10 * i + 2.5)}, repeat=None)] for i in range(12)})
    m1 = run(a, b).measures["wall_time_s"]
    m2 = run(a, b).measures["wall_time_s"]
    assert list(m1.d) == list(m2.d)
    for i, x in enumerate(m1.d):
        assert (10 * i + 2.5 - x) - 10 * i in {0.0, 1.0, 2.0, 3.0, 4.0}
    assert math.isfinite(m1.change)


def test_tf23_22_norm_helper_is_plain() -> None:
    assert norm("a  –  b") == "a - b"
    assert tries([1.0, 2.0])[1].repeat == 1
