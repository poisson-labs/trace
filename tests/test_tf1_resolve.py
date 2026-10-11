"""TF1-4 and TF1-5: wherever a verb takes a run, the words it takes (spec section 5.2, ruling R3).

``latest`` and ``previous`` are the newest and the next newest complete run by start time, and
``latest:TARGET`` and ``previous:TARGET`` the same among one target's runs; ``#N`` is row N of
``poisson-trace runs``, so ``#1`` is ``latest`` and ``#2`` is ``previous``; then a name you gave,
a name from the manifest, and the full run id. A bare four-hex suffix, a prefix of an id, a
word no run answers to and a word two runs answer to are each refused in one line, exit 1,
nothing written: never guessed. The run a word reaches is read from ``where``'s JSON."""

from __future__ import annotations

from pathlib import Path

import pytest

from tf0_support import trace
from tf1_support import (
    T_A, T_B, T_NAMES, T_PILOT, R, make_runs, refused, resolved, run_id, runs_json, snapshot, stamp,
    tau2_copy, write_names,
)

# agent-x runs on 1 and 2 October, one partial in the middle and one partial newest of all;
# one agent-y run between them
X1, X2, X3, X4, X5 = (run_id(1, 10, 0, "0a01"), run_id(1, 11, 0, "0a02"), run_id(1, 12, 0, "0a03"),
                      run_id(2, 9, 0, "0a04"), run_id(2, 10, 0, "0a05"))
Y1 = run_id(1, 13, 0, "0b01")
RUNS = [
    R(X1, stamp(1, 10)), R(X2, stamp(1, 11)), R(X3, stamp(1, 12), status="partial"),
    R(X4, stamp(2, 9)), R(X5, stamp(2, 10), status="partial"),
    R(Y1, stamp(1, 13), target_id="agent-y/model-2@v0"),
]
# complete runs, newest first
NEWEST_FIRST = [X4, Y1, X2, X1]


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return make_runs(tmp_path_factory.mktemp("resolve") / "store", RUNS)


# ---------- TF1-4: the reserved forms ----------


@pytest.mark.parametrize("word,run", [
    ("latest", X4), ("previous", Y1),
    ("latest:agent-x", X4), ("previous:agent-x", X2),
    ("latest:agent-y", Y1),
], ids=["latest", "previous", "latest:agent-x", "previous:agent-x", "latest:agent-y"])
def test_tf1_04_latest_and_previous_are_the_newest_complete_runs(store: Path, word: str, run: str) -> None:
    assert resolved(store, word) == run


@pytest.mark.parametrize("word", ["previous:agent-y", "latest:agent-z", "previous:agent-z", "latest:agent", "latest:agent-", "latest:Agent-x"])
def test_tf1_04_a_target_with_too_few_complete_runs_is_refused(store: Path, word: str) -> None:
    before = snapshot(store)
    refused(trace(["where", word, "--store", str(store), "--event", "fail"]))
    assert snapshot(store) == before


def test_tf1_04_previous_needs_two_complete_runs(tmp_path: Path) -> None:
    one = make_runs(tmp_path / "one", [R("only", stamp(5, 9)), R("half", stamp(5, 10), status="partial")])
    assert resolved(one, "latest") == "only"
    refused(trace(["where", "previous", "--store", str(one), "--event", "fail"]))


def test_tf1_04_no_complete_run_is_latest(tmp_path: Path) -> None:
    half = make_runs(tmp_path / "half", [R("half", stamp(5, 10), status="partial")])
    refused(trace(["where", "latest", "--store", str(half), "--event", "fail"]))
    # a partial run is still named, by its id and by its name from the manifest
    assert resolved(half, "half") == "half"
    assert resolved(half, "agent-x 2026-10-05 a") == "half"


# ---------- TF1-5: numbers ----------


@pytest.mark.parametrize("n", range(1, len(NEWEST_FIRST) + 1))
def test_tf1_05_hash_n_is_row_n_of_the_listing(store: Path, n: int) -> None:
    assert resolved(store, f"#{n}") == NEWEST_FIRST[n - 1]
    rows = {r["number"]: r["run_id"] for r in runs_json(store)["runs"]}
    assert rows[n] == NEWEST_FIRST[n - 1]


def test_tf1_05_hash_one_and_two_are_latest_and_previous(store: Path) -> None:
    assert resolved(store, "#1") == resolved(store, "latest") == X4
    assert resolved(store, "#2") == resolved(store, "previous") == Y1


@pytest.mark.parametrize("word", ["#0", "#5", "#-1", "#x", "#", "#1.0"])
def test_tf1_05_a_number_no_row_has_is_refused(store: Path, word: str) -> None:
    refused(trace(["where", word, "--store", str(store), "--event", "fail"]))


def test_tf1_05_numbers_are_the_same_with_all(store: Path) -> None:
    every = runs_json(store, "--all")["runs"]
    assert {r["run_id"]: r["number"] for r in every} == {
        **{run: i for i, run in enumerate(NEWEST_FIRST, start=1)}, X3: None, X5: None,
    }


# ---------- TF1-4: names and ids ----------


def test_tf1_04_a_full_id_still_names_its_run(store: Path) -> None:
    for run in (X1, X3, Y1):
        assert resolved(store, run) == run


@pytest.mark.parametrize("word", [X4[-4:], X4[:-5], X4[:-1], "agent-x 2026-10-02", "agent-x", "Agent-x 2026-10-02 a", "AGENT-X 2026-10-01 A"])
def test_tf1_04_a_hash_fragment_or_a_part_of_a_name_is_refused(store: Path, word: str) -> None:
    refused(trace(["where", word, "--store", str(store), "--event", "fail"]))


def test_tf1_04_a_word_is_read_trimmed(store: Path) -> None:
    assert resolved(store, "  latest ") == X4
    assert resolved(store, " agent-y 2026-10-01 a\t") == Y1


def test_tf1_04_an_unknown_run_is_refused_naming_the_runs_by_name(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    write_names(store, {"patched pilot": T_PILOT})
    result = trace(["where", "no such run", "--store", str(store), "--event", "unsolved"])
    refused(result)
    for shown in ("patched pilot", T_NAMES[T_A], T_NAMES[T_B]):
        assert shown in result.err, (shown, result.err)


def test_tf1_04_two_runs_answering_to_one_name_is_refused(tmp_path: Path) -> None:
    """An imported run's name is its id; a run of Prove can carry the same name from its
    manifest."""
    runs = [R("p1", stamp(6, 9)), R("agent-x 2026-10-06 a", stamp(6, 10), backend="import:deepeval")]
    store = make_runs(tmp_path / "store", runs)
    line = refused(trace(["where", "agent-x 2026-10-06 a", "--store", str(store), "--event", "fail"]))
    # unlike an unknown word, it names the runs the word reaches
    assert "p1" in line.replace("agent-x 2026-10-06 a", ""), line
    # each is still reached another way
    assert resolved(store, "p1") == "p1"
    assert resolved(store, "latest") == "agent-x 2026-10-06 a"


def test_tf1_04_a_name_you_gave_and_another_runs_id_is_refused(tmp_path: Path) -> None:
    runs = [R("p1", stamp(6, 9)), R("p2", stamp(6, 10)), R("v1", stamp(6, 11), backend="import:ragas")]
    store = make_runs(tmp_path / "store", runs)
    # written by hand: name refuses a name that is a run's id, so it arrives only by an import
    # after the naming, which this stands for
    write_names(store, {"v1": "p1"})
    refused(trace(["where", "v1", "--store", str(store), "--event", "fail"]))


def test_tf1_04_the_typed_word_reaches_every_verb(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    s = str(store)
    for argv, keys in (
        (["compare", "#3", "#2", "--store", s, "--event", "unsolved", "--max-mde-hr", "1.5", "--json"], (("runs", "a"), ("runs", "b"))),
        (["fix-check", "previous", "latest", "--store", s, "--event", "unsolved", "--failing-from", "#3", "--max-mde", "0.2", "--json"], (("runs", "old"), ("runs", "new"))),
        (["changes", T_NAMES[T_A], "previous", "--store", s, "--event", "unsolved", "--json"], (("runs", "a"), ("runs", "b"))),
    ):
        result = trace(argv)
        assert result.code == 0, result.text
        doc = result.json()
        got = [doc[k][arm]["run_id"] for k, arm in keys]
        want = {"compare": [T_A, T_B], "fix-check": [T_B, T_PILOT], "changes": [T_A, T_B]}[argv[0]]
        assert got == want, (argv[0], got)
        if argv[0] == "fix-check":
            assert doc["inputs"]["failing_from"] == T_A
