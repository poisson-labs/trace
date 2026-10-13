"""TF2-26: with a config, a ``next:`` command leaves out what the config gave and carries what
was typed (spec section 9.4's bare commands; handed on by TF1 Session A's yes/no 3; yes/no 6,
pending: dropped on a no).

What came from ``trace.toml`` (the store, the failures) is not written into the next command,
which reads the same config when run in the same folder; what the user typed is carried as
typed: a store or an ``--event`` given beside the config, and ``--config PATH`` when the config
was named by flag. Each such command runs as written."""

from __future__ import annotations

from pathlib import Path

import pytest

from tf1_support import next_line, shell_words, tau2_copy
from tf2_support import config_of, here, scratch_home, work, write_config  # noqa: F401

S = "proofload-runs"
CEILINGS = "\n[check]\nmax_mde = 0.2\nmax_mde_hr = 1.5\n"


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    place = work(tmp_path)
    tau2_copy(place, S)
    write_config(place, config_of(S, extra=CEILINGS))
    return place


def _followed(folder: Path, argv: list[str]) -> list[str]:
    result = here(folder, argv)
    assert result.code == 0, result.text
    words = shell_words(next_line(result))
    assert words[0] == "poisson-trace", words
    again = here(folder, words[1:])
    assert again.code == 0, (words, again.text)
    return words


@pytest.mark.parametrize("argv", [
    ["where", "#2"], ["compare", "#3", "#2"], ["fix-check", "#3", "#2", "--inputs", "all"], ["changes", "#3", "#2"], ["runs"],
], ids=["where", "compare", "fix-check", "changes", "runs"])
def test_tf2_26_what_the_config_gave_is_left_out(folder: Path, argv: list[str]) -> None:
    words = _followed(folder, argv)
    assert "--store" not in words and "--event" not in words and "--config" not in words, words


def test_tf2_26_what_was_typed_is_carried(folder: Path) -> None:
    words = _followed(folder, ["changes", "#3", "#2", "--event", "solved", "--store", S])
    pairs = {(words[i], words[i + 1]) for i in range(len(words) - 1)}
    assert {("--event", "solved"), ("--store", S)} <= pairs, words


def test_tf2_26_a_config_named_by_flag_is_carried(folder: Path) -> None:
    (folder / "trace.toml").rename(folder / "team.toml")
    words = _followed(folder, ["changes", "#3", "#2", "--config", "team.toml"])
    pairs = {(words[i], words[i + 1]) for i in range(len(words) - 1)}
    assert ("--config", "team.toml") in pairs and "--store" not in words and "--event" not in words, words


def test_tf2_26_every_next_line_carries_the_config_named_by_flag(folder: Path) -> None:
    """The commands under a refusal and those of name and runs, too: the config named by flag, and
    not the store it gave."""
    (folder / "trace.toml").unlink()
    (folder / "conf").mkdir()
    (folder / "conf" / "team.toml").write_text(config_of("../proofload-runs", extra=CEILINGS), encoding="utf-8")
    flag = ["--config", "conf/team.toml"]
    commands = []
    for argv in (["name", "previous", "old re-run", *flag], ["runs", *flag]):
        result = here(folder, argv)
        assert result.code == 0, result.text
        commands.append(next_line(result))
    refused = here(folder, ["where", "no such run", *flag])
    assert refused.code == 1 and refused.lines()[1].startswith("  next: "), refused.text
    commands.append(refused.lines()[1][len("  next: "):])
    for command in commands:
        words = shell_words(command)
        pairs = {(words[i], words[i + 1]) for i in range(len(words) - 1)}
        assert ("--config", "conf/team.toml") in pairs and "--store" not in words, command
        again = here(folder, words[1:])
        assert again.code == 0, (command, again.text)
