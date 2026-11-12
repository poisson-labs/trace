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
    "test_tf24_cli.py": "eeb7b50cf22859ba1df7ec203f1e5f8635538c41c358d994de031da8d30ecb37",
    "test_tf24_pages.py": "715613d965529e16b8440416bbfdba3c9118413bb5d695fecd860b750b197698",
    "test_tf24_unchanged.py": "7407f48a1d1bc24e3a52e08a9328224daa4f71b33431cb3934ef99ccc4399d17",
    "test_tf24_stand_ins.py": "6ed42680775c216189b7a0c6424e5b59d8a6eeffc3ef26284abbb0a7d9f4250b",
    "fixtures/tf24/make_main_pins.py": "5bc2a0fb5b12a2f40590349791d39e3d1287adb3804af2d5182d27d2d6a4cf84",
    "fixtures/tf24/main-pins.json": "214b888e9671a37532cfd25b41384723b47d42f3251ae8328e12a9cc00dce3e0",
}


def test_tf24_72_no_frozen_tf24_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
