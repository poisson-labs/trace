"""PF-99: the Prove floor pair's tests are frozen. Green by construction: the digests of its files
as its Session A froze them on ``trace-prove-floor-a``. A ruled change to one of them moves its
digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "pf_support.py": "e36b88453ae1b1efc84425a615a6b8c46f0350473dd1c9045a9a6b0cd2e1ffb2",
    "pf_pins.py": "ab07773323d791fbd37e790b5a286e33a42e7f1921f1f684687cf58392d608ca",
    "test_pf_floor.py": "c484787b8c5a3c6fd4f259533327b046cf1b3b89928fc683572dacb5cedea67e",
    "test_pf_store.py": "ecf473ceba293d7411f337a0deb1351f3b91a12001f5762c70954ffe12ebe758",
    "test_pf_ci.py": "30fd4073681f383e1c51577a281b094febafaed7b596677906b45612365df11a",
    "test_pf_unchanged.py": "ffd1d3e255dcde9c5d3769355e0ee48545f6d4e12a3831894137ab24eb90af18",
    "fixtures/pf/make_main_pins.py": "78960a06e4445afec302ebcc911cec9a2b50398b3e813e383f9ae34815cec947",
    "fixtures/pf/main-pins.json": "03d1b16f77f0ba06d1d8fd9ae2eb2ad41c181a434e22845a70c21027faf4898f",
}


def test_pf_99_no_frozen_pf_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
    assert len(FROZEN) == 8
