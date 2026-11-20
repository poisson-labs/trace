"""TF24-28 to TF24-32: the same run read from different exports agrees wherever the exports hold
the same facts, and where they differ the difference is the exports' own, named here (on the real
captures, whose run statistics lag behind the feedback records on two baseline roots).

- TF24-28: with the feedback records beside them, the five exports that carry the steps (the v1
  and v2 run queries, v2 with subtree usage, the command's run export and its trace files) give
  the same record for every case, key for key, and the same stored columns and spans. The only
  keys that differ are the ones the exports themselves hold differently: cached and reasoning
  tokens (the API splits them, the command's export does not) and the token counts of the one
  trace that made no model call (the v1 root says 0, the others say nothing).
- TF24-29: without the feedback records, the exports differ on exactly the two baseline roots
  whose statistics trail (``exact`` on 8 of 10 in v2 and the command's exports, 10 in v1): those
  two rows have no outcome there, and every other row and every other key is the same. The
  candidate agrees everywhere.
- TF24-30: the UI's CSV agrees with the other exports on everything it holds: the cases (by
  the example's ``case``), the outcome by status and by score, the
  wall time, the lengths, the total tokens, the cost, each score's value and each word; what it
  lacks is not recorded; and the one kind it reads differently is the candidate's cut reply (a
  crash, where the exports with the steps see the parser fail).
- TF24-31: a fix check of the two versions counts the same from every export read by the
  root's status, and from every export that holds every score when read by the score; from the
  exports whose statistics trail it counts two baseline tries fewer, and says so.
- TF24-32: two files of one export in either order, and the trace folder's files in any order,
  give the same run.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pytest

from look_support import trace
from langsmith_support import (
    CASES, EXACT, EXPORTS, LATE, RUN, TRACE_EXPORTS, VERSIONS, approx, by_status, columns, export,
    feedback_file, imported, ls_argv, recs, world,
)

#: The keys of the record an export may hold differently from another, and nothing else may.
SPLIT_KEYS = ("cached_tokens", "reasoning_tokens")
TOKEN_KEYS = ("input_tokens", "output_tokens", "total_tokens")
NO_CALL = ("baseline", "c08")


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


# ---------- TF24-28 ----------


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("mode", ["status", "exact"])
def test_tf24_28_the_exports_with_the_steps_give_the_same_record(tmp_path_factory: Any, version: str, mode: str) -> None:
    stored = {kind: recs(world(tmp_path_factory, version, kind, mode, feedback=True)[0], RUN) for kind in TRACE_EXPORTS}
    first = stored["v2"]
    for kind in TRACE_EXPORTS:
        for case in CASES:
            allowed: set[str] = set()
            if kind.startswith("cli"):
                allowed |= set(SPLIT_KEYS)
            if kind == "v1" and (version, case) == NO_CALL:
                allowed |= set(TOKEN_KEYS)
            differing = _differing(first[case], stored[kind][case])
            assert set(differing) <= allowed, (kind, case, differing)
            if kind.startswith("cli") and (version, case) != NO_CALL:
                assert differing == list(SPLIT_KEYS), (kind, case, differing)
    # the two command exports are one export written two ways
    assert stored["cli-runs"] == stored["cli-traces"]
    assert _differing(stored["v2"]["c01"], stored["v2-subtree"]["c01"]) == []


@pytest.mark.parametrize("version", VERSIONS)
def test_tf24_28_and_the_same_columns_and_spans(tmp_path_factory: Any, version: str) -> None:
    roots = {kind: world(tmp_path_factory, version, kind, "exact", feedback=True)[0] for kind in TRACE_EXPORTS}
    first_columns, first_spans = columns(roots["v2"], RUN), _spans(roots["v2"])
    for kind, root in roots.items():
        got = columns(root, RUN)
        for case in CASES:
            for key in ("outcome", "error", "t", "horizon", "confidence", "config_hash"):
                assert _same(got[case][key], first_columns[case][key]) or (got[case][key] != got[case][key]), (kind, case, key)
            assert approx(got[case]["wall_time"], first_columns[case]["wall_time"]), (kind, case)
        assert _spans(root) == first_spans, kind


# ---------- TF24-29 ----------


@pytest.mark.parametrize("version", VERSIONS)
def test_tf24_29_without_the_feedback_records_only_the_trailing_statistics_differ(tmp_path_factory: Any, version: str) -> None:
    whole = recs(world(tmp_path_factory, version, "v1", "exact")[0], RUN)
    for kind in ("v2", "v2-subtree", "cli-runs", "cli-traces"):
        root, data = world(tmp_path_factory, version, kind, "exact")
        stored = recs(root, RUN)
        for case in CASES:
            differing = set(_differing(whole[case], stored[case])) - set(SPLIT_KEYS)
            if (version, case) == NO_CALL:
                differing -= set(TOKEN_KEYS)
            if case in LATE[version]:
                assert {"outcome", "score", "scores"} <= differing <= {"outcome", "score", "scores", "failure_kind", "signals"}, (kind, case, differing)
                assert stored[case]["score"] is None and whole[case]["score"] == EXACT[version][case]
            else:
                assert differing == set(), (kind, case, differing)
        assert data["no_outcome"] == ({"no score": len(LATE[version])} if LATE[version] else {})
    assert LATE["candidate"] == () and LATE["baseline"] == ("c08", "c10")


# ---------- TF24-30 ----------

#: What the CSV holds of a row, which must be what the other exports hold.
CSV_HOLDS = ("case", "repeat", "outcome", "wall_time_s", "input_chars", "output_chars", "cost_usd", "score", "error_type")
#: What it cannot hold.
CSV_LACKS = ("ttft_s", "input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens", "steps", "llm_calls",
             "tool_calls", "tool_call_count", "tool_error_count", "retries", "error_span_kind", "horizon", "working_time_s")


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("mode", ["status", "exact"])
def test_tf24_30_the_csv_agrees_on_what_it_holds_and_records_nothing_else(tmp_path_factory: Any, version: str, mode: str) -> None:
    ui = recs(world(tmp_path_factory, version, "ui", mode)[0], RUN)
    v1 = recs(world(tmp_path_factory, version, "v1", mode)[0], RUN)
    for case in CASES:
        for key in CSV_HOLDS:
            assert _same(ui[case][key], v1[case][key]) or (ui[case][key] is None and v1[case][key] is None), (case, key, ui[case][key], v1[case][key])
        assert ui[case]["total_tokens"] == v1[case]["total_tokens"], case
        for key in CSV_LACKS:
            assert ui[case][key] is None, (case, key)
        for name, value in v1[case]["scores"].items():
            assert ui[case]["scores"][name] == value, (case, name)
        for name, value in v1[case]["feedback"].items():
            held = ui[case]["scores"].get(name, ui[case]["feedback"].get(name))
            if name == "human_thumbs":
                # made by hand after the CSV was downloaded: the file predates them
                assert held is None
            else:
                assert held == value, (case, name)
        if (version, case) == ("candidate", "c09"):
            assert (ui[case]["failure_kind"], v1[case]["failure_kind"]) == ("crash", "format_error")
        else:
            assert ui[case]["failure_kind"] == v1[case]["failure_kind"], case


# ---------- TF24-31 ----------

COMPARED = ("verdict", "sentence", "inputs", "rows", "control", "test", "difference", "by_input", "direction", "limits", "guidance")


def _fix_check(tmp: Path, kind: str, mode: str, feedback: bool = False) -> dict[str, Any]:
    for version, run in (("baseline", "old"), ("candidate", "new")):
        files = [*export(version, kind), *([feedback_file(version)] if feedback else [])]
        imported(by_status(files, tmp / "st", run, case="example" if kind in ("v1", "v2", "v2-subtree", "ui") else "metadata:ls_example_case")
                 if mode == "status" else ls_argv(files, tmp / "st", run))
    ran = trace(["fix-check", "old", "new", "--store", str(tmp / "st"), "--event", "missed", "--inputs", "all", "--max-mde", "0.2", "--json"])
    assert ran.code == 0, ran.err
    doc: dict[str, Any] = json.loads(ran.out)
    return doc


_FIRST: dict[str, dict[str, Any]] = {}


def _first(factory: Any, mode: str) -> dict[str, Any]:
    """The fix check of the v1 run queries, which every other export's is compared with: made
    once in a store of its own. Read-only."""
    if mode not in _FIRST:
        _FIRST[mode] = _fix_check(factory.mktemp(f"ls-first-{mode}"), "v1", mode)
    return _FIRST[mode]


@pytest.mark.parametrize("kind", EXPORTS)
def test_tf24_31_a_fix_check_by_status_counts_the_same_from_every_export(tmp_path: Path, tmp_path_factory: Any, kind: str) -> None:
    doc = _fix_check(tmp_path / kind, kind, "status")
    first = _first(tmp_path_factory, "status")
    for key in COMPARED:
        assert _same(doc[key], first[key]), (kind, key, doc[key], first[key])
    assert (doc["rows"]["old"]["failed"], doc["rows"]["old"]["runs"]) == (1, 10)
    assert (doc["rows"]["new"]["failed"], doc["rows"]["new"]["runs"]) == (1, 10)
    assert doc["inputs"]["compared"] == 10


@pytest.mark.parametrize(("kind", "feedback"), [("v1", False), ("ui", False), ("v2", True), ("v2-subtree", True), ("cli-runs", True), ("cli-traces", True)])
def test_tf24_31_by_the_score_every_export_that_holds_every_score_counts_the_same(tmp_path: Path, tmp_path_factory: Any, kind: str, feedback: bool) -> None:
    doc = _fix_check(tmp_path / kind, kind, "exact", feedback)
    assert (doc["rows"]["old"]["failed"], doc["rows"]["old"]["runs"], doc["rows"]["old"]["no_outcome"]) == (4, 10, 0)
    assert (doc["rows"]["new"]["failed"], doc["rows"]["new"]["runs"], doc["rows"]["new"]["no_outcome"]) == (2, 10, 0)
    first = _first(tmp_path_factory, "exact")
    for key in COMPARED:
        assert _same(doc[key], first[key]), (kind, key)


@pytest.mark.parametrize("kind", ["v2", "cli-runs"])
def test_tf24_31_where_the_statistics_trail_the_fix_check_says_two_tries_have_no_outcome(tmp_path: Path, kind: str) -> None:
    doc = _fix_check(tmp_path / kind, kind, "exact")
    tally = doc["runs"]["old"]["tally"]
    assert (tally["rows"], tally["with_outcome"], tally["no_outcome"]) == (10, 8, 2), tally
    assert doc["runs"]["new"]["tally"]["with_outcome"] == 10
    assert doc["rows"]["old"]["failed"] == 2 and doc["rows"]["new"]["failed"] == 2
    assert doc["inputs"]["compared"] == 8 and doc["inputs"]["left_out"]["no outcome on the old version"] == 2


# ---------- TF24-32 ----------


def test_tf24_32_the_order_the_files_are_given_in_changes_nothing(tmp_path: Path) -> None:
    files = export("candidate", "cli-traces")
    shuffled = list(files)
    random.Random(3).shuffle(shuffled)
    assert shuffled != files
    a = imported(by_status(files, tmp_path / "a", "r"))
    b = imported(by_status(shuffled, tmp_path / "b", "r"))
    assert recs(tmp_path / "a", "r") == recs(tmp_path / "b", "r")
    assert _spans(tmp_path / "a") == _spans(tmp_path / "b")
    for key in ("rows", "cases", "outcomes", "counts", "started"):
        assert a[key] == b[key], key
    # the feedback list before or after the runs
    c = imported(ls_argv([feedback_file("baseline"), *export("baseline", "v2")], tmp_path / "c", "r"))
    d = imported(ls_argv([*export("baseline", "v2"), feedback_file("baseline")], tmp_path / "d", "r"))
    assert recs(tmp_path / "c", "r") == recs(tmp_path / "d", "r") and c["outcomes"] == d["outcomes"]
