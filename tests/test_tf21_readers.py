"""TF21-51 to TF21-54: signal and failure-kind extraction on the five existing readers, on the
committed real fixtures (spec section 18.1.1 rows 1 to 5, 18.5.2; SG1, SG2, SG11; SA6, SA7).

Each reader records what its source records, marks the rest not recorded (``None``), and gives
each failing row its kind by the built-in rules (``ref_kind``). The expectations are read from
the fixture files here, independently of the readers. The Prove reader is
``test_tf21_prove.py``. Each committed fixture is imported once for the module and only read
after; every import here is fast (all eleven together take about four seconds), so none goes to
the slow lane."""

from __future__ import annotations

import csv
import gzip
import json
import math
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from tf21_support import (
    INGEST,
    IMPORTS,
    STARTED,
    TAU2,
    do_import,
    records,
    run_import,
)

DEEPEVAL = INGEST / "deepeval"
JUNIT = INGEST / "junit"
RAGAS = INGEST / "ragas"
TABLE = INGEST / "table"
NOT_RECORDED = ("working_time_s", "ttft_s", "input_tokens", "output_tokens", "cached_tokens",
                "reasoning_tokens", "total_tokens", "steps", "horizon", "llm_calls", "retries",
                "tool_call_count", "tool_error_count", "tool_calls")
EXCEPTION = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Failure|Warning)):")


class _R:
    """A record read as the reference reads a row (``ref_kind`` takes attributes)."""

    def __init__(self, rec: dict[str, Any]) -> None:
        self.result = rec["outcome"]
        self.error = None
        self.__dict__.update({k: v for k, v in rec.items() if k != "outcome"})
        self.signals = tuple(rec["signals"])
        self.scores = rec["scores"]
        self.tool_calls = None


def _kind(rec: dict[str, Any], error: str | None = None) -> str | None:
    from tf21_support import ref_kind

    r = _R(rec)
    r.error = error
    return ref_kind(r)


class _Imports:
    """Each committed fixture imported once for the module, into a store of its own. The tests
    only read: ``root`` is the store as the import left it, ``records`` a fresh list each call."""

    def __init__(self, factory: pytest.TempPathFactory) -> None:
        self._factory = factory
        self._roots: dict[str, Path] = {}
        self._records: dict[str, list[dict[str, Any]]] = {}

    def root(self, key: str) -> Path:
        if key not in self._roots:
            root = self._factory.mktemp(key) / "store"
            do_import(key, root)
            self._roots[key] = root
        return self._roots[key]

    def records(self, key: str) -> list[dict[str, Any]]:
        if key not in self._records:
            self._records[key] = records(self.root(key), key)
        return [dict(r) for r in self._records[key]]


@pytest.fixture(scope="module")
def imports(tmp_path_factory: pytest.TempPathFactory) -> _Imports:
    return _Imports(tmp_path_factory)


@pytest.fixture(scope="module")
def tau2_lines() -> list[dict[str, Any]]:
    """The committed tau2 run's real values, one table line a try, read once for the module."""
    from poisson_prove.store import Store

    df = Store(TAU2).read("20260915T210140Z-4847", meta=True, trace="full")
    lines = []
    for h, o, w, m in zip(df["config_hash"], df["outcome"], df["wall_time"], df["meta"],
                          strict=True):
        spans = (m.get("trace") or {}).get("spans") or []
        ins = [s["tokens"]["in"] for s in spans if s.get("tokens") and "in" in s["tokens"]]
        lines.append({"case": h, "outcome": o, "wall_time_s": repr(float(w)),
                      "input_tokens": str(sum(ins)) if ins else "",
                      "agent_cost": repr(float(m["cost_tau2"]["agent"]))})
    return lines


def _order(cases: list[str]) -> list[tuple[str, int]]:
    seen: Counter[str] = Counter()
    out = []
    for c in cases:
        out.append((c, seen[c]))
        seen[c] += 1
    return out


# ---------- TF21-51: DeepEval ----------


def _deepeval(name: str) -> list[dict[str, Any]]:
    return json.loads(gzip.decompress((DEEPEVAL / name).read_bytes()))["testCases"]


@pytest.mark.parametrize("key", ["deepeval-a", "deepeval-b"])
def test_tf21_51_deepeval_records_time_lengths_and_every_metric(imports: _Imports, key: str) -> None:
    cases = _deepeval(f"humaneval-{key[-1]}.json.gz")
    got = {(r["case"], r["repeat"]): r for r in imports.records(key)}
    assert len(got) == len(cases)
    for (case, repeat), tc in zip(_order([tc["name"] for tc in cases]), cases, strict=True):
        rec = got[(case, repeat)]
        metric = next(m for m in tc["metricsData"] if m["name"] == "Tests Passed")
        assert rec["outcome"] == ("pass" if metric["success"] else "fail")
        assert rec["wall_time_s"] == tc["runDuration"]
        assert rec["input_chars"] == len(tc["input"])
        assert rec["output_chars"] == len(tc["actualOutput"])
        assert rec["scores"] == {m["name"]: float(m["score"]) for m in tc["metricsData"]}
        assert rec["score"] == float(metric["score"])
        assert rec["cost_usd"] is None  # this DeepEval run saved no tokenCost
        assert rec["error_type"] is None and rec["feedback"] == {}
        for name in NOT_RECORDED:
            assert rec[name] is None, name


@pytest.mark.parametrize(("key", "missed"), [("deepeval-a", 1338), ("deepeval-b", 1387)])
def test_tf21_51_deepeval_failures_are_wrong_answers(imports: _Imports, key: str, missed: int) -> None:
    recs = imports.records(key)
    kinds = Counter(r["failure_kind"] for r in recs)
    assert kinds == Counter({None: len(recs) - missed, "wrong_answer": missed})
    assert all(r["failure_kind"] == _kind(r) for r in recs)


def test_tf21_51_deepeval_text_is_measured_never_kept(imports: _Imports) -> None:
    root = imports.root("deepeval-a")
    blob = b"".join(p.read_bytes() for p in root.rglob("*") if p.is_file())
    assert b"at temperature 0.0" not in blob
    assert b"HumanEval/152 at" not in blob


# ---------- TF21-52: JUnit ----------


def _junit_expected(paths: list[Path]) -> Counter[tuple[Any, ...]]:
    out: Counter[tuple[Any, ...]] = Counter()
    for path in paths:
        for tc in ET.parse(path).iter("testcase"):
            child = next((c for c in tc if c.tag in ("failure", "error")), None)
            skipped = any(c.tag == "skipped" for c in tc)
            time = tc.get("time")
            wall = float(time) if time not in (None, "") else None
            if child is not None:
                etype = child.get("type") or None
                if etype is None:
                    m = EXCEPTION.match(child.get("message") or "")
                    etype = m.group(1) if m else None
                span = "grader" if child.tag == "failure" else "lifecycle"
                out[("fail", wall, etype, span)] += 1
            elif skipped:
                out[(None, wall, None, None)] += 1
            else:
                out[("pass", wall, None, None)] += 1
    return out


@pytest.mark.parametrize("key", ["junit-a", "junit-b", "junit-suite"])
def test_tf21_52_junit_records_time_and_the_exception_class(imports: _Imports, key: str) -> None:
    paths = [Path(p) for p in IMPORTS[key][1:]]
    recs = imports.records(key)
    got = Counter((r["outcome"], r["wall_time_s"], r["error_type"], r["error_span_kind"])
                  for r in recs)
    assert got == _junit_expected(paths)
    for r in recs:
        for name in (*NOT_RECORDED, "input_chars", "output_chars", "cost_usd", "score"):
            assert r[name] is None, name
        assert r["scores"] == {} and r["feedback"] == {}


def test_tf21_52_a_recorded_zero_time_is_zero_not_missing(imports: _Imports) -> None:
    recs = imports.records("junit-a")
    assert sum(1 for r in recs if r["wall_time_s"] == 0.0) > 600
    assert all(r["wall_time_s"] is not None for r in recs)


def test_tf21_52_junit_kinds(imports: _Imports) -> None:
    recs = imports.records("junit-a")
    assert Counter(r["failure_kind"] for r in recs) == Counter(
        {None: 569, "wrong_answer": 86, "crash": 1})
    assert all(r["failure_kind"] == _kind(r) for r in recs)
    suite = imports.records("junit-suite")
    skipped = [r for r in suite if r["outcome"] is None]
    assert len(skipped) == 2 and all(r["failure_kind"] is None for r in skipped)


def test_tf21_52_junit_keeps_no_message_text(imports: _Imports) -> None:
    root = imports.root("junit-a")
    blob = b"".join(p.read_bytes() for p in root.rglob("*") if p.is_file())
    for needle in (b"failed_assertion", b"the episode crashed", b"replay_humaneval.py:41"):
        assert needle not in blob


# ---------- TF21-53: Ragas ----------


def _ragas_rows(name: str) -> list[dict[str, Any]]:
    raw = (RAGAS / name).read_bytes()
    if name.endswith(".gz"):
        raw = gzip.decompress(raw)
    return [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]


def _number(x: Any) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return None if math.isnan(float(x)) else float(x)


RAGAS_KEYS = {
    "ragas-base": ("rag-base.jsonl", "faithfulness", "case"),
    "ragas-raft": ("rag-raft.jsonl", "faithfulness", "case"),
    "ragas-causal": ("memory-causal.jsonl.gz", "id_based_context_recall", "user_input"),
    "ragas-strong": ("memory-strong.jsonl.gz", "id_based_context_recall", "user_input"),
}


@pytest.mark.parametrize("key", sorted(RAGAS_KEYS))
def test_tf21_53_ragas_records_every_score_column_and_the_input_length(
    imports: _Imports, key: str
) -> None:
    name, metric, case_column = RAGAS_KEYS[key]
    rows = _ragas_rows(name)
    got = {(r["case"], r["repeat"]): r for r in imports.records(key)}
    for (case, repeat), row in zip(_order([str(r[case_column]) for r in rows]), rows, strict=True):
        rec = got[(case, repeat)]
        score = _number(row[metric])
        assert rec["outcome"] == ("censored" if score is None else "fail" if score < 0.5 else "pass")
        if score is None:
            assert rec["score"] is None  # a judge's NaN keeps no score
        want = {k: v for k, v in ((k, _number(v)) for k, v in row.items() if k != case_column)
                if v is not None}
        assert rec["scores"] == want
        text = row.get("user_input", row.get("question"))
        assert rec["input_chars"] == (len(text) if isinstance(text, str) else None)
        answer = row.get("response", row.get("answer"))
        assert rec["output_chars"] == (len(answer) if isinstance(answer, str) else None)
        for field in (*NOT_RECORDED, "wall_time_s", "cost_usd", "error_type"):
            assert rec[field] is None, field


@pytest.mark.parametrize("key", sorted(RAGAS_KEYS))
def test_tf21_53_ragas_kinds(imports: _Imports, key: str) -> None:
    recs = imports.records(key)
    for r in recs:
        if r["outcome"] == "censored":
            assert r["failure_kind"] == "unclassified_error"  # a judge's NaN
        else:
            assert r["failure_kind"] == _kind(r)


# ---------- TF21-54: tables ----------


@pytest.mark.parametrize("key", ["table-a", "table-b"])
def test_tf21_54_an_outcome_table_records_only_its_outcome(imports: _Imports, key: str) -> None:
    recs = imports.records(key)
    with (TABLE / f"humaneval-{key[-1]}.csv").open(encoding="utf-8", newline="") as fh:
        lines = list(csv.DictReader(fh))
    assert Counter(r["outcome"] for r in recs) == Counter(
        "fail" if line["outcome"] in ("failed_assertion", "crashed") else "pass" for line in lines)
    for r in recs:
        # a bare outcome column says a try failed, and nothing of how
        assert r["failure_kind"] == ("unclassified_error" if r["outcome"] == "fail" else None)
        for name in (*NOT_RECORDED, "wall_time_s", "input_chars", "output_chars", "cost_usd",
                     "score", "error_type"):
            assert r[name] is None, name
        assert r["scores"] == {}


def _tau2_table(path: Path, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A table of the committed tau2 run's real values, as a team's script would save it."""
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(lines[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(lines)
    return lines


TABLE_ARGV = ["--case-column", "case", "--outcome-column", "outcome", "--failed", "unsolved"]


def test_tf21_54_a_table_column_named_as_a_signal_is_read(
    tmp_path: Path, tau2_lines: list[dict[str, Any]]
) -> None:
    lines = _tau2_table(tmp_path / "tau2.csv", tau2_lines)
    r = run_import(["table", tmp_path / "tau2.csv", "--store", tmp_path / "st", "--run", "t",
                    *TABLE_ARGV, "--started", STARTED, "--json"])
    assert r.code == 0, r.out + r.err
    got = Counter((x["case"], x["wall_time_s"], x["input_tokens"]) for x in records(tmp_path / "st", "t"))
    want = Counter((x["case"], float(x["wall_time_s"]),
                    int(x["input_tokens"]) if x["input_tokens"] else None) for x in lines)
    assert got == want
    assert all(x["cost_usd"] is None for x in records(tmp_path / "st", "t"))


def test_tf21_54_an_empty_cell_is_not_recorded_and_zero_is_zero(
    tmp_path: Path, tau2_lines: list[dict[str, Any]]
) -> None:
    path = tmp_path / "t.csv"
    lines = _tau2_table(path, tau2_lines)
    text = path.read_text(encoding="utf-8").splitlines()
    # the first data line's tokens left empty, the second's written as 0
    head = text[0].split(",")
    at = head.index("input_tokens")
    one, two = text[1].split(","), text[2].split(",")
    one[at], two[at] = "", "0"
    path.write_text("\n".join([text[0], ",".join(one), ",".join(two), *text[3:]]) + "\n",
                    encoding="utf-8")
    r = run_import(["table", path, "--store", tmp_path / "st", "--run", "t", *TABLE_ARGV,
                    "--started", STARTED, "--json"])
    assert r.code == 0, r.out + r.err
    recs = records(tmp_path / "st", "t")
    firsts = {lines[0]["case"], lines[1]["case"]}
    toks = sorted(str(x["input_tokens"]) for x in recs if x["case"] in firsts)
    assert "None" in toks and "0" in toks


def test_tf21_54_a_signal_column_that_is_not_a_number_is_refused(
    tmp_path: Path, tau2_lines: list[dict[str, Any]]
) -> None:
    path = tmp_path / "t.csv"
    _tau2_table(path, tau2_lines)
    text = path.read_text(encoding="utf-8").splitlines()
    first = text[1].split(",")
    first[2] = "fast"
    path.write_text("\n".join([text[0], ",".join(first), *text[2:]]) + "\n", encoding="utf-8")
    r = run_import(["table", path, "--store", tmp_path / "st", "--run", "t", *TABLE_ARGV,
                    "--started", STARTED])
    assert r.code == 1
    assert "wall_time_s" in r.err and "fast" in r.err
    assert not (tmp_path / "st" / "t").exists()


def test_tf21_54_a_failure_kind_column_is_taken_as_written(
    tmp_path: Path, tau2_lines: list[dict[str, Any]]
) -> None:
    path = tmp_path / "k.csv"
    lines = _tau2_table(path, tau2_lines)
    text = path.read_text(encoding="utf-8").splitlines()
    out = [text[0] + ",failure_kind"]
    for line, row in zip(text[1:], lines, strict=True):
        out.append(line + ("," + ("tool_error" if row["outcome"] == "unsolved" else "")))
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    r = run_import(["table", path, "--store", tmp_path / "st", "--run", "t", *TABLE_ARGV,
                    "--started", STARTED])
    assert r.code == 0, r.out + r.err
    recs = records(tmp_path / "st", "t")
    assert {x["failure_kind"] for x in recs if x["outcome"] == "fail"} == {"tool_error"}
    assert {x["failure_kind"] for x in recs if x["outcome"] == "pass"} == {None}
