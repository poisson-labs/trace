"""TF6-30 to TF6-35: ``--verdicts FILE`` on the comparison verbs, one file joined onto both runs,
by the rules TF22's import side follows.

The file is TF22's: ``.csv`` (``case``, ``input``, ``outcome``, ``score``,
``failure_kind``) or ``.jsonl`` (those, plus ``scores`` and ``feedback``). On a verb it is read
over both runs at once, in memory; nothing is written, to the store or anywhere. A stored
run's cases are those TF21's ``read_rows`` gives it: the case of an import, the input's hash of a
run Prove swept.

- TF6-30: a row joins every try of its case in each run that holds the case. A try with no
  outcome takes the verdict's: ``fail`` counts as failed, ``pass`` as not. A try with an
  outcome must agree, failed meaning an outcome among the verb's ``--event`` names.
- TF6-31: matched by case. On stored runs no input is kept, so an ``input`` column alone matches
  nothing. A row joins whichever runs hold its case.
- TF6-32: refused, exit 1, nothing on stdout, nothing written: a verdict disagreeing with a try
  (naming the case), a file none of whose rows matches a case in either run (naming the file), two
  rows for one case, a failure kind on a pass, an unknown column or outcome, a missing file.
- TF6-33: the verb says what was joined: ``--json`` gains ``verdicts`` (TF22's block:
  name, sha256, rows, by_case, by_input, unmatched) before ``saved`` and ``next``; the plain
  output gains one detail line right under the verdict line. Without ``--verdicts``, nothing
  changes.
- TF6-34: a saved verdict records the file's digest among its result-changing settings, never its
  name or path; the same bytes under another name are the same artifact. A verdict's failure kind
  reaches the saved verdict's failure-type counts; its scores and feedback reach nothing.
- TF6-35: ``where`` does not take it: exit 2.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from tf0_support import trace
from tf6_support import (
    argv012, artifacts, descriptor, result_of, run_ok, store012, tree, without_detail, write,
)

# c0 to c11 scored in both runs (c0 failed in both, c3 only in the old, c4 only in the new); c12
# with no outcome in both; c13 only in the new run, with no outcome
OUTCOMES = {
    "old": {**{f"c{j}": "failed" if j % 3 == 0 else "passed" for j in range(12)}, "c12": ""},
    "new": {**{f"c{j}": "failed" if j % 4 == 0 else "passed" for j in range(12)}, "c12": "", "c13": ""},
}
UNSCORED, PASSED, FAILED, ONLY_NEW = "c12", "c1", "c0", "c13"


def _store(tmp_path: Path) -> Path:
    store = tmp_path / "tables"
    for i, run in enumerate(("old", "new")):
        csv = write(tmp_path / f"{run}.csv", "case,outcome\n" + "".join(f"{c},{o}\n" for c, o in OUTCOMES[run].items()))
        made = trace(["import", "table", str(csv), "--store", str(store), "--run", run, "--case-column", "case",
                      "--outcome-column", "outcome", "--failed", "failed", "--started", f"2026-11-0{i + 1}T10:00:00Z"])
        assert made.code == 0, made.text
    return store


def _fix(store: Path, *extra: str) -> list[str]:
    return ["fix-check", "old", "new", "--store", str(store), "--event", "missed", "--inputs", "all",
            "--max-mde", "0.5", *extra]


def _changes(store: Path, *extra: str) -> list[str]:
    return ["changes", "old", "new", "--store", str(store), "--event", "missed", *extra]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------- TF6-30 ----------


@pytest.mark.parametrize("outcome,failed", [("fail", 1), ("pass", 0)])
def test_tf6_30_a_verdict_fills_the_untried_in_both_runs(tmp_path: Path, outcome: str, failed: int) -> None:
    store = _store(tmp_path)
    before = run_ok(_fix(store, "--json")).json()
    v = write(tmp_path / "v.csv", f"case,outcome\n{UNSCORED},{outcome}\n")
    after = run_ok(_fix(store, "--verdicts", str(v), "--json")).json()
    # c12 had no outcome in either run, so it was left out; with one, it is compared
    assert after["inputs"]["compared"] == before["inputs"]["compared"] + 1
    for arm in ("old", "new"):
        assert after["rows"][arm]["runs"] == before["rows"][arm]["runs"] + 1
        assert after["rows"][arm]["failed"] == before["rows"][arm]["failed"] + failed


def test_tf6_30_a_verdict_that_agrees_changes_nothing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    v = write(tmp_path / "v.csv", f"case,outcome\n{FAILED},fail\n{PASSED},pass\n")
    for argv in (_fix(store), _changes(store)):
        plain = run_ok(argv)
        joined = run_ok([*argv, "--verdicts", str(v)])
        assert without_detail(joined.out, "verdicts") == plain.out


def test_tf6_30_a_prove_runs_failures_are_its_event_words(tmp_path: Path) -> None:
    """On a run Prove swept the failures are the --event words. Every try of the 0.1.3 store has
    an outcome, so a verdict there can only agree, or be refused: here on the input none of whose
    tries failed in either run."""
    store = store012(tmp_path)
    rows = run_ok(argv012("changes", store, "--json")).json()["rows"]
    calm = next(r["config_hash"] for r in rows if r["failed_a"] == 0 and r["failed_b"] == 0)
    v = write(tmp_path / "v.csv", f"case,outcome\n{calm},pass\n")
    plain = run_ok(argv012("changes", store))
    assert without_detail(run_ok(argv012("changes", store, "--verdicts", str(v))).out, "verdicts") == plain.out
    bad = write(tmp_path / "bad.csv", f"case,outcome\n{calm},fail\n")
    ran = trace(argv012("changes", store, "--verdicts", str(bad)))
    assert ran.code == 1 and calm in ran.err, ran.text


# ---------- TF6-31 ----------


def test_tf6_31_an_input_column_never_matches_a_stored_run(tmp_path: Path) -> None:
    store = _store(tmp_path)
    v = write(tmp_path / "v.csv", f"case,input,outcome\n{UNSCORED},,fail\n,what is 2+2,pass\n")
    block = run_ok(_fix(store, "--verdicts", str(v), "--json")).json()["verdicts"]
    assert (block["rows"], block["by_case"], block["by_input"], block["unmatched"]) == (2, 1, 0, 1)


@pytest.mark.parametrize("verb", ["fix-check", "changes"])
def test_tf6_31_a_row_joins_whichever_run_holds_its_case(tmp_path: Path, verb: str) -> None:
    store = _store(tmp_path)
    v = write(tmp_path / "v.csv", f"case,outcome\n{UNSCORED},fail\n{ONLY_NEW},pass\nno-such-case,fail\n")
    argv = _fix(store) if verb == "fix-check" else _changes(store)
    block = run_ok([*argv, "--verdicts", str(v), "--json"]).json()["verdicts"]
    assert (block["rows"], block["by_case"], block["by_input"], block["unmatched"]) == (3, 2, 0, 1)


# ---------- TF6-32 ----------


def _refused(ran: Any) -> str:
    assert ran.code == 1 and ran.out == "", ran.text
    first = ran.err.splitlines()[0]
    assert first.startswith("error: ") and "Traceback" not in ran.err
    return first


def test_tf6_32_a_disagreement_is_refused_naming_the_case(tmp_path: Path) -> None:
    store = _store(tmp_path)
    v = write(tmp_path / "v.csv", f"case,outcome\n{PASSED},fail\n")
    before = tree(tmp_path)
    assert PASSED in _refused(trace(_fix(store, "--verdicts", str(v), "--save")))
    assert tree(tmp_path) == before
    w = write(tmp_path / "w.csv", f"case,outcome\n{FAILED},pass\n")
    assert FAILED in _refused(trace(_changes(store, "--verdicts", str(w))))


def test_tf6_32_a_file_matching_nothing_is_refused_naming_it(tmp_path: Path) -> None:
    store = _store(tmp_path)
    v = write(tmp_path / "grades.csv", "case,outcome\nno-such,fail\nnor-this,pass\n")
    assert "grades.csv" in _refused(trace(_fix(store, "--verdicts", str(v))))


@pytest.mark.parametrize("body", [
    f"case,outcome\n{UNSCORED},fail\n{UNSCORED},pass\n",
    f"case,outcome,failure_kind\n{PASSED},pass,crash\n",
    f"case,colour\n{UNSCORED},red\n",
    f"case,outcome\n{UNSCORED},maybe\n",
    f"case,outcome,failure_kind\n{UNSCORED},fail,meltdown\n",
])
def test_tf6_32_what_tf22_refuses_is_refused_here(tmp_path: Path, body: str) -> None:
    store = _store(tmp_path)
    v = write(tmp_path / "v.csv", body)
    _refused(trace(_fix(store, "--verdicts", str(v))))


def test_tf6_32_a_missing_file_is_refused(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert "nothing.csv" in _refused(trace(_fix(store, "--verdicts", str(tmp_path / "nothing.csv"))))


# ---------- TF6-33 ----------


@pytest.mark.parametrize("verb", ["fix-check", "changes"])
def test_tf6_33_the_json_and_the_plain_output_say_what_was_joined(tmp_path: Path, verb: str) -> None:
    store = _store(tmp_path)
    v = write(tmp_path / "grades.csv", f"case,outcome\n{UNSCORED},fail\nno-such-case,pass\n")
    argv = _fix(store) if verb == "fix-check" else _changes(store)
    doc = run_ok([*argv, "--verdicts", str(v), "--json"]).json()
    assert doc["verdicts"] == {"name": "grades.csv", "sha256": _sha(v), "rows": 2, "by_case": 1,
                               "by_input": 0, "unmatched": 1}
    assert list(doc)[-2:] == ["verdicts", "next"]
    saved = run_ok([*argv, "--verdicts", str(v), "--json", "--save"]).json()
    assert list(saved)[-3:] == ["verdicts", "saved", "next"]
    lines = run_ok([*argv, "--verdicts", str(v)]).out.splitlines()
    assert lines[1] == "  verdicts  grades.csv · rows 2 · joined by case 1 · by input 0 · matched no case 1", lines[:3]


def test_tf6_33_compare_takes_verdicts_on_a_prove_store(tmp_path: Path) -> None:
    store = store012(tmp_path)
    rows = run_ok(argv012("changes", store, "--json")).json()["rows"]
    calm = next(r["config_hash"] for r in rows if r["failed_a"] == 0 and r["failed_b"] == 0)
    v = write(tmp_path / "v.csv", f"case,outcome\n{calm},pass\n")
    plain = run_ok(argv012("compare", store))
    ran = run_ok(argv012("compare", store, "--verdicts", str(v)))
    assert without_detail(ran.out, "verdicts") == plain.out
    block = run_ok(argv012("compare", store, "--verdicts", str(v), "--json")).json()["verdicts"]
    assert (block["rows"], block["by_case"], block["by_input"], block["unmatched"]) == (1, 1, 0, 0)


def test_tf6_33_the_verdicts_line_comes_before_wrote_and_saved(tmp_path: Path) -> None:
    store = _store(tmp_path)
    v = write(tmp_path / "g.csv", f"case,outcome\n{UNSCORED},fail\n")
    lines = run_ok(_fix(store, "--verdicts", str(v), "--out", str(tmp_path / "b"))).out.splitlines()
    detail = [line.split("  ")[1] for line in lines[1:lines.index("")]]
    assert detail == ["verdicts", "wrote", "saved"], detail


def test_tf6_33_without_verdicts_nothing_changes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    v = write(tmp_path / "g.csv", f"case,outcome\n{FAILED},fail\n")
    for argv in (_fix(store), _changes(store)):
        doc = run_ok([*argv, "--verdicts", str(v), "--json"]).json()
        plain = run_ok([*argv, "--json"]).json()
        assert "verdicts" not in plain
        assert {k: x for k, x in doc.items() if k != "verdicts"} == plain


# ---------- TF6-34 ----------


def test_tf6_34_the_saved_verdict_records_the_files_digest_not_its_name(tmp_path: Path) -> None:
    store = _store(tmp_path)
    text = f"case,outcome\n{UNSCORED},fail\n"
    one, two = write(tmp_path / "one.csv", text), write(tmp_path / "two.csv", text)
    run_ok(_fix(store, "--verdicts", str(one), "--save"))
    run_ok(_fix(store, "--verdicts", str(two), "--save"))
    found = artifacts(store, "fix-check")
    assert len(found) == 1
    desc = descriptor(found[0])
    assert desc["settings"]["verdicts"] == _sha(one)
    assert str(tmp_path) not in json.dumps(desc) and "one.csv" not in json.dumps(desc["settings"])
    run_ok(_fix(store, "--save"))
    assert len(artifacts(store, "fix-check")) == 2


def test_tf6_34_a_verdicts_failure_kind_reaches_the_counts(tmp_path: Path) -> None:
    store = _store(tmp_path)
    v = write(tmp_path / "v.jsonl", json.dumps({"case": UNSCORED, "outcome": "fail", "failure_kind": "tool_error",
                                                 "scores": {"reviewer": 0.0}, "feedback": {"thumb": "down"}}) + "\n")
    run_ok(_fix(store, "--save"))
    plain = {d["failure_kind"]: d for d in result_of(artifacts(store, "fix-check")[0])["failure_taxonomy_diff"]["kinds"]}
    run_ok(_fix(store, "--verdicts", str(v), "--save"))
    folder = next(f for f in artifacts(store, "fix-check") if descriptor(f)["settings"]["verdicts"] is not None)
    joined = {d["failure_kind"]: d for d in result_of(folder)["failure_taxonomy_diff"]["kinds"]}
    was = plain.get("tool_error", {"old": 0, "new": 0})
    assert (joined["tool_error"]["old"], joined["tool_error"]["new"]) == (was["old"] + 1, was["new"] + 1)
    # the scores and the feedback are the join's, never the artifact's
    blob = "".join(p.read_text(encoding="utf-8", errors="replace") for p in folder.rglob("*") if p.suffix in (".json", ".md"))
    assert "reviewer" not in blob and "thumb" not in blob


def test_tf6_34_nothing_is_written_without_save(tmp_path: Path) -> None:
    store = _store(tmp_path)
    v = write(tmp_path / "v.csv", f"case,outcome\n{UNSCORED},fail\n")
    before = tree(tmp_path)
    run_ok(_fix(store, "--verdicts", str(v)))
    run_ok(_changes(store, "--verdicts", str(v), "--json"))
    assert tree(tmp_path) == before


# ---------- TF6-35 ----------


def test_tf6_35_where_does_not_take_verdicts(tmp_path: Path) -> None:
    store = store012(tmp_path)
    v = write(tmp_path / "v.csv", "case,outcome\nx,fail\n")
    ran = trace(argv012("where", store, "--verdicts", str(v)))
    assert ran.code == 2, ran.text
