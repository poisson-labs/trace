"""Takes the pins of what main prints and builds, for TF19-17 and TF19-18
(``tests/test_tf19_unchanged.py``): run on main (the commit ``tf19_support.MAIN`` names), from the
repository's root, with the package installed::

    python tests/fixtures/tf19/make_main_pins.py

It writes ``tests/fixtures/tf19/main-pins.json``: for each invocation of
``tf19_support.pin_corpus()``, each step's exit code and the digests of its stdout and stderr,
whole; for each of ``tf19_support.CHANGED``, each step's exit code, stdout and stderr as text; and
``pages``, the digest of each file of the pages ``tf19_support.pages_pins`` builds over the app's
workspace, its times written ``<TIME>``. Paths are written ``<ROOT>``.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TESTS))

from tf0_support import REPO  # noqa: E402
from tf13_support import workspace  # noqa: E402
from tf19_support import CHANGED, MAIN, PINS, digest, make_world, normal, pages_pins, pin_corpus, run_steps  # noqa: E402


def case(tmp: Path, place: str, kind: str, steps: list[list[str]], whole: bool) -> list[list[object]]:
    work = workspace(tmp) if place == "work" else REPO
    got: list[list[object]] = []
    for ran in run_steps(work, place, kind, steps):
        out, err = normal(ran.out, work), normal(ran.err, work)
        got.append([ran.code, out, err] if whole else [ran.code, digest(out), digest(err)])
    return got


def main() -> None:
    pins: dict[str, object] = {"main": MAIN, "python": sys.version.split()[0], "piped": {}, "changed": {}, "pages": {}}
    for label, (place, kind, steps) in pin_corpus().items():
        with tempfile.TemporaryDirectory() as tmp:
            pins["piped"][label] = case(Path(tmp), place, kind, steps, False)  # type: ignore[index]
        print(label, file=sys.stderr)
    for label, (place, kind, steps) in CHANGED.items():
        with tempfile.TemporaryDirectory() as tmp:
            pins["changed"][label] = case(Path(tmp), place, kind, steps, True)  # type: ignore[index]
        print("changed", label, file=sys.stderr)
    with tempfile.TemporaryDirectory() as tmp:
        pins["pages"] = pages_pins(make_world(Path(tmp)))
    PINS.write_text(json.dumps(pins, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
