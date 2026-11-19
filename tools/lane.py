"""Run one lane of the suite, or the linter or the type checker, the way a change is held to.

    python tools/lane.py LANE [ARGUMENT ...]

LANE is one of

``pr``
    The pull-request lane: every test that is quick.
``slow``
    The long form of tests whose short form is in the pull-request lane.
``math``
    The statistics' slow checks against their references.
``lane_j``
    The one lane that reaches the package index.
``ruff``
    ``ruff check src tests``.
``mypy``
    ``mypy --strict``.

Everything runs with the Python this file is started with, so ``.venv/bin/python tools/lane.py
pr`` is the lane on that environment's Python and ``.venv311/bin/python tools/lane.py pr`` the
same lane on the other.

What it adds to the plain command:

- A test lane gets a temporary folder of its own (pytest's ``--basetemp``), and the folder is
  removed when the run ends, however it ends. Two runs never share one, and none is left behind.
- ``CI`` is taken out of the environment: Trace reads it as a reason to print plain text, and
  the tests pin what it prints without it.
- A test lane runs on ten workers, unless an argument gives ``-n`` itself. Lane J runs on one.
- ``mypy`` is given a cache named for the running Python (``.mypy_cache_312`` on Python 3.12),
  so one Python's cache is never read by another.

Every ARGUMENT is passed on to pytest, ruff or mypy as written: ``python tools/lane.py pr
tests/test_cli.py -k where`` runs the pull-request lane's tests of one file.

It exits with the exit code of the command it ran, and 2 when LANE is not one of the six. This
file needs the standard library alone.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Each test lane and the marks that select it (``pyproject.toml`` names the marks).
LANES = {
    "pr": "not math and not lane_j and not slow",
    "slow": "slow",
    "math": "math",
    "lane_j": "lane_j",
}
WORKERS = "10"


def mypy_cache() -> str:
    """The folder mypy keeps its cache in for the running Python."""
    return f".mypy_cache_{sys.version_info.major}{sys.version_info.minor}"


def command(lane: str, arguments: Sequence[str], basetemp: Path | None) -> list[str]:
    """The command ``lane`` runs. ``basetemp`` is the folder a test lane's files go under."""
    if lane == "ruff":
        return [sys.executable, "-m", "ruff", "check", "src", "tests", *arguments]
    if lane == "mypy":
        return [sys.executable, "-m", "mypy", "--strict", "--cache-dir", mypy_cache(), *arguments]
    words = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-m", LANES[lane]]
    if basetemp is not None:
        words += ["--basetemp", str(basetemp)]
    given = any(a == "-n" or a.startswith(("-n", "--numprocesses")) for a in arguments)
    if lane != "lane_j" and not given:
        words += ["-n", WORKERS]
    return [*words, *arguments]


def remove(folder: Path) -> None:
    """Remove ``folder`` and all it holds, a folder a test left read-only among them."""

    def writable(function: object, path: str, error: object) -> None:
        # a test of a folder that cannot be written leaves one behind when it is stopped midway
        try:
            os.chmod(os.path.dirname(path), 0o700)
            os.chmod(path, 0o700)
            os.rmdir(path) if os.path.isdir(path) else os.remove(path)
        except OSError:
            pass

    shutil.rmtree(folder, onerror=writable)
    shutil.rmtree(folder, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    words = list(sys.argv[1:] if argv is None else argv)
    known = [*LANES, "ruff", "mypy"]
    if not words or words[0] not in known:
        print(f"usage: python tools/lane.py LANE [ARGUMENT ...], LANE one of {', '.join(known)}",
              file=sys.stderr)
        return 2
    lane, arguments = words[0], words[1:]
    env = {name: value for name, value in os.environ.items() if name != "CI"}
    if lane not in LANES:
        return subprocess.run(command(lane, arguments, None), cwd=REPO, env=env).returncode
    # pytest empties the folder --basetemp names, so it is given one inside a folder made here
    made = Path(tempfile.mkdtemp(prefix="poisson-trace-lane-"))
    try:
        return subprocess.run(command(lane, arguments, made / "run"), cwd=REPO, env=env).returncode
    except KeyboardInterrupt:
        return 130
    finally:
        remove(made)


if __name__ == "__main__":
    sys.exit(main())
