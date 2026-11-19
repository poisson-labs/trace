"""What a first-time reader of the reports could misread, each
pinned so it stays said: a run that declares no repeats is not "0 inputs short" of them, the
limits under a range that decided say they are for planning, two runs sharing a run_salt are
still read unpaired, and too small to tell's next: line points at the two new runs."""

from __future__ import annotations

from conftest import TAU2, TAU2_A, TAU2_B, compare
from fixcheck_support import PILOT, TAU2_EVENTS, fix_check, ok


def test_no_repeats_declared_is_said_so(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from fixcheck_support import pair_store

    root = pair_store(tmp_path, [(1, 4, 2, 4)] * 12)
    out = ok(fix_check(root, "old", "new", ["fail"], "--inputs", "all", "--max-mde", "0.5")).out
    assert "- inputs short of the declared repeats: old no repeats declared · new no repeats declared" in out.splitlines()
    tau2 = ok(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, "--inputs", "all", "--max-mde", "0.10")).out
    assert "- inputs short of the declared repeats: old 0 · new 0" in tau2.splitlines()


def test_the_limits_under_a_range_that_decided_are_for_planning() -> None:
    out = ok(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, "--inputs", "all", "--max-mde", "0.10")).out
    assert "The line below follows the range, which is reliable here; these limits are for planning the next run." in out
    picked = ok(fix_check(TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.20")).out
    assert "follows the range" not in picked


def test_a_shared_run_salt_is_still_unpaired_and_the_next_line_names_new_runs() -> None:
    out = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.3).out
    assert "unpaired, though the runs share a run_salt" in out
    picked = ok(fix_check(TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.20")).out
    assert picked.rstrip("\n").splitlines()[-1].endswith("then poisson-trace fix-check on the two new runs")


def test_compare_says_it_asks_another_question_than_fix_check() -> None:
    from tf15_support import caveats

    said = caveats(compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.3).out)
    assert ("This asks whether failures come sooner or later among tries still going. Whether a version fails "
            "more often overall is fix-check's question, and on the same two runs the two can read differently.") in said
