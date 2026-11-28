"""Writes ``tests/fixtures/portable/golden.json``, the golden table that
``tests/test_portable_golden.py`` holds every build to, bit for bit.

Run from the repository's root, with the build installed::

    python tests/fixtures/portable/make_golden.py

It writes ``portable_support.entries()``: ``float.hex()`` of every result for the fixed inputs that
module lists, as the installed build computes them. Each value is computed only with arithmetic
that gives the same bits on every platform, so the table it writes on one platform holds on every
other. Run it once, when the numbers' arithmetic is written or changed on purpose; the table
changes only as a frozen move, with its line in ``tests/frozen.sha256`` moved in the same commit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TESTS))

from portable_support import GOLDEN, entries  # noqa: E402


def main() -> None:
    table = entries()
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(table, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {GOLDEN.relative_to(TESTS.parent)}", file=sys.stderr)


if __name__ == "__main__":
    main()
