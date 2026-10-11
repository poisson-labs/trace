"""IR7 to IR9: two real pairs of Ragas score tables, imported and read by Trace (lane F, the
committed fixtures, no network). Every figure pinned here was recomputed from the fixtures before
it was pinned.

The memory pair: one stored memory-retrieval experiment, the same 1,800 lookups on a memory
with causal reads (old) and on one with strong reads (new), scored by Ragas 0.4.3's two id-based
context metrics. The public pair: two published result sets, a base model (old) and the same
model fine-tuned (new) on the same 150 questions, three model-judged Ragas scores each, reduced
to a hash of each question and the scores.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from proofload.store import Store
from support import FIXTURES, read_rows, run_import, run_trace

RAGAS = FIXTURES / "ingest" / "ragas"
MEMORY = {"memory-causal": "2026-09-28T19:37:36Z", "memory-strong": "2026-09-29T08:26:16Z"}
PUBLIC = {"rag-base": "2025-03-31T06:56:41Z", "rag-raft": "2025-03-31T07:16:07Z"}
RECALL, PRECISION = "id_based_context_recall", "id_based_context_precision"
PUBLIC_METRICS = ("faithfulness", "answer_correctness", "answer_relevancy")


def _file(name: str) -> Path:
    return RAGAS / (f"{name}.jsonl.gz" if name.startswith("memory") else f"{name}.jsonl")


def _table(name: str) -> list[dict[str, Any]]:
    raw = _file(name).read_bytes()
    if name.startswith("memory"):
        raw = gzip.decompress(raw)
    return [json.loads(line) for line in raw.decode("utf-8").splitlines()]


def _import(
    root: Path, name: str, metric: str, cut: str, case_column: str, started: str
) -> dict[str, Any]:
    r = run_import(
        [
            "ragas",
            str(_file(name)),
            "--store",
            str(root),
            "--run",
            f"{name}-{metric}",
            "--metric",
            metric,
            "--cut",
            cut,
            "--below",
            "--case-column",
            case_column,
            "--started",
            started,
            "--json",
        ]
    )
    assert r.code == 0, r.text
    return r.json()


@pytest.fixture(scope="module")
def memory(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, dict[str, Any]]]:
    root = tmp_path_factory.mktemp("memory") / "store"
    summaries = {}
    for name, started in MEMORY.items():
        summaries[f"{name}-{RECALL}"] = _import(root, name, RECALL, "1.0", "user_input", started)
        summaries[f"{name}-{PRECISION}"] = _import(
            root, name, PRECISION, "0.5", "user_input", started
        )
    return root, summaries


@pytest.fixture(scope="module")
def public(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, dict[str, Any]]]:
    root = tmp_path_factory.mktemp("public") / "store"
    summaries = {}
    for name, started in PUBLIC.items():
        for metric in PUBLIC_METRICS:
            summaries[f"{name}-{metric}"] = _import(root, name, metric, "0.5", "case", started)
    return root, summaries


def _fix_check(root: Path, old: str, new: str, max_mde: str) -> tuple[int, dict[str, Any], str]:
    argv = [
        "fix-check",
        old,
        new,
        "--store",
        root,
        "--event",
        "missed",
        "--inputs",
        "all",
        "--max-mde",
        max_mde,
    ]
    js, md = run_trace([*argv, "--json"]), run_trace([*argv, "--top", "0"])
    assert js.code == md.code, (js.code, md.code, md.err)
    return js.code, json.loads(js.out), " ".join(md.out.split())


def _kept(root: Path, run: str) -> list[float]:
    return [r["import"]["score"] for r in read_rows(root, run) if r["import"]["score"] is not None]


def test_ir7_to_ir9_the_fixture_files_are_the_committed_bytes() -> None:
    """Green by construction: the four files against SHA256SUMS."""
    sums = {}
    for line in (FIXTURES / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        sums[name] = digest
    for name in (*MEMORY, *PUBLIC):
        f = _file(name)
        assert sums[f"./ingest/ragas/{f.name}"] == hashlib.sha256(f.read_bytes()).hexdigest()


# ---------- IR7: the memory pair at recall ----------


@pytest.mark.parametrize(
    "name,missed,mean", [("memory-causal", 1140, 0.367), ("memory-strong", 0, 1.000)]
)
def test_ir7_the_memory_pair_at_recall_imports_to_its_counts(
    memory: tuple[Path, dict[str, Any]], name: str, missed: int, mean: float
) -> None:
    root, summaries = memory
    run = f"{name}-{RECALL}"
    rows = read_rows(root, run)
    assert len(rows) == 1800 and len({r["case"] for r in rows}) == 1800
    assert Counter(r["outcome"] for r in rows) == Counter({"missed": missed, "met": 1800 - missed})
    assert all(r["error"] is None for r in rows)
    d = summaries[run]
    assert (d["rows"], d["cases"], d["no_outcome"]) == (1800, 1800, {})
    # the score kept on each row is the one Ragas wrote for that row
    wrote = {t["user_input"]: t[RECALL] for t in _table(name)}
    assert {r["case"]: r["import"]["score"] for r in rows} == wrote
    assert round(sum(_kept(root, run)) / 1800, 3) == mean


def test_ir7_fix_check_on_recall_reads_different_the_new_version_failed_less(
    memory: tuple[Path, dict[str, Any]],
) -> None:
    root, _ = memory
    code, d, text = _fix_check(root, f"memory-causal-{RECALL}", f"memory-strong-{RECALL}", "0.10")
    assert code == 0, text
    assert (d["rows"]["old"]["failed"], d["rows"]["old"]["runs"]) == (1140, 1800)
    assert (d["rows"]["new"]["failed"], d["rows"]["new"]["runs"]) == (0, 1800)
    assert (d["inputs"]["compared"], sum(d["inputs"]["left_out"].values())) == (1800, 0)
    t = d["test"]
    assert t["observed_new"] == 0
    assert t["expected_new"] == pytest.approx(570.0, abs=1e-9)
    assert t["variance"] == pytest.approx(285.0, abs=1e-9)
    assert d["difference"]["points"] == pytest.approx(-0.633333, abs=1e-6)
    assert d["difference"]["lo"] == pytest.approx(-0.655595, abs=1e-4)
    assert d["difference"]["hi"] == pytest.approx(-0.611071, abs=1e-4)
    assert d["limits"]["drop"] == pytest.approx(0.0509, abs=1e-4)
    assert (d["verdict"], d["direction"]) == ("different", "failed less in new")
    assert "different: the new version failed less" in text


# ---------- IR8: the memory pair at precision, where Ragas could not score ----------


def test_ir8_precision_has_no_score_exactly_where_nothing_was_retrieved(
    memory: tuple[Path, dict[str, Any]],
) -> None:
    root, summaries = memory
    old, new = summaries[f"memory-causal-{PRECISION}"], summaries[f"memory-strong-{PRECISION}"]
    assert (old["rows"], old["outcomes"], old["no_outcome"]) == (
        1800,
        {"met": 331, "missed": 339},
        {"no score": 1130},
    )
    assert (new["rows"], new["no_outcome"]) == (1800, {})
    nothing = {t["user_input"] for t in _table("memory-causal") if not t["retrieved_context_ids"]}
    unscored = {
        r["case"] for r in read_rows(root, f"memory-causal-{PRECISION}") if r["outcome"] is None
    }
    assert len(nothing) == 1130 and unscored == nothing
    assert Store(root).tally(f"memory-causal-{PRECISION}").no_outcome == 1130
    for run, n, mean in (
        (f"memory-causal-{PRECISION}", 670, 0.453),
        (f"memory-strong-{PRECISION}", 1800, 0.458),
    ):
        kept = _kept(root, run)
        assert len(kept) == n and round(sum(kept) / n, 3) == mean


def test_ir8_fix_check_on_precision_reads_no_significant_difference_on_670_cases(
    memory: tuple[Path, dict[str, Any]],
) -> None:
    root, _ = memory
    code, d, text = _fix_check(
        root, f"memory-causal-{PRECISION}", f"memory-strong-{PRECISION}", "0.05"
    )
    assert code == 0, text
    assert (d["inputs"]["compared"], d["inputs"]["informative"]) == (670, 3)
    assert {k: v for k, v in d["inputs"]["left_out"].items() if v} == {
        "no outcome on the old version": 1130
    }
    assert (d["rows"]["old"]["failed"], d["rows"]["old"]["runs"]) == (339, 670)
    assert (d["rows"]["new"]["failed"], d["rows"]["new"]["runs"]) == (338, 670)
    t = d["test"]
    assert (t["observed_new"], t["expected_new"], t["variance"]) == (
        338,
        pytest.approx(338.5, abs=1e-9),
        pytest.approx(0.75, abs=1e-9),
    )
    assert t["p"] == pytest.approx(1.0, abs=1e-9)
    assert d["limits"]["drop"] == pytest.approx(0.017, abs=1e-3)
    assert d["verdict"] == "no significant difference"
    # the header says how many cases were left out, and why, before the line that states the result
    left = re.search(r"left out 1,130 \(no outcome on the old version 1,130", text)  # R18: counts with separators
    line = text.find("**no significant difference")  # the result line inside the report; the verdict line opens stdout
    assert left is not None and 0 <= left.start() < line, text


# ---------- IR9: the public pair ----------


@pytest.mark.parametrize(
    "metric,no_score,means",
    [
        ("faithfulness", (3, 8), (0.550, 0.566)),
        ("answer_correctness", (0, 0), (0.440, 0.472)),
        ("answer_relevancy", (0, 0), (0.618, 0.743)),
    ],
)
def test_ir9_the_public_pair_imports_to_its_counts(
    public: tuple[Path, dict[str, Any]],
    metric: str,
    no_score: tuple[int, int],
    means: tuple[float, float],
) -> None:
    """150 rows and 146 questions a version: one question three times, two twice, as published."""
    root, summaries = public
    for name, n, mean in zip(PUBLIC, no_score, means):
        run = f"{name}-{metric}"
        d = summaries[run]
        assert (d["rows"], d["cases"], d["repeats"]) == (150, 146, {"min": 1, "max": 3})
        assert d["no_outcome"] == ({"no score": n} if n else {})
        rows = read_rows(root, run)
        assert sorted(Counter(Counter(r["case"] for r in rows).values()).items()) == [
            (1, 143),
            (2, 2),
            (3, 1),
        ]
        kept = _kept(root, run)
        assert len(kept) == 150 - n and round(sum(kept) / len(kept), 3) == mean


def test_ir9_fix_check_on_faithfulness_is_too_small_to_tell(
    public: tuple[Path, dict[str, Any]],
) -> None:
    root, _ = public
    code, d, text = _fix_check(root, "rag-base-faithfulness", "rag-raft-faithfulness", "0.10")
    assert code == 0, text  # R17: a result exits 0, too small to tell included
    assert (d["inputs"]["selected"], d["inputs"]["compared"]) == (146, 137)
    assert {k: v for k, v in d["inputs"]["left_out"].items() if v} == {
        "no outcome on the old version": 3,
        "no outcome on the new version": 6,
    }
    assert (d["rows"]["old"]["failed"], d["rows"]["old"]["runs"]) == (51, 141)
    assert (d["rows"]["new"]["failed"], d["rows"]["new"]["runs"]) == (46, 141)
    t = d["test"]
    assert (t["observed_new"], t["expected_new"]) == (46, pytest.approx(48.5, abs=1e-9))
    assert t["variance"] == pytest.approx(17.0833, abs=1e-4)
    assert t["p"] == pytest.approx(0.629, abs=1e-3)
    assert d["limits"]["drop"] == pytest.approx(0.1588, abs=1e-4)
    assert d["verdict"] == "too small to tell"
    assert d["guidance"] == {"repeats": 3, "inputs": 356, "accepts_at": 0.1588}


@pytest.mark.parametrize(
    "metric,old,new,expected,variance,p,points,lo,hi",
    [
        ("answer_correctness", 107, 87, 97.0, 14.3333, 0.011, -0.133333, -0.231, -0.036),
        ("answer_relevancy", 49, 32, 40.5, 9.75, 0.009, -0.113333, -0.193, -0.034),
    ],
)
def test_ir9_fix_check_on_answer_correctness_and_relevancy_reads_failed_less(
    public: tuple[Path, dict[str, Any]],
    metric: str,
    old: int,
    new: int,
    expected: float,
    variance: float,
    p: float,
    points: float,
    lo: float,
    hi: float,
) -> None:
    root, _ = public
    code, d, text = _fix_check(root, f"rag-base-{metric}", f"rag-raft-{metric}", "0.10")
    assert code == 0, text
    assert (d["inputs"]["compared"], sum(d["inputs"]["left_out"].values())) == (146, 0)
    assert (d["rows"]["old"]["failed"], d["rows"]["old"]["runs"]) == (old, 150)
    assert (d["rows"]["new"]["failed"], d["rows"]["new"]["runs"]) == (new, 150)
    t = d["test"]
    assert (t["observed_new"], t["expected_new"]) == (new, pytest.approx(expected, abs=1e-9))
    assert t["variance"] == pytest.approx(variance, abs=1e-4)
    assert t["p"] == pytest.approx(p, abs=1e-3)
    assert d["difference"]["points"] == pytest.approx(points, abs=1e-6)
    assert (d["difference"]["lo"], d["difference"]["hi"]) == (
        pytest.approx(lo, abs=1e-3),
        pytest.approx(hi, abs=1e-3),
    )
    assert (d["verdict"], d["direction"]) == ("different", "failed less in new")
    assert "different: the new version failed less" in text
