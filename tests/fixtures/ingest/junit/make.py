"""Rebuild the JUnit reports: pytest's --junitxml on two small suites of Trace's own, each twice.

    python tests/fixtures/ingest/junit/make.py own DEST
    python tests/fixtures/ingest/junit/make.py replay DEST STORE

``own``: run from the root of a Trace checkout at the commit the provenance names, with Trace,
Prove and pytest importable. The suite is three of Trace's own test files (``SUITE``), run twice,
one run after the other, with nothing changed between them: ``trace-suite-1.xml``, then
``trace-suite-2.xml``.

``replay``: run from a folder holding ``replay_humaneval.py`` (beside this file) and a copy of
the committed HumanEval store at ``STORE``, with Prove and pytest importable. The suite replays
one stored run's outcomes (its docstring says how); it is run twice, against the first stored run
and then the second: ``humaneval-a.xml``, then ``humaneval-b.xml``. An empty config file is
given, so the folder is pytest's root and the class names are the suite's own.

pytest's own JUnit writer makes every report (``junit_family`` xunit2, its default); the one
plugin loaded, ``fixture_host.py`` beside this file, makes the report name its host
``localhost``. Nothing is edited after pytest writes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SUITE = ("tests/test_tf1_names.py", "tests/ingest/test_cut.py", "tests/ingest/test_rows.py")
RUNS = {"humaneval-a.xml": "20260905T185407Z-0313", "humaneval-b.xml": "20260905T195009Z-18ac"}
HERE = Path(__file__).resolve().parent


def _pytest(report: Path, args: list[str], env: dict[str, str]) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "fixture_host",
         f"--junitxml={report}", *args],
        env=env,
    )
    print(f"{report.name}: pytest exited {proc.returncode}")


def main() -> int:
    what, dest = sys.argv[1], Path(sys.argv[2]).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(HERE), os.environ.get("PYTHONPATH", "")]))
    if what == "own":
        for n in (1, 2):
            _pytest(dest / f"trace-suite-{n}.xml", list(SUITE), env)
    else:
        store = str(Path(sys.argv[3]).resolve())
        Path("empty.ini").write_text("[pytest]\n", encoding="utf-8")
        for name, run in RUNS.items():
            _pytest(dest / name, ["-c", "empty.ini", "--tb=short", "replay_humaneval.py"],
                    dict(env, REPLAY_STORE=store, REPLAY_RUN=run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
