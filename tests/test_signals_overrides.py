"""TF21-56 to TF21-63: ``trace.toml`` ``[signals]``, ``[signals.budgets]`` and
``[[taxonomy.rules]]`` (``docs/config.md``). Read and checked by
``config.parse``; at the import, ``cost_field``, the budgets and the rules apply and the
taxonomy's digest is recorded so a verdict can say which rules made it. ``outcome_field``,
``score_field`` and ``cut`` are read and checked but do not stand in for the import's flags;
``case_field`` stands in for ``--case-column`` when the flag is not given (TF21-61)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest
from poisson_prove.store import Store
from signals_support import STARTED, TAU2, records, run_import

from poisson_trace import config
from poisson_trace.ingest import taxonomy
from poisson_trace.ingest.taxonomy import Budgets, Rule

EXAMPLE = """\
version = 1

[signals]
case_field = "metadata.case_id"
outcome_field = "feedback_stats.correctness"
score_field = "scores.Factuality"
cut = 0.8
cost_field = "metrics.estimated_cost"

[signals.budgets]
max_wall_time_s = 30.0
max_total_tokens = 16000
max_cost_usd = 0.10

[[taxonomy.rules]]
failure_kind = "tool_error"
when_error_matches = "SqlDeadlockError|ConnectionResetByPeer"
when_span_kind = "tool"

[[taxonomy.rules]]
failure_kind = "guardrail_blocked"
when_error_matches = "PolicyViolation|PIIBlocked"

[[taxonomy.rules]]
failure_kind = "abstained"
when_metric_below = { metric = "helpfulness", cut = 0.2 }
"""

RULES = (
    Rule("tool_error", when_error_matches="SqlDeadlockError|ConnectionResetByPeer",
         when_span_kind="tool"),
    Rule("guardrail_blocked", when_error_matches="PolicyViolation|PIIBlocked"),
    Rule("abstained", when_metric_below={"metric": "helpfulness", "cut": 0.2}),
)


def parse(text: str, tmp_path: Path) -> Any:
    path = tmp_path / "trace.toml"
    path.write_text(text, encoding="utf-8")
    return config.parse(text, path, "trace.toml", given=False)


# ---------- TF21-56: a config using every key of the three tables reads whole ----------


def test_tf21_56_the_example_reads(tmp_path: Path) -> None:
    cfg = parse(EXAMPLE, tmp_path)
    assert dict(cfg.signals) == {
        "case_field": "metadata.case_id", "outcome_field": "feedback_stats.correctness",
        "score_field": "scores.Factuality", "cut": 0.8, "cost_field": "metrics.estimated_cost",
    }
    assert cfg.budgets == Budgets(max_wall_time_s=30.0, max_total_tokens=16000, max_cost_usd=0.10)
    assert tuple(cfg.rules) == RULES


def test_tf21_56_a_config_without_them_reads_with_none(tmp_path: Path) -> None:
    cfg = parse('version = 1\n[store]\npath = "st"\n', tmp_path)
    assert dict(cfg.signals) == {} and cfg.budgets is None and tuple(cfg.rules) == ()


def test_tf21_56_each_table_alone(tmp_path: Path) -> None:
    cfg = parse('version = 1\n[signals.budgets]\nmax_cost_usd = 1\n', tmp_path)
    assert cfg.budgets == Budgets(max_cost_usd=1.0) and dict(cfg.signals) == {}
    cfg = parse('version = 1\n[[taxonomy.rules]]\nfailure_kind = "crash"\n'
                'when_span_kind = "lifecycle"\n', tmp_path)
    assert tuple(cfg.rules) == (Rule("crash", when_span_kind="lifecycle"),)


# ---------- TF21-57: faults are refused in one sentence naming the line ----------


@pytest.mark.parametrize(
    ("text", "line", "words"),
    [
        ('version = 1\n[signals]\ncost_feild = "c"\n', 3, ["cost_feild", "cost_field"]),
        ('version = 1\n[signals]\ncut = "high"\n', 3, ["cut"]),
        ('version = 1\n[signals.budgets]\nmax_cost_usd = -1\n', 3, ["max_cost_usd"]),
        ('version = 1\n[signals.budgets]\nmax_total_tokens = 1.5\n', 3, ["max_total_tokens"]),
        ('version = 1\n[signals.budgets]\nmax_tokens = 10\n', 3, ["max_tokens", "max_total_tokens"]),
        ('version = 1\n[[taxonomy.rules]]\nfailure_kind = "oops"\nwhen_span_kind = "tool"\n', 3,
         ["oops"]),
        ('version = 1\n[[taxonomy.rules]]\nfailure_kind = "crash"\n', 2, ["when_"]),
        ('version = 1\n[[taxonomy.rules]]\nfailure_kind = "crash"\nwhen_error_matches = "("\n', 4,
         ["when_error_matches"]),
        ('version = 1\n[[taxonomy.rules]]\nfailure_kind = "crash"\nwhen_span_kind = "judge"\n', 4,
         ["judge"]),
        ('version = 1\n[[taxonomy.rules]]\nfailure_kind = "crash"\nwhen_colour = "red"\n', 4,
         ["when_colour"]),
        ('version = 1\n[taxonomy]\nrules = 3\n', 3, ["rules"]),
        ('version = 1\n[taxonomy]\nengine = "llm"\n', 3, ["engine"]),
    ],
)
def test_tf21_57_a_fault_is_refused_naming_its_line(
    tmp_path: Path, text: str, line: int, words: list[str]
) -> None:
    with pytest.raises(config.ConfigError) as caught:
        parse(text, tmp_path)
    message = str(caught.value)
    assert f"line {line}" in message, message
    for w in words:
        assert w in message, (w, message)
    assert "\n" not in message.strip()


# ---------- TF21-58: the digest of the rules a config holds ----------


def test_tf21_58_the_config_gives_its_taxonomy_digest(tmp_path: Path) -> None:
    cfg = parse(EXAMPLE, tmp_path)
    assert cfg.taxonomy_sha256 == taxonomy.taxonomy_sha256(RULES, cfg.budgets)
    plain = parse("version = 1\n", tmp_path)
    assert plain.taxonomy_sha256 == taxonomy.taxonomy_sha256((), None)


def test_tf21_58_the_digest_ignores_comments_and_spacing(tmp_path: Path) -> None:
    spaced = EXAMPLE.replace("[[taxonomy.rules]]", "# a rule\n[[taxonomy.rules]]").replace(
        "cut = 0.8", "cut   =   0.8")
    assert parse(spaced, tmp_path).taxonomy_sha256 == parse(EXAMPLE, tmp_path).taxonomy_sha256


def test_tf21_58_signal_fields_do_not_change_the_digest(tmp_path: Path) -> None:
    other = EXAMPLE.replace('cost_field = "metrics.estimated_cost"', 'cost_field = "cost"')
    assert parse(other, tmp_path).taxonomy_sha256 == parse(EXAMPLE, tmp_path).taxonomy_sha256


# ---------- TF21-59: the import applies cost_field, budgets and rules ----------


def _tau2_table(path: Path) -> list[dict[str, str]]:
    df = Store(TAU2).read("20260915T210140Z-4847", meta=True, trace="none")
    lines = [{"case": h, "outcome": o, "agent_cost": repr(float(m["cost_tau2"]["agent"])),
              "wall_time_s": repr(float(w))}
             for h, o, w, m in zip(df["config_hash"], df["outcome"], df["wall_time"], df["meta"],
                                   strict=True)]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(lines[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(lines)
    return lines


def _import(tmp_path: Path, toml: str) -> list[dict[str, Any]]:
    _tau2_table(tmp_path / "tau2.csv")
    (tmp_path / "trace.toml").write_text(toml, encoding="utf-8")
    r = run_import(["table", tmp_path / "tau2.csv", "--store", tmp_path / "st", "--run", "t",
                    "--case-column", "case", "--outcome-column", "outcome", "--failed",
                    "unsolved", "--started", STARTED, "--config", tmp_path / "trace.toml"])
    assert r.code == 0, r.out + r.err
    return records(tmp_path / "st", "t")


def test_tf21_59_cost_field_names_the_cost_column(tmp_path: Path) -> None:
    lines = _tau2_table(tmp_path / "x.csv")
    recs = _import(tmp_path, 'version = 1\n[signals]\ncost_field = "agent_cost"\n')
    assert sorted(r["cost_usd"] for r in recs) == sorted(float(x["agent_cost"]) for x in lines)


def test_tf21_59_budgets_mark_over_budget(tmp_path: Path) -> None:
    lines = _tau2_table(tmp_path / "x.csv")
    recs = _import(tmp_path, 'version = 1\n[signals.budgets]\nmax_wall_time_s = 30.0\n')
    over = sum(1 for x in lines if float(x["wall_time_s"]) > 30.0)
    assert 0 < over < len(lines)
    assert sum(1 for r in recs if "over_budget" in r["signals"]) == over


def test_tf21_59_a_rule_classifies_before_the_built_ins(tmp_path: Path) -> None:
    toml = ('version = 1\n[signals]\ncost_field = "agent_cost"\n[[taxonomy.rules]]\n'
            'failure_kind = "abstained"\nwhen_metric_below = { metric = "nothing", cut = 1.0 }\n'
            '[[taxonomy.rules]]\nfailure_kind = "guardrail_blocked"\n'
            'when_error_matches = "never-written"\n')
    recs = _import(tmp_path, toml)
    fails = [r for r in recs if r["outcome"] == "fail"]
    # neither rule matches a bare table's failure: the built-ins decide
    assert {r["failure_kind"] for r in fails} == {"unclassified_error"}
    m = Store(tmp_path / "st").manifest("t").environment["import"]
    rules = (Rule("abstained", when_metric_below={"metric": "nothing", "cut": 1.0}),
             Rule("guardrail_blocked", when_error_matches="never-written"))
    assert m["taxonomy_sha256"] == taxonomy.taxonomy_sha256(rules, None)


def test_tf21_59_a_rule_that_matches_wins(tmp_path: Path) -> None:
    toml = ('version = 1\n[[taxonomy.rules]]\nfailure_kind = "abstained"\n'
            'when_metric_below = { metric = "faithfulness", cut = 0.5 }\n')
    path = tmp_path / "r.jsonl"
    src = (Path(__file__).resolve().parent / "fixtures" / "ingest" / "ragas" / "rag-base.jsonl")
    path.write_bytes(src.read_bytes())
    (tmp_path / "trace.toml").write_text(toml, encoding="utf-8")
    r = run_import(["ragas", path, "--store", tmp_path / "st", "--run", "r", "--metric",
                    "faithfulness", "--cut", "0.5", "--below", "--case-column", "case",
                    "--started", STARTED, "--config", tmp_path / "trace.toml"])
    assert r.code == 0, r.out + r.err
    recs = records(tmp_path / "st", "r")
    assert {x["failure_kind"] for x in recs if x["outcome"] == "fail"} == {"abstained"}
    assert {x["failure_kind"] for x in recs if x["outcome"] == "censored"} == {"unclassified_error"}


# ---------- TF21-60: without a config, the built-in digest is recorded ----------


def test_tf21_60_an_import_without_a_config_records_the_built_in_digest(tmp_path: Path) -> None:
    from signals_support import do_import

    do_import("junit-a", tmp_path / "st")
    m = Store(tmp_path / "st").manifest("junit-a").environment["import"]
    assert m["taxonomy_sha256"] == taxonomy.taxonomy_sha256((), None)


# ---------- TF21-61: [signals] case_field stands in for --case-column ----------


def test_tf21_61_case_field_stands_in_for_case_column(tmp_path: Path) -> None:
    """The import takes the case column from ``[signals]`` when the flag is not given."""
    _tau2_table(tmp_path / "tau2.csv")
    (tmp_path / "trace.toml").write_text('version = 1\n[signals]\ncase_field = "case"\n',
                                         encoding="utf-8")
    r = run_import(["table", tmp_path / "tau2.csv", "--store", tmp_path / "st", "--run", "t",
                    "--outcome-column", "outcome", "--failed", "unsolved", "--config",
                    tmp_path / "trace.toml"])
    assert r.code == 0, r.out + r.err
    assert (tmp_path / "st" / "t").exists()
    m = Store(tmp_path / "st").manifest("t").environment["import"]
    assert m["declared"]["case_column"] == "case"


# ---------- TF21-62: a config fault stops the import before anything is written ----------


def test_tf21_62_a_bad_rule_stops_the_import(tmp_path: Path) -> None:
    _tau2_table(tmp_path / "tau2.csv")
    (tmp_path / "trace.toml").write_text(
        'version = 1\n[[taxonomy.rules]]\nfailure_kind = "oops"\nwhen_span_kind = "tool"\n',
        encoding="utf-8")
    r = run_import(["table", tmp_path / "tau2.csv", "--store", tmp_path / "st", "--run", "t",
                    "--case-column", "case", "--outcome-column", "outcome", "--failed",
                    "unsolved", "--config", tmp_path / "trace.toml"])
    assert r.code == 1
    assert "oops" in r.err and "line 3" in r.err
    assert not (tmp_path / "st").exists() or not (tmp_path / "st" / "t").exists()


# ---------- TF21-63: a table named nearly as [signals] is asked about ----------


def test_tf21_63_a_table_named_nearly_as_signals_is_asked_did_you_mean(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError) as caught:
        parse('version = 1\n[sginals]\ncut = 1\n', tmp_path)
    assert str(caught.value) == (
        "trace.toml line 2: [sginals] is not a table; did you mean [signals]?")
