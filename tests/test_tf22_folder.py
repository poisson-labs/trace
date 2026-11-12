"""TF22-1 to TF22-14: the folder resolver, ``poisson_trace.ingest.folder.resolve`` (spec section
18.3.1). It says what a folder holds, in the spec's order, and refuses what it cannot read as
one run, without reading a row: a Prove run folder, a store holding one run, a saved pull
folder, or one tool's result files. Several runs, several tools and nothing to read are refused
(``Refusal``, exit 1 at the command line), each naming what it found.

The API these tests pin: ``resolve(path, tool=None) -> Resolved`` with ``kind`` (one of
``KINDS``), ``path``, ``name`` (the folder's own name, the default run name), ``tool``,
``files`` (absolute paths, in name order; as listed for a pull), ``store`` and ``run_id`` (a
Prove folder's).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import CS, TAU2
from tf22_support import (
    CS_RUNS,
    JUNIT,
    PROVE_013,
    PROVE_013_RUNS,
    RAGAS,
    TABLE,
    TAU2_RUNS,
    copy_into,
    deepeval_folder,
    junit_shards,
    names,
    one_run_store,
    pull_folder,
    ragas_parts,
    sha256_of,
    table_parts,
)

from poisson_trace.ingest.rows import Refusal


def _resolve(path: Path, tool: str | None = None):  # type: ignore[no-untyped-def]
    from poisson_trace.ingest.folder import resolve

    return resolve(path, tool)


def test_tf22_1_kinds_are_the_four() -> None:
    from poisson_trace.ingest.folder import KINDS

    assert KINDS == ("run", "store", "pull", "files")


# ---------- TF22-1: a Prove run folder ----------


@pytest.mark.parametrize(
    ("store", "run_id"),
    [(PROVE_013, PROVE_013_RUNS[0]), (CS, CS_RUNS[0]), (TAU2, TAU2_RUNS[1])],
    ids=["prove-0.1.3", "cs", "tau2"],
)
def test_tf22_1_a_prove_run_folder_is_read_where_it_is(store: Path, run_id: str) -> None:
    got = _resolve(store / run_id)
    assert got.kind == "run"
    assert got.store == store
    assert got.run_id == run_id
    assert got.tool is None
    assert got.files == ()
    assert got.name == run_id


def test_tf22_1_a_run_folder_is_known_by_its_manifest_and_episodes(tmp_path: Path) -> None:
    # control: the run folder copied whole is a run
    import shutil

    whole = tmp_path / "whole"
    shutil.copytree(CS / CS_RUNS[0], whole / CS_RUNS[0])
    assert _resolve(whole / CS_RUNS[0]).kind == "run"
    # a manifest without the episodes folder is not a run folder; nothing else in it is read
    bare = tmp_path / "bare" / CS_RUNS[0]
    bare.mkdir(parents=True)
    shutil.copy2(CS / CS_RUNS[0] / "manifest.json", bare / "manifest.json")
    with pytest.raises(Refusal):
        _resolve(bare)


# ---------- TF22-2 and TF22-3: a store ----------


@pytest.mark.parametrize(
    ("source", "run_id"),
    [(PROVE_013, PROVE_013_RUNS[1]), (CS, CS_RUNS[1]), (TAU2, TAU2_RUNS[0])],
    ids=["prove-0.1.3", "cs", "tau2"],
)
def test_tf22_2_a_store_of_one_run_is_that_run(tmp_path: Path, source: Path, run_id: str) -> None:
    store = one_run_store(tmp_path / "one", source, run_id)
    got = _resolve(store)
    assert got.kind == "store"
    assert got.store == store
    assert got.run_id == run_id
    assert got.tool is None
    assert got.name == "one"


@pytest.mark.parametrize(
    ("store", "runs"),
    [(PROVE_013, PROVE_013_RUNS), (CS, CS_RUNS), (TAU2, TAU2_RUNS)],
    ids=["prove-0.1.3", "cs", "tau2"],
)
def test_tf22_3_a_store_of_several_runs_is_refused_naming_each(store: Path, runs: tuple[str, ...]) -> None:
    with pytest.raises(Refusal) as e:
        _resolve(store)
    said = str(e.value) + " ".join(e.value.nexts)
    # every run's folder is named, so that one can be given; the store's own .poisson is not a run
    assert names(said, *runs)
    assert ".poisson" not in said.replace(str(store), "")


# ---------- TF22-4 and TF22-5: a saved pull folder ----------


def test_tf22_4_a_pull_folder_reads_its_listed_files_with_its_tool(tmp_path: Path) -> None:
    files = [JUNIT / "trace-suite-1.xml"]
    folder = pull_folder(tmp_path / "pull", "junit", files)
    # a file the pull did not list is not read, even one a reader claims
    copy_into(folder, JUNIT / "humaneval-b.xml")
    got = _resolve(folder)
    assert got.kind == "pull"
    assert got.tool == "junit"
    assert [p.name for p in got.files] == ["trace-suite-1.xml"]
    assert got.name == "pull"


def test_tf22_4_a_pull_lists_its_files_in_its_own_order(tmp_path: Path) -> None:
    files = [JUNIT / "trace-suite-2.xml", JUNIT / "trace-suite-1.xml"]
    got = _resolve(pull_folder(tmp_path / "pull", "junit", files))
    assert [p.name for p in got.files] == ["trace-suite-2.xml", "trace-suite-1.xml"]


def _pull_cases(tmp: Path) -> dict[str, Path]:
    f = JUNIT / "trace-suite-1.xml"
    good = {"path": f.name, "sha256": sha256_of(f), "rows": None}
    return {
        "schema": pull_folder(tmp / "schema", "junit", [f], schema="poisson.raw-pull/9"),
        "tool": pull_folder(tmp / "tool", "lemma", [f]),
        "missing": pull_folder(tmp / "missing", "junit", [f], files=[good, {**good, "path": "gone.xml"}]),
        "digest": pull_folder(tmp / "digest", "junit", [f], files=[{**good, "sha256": "0" * 64}]),
        "outside": pull_folder(tmp / "outside", "junit", [f], files=[good, {**good, "path": "../x.xml"}]),
        "empty": pull_folder(tmp / "empty", "junit", [f], files=[]),
        "not-json": copy_into(tmp / "not-json", f),
    }


@pytest.mark.parametrize("fault", ["schema", "tool", "missing", "digest", "outside", "empty", "not-json"])
def test_tf22_5_a_pull_folder_that_is_not_whole_is_refused(tmp_path: Path, fault: str) -> None:
    folder = _pull_cases(tmp_path)[fault]
    if fault == "not-json":
        (folder / "pull.json").write_text("{ not json\n", encoding="utf-8")
    # control: the same files under a whole pull.json resolve
    control = pull_folder(tmp_path / "control", "junit", [JUNIT / "trace-suite-1.xml"])
    assert _resolve(control).kind == "pull"
    with pytest.raises(Refusal) as e:
        _resolve(folder)
    assert names(str(e.value), "pull.json")


def test_tf22_5_a_pull_of_a_tool_not_in_this_install_names_the_tool(tmp_path: Path) -> None:
    folder = pull_folder(tmp_path / "lm", "lemma", [JUNIT / "trace-suite-1.xml"])
    with pytest.raises(Refusal) as e:
        _resolve(folder)
    assert names(str(e.value), "lemma", tmp=tmp_path)


def test_tf22_5_a_tool_given_that_differs_from_the_pull_is_refused(tmp_path: Path) -> None:
    folder = pull_folder(tmp_path / "pull", "junit", [JUNIT / "trace-suite-1.xml"])
    assert _resolve(folder, "junit").kind == "pull"
    with pytest.raises(Refusal):
        _resolve(folder, "table")


# ---------- TF22-6 to TF22-9: one tool's files ----------


@pytest.mark.parametrize(
    ("tool", "source"),
    [("junit", JUNIT / "humaneval-a.xml"), ("table", TABLE / "humaneval-a.csv"),
     ("ragas", RAGAS / "rag-base.jsonl")],
)
def test_tf22_6_one_data_file_is_the_run(tmp_path: Path, tool: str, source: Path) -> None:
    folder = copy_into(tmp_path / "results", source)
    got = _resolve(folder)
    assert (got.kind, got.tool, got.name) == ("files", tool, "results")
    assert got.files == (folder / source.name,)
    assert got.store is None and got.run_id is None


def test_tf22_6_a_deepeval_results_folder_is_deepevals(tmp_path: Path) -> None:
    folder = deepeval_folder(tmp_path / "deepeval-results", "a")
    got = _resolve(folder)
    assert (got.kind, got.tool) == ("files", "deepeval")
    assert [p.name for p in got.files] == ["test_run_20260929_143252.json"]


def test_tf22_7_hidden_journal_and_readme_files_are_left_out(tmp_path: Path) -> None:
    folder = copy_into(tmp_path / "results", JUNIT / "humaneval-a.xml")
    # each of these is a JUnit report by content, so only the name keeps it out
    for name in (".DS_Store", ".hidden.xml", "_journal.xml", "README.xml", "README"):
        (folder / name).write_bytes((JUNIT / "humaneval-b.xml").read_bytes())
    got = _resolve(folder)
    assert [p.name for p in got.files] == ["humaneval-a.xml"]


def test_tf22_7_files_no_reader_claims_and_subfolders_are_left_out(tmp_path: Path) -> None:
    # the committed junit folder holds the reports' own recipe scripts beside them
    folder = copy_into(tmp_path / "results", JUNIT / "humaneval-a.xml", JUNIT / "make.py",
                       JUNIT / "fixture_host.py")
    copy_into(folder / "older", JUNIT / "humaneval-b.xml")
    got = _resolve(folder)
    assert [p.name for p in got.files] == ["humaneval-a.xml"]
    assert got.tool == "junit"


def test_tf22_8_junit_shards_are_every_shard_in_name_order(tmp_path: Path) -> None:
    folder = junit_shards(tmp_path / "shards")
    got = _resolve(folder)
    assert got.tool == "junit"
    assert [p.name for p in got.files] == ["junit-0.xml", "junit-1.xml", "junit-2.xml", "junit-3.xml"]


def test_tf22_8_name_order_is_by_code_point_not_by_number(tmp_path: Path) -> None:
    folder = junit_shards(tmp_path / "shards", pattern="w{i}.xml")
    (folder / "w3.xml").rename(folder / "w10.xml")
    got = _resolve(folder)
    assert [p.name for p in got.files] == ["w0.xml", "w1.xml", "w10.xml", "w2.xml"]


@pytest.mark.parametrize("tool", ["table", "ragas"])
def test_tf22_9_table_parts_are_every_part(tmp_path: Path, tool: str) -> None:
    folder = table_parts(tmp_path / "t") if tool == "table" else ragas_parts(tmp_path / "t")
    got = _resolve(folder)
    assert got.tool == tool
    ext = "csv" if tool == "table" else "jsonl"
    assert [p.name for p in got.files] == [f"part-00000.{ext}", f"part-00001.{ext}"]


# ---------- TF22-10 to TF22-14: what is refused ----------


def test_tf22_10_the_claims_are_the_readers_own(tmp_path: Path) -> None:
    """Every file resolve takes for a tool is one that tool's ``looks_like`` claims."""
    from importlib import import_module

    for tool, folder in (
        ("junit", junit_shards(tmp_path / "j")),
        ("table", table_parts(tmp_path / "t")),
        ("ragas", ragas_parts(tmp_path / "r")),
        ("deepeval", deepeval_folder(tmp_path / "d", "a", "b")),
    ):
        got = _resolve(folder)
        reader = import_module(f"poisson_trace.ingest.{tool}")
        assert got.tool == tool
        assert all(reader.looks_like(p) is not None for p in got.files)


def test_tf22_11_a_folder_of_two_tools_is_refused_naming_each_file(tmp_path: Path) -> None:
    folder = copy_into(tmp_path / "mixed", JUNIT / "humaneval-a.xml", TABLE / "humaneval-a.csv")
    with pytest.raises(Refusal) as e:
        _resolve(folder)
    said = str(e.value) + " ".join(e.value.nexts)
    assert names(said, "humaneval-a.xml", "humaneval-a.csv", "junit", "table", tmp=tmp_path)


def test_tf22_11_naming_the_tool_reads_only_its_files(tmp_path: Path) -> None:
    folder = copy_into(tmp_path / "mixed", JUNIT / "humaneval-a.xml", TABLE / "humaneval-a.csv")
    got = _resolve(folder, "table")
    assert (got.kind, got.tool) == ("files", "table")
    assert [p.name for p in got.files] == ["humaneval-a.csv"]
    got = _resolve(folder, "junit")
    assert [p.name for p in got.files] == ["humaneval-a.xml"]


def test_tf22_11_a_tool_named_with_no_file_of_its_own_is_refused(tmp_path: Path) -> None:
    folder = copy_into(tmp_path / "j", JUNIT / "humaneval-a.xml")
    assert _resolve(folder, "junit").files
    with pytest.raises(Refusal):
        _resolve(folder, "ragas")


@pytest.mark.parametrize("held", ["nothing", "ignored", "unclaimed", "subfolder"])
def test_tf22_12_a_folder_with_nothing_to_read_is_refused(tmp_path: Path, held: str) -> None:
    folder = tmp_path / "empty-results"
    folder.mkdir()
    if held == "ignored":
        (folder / ".DS_Store").write_bytes(b"\0")
        (folder / "README.md").write_text("results\n")
    elif held == "unclaimed":
        copy_into(folder, JUNIT / "make.py")
    elif held == "subfolder":
        copy_into(folder / "inner", JUNIT / "humaneval-a.xml")
    with pytest.raises(Refusal) as e:
        _resolve(folder)
    assert names(str(e.value), "empty-results", tmp=tmp_path)


@pytest.mark.parametrize("what", ["missing", "file"])
def test_tf22_12_a_path_that_is_not_a_folder_is_refused(tmp_path: Path, what: str) -> None:
    path = tmp_path / "missing" if what == "missing" else copy_into(tmp_path, JUNIT / "humaneval-a.xml") / "humaneval-a.xml"
    with pytest.raises(Refusal):
        _resolve(path)


def test_tf22_13_an_unpacked_inspect_log_is_one_inspect_run(tmp_path: Path) -> None:
    """An unpacked Inspect log (``header.json`` and ``samples/*.json``) is one Inspect run
    (section 18.3.1 3b). The Inspect reader is TF10's (FI3; TF10's RD7 moved this test from
    the refusal TF22 froze to the reading): the folder resolves to the Inspect reader, with the
    folder itself as what it reads, and imported, with the tool named or left out, it gives the
    same records as the ``.eval`` it was unpacked from. Named as another tool's, it is refused,
    saying it is Inspect's, rather than read as anything else."""
    from tf10_support import IN_EVAL, eval_members, imported, in_argv, recs

    from poisson_trace.ingest.cli import present

    assert "inspect" in present()
    folder = tmp_path / "inspect-log"
    (folder / "samples").mkdir(parents=True)
    for name, value in eval_members().items():
        if name == "header.json" or name.startswith("samples/"):
            (folder / name).write_text(json.dumps(value) + "\n")
    got = _resolve(folder)
    assert (got.kind, got.tool, got.files, got.name) == ("files", "inspect", (folder,), "inspect-log")
    assert _resolve(folder, "inspect") == got
    root = tmp_path / "st"
    imported(in_argv(IN_EVAL, root, "eval"))
    imported(in_argv(folder, root, "named"))
    imported([str(folder), "--store", str(root), "--run", "found"])
    assert recs(root, "named") == recs(root, "eval") == recs(root, "found")
    with pytest.raises(Refusal) as e:
        _resolve(folder, "junit")
    assert names(str(e.value), "Inspect", tmp=tmp_path)


def test_tf22_14_resolving_writes_nothing(tmp_path: Path) -> None:
    from tf22_support import tree

    folders = [
        junit_shards(tmp_path / "j"),
        pull_folder(tmp_path / "p", "junit", [JUNIT / "trace-suite-1.xml"]),
        one_run_store(tmp_path / "s", CS, CS_RUNS[0]),
    ]
    before = tree(tmp_path)
    for f in folders:
        _resolve(f)
    for store in (CS, TAU2, PROVE_013):
        with pytest.raises(Refusal):
            _resolve(store)
    assert tree(tmp_path) == before
