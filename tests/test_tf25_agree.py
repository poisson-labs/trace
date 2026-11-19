"""TF25-28 to TF25-32: the same experiment read from different exports agrees wherever they hold
the same facts, and every difference is named here and nowhere else (on the real captures, whose
page downloads carry no id).

- TF25-28: the three exports that hold the spans (the fetch, BTQL's ``spans`` and ``traces``)
  give the same record for every case, key for key, the same stored columns and the same spans:
  they are one set of events in two orders.
- TF25-29: the three exports that hold one row a case (BTQL's ``summary``, the page's JSON and
  its CSV) agree with the spans on every key they can hold, and differ only where named:
  (a) the structure the rolled-up row cannot hold (steps, tool calls and their counts, retries)
  is not recorded; (b) a trace that made no model call says 0 tokens where the spans say
  nothing; (c) of the case that errored, the summary holds no class (its traceback is cut) and
  the rolled-up rows no span, only the count of tool errors, so the kind differs as TF25-20
  pins. The page's JSON and its CSV give the same record, key for key.
- TF25-30: both versions pair. Read by the input, a page's download of one version pairs
  with an API answer of the other. The page's files pair by input only: the record is refused there, and a metadata key
  drops each version's errored case.
- TF25-31: a fix check counts the same from every export, by the root's error and by the
  score: the same tries, the same failures, the same rows with no outcome, the same verdict.
- TF25-32: the order the files are given in changes nothing; the lookup fixture's two tries a
  case pair across its two versions from every export.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pytest

from tf0_support import trace
from tf21_support import RECORD_KEYS, run_import
from tf25_support import (
    CASES, ERRORED, EXPORTS, PAGED, ROW_EXPORTS, RUN, SPAN_EXPORTS, USAGE, VERSIONS, approx, bt_argv, by_error, columns,
    export, imported, outcomes, recs, refused, tally, tries, world,
)

#: What a rolled-up row cannot hold of a trace's structure.
STRUCTURE = ("steps", "tool_calls", "tool_call_count", "tool_error_count", "retries")
TOKENS = ("input_tokens", "output_tokens", "total_tokens", "cached_tokens", "reasoning_tokens")
#: What may differ of the case that errored.
OF_THE_ERROR = ("error_type", "error_span_kind", "failure_kind", "signals")
PAGE = ("ui-json", "ui-csv")
MODES = ("error", "exact")


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and approx(a, b, 1e-9)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_same(a[k], b[k]) for k in a)
    return bool(a == b)


def _differing(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    return sorted(key for key in set(a) | set(b) if not _same(a.get(key), b.get(key)))


def _spans(root: Path) -> dict[str, list[tuple[Any, ...]]]:
    out = {}
    for case, row in columns(root, RUN).items():
        trace_ = row["trace"] if isinstance(row["trace"], dict) else json.loads(row["trace"])
        out[case] = sorted((s["span_id"], s["parent_id"], s["kind"], s["start_ns"], s["end_ns"], s["error"] is not None) for s in trace_["spans"])
    return out


# ---------- TF25-28 ----------


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("mode", MODES)
def test_tf25_28_the_exports_with_the_spans_give_the_same_record(tmp_path_factory: Any, version: str, mode: str) -> None:
    stored = {kind: recs(world(tmp_path_factory, version, kind, mode)[0], RUN) for kind in SPAN_EXPORTS}
    assert stored["fetch"] == stored["btql-spans"] == stored["btql-traces"]
    assert sorted(stored["fetch"]) == list(CASES)


@pytest.mark.parametrize("version", VERSIONS)
def test_tf25_28_and_the_same_columns_and_spans(tmp_path_factory: Any, version: str) -> None:
    roots = {kind: world(tmp_path_factory, version, kind, "exact")[0] for kind in SPAN_EXPORTS}
    first_columns, first_spans = columns(roots["fetch"], RUN), _spans(roots["fetch"])
    for kind, root in roots.items():
        got = columns(root, RUN)
        for case in CASES:
            for key in ("outcome", "error", "t", "horizon", "confidence", "config_hash"):
                assert _same(got[case][key], first_columns[case][key]) or (got[case][key] != got[case][key]), (kind, case, key)
            assert approx(got[case]["wall_time"], first_columns[case]["wall_time"]), (kind, case)
        assert _spans(root) == first_spans, kind
    # every event but the grading spans: 27 of the baseline's 85 and of the candidate's 88
    assert sum(len(spans) for spans in first_spans.values()) == {"baseline": 58, "candidate": 61}[version]


@pytest.mark.parametrize("kind", PAGED)
def test_tf25_28_the_pages_give_the_record_the_whole_answer_gives(tmp_path: Path, tmp_path_factory: Any, kind: str) -> None:
    imported(bt_argv(export("candidate", kind), tmp_path / "st", RUN))
    whole = world(tmp_path_factory, "candidate", "fetch", "exact")[0]
    assert recs(tmp_path / "st", RUN) == recs(whole, RUN)
    assert _spans(tmp_path / "st") == _spans(whole)


# ---------- TF25-29 ----------


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("kind", ROW_EXPORTS)
def test_tf25_29_a_rolled_up_row_differs_from_the_spans_only_where_named(tmp_path_factory: Any, version: str, mode: str, kind: str) -> None:
    spans = recs(world(tmp_path_factory, version, "fetch", mode)[0], RUN)
    rolled = recs(world(tmp_path_factory, version, kind, mode)[0], RUN)
    bad = ERRORED[version][0]
    for case in CASES:
        differing = set(_differing(spans[case], rolled[case]))
        # (a) the structure is not in a rolled-up row
        assert set(STRUCTURE) <= differing, (case, differing)
        assert all(rolled[case][key] is None and spans[case][key] is not None for key in STRUCTURE), case
        allowed = set(STRUCTURE)
        if USAGE[version][case] is None:
            # (b) no model call: nothing in the spans, 0 in the rolled-up row
            assert set(TOKENS) <= differing, (case, differing)
            assert all(spans[case][key] is None and rolled[case][key] == 0 for key in TOKENS), case
            allowed |= set(TOKENS)
        if case == bad:
            # (c) what each shape holds of the error
            allowed |= set(OF_THE_ERROR)
        assert differing <= allowed, (kind, case, differing - allowed)
    # everything else, key for key: the case and its try, the outcome and the score, the times,
    # the lengths, the tokens and the cost of a model call, the count of model calls, the scores
    # and the feedback
    agreed = [key for key in RECORD_KEYS if key not in (*STRUCTURE, *TOKENS, *OF_THE_ERROR)]
    assert {"case", "repeat", "outcome", "score", "wall_time_s", "ttft_s", "input_chars", "output_chars", "cost_usd", "llm_calls",
            "scores", "feedback"} <= set(agreed)
    for case in CASES:
        for key in agreed:
            assert _same(spans[case][key], rolled[case][key]) or (spans[case][key] is None and rolled[case][key] is None), (case, key)


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("mode", MODES)
def test_tf25_29_the_page_s_json_and_its_csv_give_the_same_record(tmp_path_factory: Any, version: str, mode: str) -> None:
    a = recs(world(tmp_path_factory, version, "ui-json", mode)[0], RUN)
    b = recs(world(tmp_path_factory, version, "ui-csv", mode)[0], RUN)
    for case in CASES:
        assert _differing(a[case], b[case]) == [], case


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("mode", MODES)
def test_tf25_29_the_summary_and_the_page_s_rows_differ_only_on_the_error_s_class(tmp_path_factory: Any, version: str, mode: str) -> None:
    summary = recs(world(tmp_path_factory, version, "summary", mode)[0], RUN)
    page = recs(world(tmp_path_factory, version, "ui-json", mode)[0], RUN)
    bad = ERRORED[version][0]
    for case in CASES:
        differing = set(_differing(summary[case], page[case]))
        if case == bad:
            assert {"error_type", "failure_kind"} <= differing <= {"error_type", "failure_kind", "signals"}, differing
            assert summary[case]["error_type"] is None and page[case]["error_type"] == ERRORED[version][1]
        else:
            assert differing == set(), (case, differing)


@pytest.mark.parametrize("version", VERSIONS)
def test_tf25_29_the_stored_columns_agree_but_for_the_steps(tmp_path_factory: Any, version: str) -> None:
    first = columns(world(tmp_path_factory, version, "fetch", "exact")[0], RUN)
    for kind in ROW_EXPORTS:
        got = columns(world(tmp_path_factory, version, kind, "exact")[0], RUN)
        for case in CASES:
            for key in ("outcome", "error", "confidence", "config_hash"):
                assert _same(got[case][key], first[case][key]) or (got[case][key] != got[case][key]), (kind, case, key)
            assert approx(got[case]["wall_time"], first[case]["wall_time"]), (kind, case)


# ---------- TF25-30 ----------


@pytest.mark.parametrize(("old_kind", "new_kind"), [("ui-json", "fetch"), ("summary", "ui-csv"), ("ui-csv", "ui-json"), ("fetch", "summary")])
def test_tf25_30_one_export_of_one_version_pairs_with_another_of_the_other(tmp_path: Path, old_kind: str, new_kind: str) -> None:
    imported(by_error(export("baseline", old_kind), tmp_path / "st", "old", case="input"))
    imported(by_error(export("candidate", new_kind), tmp_path / "st", "new", case="input"))
    ran = trace(["fix-check", "old", "new", "--store", str(tmp_path / "st"), "--event", "missed", "--inputs", "all", "--max-mde", "0.5", "--json"])
    assert ran.code == 0, ran.err
    doc = json.loads(ran.out)
    assert doc["inputs"]["compared"] == 10, doc["inputs"]


@pytest.mark.parametrize("kind", PAGE)
def test_tf25_30_the_page_s_files_pair_by_input_only(tmp_path: Path, kind: str) -> None:
    for version in VERSIONS:
        line = refused(run_import(by_error(export(version, kind), tmp_path / "st", version, case="record")))
        assert "--case-from input" in line, line
    # by a metadata key each version loses the case that errored, a different case in each
    for version, run in (("baseline", "old"), ("candidate", "new")):
        data = imported(by_error(export(version, kind), tmp_path / "meta", run, case="metadata:case"))
        assert data["rows"] == 9 and data["counts"]["no case"] == 1
    old, new = outcomes(tmp_path / "meta", "old"), outcomes(tmp_path / "meta", "new")
    assert sorted(set(old) & set(new)) == [c for c in CASES if c not in ("c08", "c09")]
    assert set(old.values()) == set(new.values()) == {"met"}, "no failure is left to compare"


# ---------- TF25-31 ----------

COMPARED = ("verdict", "sentence", "inputs", "rows", "control", "test", "difference", "by_input", "direction", "limits", "guidance")


def _fix_check(tmp: Path, kind: str, mode: str, name: tuple[str, str] = VERSIONS) -> dict[str, Any]:
    for version, run in zip(name, ("old", "new"), strict=True):
        files = export(version, kind)
        imported(by_error(files, tmp / "st", run) if mode == "error" else bt_argv(files, tmp / "st", run))
    ran = trace(["fix-check", "old", "new", "--store", str(tmp / "st"), "--event", "missed", "--inputs", "all", "--max-mde", "0.2", "--json"])
    assert ran.code == 0, ran.err
    doc: dict[str, Any] = json.loads(ran.out)
    return doc


_FIRST: dict[str, dict[str, Any]] = {}


def _first(factory: Any, mode: str) -> dict[str, Any]:
    """The fix check of the fetch, which every other export's is compared with: made once in a
    store of its own. Read-only."""
    if mode not in _FIRST:
        _FIRST[mode] = _fix_check(factory.mktemp(f"bt-first-{mode}"), "fetch", mode)
    return _FIRST[mode]


@pytest.mark.parametrize("kind", EXPORTS)
def test_tf25_31_a_fix_check_by_the_error_counts_the_same_from_every_export(tmp_path: Path, tmp_path_factory: Any, kind: str) -> None:
    doc = _fix_check(tmp_path / kind, kind, "error")
    first = _first(tmp_path_factory, "error")
    for key in COMPARED:
        assert _same(doc[key], first[key]), (kind, key, doc[key], first[key])
    assert (doc["rows"]["old"]["failed"], doc["rows"]["old"]["runs"]) == (1, 10)
    assert (doc["rows"]["new"]["failed"], doc["rows"]["new"]["runs"]) == (1, 10)
    assert doc["inputs"]["compared"] == 10


@pytest.mark.parametrize("kind", EXPORTS)
def test_tf25_31_by_the_score_every_export_counts_the_same_and_says_which_tries_have_no_outcome(tmp_path: Path, tmp_path_factory: Any, kind: str) -> None:
    doc = _fix_check(tmp_path / kind, kind, "exact")
    first = _first(tmp_path_factory, "exact")
    for key in COMPARED:
        assert _same(doc[key], first[key]), (kind, key)
    for run, failed in (("old", 3), ("new", 1)):
        held = doc["runs"][run]["tally"]
        assert (held["rows"], held["with_outcome"], held["no_outcome"]) == (10, 9, 1), held
        assert (doc["rows"][run]["failed"], doc["rows"][run]["runs"]) == (failed, 8), doc["rows"][run]
    # the errored case of each version has no score, so its input is left out of the pairs
    assert doc["inputs"]["selected"] == 10 and doc["inputs"]["compared"] == 8, doc["inputs"]
    left = doc["inputs"]["left_out"]
    assert left["no outcome on the old version"] == 1 and left["no outcome on the new version"] == 1 and sum(left.values()) == 2, left


# ---------- TF25-32 ----------


def test_tf25_32_the_order_the_files_are_given_in_changes_nothing(tmp_path: Path) -> None:
    files = export("candidate", "fetch-pages")
    shuffled = list(files)
    random.Random(3).shuffle(shuffled)
    assert shuffled != files
    a = imported(by_error(files, tmp_path / "a", "r"))
    b = imported(by_error(shuffled, tmp_path / "b", "r"))
    assert recs(tmp_path / "a", "r") == recs(tmp_path / "b", "r")
    assert _spans(tmp_path / "a") == _spans(tmp_path / "b")
    for key in ("rows", "cases", "outcomes", "counts", "started"):
        assert a[key] == b[key], key


@pytest.mark.parametrize("kind", EXPORTS)
def test_tf25_32_the_lookup_fixture_s_two_tries_a_case_pair_across_its_versions(tmp_path: Path, kind: str) -> None:
    doc = _fix_check(tmp_path / kind, kind, "exact", ("old", "new"))
    assert (doc["rows"]["old"]["failed"], doc["rows"]["old"]["runs"]) == (4, 6)
    assert (doc["rows"]["new"]["failed"], doc["rows"]["new"]["runs"]) == (0, 6)
    assert doc["inputs"]["compared"] == 3
    old, new = tries(tmp_path / kind / "st", "old"), tries(tmp_path / kind / "st", "new")
    assert sorted(old) == sorted(new) and len(old) == 6
    assert tally({"outcomes": {"met": sum(1 for r in new.values() if r["outcome"] == "pass")}}) == {"met": 6}
