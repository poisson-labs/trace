"""BD-2: the breakdown in ``--json``, in the saved verdict and in the API's typed results, the same
counts as the failure-type diff TF6 saves.

**BD-2a** ``--json`` of ``fix-check``, ``compare`` and ``changes`` carries ``failure_taxonomy_diff``,
before ``continuous_measures`` (when ``--measures`` prints it), ``verdicts`` (when a file was
joined) and ``next``; ``where``'s does not. Nothing else in the document moves (BD-5 holds the
bytes) and the schema names stay.

**BD-2b** It is the very object the saved verdict holds (``result.json``), the API result's
``failure_taxonomy_diff``, and what the API's ``to_json()`` prints.

**BD-2c** The section printed is that object's counts: each row's counts, shares and change are
worked out from it, every kind and signal it lists has its row, and the tries line is its tries
(held with BD-2b's API result). The JSON lists kinds in precedence, the section by count.

**BD-2d** The saved ``report.md`` holds the section as the plain report prints it; the API's
``to_markdown()`` too; a bundle with it passes ``handover --check``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from breakdown_support import (
    AFTER, ARMS, BEFORE, EV, HEADING, KINDS, SIGNALS, TWO_RUNS, argv_of, expected_section, ok,
    prove_store, section, table_rows, table_store,
)
from look_support import chdir

SCHEMAS = {"fix-check": "poisson-trace.fix-check/2", "compare": "poisson-trace.compare/1",
           "changes": "poisson-trace.changes/2", "where": "poisson-trace.where/1"}


def _diff_section(verb: str, diff: dict[str, Any]) -> list[str]:
    a, b = ARMS[verb]
    kinds = {k["failure_kind"]: (k[a], k[b]) for k in diff["kinds"]}
    signals = {s["signal"]: (s[a], s[b]) for s in diff["signals"]}
    return expected_section(verb, kinds, signals, (diff["tries"][a], diff["tries"][b]))


# ---------- BD-2a ----------


@pytest.mark.parametrize("verb", TWO_RUNS)
def test_bd_2a_json_carries_the_diff_before_next(verb: str, tmp_path: Path) -> None:
    store = prove_store(tmp_path)
    doc = ok(argv_of(verb, store, "--json")).json()
    assert list(doc)[-2:] == ["failure_taxonomy_diff", "next"], list(doc)
    assert doc["schema"] == SCHEMAS[verb]
    diff = doc["failure_taxonomy_diff"]
    assert list(diff) == ["taxonomy_sha256", "same_rules", "tries", "kinds", "signals"]
    # the JSON names the arms as the verb's ``runs`` does; the section names them in words
    assert set(diff["tries"]) == set(doc["runs"]) == set(ARMS[verb])


def test_bd_2a_fix_check_measures_after_the_diff(tmp_path: Path) -> None:
    doc = ok(argv_of("fix-check", prove_store(tmp_path), "--measures", "--json")).json()
    assert list(doc)[-3:] == ["failure_taxonomy_diff", "continuous_measures", "next"], list(doc)


def test_bd_2a_verdicts_after_the_diff(tmp_path: Path) -> None:
    old = {**{f"c{i}": ("failed" if i < 2 else "passed") for i in range(6)}, "c6": ""}
    new = {**{f"c{i}": ("failed" if i < 1 else "passed") for i in range(6)}, "c6": ""}
    store = table_store(tmp_path, {"old": old, "new": new})
    grades = tmp_path / "grades.csv"
    grades.write_text("case,outcome\nc6,fail\n", encoding="utf-8")
    doc = ok(["changes", "old", "new", "--store", str(store), "--event", "missed", "--verdicts", str(grades),
              "--json"]).json()
    assert list(doc)[-3:] == ["failure_taxonomy_diff", "verdicts", "next"], list(doc)


def test_bd_2a_where_carries_none(tmp_path: Path) -> None:
    doc = ok(["where", AFTER, "--store", str(prove_store(tmp_path)), *EV, "--json"]).json()
    assert "failure_taxonomy_diff" not in doc and doc["schema"] == SCHEMAS["where"]


# ---------- BD-2b ----------


@pytest.mark.parametrize("verb", TWO_RUNS)
def test_bd_2b_the_saved_diff_is_the_printed_one(verb: str, tmp_path: Path) -> None:
    store = prove_store(tmp_path)
    printed = ok(argv_of(verb, store, "--save", "--json")).json()
    assert list(printed)[-3:] == ["failure_taxonomy_diff", "saved", "next"], list(printed)
    folder = store / printed["saved"]
    result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    assert result["failure_taxonomy_diff"] == printed["failure_taxonomy_diff"]
    # result.json keeps its order: the printed keys first (the diff among them), then TF6's
    body = [k for k in printed if k not in ("saved", "next")]
    added = [k for k in ("summary", "before_you_act", "note", "versions", "failure_taxonomy_diff",
                         "continuous_measures") if k not in body]
    assert list(result) == [*body, *added, "saved", "next"], list(result)


def _api_call(verb: str, store: Path) -> Any:
    from poisson_trace import api

    common: dict[str, Any] = {"event": ["violated", "timeout"]}
    if verb == "fix-check":
        return api.fix_check(str(store), BEFORE, AFTER, inputs="all", max_mde=0.10, **common)
    if verb == "compare":
        return api.compare(str(store), BEFORE, AFTER, max_mde_hr=1.5, **common)
    return api.changes(str(store), BEFORE, AFTER, **common)


@pytest.mark.parametrize("verb", TWO_RUNS)
def test_bd_2b_the_api_result_carries_the_same(verb: str, tmp_path: Path) -> None:
    store = prove_store(tmp_path)
    with chdir(tmp_path):
        r = _api_call(verb, Path("store"))
        printed = ok(argv_of(verb, Path("store"), "--json"))
        plain = ok(argv_of(verb, Path("store")))
        as_json = json.loads(r.to_json())
        assert r.to_json() == printed.out
        assert as_json["failure_taxonomy_diff"] == json.loads(json.dumps(r.failure_taxonomy_diff))
        assert r.to_markdown() == plain.out
    diff = as_json["failure_taxonomy_diff"]
    assert section(r.to_markdown()) == _diff_section(verb, diff)
    # the JSON keeps its own order of signals
    assert [s["signal"] for s in diff["signals"]] == [s for s in SIGNALS if s in [x["signal"] for x in diff["signals"]]]
    del store


# ---------- BD-2c ----------


def test_bd_2c_the_diff_lists_kinds_in_precedence_and_the_section_by_count(tmp_path: Path) -> None:
    """The JSON keeps the kinds' precedence order (TF6's); the table orders by count."""
    doc = ok(argv_of("fix-check", prove_store(tmp_path), "--json")).json()
    listed = [k["failure_kind"] for k in doc["failure_taxonomy_diff"]["kinds"]]
    assert listed == sorted(listed, key=KINDS.index) == ["loop_detected", "step_limit", "tool_error"]
    rows = table_rows(section(ok(argv_of("fix-check", tmp_path / "store")).out))
    assert [r[0] for r in rows] == ["tool_error", "loop_detected", "step_limit", "all failures"]


# ---------- BD-2d ----------


@pytest.mark.parametrize("verb", TWO_RUNS)
def test_bd_2d_report_md_holds_the_section(verb: str, tmp_path: Path) -> None:
    store = prove_store(tmp_path)
    plain = ok(argv_of(verb, store)).out
    doc = ok(argv_of(verb, store, "--save", "--json")).json()
    report = (store / doc["saved"] / "report.md").read_text(encoding="utf-8")
    assert section(report) == section(plain)
    assert report.count(HEADING) == 1


@pytest.mark.parametrize("verb", TWO_RUNS)
def test_bd_2d_a_bundle_with_it_passes_the_check(verb: str, tmp_path: Path) -> None:
    store = prove_store(tmp_path)
    ok(argv_of(verb, store, "--out", str(tmp_path / "bundle")))
    checked = ok(["handover", "--check", str(tmp_path / "bundle")])
    assert checked.out.startswith("ok  ")
    result = json.loads((tmp_path / "bundle" / "result.json").read_text(encoding="utf-8"))
    assert result["failure_taxonomy_diff"]["same_rules"] is True

