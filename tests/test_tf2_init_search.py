"""TF2-6, TF2-7 and TF2-9: how ``init`` finds results (spec sections 4.3 and 4.7, ruling R1;
yes/nos 11 to 14).

One pass over the current folder's tree, breadth first and in name order, to a depth of six
folders below it, reading at most 10,000 entries and saying so when it stops short. A store is a
folder holding at least one run folder whose ``manifest.json`` has ``run_id``, ``target_id`` and
``t_unit``; a run folder is not searched further. The pass skips ``.git``, ``.venv``, ``venv``,
``node_modules``, ``__pycache__``, ``.work``, ``site-packages`` and every folder whose name opens
with a dot but ``.deepeval``; it follows no link to a folder. It never searches the home folder:
run in the home folder or a folder above it, ``init`` refuses before it looks. ``--store PATH``
searches nothing.

The listing goes to stderr, stores first (shallower first, then by path), then the result files
the readers in the install would read (DeepEval's saved test runs, by folder; tables with a
column named like a Ragas metric, at most 200 candidate files opened). Each store's line gives its
runs, its targets as names show them (four at most, then how many more) and its newest day. Only
manifests are read to list a store; the one store read further is the one chosen, and of it the
newest 20 runs only."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from poisson_prove.store import Store

from tf0_support import RUN_ID
from tf2_support import (  # noqa: F401
    CONFIG, R, config, no_network, refused, counts, deepeval_file, doc, init_yes, number_of, numbered, outcome_runs, ragas_file,
    scratch_home, stamp, store_of, tree, two_stores, work,
)


def _listed(err: str) -> list[str]:
    """The paths the listing numbers, in its order."""
    return [line.split()[0].rstrip("/") for _, line in sorted(numbered(err).items())]


def _yes(folder: Path, *argv: str):  # type: ignore[no-untyped-def]
    result = init_yes(folder, *argv)
    assert result.code == 0, result.text
    return result


# ---------- TF2-6: stores ----------


def test_tf2_06_every_store_is_listed_shallower_first_and_the_first_is_taken(tmp_path: Path) -> None:
    folder = work(tmp_path)
    two_stores(folder)
    result = _yes(folder)
    assert _listed(result.err)[:2] == ["proofload-runs", "demo/store"], result.err
    assert config(folder)["store"]["path"] == "proofload-runs"


def test_tf2_06_stores_at_one_depth_are_listed_by_path(tmp_path: Path) -> None:
    folder = work(tmp_path)
    store_of(folder / "b-store", [R("b1", stamp(1, 9))])
    store_of(folder / "a-store", [R("a1", stamp(1, 10))])
    store_of(folder / "c" / "deeper", [R("c1", stamp(1, 11))])
    assert _listed(_yes(folder).err) == ["a-store", "b-store", "c/deeper"]


def test_tf2_06_a_store_six_folders_down_is_found_and_seven_is_not(tmp_path: Path) -> None:
    folder = work(tmp_path)
    store_of(folder / "a" / "b" / "c" / "d" / "e" / "six", [R("six-run", stamp(1, 9))])
    store_of(folder / "p" / "q" / "r" / "s" / "t" / "u" / "seven", [R("seven-run", stamp(1, 9))])
    assert _listed(_yes(folder).err) == ["a/b/c/d/e/six"]


SKIPPED = (".git", ".venv", "venv", "node_modules", "__pycache__", ".work", "site-packages", ".hidden")


def test_tf2_06_the_skipped_folders_are_not_searched(tmp_path: Path) -> None:
    folder = work(tmp_path)
    for skip in SKIPPED:
        store_of(folder / skip / "store", [R(f"r-{skip.strip('.')}", stamp(1, 9))])
    store_of(folder / "kept", [R("kept-run", stamp(1, 9))])
    assert _listed(_yes(folder).err) == ["kept"]


def _manifest(path: Path, body: object) -> None:
    path.mkdir(parents=True)
    (path / "manifest.json").write_text(body if isinstance(body, str) else json.dumps(body), encoding="utf-8")


def test_tf2_06_a_store_is_a_folder_of_runs_whose_manifests_name_run_target_and_unit(tmp_path: Path) -> None:
    folder = work(tmp_path)
    _manifest(folder / "no-unit" / "r1", {"run_id": "r1", "target_id": "agent-x/m@v0"})
    _manifest(folder / "no-target" / "r1", {"run_id": "r1", "t_unit": "steps"})
    _manifest(folder / "not-json" / "r1", "{ not json")
    _manifest(folder / "a-list" / "r1", ["run_id", "target_id", "t_unit"])
    store_of(folder / "real", [R("real-run", stamp(1, 9))])
    assert _listed(_yes(folder).err) == ["real"]


def test_tf2_06_a_store_inside_a_run_is_not_found(tmp_path: Path) -> None:
    folder = work(tmp_path)
    store_of(folder / "outer", [R("o1", stamp(1, 9))])
    store_of(folder / "outer" / "o1" / "inner", [R("i1", stamp(1, 10))])
    assert _listed(_yes(folder).err) == ["outer"]


def test_tf2_06_no_link_to_a_folder_is_followed(tmp_path: Path) -> None:
    folder = work(tmp_path)
    store_of(tmp_path / "outside" / "store", [R("away", stamp(1, 9))])
    os.symlink(tmp_path / "outside", folder / "link-out")
    store_of(folder / "real-store", [R("near", stamp(1, 9))])
    os.symlink(folder / "real-store", folder / "alias")
    assert _listed(_yes(folder).err) == ["real-store"]


@pytest.mark.parametrize("where", ["the home folder", "a folder above it"])
def test_tf2_06_init_never_searches_the_home_folder(tmp_path: Path, scratch_home: Path, where: str) -> None:  # noqa: F811
    store_of(scratch_home / "zq-proj" / "store", [R("mine", stamp(1, 9))])
    folder = scratch_home if where == "the home folder" else tmp_path
    result = init_yes(folder)
    refused(result)
    assert numbered(result.err) == {} and "zq-proj" not in result.err, result.err
    assert not (folder / CONFIG).exists()


def test_tf2_06_a_project_inside_the_home_folder_is_searched(scratch_home: Path) -> None:  # noqa: F811
    """The refusal is for the home folder and the folders above it, not the projects in it."""
    project = scratch_home / "code" / "agent"
    store_of(project / "store", [R("mine", stamp(1, 9))])
    _yes(project)
    assert config(project)["store"]["path"] == "store"


def test_tf2_06_a_store_in_the_home_folder_beside_is_not_found(tmp_path: Path, scratch_home: Path) -> None:  # noqa: F811
    store_of(scratch_home / "zq-proj" / "store", [R("mine", stamp(1, 9))])
    folder = work(tmp_path)
    result = _yes(folder)
    assert numbered(result.err) == {} and "zq-proj" not in result.err, result.err
    assert "store" not in config(folder)


@pytest.mark.parametrize("filled", ["one folder of files", "three folders of files", "one folder of folders"])
def test_tf2_06_the_pass_stops_at_10000_entries_and_says_so(tmp_path: Path, filled: str) -> None:
    """Every entry read counts, files and folders alike, across folders: the store past the bound
    is not reached."""
    folder = work(tmp_path)
    if filled == "one folder of files":
        (folder / "a-fill").mkdir()
        for i in range(15_000):
            (folder / "a-fill" / f"f{i:05d}").touch()
    elif filled == "three folders of files":
        for part in ("a-1", "a-2", "a-3"):
            (folder / part).mkdir()
            for i in range(6_000):
                (folder / part / f"f{i:04d}").touch()
    else:
        (folder / "a-fill").mkdir()
        for i in range(12_000):
            (folder / "a-fill" / f"d{i:05d}").mkdir()
    store_of(folder / "b-proj" / "store", [R("late", stamp(1, 9))])
    result = _yes(folder)
    assert 10_000 in counts(result.err), result.err
    assert "b-proj/store" not in _listed(result.err)
    assert "store" not in config(folder)


def test_tf2_06_the_pass_is_breadth_first(tmp_path: Path) -> None:
    """A store one folder down is reached before the bound a deep folder of files would hit first
    going depth first."""
    folder = work(tmp_path)
    (folder / "a" / "b" / "fill").mkdir(parents=True)
    for i in range(15_000):
        (folder / "a" / "b" / "fill" / f"f{i:05d}").touch()
    store_of(folder / "z-store", [R("near", stamp(1, 9))])
    result = _yes(folder)
    assert "z-store" in _listed(result.err), result.err
    assert config(folder)["store"]["path"] == "z-store"


def test_tf2_06_store_path_searches_nothing(tmp_path: Path) -> None:
    folder = work(tmp_path)
    two_stores(folder)
    result = _yes(folder, "--store", "demo/store")
    assert "proofload-runs" not in result.err, result.err
    assert config(folder)["store"]["path"] == "demo/store"


def test_tf2_06_store_path_that_holds_no_run_is_refused(tmp_path: Path) -> None:
    folder = work(tmp_path)
    (folder / "empty").mkdir()
    for path in ("no-such", "empty"):
        result = init_yes(folder, "--store", path)
        assert path in refused(result), result.err
    assert not (folder / CONFIG).exists()


# ---------- TF2-7: result files ----------


def _results(folder: Path) -> None:
    deepeval_file(folder / "results" / "test_run_20261002_101500.json")
    deepeval_file(folder / "results" / "test_run_20261002_111500.json")
    wrapped = folder / ".deepeval" / ".latest_test_run.json"
    deepeval_file(wrapped)
    wrapped.write_text(json.dumps({"testRunData": json.loads(wrapped.read_text(encoding="utf-8"))}), encoding="utf-8")
    ragas_file(folder / "scores" / "base.jsonl")
    ragas_file(folder / "scores" / "table.csv")
    # files with the same extensions that no reader of the install reads
    (folder / "notes").mkdir()
    (folder / "notes" / "data.json").write_text(json.dumps([{"case": "a", "score": 1}]), encoding="utf-8")
    (folder / "notes" / "plain.csv").write_text("case,score\na,1\nfaithfulness,2\n", encoding="utf-8")
    (folder / "notes" / "test_run_20261002_121500.json").write_text(json.dumps({"rows": []}), encoding="utf-8")


def test_tf2_07_result_files_of_the_readers_in_the_install_are_listed(tmp_path: Path) -> None:
    folder = work(tmp_path)
    _results(folder)
    result = _yes(folder, "--no-import")
    listed = _listed(result.err)
    assert sorted(listed) == sorted([".deepeval", "results", "scores/base.jsonl", "scores/table.csv"]), result.err
    assert "store" not in config(folder)


def test_tf2_07_result_files_are_listed_after_the_stores(tmp_path: Path) -> None:
    folder = work(tmp_path)
    _results(folder)
    store_of(folder / "zz-deep" / "store", [R("s1", stamp(1, 9))])
    result = _yes(folder)
    listed = _listed(result.err)
    assert listed[0] == "zz-deep/store" and len(listed) == 5, result.err
    assert config(folder)["store"]["path"] == "zz-deep/store"


@pytest.mark.parametrize("decoys,found", [(199, True), (200, False)])
def test_tf2_07_at_most_200_candidate_files_are_opened(tmp_path: Path, decoys: int, found: bool) -> None:
    folder = work(tmp_path)
    for i in range(decoys):
        (folder / f"c{i:03d}.csv").write_text("case,score\na,1\n", encoding="utf-8")
    ragas_file(folder / "zz-scores.csv")
    result = _yes(folder, "--no-import")
    assert ("zz-scores.csv" in _listed(result.err)) is found, result.err


# ---------- TF2-9: what listing a store reads ----------


def test_tf2_09_a_store_line_gives_its_runs_targets_and_newest_day(tmp_path: Path) -> None:
    folder = work(tmp_path)
    targets = ("t-alpha", "t-bravo", "t-charlie", "t-delta", "t-echo", "t-foxtrot")
    runs = [R(f"run-{i}", stamp(1 + i, 9), target_id=f"{t}/model@v0") for i, t in enumerate(targets)]
    runs.append(R("run-again", stamp(9, 9), target_id="t-alpha/model@v0"))
    store_of(folder / "many", runs)
    store_of(folder / "two", [R("a", stamp(4, 9), target_id="t-golf/m@v0"), R("b", stamp(5, 9), target_id="t-hotel/m@v0")])
    result = _yes(folder)
    lines = numbered(result.err)
    many = lines[number_of(result.err, "many")]
    shown = [t for t in targets if t in many]
    assert len(shown) == 4 and "model" not in many, many
    assert 7 in counts(many) and 2 in counts(many) and "2026-10-09" in many, many
    two = lines[number_of(result.err, "two")]
    assert "t-golf" in two and "t-hotel" in two and 2 in counts(two) and "2026-10-05" in two, two


def test_tf2_09_only_the_chosen_stores_newest_20_runs_are_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = work(tmp_path)
    ids = outcome_runs(folder / "a-store", [("ancient", "fail")] * 2 + [("fail", "ok")] * 20)
    store_of(folder / "b-store", [R("b-one", stamp(1, 9)), R("b-two", stamp(1, 10))])
    read: list[str] = []
    contents: list[object] = []
    for method in ("read", "tally", "count"):
        original = getattr(Store, method)

        def recorded(self: Store, run_id: str, *args: object, _original=original, _method=method, **kwargs: object) -> object:  # type: ignore[no-untyped-def]
            read.append(run_id)
            if _method == "read":
                contents.append(kwargs.get("meta", True))
            return _original(self, run_id, *args, **kwargs)

        monkeypatch.setattr(Store, method, recorded)
    result = _yes(folder)
    assert config(folder)["store"]["path"] == "a-store"
    assert config(folder)["events"]["failed"] == ["fail"], result.text
    assert read and set(read) <= set(ids[2:]), sorted(set(read))
    # the rows are read for their outcomes, never for what they hold
    assert contents and not any(contents), contents


def test_tf2_09_init_writes_nothing_under_any_store_and_contacts_no_host(tmp_path: Path, no_network: list[str]) -> None:  # noqa: F811
    folder = work(tmp_path)
    first, second = two_stores(folder)
    before = (tree(first), tree(second))
    result = _yes(folder)
    assert no_network == []
    assert (tree(first), tree(second)) == before
    assert not (first / "trace-names.toml").exists()
    assert RUN_ID.search(result.out) is None and RUN_ID.search((folder / CONFIG).read_text()) is None, result.out
