"""TF3-35 to TF3-37: the two fixtures (a reader is listed only on a real file the tool wrote,
committed with its provenance and its checksum).

- TF3-35: every file of ``tests/fixtures/ingest/table`` and ``…/junit`` that is data is listed in
  ``SHA256SUMS`` and holds its digest, and ``PROVENANCE.md`` has a section for each naming its
  recipe.
- TF3-36: the HumanEval tables, read back through the table reader and Prove, give the source
  store's failures case by case; and the fix check and the changes on the two imported runs give
  the source runs' numbers.
- TF3-37: the JUnit pairs, read back: each report of Trace's own tests is 91 test cases, 90 passed
  and 1 skipped; each replay report holds its stored run's failures, problem by problem, four
  repeats each when the case is the test's name.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from poisson_prove.store import Store

from conftest import FIXTURES
from look_support import HE_A, HE_B, HUMANEVAL, chdir, trace
from setup_support import scratch_home  # noqa: F401
from junit_table_support import HE_FAILED, OWN_1, OWN_2, SUITE_1, SUITE_2, by_case, he_table_argv, imported, junit_argv, read_rows, sha256, verb

DATA = {"table": ("humaneval-a.csv", "humaneval-b.csv"), "junit": ("trace-suite-1.xml", "trace-suite-2.xml", "humaneval-a.xml", "humaneval-b.xml")}


def _sums() -> dict[str, str]:
    out = {}
    for line in (FIXTURES / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        out[name.removeprefix("./")] = digest
    return out


# ---------- TF3-35 ----------


@pytest.mark.parametrize("tool", ["table", "junit"])
def test_tf3_35_each_fixture_is_listed_with_its_digest_and_its_provenance(tool: str) -> None:
    sums = _sums()
    folder = FIXTURES / "ingest" / tool
    for name in DATA[tool]:
        key = f"ingest/{tool}/{name}"
        assert sums.get(key) == sha256(folder / name), key
    assert (folder / "make.py").is_file()
    provenance = (FIXTURES / "PROVENANCE.md").read_text(encoding="utf-8")
    sections = [s for s in provenance.split("\n## ") if f"ingest/{tool}/" in s]
    assert sections and any("make.py" in s for s in sections), tool


# ---------- TF3-36: the tables ----------


def _source_failures(run: str) -> dict[str, int]:
    frame = Store(HUMANEVAL).read(run, meta=False)
    out: Counter[str] = Counter()
    for row in frame.itertuples(index=False):
        case = f"{row.config['task_id']}@{row.config['temperature']}"
        out[case] += row.outcome in HE_FAILED
    return dict(out)


@pytest.fixture(scope="module")
def tables(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("tables")
    with chdir(folder):
        for which in ("a", "b"):
            imported(verb([*he_table_argv("st", f"he-{which}", which), "--json"]))
    return folder / "st"


@pytest.mark.parametrize("which,run", [("a", HE_A), ("b", HE_B)])
def test_tf3_36_the_tables_hold_the_source_failures_case_by_case(tables: Path, which: str, run: str) -> None:
    got = by_case(read_rows(tables, f"he-{which}"))
    assert {case: outs.count("missed") for case, outs in got.items()} == _source_failures(run)
    assert all(len(outs) == 32 and None not in outs for outs in got.values())


def _close(a: Any, b: Any) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12)
    return bool(a == b)


def test_tf3_36_the_fix_check_on_the_tables_is_the_source_s(tables: Path) -> None:
    common = ["--inputs", "all", "--max-mde", "0.05", "--json"]
    source = json.loads(trace(["fix-check", HE_A, HE_B, "--store", str(HUMANEVAL), "--event", HE_FAILED[0], "--event", HE_FAILED[1], *common]).out)
    result = trace(["fix-check", "he-a", "he-b", "--store", str(tables), "--event", "missed", *common])
    assert result.code == 0, result.text
    got = json.loads(result.out)
    assert got["verdict"] == source["verdict"]
    for section, keys in {
        "test": ("observed_new", "expected_new", "variance", "p"),
        "difference": ("points", "lo", "hi"),
        "limits": ("drop", "rise"),
        "consistency": ("failure_share", "fails_again", "kappa"),
        "inputs": ("compared", "informative"),
    }.items():
        for key in keys:
            assert _close(got[section][key], source[section][key]), (section, key, got[section][key], source[section][key])
    assert got["rows"]["old"]["failed"] == 1_338 and got["rows"]["new"]["failed"] == 1_387
    assert got["by_input"]["moved"] == source["by_input"]["moved"]


def test_tf3_36_the_changes_on_the_tables_are_the_source_s(tables: Path) -> None:
    source = json.loads(trace(["changes", HE_A, HE_B, "--store", str(HUMANEVAL), "--event", HE_FAILED[0], "--event", HE_FAILED[1], "--json"]).out)
    result = trace(["changes", "he-a", "he-b", "--store", str(tables), "--event", "missed", "--json"])
    assert result.code == 0, result.text
    got = json.loads(result.out)
    assert got["verdict"] == source["verdict"]
    for key in ("tested", "flagged", "lone_threshold", "smallest_attainable_p", "together", "lone_flip_repeats"):
        assert _close(got[key], source[key]), (key, got[key], source[key])
    assert got["flagged"] == 2


# ---------- TF3-37: the JUnit pairs ----------


@pytest.mark.parametrize("report", [OWN_1, OWN_2], ids=["trace-suite-1", "trace-suite-2"])
def test_tf3_37_each_report_of_trace_s_own_tests_is_its_suite(tmp_path: Path, report: Path) -> None:
    with chdir(tmp_path):
        doc = imported(verb([*junit_argv(report, "st", "r"), "--json"]))
    assert doc["rows"] == 91 and doc["cases"] == 91 and doc["outcomes"] == {"met": 90, "missed": 0}
    assert sum(doc["no_outcome"].values()) == 1
    assert [(f["name"], f["sha256"]) for f in doc["files"]] == [(report.name, sha256(report))]


def _replayed(run: str) -> dict[str, int]:
    """Each problem's failures at temperature 0.7 in replicates 0 to 3 of the stored run."""
    frame = Store(HUMANEVAL).read(run, meta=False)
    out: Counter[str] = Counter()
    for row in frame.itertuples(index=False):
        if row.config["temperature"] == 0.7 and row.replicate_index < 4:
            out[row.config["task_id"]] += row.outcome in HE_FAILED
    return dict(out)


@pytest.mark.parametrize("report,run", [(SUITE_1, HE_A), (SUITE_2, HE_B)], ids=["humaneval-a", "humaneval-b"])
def test_tf3_37_each_replay_report_holds_its_run_s_failures(tmp_path: Path, report: Path, run: str) -> None:
    with chdir(tmp_path):
        doc = imported(verb([*junit_argv(report, "st", "r", "--case", "name"), "--json"]))
    assert doc["rows"] == 656 and doc["cases"] == 164 and doc["repeats"] == {"min": 4, "max": 4}
    got = by_case(read_rows(tmp_path / "st", "r"))
    replayed = {f"test_solves[{task}]": n for task, n in _replayed(run).items()}
    assert {case: outs.count("missed") for case, outs in got.items()} == replayed
