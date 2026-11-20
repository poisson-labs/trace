"""PL-1 to PL-9: the Prove reader reads a failure kind from a try's outcome label
(``label_kinds_support``'s opening: items 1, 2, 3 and 6).

- PL-1: the defaults: each kind's own name and Poisson Tasks' nine failure labels, every one,
  and nothing else; a label is matched letter for letter.
- PL-2: the team's own: ``read_rows(..., labels=...)`` takes ``[taxonomy.labels]``; it names
  the kind of a label with no default, wins over a default, and may name ``unclassified_error``.
- PL-3: the order: the rollout's own kind, then Prove's ``timeout`` short of the cap, then the
  team's rules (PL-9), then the built-in rules that find a cause, then the label, then ``wrong_answer`` for a graded try, then
  ``unclassified_error``.
- PL-4: the rollout's own kind: read from its own record of the signals schema with no
  ``case``, only its kind, only a kind of the 13, only on a try that failed or errored; main
  raised ``KeyError`` on such a record.
- PL-5: the signals follow the kind the label gives.
- PL-6: only runs Prove swept: an import's kinds and digest do not move under a table.
- PL-7: the kinds of every try of the committed Prove stores are main's.
- PL-8: ``taxonomy_sha256`` is main's without a table and holds the table under one.
- PL-9: ``[[taxonomy.rules]]`` apply to a run Prove swept: after the
  rollout's own kind and Prove's ``timeout``, before every built-in rule and the label, in the
  order written; the digest holds them; the verbs print what they give; the note counts a try
  they classified as classified. ``[signals.budgets]`` apply too:
  ``over_budget`` from the try's wall time, its steps' tokens in and out together, and the
  rollout's own ``cost_usd``, a signal not recorded never over; the digest holds them; an
  import and a swept run under one config read as the same rules.
"""

from __future__ import annotations

import collections
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from label_kinds_support import (
    CAUSES, CS, DEFAULTS, HUMANEVAL, KINDS, PROVE_013, SIGNALS_SCHEMA, TASKS_LABELS, TAU2, Try, config, own, prove_run,
    note, read_one, run, section, two_runs,
)

from poisson_trace.ingest.prove import read_rows

#: The digest of the built-in rules with no rule and no budget, as the pinned main computes it.
BUILT_IN_DIGEST = "0c4fdf47aa7f7f88f5f1c3712bd2f662d8aafac08e6dfa50a84107c2c75706ba"


# ---------- PL-1: the defaults ----------


def test_pl_1_the_defaults_are_every_kind_and_tasks_labels() -> None:
    from poisson_trace.ingest.taxonomy import LABEL_KINDS

    assert isinstance(LABEL_KINDS, Mapping)
    assert dict(LABEL_KINDS) == DEFAULTS
    assert len(LABEL_KINDS) == 22
    assert set(LABEL_KINDS.values()) <= set(KINDS)


def test_pl_1_tasks_labels_are_the_checkers_own_failures() -> None:
    """The nine labels are every label Poisson Tasks 0.4.2's checker gives but ``passed``."""
    from poisson_tasks.tasks import OUTCOMES

    assert set(TASKS_LABELS) == set(OUTCOMES) - {"passed"}


@pytest.mark.parametrize("label", sorted(DEFAULTS))
def test_pl_1_each_default_is_read(tmp_path: Path, label: str) -> None:
    row = read_one(tmp_path, Try("t", label))
    assert row.result == "fail"
    assert row.failure_kind == DEFAULTS[label]


@pytest.mark.parametrize("label", ["Wrong_State", "wrong-state", "WRONG_STATE", " wrong_state", "wrong_state ", "Timeout"])
def test_pl_1_a_label_is_matched_letter_for_letter(tmp_path: Path, label: str) -> None:
    assert read_one(tmp_path, Try("t", label)).failure_kind == "unclassified_error"


@pytest.mark.parametrize("label", ["unsolved", "unresolved", "forbidden_action", "failed_assertion", "crashed", "fail", "failed",
                                   "error", "max_turns", "violated", "missed"])
def test_pl_1_a_label_with_no_default_stays_unclassified(tmp_path: Path, label: str) -> None:
    assert read_one(tmp_path, Try("t", label)).failure_kind == "unclassified_error"


def test_pl_1_a_passing_try_has_no_kind_whatever_its_label(tmp_path: Path) -> None:
    row = read_one(tmp_path, Try("t", "wrong_state"), failed=["other"])
    assert (row.result, row.failure_kind) == ("pass", None)
    row = read_one(tmp_path / "b", Try("t", "wrong_state"), failed=["other"], labels={"wrong_state": "crash"})
    assert (row.result, row.failure_kind) == ("pass", None)


# ---------- PL-2: the team's own ----------


def test_pl_2_a_team_names_a_label_with_no_default(tmp_path: Path) -> None:
    row = read_one(tmp_path, Try("t", "forbidden_action"), labels={"forbidden_action": "guardrail_blocked"})
    assert row.failure_kind == "guardrail_blocked"


def test_pl_2_a_team_wins_over_a_default(tmp_path: Path) -> None:
    row = read_one(tmp_path, Try("t", "wrong_state"), labels={"wrong_state": "tool_error"})
    assert row.failure_kind == "tool_error"
    row = read_one(tmp_path / "b", Try("t", "crash"), labels={"crash": "wrong_answer"})
    assert row.failure_kind == "wrong_answer"


def test_pl_2_a_team_may_name_unclassified_error(tmp_path: Path) -> None:
    row = read_one(tmp_path, Try("t", "wrong_state"), labels={"wrong_state": "unclassified_error"})
    assert row.failure_kind == "unclassified_error"


def test_pl_2_other_labels_keep_their_defaults(tmp_path: Path) -> None:
    row = read_one(tmp_path, Try("t", "malformed_call"), labels={"wrong_state": "tool_error"})
    assert row.failure_kind == "format_error"


def test_pl_2_an_empty_table_is_no_table(tmp_path: Path) -> None:
    for i, label in enumerate(("wrong_state", "unsolved")):
        a = read_one(tmp_path / f"a{i}", Try("t", label))
        b = read_one(tmp_path / f"b{i}", Try("t", label), labels={})
        assert a == b


# ---------- PL-3: the order ----------

#: Records on which a rule finds a cause, each with the kind it gives, as main gives it.
CAUSED: dict[str, tuple[dict[str, Any], str]] = {
    "tool error": ({"spans": [{"kind": "tool", "error": "ToolError"}]}, "tool_error"),
    "an error that names a time out": ({"spans": [{"kind": "llm", "error": "ReadTimeout"}]}, "timeout"),
    "an error that names a rate limit": ({"spans": [{"kind": "llm", "error": "HTTP 429"}]}, "rate_limit"),
    "an error that names the context": ({"spans": [{"kind": "llm", "error": "context_length exceeded"}]}, "context_overflow"),
    "at the cap": ({"t": 32.0, "horizon": 32.0}, "step_limit"),
    "at the cap in a storm": ({"t": 32.0, "horizon": 32.0, "spans": [{"kind": "tool", "attempt": 4}]}, "loop_detected"),
    "a retrieval error": ({"spans": [{"kind": "retrieval", "error": "NotFound"}]}, "retrieval_error"),
    "a guardrail's words": ({"spans": [{"kind": "llm", "error": "content_filter"}]}, "guardrail_blocked"),
    "a parse error": ({"spans": [{"kind": "llm", "error": "JSONDecodeError"}]}, "format_error"),
    "an error's class": ({"spans": [{"kind": "llm", "error": "ValueError"}]}, "crash"),
}


@pytest.mark.parametrize("case", sorted(CAUSED))
def test_pl_3_a_cause_on_the_record_wins_over_the_label(tmp_path: Path, case: str) -> None:
    given, want = CAUSED[case]
    for i, (label, labels) in enumerate([("wrong_state", None), ("api_error", None), ("unsolved", {"unsolved": "abstained"}),
                                         ("wrong_state", {"wrong_state": "retrieval_error"})]):
        row = read_one(tmp_path / str(i), Try("t", label, **given), labels=labels)
        assert row.failure_kind == want, (case, label, labels)
        # the same try with no label of a kind reads as main reads it
        bare = read_one(tmp_path / f"bare{i}", Try("t", "zz_no_kind", **given))
        assert bare.failure_kind == want, case
    assert want in CAUSES


def test_pl_3_the_label_wins_over_a_score(tmp_path: Path) -> None:
    assert read_one(tmp_path / "a", Try("t", "api_error", confidence=0.2)).failure_kind == "crash"
    assert read_one(tmp_path / "b", Try("t", "turn_limit", confidence=0.0)).failure_kind == "step_limit"
    assert read_one(tmp_path / "c", Try("t", "unsolved", confidence=0.2), labels={"unsolved": "abstained"}).failure_kind == "abstained"
    # a label with no kind: graded, as main reads it
    assert read_one(tmp_path / "d", Try("t", "unsolved", confidence=0.2)).failure_kind == "wrong_answer"


def test_pl_3_the_label_wins_over_an_assertion(tmp_path: Path) -> None:
    spans = [{"kind": "llm", "error": "AssertionError"}]
    assert read_one(tmp_path / "a", Try("t", "malformed_call", spans=spans)).failure_kind == "format_error"
    assert read_one(tmp_path / "b", Try("t", "unsolved", spans=spans)).failure_kind == "wrong_answer"


def test_pl_3_prove_timeout_short_of_the_cap_wins_over_the_table(tmp_path: Path) -> None:
    row = read_one(tmp_path / "a", Try("t", "timeout", t=3.0, horizon=20.0), labels={"timeout": "crash"})
    assert row.failure_kind == "timeout"
    # at the cap a rule finds the cause, as main reads it, the table and the default aside
    for i, labels in enumerate((None, {"timeout": "crash"})):
        row = read_one(tmp_path / f"b{i}", Try("t", "timeout", t=20.0, horizon=20.0), labels=labels)
        assert row.failure_kind == "step_limit"


def test_pl_3_the_rollouts_own_kind_wins_over_everything(tmp_path: Path) -> None:
    cases = [
        Try("t", "wrong_state", meta=own("tool_error")),
        Try("t", "unsolved", meta=own("abstained")),
        Try("t", "timeout", t=3.0, horizon=20.0, meta=own("crash")),
        Try("t", "wrong_state", t=32.0, horizon=32.0, meta=own("retrieval_error")),
        Try("t", "wrong_state", spans=[{"kind": "tool", "error": "ToolError"}], meta=own("wrong_answer")),
        Try("t", "wrong_state", confidence=0.1, meta=own("rate_limit")),
    ]
    for i, t in enumerate(cases):
        row = read_one(tmp_path / str(i), t, labels={"wrong_state": "format_error", "unsolved": "crash", "timeout": "crash"})
        assert row.failure_kind == t.meta["trace_signals"]["failure_kind"], i


# ---------- PL-4: the rollout's own kind ----------


@pytest.mark.parametrize("kind", KINDS)
def test_pl_4_each_kind_a_rollout_records_is_read(tmp_path: Path, kind: str) -> None:
    assert read_one(tmp_path, Try("t", "zz_no_kind", meta=own(kind))).failure_kind == kind


def test_pl_4_an_errored_tries_own_kind_is_read(tmp_path: Path) -> None:
    row = read_one(tmp_path, Try("t", None, error="infra: lost the sandbox", meta=own("timeout")), failed=["x"])
    assert (row.result, row.failure_kind) == ("censored", "timeout")
    row = read_one(tmp_path / "b", Try("t", None, error="infra: lost the sandbox"), failed=["x"])
    assert (row.result, row.failure_kind) == ("censored", "crash")


def test_pl_4_a_passing_tries_own_kind_is_not_read(tmp_path: Path) -> None:
    row = read_one(tmp_path, Try("t", "passed", meta=own("tool_error")), failed=["wrong_state"])
    assert (row.result, row.failure_kind) == ("pass", None)


@pytest.mark.parametrize("meta", [
    own("tool error"), own("Tool_Error"), own(None), own(3), own(["tool_error"]),
    {"trace_signals": {"failure_kind": "tool_error"}},
    {"trace_signals": {"schema": "poisson.trace-signals/2", "failure_kind": "tool_error"}},
    {"trace_signals": "tool_error"},
    {"failure_kind": "tool_error"},
], ids=["spaced", "capital", "none", "number", "list", "no-schema", "other-schema", "text", "bare-key"])
def test_pl_4_anything_else_is_not_read_and_the_label_decides(tmp_path: Path, meta: dict[str, Any]) -> None:
    assert read_one(tmp_path / "a", Try("t", "wrong_state", meta=meta)).failure_kind == "wrong_answer"
    assert read_one(tmp_path / "b", Try("t", "unsolved", meta=meta)).failure_kind == "unclassified_error"


def test_pl_4_only_the_kind_is_read_from_the_rollouts_record(tmp_path: Path) -> None:
    meta = own("tool_error", outcome="pass", repeat=7, wall_time_s=99.0, input_tokens=5, steps=9, signals=["retry_storm"],
               error_type="Boom", score=0.5)
    row = read_one(tmp_path, Try("t", "wrong_state", meta=meta))
    plain = read_one(tmp_path / "b", Try("t", "wrong_state"))
    assert row.failure_kind == "tool_error"
    assert (row.result, row.repeat, row.wall_time_s, row.input_tokens, row.steps, row.error_type, row.score) == \
        (plain.result, plain.repeat, plain.wall_time_s, plain.input_tokens, plain.steps, plain.error_type, plain.score)
    assert "retry_storm" not in row.signals


def test_pl_4_a_whole_record_with_its_case_is_still_read_as_an_import(tmp_path: Path) -> None:
    from poisson_trace.ingest.rows import Row, Run
    from poisson_trace.ingest.writer import write

    rows = [Row("c1", "missed", None, None, result="fail", failure_kind="tool_error")]
    root = tmp_path / "store"
    write(Run("imp", "table", tuple(rows), "2026-11-16T09:00:00Z", "given", {}, ()), root)
    back = read_rows(root, "imp", failed=("wrong_state",), labels={"missed": "crash"})
    assert [(r.case, r.result, r.failure_kind) for r in back] == [("c1", "fail", "tool_error")]


def test_pl_4_a_run_whose_rollouts_record_their_kind_is_read_by_the_verbs(tmp_path: Path) -> None:
    """On main every verb of two runs failed on such a run (``KeyError: 'case'``)."""
    old = [Try(f"t{i}", "wrong_state", meta=own("tool_error")) for i in range(4)] + [Try("t9", "passed")]
    new = [Try(f"t{i}", "passed", meta=own("tool_error")) for i in range(4)] + [Try("t9", "passed")]
    root = two_runs(tmp_path, old, new)
    config(tmp_path, root.name, ["wrong_state"])
    ran = run(["fix-check", "old", "new", "--inputs", "all", "--max-mde", "0.9", "--config", tmp_path / "trace.toml", "--json"])
    assert ran.code == 0, ran.text
    kinds = ran.json()["failure_taxonomy_diff"]["kinds"]
    assert kinds == [{"failure_kind": "tool_error", "old": 4, "new": 0}]


# ---------- PL-5: the signals follow the kind ----------


@pytest.mark.parametrize(("label", "signals"), [
    ("wall_timeout", ("over_budget",)), ("turn_limit", ("over_budget",)), ("timeout", ("over_budget",)),
    ("context_overflow", ("over_budget",)), ("step_limit", ("over_budget",)), ("abstained", ("gave_up",)),
    ("wrong_state", ()), ("malformed_call", ()), ("api_error", ()), ("unsolved", ()),
])
def test_pl_5_the_signals_follow_the_labels_kind(tmp_path: Path, label: str, signals: tuple[str, ...]) -> None:
    assert read_one(tmp_path, Try("t", label)).signals == signals


def test_pl_5_the_signals_follow_the_teams_kind_and_the_rollouts(tmp_path: Path) -> None:
    assert read_one(tmp_path / "a", Try("t", "unsolved"), labels={"unsolved": "step_limit"}).signals == ("over_budget",)
    assert read_one(tmp_path / "b", Try("t", "wrong_state", meta=own("abstained"))).signals == ("gave_up",)


# ---------- PL-6: only runs Prove swept ----------


def _table_import(tmp: Path, extra: list[str]) -> tuple[Any, Path]:
    tmp.mkdir(parents=True, exist_ok=True)
    table = tmp / "results.csv"
    table.write_text("case,outcome\nc1,wrong_state\nc2,passed\nc3,wrong_state\n", encoding="utf-8")
    root = tmp / "tables"
    ran = run(["import", "table", table, "--store", root, "--run", "t", "--case-column", "case", "--outcome-column", "outcome",
               "--failed", "wrong_state", "--started", "2026-11-16T09:00:00Z", *extra])
    assert ran.code == 0, ran.text
    return ran, root


def test_pl_6_an_imports_kinds_do_not_move_under_a_table(tmp_path: Path) -> None:
    from poisson_prove.store import Store

    from poisson_trace.ingest.taxonomy import taxonomy_sha256

    _, plain_root = _table_import(tmp_path / "a", [])
    (tmp_path / "b").mkdir()
    cfg = config(tmp_path / "b", "tables", ["wrong_state"], labels='wrong_state = "crash"\nmissed = "tool_error"\n')
    _, labelled_root = _table_import(tmp_path / "b", ["--config", cfg])
    for root in (plain_root, labelled_root):
        rows = read_rows(root, Store(root).runs()[0], failed=("wrong_state",), labels={"missed": "crash"})
        assert sorted((r.result, r.failure_kind) for r in rows) == [("fail", "unclassified_error")] * 2 + [("pass", None)]
        manifest = json.loads(next(root.glob("*/manifest.json")).read_text(encoding="utf-8"))
        assert manifest["environment"]["import"]["taxonomy_sha256"] == taxonomy_sha256((), None) == BUILT_IN_DIGEST


# ---------- PL-7: the committed stores read as main reads them ----------

#: Each committed run read with every label but its successes as a failure: each label's kinds
#: and their counts on the pinned main.
MAIN_KINDS: dict[tuple[str, str], dict[tuple[str | None, str | None], int]] = {
    ("cs", "20260925T234602Z-3ea0"): {("forbidden_action", "unclassified_error"): 2, ("app_error", "crash"): 2,
                                      ("unresolved", "unclassified_error"): 2, ("max_turns", "step_limit"): 1},
    ("cs", "20260925T235434Z-af48"): {("forbidden_action", "unclassified_error"): 2, ("app_error", "crash"): 2,
                                      (None, "crash"): 3, ("unresolved", "unclassified_error"): 2, ("max_turns", "step_limit"): 1},
    ("humaneval", "20260905T185407Z-0313"): {("failed_assertion", "unclassified_error"): 1329, ("crashed", "unclassified_error"): 8,
                                             ("failed_assertion", "step_limit"): 1},
    ("humaneval", "20260905T195009Z-18ac"): {("failed_assertion", "unclassified_error"): 1376, ("crashed", "unclassified_error"): 11},
    ("prove-0.1.3", "20261104T162926Z-b4d5"): {("violated", "tool_error"): 66, ("timeout", "loop_detected"): 6},
    ("prove-0.1.3", "20261104T162928Z-1596"): {("timeout", "loop_detected"): 15, ("violated", "tool_error"): 21,
                                               ("timeout", "step_limit"): 5},
    ("tau2", "20260915T210140Z-4847"): {("unsolved", "unclassified_error"): 110},
    ("tau2", "20260915T211148Z-965d"): {("unsolved", "unclassified_error"): 112},
    ("tau2", "20260917T140219Z-2b2d"): {("unsolved", "unclassified_error"): 3},
}
STORES = {"cs": CS, "humaneval": HUMANEVAL, "prove-0.1.3": PROVE_013, "tau2": TAU2}
SUCCESSES = {"passed", "completed", "resolved", "solved"}


@pytest.mark.parametrize("key", sorted(MAIN_KINDS), ids=lambda k: f"{k[0]}-{k[1][-4:]}")
def test_pl_7_the_committed_stores_kinds_are_mains(key: tuple[str, str]) -> None:
    from poisson_prove.store import Store

    store, run_id = key
    root = STORES[store]
    labels = sorted({str(o) for o in Store(root).read(run_id, meta=False, trace="none")["outcome"].dropna()} - SUCCESSES)
    rows = read_rows(root, run_id, failed=labels)
    got = collections.Counter((r.outcome, r.failure_kind) for r in rows if r.result in ("fail", "censored"))
    assert dict(got) == MAIN_KINDS[key]
    signals = collections.Counter(s for r in rows for s in r.signals)
    plain = read_rows(root, run_id, failed=labels, labels={})
    assert collections.Counter(s for r in plain for s in r.signals) == signals
    assert [r.failure_kind for r in plain] == [r.failure_kind for r in rows]


# ---------- PL-8: the digest ----------


def _digest(labels: Mapping[str, str] | None) -> str:
    doc: dict[str, Any] = {"schema": "poisson.trace-taxonomy/1", "rules": [], "budgets": {}}
    if labels:
        doc["labels"] = dict(labels)
    text = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_pl_8_the_built_in_digest_is_mains() -> None:
    from poisson_trace.ingest.taxonomy import taxonomy_sha256

    assert taxonomy_sha256((), None) == BUILT_IN_DIGEST == _digest(None)
    assert taxonomy_sha256((), None, None) == taxonomy_sha256((), None, {}) == BUILT_IN_DIGEST


def test_pl_8_a_table_is_in_the_digest() -> None:
    from poisson_trace.ingest.taxonomy import Budgets, Rule, taxonomy_sha256

    table = {"wrong_state": "tool_error", "forbidden_action": "guardrail_blocked", "não": "crash"}
    assert taxonomy_sha256((), None, table) == _digest(table) != BUILT_IN_DIGEST
    assert taxonomy_sha256((), None, dict(reversed(list(table.items())))) == _digest(table)
    rule = Rule("crash", when_error_matches="x")
    budgets = Budgets(max_wall_time_s=3.0)
    with_rules = taxonomy_sha256((rule,), budgets, table)
    doc = {"schema": "poisson.trace-taxonomy/1", "rules": [rule.to_dict()], "budgets": budgets.to_dict(), "labels": table}
    assert with_rules == hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    assert taxonomy_sha256((rule,), budgets) != with_rules


# ---------- PL-9: the team's rules on a run Prove swept ----------


def _rules_read(tmp: Path, t: Try, rules: Any, labels: Mapping[str, str] | None = None,
                failed: list[str] | None = None) -> Any:
    """The one row of a run of ``t``, read with the team's ``rules`` (and ``labels``)."""
    root = prove_run(tmp / "store", "r", [t])
    words = failed if failed is not None else ([t.outcome] if t.outcome else ["x"])
    rows = read_rows(root, "r", words, labels, tuple(rules))
    assert len(rows) == 1
    return rows[0]


def _rule(kind: str, **when: Any) -> Any:
    from poisson_trace.ingest.taxonomy import Rule

    return Rule(kind, **when)


#: A rule that matches every try.
EVERY = {"when_error_matches": ".*"}


def test_pl_9_read_rows_takes_the_rules_and_the_budgets_last_none_by_default(tmp_path: Path) -> None:
    import inspect

    params = inspect.signature(read_rows).parameters
    assert list(params) == ["root", "run_id", "failed", "labels", "rules", "budgets"]
    for i, label in enumerate(("wrong_state", "unsolved", "passed")):
        root = prove_run(tmp_path / f"s{i}", "r", [Try("t", label)])
        words = ["wrong_state", "unsolved"]
        assert read_rows(root, "r", words) == read_rows(root, "r", words, None, ()) == read_rows(root, "r", words, None, (), None)


@pytest.mark.parametrize("case", sorted(CAUSED))
def test_pl_9_a_team_rule_wins_over_every_built_in_cause(tmp_path: Path, case: str) -> None:
    given, want = CAUSED[case]
    assert want != "wrong_answer"
    for i, (label, labels) in enumerate([("wrong_state", None), ("unsolved", None), ("unsolved", {"unsolved": "crash"})]):
        row = _rules_read(tmp_path / str(i), Try("t", label, **given), [_rule("wrong_answer", **EVERY)], labels)
        assert row.failure_kind == "wrong_answer", (case, label)
        # without the rule the built-in rule gives its cause, as main does
        assert _rules_read(tmp_path / f"b{i}", Try("t", label, **given), [], labels).failure_kind == want


def test_pl_9_a_team_rule_wins_over_the_label_a_score_and_an_assertion(tmp_path: Path) -> None:
    rule = [_rule("retrieval_error", **EVERY)]
    cases = [Try("t", "wrong_state"), Try("t", "api_error"), Try("t", "unsolved"), Try("t", "unsolved", confidence=0.2),
             Try("t", "unsolved", spans=[{"kind": "llm", "error": "AssertionError"}]), Try("t", "turn_limit", confidence=0.0)]
    for i, t in enumerate(cases):
        for j, labels in enumerate((None, {"wrong_state": "crash", "unsolved": "abstained", "turn_limit": "timeout"})):
            assert _rules_read(tmp_path / f"{i}-{j}", t, rule, labels).failure_kind == "retrieval_error", (i, j)


def test_pl_9_the_rollouts_own_kind_and_proves_timeout_win_over_a_team_rule(tmp_path: Path) -> None:
    rule = [_rule("crash", **EVERY)]
    assert _rules_read(tmp_path / "a", Try("t", "wrong_state", meta=own("tool_error")), rule).failure_kind == "tool_error"
    assert _rules_read(tmp_path / "b", Try("t", None, error="infra: lost", meta=own("timeout")), rule).failure_kind == "timeout"
    assert _rules_read(tmp_path / "c", Try("t", "timeout", t=3.0, horizon=20.0), rule).failure_kind == "timeout"
    # at the cap Prove's word gives no kind of its own, so the rule decides
    assert _rules_read(tmp_path / "d", Try("t", "timeout", t=20.0, horizon=20.0), rule).failure_kind == "crash"


def test_pl_9_the_first_rule_that_matches_in_the_order_written(tmp_path: Path) -> None:
    spans = [{"kind": "tool", "error": "BookingError: seat gone"}]
    t = Try("t", "wrong_state", spans=spans)
    first = [_rule("guardrail_blocked", when_error_matches="Nothing"), _rule("abstained", when_span_kind="tool"),
             _rule("crash", when_error_matches="Booking")]
    assert _rules_read(tmp_path / "a", t, first).failure_kind == "abstained"
    assert _rules_read(tmp_path / "b", t, list(reversed(first))).failure_kind == "crash"
    both = [_rule("format_error", when_span_kind="tool", when_error_matches="seat"), _rule("crash", **EVERY)]
    assert _rules_read(tmp_path / "c", t, both).failure_kind == "format_error"
    held = [_rule("format_error", when_span_kind="llm", when_error_matches="seat"), _rule("crash", when_error_matches="Nothing")]
    assert _rules_read(tmp_path / "d", t, held).failure_kind == "tool_error"


def test_pl_9_a_rule_that_matches_nothing_leaves_the_order_as_it_was(tmp_path: Path) -> None:
    none = [_rule("crash", when_error_matches="NeverWritten"), _rule("crash", when_span_kind="retrieval")]
    cases = [Try("t", "wrong_state"), Try("t", "unsolved"), Try("t", "unsolved", confidence=0.3), Try("t", "api_error"),
             Try("t", "unsolved", spans=[{"kind": "tool", "error": "ToolError"}]), Try("t", "timeout", t=3.0, horizon=20.0),
             Try("t", "unsolved", meta=own("abstained")), Try("t", None, error="infra: lost the sandbox"), Try("t", "passed")]
    for i, t in enumerate(cases):
        for j, labels in enumerate((None, {"unsolved": "guardrail_blocked"})):
            got = _rules_read(tmp_path / f"{i}-{j}", t, none, labels, failed=["wrong_state", "unsolved", "api_error", "timeout"])
            assert got == _rules_read(tmp_path / f"m{i}-{j}", t, [], labels, failed=["wrong_state", "unsolved", "api_error", "timeout"])


def test_pl_9_each_condition_reads_a_swept_try(tmp_path: Path) -> None:
    spans = [{"kind": "retrieval", "error": "IndexMiss: no passage"}]
    t = Try("t", "unsolved", spans=spans, confidence=0.1)
    assert _rules_read(tmp_path / "a", t, [_rule("abstained", when_error_matches="IndexMiss")]).failure_kind == "abstained"
    assert _rules_read(tmp_path / "b", t, [_rule("abstained", when_error_matches="no passage")]).failure_kind == "abstained"
    assert _rules_read(tmp_path / "c", t, [_rule("abstained", when_span_kind="retrieval")]).failure_kind == "abstained"
    assert _rules_read(tmp_path / "d", t, [_rule("abstained", when_span_kind="tool")]).failure_kind == "retrieval_error"
    # Prove records a confidence and no named metric: a metric rule matches no swept try
    for i, metric in enumerate(("confidence", "score", "accuracy")):
        rule = [_rule("abstained", when_metric_below={"metric": metric, "cut": 0.5})]
        assert _rules_read(tmp_path / f"e{i}", t, rule).failure_kind == "retrieval_error"
        assert _rules_read(tmp_path / f"f{i}", Try("t", "unsolved", confidence=0.1), rule).failure_kind == "wrong_answer"


def test_pl_9_an_errored_try_and_a_passing_one(tmp_path: Path) -> None:
    rule = [_rule("timeout", when_error_matches="lost the sandbox")]
    row = _rules_read(tmp_path / "a", Try("t", None, error="infra: lost the sandbox"), rule)
    assert (row.result, row.failure_kind) == ("censored", "timeout")
    row = _rules_read(tmp_path / "b", Try("t", "passed", spans=[{"kind": "tool", "error": "lost the sandbox"}]), rule,
                      failed=["wrong_state"])
    assert (row.result, row.failure_kind) == ("pass", None)


def test_pl_9_the_signals_follow_the_rules_kind(tmp_path: Path) -> None:
    row = _rules_read(tmp_path / "a", Try("t", "unsolved"), [_rule("step_limit", **EVERY)])
    assert row.failure_kind == "step_limit" and "over_budget" in row.signals
    row = _rules_read(tmp_path / "b", Try("t", "turn_limit"), [_rule("wrong_answer", **EVERY)])
    assert row.failure_kind == "wrong_answer" and "over_budget" not in row.signals


#: The team's rules the verbs are given, as ``trace.toml`` writes them.
RULES_TOML = ('\n[[taxonomy.rules]]\nfailure_kind = "tool_error"\nwhen_error_matches = "BookingError"\n'
              '\n[[taxonomy.rules]]\nfailure_kind = "unclassified_error"\nwhen_span_kind = "retrieval"\n')
BOOKING = [{"kind": "llm", "error": "BookingError: seat gone"}]
MISS = [{"kind": "retrieval", "error": "IndexMiss"}]


def _team_rules() -> tuple[Any, ...]:
    return (_rule("tool_error", when_error_matches="BookingError"), _rule("unclassified_error", when_span_kind="retrieval"))


def _doc_digest(rules: Any, labels: Mapping[str, str] | None = None, budgets: Mapping[str, Any] | None = None) -> str:
    doc: dict[str, Any] = {"schema": "poisson.trace-taxonomy/1", "rules": [r.to_dict() for r in rules], "budgets": dict(budgets or {})}
    if labels:
        doc["labels"] = dict(labels)
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _rule_runs(tmp: Path) -> Path:
    old = [Try("t1", "unsolved", spans=BOOKING), Try("t2", "unsolved", spans=MISS), Try("t3", "unsolved"),
           Try("t4", "forbidden_action", spans=MISS), Try("t5", "passed")]
    new = [Try("t1", "passed"), Try("t2", "passed"), Try("t3", "passed"), Try("t4", "passed"), Try("t5", "passed")]
    return two_runs(tmp, old, new)


FIX_CHECK = ["fix-check", "old", "new", "--inputs", "all", "--max-mde", "0.9"]


def test_pl_9_the_verbs_print_what_the_rules_give(tmp_path: Path) -> None:
    root = _rule_runs(tmp_path)
    path = config(tmp_path, root.name, ["unsolved", "forbidden_action"], extra=RULES_TOML)
    ran = run([*FIX_CHECK, "--config", path, "--json"])
    assert ran.code == 0, ran.text
    diff = ran.json()["failure_taxonomy_diff"]
    assert diff["kinds"] == [{"failure_kind": "tool_error", "old": 1, "new": 0},
                             {"failure_kind": "unclassified_error", "old": 3, "new": 0}]
    digest = _doc_digest(_team_rules())
    assert diff["taxonomy_sha256"] == {"old": digest, "new": digest} and diff["same_rules"] is True
    plain = run([*FIX_CHECK, "--config", path])
    assert plain.code == 0, plain.text
    lines = section(plain.out)
    assert lines[2].startswith("Each failed try's kind of failure, by your own rules and the built-in ones; "
                               "the same rules classified both runs.")
    assert "| tool_error | 1 | 20.0% | 0 | 0.0% | -20.0 points |" in lines


def test_pl_9_the_note_counts_a_try_the_rules_classified_as_classified(tmp_path: Path) -> None:
    """t2 and t4 are unclassified_error by the team's second rule: their labels are not named;
    t3's ``unsolved`` matched no rule and is, once."""
    root = _rule_runs(tmp_path)
    path = config(tmp_path, root.name, ["unsolved", "forbidden_action"], extra=RULES_TOML)
    diff = run([*FIX_CHECK, "--config", path, "--json"]).json()["failure_taxonomy_diff"]
    assert diff["labels_without_kind"] == [{"label": "unsolved", "old": 1, "new": 0}]
    got = "\n".join(section(run([*FIX_CHECK, "--config", path]).out))
    assert note(["unsolved"]) in got and "forbidden_action" not in got
    # without the rules, t2 and t4 are retrieval_error by the built-in rules, and only t3 is named
    config(tmp_path, root.name, ["unsolved", "forbidden_action"])
    bare = run([*FIX_CHECK, "--config", path, "--json"]).json()["failure_taxonomy_diff"]
    assert bare["labels_without_kind"] == [{"label": "unsolved", "old": 1, "new": 0}]
    assert {k["failure_kind"]: k["old"] for k in bare["kinds"]} == {"crash": 1, "retrieval_error": 2, "unclassified_error": 1}
    assert bare["taxonomy_sha256"] == {"old": BUILT_IN_DIGEST, "new": BUILT_IN_DIGEST}


def test_pl_9_a_rule_that_names_every_unclassified_try_silences_the_note(tmp_path: Path) -> None:
    root = _rule_runs(tmp_path)
    extra = RULES_TOML + '\n[[taxonomy.rules]]\nfailure_kind = "unclassified_error"\nwhen_error_matches = ".*"\n'
    path = config(tmp_path, root.name, ["unsolved", "forbidden_action"], extra=extra)
    for verb in ("fix-check", "compare", "changes"):
        argv = {"fix-check": FIX_CHECK, "compare": ["compare", "old", "new", "--max-mde-hr", "9"],
                "changes": ["changes", "old", "new"]}[verb]
        ran = run([*argv, "--config", path, "--json"])
        assert ran.code == 0, ran.text
        assert "labels_without_kind" not in ran.json()["failure_taxonomy_diff"], verb
        assert "Trace has no kind for the label" not in run([*argv, "--config", path]).out, verb


def test_pl_9_the_digest_holds_the_rules_and_the_table(tmp_path: Path) -> None:
    root = _rule_runs(tmp_path)
    table = {"forbidden_action": "guardrail_blocked"}
    path = config(tmp_path, root.name, ["unsolved", "forbidden_action"], labels='forbidden_action = "guardrail_blocked"\n',
                  extra=RULES_TOML)
    diff = run([*FIX_CHECK, "--config", path, "--json"]).json()["failure_taxonomy_diff"]
    digest = _doc_digest(_team_rules(), table)
    assert digest == taxonomy_sha256_of(_team_rules(), table)
    assert diff["taxonomy_sha256"] == {"old": digest, "new": digest}
    assert digest not in (BUILT_IN_DIGEST, _doc_digest(_team_rules()), _doc_digest((), table))
    # t4: the team's rule before the table's kind for its label
    assert {k["failure_kind"]: k["old"] for k in diff["kinds"]} == {"tool_error": 1, "unclassified_error": 3}


def taxonomy_sha256_of(rules: Any, labels: Mapping[str, str] | None) -> str:
    from poisson_trace.ingest.taxonomy import taxonomy_sha256

    return taxonomy_sha256(tuple(rules), None, labels)


def test_pl_9_an_import_made_under_the_same_rules_reads_as_the_same_rules(tmp_path: Path) -> None:
    root = two_runs(tmp_path, [Try("c1", "wrong_state"), Try("c2", "passed")], [Try("c1", "passed"), Try("c2", "passed")], axis="case")
    path = config(tmp_path, root.name, ["wrong_state"], extra=RULES_TOML)
    table = tmp_path / "results.csv"
    table.write_text("case,outcome\nc1,wrong_state\nc2,passed\n", encoding="utf-8")
    ran = run(["import", "table", table, "--store", root, "--run", "imp", "--case-column", "case", "--outcome-column", "outcome",
               "--failed", "wrong_state", "--started", "2026-11-16T09:30:00Z", "--config", path])
    assert ran.code == 0, ran.text
    diff = run(["changes", "old", "imp", "--config", path, "--json"]).json()["failure_taxonomy_diff"]
    assert diff["same_rules"] is True
    assert diff["taxonomy_sha256"] == {"a": _doc_digest(_team_rules()), "b": _doc_digest(_team_rules())}
    # read with no rules, the swept run is the built-in rules' and the import keeps its own
    config(tmp_path, root.name, ["wrong_state"])
    diff = run(["changes", "old", "imp", "--config", path, "--json"]).json()["failure_taxonomy_diff"]
    assert diff["same_rules"] is False
    assert diff["taxonomy_sha256"] == {"a": BUILT_IN_DIGEST, "b": _doc_digest(_team_rules())}


def test_pl_9_an_imports_kinds_do_not_move_with_the_rules_read_beside_it(tmp_path: Path) -> None:
    from poisson_prove.store import Store

    root = tmp_path / "imports"
    table = tmp_path / "results.csv"
    table.write_text("case,outcome\nc1,wrong_state\nc2,passed\n", encoding="utf-8")
    ran = run(["import", "table", table, "--store", root, "--run", "imp", "--case-column", "case", "--outcome-column", "outcome",
               "--failed", "wrong_state", "--started", "2026-11-16T09:30:00Z"])
    assert ran.code == 0, ran.text
    (run_id,) = Store(root).runs()
    before = read_rows(root, run_id, ["wrong_state"])
    assert sorted((r.result, r.failure_kind) for r in before) == [("fail", "unclassified_error"), ("pass", None)]
    every = (*_team_rules(), _rule("crash", **EVERY))
    assert read_rows(root, run_id, ["wrong_state"], None, every) == before
    assert read_rows(root, run_id, ["wrong_state"], {"wrong_state": "tool_error"}, every) == before
    # nor by the budgets: an import was held to its own at the import
    assert read_rows(root, run_id, ["wrong_state"], None, (), _budgets(max_wall_time_s=0.0, max_total_tokens=0)) == before


# ---------- PL-9: the team's budgets on a run Prove swept ----------


def _budgets(**limits: Any) -> Any:
    from poisson_trace.ingest.taxonomy import Budgets

    return Budgets(**limits)


def _budgets_read(tmp: Path, t: Try, budgets: Any, failed: list[str] | None = None) -> Any:
    """The one row of a run of ``t``, read with the team's ``budgets`` and nothing else."""
    root = prove_run(tmp / "store", "r", [t])
    words = failed if failed is not None else ([t.outcome] if t.outcome else ["x"])
    rows = read_rows(root, "r", words, None, (), budgets)
    assert len(rows) == 1
    return rows[0]


def _over(tmp: Path, t: Try, budgets: Any, failed: list[str] | None = None) -> bool:
    return "over_budget" in _budgets_read(tmp, t, budgets, failed).signals


#: Steps that record 40 tokens in and 20 out over two calls, and a tool step with none.
TOKENS = [{"kind": "llm", "tokens": {"in": 30, "out": 5}}, {"kind": "llm", "tokens": {"in": 10, "out": 15}},
          {"kind": "tool", "name": "submit"}]


def test_pl_9_wall_time_is_held_to_its_budget_on_every_try(tmp_path: Path) -> None:
    """Prove records every try's wall time (``wall_time``, 1.0 s in these stores): over a budget
    strictly under it, whether the try failed, passed or errored."""
    tries = [Try("t", "unsolved"), Try("t", "wrong_state"), Try("t", "passed"), Try("t", None, error="infra: lost")]
    for i, t in enumerate(tries):
        assert _over(tmp_path / f"a{i}", t, _budgets(max_wall_time_s=0.5), failed=["unsolved", "wrong_state"]), i
        assert not _over(tmp_path / f"b{i}", t, _budgets(max_wall_time_s=1.0), failed=["unsolved", "wrong_state"]), i
        assert not _over(tmp_path / f"c{i}", t, _budgets(max_wall_time_s=2.0), failed=["unsolved", "wrong_state"]), i
        assert not _over(tmp_path / f"d{i}", t, None, failed=["unsolved", "wrong_state"]), i


def test_pl_9_tokens_are_the_steps_in_and_out_together(tmp_path: Path) -> None:
    t = Try("t", "unsolved", spans=TOKENS)
    row = _budgets_read(tmp_path / "a", t, _budgets(max_total_tokens=59))
    assert (row.input_tokens, row.output_tokens, row.total_tokens) == (40, 20, 60)
    assert "over_budget" in row.signals
    assert not _over(tmp_path / "b", t, _budgets(max_total_tokens=60))
    assert not _over(tmp_path / "c", Try("t", "passed", spans=TOKENS), _budgets(max_total_tokens=60), failed=["unsolved"])
    assert _over(tmp_path / "d", Try("t", "passed", spans=TOKENS), _budgets(max_total_tokens=0), failed=["unsolved"])


@pytest.mark.parametrize("spans", [
    None,
    [{"kind": "llm", "tokens": {"in": 500}}],
    [{"kind": "llm", "tokens": {"out": 500}}],
    [{"kind": "llm", "tokens": {"in": 500}}, {"kind": "llm", "tokens": {"in": 7}}],
], ids=["no tokens", "in only", "out only", "in only twice"])
def test_pl_9_a_try_with_no_total_is_never_over_the_token_budget(tmp_path: Path, spans: Any) -> None:
    """Without both tokens in and out the try records no total: not recorded, never over."""
    row = _budgets_read(tmp_path / "a", Try("t", "unsolved", spans=spans), _budgets(max_total_tokens=0))
    assert row.total_tokens is None and "over_budget" not in row.signals
    errored = _budgets_read(tmp_path / "b", Try("t", None, error="infra: lost"), _budgets(max_total_tokens=0))
    assert errored.total_tokens is None and "over_budget" not in errored.signals


def test_pl_9_cost_is_the_rollouts_own_cost_usd(tmp_path: Path) -> None:
    t = Try("t", "unsolved", meta={"cost_usd": 0.3})
    assert _budgets_read(tmp_path / "a", t, _budgets(max_cost_usd=0.29)).cost_usd == 0.3
    assert _over(tmp_path / "b", t, _budgets(max_cost_usd=0.29))
    assert not _over(tmp_path / "c", t, _budgets(max_cost_usd=0.3))
    assert _over(tmp_path / "d", Try("t", "passed", meta={"cost_usd": 2}), _budgets(max_cost_usd=1), failed=["unsolved"])


@pytest.mark.parametrize("meta", [{}, {"cost_usd": "0.3"}, {"cost_usd": None}, {"cost": 9.0}, {"agent_cost": 9.0},
                                  {"trace_signals": {"schema": SIGNALS_SCHEMA, "cost_usd": 9.0}}],
                         ids=["none", "text", "null", "other name", "a cost_field's name", "in the rollout's record"])
def test_pl_9_a_try_with_no_cost_is_never_over_the_cost_budget(tmp_path: Path, meta: dict[str, Any]) -> None:
    row = _budgets_read(tmp_path, Try("t", "unsolved", meta=meta), _budgets(max_cost_usd=0.0))
    assert row.cost_usd is None and "over_budget" not in row.signals


def test_pl_9_any_one_budget_over_is_enough_and_the_kind_does_not_move(tmp_path: Path) -> None:
    t = Try("t", "unsolved", spans=TOKENS, meta={"cost_usd": 0.3})
    for i, budgets in enumerate([_budgets(max_wall_time_s=0.5, max_total_tokens=100, max_cost_usd=1.0),
                                 _budgets(max_wall_time_s=5.0, max_total_tokens=10, max_cost_usd=1.0),
                                 _budgets(max_wall_time_s=5.0, max_total_tokens=100, max_cost_usd=0.1)]):
        row = _budgets_read(tmp_path / str(i), t, budgets)
        assert "over_budget" in row.signals, i
        assert row.failure_kind == _budgets_read(tmp_path / f"n{i}", t, None).failure_kind == "unclassified_error"
    assert not _over(tmp_path / "x", t, _budgets(max_wall_time_s=5.0, max_total_tokens=100, max_cost_usd=1.0))


def test_pl_9_budgets_and_rules_and_labels_read_together(tmp_path: Path) -> None:
    root = prove_run(tmp_path / "store", "r", [Try("t", "unsolved", spans=TOKENS)])
    rows = read_rows(root, "r", ["unsolved"], {"unsolved": "abstained"}, (_rule("format_error", when_span_kind="tool"),),
                     _budgets(max_total_tokens=10))
    assert (rows[0].failure_kind, rows[0].signals) == ("abstained", ("gave_up", "over_budget"))


#: The budgets the verbs are given, as ``trace.toml`` writes them: every try is over (1.0 s).
BUDGETS_TOML = "\n[signals.budgets]\nmax_wall_time_s = 0.5\nmax_total_tokens = 100\n"


def _budget_runs(tmp: Path) -> Path:
    old = [Try("t1", "unsolved"), Try("t2", "unsolved"), Try("t3", "passed"), Try("t4", "passed")]
    new = [Try("t1", "passed"), Try("t2", "passed"), Try("t3", "passed"), Try("t4", "passed")]
    return two_runs(tmp, old, new)


def test_pl_9_over_budget_shows_in_the_signals_lines_and_the_json(tmp_path: Path) -> None:
    root = _budget_runs(tmp_path)
    path = config(tmp_path, root.name, ["unsolved"], extra=BUDGETS_TOML)
    for verb, arms in (("fix-check", ("old", "new")), ("compare", ("a", "b")), ("changes", ("a", "b"))):
        argv = {"fix-check": FIX_CHECK, "compare": ["compare", "old", "new", "--max-mde-hr", "9"],
                "changes": ["changes", "old", "new"]}[verb]
        ran = run([*argv, "--config", path, "--json"])
        assert ran.code == 0, ran.text
        diff = ran.json()["failure_taxonomy_diff"]
        assert diff["signals"] == [{"signal": "over_budget", arms[0]: 4, arms[1]: 4}], verb
        lines = section(run([*argv, "--config", path]).out)
        assert "| over_budget | 4 | 100.0% | 4 | 100.0% |" in lines, (verb, lines)
    # without the budgets, no signal, as main prints it
    config(tmp_path, root.name, ["unsolved"])
    assert run([*FIX_CHECK, "--config", path, "--json"]).json()["failure_taxonomy_diff"]["signals"] == []


def test_pl_9_the_digest_holds_the_budgets(tmp_path: Path) -> None:
    root = _budget_runs(tmp_path)
    budgets = {"max_wall_time_s": 0.5, "max_total_tokens": 100}
    path = config(tmp_path, root.name, ["unsolved"], extra=BUDGETS_TOML)
    diff = run([*FIX_CHECK, "--config", path, "--json"]).json()["failure_taxonomy_diff"]
    digest = _doc_digest((), None, budgets)
    assert diff["taxonomy_sha256"] == {"old": digest, "new": digest} and digest != BUILT_IN_DIGEST
    assert section(run([*FIX_CHECK, "--config", path]).out)[2].startswith(
        "Each failed try's kind of failure, by your own rules and the built-in ones; the same rules classified both runs.")
    table = {"unsolved": "abstained"}
    config(tmp_path, root.name, ["unsolved"], labels='unsolved = "abstained"\n', extra=BUDGETS_TOML + RULES_TOML)
    diff = run([*FIX_CHECK, "--config", path, "--json"]).json()["failure_taxonomy_diff"]
    digest = _doc_digest(_team_rules(), table, budgets)
    from poisson_trace.ingest.taxonomy import taxonomy_sha256

    assert digest == taxonomy_sha256(_team_rules(), _budgets(**budgets), table)
    assert diff["taxonomy_sha256"] == {"old": digest, "new": digest}
    # with no rules, no table and no budgets: main's digest
    config(tmp_path, root.name, ["unsolved"])
    diff = run([*FIX_CHECK, "--config", path, "--json"]).json()["failure_taxonomy_diff"]
    assert diff["taxonomy_sha256"] == {"old": BUILT_IN_DIGEST, "new": BUILT_IN_DIGEST}


@pytest.mark.parametrize("extra", [BUDGETS_TOML, BUDGETS_TOML + RULES_TOML], ids=["budgets", "budgets and rules"])
def test_pl_9_an_import_and_a_swept_run_under_one_config_read_as_the_same_rules(tmp_path: Path, extra: str) -> None:
    root = two_runs(tmp_path, [Try("c1", "wrong_state"), Try("c2", "passed")], [Try("c1", "passed"), Try("c2", "passed")], axis="case")
    path = config(tmp_path, root.name, ["wrong_state"], extra=extra)
    table = tmp_path / "results.csv"
    table.write_text("case,outcome,wall_time_s\nc1,wrong_state,0.1\nc2,passed,0.9\n", encoding="utf-8")
    ran = run(["import", "table", table, "--store", root, "--run", "imp", "--case-column", "case", "--outcome-column", "outcome",
               "--failed", "wrong_state", "--started", "2026-11-16T09:30:00Z", "--config", path])
    assert ran.code == 0, ran.text
    diff = run(["changes", "old", "imp", "--config", path, "--json"]).json()["failure_taxonomy_diff"]
    assert diff["same_rules"] is True, diff
    assert diff["taxonomy_sha256"]["a"] == diff["taxonomy_sha256"]["b"] != BUILT_IN_DIGEST
    # every swept try is over the wall-time budget
    assert {s["signal"]: s["a"] for s in diff["signals"]}["over_budget"] == 2
