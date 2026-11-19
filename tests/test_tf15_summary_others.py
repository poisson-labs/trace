"""TF15-P13 to TF15-P28: the plain parts of compare, where, changes and the import, with what
the statistics change in what they say, and three smaller fixes to the import and where.

As in test_tf15_summary_fix_check: the wording is pinned where it is fixed; where only what a
sentence must say is fixed, the facts it carries are pinned. Every number is the
report's own. Commands in the four lines are code spans; a Next command may carry the store and
events flags the report was given (the summary's own wording leaves them out), so it is pinned up
to them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import (
    CS, CS_EVENTS, CS_RECORD, CS_REPLAY, TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, compare, deaths_rows, norm, where,
)
from fixcheck_support import HE_A, HE_B, HE_EVENTS, HUMANEVAL, changes
from tf15_support import caveats, first_line, section, summary

SIDE = (
    "Trace can't tell whether they were run side by side, so anything else that changed between them "
    "(the provider, the model behind the API, the day) may be part of the difference, in either direction."
)
TAU2_NAMES = '"tau2-airline 2026-09-15 a" "tau2-airline 2026-09-15 b"'


def _ok(result):  # type: ignore[no-untyped-def]
    assert result.code == 0, result.text
    return result.out


def _head(out: str, title: str, labels: list[str]) -> None:
    lines = out.splitlines()
    assert lines[1] == "" and lines[2].startswith(f"# Poisson Trace · {title}") and lines[3] == "", lines[:4]
    assert lines[4] == "## Summary" and lines[5] == "", lines[4:6]
    assert [line.split(":", 1)[0] for line in lines[6:10]] == [f"- {label}" for label in labels], lines[6:10]


def _command(text: str) -> str:
    found = re.findall(r"`([^`]+)`", text)
    assert len(found) == 1, text
    return found[0]


def _last_next(out: str) -> str:
    last = out.rstrip("\n").splitlines()[-1]
    assert last.startswith("next: "), last
    return last[len("next: "):]


def _runnable(command: str) -> str:
    """The last next: line is the summary's Next, under the frozen rule that a next: line runs as
    written (TF1-17, TF2-16, TF2-26): the next: line is the summary's command without its
    placeholder ceiling, the one thing a next command may lack."""
    return re.sub(r" --max-mde(-hr)? X\b", "", command)


# ---------- compare ----------


def test_tf15_p13_compare_cant_tell_yet() -> None:
    out = _ok(compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.3))
    _head(out, "compare · ", ["Compared", "Question", "Answer", "Next"])
    s = summary(out)
    assert s["Compared"] == (
        "before tau2-airline 2026-09-15 a against after tau2-airline 2026-09-15 b, on the same 50 inputs: "
        "200 tries each. A try counts as failed when it ended unsolved."
    )
    assert s["Question"] == (
        "Step by step, among tries still going, did the after version fail more or less often? You asked to "
        "see that rate change 1.3-fold, either way."
    )
    assert s["Answer"].startswith(
        "Can't tell yet. 112 of 200 tries failed after and 110 of 200 before; by Trace's estimate these tries "
        "would catch a 1.60-fold change in that rate 4 times in 5, and you asked about 1.3-fold"), s["Answer"]
    # the Answer gives the estimate
    assert "after against before, the per-step failure rate is 1.11 times as high (0.80 to 1.55)" in s["Answer"]
    assert s["Next"] == (
        "Run each version 11 times on each of these 50 inputs with your own harness, then run "
        "`poisson-trace compare` on the two new runs."
    )
    c = caveats(out)
    assert c[0] == f"They started 10 min apart. {SIDE}"
    assert c[1] == (
        "Both runs name the same target (tau2-airline/gpt-4.1-mini-2025-04-14@v0); Trace can't tell what "
        "differs between them, only what you tell it."
    )
    assert (
        "A try that finished without failing counts as still going up to its last step, so this mixes how "
        "often and how early tries fail. Tries of the same input are counted as separate chances; if they are "
        "near copies, this is more confident than it should be."
    ) in c
    assert (
        "A 1.60-fold change means the per-step failure rate among tries still going rises 1.60 times, or "
        "falls to 0.62 of what it was; it is not the ratio of the failure counts."
    ) in c
    # the clause naming a target number of failures goes
    assert (
        "The 11 times per input is an estimate from these runs' failure rates. Even with good estimates, about "
        "half of runs built to it end up a little too small. Make it a fresh run, judged on its own."
    ) in c
    accept = [x for x in c if "`--max-mde-hr 1.604`" in x]
    assert len(accept) == 1 and accept[0].endswith("That changes the label only, not the evidence."), c
    # the report prints the estimate now, so the summary no longer says it prints none
    assert "prints no fold-change estimate" not in norm(out)


def test_tf15_p14_compare_no_clear_change() -> None:
    out = _ok(compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.604))
    s = summary(out)
    assert s["Answer"].startswith(
        "No clear change. 112 of 200 tries failed after and 110 of 200 before; by Trace's estimate these tries "
        "would catch a 1.60-fold change in that rate 4 times in 5, so a smaller change could be hiding"), s["Answer"]
    assert s["Next"].startswith(f"Compare how often each version fails overall: `poisson-trace fix-check {TAU2_NAMES}"), s["Next"]
    assert s["Next"].endswith("--inputs all --max-mde X`, choosing X before you look."), s["Next"]
    assert _last_next(out) == _runnable(_command(s["Next"]))  # the summary's Next


def test_tf15_p15_compare_different(two_run_store) -> None:  # type: ignore[no-untyped-def]
    root = two_run_store(deaths_rows(list(range(1, 21))), deaths_rows(list(range(21, 41))))
    out = _ok(compare(root, "a", "b", ["fail"], 100.0))
    s = summary(out)
    assert s["Answer"].startswith(
        "Failures come later. Each version failed 20 of 20 tries; if each input failed equally often under both "
        "versions, a gap at least this big, either way, would turn up less than once in 1,000 (counting tries as "
        "independent)"), s["Answer"]
    assert "Before putting the difference down to the version, run both versions side by side." in caveats(out)


# ---------- where ----------


def test_tf15_p16_where_on_a_run_counted_in_turns() -> None:
    out = _ok(where(CS, CS_RECORD, CS_EVENTS))
    _head(out, "where runs die · ", ["Read", "Question", "Answer", "Next"])
    s = summary(out)
    assert s["Read"] == "cs_agents 2026-09-25 a (cs_agents/record): 24 tries, each placed at the turn where it stopped."
    assert s["Question"] == "At which turn do failing tries stop?"
    assert s["Answer"] == (
        "7 of 24 failed. Their last steps: 4 at a model call and 3 at an agent step (not necessarily the cause), "
        "between turn 24 and turn 58."
    )
    # no run of the same target started before this one
    assert s["Next"].startswith(
        'Before blaming that step, see where passing tries stop too: `poisson-trace where "cs_agents 2026-09-25 a"'), s["Next"]
    assert "--event PASSING-OUTCOME`, naming an outcome other than " in s["Next"], s["Next"]
    assert s["Next"].endswith("(init lists a store's outcomes)."), s["Next"]
    # the summary's command names an outcome to choose; the next: line stays one that runs (TF1-11)
    assert _last_next(out) == "poisson-trace fix-check --help"
    c = caveats(out)
    assert c[0] == (
        "The turn is where a try stopped, not where it went wrong; the kind of step is that of its last turn, "
        "not the cause. Check what passing tries end on before reading it as one part's fault."
    )
    assert c[-1] == "One run shows where tries stop, not whether a change moved anything."
    # the caveat about the curve counting finished tries goes
    assert not any("counts finished tries as if they might still have failed" in x for x in c)


def test_tf15_p17_where_with_a_run_before_it() -> None:
    out = _ok(where(TAU2, TAU2_B, TAU2_EVENTS))
    assert first_line(out) == (
        "ok", "112 of 200 tries failed; each one's last step was a model call (not necessarily the cause)")
    s = summary(out)
    assert s["Answer"] == (
        "112 of 200 failed. Each failure's last step was a model call (not necessarily the cause), between step 9 "
        "and step 40."
    )
    assert s["Next"].startswith(f"See whether a change moved this: `poisson-trace compare {TAU2_NAMES}"), s["Next"]
    assert "--max-mde-hr X`" in s["Next"], s["Next"]
    assert _last_next(out) == _runnable(_command(s["Next"]))  # the summary's Next


def test_tf15_p18_where_with_no_failure(two_run_store) -> None:  # type: ignore[no-untyped-def]
    rows = deaths_rows([2, 3, 4, 5], died=False) + deaths_rows([3], died=True, kind="tool", start_rep=10)
    root = two_run_store(rows, rows)
    out = _ok(where(root, "a", ["fail"]))
    assert summary(out)["Answer"].startswith("1 of 5 failed.")
    none = two_run_store(deaths_rows([2, 3, 4, 5], died=False) + deaths_rows([4, 4], start_rep=5),
                         deaths_rows([2, 3], died=False), cap=4)
    out = _ok(where(none, "a", ["fail"]))
    assert first_line(out) == ("ok", "none of 6 tries failed (fail)")
    assert summary(out)["Answer"] == "None failed. All 6 tries finished without fail."


def test_tf15_p19_where_on_a_run_with_no_traces(tmp_path: Path) -> None:
    from tf1_support import import_he

    store = tmp_path / "store"
    assert import_he(store, "he-a").code == 0
    assert import_he(store, "he-b", "b").code == 0
    out = _ok(where(store, "he-b", ["missed"]))
    assert first_line(out) == ("ok", "this run has no traces, so there is no step to place its failures on")
    s = summary(out)
    assert s["Read"] == "he-b (import/deepeval): 10,496 tries."
    assert s["Answer"].startswith("Nothing to place. This run has no traces (") and s["Answer"].endswith(
        "), so its tries carry no steps."), s["Answer"]
    assert s["Next"].startswith("Compare its failures with another version's: `poisson-trace fix-check he-a he-b"), s["Next"]
    assert s["Next"].endswith("--inputs all --max-mde X`, choosing X before you look."), s["Next"]
    assert "## Before you act on this" not in out.splitlines()


# ---------- changes ----------


def test_tf15_p20_changes_with_two_inputs_flagged() -> None:
    out = _ok(changes(HUMANEVAL, HE_A, HE_B, HE_EVENTS))
    assert first_line(out) == (
        "ok", "2 of 328 inputs stand out: task_id HumanEval/129 at temperature 0.7 failed more in B; task_id "
        "HumanEval/129 at temperature 0.0 failed more in B")
    _head(out, "changes · ", ["Compared", "Question", "Answer", "Next"])
    s = summary(out)
    assert s["Compared"] == (
        "A golden-pilot 2026-09-05 a against B golden-pilot 2026-09-05 b, input by input, on 328 inputs: 32 per input."
    )
    assert s["Question"] == "Which single inputs failed more or less often in B than in A?"
    assert s["Answer"].startswith(
        "2 inputs stand out. In B, task_id HumanEval/129 at temperature 0.7 failed 32 of 32 tries against 12 of "
        "32 in A; task_id HumanEval/129 at temperature 0.0"), s["Answer"]
    assert s["Next"].startswith(
        'See whether the versions differ overall: `poisson-trace fix-check "golden-pilot 2026-09-05 a" '
        '"golden-pilot 2026-09-05 b"'), s["Next"]
    assert s["Next"].endswith("--inputs all --max-mde X`, choosing X before you look."), s["Next"]
    assert _last_next(out) == _runnable(_command(s["Next"]))  # the summary's Next
    c = caveats(out)
    assert c[0] == f"They started 56 min apart. {SIDE}"
    assert "Both are task_id HumanEval/129 at different settings, which may be one fault rather than 2." in c
    assert (
        "Trace's rule keeps false alarms to at most about 1 in 20 of flagged inputs on average, if tries of an "
        "input are independent; a flag says the runs differ on that input, not why. An input with no flag may "
        "still have changed."
    ) in c


def test_tf15_p21_changes_where_no_lone_input_could_stand_out() -> None:
    out = _ok(changes(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS))
    assert first_line(out) == ("ok", "0 of 50 inputs stand out; on this design, no single input could on its own")
    assert summary(out)["Answer"] == (
        "None stood out, and none could on its own on this design. With 4 tries per input, even one input going "
        "from never failing to always failing couldn't stand out among 50."
    )


# ---------- the import ----------


def _table_import(tmp_path: Path, run: str = "ha"):  # type: ignore[no-untyped-def]
    from tf0_support import trace_import

    from conftest import FIXTURES

    return trace_import([
        "table", str(FIXTURES / "ingest" / "table" / "humaneval-a.csv"), "--store", str(tmp_path / "st"),
        "--run", run, "--case-column", "case", "--outcome-column", "outcome", "--failed", "failed_assertion",
        "--failed", "crashed",
    ])


def test_tf15_p22_the_import_of_a_table(tmp_path: Path) -> None:
    result = _table_import(tmp_path)
    assert result.code == 0, result.text
    out = result.out
    _head(out, "import · ha", ["Wrote", "Failures", "Compared", "Next"])
    s = summary(out)
    assert s["Wrote"] == f"ha into {tmp_path / 'st'}, from humaneval-a.csv (table): 10,496 tries on 328 inputs."
    assert s["Failures"] == (
        '1,338 failed and 9,158 passed. A try counts as failed when its outcome column reads "failed_assertion" '
        'or "crashed"; any other value counts as a pass.'
    )
    assert s["Compared"] == "Nothing yet. One import is one version."
    assert s["Next"].startswith("Import the other version's file the same way: `poisson-trace import table OTHER.csv "), s["Next"]
    command = _command(s["Next"])
    for words in (f"--store {tmp_path / 'st'}", "--run OTHER", "--case-column case", "--outcome-column outcome", "--failed failed_assertion", "--failed crashed"):
        assert words in command, command
    c = caveats(out)
    assert "Every other value of the outcome column counts as a pass." in c
    assert (
        "Its start time is when its file was written or copied, so latest and previous won't order it: name the "
        "runs when you compare them, the older first."
    ) in c
    assert c[-1] == (
        "When you compare, choose the smallest drop that matters to you (--max-mde) before you look at any "
        "results; Trace then says whether these tries could catch it."
    )
    lines = out.splitlines()
    assert "## What was written" in lines
    assert lines.index("## What was written") > lines.index("## Before you act on this")


def test_tf15_p23_the_import_of_junit_skips_and_its_start(tmp_path: Path) -> None:
    from tf0_support import trace_import

    from conftest import FIXTURES

    result = trace_import(["junit", str(FIXTURES / "ingest" / "junit" / "humaneval-a.xml"), "--store",
                           str(tmp_path / "st"), "--run", "ja"])
    assert result.code == 0, result.text
    c = caveats(result.out)
    assert "Its start time is the report's earliest suite timestamp." in c
    assert "A skipped test has no outcome and is left out." in c
    assert summary(result.out)["Failures"].endswith("A try counts as failed when its test failed or errored."), summary(result.out)


# ---------- the import's words, where in turns, the first line and the JSON ----------


def test_tf15_p24_the_import_line_says_passed_and_failed(tmp_path: Path) -> None:
    """The import's first line uses the summary's words, passed and failed, not met and missed."""
    result = _table_import(tmp_path)
    word, sentence = first_line(result.out)
    assert word == "ok"
    assert not re.search(r"\b(met|missed)\b", sentence), sentence
    assert re.search(r"\b1,338 failed\b|\bfailed 1,338\b", sentence), sentence
    assert re.search(r"\b9,158 passed\b|\bpassed 9,158\b", sentence), sentence


def test_tf15_p26_where_on_a_run_counted_in_turns_says_turn() -> None:
    out = _ok(where(CS, CS_RECORD, CS_EVENTS))
    body = out.split("\n## Run\n", 1)[1]
    assert "median turn of the failed tries: 35" in body, body
    assert "| turn |" in body
    assert "median step" not in body and "| step |" not in body
    tau2 = _ok(where(TAU2, TAU2_A, TAU2_EVENTS)).split("\n## Run\n", 1)[1]
    assert "median step of the failed tries: 20" in tau2 and "| step |" in tau2


# ---------- the plain first lines that remain ----------


def test_tf15_p27_the_first_line_and_the_json_sentence_agree() -> None:
    for result, js in (
        (compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.3), compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.3, "--json")),
        (where(CS, CS_RECORD, CS_EVENTS), where(CS, CS_RECORD, CS_EVENTS, "--json")),
        (changes(HUMANEVAL, HE_A, HE_B, HE_EVENTS), changes(HUMANEVAL, HE_A, HE_B, HE_EVENTS, "--json")),
    ):
        d = js.json()
        assert d["sentence"] == first_line(result.out)[1]
        assert not any("summary" in k or "before_you_act" in k for k in d)


@pytest.mark.parametrize("verb", ["compare", "where", "changes"])
def test_tf15_p28_no_summary_line_opens_bold(verb: str) -> None:
    run = {
        "compare": lambda: compare(CS, CS_RECORD, CS_REPLAY, CS_EVENTS, 2.0),
        "where": lambda: where(TAU2, TAU2_A, TAU2_EVENTS),
        "changes": lambda: changes(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS),
    }[verb]
    lines = section(_ok(run()), "Summary")
    assert len(lines) == 4 and not any(line.startswith("**") or line.startswith("- **") for line in lines), lines


def test_tf15_p30_the_import_of_deepeval_and_ragas(tmp_path: Path) -> None:
    import gzip

    from tf0_support import trace_import

    from conftest import FIXTURES

    (tmp_path / "results").mkdir()
    saved = tmp_path / "results" / "test_run_20260905_185407.json"
    saved.write_bytes(gzip.decompress((FIXTURES / "ingest" / "deepeval" / "humaneval-a.json.gz").read_bytes()))
    result = trace_import(["deepeval", str(saved), "--store", str(tmp_path / "st"), "--run", "d", "--metric",
                           "Tests Passed", "--cut", "recorded", "--case", "name"])
    assert result.code == 0, result.text
    s = summary(result.out)
    assert s["Failures"].endswith("A try counts as failed when DeepEval marked its Tests Passed metric as not passed."), s
    zone = [c for c in caveats(result.out) if c.startswith("Its start time is taken from the file's name")]
    assert len(zone) == 1 and re.search(
        r"read as if in this machine's zone, which is a guess \([^)]+\); if the name was written in another zone, the "
        r"start is off by the difference\.$", zone[0]), zone
    result = trace_import(["ragas", str(FIXTURES / "ingest" / "ragas" / "rag-base.jsonl"), "--store", str(tmp_path / "st"),
                           "--run", "r", "--metric", "faithfulness", "--cut", "0.5", "--below", "--case-column", "case"])
    assert result.code == 0, result.text
    assert summary(result.out)["Failures"].endswith("A try counts as failed when its faithfulness score is below 0.5."), result.out
