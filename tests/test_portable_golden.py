"""The golden table holds, bit for bit.

``tests/fixtures/portable/golden.json`` holds ``float.hex()`` of every result for a fixed list of
inputs (``portable_support.entries``): each portable function at 200 fixed points; the fix
check's exact test, difference and range at two levels, by-input reading (enumerated, drawn, and
one case compared in floating point), consistency, both detection limits and the per-input flags
on 400 seeded tables; the log-rank, its detection limit, the one-step hazard ratio, Schoenfeld's
limit and Benjamini-Hochberg on 50 seeded pairs of runs; the measures' t range, sign-flip p,
smallest catchable change and Walsh-average range on 50 seeded samples; and the values the tie
tests stand on.

The test recomputes every entry with the installed build and requires the same strings. It runs
on macOS and on Linux, and at the numpy and scipy floors, so a number that differs by platform
or by version fails here. The table is written by ``tests/fixtures/portable/make_golden.py`` and
changes only as a frozen move.
"""

from __future__ import annotations

from typing import Any

from portable_support import GOLDEN, entries, golden


def _differences(want: Any, got: Any, at: str, out: list[str]) -> None:
    if len(out) >= 20:
        return
    if isinstance(want, dict) and isinstance(got, dict):
        for key in sorted(set(want) | set(got)):
            if key not in got or key not in want:
                out.append(f"{at}/{key}: {'missing' if key not in got else 'not in the table'}")
            else:
                _differences(want[key], got[key], f"{at}/{key}", out)
    elif isinstance(want, list) and isinstance(got, list) and len(want) == len(got):
        for i, (w, g) in enumerate(zip(want, got, strict=True)):
            _differences(w, g, f"{at}/{i}", out)
    elif want != got:
        out.append(f"{at}: the table holds {want!r}, the build gives {got!r}")


def test_every_entry_of_the_golden_table_is_recomputed_to_the_same_bits() -> None:
    assert GOLDEN.is_file(), f"{GOLDEN.relative_to(GOLDEN.parents[3])} is not written"
    want = golden()
    got = entries()
    found: list[str] = []
    _differences(want, got, "", found)
    assert not found, "the build does not give the golden table's bits:\n" + "\n".join(found)
