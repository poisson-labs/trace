"""TF2-8: each reader in the install says whether a file looks like one it reads
(``looks_like(path) -> str | None``).

``poisson_trace.ingest.deepeval.looks_like`` and ``poisson_trace.ingest.ragas.looks_like`` give the
one line a listing shows for a file the reader reads, and None for any other file, without
raising: another tool's file, a file of the right name and the wrong content, a folder, a file
that is not there or cannot be read, bytes that are not text. DeepEval's are its saved test runs
(``test_run_*.json``, and ``.latest_test_run.json`` in a ``.deepeval`` folder); Ragas's are tables
(``.csv``, ``.jsonl``, ``.json``) with a column named like a Ragas metric within their first
4 KB. The name is looked up when called, so the tests reach the reader through the module."""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest

from tf2_support import deepeval_file, ragas_file, ragas_rows, scratch_home  # noqa: F401

METRICS = ("faithfulness", "answer_relevancy", "answer_correctness", "context_precision", "context_recall",
           "id_based_context_precision", "id_based_context_recall")


def looks_like(tool: str, path: Path) -> Any:
    reader = import_module(f"poisson_trace.ingest.{tool}")
    return reader.looks_like(path)


def _one_line(said: Any) -> None:
    assert isinstance(said, str) and said.strip() and "\n" not in said, said


@pytest.fixture
def files(tmp_path: Path) -> dict[str, Path]:
    made = {
        "deepeval results": deepeval_file(tmp_path / "results" / "test_run_20261002_101500.json"),
        "deepeval latest": deepeval_file(tmp_path / ".deepeval" / ".latest_test_run.json"),
        "ragas jsonl": ragas_file(tmp_path / "scores" / "base.jsonl"),
        "ragas csv": ragas_file(tmp_path / "scores" / "base.csv"),
        "ragas json": ragas_file(tmp_path / "scores" / "base.json"),
    }
    latest = made["deepeval latest"]
    latest.write_text(json.dumps({"testRunData": json.loads(latest.read_text(encoding="utf-8"))}), encoding="utf-8")
    return made


@pytest.mark.parametrize("label,tool", [
    ("deepeval results", "deepeval"), ("deepeval latest", "deepeval"),
    ("ragas jsonl", "ragas"), ("ragas csv", "ragas"), ("ragas json", "ragas"),
])
def test_tf2_08_a_file_the_reader_reads_is_described_in_one_line(files: dict[str, Path], label: str, tool: str) -> None:
    _one_line(looks_like(tool, files[label]))


@pytest.mark.parametrize("metric", METRICS)
def test_tf2_08_every_ragas_metric_names_a_table(tmp_path: Path, metric: str) -> None:
    path = tmp_path / "t.csv"
    path.write_text(f"case,{metric}\na,0.5\n", encoding="utf-8")
    _one_line(looks_like("ragas", path))


def test_tf2_08_a_metric_is_a_column_not_a_word_in_a_cell(tmp_path: Path) -> None:
    cell = tmp_path / "cell.csv"
    cell.write_text("case,score\nfaithfulness,0.5\n", encoding="utf-8")
    assert looks_like("ragas", cell) is None
    lines = tmp_path / "cell.jsonl"
    lines.write_text(json.dumps({"case": "faithfulness", "score": 0.5}) + "\n", encoding="utf-8")
    assert looks_like("ragas", lines) is None
    similar = tmp_path / "similar.csv"
    similar.write_text("case,faithfulness_note\na,1\n", encoding="utf-8")
    assert looks_like("ragas", similar) is None
    # a .json file is a table when it is a list of rows; one object with a metric's key is not
    one = tmp_path / "one.json"
    one.write_text(json.dumps({"case": "a", "faithfulness": 0.5}), encoding="utf-8")
    assert looks_like("ragas", one) is None
    rows = tmp_path / "rows.json"
    rows.write_text(json.dumps([{"case": "a", "faithfulness": 0.5}]), encoding="utf-8")
    _one_line(looks_like("ragas", rows))


def test_tf2_08_a_metric_past_the_first_4_kb_is_not_looked_for(tmp_path: Path) -> None:
    row = ragas_rows()[0]
    late = tmp_path / "late.jsonl"
    padded = {"case": row["case"], "notes": "x" * 5000, "faithfulness": row["faithfulness"]}
    late.write_text(json.dumps(padded) + "\n", encoding="utf-8")
    assert looks_like("ragas", late) is None
    early = tmp_path / "early.jsonl"
    early.write_text(json.dumps({"case": row["case"], "faithfulness": row["faithfulness"], "notes": "x" * 5000}) + "\n", encoding="utf-8")
    _one_line(looks_like("ragas", early))


def test_tf2_08_deepeval_needs_its_name_and_its_content(tmp_path: Path, files: dict[str, Path]) -> None:
    renamed = tmp_path / "renamed.json"
    renamed.write_bytes(files["deepeval results"].read_bytes())
    assert looks_like("deepeval", renamed) is None
    named = tmp_path / "results" / "test_run_20261002_121500.json"
    named.write_text(json.dumps({"rows": [1, 2]}), encoding="utf-8")
    assert looks_like("deepeval", named) is None
    # DeepEval keeps its latest test run in a .deepeval folder; the name elsewhere is not its
    elsewhere = tmp_path / "results" / ".latest_test_run.json"
    elsewhere.write_bytes(files["deepeval latest"].read_bytes())
    assert looks_like("deepeval", elsewhere) is None


@pytest.mark.parametrize("tool", ["deepeval", "ragas"])
def test_tf2_08_never_raises(tmp_path: Path, tool: str) -> None:
    folder = tmp_path / "test_run_20261002_101500.json"
    folder.mkdir()
    missing = tmp_path / "test_run_20261002_131500.json"
    binary = tmp_path / "test_run_20261002_141500.json"
    binary.write_bytes(b"\xff\xfe\x00\x81" * 4000)
    empty = tmp_path / "test_run_20261002_151500.json"
    empty.write_bytes(b"")
    locked = tmp_path / "test_run_20261002_161500.json"
    locked.write_text("[]", encoding="utf-8")
    locked.chmod(0o000)
    tables = [tmp_path / "bin.csv", tmp_path / "empty.jsonl"]
    tables[0].write_bytes(b"\xff\xfe\x00\x81" * 4000)
    tables[1].write_bytes(b"")
    try:
        for path in (folder, missing, binary, empty, locked, *tables):
            assert looks_like(tool, path) is None, path
    finally:
        locked.chmod(0o600)
