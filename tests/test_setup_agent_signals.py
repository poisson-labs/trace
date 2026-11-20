"""TF17-42: ``[signals]``'s field mappings stand in for the import's required flags
(``docs/config.md``, "``[signals]``: where an import finds what it reads").

- ``case_field`` stands in for ``--case-column`` (the Ragas and table readers);
  ``outcome_field`` for ``--outcome-column`` (table); ``score_field`` for ``--metric`` (Ragas,
  DeepEval) and ``--score-column`` (table); ``cut`` for ``--cut`` (Ragas, table, DeepEval), and
  a cut that came from the config with no side flag reads ``below``, said on the ``declared``
  line as a side the flags gave would be.
- A flag given on the command line wins over the config; the run records what the import used.
- Nothing stands in without a config, or when the config has no ``[signals]``: the import's
  help is unchanged byte for byte and the refusal of a missing flag is argparse's (exit 2).
- ``cost_field``, the budgets and the rules keep working as TF21's tests hold them.
- A ``[[import]]`` entry too may leave to ``[signals]`` what it does not say.

TF21-61 holds the same from TF21's side: ``case_field`` stands in for ``--case-column``.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from poisson_prove.store import Store

from conftest import TAU2
from setup_support import scratch_home, work  # noqa: F401
from setup_agent_support import config_text, import_entry, ragas_entry, ragas_pair, rows_of, setup_check, trace_in, write_toml

T_A = "20260915T210140Z-4847"


def tau2_table(path: Path) -> None:
    df = Store(TAU2).read(T_A, meta=True, trace="none")
    lines = [
        {"case": h, "outcome": o, "faith": repr(float(m["cost_tau2"]["agent"]))}
        for h, o, m in zip(df["config_hash"], df["outcome"], df["meta"], strict=True)
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(lines[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(lines)


def declared(store: Path, run: str) -> dict[str, object]:
    held = Store(store).manifest(run).environment["import"]["declared"]
    return dict(held)


# ---------- the stand-ins ----------


def test_tf17_42_case_field_stands_in_for_case_column_on_a_table(tmp_path: Path) -> None:
    folder = work(tmp_path)
    tau2_table(folder / "t.csv")
    write_toml(folder, 'version = 1\n[signals]\ncase_field = "case"\n')
    r = trace_in(folder, ["import", "table", "t.csv", "--store", "st", "--run", "t", "--outcome-column", "outcome", "--failed", "unsolved"])
    assert r.code == 0, r.text
    assert declared(folder / "st", "t")["case_column"] == "case"
    assert "case_column case" in r.out, r.out


def test_tf17_42_score_field_and_cut_stand_in_for_metric_and_cut_on_ragas(tmp_path: Path) -> None:
    folder = work(tmp_path)
    base, _ = ragas_pair(folder)
    write_toml(folder, 'version = 1\n[signals]\nscore_field = "faithfulness"\ncut = 0.5\ncase_field = "case"\n')
    r = trace_in(folder, ["import", "ragas", base, "--store", "st", "--run", "r"])
    assert r.code == 0, r.text
    d = declared(folder / "st", "r")
    assert d["metric"] == "faithfulness" and float(str(d["cut"])) == 0.5 and d["side"] == "below" and d["case_column"] == "case", d
    assert "side below" in r.out, r.out
    rows = rows_of(folder / "st", "r")
    assert sum(1 for row in rows if row["outcome"] == "missed") == 52


def test_tf17_42_score_field_outcome_field_and_cut_stand_in_on_a_table(tmp_path: Path) -> None:
    folder = work(tmp_path)
    tau2_table(folder / "t.csv")
    write_toml(folder, 'version = 1\n[signals]\ncase_field = "case"\noutcome_field = "outcome"\n')
    r = trace_in(folder, ["import", "table", "t.csv", "--store", "st", "--run", "o", "--failed", "unsolved"])
    assert r.code == 0, r.text
    assert declared(folder / "st", "o")["outcome_column"] == "outcome"
    write_toml(folder, 'version = 1\n[signals]\ncase_field = "case"\nscore_field = "faith"\ncut = 0.01\n')
    r = trace_in(folder, ["import", "table", "t.csv", "--store", "st", "--run", "s", "--above"])
    assert r.code == 0, r.text
    d = declared(folder / "st", "s")
    assert d["score_column"] == "faith" and d["side"] == "above", d


def test_tf17_42_a_flag_given_wins_over_the_config(tmp_path: Path) -> None:
    folder = work(tmp_path)
    base, _ = ragas_pair(folder)
    write_toml(folder, 'version = 1\n[signals]\nscore_field = "faithfulness"\ncut = 0.5\ncase_field = "nothing"\n')
    r = trace_in(folder, ["import", "ragas", base, "--store", "st", "--run", "r", "--metric", "answer_relevancy", "--cut", "0.9", "--above", "--case-column", "case"])
    assert r.code == 0, r.text
    d = declared(folder / "st", "r")
    assert d["metric"] == "answer_relevancy" and float(str(d["cut"])) == 0.9 and d["side"] == "above" and d["case_column"] == "case", d


def test_tf17_42_deepeval_takes_the_metric_and_the_cut_from_the_config(tmp_path: Path) -> None:
    from setup_support import deepeval_file

    folder = work(tmp_path)
    deepeval_file(folder / "d.json")
    write_toml(folder, 'version = 1\n[signals]\nscore_field = "Tests Passed"\ncut = 0.5\n')
    r = trace_in(folder, ["import", "deepeval", "d.json", "--store", "st", "--run", "d", "--case", "name"])
    assert r.code == 0, r.text
    d = declared(folder / "st", "d")
    assert d["metric"] == "Tests Passed" and d["side"] == "below", d


# ---------- nothing stands in without the config ----------


@pytest.mark.parametrize("reader", ["ragas", "table", "deepeval"])
def test_tf17_42_the_help_and_a_missing_flags_refusal_are_argparses(tmp_path: Path, reader: str) -> None:
    folder = work(tmp_path)
    helped = trace_in(folder, ["import", reader, "--help"])
    assert helped.code == 0 and helped.out.startswith("usage"), helped.text
    for required in {"ragas": ("--metric", "--cut", "--case-column"), "table": ("--case-column",), "deepeval": ("--metric", "--cut", "--case")}[reader]:
        assert required in helped.out
    assert "[signals]" not in helped.out and "case_field" not in helped.out, helped.out
    base, _ = ragas_pair(folder)
    r = trace_in(folder, ["import", "ragas", base, "--store", "st", "--run", "r", "--metric", "faithfulness", "--cut", "0.5", "--below"])
    assert r.code == 2, r.text
    assert "--case-column" in r.err and "required" in r.err, r.err
    write_toml(folder, "version = 1\n")
    r = trace_in(folder, ["import", "ragas", base, "--store", "st", "--run", "r", "--metric", "faithfulness", "--cut", "0.5", "--below"])
    assert r.code == 2 and "--case-column" in r.err, r.text
    assert not (folder / "st").exists()


def test_tf17_42_a_field_the_file_does_not_have_is_the_readers_refusal(tmp_path: Path) -> None:
    folder = work(tmp_path)
    base, _ = ragas_pair(folder)
    write_toml(folder, 'version = 1\n[signals]\nscore_field = "faithfulness"\ncut = 0.5\ncase_field = "question_id"\n')
    r = trace_in(folder, ["import", "ragas", base, "--store", "st", "--run", "r"])
    assert r.code == 1 and "question_id" in r.err, r.text
    assert not (folder / "st" / "r").exists()


# ---------- cost_field, the budgets and the rules still apply ----------


def test_tf17_42_cost_field_and_budgets_still_apply(tmp_path: Path) -> None:
    folder = work(tmp_path)
    tau2_table(folder / "t.csv")
    write_toml(folder, 'version = 1\n[signals]\ncase_field = "case"\ncost_field = "faith"\n[signals.budgets]\nmax_cost_usd = 0.0\n')
    r = trace_in(folder, ["import", "table", "t.csv", "--store", "st", "--run", "t", "--outcome-column", "outcome", "--failed", "unsolved"])
    assert r.code == 0, r.text
    rows = rows_of(folder / "st", "t")
    assert any(row["meta"]["trace_signals"]["cost_usd"] for row in rows), "cost_field no longer read"
    assert any("over_budget" in row["meta"]["trace_signals"]["signals"] for row in rows), "the budget no longer applies"


# ---------- an [[import]] entry may leave to [signals] what it does not say ----------


def test_tf17_42_an_import_entry_takes_what_signals_gives(tmp_path: Path) -> None:
    folder = work(tmp_path)
    base, raft = ragas_pair(folder)
    text = config_text(
        import_entry(base, "ragas", "old"),
        import_entry(raft, "ragas", "new"),
        '[signals]\nscore_field = "faithfulness"\ncut = 0.5\ncase_field = "case"\n',
        store=None,
        events=("missed",),
    )
    write_toml(folder, text)
    r = setup_check(folder)
    assert r.code == 0, r.text
    assert "faithfulness at 0.5" in r.out, r.out
    write_toml(folder, config_text(ragas_entry(base, "old", cut=0.9), import_entry(raft, "ragas", "new"), '[signals]\nscore_field = "faithfulness"\ncut = 0.5\ncase_field = "case"\n', store=None, events=("missed",)))
    r = setup_check(folder)
    assert r.code == 0, r.text
    assert "faithfulness at 0.9" in r.out and "faithfulness at 0.5" in r.out, r.out
