"""TF20-99: TF20's tests are frozen. Green by construction: the digests of its files as its
Session A froze them on ``trace-tf20-a``, as TF5-99 holds TF5's. A ruled change to one of them
moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "tf20_support.py": "cb1e097e8b9951ed04605cde96173c664be9bedfa16ad4f6cc4f963ac938332f",
    "tf20_pins.py": "a37abc25c29d9dee9fb2254e434d7115fc2ece061857a68f335fd0863e5f2841",
    "test_tf20_recipe.py": "e3c7e27a9424b98826ec5ed0f75ce67bccf286c3266b3cabacbc15021b7c9511",
    "test_tf20_fixtures.py": "fc4a97fde2853ae8b7d3183afd71a1a3fb52cd33fb891e7370e9063737de256d",
    "test_tf20_unchanged.py": "cbaaaeb92a5c96cfb8e582e1711a1914047172d012df0082f91722105c44276c",
    "test_tf20_ci.py": "6d02ac2a4ce361089f41f3337fcb0d471ac5a90fc89cd033f05c8154ba67724a",
    "fixtures/tf20/make_main_pins.py": "c16a77486f3d2bf5db0aba538d15eff679ad87c102899ead9bdf50f389023537",
    "fixtures/tf20/main-pins.json": "c7069d38e2b90ecd9058979c17c60bf7b549c5dcd918e8d82a2f491b51d5d965",
}


def test_tf20_99_no_frozen_tf20_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
    assert len(FROZEN) == 8
