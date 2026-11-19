"""ID10: the HumanEval pair written through DeepEval 4.2.6, imported by Trace
(the committed fixtures, no network). Every figure pinned here was recomputed from the
fixtures before it was pinned."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from pathlib import Path

import pytest
from poisson_prove.store import Store
from support import FIXTURES, HE_A, HE_B, HUMANEVAL, PAIR, read_rows, run_import

RUNS = ("humaneval-a", "humaneval-b")
STARTS = ("2026-09-05T18:54:07Z", "2026-09-05T19:50:09Z")


@pytest.fixture(scope="module")
def pair(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("pair") / "store"
    for f, run, started in zip(PAIR, RUNS, STARTS, strict=True):
        r = run_import(["deepeval", str(f), "--store", str(root), "--run", run, "--metric", "Tests Passed",
                        "--cut", "recorded", "--case", "name", "--started", started])
        assert r.code == 0, r.text
    return root


def test_id10_the_fixture_files_are_the_committed_bytes() -> None:
    """Green by construction: the two files against SHA256SUMS."""
    sums = {}
    for line in (FIXTURES / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        sums[name] = digest
    for f in PAIR:
        assert sums[f"./ingest/deepeval/{f.name}"] == hashlib.sha256(f.read_bytes()).hexdigest()


@pytest.mark.parametrize("run,met,missed", [("humaneval-a", 9158, 1338), ("humaneval-b", 9109, 1387)])
def test_id10_the_pair_imports_to_its_counts(pair: Path, run: str, met: int, missed: int) -> None:
    rows = read_rows(pair, run)
    assert len(rows) == 10496
    per_case = Counter(r["case"] for r in rows)
    assert len(per_case) == 328 and set(per_case.values()) == {32}
    outcomes = Counter(r["outcome"] for r in rows)
    assert outcomes == {"met": met, "missed": missed}
    assert all(r["error"] is None for r in rows)
    tally = Store(pair).tally(run)
    assert (tally.rows, tally.with_outcome, tally.no_outcome) == (10496, 10496, 0)


@pytest.mark.parametrize("run,source", [("humaneval-a", HE_A), ("humaneval-b", HE_B)])
def test_id10_every_case_counts_as_the_prove_fixture_does(pair: Path, run: str, source: str) -> None:
    want: dict[str, Counter[str]] = defaultdict(Counter)
    frame = Store(HUMANEVAL).read(source, meta=False, trace="none")
    for cfg, outcome in zip(frame["config"], frame["outcome"], strict=True):
        want[f"{cfg['task_id']}@{cfg['temperature']}"]["met" if outcome == "passed" else "missed"] += 1
    got: dict[str, Counter[str]] = defaultdict(Counter)
    for r in read_rows(pair, run):
        got[r["case"]][r["outcome"]] += 1
    assert got == want
