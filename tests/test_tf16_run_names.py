"""TF16-8 to TF16-12: a name given at sweep time (``poisson-prove sweep --name``, written into the
run's manifest as ``name``) is read as the run's name, below a name in ``trace-names.toml``
(spec section 16.1 step 1, sections 5.2, 5.3 and 17.6; Prove's spec section 4.3 with its
rulings of 2026-10-23 and 2026-10-24).

- TF16-8: a run named at sweep time goes by that name in every output, and every verb takes it;
  a store with no such names is named as before.
- TF16-9: a name of yours ranks above it, and every name a run has still reaches it: yours, the
  sweep-time one, the computed one and the id. Forgetting yours gives the sweep-time one back.
- TF16-10: a sweep-time name another run also answers to is refused when typed, never guessed;
  and ``name`` and ``import`` refuse to give a run a name another run has from its manifest.
- TF16-11: a sweep-time name that could not be typed back as a name is passed over, and the run
  goes by its computed name; one with spaces at either end goes by it trimmed.
- TF16-12: Trace and Prove name every run alike and take every word to the same run, read
  through Prove's public ``poisson_prove.compare``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tf16_support import (  # noqa: F401
    COMPUTED, EVENT, NEW, NEW_AFTER, NEW_BEFORE, OLD, OLD_A, OLD_B, REPO, SWEEP_NAMES, Made,
    copies, copy_store, make_store, resolved, run_names, scratch_home, snapshot, trace,
)

FIX_CHECK = ["--event", EVENT, "--inputs", "all", "--max-mde", "0.5"]
DAY1, DAY2 = "2026-10-01T10:00:00Z", "2026-10-02T10:00:00Z"
X, Y = "20261001T100000Z-aaaa", "20261002T100000Z-bbbb"


def _names_file(store: Path, entries: dict[str, str]) -> None:
    """``trace-names.toml`` as section 5.2 writes it."""
    lines = ["# Poisson Trace: your names for the runs in this store. Written by `poisson-trace name`.",
             "version = 1", "", "[names]", *(f'"{k}" = "{v}"' for k, v in entries.items())]
    (store / "trace-names.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------- TF16-8 ----------


def test_tf16_8_a_run_named_at_sweep_time_goes_by_that_name(tmp_path: Path) -> None:
    old, new = copies(tmp_path)
    assert run_names(new) == SWEEP_NAMES
    assert run_names(old) == {OLD_A: COMPUTED[0], OLD_B: COMPUTED[1]}
    # the three-tools recipe's commands (section 17.6 step 4)
    for argv in (["fix-check", "agent before", "agent after", *FIX_CHECK],
                 ["where", "agent before", "--event", EVENT]):
        ran = trace([*argv, "--store", new, "--json"])
        assert ran.code in (0, 2), ran.text
        doc = ran.json()
        runs = [doc["run"]] if "run" in doc else [doc["runs"]["old"], doc["runs"]["new"]]
        assert [(r["run_id"], r["run_name"]) for r in runs] == [
            (run_id, SWEEP_NAMES[run_id]) for run_id in (NEW_BEFORE, NEW_AFTER)[: len(runs)]
        ]
        text = trace([*argv, "--store", new])
        assert text.code == ran.code, text.text
        for run in runs:
            assert f'{run["run_name"]} ({run["run_id"]})' in text.out, text.out
    listing = trace(["runs", "--store", new])
    assert all(name in listing.out for name in SWEEP_NAMES.values()), listing.out


# ---------- TF16-9 ----------


def test_tf16_9_a_name_of_yours_ranks_above_the_sweep_time_name_and_every_name_still_reaches(tmp_path: Path) -> None:
    store = copy_store(NEW, tmp_path / "store")
    ran = trace(["name", "agent before", "baseline", "--store", store])
    assert ran.code == 0, ran.text
    assert run_names(store) == {NEW_BEFORE: "baseline", NEW_AFTER: "agent after"}
    for word in ("baseline", "agent before", COMPUTED[0], NEW_BEFORE):
        assert resolved(store, word) == NEW_BEFORE, word
    ran = trace(["name", "baseline", "--forget", "--store", store])
    assert ran.code == 0, ran.text
    assert run_names(store) == SWEEP_NAMES


# ---------- TF16-10 ----------

# a sweep-time name of X that another run, Y, also answers to, and how Y answers to it
COLLISIONS = {
    "Y's own sweep-time name": ("agent", {"y_name": "agent"}),
    "Y's computed name": ("mock-agent 2026-10-02 a", {}),
    "Y's id": (Y, {}),
    "a name of yours for Y": ("agent", {"yours": {"agent": Y}}),
}


@pytest.mark.parametrize("case", list(COLLISIONS))
def test_tf16_10_a_word_two_runs_answer_to_is_refused_never_guessed(tmp_path: Path, case: str) -> None:
    word, how = COLLISIONS[case]
    # alone, X answers to its sweep-time name
    alone = make_store(tmp_path / "alone", [Made(X, DAY1, word)])
    assert resolved(alone, word) == X
    # beside Y, which answers to the same word, neither is guessed
    store = make_store(tmp_path / "store", [Made(X, DAY1, word), Made(Y, DAY2, how.get("y_name"))])
    if "yours" in how:
        _names_file(store, how["yours"])
    ran = trace(["where", word, "--store", store, "--event", EVENT, "--json"])
    assert ran.code == 1 and ran.out == "", ran.text
    first = ran.err.splitlines()[0]
    assert first.startswith("error: ") and X in first and Y in first, first


def test_tf16_10_name_and_import_refuse_a_name_another_run_has_from_its_manifest(tmp_path: Path) -> None:
    store = make_store(tmp_path / "store", [Made(X, DAY1, "agent"), Made(Y, DAY2)])
    before = snapshot(store)
    ran = trace(["name", Y, "agent", "--store", store])
    assert ran.code == 1 and ran.err.startswith("error: ") and '"agent"' in ran.err.splitlines()[0], ran.text
    report = REPO / "tests" / "fixtures" / "ingest" / "junit" / "trace-suite-1.xml"
    ran = trace(["import", "junit", report, "--store", store, "--run", "agent"])
    assert ran.code == 1 and ran.err.startswith("error: ") and '"agent"' in ran.err.splitlines()[0], ran.text
    assert snapshot(store) == before
    # the same two commands with a name no run has: the refusals were for the name alone
    assert trace(["name", Y, "free", "--store", store]).code == 0
    assert trace(["import", "junit", report, "--store", store, "--run", "free-run"]).code == 0


# ---------- TF16-11 ----------

UNFIT = {
    "latest": "latest",
    "previous:": "previous:mock-agent",
    "a number": "#1",
    "a dash first": "-agent",
    "81 characters": "x" * 81,
    "two lines": "two\nlines",
    "a control character": "bell\x07",
    "only spaces": "   ",
}


@pytest.mark.parametrize("case", list(UNFIT))
def test_tf16_11_a_sweep_time_name_that_cannot_be_a_name_is_passed_over(tmp_path: Path, case: str) -> None:
    store = make_store(tmp_path / "store", [Made(X, DAY1, UNFIT[case])])
    assert run_names(store) == {X: "mock-agent 2026-10-01 a"}
    assert resolved(store, "mock-agent 2026-10-01 a") == X


def test_tf16_11_a_sweep_time_name_is_read_trimmed(tmp_path: Path) -> None:
    store = make_store(tmp_path / "store", [Made(X, DAY1, "  agent before\t")])
    assert run_names(store) == {X: "agent before"}
    assert resolved(store, "agent before") == X


# ---------- TF16-12 ----------


def _store(tmp_path: Path, case: str) -> Path:
    if case == "0.0.1":
        return copy_store(OLD, tmp_path / "store")
    if case == "0.1.0, with a name of yours":
        store = copy_store(NEW, tmp_path / "store")
        _names_file(store, {"baseline": NEW_BEFORE})
        return store
    # names Prove passes over, trims or finds twice, beside a run with none
    return make_store(tmp_path / "store", [
        Made("20261001T100000Z-aaaa", DAY1, "latest"),
        Made("20261001T110000Z-bbbb", "2026-10-01T11:00:00Z", " padded "),
        Made("20261002T100000Z-cccc", DAY2, "twin"),
        Made("20261002T110000Z-dddd", "2026-10-02T11:00:00Z", "twin"),
        Made("20261002T120000Z-eeee", "2026-10-02T12:00:00Z"),
    ])


@pytest.mark.parametrize("case", ["0.0.1", "0.1.0, with a name of yours", "names to pass over"])
def test_tf16_12_trace_and_prove_name_every_run_alike_and_resolve_every_word_alike(tmp_path: Path, case: str) -> None:
    from poisson_prove import compare

    store = _store(tmp_path, case)
    listed = compare.runs(store)
    assert run_names(store) == {r.run_id: r.run_name for r in listed}
    words = {"latest", "previous", "#1", "#2", "#9", "twin", "padded", "baseline", "agent before"}
    for r in listed:
        words |= {r.run_id, r.run_name}
    words |= {f"mock-agent 2026-10-0{d} {c}" for d in (1, 2) for c in "abc"} | set(COMPUTED)
    for word in sorted(words):
        try:
            prove: str | None = compare.resolve(store, word)
        except compare.Refusal:
            prove = None
        assert resolved(store, word) == prove, word
    shutil.rmtree(store)
