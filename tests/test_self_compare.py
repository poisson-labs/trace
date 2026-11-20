"""PA20: ``compare`` refuses two words that reach one run, as ``fix-check`` and ``changes`` do.
A check that the two words differ is not enough: ``compare "#2" "agent before"`` would compare a
run with itself and say *too small to tell*; the check is that the two runs differ.

Every way two words reach one run, on the three verbs that take two runs, through the command
line and through the Python API: one word twice, a name and its id, a name and its number, an id
and its number, and (in a store with no names of yours) a run's own name beside its id and number.
``compare`` must refuse with the sentence ``changes`` gives for the same two words, the same next
commands and the same exit code; ``fix-check`` gives that sentence with its own labels (OLD and
NEW). A pair of two different runs must still pass the check."""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

import pytest
from conftest import TAU2_A, TAU2_B, TAU2_EVENTS, compare
from fixcheck_support import changes, fix_check
from names_support import runs_json, tau2_copy, write_names

NAME = "agent before"


def _number(store: Path, run_id: str) -> str:
    rows = runs_json(store)["runs"]
    return "#" + str(next(r["number"] for r in rows if r["run_id"] == run_id))


def _manifest_name(store: Path, run_id: str) -> str:
    rows = runs_json(store)["runs"]
    return str(next(r["name"] for r in rows if r["run_id"] == run_id))


def _named(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    store = tau2_copy(tmp_path)
    write_names(store, {NAME: TAU2_A})
    return store, {"id": TAU2_A, "number": _number(store, TAU2_A), "name": NAME}


def _unnamed(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    store = tau2_copy(tmp_path)
    return store, {
        "id": TAU2_A,
        "number": _number(store, TAU2_A),
        "name": _manifest_name(store, TAU2_A),
    }


def _pairs(forms: dict[str, str], only: tuple[str, ...] | None = None) -> list[tuple[str, str]]:
    keys = only or tuple(forms)
    return [(forms[a], forms[b]) for a, b in itertools.product(keys, keys)]


def _cases() -> list[tuple[str, str, str]]:
    out = []
    for store_kind in ("named", "unnamed"):
        keys = ("id", "number", "name")
        for a, b in itertools.product(keys, keys):
            out.append((store_kind, a, b))
    return out


CASES = _cases()
IDS = [f"{k}:{a}+{b}" for k, a, b in CASES]


Stores = dict[str, tuple[Path, dict[str, str]]]


@pytest.fixture(scope="module")
def stores(tmp_path_factory: pytest.TempPathFactory) -> Stores:
    """The two stores every test here reads, each copied once: one with a name of yours, one
    with none. No test writes into them (a refusal writes nothing, and the verbs run without
    ``--save`` or ``--out``)."""
    return {"named": _named(tmp_path_factory.mktemp("named")),
            "unnamed": _unnamed(tmp_path_factory.mktemp("unnamed"))}


def _store_and_words(stores: Stores, kind: str, a: str, b: str) -> tuple[Path, str, str]:
    store, forms = stores[kind]
    return store, forms[a], forms[b]


def _compare(store: Path, a: str, b: str) -> Any:
    return compare(store, a, b, TAU2_EVENTS, 1.5)


def _fix_check(store: Path, a: str, b: str) -> Any:
    return fix_check(store, a, b, TAU2_EVENTS, "--inputs", "all", "--max-mde", "0.2")


@pytest.mark.parametrize(("kind", "a", "b"), CASES, ids=IDS)
def test_pa20_2_fix_check_refuses_every_pair_that_reaches_one_run(
    stores: Stores, kind: str, a: str, b: str
) -> None:
    store, first, second = _store_and_words(stores, kind, a, b)
    ran = _fix_check(store, first, second)
    assert ran.code == 1 and ran.out == "", ran.text
    assert "the two runs compared must differ" in ran.err, ran.text
    twin = changes(store, first, second, TAU2_EVENTS)
    assert ran.err.replace("OLD and NEW", "A and B") == twin.err


@pytest.mark.parametrize(("kind", "a", "b"), CASES, ids=IDS)
def test_pa20_3_compare_refuses_every_pair_that_reaches_one_run_as_changes_does(
    stores: Stores, kind: str, a: str, b: str
) -> None:
    store, first, second = _store_and_words(stores, kind, a, b)
    ran = _compare(store, first, second)
    twin = changes(store, first, second, TAU2_EVENTS)
    # the same sentence shape (A and B are both ...), next commands and exit code, nothing printed
    assert (ran.code, ran.out, ran.err) == (twin.code, twin.out, twin.err), ran.text
    assert ran.code == 1 and ran.out == "", ran.text
    assert "the two runs compared must differ" in ran.err, ran.text


def test_pa20_4_a_number_and_a_name_for_one_run(stores: Stores) -> None:
    store, forms = stores["named"]
    ran = _compare(store, forms["number"], NAME)
    assert ran.code == 1 and ran.out == "", ran.text
    assert ran.err.startswith("error: A and B are both "), ran.text
    assert "too small to tell" not in ran.text


def test_pa20_5_the_refusal_comes_before_any_other_check_of_the_runs(stores: Stores) -> None:
    # the run has no traces, which compare refuses for its own reason; two words for it are
    # refused for being one run first, as changes and fix-check refuse them
    store, forms = stores["named"]
    ran = _compare(store, forms["id"], NAME)
    assert "has no traces" not in ran.err, ran.text
    assert "the two runs compared must differ" in ran.err, ran.text


def test_pa20_6_two_different_runs_are_not_refused_for_being_one(stores: Stores) -> None:
    store, forms = stores["named"]
    for a, b in ((forms["id"], TAU2_B), (NAME, TAU2_B), (forms["number"], TAU2_B)):
        ran = _compare(store, a, b)
        assert "must differ" not in ran.err + ran.out, ran.text
        ran = changes(store, a, b, TAU2_EVENTS)
        assert "must differ" not in ran.err + ran.out, ran.text


# ---------- through the Python API ----------


def _api_refusal(verb: str, store: Path, a: str, b: str) -> Any:
    from poisson_trace import api

    events = list(TAU2_EVENTS)
    with pytest.raises(api.Refusal) as caught:
        if verb == "compare":
            api.compare(str(store), a, b, event=events, max_mde_hr=1.5)
        elif verb == "changes":
            api.changes(str(store), a, b, event=events)
        else:
            api.fix_check(str(store), a, b, event=events, inputs="all", max_mde=0.2)
    return caught.value


@pytest.mark.parametrize(("kind", "a", "b"), CASES, ids=IDS)
def test_pa20_7_the_api_refuses_compare_as_it_refuses_changes_and_fix_check(
    stores: Stores, kind: str, a: str, b: str
) -> None:
    store, first, second = _store_and_words(stores, kind, a, b)
    got = _api_refusal("compare", store, first, second)
    twin = _api_refusal("changes", store, first, second)
    fix = _api_refusal("fix_check", store, first, second)
    assert (got.message, got.next, got.exit_code, got.notes) == (
        twin.message, twin.next, twin.exit_code, twin.notes,
    )
    assert "the two runs compared must differ" in got.message
    assert fix.message.replace("OLD and NEW", "A and B") == twin.message
    assert fix.exit_code == twin.exit_code == 1
