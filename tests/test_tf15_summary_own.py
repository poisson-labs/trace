"""What the plain parts at the head of a report say where the frozen tests leave it open and
a wrong build would still pass them.

- At another --alpha the range's caveat names the range's own level, as the bold line does.
- A design that can see the size asked is not called one that "sees only very large changes",
  though a rough range still makes it say little.
- where's Next toward compare asks for a ceiling on the per-step failure rate, which the
  share's example "(0.10 is 10 points)" does not fit.
- compare on a run and what may be its replay says to check that first.
"""

from __future__ import annotations

from pathlib import Path

from conftest import CS, CS_EVENTS, CS_RECORD, CS_REPLAY, TAU2, TAU2_B, TAU2_EVENTS, compare, where
from fixcheck_support import fix_check, ok, pair_store
from tf15_support import caveats, first_line, summary

# 15 inputs, 14 vary; reliable; at --alpha 0.1 the 90% range lies inside plus or minus 24 points
POWER_SAYS_YES = [
    (1, 4, 1, 4), (3, 4, 1, 4), (0, 4, 2, 4), (0, 4, 0, 4), (1, 4, 2, 4), (3, 4, 3, 4), (3, 4, 3, 4),
    (2, 4, 1, 4), (0, 4, 3, 4), (2, 4, 4, 4), (0, 4, 1, 4), (0, 4, 2, 4), (1, 4, 0, 4), (2, 4, 2, 4),
    (3, 4, 2, 4),
]
# 9 inputs vary, so the range is rough and the drop limit (34.2 points) reads the verdict; the
# rise limit is 31.9 points and the old version failed 64% of tries, so a 35-point drop is seen
NINE_VARY = [
    (4, 4, 3, 4), (0, 4, 1, 4), (3, 4, 1, 4), (4, 4, 1, 4), (3, 4, 2, 4), (3, 4, 3, 4), (2, 4, 2, 4),
    (2, 4, 2, 4), (2, 4, 2, 4),
]


def test_the_range_caveat_names_the_level_the_range_was_built_at(tmp_path: Path) -> None:
    root = pair_store(tmp_path, POWER_SAYS_YES)
    at_90 = [c for c in caveats(ok(fix_check(root, "old", "new", ["fail"], "--inputs", "all", "--max-mde", "0.24", "--alpha", "0.1")).out)
             if c.startswith("These results fit")]
    assert len(at_90) == 1 and "about 90 times in 100" in at_90[0] and "95" not in at_90[0], at_90
    at_95 = [c for c in caveats(ok(fix_check(root, "old", "new", ["fail"], "--inputs", "all", "--max-mde", "0.24")).out)
             if c.startswith("These results fit")]
    assert len(at_95) == 1 and "about 95 times in 100" in at_95[0], at_95


def test_a_design_that_sees_the_size_asked_is_not_called_one_that_sees_only_very_large_changes(tmp_path: Path) -> None:
    out = ok(fix_check(pair_store(tmp_path, NINE_VARY), "old", "new", ["fail"], "--inputs", "all", "--max-mde", "0.35")).out
    word, sentence = first_line(out)
    assert word == "no significant difference", out.splitlines()[0]
    assert "very large" not in sentence and sentence.startswith("the gap could be chance"), sentence
    answer = summary(out)["Answer"]
    assert answer.startswith("No clear change, but this run says little. ") and "only a drop" not in answer, answer
    assert "a drop of 34 points or more 4 times in 5" in answer, answer


def test_wheres_next_toward_compare_gives_no_share_as_its_example() -> None:
    told = summary(ok(where(TAU2, TAU2_B, TAU2_EVENTS)).out)["Next"]
    assert told.endswith("--max-mde-hr X`, choosing X before you look."), told
    assert "0.10 is 10 points" not in told, told


def test_compare_on_a_possible_replay_says_to_check_that_first() -> None:
    result = compare(CS, CS_RECORD, CS_REPLAY, CS_EVENTS, 2.0)
    assert result.code == 0, result.text
    s = summary(result.out)
    assert s["Compared"].endswith(
        "Their targets differ (cs_agents/record, cs_agents/replay), and every input failed the same number of "
        "times in both: if one replays the other, this is not a comparison of two versions."), s["Compared"]
    assert s["Next"].startswith("First check whether cs_agents/replay replays cs_agents/record; if it does, "), s["Next"]
    assert not any(c.startswith("Both runs name the same target") for c in caveats(result.out))


def test_inputs_that_share_no_key_are_named_as_a_list() -> None:
    from poisson_trace.summary import inputs_named

    assert inputs_named([{"case": "a"}, {"case": "b"}]) == "case a and case b"
    assert inputs_named([{"case": "a"}, {"case": "b"}, {"case": "c"}]) == "case a, case b and case c"
    assert inputs_named([{"case": "a"}]) == "case a"
