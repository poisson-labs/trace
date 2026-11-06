"""TF23-35: TF23's tests are frozen. Green by construction: the digests of its files as its
Session A froze them on ``trace-tf23-a``, as SF3 and TF16-14 hold theirs. A ruled change to one
of them moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "tf23_support.py": "cb1b236ea6cf1e9487bb4a078c069c24d68ca2aa9de2d2450388e9a56f5f11b5",
    "test_tf23_estimators.py": "3daeb66ee983467549939b4e95dcd3ab242f4cbf8f4a7def4328b6881bf09a05",
    "test_tf23_verdicts.py": "4785c8bce2957105c9f421952c36f5ea8dc7a5e661a2dff4e5a61347386ea5a3",
    "test_tf23_endings.py": "bd06da29ced4bc6c4885f3b16e9ebade922b8589e6a99686af500033c7a8b204",
    "test_tf23_scenarios.py": "ebdceca366b6d16d69e2bf255161d74bc46b9d0d63b6b64c83276746282d6b85",
    "test_tf23_table.py": "15e01c4e1b9de235c5a0b0a142458af599edc58e11c578d0597f638da4176cfc",
}


def test_tf23_35_no_frozen_tf23_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
