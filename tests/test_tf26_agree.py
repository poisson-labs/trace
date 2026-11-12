"""TF26-28 to TF26-32: the same evaluation read from different exports agrees wherever they hold
the same facts, every difference is named, and both versions pair (the brief's rule 2; spec
section 18.3.2's "two entry points that converge on one reader"; SG9).

- TF26-28: the exports that are one export give the same record, key for key: the candidate's
  answer whole and in pages; the page's JSON and its JSON Lines; the page's CSV and its TSV.
- TF26-29: every export read against the expanded answer, which holds the most. They agree on
  the case, the try, the outcome, the score, the wall time, the output's length, the total
  tokens, the scores, and the cached and reasoning tokens. They differ in these ways and no
  other, each frozen:

  a. the plain answer holds a reference where the dataset row is: the input's length is not
     recorded (and a key of the row, and the input's key, cannot name the case);
  b. an answer that was not asked for costs and feedback, and every download of the page,
     records no cost and no feedback, and counts the rows that record tokens and no cost;
  c. the page's downloads hold the rows alone: steps, tool calls, their counts and retries are
     not recorded, the count of model calls is the summary's requests (so not recorded where
     no model was called, where the calls say a recorded none), no trace is written, and the
     case that errored has no class, no kind of step and is unclassified (so it carries no
     signal that follows from its kind);
  d. the page's table holds a model's total tokens and no input or output count, and leaves
     out the reference to the dataset row.
- TF26-30: both versions pair, for both evaluation pairs: by the dataset row's digest from
  every export that carries the reference; by the input's key and by a key of the row from
  every export that holds the row; one export of one version with another of the other. The
  page's table pairs by a key of the row or by the input, never by the reference.
- TF26-31: a fix check counts the same from every export, by the status and by the score; by
  the score it says which tries have no outcome.
- TF26-32: the order the files are given in changes nothing; the lookup fixture's two tries a
  case pair across its versions.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pytest

from tf0_support import trace
from tf21_support import records, run_import
from tf26_support import (
    API_EXPORTS, CASES, DIGEST, ERRORED, EXPORTS, KEY, LOOKUP, QUESTIONS, RUN, UI_CALLS, UI_EXPORTS, UI_TABLES, VERSIONS, WITH_REF,
    WITH_ROW, approx, columns, export, imported, of, recs, refused, same_but_case, stored_spans, tally, tries, world, wv_argv,
)

MODES = ("status", "exact")
#: What an export that was not asked for costs and feedback does not record.
NOT_ASKED = ("cost_usd", "feedback")
#: What the page's rows, which hold no call under them, do not record of the structure.
NO_CALLS = ("steps", "tool_calls", "tool_call_count", "tool_error_count", "retries")
#: What differs for the case that errored, whose exception the page's rows do not hold.
NO_EXCEPTION = ("error_type", "error_span_kind", "failure_kind")
#: What the page's table does not hold of the tokens.
NO_PARTS = ("input_tokens", "output_tokens")


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and approx(a, b, 1e-12)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_same(a[k], b[k]) for k in a)
    return bool(a == b)


def _differing(a: dict[str, Any], b: dict[str, Any]) -> set[str]:
    return {key for key in set(a) | set(b) if key != "case" and not _same(a.get(key), b.get(key))}


def _spans(root: Path, run: str = RUN) -> dict[str, list[tuple[Any, ...]]]:
    out = {}
    for case, row in columns(root, run).items():
        out[case] = sorted((s["span_id"], s["parent_id"], s["kind"], s["start_ns"], s["end_ns"], s["error"] is not None) for s in stored_spans(row))
    return out


# ---------- TF26-28 ----------


@pytest.mark.parametrize("mode", MODES)
def test_tf26_28_the_candidate_s_answer_whole_and_in_pages_give_the_same_record(tmp_path_factory: Any, mode: str) -> None:
    whole, pages = world(tmp_path_factory, "candidate", "pull", mode), world(tmp_path_factory, "candidate", "pages", mode)
    assert recs(whole[0], RUN) == recs(pages[0], RUN)
    assert _spans(whole[0]) == _spans(pages[0])
    for key in ("rows", "cases", "outcomes", "no_outcome", "counts", "started", "declared"):
        assert whole[1][key] == pages[1][key], key


@pytest.mark.parametrize("name", [*VERSIONS, *LOOKUP])
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("pair", [UI_CALLS, UI_TABLES])
def test_tf26_28_the_page_s_two_formats_of_one_shape_give_the_same_record(tmp_path_factory: Any, name: str, mode: str, pair: tuple[str, str]) -> None:
    (a_root, a), (b_root, b) = (world(tmp_path_factory, name, kind, mode) for kind in pair)
    assert tries(a_root, RUN) == tries(b_root, RUN)
    for key in ("rows", "cases", "outcomes", "no_outcome", "counts", "started", "declared"):
        assert a[key] == b[key], key


# ---------- TF26-29 ----------


def _against_expanded(factory: Any, version: str, kind: str, mode: str) -> dict[str, set[str]]:
    """The keys of each case's record that differ between the export and the expanded answer."""
    got = recs(world(factory, version, kind, mode)[0], RUN)
    most = recs(world(factory, version, "expanded", mode)[0], RUN)
    assert sorted(got) == sorted(most) == list(CASES)
    return {case: _differing(got[case], most[case]) for case in CASES}


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("mode", MODES)
def test_tf26_29_a_the_plain_answer_differs_in_the_input_s_length_alone(tmp_path_factory: Any, version: str, mode: str) -> None:
    differing = _against_expanded(tmp_path_factory, version, "pull", mode)
    assert all(keys == {"input_chars"} for keys in differing.values()), differing
    assert _spans(world(tmp_path_factory, version, "pull", mode)[0]) == _spans(world(tmp_path_factory, version, "expanded", mode)[0])


@pytest.mark.parametrize("mode", MODES)
def test_tf26_29_b_an_answer_not_asked_for_costs_and_feedback_records_neither(tmp_path_factory: Any, mode: str) -> None:
    differing = _against_expanded(tmp_path_factory, "candidate", "plain", mode)
    # every case of the candidate called the model and carries a reaction
    assert all(keys == {"input_chars", *NOT_ASKED} for keys in differing.values()), differing
    plain = world(tmp_path_factory, "candidate", "plain", mode)
    asked = world(tmp_path_factory, "candidate", "pull", mode)
    assert plain[1]["counts"]["no cost recorded"] == 10 and asked[1]["counts"]["no cost recorded"] == 0
    assert _spans(plain[0]) == _spans(asked[0])


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("kind", UI_EXPORTS)
@pytest.mark.parametrize("mode", MODES)
def test_tf26_29_c_d_the_page_s_rows_differ_in_what_they_do_not_hold_and_no_more(tmp_path_factory: Any, version: str, kind: str, mode: str) -> None:
    differing = _against_expanded(tmp_path_factory, version, kind, mode)
    bad, _, _, _, reached = ERRORED[version]
    most = recs(world(tmp_path_factory, version, "expanded", mode)[0], RUN)
    for case, keys in differing.items():
        want = {*NOT_ASKED, *NO_CALLS}
        if most[case]["total_tokens"] is None:
            # no model call: the calls say a recorded none, the row alone says nothing; and
            # there is no cost to miss
            want |= {"llm_calls"}
            want -= {"cost_usd"}
        elif kind in UI_TABLES:
            want |= set(NO_PARTS)
        if case == bad:
            want |= set(NO_EXCEPTION)
            if reached == "timeout":
                want |= {"signals"}  # a timeout is a budget hit; an unclassified error is none
        assert keys == want, (case, sorted(keys ^ want))
    got = recs(world(tmp_path_factory, version, kind, mode)[0], RUN)
    assert got[bad]["failure_kind"] == "unclassified_error" and most[bad]["failure_kind"] == reached


def test_tf26_29_what_every_export_agrees_on() -> None:
    """Written out, so that a key dropped from the differences above is seen to be one of
    these: every export of one evaluation gives the same of each."""
    agreed = {"outcome", "score", "wall_time_s", "output_chars", "total_tokens", "cached_tokens", "reasoning_tokens", "scores", "repeat",
              "ttft_s", "working_time_s", "horizon", "schema"}
    named = {"input_chars", *NOT_ASKED, *NO_CALLS, "llm_calls", *NO_EXCEPTION, "signals", *NO_PARTS}
    from tf21_support import RECORD_KEYS

    assert not agreed & named
    assert agreed | named | {"case"} == set(RECORD_KEYS), set(RECORD_KEYS) ^ (agreed | named | {"case"})


# ---------- TF26-30 ----------


@pytest.mark.parametrize("kind", [k for k in EXPORTS if k in WITH_REF])
@pytest.mark.parametrize("pair", [VERSIONS, LOOKUP])
def test_tf26_30_by_the_dataset_row_the_two_versions_hold_the_same_cases(tmp_path: Path, kind: str, pair: tuple[str, str]) -> None:
    for name, run in zip(pair, ("old", "new"), strict=True):
        imported(of(name, kind, tmp_path / "st", run, mode="status", case="example"))
    old = sorted({r["case"] for r in records(tmp_path / "st", "old")})
    new = sorted({r["case"] for r in records(tmp_path / "st", "new")})
    assert old == new == sorted(DIGEST[case] for case in (CASES if pair == VERSIONS else QUESTIONS))


@pytest.mark.parametrize("kind", WITH_ROW)
@pytest.mark.parametrize("pair", [VERSIONS, LOOKUP])
@pytest.mark.parametrize("case", ["input", "example:id"])
def test_tf26_30_by_the_input_or_a_key_of_the_row_every_export_that_holds_the_row_pairs_them(tmp_path: Path, kind: str, pair: tuple[str, str], case: str) -> None:
    for name, run in zip(pair, ("old", "new"), strict=True):
        imported(of(name, kind, tmp_path / "st", run, mode="status", case=case))
    old = sorted({r["case"] for r in records(tmp_path / "st", "old")})
    new = sorted({r["case"] for r in records(tmp_path / "st", "new")})
    cases = CASES if pair == VERSIONS else QUESTIONS
    assert old == new == sorted((KEY[c] if case == "input" else c) for c in cases)


@pytest.mark.parametrize(("old_kind", "new_kind", "case"), [
    ("ui-json", "pull", "example"), ("pull", "ui-jsonl", "example"), ("expanded", "ui-csv", "input"), ("ui-tsv", "ui-json", "input"),
    ("ui-csv", "expanded", "example:case"), ("ui-json", "ui-tsv", "example:id"),
])
def test_tf26_30_one_export_of_one_version_pairs_with_another_of_the_other(tmp_path: Path, old_kind: str, new_kind: str, case: str) -> None:
    imported(of("baseline", old_kind, tmp_path / "st", "old", mode="status", case=case))
    imported(of("candidate", new_kind, tmp_path / "st", "new", mode="status", case=case))
    ran = trace(["fix-check", "old", "new", "--store", str(tmp_path / "st"), "--event", "missed", "--inputs", "all", "--max-mde", "0.5", "--json"])
    assert ran.code == 0, ran.err
    doc = json.loads(ran.out)
    assert doc["inputs"]["compared"] == 10, doc["inputs"]


@pytest.mark.parametrize("kind", UI_TABLES)
def test_tf26_30_the_page_s_table_pairs_by_a_key_of_the_row_or_by_the_input_never_by_the_reference(tmp_path: Path, kind: str) -> None:
    for version in VERSIONS:
        line = refused(run_import(of(version, kind, tmp_path / "st", version, mode="status", case="example")))
        assert "--case-from input" in line and "example:" in line, line
    # the answer that holds only the reference pairs by the reference, and by nothing of the row
    for case in ("input", "example:id"):
        line = refused(run_import(of("baseline", "pull", tmp_path / "st", "x", mode="status", case=case)))
        assert "--case-from example" in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF26-31 ----------

COMPARED = ("verdict", "sentence", "inputs", "rows", "control", "test", "difference", "by_input", "direction", "limits", "guidance")


def _fix_check(tmp: Path, kind: str, mode: str, pair: tuple[str, str] = VERSIONS, case: str | None = None) -> dict[str, Any]:
    for name, run in zip(pair, ("old", "new"), strict=True):
        flags = {} if case is None else {"case": case}
        imported(of(name, kind, tmp / "st", run, mode=mode, **flags))
    ran = trace(["fix-check", "old", "new", "--store", str(tmp / "st"), "--event", "missed", "--inputs", "all", "--max-mde", "0.2", "--json"])
    assert ran.code == 0, ran.err
    doc: dict[str, Any] = json.loads(ran.out)
    return doc


@pytest.mark.parametrize("kind", EXPORTS)
def test_tf26_31_a_fix_check_by_the_status_counts_the_same_from_every_export(tmp_path: Path, kind: str) -> None:
    doc = _fix_check(tmp_path / kind, kind, "status")
    first = _fix_check(tmp_path / "first", "pull", "status")
    for key in COMPARED:
        if key == "by_input":
            # the inputs are named by the case, which the table spells by a key of the row
            assert len(doc[key]) == len(first[key]), key
            continue
        assert _same(doc[key], first[key]), (kind, key, doc[key], first[key])
    assert (doc["rows"]["old"]["failed"], doc["rows"]["old"]["runs"]) == (1, 10)
    assert (doc["rows"]["new"]["failed"], doc["rows"]["new"]["runs"]) == (1, 10)
    assert doc["inputs"]["compared"] == 10


@pytest.mark.parametrize("kind", EXPORTS)
def test_tf26_31_by_the_score_every_export_counts_the_same_and_says_which_tries_have_no_outcome(tmp_path: Path, kind: str) -> None:
    doc = _fix_check(tmp_path / kind, kind, "exact")
    first = _fix_check(tmp_path / "first", "pull", "exact")
    for key in COMPARED:
        if key == "by_input":
            assert len(doc[key]) == len(first[key]), key
            continue
        assert _same(doc[key], first[key]), (kind, key)
    for run, failed in (("old", 3), ("new", 1)):
        held = doc["runs"][run]["tally"]
        assert (held["rows"], held["with_outcome"], held["no_outcome"]) == (10, 9, 1), held
        assert (doc["rows"][run]["failed"], doc["rows"][run]["runs"]) == (failed, 8), doc["rows"][run]
    # the errored case of each version has no score, so its input is left out of the pairs
    assert doc["inputs"]["selected"] == 10 and doc["inputs"]["compared"] == 8, doc["inputs"]
    left = doc["inputs"]["left_out"]
    assert left["no outcome on the old version"] == 1 and left["no outcome on the new version"] == 1 and sum(left.values()) == 2, left


@pytest.mark.parametrize("kind", ["expanded", "ui-json", "ui-csv"])
def test_tf26_31_by_the_input_the_fix_check_is_the_same_document_from_every_export_that_holds_the_row(tmp_path: Path, kind: str) -> None:
    doc = _fix_check(tmp_path / kind, kind, "exact", case="input")
    first = _fix_check(tmp_path / "first", "expanded", "exact", case="input")
    for key in COMPARED:
        assert _same(doc[key], first[key]), (kind, key)


# ---------- TF26-32 ----------


def test_tf26_32_the_order_the_files_are_given_in_changes_nothing(tmp_path: Path) -> None:
    files = export("candidate", "pages")
    shuffled = list(files)
    random.Random(3).shuffle(shuffled)
    assert shuffled != files
    a = imported(wv_argv(files, tmp_path / "a", "r", case="example", outcome="status", cut=None))
    b = imported(wv_argv(shuffled, tmp_path / "b", "r", case="example", outcome="status", cut=None))
    assert recs(tmp_path / "a", "r") == recs(tmp_path / "b", "r")
    assert _spans(tmp_path / "a", "r") == _spans(tmp_path / "b", "r")
    for key in ("rows", "cases", "outcomes", "counts", "started"):
        assert a[key] == b[key], key


@pytest.mark.parametrize("kind", EXPORTS)
def test_tf26_32_the_lookup_fixture_s_two_tries_a_case_pair_across_its_versions(tmp_path: Path, kind: str) -> None:
    doc = _fix_check(tmp_path / kind, kind, "exact", LOOKUP)
    assert (doc["rows"]["old"]["failed"], doc["rows"]["old"]["runs"]) == (4, 6)
    assert (doc["rows"]["new"]["failed"], doc["rows"]["new"]["runs"]) == (0, 6)
    assert doc["inputs"]["compared"] == 3
    old, new = tries(tmp_path / kind / "st", "old"), tries(tmp_path / kind / "st", "new")
    assert sorted(old) == sorted(new) and len(old) == 6
    assert tally({"outcomes": {"met": sum(1 for r in new.values() if r["outcome"] == "pass")}}) == {"met": 6}


@pytest.mark.parametrize("kind", API_EXPORTS)
def test_tf26_32_the_two_answers_of_one_evaluation_place_its_failures_alike(tmp_path_factory: Any, kind: str) -> None:
    for version in VERSIONS:
        a, b = world(tmp_path_factory, version, kind, "status"), world(tmp_path_factory, version, "pull", "status")
        assert {c: same_but_case(r) for c, r in recs(a[0], RUN).items() if kind == "pull"} == {c: same_but_case(r) for c, r in recs(b[0], RUN).items() if kind == "pull"}
        assert _spans(a[0]) == _spans(b[0])
