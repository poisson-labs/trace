"""TF16-13 and TF16-14: the two committed Prove stores are what their provenance says, and TF16's
tests are frozen.

- TF16-13: every file of the two stores is listed in ``SHA256SUMS`` with its digest, and the
  provenance names the recipe and both Prove commits; the 0.0.1 store has no ``.poisson/``, no
  event log and no names, the main store has all three; and the two hold the same outcomes, row
  for row, which is what lets TF16-4 ask the same answer of both.
- TF16-14: green by construction: the digests of TF16's test files as Session A froze them.
"""

from __future__ import annotations

import hashlib
import json

from tf16_support import (  # noqa: F401
    NEW, NEW_AFTER, NEW_BEFORE, OLD, OLD_A, OLD_B, POISSON, STORES, SWEEP_NAMES, TESTS, scratch_home,
)


def _sha256(path) -> str:  # type: ignore[no-untyped-def]
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------- TF16-13 ----------


def test_tf16_13_the_stores_are_listed_with_their_digests_and_their_recipe() -> None:
    sums = {}
    for line in (STORES / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        sums[name.removeprefix("./")] = digest
    files = {str(p.relative_to(STORES)): p for root in (OLD, NEW) for p in root.rglob("*") if p.is_file()}
    assert set(sums) == set(files)
    assert {name: _sha256(p) for name, p in files.items()} == sums
    provenance = (STORES / "PROVENANCE.md").read_text(encoding="utf-8")
    assert "make.py" in provenance and (STORES / "make.py").is_file()
    assert "98dc6af" in provenance and "fa31d79" in provenance


def test_tf16_13_each_store_is_as_its_prove_writes_one() -> None:
    old = {run: json.loads((OLD / run / "manifest.json").read_text()) for run in (OLD_A, OLD_B)}
    assert not (OLD / POISSON).exists()
    for run, manifest in old.items():
        assert manifest["proofload_version"] == "0.0.1" and "name" not in manifest, run
        assert not (OLD / run / "events.jsonl").exists()
    descriptor = json.loads((NEW / POISSON / "store.json").read_text())
    assert descriptor["format"] == "poisson.store/1"
    for run, name in SWEEP_NAMES.items():
        manifest = json.loads((NEW / run / "manifest.json").read_text())
        assert manifest["name"] == name and "proofload_version" not in manifest, run
        first = json.loads((NEW / run / "events.jsonl").read_text().splitlines()[0])
        assert (first["schema"], first["kind"]) == ("poisson.run-event/1", "planned"), run


def test_tf16_13_the_two_stores_hold_the_same_outcomes_row_for_row() -> None:
    from poisson_prove.store import Store

    def rows(root, run):  # type: ignore[no-untyped-def]
        frame = Store(root).read(run)
        return sorted(zip(frame["config_hash"], frame["replicate_index"], frame["outcome"], frame["t"], strict=True))

    for old_run, new_run in ((OLD_A, NEW_BEFORE), (OLD_B, NEW_AFTER)):
        assert rows(OLD, old_run) == rows(NEW, new_run), (old_run, new_run)


# ---------- TF16-14 ----------

FROZEN = {
    "tf16_support.py": "8e02290a379f8a031497fcc19405ba24f2e59559fdb5f2138341b45d237d8fa6",
    "test_tf16_prove_name.py": "483c4a1124768ba8e9aa8e6e1f920967f0f5db85d5de6c86b7c4e92e900f9382",
    "test_tf16_stores.py": "847c4b3f350ee449c52691b10b7770aea67549d1f718b9eea224e0bf21fe9e53",
    "test_tf16_run_names.py": "19d8cbeec6bc1adde8f342e29da93f0c7c40942d6b8aad5336688f0f622afb80",
    "fixtures/prove-stores/make.py": "5343906bbc2349d7cce3b90e816e690d53546e9c513ce5f235d6d89b5bf56944",
    "fixtures/prove-stores/sweep.toml": "690368203d9ccf5d9542cfb95aec7b454c7a301b0eabee6fe94a06b9af18adff",
    "fixtures/prove-stores/PROVENANCE.md": "e8e1dd7fd49e9b66e603f5c4d54787e89a2e41ee433c84d5cf645110899c1b9d",
    "fixtures/prove-stores/SHA256SUMS": "19de0494f901e186c34410c4a5a9a233228544138c19b41393295bf31af4335a",
}


def test_tf16_14_no_frozen_tf16_test_is_edited() -> None:
    """Green by construction: the digests of TF16's files as Session A froze them on tf16-a."""
    got = {name: _sha256(TESTS / name) for name in FROZEN}
    assert got == FROZEN
