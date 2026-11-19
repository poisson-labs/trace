"""TF1-6: ``poisson-trace name`` (``docs/commands.md``).

``name RUN NAME`` gives the run the name, wherever RUN is given by any word a verb takes;
naming it again replaces its name; ``name RUN --forget`` takes the name back, a stale entry
included; ``name --list`` shows each name with the name its run has from its manifest. Refused
in one line, with the file left as it was: a name another run answers to (by your name or by
its manifest's), a name that is a run's id, an empty name, one over 80 characters, one holding
a newline, and the reserved forms. Names are compared
case-sensitively and whitespace-trimmed. It never makes a store."""

from __future__ import annotations

from pathlib import Path

import pytest

from tf0_support import trace
from tf1_support import (
    NAMES_FILE, T_A, T_B, T_NAMES, T_PILOT, counts_in, first_line, name, names_file, refused,
    resolved, runs_json, tau2_copy, verdict_parts,
)


def _names(store: Path) -> dict[str, str]:
    return dict(names_file(store)["names"]) if (store / NAMES_FILE).exists() else {}


def test_tf1_06_name_gives_a_run_a_name_and_says_so(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    result = name(store, T_B, "tau2 old re-run")
    assert result.code == 0 and result.err == "", result.text
    word, sentence = verdict_parts(first_line(result))
    assert word == "ok"
    # the run once for the record, the name, and the file it was written to
    assert T_B in sentence and "tau2 old re-run" in sentence and NAMES_FILE in sentence, sentence
    assert _names(store) == {"tau2 old re-run": T_B}
    assert resolved(store, "tau2 old re-run", "unsolved") == T_B


@pytest.mark.parametrize("word,run", [
    ("latest", T_PILOT), ("previous", T_B), ("#3", T_A), (T_NAMES[T_B], T_B), (T_A, T_A),
], ids=["latest", "previous", "#3", "its name from the manifest", "its id"])
def test_tf1_06_the_run_to_name_is_given_as_any_verb_takes_it(tmp_path: Path, word: str, run: str) -> None:
    store = tau2_copy(tmp_path)
    assert name(store, word, "chosen").code == 0
    assert _names(store) == {"chosen": run}


def test_tf1_06_a_run_named_again_has_the_new_name_only(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    assert name(store, T_B, "first").code == 0
    assert name(store, "first", "second").code == 0
    assert _names(store) == {"second": T_B}
    assert resolved(store, "first", "unsolved") is None
    # naming a run the name it has already is no change and no refusal
    assert name(store, T_B, "second").code == 0
    assert _names(store) == {"second": T_B}


def test_tf1_06_names_are_trimmed_and_compared_by_case(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    assert name(store, T_A, "  padded  ").code == 0
    assert _names(store) == {"padded": T_A}
    assert name(store, T_B, "Padded").code == 0
    assert _names(store) == {"padded": T_A, "Padded": T_B}
    assert resolved(store, "padded", "unsolved") == T_A
    assert resolved(store, "Padded", "unsolved") == T_B


REFUSED_NAMES = {
    "another run's name of yours": "taken",
    "another run's name from its manifest": T_NAMES[T_A],
    "another run's id": T_A,
    "this run's own id": T_PILOT,
    "empty": "",
    "only spaces": "   ",
    "81 characters": "x" * 81,
    "a newline": "two\nlines",
    "latest": "latest",
    "previous": "previous",
    "latest:TARGET": "latest:tau2-airline",
    "previous:TARGET": "previous:anything",
    "a number": "#1",
    "anything beginning #": "#ship-it",
}


@pytest.mark.parametrize("label", REFUSED_NAMES)
def test_tf1_06_a_name_that_cannot_be_one_is_refused_and_nothing_is_written(tmp_path: Path, label: str) -> None:
    store = tau2_copy(tmp_path)
    assert name(store, T_B, "taken").code == 0
    before = (store / NAMES_FILE).read_bytes()
    refused(name(store, T_PILOT, REFUSED_NAMES[label]))
    assert (store / NAMES_FILE).read_bytes() == before


@pytest.mark.parametrize("text", ["x" * 80, "é" * 80, "Latest", "latest run", "the #1 run", "a:b"], ids=["80 characters", "80 letters outside ASCII", "Latest", "latest run", "a # inside", "a colon"])
def test_tf1_06_a_name_at_the_limits_is_taken(tmp_path: Path, text: str) -> None:
    store = tau2_copy(tmp_path)
    result = name(store, T_PILOT, text)
    assert result.code == 0, result.text
    assert _names(store) == {text: T_PILOT}
    assert resolved(store, text, "unsolved") == T_PILOT


def test_tf1_06_forget_takes_the_name_back(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    assert name(store, T_B, "old re-run").code == 0
    assert name(store, T_A, "selecting").code == 0
    result = name(store, "old re-run", "--forget")
    assert result.code == 0, result.text
    assert verdict_parts(first_line(result))[0] == "ok"
    assert _names(store) == {"selecting": T_A}
    rows = {r["run_id"]: r for r in runs_json(store)["runs"]}
    assert (rows[T_B]["name"], rows[T_B]["named_by"]) == (T_NAMES[T_B], "manifest")
    assert resolved(store, "old re-run", "unsolved") is None
    # a run given by another word forgets its name too
    assert name(store, T_NAMES[T_A], "--forget").code == 0
    assert _names(store) == {}


def test_tf1_06_forget_clears_a_stale_entry_and_every_verb_reads_the_store_again(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    assert name(store, T_B, "kept").code == 0
    # written by hand: an entry for a run removed from the store since it was named
    text = (store / NAMES_FILE).read_text(encoding="utf-8") + '"gone" = "20260101T000000Z-dead"\n'
    (store / NAMES_FILE).write_text(text, encoding="utf-8")
    refused(trace(["runs", "--store", str(store)]))
    result = name(store, "gone", "--forget")
    assert result.code == 0, result.text
    assert _names(store) == {"kept": T_B}
    assert trace(["runs", "--store", str(store)]).code == 0
    assert resolved(store, "kept", "unsolved") == T_B


def test_tf1_06_list_shows_each_name_and_the_name_from_its_manifest(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    assert name(store, T_B, "old re-run").code == 0
    assert name(store, T_PILOT, "patched pilot").code == 0
    result = name(store, "--list")
    assert result.code == 0, result.text
    word, sentence = verdict_parts(first_line(result))
    assert word == "ok" and "2" in counts_in(sentence), sentence
    lines = result.out.splitlines()
    for mine, run in (("old re-run", T_B), ("patched pilot", T_PILOT)):
        line = next((line for line in lines if mine in line), None)
        assert line is not None and T_NAMES[run] in line, (mine, result.out)


def test_tf1_06_list_on_a_store_with_no_names_says_so(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    result = name(store, "--list")
    assert result.code == 0, result.text
    assert verdict_parts(first_line(result))[0] == "ok"
    assert not (store / NAMES_FILE).exists()
    # nothing is listed as a name of yours: no run's id and no run's name on any line
    for line in result.out.splitlines()[1:]:
        if not line.startswith("next:"):
            assert not any(run in line or computed in line for run, computed in T_NAMES.items()), line


def test_tf1_06_name_never_makes_a_store(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-store"
    refused(name(missing, "latest", "x"))
    assert not missing.exists()


@pytest.mark.parametrize("argv", [
    ["name"], ["name", T_A], ["name", T_A, "x", "--forget"], ["name", T_A, "--list"], ["name", T_A, "x", "y"],
], ids=["nothing", "a run and no name", "a name and --forget", "a run and --list", "three words"])
def test_tf1_06_a_name_command_line_that_says_nothing_whole_is_wrong(tmp_path: Path, argv: list[str]) -> None:
    store = tau2_copy(tmp_path)
    result = trace([*argv, "--store", str(store)])
    assert result.code == 2 and result.out == "", result.text
    assert not (store / NAMES_FILE).exists()


def test_tf1_06_a_partial_runs_name_from_its_manifest_is_taken(tmp_path: Path) -> None:
    from tf1_support import R, make_runs, stamp

    store = make_runs(tmp_path / "store", [R("done", stamp(9, 9)), R("half", stamp(9, 10), status="partial")])
    before = sorted(p.name for p in store.iterdir())
    refused(name(store, "done", "agent-x 2026-10-09 b"))
    assert sorted(p.name for p in store.iterdir()) == before


def test_tf1_06_the_limit_is_on_the_trimmed_name(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    result = name(store, T_PILOT, "  " + "x" * 80 + "  ")
    assert result.code == 0, result.text
    assert _names(store) == {"x" * 80: T_PILOT}


def test_tf1_06_a_name_beginning_with_a_dash_is_never_written(tmp_path: Path) -> None:
    """A command line reads it as an option, so no command could give it back to a verb."""
    store = tau2_copy(tmp_path)
    for argv in (["name", T_PILOT, "-x", "--store", str(store)], ["name", T_PILOT, "--store", str(store), "--", "-x"]):
        result = trace(argv)
        assert result.code in (1, 2) and result.out == "", result.text
    assert not (store / NAMES_FILE).exists()


def test_tf1_06_ctrl_c_writes_no_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from poisson_prove.store import Store

    store = tau2_copy(tmp_path)
    assert name(store, T_B, "kept").code == 0
    before = (store / NAMES_FILE).read_bytes()

    def interrupted(self: Store, *args: object, **kwargs: object) -> object:
        raise KeyboardInterrupt

    monkeypatch.setattr(Store, "manifest", interrupted)
    result = name(store, T_PILOT, "pilot")
    assert result.code == 130 and verdict_parts(first_line(result))[0] == "stopped", result.text
    assert (store / NAMES_FILE).read_bytes() == before
