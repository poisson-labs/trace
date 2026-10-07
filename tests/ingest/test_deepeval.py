"""ID1 to ID9: DeepEval's files, as DeepEval 4.2.6 writes them, built in the test (lane H)."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from proofload.store import Store
from support import (
    IMPORT_MAIN, by_case, case, conversation, deepeval_argv, holds, metric, read_rows, refused,
    run_doc, run_import, run_python, save, scored, tree,
)
from support import scalars

STARTED = ["--started", "2026-09-05T18:54:07Z"]


def _nothing_under(root: Path) -> None:
    assert not root.exists() or not any(root.iterdir()), tree(root)


def _frame(root: Path, run: str) -> pd.DataFrame:
    return Store(root).read(run, meta=True, trace="none").drop(columns=["run_id"])


def _ok(argv: list[str]) -> None:
    r = run_import(argv)
    assert r.code == 0, r.text


# ---------- ID1 ----------


def _mixed_doc() -> dict[str, Any]:
    return run_doc(
        [*scored("a", [0.9, 0.1]), *scored("b", [None, 0.6], start=2)],
        [conversation("c", [metric("Score", 0.3)], order=4)],
    )


def test_id1_the_test_run_and_the_wrapped_test_run_give_equal_rows(tmp_path: Path) -> None:
    doc = _mixed_doc()
    shapes = {
        "plain": save(tmp_path / "test_run.json", doc),
        "wrapped": save(tmp_path / ".latest_test_run.json", {"testRunData": doc}),
        "full": save(tmp_path / ".latest_run_full.json", doc),
        "gzipped": save(tmp_path / "test_run.json.gz", doc, gz=True),
    }
    frames = {}
    for shape, f in shapes.items():
        root = tmp_path / f"store-{shape}"
        _ok(deepeval_argv(f, root, "v1", extra=STARTED))
        frames[shape] = _frame(root, "v1")
    assert len(frames["plain"]) == 5
    for shape in ("wrapped", "full", "gzipped"):
        pd.testing.assert_frame_equal(frames["plain"], frames[shape], check_exact=True)


def test_id1_a_file_holding_only_a_link_is_refused(tmp_path: Path) -> None:
    f = save(tmp_path / ".latest_test_run.json", {"testRunLink": "https://app.confident-ai.com/project/p/evaluation/test-runs/r"})
    root = tmp_path / "store"
    refused(run_import(deepeval_argv(f, root, "v1")))
    refused(run_import(deepeval_argv(f, root, "v1", cut=("recorded",))))
    _nothing_under(root)
    save(f, {"testRunData": _mixed_doc()})
    _ok(deepeval_argv(f, root, "v1"))


# ---------- ID2 ----------


def test_id2_one_row_per_test_case_single_turn_then_conversational_then_the_next_file(tmp_path: Path) -> None:
    first = {
        # the conversational list first in the file, and every `order` out of step with the list
        "conversationalTestCases": [
            conversation("q1", [metric("Score", 0.1)], order=0),
            conversation("q2", [metric("Score", 0.3)], order=1),
        ],
        "testCases": [
            case("q1", [metric("Score", 0.2)], order=3),
            case("q2", [metric("Score", 0.9)], order=0),
            case("q1", [metric("Score", 0.8)], order=2),
            case("other", [metric("Other", 0.5)], order=5),
            case("q1", [metric("Score", 0.4)], order=1),
        ],
    }
    second = run_doc([case("q1", [metric("Score", 0.6)], order=0), case("q3", [metric("Other", 0.1)], order=1)])
    f1, f2 = save(tmp_path / "one.json", first), save(tmp_path / "two.json", second)
    root = tmp_path / "store"
    r = run_import(deepeval_argv([f1, f2], root, "v1", extra=STARTED))
    assert r.code == 0, r.text
    rows = read_rows(root, "v1")
    scores = {k: [x["score"] for x in v] for k, v in by_case(rows, "import").items()}
    assert scores == {"q1": [0.2, 0.8, 0.4, 0.1, 0.6], "q2": [0.9, 0.3]}
    line = next(line for line in r.out.splitlines() if "without this metric" in line.lower())
    assert re.search(r"(?<![\d.])2(?![\d.])", line), line


# ---------- ID3 ----------


def test_id3_recorded_follows_that_metrics_success_and_nothing_else(tmp_path: Path) -> None:
    """Sole catch for a reader that uses the test case's own success."""
    doc = run_doc([
        # the test case failed because of the other metric; this one succeeded
        case("t1", [metric("Other", 0.1, success=False), metric("Score", 0.9, success=True)], order=0, success=False),
        # the test case succeeded as a whole; this metric did not
        case("t2", [metric("Score", 0.9, success=False), metric("Other", 0.9, success=True)], order=1, success=True),
        # DeepEval's decision stands against the score (a metric where lower is better)
        case("t3", [metric("Score", 0.05, threshold=0.5, success=True)], order=2, success=True),
        case("t4", [metric("Score", 0.95, threshold=0.5, success=False)], order=3, success=False),
    ])
    f = save(tmp_path / "results.json", doc)
    root = tmp_path / "store"
    _ok(deepeval_argv(f, root, "v1", cut=("recorded",)))
    got = {k: v for k, v in by_case(read_rows(root, "v1")).items()}
    assert got == {"t1": ["met"], "t2": ["missed"], "t3": ["met"], "t4": ["missed"]}


def test_id3_recorded_thresholds_that_differ_are_each_printed_with_their_count(tmp_path: Path) -> None:
    doc = run_doc([
        *[case(f"a{i}", [metric("Score", 0.9, threshold=0.25)], order=i) for i in range(3)],
        *[case(f"b{i}", [metric("Score", 0.9, threshold=0.75)], order=3 + i) for i in range(2)],
    ])
    f = save(tmp_path / "results.json", doc)
    root = tmp_path / "store"
    r = run_import(deepeval_argv(f, root, "v1", cut=("recorded",)))
    assert r.code == 0, r.text
    for threshold, count in (("0.25", 3), ("0.75", 2)):
        assert any(threshold in line and re.search(rf"(?<![\d.]){count}(?![\d.])", line.replace(threshold, ""))
                   for line in r.out.splitlines()), (threshold, count, r.out)


# ---------- ID4 ----------


def test_id4_a_declared_cut_follows_cut_and_not_the_recorded_decision(tmp_path: Path) -> None:
    doc = run_doc([
        case("s1", [metric("Score", 0.3, threshold=0.2, success=True)], order=0),
        case("s2", [metric("Score", 0.8, threshold=0.9, success=False)], order=1),
        case("s3", [metric("Score", 0.5, threshold=0.9, success=False)], order=2),
        case("s4", [metric("Score", 0.49999, threshold=0.1, success=True)], order=3),
    ])
    f = save(tmp_path / "results.json", doc)
    root = tmp_path / "store"
    _ok(deepeval_argv(f, root, "below", cut=("0.5", "--below")))
    _ok(deepeval_argv(f, root, "above", cut=("0.5", "--above")))
    below = {k: v[0] for k, v in by_case(read_rows(root, "below")).items()}
    above = {k: v[0] for k, v in by_case(read_rows(root, "above")).items()}
    assert below == {"s1": "missed", "s2": "met", "s3": "met", "s4": "missed"}
    assert above == {"s1": "met", "s2": "missed", "s3": "met", "s4": "met"}


@pytest.mark.parametrize("cut,side,scores,want", [
    ("0.7", "--below", [0.0, 0.69, 0.7, 0.71, 1.0], ["missed", "missed", "met", "met", "met"]),
    ("0.3", "--above", [0.0, 0.29, 0.3, 0.31, 1.0], ["met", "met", "met", "missed", "missed"]),
    ("-1", "--below", [-2.0, -1.0, 0.0], ["missed", "met", "met"]),
    ("7", "--above", [6.0, 7.0, 8.5], ["met", "met", "missed"]),
])
def test_id4_every_score_against_a_declared_cut(tmp_path: Path, cut: str, side: str, scores: list[float], want: list[str]) -> None:
    f = save(tmp_path / "results.json", run_doc(scored("x", scores)))
    root = tmp_path / "store"
    _ok(deepeval_argv(f, root, "v1", cut=(cut, side)))
    assert by_case(read_rows(root, "v1")) == {"x": want}


# ---------- ID5 ----------


@pytest.mark.parametrize("cut", [("recorded",), ("0.5", "--below"), ("0.5", "--above")])
def test_id5_a_metric_with_no_score_or_with_an_error_has_no_outcome(tmp_path: Path, cut: tuple[str, ...]) -> None:
    raised = metric("Score", None, error="RuntimeError: raised")
    both = metric("Score", 0.9, success=True)
    both["error"] = "TimeoutError: the judge did not answer"
    bare = {"name": "Score", "threshold": 0.5, "success": False, "strictMode": False}
    doc = run_doc([
        case("ok", [metric("Score", 0.9)], order=0),
        case("raised", [raised], order=1),
        case("both", [both], order=2),
        case("bare", [bare], order=3),
    ])
    f = save(tmp_path / "results.json", doc)
    root = tmp_path / "store"
    _ok(deepeval_argv(f, root, "v1", cut=cut))
    rows = {r["case"]: (r["outcome"], r["error"]) for r in read_rows(root, "v1")}
    assert rows["raised"] == rows["both"] == rows["bare"] == (None, "no score")
    assert rows["ok"][0] in ("met", "missed") and rows["ok"][1] is None
    tally = Store(root).tally("v1")
    assert (tally.rows, tally.no_outcome) == (4, 3)


# ---------- ID6 ----------


def test_id6_case_name_input_and_position(tmp_path: Path) -> None:
    long_name = "a test case named at length, " * 4
    long_input = "What is the capital of the country whose flag has a maple leaf on it, and why? " * 2
    other_input = "line one of a question\nline two of the same question"
    doc = run_doc([
        case("HumanEval/129@0.7", [metric("Score", 0.9)], order=4, input=long_input),
        case(long_name, [metric("Score", 0.1)], order=7, input=other_input),
    ])
    f = save(tmp_path / "results.json", doc)
    root = tmp_path / "store"
    for mode in ("name", "input", "position"):
        _ok(deepeval_argv(f, root, mode, case=mode))

    def digest(text: str) -> str:
        return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    assert sorted(by_case(read_rows(root, "name"))) == sorted(["HumanEval/129@0.7", digest(long_name)])
    assert sorted(by_case(read_rows(root, "input"))) == sorted([digest(long_input), digest(other_input)])
    assert by_case(read_rows(root, "position")) == {"position:4": ["met"], "position:7": ["missed"]}


def test_id6_case_input_on_a_conversational_test_case_is_refused(tmp_path: Path) -> None:
    doc = run_doc(scored("single", [0.9]), [conversation("chat", [metric("Score", 0.8)], order=1)])
    f = save(tmp_path / "results.json", doc)
    root = tmp_path / "store"
    refused(run_import(deepeval_argv(f, root, "v1", case="input")))
    _nothing_under(root)
    _ok(deepeval_argv(f, root, "v1", case="name"))


def test_id6_case_name_on_every_name_positional_is_refused_and_position_reads_it(tmp_path: Path) -> None:
    positional = run_doc([case(f"test_case_{i}", [metric("Score", s)], order=i) for i, s in enumerate([0.9, 0.2, 0.6])])
    f = save(tmp_path / "results.json", positional)
    root = tmp_path / "store"
    refused(run_import(deepeval_argv(f, root, "v1", case="name")))
    _nothing_under(root)
    _ok(deepeval_argv(f, root, "v1", case="position"))
    assert sorted(by_case(read_rows(root, "v1"))) == ["position:0", "position:1", "position:2"]


def test_id6_case_name_with_some_names_set_is_read(tmp_path: Path) -> None:
    doc = run_doc([case("test_case_0", [metric("Score", 0.9)], order=0), case("mine", [metric("Score", 0.2)], order=1)])
    f = save(tmp_path / "results.json", doc)
    root = tmp_path / "store"
    _ok(deepeval_argv(f, root, "v1", case="name"))
    assert sorted(by_case(read_rows(root, "v1"))) == ["mine", "test_case_0"]


@pytest.mark.parametrize("mode,field", [("name", "name"), ("input", "input")])
def test_id6_an_empty_case_text_is_refused(tmp_path: Path, mode: str, field: str) -> None:
    empty = case("x", [metric("Score", 0.9)], order=1)
    empty[field] = ""
    doc = run_doc([case("fine", [metric("Score", 0.9)], order=0, input="a question " * 10), empty])
    f = save(tmp_path / "results.json", doc)
    root = tmp_path / "store"
    refused(run_import(deepeval_argv(f, root, "v1", case=mode)))
    _nothing_under(root)
    save(f, run_doc(doc["testCases"][:1]))
    _ok(deepeval_argv(f, root, "v1", case=mode))


# ---------- ID7 ----------


def _base(tmp_path: Path) -> Path:
    doc = run_doc([
        *scored("a", [0.9, 0.1]),
        case("b", [metric("Faithfulness", 0.4), metric("Score", 0.7)], order=2),
    ])
    return save(tmp_path / "results.json", doc)


METRIC, CUT, CASE = ("--metric", "Score"), ("--cut", "0.5", "--below"), ("--case", "name")


def _argv(f: Path, root: Path, metric: tuple[str, ...] = METRIC, cut: tuple[str, ...] = CUT,
          case: tuple[str, ...] = CASE) -> list[str]:
    return ["deepeval", str(f), "--store", str(root), "--run", "v1", *metric, *cut, *case]


MALFORMED = {
    "no --metric": {"metric": ()},
    "no --cut": {"cut": ()},
    "no --case": {"case": ()},
    "a number with no side": {"cut": ("--cut", "0.5")},
    "a number with both sides": {"cut": ("--cut", "0.5", "--below", "--above")},
    "recorded with --below": {"cut": ("--cut", "recorded", "--below")},
    "recorded with --above": {"cut": ("--cut", "recorded", "--above")},
    "a cut that is not a number": {"cut": ("--cut", "high", "--below")},
    "a nan cut": {"cut": ("--cut", "nan", "--below")},
    "a case rule that does not exist": {"case": ("--case", "id")},
}


# R17: a flag missing, or a value outside its choices, is a wrong command line: exit 2, one line,
# nothing on stdout and nothing written
WRONG_COMMAND_LINE = {"no --metric", "no --cut", "no --case", "a case rule that does not exist"}


def _wrong_command_line(r) -> None:  # type: ignore[no-untyped-def]
    assert r.code == 2, r.text
    assert r.out.strip() == "", r.out
    assert len([line for line in r.err.splitlines() if line.strip()]) == 1, r.err


@pytest.mark.parametrize("what", list(MALFORMED))
def test_id7_a_missing_or_malformed_rule_is_refused(tmp_path: Path, what: str) -> None:
    f = _base(tmp_path)
    root = tmp_path / "store"
    (_wrong_command_line if what in WRONG_COMMAND_LINE else refused)(run_import(_argv(f, root, **MALFORMED[what])))
    _nothing_under(root)
    _ok(_argv(f, root))


def test_id7_a_metric_the_file_does_not_carry_is_refused_naming_those_it_does(tmp_path: Path) -> None:
    f = _base(tmp_path)
    root = tmp_path / "store"
    r = run_import(_argv(f, root, metric=("--metric", "Answer Relevancy")))
    refused(r)
    assert "Score" in r.err and "Faithfulness" in r.err
    _nothing_under(root)
    _ok(_argv(f, root, metric=("--metric", "Faithfulness")))


@pytest.mark.parametrize("doc", [{"results": []}, {"testRun": {"testCases": []}}, {"identifier": "x", "testPassed": 3}])
def test_id7_json_with_no_test_cases_and_no_test_run_data_is_refused(tmp_path: Path, doc: dict[str, Any]) -> None:
    f = save(tmp_path / "results.json", doc)
    root = tmp_path / "store"
    refused(run_import(deepeval_argv(f, root, "v1")))
    _nothing_under(root)
    save(f, {**doc, "testRunData": run_doc(scored("a", [0.9]))})
    _ok(deepeval_argv(f, root, "v1"))


# ---------- ID8 ----------


def test_id8_the_score_and_the_rule_are_kept_on_every_row(tmp_path: Path) -> None:
    doc = run_doc([
        case("m", [metric("Score", 0.62, threshold=0.4, success=True)], order=0),
        case("r", [metric("Score", None, threshold=0.4, error="ValueError: raised")], order=1),
    ])
    f = save(tmp_path / "results.json", doc)
    root = tmp_path / "store"
    _ok(deepeval_argv(f, root, "cut", cut=("0.7", "--below")))
    _ok(deepeval_argv(f, root, "recorded", cut=("recorded",)))
    cut = {r["case"]: r["import"] for r in read_rows(root, "cut")}
    assert cut["m"]["score"] == 0.62 and cut["m"]["metric"] == "Score" and cut["m"]["threshold"] == 0.4
    assert cut["m"]["cut"] == 0.7 and cut["m"]["side"] == "below" and cut["m"]["deepeval_success"] is True
    assert cut["r"]["score"] is None and cut["r"]["threshold"] == 0.4 and cut["r"]["deepeval_success"] is False
    recorded = {r["case"]: r["import"] for r in read_rows(root, "recorded")}
    assert recorded["m"]["cut"] == "recorded" and recorded["m"]["score"] == 0.62
    assert recorded["m"]["metric"] == "Score" and recorded["m"]["deepeval_success"] is True


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


FIELD_SENTINELS = {
    "input": "Hq3v8InputK2m9", "actualOutput": "Jw5x1OutputP7r4", "expectedOutput": "Ly6z0ExpectedN8t2",
    "reason": "Mb9c4ReasonS3u7",
}


def test_id8_no_input_output_expected_output_or_reason_is_kept(tmp_path: Path) -> None:
    s = FIELD_SENTINELS
    doc = run_doc([
        case(f"c{i}", [metric("Score", score, reason=f"{s['reason']} {i}")], order=i,
             input=f"{s['input']} {i}", actualOutput=f"{s['actualOutput']} {i}",
             expectedOutput=f"{s['expectedOutput']} {i}")
        for i, score in enumerate([0.9, 0.1, 0.6])
    ])
    f = save(tmp_path / "results.json", doc)
    root = tmp_path / "store"
    _ok(deepeval_argv(f, root, "v1", case="name"))
    for row in read_rows(root, "v1"):
        assert not ({"input", "actualOutput", "expectedOutput", "reason", "actual_output", "expected_output"} & _keys(row["meta"]))
    for name, sentinel in s.items():
        assert holds(root, sentinel) == [], name


# ---------- ID9 ----------


def test_id9_started_is_taken_when_given(tmp_path: Path) -> None:
    f = save(tmp_path / "test_run_20260101_000000.json", run_doc(scored("x", [0.9])))
    root = tmp_path / "store"
    _ok(deepeval_argv(f, root, "v1", extra=["--started", "2026-09-05T18:54:07Z"]))
    m = Store(root).manifest("v1")
    assert (m.created_at, m.environment["import"]["started_from"]) == ("2026-09-05T18:54:07Z", "given")


NAME_TIME = """
import os, sys, time
os.environ["TZ"] = "UTC"
time.tzset()
""" + IMPORT_MAIN


def test_id9_the_first_files_name_gives_the_time_under_a_utc_clock(tmp_path: Path) -> None:
    """Run with the clock's zone set to UTC, where reading the name as UTC and reading it as the
    machine's own time agree; which of the two holds elsewhere is owed as a ruling."""
    first = save(tmp_path / "test_run_20260905_185407.json", run_doc(scored("x", [0.9])))
    second = save(tmp_path / "test_run_20270101_000000.json", run_doc(scored("x", [0.1])))
    root = tmp_path / "store"
    env = dict(os.environ, TZ="UTC")
    r = run_python(NAME_TIME, deepeval_argv([first, second], root, "v1"), env=env, cwd=tmp_path)
    assert r.code == 0, r.text
    m = Store(root).manifest("v1")
    assert (m.created_at, m.environment["import"]["started_from"]) == ("2026-09-05T18:54:07Z", "file name")
    assert "file name" in r.out


def test_id9_otherwise_the_first_files_modification_time(tmp_path: Path) -> None:
    first = save(tmp_path / "old-version.json", run_doc(scored("x", [0.9])))
    second = save(tmp_path / "test_run_20270101_000000.json", run_doc(scored("x", [0.1])))
    os.utime(first, (1_757_098_447, 1_757_098_447))
    os.utime(second, (1_800_000_000, 1_800_000_000))
    root = tmp_path / "store"
    r = run_import(deepeval_argv([first, second], root, "v1"))
    assert r.code == 0, r.text
    m = Store(root).manifest("v1")
    assert m.environment["import"]["started_from"] == "file time"
    assert m.created_at.endswith("Z")
    assert pd.Timestamp(m.created_at) == pd.Timestamp("2025-09-05T18:54:07Z")
    assert "file time" in r.out


def test_ic5_the_manifest_files_are_each_input_files_name_and_digest(tmp_path: Path) -> None:
    first = save(tmp_path / "one.json", run_doc(scored("x", [0.9])))
    second = save(tmp_path / "two.json.gz", run_doc(scored("x", [0.1])), gz=True)
    root = tmp_path / "store"
    _ok(deepeval_argv([first, second], root, "v1", extra=STARTED))
    files = [dict(f) for f in Store(root).manifest("v1").environment["import"]["files"]]
    assert files == [
        {"name": "one.json", "sha256": hashlib.sha256(first.read_bytes()).hexdigest()},
        {"name": "two.json.gz", "sha256": hashlib.sha256(second.read_bytes()).hexdigest()},
    ]


# ---------- ruled 2026-09-29, Session A ruling 1: the name is DeepEval's local clock ----------

NEW_YORK = "America/New_York"


def _names_the_zone(text: str, local: datetime) -> bool:
    """The summary names the zone the name was read in: its IANA name, its abbreviation, or its
    offset from UTC in any of the usual spellings."""
    offset = local.utcoffset()
    assert offset is not None
    minutes = int(offset.total_seconds() // 60)
    sign, hours, rest = "-" if minutes < 0 else "+", abs(minutes) // 60, abs(minutes) % 60
    spelled = rf"(?<![\d:]){re.escape(sign)}0?{hours}(?::?{rest:02d})?(?![\d])"
    return NEW_YORK in text or re.search(rf"\b{local.strftime('%Z')}\b", text) is not None or re.search(spelled, text) is not None


@pytest.mark.parametrize("name,utc", [
    ("test_run_20260905_145407.json", "2026-09-05T18:54:07Z"),  # EDT, four hours behind UTC
    ("test_run_20260105_135407.json", "2026-01-05T18:54:07Z"),  # EST, five hours behind UTC
])
def test_id9_the_name_is_read_in_the_zone_of_the_machine_running_the_import(tmp_path: Path, name: str, utc: str) -> None:
    f = save(tmp_path / name, run_doc(scored("x", [0.9, 0.2])))
    root = tmp_path / "store"
    r = run_python(IMPORT_MAIN, deepeval_argv(f, root, "v1"), env=dict(os.environ, TZ=NEW_YORK), cwd=tmp_path)
    assert r.code == 0, r.text
    m = Store(root).manifest("v1")
    assert (m.created_at, m.environment["import"]["started_from"]) == (utc, "file name")
    local = datetime.fromisoformat(utc[:-1] + "+00:00").astimezone(ZoneInfo(NEW_YORK))
    text = r.out.replace(str(tmp_path.resolve()), "").replace(str(tmp_path), "")
    assert "saved" in text.lower(), r.out
    assert _names_the_zone(text, local), r.out


def test_id9_a_name_with_deepevals_collision_suffix_is_read_the_same(tmp_path: Path) -> None:
    f = save(tmp_path / "test_run_20260905_185407_2.json", run_doc(scored("x", [0.9])))
    os.utime(f, (1_800_000_000, 1_800_000_000))
    root = tmp_path / "store"
    r = run_python(IMPORT_MAIN, deepeval_argv(f, root, "v1"), env=dict(os.environ, TZ="UTC"), cwd=tmp_path)
    assert r.code == 0, r.text
    m = Store(root).manifest("v1")
    assert (m.created_at, m.environment["import"]["started_from"]) == ("2026-09-05T18:54:07Z", "file name")


# ---------- ruled 2026-09-29, Session A ruling 2: --case input is always a digest ----------


def test_id6_case_input_is_a_digest_whatever_the_inputs_length(tmp_path: Path) -> None:
    short, tiny = "Kz3w what is two plus two", "Q7"
    doc = run_doc([case("a", [metric("Score", 0.9)], order=0, input=short),
                   case("b", [metric("Score", 0.1)], order=1, input=tiny)])
    f = save(tmp_path / "results.json", doc)
    root = tmp_path / "store"
    _ok(deepeval_argv(f, root, "v1", case="input"))

    def digest(text: str) -> str:
        return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    assert by_case(read_rows(root, "v1")) == {digest(short): ["met"], digest(tiny): ["missed"]}
    assert holds(root, short) == []


# ---------- ruled 2026-09-29, Session A ruling 3: the reader's counts reach --json too ----------


def _carries(value: Any, label: str, count: int) -> bool:
    """Somewhere in the JSON, a mapping pairs the label with the count: as key and value, or as
    two values of one object."""
    if isinstance(value, dict):
        if value.get(label) == count or (label in value.values() and count in value.values()):
            return True
        return any(_carries(v, label, count) for v in value.values())
    if isinstance(value, list):
        return any(_carries(v, label, count) for v in value)
    return False


def test_id2_without_this_metric_and_the_thresholds_are_carried_in_json(tmp_path: Path) -> None:
    doc = run_doc([
        *[case(f"a{i}", [metric("Score", 0.9, threshold=0.25)], order=i) for i in range(3)],
        *[case(f"b{i}", [metric("Score", 0.9, threshold=0.75)], order=3 + i) for i in range(2)],
        case("c0", [metric("Other", 0.5)], order=5), case("c1", [metric("Other", 0.5)], order=6),
    ])
    f = save(tmp_path / "results.json", doc)
    root = tmp_path / "store"
    r = run_import(deepeval_argv(f, root, "v1", cut=("recorded",), extra=["--json"]))
    assert r.code == 0, r.text
    out = r.json()
    assert _carries(out, "without this metric", 2), out
    labels = [s for s in scalars(out) if isinstance(s, str)]
    for threshold, count in (("0.25", 3), ("0.75", 2)):
        assert any(threshold in s and _carries(out, s, count) for s in labels) or _carries(out, float(threshold), count), (threshold, out)
