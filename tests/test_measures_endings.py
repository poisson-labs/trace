"""TF23-23 to TF23-27: tries that ended early, timeouts, and the number of tries per case. Fast,
hand-built cases; the check's scenarios at its seeds are in test_measures_scenarios.py.

**TF23-23** A case leaves the time (``wall_time_s``, ``working_time_s``) and output-length
comparison when any try of it in either version ended early: ``crash``, ``rate_limit``,
``abstained``, ``guardrail_blocked``, or the ``gave_up`` signal; it is counted unfinished, by
kind, for the version that ended early. A ``timeout`` or a ``wrong_answer`` does not take a case
out. Tokens, input length and cost keep every case with a value.

**TF23-24** When both versions' timeout caps are known and differ, every time in both is cut
at the lower cap, and a try cut there counts as timed out; output length is not cut.

**TF23-25** With cases left out, the line reads "on the K of N cases both versions finished"
and names each version's unfinished cases by kind; a faster (or slower, shorter, longer) call is
*unconfirmed* when the version it favours left more cases unfinished, or timed out on more; the
10th/90th-percentile guard plays no part.

**TF23-26** On tokens and cost a call on every case stands, and when the version it
favours stopped early on more cases it reads "partly because {version} stopped early on {n}
cases (on the {K} cases both finished: {range})".

**TF23-27** Each case is compared on the first ``min(r_old, r_new)`` tries of each version
in the order recorded, and the line says so when the counts differed ("old had 1 try per case,
new had 5; compared on 1 each").
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from measures_support import EARLY_KINDS, FINISHED_ONLY, cm, one_measure, run, version, words

K = 30


def _base(k: int = K, seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    a = rng.lognormal(1.5, 0.6, k)
    return a, a * np.exp(rng.normal(0, 0.3, k))


def _two(measure_values: dict[str, tuple[np.ndarray, np.ndarray]], ends_a=None, ends_b=None,  # type: ignore[no-untyped-def]
         signals_b=None, cap_a=None, cap_b=None):
    T = cm().Try
    k = len(next(iter(measure_values.values()))[0])
    ea = ends_a or {}
    eb = ends_b or {}
    sb = signals_b or {}
    va = {f"c{i:02d}": [T(values={m: float(v[0][i]) for m, v in measure_values.items()}, ending=ea.get(i), repeat=0)] for i in range(k)}
    vb = {f"c{i:02d}": [T(values={m: float(v[1][i]) for m, v in measure_values.items()}, ending=eb.get(i), signals=sb.get(i, ()), repeat=0)] for i in range(k)}
    return version("run-a", "old", va, cap_s=cap_a), version("run-b", "new", vb, cap_s=cap_b)


# ---------- TF23-23 ----------


@pytest.mark.parametrize("kind", [*EARLY_KINDS, "gave_up"])
@pytest.mark.parametrize("side", ["old", "new"])
def test_tf23_23_an_early_ending_takes_the_case_out_of_time_and_output_length(kind: str, side: str) -> None:
    a_vals, b_vals = _base()
    cols = {m: (a_vals * 100, b_vals * 100) for m in (*FINISHED_ONLY, "output_tokens", "cost_usd", "input_chars")}
    early = {3: kind, 7: kind} if kind != "gave_up" else {}
    signals = {3: ("gave_up",), 7: ("gave_up",)} if kind == "gave_up" else {}
    if side == "old":
        a, b = _two(cols, ends_a=early)
        if signals:  # the signal on the old version's tries
            T = cm().Try
            cases = dict(a.cases)
            for i in (3, 7):
                t = cases[f"c{i:02d}"][0]
                cases[f"c{i:02d}"] = [T(values=t.values, signals=("gave_up",), repeat=0)]
            a = version("run-a", "old", cases)
    else:
        a, b = _two(cols, ends_b=early, signals_b=signals)
    c = run(a, b)
    for m in FINISHED_ONLY:
        got = c.measures[m]
        assert got.k_total == K and got.k_paired == K - 2, m
        assert "c03" not in got.cases and "c07" not in got.cases, m
        assert dict(got.unfinished[side]).get(kind) == 2, (m, got.unfinished)
        other = "new" if side == "old" else "old"
        assert sum(dict(got.unfinished[other]).values()) == 0
    for m in ("output_tokens", "cost_usd", "input_chars"):
        assert c.measures[m].k_paired == K, m


@pytest.mark.parametrize("kind", ["timeout", "wrong_answer", "tool_error", "format_error"])
def test_tf23_23_other_endings_stay(kind: str) -> None:
    a_vals, b_vals = _base()
    a, b = _two({"wall_time_s": (a_vals, b_vals)}, ends_b={2: kind, 5: kind})
    assert run(a, b).measures["wall_time_s"].k_paired == K


def test_tf23_23_one_early_try_takes_out_the_whole_case() -> None:
    T = cm().Try
    va = {f"c{i:02d}": [T(values={"wall_time_s": 5.0 + i + j}, repeat=j) for j in range(3)] for i in range(12)}
    vb = {f"c{i:02d}": [T(values={"wall_time_s": 5.5 + i + j}, repeat=j) for j in range(3)] for i in range(12)}
    vb["c04"] = [T(values={"wall_time_s": 9.0}, repeat=0), T(values={"wall_time_s": 0.05}, ending="crash", repeat=1),
                 T(values={"wall_time_s": 9.5}, repeat=2)]
    m = run(version("x", "old", va), version("y", "new", vb)).measures["wall_time_s"]
    assert "c04" not in m.cases and m.k_paired == 11
    assert dict(m.unfinished["new"]) == {"crash": 1}


def test_tf23_23_the_early_kinds() -> None:
    assert set(cm().EARLY) == set(EARLY_KINDS)


# ---------- TF23-24 ----------


def test_tf23_24_times_are_cut_at_the_lower_cap() -> None:
    a_vals = np.array([5.0, 8.0, 12.0, 25.0, 30.0, 3.0, 4.0, 6.0, 7.0, 9.0, 11.0, 14.0])
    b_vals = np.array([5.5, 8.5, 13.0, 30.0, 18.0, 3.5, 4.5, 6.5, 7.5, 9.5, 11.5, 14.5])
    out_a, out_b = a_vals * 40, b_vals * 40
    ends_a = {4: "timeout"}  # old ran with a 30 s cap and hit it on c04
    a, b = _two({"wall_time_s": (a_vals, b_vals), "output_chars": (out_a, out_b)}, ends_a=ends_a, cap_a=30.0, cap_b=20.0)
    c = run(a, b)
    m = c.measures["wall_time_s"]
    assert m.k_paired == 12  # a timeout stays
    cut_a, cut_b = np.minimum(a_vals, 20.0), np.minimum(b_vals, 20.0)
    assert list(m.d) == pytest.approx(list(cut_b - cut_a))
    assert dict(m.timed_out) == {"old": 2, "new": 1}  # old: c03 cut, c04; new: c03 cut
    o = c.measures["output_chars"]
    assert list(o.d) == pytest.approx(list(out_b - out_a))


def test_tf23_24_one_cap_or_equal_caps_cut_nothing() -> None:
    a_vals, b_vals = _base(seed=3)
    for caps in ((20.0, 20.0), (None, 20.0), (None, None)):
        a, b = _two({"wall_time_s": (a_vals * 10, b_vals * 10)}, cap_a=caps[0], cap_b=caps[1])
        m = run(a, b).measures["wall_time_s"]
        assert list(m.d) == pytest.approx(list(b_vals * 10 - a_vals * 10)), caps


# ---------- TF23-25 ----------


def _hidden_slow(k: int = 40, seed: int = 4):  # type: ignore[no-untyped-def]
    """New is 15% faster on the easy cases and crashes after 0.05 s on the hardest fifth, where it
    would have been 60% slower: faster where it finished, slower overall."""
    rng = np.random.default_rng(seed)
    b = np.exp(rng.normal(np.log(5.0), 1.0, k))
    hard = b >= np.quantile(b, 0.8)
    ya = b * np.exp(rng.normal(0, 0.05, k))
    yb = np.where(hard, 0.05, b * 0.85 * np.exp(rng.normal(0, 0.05, k)))
    ends_b = {i: "crash" for i in np.nonzero(hard)[0]}
    return ya, yb, ends_b, int(hard.sum())


def test_tf23_25_a_faster_call_for_a_version_that_finished_fewer_is_unconfirmed() -> None:
    ya, yb, ends_b, n = _hidden_slow()
    a, b = _two({"wall_time_s": (ya, yb)}, ends_b=ends_b)
    m = run(a, b).measures["wall_time_s"]
    assert m.p_value is not None and m.p_value < 0.05  # the test sees "faster" on what both finished
    assert m.verdict == "unconfirmed"
    assert m.direction == "faster"
    text = words(m)
    assert f"on the {40 - n} of 40 cases both versions finished" in text
    assert f"{n} crash" in text


def test_tf23_25_confirmed_when_the_favoured_version_finished_as_many() -> None:
    ya, yb, ends_b, n = _hidden_slow()
    ends_a = {i: "rate_limit" for i in list(ends_b)}  # old also left those cases unfinished
    a, b = _two({"wall_time_s": (ya, np.where(np.isin(np.arange(40), list(ends_b)), ya, yb))}, ends_a=ends_a, ends_b=ends_b)
    m = run(a, b).measures["wall_time_s"]
    assert m.verdict == "different" and m.direction == "faster"


def test_tf23_25_timing_out_more_also_unconfirms() -> None:
    rng = np.random.default_rng(6)
    ya = rng.lognormal(1.5, 0.4, 30)
    yb = ya * 0.8 * np.exp(rng.normal(0, 0.02, 30))
    a, b = _two({"wall_time_s": (ya, yb)}, ends_b={0: "timeout", 1: "timeout"})
    m = run(a, b).measures["wall_time_s"]
    assert m.direction == "faster"
    assert m.verdict == "unconfirmed"


def test_tf23_25_slower_for_the_old_version_mirrors_it() -> None:
    ya, yb, ends_b, n = _hidden_slow(seed=5)
    a, b = _two({"wall_time_s": (yb, ya)}, ends_a=ends_b)  # old is the one crashing: new looks slower
    m = run(a, b).measures["wall_time_s"]
    assert m.direction == "slower"
    assert m.verdict == "unconfirmed"


def test_tf23_25_the_percentile_guard_is_gone() -> None:
    ya, yb, ends_b, n = _hidden_slow()
    a, b = _two({"wall_time_s": (ya, yb)}, ends_b=ends_b)
    text = json.dumps(run(a, b).to_dict()).lower()
    assert "sensitive to" not in text and "percentile" not in text and "p10" not in text


# ---------- TF23-26 ----------


def test_tf23_26_a_spending_call_stands_and_names_the_early_stops() -> None:
    ya, yb, ends_b, n = _hidden_slow()
    tok_a = np.round(80 * ya)
    tok_b = np.where(np.isin(np.arange(40), list(ends_b)), np.round(0.05 * 80 * ya), np.round(80 * yb))
    a, b = _two({"output_tokens": (tok_a, tok_b), "cost_usd": (tok_a * 1e-5, tok_b * 1e-5)}, ends_b=ends_b)
    c = run(a, b)
    for m in ("output_tokens", "cost_usd"):
        got = c.measures[m]
        assert got.k_paired == 40, m
        assert got.verdict == "different", m
        assert got.direction == ("fewer tokens" if m == "output_tokens" else "cheaper")
        text = words(got)
        assert f"partly because new stopped early on {n} cases" in text, text
        assert f"on the {40 - n} cases both finished" in text


def test_tf23_26_no_cause_named_when_the_early_stops_do_not_favour_it() -> None:
    rng = np.random.default_rng(8)
    tok_a = rng.integers(300, 900, 30).astype(float)
    tok_b = np.round(tok_a * 0.8)
    a, b = _two({"output_tokens": (tok_a, tok_b)}, ends_a={0: "crash", 1: "crash"})
    got = run(a, b).measures["output_tokens"]
    assert got.verdict == "different" and got.direction == "fewer tokens"
    assert "stopped early" not in words(got)


# ---------- TF23-27 ----------


def test_tf23_27_compared_on_the_first_tries_of_each() -> None:
    T = cm().Try
    va = {f"c{i:02d}": [T(values={"wall_time_s": 10.0 + i}, repeat=0)] for i in range(12)}
    vb = {f"c{i:02d}": [T(values={"wall_time_s": v}, repeat=j)
                        for j, v in reversed(list(enumerate([11.0 + i, 50.0, 60.0, 70.0, 80.0])))] for i in range(12)}
    m = run(version("x", "old", va), version("y", "new", vb)).measures["wall_time_s"]
    assert list(m.d) == pytest.approx([1.0] * 12)  # repeat 0 of new, whatever order it was given in
    assert "old had 1 try per case, new had 5; compared on 1 each" in words(m)


def test_tf23_27_equal_tries_say_nothing() -> None:
    a, b = one_measure([float(i) for i in range(5, 17)], [float(i) + 0.5 for i in range(5, 17)])
    assert "compared on" not in words(run(a, b).measures["wall_time_s"])


def test_tf23_27_mixed_counts_still_say_so() -> None:
    T = cm().Try
    va = {f"c{i:02d}": [T(values={"wall_time_s": 10.0 + i + j}, repeat=j) for j in range(1 + i % 3)] for i in range(12)}
    vb = {f"c{i:02d}": [T(values={"wall_time_s": 10.5 + i + j}, repeat=j) for j in range(3)] for i in range(12)}
    m = run(version("x", "old", va), version("y", "new", vb)).measures["wall_time_s"]
    assert list(m.d) == pytest.approx([0.5] * 12)  # first n of each, n = 1, 2 or 3 by case
    assert "compared on" in words(m)
