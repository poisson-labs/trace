"""TR57 to TR60 through the command line, and the ``changes`` verb's own JSON, bytes and
refusals: the per-input flags against Prove's public statistics, Fisher's test on each input then
Benjamini and Hochberg's correction (``poisson_prove.stats``, a dev oracle, imported inside the test),
that no row carries a per-input limit, the attainability numbers, and the
order and length of the flags table."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from scipy import stats

from conftest import TAU2, TAU2_A, TAU2_B, norm
from fixcheck_support import (
    CHANGES_KEYS, FLAG_ROW_KEYS, HE_A, HE_B, HE_EVENTS, HEADER_KEYS, HUMANEVAL, PILOT, TAU2_EVENTS,
    Obs, build_run, changes, fix_check, ok, one_sentence, pair_store,
)


def _json(result):  # type: ignore[no-untyped-def]
    assert result.code == 0, result.text
    return result.json()


def _fisher(xa: int, na: int, xb: int, nb: int) -> float:
    return float(stats.fisher_exact([[xa, na - xa], [xb, nb - xb]], alternative="two-sided")[1])


# ---------- TR57 ----------


def _prove_cells(root: Path, a: str, b: str, event: str, alpha: float):  # type: ignore[no-untyped-def]
    from poisson_prove.stats import bh, fisher_test
    from poisson_prove.store import Store

    store = Store(root)

    def counts(run: str) -> dict[str, tuple[int, int]]:
        # a row with no outcome is left out, as Prove's own comparison leaves it out
        rows = store.read(run)
        rows = rows[rows["outcome"].notna()]
        failed = (rows["outcome"] == event).groupby(rows["config_hash"].astype(str))
        return {h: (int(f.sum()), int(len(f))) for h, f in failed}

    ca, cb = counts(a), counts(b)
    common = sorted(set(ca) & set(cb))
    p = [fisher_test(*ca[h], *cb[h])[1] for h in common]
    q = bh(p, alpha)
    return {h: {"p": p[i], "q": float(q[i]), "flag": bool(q[i] < alpha)} for i, h in enumerate(common)}


@pytest.mark.parametrize("alpha", [0.05, 0.2])
def test_tr57_the_flags_are_proves_on_the_tau2_pair(alpha: float) -> None:
    d = _json(changes(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, "--alpha", str(alpha), "--json"))
    prove = _prove_cells(TAU2, TAU2_A, TAU2_B, "unsolved", alpha)
    rows = {r["config_hash"]: r for r in d["rows"]}
    assert set(rows) == set(prove) and len(rows) == 50
    for h, r in rows.items():
        assert r["p"] == pytest.approx(float(prove[h]["p"]), abs=1e-12)
        assert r["q"] == pytest.approx(float(prove[h]["q"]), abs=1e-12)
    flagged = {h for h, r in rows.items() if r["flag"] is not None}
    assert flagged == {h for h, c in prove.items() if c["flag"]}
    assert d["flagged"] == len(flagged)


def test_tr57_the_flags_are_proves_on_the_humaneval_pair_for_one_event() -> None:
    d = _json(changes(HUMANEVAL, HE_A, HE_B, ["failed_assertion"], "--json"))
    prove = _prove_cells(HUMANEVAL, HE_A, HE_B, "failed_assertion", 0.05)
    rows = {r["config_hash"]: r for r in d["rows"]}
    assert set(rows) == set(prove) and len(rows) == 328
    for h, r in rows.items():
        assert r["p"] == pytest.approx(float(prove[h]["p"]), abs=1e-12)
        assert r["q"] == pytest.approx(float(prove[h]["q"]), abs=1e-12)
        assert (r["flag"] is not None) == prove[h]["flag"]
    assert {r["config"]["task_id"] for r in d["rows"] if r["flag"]} == {"HumanEval/129"}


def test_tr57_each_row_is_fisher_on_its_counts_and_flagged_by_its_q(tmp_path: Path) -> None:
    from poisson_prove.stats import bh

    tab = [(0, 12, 12, 12), (12, 12, 0, 12), (3, 6, 2, 5), (1, 3, 2, 7)] + [(4, 8, 4, 8)] * 6
    root = pair_store(tmp_path, tab)
    d = _json(changes(root, "old", "new", ["fail"], "--json"))
    ps = [r["p"] for r in d["rows"]]
    qs = bh(ps, 0.05)
    for r, q in zip(d["rows"], qs):
        assert r["p"] == pytest.approx(_fisher(r["failed_a"], r["runs_a"], r["failed_b"], r["runs_b"]), abs=1e-12)
        assert r["q"] == pytest.approx(float(q), abs=1e-12)
        change = r["failed_b"] / r["runs_b"] - r["failed_a"] / r["runs_a"]
        assert r["change"] == pytest.approx(change, abs=1e-12)
        expected = None if not r["q"] < 0.05 else ("failed more in B" if change > 0 else "failed less in B")
        assert r["flag"] == expected
    assert sorted(r["flag"] for r in d["rows"] if r["flag"]) == ["failed less in B", "failed more in B"]


# ---------- TR58 ----------


def test_tr58_no_row_carries_a_per_input_limit() -> None:
    """No row carries a per-input limit, in the table or the JSON, at any alpha (no value it
    could print is reached 4 times in 5 by the flag Trace raises)."""
    for root, a, b, events in ((TAU2, TAU2_A, TAU2_B, TAU2_EVENTS), (TAU2, TAU2_B, PILOT, TAU2_EVENTS)):
        for alpha in ("0.05", "0.1"):
            d = _json(changes(root, a, b, events, "--alpha", alpha, "--json"))
            assert d["rows"] and all(set(r) == FLAG_ROW_KEYS for r in d["rows"])
            assert "could not have detected a rise below" not in ok(changes(root, a, b, events, "--alpha", alpha)).out


# ---------- TR59 ----------


def _attainability(rows, alpha):  # type: ignore[no-untyped-def]
    m = len(rows)
    smallest = min(_fisher(0, r["runs_a"], r["runs_b"], r["runs_b"]) for r in rows)
    together = next((j for j in range(1, m + 1) if smallest * m / j < alpha), None)
    n = 1
    while _fisher(0, n, n, n) > alpha / m:
        n += 1
    return alpha / m, smallest, together, n


def _check_attainability(d) -> None:  # type: ignore[no-untyped-def]
    lone, smallest, together, n = _attainability(d["rows"], d["alpha"])
    assert d["lone_threshold"] == pytest.approx(lone, abs=1e-15)
    assert d["smallest_attainable_p"] == pytest.approx(smallest, rel=1e-9, abs=1e-300)
    assert d["together"] == together
    assert d["lone_flip_repeats"] == n


def test_tr59_on_the_tau2_pair() -> None:
    d = _json(changes(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, "--json"))
    assert d["lone_threshold"] == pytest.approx(0.001, abs=1e-12)
    assert d["smallest_attainable_p"] == pytest.approx(0.028571, abs=1e-6)
    assert (d["together"], d["lone_flip_repeats"]) == (29, 7)
    _check_attainability(d)
    text = norm(ok(changes(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS)).out)
    assert "a lone changed input cannot be flagged" in text
    assert "at least 29 inputs would have to flip" in text
    assert "a lone complete flip needs 7 repeats per arm" in text


def test_tr59_on_the_humaneval_pair() -> None:
    d = _json(changes(HUMANEVAL, HE_A, HE_B, HE_EVENTS, "--json"))
    assert d["lone_threshold"] == pytest.approx(0.05 / 328, abs=1e-15)
    assert d["smallest_attainable_p"] == pytest.approx(1.0913e-18, rel=1e-3)
    _check_attainability(d)
    assert "a lone change can be flagged" in norm(ok(changes(HUMANEVAL, HE_A, HE_B, HE_EVENTS)).out)


def test_tr59_on_the_patched_pilot_nothing_can_be_flagged() -> None:
    d = _json(changes(TAU2, TAU2_A, PILOT, TAU2_EVENTS, "--json"))
    assert d["tested"] == 10
    assert d["lone_threshold"] == pytest.approx(0.005, abs=1e-12)
    assert d["smallest_attainable_p"] == pytest.approx(0.2, abs=1e-12)
    assert d["together"] is None
    _check_attainability(d)
    assert "no input can be flagged whatever happens" in norm(ok(changes(TAU2, TAU2_A, PILOT, TAU2_EVENTS)).out)


def test_tr59_on_an_unbalanced_design(tmp_path: Path) -> None:
    root = pair_store(tmp_path, [(1, 3, 2, 5), (0, 6, 1, 2), (2, 4, 4, 4), (0, 1, 1, 9)])
    _check_attainability(_json(changes(root, "old", "new", ["fail"], "--json")))


# ---------- TR60 ----------


_CONFIG = re.compile(r"\{\"task_id\":[^|]*?\}")


def _printed(text: str) -> list[str]:
    return _CONFIG.findall(text)


def _compact(config) -> str:  # type: ignore[no-untyped-def]
    return json.dumps(config, sort_keys=True, separators=(",", ":"))


def test_tr60_the_json_lists_every_input_sorted_by_p_then_hash() -> None:
    for root, a, b, events in ((TAU2, TAU2_A, TAU2_B, TAU2_EVENTS), (HUMANEVAL, HE_A, HE_B, HE_EVENTS)):
        d = _json(changes(root, a, b, events, "--json"))
        assert len(d["rows"]) == d["tested"]
        keys = [(r["p"], r["config_hash"]) for r in d["rows"]]
        assert keys == sorted(keys)
        assert all(set(r) == FLAG_ROW_KEYS for r in d["rows"])


@pytest.mark.parametrize("top,expect", [(None, 10), ("3", 3), ("1", 1)])
def test_tr60_the_markdown_shows_top_rows_on_the_tau2_pair(top: str | None, expect: int) -> None:
    extra = () if top is None else ("--top", top)
    d = _json(changes(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, "--json", *extra))
    printed = _printed(ok(changes(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *extra)).out)
    assert printed == [_compact(r["config"]) for r in d["rows"][:expect]]


@pytest.mark.parametrize("top,expect", [("1", 2), ("2", 2), ("5", 5)])
def test_tr60_every_flagged_row_prints_whatever_top_says(top: str, expect: int) -> None:
    d = _json(changes(HUMANEVAL, HE_A, HE_B, HE_EVENTS, "--json", "--top", top))
    printed = _printed(ok(changes(HUMANEVAL, HE_A, HE_B, HE_EVENTS, "--top", top)).out)
    assert printed == [_compact(r["config"]) for r in d["rows"][:expect]]
    assert printed[:2] == ['{"task_id":"HumanEval/129","temperature":0.7}', '{"task_id":"HumanEval/129","temperature":0.0}']


def test_tr60_the_fix_check_carries_the_same_table() -> None:
    fc = fix_check(HUMANEVAL, HE_A, HE_B, HE_EVENTS, "--inputs", "all", "--max-mde", "0.05", "--json")
    ok(fc)
    ch = _json(changes(HUMANEVAL, HE_A, HE_B, HE_EVENTS, "--json"))
    block = fc.json()["changes"]
    for key in ("tested", "flagged", "alpha", "lone_threshold", "smallest_attainable_p", "together", "lone_flip_repeats", "rows"):
        assert block[key] == ch[key], key
    printed = _printed(fix_check(HUMANEVAL, HE_A, HE_B, HE_EVENTS, "--inputs", "all", "--max-mde", "0.05", "--top", "4").out)
    assert printed == [_compact(r["config"]) for r in ch["rows"][:4]]


# ---------- the changes JSON and refusals (TR61, TR41) ----------


def test_tr61_changes_json_keys_and_bytes() -> None:
    a = changes(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, "--json")
    b = changes(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, "--json")
    d = _json(a)
    assert a.out == b.out
    assert tuple(d) == CHANGES_KEYS
    assert d["schema"] == "poisson-trace.changes/2"  # no per-input limit
    assert set(d["runs"]) == {"a", "b"} and all(set(h) == HEADER_KEYS for h in d["runs"].values())
    assert d["events"] == ["unsolved"] and d["alpha"] == 0.05
    assert (d["tested"], d["flagged"]) == (50, 0)
    assert "NaN" not in a.out and "Infinity" not in a.out
    he = changes(HUMANEVAL, HE_A, HE_B, HE_EVENTS)
    assert he.code == 0 and he.err == ""


def test_tr41_changes_refusals(tmp_path: Path) -> None:
    ok(changes(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS))
    one_sentence(changes(TAU2, TAU2_A, TAU2_B, ["max_steps"]))
    build_run(tmp_path, "a", [Obs("x", "fail")])
    build_run(tmp_path, "b", [Obs("y", "fail")])
    one_sentence(changes(tmp_path, "a", "b", ["fail"]))
    build_run(tmp_path, "c", [Obs("x", None, "timeout")])
    one_sentence(changes(tmp_path, "a", "c", ["fail"]))
