"""ID10 and ID11: the HumanEval pair written through DeepEval 4.2.6, imported and read by Trace
(lane F, the committed fixtures, no network). Every figure pinned here was recomputed from the
fixtures before it was pinned."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest
from proofload.store import Store
from support import FIXTURES, HE_A, HE_B, HUMANEVAL, PAIR, read_rows, run_import, run_trace

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


def test_id11_fix_check_on_the_pair_reads_different_failed_more(pair: Path) -> None:
    r = run_trace(["fix-check", *RUNS, "--store", pair, "--event", "missed", "--inputs", "all",
                   "--max-mde", "0.02", "--json"])
    assert r.code == 0, r.text
    d = json.loads(r.out)
    assert (d["rows"]["old"]["failed"], d["rows"]["old"]["runs"]) == (1338, 10496)
    assert (d["rows"]["new"]["failed"], d["rows"]["new"]["runs"]) == (1387, 10496)
    assert (d["inputs"]["compared"], d["inputs"]["informative"]) == (328, 58)
    assert sum(d["inputs"]["left_out"].values()) == 0
    t = d["test"]
    assert t["observed_new"] == 1387
    assert t["expected_new"] == pytest.approx(1362.5, abs=1e-4)
    assert t["variance"] == pytest.approx(131.1389, abs=1e-4)
    assert t["p"] == pytest.approx(0.036024, abs=1e-6)
    assert d["difference"]["points"] == pytest.approx(0.004668, abs=1e-6)
    assert d["difference"]["lo"] == pytest.approx(0.000364, abs=1e-6)
    assert d["difference"]["hi"] == pytest.approx(0.008973, abs=1e-6)
    assert (d["verdict"], d["direction"]) == ("different", "failed more in new")
    assert d["limits"]["drop"] == pytest.approx(0.006436, abs=1e-6)
    assert d["limits"]["rise"] == pytest.approx(0.006575, abs=1e-6)
    assert d["by_input"]["moved"] == 47
    assert d["gap_seconds"] == pytest.approx(3362.0, abs=1e-6)
    text = " ".join(run_trace(["fix-check", *RUNS, "--store", pair, "--event", "missed", "--inputs", "all",
                               "--max-mde", "0.02"]).out.split())
    assert "different: the new version failed more on these inputs" in text
    assert "56 min" in text


def test_id11_changes_on_the_pair_flags_humaneval_129_only(pair: Path) -> None:
    r = run_trace(["changes", *RUNS, "--store", pair, "--event", "missed", "--json"])
    assert r.code == 0, r.text
    d = json.loads(r.out)
    assert (d["tested"], d["flagged"]) == (328, 2)
    flagged = [row for row in d["rows"] if row["flag"] is not None]
    assert [row["config"] for row in flagged] == [{"case": "HumanEval/129@0.7"}, {"case": "HumanEval/129@0.0"}]
    hot, cold = flagged
    assert (hot["failed_a"], hot["runs_a"], hot["failed_b"], hot["runs_b"]) == (12, 32, 32, 32)
    assert (cold["failed_a"], cold["runs_a"], cold["failed_b"], cold["runs_b"]) == (20, 32, 32, 32)
    assert hot["q"] == pytest.approx(7.549550115e-6, rel=1e-9)
    assert cold["q"] == pytest.approx(2.255030752e-2, rel=1e-9)
    assert all(row["flag"] == "failed more in B" for row in flagged)
