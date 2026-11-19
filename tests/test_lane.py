"""``tools/lane.py``, the one command that runs a lane, the linter or the type checker, and the two
settings of ``pyproject.toml`` that keep a lane's temporary files from filling the disk.

- A lane is run with the marks ``pyproject.toml`` names for it, on ten workers unless the call says how many,
  and lane J on one.
- A test lane gets a temporary folder of its own, removed when the run ends; ``CI`` is not in its environment.
- ``mypy`` gets a cache named for the running Python, so one Python never reads another's.
- A word that is no lane is a wrong command line: exit 2, the usage on stderr, nothing run.
- ``pyproject.toml`` has pytest remove a passed test's folder at once and keep a failed test's from the last
  run alone.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parent.parent
LANE = REPO / "tools" / "lane.py"


def _lane() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lane", LANE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_lane_is_run_by_its_marks_on_ten_workers_in_a_folder_of_its_own(tmp_path: Path) -> None:
    lane = _lane()
    marks = {"pr": "not math and not lane_j and not slow", "slow": "slow", "math": "math", "lane_j": "lane_j"}
    assert marks == lane.LANES
    for name, mark in marks.items():
        words = lane.command(name, ["tests/test_cli.py", "-k", "where"], tmp_path / "run")
        assert words[:3] == [sys.executable, "-m", "pytest"]
        assert words[words.index("-m", 3) + 1] == mark
        assert words[words.index("--basetemp") + 1] == str(tmp_path / "run")
        assert words[-3:] == ["tests/test_cli.py", "-k", "where"]
        assert ("-n" in words) == (name != "lane_j"), words
    assert lane.command("pr", [], tmp_path)[-2:] == ["-n", "10"]
    for given in (["-n", "4"], ["-n4"], ["--numprocesses=4"]):
        assert lane.command("pr", given, tmp_path).count("-n") == given.count("-n"), given


def test_the_linter_and_the_type_checker_are_the_lines_a_change_is_held_to() -> None:
    lane = _lane()
    assert lane.command("ruff", [], None) == [sys.executable, "-m", "ruff", "check", "src", "tests"]
    cache = f".mypy_cache_{sys.version_info.major}{sys.version_info.minor}"
    assert lane.command("mypy", [], None) == [sys.executable, "-m", "mypy", "--strict", "--cache-dir", cache]


def test_a_word_that_is_no_lane_is_a_wrong_command_line() -> None:
    for words in ([], ["everything"], ["-n", "4"]):
        ran = subprocess.run([sys.executable, str(LANE), *words], capture_output=True, text=True, timeout=60)
        assert (ran.returncode, ran.stdout) == (2, ""), ran
        assert ran.stderr.startswith("usage: python tools/lane.py LANE") and "pr, slow, math, lane_j, ruff, mypy" in ran.stderr


def test_a_run_has_a_temporary_folder_of_its_own_gone_when_it_ends_and_no_ci(tmp_path: Path) -> None:
    """A real run of the pull-request lane over one test written here: the test notes its temporary folder and
    whether ``CI`` was set, and fails on purpose the second time, since a failed run's folder goes too."""
    probe = tmp_path / "probe" / "test_probe.py"
    probe.parent.mkdir()
    probe.write_text(
        "import os\nfrom pathlib import Path\n\n"
        "def test_probe(tmp_path):\n"
        "    notes = Path(os.environ['PROBE_NOTES'])\n"
        "    notes.write_text(f\"{tmp_path}\\n{'CI' in os.environ}\\n\", encoding='utf-8')\n"
        "    assert os.environ.get('PROBE_FAILS') != 'yes'\n", encoding="utf-8")
    made = tmp_path / "tmp"
    made.mkdir()
    for fails, code in (("no", 0), ("yes", 1)):
        notes = tmp_path / f"notes-{fails}.txt"
        env = dict(os.environ, CI="true", TMPDIR=str(made), PROBE_NOTES=str(notes), PROBE_FAILS=fails)
        ran = subprocess.run([sys.executable, str(LANE), "pr", "-n", "0", "-q", "-p", "no:cacheprovider", "--rootdir",
                              str(probe.parent), "-c", os.devnull, str(probe)],
                             capture_output=True, text=True, env=env, timeout=300)
        assert ran.returncode == code, ran.stdout + ran.stderr
        folder, ci = notes.read_text(encoding="utf-8").splitlines()
        assert ci == "False", "CI reached the lane"
        assert Path(folder).is_relative_to(made.resolve()) or Path(folder).is_relative_to(made), folder
        assert "poisson-trace-lane-" in folder
        assert not Path(folder).exists() and list(made.iterdir()) == [], list(made.iterdir())


def test_pytest_removes_a_passed_tests_folder_and_keeps_one_failed_run() -> None:
    settings = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]
    assert settings["tmp_path_retention_policy"] == "failed"
    assert settings["tmp_path_retention_count"] == 1
