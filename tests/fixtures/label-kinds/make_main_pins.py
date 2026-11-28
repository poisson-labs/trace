"""Takes the pins of what main prints, builds and holds, for the unchanged tests of the Prove label
kinds (``tests/test_label_kinds_unchanged.py``): run on main (the commit ``label_kinds_pins.MAIN`` names), from the
repository's root, with the package installed with its development extra::

    python tests/fixtures/label-kinds/make_main_pins.py

It writes ``tests/fixtures/label-kinds/main-pins.json`` (see ``label_kinds_pins``'s opening for what each section
holds). It refuses to run when the checkout is not main's tree as committed.

When the numbers Trace computes became the same bits on every platform, the outputs whose last
digits moved (their ``--json`` numbers, and in a few plain reports the order of rows that tie
exactly on p) were re-taken from that build, entry by entry, and each move was checked by
``tests/fixtures/portable/check_moves.py``; run on main, this maker gives those entries' earlier
digests.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TESTS))

from label_kinds_pins import CHANGED, MAIN, PINS, REPO, TEXT_FILES, file_digest, pin_corpus, pinned_paths, tracked  # noqa: E402
from docs_pins import app_pins, machine, ran_case, ran_every_tool, ran_init  # noqa: E402
from app_support import make_world, pages_pins  # noqa: E402
from recipe_pins import EVERY_LABEL, INIT, SETUP, SKILL, digest_text_steps  # noqa: E402


def main() -> None:
    head = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
    assert head == MAIN, f"take the pins on main {MAIN}, not {head}"
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    assert dirty == "", "take the pins on main's tree as committed"
    pins: dict[str, object] = {"main": MAIN, "python": sys.version.split()[0], "piped": {}, "init": {}, "setup": {}, "files": {},
                               "texts": {"piped": {}, "files": {}}}
    for label, (place, kind, steps) in pin_corpus().items():
        with tempfile.TemporaryDirectory() as tmp:
            got = ran_case(Path(tmp), place, kind, steps)
        pins["piped"][label] = digest_text_steps(got)  # type: ignore[index]
        if label in CHANGED:
            pins["texts"]["piped"][label] = [list(step) for step in got]  # type: ignore[index]
        print(label, file=sys.stderr)
    for label, (holds, steps) in INIT.items():
        with tempfile.TemporaryDirectory() as tmp:
            pins["init"][label] = digest_text_steps(ran_init(Path(tmp), holds, steps))  # type: ignore[index]
    with tempfile.TemporaryDirectory() as tmp:
        pins["init"][EVERY_LABEL] = digest_text_steps(ran_every_tool(Path(tmp)))  # type: ignore[index]
    for label, (place, kind, steps) in SETUP.items():
        with tempfile.TemporaryDirectory() as tmp:
            got = [(code, machine(out), machine(err)) for code, out, err in ran_case(Path(tmp), place, kind, steps)]
            pins["setup"][label] = digest_text_steps(got)  # type: ignore[index]
    with tempfile.TemporaryDirectory() as tmp:
        pins["skill"] = digest_text_steps(ran_case(Path(tmp), *SKILL))
    with tempfile.TemporaryDirectory() as tmp:
        pins["app"] = app_pins(make_world(Path(tmp)))
    with tempfile.TemporaryDirectory() as tmp:
        pins["pages"] = pages_pins(make_world(Path(tmp)))
    for name in pinned_paths(tracked()):
        pins["files"][name] = file_digest(REPO / name)  # type: ignore[index]
    for name in TEXT_FILES:
        pins["texts"]["files"][name] = (REPO / name).read_text(encoding="utf-8")  # type: ignore[index]
    pins["tracked"] = tracked()
    PINS.parent.mkdir(parents=True, exist_ok=True)
    PINS.write_text(json.dumps(pins, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
