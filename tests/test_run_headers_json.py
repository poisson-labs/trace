"""A test of this build's own: what a run's header carries for the markdown alone (where its
start came from, whether it was imported) stays out of every verb's JSON, on runs Prove stored
and on imported ones. The fix-check and changes headers are pinned key by key elsewhere; where's
and compare's are not."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from conftest import TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, compare, where
from tf2_support import here, import_here, work
from tf3_support import TABLE_A, TABLE_B

COLUMNS = ["--case-column", "case", "--outcome-column", "outcome", "--failed", "failed_assertion", "--failed", "crashed"]


def _headers(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [doc["run"]] if "run" in doc else list(doc["runs"].values())


def _private(doc: dict[str, Any]) -> list[str]:
    return [key for header in _headers(doc) for key in header if key.startswith("_")]


def test_no_header_key_of_the_markdown_reaches_the_json_of_runs_prove_stored() -> None:
    for result in (where(TAU2, TAU2_A, TAU2_EVENTS, "--json"), compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.3, "--json")):
        assert result.code == 0, result.out
        assert _private(result.json()) == []


def test_no_header_key_of_the_markdown_reaches_the_json_of_imported_runs(tmp_path: Path) -> None:
    folder = work(tmp_path)
    for name, table, started in (("old", TABLE_A, None), ("new", TABLE_B, "2026-09-05T19:50:09Z")):
        argv = ["table", str(table), "--store", "st", "--run", name, *COLUMNS]
        assert import_here(folder, argv + ([] if started is None else ["--started", started])).code == 0
    reach = ["--store", "st", "--event", "missed", "--json"]
    for argv in (
        ["where", "old", *reach],
        ["fix-check", "old", "new", "--inputs", "all", "--max-mde", "0.05", *reach],
        ["changes", "old", "new", *reach],
    ):
        result = here(folder, argv)
        assert result.code == 0, result.text
        assert _private(result.json()) == [], argv
