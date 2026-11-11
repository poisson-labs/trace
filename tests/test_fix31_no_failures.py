"""trace#31: ``fix-check`` answers when the runs it compares hold no failed run.

On main at ``a4bc065`` a pair in which neither run carried the event was refused, ``unknown
event failed; the runs carry the outcomes: ok``, exit 1 and nothing on stdout, so Poisson
Break's confirm stage, which asks ``fix-check --json`` of a control arm and each candidate's
arm, ended with no finding on a sound agent. These tests hold the answer.

The cases:

- **Neither version failed on the inputs compared** (FIX31-1 to FIX31-9). Whether the event's
  name is carried by neither run (Break's case, refused on main) or by a run on an input that
  is not compared (answered on main, by the rule for a drop). The answer is the fix check's own
  statistics at zero counts: both shares 0, the difference 0, the exact test's p 1 (its
  distribution is one point), no direction, the stratified Miettinen-Nurminen range (which at
  zero failures is a closed form and never one point wide), no drop limit and the rise limit.
  The range reads the verdict: *no significant difference* when it lies inside plus or minus
  the size asked, *too small to tell* otherwise, with the tries that would bring it inside.
  Ruled 2026-11-10 (F31-3, F31-4; FIX31-21, FIX31-22): on fewer than three inputs, and where the
  tries are so unequal across the inputs that the range's one-sided miss is above 5%, the range
  is labelled rough and does not read the verdict: main's rule for a drop does, as before.
- **Only one version failed** (FIX31-10, FIX31-11): answered on main already; their numbers
  are checked here against the independent computations, and their bytes are pinned in
  ``test_fix31_unchanged.py``.
- **What is still refused** (FIX31-12): no input with an outcome on both versions; a name
  neither run carries while a run carries an outcome that is no word for success.
- **Every way in and out** (FIX31-13 to FIX31-17): the saved verdict, the bundle, the pages,
  folders and the Python API.

Every number is checked against a computation written in ``fix31_support.py`` that shares no
code with the package: enumeration in fractions, scipy, or a closed form derived there.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from fix31_support import (
    BREAK_CASES, BREAK_FAILED_1, BREAK_REPEATS, CANDIDATE_1, CANDIDATE_2, CONTROL, MISS_BAR,
    accepts_at, asked, break_argv, break_case, clean, clean_chance, clean_inputs_needed, clean_miss,
    clean_range,
    clean_repeats_needed, difference, exact_p, exact_power_of_a_rise, fisher_p, junit_clean,
    limit, no_outcome_store, other_outcome_store, score_range, selecting_store, stray_store,
)
from fixcheck_support import FIX_KEYS, GUIDANCE_KEYS, exact_p_enumerated, pair_store
from tf0_support import Ran, chdir, trace

INTERVAL = "stratified Miettinen-Nurminen score interval, Mantel-Haenszel weights"

# ---------- the words (each a call of Taylor's; a ruling moves them here) ----------

SENTENCE_NO_DIFFERENCE = "neither version failed"


def sentence_too_small(points: str) -> str:
    article = "an" if points.startswith("8") or points in ("11", "18") else "a"
    return f"neither version failed, on too few tries to rule out {article} {points}-point change"


NOTE_NEITHER = "- event {event}: carried by neither run"
DROP_LINE = ("- a drop in failure share: no limit; neither version failed on these inputs, so "
             "there is no failure to drop")
NEXT_BIGGER = ("If a change inside that range matters to you, plan a bigger run with your own "
               "harness, then run `poisson-trace fix-check` on it.")
GUIDANCE_CLOSING = ("These numbers hold if neither version fails in the next runs either, and if "
                    "new inputs resemble the present ones. A run in which either version fails "
                    "is read as any other.")
CLOSE_TO_THE_MOST = "is close to the most these inputs could drop"
# F31-3 and F31-4 (ruled 2026-11-10): where the range at zero is rough, main's rule for a drop
# reads the pair, in main's words, and the range prints with its reason
SENTENCE_ROUGH = "too few tries to see a drop of any size"
FEW_INPUTS = "fewer than 3 inputs"
UNEQUAL = "unequal tries"
NO_GUIDANCE = {"repeats": None, "inputs": None, "accepts_at": None}


def points(x: float, places: int = 1) -> str:
    """A signed share as the report's range prints it."""
    return f"{100.0 * x:+.{places}f}"


def per_100(x: float) -> str:
    """Failures per 100 tries as the summary says them: whole from 10, else one decimal, two below 1."""
    v = abs(100.0 * x)
    if round(v) >= 10:
        return f"{v:.0f}"
    return f"{v:.1f}" if round(v, 2) >= 1 else f"{v:.2f}"


def fits(lo: float, hi: float) -> str:
    return f"anything from {per_100(lo)} fewer failures per 100 tries to {per_100(hi)} more"


def answered(ran: Ran) -> Ran:
    assert ran.code == 0, ran.text
    assert ran.err == "", ran.err
    assert ran.out, "nothing was printed"
    return ran


def doc_of(store: Path, *extra: str, **kw: str) -> dict[str, Any]:
    doc: dict[str, Any] = answered(asked(store, *extra, "--json", **kw)).json()
    return doc


def lines_of(store: Path, *extra: str, **kw: str) -> list[str]:
    return answered(asked(store, *extra, **kw)).out.splitlines()


def design_of(tab: list[tuple[int, int, int, int]]) -> list[tuple[int, int]]:
    return [(na, nb) for _, na, _, nb in tab]


# the pairs in which neither version failed: (label, inputs, old tries, new tries, size asked)
CLEAN = [
    ("six by five", 6, 5, 5, "0.2"),
    ("three by four", 3, 4, 4, "0.2"),
    ("three inputs, one try", 3, 1, 1, "0.2"),
    ("one try on thirty inputs", 30, 1, 1, "0.25"),
    ("three by three, new run longer", 3, 3, 9, "0.3"),
    ("forty by fifty", 40, 50, 50, "0.01"),
    ("four by eight", 4, 8, 8, "0.5"),
]
CLEAN_IDS = [c[0] for c in CLEAN]


# ---------- FIX31-1: Break's case, on the committed fixture ----------


def test_fix31_1_breaks_case_is_answered(tmp_path: Path) -> None:
    """The control and a candidate that changes nothing, neither with a failed run, asked as
    Break asks: one JSON document, exit 0, with the verdict and direction words, the shares,
    the difference, the range and p that Break reads."""
    store = break_case(tmp_path)
    ran = answered(trace(break_argv(CONTROL, CANDIDATE_2, store)))
    doc = ran.json()
    tries = BREAK_CASES * BREAK_REPEATS
    design = [(BREAK_REPEATS, BREAK_REPEATS)] * BREAK_CASES
    tab = clean(BREAK_CASES, BREAK_REPEATS)
    lo, hi = clean_range(design)
    assert doc["schema"] == "poisson-trace.fix-check/2"
    assert doc["verdict"] == "no significant difference"
    assert doc["direction"] == "no direction"
    assert doc["sentence"] == SENTENCE_NO_DIFFERENCE
    for arm in ("old", "new"):
        assert (doc["rows"][arm]["failed"], doc["rows"][arm]["runs"]) == (0, tries)
        # the share Break computes: failed over runs
        assert doc["rows"][arm]["failed"] / doc["rows"][arm]["runs"] == 0.0
    assert doc["difference"]["points"] == 0.0 == float(difference(tab))
    assert doc["difference"]["lo"] == pytest.approx(lo, abs=1e-9)
    assert doc["difference"]["hi"] == pytest.approx(hi, abs=1e-9)
    # the same range from the score with numerically constrained rates
    assert (doc["difference"]["lo"], doc["difference"]["hi"]) == pytest.approx(score_range(tab), abs=1e-6)
    assert doc["difference"]["lo"] < 0.0 < doc["difference"]["hi"]
    assert -0.2 < doc["difference"]["lo"] and doc["difference"]["hi"] < 0.2
    assert doc["test"]["p"] == 1.0 == exact_p(tab) == exact_p_enumerated(tab) == fisher_p(tab)
    assert doc["guidance"] is None
    assert list(doc) == list(FIX_KEYS)


def test_fix31_1_the_candidate_with_the_weakness_gets_its_verdict_beside_it(tmp_path: Path) -> None:
    """The stage of the issue: against a control that never fails, the candidate that fails 28
    runs of 30 is *different*, failed more, and the candidate that changes nothing is answered
    too, so the stage is whole."""
    store = break_case(tmp_path)
    weak = answered(trace(break_argv(CONTROL, CANDIDATE_1, store))).json()
    sound = answered(trace(break_argv(CONTROL, CANDIDATE_2, store))).json()
    assert (weak["verdict"], weak["direction"]) == ("different", "failed more in new")
    assert weak["rows"]["new"]["failed"] == BREAK_FAILED_1
    assert (sound["verdict"], sound["direction"]) == ("no significant difference", "no direction")


def test_fix31_1_the_answer_is_the_same_bytes_each_time_and_either_way_round(tmp_path: Path) -> None:
    store = break_case(tmp_path)
    first = answered(trace(break_argv(CONTROL, CANDIDATE_2, store)))
    again = answered(trace(break_argv(CONTROL, CANDIDATE_2, store)))
    assert first.out == again.out
    turned = answered(trace(break_argv(CANDIDATE_2, CONTROL, store))).json()
    doc = first.json()
    # the pair is symmetric here: the range turned round is the range mirrored
    assert turned["verdict"] == doc["verdict"] and turned["direction"] == "no direction"
    assert turned["difference"]["lo"] == pytest.approx(-doc["difference"]["hi"], abs=1e-12)
    assert turned["difference"]["hi"] == pytest.approx(-doc["difference"]["lo"], abs=1e-12)


# ---------- FIX31-2: every number at zero counts, in --json ----------


@pytest.mark.parametrize(("label", "inputs", "old", "new", "ceiling"), CLEAN, ids=CLEAN_IDS)
def test_fix31_2_every_number_of_a_pair_that_never_failed(
    tmp_path: Path, label: str, inputs: int, old: int, new: int, ceiling: str
) -> None:
    tab = clean(inputs, old, new)
    design = design_of(tab)
    doc = doc_of(pair_store(tmp_path / "s", tab), ceiling=ceiling)
    assert list(doc) == list(FIX_KEYS)
    assert doc["events"] == ["fail"]
    assert doc["inputs"]["compared"] == inputs and doc["inputs"]["informative"] == 0
    for arm, tries in (("old", inputs * old), ("new", inputs * new)):
        assert doc["rows"][arm]["runs"] == tries and doc["rows"][arm]["failed"] == 0
        assert doc["rows"][arm]["mixed"] == 0
    assert doc["control"] == {"old_did_not_fail_share": 1.0, "new_did_not_fail_share": 1.0}
    # the exact test: nothing to redistribute, so its distribution is one point
    test = doc["test"]
    assert test["observed_new"] == 0 and test["expected_new"] == 0.0 and test["variance"] == 0.0
    assert test["weight"] == pytest.approx(sum(a * b / (a + b) for a, b in design), rel=1e-12)
    assert test["p"] == 1.0 == exact_p(tab)
    # the difference and its range
    diff = doc["difference"]
    assert diff["points"] == 0.0 == float(difference(tab))
    assert diff["interval"] == INTERVAL
    lo, hi = clean_range(design)
    assert diff["lo"] == pytest.approx(lo, abs=1e-9) and diff["hi"] == pytest.approx(hi, abs=1e-9)
    assert (diff["lo"], diff["hi"]) == pytest.approx(score_range(tab), abs=1e-6)
    assert -1.0 < diff["lo"] < 0.0 < diff["hi"] < 1.0
    assert diff["variance"] == 0.0
    assert doc["by_input"] == {"moved": 0, "p": 1.0, "method": "exact", "draws": None, "seed": None}
    cons = doc["consistency"]
    assert cons["failure_share"] == 0.0 and cons["fails_again"] is None and cons["kappa"] is None
    assert cons["within"] == 0.0 and cons["pooled"] == 0.0
    # what it could catch: no drop (there is no failure to drop), and the rise of the spec's
    # power formula with the old version at zero
    limits = doc["limits"]
    assert limits["drop"] is None and limit(tab, "drop") is None
    rise = limit(tab, "rise")
    if rise is None:
        assert limits["rise"] is None
    else:
        assert limits["rise"] == pytest.approx(rise, abs=1e-9)
    assert limits["max_mde"] == float(ceiling) and limits["power"] == 0.8
    assert doc["direction"] == "no direction"
    # the range reads the verdict
    a = float(ceiling)
    if -a <= lo and hi <= a:
        assert doc["verdict"] == "no significant difference"
        assert doc["sentence"] == SENTENCE_NO_DIFFERENCE
        assert doc["guidance"] is None
    else:
        assert doc["verdict"] == "too small to tell"
        assert doc["sentence"] == sentence_too_small(f"{100.0 * a:g}")
        g = doc["guidance"]
        assert set(g) == GUIDANCE_KEYS
        assert g["repeats"] == clean_repeats_needed(inputs, a)
        assert g["inputs"] == clean_inputs_needed(design, a)
        assert g["accepts_at"] == pytest.approx(accepts_at(lo, hi), abs=1e-12)
    changes = doc["changes"]
    assert changes["tested"] == inputs and changes["flagged"] == 0
    assert all(r["failed_a"] == 0 and r["failed_b"] == 0 and r["p"] == 1.0 and r["flag"] is None
               for r in changes["rows"])
    json.dumps(doc, allow_nan=False)


def test_fix31_2_both_verdicts_are_reached() -> None:
    """The table above holds pairs on each side of the size asked, so neither branch of the
    test before this one is empty."""
    sides = set()
    for _, inputs, old, new, ceiling in CLEAN:
        lo, hi = clean_range([(old, new)] * inputs)
        sides.add(-float(ceiling) <= lo and hi <= float(ceiling))
    assert sides == {True, False}


@pytest.mark.parametrize("alpha", ["0.1", "0.01"])
def test_fix31_2_the_range_is_at_the_level_asked(tmp_path: Path, alpha: str) -> None:
    tab = clean(5, 4)
    doc = doc_of(pair_store(tmp_path / "s", tab), "--alpha", alpha)
    lo, hi = clean_range(design_of(tab), float(alpha))
    assert doc["difference"]["lo"] == pytest.approx(lo, abs=1e-9)
    assert doc["difference"]["hi"] == pytest.approx(hi, abs=1e-9)
    assert (doc["difference"]["lo"], doc["difference"]["hi"]) == pytest.approx(
        score_range(tab, float(alpha)), abs=1e-6)
    assert doc["test"]["alpha"] == float(alpha)


def test_fix31_2_the_verdict_turns_exactly_where_the_range_meets_the_size_asked(tmp_path: Path) -> None:
    """On six inputs by five tries the range's ends are 12.4555 points: asked for 12.46 the
    range lies inside and it reads *no significant difference*; asked for 12.45 it does not."""
    store = pair_store(tmp_path / "s", clean(6, 5))
    lo, hi = clean_range([(5, 5)] * 6)
    assert 0.1245 < hi < 0.1246 and lo == -hi
    inside = doc_of(store, ceiling="0.1246")
    outside = doc_of(store, ceiling="0.1245")
    assert inside["verdict"] == "no significant difference" and inside["guidance"] is None
    assert outside["verdict"] == "too small to tell"
    assert outside["guidance"]["repeats"] == clean_repeats_needed(6, 0.1245) == 6
    assert outside["guidance"]["accepts_at"] == 0.1246


# ---------- FIX31-3: the range at zero is never one point, and what it leaves out ----------


@pytest.mark.parametrize(("inputs", "tries"), [(1, 1), (1, 5), (2, 2), (3, 1), (6, 5), (12, 3), (40, 50)])
def test_fix31_3_the_range_at_zero_has_two_ends_that_close_with_more_tries(
    tmp_path: Path, inputs: int, tries: int
) -> None:
    doc = doc_of(pair_store(tmp_path / "s", clean(inputs, tries)))
    more = doc_of(pair_store(tmp_path / "m", clean(inputs, tries + 1)))
    lo, hi = doc["difference"]["lo"], doc["difference"]["hi"]
    assert lo == pytest.approx(-hi, abs=1e-12) and hi > 0.0
    assert 0.0 < more["difference"]["hi"] < hi


@pytest.mark.parametrize(("inputs", "tries"), [(3, 1), (3, 2), (3, 5), (4, 3), (6, 5), (10, 2), (12, 12), (40, 50)])
def test_fix31_3_a_rise_beyond_the_range_would_have_shown(inputs: int, tries: int) -> None:
    """What the high end means, checked exactly. If the new version failed on a share of tries
    as large as the range's high end, on every input alike, the chance of the clean run that was
    seen is the binomial's at zero. With equal tries of both versions and three inputs or more
    that chance is under 2.5%, the range's stated one-sided miss at 95%."""
    _, hi = clean_range([(tries, tries)] * inputs)
    assert clean_chance(inputs * tries, hi) < 0.025


@pytest.mark.parametrize(("inputs", "tries", "most"), [(1, 1, 0.116), (1, 2, 0.079), (1, 5, 0.046), (1, 30, 0.026),
                                                       (2, 1, 0.043), (2, 5, 0.029), (2, 10, 0.0252)])
def test_fix31_3_on_one_or_two_inputs_the_miss_is_larger_and_this_is_how_large(
    inputs: int, tries: int, most: float
) -> None:
    """The same chance on one or two inputs, where it is above 2.5%: the figures the record
    gives (rulings.md, F31-3). The range is the score interval's, which is approximate there."""
    _, hi = clean_range([(tries, tries)] * inputs)
    assert 0.025 < clean_chance(inputs * tries, hi) < most


@pytest.mark.parametrize(("inputs", "tries"), [(6, 5), (4, 3), (3, 8), (10, 2)])
def test_fix31_3_the_rise_limit_is_caught_at_least_four_times_in_five(inputs: int, tries: int) -> None:
    """The rise limit printed for a pair that never failed, put to the exact test itself: with
    the old version never failing and the new failing that share of tries, every outcome
    enumerated, the test calls *different, failed more* at least 80% of the time."""
    rise = limit(clean(inputs, tries), "rise")
    assert rise is not None
    power = exact_power_of_a_rise([(tries, tries)] * inputs, rise)
    assert 0.8 <= power < 0.95


# ---------- FIX31-4: the plain report, a pair inside the size asked ----------


def test_fix31_4_the_plain_report_of_breaks_case(tmp_path: Path) -> None:
    store = pair_store(tmp_path / "s", clean(6, 5))
    lines = lines_of(store)
    lo, hi = clean_range([(5, 5)] * 6)
    assert (points(lo), points(hi)) == ("-12.5", "+12.5")
    assert lines[0] == f"no significant difference  {SENTENCE_NO_DIFFERENCE}"
    assert lines[1] == "" and lines[2].startswith("# Poisson Trace · fix check · ")
    assert ("- Answer: Neither version failed. The new version failed 0 of 30 tries and the old 0 "
            f"of 30; the results fit {fits(lo, hi)}, so a change of 20 points or more either way "
            "does not fit them (if tries of an input are independent).") in lines
    assert f"- Next: {NEXT_BIGGER}" in lines
    assert "- events: fail" in lines
    assert NOTE_NEITHER.format(event="fail") in lines
    assert "| old | 30 | 0 | 0.0% | 100.0% |" in lines and "| new | 30 | 0 | 0.0% | 100.0% |" in lines
    assert ("exact conditional Cochran-Mantel-Haenszel test, stratified by input over 6 inputs "
            "(0 informative), two-sided; α = 0.05.") in lines
    assert "new failures: observed 0, expected 0.000, variance 0.000; p = 1.000" in lines
    assert ("difference: 0.0 points, new minus old (-12.5 to +12.5; Mantel-Haenszel weights; range: "
            "stratified Miettinen-Nurminen score interval, 95%, for these inputs as run)") in lines
    assert "by input: p = 1.000 (sign-flip over the 0 inputs that moved, exact); not part of the line below" in lines
    assert DROP_LINE in lines
    rise = limit(clean(6, 5), "rise")
    assert rise is not None
    assert f"- a rise in failure share: could not have detected one below {100.0 * rise:.1f} points" in lines
    assert ("**no significant difference (p = 1.000); the 95% range, -12.5 to +12.5 points, lies "
            "inside ±20**") in lines
    assert "## Guidance" not in lines
    assert lines[-1] == "next: poisson-trace fix-check --help"


def test_fix31_4_the_report_says_nothing_it_said_of_a_drop(tmp_path: Path) -> None:
    """The sentences main printed for zero counts by its rule for a drop are gone: no *drop of
    any size*, no interval withheld, no *every failure gone, a drop of 0.00 points*, and no size
    asked *close to the most these inputs could drop*."""
    text = answered(asked(pair_store(tmp_path / "s", clean(6, 5)))).out
    for gone in ("drop of any size", "no interval", "can't put a range", "every failure gone",
                 CLOSE_TO_THE_MOST, "rough"):
        assert gone not in text, gone


def test_fix31_4_the_caveats_keep_the_range_and_the_copies(tmp_path: Path) -> None:
    lines = lines_of(pair_store(tmp_path / "s", clean(6, 5)))
    lo, hi = clean_range([(5, 5)] * 6)
    assert (f"- These results fit {fits(lo, hi)} (ranges built this way hold the true difference "
            "about 95 times in 100, if tries are independent), which does not include a 20-point "
            "drop.") in lines
    assert ("- Tries of the same input are counted as separate chances, and if they are near "
            "copies the answer is more confident than it should be.") in lines
    assert "- Trace would catch a 28-point rise 4 times in 5, a smaller rise less often." in lines


def test_fix31_4_two_decimals_where_the_range_is_under_a_point(tmp_path: Path) -> None:
    lines = lines_of(pair_store(tmp_path / "s", clean(40, 50)), ceiling="0.01")
    lo, hi = clean_range([(50, 50)] * 40)
    assert (points(lo, 2), points(hi, 2)) == ("-0.19", "+0.19")
    assert ("difference: 0.00 points, new minus old (-0.19 to +0.19; Mantel-Haenszel weights; "
            "range: stratified Miettinen-Nurminen score interval, 95%, for these inputs as run)") in lines
    assert ("**no significant difference (p = 1.000); the 95% range, -0.19 to +0.19 points, lies "
            "inside ±1**") in lines


# ---------- FIX31-5: the plain report, a pair too small for the size asked ----------


def test_fix31_5_the_plain_report_of_a_pair_too_small(tmp_path: Path) -> None:
    store = pair_store(tmp_path / "s", clean(3, 4))
    lines = lines_of(store)
    lo, hi = clean_range([(4, 4)] * 3)
    assert (points(lo), points(hi)) == ("-26.8", "+26.8")
    repeats, inputs = clean_repeats_needed(3, 0.2), clean_inputs_needed([(4, 4)] * 3, 0.2)
    assert (repeats, inputs) == (6, 5)
    assert lines[0] == f"too small to tell  {sentence_too_small('20')}"
    assert ("- Answer: Can't tell yet. The new version failed 0 of 12 tries and the old 0 of 12; "
            f"they fit {fits(lo, hi)} (if tries of an input are independent), so a change of 20 "
            "points or more still fits them.") in lines
    assert ("- Next: Run each version 6 times on each of these 3 inputs with your own harness, "
            "then run `poisson-trace fix-check` on the two new runs.") in lines
    assert ("**too small to tell: the 95% range, -26.8 to +26.8 points, does not lie inside ±20, "
            "which was asked for**") in lines
    at = lines.index("## Guidance")
    assert lines[at + 2:at + 7] == [
        "- repeats: 6 per arm on these 3 inputs, with no failure in either version, would bring "
        "the range inside ±20 points",
        "- inputs: 5 inputs like these, at the present repeats, would do the same",
        f"- ceiling: --max-mde {accepts_at(lo, hi):.4f} accepts this design as it stands",
        "",
        GUIDANCE_CLOSING,
    ]
    assert DROP_LINE in lines
    assert lines[-1] == ("next: run 6 repeats per arm on these 3 inputs, then poisson-trace "
                         "fix-check on the two new runs")


def test_fix31_5_the_caveats_of_a_pair_too_small(tmp_path: Path) -> None:
    lines = lines_of(pair_store(tmp_path / "s", clean(3, 4)))
    lo, hi = clean_range([(4, 4)] * 3)
    assert ("- The 6 times per input is what brings the range inside ±20 points if neither version "
            "fails then either. 5 inputs like these at the present tries would do the same, more "
            "than the 3 here. Make it a fresh run, judged on its own: don't add tries to these "
            "and test again.") in lines
    assert (f"- If a {per_100(max(-lo, hi))}-point change is the smallest that matters to you, and "
            "you would have said so before seeing this, "
            f"`--max-mde {accepts_at(lo, hi):.4f}` accepts this design as it stands. That changes "
            "the label only, not the evidence.") in lines
    text = "\n".join(lines)
    for gone in ("drop of any size", "an estimate from these runs' failure rates", CLOSE_TO_THE_MOST,
                 "about half of runs built to it"):
        assert gone not in text, gone


def test_fix31_5_the_tries_it_names_are_enough_when_run(tmp_path: Path) -> None:
    """The guidance is checked by following it: the pair too small at 3 by 4, run again at the
    tries named with no failure, reads *no significant difference*; one try fewer does not. The
    inputs named likewise."""
    assert doc_of(pair_store(tmp_path / "a", clean(3, 6)))["verdict"] == "no significant difference"
    assert doc_of(pair_store(tmp_path / "b", clean(3, 5)))["verdict"] == "too small to tell"
    assert doc_of(pair_store(tmp_path / "c", clean(5, 4)))["verdict"] == "no significant difference"
    assert doc_of(pair_store(tmp_path / "d", clean(4, 4)))["verdict"] == "too small to tell"


def test_fix31_5_unequal_tries_give_unequal_ends(tmp_path: Path) -> None:
    """Three inputs, 3 tries of the old version and 9 of the new: fewer old tries leave more
    room for a drop than new tries leave for a rise, and the larger end reads the verdict."""
    tab = clean(3, 3, 9)
    doc = doc_of(pair_store(tmp_path / "s", tab), ceiling="0.3")
    lo, hi = clean_range(design_of(tab))
    assert -lo > 0.3 > hi
    assert doc["verdict"] == "too small to tell"
    assert doc["guidance"]["accepts_at"] == pytest.approx(accepts_at(lo, hi), abs=1e-12)


# ---------- FIX31-6: the pair main answered by its rule for a drop ----------


def test_fix31_6_a_failure_only_on_an_input_not_compared(tmp_path: Path) -> None:
    """The old run failed once, on an input the new run does not hold. The inputs compared hold
    no failure, so the answer is the answer of a pair that never failed; the event is carried,
    so the note is main's."""
    store = stray_store(tmp_path / "s", clean(6, 5))
    doc = doc_of(store)
    assert doc["inputs"]["selected"] == 7 and doc["inputs"]["compared"] == 6
    assert doc["inputs"]["left_out"]["not re-run on the new version"] == 1
    assert doc["verdict"] == "no significant difference" and doc["sentence"] == SENTENCE_NO_DIFFERENCE
    lo, hi = clean_range([(5, 5)] * 6)
    assert doc["difference"]["lo"] == pytest.approx(lo, abs=1e-9)
    assert doc["difference"]["hi"] == pytest.approx(hi, abs=1e-9)
    lines = lines_of(store)
    assert "- event fail: carried by the old run only" in lines
    assert NOTE_NEITHER.format(event="fail") not in lines
    assert "- 1 input was left out (1 not re-run on the new version)." in lines


def test_fix31_6_the_inputs_picked_from_a_selecting_run(tmp_path: Path) -> None:
    """``--failing-from``: the inputs failed in the selecting run and neither re-run failed on
    them. Answered as any pair that never failed, under the control's heading."""
    store = selecting_store(tmp_path / "s", clean(6, 5))
    ran = answered(trace(["fix-check", "old", "new", "--store", str(store), "--event", "fail",
                          "--failing-from", "sel", "--max-mde", "0.2"]))
    lines = ran.out.splitlines()
    assert lines[0] == f"no significant difference  {SENTENCE_NO_DIFFERENCE}"
    assert "## The control" in lines
    doc = answered(trace(["fix-check", "old", "new", "--store", str(store), "--event", "fail",
                          "--failing-from", "sel", "--max-mde", "0.2", "--json"])).json()
    assert doc["inputs"]["rule"] == "failing-from" and doc["inputs"]["compared"] == 6
    assert doc["verdict"] == "no significant difference"


def test_fix31_6_different_targets_keep_the_replay_warning(tmp_path: Path) -> None:
    """Two runs that never failed match input for input. Where their targets differ, main's
    rule for matching runs still speaks: the Compared line says one may replay the other, and a
    pair too small is told to check that before adding tries. The numbers are the same."""
    from fix31_support import T_NEW, T_OLD
    from fixcheck_support import arm_rows, build_run

    for name, tab, verdict in (("inside", clean(6, 5), "no significant difference"),
                               ("small", clean(3, 4), "too small to tell")):
        root = tmp_path / name
        build_run(root, "old", arm_rows(tab, "old"), created_at=T_OLD, target_id="agent/one")
        build_run(root, "new", arm_rows(tab, "new"), created_at=T_NEW, target_id="agent/two")
        doc = doc_of(root)
        assert doc["verdict"] == verdict
        lo, hi = clean_range(design_of(tab))
        assert doc["difference"]["lo"] == pytest.approx(lo, abs=1e-9)
        text = answered(asked(root)).out
        assert ("Their targets differ (agent/one, agent/two), and every input failed the same "
                "number of times in both: if one replays the other, this is not a comparison of "
                "two versions.") in text
        if verdict == "too small to tell":
            assert doc["sentence"] == "one run may replay the other: check that before adding tries"
        else:
            assert doc["sentence"] == SENTENCE_NO_DIFFERENCE


# ---------- FIX31-7: the event's name ----------


def test_fix31_7_two_names_neither_run_carries(tmp_path: Path) -> None:
    store = pair_store(tmp_path / "s", clean(6, 5))
    ran = answered(trace(["fix-check", "old", "new", "--store", str(store), "--event", "fail",
                          "--event", "crashed", "--inputs", "all", "--max-mde", "0.2"]))
    lines = ran.out.splitlines()
    at = lines.index("- events: crashed, fail")
    assert lines[at + 1:at + 3] == [NOTE_NEITHER.format(event="crashed"), NOTE_NEITHER.format(event="fail")]
    assert lines[0] == f"no significant difference  {SENTENCE_NO_DIFFERENCE}"


def test_fix31_7_a_misspelt_name_on_runs_that_hold_failures_is_still_refused(tmp_path: Path) -> None:
    """The guard against a typing slip stays where a slip could hide failures: a name neither
    run carries is refused, as on main, when a run carries an outcome that is no word for
    success. (Its bytes are pinned in ``test_fix31_unchanged.py``.)"""
    store = pair_store(tmp_path / "s", [(2, 5, 1, 5)] * 4)
    ran = asked(store, event="faild")
    assert ran.code == 1 and ran.out == ""
    assert ran.err.splitlines()[0] == "error: unknown event faild; the runs carry the outcomes: fail, ok"
    other = asked(other_outcome_store(tmp_path / "o"))
    assert other.code == 1 and other.out == ""
    assert other.err.splitlines()[0] == "error: unknown event fail; the runs carry the outcomes: crashed, ok"


# ---------- FIX31-8: the other verbs are not changed ----------


def test_fix31_8_changes_and_where_still_refuse_the_name(tmp_path: Path) -> None:
    """trace#31 is fix-check's. ``changes`` and ``where`` on runs that never failed refuse the
    event as before (their bytes are pinned in ``test_fix31_unchanged.py``); this test is here
    so that a later change to them is made on purpose. It asks fix-check first, which must
    answer."""
    store = pair_store(tmp_path / "s", clean(6, 5))
    answered(asked(store))
    for argv in (["changes", "old", "new"], ["where", "old"]):
        ran = trace([*argv, "--store", str(store), "--event", "fail"])
        assert ran.code == 1 and ran.out == "", ran.text
        assert ran.err.startswith("error: unknown event fail; the run"), ran.err


# ---------- FIX31-9: pretty and plain ----------


def test_fix31_9_plain_is_the_piped_output(tmp_path: Path) -> None:
    store = pair_store(tmp_path / "s", clean(6, 5))
    assert answered(asked(store, "--plain")).out == answered(asked(store)).out


# ---------- FIX31-10, FIX31-11: only one version failed ----------

ONE_SIDED = {
    "old none, new some": [(0, 5, 0, 5)] * 5 + [(0, 5, 3, 5)],
    "new none, old some": [(0, 5, 0, 5)] * 5 + [(3, 5, 0, 5)],
    "old none, new on several inputs": [(0, 6, 2, 6), (0, 6, 1, 6), (0, 6, 0, 6), (0, 6, 3, 6)] * 3,
    "new none, old on several inputs": [(2, 6, 0, 6), (1, 6, 0, 6), (0, 6, 0, 6), (3, 6, 0, 6)] * 3,
    "old none on unequal tries": [(0, 3, 2, 7), (0, 9, 1, 2), (0, 4, 0, 4)],
    "new none on unequal tries": [(2, 7, 0, 3), (1, 2, 0, 9), (0, 4, 0, 4)],
}


@pytest.mark.parametrize("label", list(ONE_SIDED))
def test_fix31_10_every_number_where_one_version_never_failed(tmp_path: Path, label: str) -> None:
    """One version holds no failed run and the other does. Main answers these; the numbers Break
    reads, and the limits, against the independent computations."""
    tab = ONE_SIDED[label]
    doc = doc_of(pair_store(tmp_path / "s", tab))
    failed_old, failed_new = sum(r[0] for r in tab), sum(r[2] for r in tab)
    assert min(failed_old, failed_new) == 0 < max(failed_old, failed_new)
    assert doc["rows"]["old"]["failed"] == failed_old and doc["rows"]["new"]["failed"] == failed_new
    assert doc["rows"]["old"]["runs"] == sum(r[1] for r in tab)
    assert doc["rows"]["new"]["runs"] == sum(r[3] for r in tab)
    d = float(difference(tab))
    assert doc["difference"]["points"] == pytest.approx(d, abs=1e-12)
    assert doc["test"]["p"] == pytest.approx(exact_p(tab), rel=1e-9)
    lo, hi = score_range(tab)
    assert doc["difference"]["lo"] == pytest.approx(lo, abs=1e-6)
    assert doc["difference"]["hi"] == pytest.approx(hi, abs=1e-6)
    assert doc["difference"]["lo"] < d < doc["difference"]["hi"]
    for direction in ("drop", "rise"):
        want = limit(tab, direction)
        if want is None:
            assert doc["limits"][direction] is None
        else:
            assert doc["limits"][direction] == pytest.approx(want, abs=1e-9)
    assert doc["direction"] == ("failed more in new" if failed_new else "failed less in new")
    if doc["test"]["p"] < 0.05:
        assert doc["verdict"] == "different"
    else:
        assert doc["verdict"] in ("no significant difference", "too small to tell")
    lines = lines_of(pair_store(tmp_path / "t", tab))
    assert f"- event fail: carried by the {'new' if failed_new else 'old'} run only" in lines


def test_fix31_11_one_input_is_fishers_test(tmp_path: Path) -> None:
    """One input, one version never failing: the exact test is Fisher's, scipy's number."""
    for k, tab in enumerate(([(0, 8, 5, 8)], [(5, 8, 0, 8)], [(0, 3, 1, 3)])):
        doc = doc_of(pair_store(tmp_path / f"s{k}", tab), ceiling="0.5")
        assert doc["test"]["p"] == pytest.approx(fisher_p(tab), rel=1e-9)
        assert doc["test"]["p"] == pytest.approx(exact_p_enumerated(tab), rel=1e-9)


# ---------- FIX31-12: what is still refused ----------


def test_fix31_12_no_try_with_an_outcome_is_refused_in_one_sentence(tmp_path: Path) -> None:
    """Runs in which no try has an outcome cannot be answered: there is no try to count. One
    sentence that says so, exit 1, nothing on stdout, in plain and in --json."""
    store = no_outcome_store(tmp_path / "s")
    for extra in ((), ("--json",)):
        ran = asked(store, *extra)
        assert ran.code == 1 and ran.out == "", ran.text
        first = ran.err.splitlines()[0]
        assert first == ("error: no input is left to compare: 4 selected, left out: no outcome "
                         "on the old version 4"), first


def test_fix31_12_no_outcome_on_one_side_is_refused(tmp_path: Path) -> None:
    """The old version has outcomes and never failed; the new has none on any input."""
    from fix31_support import T_NEW, T_OLD
    from fixcheck_support import Obs, arm_rows, build_run

    root = tmp_path / "s"
    build_run(root, "old", arm_rows(clean(3, 2), "old"), created_at=T_OLD)
    build_run(root, "new", [Obs(f"i{k}", None, "timeout") for k in range(3)], created_at=T_NEW)
    ran = asked(root)
    assert ran.code == 1 and ran.out == ""
    assert ran.err.splitlines()[0] == ("error: no input is left to compare: 3 selected, left out: "
                                       "no outcome on the new version 3")


def test_fix31_12_no_input_in_common_is_refused(tmp_path: Path) -> None:
    from fix31_support import T_NEW, T_OLD
    from fixcheck_support import Obs, build_run

    root = tmp_path / "s"
    build_run(root, "old", [Obs("a", "ok"), Obs("b", "ok")], created_at=T_OLD)
    build_run(root, "new", [Obs("c", "ok")], created_at=T_NEW)
    ran = asked(root)
    assert ran.code == 1 and ran.out == ""
    assert ran.err.splitlines()[0] == (
        "error: no input is left to compare: 3 selected, left out: not re-run on the old version 1; "
        "not re-run on the new version 2")


# ---------- FIX31-13: the saved verdict ----------


def test_fix31_13_the_saved_verdict(tmp_path: Path) -> None:
    from tf6_support import descriptor, result_of, the_artifact

    store = pair_store(tmp_path / "s", clean(6, 5))
    said = answered(asked(store, "--json")).json()
    saved = answered(asked(store, "--save", "--json")).json()
    folder = the_artifact(store, "fix-check")
    assert saved["saved"] == f".poisson/artifacts/fix-check/{folder.name}"
    kept = result_of(folder)
    for key in ("verdict", "sentence", "direction", "difference", "test", "rows", "limits", "guidance"):
        assert kept[key] == said[key], key
    assert kept["verdict"] == "no significant difference" and kept["sentence"] == SENTENCE_NO_DIFFERENCE
    assert descriptor(folder)["kind"] == "fix-check"
    plain = answered(asked(store)).out
    assert (folder / "report.md").read_text(encoding="utf-8").splitlines()[0] == plain.splitlines()[0]


def test_fix31_13_the_saved_verdict_of_a_pair_too_small(tmp_path: Path) -> None:
    from tf6_support import result_of, the_artifact

    store = pair_store(tmp_path / "s", clean(3, 4))
    answered(asked(store, "--save"))
    kept = result_of(the_artifact(store, "fix-check"))
    assert kept["verdict"] == "too small to tell"
    assert kept["guidance"]["repeats"] == 6 and kept["guidance"]["inputs"] == 5


# ---------- FIX31-14: the bundle ----------


def test_fix31_14_the_bundle_is_whole(tmp_path: Path) -> None:
    store = pair_store(tmp_path / "s", clean(6, 5))
    bundle = tmp_path / "bundle"
    answered(asked(store, "--out", str(bundle)))
    plain = answered(asked(store)).out
    report = (bundle / "report.md").read_text(encoding="utf-8")
    assert report.splitlines()[0] == plain.splitlines()[0] == f"no significant difference  {SENTENCE_NO_DIFFERENCE}"
    result = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
    assert result["verdict"] == "no significant difference"
    assert result["difference"]["lo"] == pytest.approx(clean_range([(5, 5)] * 6)[0], abs=1e-9)
    checked = trace(["handover", "--check", str(bundle)])
    assert checked.code == 0, checked.text
    assert checked.out.startswith("ok  ")


# ---------- FIX31-15: the pages ----------


@pytest.mark.parametrize(("inputs", "tries"), [(6, 5), (3, 4), (2, 5)], ids=["inside", "too small", "rough"])
def test_fix31_15_the_verdict_page_shows_the_report(tmp_path: Path, inputs: int, tries: int) -> None:
    from tf18_support import missing_lines, pages_of, read_file, report_lines, verdict_line
    from tf6_support import result_of, the_artifact

    store = pair_store(tmp_path / "s", clean(inputs, tries))
    answered(asked(store, "--save"))
    folder = the_artifact(store, "fix-check")
    page = read_file(pages_of(store) / "fix-check" / f"{folder.name}.html")
    result = result_of(folder)
    assert page.h1 == verdict_line(result)
    assert (result["sentence"] == SENTENCE_ROUGH) == (inputs < 3)
    assert result["sentence"].startswith(SENTENCE_NO_DIFFERENCE) == (inputs >= 3)
    report = (folder / "report.md").read_text(encoding="utf-8")
    assert missing_lines(page, report_lines(report)) == []
    index = read_file(pages_of(store) / "index.html")
    assert any(result["verdict"] in block for block in index.blocks)


# ---------- FIX31-16: folders ----------


def test_fix31_16_two_folders_in_which_every_case_passed(tmp_path: Path) -> None:
    """Two JUnit folders, every case passed in both: read from the folders, ``--event missed``
    names an outcome neither holds, and the fix check answers (refused on main)."""
    junit_clean(tmp_path / "before", started="2026-11-01T10:00:00")
    junit_clean(tmp_path / "after", started="2026-11-02T10:00:00")
    base = ["fix-check", "before", "after", "--event", "missed", "--inputs", "all", "--max-mde", "0.5"]
    with chdir(tmp_path):
        plain = answered(trace([*base, "--plain"]))
        doc = answered(trace([*base, "--json"])).json()
    lo, hi = clean_range([(1, 1)] * 12)
    assert doc["rows"]["old"] == {**doc["rows"]["old"], "runs": 12, "failed": 0}
    assert doc["rows"]["new"] == {**doc["rows"]["new"], "runs": 12, "failed": 0}
    assert doc["difference"]["lo"] == pytest.approx(lo, abs=1e-9)
    assert doc["difference"]["hi"] == pytest.approx(hi, abs=1e-9)
    assert doc["test"]["p"] == 1.0 and doc["direction"] == "no direction"
    assert doc["verdict"] == ("no significant difference" if hi <= 0.5 else "too small to tell")
    assert doc["prove"]["store"] is None
    assert plain.out.splitlines()[0] == f"{doc['verdict']}  {doc['sentence']}"
    assert NOTE_NEITHER.format(event="missed") in plain.out.splitlines()


def test_fix31_16_two_imported_runs_in_which_every_case_passed(tmp_path: Path) -> None:
    """The same two reports imported into a store, then asked by name."""
    from tf0_support import trace_import

    for run, started in (("before", "2026-11-01T10:00:00Z"), ("after", "2026-11-02T10:00:00Z")):
        junit_clean(tmp_path / run)
        made = trace_import(["junit", str(tmp_path / run / "report.xml"), "--store", str(tmp_path / "st"),
                             "--run", run, "--started", started])
        assert made.code == 0, made.text
    doc = answered(trace(["fix-check", "before", "after", "--store", str(tmp_path / "st"), "--event", "missed",
                          "--inputs", "all", "--max-mde", "0.5", "--json"])).json()
    assert doc["rows"]["old"]["failed"] == 0 == doc["rows"]["new"]["failed"]
    assert doc["verdict"] in ("no significant difference", "too small to tell")
    assert doc["sentence"].startswith(SENTENCE_NO_DIFFERENCE)


# ---------- FIX31-17: the Python API ----------


def test_fix31_17_the_python_api_answers(tmp_path: Path) -> None:
    import poisson_trace.api as api

    store = pair_store(tmp_path / "s", clean(6, 5))
    result = api.fix_check(str(store), "old", "new", event=["fail"], inputs="all", max_mde=0.2)
    lo, hi = clean_range([(5, 5)] * 6)
    assert result.verdict == "no significant difference"
    assert result.sentence == SENTENCE_NO_DIFFERENCE
    assert result.direction == "no direction"
    assert result.rows["old"]["failed"] == 0 == result.rows["new"]["failed"]
    assert result.difference["points"] == 0.0
    assert result.difference["lo"] == pytest.approx(lo, abs=1e-9)
    assert result.difference["hi"] == pytest.approx(hi, abs=1e-9)
    assert result.test["p"] == 1.0
    assert result.limits["drop"] is None and result.guidance is None
    # the result prints what the command line prints, byte for byte
    assert result.to_json() == answered(asked(store, "--json")).out
    assert result.to_markdown() == answered(asked(store)).out


def test_fix31_17_the_python_api_on_a_pair_too_small_and_on_breaks_case(tmp_path: Path) -> None:
    import poisson_trace.api as api

    small = api.fix_check(str(pair_store(tmp_path / "s", clean(3, 4))), "old", "new", event=["fail"],
                          inputs="all", max_mde=0.2)
    assert small.verdict == "too small to tell"
    assert small.guidance == {"repeats": 6, "inputs": 5,
                              "accepts_at": accepts_at(*clean_range([(4, 4)] * 3))}
    rough = api.fix_check(str(pair_store(tmp_path / "r", clean(2, 5))), "old", "new", event=["fail"],
                          inputs="all", max_mde=0.2)
    assert (rough.verdict, rough.sentence) == ("too small to tell", SENTENCE_ROUGH)
    assert rough.guidance == NO_GUIDANCE
    store = break_case(tmp_path)
    sound = api.fix_check(str(store), CONTROL, CANDIDATE_2, event=["failed"], inputs="all", max_mde=0.2)
    assert (sound.verdict, sound.direction) == ("no significant difference", "no direction")


def test_fix31_17_the_python_api_still_refuses_what_cannot_be_answered(tmp_path: Path) -> None:
    import poisson_trace.api as api

    store = pair_store(tmp_path / "s", clean(6, 5))
    assert api.fix_check(str(store), "old", "new", event=["fail"], inputs="all", max_mde=0.2).verdict
    with pytest.raises(api.Refusal) as refused:
        api.fix_check(str(no_outcome_store(tmp_path / "n")), "old", "new", event=["fail"], inputs="all",
                      max_mde=0.2)
    assert "no input is left to compare" in str(refused.value)
    with pytest.raises(api.Refusal) as unknown:
        api.fix_check(str(other_outcome_store(tmp_path / "o")), "old", "new", event=["fail"], inputs="all",
                      max_mde=0.2)
    assert "unknown event fail" in str(unknown.value)


# ---------- the statistics module itself ----------


def test_fix31_18_the_statistics_at_zero_counts() -> None:
    """``poisson_trace.paired`` on counts with no failure: the difference with its range, the
    test, the limits and the range-based guidance, each against its independent computation."""
    from poisson_trace import paired

    for inputs, old, new in ((6, 5, 5), (1, 1, 1), (3, 3, 9), (12, 2, 7), (40, 50, 50)):
        tab = clean(inputs, old, new)
        counts = [paired.Counts(f"h{k}", *row) for k, row in enumerate(tab)]
        d, variance, lo, hi = paired.difference(counts)
        want = clean_range(design_of(tab))
        assert d == 0.0 and variance == 0.0
        assert lo is not None and hi is not None
        assert (lo, hi) == pytest.approx(want, abs=1e-9)
        assert paired.paired_test(counts).p == 1.0
        why = paired.rough(counts, informative=0, disagree=False)
        assert why == (("fewer than 3 inputs",) if inputs < 3 else ())
        assert paired.detection_limit(counts, direction="drop") is None


def test_fix31_18_counts_with_a_failure_keep_their_statistics() -> None:
    """Counts that hold a failure are not touched: where Sato's variance is not positive and a
    version failed, there is still no interval, and the roughness reasons are main's."""
    from poisson_trace import paired

    counts = [paired.Counts(f"h{k}", 4, 4, 0, 4) for k in range(3)]
    d, variance, lo, hi = paired.difference(counts)
    assert d == -1.0 and (variance, lo, hi) == (None, None, None)
    every = [paired.Counts(f"h{k}", 5, 5, 5, 5) for k in range(6)]
    assert paired.difference(every) == (0.0, None, None, None)
    assert paired.rough(every, informative=0, disagree=False) == ("fewer than 10 inputs vary",)
    one = [paired.Counts("h", 0, 1, 1, 1)]
    assert paired.rough(one, informative=1, disagree=False) == (
        "fewer than 10 inputs vary", "one try per input on the new version",
        "one try per input on the old version")


def test_fix31_19_the_closed_form_is_the_score_interval() -> None:
    """The closed form the tests use for the range at zero is the score interval itself: on a
    spread of designs it meets the interval found from the score with numerically constrained
    rates. A check of the tests' own oracle, green before and after the fix."""
    designs = [[(1, 1)], [(5, 5)] * 6, [(3, 9)] * 3, [(2, 6), (7, 3), (4, 4), (1, 9)], [(1, 1)] * 30,
               [(50, 50)] * 4, [(11, 1)], [(6, 22), (4, 13), (16, 2)]]
    for design in designs:
        tab = [(0, a, 0, b) for a, b in design]
        for alpha in (0.05, 0.1):
            assert clean_range(design, alpha) == pytest.approx(score_range(tab, alpha), abs=1e-7)
    assert math.isclose(clean_range([(5, 5)] * 6)[1], 0.12455502974186711, rel_tol=1e-12)


# ---------- FIX31-20: on a terminal ----------


@pytest.mark.parametrize("cols", [80, 140])
@pytest.mark.parametrize(("inputs", "tries", "word"), [(6, 5, "no significant difference"), (3, 4, "too small to tell")])
def test_fix31_20_on_a_terminal_the_same_facts_in_the_verdicts_colour(
    tmp_path: Path, cols: int, inputs: int, tries: int, word: str
) -> None:
    """The pretty rendering of the new answer: exit 0, every word and number of the piped report
    is on the terminal, pretty and ``--plain``, and the verdict word opens the first line in
    yellow, as the look gives both of these verdicts (docs/cli-look.md)."""
    from tf13_support import cli
    from tf9_support import cells, role, strip, tokens
    from tf9_support import run as pty

    pair_store(tmp_path / "s", clean(inputs, tries))
    home = tmp_path / "home"
    home.mkdir()
    argv = ["fix-check", "old", "new", "--store", "s", "--event", "fail", "--inputs", "all", "--max-mde", "0.2"]
    piped = cli(tmp_path, argv)
    assert piped.code == 0 and piped.out.startswith(f"{word}  {SENTENCE_NO_DIFFERENCE}")
    pretty = pty(argv, cwd=tmp_path, home=home, cols=cols)
    plain = pty([*argv, "--plain"], cwd=tmp_path, home=home, cols=cols)
    for ran in (pretty, plain):
        assert ran.code == 0, ran.err
        assert tokens(piped.out) <= tokens(ran.out), sorted(tokens(piped.out) - tokens(ran.out))
    first = cells(pretty.out)[0]
    assert "".join(c.char for c in first).startswith(f"{word}  {SENTENCE_NO_DIFFERENCE}")
    assert {role(c) for c in first[:len(word)] if c.char != " "} == {"Y"}
    assert strip(plain.out).split("\n")[0].startswith(f"{word}  {SENTENCE_NO_DIFFERENCE}")


# ---------- FIX31-21: fewer than three inputs (F31-3, ruled 2026-11-10) ----------

FEW = [(2, 5, "0.2"), (1, 1, "0.2"), (1, 30, "0.2"), (2, 14, "0.2"), (2, 2, "0.9")]


@pytest.mark.parametrize(("inputs", "tries", "ceiling"), FEW)
def test_fix31_21_on_fewer_than_three_inputs_the_range_is_rough(
    tmp_path: Path, inputs: int, tries: int, ceiling: str
) -> None:
    """At zero failures a range on one or two inputs is labelled rough, wherever it lies: it
    prints, with its reason, and does not read the verdict. Main's rule for a drop reads it, as
    it read these counts before: *too small to tell*, with no count of tries."""
    tab = clean(inputs, tries)
    store = pair_store(tmp_path / "s", tab)
    doc = doc_of(store, ceiling=ceiling)
    lo, hi = clean_range(design_of(tab))
    assert doc["difference"]["lo"] == pytest.approx(lo, abs=1e-9)
    assert doc["difference"]["hi"] == pytest.approx(hi, abs=1e-9)
    assert doc["difference"]["points"] == 0.0 and doc["difference"]["variance"] == 0.0
    assert doc["test"]["p"] == 1.0 and doc["direction"] == "no direction"
    assert (doc["verdict"], doc["sentence"]) == ("too small to tell", SENTENCE_ROUGH)
    assert doc["guidance"] == NO_GUIDANCE
    assert doc["limits"]["drop"] is None
    lines = lines_of(store, ceiling=ceiling)
    assert lines[0] == f"too small to tell  {SENTENCE_ROUGH}"
    places = 2 if max(-lo, hi) < 0.01 else 1
    assert (f"difference: {0.0:.{places}f} points, new minus old ({points(lo, places)} to {points(hi, places)}; "
            "Mantel-Haenszel weights; range: stratified Miettinen-Nurminen score interval, 95%, for "
            f"these inputs as run; rough here: {FEW_INPUTS})") in lines
    assert (f"- These results fit {fits(lo, hi)}, but that range is only a rough guide here and may "
            f"be off either way ({FEW_INPUTS}): don't use it to rule sizes in or out.") in lines
    n = inputs * tries
    assert (f"- Answer: Can't tell. The new version failed 0 of {n} tries and the old 0 of {n}, and "
            "with these tries Trace can't reliably catch a drop of any size.") in lines
    assert DROP_LINE in lines
    text = "\n".join(lines)
    for gone in ("Neither version failed", "which is reliable here", "would bring the range inside",
                 CLOSE_TO_THE_MOST, "lies inside"):
        assert gone not in text, gone


def test_fix31_21_the_label_does_not_wait_on_where_the_range_lies(tmp_path: Path) -> None:
    """Two inputs by 14 tries: the range, ±12.5 points, lies inside ±20 and the pair is still
    *too small to tell*, because the range is rough there. Three inputs by 9 tries, a range of
    ±13.1, read *no significant difference*."""
    lo, hi = clean_range([(14, 14)] * 2)
    assert hi < 0.2 and hi == pytest.approx(clean_range([(5, 5)] * 6)[1], abs=2e-3)
    assert doc_of(pair_store(tmp_path / "two", clean(2, 14)))["verdict"] == "too small to tell"
    three = doc_of(pair_store(tmp_path / "three", clean(3, 9)))
    assert three["verdict"] == "no significant difference" and three["sentence"] == SENTENCE_NO_DIFFERENCE


def test_fix31_21_why_the_bar_is_three() -> None:
    """The figures behind F31-3: at equal tries the range's one-sided miss is under 2.5% from
    three inputs up, and above it on one or two."""
    for inputs, tries, above in ((1, 1, True), (1, 5, True), (2, 1, True), (2, 5, True), (3, 1, False),
                                 (3, 2, False), (6, 5, False)):
        _, hi = clean_range([(tries, tries)] * inputs)
        assert (clean_chance(inputs * tries, hi) > 0.025) == above, (inputs, tries)


# ---------- FIX31-22: unequal tries (F31-4, ruled 2026-11-10) ----------

# five inputs, one with many old tries and few new, four the other way round: one try apart,
# the range's least favourable one-sided miss is 3.95% and 5.60%
UNDER = [(0, 7, 0, 3)] + [(0, 3, 0, 7)] * 4
OVER = [(0, 8, 0, 3)] + [(0, 3, 0, 8)] * 4


def test_fix31_22_the_two_sides_of_the_bar() -> None:
    assert MISS_BAR == 0.05
    assert clean_miss(design_of(UNDER)) == pytest.approx(0.0395, abs=5e-4)
    assert clean_miss(design_of(OVER)) == pytest.approx(0.0560, abs=5e-4)
    # equal tries, and one try missing, are far under it
    assert clean_miss([(5, 5)] * 6) < 0.02 and clean_miss([(5, 5)] * 5 + [(5, 4)]) < 0.025


def test_fix31_22_under_the_bar_the_range_reads_the_verdict(tmp_path: Path) -> None:
    store = pair_store(tmp_path / "s", UNDER)
    doc = doc_of(store, ceiling="0.25")
    lo, hi = clean_range(design_of(UNDER))
    assert -0.25 < lo and hi < 0.25
    assert doc["difference"]["lo"] == pytest.approx(lo, abs=1e-9)
    assert doc["difference"]["hi"] == pytest.approx(hi, abs=1e-9)
    assert (doc["verdict"], doc["sentence"]) == ("no significant difference", SENTENCE_NO_DIFFERENCE)
    assert "rough" not in answered(asked(store, ceiling="0.25")).out


def test_fix31_22_over_the_bar_the_range_is_rough(tmp_path: Path) -> None:
    """One more try on each side of the lopsided inputs and the least favourable miss passes
    5%: the range still prints, labelled, and main's rule for a drop reads the pair."""
    store = pair_store(tmp_path / "s", OVER)
    doc = doc_of(store, ceiling="0.25")
    lo, hi = clean_range(design_of(OVER))
    assert -0.25 < lo and hi < 0.25  # it would have read no significant difference
    assert doc["difference"]["lo"] == pytest.approx(lo, abs=1e-9)
    assert doc["difference"]["hi"] == pytest.approx(hi, abs=1e-9)
    assert (doc["verdict"], doc["sentence"]) == ("too small to tell", SENTENCE_ROUGH)
    assert doc["guidance"] == NO_GUIDANCE and doc["test"]["p"] == 1.0
    lines = lines_of(store, ceiling="0.25")
    assert (f"difference: 0.0 points, new minus old ({points(lo)} to {points(hi)}; Mantel-Haenszel "
            "weights; range: stratified Miettinen-Nurminen score interval, 95%, for these inputs as "
            f"run; rough here: {UNEQUAL})") in lines
    assert (f"- These results fit {fits(lo, hi)}, but that range is only a rough guide here and may "
            f"be off either way ({UNEQUAL}): don't use it to rule sizes in or out.") in lines


def test_fix31_22_tries_a_little_short_stay_reliable(tmp_path: Path) -> None:
    """Break's arms with a try or two that gave no outcome: six inputs by five tries, one input
    a try short on the new side and one two short on the old. Under the bar, and the range reads
    the verdict."""
    tab = [(0, 5, 0, 5)] * 4 + [(0, 5, 0, 4), (0, 3, 0, 5)]
    assert clean_miss(design_of(tab)) < MISS_BAR
    doc = doc_of(pair_store(tmp_path / "s", tab))
    lo, hi = clean_range(design_of(tab))
    assert doc["verdict"] == ("no significant difference" if -0.2 <= lo and hi <= 0.2 else "too small to tell")
    assert doc["sentence"].startswith(SENTENCE_NO_DIFFERENCE)


def test_fix31_22_on_fewer_than_three_inputs_one_reason_is_given(tmp_path: Path) -> None:
    """On one or two inputs the miss is large whatever the tries, so the reason given is the
    number of inputs alone, lopsided tries or not: the unequal-tries reason is for a pair that
    would otherwise be reliable."""
    for k, tab in enumerate(([(0, 12, 0, 1), (0, 1, 0, 12)], [(0, 12, 0, 1)], [(0, 1, 0, 1)])):
        lines = lines_of(pair_store(tmp_path / f"s{k}", tab), ceiling="0.5")
        assert any(line.endswith(f"rough here: {FEW_INPUTS})") for line in lines), tab
        assert not any(UNEQUAL in line for line in lines), tab
        assert lines[0] == f"too small to tell  {SENTENCE_ROUGH}"
