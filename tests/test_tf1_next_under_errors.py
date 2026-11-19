"""TF1-18: the command to run goes on its own ``  next:`` line under an error, where there is one
(the look's rule 4).

A refusal or a wrong command line is one ``error:`` line, then, where there is a command that
moves the user on, one ``  next: <exact command>`` line, indented two spaces, and nothing else:
``poisson-trace runs`` for a run the store does not hold, the verb's own help for a wrong
command line, the forget command for a stale name. Each command runs as written."""

from __future__ import annotations

from pathlib import Path

import pytest

from tf0_support import chdir, trace, trace_import
from tf1_support import NAMES_FILE, T_B, shell_words, tau2_copy


def _error_and_next(result) -> str:  # type: ignore[no-untyped-def]
    """One error line and one next line under it; the next line's command."""
    assert result.out == "", result.out
    lines = [line for line in result.err.splitlines() if line.strip()]
    assert len(lines) == 2, result.err
    assert lines[0].startswith("error: ") and lines[1].startswith("  next: "), result.err
    return lines[1][len("  next: "):]


def _runs_as_written(folder: Path, command: str) -> None:
    words = shell_words(command)
    with chdir(folder):
        if words[0] == "poisson-trace":
            followed = trace(words[1:])
        else:
            assert words[0] in ("poisson-trace-import",), command
            followed = trace_import(words[1:])
    assert followed.code == 0, (command, followed.text)


@pytest.mark.parametrize("word", ["no such run", "965d", "#9", "latest:no-such-agent"])
def test_tf1_18_a_run_the_store_does_not_hold_points_at_the_listing(tmp_path: Path, word: str) -> None:
    tau2_copy(tmp_path)
    with chdir(tmp_path):
        result = trace(["where", word, "--store", "proofload-runs", "--event", "unsolved"])
    assert result.code == 1, result.text
    command = _error_and_next(result)
    assert shell_words(command)[:2] == ["poisson-trace", "runs"], command
    _runs_as_written(tmp_path, command)


@pytest.mark.parametrize("argv", [
    ["where", T_B, "--store", "proofload-runs"],
    ["where", T_B, "--event", "unsolved"],
    ["compare", T_B, "--store", "proofload-runs", "--event", "unsolved"],
    ["fix-check", T_B, "latest", "--store", "proofload-runs", "--event", "unsolved", "--top", "many"],
    ["changes", T_B, "latest", "--store", "proofload-runs", "--event", "unsolved", "--bogus"],
    ["runs"],
    ["name", "latest", "--store", "proofload-runs"],
], ids=["where", "where with no store", "compare", "fix-check", "changes", "runs", "name"])
def test_tf1_18_a_wrong_command_line_points_at_the_verbs_help(tmp_path: Path, argv: list[str]) -> None:
    tau2_copy(tmp_path)
    with chdir(tmp_path):
        result = trace(argv)
    assert result.code == 2, result.text
    command = _error_and_next(result)
    assert shell_words(command) == ["poisson-trace", argv[0], "--help"], command
    _runs_as_written(tmp_path, command)


def test_tf1_18_a_stale_name_points_at_forgetting_it(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    (store / NAMES_FILE).write_text('version = 1\n\n[names]\n"gone" = "20260101T000000Z-dead"\n', encoding="utf-8")
    with chdir(tmp_path):
        result = trace(["runs", "--store", "proofload-runs"])
    command = _error_and_next(result)
    _runs_as_written(tmp_path, command)
    with chdir(tmp_path):
        assert trace(["runs", "--store", "proofload-runs"]).code == 0


def test_tf1_18_a_refusal_with_no_command_to_give_stays_one_line(tmp_path: Path) -> None:
    tau2_copy(tmp_path)
    with chdir(tmp_path):
        result = trace(["compare", "#3", "#2", "--store", "proofload-runs", "--event", "unsolved"])
    assert result.code == 1 and result.out == "", result.text
    assert len([line for line in result.err.splitlines() if line.strip()]) == 1, result.err
