"""TF16-13: the two committed Prove stores are what their provenance says.

- TF16-13: every file of the two stores is listed in ``SHA256SUMS`` with its digest, and the
  provenance names the recipe and the published Prove that made the new store; the 0.0.1 store has no ``.poisson/``, no
  event log and no names, the main store has all three; and the two hold the same outcomes, row
  for row, which is what lets TF16-4 ask the same answer of both.
"""

from __future__ import annotations

import hashlib
import json

from pin_support import REQUIREMENT
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
    # the floor's store beside the two (test_pf_pages_and_stores.py, PF-14, holds what it is)
    from pin_support import RECORDED

    files = {str(p.relative_to(STORES)): p for root in (OLD, NEW, STORES / f"prove-{RECORDED}") for p in root.rglob("*") if p.is_file()}
    assert set(sums) == set(files)
    assert {name: _sha256(p) for name, p in files.items()} == sums
    provenance = (STORES / "PROVENANCE.md").read_text(encoding="utf-8")
    assert "make.py" in provenance and (STORES / "make.py").is_file()
    assert REQUIREMENT in provenance and "PyPI" in provenance


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
