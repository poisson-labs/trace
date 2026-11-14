"""Takes the pins of what main prints, builds and shows, for TF5's unchanged tests
(``tests/test_tf5_unchanged.py``): run on main (the commit ``tf5_pins.MAIN`` names), from the
repository's root, with the package installed and nothing of the docs pair's in the tree::

    python tests/fixtures/tf5/make_main_pins.py

It writes ``tests/fixtures/tf5/main-pins.json``: for each invocation of
``tf5_pins.pin_corpus()``, each step's exit code and the digests of its stdout and stderr,
whole; for each of ``tf5_pins.CHANGED``, ``tf5_pins.INIT`` and ``tf5_pins.READERS_SAID``, each
step's exit code, stdout and stderr as text (of ``doctor``, its readers line alone); ``setup``,
``doctor`` and ``init`` on a store as text, the machine's own words written out
(``tf5_pins.machine``); ``skill``, what ``init --agent --print`` prints; ``pages``, the digest of each file of the pages
TF19's workspace builds; and ``app``, each screen of the terminal app over that workspace, as
text. Paths are written ``<ROOT>`` and times ``<TIME>``.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TESTS))

from tf5_pins import CHANGED, EVERY_LABEL, INIT, MAIN, OLD_STORE, PINS, READERS_SAID, SETUP, SKILL, machine, app_pins, digest_steps, pin_corpus, ran_case, ran_every_tool, ran_init  # noqa: E402
from tf19_support import make_world, pages_pins  # noqa: E402


def main() -> None:
    assert not (TESTS.parent / "tools" / "docs_check.py").exists(), "take the pins on main, before the docs pair's files exist"
    pins: dict[str, object] = {"main": MAIN, "python": sys.version.split()[0], "piped": {}, "changed": {}, "init": {}, "readers": {},
                               "pages": {}, "app": {}}
    for label, (place, kind, steps) in pin_corpus().items():
        with tempfile.TemporaryDirectory() as tmp:
            got = ran_case(Path(tmp), place, kind, steps)
        if label.startswith("help"):
            assert not any(OLD_STORE in out + err for _, out, err in got), f"{label} names the old store folder and is not in CHANGED"
        pins["piped"][label] = digest_steps(got)  # type: ignore[index]
        print(label, file=sys.stderr)
    for label, (place, kind, steps) in CHANGED.items():
        with tempfile.TemporaryDirectory() as tmp:
            got = ran_case(Path(tmp), place, kind, steps)
        assert all(OLD_STORE in out for _, out, _ in got), f"{label} does not name the old store folder"
        pins["changed"][label] = [list(step) for step in got]  # type: ignore[index]
    for label, (place, kind, steps) in READERS_SAID.items():
        with tempfile.TemporaryDirectory() as tmp:
            got = ran_case(Path(tmp), place, kind, steps)
        if label == "doctor":  # its other lines name this machine's Python and folders: the readers line alone
            got = [(code, "".join(line for line in out.splitlines(keepends=True) if line.startswith("  readers")), err) for code, out, err in got]
        pins["readers"][label] = [list(step) for step in got]  # type: ignore[index]
    for label, (holds, steps) in INIT.items():
        with tempfile.TemporaryDirectory() as tmp:
            pins["init"][label] = [list(step) for step in ran_init(Path(tmp), holds, steps)]  # type: ignore[index]
    pins["setup"] = {}
    for label, (place, kind, steps) in SETUP.items():
        with tempfile.TemporaryDirectory() as tmp:
            pins["setup"][label] = [[code, machine(out), machine(err)] for code, out, err in ran_case(Path(tmp), place, kind, steps)]  # type: ignore[index]
    with tempfile.TemporaryDirectory() as tmp:
        pins["skill"] = [list(step) for step in ran_case(Path(tmp), *SKILL)]
    with tempfile.TemporaryDirectory() as tmp:
        pins["init"][EVERY_LABEL] = [list(step) for step in ran_every_tool(Path(tmp))]  # type: ignore[index]
    with tempfile.TemporaryDirectory() as tmp:
        pins["app"] = app_pins(make_world(Path(tmp)))
    with tempfile.TemporaryDirectory() as tmp:
        pins["pages"] = pages_pins(make_world(Path(tmp)))
    PINS.write_text(json.dumps(pins, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
