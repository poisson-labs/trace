"""PL-20 to PL-31: the labels with no kind are named once (``pl_support``'s opening, reading 4).

- PL-20: the note's words: one paragraph, the labels sorted, ``the label X``/``its`` for one and
  ``the labels X, Y and Z``/``their`` for several, the first label as ``trace.toml`` writes it
  (in quotes when it is not a bare key), and the twelve kinds a team names.
- PL-21: its place: in ``Failures by kind``, after the tries line and the no-outcome sentence
  when there is one, before the signals.
- PL-22: once: in each of ``fix-check``, ``compare`` and ``changes``, a label of both runs is
  named once, and no other part of the report names it.
- PL-23: ``--json``: ``failure_taxonomy_diff`` ends with ``labels_without_kind``, a list sorted by
  label of ``{"label", <run>: n, <run>: n}``, n the failed tries of that run with the label and
  the kind ``unclassified_error``.
- PL-24: no note and no key when every failed label has a kind: by default, by the table, or
  named ``unclassified_error`` by the table; the section and the JSON's keys are then as main
  gives them.
- PL-25: the plain words that say only that a try failed (``fail``, ``failed``, ``failure``,
  ``missed``) are never named.
- PL-26: a label is named only for a failed try whose kind is ``unclassified_error``: not on a
  passing try, not on a try a cause was found for.
- PL-27: only a run Prove swept: an imported run beside one is counted 0 for every label.
- PL-28: under different rules there are no counts, and no note.
- PL-29: a ``--verdicts`` join leaves the labels named as the store's.
- PL-30: the saved verdict holds the key, and the report saved beside it the note.
- PL-31: on the committed stores: tau2's ``unsolved``, cs's ``forbidden_action`` and
  ``unresolved``, HumanEval's ``crashed`` and ``failed_assertion``.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pl_support import ARGS, ARMS, CS, HUMANEVAL, TAU2, VERBS, Try, config, note, run, section, two_runs

SIGNALS_LINE = "Signals seen on tries, failed or not:"
MAIN_KEYS = ["taxonomy_sha256", "same_rules", "tries", "kinds", "signals"]


def _store(tmp: Path) -> Path:
    """Two runs on six tasks: the old one fails with two labels that have no kind (one of
    them in both runs), one that has one, and one whose try ran out of time."""
    old = [Try("t1", "forbidden_action"), Try("t1", "forbidden_action", replicate=1), Try("t2", "unsolved"), Try("t3", "wrong_state"),
           Try("t4", "passed"), Try("t5", "wall_timeout")]
    new = [Try("t1", "passed"), Try("t1", "forbidden_action", replicate=1), Try("t2", "passed"), Try("t3", "passed"),
           Try("t4", "passed"), Try("t5", "passed")]
    return two_runs(tmp, old, new)


FAILED = ["forbidden_action", "unsolved", "wrong_state", "wall_timeout"]


def _ran(tmp: Path, verb: str, *extra: Any, labels: str | None = None, failed: list[str] | None = None) -> tuple[str, dict[str, Any]]:
    root = _store(tmp) if not (tmp / "store").exists() else tmp / "store"
    path = config(tmp, root.name, failed or FAILED, labels=labels)
    plain = run([*ARGS[verb], "--config", path, *extra])
    assert plain.code == 0, plain.text
    doc = run([*ARGS[verb], "--config", path, *extra, "--json"])
    assert doc.code == 0, doc.text
    return plain.out, doc.json()


@pytest.fixture(scope="module")
def ran_once(tmp_path_factory: pytest.TempPathFactory) -> Callable[[str], tuple[str, dict[str, Any]]]:
    """What ``_ran`` gives for a verb on the store of ``_store`` with no table, each verb run
    once for the tests that read it: the verbs read the store and write nothing, and no test
    changes what it is given."""
    tmp = tmp_path_factory.mktemp("pl-section")
    held: dict[str, tuple[str, dict[str, Any]]] = {}

    def of(verb: str) -> tuple[str, dict[str, Any]]:
        if verb not in held:
            held[verb] = _ran(tmp, verb)
        return held[verb]

    return of


# ---------- PL-20: the words ----------


@pytest.mark.parametrize("verb", VERBS)
def test_pl_20_each_verb_says_it(ran_once: Callable[[str], tuple[str, dict[str, Any]]], verb: str) -> None:
    out, _ = ran_once(verb)
    assert note(["forbidden_action", "unsolved"]) in section(out)
    assert (
        "Trace has no kind for the labels forbidden_action and unsolved, so their failed tries count as unclassified_error. "
        'To name a label\'s kind, add it to trace.toml under [taxonomy.labels], as forbidden_action = "KIND", where KIND is '
        "timeout, rate_limit, context_overflow, loop_detected, step_limit, guardrail_blocked, tool_error, retrieval_error, "
        "format_error, abstained, crash or wrong_answer."
    ) in section(out)


def test_pl_20_a_label_that_is_no_bare_key(tmp_path: Path) -> None:
    root = two_runs(tmp_path, [Try("t", "not solved"), Try("u", "passed")], [Try("t", "passed"), Try("u", "passed")])
    path = config(tmp_path, root.name, ["not solved"])
    out = run([*ARGS["changes"], "--config", path]).out
    said = note(["not solved"])
    assert said in section(out)
    assert 'as "not solved" = "KIND"' in said


# ---------- PL-21: its place ----------


@pytest.mark.parametrize("verb", VERBS)
def test_pl_21_after_the_tries_line_before_the_signals(ran_once: Callable[[str], tuple[str, dict[str, Any]]], verb: str) -> None:
    out, _ = ran_once(verb)
    lines = section(out)
    said = note(["forbidden_action", "unsolved"])
    at = lines.index(said)
    assert lines[at - 2].endswith("; a try has one kind") and lines[at - 1] == ""
    assert lines[at + 1] == "" and lines[at + 2] == SIGNALS_LINE


@pytest.mark.parametrize("verb", ["fix-check", "changes"])
def test_pl_21_after_the_no_outcome_sentence(tmp_path: Path, verb: str) -> None:
    old = [Try("t1", "unsolved"), Try("t2", None, error="infra: lost"), Try("t3", "passed")]
    new = [Try("t1", "passed"), Try("t2", None, error="infra: lost"), Try("t3", "passed")]
    root = two_runs(tmp_path, old, new)
    path = config(tmp_path, root.name, ["unsolved"])
    lines = section(run([*ARGS[verb], "--config", path]).out)
    said = note(["unsolved"])
    at = lines.index(said)
    assert lines[at - 2].startswith("Tries with no outcome: ") and lines[at - 1] == ""
    assert lines[at - 4].endswith("; a try has one kind")
    assert at == len(lines) - 1


# ---------- PL-22: once ----------


@pytest.mark.parametrize("verb", VERBS)
def test_pl_22_named_once_in_the_whole_report(ran_once: Callable[[str], tuple[str, dict[str, Any]]], verb: str) -> None:
    out, _ = ran_once(verb)
    said = note(["forbidden_action", "unsolved"])
    assert out.count(said) == 1
    assert out.count("Trace has no kind for") == 1
    assert out.count("[taxonomy.labels]") == 1
    assert out.count('= "KIND"') == 1


# ---------- PL-23: the JSON ----------


@pytest.mark.parametrize("verb", VERBS)
def test_pl_23_the_json_names_each_label_and_its_counts(ran_once: Callable[[str], tuple[str, dict[str, Any]]], verb: str) -> None:
    _, doc = ran_once(verb)
    diff = doc["failure_taxonomy_diff"]
    a, b = ARMS[verb]
    assert list(diff) == [*MAIN_KEYS, "labels_without_kind"]
    assert diff["labels_without_kind"] == [{"label": "forbidden_action", a: 2, b: 1}, {"label": "unsolved", a: 1, b: 0}]
    kinds = {k["failure_kind"]: (k[a], k[b]) for k in diff["kinds"]}
    assert kinds == {"unclassified_error": (3, 1), "wrong_answer": (1, 0), "timeout": (1, 0)}


#: Eight labels with no kind, written out of order (LK-38): left unsorted, they come out sorted
#: on at most one hash seed in 40,320.
EIGHT = ["zeta", "alpha", "mu", "delta", "omega", "beta", "kappa", "gamma"]


@pytest.mark.parametrize("verb", VERBS)
def test_pl_23_eight_labels_are_named_in_sorted_order(tmp_path: Path, verb: str) -> None:
    """LK-38 (ruled yes 2026-11-16): the note and ``labels_without_kind`` name eight labels sorted,
    so a note left unsorted is caught on every hash seed, not only on most."""
    ordered = ["alpha", "beta", "delta", "gamma", "kappa", "mu", "omega", "zeta"]
    assert sorted(EIGHT) == ordered
    old = [Try(f"t{i}", label) for i, label in enumerate(EIGHT)]
    new = [Try(f"t{i}", "passed") for i in range(len(EIGHT))]
    root = two_runs(tmp_path, old, new)
    path = config(tmp_path, root.name, EIGHT)
    lines = section(run([*ARGS[verb], "--config", path]).out)
    said = [line for line in lines if line.startswith("Trace has no kind for")]
    assert said == [note(EIGHT)]
    assert said[0].startswith(
        "Trace has no kind for the labels alpha, beta, delta, gamma, kappa, mu, omega and zeta, so their failed tries ")
    assert 'as alpha = "KIND"' in said[0]
    diff = run([*ARGS[verb], "--config", path, "--json"]).json()["failure_taxonomy_diff"]
    a, b = ARMS[verb]
    assert diff["labels_without_kind"] == [{"label": label, a: 1, b: 0} for label in ordered]


# ---------- PL-24: silent when every label has a kind ----------


@pytest.mark.parametrize("verb", VERBS)
@pytest.mark.parametrize("labels", [None, 'forbidden_action = "unclassified_error"\nunsolved = "unclassified_error"\n'],
                         ids=["defaults", "named-unclassified"])
def test_pl_24_no_note_when_every_label_has_a_kind(tmp_path: Path, verb: str, labels: str | None) -> None:
    failed = ["wrong_state", "wall_timeout"] if labels is None else FAILED
    out, doc = _ran(tmp_path, verb, labels=labels, failed=failed)
    assert "Trace has no kind" not in out and "[taxonomy.labels]" not in out
    assert list(doc["failure_taxonomy_diff"]) == MAIN_KEYS
    lines = section(out)
    at = next(i for i, x in enumerate(lines) if x.endswith("; a try has one kind"))
    assert lines[at + 1:at + 3] == ["", SIGNALS_LINE]


@pytest.mark.parametrize("verb", VERBS)
def test_pl_24_a_table_naming_them_silences_it(tmp_path: Path, verb: str) -> None:
    out, doc = _ran(tmp_path, verb, labels='forbidden_action = "guardrail_blocked"\nunsolved = "wrong_answer"\n')
    assert "Trace has no kind" not in out
    diff = doc["failure_taxonomy_diff"]
    assert list(diff) == MAIN_KEYS
    a, b = ARMS[verb]
    assert {k["failure_kind"]: (k[a], k[b]) for k in diff["kinds"]} == \
        {"guardrail_blocked": (2, 1), "wrong_answer": (2, 0), "timeout": (1, 0)}


@pytest.mark.parametrize("verb", VERBS)
def test_pl_24_one_named_one_not(tmp_path: Path, verb: str) -> None:
    out, doc = _ran(tmp_path, verb, labels='forbidden_action = "guardrail_blocked"\n')
    assert note(["unsolved"]) in section(out)
    a, b = ARMS[verb]
    assert doc["failure_taxonomy_diff"]["labels_without_kind"] == [{"label": "unsolved", a: 1, b: 0}]


# ---------- PL-25: the plain words ----------


@pytest.mark.parametrize(("verb", "word"), [
    *[(VERBS[0], word) for word in ("fail", "failed", "failure", "missed")],
    *[(verb, "fail") for verb in VERBS[1:]],
])
def test_pl_25_a_plain_word_is_never_named(tmp_path: Path, verb: str, word: str) -> None:
    root = two_runs(tmp_path, [Try("t", word), Try("u", "passed")], [Try("t", "passed"), Try("u", "passed")])
    path = config(tmp_path, root.name, [word])
    out = run([*ARGS[verb], "--config", path]).out
    doc = run([*ARGS[verb], "--config", path, "--json"]).json()["failure_taxonomy_diff"]
    assert "Trace has no kind" not in out and list(doc) == MAIN_KEYS
    a, b = ARMS[verb]
    assert doc["kinds"] == [{"failure_kind": "unclassified_error", a: 1, b: 0}]


def test_pl_25_beside_a_label_the_plain_word_is_left_out(tmp_path: Path) -> None:
    root = two_runs(tmp_path, [Try("t", "fail"), Try("u", "unsolved")], [Try("t", "passed"), Try("u", "passed")])
    path = config(tmp_path, root.name, ["fail", "unsolved"])
    assert note(["unsolved"]) in section(run([*ARGS["changes"], "--config", path]).out)


# ---------- PL-26: only a failed try left unclassified ----------


def test_pl_26_not_a_passing_try_nor_a_try_with_a_cause(tmp_path: Path) -> None:
    old = [Try("t1", "unsolved", spans=[{"kind": "tool", "error": "ToolError"}]), Try("t2", "zz_pass"), Try("t3", "wrong_state")]
    new = [Try("t1", "passed"), Try("t2", "zz_pass"), Try("t3", "passed")]
    root = two_runs(tmp_path, old, new)
    path = config(tmp_path, root.name, ["unsolved", "wrong_state"])
    out = run([*ARGS["changes"], "--config", path]).out
    diff = run([*ARGS["changes"], "--config", path, "--json"]).json()["failure_taxonomy_diff"]
    assert "Trace has no kind" not in out and list(diff) == MAIN_KEYS
    assert diff["kinds"] == [{"failure_kind": "tool_error", "a": 1, "b": 0}, {"failure_kind": "wrong_answer", "a": 1, "b": 0}]


# ---------- PL-27: only a run Prove swept ----------


def test_pl_27_an_imported_run_counts_zero(tmp_path: Path) -> None:
    from poisson_trace.ingest.rows import Row, Run
    from poisson_trace.ingest.writer import write

    root = two_runs(tmp_path, [Try("c1", "unsolved"), Try("c2", "passed")], [Try("c1", "passed"), Try("c2", "passed")], axis="case")
    rows = [Row("c1", "unsolved", None, None, result="fail"), Row("c2", "passed", None, None, result="pass")]
    write(Run("imp", "table", tuple(rows), "2026-11-16T09:30:00Z", "given", {}, ()), root)
    path = config(tmp_path, root.name, ["unsolved"])
    for argv, (a, b) in ((["changes", "old", "imp"], ("a", "b")), (["changes", "imp", "old"], ("a", "b"))):
        diff = run([*argv, "--config", path, "--json"]).json()["failure_taxonomy_diff"]
        assert diff["same_rules"] is True
        swept, imported = (a, b) if argv[1] == "old" else (b, a)
        assert diff["labels_without_kind"] == [{"label": "unsolved", swept: 1, imported: 0}]


# ---------- PL-28: different rules ----------


def test_pl_28_no_note_under_different_rules(tmp_path: Path) -> None:
    from poisson_trace.ingest.rows import Row, Run
    from poisson_trace.ingest.writer import write

    root = two_runs(tmp_path, [Try("c1", "unsolved"), Try("c2", "passed")], [Try("c1", "passed"), Try("c2", "passed")], axis="case")
    rows = (Row("c1", "x", None, None, result="fail"), Row("c2", "y", None, None, result="pass"))
    write(Run("imp", "table", rows, "2026-11-16T09:30:00Z", "given", {}, ()), root)
    path = config(tmp_path, root.name, ["unsolved"], labels='wrong_state = "crash"\n')
    out = run(["changes", "old", "imp", "--config", path]).out
    diff = run(["changes", "old", "imp", "--config", path, "--json"]).json()["failure_taxonomy_diff"]
    assert diff["same_rules"] is False and list(diff) == MAIN_KEYS
    assert "Trace has no kind" not in out


# ---------- PL-29: a --verdicts join ----------


def test_pl_29_a_verdicts_join_leaves_the_labels(tmp_path: Path) -> None:
    """A verdicts file cannot give a Prove try another outcome (it fills only what the source
    left out, and an errored try's is recorded), so no try it joins carries its word: the
    labels named are the store's."""
    from poisson_prove.store import config_hash

    old = [Try("t1", None, error="infra: lost"), Try("t2", "passed"), Try("t3", "unsolved")]
    new = [Try("t1", None, error="infra: lost"), Try("t2", "passed"), Try("t3", "passed")]
    root = two_runs(tmp_path, old, new)
    path = config(tmp_path, root.name, ["unsolved"])
    verdicts = tmp_path / "verdicts.csv"
    verdicts.write_text(f"case,input,outcome,score,failure_kind\n{config_hash({'task': 't3'})},,,0.5,\n", encoding="utf-8")
    plain = run([*ARGS["changes"], "--config", path, "--json"]).json()["failure_taxonomy_diff"]
    ran = run([*ARGS["changes"], "--config", path, "--verdicts", verdicts, "--json"])
    assert ran.code == 0, ran.text
    diff = ran.json()["failure_taxonomy_diff"]
    assert diff["labels_without_kind"] == plain["labels_without_kind"] == [{"label": "unsolved", "a": 1, "b": 0}]
    refused = tmp_path / "refused.csv"
    refused.write_text(f"case,input,outcome,score,failure_kind\n{config_hash({'task': 't1'})},,fail,,\n", encoding="utf-8")
    assert run([*ARGS["changes"], "--config", path, "--verdicts", refused]).code != 0


# ---------- PL-30: the saved verdict ----------


def test_pl_30_the_saved_verdict_and_its_report(tmp_path: Path) -> None:
    root = _store(tmp_path)
    path = config(tmp_path, root.name, FAILED)
    ran = run([*ARGS["fix-check"], "--config", path, "--save", "--json"])
    assert ran.code == 0, ran.text
    saved = Path(ran.json()["saved"])
    folder = saved if saved.is_absolute() else root / saved
    result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    assert result["failure_taxonomy_diff"]["labels_without_kind"] == [{"label": "forbidden_action", "old": 2, "new": 1},
                                                                       {"label": "unsolved", "old": 1, "new": 0}]
    texts = [p.read_text(encoding="utf-8") for p in folder.rglob("*.md")]
    assert texts and all(t.count(note(["forbidden_action", "unsolved"])) == 1 for t in texts)


# ---------- PL-31: the committed stores ----------

COMMITTED = {
    "tau2": (TAU2, "20260915T210140Z-4847", "20260915T211148Z-965d", ["unsolved"], [{"label": "unsolved", "a": 110, "b": 112}]),
    "cs": (CS, "20260925T234602Z-3ea0", "20260925T235434Z-af48", ["forbidden_action", "unresolved", "app_error", "max_turns"],
           [{"label": "forbidden_action", "a": 2, "b": 2}, {"label": "unresolved", "a": 2, "b": 2}]),
    "humaneval": (HUMANEVAL, "20260905T185407Z-0313", "20260905T195009Z-18ac", ["failed_assertion", "crashed"],
                  [{"label": "crashed", "a": 8, "b": 11}, {"label": "failed_assertion", "a": 1329, "b": 1376}]),
}


@pytest.mark.parametrize("name", sorted(COMMITTED))
def test_pl_31_the_committed_stores(tmp_path: Path, name: str) -> None:
    src, a, b, failed, want = COMMITTED[name]
    root = tmp_path / name
    shutil.copytree(src, root)
    argv = ["changes", a, b, "--store", root, *[w for f in failed for w in ("--event", f)]]
    out = run(argv)
    assert out.code == 0, out.text
    assert note([x["label"] for x in want]) in section(out.out)
    assert run([*argv, "--json"]).json()["failure_taxonomy_diff"]["labels_without_kind"] == want
