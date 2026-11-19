"""TF10-4 to TF10-14: the promptfoo reader on promptfoo 0.120.19's committed files (spec section
6.3's ``promptfoo`` item, R24; section 18.1.1 row 6; section 18.5.2's promptfoo row; the readings
in ``tf10_support``'s docstring, RD1, RD2 and RD4).

- TF10-4: each prompt of the JSON file, picked by its label or its number, is one run of four
  rows, one per test, met and missed as promptfoo's ``success`` says.
- TF10-5: one import is one prompt and one provider: a file of several prompts with none named
  is refused with the labels listed, a label or number the file lacks likewise; a file of one
  prompt needs none; a second provider is named by ``--provider`` and refused unnamed.
- TF10-6: the case is a named test variable or the test's position; a case in two rows is a
  repeat; a row without the variable is refused naming it; ``--case`` is required.
- TF10-7: ``--outcome score`` reads ``score`` at a cut, a score equal to the cut meeting it;
  without ``--cut`` the command line is wrong.
- TF10-8: the start is ``results.timestamp`` in the JSON file; the JSON Lines file has none, so
  it is ``--started`` or the file's time, said in the summary.
- TF10-9: the summary counts the file's rows per prompt and per provider, and ``declared`` names
  the case, the prompt by its label and the provider.
- TF10-10: the CSV is refused, pointing at the JSON export; the table reader refuses it too (RD1).
- TF10-11: the signals each row records, and those it does not (``None``, not zero).
- TF10-12: the failure kinds: the fixture's failed assertions are wrong answers; each assertion
  type of section 18.5.2 gives its kind; an error row has no outcome, is censored and takes its
  kind from its text.
- TF10-13: nothing of the prompt, the answer, another variable, an error or a grader's reason
  is written or printed.
- TF10-14: the JSON file and the JSON Lines file of one evaluation give the same records.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tf10_support import (
    PF_CSV, PF_JSON, PF_JSONL, PF_LABELS, STARTED, imported, pf_argv, pf_as_error, pf_assertion, pf_doc,
    pf_results, pf_row, recs, ref_kind_of, refused, stored_bytes, write_pf, write_pf_lines, wrong_line,
)
from tf21_support import run_import

CASES = ("q1", "q2", "q3", "q4")


def _by_case(root: Path, run: str) -> dict[str, list[str | None]]:
    from tf3_support import by_case, read_rows

    return by_case(read_rows(root, run))


def _expected(prompt_idx: int) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for r in sorted(pf_results(), key=lambda r: r["testIdx"]):
        if r["promptIdx"] == prompt_idx:
            out.setdefault(r["vars"]["case"], []).append("met" if r["success"] else "missed")
    return out


# ---------- TF10-4 ----------


@pytest.mark.parametrize("prompt", ["1", "2", PF_LABELS[0], PF_LABELS[1]])
def test_tf10_4_each_prompt_is_one_run_of_its_four_tests(tmp_path: Path, prompt: str) -> None:
    idx = 0 if prompt in ("1", PF_LABELS[0]) else 1
    data = imported(pf_argv(PF_JSON, tmp_path / "st", "v", prompt=prompt))
    assert data["tool"] == "promptfoo" and data["rows"] == 4 and data["cases"] == 4
    assert data["repeats"] == {"min": 1, "max": 1}
    got = _by_case(tmp_path / "st", "v")
    assert got == _expected(idx) == [{"q1": ["missed"], "q2": ["missed"], "q3": ["met"], "q4": ["met"]},
                                     {c: ["met"] for c in CASES}][idx]
    assert data["outcomes"] == {"met": sum(v == ["met"] for v in got.values()),
                                "missed": sum(v == ["missed"] for v in got.values())}
    assert data["no_outcome"] == {}


# ---------- TF10-5 ----------


def test_tf10_5_several_prompts_and_none_named_is_refused_with_the_labels(tmp_path: Path) -> None:
    line = refused(run_import(pf_argv(PF_JSON, tmp_path / "st", "v", prompt=None)))
    assert all(label in line for label in PF_LABELS), line
    assert "--prompt" in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("prompt", ["3", "0", "newest: {{text}}"])
def test_tf10_5_a_prompt_the_file_lacks_is_refused_with_the_labels(tmp_path: Path, prompt: str) -> None:
    line = refused(run_import(pf_argv(PF_JSON, tmp_path / "st", "v", prompt=prompt)))
    assert all(label in line for label in PF_LABELS), line
    assert not (tmp_path / "st").exists()


def _one_prompt(doc: dict[str, Any]) -> None:
    doc["results"]["prompts"] = doc["results"]["prompts"][:1]
    doc["results"]["results"] = [r for r in doc["results"]["results"] if r["promptIdx"] == 0]


@pytest.mark.parametrize("form", ["json", "jsonl"])
def test_tf10_5_a_file_of_one_prompt_needs_none_named(tmp_path: Path, form: str) -> None:
    if form == "json":
        path = write_pf(tmp_path / "one.json", _one_prompt)
    else:
        path = write_pf_lines(tmp_path / "one.jsonl", lambda rows: rows.__setitem__(slice(None), [r for r in rows if r["promptIdx"] == 0]))
    data = imported(pf_argv(path, tmp_path / "st", "v", "--started", STARTED, prompt=None))
    assert data["rows"] == 4 and data["declared"]["prompt"] == PF_LABELS[0]


def _two_providers(doc: dict[str, Any]) -> None:
    prompts = doc["results"]["prompts"]
    doc["results"]["prompts"] = prompts + [{**p, "provider": "echo-b"} for p in prompts]
    extra = []
    for r in doc["results"]["results"]:
        twin = json.loads(json.dumps(r))
        twin["provider"] = {"id": "echo-b", "label": "echo-b"}
        twin["id"] = r["id"] + "-b"
        twin["success"], twin["score"] = True, 1
        twin.pop("error", None)
        twin["failureReason"] = 0
        extra.append(twin)
    doc["results"]["results"] += extra


def test_tf10_5_a_second_provider_is_named_or_refused(tmp_path: Path) -> None:
    path = write_pf(tmp_path / "two.json", _two_providers)
    line = refused(run_import(pf_argv(path, tmp_path / "st", "v")))
    assert "echo" in line and "echo-b" in line and "--provider" in line, line
    assert not (tmp_path / "st").exists()
    data = imported(pf_argv(path, tmp_path / "st", "b", "--provider", "echo-b"))
    assert data["rows"] == 4 and data["outcomes"] == {"met": 4, "missed": 0}
    assert data["declared"]["provider"] == "echo-b"
    data = imported(pf_argv(path, tmp_path / "st", "a", "--provider", "echo"))
    assert data["outcomes"] == {"met": 2, "missed": 2}
    line = refused(run_import(pf_argv(path, tmp_path / "st", "c", "--provider", "other")))
    assert "echo" in line and "echo-b" in line, line


# ---------- TF10-6 ----------


def test_tf10_6_the_case_is_a_variable_or_the_test_s_position(tmp_path: Path) -> None:
    imported(pf_argv(PF_JSON, tmp_path / "st", "by-var", case="var:case"))
    assert sorted(_by_case(tmp_path / "st", "by-var")) == list(CASES)
    data = imported(pf_argv(PF_JSON, tmp_path / "st", "by-test", case="test"))
    assert sorted(_by_case(tmp_path / "st", "by-test")) == [f"test:{i}" for i in range(4)]
    assert data["declared"]["case"] == "test"
    by_test = _by_case(tmp_path / "st", "by-test")
    assert [by_test[f"test:{i}"] for i in range(4)] == [_expected(0)[c] for c in CASES]


def test_tf10_6_a_case_in_two_rows_is_a_repeat_in_the_order_read(tmp_path: Path) -> None:
    def same(doc: dict[str, Any]) -> None:
        for r in doc["results"]["results"]:
            if r["promptIdx"] == 0 and r["testIdx"] == 2:
                r["vars"]["case"] = "q1"
    path = write_pf(tmp_path / "rep.json", same)
    data = imported(pf_argv(path, tmp_path / "st", "v"))
    assert data["cases"] == 3 and data["repeats"] == {"min": 1, "max": 2}
    # the order read is the file's: q1's test 0 (missed) is read before test 2 (met)
    order = [r for r in pf_results(json.loads(path.read_text())) if r["promptIdx"] == 0 and r["vars"]["case"] == "q1"]
    assert _by_case(tmp_path / "st", "v")["q1"] == ["met" if r["success"] else "missed" for r in order]


def test_tf10_6_a_row_without_the_variable_is_refused_naming_it(tmp_path: Path) -> None:
    line = refused(run_import(pf_argv(PF_JSON, tmp_path / "st", "v", case="var:ticket")))
    assert "ticket" in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("case", [None, "case", "var:", "position"])
def test_tf10_6_case_is_required_and_takes_two_forms(tmp_path: Path, case: str | None) -> None:
    wrong_line(run_import(pf_argv(PF_JSON, tmp_path / "st", "v", case=case)))
    assert not (tmp_path / "st").exists()


# ---------- TF10-7 ----------


@pytest.mark.parametrize("cut, side, missed", [("0.5", "--below", 2), ("1", "--below", 2), ("0", "--below", 0),
                                               ("0", "--above", 2), ("0.5", "--above", 2)])
def test_tf10_7_score_at_a_cut(tmp_path: Path, cut: str, side: str, missed: int) -> None:
    data = imported(pf_argv(PF_JSON, tmp_path / "st", "v", "--outcome", "score", "--cut", cut, side))
    scores = [float(r["score"]) for r in pf_results() if r["promptIdx"] == 0]
    c = float(cut)
    want = sum(1 for s in scores if (s < c if side == "--below" else s > c))
    assert want == missed and data["outcomes"].get("missed", 0) == missed


@pytest.mark.parametrize("extra", [["--outcome", "score"], ["--outcome", "score", "--cut", "0.5"],
                                   ["--outcome", "pass"], ["--cut", "0.5", "--below"]])
def test_tf10_7_a_score_outcome_needs_its_cut_and_side(tmp_path: Path, extra: list[str]) -> None:
    wrong_line(run_import(pf_argv(PF_JSON, tmp_path / "st", "v", *extra)))
    assert not (tmp_path / "st").exists()


# ---------- TF10-8 ----------


def test_tf10_8_the_json_file_s_start_is_its_timestamp(tmp_path: Path) -> None:
    data = imported(pf_argv(PF_JSON, tmp_path / "st", "v"))
    assert pf_doc()["results"]["timestamp"] == "2026-10-07T04:22:52.124Z"
    assert data["started"]["from"] == "file"
    assert data["started"]["at"] in ("2026-10-07T04:22:52.124Z", "2026-10-07T04:22:52.124000Z")


def test_tf10_8_the_json_lines_file_starts_when_given_or_at_its_file_time(tmp_path: Path) -> None:
    given = imported(pf_argv(PF_JSONL, tmp_path / "st", "given", "--started", STARTED))
    assert given["started"] == {"at": STARTED, "from": "given"}
    copy = tmp_path / "results.jsonl"
    copy.write_bytes(PF_JSONL.read_bytes())
    os.utime(copy, (1_790_000_000, 1_790_000_000))
    data = imported(pf_argv(copy, tmp_path / "st", "file"))
    assert data["started"]["from"] == "file time"
    text = run_import(pf_argv(copy, tmp_path / "st2", "file"))
    assert text.code == 0 and "when its file was written or copied" in text.out, text.out


# ---------- TF10-9 ----------


def test_tf10_9_the_summary_counts_rows_per_prompt_and_provider(tmp_path: Path) -> None:
    data = imported(pf_argv(PF_JSON, tmp_path / "st", "v", prompt="2"))
    counts = data["counts"]
    for number, label in ((1, PF_LABELS[0]), (2, PF_LABELS[1])):
        assert any(label in k and str(number) in k.replace(label, "") and v == 4 for k, v in counts.items()), counts
    assert any("echo" in k and v == 8 for k, v in counts.items()), counts
    declared = data["declared"]
    assert declared["case"] == "var:case" and declared["prompt"] == PF_LABELS[1] and declared["provider"] == "echo"
    text = run_import(pf_argv(PF_JSON, tmp_path / "st2", "v", prompt="2"))
    assert text.code == 0 and all(label in text.out for label in PF_LABELS), text.out


# ---------- TF10-10 ----------


def test_tf10_10_the_csv_is_refused_pointing_at_the_json_export(tmp_path: Path) -> None:
    line = refused(run_import(pf_argv(PF_CSV, tmp_path / "st", "v")))
    assert "results.csv" in line and "-o results.json" in line, line
    assert not (tmp_path / "st").exists()


def test_tf10_10_the_table_reader_refuses_the_csv_for_its_repeated_columns(tmp_path: Path) -> None:
    argv = ["table", str(PF_CSV), "--store", str(tmp_path / "st"), "--run", "v", "--case-column", "case",
            "--outcome-column", "Status", "--failed", "FAIL", "--started", STARTED]
    line = refused(run_import(argv))
    assert "2 columns named Status" in line, line


# ---------- TF10-11 ----------


def _signals_of(r: dict[str, Any]) -> dict[str, Any]:
    usage = r["response"]["tokenUsage"]
    return {
        "wall_time_s": r["latencyMs"] / 1000, "input_chars": len(r["prompt"]["raw"]),
        "output_chars": len(r["response"]["output"]), "input_tokens": usage["prompt"],
        "output_tokens": usage["completion"], "total_tokens": usage["total"],
        "cached_tokens": usage.get("cached"), "reasoning_tokens": (usage.get("completionDetails") or {}).get("reasoning"),
        "cost_usd": float(r["response"]["cost"]), "score": float(r["score"]), "scores": dict(r["namedScores"]),
    }


@pytest.mark.parametrize("prompt", ["1", "2"])
def test_tf10_11_the_signals_each_row_records(tmp_path: Path, prompt: str) -> None:
    imported(pf_argv(PF_JSON, tmp_path / "st", "v", prompt=prompt))
    want = {r["vars"]["case"]: _signals_of(r) for r in pf_results() if r["promptIdx"] == int(prompt) - 1}
    for rec in recs(tmp_path / "st", "v"):
        w = want[rec["case"]]
        for key, value in w.items():
            assert rec[key] == pytest.approx(value) if isinstance(value, float) else rec[key] == value, (rec["case"], key, rec[key], value)
        assert rec["outcome"] == ("pass" if rec["score"] == 1.0 else "fail")


def test_tf10_11_zero_tokens_are_recorded_and_absent_ones_are_not(tmp_path: Path) -> None:
    imported(pf_argv(PF_JSON, tmp_path / "st", "v"))
    for rec in recs(tmp_path / "st", "v"):
        assert rec["input_tokens"] == 0 and rec["output_tokens"] == 0 and rec["total_tokens"] == 0
        assert rec["cost_usd"] == 0.0
        assert rec["cached_tokens"] is None and rec["reasoning_tokens"] is None
        for name in ("working_time_s", "ttft_s", "steps", "horizon", "llm_calls", "retries",
                     "tool_calls", "tool_call_count", "tool_error_count", "error_type"):
            assert rec[name] is None, name
        assert rec["feedback"] == {} and rec["signals"] == []
        assert rec["wall_time_s"] is not None and rec["wall_time_s"] > 0


# ---------- TF10-12 ----------


def test_tf10_12_the_fixture_s_failures_are_wrong_answers(tmp_path: Path) -> None:
    imported(pf_argv(PF_JSON, tmp_path / "st", "v"))
    got = {r["case"]: r["failure_kind"] for r in recs(tmp_path / "st", "v")}
    assert got == {"q1": "wrong_answer", "q2": "wrong_answer", "q3": None, "q4": None}
    assert all(r["failure_kind"] == ref_kind_of(r) for r in recs(tmp_path / "st", "v"))


ASSERTIONS = {
    "is-json": "format_error", "is-xml": "format_error", "is-sql": "format_error",
    "is-valid-function-call": "format_error", "regex": "format_error", "is-refusal": "abstained",
    "guardrails": "guardrail_blocked", "moderation": "guardrail_blocked", "function-call": "tool_error",
    "context-recall": "retrieval_error", "context-relevance": "retrieval_error", "equals": "wrong_answer",
    "llm-rubric": "wrong_answer",
}


@pytest.mark.parametrize("assertion", list(ASSERTIONS))
def test_tf10_12_each_failed_assertion_type_gives_its_kind(tmp_path: Path, assertion: str) -> None:
    path = write_pf(tmp_path / "a.json", lambda doc: pf_assertion(pf_row(doc, 0, 0), assertion))
    imported(pf_argv(path, tmp_path / "st", "v"))
    got = {r["case"]: (r["outcome"], r["failure_kind"]) for r in recs(tmp_path / "st", "v")}
    assert got["q1"] == ("fail", ASSERTIONS[assertion]) and got["q2"] == ("fail", "wrong_answer")


ERRORS = {
    "Request timed out after 30000 ms": "timeout", "connect ETIMEDOUT 10.0.0.1:443": "timeout",
    "API error: 429 Too Many Requests": "rate_limit", "Provider rate limit reached": "rate_limit",
    "This model's maximum context length is 8192 tokens (context_length_exceeded)": "context_overflow",
    "finish_reason max_tokens reached": "context_overflow", "Unexpected token < in JSON at position 0": "crash",
}


@pytest.mark.parametrize("text", list(ERRORS))
def test_tf10_12_an_error_row_has_no_outcome_and_its_kind_from_its_text(tmp_path: Path, text: str) -> None:
    path = write_pf(tmp_path / "e.json", lambda doc: pf_as_error(pf_row(doc, 0, 2), text))
    data = imported(pf_argv(path, tmp_path / "st", "v"))
    assert data["rows"] == 4 and data["no_outcome"] == {"error": 1}
    assert data["outcomes"] == {"met": 1, "missed": 2}
    rec = next(r for r in recs(tmp_path / "st", "v") if r["case"] == "q3")
    assert rec["outcome"] == "censored" and rec["failure_kind"] == ERRORS[text]
    assert ("over_budget" in rec["signals"]) == (ERRORS[text] in ("timeout", "context_overflow"))
    from tf3_support import read_rows

    row = next(r for r in read_rows(tmp_path / "st", "v") if r["case"] == "q3")
    assert row["outcome"] is None and row["error"] == "error"
    blob = stored_bytes(tmp_path / "st")
    assert text.encode("utf-8") not in blob and text[:12].encode("utf-8") not in blob
    printed = run_import(pf_argv(path, tmp_path / "st2", "v"))
    assert printed.code == 0 and text not in printed.out + printed.err


def test_tf10_12_a_file_of_error_rows_only_writes_nothing(tmp_path: Path) -> None:
    def all_errors(doc: dict[str, Any]) -> None:
        for r in doc["results"]["results"]:
            if r["promptIdx"] == 0:
                pf_as_error(r, "Request timed out")
    path = write_pf(tmp_path / "e.json", all_errors)
    line = refused(run_import(pf_argv(path, tmp_path / "st", "v")))
    # the import's own sentence for rows none of which has an outcome
    assert "none of the 4 rows read has an outcome" in line, line
    assert not (tmp_path / "st" / "v").exists()


# ---------- TF10-13 ----------

SENTINELS = ("quick brown fox", "jumps over", "lazy dog", "banana split", "Expected output to contain",
             "All assertions passed", "8474fcf7-080b-4006-b2de-2b57b237d522")


@pytest.mark.parametrize("path", [PF_JSON, PF_JSONL], ids=["json", "jsonl"])
def test_tf10_13_no_content_is_written_or_printed(tmp_path: Path, path: Path) -> None:
    printed = []
    for prompt in ("1", "2"):
        for json_out in (True, False):
            argv = pf_argv(path, tmp_path / f"st-{prompt}-{json_out}", "v", "--started", STARTED, prompt=prompt)
            result = run_import([*argv, "--json"] if json_out else argv)
            assert result.code == 0, result.err
            printed.append(result.out + result.err)
            blob = stored_bytes(tmp_path / f"st-{prompt}-{json_out}")
            for needle in SENTINELS:
                assert needle.encode("utf-8") not in blob, (needle, prompt)
    for text in printed:
        for needle in SENTINELS:
            assert needle not in text, needle


# ---------- TF10-14 ----------


@pytest.mark.parametrize("prompt", ["1", "2"])
def test_tf10_14_the_json_and_json_lines_files_give_the_same_records(tmp_path: Path, prompt: str) -> None:
    a = imported(pf_argv(PF_JSON, tmp_path / "st", "a", "--started", STARTED, prompt=prompt))
    b = imported(pf_argv(PF_JSONL, tmp_path / "st", "b", "--started", STARTED, prompt=prompt))
    assert recs(tmp_path / "st", "a") == recs(tmp_path / "st", "b")
    for key in ("rows", "cases", "repeats", "outcomes", "no_outcome", "declared"):
        assert a[key] == b[key], key
