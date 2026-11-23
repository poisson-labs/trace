"""The promise Trace's JSON documents make to a program that reads them (``docs/handover.md``,
"What result.json promises"), for ``--json`` output and a bundle's ``result.json`` alike:

- each document's first key is ``schema``, its schema id with a number at the end;
- within one number, no public key is renamed or removed, and keys are only added;
- a rename or a removal moves the number;
- a public key is any key that does not start with an underscore; keys that do are internal.

Each case below is a document as the suite's own workspace gives it (``api_support.workspace``:
the committed Prove store, two table imports, two JUnit imports and a config), run through the
command line in-process. Its public keys are held to those pinned in ``json_promise_pins``, which
were taken from the same cases on the main that made the promise. Every pinned key must still be
there under the same schema id. A key that is not pinned is an addition and passes.

A key is named by its path from the document's root, as a JSON pointer writes it
(``/runs/a/tally/rows``), with ``*`` standing for every item of a list. Two objects hold keys that
are not Trace's but the run's or the user's: an input's ``config`` (the run's own condition names)
and ``continuous_measures/ceilings`` (the measures named on the command line). The path stops at
them, and the keys inside are not pinned.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from api_support import VERBS_ARGV, cli, workspace
from json_promise_pins import COMMON, EXTRA, SCHEMA

#: The objects whose keys are the run's or the user's, not Trace's, by their own key.
NOT_TRACES = frozenset({"config", "ceilings"})

#: The verbs that hand a result over as a bundle, each once, and two more ways in: the table
#: imports and the JUnit imports, whose runs carry no trace.
BUNDLED = ("where", "where untraced", "compare", "fix-check", "fix-check tables", "changes",
           "changes verdicts")

#: init's two documents (the setup it writes, and the setup for a coding agent) and doctor's two
#: (the check of this environment, and the check of a setup), each as the suite's workspace gives it.
SETUP_ARGV: dict[str, list[str]] = {
    "init": ["init", "--yes", "--store", "store", "--event", "violated", "--event", "timeout", "--json"],
    "init --agent": ["init", "--agent", "--repo", "repo", "--json"],
    "doctor": ["doctor", "--config", "conf/trace.toml", "--json"],
    "doctor --setup": ["doctor", "--setup", "--config", "conf/trace.toml", "--json"],
}


def _cases() -> dict[str, tuple[list[str], bool]]:
    """Each case's words and whether its document is the bundle's ``result.json``."""
    cases: dict[str, tuple[list[str], bool]] = {}
    for name, argv in VERBS_ARGV.items():
        cases[f"{name} --json"] = ([*argv, "--json"], False)
    for name in BUNDLED:
        cases[f"{name} --out"] = ([*VERBS_ARGV[name], "--out", "bundle"], True)
    for name, argv in SETUP_ARGV.items():
        cases[name] = (argv, False)
    return cases


CASES = _cases()


def _escaped(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def _paths(value: Any, at: str) -> Iterator[str]:
    if isinstance(value, dict):
        for key, inner in value.items():
            if key.startswith("_"):
                continue
            path = f"{at}/{_escaped(key)}"
            yield path
            if key not in NOT_TRACES:
                yield from _paths(inner, path)
    elif isinstance(value, list):
        for inner in value:
            yield from _paths(inner, f"{at}/*")


def public_keys(document: Any) -> frozenset[str]:
    """Every public key of a document, by its path."""
    return frozenset(_paths(document, ""))


def lost(pinned: frozenset[str], document: Any) -> list[str]:
    """The pinned keys a document no longer holds: those renamed or removed."""
    return sorted(pinned - public_keys(document))


def document(tmp: Path, case: str) -> Any:
    """The document a case writes, read as JSON."""
    argv, bundled = CASES[case]
    work = workspace(tmp)
    if case == "init --agent":
        (work / "repo").mkdir()
    ran = cli(work, argv)
    assert ran.code == 0, ran.text
    if bundled:
        return json.loads((work / "bundle" / "result.json").read_text(encoding="utf-8"))
    return json.loads(ran.out)


def pinned(case: str) -> frozenset[str]:
    """The public keys pinned for a case: those every case of its document holds, and its own."""
    group = f"{SCHEMA[case]} result.json" if CASES[case][1] else SCHEMA[case]
    return frozenset(COMMON[group]) | frozenset(EXTRA.get(case, ()))


def test_every_case_is_pinned() -> None:
    assert sorted(SCHEMA) == sorted(CASES)
    assert set(EXTRA) <= set(CASES)
    groups = {f"{SCHEMA[c]} result.json" if CASES[c][1] else SCHEMA[c] for c in CASES}
    assert groups == set(COMMON)


def test_the_promise_covers_each_schema_it_names() -> None:
    named = {"poisson-trace.where/1", "poisson-trace.compare/1", "poisson-trace.runs/1",
             "poisson-trace.fix-check/2", "poisson-trace.changes/2", "poisson-trace.init/1",
             "poisson-trace.doctor/1"}
    assert set(SCHEMA.values()) == named
    bundled = {SCHEMA[c] for c in CASES if CASES[c][1]}
    assert bundled == {"poisson-trace.where/1", "poisson-trace.compare/1",
                       "poisson-trace.fix-check/2", "poisson-trace.changes/2"}


def test_no_pinned_key_is_internal() -> None:
    for keys in (*COMMON.values(), *EXTRA.values()):
        for path in keys:
            assert not any(part.startswith("_") for part in path.split("/")[1:]), path


@pytest.mark.parametrize("case", list(CASES))
def test_a_document_keeps_every_public_key_it_had(tmp_path: Path, case: str) -> None:
    held = document(tmp_path, case)
    assert list(held)[0] == "schema", list(held)[:3]
    assert held["schema"] == SCHEMA[case], (
        f"{case}: the schema id moved from {SCHEMA[case]} to {held['schema']}; pin the keys "
        "of the new number beside the old"
    )
    gone = lost(pinned(case), held)
    assert not gone, (
        f"{case}: {held['schema']} no longer holds these public keys; a key is renamed or "
        f"removed only with the number moved: {gone}"
    )


def test_an_added_key_passes_and_a_removed_or_renamed_one_does_not() -> None:
    doc = {"schema": "poisson-trace.where/1", "run": {"run_id": "r", "tally": {"rows": 3}},
           "curve": [{"step": 1}, {"step": 2, "at_risk": 4}], "_internal": 1}
    keys = public_keys(doc)
    assert keys == {"/schema", "/run", "/run/run_id", "/run/tally", "/run/tally/rows", "/curve",
                    "/curve/*/step", "/curve/*/at_risk"}
    added = {**doc, "verdict": "ok", "run": {**doc["run"], "status": "complete"}}
    assert lost(keys, added) == []
    removed = {**doc, "run": {"run_id": "r"}}
    assert lost(keys, removed) == ["/run/tally", "/run/tally/rows"]
    renamed = {**doc, "run": {"id": "r", "tally": {"rows": 3}}}
    assert lost(keys, renamed) == ["/run/run_id"]
    internal_gone = {k: v for k, v in doc.items() if k != "_internal"}
    assert lost(keys, internal_gone) == []
    assert public_keys({"rows": [{"config": {"task_id": "a"}}], "a/b": 1}) == {
        "/rows", "/rows/*/config", "/a~1b"}
