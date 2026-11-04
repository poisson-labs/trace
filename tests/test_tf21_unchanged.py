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
from tf21_support import IMPORTS, digest, do_import, json_without_store, verb_view

# (verb view, import --json) per import, as main d7e19c7 wrote them
MAIN = {
    "deepeval-a": ("474bacf0a600748e2744fb460bb84b7a41c9bf4828a0cf18c5a838fe473415ec",
                   "6be6a1b07a7ef172808e2f6336abf5e7d8586799dd90955c3590021b70cb34c4"),
    "deepeval-b": ("ee56b1df5d2adf53a1238411d7d344d383c574e7c469b85ee4e3725b0a40af41",
                   "54333567690813ee0aed8f0cb52be6421322bff25af2f59e94cdc591259d27f8"),
    "junit-a": ("053ede640e1ac4fffff2dfcadb552d89cc9aa4acc5d7482a3db0c55351871002",
                "1b5a845c8f2951fe04c7c6ad520e97bda431c231da90a140e04641161f5b1fbe"),
    "junit-b": ("e15cee9a64d9d5e94855f906e6071fc7a455d941cc69c93cf5ba0ca61fbecbdc",
                "4ddb2f827575e1ccda857e07c7be8018e9263fd23a2e46827334c337667938c1"),
    "junit-suite": ("3ed3584fe5e591fb3b12995721b935025768bd0a6220f131e129662918858490",
                    "8b9dc4c1acb02984465b2656076d11a04dc9455cc031211a999fefa2a9142daa"),
    "ragas-base": ("599b50baa9b3f77dfaa5ab4370e4eceb1383e8067e2c51064a8100290c2181a2",
                   "90301d338d112fa1fcf31c6f127dd0d9ea4bcb49822a551df6291ec205aae4e5"),
    "ragas-raft": ("0e9921cb735b5abc49f0f972e71b3697641bf334d1a7389293d0789e15e32d26",
                   "bd52ead150045c610dce8f62713ebd048bfbe677e78f882404d7678a3245cb0e"),
    "ragas-causal": ("cd7d66d9840cdef47448407f7626bb0a72a5763194b78f004e7202e8794a4a6c",
                     "07e919dd58c664f23b653013a86d9c5e5b9e0e67f87640793ae1f93affa3b805"),
    "ragas-strong": ("18d5ce1d78be95d69f4a5e5b2538bb232ddc4a6b101d7e18caf430b5f5e42bcf",
                     "f55598496888bf67921fc903fba57fc7ad23d79e0c2c20b651d0756cdaab4f2e"),
    "table-a": ("a5102653f35fcf02db495857f16912deb094543ac1afd66f79174a2ce21828fc",
                "ace3b96ac51458591fc266c3632ed0bd696947f3187204bf3196b1396837b180"),
    "table-b": ("e8a746ecb420d6512cffd581de78a911abccb6ffe96f2cbf6152f91f8b82b1a1",
                "b918293b05b0464b75b22984c35abb34cb30fe1471d3151158c53f8b0cb1798a"),
}


def test_tf21_64_every_committed_import_is_pinned() -> None:
    assert set(MAIN) == set(IMPORTS)


@pytest.mark.parametrize("key", sorted(MAIN))
def test_tf21_64_what_a_verb_reads_is_unchanged(tmp_path: Path, key: str) -> None:
    root = tmp_path / "store"
    result = do_import(key, root)
    assert digest(verb_view(root, key)) == MAIN[key][0]
    out = json_without_store(result, root)
    assert hashlib.sha256(out.encode("utf-8")).hexdigest() == MAIN[key][1]


def test_tf21_65_the_frozen_import_tests_still_read_rows_by_position() -> None:
    # tests/ingest builds rows as Row(case, outcome, error, score): TF21 keeps that working
    from poisson_trace.ingest.rows import Row

    row = Row("c1", "missed", None, 0.1)
    assert (row.case, row.outcome, row.error, row.score) == ("c1", "missed", None, 0.1)
