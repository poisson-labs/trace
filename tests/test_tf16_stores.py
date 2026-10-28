"""TF16-4 to TF16-7: a store Prove 0.0.1 wrote and a store Prove's main writes read alike
(spec section 16.1 step 1, section 17.3; Prove's docs/artifact-format.md at fa31d79).

The two committed stores hold the same outcomes (one sweep spec, one salt, the same mock agent),
one written by proofload 0.0.1 (no ``.poisson/``, no event logs, the version under the old key,
traces under the old schema) and one by poisson-prove (``.poisson/`` with the store descriptor and
a saved comparison, an ``events.jsonl`` in each run, names given at sweep time).

- TF16-4: every verb that reads runs gives the same answer on either store: the same JSON but for
  the runs' ids, names and start times.
- TF16-5: a store holding a run of each (a 0.0.1 run beside runs a 0.1.0 sweep added, as a store
  is after the upgrade) compares across them as within one version.
- TF16-6: reading writes nothing into either store: no ``.poisson/`` appears in the old one and
  nothing in the new one's changes; ``name`` writes ``trace-names.toml`` and nothing else.
- TF16-7: ``init`` finds a 0.1.0 store by its runs and offers nothing under ``.poisson/`` and no
  run's ``events.jsonl`` as a file to import, from the folder above it or from inside it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from tf16_support import (  # noqa: F401
    EVENT, NEW, NEW_AFTER, NEW_BEFORE, OLD, OLD_A, OLD_B, POISSON, RUN_ID, TESTS, copies, copy_store,
    scratch_home, snapshot, trace,
)

# the verbs that read runs, each on the store's two runs by number (#2 the older, #1 the newer)
VERBS = {
    "runs": ["runs", "--event", EVENT],
    "where": ["where", "#2", "--event", EVENT],
    "compare": ["compare", "#2", "#1", "--event", EVENT, "--max-mde-hr", "3"],
    "fix-check": ["fix-check", "#2", "#1", "--event", EVENT, "--inputs", "all", "--max-mde", "0.5"],
    "changes": ["changes", "#2", "#1", "--event", EVENT],
}
# what differs between two stores of the same outcomes: when each run started, and the store's
# path; a run's ids and names are replaced by its place before the two are compared
TIMES = {"created_at", "started", "gap_seconds"}


def _read(store: Path, verb: str) -> tuple[int, Any]:
    ran = trace([*VERBS[verb], "--store", store, "--json"])
    assert ran.code in (0, 2), ran.text  # 2: a verdict a reader must act on is still an answer
    return ran.code, json.loads(ran.out)


def _placed(doc: Any, store: Path) -> Any:
    """``doc`` with each run's id and name replaced by its place in the store, newest first, and
    without the keys that say when a run started or where the store is."""
    listed = trace(["runs", "--store", store, "--all", "--json"]).json()["runs"]
    words = {}
    for place, row in enumerate(listed, start=1):
        words[row["run_id"]] = f"RUN{place}"
        words[row["name"]] = f"RUN{place}"
    text = json.dumps(doc)
    for word in sorted(words, key=len, reverse=True):
        text = text.replace(json.dumps(word)[1:-1], words[word])
    text = text.replace(json.dumps(str(store))[1:-1], "STORE")

    def drop(x: Any) -> Any:
        if isinstance(x, dict):
            return {k: drop(v) for k, v in x.items() if k not in TIMES and k != "named_by"}
        if isinstance(x, list):
            return [drop(v) for v in x]
        return x

    return drop(json.loads(text))


# ---------- TF16-4 ----------


@pytest.mark.parametrize("verb", list(VERBS))
def test_tf16_4_each_verb_reads_a_0_0_1_store_and_a_0_1_0_store_alike(tmp_path: Path, verb: str) -> None:
    old_store, new_store = copies(tmp_path)
    old_code, old = _read(old_store, verb)
    new_code, new = _read(new_store, verb)
    assert old["verdict"] != "error" and old_code == new_code
    assert "runs" not in old or len(old["runs"]) == 2, old
    if verb == "runs":
        # the sentence counts the runs by who named them, which a sweep-time name moves
        old.pop("sentence"), new.pop("sentence")
    assert _placed(old, old_store) == _placed(new, new_store)
    assert not any(RUN_ID.search(json.dumps(_placed(d, s))) for d, s in ((old, old_store), (new, new_store)))


# ---------- TF16-5 ----------


def test_tf16_5_a_store_with_runs_of_both_versions_compares_across_them(tmp_path: Path) -> None:
    old_store, _ = copies(tmp_path)
    mixed = copy_store(OLD, tmp_path / "store", [OLD_A])
    copy_store(NEW, mixed, [NEW_AFTER])
    shutil.copytree(NEW / POISSON, mixed / POISSON)
    listed = trace(["runs", "--store", mixed, "--json"])
    assert listed.code == 0, listed.text
    assert sorted(r["run_id"] for r in listed.json()["runs"]) == sorted([OLD_A, NEW_AFTER])
    fix_check = ["fix-check", "--event", EVENT, "--inputs", "all", "--max-mde", "0.5", "--json"]
    across = trace([*fix_check[:1], OLD_A, NEW_AFTER, *fix_check[1:], "--store", mixed])
    within = trace([*fix_check[:1], OLD_A, OLD_B, *fix_check[1:], "--store", old_store])
    assert across.code == within.code and across.code in (0, 2), across.text
    a, w = across.json(), within.json()
    assert (a["runs"]["old"]["run_id"], a["runs"]["new"]["run_id"]) == (OLD_A, NEW_AFTER)
    # the same outcomes, so the same counts, test, difference and limits; only the start times
    # (and the sentences that state them) differ
    for key in ("verdict", "rows", "inputs", "test", "difference", "by_input", "limits", "direction"):
        assert a[key] == w[key], key


# ---------- TF16-6 ----------

# every verb that reads, and each with --json, on the store's two runs
READS = [[*argv, *extra] for argv in VERBS.values() for extra in ([], ["--json"])]


@pytest.mark.parametrize("source", [OLD, NEW], ids=["0.0.1", "0.1.0"])
def test_tf16_6_reading_writes_nothing_and_name_writes_only_the_names_file(tmp_path: Path, source: Path) -> None:
    store = copy_store(source, tmp_path / "store")
    before = snapshot(store)
    for argv in [*READS, ["name", "--list"]]:
        ran = trace([*argv, "--store", store])
        assert ran.code in (0, 2), (argv, ran.text)
    assert snapshot(store) == before
    assert (store / POISSON).exists() == (source == NEW)
    ran = trace(["name", "#1", "the newer", "--store", store])
    assert ran.code == 0, ran.text
    after = snapshot(store)
    assert set(after) - set(before) == {"trace-names.toml"}
    assert {k: v for k, v in after.items() if k != "trace-names.toml"} == before


# ---------- TF16-7 ----------


def _poisson_holds_files_a_reader_reads(store: Path) -> None:
    """Into the store's ``.poisson/``, files a reader of the install reads: a JUnit report and a
    table, as another tool's artifact could be."""
    inside = store / POISSON / "artifacts" / "other-tool" / "0123456789abcdef"
    inside.mkdir(parents=True)
    shutil.copyfile(TESTS / "fixtures" / "ingest" / "junit" / "trace-suite-1.xml", inside / "report.xml")
    shutil.copyfile(TESTS / "fixtures" / "ingest" / "table" / "humaneval-a.csv", inside / "rows.csv")


@pytest.mark.parametrize("start", ["above", "inside"])
def test_tf16_7_init_finds_the_store_by_its_runs_and_nothing_under_poisson(tmp_path: Path, start: str) -> None:
    work = tmp_path / "work"
    store = copy_store(NEW, work / "prove-runs")
    _poisson_holds_files_a_reader_reads(store)
    folder = work if start == "above" else store
    # inside a store, the config goes outside it (init writes nothing into a store)
    outside = [] if start == "above" else ["--config", work / "trace.toml"]
    ran = trace(["init", "--yes", "--event", EVENT, "--json", *outside], cwd=folder)
    assert ran.code == 0, ran.text
    found = ran.json()["stores"]
    assert [(s["path"], s["runs"]) for s in found] == [("prove-runs" if start == "above" else ".", 2)]
    assert POISSON not in ran.text and "events.jsonl" not in ran.text, ran.text
    assert "report.xml" not in ran.text and "rows.csv" not in ran.text, ran.text
