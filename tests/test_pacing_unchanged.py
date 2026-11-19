"""PACE-10: three cases of what main 2ff191b printed that no later list runs.

**PACE-10** Each of the three invocations prints, piped, what main 2ff191b printed, byte for
byte: the exit code, stdout and stderr of each step. They are the refusal of ``weave`` as a tool
the install lacks, the import of Weave's paged pull, and the Weave reader's refusals as this pair
ran them. Pinned by ``fixtures/pacing/make_main_pins.py`` on Python 3.12.13, checked on 3.11.

The other 190 cases of PACE-10, its tests of its own pins, and PACE-11 to PACE-13 (``init``, the
pages and the terminal app as main gave them) were cut on the rulings of 2026-11-18 (AR-1, AR-3):
``test_pl_unchanged.py`` (PL-51 to PL-55) holds each at today's bytes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pacing_pins import PINS, digest_steps, pin_corpus, ran_case

PINNED: dict[str, Any] = json.loads(PINS.read_text(encoding="utf-8"))
CORPUS = pin_corpus()


# ---------- PACE-10 ----------


#: The three cases no later list runs: the newest list (``pl_pins``, PL-51) runs every other case of this corpus whole,
#: at today's bytes, so only these are still held here (ruled 2026-11-18, AR-1).
HELD_HERE = ("import refusal: weave", "weave: import the paged pull", "weave: refusals")


@pytest.mark.parametrize("label", HELD_HERE)
def test_pace_10_as_main_prints_it(tmp_path: Path, label: str) -> None:
    place, kind, steps = CORPUS[label]
    # none of the three is a case a later ruling moved, so each is held as it prints, with nothing written back
    assert digest_steps(ran_case(tmp_path, place, kind, steps)) == PINNED["piped"][label], label
