"""TF1-17: a ``next:`` command runs as written (spec section 9.4 and the look's rule 13: ``next:
<exact command>``; pending yes/no 3).

Until a config gives the store and the events (``trace.toml``, a later pair), the command
carries the ``--store`` and the ``--event`` names given, so that copied into a shell in the same
folder it is never a wrong command line. The one thing it may lack is the ceiling a comparison
asks for, which has no default and is the user's to choose."""

from __future__ import annotations

from pathlib import Path

import pytest

from tf0_support import chdir, trace
from tf1_support import T_A, T_B, next_line, shell_words, tau2_copy


def _ran(argv: list[str]):  # type: ignore[no-untyped-def]
    result = trace(argv)
    assert result.code == 0, result.text
    return result


@pytest.mark.parametrize("verb", ["where", "compare", "fix-check", "changes", "runs"])
def test_tf1_17_the_next_command_is_never_a_wrong_command_line(tmp_path: Path, verb: str) -> None:
    store = tau2_copy(tmp_path / "work", "proofload-runs")
    with chdir(tmp_path / "work"):
        argv = {
            "where": ["where", T_B, "--store", "proofload-runs", "--event", "unsolved"],
            "compare": ["compare", T_A, T_B, "--store", "proofload-runs", "--event", "unsolved", "--max-mde-hr", "1.5"],
            "fix-check": ["fix-check", T_A, T_B, "--store", "proofload-runs", "--event", "unsolved", "--inputs", "all", "--max-mde", "0.2"],
            "changes": ["changes", T_A, T_B, "--store", "proofload-runs", "--event", "unsolved"],
            "runs": ["runs", "--store", "proofload-runs", "--event", "unsolved"],
        }[verb]
        command = next_line(_ran(argv))
        words = shell_words(command)
        assert words[0] == "poisson-trace", command
        followed = trace(words[1:])
    assert followed.code != 2, (command, followed.err)
    assert followed.code in (0, 1), (command, followed.text)
    if followed.code == 1:
        # the one thing it may lack is the ceiling, which has no default
        assert "--max-mde" in followed.err, (command, followed.err)
    assert store.exists()




def test_tf1_17_every_event_given_is_carried(tmp_path: Path) -> None:
    import shutil

    from conftest import FIXTURES
    from tf0_support import HE_A, HE_B

    shutil.copytree(FIXTURES / "humaneval", tmp_path / "he")
    with chdir(tmp_path):
        command = next_line(_ran(["changes", HE_A, HE_B, "--store", "he", "--event", "failed_assertion", "--event", "crashed"]))
        words = shell_words(command)
        followed = trace([*words[1:], "--max-mde", "0.05"])
    pairs = {(words[i], words[i + 1]) for i in range(len(words) - 1)}
    assert {("--event", "failed_assertion"), ("--event", "crashed"), ("--store", "he")} <= pairs, command
    assert followed.code == 0, (command, followed.text)
