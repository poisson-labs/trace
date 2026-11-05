"""TF22-46: TF22's tests are frozen. Green by construction: the digests of its files as its
Session A froze them on ``trace-tf22-a``, as TF21-66 holds TF21's. A ruled change to one of them
moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "tf22_support.py": "89e6b38826bb555452fd832053c8b9a11ebe6ae2c890885deb404245327f8e86",
    "test_tf22_folder.py": "bc026f4e6c83bd6baf9db471c38e65141e65932dee6c715783a6c1e84c86b7bf",
    "test_tf22_import.py": "facfda44788e56a75a428c66442fb2113799f8f7d2be95d57548ec85fd93a739",
    "test_tf22_verbs.py": "16e4d86a0a6591600a5062891a3458df71d58d1cefc52b4aefc2b709acf2f186",
    "test_tf22_verdicts.py": "d4f2d9c905d60b9cccc50096294656b6bb894d3e7c77ee1d84f278c5629f6d43",
}


def test_tf22_46_no_frozen_tf22_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
