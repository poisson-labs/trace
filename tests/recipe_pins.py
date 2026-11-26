"""What main prints, builds and holds, pinned for TF20: the pinned main (``MAIN``) is the
release candidate of the TF5 docs work, and the three-tools recipe moves none of it. Not collected.

What is pinned, each as the pinned main gives it:

``piped``
    TF5's whole corpus (``docs_pins.pin_corpus()``, every earlier corpus inside it:
    every verb's plain and ``--json`` output on each kind of store, each option, the refusals,
    every reader's help under both spellings, every import, a pull of each service, the names,
    the saves, ``ui`` and ``report``), with the eight helps and the readers' facts the TF5
    docs changed or read (``docs_pins.CHANGED``, ``docs_pins.READERS_SAID``) now pinned as main
    prints them: each step's exit code and the digests of its stdout and stderr.
``init``
    ``init`` on the files it finds (``docs_pins.INIT``) and on a folder of every tool, digests.
``setup``, ``skill``
    ``doctor`` and ``init`` on a store, with the machine's own words written out
    (``docs_pins.machine``), and the setup skill ``init --agent --print`` prints; digests.
``pages``, ``app``
    Every file ``ui`` writes over TF19's workspace (digests, save times set aside), and every
    screen of the terminal app over it (text).
``texts``, ``tracked``
    The six files the recipe changes (``TEXTS``) as text, and the path of every file main
    tracks.
``files``
    The digest of every file of the repository a user is given or reads, as main holds it: the
    package's source, every page under ``docs/``, the README, the CHANGELOG, the contributing
    page, ``pyproject.toml``, the build hook, the licence and notice, the docs checker, the
    workflows and lane scripts, and every committed fixture under ``tests/fixtures/``.

Paths are written ``<ROOT>`` and times ``<TIME>``; no pin holds a path of the machine that took
it.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from docs_pins import CHANGED, EVERY_LABEL, INIT, READERS_SAID, SETUP, SKILL, pin_corpus as tf5_corpus

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
MAIN = "5700ad9"

#: The files the recipe changes, pinned as text as well, so that a test can say what moved in
#: them without the repository's history (a shallow clone has none).
TEXTS = ("README.md", "CHANGELOG.md", "CONTRIBUTING.md", "pyproject.toml", ".github/workflows/ci.yml", ".github/workflows/release.yml")
#: The files of the repository pinned whole: these paths, and every tracked file under these
#: folders.
PINNED_FILES = ("README.md", "CHANGELOG.md", "CONTRIBUTING.md", "pyproject.toml", "hatch_build.py", "LICENSE", "NOTICE")
PINNED_FOLDERS = ("src/", "docs/", "tools/", ".github/", "tests/fixtures/")


def pin_corpus() -> dict[str, tuple[str, str, list[list[str]]]]:
    """Every invocation pinned under ``piped``: TF5's corpus, and the helps and
    readers' facts it held as text, now as main prints them."""
    out = dict(tf5_corpus())
    for label, case in {**CHANGED, **READERS_SAID}.items():
        if label != "doctor":  # it names the machine's Python: pinned under ``setup`` as "doctor: a config"
            out.setdefault(label, case)
    return out


def pin_slow() -> frozenset[str]:
    from docs_pins import pin_slow as tf5_slow

    return tf5_slow()


def tracked(at: Path = REPO) -> list[str]:
    """The files git tracks in the checkout, as paths from its root."""
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=at, capture_output=True, text=True, check=True).stdout
    return sorted(name for name in listed.split("\0") if name)


def pinned_paths(names: list[str]) -> list[str]:
    return [name for name in names if (name in PINNED_FILES or name.startswith(PINNED_FOLDERS)) and not name.startswith("tests/fixtures/tf20/")]


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest_text_steps(got: list[tuple[int, str, str]]) -> list[list[Any]]:
    return [[code, text_digest(out), text_digest(err)] for code, out, err in got]


__all__ = ["TEXTS", "CHANGED", "EVERY_LABEL", "INIT", "MAIN", "READERS_SAID", "SETUP", "SKILL", "file_digest", "pin_corpus", "pin_slow",
           "pinned_paths", "text_digest", "tracked"]
