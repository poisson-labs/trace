"""TF6-36: TF6's tests are frozen. Green by construction: the digests of its files as its
Session A froze them on ``trace-tf6-a``, as TF21-66 and TF23-35 hold theirs. A ruled change to one
of them moves its digest here in the same commit. SB7 (ruled by Taylor 2026-11-04) pointed
``tf6_support.py`` and ``test_tf6_unchanged.py`` at the Prove 0.1.3 store that replaced the 0.1.2
one with the Prove pin, and moved TF6-1's digests with it; their digests moved here."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "tf6_support.py": "10f511456dfdea1d9484ce9a9a6a32027141356af1c886997acec2be3bffa28d",
    "test_tf6_unchanged.py": "a840eee8551f81877a8e88634b1928b0330d629b5b620966a664c1fc55825d79",
    "test_tf6_save.py": "428dde054240f3f6b89fc9c8a6a66800fb88a279af1c2b8936de80e258221edf",
    "test_tf6_out.py": "cb14cc69b2ca8b65341429908bd856e682bcf2d8dd54f4c69aa5f27c7b6353a8",
    "test_tf6_handover_check.py": "858a5a26cd11a92bcadea5f9a35abbfcb603db17995e8e15c33b35a2c637b99a",
    "test_tf6_measures.py": "94668809c591570c80a4d88fb65875c95eb32bda71b823fed357ea16b3b7b841",
    "test_tf6_verdicts.py": "7f481745085b93f4576f60f7e4f4af7fcd0cd2239a9773c9c43f65457dc6d5df",
}


def test_tf6_36_no_frozen_tf6_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
