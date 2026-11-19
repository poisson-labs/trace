"""The frozen tests, held by one list.

``tests/frozen.sha256`` names every frozen file with the SHA-256 digest of its bytes, one line a
file, as ``shasum -a 256`` writes it and from the repository's root::

    shasum -a 256 -c tests/frozen.sha256

Frozen are every Python file under ``tests/`` (each test file, each support module and
``conftest.py``) and the files under ``tests/fixtures/`` that the tests' own pins and makers are.
The one test here fails when a listed file is edited or gone, and when a Python file under
``tests/`` is not on the list, so no test file is unheld and a new one joins the list in the commit
that adds it. This file and the list are the two that no line holds.

A frozen file changes only in a commit of its own that says why, with the file's line in the
list moved in that commit. The failure below prints the line to write.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"
LIST = TESTS / "frozen.sha256"


def _listed() -> dict[str, str]:
    held: dict[str, str] = {}
    for line in LIST.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        assert name not in held, f"{name} is listed twice"
        held[name] = digest
    return held


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _python_files() -> list[str]:
    """Every Python file under ``tests/`` but this one: the fixtures' own scripts are listed by name
    where a test's pins or makers are among them, and are not asked for here."""
    found = []
    for path in sorted(TESTS.rglob("*.py")):
        inside = path.relative_to(TESTS).parts
        if "__pycache__" in inside or inside[0] == "fixtures" or path == Path(__file__).resolve():
            continue
        found.append(path.relative_to(REPO).as_posix())
    return found


def test_no_frozen_file_is_edited_and_no_test_file_is_unheld() -> None:
    held = _listed()
    assert list(held) == sorted(held), "the list is kept in the order of its names"
    gone = [name for name in held if not (REPO / name).is_file()]
    edited = {name: _digest(REPO / name) for name in held if name not in gone and _digest(REPO / name) != held[name]}
    unheld = {name: _digest(REPO / name) for name in _python_files() if name not in held}
    lines = "\n".join(f"{digest}  {name}" for name, digest in sorted({**edited, **unheld}.items()))
    assert not gone, f"listed in tests/frozen.sha256 and not there: {gone}"
    assert not edited, f"edited without its line in tests/frozen.sha256 moved; on a ruling, the lines are:\n{lines}"
    assert not unheld, f"not in tests/frozen.sha256; the lines to add are:\n{lines}"
