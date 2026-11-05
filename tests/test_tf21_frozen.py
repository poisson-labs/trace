"""TF21-66: TF21's tests are frozen. Green by construction: the digests of its files as its
Session A froze them on ``trace-tf21-a``, as TF23-35 holds TF23's. A ruled change to one of them
moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "tf21_support.py": "eefa0e0b7ff018f4d285b13005a565a11d2c5e80e171187c96096bd82a36c467",
    "test_tf21_rows.py": "9d0faedfc7f4806b98a0e3f3fdc89b16d6a8925c110627e685e6f9f0462ac6af",
    "test_tf21_taxonomy.py": "98e6d47342aac30e37301767700b93ca0cc75c405ed9ec689f00bb6aa6096cef",
    "test_tf21_writer.py": "3c6658d4fc87d6258fab15208c18a27943c54e49b28bb0801bbe9e55527ab408",
    "test_tf21_prove.py": "df07589f3c7d67163057d3ab25020d9c744e73e20b2c9db6bb30bda2b032da35",
    "test_tf21_tries.py": "46643363680bcfd2d3025914384becdd578a62ee2976358dc051b8faf6f23157",
    "test_tf21_readers.py": "4b28600702c2f4cb61e12aa9c66e18e132a4ac170450b5e8211bf0b92e4636e7",
    "test_tf21_overrides.py": "733123dacb3a5325ac5255bba0c1b54d79bd63842bb32bdf5d3a75920323038c",
    "test_tf21_unchanged.py": "76ed5d0270b55f8d42141b8858fa4350c6c58a31b2c2844a2cab587ad16cf637",
}


def test_tf21_66_no_frozen_tf21_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
