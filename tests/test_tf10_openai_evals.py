"""TF10-26 to TF10-32: the OpenAI Evals reader on evals 3.0.1.post1's committed records (the
readings in ``tf10_support``'s docstring).

- TF10-26: a ``match`` event is a row, ``data.correct`` its outcome, ``sample_id`` its case.
- TF10-27: the ``match`` events of one sample are its repeats in ``event_id`` order; every other
  event type is counted and is not a row.
- TF10-28: a record with no ``spec`` line or no ``match`` event is refused, and so is a line that
  is not JSON or a ``match`` whose ``data.correct`` is not true or false, each naming the file.
- TF10-29: the start is ``spec.created_at``, read as UTC since it carries no zone, which the
  summary says; the eval's name and completion functions are declared.
- TF10-30: the signals each row records, and those it does not.
- TF10-31: a missed row is a wrong answer, or abstained when its answer is empty.
- TF10-32: nothing of the sampled answer, the expected answer, the options or the pick is written
  or printed, nor the registry path of the ``spec`` line.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tf10_support import (
    OE_NEW, OE_OLD, STARTED, imported, match_events, oe_argv, oe_lines, recs, ref_kind_of, refused, stored_bytes,
    write_oe,
)
from tf21_support import run_import


def _by_case(root: Path, run: str) -> dict[str, list[str | None]]:
    from tf3_support import by_case, read_rows

    return by_case(read_rows(root, run))


def _match(sample_id: str, event_id: int, correct: Any, sampled: Any = "This is a dummy response.") -> dict[str, Any]:
    return {"run_id": "261007042429AKZ6ZLA4", "event_id": event_id, "sample_id": sample_id, "type": "match",
            "data": {"correct": correct, "expected": "15", "picked": None, "sampled": sampled, "options": ["15"]},
            "created_by": "", "created_at": "2026-10-07 04:24:29.700000+00:00"}


def _sampling(sample_id: str, event_id: int) -> dict[str, Any]:
    return {"run_id": "261007042429AKZ6ZLA4", "event_id": event_id, "sample_id": sample_id, "type": "sampling",
            "data": {"prompt": [{"role": "user", "content": "What is 7 + 8?"}], "sampled": ["This is a dummy response."]},
            "created_by": "", "created_at": "2026-10-07 04:24:29.650000+00:00"}


# ---------- TF10-26 ----------


@pytest.mark.parametrize("path", [OE_OLD, OE_NEW], ids=["old", "new"])
def test_tf10_26_each_match_event_is_a_row(tmp_path: Path, path: Path) -> None:
    data = imported(oe_argv(path, tmp_path / "st", "v"))
    assert data["tool"] == "openai-evals" and data["rows"] == 3 and data["cases"] == 3
    assert data["repeats"] == {"min": 1, "max": 1}
    assert data["outcomes"] == {"met": 0, "missed": 3} and data["no_outcome"] == {}
    assert _by_case(tmp_path / "st", "v") == {m["sample_id"]: ["missed"] for m in match_events(oe_lines(path))}


def test_tf10_26_a_correct_match_is_met(tmp_path: Path) -> None:
    path = write_oe(tmp_path / "r.jsonl", lambda lines: lines[3]["data"].__setitem__("correct", True))
    data = imported(oe_argv(path, tmp_path / "st", "v"))
    assert data["outcomes"] == {"met": 1, "missed": 2}
    assert _by_case(tmp_path / "st", "v")["test-match.s1.1"] == ["met"]


# ---------- TF10-27 ----------


def test_tf10_27_matches_of_one_sample_are_repeats_in_event_id_order(tmp_path: Path) -> None:
    def repeats(lines: list[dict[str, Any]]) -> None:
        # written out of order: event 4 (met) before event 3 (missed)
        lines += [_match("test-match.s1.0", 4, True), _match("test-match.s1.0", 3, False)]
    path = write_oe(tmp_path / "r.jsonl", repeats)
    data = imported(oe_argv(path, tmp_path / "st", "v"))
    assert data["rows"] == 5 and data["cases"] == 3 and data["repeats"] == {"min": 1, "max": 3}
    # event 2 (missed), then 3 (missed), then 4 (met)
    assert _by_case(tmp_path / "st", "v")["test-match.s1.0"] == ["missed", "missed", "met"]


def test_tf10_27_other_events_are_counted_and_are_not_rows(tmp_path: Path) -> None:
    def more(lines: list[dict[str, Any]]) -> None:
        lines.insert(2, _sampling("test-match.s1.2", 10))
        lines.insert(3, _sampling("test-match.s1.1", 11))
        lines.append({"run_id": "261007042429AKZ6ZLA4", "event_id": 12, "sample_id": "test-match.s1.0", "type": "metrics",
                      "data": {"accuracy": 0.0}, "created_by": "", "created_at": "2026-10-07 04:24:29.800000+00:00"})
    path = write_oe(tmp_path / "m.jsonl", more)
    data = imported(oe_argv(path, tmp_path / "st", "v"))
    assert data["rows"] == 3
    counts = data["counts"]
    for kind, n in (("match", 3), ("sampling", 2), ("metrics", 1)):
        assert any(kind in k and v == n for k, v in counts.items()), counts


# ---------- TF10-28 ----------

BROKEN = {
    "no spec line": lambda lines: lines.pop(0),
    "no match event": lambda lines: lines.__delitem__(slice(2, None)),
    "a correct that is not true or false": lambda lines: lines[2]["data"].__setitem__("correct", "no"),
    "a match with no sample": lambda lines: lines[2].pop("sample_id"),
}


@pytest.mark.parametrize("label", list(BROKEN))
def test_tf10_28_a_broken_record_is_refused_naming_the_file(tmp_path: Path, label: str) -> None:
    path = write_oe(tmp_path / "bad.jsonl", BROKEN[label])
    line = refused(run_import(oe_argv(path, tmp_path / "st", "v")))
    assert "bad.jsonl" in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("label, line_no", [("a line that is not JSON", 4), ("an empty file", None)])
def test_tf10_28_a_file_that_is_not_a_record_is_refused(tmp_path: Path, label: str, line_no: int | None) -> None:
    path = tmp_path / "bad.jsonl"
    if line_no is None:
        path.write_text("", encoding="utf-8")
    else:
        text = OE_OLD.read_text(encoding="utf-8").splitlines()
        text[line_no - 1] = text[line_no - 1][:40]
        path.write_text("\n".join(text) + "\n", encoding="utf-8")
    line = refused(run_import(oe_argv(path, tmp_path / "st", "v")))
    assert "bad.jsonl" in line, line
    if line_no is not None:
        assert f"line {line_no}" in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF10-29 ----------


def test_tf10_29_the_start_is_the_spec_s_time_read_as_utc(tmp_path: Path) -> None:
    assert oe_lines()[0]["spec"]["created_at"] == "2026-10-07 04:24:29.594390"
    data = imported(oe_argv(OE_OLD, tmp_path / "st", "old"))
    assert data["started"]["at"] == "2026-10-07T04:24:29.594390Z" and data["started"]["from"] == "file"
    assert "UTC" in data["started"]["note"]
    text = run_import(oe_argv(OE_NEW, tmp_path / "st2", "new"))
    assert text.code == 0 and "UTC" in text.out, text.out
    declared = data["declared"]
    assert declared["eval_name"] == "test-match.s1.simple-v0" and declared["completion_fns"] == ["dummy"]
    given = imported(oe_argv(OE_OLD, tmp_path / "st", "given", "--started", STARTED))
    assert given["started"] == {"at": STARTED, "from": "given"}


def test_tf10_29_a_zoned_spec_time_carries_no_note(tmp_path: Path) -> None:
    path = write_oe(tmp_path / "z.jsonl", lambda lines: lines[0]["spec"].__setitem__("created_at", "2026-10-07 04:24:29.594390+02:00"))
    data = imported(oe_argv(path, tmp_path / "st", "v"))
    assert data["started"]["at"] == "2026-10-07T02:24:29.594390Z" and "note" not in data["started"]


# ---------- TF10-30 ----------


def test_tf10_30_the_signals_each_row_records(tmp_path: Path) -> None:
    imported(oe_argv(OE_OLD, tmp_path / "st", "v"))
    for rec in recs(tmp_path / "st", "v"):
        assert rec["output_chars"] == len("This is a dummy response.")
        for name in ("wall_time_s", "working_time_s", "ttft_s", "input_chars", "input_tokens", "output_tokens",
                     "cached_tokens", "reasoning_tokens", "total_tokens", "cost_usd", "steps", "horizon", "llm_calls",
                     "retries", "tool_calls", "tool_call_count", "tool_error_count", "score", "error_type"):
            assert rec[name] is None, name
        assert rec["scores"] == {} and rec["feedback"] == {}


def test_tf10_30_a_match_s_score_is_read_where_written(tmp_path: Path) -> None:
    path = write_oe(tmp_path / "s.jsonl", lambda lines: lines[2]["data"].__setitem__("score", 0.25))
    imported(oe_argv(path, tmp_path / "st", "v"))
    rec = next(r for r in recs(tmp_path / "st", "v") if r["case"] == "test-match.s1.2")
    assert rec["score"] == 0.25


# ---------- TF10-31 ----------


def test_tf10_31_a_missed_row_is_a_wrong_answer(tmp_path: Path) -> None:
    imported(oe_argv(OE_OLD, tmp_path / "st", "v"))
    rs = recs(tmp_path / "st", "v")
    assert [r["failure_kind"] for r in rs] == ["wrong_answer"] * 3
    assert all(r["outcome"] == "fail" and r["signals"] == [] for r in rs)
    assert all(r["failure_kind"] == ref_kind_of(r) for r in rs)


def test_tf10_31_an_empty_answer_is_abstained(tmp_path: Path) -> None:
    path = write_oe(tmp_path / "e.jsonl", lambda lines: lines[3]["data"].__setitem__("sampled", ""))
    imported(oe_argv(path, tmp_path / "st", "v"))
    rec = next(r for r in recs(tmp_path / "st", "v") if r["case"] == "test-match.s1.1")
    assert rec["output_chars"] == 0 and rec["failure_kind"] == "abstained" and "gave_up" in rec["signals"]
    assert rec["failure_kind"] == ref_kind_of(rec)


# ---------- TF10-32 ----------

SENTINELS = ("dummy response", "George Washington", "registry", "/opt/venv", "evals.elsuite", "oaieval")


@pytest.mark.parametrize("path", [OE_OLD, OE_NEW], ids=["old", "new"])
def test_tf10_32_no_content_is_written_or_printed(tmp_path: Path, path: Path) -> None:
    for json_out in (True, False):
        argv = oe_argv(path, tmp_path / f"st-{json_out}", "v")
        result = run_import([*argv, "--json"] if json_out else argv)
        assert result.code == 0, result.err
        blob = stored_bytes(tmp_path / f"st-{json_out}")
        for needle in SENTINELS:
            assert needle.encode("utf-8") not in blob, needle
            assert needle not in result.out + result.err, needle
