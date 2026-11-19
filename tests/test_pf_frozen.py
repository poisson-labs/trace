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
    "test_pf_floor.py": "9c6eed05a24edc859b4be067b626a34112ef87ae0153c7874675d23756e73a4f",
    "test_pf_store.py": "0da810b0203b13db457aae8da2392e68d6322519834f83e6c125b404716686d8",
    "test_pf_ci.py": "1190a41856f1fdf1cf49f899091785d7fe6739e93a8905a1612d769a0025d457",
    "test_pf_pages_and_stores.py": "3da28c6d539f6ac2ab52838c2b4dfa5cd5b180e0a9b4cce92add475be584feab",
    "test_pf_unchanged.py": "41df3073afb5a170719d077af46eb65d03c29d25e1a2680ccd83b33a4d4375cd",
    "fixtures/pf/make_main_pins.py": "78960a06e4445afec302ebcc911cec9a2b50398b3e813e383f9ae34815cec947",
    "fixtures/pf/main-pins.json": "03d1b16f77f0ba06d1d8fd9ae2eb2ad41c181a434e22845a70c21027faf4898f",
}


def test_pf_99_no_frozen_pf_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
    assert len(FROZEN) == 9
