"""TF23-28 to TF23-32: the continuous statistics check's scenarios at its own seeds (vault
log/trace-continuous-statistics-check/, rulings.md "The order and the counts": TF23's tests gain
the steadier version (CS13), the low-noise hidden slowdown (CS8) and unequal tries (CS14); and
the give-up and spending scenarios of findings item 6 for CS7 and CS9).

All of these are in the slow lane; each has a fast twin on hand-built data in
test_tf23_endings.py or test_tf23_verdicts.py, named beside it.

**TF23-28** The data are the check's: rebuilt from its generators and seeds
(tf23_support), the check's own readings of them are the rows it printed, to the repetition
(``review/scripts/r1_shape_null.out``, ``r3_tip_stress.out``).

**TF23-29** CS13, the steadier version (r1 ``steadier_B``, 50 cases): every mean unchanged, new
steadier. Whenever Trace calls *different* on time and the t range for the mean holds 0, the call
reads "on most cases ... the mean did not clearly move", never a bare *slower*; and Trace calls
*different* as often as the check's test does on the same repetitions. Fast twin: TF23-20.

**TF23-30** CS8, the low-noise hidden slowdown (r3 "hidden h1.6 s0.15", 20 cases): new is
faster where it finished and slower overall. The guard CS8 replaced let a wrong *faster* stand
69.7% of the time; Trace lets none stand. Fast twin: TF23-25.

**TF23-31** CS14, unequal tries (r1 ``unequal_1v5``, 50 cases, nothing changed, old run once and
new five times): compared on one try each, Trace calls *different* no more often than its level
allows (the check, on every try, 8.6%); the line says it compared on 1 each. Fast twin: TF23-27.

**TF23-32** CS7 and CS9 on findings item 6's runs (``sim_crash.py``, 50 cases, no real change):
new gives up early on its hardest cases, and Trace never lets *faster* stand (the spec as written
said *faster* 95.3%); new crashes early on its hardest cases, and when Trace says *fewer tokens* it
names the early stops. Fast twins: TF23-23, TF23-26.
"""

from __future__ import annotations

import numpy as np
import pytest

from tf23_support import cm, crash_reps, r1_reps, r3_reps, versions_from_runs, words

pytestmark = pytest.mark.slow


def _wall(c):  # type: ignore[no-untyped-def]
    return c.measures["wall_time_s"]


# ---------- TF23-28 ----------


@pytest.mark.parametrize("scenario,k,want_05,want_t", [
    ("steadier_B", 50, 355, 338),   # r1: 17.8% (of which slower 17.6%), t-test 16.9%
    ("unequal_1v5", 50, 171, None),  # r1: 8.6%
])
def test_tf23_28_r1_rows_are_rebuilt(scenario: str, k: int, want_05: int, want_t: int | None) -> None:
    got = list(r1_reps(scenario, k, 2000))
    assert sum(p < 0.05 for *_, p, _ in got) == want_05
    if want_t is not None:
        assert sum(t for *_, t in got) == want_t


def test_tf23_28_r3_row_is_rebuilt() -> None:
    got = list(r3_reps(1, 20, 2000))
    assert sum(spec == "B lower" for *_, spec, _ in got) == 1394  # r3: spec 69.7%
    assert sum(count == "B lower" for *_, count in got) == 0  # r3: count 0.0%


# ---------- TF23-29 ----------


def test_tf23_29_the_steadier_version_is_not_called_slower_on_the_mean() -> None:
    n = 300
    called = most = bare = check = 0
    for ta, tb, p, _ in r1_reps("steadier_B", 50, n):
        check += p < 0.05
        m = _wall(cm().compare(*versions_from_runs(ta, tb)))
        if m.verdict != "different":
            continue
        called += 1
        text = words(m)
        if m.lo <= 0 <= m.hi:
            most += 1
            assert "on most cases" in text and "the mean did not clearly move" in text, text
        else:
            bare += 1
            assert (m.lo > 0) == (m.direction == "slower")
    assert most >= 1, "no repetition reached the rule"
    assert abs(called - check) <= max(4, 0.02 * n), (called, check)


# ---------- TF23-30 ----------


def test_tf23_30_no_wrong_faster_call_stands_at_low_noise() -> None:
    n = 2000
    stand = unconfirmed = 0
    for ya, yb, ka, kb, _spec, _ in r3_reps(1, 20, n):
        m = _wall(cm().compare(*versions_from_runs(ya, yb, ka, kb)))
        stand += m.verdict == "different" and m.direction == "faster"
        unconfirmed += m.verdict == "unconfirmed"
    assert stand == 0
    assert unconfirmed >= n // 2, unconfirmed


# ---------- TF23-31 ----------


def test_tf23_31_unequal_tries_keep_the_level() -> None:
    n = 500
    called = 0
    for ta, tb, _, _ in r1_reps("unequal_1v5", 50, n):
        m = _wall(cm().compare(*versions_from_runs(ta, tb)))
        assert "old had 1 try per case, new had 5; compared on 1 each" in words(m)
        called += m.verdict in ("different", "unconfirmed")
    assert called <= n * (0.05 + 3 * np.sqrt(0.05 * 0.95 / n)), called


# ---------- TF23-32 ----------


def test_tf23_32_giving_up_early_never_reads_faster() -> None:
    n = 200
    for ya, yb, _ta, _tb, ka, kb in crash_reps("hard_giveup", 1.0, 50, n):
        m = _wall(cm().compare(*versions_from_runs(ya, yb, ka, kb)))
        assert m.k_paired == 41 and dict(m.unfinished["new"]) == {"abstained": 9}
        assert not (m.verdict == "different" and m.direction == "faster")


def test_tf23_32_fewer_tokens_names_the_early_stops() -> None:
    n = 50
    fewer = 0
    for _ya, _yb, ta, tb, ka, kb in crash_reps("hard_crash", 1.0, 50, n):
        c = cm().compare(*versions_from_runs(ta, tb, ka, kb, measure="output_tokens"))
        m = c.measures["output_tokens"]
        assert m.k_paired == 50
        if m.verdict == "different" and m.direction == "fewer tokens":
            fewer += 1
            assert "partly because new stopped early on 9 cases" in words(m)
    assert fewer >= 0.8 * n, fewer  # the check: fewer tokens 93.2% at 50 cases
