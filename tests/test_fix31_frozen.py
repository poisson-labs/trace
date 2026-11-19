"""FIX31-99: the tests of trace#31 (a fix check on runs that never failed) are frozen. Green by
construction: the digests of its files as they stand on main, as RUNREC-50 holds the run
record's. A ruled change to one of them moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "fix31_support.py": "4b683cdb25450529d3b33b66aa98fdcb1629eb1b9ebaa7fd5ba71cc549debd01",
    "test_fix31_math.py": "35f99814ac6e53ff03a5da65ece7d71fb4bb9f9df436eea35a5b0cae806efcea",
    "test_fix31_no_failures.py": "5e53be4f2a5bb5857dcac54e427c9740bfc41f155774e568e20baff90f582c87",
    "test_fix31_printed.py": "59e7d35b868c8238fd094eefb640860375540b0f8e3ff8c27c67ff9c6926f91d",
    "test_fix31_unchanged.py": "6e28f812c25d92c5361d03b5e615a02fa4bf0dc3f1a4fd2595c095e4253fc088",
    "fixtures/fix31/make_main_pins.py": "864d8ab46081dd70e0ccad90c0a4d23a13c21a7ac1770fea3d1c702984f086d8",
    "fixtures/fix31/main-pins.json": "0fe95ec9a747461600e034dfb7aae247559e114b7b509bfb4f533ad2f1fbf83e",
    "fixtures/fix31/make_printed.py": "1b1913b065a466bebe0ffa07e583b47cc80aa73d960c5169554b845a0c2727d3",
    "fixtures/fix31/break-case.json": "027cec2f17d1c1335cd3622d8060ab986f63ebc3407dd2f1ccca9f35ecb054cc",
    "fixtures/fix31/printed/break-case-weak-candidate.json": "c298b2e41a25538f509594eb243f6b5aad42cba266e39a5d17f2cdaf478ee6b6",
    "fixtures/fix31/printed/break-case.json": "e576a741dc90e224b8f6dce935d92ab1bc752ebb9e969e31d6d476f46c72f148",
    "fixtures/fix31/printed/break-case.md": "d99b5b7fdb9eb97c8750f04a443646a6b9f9affe7b8bbb1cfde41554e51fd018",
    "fixtures/fix31/printed/stray.json": "cce28779a8a56fa7418dd0bb044ba3774c60959ba090068dfacc4c9e29dd615d",
    "fixtures/fix31/printed/stray.md": "acc99e27d8c0247e4894983fa07faf433c41487ceba80fd637e445003c9592a6",
    "fixtures/fix31/printed/three-by-four.json": "76d8867290c6f648a2b595e1eee04afc5b0f67ec25419ca49bdc1eec1d67240e",
    "fixtures/fix31/printed/three-by-four.md": "f056c81c466429896a590a733059c4101b57f1d8e837db6be393fbd12b25ec99",
    "fixtures/fix31/printed/two-by-five.json": "4b5efe67152578960ebc6597f496263d0cb4f398ff6ad54a5ba5ce75d337997e",
    "fixtures/fix31/printed/two-by-five.md": "d58f1b25f72ac7de006c92cf28fae61045e2993a533bdb027347df3abc355d4c",
}


def test_fix31_99_no_frozen_fix31_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
    assert len(FROZEN) == 18
