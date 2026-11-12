"""TF17-48: TF17's tests are frozen. Green by construction: the digests of its files as its
Session A froze them on ``trace-tf17-a``, as TF22-46 holds TF22's; the shared-text fixture and
the expected config of the scripted run are frozen with them. A ruled change to one of them
moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "tf17_support.py": "ceebb5ad5a1ec3edfbe6ef71b6272fe6ed30f892ca64d46b1830ebfdbd4820c6",
    "test_tf17_agent.py": "9cc94aca1a3e1d2e1fbb7cb17bec94d70139a8d870de9ad8d2aaf05e16a045a8",
    "test_tf17_skill.py": "024d5a288dd82b84838b8fe21c558d4610f838a64236bcac564432895f76784e",
    "test_tf17_config.py": "df5dde51c3d58b26864de200b680d4815da34a056324507451410baa981ac6ba",
    "test_tf17_setup_check.py": "d7254e23ffe1b2b23c6789c969658db5dbdf1a89c29219879f1a3f666ad0c7a9",
    "test_tf17_handover.py": "2be418fef5aa1cfa4033cec0aae689f0b213228fbce57bbe7cf04c514e488914",
    "test_tf17_scripted.py": "2b3680b7c0b31c324dcb63b3eb31e4c65180657a5aba5878989c461769baa860",
    "test_tf17_signals.py": "7ed74db201ad99e14d9b7cc6922529af4ad3e159bf446aa2eab95e2c71382b36",
    "test_tf17_readers.py": "3d56c9660212b9a44d430cb72ff340692942500bd903c9811e325ea5ab5b5034",
    "fixtures/setup-agent/setup-file-format-1.txt": "19ebfd4e5974de468e666eb821fd04cab9624105dddf4611ca38a6caf72956e8",
    "fixtures/setup-agent/expected/trace.toml": "b698626def97dea1ab998232da7627c84f544f3e4f84265df412d3535a535710",
}


def test_tf17_48_no_frozen_tf17_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
