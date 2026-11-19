"""Choices the continuous measures make where the other tests of TF23 are silent. Each test pins
one choice, so that a later change to it is a change to a test.

- a ceiling is refused for ``total_tokens`` (shown, not tested), for a name that is not a
  measure and for a share that is not above zero; two versions must have different labels
- above 1,000 cases the typical case's range uses the large-sample formula and agrees with the
  exact table to within a few order statistics
- a try that ended early and recorded no time still takes its case out of the time comparison
- when every case is left out, the measure reads *too small to tell* with no paired cases
- a call that rests on a minority of cases says "n of K cases", never "most cases"
- a signal given as one bare string is one signal, not a run of letters
- ``technical`` adds the range and the p to the table, before the verdict
"""

from __future__ import annotations

import numpy as np
import pytest

from tf23_support import cm, from_differences, one_measure, run, version, words


def test_tf23_b_a_ceiling_is_refused_where_it_means_nothing() -> None:
    a, b = from_differences([float(i) for i in range(12)])
    for bad in ({"total_tokens": 0.1}, {"speed": 0.1}, {"wall_time_s": 0.0}, {"wall_time_s": -0.1}):
        with pytest.raises(ValueError):
            run(a, b, ceilings=bad)
    with pytest.raises(ValueError, match="total_tokens"):
        cm().parse_max_change("total_tokens=10%")


def test_tf23_b_the_labels_must_differ() -> None:
    T = cm().Try
    cases = {f"c{i}": [T(values={"wall_time_s": 1.0 + i}, repeat=0)] for i in range(12)}
    with pytest.raises(ValueError, match="labels"):
        cm().compare(version("x", "old", cases), version("y", "old", cases))


def test_tf23_b_the_range_above_a_thousand_cases_follows_the_exact_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = cm()
    d = np.random.default_rng(1001).standard_normal(1001) + 0.05
    approx = c.hl_range(d)
    monkeypatch.setattr(c, "HL_EXACT_MAX", 2000)
    exact = c.hl_range(d)
    width = exact[1] - exact[0]
    assert approx == pytest.approx(exact, abs=0.01 * width)


def test_tf23_b_a_crash_that_recorded_no_time_still_leaves_the_case_out() -> None:
    T = cm().Try
    va = {f"c{i:02d}": [T(values={"wall_time_s": 5.0 + i}, repeat=0)] for i in range(14)}
    vb = {f"c{i:02d}": [T(values={"wall_time_s": 5.5 + i}, repeat=0)] for i in range(14)}
    vb["c03"] = [T(values={"wall_time_s": None}, ending="crash", repeat=0)]
    vb["c05"] = [T(values={"wall_time_s": None}, repeat=0)]  # no ending, no time: no measurement
    m = run(version("x", "old", va), version("y", "new", vb)).measures["wall_time_s"]
    assert m.k_total == 14 and m.k_paired == 12
    assert "c03" not in m.cases and "c05" not in m.cases
    assert dict(m.unfinished["new"]) == {"crash": 1}
    assert "1 of the 14 shared cases had no measurement" in words(m)


def test_tf23_b_every_case_left_out() -> None:
    a, b = one_measure([float(i) for i in range(12)], [float(i) for i in range(12)],
                       ends_b=["crash"] * 12)
    m = run(a, b).measures["wall_time_s"]
    assert m.status == "under_floor" and m.verdict == "too small to tell"
    assert m.k_paired == 0 and m.mean_a is None and m.p_value is None
    assert "on the 0 of 12 cases both versions finished" in words(m)
    assert m.to_dict()["k_paired"] == 0


def test_tf23_b_a_minority_is_not_most_cases() -> None:
    # six cases carry the change (one of them far out), seven barely move the other way: the
    # sign-flip test calls it (p = 2^-5), the mean's range holds 0, and 6 of 13 is not most
    d = [50.0, 1, 1, 1, 1, 1] + [-0.01] * 7
    a, b = from_differences(d)
    m = run(a, b).measures["wall_time_s"]
    assert m.p_value == pytest.approx(0.03125)
    assert m.verdict == "different" and m.lo < 0 < m.hi
    text = words(m)
    assert "different: slower on 6 of 13 cases" in text
    assert "on most cases" not in text and "the mean did not clearly move" in text


def test_tf23_b_a_bare_signal_string_is_one_signal() -> None:
    T = cm().Try
    va = {f"c{i:02d}": [T(values={"wall_time_s": 5.0 + i}, repeat=0)] for i in range(12)}
    vb = {f"c{i:02d}": [T(values={"wall_time_s": 5.5 + i}, repeat=0)] for i in range(12)}
    vb["c02"] = [T(values={"wall_time_s": 1.0}, signals="gave_up_later", repeat=0)]  # type: ignore[arg-type]
    vb["c04"] = [T(values={"wall_time_s": 1.0}, signals="gave_up", repeat=0)]  # type: ignore[arg-type]
    m = run(version("x", "old", va), version("y", "new", vb)).measures["wall_time_s"]
    assert dict(m.unfinished["new"]) == {"gave_up": 1}
    assert "c04" not in m.cases and "c02" in m.cases


def test_tf23_b_technical_adds_the_range_and_the_p() -> None:
    a, b = from_differences([0.2, 0.4, 0.3, 0.7, 0.3, 1.4, 0.3, 0.5, -0.1, 0.1, -0.7, 1.1])
    c = run(a, b)
    plain_header, _ = cm().table(c)
    header, rows = cm().table(c, technical=True)
    assert header == [*plain_header[:-1], "95% range", "p", "verdict"]
    assert all(len(r) == len(header) for r in rows)
    wall = next(r for r in rows if r[0] == "wall_time_s")
    assert wall[header.index("p")] == "0.0391" and " to " in wall[header.index("95% range")]
