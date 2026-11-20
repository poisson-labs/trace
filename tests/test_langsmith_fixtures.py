"""TF24-1 to TF24-3: the committed LangSmith captures, and the facts about LangSmith's exports
that only the captures show.

- TF24-1: every data file under ``tests/fixtures/ingest/langsmith`` is listed in ``SHA256SUMS``
  with its digest, the set of them as committed; ``PROVENANCE.md`` has the section
  naming the tools' versions; the two scripts are committed beside the files.
- TF24-2: the three facts the captures correct. LangSmith's UI offers no JSON: ``ui/`` holds the
  two CSVs and nothing else. The command's trace export writes ``<trace_id>.jsonl``, one a trace,
  each row of it of that trace. The v2 run query's ``status`` is lower-case. And beside them what
  the reader's shapes rest on: the keys that tell v1, v2 and the command's rows apart; the
  command's export carrying an empty ``status`` on every run, no ``reference_example_id`` and no
  ``dotted_order``, and the example's ``case`` as ``custom_metadata.ls_example_case``; an errored
  experiment root carrying its ``reference_example_id``; one level of nesting.
- TF24-3: the counts the tests rest on: 48 and 51 runs, ten traces each; 39 and 41 feedback
  records with their sources (``model``, ``api``, and ``app`` on the candidate's two); the pages
  hold the whole pull; and the late statistics: ``exact`` is in ``feedback_stats`` on 8 of the 10
  baseline roots in v2, v2 with subtree usage and the command's exports, and on all 10 in v1 and
  in the feedback list, while the candidate agrees everywhere.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter

import pytest

from signals_support import FIXTURES
from langsmith_support import (
    API, CASES, CHILDREN, CLI, EXACT, FEEDBACK, LATE, LS, RUNS, TRACE_EXPORTS, UI, USUAL, VERSIONS, case_of_root,
    children, example_ids, export, feedback_file, feedback_pages, parent_of, roots, rows_of, run_id,
)

#: SHA-256 of the sorted ``SHA256SUMS`` lines of the LangSmith capture, as committed.
SUMS_DIGEST = "2ae17b26d92edc1f96858cfd5b6b768c5ae89e3561ccfbe83dbf28fdb77e33c3"
DATA_FILES = 46


def _data_files() -> list[str]:
    return sorted(str(p.relative_to(FIXTURES)) for p in LS.rglob("*") if p.is_file() and p.suffix != ".py" and "__pycache__" not in p.parts)


# ---------- TF24-1 ----------


def test_tf24_1_every_capture_is_listed_with_its_digest() -> None:
    listed = {}
    for line in (FIXTURES / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        if name.startswith("./ingest/langsmith/"):
            listed[name[2:]] = digest
    files = _data_files()
    assert len(files) == DATA_FILES, len(files)
    assert sorted(n for n in listed if not n.endswith(".py")) == files
    for name in files:
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == listed[name], name
    lines = "".join(f"{listed[n]}  {n}\n" for n in files)
    assert hashlib.sha256(lines.encode("utf-8")).hexdigest() == SUMS_DIGEST


def test_tf24_1_the_provenance_names_the_tools_and_the_scripts_are_committed() -> None:
    text = (FIXTURES / "PROVENANCE.md").read_text(encoding="utf-8")
    section = text.split("## Added for the LangSmith captures", 1)[1]
    for said in ("langsmith 0.14.17", "v0.3.13", "trace-fixture-baseline-bbb64b8e", "trace-fixture-candidate-7e3f7200",
                 "there is no JSON download from the UI", "the command writes `.jsonl`", "lower-case"):
        assert said in section, said
    assert (LS / "fixture_langsmith.py").is_file() and (LS / "pull.py").is_file()


# ---------- TF24-2 ----------


def test_tf24_2_the_ui_offers_csv_only() -> None:
    assert sorted(p.name for p in UI.iterdir()) == ["trace-fixture-baseline-bbb64b8e.csv", "trace-fixture-candidate-7e3f7200.csv"]


@pytest.mark.parametrize("version", VERSIONS)
def test_tf24_2_the_trace_export_writes_one_jsonl_a_trace(version: str) -> None:
    files = export(version, "cli-traces")
    assert len(files) == 10 and all(p.suffix == ".jsonl" for p in files)
    assert sorted(p.name for p in (CLI / f"{version}-traces").iterdir()) == [p.name for p in files]
    held = []
    for path in files:
        rows = rows_of(path)
        assert {r["trace_id"] for r in rows} == {path.stem}, path.name
        assert sum(1 for r in rows if r["parent_run_id"] is None) == 1, path.name
        held += rows
    whole = rows_of(export(version, "cli-runs")[0])
    assert sorted(run_id(r) for r in held) == sorted(run_id(r) for r in whole)
    assert len(held) == RUNS[version]


@pytest.mark.parametrize("version", VERSIONS)
def test_tf24_2_v2_status_is_lower_case_and_the_shapes_differ_by_their_keys(version: str) -> None:
    v2, v1, cli = (rows_of(export(version, kind)[0]) for kind in ("v2", "v1", "cli-runs"))
    assert {r["status"] for r in v2} == {"success", "error"} == {r["status"] for r in v1}
    assert {r["run_type"] for r in v2} == {"chain", "retriever", "tool", "llm", "parser"}
    for r in v2:
        assert "parent_run_id" not in r and "run_id" not in r and "parent_run_ids" in r and "is_root" in r
        assert isinstance(r["metadata"], dict)
    for r in v1:
        assert "parent_run_id" in r and "run_id" not in r and isinstance(r["extra"]["metadata"], dict)
    for r in cli:
        assert "run_id" in r and "id" not in r and "parent_run_id" in r
        assert r["status"] == "" and "reference_example_id" not in r and "dotted_order" not in r
        assert isinstance(r["custom_metadata"], dict)
    examples = example_ids()
    for rows in (v2, v1):
        for case, root in roots(rows).items():
            assert root["reference_example_id"] == examples[case], case
    assert sorted(roots(cli)) == list(CASES)
    # one level of nesting: every run that is not a root is a root's child
    for rows in (v2, v1, cli):
        ids = {run_id(r) for r in rows if parent_of(r) is None}
        assert all(parent_of(r) in ids for r in rows if parent_of(r) is not None)


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("kind", TRACE_EXPORTS)
def test_tf24_2_every_trace_is_the_runs_the_support_names(version: str, kind: str) -> None:
    rows = [r for path in export(version, kind) for r in rows_of(path)]
    assert len(rows) == RUNS[version]
    for case, root in roots(rows).items():
        under = sorted((r for r in rows if r["trace_id"] == root["trace_id"] and r is not root), key=lambda r: r["start_time"])
        got = tuple((r["run_type"], bool(r.get("error"))) for r in under)
        assert got == children(version, case), (case, got)
    assert set(CHILDREN) == {("baseline", "c08"), ("candidate", "c04"), ("candidate", "c09")} and len(USUAL) == 4


# ---------- TF24-3 ----------


@pytest.mark.parametrize("version", VERSIONS)
def test_tf24_3_the_feedback_records_and_their_sources(version: str) -> None:
    held = json.loads(feedback_file(version).read_text(encoding="utf-8"))
    assert len(held) == FEEDBACK[version]
    by = Counter((f["key"], f["feedback_source"]["type"]) for f in held)
    want = {("exact", "model"): 10, ("judge_correct", "model"): 9, ("thumbs", "api"): 10, ("review", "api"): 10}
    if version == "candidate":
        want[("human_thumbs", "app")] = 2
    assert dict(by) == want
    root_of = {run_id(r): case for case, r in roots(rows_of(export(version, "v1")[0])).items()}
    exact = {root_of[f["run_id"]]: float(f["score"]) for f in held if f["key"] == "exact"}
    assert exact == EXACT[version]


def test_tf24_3_the_pages_hold_the_whole_pull() -> None:
    for kind, whole in (("v2-pages", "v2"), ("v1-pages", "v1")):
        pages = [rows_of(p) for p in export("candidate", kind)]
        assert [len(p) for p in pages] == [25, 25, 1]
        assert sorted(run_id(r) for p in pages for r in p) == sorted(run_id(r) for r in rows_of(export("candidate", whole)[0]))
    pages = [json.loads(p.read_text(encoding="utf-8")) for p in feedback_pages()]
    assert [len(p) for p in pages] == [25, 16, 0]
    whole = json.loads(feedback_file("candidate").read_text(encoding="utf-8"))
    assert sorted(f["id"] for p in pages for f in p) == sorted(f["id"] for f in whole)


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("kind", TRACE_EXPORTS)
def test_tf24_3_the_statistics_trail_the_feedback_records_on_two_baseline_roots(version: str, kind: str) -> None:
    rows = [r for path in export(version, kind) for r in rows_of(path)]
    lacking = sorted(case for case, root in roots(rows).items() if "exact" not in (root.get("feedback_stats") or {}))
    assert lacking == ([] if kind == "v1" else list(LATE[version])), (version, kind, lacking)
    for case, root in roots(rows).items():
        stats = root.get("feedback_stats") or {}
        if "exact" in stats:
            assert float(stats["exact"]["avg"]) == EXACT[version][case], case
    assert case_of_root(next(iter(roots(rows).values()))) in CASES
    assert (API / "requests.json").is_file()
