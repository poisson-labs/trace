"""TF21-64 and TF21-65: what TF21 leaves as it is (spec section 18.4.2, SG3; SA1, SA10).

For every committed import, everything a Trace verb reads of the stored run (the outcome,
error, config and config_hash columns, seed and replicate, the trace envelope, the tally, and the
manifest apart from the taxonomy digest TF21 adds) and the import's own ``--json`` output are
byte for byte what Trace main ``d7e19c7`` wrote, so no verb prints anything different on an
imported run. Green on main by construction; a ruled change moves its digest here. Taylor's ruling
of 2026-11-04 moved the verb views' digests for the manifest's Prove version, 0.1.2 to 0.1.3, alone. Taylor's ruling
of 2026-11-04 moved the verb views' digests for the manifest's Prove version, 0.1.2 to 0.1.3, alone."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from tf21_support import IMPORTS, do_import, json_without_store, verb_view

# (verb view, import --json) per import, as main d7e19c7 wrote them; the verb views re-pinned at
# 0.1.0a1 (ruled 2026-11-11, the pre-release cut): the version the import records is their one change
MAIN = {
    "deepeval-a": ("944bc4c98a409ad780570e94898e13118c0b21066b165e42148f130f7e522936",
                   "6be6a1b07a7ef172808e2f6336abf5e7d8586799dd90955c3590021b70cb34c4"),
    "deepeval-b": ("2bde2a00c6acaad070fed19266a7c4315b2033d97123cc981dbe2dfe6694d821",
                   "54333567690813ee0aed8f0cb52be6421322bff25af2f59e94cdc591259d27f8"),
    "junit-a": ("710687d77c5103b9f1de901512003d0528d01d1a2c52cfa04d8f215bd382780e",
                "1b5a845c8f2951fe04c7c6ad520e97bda431c231da90a140e04641161f5b1fbe"),
    "junit-b": ("69763ad0c51d368911e8a52c34030f25322e22b26254482ddc71f175b7f990cf",
                "4ddb2f827575e1ccda857e07c7be8018e9263fd23a2e46827334c337667938c1"),
    "junit-suite": ("e8912171ab04f8850afa4faa8b6a4eb8e03dfcd7c7f8b48d3104227c0baa9258",
                    "8b9dc4c1acb02984465b2656076d11a04dc9455cc031211a999fefa2a9142daa"),
    "ragas-base": ("296270ac52b49dfc2c513ab7e6dbba7fdb3707033d1802c3ebb6cd763c633f7d",
                   "90301d338d112fa1fcf31c6f127dd0d9ea4bcb49822a551df6291ec205aae4e5"),
    "ragas-raft": ("16ddff84760cf0a7ec409bc502d7955f1a7ff7b23cb1be77b75abd2fbcd9e2ed",
                   "bd52ead150045c610dce8f62713ebd048bfbe677e78f882404d7678a3245cb0e"),
    "ragas-causal": ("1528b2d232e6542ccd6644fd896d673c7131974abb4257626fc9b7f1d6893350",
                     "07e919dd58c664f23b653013a86d9c5e5b9e0e67f87640793ae1f93affa3b805"),
    "ragas-strong": ("36e3f077a4ad76fb12f14d8a2c1efca63cdd4ae02a43b87980df5aecf1aa4c03",
                     "f55598496888bf67921fc903fba57fc7ad23d79e0c2c20b651d0756cdaab4f2e"),
    "table-a": ("e1df353693dd3cf82dff92cfd25587052ef502a2f8a5563f53de0fa3e581067d",
                "ace3b96ac51458591fc266c3632ed0bd696947f3187204bf3196b1396837b180"),
    "table-b": ("156797b4342f31dba0c38f84b97df0b9724852798adf24bb739b49b44b874f8b",
                "b918293b05b0464b75b22984c35abb34cb30fe1471d3151158c53f8b0cb1798a"),
}


def test_tf21_64_every_committed_import_is_pinned() -> None:
    assert set(MAIN) == set(IMPORTS)


@pytest.mark.parametrize("key", sorted(MAIN))
def test_tf21_64_what_a_verb_reads_is_unchanged(tmp_path: Path, key: str) -> None:
    root = tmp_path / "store"
    result = do_import(key, root)
    from pin_support import as_pinned
    from tf21_support import canonical

    # Prove's version, where Trace prints it, is written as the pins hold it (pin_support.as_pinned; ruled 2026-11-17, PV-5)
    assert hashlib.sha256(as_pinned(canonical(verb_view(root, key)).decode("utf-8")).encode("utf-8")).hexdigest() == MAIN[key][0]
    out = as_pinned(json_without_store(result, root))
    assert hashlib.sha256(out.encode("utf-8")).hexdigest() == MAIN[key][1]


def test_tf21_65_the_frozen_import_tests_still_read_rows_by_position() -> None:
    # tests/ingest builds rows as Row(case, outcome, error, score): TF21 keeps that working
    from poisson_trace.ingest.rows import Row

    row = Row("c1", "missed", None, 0.1)
    assert (row.case, row.outcome, row.error, row.score) == ("c1", "missed", None, 0.1)
