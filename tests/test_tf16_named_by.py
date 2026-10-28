"""TF16-15 (pending yes/no 3 of TF16 Session A): a run named at sweep time is counted as named by
you, as a run named at import is (spec section 5.3: ``named_by`` is ``you`` or ``manifest``; a
name typed when the run was made is the user's own), in ``runs --json`` and in the listing's
first line.
"""

from __future__ import annotations

from pathlib import Path

from tf16_support import NEW_AFTER, NEW_BEFORE, OLD_A, OLD_B, copies, scratch_home, trace  # noqa: F401


def test_tf16_15_a_run_named_at_sweep_time_is_counted_as_named_by_you(tmp_path: Path) -> None:
    old, new = copies(tmp_path)
    for store, want in ((new, {NEW_BEFORE: "you", NEW_AFTER: "you"}),
                        (old, {OLD_A: "manifest", OLD_B: "manifest"})):
        ran = trace(["runs", "--store", store, "--json"])
        assert ran.code == 0, ran.text
        assert {r["run_id"]: r["named_by"] for r in ran.json()["runs"]} == want
    listing = trace(["runs", "--store", new])
    assert "2 named by you, 0 named from their manifests" in listing.out.splitlines()[0], listing.out
