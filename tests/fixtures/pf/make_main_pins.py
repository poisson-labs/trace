"""Takes the pins of what main holds, for the Prove floor pair's unchanged tests
(``tests/test_pf_unchanged.py``): run from the repository's root, in a checkout that has main's
commit (the one ``pf_pins.MAIN`` names)::

    python tests/fixtures/pf/make_main_pins.py

It writes ``tests/fixtures/pf/main-pins.json`` (see ``pf_pins``'s opening for what each section
holds). Every file is read from that commit itself (``git show``), never from the checkout, so
the pins are main's whatever the working tree holds.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TESTS))

from pf_pins import MAIN, PINS, REPO, TEXTS, pinned_paths  # noqa: E402


def git(*argv: str) -> bytes:
    return subprocess.run(["git", *argv], cwd=REPO, capture_output=True, check=True).stdout


def main() -> None:
    commit = git("rev-parse", "--short=7", f"{MAIN}^{{commit}}").decode().strip()
    assert commit == MAIN, commit
    names = sorted(name for name in git("ls-tree", "-r", "-z", "--name-only", MAIN).decode("utf-8").split("\0") if name)
    pins: dict[str, object] = {"main": MAIN, "files": {}, "texts": {}, "tracked": names}
    for name in pinned_paths(names):
        pins["files"][name] = hashlib.sha256(git("show", f"{MAIN}:{name}")).hexdigest()  # type: ignore[index]
    for name in TEXTS:
        pins["texts"][name] = git("show", f"{MAIN}:{name}").decode("utf-8")  # type: ignore[index]
    PINS.parent.mkdir(parents=True, exist_ok=True)
    PINS.write_text(json.dumps(pins, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
