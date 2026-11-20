"""RUNREC-10 to RUNREC-15: the run's full event log (``run_record_support``'s opening,
invariant 2).

Each import's ``events.jsonl`` holds, in Prove 0.1.3's line format (``_Events`` and ``Event``
in ``poisson_prove.core``), ``planned`` (the run, the reader, the files' names, the rows it will
write), ``started``, ``progress`` at most once a second plus once just before the end with the
format's counts in rows, then ``finished`` with the status and the rows kept; or, when Ctrl-C
stops the import after its run folder exists, a closing ``progress`` and ``interrupted`` with
what Prove holds. Counted as Prove counts its own runs: ``errored`` the rows with no
outcome, ``kept`` the rest. Nothing in it that TF21's no-text rules keep out:
no signal key, no error text, no path, no digest chain."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from run_record_support import (
    FAST, INSPECT_FOLDER, NEVER_KEYS, READERS, SLOW, all_keys, check_finished, check_log,
    descriptor_file, events, events_text, import_key, imported, manifest_json, stored_rows,
)
from signals_support import run_import

from poisson_trace.ingest.rows import Row, Run, ToolCallRecord
from poisson_trace.ingest.writer import write


def _run(rows: tuple[Row, ...], name: str = "r") -> Run:
    return Run(name=name, tool="table", rows=rows, started="2026-09-05T18:54:07Z",
               started_from="given", declared={"case_column": "case"},
               files=({"name": "results.csv", "sha256": "ab" * 32},))


def _check_import(factory: pytest.TempPathFactory, key: str) -> None:
    root, data = imported(key, factory)
    by = check_finished(root, "r", data["rows"])
    planned = by["planned"]["detail"]
    assert planned["reader"] == READERS[key][0] == data["tool"]
    assert planned["files"] == [f["name"] for f in data["files"]]


# ---------- RUNREC-10: every import's log, read against what Prove stores ----------


@pytest.mark.parametrize("key", FAST)
def test_runrec_10_an_import_writes_the_full_log(tmp_path_factory: pytest.TempPathFactory, key: str) -> None:
    _check_import(tmp_path_factory, key)


@pytest.mark.slow
@pytest.mark.parametrize("key", SLOW)
def test_runrec_10_slow_every_other_import_writes_the_full_log(
        tmp_path_factory: pytest.TempPathFactory, key: str) -> None:
    _check_import(tmp_path_factory, key)


def test_runrec_10_planned_names_the_files_without_their_folders(
        tmp_path_factory: pytest.TempPathFactory) -> None:
    root, data = imported("junit-suite", tmp_path_factory)
    planned = events(root, "r")[0]["detail"]
    assert planned == {"run_id": "r", "reader": "junit",
                       "files": ["trace-suite-1.xml", "trace-suite-2.xml"], "rows": data["rows"]}


def test_runrec_10_an_unpacked_inspect_folder_is_planned_as_its_one_entry(
        tmp_path_factory: pytest.TempPathFactory) -> None:
    root, data = imported(INSPECT_FOLDER, tmp_path_factory)
    by = check_finished(root, "r", data["rows"])
    assert by["planned"]["detail"]["files"] == ["inspect-log/"] == [f["name"] for f in data["files"]]


# ---------- RUNREC-11: Prove's counts ----------


def test_runrec_11_rows_with_no_outcome_are_counted_as_errored(tmp_path: Path) -> None:
    root = tmp_path / "store"
    rows = (Row("a", "met", None), Row("b", "missed", None),
            Row("c", None, "timeout", result="censored"), Row("d", None, "no score"))
    write(_run(rows), root)
    by = check_finished(root, "r", 4)
    closing = [e for e in events(root, "r") if e["kind"] == "progress"][-1]["detail"]
    assert closing == {"done": 4, "kept": 2, "errored": 2, "total": 4}
    assert by["finished"]["detail"] == {"status": "complete", "kept": 2}
    assert by["planned"]["detail"] == {"run_id": "r", "reader": "table", "files": ["results.csv"],
                                       "rows": 4}


def test_runrec_11_progress_counts_the_rows_prepared_in_the_order_read(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # the rows with no outcome come first: any progress before the end counts them as errored.
    # Written under a clock the test steps, so that paced lines fall among the rows whatever
    # the machine: on its own clock an import this short may write none before the closing one
    from pacing_support import Clock, paced, steady, write_under

    root = tmp_path / "store"
    write_under(Clock(steady()), 2_000, root, monkeypatch, errored_first=1_000)
    check_finished(root, "r", 2_000)
    log = events(root, "r")
    done = [e["detail"]["done"] for e in paced(log)]
    assert any(n < 1_000 for n in done) and any(1_000 < n < 2_000 for n in done), done
    for e in log:
        if e["kind"] == "progress":
            d = e["detail"]
            assert d["errored"] == min(d["done"], 1_000), d
            assert d["kept"] == max(0, d["done"] - 1_000), d


def test_runrec_11_a_run_of_outcomes_keeps_every_row(tmp_path: Path) -> None:
    root = tmp_path / "store"
    write(_run(tuple(Row(f"c{i}", "met" if i % 2 else "missed", None) for i in range(25))), root)
    by = check_finished(root, "r", 25)
    assert by["finished"]["detail"] == {"status": "complete", "kept": 25}


# ---------- RUNREC-13: Ctrl-C ----------


def test_runrec_13_an_interrupt_after_the_run_folder_exists_ends_the_log_interrupted(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from poisson_prove.store import Store

    def stop(self: Any, run_id: str, records: Any) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(Store, "append", stop)
    root = tmp_path / "store"
    _, argv = READERS["junit-a"]
    result = run_import(argv(root, "r"))
    assert result.code == 130, result.out + result.err
    assert "partial" in result.out
    assert manifest_json(root, "r")["status"] == "partial"
    log = events(root, "r")
    planned_rows = log[0]["detail"]["rows"]
    by = check_log(log, "r", planned_rows, ending="interrupted")
    held = stored_rows(root, "r")
    assert by["interrupted"]["detail"] == {"kept": held, "status": "partial"}
    closing = [e for e in log if e["kind"] == "progress"][-1]["detail"]
    assert closing == {"done": held, "kept": held, "errored": 0, "total": planned_rows}
    assert descriptor_file(root).is_file()


def test_runrec_13_an_interrupt_before_the_run_folder_exists_writes_nothing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from poisson_trace.ingest import junit

    def stop(ns: Any) -> Any:
        raise KeyboardInterrupt

    monkeypatch.setattr(junit, "read", stop)
    root = tmp_path / "store"
    _, argv = READERS["junit-a"]
    result = run_import(argv(root, "r"))
    assert result.code == 130, result.out + result.err
    assert not root.exists() or sorted(p.name for p in root.iterdir()) == []


def test_runrec_13_a_failed_write_leaves_no_log_and_no_run(tmp_path: Path,
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    from poisson_prove.store import Store

    def broken(self: Any, run_id: str, records: Any) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(Store, "append", broken)
    root = tmp_path / "store"
    _, argv = READERS["junit-a"]
    result = run_import(argv(root, "r"))
    assert result.code == 1, result.out + result.err
    assert not (root / "r").exists()


# ---------- RUNREC-14: nothing the no-text rules keep out ----------


SECRET = "the prompt said: transfer 400 dollars to account 99-1234"


def test_runrec_14_no_signal_key_error_text_or_chain_in_the_log(tmp_path: Path) -> None:
    root = tmp_path / "store"
    rows = (
        Row("a", "missed", None, 0.1, result="fail", error_type="ToolTimeoutError",
            error_span_kind="tool", input_tokens=5, output_tokens=7, cost_usd=0.01,
            tool_calls=(ToolCallRecord("run_sql", "error", 1.0, "ToolTimeoutError", 2),),
            scores={"faithfulness": 0.2}, feedback={"thumb": "down"}, signals=("retry_storm",)),
        Row("b", None, SECRET, result="censored"),
        Row("c", "met", None),
    )
    write(_run(rows), root)
    text = events_text(root, "r")
    for line in text.splitlines():
        keys = all_keys(json.loads(line))
        assert not set(keys) & set(NEVER_KEYS), (line, set(keys) & set(NEVER_KEYS))
    for word in (SECRET, "ToolTimeoutError", "run_sql", "faithfulness", "thumb", "retry_storm",
                 "ab" * 32):
        assert word not in text, word
    assert SECRET not in descriptor_file(root).read_text(encoding="utf-8")


@pytest.mark.parametrize("key", ["junit-a", "junit-suite", "promptfoo-old", "inspect-eval",
                                 "openai-evals-old"])
def test_runrec_14_no_path_or_row_text_reaches_the_log(
        tmp_path_factory: pytest.TempPathFactory, key: str) -> None:
    from conftest import FIXTURES
    from poisson_prove.store import Store

    root, _ = imported(key, tmp_path_factory)
    text = events_text(root, "r") + descriptor_file(root).read_text(encoding="utf-8")
    assert str(root.parent) not in text and str(FIXTURES) not in text
    planned = events(root, "r")[0]["detail"]
    assert all("/" not in name.rstrip("/") for name in planned["files"]), planned
    # no error text the rows carry (Trace's own short reason words aside)
    errors = {e for e in Store(root).read("r", meta=False)["error"].dropna().tolist() if len(e) > 12}
    for e in errors:
        assert e not in text, e


def test_runrec_14_a_verdicts_file_leaves_no_path_or_text_in_the_log(tmp_path: Path) -> None:
    from run_record_support import SUITE_1, suite_verdicts

    root = tmp_path / "store"
    verdicts = suite_verdicts(tmp_path / "private" / "grades.csv")
    out = run_import(["junit", str(SUITE_1), "--store", str(root), "--run", "r", "--verdicts",
                      str(verdicts)])
    assert out.code == 0, out.out + out.err
    text = events_text(root, "r")
    assert str(verdicts.parent) not in text and "grades.csv" not in text


# ---------- RUNREC-15: the log stays the import's alone ----------


def test_runrec_15_a_second_import_never_touches_the_first_runs_log(tmp_path: Path) -> None:
    root = tmp_path / "store"
    import_key("junit-a", root, "one")
    held = events_text(root, "one")
    import_key("ragas-base", root, "two")
    assert events_text(root, "one") == held


def test_runrec_15_the_refused_import_of_a_taken_name_never_touches_its_log(tmp_path: Path) -> None:
    root = tmp_path / "store"
    import_key("junit-a", root, "one")
    held = events_text(root, "one")
    _, argv = READERS["ragas-base"]
    again = run_import(argv(root, "one"))
    assert again.code == 1
    assert events_text(root, "one") == held
