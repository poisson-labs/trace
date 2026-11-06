"""TF13-37: TF13's tests are frozen. Green by construction: the digests of its files as its
Session A froze them on ``trace-tf13-a``, as TF6-36, TF21-66 and TF23-35 hold theirs. A ruled
change to one of them moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "tf13_support.py": "de28a7263493cc09f69e670bfda9bd4580ed09766cd129e76a8b2a0747b4da71",
    "test_tf13_surface.py": "f2b8e545b4686b14a912844044c3813946bccd9217ea78cb7dc29cc614a55161",
    "test_tf13_results.py": "a65b4e883216132d7641b458019916fb46cda27f2099fc20267c385700ee2164",
    "test_tf13_refusals.py": "84331a50059ecad87f62c13485734f02b133794cf34389d50735e766b2f29bfc",
    "test_tf13_purity.py": "33d0343b01102320c94d7305095f2dc330f79940be30f96bb1c703a3f6263fa3",
    "test_tf13_thin.py": "aa98e26dc93542c049150de1b480bcc06dbc5f31c5feccd38bb5af38064611af",
    "test_tf13_unchanged.py": "a47bcca0442de0a80241484ab3d55b0eff35aeade9bd10694e8a8efb59beeb5d",
    "test_tf13_docs.py": "86c84616ee3f534aa458a11c4486368850d102d85f86cb3ff0fe6c9259160609",
}


def test_tf13_37_no_frozen_tf13_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
