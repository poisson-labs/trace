"""TF15-S44 (PENDING Taylor's yes/no, Session A log rulings.md): compare's --at difference is banded
by resampling the inputs the two runs share, both runs' tries on each input drawn together, as
where's band resamples inputs (section 9.7 item 8 names no method for this band).

On tau2 at step 20 the two runs' shares not yet failed are 0.695 and 0.655; resampled together the
band is about 0.135 wide (the statistician's read of 2026-10-20: -0.105 to +0.030, 2,000 draws),
resampled apart about 0.255. Revert this file's commit if the answer is no.
"""

from __future__ import annotations

from conftest import TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, compare


def test_tf15_s44_the_at_band_resamples_the_shared_inputs_together() -> None:
    result = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.5, "--at", "20", "--at", "30", "--json")
    assert result.code == 0, result.text
    rows = {r["step"]: r for r in result.json()["at"]}
    for step in (20, 30):
        row = rows[step]
        assert row["lo"] < row["diff"] < row["hi"], row
        assert row["hi"] - row["lo"] <= 0.18, row
