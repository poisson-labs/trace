"""IG-99: the Prove import guard's tests are frozen. Green by construction: the digest of its file
as it was frozen on ``trace-import-guard``, before the build (FL-11). A ruled change to it moves
its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "test_ig_bundle.py": "f6965ec9dab6ae69ba11868c6ce409c723e0e59876c972479a74e8dd362abb0f",
    "test_ig_imports.py": "980be948778dfeb80c6a33daa07aecba06ee5b50dbad7e9b29f0ee018397a584",
}


def test_ig_99_no_frozen_ig_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
    assert len(FROZEN) == 2
