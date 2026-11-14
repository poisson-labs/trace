"""TF19-13: the terminal app pair's tests are frozen. Green by construction: the digests of its
files as Session A froze them on ``trace-tf19-a``, as TF18-24 holds TF18's. A ruled change to one
of them moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "fixtures/tf19/main-pins.json": "eab28b03b19077aba57a9f44397381dd1c4ab6be19c306b94688b4db9bfbec6f",
    "fixtures/tf19/make_main_pins.py": "5f07eb1e47483e4ca03842f573f6445590a3b6b7cb9d5bb1b77f64b4022e8dc8",
    "fixtures/tf19/prove-shell.json": "2bcdc708252ed0a82e52515ecfc14cc54e8d5365c365c9b3d63bff8095ab4743",
    "test_tf19_facts.py": "17c932c5d8e8a8195f70eeefc8e6f749cb8ad8da308adaf1ffe8db221b05d3a8",
    "test_tf19_keys.py": "feaa0d7a5008f04266034b27025c4692b7be13845e24b30555fc9a6be91aac07",
    "test_tf19_links.py": "4e4207229a36cd5b1508d1fb50a834dc11d2e89faca2e8129a6884e24b2d4ebb",
    "test_tf19_never.py": "e107c5b07fb9aa48fb6f046ad89d32d29708fb6f1380117b1d0521f15033d6c3",
    "test_tf19_objects.py": "467edf74cf99e56f97d7ecb2e56d435cb1b552146e00f3a2259b0b4711f1d4b4",
    "test_tf19_open.py": "b490f779e522877839b626fd6b71a016b2ada290651040e2e4a3754c3b4d9073",
    "test_tf19_saves.py": "8846954f904b7f7cfaa1db06c74189f9df0e9d37a0089f8d46099222054f95eb",
    "test_tf19_screens.py": "93ee57f27d2f5dabdb8e672d5fe921bb10ccd2f263824f1517ba8fb747daa850",
    "test_tf19_shell.py": "c7bf2b2f43a1482149683c9afec479b302538beb25e7770a55e7f5d9e171e815",
    "test_tf19_unchanged.py": "7bece4ff0fe38e1a8417956b27fa766147ddfa20becd4de6cfa8cb0639594caf",
    "tf19_support.py": "0a5cf2144cece8503e2ae0ca102d0632b1a00cd834009fcf2297c5d083d2283a",
}


def test_tf19_13_no_frozen_tf19_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN


def test_tf19_13_every_file_of_the_pair_is_frozen() -> None:
    mine = {p.name for p in TESTS.glob("test_tf19_*.py")} - {"test_tf19_frozen.py"}
    fixtures = {str(p.relative_to(TESTS)) for p in (TESTS / "fixtures" / "tf19").rglob("*")
                if p.is_file() and "__pycache__" not in p.parts}
    assert mine | fixtures | {"tf19_support.py"} == set(FROZEN)
