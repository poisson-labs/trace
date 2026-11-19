"""TF1-8: every output names a run by its name, and its id once for the record (the header
line ``name (id)``).

The report's title names each run by name; the header bullet of each run carries
``name (id)``; no other line holds a run id, the selecting run of a fix check included, which
the inputs line names by its name. The JSON carries ``run_name`` right after ``run_id`` in
every run's header, and ``run_id`` and ``failing_from`` are the ids the words given reach. The
checks that two runs differ are made on the runs the words reach, not on the words."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tf0_support import RUN_ID, trace
from tf1_support import T_A, T_B, T_NAMES, T_PILOT, ids_in, refused, tau2_copy, write_names

NAMED = {T_A: "tau2 selecting run", T_B: "tau2 old re-run", T_PILOT: "tau2 patched pilot"}


@pytest.fixture
def store(tmp_path: Path) -> Path:
    root = tau2_copy(tmp_path)
    write_names(root, {given: run for run, given in NAMED.items()})
    return root


def _argv(verb: str, store: Path, *extra: str) -> list[str]:
    s = str(store)
    return {
        "where": ["where", T_B, "--store", s, "--event", "unsolved"],
        "compare": ["compare", T_A, T_B, "--store", s, "--event", "unsolved", "--max-mde-hr", "1.5"],
        "fix-check": ["fix-check", T_B, T_PILOT, "--store", s, "--event", "unsolved", "--failing-from", T_A, "--max-mde", "0.20"],
        "changes": ["changes", T_A, T_B, "--store", s, "--event", "unsolved"],
    }[verb] + list(extra)


# the header bullet each run gets, and the runs whose ids are printed once
BULLETS = {
    "where": [("- run: ", T_B)],
    "compare": [("- run: ", T_A), ("- run: ", T_B)],
    "fix-check": [("- old: ", T_B), ("- new: ", T_PILOT)],
    "changes": [("- A: ", T_A), ("- B: ", T_B)],
}


@pytest.mark.parametrize("verb", BULLETS)
def test_tf1_08_the_title_names_runs_by_name_and_the_header_by_name_and_id(store: Path, verb: str) -> None:
    result = trace(_argv(verb, store))
    assert result.code == 0, result.text
    lines = result.out.splitlines()
    title = next(line for line in lines if line.startswith("# Poisson Trace · "))
    assert not RUN_ID.search(title), title
    for _, run in BULLETS[verb]:
        assert NAMED[run] in title, title
    for opening, run in BULLETS[verb]:
        assert any(line.startswith(opening + f"{NAMED[run]} ({run})") for line in lines), (opening, run, result.out)


@pytest.mark.parametrize("verb", BULLETS)
def test_tf1_08_each_run_id_is_printed_once_and_nowhere_else(store: Path, verb: str) -> None:
    result = trace(_argv(verb, store))
    assert result.code == 0, result.text
    printed = sorted(ids_in(result.out))
    assert printed == sorted(run for _, run in BULLETS[verb]), printed


def test_tf1_08_the_selecting_run_is_named_by_its_name(store: Path) -> None:
    result = trace(_argv("fix-check", store))
    inputs = next(line for line in result.out.splitlines() if line.startswith("- inputs: "))
    assert NAMED[T_A] in inputs and T_A not in inputs, inputs
    doc = trace(_argv("fix-check", store, "--json")).json()
    assert doc["inputs"]["failing_from"] == T_A


def _headers(verb: str, doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if verb == "where":
        return {"run": doc["run"]}
    return dict(doc["runs"])


WORDS = {
    "where": ["where", "previous"],
    "compare": ["compare", "#3", "tau2 old re-run"],
    "fix-check": ["fix-check", T_NAMES[T_B], "latest"],
    "changes": ["changes", "tau2 selecting run", "#2"],
}
REACHED = {"where": {"run": T_B}, "compare": {"a": T_A, "b": T_B}, "fix-check": {"old": T_B, "new": T_PILOT}, "changes": {"a": T_A, "b": T_B}}


@pytest.mark.parametrize("verb", WORDS)
def test_tf1_08_the_json_carries_run_name_beside_the_id_the_words_reach(store: Path, verb: str) -> None:
    argv = _argv(verb, store, "--json")
    positional = 2 if verb == "where" else 3
    result = trace(WORDS[verb] + argv[positional:])
    assert result.code == 0, result.text
    headers = _headers(verb, result.json())
    assert {arm: h["run_id"] for arm, h in headers.items()} == REACHED[verb]
    for arm, header in headers.items():
        keys = list(header)
        assert keys[keys.index("run_id") + 1] == "run_name", keys
        assert header["run_name"] == NAMED[REACHED[verb][arm]]


def test_tf1_08_a_run_with_no_name_of_yours_is_named_from_its_manifest(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    result = trace(["compare", T_A, T_B, "--store", str(store), "--event", "unsolved", "--max-mde-hr", "1.5"])
    title = next(line for line in result.out.splitlines() if line.startswith("# Poisson Trace · "))
    assert T_NAMES[T_A] in title and T_NAMES[T_B] in title, title
    doc = trace(["compare", T_A, T_B, "--store", str(store), "--event", "unsolved", "--max-mde-hr", "1.5", "--json"]).json()
    assert [doc["runs"][arm]["run_name"] for arm in ("a", "b")] == [T_NAMES[T_A], T_NAMES[T_B]]


def test_tf1_08_the_figure_names_its_run(store: Path, tmp_path: Path) -> None:
    svg = tmp_path / "curve.svg"
    assert trace(_argv("where", store, "--svg", str(svg))).code == 0
    assert NAMED[T_B] in svg.read_text(encoding="utf-8")


@pytest.mark.parametrize("argv,control", [
    (["fix-check", "latest", T_PILOT, "--inputs", "all"], ["fix-check", "previous", T_PILOT, "--inputs", "all"]),
    (["fix-check", "previous", "latest", "--failing-from", "tau2 old re-run"], ["fix-check", "previous", "latest", "--failing-from", "#3"]),
    (["fix-check", "#3", "#2", "--failing-from", T_NAMES[T_B]], ["fix-check", "#3", "#2", "--failing-from", "tau2 patched pilot"]),
    (["changes", "#1", "tau2 patched pilot"], ["changes", "#2", "tau2 patched pilot"]),
], ids=["old and new one run", "selecting run is the old arm", "selecting run is the new arm", "A and B one run"])
def test_tf1_08_two_words_for_one_run_are_refused_as_one_run(store: Path, argv: list[str], control: list[str]) -> None:
    tail = ["--store", str(store), "--event", "unsolved", *(["--max-mde", "0.2"] if argv[0] == "fix-check" else [])]
    refused(trace([*argv, *tail]))
    # the same words for two runs are taken
    allowed = trace([*control, *tail])
    assert allowed.code == 0, allowed.text
