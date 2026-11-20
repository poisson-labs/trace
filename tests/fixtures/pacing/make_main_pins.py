"""Takes the pins of what main prints, builds and shows, for the unchanged tests of the import's
pacing (``tests/test_pacing_unchanged.py``): run on main (the commit ``pacing_pins.MAIN``
names), from the repository's root, with the package installed and the writer as main has it::

    python tests/fixtures/pacing/make_main_pins.py

It writes ``tests/fixtures/pacing/main-pins.json``: for each invocation of
``pacing_pins.pin_corpus()`` and each case of ``pacing_pins.init_corpus()``, each step's exit
code and the digests of its stdout and stderr, whole; ``pages``, the digest of each file of the
pages the tests' pages workspace builds; and ``app``, each screen of the terminal app over that
workspace, as text. Paths are written ``<ROOT>`` and times ``<TIME>``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TESTS))

from pacing_pins import MAIN, PINS, app_pins, digest_steps, init_corpus, pin_corpus, ran_case, ran_init  # noqa: E402
from tf19_support import make_world, pages_pins  # noqa: E402


def main() -> None:
    head = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True, cwd=TESTS).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "src"], capture_output=True, text=True, cwd=TESTS).stdout
    assert head == MAIN and not dirty, f"take the pins on main {MAIN} with src as main has it (at {head}; {dirty!r})"
    pins: dict[str, object] = {"main": MAIN, "python": sys.version.split()[0], "piped": {}, "init": {}, "pages": {}, "app": {}}
    for label, (place, kind, steps) in pin_corpus().items():
        with tempfile.TemporaryDirectory() as tmp:
            pins["piped"][label] = digest_steps(ran_case(Path(tmp), place, kind, steps))  # type: ignore[index]
        print(label, file=sys.stderr)
    for label, (holds, steps) in init_corpus().items():
        with tempfile.TemporaryDirectory() as tmp:
            pins["init"][label] = digest_steps(ran_init(Path(tmp), holds, steps))  # type: ignore[index]
    with tempfile.TemporaryDirectory() as tmp:
        pins["app"] = app_pins(make_world(Path(tmp)))
    with tempfile.TemporaryDirectory() as tmp:
        pins["pages"] = pages_pins(make_world(Path(tmp)))
    PINS.write_text(json.dumps(pins, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
