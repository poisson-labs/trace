"""scipy is off the number paths when the commands run.

Each of ``fix-check --json``, ``compare --json``, ``changes --json`` and ``fix-check --measures
--json`` runs on the suite's workspace (``api_support.workspace``: the committed Prove store among
its folders) twice, each in a fresh interpreter: once as installed, and once with scipy made
unimportable (``sys.modules['scipy'] = None`` before Trace is imported). The two give the same
exit code and the same bytes on stdout and stderr.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from api_support import VERBS_ARGV, workspace

CASES = ("fix-check", "compare", "changes", "fix-check measures")
RUN = "import sys\n{block}from poisson_trace.cli import main\nraise SystemExit(main(sys.argv[1:]))\n"
BLOCK = "sys.modules['scipy'] = None\n"


def _ran(work: Path, argv: list[str], block: bool) -> tuple[int, str, str]:
    env = {k: v for k, v in os.environ.items() if k != "CI"}
    done = subprocess.run([sys.executable, "-c", RUN.format(block=BLOCK if block else ""), *argv], cwd=work, env=env,
                          capture_output=True, text=True, timeout=600)
    return done.returncode, done.stdout, done.stderr


@pytest.mark.parametrize("case", CASES)
def test_each_verb_gives_the_same_bytes_with_scipy_unimportable(tmp_path: Path, case: str) -> None:
    work = workspace(tmp_path)
    argv = [*VERBS_ARGV[case], "--json"]
    with_scipy = _ran(work, argv, block=False)
    assert with_scipy[0] == 0, with_scipy[2]
    without = _ran(work, argv, block=True)
    assert without[0] == with_scipy[0], f"exit {without[0]} with scipy unimportable:\n{without[2][-3000:]}"
    assert without[2] == with_scipy[2]
    assert without[1] == with_scipy[1], "stdout differs with scipy unimportable"
