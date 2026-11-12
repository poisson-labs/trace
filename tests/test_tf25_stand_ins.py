"""TF25-73 to TF25-79: ``[signals]`` stands in for the Braintrust reader's flags, as it does for
the LangSmith reader's (ruled for that reader on 2026-11-10, where its Session A had recommended
leaving it out; the brief asks the same of this one) and for the Ragas, DeepEval and table
readers' (SA8; spec section 18.5.3). Every test reads a committed capture.

- TF25-73: ``case_field`` stands in for ``--case-from`` and ``outcome_field`` for
  ``--outcome-from``, each written as the flag writes it (``"record"``, ``"metadata:KEY"``,
  ``"input"``; ``"error"``, ``"score:KEY"``, ``"metadata:KEY"``), and ``cut`` for ``--cut``:
  an import given the config and no reader flag writes the run the flags write, from the API's
  answer, the summary and the page's CSV, and records what it used.
- TF25-74: ``score_field`` names the score whose value is read, as ``KEY``, as ``score:KEY``
  or, as the spec's own example writes Braintrust's field, as ``scores.KEY``; an
  ``outcome_field`` beside it wins.
- TF25-75: a cut from the config with no side on the line reads below, and a side given is
  kept; the cut is filled only where a score is read (not with ``error``, and not with a
  metadata value read by ``--failed``), so a config that holds a cut does not make those wrong.
- TF25-76: a flag given wins over the config, each of the three.
- TF25-77: nothing stands in without a config or without ``[signals]``: a missing flag is still
  the parser's refusal, exit 2, and the reader's help is byte for byte the same with a config as
  without.
- TF25-78: an ``[[import]]`` entry and the Python API too may leave to ``[signals]`` what they do
  not say; what an entry says wins.
- TF25-79: ``cost_field`` names the metric the cost is read from in place of
  ``estimated_cost``, as ``NAME`` or, as the spec's example writes it, ``metrics.NAME``: a
  model call's metric in the spans, the row's in the summary and the page's files; a metric no
  row holds records no cost.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tf0_support import chdir, trace
from tf2_support import scratch_home, work  # noqa: F401
from tf17_support import config_text, import_entry, setup_check, write_toml
from tf21_support import run_import
from tf25_support import (
    CASES, ERRORED, EXACT, USAGE, approx, bt_argv, by_error, edited, export, imported, metas, outcomes, recs, roots, span_type,
    tally, work_spans, wrong_line,
)

KINDS = ("fetch", "summary", "ui-csv")


def _config(tmp: Path, **signals: Any) -> Path:
    lines = ["version = 1", "[signals]"]
    for key, value in signals.items():
        lines.append(f"{key} = {value!r}" if not isinstance(value, str) else f'{key} = "{value}"')
    path = tmp / "trace.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _bare(files: Any, root: Path, run: str, config: Path, *extra: Any) -> list[str]:
    """An import that gives the reader no flag of its own, only the config."""
    return [*bt_argv(files, root, run, case=None, outcome=None), "--config", str(config), *[str(e) for e in extra]]


def _by_score(version: str) -> dict[str, Any]:
    return {case: None if score is None else ("met" if score >= 0.5 else "missed") for case, score in EXACT[version].items()}


def _by_error(version: str) -> dict[str, str]:
    return {case: "missed" if case == ERRORED[version][0] else "met" for case in CASES}


# ---------- TF25-73 ----------


@pytest.mark.parametrize("kind", KINDS)
def test_tf25_73_the_config_stands_in_for_the_case_the_outcome_and_the_cut(tmp_path: Path, kind: str) -> None:
    config = _config(tmp_path, case_field="input", outcome_field="score:exact", cut=0.5)
    data = imported(_bare(export("baseline", kind), tmp_path / "config", "r", config))
    flags = imported(bt_argv(export("baseline", kind), tmp_path / "flags", "r"))
    assert recs(tmp_path / "config", "r") == recs(tmp_path / "flags", "r")
    assert data["declared"] == flags["declared"]
    assert data["declared"]["case_from"] == "input" and data["declared"]["outcome_from"] == "score:exact"
    assert data["declared"]["cut"] == 0.5 and data["declared"]["side"] == "below"
    for key in ("rows", "cases", "outcomes", "no_outcome", "counts"):
        assert data[key] == flags[key], key


@pytest.mark.parametrize(("case_field", "outcome_field"), [("record", "error"), ("input", "error"), ("none", "error"),
                                                           ("metadata:case", "metadata:version")])
def test_tf25_73_each_value_is_written_as_the_flag_writes_it(tmp_path: Path, case_field: str, outcome_field: str) -> None:
    config = _config(tmp_path, case_field=case_field, outcome_field=outcome_field)
    extra = ["--failed", "baseline"] if outcome_field.startswith("metadata:") else []
    data = imported(_bare(export("baseline", "fetch"), tmp_path / "config", "r", config, *extra))
    flags = imported(bt_argv(export("baseline", "fetch"), tmp_path / "flags", "r", *extra, case=case_field, outcome=outcome_field, cut=None))
    assert data["declared"] == flags["declared"] and data["outcomes"] == flags["outcomes"]
    assert data["declared"]["case_from"] == case_field and data["declared"]["outcome_from"] == outcome_field
    if case_field != "none":
        assert recs(tmp_path / "config", "r") == recs(tmp_path / "flags", "r")


@pytest.mark.parametrize(("field", "value", "flag"), [("case_field", "row", "--case-from"), ("case_field", "example", "--case-from"),
                                                      ("case_field", "metadata.case", "--case-from"), ("outcome_field", "status", "--outcome-from")])
def test_tf25_73_a_value_the_flag_would_not_take_is_refused_as_the_flag_s(tmp_path: Path, field: str, value: str, flag: str) -> None:
    signals = {"case_field": "input", "outcome_field": "error", field: value}
    config = _config(tmp_path, **signals)
    line = wrong_line(run_import(_bare(export("baseline", "fetch"), tmp_path / "st", "r", config)))
    assert flag in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF25-74 ----------


@pytest.mark.parametrize("score_field", ["exact", "score:exact", "scores.exact"])
@pytest.mark.parametrize("kind", KINDS)
def test_tf25_74_score_field_names_the_score(tmp_path: Path, kind: str, score_field: str) -> None:
    config = _config(tmp_path, case_field="input", score_field=score_field, cut=0.5)
    data = imported(_bare(export("candidate", kind), tmp_path / "st", "r", config))
    assert data["declared"]["outcome_from"] == "score:exact"
    assert tally(data) == {"met": 8, "missed": 1} and data["no_outcome"] == {"no score": 1}
    assert {case: r["score"] for case, r in recs(tmp_path / "st", "r").items()} == EXACT["candidate"]


def test_tf25_74_an_outcome_field_beside_it_wins(tmp_path: Path) -> None:
    config = _config(tmp_path, case_field="input", outcome_field="score:gave_answer", score_field="exact", cut=0.5)
    data = imported(_bare(export("baseline", "fetch"), tmp_path / "st", "r", config))
    assert data["declared"]["outcome_from"] == "score:gave_answer" and tally(data) == {"met": 8, "missed": 1}
    other = _config(tmp_path, case_field="input", score_field="exact", cut=0.5)
    assert tally(imported(_bare(export("baseline", "fetch"), tmp_path / "st2", "r", other))) == {"met": 6, "missed": 3}


# ---------- TF25-75 ----------


def test_tf25_75_a_cut_from_the_config_reads_below_and_a_side_given_is_kept(tmp_path: Path) -> None:
    config = _config(tmp_path, case_field="input", outcome_field="score:exact", cut=1)
    below = imported(_bare(export("baseline", "fetch"), tmp_path / "below", "r", config))
    assert (below["declared"]["cut"], below["declared"]["side"]) == (1.0, "below") and tally(below) == {"met": 6, "missed": 3}
    above = imported(_bare(export("baseline", "fetch"), tmp_path / "above", "r", config, "--above"))
    assert (above["declared"]["cut"], above["declared"]["side"]) == (1.0, "above") and tally(above) == {"met": 9}


@pytest.mark.parametrize("kind", KINDS)
def test_tf25_75_the_cut_is_not_filled_where_no_score_is_read(tmp_path: Path, kind: str) -> None:
    """A config whose cut serves another import of the project: by the error, and by a metadata
    value named as failed, there is no score, and the cut is left out, not refused."""
    config = _config(tmp_path, case_field="input", outcome_field="error", cut=0.5)
    data = imported(_bare(export("baseline", kind), tmp_path / "error", "r", config))
    assert "cut" not in data["declared"] and "side" not in data["declared"]
    assert outcomes(tmp_path / "error", "r") == _by_error("baseline")
    config = _config(tmp_path, case_field="input", outcome_field="metadata:version", cut=0.5)
    data = imported(_bare(export("baseline", kind), tmp_path / "failed", "r", config, "--failed", "baseline"))
    assert "cut" not in data["declared"] and tally(data) == {"missed": 9}
    # the same holds when the line names the error over a config that reads a score
    config = _config(tmp_path, case_field="input", outcome_field="score:exact", cut=0.5)
    data = imported(_bare(export("baseline", kind), tmp_path / "line", "r", config, "--outcome-from", "error"))
    assert "cut" not in data["declared"] and tally(data) == {"met": 9, "missed": 1}


@pytest.mark.parametrize("kind", KINDS)
def test_tf25_75_a_metadata_number_takes_the_config_s_cut(tmp_path: Path, kind: str) -> None:
    def grade(rows: list[dict[str, Any]]) -> None:
        for case, root in roots(rows).items():
            root["metadata"] = {**(root["metadata"] or {}), "grade": 0.25 if case in ("c02", "c05") else 0.75}  # type: ignore[index]

    path = edited(tmp_path, "baseline", kind, grade)
    config = _config(tmp_path, case_field="input", outcome_field="metadata:grade", cut=0.5)
    data = imported(_bare(path, tmp_path / "st", "r", config))
    assert data["declared"]["cut"] == 0.5 and tally(data) == {"met": 8, "missed": 2}


# ---------- TF25-76 ----------


def test_tf25_76_a_flag_given_wins_over_the_config(tmp_path: Path) -> None:
    config = _config(tmp_path, case_field="input", outcome_field="score:exact", cut=0.5)
    files = export("baseline", "fetch")
    case = imported(_bare(files, tmp_path / "case", "r", config, "--case-from", "record"))
    assert case["declared"]["case_from"] == "record"
    from tf21_support import records

    assert sorted(r["case"] for r in records(tmp_path / "case", "r")) == list(CASES)
    outcome = imported(_bare(files, tmp_path / "outcome", "r", config, "--outcome-from", "score:gave_answer"))
    assert outcome["declared"]["outcome_from"] == "score:gave_answer" and outcome["declared"]["cut"] == 0.5
    cut = imported(_bare(files, tmp_path / "cut", "r", config, "--cut", "0", "--below"))
    assert cut["declared"]["cut"] == 0.0 and tally(cut) == {"met": 9}
    every = imported(bt_argv(files, tmp_path / "every", "r", "--config", config, case="record", outcome="error", cut=None))
    assert every["declared"]["case_from"] == "record" and every["declared"]["outcome_from"] == "error"
    assert "cut" not in every["declared"]


# ---------- TF25-77 ----------


def test_tf25_77_nothing_stands_in_without_signals(tmp_path: Path) -> None:
    files = export("baseline", "fetch")
    line = wrong_line(run_import(bt_argv(files, tmp_path / "st", "r", case=None, outcome=None)))
    assert "--case-from" in line and "--outcome-from" in line, line
    empty = tmp_path / "trace.toml"
    empty.write_text("version = 1\n", encoding="utf-8")
    line = wrong_line(run_import(_bare(files, tmp_path / "st", "r", empty)))
    assert "--case-from" in line and "--outcome-from" in line, line
    half = _config(tmp_path, case_field="record")
    line = wrong_line(run_import(_bare(files, tmp_path / "st", "r", half)))
    assert "--outcome-from" in line and "--case-from" not in line, line
    scored = _config(tmp_path, case_field="record", outcome_field="score:exact")
    line = wrong_line(run_import(_bare(files, tmp_path / "st", "r", scored)))
    assert "--cut" in line, line
    assert not (tmp_path / "st").exists()


def test_tf25_77_the_help_is_the_same_with_a_config_as_without(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with chdir(plain):
        without = trace(["import", "braintrust", "--help"])
    held = tmp_path / "held"
    held.mkdir()
    _config(held, case_field="record", outcome_field="score:exact", score_field="exact", cut=0.5, cost_field="estimated_cost")
    with chdir(held):
        with_config = trace(["import", "braintrust", "--help"])
        named = trace(["import", "braintrust", "--help", "--config", "trace.toml"])
    assert without.code == with_config.code == named.code == 0
    assert without.out == with_config.out == named.out and without.err == with_config.err == named.err == ""


# ---------- TF25-78 ----------


def test_tf25_78_an_import_entry_takes_what_signals_gives_and_what_it_says_wins(tmp_path: Path) -> None:
    import shutil

    from poisson_trace import config as config_module

    folder = work(tmp_path)
    (folder / "exports").mkdir()
    for version, run in (("baseline", "old"), ("candidate", "new")):
        shutil.copy(export(version, "fetch")[0], folder / "exports" / f"{run}.json")
    signals = '[signals]\ncase_field = "record"\noutcome_field = "score:exact"\ncut = 0.5\n'
    text = config_text(import_entry("exports/old.json", "braintrust", "old"),
                       import_entry("exports/new.json", "braintrust", "new", outcome_from="error"), signals, store=None, events=("missed",))
    held = config_module.parse(text, folder / "trace.toml", "trace.toml", given=False)
    assert [dict(e.options) for e in held.imports] == [{}, {"outcome_from": "error"}]
    write_toml(folder, text)
    checked = setup_check(folder, "--json")
    assert checked.code == 0, checked.text
    lines = [c["line"] for c in checked.json()["checks"] if c["name"] == "import"]
    assert len(lines) == 2 and all("braintrust, 10 rows" in line for line in lines), lines
    from tf2_support import init_yes

    done = init_yes(folder, "--import")
    assert done.code == 0, done.text
    store = folder / "trace-store"
    assert outcomes(store, "old") == _by_score("baseline")
    # the second entry says the error, so the config's score and its cut are not read for it
    assert outcomes(store, "new") == _by_error("candidate")
    assert all(r["score"] is None for r in recs(store, "new").values())


def test_tf25_78_an_entry_that_signals_does_not_complete_is_refused(tmp_path: Path) -> None:
    from poisson_trace import config as config_module

    folder = work(tmp_path)
    text = config_text(import_entry("exports/old.json", "braintrust", "old"), '[signals]\ncase_field = "record"\n', store="s")
    with pytest.raises(config_module.ConfigError) as caught:
        config_module.parse(text, folder / "trace.toml", "trace.toml", given=False)
    assert "outcome_from" in str(caught.value) and "line " in str(caught.value), str(caught.value)


def test_tf25_78_the_python_api_takes_them_too(tmp_path: Path) -> None:
    from poisson_trace import api

    config = _config(tmp_path, case_field="input", outcome_field="score:exact", cut=0.5)
    result = api.import_run(str(tmp_path / "st"), "braintrust", [str(export("baseline", "fetch")[0])], config=str(config), run="r")
    assert result.exit_code == 0
    assert outcomes(tmp_path / "st", "r") == _by_score("baseline")
    by = api.import_run(str(tmp_path / "st"), "braintrust", [str(export("baseline", "fetch")[0])], config=str(config), run="by", outcome_from="error")
    assert by.exit_code == 0 and sum(1 for o in outcomes(tmp_path / "st", "by").values() if o == "missed") == 1


# ---------- TF25-79 ----------


def _billed(kind: str) -> Any:
    """An export whose model calls (or rolled-up rows) also hold a metric ``billed``, twice the
    estimated cost."""
    def add(rows: list[dict[str, Any]]) -> None:
        if kind == "fetch":
            for case in CASES:
                for span in work_spans(rows, case):
                    if span_type(span) == "llm":
                        span["metrics"]["billed"] = 2 * span["metrics"]["estimated_cost"]
        else:
            for row in rows:
                if row["metrics"].get("estimated_cost") is not None:
                    row["metrics"] = {**row["metrics"], "billed": 2 * row["metrics"]["estimated_cost"]}

    return add


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("named", ["billed", "metrics.billed"])
def test_tf25_79_cost_field_names_the_metric_the_cost_is_read_from(tmp_path: Path, kind: str, named: str) -> None:
    path = edited(tmp_path, "baseline", kind, _billed(kind))
    config = _config(tmp_path, cost_field=named)
    imported([*by_error(path, tmp_path / "st", "r"), "--config", config])
    stored, held = recs(tmp_path / "st", "r"), metas(tmp_path / "st", "r")
    where = "llm spans" if kind == "fetch" else "row metrics"
    for case in CASES:
        usage = USAGE["baseline"][case]
        if usage is None:
            assert stored[case]["cost_usd"] is None and "cost_usd" not in held[case], case
        else:
            assert approx(stored[case]["cost_usd"], 2 * usage[3], 1e-12) and approx(held[case]["cost_usd"], 2 * usage[3], 1e-12), case
            assert held[case]["import"]["cost_from"] == where


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("named", ["estimated_cost", "metrics.estimated_cost"])
def test_tf25_79_the_default_is_the_estimated_cost_and_naming_it_changes_nothing(tmp_path: Path, kind: str, named: str) -> None:
    config = _config(tmp_path, cost_field=named)
    imported([*by_error(export("baseline", kind), tmp_path / "named", "r"), "--config", config])
    imported(by_error(export("baseline", kind), tmp_path / "plain", "r"))
    assert recs(tmp_path / "named", "r") == recs(tmp_path / "plain", "r")
    assert recs(tmp_path / "plain", "r")["c10"]["cost_usd"] == 2.76e-05


@pytest.mark.parametrize("kind", KINDS)
def test_tf25_79_a_metric_no_row_holds_records_no_cost(tmp_path: Path, kind: str) -> None:
    config = _config(tmp_path, cost_field="no_such_cost")
    data = imported([*by_error(export("baseline", kind), tmp_path / "st", "r"), "--config", config])
    assert data["rows"] == 10
    for case, rec in recs(tmp_path / "st", "r").items():
        assert rec["cost_usd"] is None, case
        assert "cost_usd" not in metas(tmp_path / "st", "r")[case] and "cost_from" not in metas(tmp_path / "st", "r")[case]["import"]
