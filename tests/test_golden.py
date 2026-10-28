"""TR32 to TR36: the goldens on the committed fixtures and the synthetic store. Every figure
was recomputed from the spec's definitions (sections 2 and 3) on the fixtures before it was
pinned here; see tests/fixtures/PROVENANCE.md."""

from __future__ import annotations

import numpy as np
import pytest
from proofload.store import Store

from conftest import (
    CS, CS_EVENTS, CS_RECORD, CS_REPLAY, SYNTH_COUNTS, SYNTH_DECLARED, SYNTH_EVENTS, TAU2, TAU2_A,
    TAU2_B, TAU2_EVENTS, compare, where,
)


def _steps(root, run, events):  # type: ignore[no-untyped-def]
    from poisson_trace.clock import place

    store = Store(root)
    placed = place(store.manifest(run), store.read(run, meta=False, trace="envelope"), store.tally(run),
                   events=frozenset(events), by="kind")
    index = np.array([p.index for p in placed.rows])
    return placed, (int(index.min()), int(np.median(index)), int(index.max()))


def _where(root, run, events):  # type: ignore[no-untyped-def]
    result = where(root, run, events, "--at", "10", "--at", "20", "--at", "30", "--json")
    assert result.code == 0, result.text
    return result.json()


# ---------- TR32 ----------


def test_tr32_golden_tau2_a() -> None:
    data = _where(TAU2, TAU2_A, TAU2_EVENTS)
    placement = data["run"]["placement"]
    assert (placement["placed"], placement["died"], placement["ended"]) == (200, 110, 90)
    assert (placement["timed out"], placement["capped"]) == (0, 0)
    assert sum(placement["excluded"].values()) == 0
    _, steps = _steps(TAU2, TAU2_A, TAU2_EVENTS)
    assert steps == (6, 18, 44)
    # ST8 (ruled 2026-10-20): finishing and timing out are ends of their own; the share not yet
    # failed is counts over tries here, nothing being censored (the statistics check's episode dumps)
    at = {row["step"]: row["survival"] for row in data["at"]}
    assert at[10] == pytest.approx(0.965, abs=1e-3)
    assert at[20] == pytest.approx(0.695, abs=1e-3)
    assert at[30] == pytest.approx(0.490, abs=1e-3)
    assert data["median_step"] == 20
    assert [(c["cause"], c["deaths"]) for c in data["causes"]] == [("llm", 110)]
    assert data["causes"][0]["f"] == pytest.approx(0.55, abs=1e-12)
    first = data["curve"][0]
    assert (first["step"], first["at_risk"], first["died"]) == (9, 197, 5)
    assert first["survival"] == pytest.approx(0.975, abs=1e-3)
    assert data["curve"][-1]["step"] == 44


# ---------- TR33 ----------


def test_tr33_golden_tau2_b() -> None:
    data = _where(TAU2, TAU2_B, TAU2_EVENTS)
    placement = data["run"]["placement"]
    assert (placement["placed"], placement["died"], placement["ended"]) == (200, 112, 88)
    _, steps = _steps(TAU2, TAU2_B, TAU2_EVENTS)
    assert steps == (6, 17, 40)
    # ST8 (ruled 2026-10-20): finishing and timing out are ends of their own; the share not yet
    # failed is counts over tries here, nothing being censored (the statistics check's episode dumps)
    at = {row["step"]: row["survival"] for row in data["at"]}
    assert at[10] == pytest.approx(0.970, abs=1e-3)
    assert at[20] == pytest.approx(0.655, abs=1e-3)
    assert at[30] == pytest.approx(0.500, abs=1e-3)
    assert data["median_step"] == 19
    assert [(c["cause"], c["deaths"]) for c in data["causes"]] == [("llm", 112)]


# ---------- TR34 ----------


def test_tr34_golden_comparison() -> None:
    tight = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.3, "--json")
    assert tight.code == 0, tight.text  # R17: a result exits 0, too small to tell included
    c = tight.json()["comparison"]
    assert c["cells"] == 50
    assert c["excluded_cells"] == {"a_only": 0, "b_only": 0}
    assert c["observed_a"] == 110
    assert c["expected_a"] == pytest.approx(113.805, abs=1e-3)
    assert c["variance"] == pytest.approx(35.223, abs=1e-3)
    assert c["statistic"] == pytest.approx(0.411, abs=1e-3)
    assert c["p"] == pytest.approx(0.5215, abs=1e-3)
    # ST5 (ruled 2026-10-20): exp((z_0.975 + z_0.8) / sqrt(V)), the statistics check's 1.603
    assert c["mde_hazard_ratio"] == pytest.approx(1.603, abs=1e-3)
    assert c["verdict"] == "too small to tell"
    assert "earlier in B" in c["direction"]
    md_tight = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.3)
    assert md_tight.code == 0 and "too small to tell" in md_tight.out  # R17: a result exits 0, too small to tell included
    assert "unpaired" in md_tight.out
    loose = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.604)
    assert loose.code == 0, loose.text
    assert "no significant difference" in loose.out
    assert compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.604, "--json").json()["comparison"]["verdict"] == "no significant difference"
    assert compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.5, "--json").json()["comparison"]["verdict"] == "too small to tell"
    per = tight.json()["per_cause"]
    assert [(r["cause"], r["deaths_a"], r["deaths_b"]) for r in per] == [("llm", 110, 112)]
    assert per[0]["statistic"] == pytest.approx(0.411, abs=1e-3)
    assert per[0]["q"] == pytest.approx(per[0]["p"], abs=1e-12)


# ---------- TR35 ----------


def test_tr35_golden_cs_record_and_replay() -> None:
    result = where(CS, CS_RECORD, CS_EVENTS, "--json")
    assert result.code == 0, result.text
    data = result.json()
    placement = data["run"]["placement"]
    assert (placement["placed"], placement["died"], placement["ended"]) == (24, 7, 17)
    _, steps = _steps(CS, CS_RECORD, CS_EVENTS)
    assert steps == (14, 31, 59)
    # ST8 (ruled 2026-10-20): finishing and timing out are ends of their own; the share not yet
    # failed is counts over tries here, nothing being censored (the statistics check's episode dumps)
    assert data["median_step"] == 35
    causes = {c["cause"]: c for c in data["causes"]}
    assert [c["cause"] for c in data["causes"]] == ["llm", "agent"]
    assert (causes["agent"]["deaths"], causes["llm"]["deaths"]) == (3, 4)
    assert data["curve"][-1]["step"] == 58
    assert causes["agent"]["f"] == pytest.approx(3 / 24, abs=1e-3)
    assert causes["llm"]["f"] == pytest.approx(4 / 24, abs=1e-3)
    assert causes["agent"]["f"] + causes["llm"]["f"] == pytest.approx(1 - data["curve"][-1]["survival"], abs=1e-12)
    assert data["run"]["cap"] is None
    replay = where(CS, CS_REPLAY, CS_EVENTS, "--json")
    assert replay.code == 0, replay.text
    rp = replay.json()["run"]["placement"]
    assert rp["placed"] == 21
    assert rp["excluded"]["no outcome, not a timeout"] == 3
    assert rp["died"] == 7
    assert replay.json()["run"]["tally"]["other"] == 3


# ---------- TR36 ----------


def test_tr36_golden_synthetic_store(synth) -> None:  # type: ignore[no-untyped-def]
    root, run = synth
    result = where(root, run, SYNTH_EVENTS, "--json")
    assert result.code == 0, result.text
    data = result.json()
    header = data["run"]
    assert header["tally"] == {k: SYNTH_COUNTS[k] for k in ("rows", "with_outcome", "no_outcome", "timed_out", "infra", "other")}
    assert header["placement"] == {
        "placed": SYNTH_COUNTS["placed"], "died": SYNTH_COUNTS["died"], "ended": SYNTH_COUNTS["ended"],
        "timed out": SYNTH_COUNTS["timed out"], "capped": SYNTH_COUNTS["capped"],
        "excluded": SYNTH_COUNTS["excluded"],
    }
    assert header["cap"] == 6
    assert [(c["step"], c["at_risk"], c["died"]) for c in data["curve"]] == [(2, 4, 1)]
    # ST8 (ruled 2026-10-20): the time-out at 2 is an end of its own and the capped try censored;
    # a quarter failed by step 2; no Greenwood variance; the median failed step is 2
    assert data["curve"][0]["survival"] == pytest.approx(0.75, abs=1e-12)
    assert data["curve"][0]["var"] is None
    assert data["median_step"] == 2
    assert [(c["cause"], c["deaths"]) for c in data["causes"]] == [("llm", 1)]
    assert data["causes"][0]["f"] == 0.25
    assert "declared" in data and set(data["declared"]["declared_steps"]) == set(SYNTH_DECLARED.steps)
    assert data["declared"]["never_reached"] == ["check"]
    by_step = where(root, run, SYNTH_EVENTS, "--by", "step", "--json").json()
    assert [(c["cause"], c["deaths"]) for c in by_step["causes"]] == [("plan", 1)]
    assert by_step["clock"]["by"] == "step"
