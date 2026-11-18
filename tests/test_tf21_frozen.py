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
    "test_tf21_writer.py": "18aa5c69705c53aa72ec000dab220b617b00dfaeaddf03eb25051d9e24a6cb21",
    "test_tf21_prove.py": "2565ef1613f4694197ee2a533b0d4166def92eb191e90890b1dab54e4aeb1f94",
    "test_tf21_tries.py": "46643363680bcfd2d3025914384becdd578a62ee2976358dc051b8faf6f23157",
    "test_tf21_readers.py": "4b28600702c2f4cb61e12aa9c66e18e132a4ac170450b5e8211bf0b92e4636e7",
    "test_tf21_overrides.py": "733123dacb3a5325ac5255bba0c1b54d79bd63842bb32bdf5d3a75920323038c",
    "test_tf21_unchanged.py": "38f4912235d9f85abfc0df27840c7302599903e1c8fcea79f3f14ccd12d9e7a3",
}


def test_tf21_66_no_frozen_tf21_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
