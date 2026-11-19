"""TF26-72: TF26's tests are frozen. Green by construction: the digests of its files as its
Session A froze them on ``trace-tf26-a``, as TF25-72 holds TF25's. A ruled change to one of them
moves its digest here in the same commit. The two tests Taylor ruled on 2026-11-12 (B-3 and
B-4 of Session B) are held here from the commit that adds them."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "tf26_support.py": "b46008caf0913da496cb1386f65948d06ae5931f33200ed5140538c21f92c7b4",
    "tf26_pins.py": "7e5eb36fa9a79b8835ca11d563f6ad5a6025e33696dc7e2c09f65dcb4f477148",
    "test_tf26_fixtures.py": "dc57687279113ac01b07bdf79d3ab566d64c3f0e86bcf8beca94f6c55920846d",
    "test_tf26_reader.py": "ba4f7875123fe13c613989de9f0254d176e8738fbfb3653e1023d3f8d37f287a",
    "test_tf26_signals.py": "8073a4219a2a76ee6c1c0245efff2d046b0a197272b1518962d51d34d9c36b6c",
    "test_tf26_agree.py": "a30317941fa0d5942298b7dd1934fb71a55de0ad205ce8e6c28e3c2aeb232d18",
    "test_tf26_pull.py": "711f258df9c1aa112d70cb6037acd918384e8deeb4a416ca466179af61a81376",
    "test_tf26_cli.py": "4e7722d0fc630e00213e3c71571a1608f78c5e8f68419fe2375a47a55e1ddfcd",
    "test_tf26_pages.py": "0afafddc43018ff91f9e596eeeb611badca084f270ab014e6449e65674849090",
    "test_tf26_unchanged.py": "dd06fdff16c29c974ee19701ec14ee8e08c93817f7c3d53b74ce6932d8cff000",
    "test_tf26_stand_ins.py": "871526b5a3f461a332614d04be56c8b5c78f672439c99d44c5f203dc4dc96a38",
    "test_tf26_init.py": "b3e0eeb6d4775c75f8739e6eb5982e44bd693bbf1317c8a8aee1192d1486e6d3",
    "test_tf26_reference_answer.py": "2b2ae3926569ea8bd1fbf5bfaf870d36f371acd33646ee8c042d75d1eaccb33a",
    "test_tf26_found.py": "0ac7933f9abf343497eabcaaf95c5aca235243e3221c7102f09f68d3e8658c6f",
    "fixtures/tf26/make_main_pins.py": "47dc6fd5221e3064f78815730b1e011c71a474c5e2fccf6af17e9a167cd7532c",
    "fixtures/tf26/main-pins.json": "6e692f8b7c4af610deee22f249c0f3e5bac30569beb25388acac1278a300c2c5",
}


def test_tf26_72_no_frozen_tf26_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
    assert len(FROZEN) == 16
