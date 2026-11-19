"""RUNREC-50: the run record's tests are frozen. Green by construction: the digests of its files
as its Session A froze them on ``trace-runrec-a``, as TF21-66 holds TF21's. A ruled change to one
of them moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "runrec_support.py": "3c0e83d480641d33a673a07d94d4d7b5c222b9413b4565739a39672fd86bc338",
    "test_runrec_descriptor.py": "ae86dbd55c8de1af6911d462bc9ce7bace1773327e57b7b6d849c56b94cca473",
    "test_runrec_events.py": "24c985de9935630787e2f4780c6a8840740609c9ea68b9014a02c816cb405298",
    "test_runrec_produced_by.py": "b6a0357b4a1b93b17b46702855ff6e190d71ef2623020bdb571357d8909e86ff",
    "test_runrec_paths.py": "baf1276c99c986cf53dcd05a46dcb98ac12a678c73ec6b5307efe0fb8f16eb09",
    "test_runrec_unchanged.py": "5667a36bae0a263adadad5dde84ce7a795c4b368b0275c27d2af20733eae8758",
    # PACE-20's file: besides the pacing pair's digests it holds a test of this guard's own lines
    # (RUNREC-11, RUNREC-12 and their shared check), and no guard held it
    "test_pacing_frozen.py": "f9861a4aabd39d025fac187e962f7ffc626626dd50a6e2c6fe4279c06d81a194",
}


def test_runrec_50_no_frozen_run_record_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
