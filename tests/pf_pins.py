"""What main holds, pinned for the tests of the Prove floor: main as it stood with the exact pin
of Prove 0.1.3 still in place. Not collected. ``fixtures/pf/make_main_pins.py`` takes the pins
with this module alone.

What is pinned, each as that main holds it:

``files``, ``tracked``
    The digest of every file of the repository a user is given or reads (TF20's list:
    ``tf20_pins.pinned_paths``), and the path of every file main tracks.
``texts``
    Main's text of each file the floor changes outside the package (``TEXTS``), so that a test
    can say what moved in it without the repository's history, and so that an earlier test of
    what the file held goes on reading the file as main held it (``main_text``).

What main prints is not pinned again. Every other set of pins of what main prints holds on any
Prove at or above the floor once Prove's version is written as those pins hold it
(``pin_support.as_pinned``), and the Prove label kinds' pins (``test_pl_unchanged.py``) are the
newest of them: they hold every output of this main but the refusals the floor moves, which
``test_pf_floor.py`` and ``test_pf_store.py`` hold word for word.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tf20_pins import file_digest, pinned_paths as tf20_pinned, tracked

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
PF = TESTS / "fixtures" / "pf"
PINS = PF / "main-pins.json"
MAIN = "4bb4b95"

#: The files outside the package whose text main's pins hold, each with a test of what moves in it.
TEXTS = ("pyproject.toml", ".github/release/lanes-3.11.txt", ".github/release/lanes-3.12.txt", ".github/workflows/ci.yml",
         ".github/workflows/release.yml", "README.md", "CONTRIBUTING.md", "docs/setup-with-your-agent.md")


def pinned_paths(names: list[str]) -> list[str]:
    return [n for n in tf20_pinned(names) if not n.startswith("tests/fixtures/pf/")]


def pins() -> dict[str, Any]:
    held: dict[str, Any] = json.loads(PINS.read_text(encoding="utf-8"))
    return held


def main_text(name: str) -> str:
    """A file of ``TEXTS`` as the pinned main holds it, checked against the digest pinned beside it."""
    import hashlib

    held = pins()
    text = str(held["texts"][name])
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == held["files"][name], f"the pinned text of {name} is not main's file"
    return text


__all__ = ["MAIN", "PINS", "REPO", "TEXTS", "file_digest", "main_text", "pinned_paths", "pins", "tracked"]
