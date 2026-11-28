"""Takes the pins of what main prints for ``fix-check``, for the tests that hold its other output
(``tests/test_no_failures_unchanged.py``): run on main (the commit ``no_failures_support.MAIN`` names),
before any change, from the repository's root, with the package installed::

    python tests/fixtures/no-failures/make_main_pins.py

It writes ``tests/fixtures/no-failures/main-pins.json``: for each invocation of
``no_failures_support.run_corpus`` its exit code and the digests of its stdout and its stderr, with
the folders the run made written ``<ROOT>``. The corpus is every fix-check output but one kind:
a pair in which the inputs compared hold no failed run in either version, which is the one kind
the fix changes (``tests/test_no_failures_printed.py``).

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

from no_failures_support import MAIN, PINS, run_corpus  # noqa: E402


def main() -> None:
    src = TESTS.parent / "src"
    changed = subprocess.run(["git", "diff", "--quiet", MAIN, "--", str(src)], cwd=TESTS.parent)
    if changed.returncode != 0:
        raise SystemExit(f"src/ differs from {MAIN}: the pins are taken on main only")
    with tempfile.TemporaryDirectory() as tmp:
        pins = {"main": MAIN, "pins": run_corpus(Path(tmp).resolve())}
    PINS.write_text(json.dumps(pins, indent=1) + "\n", encoding="utf-8")
    print(f"{len(pins['pins'])} invocations pinned", file=sys.stderr)


if __name__ == "__main__":
    main()
