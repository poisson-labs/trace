"""TF1-15: names change no stored run (spec sections 5.2 and 5.3, principle P-3; TR9 as R18
rewrites it).

``runs``, ``name --list``, every verb given a run by any word, and every refusal leave every
file under the store as it was, bytes and modification time, and make no file there: a name
from the manifest is computed, never stored. ``name`` and ``name --forget`` change one file,
``trace-names.toml`` at the store root, and leave nothing else behind."""

from __future__ import annotations

from pathlib import Path

from tf0_support import trace
from tf1_support import NAMES_FILE, T_A, T_B, T_NAMES, T_PILOT, snapshot, tau2_copy, write_names


def test_tf1_15_reading_by_name_writes_nothing(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    write_names(store, {"old re-run": T_B})
    before = snapshot(store)
    s = str(store)
    for argv in (
        ["runs", "--store", s],
        ["runs", "--store", s, "--all", "--json", "--event", "unsolved"],
        ["name", "--list", "--store", s],
        ["where", "old re-run", "--store", s, "--event", "unsolved", "--json"],
        ["where", "latest:tau2-airline", "--store", s, "--event", "unsolved"],
        ["compare", "#3", "#2", "--store", s, "--event", "unsolved", "--max-mde-hr", "1.3"],
        ["fix-check", "old re-run", "latest", "--store", s, "--event", "unsolved", "--failing-from", T_NAMES[T_A], "--max-mde", "0.2"],
        ["changes", "previous", "latest", "--store", s, "--event", "unsolved", "--json"],
    ):
        result = trace(argv)
        assert result.code == 0, (argv, result.text)
    for argv in (
        ["where", "no such run", "--store", s, "--event", "unsolved"],
        ["where", "#9", "--store", s, "--event", "unsolved"],
        ["name", T_A, "old re-run", "--store", s],
        ["name", T_A, "latest", "--store", s],
        ["fix-check", "latest", T_PILOT, "--store", s, "--event", "unsolved", "--inputs", "all", "--max-mde", "0.2"],
    ):
        result = trace(argv)
        assert result.code == 1, (argv, result.text)
    assert snapshot(store) == before


def test_tf1_15_no_verb_but_name_makes_a_names_file(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    before = snapshot(store)
    s = str(store)
    for argv in (
        ["runs", "--store", s, "--all"],
        ["name", "--list", "--store", s],
        ["where", T_NAMES[T_B], "--store", s, "--event", "unsolved"],
    ):
        assert trace(argv).code == 0, argv
    assert snapshot(store) == before and not (store / NAMES_FILE).exists()


def test_tf1_15_name_changes_the_names_file_and_nothing_else(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    for step in (["name", T_B, "old re-run"], ["name", T_A, "selecting"], ["name", "old re-run", "renamed"], ["name", "selecting", "--forget"]):
        before = snapshot(store)
        assert trace([*step, "--store", str(store)]).code == 0, step
        after = snapshot(store)
        changed = {path for path in set(before) | set(after) if before.get(path) != after.get(path)}
        assert changed == {NAMES_FILE}, changed
