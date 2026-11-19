"""TF22-15 to TF22-23: ``poisson-trace import`` given a folder.

``import TOOL DIR`` reads the folder's files of that tool; ``import DIR`` finds the tool. Both
print, byte for byte, what ``import TOOL FILE ...`` prints on the same files in name order (a
pull's in its listed order), and write the same run. ``--run`` may be left out for a folder:
the run takes the folder's name. A Prove folder is not imported (it is already a store). A
folder holding two runs, two tools or nothing is refused, exit 1, with nothing written. The
reader's own flags are still required, exit 2 without them, as for files.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import CS
from tf22_support import (
    CS_RUNS,
    FLAGS,
    JUNIT,
    RAGAS,
    TABLE,
    Ran,
    copy_into,
    deepeval_folder,
    file_entries,
    junit_shards,
    names,
    one_run_store,
    plain_refusal,
    pull_folder,
    ragas_parts,
    records,
    sha256_of,
    table_parts,
    trace_import,
    tree,
)

# What each built folder is, and its files in the order the import reads them.
BUILT = ("junit-one", "junit-shards", "table-parts", "ragas-one", "ragas-parts", "deepeval-one", "pull")
FAST_BUILT = ("junit-one", "junit-shards", "ragas-parts", "pull")


def build(kind: str, tmp: Path) -> tuple[str, Path, list[Path]]:
    """``(tool, folder, files in read order)`` for a built folder."""
    folder = tmp / "results"
    if kind == "junit-one":
        copy_into(folder, JUNIT / "humaneval-a.xml")
        tool = "junit"
    elif kind == "junit-shards":
        junit_shards(folder)
        tool = "junit"
    elif kind == "table-parts":
        table_parts(folder)
        tool = "table"
    elif kind == "ragas-one":
        copy_into(folder, RAGAS / "rag-base.jsonl")
        tool = "ragas"
    elif kind == "ragas-parts":
        ragas_parts(folder)
        tool = "ragas"
    elif kind == "deepeval-one":
        deepeval_folder(folder, "a")
        tool = "deepeval"
    elif kind == "pull":
        pull_folder(folder, "junit", [JUNIT / "trace-suite-2.xml", JUNIT / "humaneval-b.xml"])
        return "junit", folder, [folder / "trace-suite-2.xml", folder / "humaneval-b.xml"]
    else:
        raise AssertionError(kind)
    files = sorted((p for p in folder.iterdir() if p.is_file()), key=lambda p: p.name)
    return tool, folder, files


def _both(kind: str, tmp: Path, *extra: str) -> tuple[Ran, Ran, Path, Path]:
    tool, folder, files = build(kind, tmp)
    by_files, by_folder = tmp / "by-files", tmp / "by-folder"
    a = trace_import(tool, *files, "--store", by_files, "--run", "v1", *FLAGS[tool], *extra)
    b = trace_import(tool, folder, "--store", by_folder, "--run", "v1", *FLAGS[tool], *extra)
    return a, b, by_files, by_folder


def _same_output(a: Ran, b: Ran, by_files: Path, by_folder: Path) -> None:
    assert a.code == 0, a.text
    assert b.code == a.code, b.text
    # the store's path is the one thing the two commands were given differently
    assert b.out.replace(str(by_folder), "<STORE>") == a.out.replace(str(by_files), "<STORE>")
    assert b.err.replace(str(by_folder), "<STORE>") == a.err.replace(str(by_files), "<STORE>")


def _same_run(by_files: Path, by_folder: Path, run: str = "v1") -> None:
    assert records(by_folder, run) == records(by_files, run)
    assert file_entries(by_folder, run) == file_entries(by_files, run)


# ---------- TF22-15: import TOOL DIR is import TOOL FILE ... ----------


@pytest.mark.parametrize("kind", FAST_BUILT)
def test_tf22_15_a_folder_imports_as_its_files(tmp_path: Path, kind: str) -> None:
    a, b, by_files, by_folder = _both(kind, tmp_path)
    _same_output(a, b, by_files, by_folder)
    _same_run(by_files, by_folder)


@pytest.mark.parametrize("kind", FAST_BUILT)
def test_tf22_15_a_folder_imports_as_its_files_json(tmp_path: Path, kind: str) -> None:
    a, b, by_files, by_folder = _both(kind, tmp_path, "--json")
    _same_output(a, b, by_files, by_folder)
    _same_run(by_files, by_folder)


@pytest.mark.slow
@pytest.mark.parametrize("kind", [kind for kind in BUILT if kind not in FAST_BUILT])  # the fast two run the rest
@pytest.mark.parametrize("form", ["plain", "json"])
def test_tf22_15_every_built_folder_imports_as_its_files(tmp_path: Path, kind: str, form: str) -> None:
    extra = ("--json",) if form == "json" else ()
    a, b, by_files, by_folder = _both(kind, tmp_path, *extra)
    _same_output(a, b, by_files, by_folder)
    _same_run(by_files, by_folder)


def test_tf22_15_shards_merged_hold_the_whole_reports_rows(tmp_path: Path) -> None:
    """The shards of one report merge into one run with every case once, as
    the whole report reads, and the manifest lists every shard with its digest."""
    _, folder, files = build("junit-shards", tmp_path)
    whole, merged = tmp_path / "whole", tmp_path / "merged"
    assert trace_import("junit", JUNIT / "humaneval-a.xml", "--store", whole, "--run", "v1").code == 0
    assert trace_import("junit", folder, "--store", merged, "--run", "v1").code == 0

    def by_case(root: Path) -> dict[str, tuple[object, object]]:
        return {r["signals"]["case"]: (r["outcome"], r["signals"]["outcome"]) for r in records(root, "v1")}

    assert by_case(merged) == by_case(whole)
    assert [(e["name"], e["sha256"]) for e in file_entries(merged, "v1")] == [
        (f.name, sha256_of(f)) for f in files
    ]


# ---------- TF22-16: import DIR finds the tool ----------


@pytest.mark.parametrize("kind", ["junit-shards", "ragas-one", "pull"])
@pytest.mark.parametrize("form", ["plain", "json"])
def test_tf22_16_import_dir_finds_the_tool(tmp_path: Path, kind: str, form: str) -> None:
    tool, folder, _ = build(kind, tmp_path)
    extra = ("--json",) if form == "json" else ()
    named, found = tmp_path / "named", tmp_path / "found"
    a = trace_import(tool, folder, "--store", named, "--run", "v1", *FLAGS[tool], *extra)
    b = trace_import(folder, "--store", found, "--run", "v1", *FLAGS[tool], *extra)
    _same_output(a, b, named, found)
    _same_run(named, found)


def test_tf22_16_the_import_command_reads_the_same(tmp_path: Path) -> None:
    """``poisson-trace-import`` is the same command (its first name): it takes a folder too."""
    from tf22_support import _call

    _, folder, _ = build("junit-shards", tmp_path)
    a = trace_import(folder, "--store", tmp_path / "a", "--run", "v1")
    b = _call("poisson_trace.ingest.cli", [folder, "--store", tmp_path / "b", "--run", "v1"])
    assert a.code == b.code == 0, a.text + b.text
    assert b.out.replace(str(tmp_path / "b"), "<S>") == a.out.replace(str(tmp_path / "a"), "<S>")


# ---------- TF22-17: the run's name ----------


def test_tf22_17_a_folder_without_run_takes_the_folders_name(tmp_path: Path) -> None:
    _, folder, files = build("junit-shards", tmp_path)
    named = tmp_path / "named"
    unnamed = tmp_path / "unnamed"
    a = trace_import("junit", *files, "--store", named, "--run", "results")
    b = trace_import(folder, "--store", unnamed)
    _same_output(a, b, named, unnamed)
    assert (unnamed / "results" / "manifest.json").is_file()


def test_tf22_17_run_given_is_the_name(tmp_path: Path) -> None:
    _, folder, _ = build("junit-one", tmp_path)
    store = tmp_path / "s"
    assert trace_import(folder, "--store", store, "--run", "baseline").code == 0
    assert (store / "baseline" / "manifest.json").is_file()
    assert not (store / "results").exists()


def test_tf22_17_files_still_need_run(tmp_path: Path) -> None:
    ran = trace_import("junit", JUNIT / "humaneval-a.xml", "--store", tmp_path / "s")
    assert ran.code == 2, ran.text
    assert not (tmp_path / "s").exists()


def test_tf22_17_a_folder_name_that_is_no_run_name_is_refused(tmp_path: Path) -> None:
    folder = copy_into(tmp_path / ("r" * 81), JUNIT / "humaneval-a.xml")
    # control: the same folder with --run imports
    assert trace_import(folder, "--store", tmp_path / "ok", "--run", "v1").code == 0
    store = tmp_path / "s"
    plain_refusal(trace_import(folder, "--store", store))
    assert not store.exists() or tree(store) == {}


# ---------- TF22-18: a Prove folder is not imported ----------


@pytest.mark.parametrize("what", ["run", "store"])
def test_tf22_18_a_prove_folder_is_already_a_store(tmp_path: Path, what: str) -> None:
    folder = CS / CS_RUNS[0] if what == "run" else one_run_store(tmp_path / "one", CS, CS_RUNS[0])
    store = tmp_path / "s"
    ran = trace_import(folder, "--store", store, "--run", "v1")
    sentence = plain_refusal(ran)
    assert names(sentence, CS_RUNS[0] if what == "run" else "one", tmp=tmp_path)
    assert not store.exists() or tree(store) == {}
    # under it, the command that reads the folder as the store it is
    held = folder.parent if what == "run" else folder
    nexts = [line.strip().removeprefix("next: ") for line in ran.err.splitlines()[1:]]
    assert any(n.startswith("poisson-trace ") and str(held) in n and "--store" in n for n in nexts), ran.err


# ---------- TF22-19: a pull folder ----------


def test_tf22_19_a_pull_folder_imports_as_its_listed_files(tmp_path: Path) -> None:
    _, folder, files = build("pull", tmp_path)
    copy_into(folder, JUNIT / "humaneval-a.xml")  # not listed, never read
    a = trace_import("junit", *files, "--store", tmp_path / "a", "--run", "v1", "--json")
    b = trace_import(folder, "--store", tmp_path / "b", "--run", "v1", "--json")
    _same_output(a, b, tmp_path / "a", tmp_path / "b")
    assert [e["name"] for e in b.json()["files"]] == ["trace-suite-2.xml", "humaneval-b.xml"]


def test_tf22_19_a_pull_whose_file_changed_writes_nothing(tmp_path: Path) -> None:
    _, folder, _ = build("pull", tmp_path)
    (folder / "humaneval-b.xml").write_bytes((JUNIT / "humaneval-a.xml").read_bytes())
    store = tmp_path / "s"
    sentence = plain_refusal(trace_import(folder, "--store", store, "--run", "v1"))
    assert names(sentence, "humaneval-b.xml", tmp=tmp_path)
    assert not store.exists() or tree(store) == {}


# ---------- TF22-20 to TF22-22: refused with nothing written ----------


def _two_runs(kind: str, tmp: Path) -> tuple[Path, tuple[str, ...]]:
    folder = tmp / "two-runs"
    if kind == "junit-suite":
        copy_into(folder, JUNIT / "trace-suite-1.xml", JUNIT / "trace-suite-2.xml")
        return folder, ("trace-suite-1.xml", "trace-suite-2.xml")
    if kind == "junit-versions":
        copy_into(folder, JUNIT / "humaneval-a.xml", JUNIT / "humaneval-b.xml")
        return folder, ("humaneval-a.xml", "humaneval-b.xml")
    if kind == "ragas":
        copy_into(folder, RAGAS / "rag-base.jsonl", RAGAS / "rag-raft.jsonl")
        return folder, ("rag-base.jsonl", "rag-raft.jsonl")
    if kind == "table":
        copy_into(folder, TABLE / "humaneval-a.csv", TABLE / "humaneval-b.csv")
        return folder, ("humaneval-a.csv", "humaneval-b.csv")
    if kind == "deepeval":
        deepeval_folder(folder, "a", "b")
        return folder, ("test_run_20260929_143252.json", "test_run_20260929_143257.json")
    raise AssertionError(kind)


TOOL_OF = {"junit-suite": "junit", "junit-versions": "junit", "ragas": "ragas", "table": "table",
           "deepeval": "deepeval"}


@pytest.mark.parametrize("kind", ["junit-suite", "junit-versions", "ragas", "table", "deepeval"])
def test_tf22_20_a_folder_of_two_runs_is_refused_naming_each(tmp_path: Path, kind: str) -> None:
    """Two runs in one folder are never pooled. A case in two files makes
    them two runs; the refusal names every file and, under it, how to read one of them."""
    folder, files = _two_runs(kind, tmp_path)
    tool = TOOL_OF[kind]
    # control: each file alone imports
    for i, f in enumerate(files):
        ok = trace_import(tool, folder / f, "--store", tmp_path / "ok", "--run", f"v{i}", *FLAGS[tool])
        assert ok.code == 0, ok.text
    store = tmp_path / "s"
    ran = trace_import(tool, folder, "--store", store, "--run", "v1", *FLAGS[tool])
    sentence = plain_refusal(ran)
    nexts = ran.err.split("\n", 1)[1]
    assert names(sentence + nexts, *files, tmp=tmp_path)
    assert "next:" in ran.err
    assert not store.exists() or tree(store) == {}


def test_tf22_20_the_refusal_without_a_tool_is_the_same(tmp_path: Path) -> None:
    folder, _ = _two_runs("junit-suite", tmp_path)
    a = trace_import("junit", folder, "--store", tmp_path / "s", "--run", "v1")
    b = trace_import(folder, "--store", tmp_path / "s", "--run", "v1")
    assert (a.code, a.out, a.err) == (b.code, b.out, b.err)


def test_tf22_21_a_folder_of_two_tools_is_refused_without_a_tool(tmp_path: Path) -> None:
    folder = copy_into(tmp_path / "mixed", JUNIT / "humaneval-a.xml", RAGAS / "rag-base.jsonl")
    store = tmp_path / "s"
    sentence = plain_refusal(trace_import(folder, "--store", store, "--run", "v1"))
    assert names(sentence, "junit", "ragas", tmp=tmp_path)
    assert not store.exists() or tree(store) == {}
    # naming the tool reads its files alone
    ran = trace_import("ragas", folder, "--store", store, "--run", "v1", *FLAGS["ragas"], "--json")
    assert ran.code == 0, ran.text
    assert [f["name"] for f in ran.json()["files"]] == ["rag-base.jsonl"]


@pytest.mark.parametrize("with_tool", [True, False])
def test_tf22_22_an_empty_folder_is_refused(tmp_path: Path, with_tool: bool) -> None:
    folder = tmp_path / "nothing-here"
    folder.mkdir()
    (folder / ".DS_Store").write_bytes(b"\0")
    store = tmp_path / "s"
    head = ("junit",) if with_tool else ()
    # control: a folder holding one report, given the same way, imports
    other = copy_into(tmp_path / "something-here", JUNIT / "trace-suite-1.xml")
    assert trace_import(*head, other, "--store", tmp_path / "ok", "--run", "v1").code == 0
    sentence = plain_refusal(trace_import(*head, folder, "--store", store, "--run", "v1"))
    assert names(sentence, "nothing-here", tmp=tmp_path)
    assert not store.exists() or tree(store) == {}


# ---------- TF22-23: the reader's flags are still the reader's ----------


@pytest.mark.parametrize("kind", ["table-parts", "ragas-one"])
def test_tf22_23_a_folder_still_needs_its_readers_flags(tmp_path: Path, kind: str) -> None:
    tool, folder, files = build(kind, tmp_path)
    by_files = trace_import(tool, *files, "--store", tmp_path / "a", "--run", "v1")
    by_folder = trace_import(tool, folder, "--store", tmp_path / "b", "--run", "v1")
    found = trace_import(folder, "--store", tmp_path / "c", "--run", "v1")
    assert by_files.code == by_folder.code == found.code == 2, by_folder.text + found.text
    assert not (tmp_path / "b").exists() and not (tmp_path / "c").exists()


def test_tf22_23_a_folder_leaves_its_files_as_they_were(tmp_path: Path) -> None:
    _, folder, _ = build("junit-shards", tmp_path)
    before = tree(folder)
    assert trace_import(folder, "--store", tmp_path / "s", "--run", "v1").code == 0
    assert tree(folder) == before
