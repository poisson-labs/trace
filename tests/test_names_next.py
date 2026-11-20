"""TF1-11: every verb ends with ``next:``, and a ``next:`` line names runs by their names (the
look's rule 13).

The verb resolves what it was given and prints the name, never an id the user typed, quoted so
that a shell reads back the name exactly, whatever it holds. ``where`` points ``compare`` at the
run before it on its target and itself, or at ``fix-check --help`` when there is none; ``compare``
and ``changes`` point ``fix-check`` at their two runs; ``fix-check`` with *too small to tell*
names the repeats and the inputs its guidance gives; ``runs`` points ``where`` at the newest
run with traces. The JSON's ``next`` is the line's command."""

from __future__ import annotations

from pathlib import Path

import pytest

from look_support import chdir, deepeval_import, trace, trace_import
from names_support import (
    T_A, T_B, T_NAMES, T_PILOT, R, ids_in, make_runs, name, next_line, positionals, resolved, shell_words, stamp,
    tau2_copy, write_names,
)


def _ran(argv: list[str]):  # type: ignore[no-untyped-def]
    result = trace(argv)
    assert result.code == 0, result.text
    return result


def test_tf1_11_every_verb_ends_with_next(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    s = str(store)
    results = {
        "where": trace(["where", T_B, "--store", s, "--event", "unsolved"]),
        "compare": trace(["compare", T_A, T_B, "--store", s, "--event", "unsolved", "--max-mde-hr", "1.5"]),
        "fix-check": trace(["fix-check", T_A, T_B, "--store", s, "--event", "unsolved", "--inputs", "all", "--max-mde", "0.2"]),
        "changes": trace(["changes", T_A, T_B, "--store", s, "--event", "unsolved"]),
        "runs": trace(["runs", "--store", s]),
        "name": name(store, T_B, "old"),
        "name --list": name(store, "--list"),
        "name --forget": name(store, "old", "--forget"),
    }
    with chdir(tmp_path):
        results["import"] = trace_import(deepeval_import("store", "he-a"))
    for verb, result in results.items():
        assert result.code == 0, (verb, result.text)
        assert next_line(result).strip(), verb


@pytest.mark.parametrize("verb", ["where", "compare", "fix-check", "changes"])
def test_tf1_11_next_never_holds_the_id_the_user_typed(tmp_path: Path, verb: str) -> None:
    store = str(tau2_copy(tmp_path))
    argv = {
        "where": ["where", T_B, "--store", store, "--event", "unsolved"],
        "compare": ["compare", T_A, T_B, "--store", store, "--event", "unsolved", "--max-mde-hr", "1.3"],
        "fix-check": ["fix-check", T_B, T_PILOT, "--store", store, "--event", "unsolved", "--failing-from", T_A, "--max-mde", "0.2"],
        "changes": ["changes", T_A, T_B, "--store", store, "--event", "unsolved"],
    }[verb]
    command = next_line(_ran(argv))
    assert ids_in(command) == [], command


def test_tf1_11_where_points_compare_at_the_run_before_it_then_itself(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    command = next_line(_ran(["where", T_B, "--store", str(store), "--event", "unsolved"]))
    pair = positionals(command, "compare")
    assert [resolved(store, word, "unsolved") for word in pair] == [T_A, T_B], command


def test_tf1_11_where_on_the_first_run_of_its_target_points_at_fix_check_help(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    command = next_line(_ran(["where", T_A, "--store", str(store), "--event", "unsolved"]))
    assert shell_words(command)[:3] == ["poisson-trace", "fix-check", "--help"], command


def test_tf1_11_the_run_before_is_on_the_same_target(tmp_path: Path) -> None:
    runs = [
        R("x-old", stamp(8, 9)), R("y-between", stamp(8, 10), target_id="agent-y/m@v0"),
        R("x-half", stamp(8, 10, 30), status="partial"), R("x-new", stamp(8, 11)),
    ]
    store = make_runs(tmp_path / "store", runs)
    command = next_line(_ran(["where", "x-new", "--store", str(store), "--event", "fail"]))
    assert [resolved(store, w) for w in positionals(command, "compare")] == ["x-old", "x-new"], command


@pytest.mark.parametrize("verb", ["compare", "changes"])
def test_tf1_11_compare_and_changes_point_fix_check_at_their_two_runs(tmp_path: Path, verb: str) -> None:
    store = tau2_copy(tmp_path)
    argv = [verb, "#3", "previous", "--store", str(store), "--event", "unsolved"] + (["--max-mde-hr", "1.5"] if verb == "compare" else [])
    command = next_line(_ran(argv))
    assert [resolved(store, w, "unsolved") for w in positionals(command, "fix-check")] == [T_A, T_B], command


def test_tf1_11_too_small_to_tell_names_the_repeats_and_the_inputs(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    argv = ["fix-check", T_B, T_PILOT, "--store", str(store), "--event", "unsolved", "--failing-from", T_A, "--max-mde", "0.20"]
    command = next_line(_ran(argv))
    doc = _ran([*argv, "--json"]).json()
    assert doc["verdict"] == "too small to tell"
    words = command.replace(",", " ").split()
    assert str(doc["guidance"]["repeats"]) in words and str(doc["inputs"]["compared"]) in words, command
    assert "fix-check" in words


def test_tf1_11_runs_points_where_at_the_newest_run_with_traces(tmp_path: Path) -> None:
    runs = [R("traced-old", stamp(9, 9)), R("traced-new", stamp(9, 10)), R("bare", stamp(9, 11), traced=False)]
    store = make_runs(tmp_path / "store", runs)
    command = next_line(_ran(["runs", "--store", str(store), "--event", "fail"]))
    assert [resolved(store, w) for w in positionals(command, "where")] == ["traced-new"], command


AWKWARD = 'tau2 "old" re-run $HOME `id` \\ #1'


@pytest.mark.parametrize("verb", ["where", "compare", "changes", "runs"])
def test_tf1_11_a_shell_reads_back_every_name_next_gives(tmp_path: Path, verb: str) -> None:
    store = tau2_copy(tmp_path)
    write_names(store, {AWKWARD: T_A, "it's the re-run": T_B})
    s = str(store)
    argv = {
        "where": ["where", T_B, "--store", s, "--event", "unsolved"],
        "compare": ["compare", T_A, T_B, "--store", s, "--event", "unsolved", "--max-mde-hr", "1.5"],
        "changes": ["changes", T_A, T_B, "--store", s, "--event", "unsolved"],
        "runs": ["runs", "--store", s, "--event", "unsolved"],
    }[verb]
    command = next_line(_ran(argv))
    want = {"where": [AWKWARD, "it's the re-run"], "compare": [AWKWARD, "it's the re-run"], "changes": [AWKWARD, "it's the re-run"], "runs": ["it's the re-run"]}[verb]
    target = {"where": "compare", "compare": "fix-check", "changes": "fix-check", "runs": "where"}[verb]
    assert positionals(command, target) == want, command


def test_tf1_11_the_names_next_gives_follow_a_name_you_gave(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    write_names(store, {"selecting": T_A})
    command = next_line(_ran(["where", "latest:tau2-airline", "--store", str(store), "--event", "unsolved"]))
    # latest is the pilot, which has no trace; the next step still names runs, by name
    assert ids_in(command) == []
    command = next_line(_ran(["where", T_NAMES[T_B], "--store", str(store), "--event", "unsolved"]))
    assert positionals(command, "compare") == ["selecting", T_NAMES[T_B]], command
