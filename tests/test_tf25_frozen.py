"""TF25-72: TF25's tests are frozen. Green by construction: the digests of its files as its
Session A froze them on ``trace-tf25-a``, as TF24-72 holds TF24's. A ruled change to one of them
moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "tf25_support.py": "30778852e2022906ea2fb5929da38a00a12f98b96206acd798d27bcff3d9b5ff",
    "tf25_pins.py": "5ff47f0eeb769c9ded597eceeff69cd99a2bed67bfb3810a75f4bfee443ffb86",
    "test_tf25_fixtures.py": "07f59dad5ea610760e5fa7f77b5720357a16cf677fd194980bbf3a7f24650b4d",
    "test_tf25_reader.py": "3c8278662a630e504177b6e20a125302b3ac356f2bfff7838ae9f99bc993b08f",
    "test_tf25_signals.py": "98097ce008e38feb2b9185506f3ac3d5e720484c40f0d51a9d4f825e3f4b670e",
    "test_tf25_agree.py": "159081a93dafe840e068045a6b5876645a18143825098d830231baab2b872596",
    "test_tf25_pull.py": "0762b6f5f9e32fe28a19fc1bbc254df09a7e183a5c1b4950347158e5f46fc8c0",
    "test_tf25_cli.py": "93b3d49688eadafc0f766b2f37bb284f68e1c30e29eb8b1ff57900cec3962582",
    "test_tf25_pages.py": "1232731db46d7d2eddb238b98c1c230a9aea7680d955a7952a022ff76d33b322",
    "test_tf25_unchanged.py": "d3e330d7b954d4f999ebe49d8bfaf3fa208c4dce37dac5eac370ad40774deaab",
    "test_tf25_stand_ins.py": "392cf150a87423fd7b51fa4450059e43767d6e03a26a9aa5bfe8a1b6def48625",
    "test_tf25_init.py": "5c78e442688a7a0e95b4e822343c5d60e3d4ff252a4751b1e1adad030b7a9516",
    "test_tf25_listing.py": "bd6dc3b2993b77bf04f1353d86ce44b7153e0bc50d8829f014febc01fcfa768d",
    "fixtures/tf25/make_main_pins.py": "1640073aa1db9863ac1bb2a36c07ba11126e57a6a7f1550d5607492dffb39ea2",
    "fixtures/tf25/main-pins.json": "d8a2fde477c0f1bd7efb10f26474e17bf20b1b70b328798a9e91cdf72a9aa968",
}


def test_tf25_72_no_frozen_tf25_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
    assert len(FROZEN) == 15
