"""TRIES-6: the no-outcome count's tests are frozen. Green by construction: the digest of the file
as it was written first, before the build, as BD-6 holds the breakdown's. A ruled change to it
moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "test_tries_section.py": "bfaac52c6e035b974c435e000ce0e8ae92046c00ddbc2e049825a4a25dc7faee",
    "test_tries_selected.py": "44b6443b7b195e3ddd08aa3f5cef221e07efb2ced1c4a36abe083f84e34b4f3e",
}


def test_tries_6_no_frozen_no_outcome_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN


def test_tries_6_every_file_of_the_fix_is_frozen() -> None:
    mine = {p.name for p in TESTS.glob("test_tries_*.py")} - {"test_tries_frozen.py"}
    assert mine == set(FROZEN)
