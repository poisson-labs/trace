"""TF21-64 and TF21-65: what TF21 leaves as it is (spec section 18.4.2, SG3; SA1, SA10).

For every committed import, everything a Trace verb reads of the stored run (the outcome,
error, config and config_hash columns, seed and replicate, the trace envelope, the tally, and the
manifest apart from the taxonomy digest TF21 adds) and the import's own ``--json`` output are
byte for byte what Trace main ``d7e19c7`` wrote, so no verb prints anything different on an
imported run. Green on main by construction; a ruled change moves its digest here."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from tf21_support import IMPORTS, digest, do_import, json_without_store, verb_view

# (verb view, import --json) per import, as main d7e19c7 wrote them
MAIN = {
    "deepeval-a": ("06c19e5a7af4c10ec64ec69f57cb9109116e4b40d68012b0e10a0797a4387b66",
                   "6be6a1b07a7ef172808e2f6336abf5e7d8586799dd90955c3590021b70cb34c4"),
    "deepeval-b": ("8c4b6af077e5fffecbe0654a1ea5616f1ace81b5d6741b0e56a88f376e586fd2",
                   "54333567690813ee0aed8f0cb52be6421322bff25af2f59e94cdc591259d27f8"),
    "junit-a": ("2e1177dc62fb306ce2a9c6b1410e67707da3a5880f91d4bfad2534c035a538b4",
                "1b5a845c8f2951fe04c7c6ad520e97bda431c231da90a140e04641161f5b1fbe"),
    "junit-b": ("186a9f94e30011877255a5a6685919707599e93ca63f206197e099e18cf22dab",
                "4ddb2f827575e1ccda857e07c7be8018e9263fd23a2e46827334c337667938c1"),
    "junit-suite": ("17bbaab136911c4980d1e97502ec175013f3584cf037ef95a2a66b68dc64ac62",
                    "8b9dc4c1acb02984465b2656076d11a04dc9455cc031211a999fefa2a9142daa"),
    "ragas-base": ("6c528f2b5b7596d3d5a3d48c8e41fe6b0572b42dac71a6ed5c231085555d6f1f",
                   "90301d338d112fa1fcf31c6f127dd0d9ea4bcb49822a551df6291ec205aae4e5"),
    "ragas-raft": ("90f7165025d3d294b2f3a6c08a0747b6d32b8e5155bf4eee56a9d6f8192d11e7",
                   "bd52ead150045c610dce8f62713ebd048bfbe677e78f882404d7678a3245cb0e"),
    "ragas-causal": ("741f49f5a70bf323c0c566baeeb41d8338f73baa4efa70069839e35d95fd398e",
                     "07e919dd58c664f23b653013a86d9c5e5b9e0e67f87640793ae1f93affa3b805"),
    "ragas-strong": ("e32edf208e2978eba534ef33c6528a33e7a6595bd514feec38dc9c27e7e0e276",
                     "f55598496888bf67921fc903fba57fc7ad23d79e0c2c20b651d0756cdaab4f2e"),
    "table-a": ("e018345a4724d3c09fd0c8545a92e3216a945474d30ce1bc29128d4710ba8415",
                "ace3b96ac51458591fc266c3632ed0bd696947f3187204bf3196b1396837b180"),
    "table-b": ("b35b9150ffb649390c910d2f12d6116df1041e43b38123c77948dcef91d318ec",
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
