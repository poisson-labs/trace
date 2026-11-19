"""TF20-99: TF20's tests are frozen. Green by construction: the digests of its files as its
Session A froze them on ``trace-tf20-a``, as TF5-99 holds TF5's. A ruled change to one of them
moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "tf20_support.py": "0a61331551c99a201bf8ead64aa5eb74ddd207a1d97f353ad18caa53a7a8d03a",
    "tf20_pins.py": "a37abc25c29d9dee9fb2254e434d7115fc2ece061857a68f335fd0863e5f2841",
    "test_tf20_recipe.py": "e3c7e27a9424b98826ec5ed0f75ce67bccf286c3266b3cabacbc15021b7c9511",
    "test_tf20_fixtures.py": "d5c127910bf834fc6cd049827d87004af842b5df78af72fc51b905723878ccca",
    "test_tf20_ci.py": "0aefca2af204566210ad435b90ea6b6f3b057f31393742967af4862672a05d8a",
}


def test_tf20_99_no_frozen_tf20_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
    assert len(FROZEN) == 5
