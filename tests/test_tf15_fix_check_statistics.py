"""TF15-S1 to TF15-S14: fix-check's statistics (docs/how-it-decides.md says them in plain words).

- The range is the stratified Miettinen-Nurminen score interval, Mantel-Haenszel weights, with
  its per-input N/(N-1) factor; the point estimate is unchanged. Its line names it, says it is for
  these inputs as run, and adds "rough here: {why}" where the range is not reliable.
- *no significant difference* when the test does not call it and a reliable range lies inside
  plus or minus the size asked; *too small to tell* otherwise; where the range is not reliable
  (reliable: it exists, agrees with the test, at least 10 compared inputs vary, neither version
  ran once per input), the drop limit against the size asked decides, as before.
- A *too small to tell* answer whose reliable range leaves out a drop of the size asked says
  so, one-sided.
- An unconfirmed *different* names the inputs that carry it, and the gap and p without them.
- The per-input column "could not have detected a rise below" and its JSON key go; the
  schemas of fix-check and changes move to /2.

Every number pinned here comes from a reference that is not Trace's code: an independent
statistics check's stratified Miettinen-Nurminen interval on per-input counts of these fixtures,
Newcombe's (1998) published worked example, and that check's recount without the flagged inputs.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from conftest import CS, CS_EVENTS, CS_RECORD, CS_REPLAY, TAU2, TAU2_A, TAU2_B, norm
from fixcheck_support import (
    HE_A, HE_B, HE_EVENTS, HUMANEVAL, PILOT, TAU2_EVENTS, WORKED, changes, counts_of, fix_check, ok,
    pair_store,
)
from tf15_support import bold_line, caveats, first_line, section, summary

ALL = ("--inputs", "all")


def _json(result):  # type: ignore[no-untyped-def]
    assert result.code == 0, result.text
    return result.json()


def _difference_line(out: str) -> str:
    found = [line for line in out.splitlines() if line.startswith("difference: ")]
    assert len(found) == 1, found
    return norm(found[0])


# ---------- the stratified Miettinen-Nurminen interval ----------

# an independent implementation of the interval, on per-input counts; fractions
MN = {
    "tau2_all": (-0.060441, 0.081196),        # tau2, all inputs
    "humaneval": (0.000378, 0.009263),        # the HumanEval pair
    "failing_from": (-0.615002, 0.113135),    # tau2, --failing-from
    "cs": (-0.212105, 0.212105),              # the cs pair
    "worked": (-0.501442, 0.004307),          # the frozen tests' WORKED table
}


@pytest.mark.parametrize("name,argv,points", [
    ("tau2_all", (TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.12"), 0.0100),
    ("humaneval", (HUMANEVAL, HE_A, HE_B, HE_EVENTS, *ALL, "--max-mde", "0.05"), 0.004668),
    ("failing_from", (TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.20"), -0.25),
    ("cs", (CS, CS_RECORD, CS_REPLAY, CS_EVENTS, *ALL, "--max-mde", "0.25"), 0.0),
])
def test_tf15_s1_the_range_is_the_stratified_miettinen_nurminen_interval(name, argv, points) -> None:  # type: ignore[no-untyped-def]
    d = _json(fix_check(*argv, "--json"))["difference"]
    assert d["points"] == pytest.approx(points, abs=1e-6)  # the Mantel-Haenszel estimate, unchanged
    lo, hi = MN[name]
    assert d["lo"] == pytest.approx(lo, abs=2e-6), name
    assert d["hi"] == pytest.approx(hi, abs=2e-6), name


def test_tf15_s1_the_worked_table_and_the_function() -> None:
    from poisson_trace.paired import difference

    points, var, lo, hi = difference(counts_of(WORKED))
    assert points == pytest.approx(-0.25, abs=1e-12)
    assert var == pytest.approx(0.015625, abs=1e-6)  # Sato's variance, still the JSON's "variance"
    assert (lo, hi) == (pytest.approx(MN["worked"][0], abs=2e-6), pytest.approx(MN["worked"][1], abs=2e-6))


def test_tf15_s2_one_input_gives_newcombes_worked_example() -> None:
    """Newcombe (1998), Stat Med 17:873-890, Table II: 56/70 against 48/80, the Miettinen-Nurminen
    interval 0.0528 to 0.3382 (with one input the stratified interval is the two-sample one)."""
    from poisson_trace.paired import Counts, difference

    points, _, lo, hi = difference([Counts("h", 48, 80, 56, 70)])
    assert points == pytest.approx(0.2, abs=1e-12)
    assert lo == pytest.approx(0.0528, abs=5e-5) and hi == pytest.approx(0.3382, abs=5e-5)


@pytest.mark.math
def test_tf15_s3_the_interval_holds_its_nominal_coverage_with_one_new_try_per_input() -> None:
    """The failing-from design of the README's patch example (6 inputs, 4 old tries, 1 new) under
    no change, 1,500 seeded draws. The independent check found Sato's interval covering 86-87% here
    and the Miettinen-Nurminen interval 95%; at seed 1 the check's
    `mn_stratified` covers 0.954 and Sato's 0.842. Monte Carlo se at 0.95
    is 0.0056, so the band 0.925 to 0.975 is 4.5 se either side: Sato's falls 15 se below it."""
    from poisson_trace.paired import Counts, difference

    p = np.array([0.75, 0.75, 0.95, 0.95, 0.8, 0.3])
    rng = np.random.default_rng(1)
    covered = 0
    reps = 1500
    for _ in range(reps):
        xa = rng.binomial(4, p)
        xb = rng.binomial(1, p)
        _, _, lo, hi = difference([Counts(str(i), int(a), 4, int(b), 1) for i, (a, b) in enumerate(zip(xa, xb, strict=True))])
        covered += lo is not None and lo <= 0.0 <= hi
    assert 0.925 <= covered / reps <= 0.975, covered / reps


def test_tf15_s4_the_interval_line_names_its_method_and_what_it_covers() -> None:
    out = ok(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.12")).out
    line = _difference_line(out)
    assert "Miettinen-Nurminen" in line and "as run" in line, line
    assert "rough here" not in line, line
    assert "Sato" not in norm(out)
    d = _json(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.12", "--json"))
    assert "Miettinen-Nurminen" in d["difference"]["interval"] and "Sato" not in d["difference"]["interval"]


def test_tf15_s5_rough_here_names_why_where_the_gate_fails(tmp_path: Path) -> None:
    """The failing-from design: 4 of 6 inputs vary, and the new version ran once per input."""
    line = _difference_line(ok(fix_check(TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.20")).out)
    assert "rough here:" in line, line
    why = line.split("rough here:", 1)[1]
    assert "fewer than 10 inputs vary" in why and "one try per input on the new version" in why, line
    assert "old version" not in why, line
    root = pair_store(tmp_path / "old_once", ONE_OLD_TRY)
    swapped = _difference_line(ok(fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", "0.309")).out)
    assert "rough here:" in swapped and "one try per input on the old version" in swapped, swapped
    assert "new version" not in swapped.split("rough here:", 1)[1], swapped
    cs = _difference_line(ok(fix_check(CS, CS_RECORD, CS_REPLAY, CS_EVENTS, *ALL, "--max-mde", "0.25")).out)
    assert "rough here:" in cs and "fewer than 10 inputs vary" in cs and "one try per input" not in cs, cs


# ---------- the verdict on a reliable range ----------


def test_tf15_s6_tau2_at_ten_points_reads_no_significant_difference() -> None:
    """The first result of the README: -6.0 to +8.1 lies inside plus or minus 10 (the rule's
    own example), though the drop limit, 11.1, is above 10."""
    d = _json(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.10", "--json"))
    assert d["verdict"] == "no significant difference"
    assert d["guidance"] is None
    assert d["limits"]["drop"] == pytest.approx(0.110854, abs=1e-4)  # the plan's number, unchanged
    out = ok(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.10")).out
    assert first_line(out)[0] == "no significant difference"
    bold = norm(bold_line(out))
    assert bold.startswith("no significant difference"), bold
    assert re.search(r"p = 0\.883\b", bold), bold
    assert re.search(r"-6\.0 to \+8\.1 points, lies inside ±10\b", bold), bold
    assert "could not have detected" not in bold


def _gate_pair(tmp_path: Path, name: str, tab):  # type: ignore[no-untyped-def]
    return pair_store(tmp_path / name, tab)


# Each table was found by search and checked against the reference (the independent interval,
# unchanged drop limit and exact test): its reference numbers sit beside it.
POWER_SAYS_YES = [  # 15 inputs, 14 vary; p 0.320; range -6.6 to +25.9; drop limit 23.67 <= 24
    (1, 4, 1, 4), (3, 4, 1, 4), (0, 4, 2, 4), (0, 4, 0, 4), (1, 4, 2, 4), (3, 4, 3, 4), (3, 4, 3, 4),
    (2, 4, 1, 4), (0, 4, 3, 4), (2, 4, 4, 4), (0, 4, 1, 4), (0, 4, 2, 4), (1, 4, 0, 4), (2, 4, 2, 4),
    (3, 4, 2, 4),
]
TEN_VARY = [  # 10 vary; p 0.163; range -37.3 to +3.8; drop limit 31.13 <= 32
    (1, 4, 0, 4), (3, 4, 2, 4), (2, 4, 2, 4), (1, 4, 0, 4), (3, 4, 2, 4), (3, 4, 3, 4), (1, 4, 2, 4),
    (3, 4, 1, 4), (4, 4, 2, 4), (2, 4, 2, 4),
]
NINE_VARY = [  # 9 vary; p 0.224; range -38.1 to +5.9; drop limit 34.18 <= 35
    (4, 4, 3, 4), (0, 4, 1, 4), (3, 4, 1, 4), (4, 4, 1, 4), (3, 4, 2, 4), (3, 4, 3, 4), (2, 4, 2, 4),
    (2, 4, 2, 4), (2, 4, 2, 4),
]
ONE_NEW_TRY = [  # new ran once per input; 18 vary; p 0.595; range -29.9 to +14.9; drop limit 34.76 > 30.9
    (2, 4, 0, 1), (3, 4, 0, 1), (0, 4, 1, 1), (3, 4, 1, 1), (2, 4, 1, 1), (1, 4, 0, 1), (3, 4, 0, 1),
    (3, 4, 1, 1), (2, 4, 1, 1), (0, 4, 0, 1), (0, 4, 0, 1), (4, 4, 0, 1), (2, 4, 1, 1), (4, 4, 0, 1),
    (3, 4, 0, 1), (1, 4, 0, 1), (2, 4, 1, 1), (3, 4, 1, 1), (3, 4, 1, 1), (1, 4, 0, 1),
]
ONE_OLD_TRY = [(b, d, a, c) for a, c, b, d in ONE_NEW_TRY]  # the same table, the arms swapped: the old ran once
DISAGREE = [  # 10 vary; exact p 0.0746 but the range -54.4 to -1.2 leaves out 0; drop limit 38.54 <= 45
    (0, 2, 1, 2), (2, 2, 1, 2), (2, 2, 0, 2), (0, 2, 0, 2), (0, 2, 0, 2), (2, 2, 1, 2), (1, 2, 1, 2),
    (2, 2, 0, 2), (1, 2, 0, 2), (1, 2, 1, 2), (1, 2, 1, 2), (2, 2, 1, 2),
]


@pytest.mark.parametrize("name,tab,asked,verdict", [
    # reliable and not inside: too small to tell, where the drop limit alone said no difference
    ("power_says_yes", POWER_SAYS_YES, "0.24", "too small to tell"),
    # exactly 10 inputs vary: the range decides
    ("ten_vary", TEN_VARY, "0.32", "too small to tell"),
    # 9 vary: not reliable, the drop limit decides
    ("nine_vary", NINE_VARY, "0.35", "no significant difference"),
    # one try per input on the new version: not reliable; inside plus or minus 30.9, but the
    # drop limit, 34.8, decides
    ("one_new_try", ONE_NEW_TRY, "0.309", "too small to tell"),
    # one try per input on the old version: the same, from the other side
    ("one_old_try", ONE_OLD_TRY, "0.309", "too small to tell"),
    # the range disagrees with the test: not reliable, the drop limit decides
    ("disagree", DISAGREE, "0.45", "no significant difference"),
])
def test_tf15_s7_the_gate_decides_which_rule_reads_the_verdict(tmp_path: Path, name, tab, asked, verdict) -> None:  # type: ignore[no-untyped-def]
    root = _gate_pair(tmp_path, name, tab)
    d = _json(fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", asked, "--json"))
    assert d["verdict"] == verdict, (name, d["difference"], d["limits"], d["test"]["p"])
    assert (d["guidance"] is not None) == (verdict == "too small to tell"), name


@pytest.mark.parametrize("name,tab,asked", [
    ("power_says_yes", POWER_SAYS_YES, "0.24"),
    ("ten_vary", TEN_VARY, "0.32"),
    ("one_new_try", ONE_NEW_TRY, "0.309"),
])
def test_tf15_s7_the_plan_offered_moves_the_verdict(tmp_path: Path, name, tab, asked) -> None:  # type: ignore[no-untyped-def]
    """Whatever too small to tell offers must work: a ceiling it says accepts the design, given,
    reads otherwise; a number of tries per input it says to run is not the design these runs had. Where the range decided the verdict and
    the drop limit is already under the size asked, the power-based plan has nothing true to say,
    so it is withheld or larger than the design."""
    root = _gate_pair(tmp_path, name, tab)
    d = _json(fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", asked, "--json"))
    assert d["verdict"] == "too small to tell"
    g = d["guidance"]
    if g["accepts_at"] is not None:
        again = _json(fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", repr(g["accepts_at"]), "--json"))
        assert again["verdict"] != "too small to tell", (name, g, again["difference"])
    if g["repeats"] is not None:
        # not the design already run: every input with that many tries on both versions
        assert not all(na == g["repeats"] == nb for _, na, _, nb in tab), (name, g)


def test_tf15_s7_the_range_is_named_at_its_own_level(tmp_path: Path) -> None:
    """At --alpha 0.1 the interval printed is a 90% one, and the line the verdict rests on says so:
    here -3.9 to +23.5 lies inside plus or minus 24."""
    root = _gate_pair(tmp_path, "alpha", POWER_SAYS_YES)
    out = ok(fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", "0.24", "--alpha", "0.1")).out
    assert "90%" in _difference_line(out)
    bold = norm(bold_line(out))
    assert bold.startswith("no significant difference") and "90% range" in bold and "95%" not in bold, bold


@pytest.mark.parametrize("name,tab,asked", [("nine_vary", NINE_VARY, "0.35"), ("disagree", DISAGREE, "0.45")])
def test_tf15_s7_no_size_is_said_not_to_fit_where_power_decided(tmp_path: Path, name, tab, asked) -> None:  # type: ignore[no-untyped-def]
    """Where the range is not reliable the drop limit decides, and nothing says a size does not
    fit: the bold line keeps the limit's sentence, and the Answer is the weak row."""
    root = _gate_pair(tmp_path, name, tab)
    out = ok(fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", asked)).out
    bold = norm(bold_line(out))
    assert bold.startswith("no significant difference") and "could not have detected a drop in failure share below" in bold, bold
    assert "lies inside" not in bold and "range" not in bold, bold
    answer = summary(out)["Answer"]
    assert answer.startswith("No clear change, but this run says little. "), answer
    assert "does not fit" not in answer, answer


def test_tf15_s8_a_range_reaching_the_size_asked_on_either_side_stays_too_small_to_tell() -> None:
    """Two-sided: tau2 at 7.5 points, -6.0 to +8.1, a drop of 7.5 or more
    does not fit but a rise of 7.5 still does; at 5 points neither side is left out."""
    for asked in ("0.075", "0.05"):
        d = _json(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", asked, "--json"))
        assert d["verdict"] == "too small to tell", asked
        assert d["guidance"] is not None, asked


def test_tf15_s9_different_still_follows_the_exact_test() -> None:
    d = _json(fix_check(HUMANEVAL, HE_A, HE_B, HE_EVENTS, *ALL, "--max-mde", "0.02", "--json"))
    assert (d["verdict"], d["direction"]) == ("different", "failed more in new")


# ---------- the one-sided sentence, only on a reliable range ----------


def test_tf15_s10_the_one_sided_answer_on_a_reliable_range() -> None:
    out = ok(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.075")).out
    assert first_line(out) == (
        "too small to tell",
        "too few tries to see a 7.5-point drop by Trace's rule; a drop that size does not fit the results",
    )
    assert summary(out)["Answer"] == (
        "Can't tell yet. The new version failed 112 of 200 tries and the old 110 of 200; they fit anything "
        "from 6.0 fewer failures per 100 tries to 8.1 more (if tries of an input are independent): a drop of "
        "7.5 points or more does not fit them, but a rise of 7.5 or more still does."
    )
    d = _json(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.075", "--json"))
    assert d["sentence"] == first_line(out)[1]


@pytest.mark.parametrize("argv", [
    # reliable, but the low end reaches the drop asked: -6.0 against 5 points
    (TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.05"),
    # not reliable (1 input of 7 varies): -21.2 would leave out a 25-point drop, and is not used
    (CS, CS_RECORD, CS_REPLAY, CS_EVENTS, *ALL, "--max-mde", "0.25"),
    # not reliable (the failing-from design)
    (TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.20"),
])
def test_tf15_s11_no_size_is_ruled_out_without_a_reliable_range_leaving_it_out(argv) -> None:  # type: ignore[no-untyped-def]
    out = ok(fix_check(*argv)).out
    word, sentence = first_line(out)
    assert word == "too small to tell"
    assert "does not fit" not in sentence and "Trace's rule" not in sentence, sentence
    answer = summary(out)["Answer"]
    assert answer.startswith("Can't tell yet. "), answer
    assert "does not fit" not in answer, answer


# ---------- an unconfirmed different names what carries it ----------


def test_tf15_s12_an_unconfirmed_difference_names_its_inputs_and_the_gap_without_them() -> None:
    """The HumanEval pair: different (exact p 0.036), by-input p 0.127. The changes block flags
    HumanEval/129 at both temperatures (32 of the net 49 extra failures); without them the
    Mantel-Haenszel gap is +0.16 points and the exact test's p 0.4745 (the independent check's
    recount without them, and test_tr69's own recomputation of the p)."""
    out = ok(fix_check(HUMANEVAL, HE_A, HE_B, HE_EVENTS, *ALL, "--max-mde", "0.02")).out
    answer = norm(summary(out)["Answer"])
    assert "32 of the net 49 extra failures come from" in answer, answer
    assert "HumanEval/129" in answer, answer
    without = "Without task_id HumanEval/129 at both settings, the gap is 0.16 points (p = 0.47)."
    assert sum(without in norm(c) for c in caveats(out)) == 1, caveats(out)
    # the verdict is the exact test's, as before
    assert first_line(out)[0] == "different"


def test_tf15_s12_an_unconfirmed_difference_with_nothing_flagged(tmp_path: Path) -> None:
    """One input moved (5 of 50 to 18 of 50) among 39 that never failed: the exact test calls it
    different, the by-input check cannot (one input moved), and no input is flagged once
    Benjamini-Hochberg reads 40 inputs. The Answer counts nothing and the caveat names nothing."""
    root = pair_store(tmp_path, [(5, 50, 18, 50)] + [(0, 4, 0, 4)] * 39)
    d = _json(fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", "0.5", "--json"))
    assert d["verdict"] == "different" and d["by_input"]["p"] >= 0.05 and d["changes"]["flagged"] == 0, (
        d["test"]["p"], d["by_input"], d["changes"]["flagged"])
    out = ok(fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", "0.5")).out
    assert "come from" not in summary(out)["Answer"]
    assert not any("Without " in c for c in caveats(out)), caveats(out)
    assert any(norm(c).startswith("A check of which inputs went up and which went down can't rule out chance on its own")
               for c in caveats(out)), caveats(out)


def test_tf15_s13_a_confirmed_difference_names_nothing_without(tmp_path: Path) -> None:
    """Twelve inputs all moved the same way: the by-input check confirms it (p = 2/4,096), and no
    input is flagged on its own. Then twenty inputs that each flipped from never failing to
    always failing: confirmed, and every one flagged, so the Answer counts them and names none."""
    root = pair_store(tmp_path / "twelve", [(3, 4, 1, 4)] * 12)
    d = _json(fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", "0.5", "--json"))
    assert d["verdict"] == "different" and d["by_input"]["p"] < 0.05
    out = ok(fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", "0.5")).out
    assert not any("Without " in c for c in caveats(out)), caveats(out)
    assert "come from" not in summary(out)["Answer"]
    flips = pair_store(tmp_path / "flips", [(0, 8, 8, 8)] * 20)
    d = _json(fix_check(flips, "old", "new", ["fail"], *ALL, "--max-mde", "0.5", "--json"))
    assert d["verdict"] == "different" and d["by_input"]["p"] < 0.05 and d["changes"]["flagged"] == 20
    out = ok(fix_check(flips, "old", "new", ["fail"], *ALL, "--max-mde", "0.5")).out
    answer = norm(summary(out)["Answer"])
    assert "input i" not in answer and not any("Without " in c for c in caveats(out)), (answer, caveats(out))


# ---------- the per-input rise column goes ----------

COLUMN = "could not have detected a rise below"


@pytest.mark.parametrize("verb,argv", [
    ("changes", (TAU2, TAU2_A, TAU2_B, TAU2_EVENTS)),
    ("changes", (HUMANEVAL, HE_A, HE_B, HE_EVENTS)),
    ("fix-check", (TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.12")),
    ("fix-check", (TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.20")),
])
def test_tf15_s14_the_rise_column_and_its_key_are_gone(verb, argv) -> None:  # type: ignore[no-untyped-def]
    run = changes if verb == "changes" else fix_check
    out = ok(run(*argv)).out
    assert COLUMN not in norm(out)
    table = [line for line in section(out, "Inputs that changed") if line.startswith("| input |")]
    assert len(table) == 1 and table[0].count("|") == 8, table  # input, old, new, change, p, q, flag
    d = _json(run(*argv, "--json"))
    rows = d["rows"] if verb == "changes" else d["changes"]["rows"]
    assert rows and all("limit_rise" not in r for r in rows)
    assert d["schema"] == f"poisson-trace.{verb}/2"
    # the design sentences that say what a lone input could show stay
    assert "a lone complete flip needs" in norm(out)

