"""IC6 to IC14 through the command: the Prove check, refusals, readers found by presence, the
start time's source, the summary, and Trace reading what was written."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tomllib
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from poisson_prove.store import Store
from support import (
    BANNED, IMPORT_MAIN, IMPORT_SCHEMA, INGEST, PACKAGE, REPO, case, conversation,
    deepeval_argv, holds, in_order, metric, read_rows, refused, run_doc, run_import, run_python,
    run_trace, save, scalars, scored, tree, words,
)

from poisson_trace.ingest.cli import READERS
from poisson_trace.ingest.rows import STARTED_FROM

from pin_support import RECORDED, REQUIREMENT

# ---------- a small DeepEval file: four cases, 17 rows, 2 without a score ----------

MET_N, MISSED_N, NO_SCORE_N, ROWS_N, CASES_N, REPEATS = 8, 7, 2, 17, 4, (3, 6)


def small_doc() -> dict[str, Any]:
    cases = [
        *scored("alpha", [0.9, 0.1, 0.8]),
        *scored("beta", [0.2, 0.7, None, 0.95], start=3),
        *scored("gamma", [0.3, 0.6, 0.4, 0.75], start=7),
        *scored("delta", [0.05, None, 0.99, 0.15, 0.85, 0.35], start=11),
        case("epsilon", [metric("Other", 0.9)], order=17),
    ]
    return run_doc(cases)


# ---------- the script entry ----------


def test_the_script_entry_is_declared_and_no_dependency_is_added() -> None:
    project = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]
    assert project["scripts"]["poisson-trace-import"] == "poisson_trace.ingest.cli:main"
    # the import adds none; the others are the Prove Trace pins,
    # Rich, which the clean look renders through (TF9-5a), and Textual,
    # which the terminal app is built with at the floor Prove declares (TF19)
    # and pyarrow, which Trace imports itself to write a saved verdict's table, declared at the
    # floor Prove declares (TF5-96)
    assert sorted(project["dependencies"]) == sorted(["numpy", "scipy", "pandas>=2", "pyarrow>=17.0.0", REQUIREMENT, "rich>=14.2.0",
                                                      "textual>=6.4.0"])


# ---------- IC6, the second half ----------


def test_ic6_two_imports_of_the_same_file_give_equal_frames(tmp_path: Path) -> None:
    f = save(tmp_path / "results.json", small_doc())
    frames = []
    for i in range(2):
        root = tmp_path / f"store{i}"
        r = run_import(deepeval_argv(f, root, "v1", extra=["--started", "2026-09-05T18:54:07Z"]))
        assert r.code == 0, r.text
        frames.append(Store(root).read("v1", meta=True, trace="none"))
    pd.testing.assert_frame_equal(frames[0], frames[1], check_exact=True)


# ---------- IC7 through the reader ----------

SENTINEL = "Z8c41e97b2d6f03a5QN"


def _content_doc() -> dict[str, Any]:
    """Every text field of a DeepEval file holds the sentinel, the case names included."""
    def texts(i: int) -> dict[str, Any]:
        s = f"{SENTINEL}-{i}"
        return {
            "input": f"{s} input", "actualOutput": f"{s} output", "expectedOutput": f"{s} expected",
            "context": [f"{s} context"], "retrievalContext": [f"{s} retrieved"],
            "toolsCalled": [{"name": f"{s} tool", "inputParameters": {"q": f"{s} args"}, "output": f"{s} result"}],
            "expectedTools": [{"name": f"{s} expected tool"}],
            "comments": f"{s} comment", "additionalMetadata": {"note": f"{s} note"},
            "metadata": {"note": f"{s} meta"}, "tags": [f"{s} tag"],
        }
    cases = [
        case(f"{SENTINEL} name {i}", [metric("Score", s, reason=f"{SENTINEL} reason {i}")], order=i,
             **{k: v for k, v in texts(i).items() if k != "input"}, input=texts(i)["input"])
        for i, s in enumerate([0.9, 0.2, 0.6, 0.4])
    ]
    cases.append(case(f"{SENTINEL} name 9", [metric("Score", None, error=f"{SENTINEL} error text")], order=9,
                      input=f"{SENTINEL} input 9"))
    convs = [conversation(f"{SENTINEL} conversation", [metric("Score", 0.8, reason=f"{SENTINEL} conv reason")],
                          order=10, scenario=f"{SENTINEL} scenario", expectedOutcome=f"{SENTINEL} outcome",
                          userDescription=f"{SENTINEL} user",
                          turns=[{"role": "user", "content": f"{SENTINEL} turn", "order": 0}])]
    return run_doc(cases, convs, identifier=f"{SENTINEL} identifier")


def test_ic7_no_text_of_the_file_reaches_any_file_under_the_store(tmp_path: Path) -> None:
    """Sole catch for a reader that stores a prompt."""
    f = save(tmp_path / "results.json", _content_doc())
    root = tmp_path / "store"
    r = run_import(deepeval_argv(f, root, "v1", case="position"))
    assert r.code == 0, r.text
    assert len(read_rows(root, "v1")) == 6
    assert holds(root, SENTINEL) == []


# ---------- IC9 ----------

PROBE = """
import sys
opened = []
def hook(event, args):
    if event == "open" and args and isinstance(args[0], (str, bytes)):
        opened.append(args[0] if isinstance(args[0], str) else args[0].decode())
sys.addaudithook(hook)
{prelude}
from poisson_trace.ingest.cli import main
try:
    code = main(sys.argv[1:])
finally:
    with open({log!r}, "w") as handle:
        handle.write("\\n".join(opened))
sys.exit(code)
"""


def _probe(tmp_path: Path, prelude: str, env: dict[str, str]) -> tuple[Any, list[str], Path, Path]:
    f = save(tmp_path / "results.json", small_doc())
    root = tmp_path / "store"
    log = tmp_path / "opened.txt"
    r = run_python(PROBE.format(prelude=prelude, log=str(log)), deepeval_argv(f, root, "v1"), env=env, cwd=tmp_path)
    opened = log.read_text().splitlines() if log.exists() else []
    return r, opened, f, root


def _no_open_of(opened: list[str], f: Path) -> None:
    hits = [p for p in opened if os.path.basename(p) == f.name]
    assert hits == [], hits


def test_ic9_without_poisson_prove_the_command_refuses_before_it_opens_a_file(tmp_path: Path) -> None:
    r, opened, f, root = _probe(tmp_path, "sys.modules['poisson_prove'] = None", dict(os.environ))
    refused(r)
    assert "poisson-prove" in r.err and RECORDED in r.err
    _no_open_of(opened, f)
    assert tree(root) == {}


# a Prove below the floor (0.3.0); one above it, such as 9.9.9, is one Trace reads
def test_ic9_with_poisson_prove_at_another_version_the_command_refuses_before_it_opens_a_file(tmp_path: Path) -> None:
    fake = tmp_path / "fake" / "poisson_prove"
    fake.mkdir(parents=True)
    (fake / "__init__.py").write_text('__version__ = "0.3.0"\n')
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path / "fake") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    r, opened, f, root = _probe(tmp_path, "", env)
    refused(r)
    assert "poisson-prove" in r.err and RECORDED in r.err and "0.3.0" in r.err
    _no_open_of(opened, f)
    assert tree(root) == {}


def test_ic9_with_poisson_prove_present_the_file_is_read(tmp_path: Path) -> None:
    r, opened, f, root = _probe(tmp_path, "", dict(os.environ))
    assert r.code == 0, r.text
    assert any(os.path.basename(p) == f.name for p in opened)


# ---------- IC10 ----------


def _nothing_under(root: Path) -> None:
    assert not root.exists() or not any(root.iterdir()), tree(root)


def test_ic10_an_unknown_tool_is_refused(tmp_path: Path) -> None:
    f = save(tmp_path / "results.json", small_doc())
    root = tmp_path / "store"
    argv = deepeval_argv(f, root, "v1")
    refused(run_import(["nosuchtool", *argv[1:]]))
    _nothing_under(root)
    assert run_import(argv).code == 0


def test_ic10_a_missing_file_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "store"
    refused(run_import(deepeval_argv(tmp_path / "absent.json", root, "v1")))
    good = save(tmp_path / "results.json", small_doc())
    refused(run_import(deepeval_argv([good, tmp_path / "absent.json"], root, "v1")))
    _nothing_under(root)
    assert run_import(deepeval_argv(good, root, "v1")).code == 0


@pytest.mark.parametrize("body", [
    b"case,score\nalpha,0.9\n",
    b"[1, 2, 3]",
    b'{"items": []}',
    b"\x00\x01\x02 not text",
    b"",
])
def test_ic10_a_file_that_is_not_the_tools_format_is_refused(tmp_path: Path, body: bytes) -> None:
    f = tmp_path / "results.json"
    f.write_bytes(body)
    root = tmp_path / "store"
    refused(run_import(deepeval_argv(f, root, "v1")))
    _nothing_under(root)
    save(f, small_doc())
    assert run_import(deepeval_argv(f, root, "v1")).code == 0


def test_ic10_no_row_read_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "store"
    empty = save(tmp_path / "empty.json", run_doc([]))
    refused(run_import(deepeval_argv(empty, root, "v1")))
    _nothing_under(root)
    save(empty, run_doc(scored("a", [0.9])))
    assert run_import(deepeval_argv(empty, root, "v1")).code == 0


def test_ic10_every_row_without_an_outcome_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "store"
    f = save(tmp_path / "results.json", run_doc([*scored("a", [None, None]), *scored("b", [None], start=2)]))
    refused(run_import(deepeval_argv(f, root, "v1")))
    refused(run_import(deepeval_argv(f, root, "v1", cut=("recorded",))))
    _nothing_under(root)
    save(f, run_doc([*scored("a", [None, 0.9]), *scored("b", [None], start=2)]))
    assert run_import(deepeval_argv(f, root, "v1")).code == 0


def test_ic10_a_run_name_in_use_is_refused_and_the_run_is_untouched(tmp_path: Path) -> None:
    """Sole catch through the command for an importer that appends to an existing run."""
    root = tmp_path / "store"
    f = save(tmp_path / "results.json", small_doc())
    g = save(tmp_path / "other.json", run_doc(scored("zeta", [0.9, 0.1])))
    assert run_import(deepeval_argv(f, root, "v1")).code == 0
    before = tree(root)
    refused(run_import(deepeval_argv(g, root, "v1")))
    refused(run_import(deepeval_argv(f, root, "v1")))
    assert tree(root) == before
    assert len(read_rows(root, "v1")) == ROWS_N


@pytest.mark.parametrize("started", ["yesterday", "2026-13-45T00:00:00Z", "12/09/2026", "", "2026-09-05 at noon"])
def test_ic10_started_that_is_not_iso_8601_is_refused(tmp_path: Path, started: str) -> None:
    root = tmp_path / "store"
    f = save(tmp_path / "results.json", small_doc())
    refused(run_import(deepeval_argv(f, root, "v1", extra=["--started", started])))
    _nothing_under(root)
    assert run_import(deepeval_argv(f, root, "v1", extra=["--started", "2026-09-05T18:54:07Z"])).code == 0


# ---------- IC11 ----------

HELP = "import sys\nfrom poisson_trace.ingest.cli import main\nsys.exit(main(['--help']))\n"


def _listed(text: str, name: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text) is not None


def test_ic11_help_lists_the_readers_present_and_no_other() -> None:
    # a tool's module is its name with "-" as "_" (openai-evals is openai_evals.py), as in TF10
    present = [n for n in READERS if (INGEST / f"{n.replace('-', '_')}.py").exists()]
    assert "deepeval" in present
    r = run_python(HELP)
    assert r.code == 0, r.text
    for name in READERS:
        assert _listed(r.out, name) == (name in present), (name, r.out)


def _copy_without(tmp_path: Path, reader: str) -> dict[str, str]:
    dest = tmp_path / "copy"
    shutil.copytree(PACKAGE, dest / "poisson_trace", ignore=shutil.ignore_patterns("__pycache__"))
    (dest / "poisson_trace" / "ingest" / f"{reader}.py").unlink()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(dest) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def test_ic11_a_reader_removed_from_a_copy_of_the_package_is_absent_and_refused(tmp_path: Path) -> None:
    env = _copy_without(tmp_path, "deepeval")
    where = run_python("import poisson_trace.ingest.cli as c; print(c.__file__)", env=env, cwd=tmp_path)
    assert where.out.strip().startswith(str(tmp_path / "copy")), where.text
    helped = run_python(HELP, env=env, cwd=tmp_path)
    assert helped.code == 0, helped.text
    assert not _listed(helped.out, "deepeval"), helped.out
    f = save(tmp_path / "results.json", small_doc())
    root = tmp_path / "store"
    refused(run_python(IMPORT_MAIN, deepeval_argv(f, root, "v1"), env=env, cwd=tmp_path))
    _nothing_under(root)


# ---------- IC12 ----------


def _started(root: Path, run: str) -> tuple[str, str]:
    m = Store(root).manifest(run)
    return m.created_at, m.environment["import"]["started_from"]


def _instant(text: str) -> datetime:
    assert text.endswith("Z"), text
    return datetime.fromisoformat(text[:-1] + "+00:00")


def test_ic12_started_from_is_given_exactly_when_started_is_passed(tmp_path: Path) -> None:
    f = save(tmp_path / "results.json", small_doc())
    stamp = 1_757_098_447  # 2025-09-05T18:54:07Z
    os.utime(f, (stamp, stamp))
    root = tmp_path / "store"
    plain = run_import(deepeval_argv(f, root, "plain"))
    given = run_import(deepeval_argv(f, root, "given", extra=["--started", "2026-01-02T03:04:05Z"]))
    offset = run_import(deepeval_argv(f, root, "offset", extra=["--started", "2026-01-02T05:04:05+02:00"]))
    for r in (plain, given, offset):
        assert r.code == 0, r.text
    at, source = _started(root, "plain")
    assert source in STARTED_FROM and source != "given" and source == "file time"
    assert _instant(at) == datetime.fromtimestamp(stamp, UTC)
    assert _started(root, "given") == ("2026-01-02T03:04:05Z", "given")
    at, source = _started(root, "offset")
    assert source == "given" and _instant(at) == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert "file time" in plain.out
    assert "given" in words(given.out)
    # a time the tool wrote inside the file (a JUnit suite's timestamp) is "file"
    assert STARTED_FROM == ("given", "file name", "earliest span", "file time", "file")


# ---------- IC13 ----------


def test_ic13_the_summary_holds_the_sections_in_order_and_ends_with_next(tmp_path: Path) -> None:
    f = save(tmp_path / "results.json", small_doc())
    digest = hashlib.sha256(f.read_bytes()).hexdigest()
    root = tmp_path / "store"
    r = run_import(deepeval_argv(f, root, "v7", metric="Score", cut=("0.5", "--below"),
                                 extra=["--started", "2026-09-05T18:54:07Z"]))
    assert r.code == 0, r.text
    assert r.err == ""
    lines = [line for line in r.out.splitlines() if line.strip()]
    assert "v7" in lines[0] and str(root) in r.out
    in_order(r.out, [
        re.escape(str(root)), re.escape(digest), r"\bScore\b", re.escape("2026-09-05T18:54:07Z"),
        rf"\b{ROWS_N}\b", rf"\b{CASES_N}\b", rf"\b{REPEATS[0]}\b", rf"\b{REPEATS[1]}\b",
        r"\bno score\b", r"(?m)^next:",
    ])
    started_at = r.out.index("2026-09-05T18:54:07Z")
    started_line = next(line for line in lines if "2026-09-05T18:54:07Z" in line)
    assert re.search(r"\bgiven\b", started_line), started_line
    no_score_at = r.out.index("no score", started_at)
    between = r.out[started_at:no_score_at]
    for n in (MET_N, MISSED_N):
        assert re.search(rf"\b{n}\b", between), (n, between)
    assert re.search(r"\bmet\b", between) and re.search(r"\bmissed\b", between)
    assert re.search(rf"\bno score\b\D*\b{NO_SCORE_N}\b|\b{NO_SCORE_N}\b\D*\bno score\b", r.out[no_score_at - 40:])
    last = lines[-1]
    assert last.startswith("next:") and "poisson-trace" in last and "v7" in last


def test_ic13_the_summary_uses_none_of_the_ten_words(tmp_path: Path) -> None:
    f = save(tmp_path / "results.json", small_doc())
    root = tmp_path / "store"
    md = run_import(deepeval_argv(f, root, "v1"))
    js = run_import(deepeval_argv(f, root, "v2", extra=["--json"]))
    recorded = run_import(deepeval_argv(f, root, "v3", cut=("recorded",)))
    for r in (md, js, recorded):
        assert r.code == 0, r.text
        assert not (words(r.out) & set(BANNED)), words(r.out) & set(BANNED)


def test_ic13_json_is_one_object_byte_identical_across_two_runs(tmp_path: Path) -> None:
    f = save(tmp_path / "results.json", small_doc())
    digest = hashlib.sha256(f.read_bytes()).hexdigest()
    root = tmp_path / "store"
    outs = []
    for _ in range(2):
        if root.exists():
            shutil.rmtree(root)
        r = run_import(deepeval_argv(f, root, "v1", extra=["--json", "--started", "2026-09-05T18:54:07Z"]))
        assert r.code == 0, r.text
        outs.append(r.out)
    assert outs[0] == outs[1]
    text = outs[0].strip()
    assert text.startswith("{") and text.endswith("}")
    doc = json.loads(text)
    assert isinstance(doc, dict) and doc["schema"] == IMPORT_SCHEMA
    values = scalars(doc)
    for want in ("v1", str(root), "deepeval", "results.json", digest, "Score", "2026-09-05T18:54:07Z",
                 "given", ROWS_N, CASES_N, REPEATS[0], REPEATS[1], MET_N, MISSED_N, NO_SCORE_N, "no score"):
        assert want in values, want


# ---------- IC14 ----------


def _versions(tmp_path: Path) -> tuple[Path, dict[str, list[str | None]], dict[str, list[str | None]]]:
    """OLD and NEW as DeepEval files, cut 0.5 below: x5 only in OLD, x6 only in NEW, x4 with a
    row without a score in OLD."""
    old = {"x1": [0.1, 0.2, 0.9, 0.3], "x2": [0.9, 0.8, 0.7, 0.6], "x3": [0.1, 0.1, 0.2, 0.4],
           "x4": [0.9, 0.2, None, 0.8, 0.7], "x5": [0.1, 0.9]}
    new = {"x1": [0.9, 0.8, 0.95, 0.6], "x2": [0.9, 0.3, 0.7, 0.6], "x3": [0.1, 0.6, 0.2, 0.7],
           "x4": [0.1, 0.2, 0.3, 0.4], "x6": [0.5, 0.2, 0.9]}
    root = tmp_path / "store"
    for name, scores in (("old", old), ("new", new)):
        cases = [c for i, (k, v) in enumerate(scores.items()) for c in scored(k, v, start=10 * i)]
        f = save(tmp_path / f"{name}.json", run_doc(cases))
        r = run_import(deepeval_argv(f, root, name))
        assert r.code == 0, r.text

    def outcomes(scores: dict[str, list[float | None]]) -> dict[str, list[str | None]]:
        return {k: [None if s is None else ("missed" if s < 0.5 else "met") for s in v] for k, v in scores.items()}

    return root, outcomes(old), outcomes(new)  # type: ignore[arg-type]


def test_ic14_fix_check_reads_the_counts_the_rows_hold(tmp_path: Path) -> None:
    root, old, new = _versions(tmp_path)
    r = run_trace(["fix-check", "old", "new", "--store", root, "--event", "missed", "--inputs", "all",
                   "--max-mde", "0.5", "--json"])
    assert r.code == 0, r.text
    d = json.loads(r.out)
    both = sorted(k for k in set(old) & set(new)
                  if any(o is not None for o in old[k]) and any(o is not None for o in new[k]))
    for arm, rows in (("old", old), ("new", new)):
        runs = sum(1 for k in both for o in rows[k] if o is not None)
        failed = sum(1 for k in both for o in rows[k] if o == "missed")
        no_outcome = sum(1 for k in both for o in rows[k] if o is None)
        assert (d["rows"][arm]["runs"], d["rows"][arm]["failed"]) == (runs, failed), arm
        assert d["rows"][arm]["no_outcome"] == no_outcome, arm
    assert d["inputs"]["compared"] == len(both)
    assert sum(d["inputs"]["left_out"].values()) == len(set(old) | set(new)) - len(both)
    tallies = {arm: Store(root).tally(arm) for arm in ("old", "new")}
    assert tallies["old"].no_outcome == sum(o is None for v in old.values() for o in v)
    assert tallies["new"].rows == sum(len(v) for v in new.values())


def test_ic14_changes_reads_the_counts_the_rows_hold(tmp_path: Path) -> None:
    root, old, new = _versions(tmp_path)
    r = run_trace(["changes", "old", "new", "--store", root, "--event", "missed", "--json"])
    assert r.code == 0, r.text
    d = json.loads(r.out)
    both = sorted(set(old) & set(new))
    assert d["tested"] == len(both)
    got = {row["config"]["case"]: (row["failed_a"], row["runs_a"], row["failed_b"], row["runs_b"]) for row in d["rows"]}
    want = {
        k: (Counter(old[k])["missed"], sum(o is not None for o in old[k]),
            Counter(new[k])["missed"], sum(o is not None for o in new[k]))
        for k in both
    }
    assert got == want


def test_ic7_case_input_keeps_no_text_of_the_input(tmp_path: Path) -> None:
    """The input is the case's identity only as a digest."""
    doc = _content_doc()
    doc["conversationalTestCases"] = []
    f = save(tmp_path / "results.json", doc)
    root = tmp_path / "store"
    r = run_import(deepeval_argv(f, root, "v1", case="input"))
    assert r.code == 0, r.text
    assert len(read_rows(root, "v1")) == 5
    assert holds(root, SENTINEL) == []
