"""TF6-4 to TF6-15: ``--save`` writes the verdict as one artifact of the suite's format (spec
section 17.3 items 1 to 4, the Artifact Format sections 2, 3 and 5; invariants 1, 4 and 5).

- TF6-4: without ``--save`` (or ``--out``) nothing is written, on any verb (AD8).
- TF6-5: with it, one artifact of the verb's kind; the plain output gains one last detail line,
  ``  saved  <kind> <first 12 hex>``, and ``--json`` gains ``saved`` before ``next``; nothing
  else printed moves.
- TF6-6: ``artifact.json``: Prove's keys in Prove's order; every file listed with its role, media
  type, schema and digest, and nothing unlisted.
- TF6-7: the id is the format's formula over the result-changing settings; those settings, per
  verb, by name (SV5); where each came from and the stores' config names kept beside them, out of
  the id; one result saved twice is one artifact, written once.
- TF6-8: the inputs name the runs by id alone, so a run's name does not move the id.
- TF6-9: saved in the store the runs were read from; the store descriptor written or its
  ``writers`` appended once, every other key kept; nothing else in the store changes.
- TF6-10: a store that cannot be written: one ``note:`` line, and the command goes on.
- TF6-11: a save that fails part way leaves no artifact and no temporary folder.
- TF6-12: ``report.md`` is the plain report; an absolute store path is written as its last folder's
  name, here and everywhere in the artifact (SV7).
- TF6-13: ``result.json`` is the printed ``--json`` with section 11.3's keys and TF6's (SV3, SV4).
- TF6-14: a saved verdict reads back the same, and equal inputs give equal bytes.
- TF6-15: ``table.parquet``: the shared columns, Trace's two, and the metrics each verb writes
  (section 17.3 item 1: "TF6's Session A freezes the names").
"""

from __future__ import annotations

import atexit
import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest
from tf0_support import TAU2_A, TAU2_B, chdir, trace
from tf1_support import tau2_copy
from tf6_support import (
    AFTER_ID, ARMS, BEFORE_ID, DESCRIPTOR_KEYS, EVENTS_012, HEX16, SCHEMAS, TABLE_COLUMNS,
    TWO_RUNS, UTC, VERBS, argv012, artifacts, descriptor, expected_id, files_in, junit_store,
    outside_dot_poisson, prove_version, read_table, result_of, run_ok, saved_line, sha256_file,
    store012, table_schema, the_artifact, trace_version, tree, without_detail, write,
)

INPUTS = {"where": [AFTER_ID], "compare": [BEFORE_ID, AFTER_ID], "fix-check": [BEFORE_ID, AFTER_ID],
          "changes": [BEFORE_ID, AFTER_ID]}
SETTINGS = {
    "where": ["events", "by", "at", "boot", "seed", "from", "stores"],
    "compare": ["events", "by", "at", "max_mde_hr", "alpha", "verdicts", "from", "stores"],
    "fix-check": ["events", "inputs", "failing_from", "min_failures", "max_mde", "alpha", "seed",
                  "max_change", "verdicts", "from", "stores"],
    "changes": ["events", "alpha", "verdicts", "from", "stores"],
}
FILES = {
    "result.json": {"role": "result", "media_type": "application/json"},
    "report.md": {"role": "report", "media_type": "text/markdown"},
    "table.parquet": {"role": "table", "media_type": "application/vnd.apache.parquet", "schema": "poisson.table/1"},
    "charts/curve.svg": {"role": "chart", "media_type": "image/svg+xml", "data": "charts/curve.json"},
    "charts/curve.json": {"role": "table", "media_type": "application/json", "schema": "poisson-trace.chart/1"},
    # SV15: compare's two curves and its hazard ratio, charted with the pages (TF18)
    "charts/curves.svg": {"role": "chart", "media_type": "image/svg+xml", "data": "charts/curves.json"},
    "charts/curves.json": {"role": "table", "media_type": "application/json", "schema": "poisson-trace.chart/1"},
    "charts/hazard-ratio.svg": {"role": "chart", "media_type": "image/svg+xml", "data": "charts/hazard-ratio.json"},
    "charts/hazard-ratio.json": {"role": "table", "media_type": "application/json", "schema": "poisson-trace.chart/1"},
}
CHARTS = {
    "where": ["charts/curve.svg", "charts/curve.json"],
    "compare": ["charts/curves.svg", "charts/curves.json", "charts/hazard-ratio.svg", "charts/hazard-ratio.json"],
}
ADDED = ["summary", "before_you_act", "note", "versions"]
ADDED_TWO = ["failure_taxonomy_diff", "continuous_measures"]


def _saved(tmp_path: Path, verb: str, *extra: str) -> tuple[Path, Path]:
    store = store012(tmp_path)
    run_ok(argv012(verb, store, "--save", *extra))
    return store, the_artifact(store, verb)


_KEPT: dict[tuple[str, ...], Path] = {}


def _kept(verb: str, *extra: str) -> Path:
    """The verb's saved artifact for the tests that only read it: saved once in each process, in
    a store no test is given. A test that writes, or compares trees, saves its own (``_saved``)."""
    key = (verb, *extra)
    if key not in _KEPT:
        root = Path(tempfile.mkdtemp(prefix="tf6-saved-"))
        atexit.register(shutil.rmtree, root, ignore_errors=True)
        _KEPT[key] = _saved(root, verb, *extra)[1]
    return _KEPT[key]


# ---------- TF6-4 ----------


@pytest.mark.parametrize("verb", VERBS)
def test_tf6_4_without_save_nothing_is_written(tmp_path: Path, verb: str) -> None:
    store = store012(tmp_path)
    before = tree(tmp_path)
    run_ok(argv012(verb, store))
    run_ok(argv012(verb, store, "--json"))
    assert tree(tmp_path) == before


# ---------- TF6-5 ----------


@pytest.mark.parametrize("verb", VERBS)
def test_tf6_5_save_adds_one_line_and_one_key(tmp_path: Path, verb: str) -> None:
    store = store012(tmp_path)
    plain = run_ok(argv012(verb, store))
    as_json = run_ok(argv012(verb, store, "--json"))
    saved = run_ok(argv012(verb, store, "--save"))
    folder = the_artifact(store, verb)
    identity = folder.name
    lines = saved.out.splitlines()
    # the last detail line: right after the verdict line (and any wrote line), before the blank line
    blank = lines.index("")
    assert lines[blank - 1] == saved_line(verb, identity), lines[:blank + 1]
    assert without_detail(saved.out, "saved") == plain.out
    again = run_ok(argv012(verb, store, "--save", "--json"))
    doc, before = again.json(), as_json.json()
    assert list(doc)[-2:] == ["saved", "next"], list(doc)
    assert doc["saved"] == f".poisson/artifacts/{verb}/{identity}"
    assert {k: v for k, v in doc.items() if k != "saved"} == before
    assert list(k for k in doc if k != "saved") == list(before)
    # one result saved twice is one artifact
    assert artifacts(store) == [folder]


# ---------- TF6-6 ----------


@pytest.mark.parametrize("verb", VERBS)
def test_tf6_6_the_descriptor_is_the_formats(verb: str) -> None:
    folder = _kept(verb)
    desc = descriptor(folder)
    assert list(desc) == DESCRIPTOR_KEYS
    assert desc["format"] == "poisson.artifact/1" and desc["kind"] == verb
    assert HEX16.match(desc["id"]) and desc["id"] == folder.name
    assert desc["tool"] == "poisson-trace" and desc["tool_version"] == trace_version()
    assert UTC.match(desc["created_at"]), desc["created_at"]
    assert desc["inputs"] == {"runs": INPUTS[verb]}
    result = result_of(folder)
    assert desc["summary"]["verdict"] == result["verdict"]
    assert desc["summary"]["sentence"] == result["sentence"]
    assert all(isinstance(d, list) and len(d) == 2 and all(isinstance(x, str) for x in d)
               for d in desc["summary"]["detail"]), desc["summary"]
    listed = [f["path"] for f in desc["files"]]
    want = ["result.json", "report.md", "table.parquet"] + CHARTS.get(verb, [])
    assert listed == want
    # nothing in the folder is unlisted, and the descriptor does not list itself
    assert files_in(folder) == sorted(["artifact.json", *want])
    for entry in desc["files"]:
        expected = dict(FILES[entry["path"]])
        if entry["path"] == "result.json":
            expected["schema"] = SCHEMAS[verb]
        assert {k: v for k, v in entry.items() if k != "sha256"} == {"path": entry["path"], **expected}, entry
        assert entry["sha256"] == sha256_file(folder / entry["path"])


def test_tf6_6_where_charts_its_curve_as_svg_writes_it(tmp_path: Path) -> None:
    store, folder = _saved(tmp_path, "where")
    svg = tmp_path / "curve.svg"
    run_ok(argv012("where", store, "--svg", str(svg)))
    assert (folder / "charts" / "curve.svg").read_bytes() == svg.read_bytes()
    data = json.loads((folder / "charts" / "curve.json").read_text(encoding="utf-8"))
    assert data["schema"] == "poisson-trace.chart/1"
    assert data["curve"] == result_of(folder)["curve"]


# ---------- TF6-7 ----------


@pytest.mark.parametrize("verb", VERBS)
def test_tf6_7_the_id_is_the_formats_formula(verb: str) -> None:
    folder = _kept(verb)
    desc = descriptor(folder)
    assert desc["id"] == expected_id(desc)
    assert list(desc["settings"]) == SETTINGS[verb]
    settings = desc["settings"]
    assert settings["events"] == ["timeout", "violated"]
    assert set(settings["from"]) <= set(SETTINGS[verb]) - {"from", "stores"}
    assert set(settings["from"].values()) <= {"flag", "trace.toml", "default"}
    assert settings["from"]["events"] == "flag" and settings["stores"] == []


def test_tf6_7_the_settings_hold_what_was_asked(tmp_path: Path) -> None:
    _, folder = _saved(tmp_path, "fix-check", "--alpha", "0.1", "--seed", "3")
    s = descriptor(folder)["settings"]
    assert (s["inputs"], s["failing_from"], s["min_failures"], s["max_mde"], s["alpha"], s["seed"]) == (
        "all", None, None, 0.2, 0.1, 3)
    assert (s["max_change"], s["verdicts"]) == ({}, None)
    _, folder = _saved(tmp_path / "w", "where", "--by", "step", "--boot", "50", "--seed", "7")
    s = descriptor(folder)["settings"]
    assert (s["by"], s["at"], s["boot"], s["seed"]) == ("step", [3], 50, 7)


# each verb's result-changing settings, each changed once from argv012's
CHANGED = [
    ("where", ["--by", "step"]), ("where", ["--boot", "50"]), ("where", ["--seed", "1"]),
    ("where", ["--at", "4"]), ("where", ["--event", "violated"]),
    ("compare", ["--max-mde-hr", "2"]), ("compare", ["--alpha", "0.1"]), ("compare", ["--at", "2"]),
    ("compare", ["--by", "step"]),
    ("fix-check", ["--max-mde", "0.3"]), ("fix-check", ["--alpha", "0.1"]), ("fix-check", ["--seed", "2"]),
    ("fix-check", ["--max-change", "wall_time_s=10%"]),
    ("changes", ["--alpha", "0.1"]),
]


def _replace(argv: list[str], extra: list[str]) -> list[str]:
    """argv with an option given again: a repeatable one (``--at``, ``--event``) replaced whole."""
    flag = extra[0]
    out, i = [], 0
    while i < len(argv):
        if argv[i] == flag:
            i += 2
            continue
        out.append(argv[i])
        i += 1
    return out + extra


@pytest.mark.parametrize("verb,extra", CHANGED)
def test_tf6_7_a_result_changing_setting_moves_the_id(tmp_path: Path, verb: str, extra: list[str]) -> None:
    store = store012(tmp_path)
    run_ok(argv012(verb, store, "--save"))
    run_ok([*_replace(argv012(verb, store), extra), "--save"])
    assert len(artifacts(store, verb)) == 2


@pytest.mark.parametrize("verb", VERBS)
def test_tf6_7_presentation_does_not_move_the_id(tmp_path: Path, verb: str) -> None:
    store = store012(tmp_path)
    run_ok(argv012(verb, store, "--save"))
    run_ok(argv012(verb, store, "--save", "--json"))
    if verb in ("fix-check", "changes"):
        run_ok(argv012(verb, store, "--save", "--top", "1"))
    if verb == "fix-check":
        run_ok(argv012(verb, store, "--save", "--measures"))
    assert len(artifacts(store, verb)) == 1


def test_tf6_7_a_setting_from_the_config_is_the_same_artifact(tmp_path: Path) -> None:
    store = store012(tmp_path)
    run_ok(argv012("fix-check", store, "--save"))
    folder = the_artifact(store, "fix-check")
    before = tree(folder)
    config = write(tmp_path / "trace.toml", "version = 1\n\n[check]\nmax_mde = 0.2\n")
    argv = [a for a in argv012("fix-check", store) if a not in ("--max-mde", "0.2")]
    ran = run_ok([*argv, "--config", str(config), "--save"])
    assert artifacts(store, "fix-check") == [folder]
    assert saved_line("fix-check", folder.name) in ran.out.splitlines()
    # the artifact that was there is that artifact: nothing in it rewritten
    assert tree(folder) == before


def test_tf6_7_where_a_setting_came_from_is_kept_out_of_the_id(tmp_path: Path) -> None:
    store = store012(tmp_path / "x")
    config = write(tmp_path / "trace.toml", f'version = 1\n\n[store]\npath = "{store}"\n\n[events]\nfailed = ["timeout", "violated"]\n\n[check]\nmax_mde = 0.2\n')
    run_ok(["fix-check", "agent before", "agent after", "--config", str(config), "--inputs", "all", "--save"])
    s = descriptor(the_artifact(store, "fix-check"))["settings"]
    assert s["from"]["max_mde"] == "trace.toml" and s["from"]["events"] == "trace.toml"
    assert s["from"]["alpha"] == "default" and s["stores"] == []


# ---------- TF6-8 ----------


def test_tf6_8_a_runs_name_does_not_move_the_id(tmp_path: Path) -> None:
    store = store012(tmp_path)
    run_ok(argv012("changes", store, "--save"))
    run_ok(["name", "agent before", "the old agent", "--store", str(store)])
    run_ok(["changes", "the old agent", "agent after", "--store", str(store), *EVENTS_012, "--save"])
    assert len(artifacts(store, "changes")) == 1


# ---------- TF6-9 ----------


def test_tf6_9_the_store_descriptor_gains_trace_as_a_writer_once(tmp_path: Path) -> None:
    store = store012(tmp_path)
    before = json.loads((store / ".poisson" / "store.json").read_text(encoding="utf-8"))
    run_ok(argv012("fix-check", store, "--save"))
    after = json.loads((store / ".poisson" / "store.json").read_text(encoding="utf-8"))
    assert {k: v for k, v in after.items() if k != "writers"} == {k: v for k, v in before.items() if k != "writers"}
    assert after["writers"][:-1] == before["writers"]
    added = after["writers"][-1]
    assert list(added) == ["tool", "version", "first_write"]
    assert (added["tool"], added["version"]) == ("poisson-trace", trace_version()) and UTC.match(added["first_write"])
    stamp = (store / ".poisson" / "store.json").stat().st_mtime_ns
    run_ok(argv012("changes", store, "--save"))
    assert (store / ".poisson" / "store.json").stat().st_mtime_ns == stamp


def test_tf6_9_a_store_with_no_descriptor_gets_one(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    assert not (store / ".poisson").exists()
    run_ok(["changes", TAU2_A, TAU2_B, "--store", str(store), "--event", "unsolved", "--save"])
    doc = json.loads((store / ".poisson" / "store.json").read_text(encoding="utf-8"))
    assert list(doc) == ["format", "created_by", "created_at", "writers"]
    assert doc["format"] == "poisson.store/1"
    assert doc["created_by"] == {"tool": "poisson-trace", "version": trace_version()}
    assert UTC.match(doc["created_at"])
    assert doc["writers"] == [{"tool": "poisson-trace", "version": trace_version(), "first_write": doc["created_at"]}]


@pytest.mark.parametrize("verb", VERBS)
def test_tf6_9_nothing_else_in_the_store_changes(tmp_path: Path, verb: str) -> None:
    store = store012(tmp_path)
    before = tree(store)
    run_ok(argv012(verb, store, "--save"))
    after = tree(store)
    assert outside_dot_poisson(after) == outside_dot_poisson(before)
    # Prove's own saved comparison is untouched
    prove_own = {k: v for k, v in before.items() if k.startswith(".poisson/artifacts/comparison/")}
    assert prove_own and all(after[k] == v for k, v in prove_own.items())
    new = sorted(set(after) - set(before))
    # A7: a save also builds Trace's pages, under .poisson/ui/trace/ (TF18)
    assert all(k.startswith((f".poisson/artifacts/{verb}/", ".poisson/ui/trace/")) for k in new), new
    assert all(k in new or after[k] == before[k] for k in after if k != ".poisson/store.json")


# ---------- TF6-10 ----------


@pytest.mark.skipif(os.geteuid() == 0, reason="a folder is never read-only to root")
def test_tf6_10_a_store_that_cannot_be_written_says_so_and_goes_on(tmp_path: Path) -> None:
    store = store012(tmp_path)
    plain = run_ok(argv012("fix-check", store))
    as_json = run_ok(argv012("fix-check", store, "--json"))
    before = tree(store)
    folders = [p for p in [store, *store.rglob("*")] if p.is_dir()]
    for p in folders:
        p.chmod(0o555)
    try:
        ran = trace(argv012("fix-check", store, "--save"))
        ran_json = trace(argv012("fix-check", store, "--save", "--json"))
    finally:
        for p in folders:
            p.chmod(0o755)
    assert ran.code == 0 and ran_json.code == 0, ran.text
    assert ran.out == plain.out and ran_json.out == as_json.out
    notes = [line for line in ran.err.splitlines() if line.strip()]
    assert len(notes) == 1 and notes[0].startswith("note: the verdict was not saved: "), ran.err
    assert tree(store) == before


# ---------- TF6-11 ----------


def test_tf6_11_a_save_that_fails_part_way_leaves_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = store012(tmp_path)
    plain = run_ok(argv012("changes", store))

    def refused(*args: Any, **kwargs: Any) -> None:
        raise OSError(28, "No space left on device")

    for name in ("replace", "rename"):
        monkeypatch.setattr(os, name, refused)
    monkeypatch.setattr(Path, "rename", lambda self, target: refused())
    monkeypatch.setattr(Path, "replace", lambda self, target: refused())
    ran = trace(argv012("changes", store, "--save"))
    monkeypatch.undo()
    assert ran.code == 0 and ran.out == plain.out, ran.text
    assert "note: the verdict was not saved: " in ran.err and "No space left on device" in ran.err
    kind = store / ".poisson" / "artifacts" / "changes"
    assert not kind.exists() or list(kind.iterdir()) == []


# ---------- TF6-12 ----------


@pytest.mark.parametrize("verb", VERBS)
def test_tf6_12_report_md_is_the_plain_report(tmp_path: Path, verb: str) -> None:
    store012(tmp_path)
    with chdir(tmp_path):
        plain = run_ok(argv012(verb, Path("store")))
        run_ok(argv012(verb, Path("store"), "--save"))
    folder = the_artifact(tmp_path / "store", verb)
    report = (folder / "report.md").read_text(encoding="utf-8")
    assert report == plain.out
    result = result_of(folder)
    assert report.splitlines()[0] == f"{result['verdict']}  {result['sentence']}"


@pytest.mark.parametrize("verb", VERBS)
def test_tf6_12_an_absolute_store_path_is_never_written(tmp_path: Path, verb: str) -> None:
    store = store012(tmp_path)
    plain = run_ok(argv012(verb, store))
    run_ok(argv012(verb, store, "--save"))
    folder = the_artifact(store, verb)
    for name in files_in(folder):
        data = (folder / name).read_bytes()
        assert str(tmp_path).encode() not in data, name
    report = (folder / "report.md").read_text(encoding="utf-8")
    assert report == plain.out.replace(str(store), store.name)
    result = result_of(folder)
    assert result["prove"]["store"] == store.name


def test_tf6_12_a_relative_store_path_is_written_as_given(tmp_path: Path) -> None:
    (tmp_path / "work").mkdir()
    store012(tmp_path / "work", "runs")
    with chdir(tmp_path / "work"):
        run_ok(argv012("changes", Path("runs"), "--save"))
    assert result_of(the_artifact(tmp_path / "work" / "runs", "changes"))["prove"]["store"] == "runs"


# ---------- TF6-13 ----------


@pytest.mark.parametrize("verb", VERBS)
def test_tf6_13_result_json_is_the_printed_json_with_the_promised_keys(tmp_path: Path, verb: str) -> None:
    store012(tmp_path)
    with chdir(tmp_path):
        printed = run_ok(argv012(verb, Path("store"), "--save", "--json")).json()
    folder = the_artifact(tmp_path / "store", verb)
    result = result_of(folder)
    added = ADDED + (ADDED_TWO if verb in TWO_RUNS else [])
    body = [k for k in printed if k not in ("saved", "next")]
    assert list(result) == [*body, *[k for k in added if k not in body], "saved", "next"], list(result)
    for key in printed:
        if key == "note":
            continue
        assert result[key] == printed[key], key
    assert result["versions"] == {"trace": trace_version(), "prove": prove_version()}
    assert isinstance(result["note"], list) and all(isinstance(n, str) for n in result["note"])
    report = (folder / "report.md").read_text(encoding="utf-8").splitlines()
    # the summary's labelled lines as [label, text] pairs, and the caveats, as the report prints them
    assert result["summary"] and all(isinstance(p, list) and len(p) == 2 for p in result["summary"])
    assert all(f"- {label}: {text}" in report for label, text in result["summary"])
    assert [label for label, _ in result["summary"]] == ["Read" if verb == "where" else "Compared", "Question", "Answer", "Next"]
    assert isinstance(result["before_you_act"], list)
    assert all(isinstance(c, str) and f"- {c}" in report for c in result["before_you_act"])
    assert descriptor(folder)["summary"]["detail"] == result["summary"]
    assert list(result)[:3] == ["schema", "verdict", "sentence"] and result["schema"] == SCHEMAS[verb]


def test_tf6_13_a_note_is_a_list_holding_what_the_json_said(tmp_path: Path) -> None:
    store = junit_store(tmp_path)
    printed = run_ok(["where", "ja", "--store", str(store), "--event", "missed", "--save", "--json"]).json()
    assert isinstance(printed["note"], str)
    result = result_of(the_artifact(store, "where"))
    assert result["note"] == [printed["note"]]
    assert list(result).index("note") == list(printed).index("note")


@pytest.mark.parametrize("verb", VERBS)
def test_tf6_13_runs_carry_their_names_and_numbers_are_numbers(verb: str) -> None:
    folder = _kept(verb)
    result = result_of(folder)
    heads = [result["run"]] if verb == "where" else [result["runs"][arm] for arm in ARMS[verb]]
    assert all(h["run_id"] in (BEFORE_ID, AFTER_ID) and isinstance(h["run_name"], str) for h in heads)
    text = (folder / "result.json").read_text(encoding="utf-8")
    assert "NaN" not in text and "Infinity" not in text
    json.loads(text, parse_constant=lambda name: (_ for _ in ()).throw(ValueError(name)))


# ---------- TF6-14 ----------


@pytest.mark.parametrize("verb", VERBS)
def test_tf6_14_a_saved_verdict_reads_back_the_same(tmp_path: Path, verb: str) -> None:
    store012(tmp_path / "one")
    store012(tmp_path / "two")
    with chdir(tmp_path / "one"):
        run_ok(argv012(verb, Path("store"), "--save"))
    with chdir(tmp_path / "two"):
        run_ok(argv012(verb, Path("store"), "--save"))
    one, two = the_artifact(tmp_path / "one" / "store", verb), the_artifact(tmp_path / "two" / "store", verb)
    assert one.name == two.name
    # equal inputs, equal bytes, but for the descriptor's time of writing
    for name in files_in(one):
        if name != "artifact.json":
            assert (one / name).read_bytes() == (two / name).read_bytes(), name
    d1, d2 = descriptor(one), descriptor(two)
    assert {k: v for k, v in d1.items() if k != "created_at"} == {k: v for k, v in d2.items() if k != "created_at"}
    # each JSON file is the format's way of writing it: indented two spaces, UTF-8, one newline at the end
    for name in [n for n in files_in(one) if n.endswith(".json")]:
        text = (one / name).read_text(encoding="utf-8")
        assert text == json.dumps(json.loads(text), indent=2, ensure_ascii=False) + "\n", name
    # saving again changes nothing and says the same
    before = tree(one)
    with chdir(tmp_path / "one"):
        again = run_ok(argv012(verb, Path("store"), "--save"))
    assert tree(one) == before and saved_line(verb, one.name) in again.out.splitlines()


# ---------- TF6-15 ----------


METRICS = {
    "where": {"tries", "failed", "survival", "survival_lo", "survival_hi", "median_step", "share", "share_lo", "share_hi"},
    "compare": {"tries", "failed", "p", "hr", "hr_lo", "hr_hi", "mde_hr", "max_mde_hr", "q", "survival", "diff", "diff_lo", "diff_hi"},
    "fix-check": {"tries", "failed", "share", "difference", "range_lo", "range_hi", "p", "q", "drop_limit", "rise_limit", "max_mde"},
    "changes": {"tries", "failed", "share", "p", "q"},
}
NOT_BOUNDS = {"tries", "failed", "share", "survival", "median_step", "p", "q", "hr", "difference", "diff", "max_mde", "max_mde_hr"}


def _rows(folder: Path) -> list[dict[str, Any]]:
    return read_table(folder / "table.parquet")


def _one(rows: list[dict[str, Any]], **where: Any) -> dict[str, Any]:
    found = [r for r in rows if all(r[k] == v for k, v in where.items())]
    assert len(found) == 1, (where, found)
    return found[0]


@pytest.mark.parametrize("verb", VERBS)
def test_tf6_15_the_table_has_the_formats_columns_and_the_frozen_metrics(verb: str) -> None:
    folder = _kept(verb, "--at", "2") if verb == "compare" else _kept(verb)
    assert table_schema(folder / "table.parquet") == [
        ("artifact_id", "string"), ("event", "string"), ("condition", "string"), ("condition_hash", "string"),
        ("arm", "string"), ("metric", "string"), ("value", "double"), ("note", "string"), ("level", "double"),
        ("step", "int64"), ("cause", "string"),
    ]
    assert [c for c, _ in table_schema(folder / "table.parquet")] == TABLE_COLUMNS
    rows = _rows(folder)
    assert rows
    assert {r["metric"] for r in rows} == METRICS[verb]
    for r in rows:
        assert r["artifact_id"] == folder.name and r["event"] == "timeout,violated"
        assert r["arm"] in ("a", "b", "both")
        assert HEX16.match(r["condition_hash"]), r
        assert (r["value"] is None) == (r["note"] is not None), r
        if r["value"] is not None:
            assert math.isfinite(r["value"]), r
        if r["metric"].endswith(("_lo", "_hi")):
            assert r["level"] is not None and 0 < r["level"] < 1, r
        if r["metric"] in NOT_BOUNDS:
            assert r["level"] is None, r


def test_tf6_15_fix_checks_rows_are_its_json() -> None:
    folder = _kept("fix-check")
    rows, result = _rows(folder), result_of(folder)
    whole = [r for r in rows if r["condition"] == "{}"]
    assert _one(whole, metric="p", arm="both")["value"] == result["test"]["p"]
    assert _one(whole, metric="difference", arm="both")["value"] == result["difference"]["points"]
    assert _one(whole, metric="range_lo", arm="both")["value"] == result["difference"]["lo"]
    assert _one(whole, metric="range_hi", arm="both")["value"] == result["difference"]["hi"]
    assert _one(whole, metric="drop_limit", arm="both")["value"] == result["limits"]["drop"]
    assert _one(whole, metric="rise_limit", arm="both")["value"] == result["limits"]["rise"]
    assert _one(whole, metric="max_mde", arm="both")["value"] == 0.2
    assert _one(whole, metric="tries", arm="a")["value"] == result["rows"]["old"]["runs"]
    assert _one(whole, metric="failed", arm="b")["value"] == result["rows"]["new"]["failed"]
    per = result["changes"]["rows"]
    assert len({r["condition_hash"] for r in rows if r["condition"] != "{}"}) == len(per)
    for input_ in per:
        mine = [r for r in rows if r["condition_hash"] == input_["config_hash"]]
        assert json.loads(mine[0]["condition"]) == input_["config"]
        assert _one(mine, metric="p", arm="both")["value"] == input_["p"]


def test_tf6_15_compares_rows_are_its_json() -> None:
    folder = _kept("compare", "--at", "2")
    rows, result = _rows(folder), result_of(folder)
    c = result["comparison"]
    whole = [r for r in rows if r["cause"] is None and r["step"] is None]
    assert _one(whole, metric="p", arm="both")["value"] == c["p"]
    assert _one(whole, metric="hr", arm="both")["value"] == c["hazard_ratio"]
    assert _one(whole, metric="mde_hr", arm="both")["value"] == c["mde_hazard_ratio"]
    for cause in result["per_cause"]:
        mine = [r for r in rows if r["cause"] == cause["cause"]]
        assert _one(mine, metric="p")["value"] == cause["p"]
    at = result["at"][0]
    assert _one(rows, metric="diff", step=2)["value"] == at["diff"]
    assert _one(rows, metric="survival", step=2, arm="b")["value"] == at["survival_b"]


def test_tf6_15_wheres_rows_are_its_json() -> None:
    folder = _kept("where")
    rows, result = _rows(folder), result_of(folder)
    assert {r["arm"] for r in rows} == {"a"}
    curve = [r for r in rows if r["metric"] == "survival"]
    assert [(r["step"], r["value"]) for r in curve] == [(p["step"], p["survival"]) for p in result["curve"]]
    assert _one(rows, metric="median_step")["value"] == result["median_step"]
    for cause in result["causes"]:
        assert _one(rows, metric="share", cause=cause["cause"])["value"] == cause["f"]


def test_tf6_15_changes_rows_are_its_json() -> None:
    folder = _kept("changes")
    rows, result = _rows(folder), result_of(folder)
    for input_ in result["rows"]:
        mine = [r for r in rows if r["condition_hash"] == input_["config_hash"]]
        assert _one(mine, metric="q", arm="both")["value"] == input_["q"]
        assert _one(mine, metric="failed", arm="a")["value"] == input_["failed_a"]
        assert _one(mine, metric="tries", arm="b")["value"] == input_["runs_b"]
