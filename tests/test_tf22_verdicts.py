"""TF22-33 to TF22-44: ``--verdicts FILE``, the sidecar join (``ingest/verdicts.py``).

A verdicts file is a ``.csv`` (columns ``case``, ``input``, ``outcome``, ``score``,
``failure_kind``) or a ``.jsonl`` (the same keys, plus ``scores`` and ``feedback`` objects).
Each row is joined onto every try of the case it names; when its ``case`` matches no case, by
its input: ``input:`` and the first 12 hex characters of the SHA-256 of the canonical input (a
string as written, anything else as compact JSON with sorted keys), given as the ``case`` itself
or computed from an ``input`` column. A verdict fills what the source did not record and must
agree with what it did. Refused, exit 1, nothing written: a file whose rows match nothing, a row
matching two cases, two rows for one case, a verdict disagreeing with the source, and a file
that is not one.

The API these tests pin: ``input_case(value) -> str``; ``join(rows, path, inputs=None) ->
Joined`` with ``rows`` (the joined rows, in order), ``read``, ``by_case``, ``by_input`` and
``unmatched`` (counts of the file's rows); ``inputs`` maps a row's case to its input key.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from tf22_support import (
    DEEPEVAL,
    FLAGS,
    JUNIT,
    TABLE,
    csv_text,
    deepeval_inputs,
    import_block,
    junit_cases,
    junit_shards,
    names,
    plain_refusal,
    records,
    sha256_of,
    trace_import,
    tree,
)

from poisson_trace.ingest.cut import MET, MISSED
from poisson_trace.ingest.rows import Refusal, Row

SUITE = JUNIT / "trace-suite-1.xml"


def _suite_rows() -> list[Row]:
    """The suite's test cases as the JUnit reader's rows: a pass, a failure, or no outcome for a
    skipped test (its only skipped one)."""
    out = []
    for case, ended in junit_cases(SUITE):
        if ended == "passed":
            out.append(Row(case, MET, None, result="pass"))
        elif ended == "skipped":
            out.append(Row(case, None, "skipped", result=None))
        else:
            out.append(Row(case, MISSED, None, result="fail"))
    return out


def _cases() -> tuple[str, str, list[str]]:
    """``(the skipped case, a passed case, every case)`` of the suite."""
    held = junit_cases(SUITE)
    skipped = next(c for c, e in held if e == "skipped")
    passed = next(c for c, e in held if e == "passed")
    return skipped, passed, [c for c, _ in held]


def _join(rows: Any, path: Path, inputs: Any = None) -> Any:
    from poisson_trace.ingest.verdicts import join

    return join(rows, path, inputs)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    return _write(path, "".join(json.dumps(r) + "\n" for r in rows))


# ---------- TF22-33: the input key ----------


def test_tf22_33_the_input_key_is_the_digest_of_the_text() -> None:
    from poisson_trace.ingest.verdicts import input_case

    text = deepeval_inputs()["HumanEval/152@0.0"]
    assert text == "HumanEval/152 at temperature 0.0"
    assert input_case(text) == "input:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    obj = {"question": "café", "context": ["a", "b"]}
    canon = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert input_case(obj) == "input:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12]
    assert input_case({"context": ["a", "b"], "question": "café"}) == input_case(obj)
    assert input_case(["x", 1]) == "input:" + hashlib.sha256(b'["x",1]').hexdigest()[:12]


def test_tf22_33_a_string_is_hashed_as_written() -> None:
    from poisson_trace.ingest.verdicts import input_case

    # no stripping, no case folding, no normalisation: two spellings are two inputs
    assert input_case("a") != input_case(" a")
    assert input_case("A") != input_case("a")
    assert input_case("é") != input_case("é")
    assert input_case("é") == "input:" + hashlib.sha256("é".encode()).hexdigest()[:12]


# ---------- TF22-34: the file ----------


def test_tf22_34_a_csv_and_a_jsonl_join_alike(tmp_path: Path) -> None:
    skipped, passed, _ = _cases()
    rows = _suite_rows()
    a = _join(rows, _write(tmp_path / "v.csv", csv_text(
        ["case", "outcome", "score"], [[skipped, "fail", "0.25"], [passed, "pass", ""]])))
    b = _join(rows, _jsonl(tmp_path / "v.jsonl", [
        {"case": skipped, "outcome": "fail", "score": 0.25}, {"case": passed, "outcome": "pass"}]))
    assert a.rows == b.rows
    assert (a.read, a.by_case, a.by_input, a.unmatched) == (2, 2, 0, 0)


BAD_FILES: dict[str, tuple[str, str, str]] = {
    # name: (suffix, the faulty file, the control differing only in that clause)
    "unknown-column": (".csv", "case,outcome,grade\n{s},fail,A\n", "case,outcome\n{s},fail\n"),
    "unknown-key": (".jsonl", '{{"case": "{s}", "grade": "A"}}\n', '{{"case": "{s}", "outcome": "fail"}}\n'),
    "no-key": (".csv", "outcome\nfail\n", "case,outcome\n{s},fail\n"),
    "empty-key": (".csv", "case,outcome\n,fail\n", "case,outcome\n{s},fail\n"),
    "outcome-word": (".csv", "case,outcome\n{s},failed\n", "case,outcome\n{s},fail\n"),
    "score": (".csv", "case,score\n{s},high\n", "case,score\n{s},0.5\n"),
    "score-nan": (".jsonl", '{{"case": "{s}", "score": "NaN"}}\n', '{{"case": "{s}", "score": 0.5}}\n'),
    "kind": (".csv", "case,outcome,failure_kind\n{s},fail,oops\n", "case,outcome,failure_kind\n{s},fail,tool_error\n"),
    "scores-not-numbers": (".jsonl", '{{"case": "{s}", "scores": {{"r": "x"}}}}\n', '{{"case": "{s}", "scores": {{"r": 0.5}}}}\n'),
    "not-json": (".jsonl", '{{"case": "{s}"\n', '{{"case": "{s}", "outcome": "fail"}}\n'),
    "duplicate": (".csv", "case,outcome\n{s},fail\n{s},fail\n", "case,outcome\n{s},fail\n"),
    "empty": (".csv", "", "case,outcome\n{s},fail\n"),
    "header-only": (".csv", "case,outcome\n", "case,outcome\n{s},fail\n"),
}


@pytest.mark.parametrize("fault", list(BAD_FILES))
def test_tf22_34_a_file_that_is_not_one_is_refused(tmp_path: Path, fault: str) -> None:
    skipped, _, _ = _cases()
    suffix, bad, good = BAD_FILES[fault]
    rows = _suite_rows()
    control = _write(tmp_path / f"good{suffix}", good.format(s=skipped))
    assert _join(rows, control).by_case == 1
    with pytest.raises(Refusal):
        _join(rows, _write(tmp_path / f"bad{suffix}", bad.format(s=skipped)))


def test_tf22_34_a_file_of_another_kind_is_refused(tmp_path: Path) -> None:
    skipped, _, _ = _cases()
    rows = _suite_rows()
    assert _join(rows, _write(tmp_path / "v.csv", f"case,outcome\n{skipped},fail\n")).by_case == 1
    for name in ("v.json", "v.tsv", "v"):
        with pytest.raises(Refusal):
            _join(rows, _write(tmp_path / name, f"case,outcome\n{skipped},fail\n"))
    with pytest.raises(Refusal):
        _join(rows, tmp_path / "missing.csv")


def test_tf22_34_a_refusal_names_the_line(tmp_path: Path) -> None:
    skipped, passed, _ = _cases()
    path = _write(tmp_path / "v.csv", csv_text(["case", "outcome"], [[passed, "pass"], [skipped, "maybe"]]))
    with pytest.raises(Refusal) as e:
        _join(_suite_rows(), path)
    assert names(str(e.value), "3", "maybe", tmp=tmp_path)


# ---------- TF22-35: what a verdict does to a row ----------


def test_tf22_35_a_verdict_fills_an_unscored_try(tmp_path: Path) -> None:
    skipped, _, _ = _cases()
    joined = _join(_suite_rows(), _write(tmp_path / "v.csv", f"case,outcome\n{skipped},fail\n"))
    row = next(r for r in joined.rows if r.case == skipped)
    assert (row.outcome, row.result, row.error) == (MISSED, "fail", None)
    joined = _join(_suite_rows(), _write(tmp_path / "w.csv", f"case,outcome\n{skipped},pass\n"))
    row = next(r for r in joined.rows if r.case == skipped)
    assert (row.outcome, row.result, row.error) == (MET, "pass", None)


def test_tf22_35_rows_no_verdict_names_are_unchanged(tmp_path: Path) -> None:
    skipped, _, cases = _cases()
    rows = _suite_rows()
    joined = _join(rows, _write(tmp_path / "v.csv", f"case,outcome\n{skipped},fail\n"))
    assert [r.case for r in joined.rows] == cases
    assert [r for r in joined.rows if r.case != skipped] == [r for r in rows if r.case != skipped]


def test_tf22_35_a_verdict_that_agrees_changes_nothing(tmp_path: Path) -> None:
    _, passed, _ = _cases()
    rows = _suite_rows()
    joined = _join(rows, _write(tmp_path / "v.csv", f"case,outcome\n{passed},pass\n"))
    assert joined.rows == tuple(rows) or list(joined.rows) == rows
    assert joined.by_case == 1


def test_tf22_35_a_verdict_that_disagrees_is_refused_naming_the_case(tmp_path: Path) -> None:
    _, passed, _ = _cases()
    with pytest.raises(Refusal) as e:
        _join(_suite_rows(), _write(tmp_path / "v.csv", f"case,outcome\n{passed},fail\n"))
    assert names(str(e.value), passed)


def test_tf22_35_scores_feedback_score_and_kind_are_carried(tmp_path: Path) -> None:
    skipped, passed, _ = _cases()
    path = _jsonl(tmp_path / "v.jsonl", [
        {"case": skipped, "outcome": "fail", "failure_kind": "tool_error", "score": 0.0,
         "scores": {"reviewer": 0.0}, "feedback": {"thumb": "down", "note": "flaky"}},
        {"case": passed, "scores": {"reviewer": 1.0}, "feedback": {"reviewed": True}},
    ])
    joined = _join(_suite_rows(), path)
    s = next(r for r in joined.rows if r.case == skipped)
    p = next(r for r in joined.rows if r.case == passed)
    assert (s.failure_kind, s.score, dict(s.scores), dict(s.feedback)) == (
        "tool_error", 0.0, {"reviewer": 0.0}, {"thumb": "down", "note": "flaky"})
    assert (p.result, dict(p.scores), dict(p.feedback)) == ("pass", {"reviewer": 1.0}, {"reviewed": True})


def test_tf22_35_a_failure_kind_on_a_pass_is_refused(tmp_path: Path) -> None:
    skipped, passed, _ = _cases()
    rows = _suite_rows()
    ok = _write(tmp_path / "ok.csv", f"case,outcome,failure_kind\n{skipped},fail,crash\n")
    assert _join(rows, ok).by_case == 1
    with pytest.raises(Refusal):
        _join(rows, _write(tmp_path / "v.csv", f"case,failure_kind\n{passed},crash\n"))


# ---------- TF22-36 to TF22-39: matching ----------


def test_tf22_36_a_verdict_joins_every_repeat_of_its_case(tmp_path: Path) -> None:
    store = tmp_path / "s"
    case = "HumanEval/152@0.0"
    verdicts = _jsonl(tmp_path / "v.jsonl", [{"case": case, "feedback": {"reviewed": True}}])
    ran = trace_import("table", TABLE / "humaneval-a.csv", "--store", store, "--run", "v1",
                       *FLAGS["table"], "--verdicts", verdicts)
    assert ran.code == 0, ran.text
    held = [r for r in records(store, "v1")]
    mine = [r for r in held if r["signals"]["case"] == case]
    assert len(mine) == 32
    assert all(r["signals"]["feedback"] == {"reviewed": True} for r in mine)
    assert all(r["signals"]["feedback"] == {} for r in held if r["signals"]["case"] != case)


def _deepeval(tmp: Path, verdicts: Path, case: str = "name", run: str = "v1") -> Any:
    return trace_import("deepeval", DEEPEVAL / "humaneval-a.json.gz", "--store", tmp / "s", "--run", run,
                        "--metric", "Tests Passed", "--cut", "recorded", "--case", case,
                        "--verdicts", verdicts, "--json")


def test_tf22_37_a_verdict_with_no_case_match_joins_by_its_input(tmp_path: Path) -> None:
    from poisson_trace.ingest.verdicts import input_case

    inputs = deepeval_inputs()
    a, b, c = "HumanEval/152@0.0", "HumanEval/73@0.7", "HumanEval/1@0.0"
    verdicts = _jsonl(tmp_path / "v.jsonl", [
        {"input": inputs[a], "feedback": {"reviewed": True}},
        {"case": input_case(inputs[b]), "feedback": {"reviewed": True}},
        {"case": "not-a-case", "input": inputs[c], "feedback": {"reviewed": True}},
    ])
    ran = _deepeval(tmp_path, verdicts)
    assert ran.code == 0, ran.text
    held = records(tmp_path / "s", "v1")
    for case in (a, b, c):
        mine = [r for r in held if r["signals"]["case"] == case]
        assert mine and all(r["signals"]["feedback"] == {"reviewed": True} for r in mine)
    assert sum(1 for r in held if r["signals"]["feedback"]) == sum(
        1 for r in held if r["signals"]["case"] in (a, b, c))
    v = ran.json()["verdicts"]
    assert (v["rows"], v["by_case"], v["by_input"], v["unmatched"]) == (3, 0, 3, 0)


def test_tf22_37_a_case_match_comes_before_the_input(tmp_path: Path) -> None:
    inputs = deepeval_inputs()
    a, b = "HumanEval/152@0.0", "HumanEval/73@0.7"
    # the row names case a and carries b's input: it joins onto a alone
    verdicts = _jsonl(tmp_path / "v.jsonl", [{"case": a, "input": inputs[b], "feedback": {"r": 1.0}}])
    ran = _deepeval(tmp_path, verdicts)
    assert ran.code == 0, ran.text
    held = records(tmp_path / "s", "v1")
    assert {r["signals"]["case"] for r in held if r["signals"]["feedback"]} == {a}
    assert ran.json()["verdicts"]["by_case"] == 1


def test_tf22_37_the_unit_join_takes_the_readers_inputs(tmp_path: Path) -> None:
    from poisson_trace.ingest.verdicts import input_case

    inputs = deepeval_inputs()
    rows = [Row(case, MET, None, result="pass") for case in list(inputs)[:5]]
    keys = {case: input_case(inputs[case]) for case in inputs}
    target = rows[2].case
    path = _jsonl(tmp_path / "v.jsonl", [{"input": inputs[target], "feedback": {"r": 1.0}}])
    joined = _join(rows, path, keys)
    assert [dict(r.feedback) for r in joined.rows] == [{}, {}, {"r": 1.0}, {}, {}]
    with pytest.raises(Refusal):
        _join(rows, path, None)  # with no inputs known, the row matches nothing


def test_tf22_38_a_verdict_matching_two_cases_is_refused(tmp_path: Path) -> None:
    """Read by position, every try of a DeepEval test case is a case of its own, and its tries
    share one input: a verdict by that input would land on many cases."""
    inputs = deepeval_inputs()
    verdicts = _jsonl(tmp_path / "v.jsonl", [{"input": inputs["HumanEval/152@0.0"], "feedback": {"r": 1.0}}])
    # control: read by name, the same file joins onto one case
    ok = _deepeval(tmp_path / "ok", verdicts)
    assert ok.code == 0, ok.text
    ran = _deepeval(tmp_path, verdicts, case="position")
    sentence = plain_refusal(ran)
    assert names(sentence, "1", tmp=tmp_path)  # the verdict's line
    assert not (tmp_path / "s").exists() or tree(tmp_path / "s") == {}


def test_tf22_38_two_rows_for_one_input_are_refused(tmp_path: Path) -> None:
    inputs = deepeval_inputs()
    text = inputs["HumanEval/152@0.0"]
    verdicts = _jsonl(tmp_path / "v.jsonl", [{"input": text, "feedback": {"r": 1.0}},
                                             {"input": text, "feedback": {"r": 0.0}}])
    plain_refusal(_deepeval(tmp_path, verdicts))
    assert not (tmp_path / "s").exists() or tree(tmp_path / "s") == {}


def test_tf22_39_a_file_whose_rows_match_nothing_is_refused(tmp_path: Path) -> None:
    store = tmp_path / "s"
    verdicts = _write(tmp_path / "v.csv", "case,outcome\nno-such-case,fail\nnor-this,pass\n")
    sentence = plain_refusal(trace_import("junit", SUITE, "--store", store, "--run", "v1",
                                          "--verdicts", verdicts))
    assert names(sentence, "v.csv", tmp=tmp_path)
    assert not store.exists() or tree(store) == {}


def test_tf22_39_some_rows_matching_nothing_are_counted(tmp_path: Path) -> None:
    skipped, passed, _ = _cases()
    verdicts = _write(tmp_path / "v.csv", f"case,outcome\n{skipped},fail\n{passed},pass\nno-such-case,fail\n")
    ran = trace_import("junit", SUITE, "--store", tmp_path / "s", "--run", "v1", "--verdicts", verdicts, "--json")
    assert ran.code == 0, ran.text
    assert ran.json()["verdicts"] == {"name": "v.csv", "sha256": sha256_of(verdicts), "rows": 3,
                                      "by_case": 2, "by_input": 0, "unmatched": 1}


# ---------- TF22-40 and TF22-41: what the import says ----------


def test_tf22_40_the_import_says_what_was_joined(tmp_path: Path) -> None:
    skipped, _, _ = _cases()
    verdicts = _write(tmp_path / "grades.csv", f"case,outcome\n{skipped},fail\n")
    store = tmp_path / "s"
    plain = trace_import("junit", SUITE, "--store", store, "--run", "v1", "--verdicts", verdicts, "--plain")
    assert plain.code == 0, plain.text
    line = f"- verdicts: grades.csv · sha256 {sha256_of(verdicts)} · rows 1 · joined by case 1 · by input 0 · matched no case 0"
    lines = plain.out.splitlines()
    assert line in lines
    # it follows the file lines in "What was written"
    assert lines.index(line) == max(i for i, x in enumerate(lines) if x.startswith("- file: ")) + 1
    # the skipped test now has an outcome: 90 passed and 1 failed, none without
    assert "wrote run v1 to" in lines[0] and "90 passed, 1 failed" in lines[0]
    assert "with no outcome" not in lines[0]


def test_tf22_40_the_json_and_the_manifest_record_it(tmp_path: Path) -> None:
    skipped, _, _ = _cases()
    verdicts = _write(tmp_path / "grades.csv", f"case,outcome\n{skipped},fail\n")
    ran = trace_import("junit", SUITE, "--store", tmp_path / "s", "--run", "v1", "--verdicts", verdicts, "--json")
    assert ran.code == 0, ran.text
    block = {"name": "grades.csv", "sha256": sha256_of(verdicts), "rows": 1, "by_case": 1,
             "by_input": 0, "unmatched": 0}
    doc = ran.json()
    assert doc["verdicts"] == block
    assert doc["outcomes"] == {"met": 90, "missed": 1}
    assert doc["no_outcome"] == {}
    assert import_block(tmp_path / "s", "v1")["verdicts"] == block


def test_tf22_40_without_verdicts_the_import_is_as_before(tmp_path: Path) -> None:
    ran = trace_import("junit", SUITE, "--store", tmp_path / "s", "--run", "v1", "--json")
    assert ran.code == 0, ran.text
    assert "verdicts" not in ran.json()
    assert "verdicts" not in import_block(tmp_path / "s", "v1")


def test_tf22_41_verdicts_join_onto_a_folder_as_onto_its_files(tmp_path: Path) -> None:
    folder = junit_shards(tmp_path / "shards")
    case = junit_cases(folder / "junit-2.xml")[0][0]
    verdicts = _jsonl(tmp_path / "v.jsonl", [{"case": case, "score": 0.5, "feedback": {"r": 1.0}}])
    files = sorted(folder.iterdir())
    a = trace_import("junit", *files, "--store", tmp_path / "a", "--run", "v1", "--verdicts", verdicts, "--json")
    b = trace_import(folder, "--store", tmp_path / "b", "--run", "v1", "--verdicts", verdicts, "--json")
    assert a.code == b.code == 0, a.text + b.text
    assert b.out.replace(str(tmp_path / "b"), "<S>") == a.out.replace(str(tmp_path / "a"), "<S>")
    assert records(tmp_path / "b", "v1") == records(tmp_path / "a", "v1")


# ---------- TF22-43 and TF22-44: the store ----------


def test_tf22_43_prove_reads_a_joined_run_and_the_record_carries_the_verdict(tmp_path: Path) -> None:
    from poisson_prove.store import Store

    skipped, passed, _ = _cases()
    verdicts = _jsonl(tmp_path / "v.jsonl", [
        {"case": skipped, "outcome": "fail", "failure_kind": "tool_error", "score": 0.0,
         "scores": {"reviewer": 0.0}, "feedback": {"thumb": "down"}},
    ])
    plain_store, joined_store = tmp_path / "plain", tmp_path / "joined"
    assert trace_import("junit", SUITE, "--store", plain_store, "--run", "v1").code == 0
    ran = trace_import("junit", SUITE, "--store", joined_store, "--run", "v1", "--verdicts", verdicts)
    assert ran.code == 0, ran.text
    held = Store(joined_store)
    assert held.tally("v1").rows == 91 and held.tally("v1").no_outcome == 0
    before = {r["signals"]["case"]: r for r in records(plain_store, "v1")}
    after = {r["signals"]["case"]: r for r in records(joined_store, "v1")}
    s = after[skipped]
    assert (s["outcome"], s["error"]) == (MISSED, None)
    sig = s["signals"]
    assert (sig["outcome"], sig["failure_kind"], sig["score"], sig["scores"], sig["feedback"]) == (
        "fail", "tool_error", 0.0, {"reviewer": 0.0}, {"thumb": "down"})
    assert {c: r for c, r in after.items() if c != skipped} == {c: r for c, r in before.items() if c != skipped}


def test_tf22_44_the_verdicts_files_text_never_reaches_the_store(tmp_path: Path) -> None:
    """The file's ``input`` column and its path stay out of the store (IC7): only the joined
    values, and the file's name and digest in the manifest, are written."""
    import pyarrow.parquet as pq

    inputs = deepeval_inputs()
    case = "HumanEval/152@0.0"
    # the row names its case, so its input is never needed; it still must not be stored
    probe = "reviewer-probe-7f3a91 " + inputs[case]
    verdicts = _jsonl(tmp_path / "grades-7f3a91.jsonl", [{"case": case, "input": probe, "feedback": {"r": 1.0}}])
    ran = _deepeval(tmp_path, verdicts)
    assert ran.code == 0, ran.text
    store = tmp_path / "s"

    def holds(needle: str) -> list[str]:
        found = []
        for p in sorted(x for x in store.rglob("*") if x.is_file()):
            data = p.read_bytes()
            if p.suffix == ".parquet":
                data += json.dumps(pq.read_table(p).to_pylist(), default=str).encode()
            if needle.encode() in data:
                found.append(str(p))
        return found

    assert holds("grades-7f3a91.jsonl")  # control: the name is recorded, so the search reads the store
    assert holds("reviewer-probe-7f3a91") == []
    assert holds(str(tmp_path)) == []
