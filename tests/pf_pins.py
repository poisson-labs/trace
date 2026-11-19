"""What main holds, pinned for the Prove floor pair: main 4bb4b95, the exact pin of Prove 0.1.3
still in place. Not collected. ``fixtures/pf/make_main_pins.py`` takes the pins with this module
alone.

What is pinned, each as main 4bb4b95 holds it:

``files``, ``tracked``
    The digest of every file of the repository a user is given or reads (TF20's list:
    ``tf20_pins.pinned_paths``), and the path of every file main tracks.
``texts``
    Main's text of each file this pair changes outside the package (``TEXTS``), so that a test
    can say what moved in it without the repository's history, and so that an earlier pair's
    test of what that pair gave the file goes on reading the file as main held it
    (``main_text``; TF20-87 to TF20-90).

What main prints is not pinned again. Every earlier pair's pins of what main prints hold on any
Prove at or above the floor once Prove's version is written as those pins hold it
(``pin_support.as_pinned``, PV-5), and the Prove label kinds pair's (``test_pl_unchanged.py``)
are the newest of them: they hold every output of main 4bb4b95 but the refusals this pair moves,
which ``test_pf_floor.py`` and ``test_pf_store.py`` hold word for word.

``BUILT`` is every file the pair's build may change: the floor's declaration, the code that reads
it and refuses on it, the store checks, the release check and the workflows, and the three pages
that say which Prove Trace reads. ``OURS`` is every file outside ``tests/`` or among the
fixtures that this pair's own frozen commits change or add, each held at the digest it was
frozen with. Every other file is main's (PF-90).
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

#: The files the build may change (Session B), and nothing else.
BUILT = (
    "pyproject.toml",
    ".github/release/lanes-3.11.txt", ".github/release/lanes-3.12.txt", ".github/release/release_check.py",
    ".github/workflows/ci.yml", ".github/workflows/release.yml",
    "README.md", "CONTRIBUTING.md", "docs/setup-with-your-agent.md",
    "src/poisson_trace/look.py", "src/poisson_trace/doctor.py", "src/poisson_trace/core.py", "src/poisson_trace/saved.py",
    "src/poisson_trace/names.py", "src/poisson_trace/setup.py", "src/poisson_trace/commands.py", "src/poisson_trace/api.py",
    "src/poisson_trace/ingest/importing.py", "src/poisson_trace/ingest/writer.py",
)
#: The files of ``BUILT`` whose text main's pins hold, each with a test of what moves in it (PF-91 to PF-96).
TEXTS = ("pyproject.toml", ".github/release/lanes-3.11.txt", ".github/release/lanes-3.12.txt", ".github/workflows/ci.yml",
         ".github/workflows/release.yml", "README.md", "CONTRIBUTING.md", "docs/setup-with-your-agent.md")
#: The fixture store this pair adds, made by the floor (``fixtures/prove-stores/make.py``).
FLOOR_STORE = "tests/fixtures/prove-stores/prove-0.4.0/"
#: The files this pair's frozen commits change or add among those main's pins hold, and the
#: digest each was frozen with: the docs checker's second ask for a pseudo-terminal (MF-2), and
#: the recipe, the provenance and the list of digests of the Prove stores, which gain the floor's.
OURS = {
    "tools/docs_check.py": "bfe03a6652cbb31ae0382c51d6cf0e2618a61bc0b76e01de11a882157ca5c726",
    "tests/fixtures/prove-stores/make.py": "7c8f464545b4395992167111602305a30affb876285553b41873cce859bbb8bc",
    "tests/fixtures/prove-stores/PROVENANCE.md": "601c997daf3e64a25ec59f868793cd3ffc762410e04970830f555f660417cdb0",
    "tests/fixtures/prove-stores/SHA256SUMS": "dce1df89ab3a7e3a0dc38e3972e9a15829f2ed14503c4d7d6dd1685e1e2b2a88",
}


def pinned_paths(names: list[str]) -> list[str]:
    return [n for n in tf20_pinned(names) if not n.startswith("tests/fixtures/pf/")]


def pins() -> dict[str, Any]:
    held: dict[str, Any] = json.loads(PINS.read_text(encoding="utf-8"))
    return held


def main_text(name: str) -> str:
    """A file of ``TEXTS`` as main 4bb4b95 holds it, checked against the digest pinned beside it."""
    import hashlib

    held = pins()
    text = str(held["texts"][name])
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == held["files"][name], f"the pinned text of {name} is not main's file"
    return text


__all__ = ["BUILT", "FLOOR_STORE", "MAIN", "OURS", "PINS", "REPO", "TEXTS", "file_digest", "main_text", "pinned_paths", "pins", "tracked"]
