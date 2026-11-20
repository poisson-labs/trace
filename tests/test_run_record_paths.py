"""RUNREC-30 to RUNREC-33: every way in records the same way (invariant 4;
TF22's folder ingest, a saved pull, and TF10's readers).

A folder of one tool's files, a saved pull and the same files named one by one write the same
run record: the same ``produced_by``, the same ``planned``, closing ``progress`` and
``finished``, and a descriptor of the same shape. ``init``, which imports the results it finds,
writes the record too, and when it rolls back leaves nothing behind, the descriptor included."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from run_record_support import (
    DESCRIPTOR_KEYS, READERS, STORE_FORMAT, TOOL, check_finished, descriptor, events, produced_by,
    trace_version,
)
from setup_support import scratch_home  # noqa: F401  (each test's HOME its own)
from signals_support import STARTED, run_import
from folders_support import (
    INGEST, JUNIT, RAGAS, TABLE, copy_into, deepeval_folder, junit_shards, pull_folder, ragas_parts,
    table_parts,
)


def _imported(argv: list[str]) -> dict[str, Any]:
    out = run_import([*argv, "--started", STARTED, "--json"])
    assert out.code == 0, out.out + out.err
    data: dict[str, Any] = json.loads(out.out)
    return data


def _record(root: Path, run: str, data: dict[str, Any]) -> dict[str, Any]:
    """What must match between two ways in: ``produced_by``, and the log's planned, closing
    progress and finished details; the times aside."""
    by = check_finished(root, run, data["rows"])
    closing = [e for e in events(root, run) if e["kind"] == "progress"][-1]["detail"]
    doc = descriptor(root)
    assert list(doc) == DESCRIPTOR_KEYS and doc["format"] == STORE_FORMAT
    assert [(w["tool"], w["version"]) for w in doc["writers"]] == [(TOOL, trace_version())]
    return {"produced_by": produced_by(root, run), "planned": by["planned"]["detail"],
            "closing": closing, "finished": by["finished"]["detail"]}


def _same(tmp: Path, tool: str, files: list[Path], folder: Path, *flags: str) -> None:
    named = _imported([tool, *[str(f) for f in sorted(files)], "--store", str(tmp / "s1"),
                       "--run", "r", *flags])
    found = _imported([str(folder), "--store", str(tmp / "s2"), "--run", "r", *flags])
    assert _record(tmp / "s1", "r", named) == _record(tmp / "s2", "r", found)
    assert produced_by(tmp / "s2", "r")["reader"] == tool


# ---------- RUNREC-30: a folder and its files ----------


FOLDERS: dict[str, tuple[str, Callable[[Path], Path], tuple[str, ...]]] = {
    "junit": ("junit", lambda d: junit_shards(d), ()),
    "table": ("table", lambda d: table_parts(d, TABLE / "humaneval-a.csv", 3),
              ("--case-column", "case", "--outcome-column", "outcome", "--failed",
               "failed_assertion", "--failed", "crashed")),
    "ragas": ("ragas", lambda d: ragas_parts(d, RAGAS / "rag-base.jsonl", 2),
              ("--metric", "faithfulness", "--cut", "0.5", "--below", "--case-column", "case")),
    "openai-evals": ("openai-evals",
                     lambda d: copy_into(d, INGEST / "openai-evals" / "old.jsonl"), ()),
    "promptfoo": ("promptfoo", lambda d: copy_into(d, INGEST / "promptfoo" / "results.json"),
                  ("--prompt", "1", "--case", "var:case")),
}


@pytest.mark.parametrize("kind", ["junit", "ragas", "openai-evals", "promptfoo"])
def test_runrec_30_a_folder_records_as_its_files_do(tmp_path: Path, kind: str) -> None:
    tool, make, flags = FOLDERS[kind]
    folder = make(tmp_path / "results")
    files = [p for p in folder.iterdir() if p.is_file()]
    _same(tmp_path, tool, files, folder, *flags)


@pytest.mark.slow
@pytest.mark.parametrize("kind", ["table", "deepeval"])
def test_runrec_30_slow_the_large_folders_record_as_their_files_do(tmp_path: Path, kind: str) -> None:
    if kind == "deepeval":
        folder = deepeval_folder(tmp_path / "results", "a")
        flags: tuple[str, ...] = ("--metric", "Tests Passed", "--cut", "recorded", "--case", "name")
        tool = "deepeval"
    else:
        tool, make, flags = FOLDERS[kind]
        folder = make(tmp_path / "results")
    files = [p for p in folder.iterdir() if p.is_file()]
    _same(tmp_path, tool, files, folder, *flags)


def test_runrec_30_an_unpacked_inspect_folder_records_as_a_log_does(tmp_path: Path) -> None:
    from run_record_support import unpacked_inspect

    folder = unpacked_inspect(tmp_path)
    data = _imported([str(folder), "--store", str(tmp_path / "s"), "--run", "r"])
    rec = _record(tmp_path / "s", "r", data)
    assert rec["produced_by"]["reader"] == "inspect"
    assert rec["planned"]["files"] == ["inspect-log/"]


def test_runrec_30_the_folders_name_is_the_run_when_none_is_given(tmp_path: Path) -> None:
    folder = junit_shards(tmp_path / "suite-results")
    data = _imported([str(folder), "--store", str(tmp_path / "s")])
    assert data["run"] == "suite-results"
    rec = _record(tmp_path / "s", "suite-results", data)
    assert rec["planned"]["run_id"] == "suite-results"
    assert [e["name"] for e in rec["produced_by"]["from"]] == sorted(
        p.name for p in folder.iterdir())


# ---------- RUNREC-31: a saved pull ----------


def test_runrec_31_a_saved_pull_records_its_listed_files(tmp_path: Path) -> None:
    source = junit_shards(tmp_path / "shards")
    listed = sorted(source.iterdir())
    folder = pull_folder(tmp_path / "pull", "junit", listed)
    data = _imported([str(folder), "--store", str(tmp_path / "s"), "--run", "r"])
    rec = _record(tmp_path / "s", "r", data)
    names = [e["name"] for e in rec["produced_by"]["from"]]
    assert names == [f["name"] for f in data["files"]] == [p.name for p in listed]
    assert rec["planned"]["files"] == names


# ---------- RUNREC-32: every reader, through the import ----------


def test_runrec_32_every_reader_on_main_is_covered() -> None:
    from poisson_trace.ingest.cli import present

    assert set(present()) == {reader for reader, _ in READERS.values()}


# ---------- RUNREC-33: init ----------


def test_runrec_33_init_records_the_runs_it_imports(tmp_path: Path) -> None:
    from setup_support import deepeval_file, init_yes, work

    folder = work(tmp_path)
    deepeval_file(folder / "results" / "test_run_20261002_101500.json")
    ran = init_yes(folder, "--metric", "Tests Passed", "--cut", "recorded", "--case", "name")
    assert ran.code == 0, ran.text
    root = folder / "trace-store"
    run = "test_run_20261002_101500"
    by = check_finished(root, run, events(root, run)[0]["detail"]["rows"])
    assert by["planned"]["detail"]["reader"] == "deepeval"
    got = produced_by(root, run)
    assert got["reader"] == "deepeval" and got["tool"] == TOOL
    assert [e["name"] for e in got["from"]] == [f"{run}.json"]
    assert descriptor(root)["created_by"] == {"tool": TOOL, "version": trace_version()}


def test_runrec_33_init_rolled_back_leaves_no_store_and_no_descriptor(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from setup_support import deepeval_file, init_yes, work

    from poisson_trace import config

    def stop(*args: Any, **kwargs: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(config, "write_config_file", stop)
    folder = work(tmp_path)
    deepeval_file(folder / "results" / "test_run_20261002_101500.json")
    deepeval_file(folder / "results" / "test_run_20261002_111500.json", cases=20)
    ran = init_yes(folder, "--metric", "Tests Passed", "--cut", "recorded", "--case", "name")
    assert ran.code == 130, ran.text
    assert not (folder / "trace-store").exists()
    assert sorted(p.name for p in folder.iterdir()) == ["results"]
    assert JUNIT.is_dir()  # the fixtures are untouched
