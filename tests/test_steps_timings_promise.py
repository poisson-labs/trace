"""TS-28 and TS-52: the promise ``tests/test_json_promise.py`` holds, for the keys under ``steps``
and ``timings``: within one schema number none of them is renamed or removed, and keys are only
added. Without ``--timings`` and ``--timings-of`` no public key is under ``timings``.

Each case is a document as the suite's workspace gives it (``api_support.workspace``), or as the
steps and timings fixture does (``st``, whose traces nest, with an orphan and parents with no
end), run through the command line in-process. Its public keys under ``/steps`` and ``/timings``,
found by the promise test's own ``public_keys``, are held to those pinned in
``steps_timings_pins``, taken from the same cases. The rest of each document is the promise
test's to hold.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from api_support import VERBS_ARGV, cli
from steps_timings_pins import KEYS, SCHEMA
from steps_timings_support import compare_argv, fresh, pair, read_only, stored, the_row, where_argv
from test_json_promise import public_keys

#: The workspace's cases of the promise test that the two keys are added to.
WORKSPACE = ("where", "where by step", "where untraced", "compare", "compare at")


def _named() -> dict[str, str]:
    """The conversations the named cases ask for, as ``HASH:REPLICATE``."""
    first = stored("agent after")[0]
    return {
        "workspace": pair(first),
        "placed": pair(the_row("fixture B", "alpha", 0)),
        "no leaf": pair(the_row("fixture B", "beta", 1)),
        "b only": pair(the_row("fixture B", "alpha", 2)),
    }


def _cases() -> dict[str, tuple[list[str], bool]]:
    """Each case's words (named conversations as ``{name}``) and whether its document is the
    bundle's ``result.json``."""
    cases: dict[str, tuple[list[str], bool]] = {}
    for name in WORKSPACE:
        cases[f"{name} --json"] = (VERBS_ARGV[name], False)
        cases[f"{name} --timings --json"] = ([*VERBS_ARGV[name], "--timings"], False)
    cases["where --timings --out"] = ([*VERBS_ARGV["where"], "--timings"], True)
    cases["compare --timings --out"] = ([*VERBS_ARGV["compare"], "--timings"], True)
    cases["where --timings-of --json"] = ([*VERBS_ARGV["where"], "--timings-of", "{workspace}"], False)
    cases["compare --timings-of --json"] = ([*VERBS_ARGV["compare"], "--timings-of", "{workspace}"], False)
    cases["fixture where B --json"] = (where_argv("fixture B"), False)
    cases["fixture where B --timings --json"] = (where_argv("fixture B", "--timings"), False)
    cases["fixture compare A B --timings --json"] = (compare_argv("fixture A B", "--timings"), False)
    cases["fixture where B --timings-of --json"] = (
        where_argv("fixture B", "--timings-of", "{placed}", "--timings-of", "{no leaf}"), False)
    cases["fixture compare A B --timings-of --json"] = (
        compare_argv("fixture A B", "--timings-of", "{placed}", "--timings-of", "{b only}", "--timings-of", "{no leaf}"),
        False)
    cases["fixture where B --timings-of --out"] = (where_argv("fixture B", "--timings-of", "{placed}"), True)
    cases["fixture compare A B --timings-of --out"] = (compare_argv("fixture A B", "--timings-of", "{placed}"), True)
    return cases


CASES = _cases()


def asks_timings(case: str) -> bool:
    return any(w in ("--timings", "--timings-of") for w in CASES[case][0])


def document(tmp: Path, case: str) -> Any:
    """The document a case writes, read as JSON."""
    argv, bundled = CASES[case]
    named = _named()
    words = [w.format(**named) if w.startswith("{") else w for w in argv]
    if not bundled:
        ran = cli(read_only(), [*words, "--json"])
        assert ran.code == 0, ran.text
        return json.loads(ran.out)
    work = fresh(tmp)
    ran = cli(work, [*words, "--out", "bundle"])
    assert ran.code == 0, ran.text
    return json.loads((work / "bundle" / "result.json").read_text(encoding="utf-8"))


def under(keys: frozenset[str]) -> frozenset[str]:
    """The keys under ``/steps`` and ``/timings``."""
    return frozenset(k for k in keys if k.split("/")[1] in ("steps", "timings"))


def test_every_case_is_pinned() -> None:
    assert sorted(SCHEMA) == sorted(CASES) == sorted(KEYS)


def test_the_pins_hold_the_paths_the_layout_names() -> None:
    where = set(KEYS["fixture where B --timings-of --json"]) | set(KEYS["fixture where B --timings --json"])
    named = [*(f"/steps/*/{k}" for k in ("step", "reached", "ended_here", "ends", "died_by", "labels")),
             *(f"/steps/*/ends/{k}" for k in ("died", "ended", "timed out", "capped")),
             "/steps/*/died_by/*/label", "/steps/*/died_by/*/count", "/steps/*/labels/*/label", "/steps/*/labels/*/count",
             *(f"/timings/{k}" for k in ("most_steps", "conversations", "listed", "no_end", "parents_no_end", "no_tree",
                                         "asked", "not_listed", "items")),
             "/timings/asked/*/config_hash", "/timings/asked/*/replicate_index",
             "/timings/not_listed/*/config_hash", "/timings/not_listed/*/replicate_index", "/timings/not_listed/*/why",
             *(f"/timings/items/*/{k}" for k in ("config_hash", "seed", "replicate_index", "end", "cause", "steps", "parents")),
             *(f"/timings/items/*/steps/*/{k}" for k in ("step", "offset_ns", "duration_ns", "kind", "label", "span_id", "parent_id")),
             *(f"/timings/items/*/parents/*/{k}" for k in ("span_id", "parent_id", "kind", "offset_ns", "duration_ns"))]
    assert not [p for p in named if p not in where]
    compare = set(KEYS["fixture compare A B --timings-of --json"]) | set(KEYS["fixture compare A B --timings --json"])
    for side in ("a", "b"):
        sided = ["/" + "/".join([p.split("/")[1], side, *p.split("/")[2:]]) for p in named]
        assert not [p for p in sided if p not in compare]


@pytest.mark.parametrize("case", list(CASES))
def test_ts_28_52_every_pinned_key_under_steps_and_timings_is_still_there(tmp_path: Path, case: str) -> None:
    held = document(tmp_path, case)
    assert held["schema"] == SCHEMA[case]
    keys = under(public_keys(held))
    gone = sorted(frozenset(KEYS[case]) - keys)
    assert not gone, f"{case}: {held['schema']} no longer holds these public keys: {gone}"
    if not asks_timings(case):
        assert not [k for k in keys if k.startswith("/timings")], case
        assert "/steps" in keys
    else:
        assert [k for k in keys if k.startswith("/timings")]
