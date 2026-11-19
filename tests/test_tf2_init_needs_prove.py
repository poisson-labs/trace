"""TF2-17: ``init`` reads stores through Prove, so without Prove it refuses before it searches
(TR10 and TR41 kept whole).

Two frozen rules hold that every read of a store goes through Prove: Trace's source never names
Prove's record file and reads no rows itself (TR10, TR41). ``init`` keeps them: without Prove at
the version Trace reads it lists nothing and writes nothing, and its one error line has the
install line under it, as every other verb's has."""

from __future__ import annotations

from pathlib import Path

import pytest

from tf0_support import INSTALL_PROVE
from tf1_support import tau2_copy
from tf2_support import CONFIG, numbered, refused, run, scratch_home, tree, work  # noqa: F401


# a Prove below the floor (0.3.0); one above it, such as 9.9.9, is one Trace reads
@pytest.mark.parametrize("prove", ["absent", "0.3.0"])
def test_tf2_17_without_prove_init_refuses_before_it_searches(tmp_path: Path, prove: str) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    before = tree(folder)
    result = run(["init", "--yes"], cwd=folder, prove=prove)
    error = refused(result)
    assert result.lines() == [error, f"  next: {INSTALL_PROVE}"], result.err
    assert INSTALL_PROVE not in error, error
    assert numbered(result.err) == {} and "proofload-runs" not in result.err
    assert tree(folder) == before and not (folder / CONFIG).exists()
