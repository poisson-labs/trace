"""SF1 and SF2: Trace's per-input limit (``paired.limit_rise``, carried on every row ``flags``
gives) follows Prove's corrected one: each arm's share goes with that arm's own number of tries
(TF16 Session A yes/no 8, ruled yes 2026-10-28). Prove 0.0.1, which Trace copied, paired the raised
share with the old arm's tries and the baseline with the new arm's; Prove fixed it at ``b6d6292``.

- SF1: on any design, even or uneven, at any share below 1, the limit is the one worked out from
  first principles in ``sf_support`` (independent of Trace's and Prove's code; checked equal to
  ``poisson_prove.stats.mde_two_proportion`` on a wide grid, ``log/trace-stats-a/``).
- SF2: at a share above 0 the limit never grows when either version gets more tries (spec §17.5's
  property for a detection limit). At a share of 0 it can: the 0.5-try guard moves the baseline
  itself when the old version has one or two tries.

- SF4: where the old version failed every try, no rise is possible and there is no limit: NaN, as
  Prove's ``mde_two_proportion`` gives (Trace's own decision for a share of 1, yes/no 8; 0.0.1
  measured a rise from ``1 - 0.5 / runs_old`` and gave a number).

All three are the math lane's (§17.5): the statistic against its reference and its property. TR57 and
TR58 (``test_paired.py``) hold the same limit equal to Prove's public function, in the code lane.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

import sf_support
from poisson_trace.paired import limit_rise

SETTINGS = settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])

ALPHAS = st.sampled_from([0.01, 0.05, 0.1, 0.2])
POWERS = st.sampled_from([0.8, 0.9])


@st.composite
def designs(draw, low: int = 0):  # type: ignore[no-untyped-def]
    """``(failed_old, runs_old, runs_new)`` with the old share below 1, and at least ``low``."""
    runs_old = draw(st.integers(max(1, low + 1), 200))
    return draw(st.integers(low, runs_old - 1)), runs_old, draw(st.integers(1, 200))


# ---------- SF1 ----------


@pytest.mark.math
@SETTINGS
@given(designs(), ALPHAS, POWERS)
@example((0, 50, 2), 0.05, 0.8)  # 0.5188; paired the 0.0.1 way, 0.7234
@example((0, 1, 50), 0.05, 0.8)  # 0.4988; paired the 0.0.1 way, 1.0 (none detectable)
@example((0, 3, 2), 0.2, 0.8)  # 0.7972; paired the 0.0.1 way, 0.7985 (TF16 Session A's case)
@example((1, 40, 3), 0.05, 0.8)  # 0.5217; paired the 0.0.1 way, 0.6610
@example((2, 9, 3), 0.05, 0.8)  # 0.7689; paired the 0.0.1 way, 0.7469
def test_sf1_each_version_s_share_goes_with_its_own_tries(design, alpha, power) -> None:  # type: ignore[no-untyped-def]
    failed_old, runs_old, runs_new = design
    share = failed_old / runs_old
    want = sf_support.limit(share, runs_old, runs_new, alpha=alpha, power_wanted=power)
    assert limit_rise(share, runs_old, runs_new, alpha=alpha, power=power) == pytest.approx(want, abs=1e-9)


# ---------- SF2 ----------


@pytest.mark.math
@SETTINGS
@given(designs(low=1), ALPHAS, POWERS)
def test_sf2_more_tries_never_raise_the_limit(design, alpha, power) -> None:  # type: ignore[no-untyped-def]
    failed_old, runs_old, runs_new = design
    share = failed_old / runs_old

    def at(old: int, new: int) -> float:
        return limit_rise(share, old, new, alpha=alpha, power=power)

    now = at(runs_old, runs_new)
    assert at(runs_old, runs_new + 1) <= now + 1e-9
    assert at(2 * runs_old, runs_new) <= now + 1e-9
    assert at(2 * runs_old, 2 * runs_new) <= now + 1e-9


# ---------- SF4 ----------


@pytest.mark.math
@SETTINGS
@given(st.integers(1, 200), st.integers(1, 200), ALPHAS, POWERS)
def test_sf4_a_version_that_failed_every_try_has_no_limit(runs_old, runs_new, alpha, power) -> None:  # type: ignore[no-untyped-def]
    assert math.isnan(limit_rise(1.0, runs_old, runs_new, alpha=alpha, power=power))
