"""TF10-51: TF10's tests are frozen. Green by construction: the digests of its files as its
Session A froze them on ``trace-tf10-a``, as TF21-66 holds TF21's. A ruled change to one of them
moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "tf10_support.py": "4c52b0ad2ff981513f16d382619599d421ddb1e93f40ed68e37993ce3e72c4ef",
    "test_tf10_fixtures.py": "a1980680a0f4a712e7062221d1d6744e64be1a5d1e5cc10f8f4733f70c6dae7a",
    "test_tf10_promptfoo.py": "9c6c0c9b094810a778b2b95b3ba41408f273de1f08cea924dc8edfa7f51cc01a",
    "test_tf10_inspect.py": "d2291bff26ff8f3e86ce3bdac1f30574ec593b2bb6106a7da1775b2161ee3ce7",
    "test_tf10_openai_evals.py": "4025f587201d2e0b7cb8f6ebf0235f9a74973728d7972ef64e2c5bd6b89687d2",
    "test_tf10_cli.py": "8b486f71b7a8eeb83582b4d5182691ba98f8b440572a47aa54cda3a2ae6c0060",
    "test_tf10_looks_like.py": "f0ed6bf9e81a8efe791142c0073d5f8db1b5dc92aa8c6745d26850e0ac2d4fd9",
    "test_tf10_pages.py": "3152aaa16601e108af530e62fc67b0ba90d6887430bdc8c9eeee7e7fb8221cfe",
    "test_tf10_unchanged.py": "21adfa0e9273a6cc971813e155ccc99827adcabd77b0c834981dd72c1bac6130",
}


def test_tf10_51_no_frozen_tf10_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
