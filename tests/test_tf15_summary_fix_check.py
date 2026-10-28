"""TF15-P1 to TF15-P12: fix-check's plain parts (spec section 9.5 and 9.5.1, ruled 2026-10-20 with
S1, S2, S12, S14 and S16, and the statistics fixes of section 9.7).

Every report opens with its verdict line, the title on line 3, a ``## Summary`` of four labelled
lines (Compared, Question, Answer, Next), a ``## Before you act on this`` section holding the
caveats, then the statistics. The wording is pinned where section 9.5 writes it (Taylor,
2026-10-20: "Freeze the wording in 9.5 and 9.6 as written"); where 9.5 names a sentence without
writing it, the facts it carries are pinned and not its words. Every number is the report's own
(its text or its --json), restated by the rules of 9.5's "Numbers".

Three sentences 9.5.1 writes carry words frozen tests ban from fix-check's output and from the
source ("worse", "better", "pass", "fixed": test_tr63, test_tr21, test_tr28): they are left out of
these pins until Taylor rules (Session A log, rulings.md); the facts around them are pinned.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import CS, CS_EVENTS, CS_RECORD, CS_REPLAY, TAU2, TAU2_A, TAU2_B, norm
from fixcheck_support import HE_A, HE_B, HE_EVENTS, HUMANEVAL, PILOT, TAU2_EVENTS, fix_check, ok, pair_store
from tf15_support import caveats, first_line, summary

ALL = ("--inputs", "all")
SAME_TARGET = "tau2-airline/gpt-4.1-mini-2025-04-14@v0"
SIDE = (
    "Trace can't tell whether they were run side by side, so anything else that changed between them "
    "(the provider, the model behind the API, the day) may be part of the difference, in either direction."
)


def _out(*argv: str) -> str:
    return ok(fix_check(*argv)).out


def _layout(out: str) -> list[str]:
    """The report's head: the verdict line, a blank, the title, a blank, the summary heading, a
    blank, four labelled lines, a blank, the caveats heading."""
    lines = out.splitlines()
    assert lines[1] == "" and lines[2].startswith("# Poisson Trace · fix check · ") and lines[3] == "", lines[:4]
    assert lines[4] == "## Summary" and lines[5] == "", lines[4:6]
    labels = [line.split(":", 1)[0] for line in lines[6:10]]
    assert labels == ["- Compared", "- Question", "- Answer", "- Next"], lines[6:10]
    assert not any(line.startswith("**") for line in lines[6:10])
    assert lines[10] == "" and lines[11] == "## Before you act on this" and lines[12] == "", lines[10:13]
    return lines


def _next_command(text: str) -> str:
    found = re.findall(r"`([^`]+)`", text)
    assert len(found) == 1, text
    return found[0]


# ---------- the layout, on every verdict ----------


@pytest.mark.parametrize("argv", [
    (TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.12"),
    (TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.20"),
    (HUMANEVAL, HE_A, HE_B, HE_EVENTS, *ALL, "--max-mde", "0.05"),
], ids=["nsd", "too-small", "different"])
def test_tf15_p1_the_head_of_the_report(argv) -> None:  # type: ignore[no-untyped-def]
    lines = _layout(_out(*argv))
    statistics = next(i for i, line in enumerate(lines) if line == "## Runs")
    bullets = [line for line in lines[13:statistics] if line.strip()]
    # a bullet may wrap onto lines that start with spaces
    assert bullets and bullets[0].startswith("- ") and all(line.startswith(("- ", "  ")) for line in bullets), bullets
    assert lines[statistics - 1] == ""


def test_tf15_p2_the_summary_stays_out_of_the_json() -> None:
    """S2 (ruled 2026-10-20): the summary is held privately in this pair; --json's sentence is the
    first line's."""
    argv = (TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.12")
    d = ok(fix_check(*argv, "--json")).json()
    assert not any("summary" in k or "before_you_act" in k for k in d), list(d)
    assert "Compared" not in fix_check(*argv, "--json").out
    assert d["sentence"] == first_line(_out(*argv))[1]


# ---------- no significant difference, decided by a reliable range (ST2) ----------


def test_tf15_p3_no_clear_change_on_a_reliable_range() -> None:
    out = _out(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.12")
    assert first_line(out) == ("no significant difference", "the gap could be chance")
    s = summary(out)
    assert s["Compared"] == (
        "old tau2-airline 2026-09-15 a against new tau2-airline 2026-09-15 b, on the same 50 inputs: 200 "
        "tries of each. A try counts as failed when it ended unsolved."
    )
    assert s["Question"] == (
        "Did the new version fail more or less often than the old? You asked that the run be able to "
        "catch a 12-point drop in how often it fails."
    )
    assert s["Answer"] == (
        "No clear change. The new version failed 112 of 200 tries and the old 110 of 200; the results fit "
        "anything from 6.0 fewer failures per 100 tries to 8.1 more, so a change of 12 points or more either "
        "way does not fit them (if tries of an input are independent)."
    )
    # no lone input can be flagged on this design (it would need 7 tries per input on each side)
    assert s["Next"] == (
        "If a change inside that range matters to you, plan a bigger run with your own harness, then run "
        "`poisson-trace fix-check` on it."
    )
    c = caveats(out)
    assert c[0] == f"They started 10 min apart. {SIDE}"
    assert c[1] == (
        f"Both runs name the same target ({SAME_TARGET}); Trace can't tell what differs between them, only "
        "what you tell it."
    )
    assert c[2] == (
        "These results fit anything from 6.0 fewer failures per 100 tries to 8.1 more (ranges built this way "
        "hold the true difference about 95 times in 100, if tries are independent), which does not include a "
        "12-point drop."
    )
    assert c[3] == (
        "Tries of the same input are counted as separate chances; here they are fairly alike (agreement "
        "0.53, where 0 is no more alike than chance and 1 is identical), and if they are near copies the "
        "answer is more confident than it should be."
    )
    # the rise sentence and the single-input sentence (9.5.1 names them, not their words)
    rest = " ".join(c[4:])
    assert "11-point rise" in rest and "7 tries per input" in rest, c[4:]


# ---------- too small to tell, on the failing-from design ----------


def test_tf15_p4_cant_tell_yet_on_the_patch_example() -> None:
    out = _out(TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.20")
    assert first_line(out) == ("too small to tell", "too few tries to see a 20-point drop")
    s = summary(out)
    assert s["Compared"] == (
        "old tau2-airline 2026-09-15 b against new tau2-airline 2026-09-17 a, on the 6 inputs that failed in "
        "tau2-airline 2026-09-15 a and were run again: 24 tries of the old, 6 of the new. A try counts as "
        "failed when it ended unsolved."
    )
    assert s["Answer"] == (
        "Can't tell yet. The new version failed 3 of 6 tries and the old 18 of 24; by Trace's rough estimate, "
        "these tries would catch a 64-point drop 4 times in 5 and smaller ones less often, and you asked for 20."
    )
    assert s["Next"] == (
        "Run each version 16 times on each of these 6 inputs (or, to avoid picking which to re-run, on all 37 "
        "that failed in tau2-airline 2026-09-15 a; Trace has not sized that) with your own harness, then run "
        "`poisson-trace fix-check` on the two new runs."
    )
    c = caveats(out)
    assert c[0] == f"They started 40 h 50 min apart. {SIDE}"
    assert c[1].startswith(f"Both runs name the same target ({SAME_TARGET})")
    assert c[2].startswith(
        "37 inputs failed in tau2-airline 2026-09-15 a; only the 6 run again on both versions are compared, so "
        "this speaks for those alone."
    ), c[2]
    assert c[3].startswith(
        "On these inputs, picked because they failed in tau2-airline 2026-09-15 a, the old version's run "
        "passed 6 of 24 tries."
    ), c[3]
    assert c[3].endswith(
        "Trace compares the new version's passes with the old version's, allowing for chance."
    ), c[3]
    assert c[4].startswith("These results fit anything from 62 fewer failures per 100 tries to 11 more, but that "
                           "range is only a rough guide here and may be off either way ("), c[4]
    assert c[4].endswith("): don't use it to rule sizes in or out."), c[4]
    assert c[5].startswith("This design is weak at spotting the new version failing more: even if it failed every "
                           "try, Trace would catch that less than 4 times in 5."), c[5]
    assert c[6] == (
        "Tries of the same input are counted as separate chances, and if they are near copies the answer is "
        "more confident than it should be."
    )
    assert c[7] == (
        "The 16 times per input is an estimate from these runs' failure rates (one try per input on one "
        "version, so rough). 55 inputs like these at the present tries would do the same, but only 37 such "
        "inputs exist. Even with good estimates, about half of runs built to it end up a little too small. Make "
        "it a fresh run, judged on its own: don't add tries to these and test again."
    )
    assert re.fullmatch(
        r"If a 64-point drop is the smallest that matters to you \(the old version failed \S+ of tries\), and you "
        r"would have said so before seeing this, `--max-mde 0\.6430` accepts this design as it stands\. That "
        r"changes the label only, not the evidence\.", c[8]), c[8]
    assert len(c) == 9, c


# ---------- different, not confirmed input by input ----------


def test_tf15_p5_slightly_more_failures_resting_on_one_task() -> None:
    out = _out(HUMANEVAL, HE_A, HE_B, HE_EVENTS, *ALL, "--max-mde", "0.05")
    assert first_line(out) == ("different", "the new version failed slightly more often")
    s = summary(out)
    assert s["Compared"] == (
        "old golden-pilot 2026-09-05 a against new golden-pilot 2026-09-05 b, on the same 328 inputs: 10,496 "
        "tries of each. A try counts as failed when it ended crashed or failed_assertion."
    )
    assert s["Answer"] == (
        "Slightly more failures, if tries of an input count as independent (here they are much alike). The new "
        "version failed 1,387 of 10,496 tries and the old 1,338 of 10,496 (0.47 more per 100 tries; the 5 "
        "points you set was for a drop, not a rise); 32 of the net 49 extra failures come from task_id "
        "HumanEval/129 at both settings."
    )
    assert s["Next"] == (
        "Run both versions side by side on these inputs with your own harness, then run `poisson-trace "
        "fix-check` on the two new runs."
    )
    c = caveats(out)
    assert c[0] == f"They started 56 min apart. {SIDE}"
    assert c[2] == (
        "These results fit anything from 0.04 to 0.93 more failures per 100 tries (ranges built this way hold "
        "the true difference about 95 times in 100, if tries are independent), which does not include a 5-point "
        "drop."
    )
    assert c[3] == (
        "Tries of the same input are counted as separate chances; here they are much alike (agreement 0.78, "
        "where 0 is no more alike than chance and 1 is identical), and if they are near copies the answer is "
        "more confident than it should be."
    )
    assert c[4] == (
        "If each input failed equally often under both versions, a gap at least this big, either way, would "
        "turn up about 4 times in 100 (counting tries as independent)."
    )
    assert c[5].startswith(
        "A check of which inputs went up and which went down can't rule out chance on its own (p = 0.127 in "
        "the report)"
    ), c[5]
    assert c[6] == (
        "The whole range is at most 0.93 points, under the 5 points you set (you set it for a drop; this is a "
        "rise), if tries of an input are independent."
    )
    assert c[7] == "Before putting the difference down to the version, run both side by side."
    assert len(c) == 8, c


# ---------- no clear change, but the run says little ----------


def test_tf15_p6_a_weak_design_says_little() -> None:
    out = _out(TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.70")
    assert first_line(out) == (
        "no significant difference", "the gap could be chance, and this run sees only very large changes")
    answer = summary(out)["Answer"]
    assert answer.startswith(
        "No clear change, but this run says little. The new version failed 3 of 6 tries and the old 18 of 24, "
        "a 25-point drop that could be chance; by Trace's rough estimate it would catch only a drop of 64 points "
        "or more 4 times in 5 (the most possible was 75)"), answer
    assert summary(out)["Next"] == (
        "Plan a bigger run with your own harness (more tries per input on both versions), then run "
        "`poisson-trace fix-check` on it."
    )


def test_tf15_p7_no_drop_limit_at_all(tmp_path: Path) -> None:
    root = pair_store(tmp_path, [(1, 1, 0, 1)])
    out = _out(root, "old", "new", ["fail"], *ALL, "--max-mde", "0.5")
    assert first_line(out) == ("too small to tell", "too few tries to see a drop of any size")
    assert summary(out)["Answer"] == (
        "Can't tell. The new version failed 0 of 1 tries and the old 1 of 1, and with these tries Trace can't "
        "reliably catch a drop of any size."
    )


# ---------- the order, and one run replaying the other ----------


def test_tf15_p8_the_new_run_started_first(tmp_path: Path) -> None:
    root = pair_store(tmp_path, [(3, 4, 0, 4)] * 20, old_created="2026-01-01T02:00:00.000000Z",
                      new_created="2026-01-01T01:00:00.000000Z")
    out = _out(root, "old", "new", ["fail"], *ALL, "--max-mde", "0.5")
    assert first_line(out) == (
        "different", "the new version failed less often (the one you gave as new started first: check the order)")
    s = summary(out)
    assert s["Compared"].endswith(
        "Check the order: the one you gave as new started 1 h 0 min before the old one."), s["Compared"]
    assert s["Answer"].startswith("Fewer failures, if the order is right."), s["Answer"]
    assert s["Answer"].endswith(
        "; the one you gave as new started first, so if you swapped them, the newer run failed more."), s["Answer"]
    assert s["Next"] == "Check which run is newer, then run `poisson-trace fix-check` with the older one first."


def test_tf15_p9_one_run_may_replay_the_other() -> None:
    """cs record and its replay: different targets, every input failing as often in both."""
    out = _out(CS, CS_RECORD, CS_REPLAY, CS_EVENTS, *ALL, "--max-mde", "0.25")
    assert first_line(out) == ("too small to tell", "one run may replay the other: check that before adding tries")
    s = summary(out)
    assert s["Compared"].endswith(
        "Their targets differ (cs_agents/record, cs_agents/replay), and every input failed the same number of "
        "times in both: if one replays the other, this is not a comparison of two versions."), s["Compared"]
    assert s["Next"] == (
        "First check whether cs_agents/replay replays cs_agents/record; if it does, compare a real second version "
        "with `poisson-trace fix-check` instead of adding tries."
    )
    assert not any(c.startswith("Both runs name the same target") for c in caveats(out))


# ---------- tries with no outcome ----------


def test_tf15_p10_tries_with_no_outcome(tmp_path: Path) -> None:
    """Old: 4 inputs of 4 tries, 2 of them failing; new: the same, with 6 tries of input i0 with no
    outcome. The gap in failures (0) is no bigger than the gap in tries with no outcome (6)."""
    from fixcheck_support import Obs, arm_rows, build_run

    tab = [(2, 4, 2, 4)] * 4
    build_run(tmp_path, "old", arm_rows(tab, "old"), created_at="2026-01-01T00:00:00.000000Z")
    rows = arm_rows(tab, "new") + [Obs("i0", None, "infra: lost", replicate_index=10 + j) for j in range(6)]
    build_run(tmp_path, "new", rows, created_at="2026-01-01T01:00:00.000000Z")
    out = _out(tmp_path, "old", "new", ["fail"], *ALL, "--max-mde", "0.3")
    assert first_line(out)[0] == "too small to tell", out.splitlines()[0]
    c = [x for x in caveats(out) if "had no outcome" in x]
    assert len(c) == 1, caveats(out)
    assert c[0].startswith("0 tries of the old and 6 of the new had no outcome"), c[0]
    assert "The difference in them (6) is larger than the whole gap in failures (0)." in c[0], c[0]
    assert summary(out)["Answer"].endswith("; the gap is no bigger than the gap in tries with no outcome.")
    assert summary(out)["Next"].startswith("First find out why the new version has more tries with no outcome; then run")


# ---------- the last next: line is the summary's Next (S14) ----------


@pytest.mark.parametrize("argv", [
    (TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.12"),
    (HUMANEVAL, HE_A, HE_B, HE_EVENTS, *ALL, "--max-mde", "0.05"),
    (CS, CS_RECORD, CS_REPLAY, CS_EVENTS, *ALL, "--max-mde", "0.25"),
], ids=["nsd", "different", "replay"])
def test_tf15_p11_the_last_next_line_is_the_summarys_command(argv) -> None:  # type: ignore[no-untyped-def]
    out = _out(*argv)
    last = out.rstrip("\n").splitlines()[-1]
    assert last.startswith("next: "), last
    command = _next_command(summary(out)["Next"])
    assert norm(last[len("next: "):]).startswith(norm(re.sub(r" --max-mde(-hr)? X\b", "", command))), (last, command)


def test_tf15_p12_the_too_small_next_line_names_the_tries_the_summary_names() -> None:
    out = _out(TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.20")
    last = out.rstrip("\n").splitlines()[-1]
    assert last.startswith("next: ") and "16" in last and "poisson-trace fix-check" in last, last


def test_tf15_p11_a_confirmed_difference_points_at_changes(tmp_path: Path) -> None:
    """The case where S14 binds: the summary's Next is `poisson-trace changes old new` and the last
    next: line is that command (with the flags the report was given)."""
    root = pair_store(tmp_path, [(3, 4, 0, 4)] * 20)
    out = _out(root, "old", "new", ["fail"], *ALL, "--max-mde", "0.5")
    told = summary(out)["Next"]
    assert told.startswith("See which inputs moved: `poisson-trace changes ") and told.endswith("`."), told
    last = out.rstrip("\n").splitlines()[-1]
    assert last.startswith("next: " + _next_command(told)), (last, told)


def test_tf15_p29_one_more_decimal_where_rounding_would_meet_the_size_asked() -> None:
    """9.5's Numbers: a 64.29-point limit against an asked 64 prints 64.3, not 64."""
    out = _out(TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.64")
    answer = summary(out)["Answer"]
    assert "a 64.3-point drop 4 times in 5" in answer and "you asked for 64" in answer, answer
