"""RUNREC-50: the run record's tests are frozen. Green by construction: the digests of its files
as its Session A froze them on ``trace-runrec-a``, as TF21-66 holds TF21's. A ruled change to one
of them moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "runrec_support.py": "616b28b0294447d61f5010361b1aa8c32f07afa9fb35e424dd93c593e0180e3b",
    "test_runrec_descriptor.py": "28fdd6dacd81921886076cc1a7aae57bbe5bb6c289a9f992e48e277e1f683128",
    "test_runrec_events.py": "24c985de9935630787e2f4780c6a8840740609c9ea68b9014a02c816cb405298",
    "test_runrec_produced_by.py": "b6a0357b4a1b93b17b46702855ff6e190d71ef2623020bdb571357d8909e86ff",
    "test_runrec_paths.py": "baf1276c99c986cf53dcd05a46dcb98ac12a678c73ec6b5307efe0fb8f16eb09",
    "test_runrec_unchanged.py": "995efee307cccd508fb10ac09b49b72123b3cf9d8fb525e3328253e2dd88c8af",
}


def test_runrec_50_no_frozen_run_record_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
