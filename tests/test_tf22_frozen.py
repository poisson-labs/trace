"""TF22-46: TF22's tests are frozen. Green by construction: the digests of its files as its
Session A froze them on ``trace-tf22-a``, as TF21-66 holds TF21's. A ruled change to one of them
moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "tf22_support.py": "9882b7949abb377b5d71f89f5247ee6db4aeacb847b53b544f0f6d042bcb9d6c",
    "test_tf22_folder.py": "ddab5dfbccda432316570d0da9587f304ba6df62ebf50526a29eb84f18a397e5",
    "test_tf22_import.py": "5fedcee5706622b377c8ae2095db4a1b25951600c6e6f6cad6aafba9f0c448d5",
    "test_tf22_verbs.py": "16e4d86a0a6591600a5062891a3458df71d58d1cefc52b4aefc2b709acf2f186",
    "test_tf22_verdicts.py": "d4f2d9c905d60b9cccc50096294656b6bb894d3e7c77ee1d84f278c5629f6d43",
}


def test_tf22_46_no_frozen_tf22_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
