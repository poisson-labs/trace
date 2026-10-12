"""What the independent read of this build found, each held by a test: both tools' files found;
Ctrl-C once the config is written; a config whose [events] table is there and empty; a store
folder named path; digits outside ASCII typed at a question; the stores offered to add; adding
a store to a config that names none; a config written into a store; line numbers after a
triple quote; a config that is a pipe; doctor's lines that no command mends; and the wrong
builds that passed every test before (success words matched exactly, a token variable's name,
--force in the command shown, a write that fails, imports counted as named, the day in a
DeepEval file's name)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tf0_support import VERDICT_LINE
from tf1_support import shell_words, tau2_copy
from tf2_support import (  # noqa: F401
    CONFIG, R, choices, config, config_of, copy_tree, deepeval_file, doc, here, init_yes, numbered, outcome_runs,
    ragas_file, refused, run, scratch_home, stamp, store_of, tree, tty, two_stores, work, write_config,
)

DEEPEVAL_ANSWERS = ["--metric", "Tests Passed", "--cut", "recorded", "--case", "name"]


def test_both_tools_files_are_refused_before_any_question(tmp_path: Path) -> None:
    """One set of the import's answers cannot fit both tools: init says so before it asks to
    import, and writes nothing; --no-import writes the config with no store."""
    folder = work(tmp_path)
    deepeval_file(folder / "results" / "test_run_20261002_101500.json")
    ragas_file(folder / "scores" / "base.jsonl")
    before = tree(folder)
    result = tty(["init"], [], cwd=folder, timeout=60)
    refused(result)
    assert "[Y/n]" not in result.err and tree(folder) == before, result.err
    assert init_yes(folder, "--no-import").code == 0 and "store" not in config(folder)


def test_ctrl_c_once_the_config_is_written_says_it_was(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from poisson_trace import setup

    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")

    def stop(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(setup, "_summary", stop)
    result = init_yes(folder)
    assert result.code == 130, result.text
    first = result.out.splitlines()[0]
    assert VERDICT_LINE.match(first) and first.startswith("stopped  ") and "nothing was written" not in first, first
    assert CONFIG in first and (folder / CONFIG).exists()


def test_a_config_with_an_empty_events_table_is_completed_under_it(tmp_path: Path) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    mine = write_config(folder, 'version = 1\n\n[store]\npath = "proofload-runs"\n\n[events]\n# fill in later\n')
    before = mine.read_text(encoding="utf-8").splitlines()
    assert init_yes(folder).code == 0
    after = mine.read_text(encoding="utf-8").splitlines()
    kept = iter(after)
    assert all(line in kept for line in before), after
    assert config(folder)["events"]["failed"] == ["unsolved"]


def test_a_digit_outside_ascii_at_a_question_is_asked_again(tmp_path: Path) -> None:
    folder = work(tmp_path)
    two_stores(folder)
    result = tty(["init"], ["²", "2", "1,²", ""], cwd=folder)
    assert result.code == 0, result.text
    assert config(folder)["store"]["path"] == "demo/store" and config(folder)["events"]["failed"] == ["fail"]


def test_every_store_offered_to_add_is_added_by_the_command_shown(tmp_path: Path) -> None:
    """Two more stores share a folder's name, one folder's name is no store name, one opens with
    a dash: each command offered runs as written, and the others are not offered as commands."""
    folder = work(tmp_path)
    tau2_copy(folder, "a-main")
    for place in ("a/runs", "b/runs", "c/my runs", "d/-dash"):
        store_of(folder / place, [R("r1", stamp(5, 9))])
    result = init_yes(folder)
    assert result.code == 0 and config(folder)["store"]["path"] == "a-main", result.text
    offered = [shell_words(line[line.find("poisson-trace init"):]) for line in result.out.splitlines() if "poisson-trace init --add-store" in line]
    assert len(offered) == 2, result.out
    for words in offered:
        added = here(folder, words[1:])
        assert added.code == 0, (words, added.text)
    assert len(config(folder)["store"]) == 3, config(folder)


def test_a_store_added_to_a_config_that_names_none_is_the_one_every_verb_reads(tmp_path: Path) -> None:
    folder = work(tmp_path)
    assert init_yes(folder).code == 0
    tau2_copy(folder, "runs")
    assert here(folder, ["init", "--add-store", "runs"]).code == 0
    assert config(folder)["store"]["path"] == "runs"
    assert here(folder, ["runs"]).code == 0


@pytest.mark.parametrize("inside", ["a store", "a run"])
def test_init_writes_no_config_into_a_store_or_a_run(tmp_path: Path, inside: str) -> None:
    folder = work(tmp_path)
    store = tau2_copy(folder, "runs")
    place = store if inside == "a store" else next(p for p in store.iterdir() if p.is_dir())
    before = tree(folder)
    refused(init_yes(place))
    assert tree(folder) == before


@pytest.mark.parametrize("text,line", [
    ('version = 1\n[store]\npath = "proofload-runs" # see """notes\n[events]\nfaild = ["unsolved"]\n', 5),
    ('version = 1\n[store]\npath = "proofload-runs"\n[names]\nfrom = "target"\n[check]\nmax_md = "it\'\'\'s"\n', 7),
    ('version = 1\n[store]\npath = """\n[events]\nfailed = 2\nx"""\n[events]\nfailed = []\n', 8),
], ids=["a triple quote in a comment", "a triple quote in a string", "lines inside a string of several lines"])
def test_a_fault_after_a_triple_quote_names_its_own_line(tmp_path: Path, text: str, line: int) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    write_config(folder, text)
    error = refused(here(folder, ["runs"]))
    assert f"trace.toml line {line}:" in error, error


def test_a_config_that_is_a_pipe_is_refused_without_waiting(tmp_path: Path) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    os.mkfifo(folder / CONFIG)
    refused(run(["runs", "--store", "proofload-runs"], cwd=folder, timeout=60))
    result = run(["doctor"], cwd=folder, timeout=60)
    assert result.code == 4, result.text


def test_doctor_names_no_command_where_none_mends_it(tmp_path: Path) -> None:
    """A config that is a folder, and runs that carry no outcome, have no command that makes
    doctor ready; a named store whose runs carry none of the failures is noted, not failed."""
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    (folder / CONFIG).mkdir()
    data = doc(here(folder, ["doctor", "--json"]))
    item = next(c for c in data["checks"] if c["name"] == "config")
    assert item["ok"] is False and item["next"] is None, item
    (folder / CONFIG).rmdir()
    outcome_runs(folder / "silent", [(None, None)])
    write_config(folder, 'version = 1\n\n[store]\npath = "silent"\n')
    item = next(c for c in doc(here(folder, ["doctor", "--json"]))["checks"] if c["name"] == "config")
    assert item["ok"] is False and item["next"] is None, item
    store_of(folder / "other", [R("o1", stamp(5, 9))])
    write_config(folder, config_of("proofload-runs", extra='\n[store.other]\npath = "other"\n'))
    result = here(folder, ["doctor", "--json"])
    assert result.code == 0, result.text
    assert "--store other" in next(c for c in doc(result)["checks"] if c["name"] == "config")["line"]


# ---------- the wrong builds that passed every test before ----------


def test_the_words_for_success_are_matched_exactly(tmp_path: Path) -> None:
    folder = work(tmp_path)
    outcome_runs(folder / "store", [("Solved", "PASSED", "solved", "boom")])
    assert init_yes(folder).code == 0
    assert sorted(config(folder)["events"]["failed"]) == ["PASSED", "Solved", "boom"]


def test_an_upload_token_name_is_a_variable_name(tmp_path: Path) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    write_config(folder, config_of("proofload-runs", extra='\n[upload]\ntoken_env = "MY TOKEN"\n'))
    assert "line 10" in refused(here(folder, ["runs"]))


def test_the_command_shown_replays_a_setup_that_replaced_a_config(tmp_path: Path) -> None:
    source = work(tmp_path, "source")
    tau2_copy(source, "proofload-runs")
    write_config(source, config_of("proofload-runs", ("solved",)))
    pristine = copy_tree(source, tmp_path / "pristine")
    command = doc(init_yes(source, "--force", "--json"))["equivalent_command"]
    assert here(pristine, command[1:]).code == 0
    assert (pristine / CONFIG).read_bytes() == (source / CONFIG).read_bytes()


def test_a_write_that_fails_leaves_the_config_as_it_was(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    mine = write_config(folder, config_of("proofload-runs", ("solved",), "\n# mine\n"))
    before = mine.read_bytes()

    def full(*args: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", full)
    refused(init_yes(folder, "--force"))
    assert mine.read_bytes() == before
    assert [p.name for p in folder.iterdir() if p.is_file()] == [CONFIG]


def test_named_counts_the_runs_an_import_named(tmp_path: Path) -> None:
    folder = work(tmp_path)
    deepeval_file(folder / "results" / "test_run_20261002_101500.json")
    deepeval_file(folder / "results" / "test_run_20261002_111500.json", cases=20)
    data = doc(init_yes(folder, *DEEPEVAL_ANSWERS, "--json"))
    assert data["named"] == 2, data


def test_a_deepeval_folder_is_listed_with_the_day_its_files_name(tmp_path: Path) -> None:
    folder = work(tmp_path)
    deepeval_file(folder / "results" / "test_run_20250105_101500.json")
    result = init_yes(folder, "--no-import")
    line = next(v for v in numbered(result.err).values() if v.startswith("results"))
    assert "2025-01-05" in line, line


@pytest.mark.parametrize("case", ["the same store twice", "no record Prove reads"])
def test_two_more_stores_init_refuses(tmp_path: Path, case: str) -> None:
    folder = work(tmp_path)
    store = tau2_copy(folder, "runs")
    if case == "the same store twice":
        argv = ["--store", "runs", "--store", "./runs"]
    else:
        for manifest in store.glob("*/manifest.json"):
            manifest.write_text("{ not a record", encoding="utf-8")
        argv = ["--store", "runs"]
    before = tree(folder)
    refused(init_yes(folder, *argv))
    assert tree(folder) == before
