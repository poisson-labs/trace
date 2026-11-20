"""Takes the pins of what main prints, builds and shows, for the unchanged tests in
``tests/test_weave_unchanged.py``: run on main (the commit ``weave_pins.MAIN`` names), from the
repository's root, with the package installed and no Weave reader in it::

    python tests/fixtures/weave-reader/make_main_pins.py

It writes ``tests/fixtures/weave-reader/main-pins.json``: for each invocation of
``weave_pins.pin_corpus()``, each step's exit code and the digests of its stdout and stderr,
whole; for each of ``weave_pins.CHANGED`` and ``weave_pins.INIT``, each step's exit code, stdout
and stderr as text; ``pages``, the digest of each file of the pages the tests' pages workspace
builds; and ``app``, each screen of the terminal app over that workspace, as text. Paths are
written ``<ROOT>`` and times ``<TIME>``.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TESTS))

from app_support import make_world, pages_pins  # noqa: E402
from weave_pins import CHANGED, INIT, MAIN, PINS, app_pins, digest_steps, pin_corpus, ran_case, ran_init  # noqa: E402


def main() -> None:
    from importlib.util import find_spec

    assert find_spec("poisson_trace.ingest.weave") is None, "take the pins on main, with no Weave reader in the install"
    pins: dict[str, object] = {"main": MAIN, "python": sys.version.split()[0], "piped": {}, "changed": {}, "init": {}, "pages": {}, "app": {}}
    for label, (place, kind, steps) in pin_corpus().items():
        with tempfile.TemporaryDirectory() as tmp:
            pins["piped"][label] = digest_steps(ran_case(Path(tmp), place, kind, steps))  # type: ignore[index]
        print(label, file=sys.stderr)
    for label, (place, kind, steps) in CHANGED.items():
        with tempfile.TemporaryDirectory() as tmp:
            pins["changed"][label] = [list(step) for step in ran_case(Path(tmp), place, kind, steps)]  # type: ignore[index]
    for label, (holds, steps) in INIT.items():
        with tempfile.TemporaryDirectory() as tmp:
            pins["init"][label] = [list(step) for step in ran_init(Path(tmp), holds, steps)]  # type: ignore[index]
    with tempfile.TemporaryDirectory() as tmp:
        pins["app"] = app_pins(make_world(Path(tmp)))
    with tempfile.TemporaryDirectory() as tmp:
        pins["pages"] = pages_pins(make_world(Path(tmp)))
    PINS.write_text(json.dumps(pins, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
