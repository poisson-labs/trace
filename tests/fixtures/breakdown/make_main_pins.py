"""Takes the pins of what main prints before the failure breakdown, for the tests that hold every
other output to it (``tests/test_bd_unchanged.py``): run on main (the commit
``breakdown_support.MAIN`` names), from the repository's root, with the package installed::

    python tests/fixtures/breakdown/make_main_pins.py

It writes ``tests/fixtures/breakdown/main-pins.json``: each piped invocation's exit code and the
digests of its stdout (with the failure breakdown, the continuous-measures section and
``failure_taxonomy_diff`` taken out, which on main takes out only the measures section) and its
stderr; and each terminal invocation's exit code and the digests of the bytes its two terminals
received, pretty and ``--plain``, at each width. Paths are written ``<ROOT>``.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TESTS))

from breakdown_support import (  # noqa: E402
    MAIN, PINS, PTY_WIDTHS, normal, outside_new_parts, piped_corpus, pty_corpus,
)
from tf0_support import REPO  # noqa: E402
from tf9_support import run as pty_run  # noqa: E402
from tf13_support import cli, cli_import, workspace  # noqa: E402
from tf0_support import chdir  # noqa: E402


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def piped_case(tmp: Path, place: str, kind: str, steps: list[list[str]]) -> list[list[object]]:
    got: list[list[object]] = []
    work = workspace(tmp) if place == "work" else REPO
    for step in steps:
        if place == "work":
            ran = (cli if kind == "trace" else cli_import)(work, step)
        else:
            from tf0_support import trace

            with chdir(REPO):
                ran = trace(step)
        out = normal(outside_new_parts(step if kind == "trace" else ["import", *step], ran.out), work)
        got.append([ran.code, digest(out), digest(normal(ran.err, work))])
    return got


def pty_case(tmp: Path, argv: list[str]) -> dict[str, list[object]]:
    work = workspace(tmp)
    home = tmp / "home"
    home.mkdir()
    got: dict[str, list[object]] = {}
    for cols in PTY_WIDTHS:
        for rendering, extra in (("pretty", []), ("plain", ["--plain"])):
            ran = pty_run([*argv, *extra], cwd=work, home=home, cols=cols)
            got[f"{cols} {rendering}"] = [ran.code, digest(normal(ran.out, work)), digest(normal(ran.err, work))]
    return got


def main() -> None:
    pins: dict[str, object] = {"main": MAIN, "piped": {}, "pty": {}}
    for label, (place, kind, steps) in piped_corpus().items():
        with tempfile.TemporaryDirectory() as tmp:
            pins["piped"][label] = piped_case(Path(tmp), place, kind, steps)  # type: ignore[index]
        print(label, file=sys.stderr)
    for label, argv in pty_corpus().items():
        with tempfile.TemporaryDirectory() as tmp:
            pins["pty"][label] = pty_case(Path(tmp), argv)  # type: ignore[index]
        print("pty", label, file=sys.stderr)
    PINS.write_text(json.dumps(pins, indent=1, sort_keys=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
