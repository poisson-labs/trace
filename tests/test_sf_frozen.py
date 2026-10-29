"""SF3: the statistics follow-up's tests are frozen. Green by construction: the digests of its
files as its Session A froze them on ``stats-a``, as ``test_ic14`` and TF16-14 hold theirs. A
PENDING commit that moves one of them moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "sf_support.py": "8720c56540b7e3be466e0400e787e1e3e3ecb81ab42c1ba586676eee23ab49b4",
    "test_sf_per_input_limit.py": "ae76bef77e80c34e854328b522b42a769f9c96ed96b4c0acbbb4dd707f76aa0a",
}


def test_sf3_no_frozen_sf_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
