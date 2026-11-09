"""TF18-24: the static pages pair's tests are frozen. Green by construction: the digests of its
files as Session A froze them on ``trace-tf18-a``, as BD-6, TF13-37 and TF6-36 hold theirs. A
ruled change to one of them moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "test_tf18_api.py": "f82a71eb0e1d9d334af178dbb94c1827f99f3a507dbc9ac36cb4e3c1aa804d98",
    "test_tf18_bundle.py": "724cbfcd38e7352db0877d682592d260f432a270a585f08abdc1f6e1665852aa",
    "test_tf18_pages.py": "42657febc858d48a25fac8b162659da2e67e20bcef3e8dde857f7b71d3914419",
    "test_tf18_privacy.py": "a7cc628e2a2fb2defea9a55ad42433f820dad72d04c4e819f483043163e9986e",
    "test_tf18_report.py": "64a4cd222d742ae0ce4091ec5f98b39f603526b2d3d5938bb30859e536e0f1f1",
    "test_tf18_ui.py": "dbecb0e82c9522f4d6cb1a5cc8a07fa986f1c02e5cac4dc953073ac9e4273176",
    "test_tf18_unchanged.py": "66b046e2052b7e1757a28e4d6c1271a52b6e312cf77eba9a50152ec4fc13de72",
    "tf18_support.py": "d5045895be180792023f8c3131895d4666454f67a4d368c73e36499ce11243db",
    "fixtures/tf18/main-pins.json": "a5632b501ef1d6641d2bf339431c1b931aeb18f4bc6614a881653b06b810ec59",
    "fixtures/tf18/make_main_pins.py": "12ad479fb934e6e551a38d07505e9730ff26b9dac5abdbbcf3db9d1e4bb945a6",
}


def test_tf18_24_no_frozen_tf18_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN


def test_tf18_24_every_file_of_the_pair_is_frozen() -> None:
    mine = {p.name for p in TESTS.glob("test_tf18_*.py")} - {"test_tf18_frozen.py"}
    fixtures = {str(p.relative_to(TESTS)) for p in (TESTS / "fixtures" / "tf18").rglob("*")
                if p.is_file() and "__pycache__" not in p.parts}
    assert mine | fixtures | {"tf18_support.py"} == set(FROZEN)
