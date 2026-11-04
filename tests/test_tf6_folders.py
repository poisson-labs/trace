"""TF6-37 to TF6-39: saving a verdict over runs read from folders (SV16, Taylor 2026-11-04;
where TF6 meets TF22's folder ingest). Added by TF6's Session B once TF22's build was on main;
not among the files Session A froze.

- TF6-37: on runs read from tool folders, ``--save`` prints one ``note:`` line, ``the verdict
  was not saved: the runs were read from folders, not a store``, and goes on: the output is the
  plain output, ``--json`` gains no ``saved``, and nothing is written anywhere.
- TF6-38: on the same runs ``--out DIR`` still writes its bundle, with each run's ``store`` null
  in ``handover.json`` (as FI13 nulls it in ``--json``), ``saved`` null in ``result.json``, no
  absolute path in it, and ``handover --check`` holds; the note is still printed.
- TF6-39: runs read from a Prove folder save into that folder's store, the same artifact the
  runs reach by ``--store``; ``handover.json``'s ``store`` is null there too.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest
from tf0_support import chdir
from tf22_support import JUNIT, NEW, OLD, copy_into, junit_shards, trace, tree
from tf6_support import (
    AFTER_ID,
    BEFORE_ID,
    EVENTS_012,
    artifacts,
    files_in,
    store012,
    the_artifact,
    without_detail,
)

NOTE = "note: the verdict was not saved: the runs were read from folders, not a store"
# each verb on the JUnit pair read from folders: its run words and its own flags
VERBS: dict[str, tuple[list[str], list[str]]] = {
    "fix-check": ([OLD, NEW], ["--inputs", "all", "--max-mde", "0.2"]),
    "changes": ([OLD, NEW], []),
    "where": ([NEW], []),
}


def _pair(here: Path) -> tuple[Path, Path]:
    """Two JUnit folders built from the committed pair, the older version first."""
    old, new = here / OLD, here / NEW
    junit_shards(old)
    copy_into(new, JUNIT / "humaneval-b.xml")
    return old, new


def _argv(verb: str, *extra: str) -> list[str]:
    words, own = VERBS[verb]
    return [verb, *words, "--event", "missed", *own, "--plain", *extra]


@pytest.fixture
def here(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A folder holding the pair, the temporary folder pointed into the test's own, so that
    nothing written anywhere can hide."""
    here = tmp_path / "here"
    here.mkdir()
    _pair(here)
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setenv("TMPDIR", str(temp))
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    return here


# ---------- TF6-37 ----------


@pytest.mark.parametrize("verb", list(VERBS))
def test_tf6_37_save_on_tool_folders_says_so_and_goes_on(here: Path, verb: str) -> None:
    before = tree(here.parent)
    with chdir(here):
        plain = trace(*_argv(verb))
        saved = trace(*_argv(verb, "--save"))
        as_json = trace(*_argv(verb, "--json"))
        saved_json = trace(*_argv(verb, "--save", "--json"))
    assert plain.code == 0 and plain.err == "", plain.text
    assert saved.code == 0 and saved_json.code == 0, saved.text + saved_json.text
    assert saved.out == plain.out
    assert "  saved  " not in saved.out
    assert saved.err.splitlines() == [NOTE] and saved_json.err.splitlines() == [NOTE]
    assert saved_json.json() == as_json.json() and "saved" not in saved_json.json()
    assert tree(here.parent) == before
    assert list((here.parent / "temp").iterdir()) == []


# ---------- TF6-38 ----------


def _bundle(here: Path, verb: str, *extra: str) -> tuple[Path, Any]:
    bundle = here.parent / "bundle"
    with chdir(here):
        ran = trace(*_argv(verb, "--out", str(bundle), *extra))
    assert ran.code == 0, ran.text
    return bundle, ran


@pytest.mark.parametrize("verb", list(VERBS))
def test_tf6_38_out_on_tool_folders_still_writes_the_bundle(here: Path, verb: str) -> None:
    with chdir(here):
        plain = trace(*_argv(verb))
    bundle, ran = _bundle(here, verb)
    assert ran.err.splitlines() == [NOTE]
    assert without_detail(ran.out, "wrote") == plain.out
    assert f"  wrote  {bundle}" in ran.out.splitlines() and "  saved  " not in ran.out
    assert {"artifact.json", "result.json", "report.md", "table.parquet", "handover.json"} <= set(
        files_in(bundle)
    )
    handover = json.loads((bundle / "handover.json").read_text(encoding="utf-8"))
    assert handover["verb"] == verb
    assert [r["store"] for r in handover["runs"]] == [None] * len(VERBS[verb][0])
    assert [r["run_name"] for r in handover["runs"]] == VERBS[verb][0]
    result = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
    assert result["saved"] is None and result["prove"]["store"] is None
    for name in files_in(bundle):
        assert str(here.parent).encode() not in (bundle / name).read_bytes(), name
    check = trace("handover", "--check", str(bundle))
    assert check.code == 0, check.text
    # the bundle is all that was written: the store that held the runs did not outlive the command
    assert list((here.parent / "temp").iterdir()) == []
    assert sorted(p.name for p in here.parent.iterdir()) == ["bundle", "here", "temp"]


def test_tf6_38_folders_typed_by_absolute_path_are_written_by_name(here: Path) -> None:
    old, new = here / OLD, here / NEW
    bundle = here.parent / "b"
    ran = trace(
        "changes", str(old), str(new), "--event", "missed", "--plain", "--out", str(bundle)
    )
    assert ran.code == 0, ran.text
    report = (bundle / "report.md").read_text(encoding="utf-8")
    assert str(here) not in report and f"poisson-trace fix-check {OLD} {NEW}" in report
    result = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
    assert str(here) not in json.dumps(result)


def test_tf6_38_the_json_gains_nothing_on_tool_folders(here: Path) -> None:
    bundle = here.parent / "bundle"
    with chdir(here):
        plain = trace(*_argv("fix-check", "--json"))
        ran = trace(*_argv("fix-check", "--json", "--out", str(bundle)))
    assert ran.code == 0 and ran.err.splitlines() == [NOTE], ran.text
    assert ran.json() == plain.json()
    assert (bundle / "handover.json").is_file()


# ---------- TF6-39 ----------


def _prove_argv(verb: str, store: Path, *extra: str) -> list[str]:
    """Each verb on the two runs of a copy of the Prove 0.1.2 store, given as run folders."""
    before, after = str(store / BEFORE_ID), str(store / AFTER_ID)
    return {
        "where": ["where", after, *EVENTS_012, "--at", "3"],
        "compare": ["compare", before, after, *EVENTS_012, "--max-mde-hr", "1.5"],
        "fix-check": ["fix-check", before, after, *EVENTS_012, "--inputs", "all", "--max-mde", "0.2"],
        "changes": ["changes", before, after, *EVENTS_012],
    }[verb] + ["--plain", *extra]


@pytest.mark.parametrize("verb", ["where", "compare", "fix-check", "changes"])
def test_tf6_39_prove_folders_save_into_their_own_store(tmp_path: Path, verb: str) -> None:
    by_store = store012(tmp_path / "one")
    by_folder = store012(tmp_path / "two")
    from tf6_support import argv012, run_ok

    run_ok(argv012(verb, by_store, "--save"))
    with chdir(tmp_path / "two"):
        ran = trace(*_prove_argv(verb, Path("store"), "--save"))
    assert ran.code == 0 and ran.err == "", ran.text
    folder = the_artifact(by_folder, verb)
    assert folder.name == the_artifact(by_store, verb).name
    assert f"  saved  {verb} {folder.name[:12]}" in ran.out.splitlines()
    result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    # the runs are read from the store that holds them, which --json names as none (FI13)
    assert result["prove"]["store"] is None and result["saved"] == f".poisson/artifacts/{verb}/{folder.name}"
    assert str(tmp_path).encode() not in (folder / "report.md").read_bytes()


def test_tf6_39_a_prove_folder_bundle_names_no_store(tmp_path: Path) -> None:
    store = store012(tmp_path)
    bundle = tmp_path / "b"
    ran = trace(*_prove_argv("changes", store, "--out", str(bundle)))
    assert ran.code == 0 and ran.err == "", ran.text
    handover = json.loads((bundle / "handover.json").read_text(encoding="utf-8"))
    assert [(r["run_id"], r["store"]) for r in handover["runs"]] == [(BEFORE_ID, None), (AFTER_ID, None)]
    assert len(artifacts(store, "changes")) == 1
    assert trace("handover", "--check", str(bundle)).code == 0
