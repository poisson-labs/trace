"""TF24-72: TF24's tests are frozen. Green by construction: the digests of its files as its
Session A froze them on ``trace-tf24-a``, as TF22-46 holds TF22's. A ruled change to one of them
moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "tf24_support.py": "db5533971ee8cb86f694a357db1643d007d57c3dcbc0625e4ad8691bcd6080f9",
    "test_tf24_fixtures.py": "9321d65d774a7fd7a040a634f3591d18b71747ca40e5213c9aab1a42ea7582f6",
    "test_tf24_reader.py": "889a04d91be35b51b71dc6acf4efd0cfe9f9e88b3603132a44f8f963f73c99fe",
    "test_tf24_signals.py": "6c6a01e6d98756749eddc7617509eb4f332eaab2d40eddd2496789e6c5c5897e",
    "test_tf24_agree.py": "987a5cc2415ae9b8dd53274ba646a41d67ca2e75d8968083593617f7addb7929",
    "test_tf24_pull.py": "0f8da599ae1367bc39f684d419d690b19cdad1bcb8e749d2a37495e258e35a83",
    "test_tf24_cli.py": "c59c0cadea836032af28decb5c665a97371472c7a547ca960d2940279b50b961",
    "test_tf24_pages.py": "e174413a52939060913f5baf3c4339a5f64c2135d9d95a6e89db1049644a3832",
    "test_tf24_unchanged.py": "ffa32048757917dece3c3c8ca6387f01e0071abc0c9ff1945a049d1ede4d0d9c",
    "test_tf24_stand_ins.py": "6ed42680775c216189b7a0c6424e5b59d8a6eeffc3ef26284abbb0a7d9f4250b",
}


def test_tf24_72_no_frozen_tf24_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
