"""TF18-24: the static pages pair's tests are frozen. Green by construction: the digests of its
files as Session A froze them on ``trace-tf18-a``, as BD-6, TF13-37 and TF6-36 hold theirs. A
ruled change to one of them moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "test_tf18_api.py": "f82a71eb0e1d9d334af178dbb94c1827f99f3a507dbc9ac36cb4e3c1aa804d98",
    "test_tf18_bundle.py": "b9cbc7053aadd3825049e5257cb42bd3718e5a26ad3eac5bca2837d2890f47b1",
    "test_tf18_pages.py": "42657febc858d48a25fac8b162659da2e67e20bcef3e8dde857f7b71d3914419",
    "test_tf18_privacy.py": "a7cc628e2a2fb2defea9a55ad42433f820dad72d04c4e819f483043163e9986e",
    "test_tf18_report.py": "64a4cd222d742ae0ce4091ec5f98b39f603526b2d3d5938bb30859e536e0f1f1",
    "test_tf18_ui.py": "dbecb0e82c9522f4d6cb1a5cc8a07fa986f1c02e5cac4dc953073ac9e4273176",
    "tf18_support.py": "fcfd853e58b6dd276b23c3f873f234b5027ad40c851fe512f5583c603d294a71",
}


def test_tf18_24_no_frozen_tf18_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN


def test_tf18_24_every_file_of_the_pair_is_frozen() -> None:
    mine = {p.name for p in TESTS.glob("test_tf18_*.py")} - {"test_tf18_frozen.py"}
    fixtures = {str(p.relative_to(TESTS)) for p in (TESTS / "fixtures" / "tf18").rglob("*")
                if p.is_file() and "__pycache__" not in p.parts}
    assert mine | fixtures | {"tf18_support.py"} == set(FROZEN)
