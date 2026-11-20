"""TF19-9: the objects only the app needs, frozen as core functions.

**TF19-9** What the app needs and no verb gives, each from a core function in
``poisson_trace.core``: ``saved_verdicts`` (the saved verdicts as a list), ``run_sources`` (a
run's target or tool, and an imported run's tool and files) and ``found_results`` (the result
files ``init`` finds, each with its import line, and whether it is imported). Their signatures
and their frozen dataclasses' fields, in order; what each returns on the workspace, held to what
the store, the verbs and ``init`` say themselves; each prints nothing, reads no environment
variable and writes nothing.
"""

from __future__ import annotations

import contextlib
import dataclasses
import inspect
import io
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from app_support import EV, RESULT_FILES, app_world, changed, cli, copy_world, ids, snapshot

FIELDS = {
    "SavedVerdict": ("kind", "id", "runs", "run_ids", "verdict", "sentence", "saved_at", "folder", "page"),
    "RunSource": ("run_id", "target", "tool", "files", "target_or_tool"),
    "FoundResult": ("path", "tool", "said", "command", "fill", "imported"),
}
FUNCTIONS = {
    "saved_verdicts": ["store"],
    "run_sources": ["store"],
    "found_results": ["folder", "store"],
}


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return app_world(tmp_path_factory)


def core() -> Any:
    from poisson_trace import core as c

    return c


# ---------- the shapes ----------


@pytest.mark.parametrize("name", sorted(FUNCTIONS))
def test_tf19_9_each_function_s_signature(name: str) -> None:
    fn = getattr(core(), name)
    params = list(inspect.signature(fn).parameters.values())
    assert [p.name for p in params] == FUNCTIONS[name]
    assert params[0].kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    if name == "found_results":
        assert params[1].kind is inspect.Parameter.KEYWORD_ONLY
        assert params[1].default == "trace-store"


@pytest.mark.parametrize("name", sorted(FIELDS))
def test_tf19_9_each_object_is_a_frozen_dataclass(name: str) -> None:
    cls = getattr(core(), name)
    assert dataclasses.is_dataclass(cls)
    assert cls.__dataclass_params__.frozen  # type: ignore[attr-defined]
    assert tuple(f.name for f in dataclasses.fields(cls)) == FIELDS[name]


# ---------- the saved verdicts ----------


def _artifact(store: Path, kind: str, ident: str) -> tuple[dict[str, Any], dict[str, Any]]:
    folder = store / ".poisson" / "artifacts" / kind / ident
    art = json.loads((folder / "artifact.json").read_text(encoding="utf-8"))
    result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    return art, result


def _names(kind: str, result: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if kind == "where":
        return (result["run"]["run_name"],), (result["run"]["run_id"],)
    runs = list(result["runs"].values())
    return tuple(r["run_name"] for r in runs), tuple(r["run_id"] for r in runs)


@pytest.mark.parametrize("store", ["store", "tables"])
def test_tf19_9_saved_verdicts_lists_every_saved_verdict(world: Path, store: str) -> None:
    got = core().saved_verdicts(world / store)
    expected = {(k, i) for s, k, i in ids(world).values() if s == store}
    assert {(v.kind, v.id) for v in got} == expected
    assert len(got) == len(expected)
    for v in got:
        art, result = _artifact(world / store, v.kind, v.id)
        names, run_ids = _names(v.kind, result)
        assert (v.verdict, v.sentence) == (result["verdict"], result["sentence"])
        assert (v.runs, v.run_ids) == (names, run_ids)
        assert v.saved_at == art["created_at"]
        assert v.folder == f".poisson/artifacts/{v.kind}/{v.id}"
        assert v.page == f"trace/{v.kind}/{v.id}.html"
        assert len(v.id) == 16


def test_tf19_9_saved_verdicts_newest_first(world: Path, tmp_path: Path) -> None:
    work = copy_world(world, tmp_path)
    store = work / "store"
    # the save times set apart, as TF18-2's case on save times does: the order is theirs alone
    stamps = ["2026-11-01T00:00:01Z", "2026-11-03T00:00:00Z", "2026-11-02T00:00:00Z", "2026-11-05T00:00:00Z", "2026-11-04T00:00:00Z"]
    # Trace's five; Prove's own saved comparison beside them is not Trace's and is not listed
    folders = sorted(p for p in (store / ".poisson" / "artifacts").glob("*/*")
                     if p.parent.name in ("where", "compare", "fix-check", "changes"))
    for folder, at in zip(folders, stamps, strict=True):
        path = folder / "artifact.json"
        art = json.loads(path.read_text(encoding="utf-8"))
        art["created_at"] = at
        path.write_text(json.dumps(art, indent=2) + "\n", encoding="utf-8")
    got = core().saved_verdicts(store)
    assert [v.saved_at for v in got] == sorted(stamps, reverse=True)


def test_tf19_9_saved_verdicts_same_times_order_by_kind_then_id(world: Path) -> None:
    got = core().saved_verdicts(world / "store")
    keys = [(v.saved_at, v.kind, v.id) for v in got]
    assert keys == sorted(keys, reverse=True)


def test_tf19_9_saved_verdicts_of_a_store_with_none(world: Path) -> None:
    assert core().saved_verdicts(world / "jstore") == []
    assert core().saved_verdicts(str(world / "jstore")) == []


def test_tf19_9_saved_verdicts_of_no_store(world: Path) -> None:
    from poisson_trace import api

    with pytest.raises(api.Refusal) as runs:
        api.runs(str(world / "no-such"))
    with pytest.raises(api.Refusal) as got:
        core().saved_verdicts(world / "no-such")
    assert str(got.value) == str(runs.value)
    with pytest.raises(api.Refusal) as sources:
        core().run_sources(world / "no-such")
    assert str(sources.value) == str(runs.value)


# ---------- the run sources ----------


def test_tf19_9_run_sources_of_prove_runs(world: Path) -> None:
    from poisson_trace import api

    got = core().run_sources(world / "store")
    listed = json.loads(api.runs(str(world / "store"), event=["violated", "timeout"]).to_json())["runs"]
    assert [s.run_id for s in got] == [r["run_id"] for r in listed]
    for s, r in zip(got, listed, strict=True):
        assert s.target == r["target_id"] == "mock-agent"
        assert (s.tool, s.files, s.target_or_tool) == (None, (), "mock-agent")


@pytest.mark.parametrize(("store", "tool", "files"), [
    ("jstore", "junit", {"jb": ("humaneval-b.xml",), "ja": ("humaneval-a.xml",)}),
    ("tables", "table", {"new": ("new.csv",), "old": ("old.csv",)}),
])
def test_tf19_9_run_sources_of_imports(world: Path, store: str, tool: str, files: dict[str, tuple[str, ...]]) -> None:
    got = core().run_sources(world / store)
    assert [s.run_id for s in got] == list(files)
    for s in got:
        manifest = json.loads((world / store / s.run_id / "manifest.json").read_text(encoding="utf-8"))
        named = tuple(f["name"] for f in manifest["produced_by"]["from"])
        assert s.files == files[s.run_id] == named
        assert (s.target, s.tool, s.target_or_tool) == (None, tool, tool)


# ---------- the files init finds ----------


def _init_listing(folder: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """What ``init --yes --no-import`` prints in a folder of result files and no store: the
    files its listing numbers (on stderr) as ``(path, words)``, and the import lines it prints
    for them."""
    ran = cli(folder, ["init", "--yes", "--no-import"])
    assert ran.code == 0, ran.text
    found, lines = [], []
    for line in (ran.err + ran.out).splitlines():
        s = line.strip()
        if s[:1].isdigit() and ") " in s:
            path, _, said = s.split(") ", 1)[1].partition("  ")
            found.append((path.strip(), said.strip()))
        elif s.startswith("poisson-trace import "):
            lines.append(s)
    return found, lines


@pytest.fixture(scope="module")
def results_only(world: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("found") / "f"
    (folder / "results").mkdir(parents=True)
    for name in sorted(p.name for p in (world / "results").iterdir()):
        shutil.copy2(world / "results" / name, folder / "results" / name)
    return folder


def test_tf19_9_found_results_are_init_s(results_only: Path, tmp_path: Path) -> None:
    got = core().found_results(results_only)
    probe = tmp_path / "probe"
    shutil.copytree(results_only, probe)
    found, lines = _init_listing(probe)
    assert [(f.path, f.said) for f in got] == found
    assert {f.command for f in got} == set(lines)
    assert {f.tool for f in got} == {r for r, _ in RESULT_FILES}
    assert all(not f.imported for f in got)
    for f in got:
        assert f.command.startswith(f"poisson-trace import {f.tool} {f.path} --store trace-store ")
        assert f.fill == tuple(w for w in f.command.split() if w.isupper() and w.isalpha())
    assert {f.tool: f.fill for f in got}["promptfoo"] == ("PROMPT",)


def test_tf19_9_found_results_take_the_store_given(results_only: Path) -> None:
    got = core().found_results(results_only, store="jstore")
    assert got and all(" --store jstore " in f.command for f in got)
    assert [f.path for f in got] == [f.path for f in core().found_results(results_only)]


def test_tf19_9_found_results_know_what_is_imported(world: Path) -> None:
    """The workspace's ``files/humaneval-a.xml`` and ``-b`` are ``jstore``'s runs' files, by
    their bytes; the files under ``results/`` are not imported."""
    got = {f.path: f for f in core().found_results(world)}
    assert got["files/humaneval-a.xml"].imported and got["files/humaneval-b.xml"].imported
    for _reader, name in RESULT_FILES:
        assert not got[f"results/{name}"].imported, name
    assert not got["files/trace-suite-1.xml"].imported


def test_tf19_9_every_found_file_has_its_line(world: Path) -> None:
    """``init`` prints at most 12 import lines; the core gives every file found its own (the
    workspace finds more than 12)."""
    got = core().found_results(world)
    assert len(got) > 12
    for f in got:
        assert f.command.startswith(f"poisson-trace import {f.tool} {f.path} --store trace-store --run "), f
    assert len({f.command.split(" --run ")[1].split()[0] for f in got}) == len(got)


def test_tf19_9_found_results_imported_by_bytes_not_name(world: Path, tmp_path: Path) -> None:
    work = copy_world(world, tmp_path)
    (work / "files" / "humaneval-a.xml").write_bytes((work / "files" / "humaneval-a.xml").read_bytes() + b"\n")
    got = {f.path: f for f in core().found_results(work)}
    assert not got["files/humaneval-a.xml"].imported
    assert got["files/humaneval-b.xml"].imported


# ---------- pure ----------


@pytest.mark.parametrize("call", ["saved_verdicts", "run_sources", "found_results"])
def test_tf19_9_each_is_pure(world: Path, tmp_path: Path, call: str) -> None:
    """Each prints nothing, reads no environment variable in Trace's own code, reads and lists
    nothing outside the path it was given (and where Python lives), and writes nothing (TF13's
    watch, as TF13-24 to TF13-27 hold the API to it)."""
    from api_support import outside, python_roots, watched

    work = copy_world(world, tmp_path)
    given = work if call == "found_results" else work / "store"
    before = snapshot(work)
    out, err = io.StringIO(), io.StringIO()
    with watched(tmp_path / "systemp") as watch, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        if call == "found_results":
            core().found_results(given)
        else:
            getattr(core(), call)(given)
    assert (out.getvalue(), err.getvalue()) == ("", "")
    assert watch.env == [], watch.env
    assert watch.written == [], watch.written
    roots = [given, *python_roots()]
    assert outside(watch.opened, roots) == [], outside(watch.opened, roots)
    assert outside(watch.listed, roots) == [], outside(watch.listed, roots)
    assert changed(before, snapshot(work)) == set()


def test_tf19_9_the_verbs_still_print_what_they_did(world: Path) -> None:
    """The objects add nothing to a verb: ``runs --json`` keeps ``target_id`` and ``backend``
    and gains no key (this holds the keys, not the whole of each verb's output)."""
    ran = cli(world, ["runs", "--store", "store", *EV, "--json"])
    doc = json.loads(ran.out)
    assert set(doc["runs"][0]) == {"number", "name", "run_id", "named_by", "rows", "failed", "traced", "created_at",
                                    "status", "target_id", "backend"}
