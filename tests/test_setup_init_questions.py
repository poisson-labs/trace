"""TF2-10, TF2-11, TF2-13 and TF2-15 on a terminal: ``init``'s questions as a user answers them.

Stdin is a terminal and every answer is typed ahead, one line each; stdout and stderr are read
apart. The questions go to stderr, each with its default in brackets; stdout holds the summary
alone, its verdict line first. Several stores: a numbered list and ``Which results … [1]``; an
answer that is no store's number is asked again; Enter takes the default. One store: no
question. The failure question lists the outcomes the store's runs carry, each with its count of
episodes, and shows the default, every outcome that is not a word for success, which Enter
takes and the numbers typed replace. No store and result files: ``Import them…? [Y/n]``, then
the reader's questions in the order the import's flags read (the metric, the cut, its side when
the cut is a number, what identifies a case), each answered as its flag's value. Ctrl-C at any
question: exit 130, a ``stopped`` line, nothing written. The command the summary shows, run in a
copy of the folder as it was, writes the same file."""

from __future__ import annotations

from pathlib import Path

import pytest
from poisson_prove.store import Store

from look_support import VERDICT_LINE
from names_support import tau2_copy
from setup_support import (  # noqa: F401
    CONFIG, DEFAULT, SUCCESS_WORDS, choices, config, copy_tree, deepeval_file, here, last_default, number_of, numbered, numbers,
    outcome_runs, scratch_home, summary_command, tree, tty, two_stores, work,
)


def _done(result) -> None:  # type: ignore[no-untyped-def]
    assert result.code == 0, result.text
    first = result.out.splitlines()[0]
    assert VERDICT_LINE.match(first) and first.startswith("ok  "), result.out


def test_tf2_10_the_store_asked_for_is_the_store_written(tmp_path: Path) -> None:
    folder = work(tmp_path)
    two_stores(folder)
    pristine = copy_tree(folder, tmp_path / "pristine")
    result = tty(["init"], ["2", ""], cwd=folder)
    _done(result)
    assert number_of(result.err, "demo/store") == 2
    assert config(folder)["store"]["path"] == "demo/store"
    assert config(folder)["events"]["failed"] == ["fail"]
    # the same setup as one command names the store answered, not the first one found
    command = summary_command(result.out)
    assert here(pristine, command[1:]).code == 0
    assert (pristine / CONFIG).read_bytes() == (folder / CONFIG).read_bytes()


def test_tf2_10_the_store_question_defaults_to_the_first(tmp_path: Path) -> None:
    folder = work(tmp_path)
    two_stores(folder)
    result = tty(["init"], ["", ""], cwd=folder)
    _done(result)
    assert config(folder)["store"]["path"] == "proofload-runs"
    assert DEFAULT.findall(result.err)[0].strip() == "1", result.err


def test_tf2_10_an_answer_that_is_no_stores_number_is_asked_again(tmp_path: Path) -> None:
    folder = work(tmp_path)
    two_stores(folder)
    result = tty(["init"], ["9", "2", ""], cwd=folder)
    _done(result)
    assert config(folder)["store"]["path"] == "demo/store"
    assert config(folder)["events"]["failed"] == ["fail"]


def test_tf2_10_one_store_is_not_asked_about(tmp_path: Path) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    # the one answer goes to the failure question; a store question would take it instead
    result = tty(["init"], ["2"], cwd=folder)
    _done(result)
    picked = choices(result.err)[2][0]
    assert config(folder)["events"]["failed"] == [picked]


def test_tf2_11_the_failure_question_lists_the_outcomes_and_shows_the_default(tmp_path: Path) -> None:
    folder = work(tmp_path)
    outcome_runs(folder / "store", [("unsolved", "unsolved", "solved", "max_steps")] * 3)
    result = tty(["init"], [""], cwd=folder)
    _done(result)
    listed = choices(result.err)
    assert sorted(listed.values()) == [("max_steps", 3), ("solved", 3), ("unsolved", 6)], result.err
    default = {n for n, (word, _) in listed.items() if word not in SUCCESS_WORDS}
    assert numbers(last_default(result.err)) == default, result.err
    assert sorted(config(folder)["events"]["failed"]) == ["max_steps", "unsolved"]


def test_tf2_11_the_numbers_typed_replace_the_default(tmp_path: Path) -> None:
    folder = work(tmp_path)
    outcome_runs(folder / "store", [("unsolved", "solved", "max_steps", "app_error")])
    pristine = copy_tree(folder, tmp_path / "pristine")
    asked = tty(["init"], [], cwd=folder, interrupt=True)
    by_word = {word: n for n, (word, _) in choices(asked.err).items()}
    assert set(by_word) == {"unsolved", "solved", "max_steps", "app_error"}, asked.err
    assert not (folder / CONFIG).exists()
    # a number past the list and a word are asked again; the numbers then typed are taken
    chosen = tty(["init"], ["9", "unsolved", f"{by_word['solved']},{by_word['app_error']}"], cwd=folder)
    _done(chosen)
    assert sorted(config(folder)["events"]["failed"]) == ["app_error", "solved"]
    # the same setup as one command, in a copy of the folder as it was
    command = summary_command(chosen.out)
    assert here(pristine, command[1:]).code == 0
    assert (pristine / CONFIG).read_bytes() == (folder / CONFIG).read_bytes()


def test_tf2_11_newest_20_runs_are_asked_about(tmp_path: Path) -> None:
    folder = work(tmp_path)
    outcome_runs(folder / "store", [("ancient", "fail")] * 2 + [("fail", "ok")] * 20)
    result = tty(["init"], [""], cwd=folder)
    _done(result)
    assert {word for word, _ in choices(result.err).values()} == {"fail", "ok"}, result.err


# ---------- the import, asked ----------


def test_tf2_10_result_files_are_imported_from_the_answers(tmp_path: Path) -> None:
    source = work(tmp_path, "source")
    deepeval_file(source / "results" / "test_run_20261002_101500.json")
    deepeval_file(source / "results" / "test_run_20261002_111500.json", cases=20)
    pristine = copy_tree(source, tmp_path / "pristine")
    result = tty(["init"], ["y", "Tests Passed", "recorded", "name", ""], cwd=source)
    _done(result)
    store = Store(source / "trace-store")
    assert sorted(store.runs()) == ["test_run_20261002_101500", "test_run_20261002_111500"]
    assert config(source)["store"]["path"] == "trace-store" and config(source)["events"]["failed"] == ["missed"]
    assert "[Y/n]" in result.err, result.err
    # the same setup as one command, in a copy of the folder as it was
    command = summary_command(result.out)
    replay = copy_tree(pristine, tmp_path / "replay")
    assert here(replay, command[1:]).code == 0
    assert (replay / CONFIG).read_bytes() == (source / CONFIG).read_bytes()
    assert sorted(Store(replay / "trace-store").runs()) == sorted(store.runs())


def test_tf2_10_a_cut_given_as_a_number_is_asked_its_side(tmp_path: Path) -> None:
    folder = work(tmp_path)
    deepeval_file(folder / "results" / "test_run_20261002_101500.json")
    result = tty(["init"], ["", "Tests Passed", "0.5", "below", "name", ""], cwd=folder)
    _done(result)
    command = summary_command(result.out)
    assert "--below" in command and "0.5" in command, command


def test_tf2_10_no_to_the_import_writes_a_config_with_no_store(tmp_path: Path) -> None:
    folder = work(tmp_path)
    deepeval_file(folder / "results" / "test_run_20261002_101500.json")
    result = tty(["init"], ["n"], cwd=folder)
    _done(result)
    assert "store" not in config(folder) and not (folder / "trace-store").exists()


# ---------- Ctrl-C ----------


@pytest.mark.parametrize("at", ["the store question", "the failure question", "the import question", "a reader question", "the failure question after an import"])
def test_tf2_13_ctrl_c_at_any_question_writes_nothing(tmp_path: Path, at: str) -> None:
    folder = work(tmp_path)
    if at in ("the store question", "the failure question"):
        two_stores(folder)
    else:
        deepeval_file(folder / "results" / "test_run_20261002_101500.json")
    answers = {
        "the store question": [], "the failure question": ["1"], "the import question": [], "a reader question": ["y", "Tests Passed"],
        "the failure question after an import": ["y", "Tests Passed", "recorded", "name"],
    }[at]
    before = tree(folder)
    result = tty(["init"], answers, cwd=folder, interrupt=True)
    assert result.code == 130, result.text
    first = result.out.splitlines()[0]
    assert first.startswith("stopped  ") and VERDICT_LINE.match(first), result.out
    assert "Traceback" not in result.text
    assert tree(folder) == before
