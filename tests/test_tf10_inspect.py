"""TF10-15 to TF10-25: the Inspect reader on inspect_ai 0.3.277's committed logs (spec section
6.3's ``inspect`` item, R25; section 18.1.1 row 7; section 18.5.2's Inspect AI row; the readings
in ``tf10_support``'s docstring, RD4).

- TF10-15: the ``.json`` log: a sample is a row, its case its ``id``, its epochs its repeats in
  epoch order, ``C`` met and ``I`` missed.
- TF10-16: the ``.eval`` log, its members Zstandard-compressed, read the same way.
- TF10-17: without the ``zstandard`` package a ``.eval`` is refused in the spec's one line; a log
  over 200 MB is refused naming its size, before it is read.
- TF10-18: ``P`` and ``N`` are missed and any other letter refused with the values listed; a
  number at a cut; declared failing values.
- TF10-19: ``--scorer`` is required, the scorers listed, when a sample holds several scores; the
  one read is named.
- TF10-20: a log whose status is ``error`` is refused with its message's first line; a sample
  with an error has no outcome, is censored, and its text is kept nowhere.
- TF10-21: the start is ``eval.created``; the model, the task and the scorer are declared.
- TF10-22: the signals each sample records, and those it does not.
- TF10-23: the failure kinds: wrong answers on the fixture; limits, stop reasons and tool
  errors as section 18.5.2 maps them.
- TF10-24: nothing of the input, the target, the messages, the output, the events or a score's
  answer or explanation is written or printed.
- TF10-25: a ``.json`` log and the ``.eval`` holding the same log give the same records.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from tf10_support import (
    IN_EVAL, IN_JSON, STARTED, ZSTD_REFUSAL, eval_samples, imported, in_argv, in_doc, letter_float,
    recs, ref_kind_of, refused, sample_of, stored_bytes, write_eval, write_in, wrong_line,
)
from tf21_support import run_import


def _by_case(root: Path, run: str) -> dict[str, list[str | None]]:
    from tf3_support import by_case, read_rows

    return by_case(read_rows(root, run))


def _letters(samples: list[dict[str, Any]], scorer: str = "includes") -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for s in sorted(samples, key=lambda s: (str(s["id"]), s["epoch"])):
        out.setdefault(str(s["id"]), []).append("met" if s["scores"][scorer]["value"] == "C" else "missed")
    return out


def _edit_sample(sid: str, epoch: int, edit: Any) -> Any:
    def apply(doc: dict[str, Any]) -> None:
        edit(sample_of(doc, sid, epoch))
    return apply


# ---------- TF10-15 ----------


def test_tf10_15_the_json_log_is_one_row_per_sample_and_epoch(tmp_path: Path) -> None:
    data = imported(in_argv(IN_JSON, tmp_path / "st", "new"))
    assert data["tool"] == "inspect" and data["rows"] == 6 and data["cases"] == 3
    assert data["repeats"] == {"min": 2, "max": 2}
    got = _by_case(tmp_path / "st", "new")
    assert got == _letters(in_doc()["samples"]) == {"q1": ["met", "met"], "q2": ["met", "met"], "q3": ["met", "missed"]}
    assert data["outcomes"] == {"met": 5, "missed": 1} and data["no_outcome"] == {}


def test_tf10_15_epochs_are_repeats_in_epoch_order_whatever_the_order_written(tmp_path: Path) -> None:
    path = write_in(tmp_path / "rev.json", lambda doc: doc["samples"].reverse())
    imported(in_argv(path, tmp_path / "st", "rev"))
    assert _by_case(tmp_path / "st", "rev")["q3"] == ["met", "missed"]
    reps = {(r["case"], r["repeat"]): r["outcome"] for r in recs(tmp_path / "st", "rev")}
    assert reps[("q3", 0)] == "pass" and reps[("q3", 1)] == "fail"


def test_tf10_15_a_numeric_sample_id_is_its_text(tmp_path: Path) -> None:
    def numeric(doc: dict[str, Any]) -> None:
        for s in doc["samples"]:
            s["id"] = int(s["id"][1:])
    path = write_in(tmp_path / "n.json", numeric)
    imported(in_argv(path, tmp_path / "st", "n"))
    assert sorted(_by_case(tmp_path / "st", "n")) == ["1", "2", "3"]


# ---------- TF10-16 ----------


def test_tf10_16_the_eval_log_is_read_from_its_compressed_members(tmp_path: Path) -> None:
    data = imported(in_argv(IN_EVAL, tmp_path / "st", "old"))
    assert data["rows"] == 6 and data["cases"] == 3 and data["repeats"] == {"min": 2, "max": 2}
    got = _by_case(tmp_path / "st", "old")
    assert got == _letters(eval_samples()) == {"q1": ["met", "met"], "q2": ["missed", "met"], "q3": ["missed", "missed"]}
    assert data["outcomes"] == {"met": 3, "missed": 3}


# ---------- TF10-17 ----------


def test_tf10_17_without_zstandard_a_eval_is_refused_in_one_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "zstandard", None)
    result = run_import(in_argv(IN_EVAL, tmp_path / "st", "old"))
    assert refused(result) == ZSTD_REFUSAL
    assert not (tmp_path / "st").exists()
    # the .json log needs no package beyond the standard library
    assert run_import(in_argv(IN_JSON, tmp_path / "st", "new")).code == 0


def test_tf10_17_a_log_over_200_mb_is_refused_naming_its_size(tmp_path: Path) -> None:
    big = tmp_path / "big.eval"
    with open(big, "wb") as f:
        f.truncate(201 * 1024 * 1024)
    line = refused(run_import(in_argv(big, tmp_path / "st", "big")))
    assert "big.eval" in line and "MB" in line and "200" in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("kind", ["not a zip", "a zip with no header", "a member not JSON"])
def test_tf10_17_a_damaged_eval_is_refused_naming_the_file(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "bad.eval"
    if kind == "not a zip":
        path.write_bytes(b"PK\x03\x04 not really a zip")
    elif kind == "a zip with no header":
        write_eval(path, members=lambda raw: raw.pop("header.json"))
    else:
        write_eval(path, members=lambda raw: raw.__setitem__("samples/q1_epoch_1.json", b"{not json"))
    line = refused(run_import(in_argv(path, tmp_path / "st", "bad")))
    assert "bad.eval" in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF10-18 ----------


@pytest.mark.parametrize("letter", ["P", "N"])
def test_tf10_18_partial_and_no_answer_are_missed(tmp_path: Path, letter: str) -> None:
    path = write_in(tmp_path / "p.json", _edit_sample("q1", 1, lambda s: s["scores"]["includes"].__setitem__("value", letter)))
    imported(in_argv(path, tmp_path / "st", "v"))
    assert _by_case(tmp_path / "st", "v")["q1"] == ["missed", "met"]
    rec = next(r for r in recs(tmp_path / "st", "v") if r["case"] == "q1" and r["repeat"] == 0)
    assert rec["score"] == letter_float(letter) and rec["scores"] == {"includes": letter_float(letter)}


def test_tf10_18_another_value_is_refused_with_the_values_listed(tmp_path: Path) -> None:
    path = write_in(tmp_path / "x.json", _edit_sample("q2", 2, lambda s: s["scores"]["includes"].__setitem__("value", "maybe")))
    line = refused(run_import(in_argv(path, tmp_path / "st", "v")))
    assert "maybe" in line and "C" in line and "I" in line, line
    assert not (tmp_path / "st").exists()


def _numeric(doc: dict[str, Any]) -> None:
    for s in doc["samples"]:
        s["scores"]["includes"]["value"] = letter_float(s["scores"]["includes"]["value"])


@pytest.mark.parametrize("cut, side, missed", [("0.5", "--below", 1), ("1", "--below", 1), ("0", "--below", 0),
                                               ("0.5", "--above", 5)])
def test_tf10_18_a_number_at_a_cut(tmp_path: Path, cut: str, side: str, missed: int) -> None:
    path = write_in(tmp_path / "num.json", _numeric)
    data = imported(in_argv(path, tmp_path / "st", "v", "--outcome", "score", "--cut", cut, side))
    assert data["outcomes"].get("missed", 0) == missed


def test_tf10_18_letters_are_not_a_number_at_a_cut(tmp_path: Path) -> None:
    line = refused(run_import(in_argv(IN_JSON, tmp_path / "st", "v", "--outcome", "score", "--cut", "0.5", "--below")))
    assert "C" in line, line


@pytest.mark.parametrize("failed, missed", [(["I"], 1), (["C"], 5), (["C", "I"], 6)])
def test_tf10_18_declared_values_that_mean_failure(tmp_path: Path, failed: list[str], missed: int) -> None:
    flags = [w for v in failed for w in ("--failed", v)]
    data = imported(in_argv(IN_JSON, tmp_path / "st", "v", "--outcome", "value", *flags))
    assert data["outcomes"].get("missed", 0) == missed


@pytest.mark.parametrize("extra", [["--outcome", "score"], ["--outcome", "score", "--cut", "0.5"],
                                   ["--outcome", "value"], ["--outcome", "letters"]])
def test_tf10_18_an_outcome_form_without_its_flags_is_a_wrong_command_line(tmp_path: Path, extra: list[str]) -> None:
    wrong_line(run_import(in_argv(IN_JSON, tmp_path / "st", "v", *extra)))
    assert not (tmp_path / "st").exists()


# ---------- TF10-19 ----------


def _two_scorers(doc: dict[str, Any]) -> None:
    for s in doc["samples"]:
        s["scores"]["exact"] = {"value": "I", "answer": "x", "explanation": "x", "history": []}


def test_tf10_19_several_scores_need_the_scorer_named(tmp_path: Path) -> None:
    path = write_in(tmp_path / "two.json", _two_scorers)
    line = refused(run_import(in_argv(path, tmp_path / "st", "v")))
    assert "includes" in line and "exact" in line and "--scorer" in line, line
    assert not (tmp_path / "st").exists()
    data = imported(in_argv(path, tmp_path / "st", "v", "--scorer", "exact"))
    assert data["outcomes"] == {"met": 0, "missed": 6} and data["declared"]["scorer"] == "exact"
    data = imported(in_argv(path, tmp_path / "st", "w", "--scorer", "includes"))
    assert data["outcomes"] == {"met": 5, "missed": 1} and data["declared"]["scorer"] == "includes"
    rec = recs(tmp_path / "st", "w")[0]
    assert set(rec["scores"]) == {"includes", "exact"}
    line = refused(run_import(in_argv(path, tmp_path / "st", "x", "--scorer", "f1")))
    assert "includes" in line and "exact" in line, line


def test_tf10_19_one_scorer_is_named_without_being_asked(tmp_path: Path) -> None:
    data = imported(in_argv(IN_JSON, tmp_path / "st", "v"))
    assert data["declared"]["scorer"] == "includes"
    text = run_import(in_argv(IN_JSON, tmp_path / "st2", "v"))
    assert text.code == 0 and "includes" in text.out, text.out


# ---------- TF10-20 ----------


def test_tf10_20_a_log_that_errored_is_refused_with_its_message_s_first_line(tmp_path: Path) -> None:
    def errored(doc: dict[str, Any]) -> None:
        doc["status"] = "error"
        doc["error"] = {"message": "RuntimeError: the sandbox died\nwhile starting q2", "traceback": "Traceback (most recent call last):\n  x",
                        "traceback_ansi": "x"}
    path = write_in(tmp_path / "err.json", errored)
    line = refused(run_import(in_argv(path, tmp_path / "st", "v")))
    assert "RuntimeError: the sandbox died" in line and "while starting" not in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("message, kind", [("ConnectionError: sandbox lost", "crash"),
                                           ("TimeoutError: the model timed out", "timeout"),
                                           ("RateLimitError: 429 Too Many Requests", "rate_limit")])
def test_tf10_20_a_sample_that_errored_has_no_outcome(tmp_path: Path, message: str, kind: str) -> None:
    def errored(s: dict[str, Any]) -> None:
        s["error"] = {"message": message, "traceback": "Traceback: secret frame", "traceback_ansi": "x"}
    path = write_in(tmp_path / "e.json", _edit_sample("q2", 1, errored))
    data = imported(in_argv(path, tmp_path / "st", "v"))
    assert data["rows"] == 6 and data["no_outcome"] == {"error": 1}
    rec = next(r for r in recs(tmp_path / "st", "v") if r["case"] == "q2" and r["repeat"] == 0)
    assert rec["outcome"] == "censored" and rec["failure_kind"] == kind
    blob = stored_bytes(tmp_path / "st")
    assert message.encode() not in blob and b"secret frame" not in blob and message.split(":")[1].strip().encode() not in blob
    printed = run_import(in_argv(path, tmp_path / "st2", "v"))
    assert printed.code == 0 and message not in printed.out + printed.err


# ---------- TF10-21 ----------


def test_tf10_21_the_start_is_eval_created_and_the_eval_is_declared(tmp_path: Path) -> None:
    new = imported(in_argv(IN_JSON, tmp_path / "st", "new"))
    old = imported(in_argv(IN_EVAL, tmp_path / "st", "old"))
    assert in_doc()["eval"]["created"] == "2026-10-07T04:23:51+00:00"
    assert new["started"] == {"at": "2026-10-07T04:23:51Z", "from": "file"}
    assert old["started"] == {"at": "2026-10-07T04:23:47Z", "from": "file"}
    for data in (new, old):
        declared = data["declared"]
        assert declared["model"] == "mockllm/model" and declared["task"] == "trace_fixture" and declared["scorer"] == "includes"
    given = imported(in_argv(IN_JSON, tmp_path / "st", "given", "--started", STARTED))
    assert given["started"] == {"at": STARTED, "from": "given"}


# ---------- TF10-22 ----------


def _want(s: dict[str, Any]) -> dict[str, Any]:
    usage = list(s["model_usage"].values())
    return {
        "wall_time_s": s["total_time"], "working_time_s": s["working_time"], "input_chars": len(s["input"]),
        "output_chars": len(s["output"]["completion"]),
        "input_tokens": sum(u["input_tokens"] for u in usage), "output_tokens": sum(u["output_tokens"] for u in usage),
        "total_tokens": sum(u["total_tokens"] for u in usage),
        "llm_calls": sum(1 for e in s["events"] if e["event"] == "model"),
        "score": letter_float(s["scores"]["includes"]["value"]),
        "scores": {"includes": letter_float(s["scores"]["includes"]["value"])},
    }


@pytest.mark.parametrize("which", ["json", "eval"])
def test_tf10_22_the_signals_each_sample_records(tmp_path: Path, which: str) -> None:
    path, samples = (IN_JSON, in_doc()["samples"]) if which == "json" else (IN_EVAL, eval_samples())
    imported(in_argv(path, tmp_path / "st", "v"))
    want = {(str(s["id"]), s["epoch"] - 1): _want(s) for s in samples}
    for rec in recs(tmp_path / "st", "v"):
        w = want[(rec["case"], rec["repeat"])]
        for key, value in w.items():
            assert rec[key] == (pytest.approx(value) if isinstance(value, float) else value), (rec["case"], key)
        assert rec["llm_calls"] == 1 and rec["input_tokens"] == 3
        assert rec["tool_calls"] == [] and rec["tool_call_count"] == 0 and rec["tool_error_count"] == 0
        for name in ("ttft_s", "steps", "horizon", "retries", "cost_usd", "cached_tokens", "reasoning_tokens"):
            assert rec[name] is None, name
        assert rec["feedback"] == {}


def test_tf10_22_cached_and_reasoning_tokens_are_read_where_inspect_records_them(tmp_path: Path) -> None:
    def more(s: dict[str, Any]) -> None:
        s["model_usage"]["mockllm/model"].update({"input_tokens_cache_read": 2, "reasoning_tokens": 0})
        s["model_usage"]["other/model"] = {"input_tokens": 10, "output_tokens": 1, "total_tokens": 11,
                                          "input_tokens_cache_read": 5}
    path = write_in(tmp_path / "u.json", _edit_sample("q1", 1, more))
    imported(in_argv(path, tmp_path / "st", "v"))
    rec = next(r for r in recs(tmp_path / "st", "v") if r["case"] == "q1" and r["repeat"] == 0)
    assert (rec["input_tokens"], rec["output_tokens"], rec["total_tokens"]) == (13, 7, 20)
    assert rec["cached_tokens"] == 7 and rec["reasoning_tokens"] == 0


# ---------- TF10-23 ----------


def test_tf10_23_the_fixture_s_failures_are_wrong_answers(tmp_path: Path) -> None:
    imported(in_argv(IN_EVAL, tmp_path / "st", "old"))
    rs = recs(tmp_path / "st", "old")
    kinds = sorted((r["case"], r["repeat"], r["failure_kind"]) for r in rs)
    assert kinds == [("q1", 0, None), ("q1", 1, None), ("q2", 0, "wrong_answer"), ("q2", 1, None),
                     ("q3", 0, "wrong_answer"), ("q3", 1, "wrong_answer")]
    assert all(r["failure_kind"] == ref_kind_of(r) for r in rs)
    assert all(r["signals"] == [] for r in rs)


def _tool_event(function: str, error: dict[str, Any] | None, working: float = 0.25) -> dict[str, Any]:
    return {"event": "tool", "type": "function", "id": f"call-{function}", "function": function, "arguments": {"q": "secret argument"},
            "result": "secret tool output", "error": error, "working_time": working, "timestamp": "2026-10-07T04:23:51.43+00:00",
            "working_start": 0.002, "pending": False}


LIMITS = {"time": "timeout", "working": "timeout", "token": "context_overflow", "cost": "context_overflow",
          "message": "step_limit"}


@pytest.mark.parametrize("limit", list(LIMITS))
def test_tf10_23_a_limit_gives_its_kind(tmp_path: Path, limit: str) -> None:
    path = write_in(tmp_path / "l.json", _edit_sample("q3", 2, lambda s: s.__setitem__("limit", {"type": limit, "limit": 10})))
    imported(in_argv(path, tmp_path / "st", "v"))
    rec = next(r for r in recs(tmp_path / "st", "v") if r["case"] == "q3" and r["repeat"] == 1)
    assert rec["outcome"] == "fail" and rec["failure_kind"] == LIMITS[limit]
    assert "over_budget" in rec["signals"]


def test_tf10_23_a_message_limit_with_a_retry_storm_is_a_loop(tmp_path: Path) -> None:
    def storm(s: dict[str, Any]) -> None:
        s["limit"] = {"type": "message", "limit": 10}
        s["events"] += [_tool_event("search", {"type": "unknown", "message": "no"}), _tool_event("search", {"type": "unknown", "message": "no"}),
                        _tool_event("search", None)]
    path = write_in(tmp_path / "s.json", _edit_sample("q3", 2, storm))
    imported(in_argv(path, tmp_path / "st", "v"))
    rec = next(r for r in recs(tmp_path / "st", "v") if r["case"] == "q3" and r["repeat"] == 1)
    assert rec["failure_kind"] == "loop_detected" and "retry_storm" in rec["signals"]
    assert rec["tool_call_count"] == 3 and rec["tool_error_count"] == 2


STOPS = {"max_tokens": "context_overflow", "model_length": "context_overflow", "content_filter": "guardrail_blocked",
         "stop": "wrong_answer"}


@pytest.mark.parametrize("stop", list(STOPS))
def test_tf10_23_a_stop_reason_gives_its_kind(tmp_path: Path, stop: str) -> None:
    path = write_in(tmp_path / "r.json", _edit_sample("q3", 2, lambda s: s["output"]["choices"][0].__setitem__("stop_reason", stop)))
    imported(in_argv(path, tmp_path / "st", "v"))
    rec = next(r for r in recs(tmp_path / "st", "v") if r["case"] == "q3" and r["repeat"] == 1)
    assert rec["failure_kind"] == STOPS[stop]


TOOL_ERRORS = {"unknown": "tool_error", "parsing": "tool_error", "timeout": "timeout", "approval": "guardrail_blocked",
               "permission": "guardrail_blocked"}


@pytest.mark.parametrize("error_type", list(TOOL_ERRORS))
def test_tf10_23_a_tool_error_gives_its_kind(tmp_path: Path, error_type: str) -> None:
    def failed_tool(s: dict[str, Any]) -> None:
        s["events"].append(_tool_event("lookup", {"type": error_type, "message": "secret tool message"}))
    path = write_in(tmp_path / "t.json", _edit_sample("q3", 2, failed_tool))
    imported(in_argv(path, tmp_path / "st", "v"))
    rec = next(r for r in recs(tmp_path / "st", "v") if r["case"] == "q3" and r["repeat"] == 1)
    assert rec["failure_kind"] == TOOL_ERRORS[error_type]
    assert rec["tool_call_count"] == 1 and rec["tool_error_count"] == 1
    call = rec["tool_calls"][0]
    assert call["name"] == "lookup" and call["status"] == "error" and call["error_type"] == error_type
    blob = stored_bytes(tmp_path / "st")
    for needle in (b"secret tool message", b"secret argument", b"secret tool output"):
        assert needle not in blob


def test_tf10_23_a_passing_sample_s_tool_call_is_recorded_and_unclassified(tmp_path: Path) -> None:
    path = write_in(tmp_path / "ok.json", _edit_sample("q1", 1, lambda s: s["events"].append(_tool_event("lookup", None, 0.5))))
    imported(in_argv(path, tmp_path / "st", "v"))
    rec = next(r for r in recs(tmp_path / "st", "v") if r["case"] == "q1" and r["repeat"] == 0)
    assert rec["outcome"] == "pass" and rec["failure_kind"] is None
    assert rec["tool_calls"] == [{"name": "lookup", "status": "ok", "duration_s": 0.5, "error_type": None, "attempt": 1}]


# ---------- TF10-24 ----------

SENTINELS = ("Say banana", "Say apple", "Say pear", "nope", "FaKNqaNkSR9ms2dMHFuxyj")


@pytest.mark.parametrize("path", [IN_JSON, IN_EVAL], ids=["json", "eval"])
def test_tf10_24_no_content_is_written_or_printed(tmp_path: Path, path: Path) -> None:
    for json_out in (True, False):
        argv = in_argv(path, tmp_path / f"st-{json_out}", "v")
        result = run_import([*argv, "--json"] if json_out else argv)
        assert result.code == 0, result.err
        blob = stored_bytes(tmp_path / f"st-{json_out}")
        for needle in SENTINELS:
            assert needle.encode("utf-8") not in blob, needle
            assert needle not in result.out + result.err, needle


# ---------- TF10-25 ----------


def test_tf10_25_the_same_log_as_json_and_as_eval_gives_the_same_records(tmp_path: Path) -> None:
    doc = in_doc()

    def as_eval(members: dict[str, Any]) -> None:
        for name in [n for n in members if n.startswith("samples/")]:
            del members[name]
        for s in doc["samples"]:
            members[f"samples/{s['id']}_epoch_{s['epoch']}.json"] = s
        header = {k: v for k, v in doc.items() if k not in ("samples", "reductions")}
        members["header.json"] = header
        members["reductions.json"] = doc["reductions"]
    archive = write_eval(tmp_path / "new.eval", as_eval)
    a = imported(in_argv(IN_JSON, tmp_path / "st", "a"))
    b = imported(in_argv(archive, tmp_path / "st", "b"))
    assert recs(tmp_path / "st", "a") == recs(tmp_path / "st", "b")
    for key in ("rows", "cases", "repeats", "outcomes", "no_outcome", "declared", "started"):
        assert a[key] == b[key], key
