"""TF16-13 and TF16-14: the two committed Prove stores are what their provenance says, and TF16's
tests are frozen.

- TF16-13: every file of the two stores is listed in ``SHA256SUMS`` with its digest, and the
  provenance names the recipe and the published Prove that made the new store; the 0.0.1 store has no ``.poisson/``, no
  event log and no names, the main store has all three; and the two hold the same outcomes, row
  for row, which is what lets TF16-4 ask the same answer of both.
- TF16-14: green by construction: the digests of TF16's test files as Session A froze them.
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
    files = {str(p.relative_to(STORES)): p for root in (OLD, NEW) for p in root.rglob("*") if p.is_file()}
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


# ---------- TF16-14 ----------

FROZEN = {
    "tf16_support.py": "d4a8bcc35fe72a405eccb132b368300564428f6af020bf8634024f28d954a5c7",
    "test_tf16_prove_name.py": "8aabcd1b957512d6b35d982675728f4df09d48219c65ecce0760eaf10cfd5b48",
    "test_tf16_stores.py": "dc0db3c091b70b797a3786e484e6f84a8a6078847800ac712806324cf6e396da",
    "test_tf16_run_names.py": "509050fb9f722e73e94cf61b7093f58e5decb95f31f32f4b50feab174831709d",
    "fixtures/prove-stores/make.py": "3181291ebde494ae353bff47fe6f0d6b065872b57048aa4454812bcccfed06a7",
    "fixtures/prove-stores/sweep.toml": "690368203d9ccf5d9542cfb95aec7b454c7a301b0eabee6fe94a06b9af18adff",
    "fixtures/prove-stores/PROVENANCE.md": "628b0f46509f64acce196183252e33180616ccbe48648c97445ad8c496073366",
    "fixtures/prove-stores/SHA256SUMS": "714b066814b7dc6402fbd04b079fe106caa05ce5d61fc0dbc73a475f32d863c2",
}


def test_tf16_14_no_frozen_tf16_test_is_edited() -> None:
    """Green by construction: the digests of TF16's files as Session A froze them on tf16-a."""
    got = {name: _sha256(TESTS / name) for name in FROZEN}
    assert got == FROZEN
