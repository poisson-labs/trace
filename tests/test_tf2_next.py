"""TF2-16 and TF2-17: with a config, every ``next:`` command still runs as written; without Prove,
``init`` points at the install line and touches no store (spec sections 9.4, 4.2 step 1 and 8.2;
handed on by TF1 Session A's yes/no 3; yes/nos 1 and 6).

In a folder whose ``trace.toml`` gives the store, the failures and both ceilings, each verb's
``next:`` line, copied into a shell in that folder, runs and exits 0, whichever of the store and
the events it carries. Without Prove, ``init`` ends in no traceback, names the install line
exactly once and as a command to run next, and writes nothing under any store."""

from __future__ import annotations

from pathlib import Path

import pytest

from tf0_support import INSTALL_PROVE
from tf1_support import next_line, shell_words, tau2_copy
from tf2_support import config_of, here, run, scratch_home, tree, work, write_config  # noqa: F401

S = "proofload-runs"
CEILINGS = "\n[check]\nmax_mde = 0.2\nmax_mde_hr = 1.5\n"


@pytest.mark.parametrize("argv", [
    ["where", "#2"], ["compare", "#3", "#2"], ["fix-check", "#3", "#2", "--inputs", "all"], ["changes", "#3", "#2"], ["runs"],
], ids=["where", "compare", "fix-check", "changes", "runs"])
def test_tf2_16_with_a_config_every_next_runs_as_written(tmp_path: Path, argv: list[str]) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, S)
    write_config(folder, config_of(S, extra=CEILINGS))
    result = here(folder, argv)
    assert result.code == 0, result.text
    words = shell_words(next_line(result))
    assert words[0] == "poisson-trace", words
    followed = here(folder, words[1:])
    assert followed.code == 0, (words, followed.text)


def test_tf2_17_init_without_prove_names_the_install_line_once_and_touches_no_store(tmp_path: Path) -> None:
    folder = work(tmp_path)
    store = tau2_copy(folder, S)
    before = tree(store)
    result = run(["init", "--yes"], cwd=folder, prove="absent")
    assert result.code in (0, 1) and "Traceback" not in result.text, result.text
    assert result.text.count(INSTALL_PROVE) == 1, result.text
    nexts = [line[len("next: "):] for line in result.out.splitlines() if line.startswith("next: ")]
    nexts += [line[len("  next: "):] for line in result.err.splitlines() if line.startswith("  next: ")]
    assert INSTALL_PROVE in nexts, result.text
    assert tree(store) == before
