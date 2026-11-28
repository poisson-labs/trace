"""Writes ``tests/fixtures/no-failures/printed/``: what fix-check prints for the pairs that never
failed (``tests/test_no_failures_printed.py`` holds them byte for byte). Run from
the repository's root, with the package installed::

    python tests/fixtures/no-failures/make_printed.py

Unlike ``main-pins.json`` these were taken from the fixed code: they are a record of what it
prints, kept so that a later change to any byte of it is made on purpose. The numbers in them are
checked against independent computations in ``tests/test_no_failures.py``.

The ``--json`` files were taken again when the numbers Trace computes became the same bits on
every platform: the last digits of the range's ends moved, and each move was held to the rule of
``tests/fixtures/portable/check_moves.py``; the plain files did not move.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TESTS))

from no_failures_support import NO_FAILURES_FIXTURES, printed  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        for name, text in printed(Path(tmp).resolve()).items():
            (NO_FAILURES_FIXTURES / "printed" / name).write_text(text, encoding="utf-8")
            print(name, file=sys.stderr)


if __name__ == "__main__":
    main()
