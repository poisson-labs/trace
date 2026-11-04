"""TF21-45 to TF21-50: TF21's per-try records convert without loss into the plain per-case inputs
``stats/continuous.py`` takes (TF23, CT2): each try's values, how it ended, its signals and its
repeat number. A conversion test only: no verb prints the continuous table yet (CT2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tf21_support import STARTED, TAU2

from poisson_trace.ingest.prove import read_rows
from poisson_trace.ingest.rows import Row, Run
from poisson_trace.ingest.tries import tries_of, version_of
from poisson_trace.ingest.writer import write
from poisson_trace.stats import continuous
from poisson_trace.stats.continuous import MEASURES, Try, Version

TAU2_A, TAU2_B = "20260915T210140Z-4847", "20260915T211148Z-965d"

ROWS = [
    Row("c1", "met", None, 0.9, result="pass", repeat=0, wall_time_s=1.0, input_chars=10,
        output_chars=0, input_tokens=3, output_tokens=4, cost_usd=0.0, working_time_s=0.5),
    Row("c1", "missed", None, 0.1, result="fail", repeat=1, failure_kind="wrong_answer",
        wall_time_s=2.0, signals=("retry_storm",)),
    Row("c2", None, "timeout", result="censored", repeat=0, failure_kind="timeout",
        wall_time_s=30.0, signals=("over_budget",)),
    Row("c3", "met", None, result="pass"),
]


# ---------- TF21-45: every measure, its value or None ----------


def test_tf21_45_each_try_carries_every_measure() -> None:
    cases = tries_of(ROWS)
    assert set(cases) == {"c1", "c2", "c3"}
    first = cases["c1"][0]
    assert isinstance(first, Try)
    assert set(first.values) == set(MEASURES)
    assert dict(first.values) == {
        "wall_time_s": 1.0, "working_time_s": 0.5, "input_chars": 10, "output_chars": 0,
        "input_tokens": 3, "output_tokens": 4, "total_tokens": 7, "cost_usd": 0.0,
    }
    assert dict(cases["c3"][0].values) == dict.fromkeys(MEASURES)


def test_tf21_45_a_recorded_zero_stays_a_zero() -> None:
    first = tries_of(ROWS)["c1"][0]
    assert first.values["output_chars"] == 0 and first.values["cost_usd"] == 0.0
    assert first.values["output_chars"] is not None


# ---------- TF21-46: how it ended, its signals, its repeat ----------


def test_tf21_46_ending_is_the_failure_kind_and_none_for_a_finished_try() -> None:
    cases = tries_of(ROWS)
    assert [t.ending for t in cases["c1"]] == [None, "wrong_answer"]
    assert cases["c2"][0].ending == "timeout"
    assert cases["c3"][0].ending is None


def test_tf21_46_signals_and_repeat_carry_over() -> None:
    cases = tries_of(ROWS)
    assert [tuple(t.signals) for t in cases["c1"]] == [(), ("retry_storm",)]
    assert tuple(cases["c2"][0].signals) == ("over_budget",)
    assert [t.repeat for t in cases["c1"]] == [0, 1]
    assert cases["c3"][0].repeat is None  # no order was recorded


def test_tf21_46_tries_keep_their_read_order_within_a_case() -> None:
    rows = [Row("c", "met", None, result="pass", repeat=2, wall_time_s=3.0),
            Row("c", "met", None, result="pass", repeat=0, wall_time_s=1.0)]
    assert [t.repeat for t in tries_of(rows)["c"]] == [2, 0]


# ---------- TF21-47: nothing is lost: back from the try, the record's measures ----------


def test_tf21_47_round_trip_through_the_store_loses_nothing(tmp_path: Path) -> None:
    root = tmp_path / "store"
    rows = [r for r in ROWS]
    write(Run("imp", "table", tuple(Row(r.case, r.outcome, r.error, r.score,
                                         **{k: getattr(r, k) for k in (
                                             "result", "failure_kind", "wall_time_s",
                                             "working_time_s", "input_chars", "output_chars",
                                             "input_tokens", "output_tokens", "cost_usd",
                                             "signals")}) for r in rows),
              STARTED, "given", {}, ()), root)
    back = read_rows(root, "imp", failed=())
    direct, stored = tries_of(ROWS), tries_of(back)
    assert set(direct) == set(stored)
    for case in direct:
        a = sorted(direct[case], key=lambda t: (t.repeat is None, t.repeat))
        b = sorted(stored[case], key=lambda t: (t.repeat is None, t.repeat))
        assert [dict(t.values) for t in a] == [dict(t.values) for t in b]
        assert [t.ending for t in a] == [t.ending for t in b]
        assert [tuple(t.signals) for t in a] == [tuple(t.signals) for t in b]


# ---------- TF21-48: version_of ----------


def test_tf21_48_version_of_names_labels_and_caps() -> None:
    v = version_of(ROWS, "run-a", label="new", cap_s=30.0)
    assert isinstance(v, Version)
    assert (v.name, v.label, v.cap_s) == ("run-a", "new", 30.0)
    assert dict(v.cases) == dict(tries_of(ROWS))
    assert version_of(ROWS, "x").label == "old" and version_of(ROWS, "x").cap_s is None


def test_tf21_48_an_unscored_try_is_kept_with_its_measures() -> None:
    rows = [Row("u", None, "skipped", wall_time_s=0.25)]
    assert tries_of(rows)["u"][0].values["wall_time_s"] == 0.25


# ---------- TF21-49: two real Prove runs compare through continuous.compare ----------


def test_tf21_49_tau2_converts_and_compares() -> None:
    a = version_of(read_rows(TAU2, TAU2_A, failed=("unsolved",)), TAU2_A, label="old")
    b = version_of(read_rows(TAU2, TAU2_B, failed=("unsolved",)), TAU2_B, label="new")
    assert len(a.cases) == len(b.cases) == 50
    assert sum(len(t) for t in a.cases.values()) == 200
    comparison = continuous.compare(a, b)
    measures = comparison.measures
    assert set(measures) == set(MEASURES)
    assert measures["wall_time_s"].k_total == 50
    for name in ("input_chars", "output_chars", "cost_usd", "working_time_s"):
        assert measures[name].status == "not_recorded", name
    for name in ("wall_time_s", "input_tokens", "output_tokens", "total_tokens"):
        assert measures[name].status != "not_recorded", name


@pytest.mark.parametrize("measure", ["wall_time_s", "input_tokens"])
def test_tf21_49_per_try_values_match_the_store(measure: str) -> None:
    from poisson_prove.store import Store

    df = Store(TAU2).read(TAU2_A, meta=True, trace="full")
    cases = version_of(read_rows(TAU2, TAU2_A, failed=()), TAU2_A).cases
    got = sorted((c, t.repeat, t.values[measure]) for c, ts in cases.items() for t in ts)
    if measure == "wall_time_s":
        want = sorted((h, int(r), float(w)) for h, r, w in
                      zip(df["config_hash"], df["replicate_index"], df["wall_time"], strict=True))
    else:
        want = []
        for h, r, m in zip(df["config_hash"], df["replicate_index"], df["meta"], strict=True):
            spans = (m.get("trace") or {}).get("spans") or []
            ins = [s["tokens"]["in"] for s in spans if s.get("tokens") and "in" in s["tokens"]]
            want.append((h, int(r), sum(ins) if ins else None))
        want.sort(key=lambda x: (x[0], x[1]))
    assert got == want


# ---------- TF21-50: no verb prints it (CT2) ----------


def test_tf21_50_no_verb_imports_the_conversion() -> None:
    import ast

    import poisson_trace

    package = Path(poisson_trace.__file__).resolve().parent
    for path in [package / "cli.py", package / "summary.py", package / "report.py",
                 package / "ingest" / "cli.py"]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {node.module for node in ast.walk(tree)
                 if isinstance(node, ast.ImportFrom) and node.module}
        names |= {a.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                  for a in node.names}
        assert "poisson_trace.ingest.tries" not in names, path.name
        assert "poisson_trace.stats.continuous" not in names, path.name
