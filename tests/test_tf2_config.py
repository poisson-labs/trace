"""TF2-1 to TF2-3: how every verb reads ``trace.toml``.

The config is the file ``trace.toml`` in the current folder, or the file ``--config PATH``
names, written before or after the verb; never one in a folder above. A store path in it is
read from the folder that holds it. Every verb that names a store or events takes them from it
when no flag gives them: ``runs``, ``name``, ``where``, ``compare``, ``fix-check``, ``changes``,
and the import's store. A flag replaces what the config gives (an ``--event`` replaces the
config's events, it does not add to them); ``--store NAME`` takes the config's store of that
name before a folder of that name. ``fix-check`` and ``compare`` take their ceilings from
``[check]`` when the flag is not given. With neither a config nor a flag giving the store or the
events, the refusal is the one with no config: a wrong command line, exit 2."""

from __future__ import annotations

from pathlib import Path

import pytest
from poisson_prove.store import Store

from tf0_support import deepeval_import
from tf1_support import T_A, T_B, T_PILOT, tau2_copy
from tf2_support import (  # noqa: F401
    R, config_of, doc, here, import_here, scratch_home, stamp, store_of, work, write_config,
)

S = "proofload-runs"


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """A folder holding a copy of the tau2 store and a config naming it, with unsolved as the failure."""
    place = work(tmp_path)
    tau2_copy(place, S)
    write_config(place, config_of(S))
    return place


VERBS = {
    "runs": ["runs", "--json"],
    "where": ["where", "previous", "--json"],
    "compare": ["compare", "#3", "#2", "--max-mde-hr", "1.5", "--json"],
    "fix-check": ["fix-check", "#3", "#2", "--inputs", "all", "--max-mde", "0.2", "--json"],
    "changes": ["changes", "#3", "#2", "--json"],
}


@pytest.mark.parametrize("verb", VERBS)
def test_tf2_01_every_verb_takes_the_store_and_the_events_from_the_config(folder: Path, tmp_path: Path, verb: str) -> None:
    result = here(folder, VERBS[verb])
    assert result.code == 0, result.text
    data = doc(result)
    if verb == "runs":
        rows = {row["run_id"]: row for row in data["runs"]}
        assert set(rows) == {T_A, T_B, T_PILOT}
        assert all(row["failed"] is not None and row["failed"] > 0 for row in rows.values()), rows
    else:
        assert data["events"] == ["unsolved"], data["events"]
    # the control: the same command where there is no config is a wrong command line
    bare = work(tmp_path, "bare")
    tau2_copy(bare, S)
    without = here(bare, VERBS[verb])
    assert without.code == 2 and without.out == "", without.text


def test_tf2_01_name_takes_the_store_from_the_config(folder: Path) -> None:
    named = here(folder, ["name", "previous", "old re-run"])
    assert named.code == 0, named.text
    assert (folder / S / "trace-names.toml").exists()
    listed = here(folder, ["name", "--list"])
    assert listed.code == 0 and "old re-run" in listed.out, listed.text


@pytest.mark.parametrize("before", [True, False], ids=["before the verb", "after the verb"])
@pytest.mark.parametrize("verb", [*VERBS, "name"])
def test_tf2_01_config_names_another_file_and_its_paths_are_read_from_its_folder(tmp_path: Path, before: bool, verb: str) -> None:
    top = work(tmp_path)
    tau2_copy(top / "elsewhere", "runs-here")
    write_config(top / "elsewhere", config_of("runs-here"), "other.toml")
    flag = ["--config", "elsewhere/other.toml"]
    words = ["name", "--list"] if verb == "name" else VERBS[verb]
    argv = [*flag, *words] if before else [*words, *flag]
    result = here(top, argv)
    assert result.code == 0, result.text
    if verb == "where":
        assert doc(result)["run"]["run_id"] == T_B and doc(result)["events"] == ["unsolved"]
    elif verb == "runs":
        assert all(row["failed"] is not None for row in doc(result)["runs"])
    elif verb != "name":
        assert doc(result)["events"] == ["unsolved"]


def test_tf2_01_a_named_stores_path_is_read_from_the_configs_folder_and_a_typed_one_from_here(tmp_path: Path) -> None:
    top = work(tmp_path)
    store_of(top / "conf" / "named", [R("n-one", stamp(5, 9))])
    store_of(top / "typed", [R("t-one", stamp(5, 10))])
    write_config(top / "conf", config_of("named", ("fail",), '\n[store.named]\npath = "named"\n'), "team.toml")
    named = here(top, ["where", "latest", "--store", "named", "--config", "conf/team.toml", "--json"])
    assert named.code == 0 and doc(named)["run"]["run_id"] == "n-one", named.text
    typed = here(top, ["where", "latest", "--store", "typed", "--config", "conf/team.toml", "--json"])
    assert typed.code == 0 and doc(typed)["run"]["run_id"] == "t-one", typed.text


def test_tf2_01_config_naming_no_file_is_refused(folder: Path) -> None:
    result = here(folder, ["--config", "no-such.toml", "where", "previous"])
    assert result.code == 1 and result.out == "", result.text
    assert result.err.startswith("error: ") and "no-such.toml" in result.err.splitlines()[0], result.err


def test_tf2_01_a_config_in_a_folder_above_is_not_read(folder: Path) -> None:
    below = folder / "sub"
    below.mkdir()
    tau2_copy(below, S)
    result = here(below, ["where", "previous", "--json"])
    assert result.code == 2 and result.out == "", result.text


# ---------- TF2-2: flags override ----------


def test_tf2_02_an_event_given_replaces_the_configs(folder: Path) -> None:
    data = doc(here(folder, ["where", "previous", "--event", "solved", "--json"]))
    assert data["events"] == ["solved"], data["events"]


def test_tf2_02_a_store_path_given_replaces_the_configs(folder: Path) -> None:
    store_of(folder / "other", [R("o-one", stamp(4, 9)), R("o-two", stamp(4, 10))])
    assert doc(here(folder, ["where", "latest", "--json"]))["run"]["run_id"] == T_PILOT
    data = doc(here(folder, ["where", "latest", "--store", "other", "--event", "fail", "--json"]))
    assert data["run"]["run_id"] == "o-two"


def test_tf2_02_a_store_name_given_is_the_configs_store_of_that_name_first(folder: Path) -> None:
    store_of(folder / "named-store", [R("n-one", stamp(5, 9))])
    # a folder named like the store name, holding another run: the config's name comes first
    store_of(folder / "imported", [R("decoy", stamp(5, 10))])
    write_config(folder, config_of(S, extra='\n[store.imported]\npath = "named-store"\n'))
    data = doc(here(folder, ["where", "latest", "--store", "imported", "--event", "fail", "--json"]))
    assert data["run"]["run_id"] == "n-one"
    # a name the config does not hold is a path
    data = doc(here(folder, ["where", "latest", "--store", "named-store", "--event", "fail", "--json"]))
    assert data["run"]["run_id"] == "n-one"


def test_tf2_02_the_ceilings_come_from_check_when_no_flag_gives_them(folder: Path) -> None:
    write_config(folder, config_of(S, extra="\n[check]\nmax_mde = 0.2\nmax_mde_hr = 1.5\n"))
    fix = here(folder, ["fix-check", "#3", "#2", "--inputs", "all", "--json"])
    assert fix.code == 0, fix.text
    assert doc(fix)["limits"]["max_mde"] == 0.2
    flagged = here(folder, ["fix-check", "#3", "#2", "--inputs", "all", "--max-mde", "0.3", "--json"])
    assert doc(flagged)["limits"]["max_mde"] == 0.3
    hr = here(folder, ["compare", "#3", "#2", "--json"])
    assert hr.code == 0, hr.text
    assert doc(hr)["comparison"]["max_mde_hr"] == 1.5


def test_tf2_02_without_a_ceiling_in_check_the_ceiling_is_still_required(folder: Path) -> None:
    for argv in (["fix-check", "#3", "#2", "--inputs", "all"], ["compare", "#3", "#2"]):
        result = here(folder, argv)
        assert result.code == 1 and result.out == "", result.text


# ---------- TF2-3: neither the config nor a flag ----------


@pytest.mark.parametrize("text,argv", [
    ('version = 1\n\n[store]\npath = "proofload-runs"\n', ["where", "previous"]),
    ('version = 1\n\n[events]\nfailed = ["unsolved"]\n', ["where", "previous"]),
    ('version = 1\n\n[events]\nfailed = ["unsolved"]\n', ["runs"]),
], ids=["no events", "no store", "runs with no store"])
def test_tf2_03_what_neither_gives_is_todays_refusal(folder: Path, text: str, argv: list[str]) -> None:
    write_config(folder, text)
    result = here(folder, argv)
    assert result.code == 2 and result.out == "", result.text
    lines = result.lines()
    assert lines[0].startswith("error: ") and lines[1:] == [f"  next: poisson-trace {argv[0]} --help"], result.err


# ---------- the import reads the config's store ----------


def test_tf2_27_an_import_with_no_store_given_writes_into_the_configs_store(tmp_path: Path) -> None:
    place = work(tmp_path)
    write_config(place, 'version = 1\n\n[store]\npath = "trace-store"\n\n[events]\nfailed = ["missed"]\n')
    argv = deepeval_import("unused", "he-a")
    at = argv.index("--store")
    result = import_here(place, argv[:at] + argv[at + 2 :])
    assert result.code == 0, result.text
    assert Store(place / "trace-store").runs() == ["he-a"]


def test_tf2_27_an_import_given_a_store_name_writes_into_that_store(tmp_path: Path) -> None:
    place = work(tmp_path)
    write_config(place, 'version = 1\n\n[store]\npath = "main"\n\n[store.imported]\npath = "from-tools"\n')
    result = import_here(place, deepeval_import("imported", "he-a"))
    assert result.code == 0, result.text
    assert Store(place / "from-tools").runs() == ["he-a"] and not (place / "imported").exists()


def test_tf2_27_an_import_reads_the_config_named_by_flag(tmp_path: Path) -> None:
    place = work(tmp_path)
    (place / "conf").mkdir()
    write_config(place / "conf", 'version = 1\n\n[store]\npath = "from-tools"\n', "imp.toml")
    argv = deepeval_import("unused", "he-a")
    at = argv.index("--store")
    result = import_here(place, [*argv[:at], *argv[at + 2 :], "--config", "conf/imp.toml"])
    assert result.code == 0, result.text
    assert Store(place / "conf" / "from-tools").runs() == ["he-a"]


def test_tf2_27_an_import_with_no_store_anywhere_is_todays_refusal(tmp_path: Path) -> None:
    place = work(tmp_path)
    argv = deepeval_import("unused", "he-a")
    at = argv.index("--store")
    result = import_here(place, argv[:at] + argv[at + 2 :])
    assert result.code == 2 and result.out == "", result.text
