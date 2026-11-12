"""Takes the pins of what main prints, builds and shows, for TF24-66 to TF24-69
(``tests/test_tf24_unchanged.py``): run on main (the commit ``tf24_support.MAIN`` names), from the
repository's root, with the package installed::

    python tests/fixtures/tf24/make_main_pins.py

It writes ``tests/fixtures/tf24/main-pins.json``: for each invocation of
``tf24_support.pin_corpus()``, each step's exit code and the digests of its stdout and stderr,
whole (a case whose output holds the refusal another session is changing is listed under
``left_out`` instead); for each of ``tf24_support.CHANGED``, each step's exit code, stdout and
stderr as text; ``pages``, the digest of each file of the pages TF19's workspace builds; and
``app``, each screen of the terminal app over that workspace, as text. Paths are written
``<ROOT>`` and times ``<TIME>``.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TESTS))

from tf19_support import digest, make_world, pages_pins  # noqa: E402
from tf24_support import CHANGED, ELSEWHERE, MAIN, PINS, app_pins, pin_corpus, ran_case  # noqa: E402


def main() -> None:
    pins: dict[str, object] = {"main": MAIN, "python": sys.version.split()[0], "piped": {}, "left_out": [], "changed": {}, "pages": {}, "app": {}}
    for label, (place, kind, steps) in pin_corpus().items():
        with tempfile.TemporaryDirectory() as tmp:
            got = ran_case(Path(tmp), place, kind, steps)
        if any(ELSEWHERE in out + err for _, out, err in got):
            pins["left_out"].append(label)  # type: ignore[attr-defined]
        else:
            pins["piped"][label] = [[code, digest(out), digest(err)] for code, out, err in got]  # type: ignore[index]
        print(label, file=sys.stderr)
    for label, (place, kind, steps) in CHANGED.items():
        with tempfile.TemporaryDirectory() as tmp:
            pins["changed"][label] = [list(step) for step in ran_case(Path(tmp), place, kind, steps)]  # type: ignore[index]
    with tempfile.TemporaryDirectory() as tmp:
        world = make_world(Path(tmp))
        pins["app"] = app_pins(world)
    with tempfile.TemporaryDirectory() as tmp:
        pins["pages"] = pages_pins(make_world(Path(tmp)))
    PINS.write_text(json.dumps(pins, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
