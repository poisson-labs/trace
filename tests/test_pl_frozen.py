"""PL-99: the Prove label kinds pair's tests are frozen. Green by construction: the digests of its
files as its Session A froze them on ``trace-labels-a``. A ruled change to one of them moves its
digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "pl_support.py": "c026cfba7d011f043b9bfaef0399a4804cb672cdf88ede69fffd9f28558e17ee",
    "pl_pins.py": "cf2a88b0471daac3fe690839fb542037a73423571ae3f4f1452faa50d4d49244",
    "test_pl_reader.py": "678138f3d18b517fcb2bd262ca2c666aa7c2298197e478eeeac546acf74f5a18",
    "test_pl_config.py": "d11f1dad00350c2867d7fd56656a55aa00898819826d848367529ad9b62d4b3b",
    "test_pl_section.py": "80967c61f6877f305b4f0bd7829e9e7f545de57127de88322ee4f14938ebc014",
    "test_pl_recipe.py": "da89faf58701fd79bf8ae99d9677296f8607c03ab84a637dccd7572fbcaf3aee",
    "test_pl_docs.py": "31c152a444f535321b0e8fc75399340ed55e1c3544ee6c93af8c57c390d8bac5",
    "test_pl_unchanged.py": "6b7daf6f757bc17c3151a39655851979dd0965be3ec35a650e5f7b96cb0e8703",
    "fixtures/pl/make_main_pins.py": "a3f0528f27e875c8e234f692f3fc1a4e37f90813c2c74110d2d609f39e4d91fd",
    "fixtures/pl/main-pins.json": "3f6a6da70f077898919dc21edd3dbd79860a2bb42a85214e53e61aae1630b56f",
}


def test_pl_99_no_frozen_pl_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
    assert len(FROZEN) == 10
