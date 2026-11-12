"""TF26-73 to TF26-79: ``[signals]`` stands in for the Weave reader's flags, as it does for the
LangSmith and Braintrust readers' (ruled for LangSmith on 2026-11-10 and kept for Braintrust; the
brief asks the same of this one) and for the Ragas, DeepEval and table readers' (SA8; spec section
18.5.3). Every test reads a committed capture.

- TF26-73: ``case_field`` stands in for ``--case-from`` and ``outcome_field`` for
  ``--outcome-from``, each written as the flag writes it (``"example"``, ``"example:KEY"``,
  ``"input"``, ``"none"``; ``"status"``, ``"score:KEY"``), and ``cut`` for ``--cut``: an import
  given the config and no reader flag writes the run the flags write, from the service's
  answer, the page's JSON and the page's table, and records what it used.
- TF26-74: ``score_field`` names the scorer whose output is read, as ``KEY``, as ``score:KEY``,
  as ``scores.KEY`` (the spec's own example's form) or as ``output.scores.KEY`` (the path in a
  Weave call, and the page's table's column); an ``outcome_field`` beside it wins.
- TF26-75: a cut from the config with no side on the line reads below, and a side given is
  kept; the cut is filled only where a score is read (not with ``status``), so a config that
  holds a cut does not make that wrong.
- TF26-76: a flag given wins over the config, each of the three.
- TF26-77: nothing stands in without a config or without ``[signals]``: a missing flag is still
  the parser's refusal, exit 2, and the reader's help is byte for byte the same with a config as
  without. Nothing stands in for ``--evaluation``, which no field of ``[signals]`` names.
- TF26-78: an ``[[import]]`` entry and the Python API too may leave to ``[signals]`` what they do
  not say; what an entry says wins.
- TF26-79: ``cost_field`` is not read by this reader: a Weave cost is not one field of a row
  (it is a model's prompt cost and its completion cost, under the model's name), so a config
  that names a cost field for another import of the project changes nothing here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tf0_support import chdir, trace
from tf2_support import scratch_home, work  # noqa: F401
from tf17_support import config_text, import_entry, setup_check, write_toml
from tf21_support import records, run_import
from tf26_support import (
    CASES, DIGEST, ERRORED, EXACT, USAGE, export, imported, metas, outcomes, picked, recs, tally, wrong_line, wv_argv,
)

KINDS = ("pull", "ui-json", "ui-csv")


def _config(tmp: Path, **signals: Any) -> Path:
    lines = ["version = 1", "[signals]"]
    for key, value in signals.items():
        lines.append(f"{key} = {value!r}" if not isinstance(value, str) else f'{key} = "{value}"')
    path = tmp / "trace.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _case(kind: str) -> str:
    return "example:id" if kind == "ui-csv" else "example"


def _bare(name: str, kind: str, root: Path, run: str, config: Path, *extra: Any) -> list[str]:
    """An import that gives the reader no flag of its own but the evaluation to read, where
    the file holds several: only the config."""
    return [*wv_argv(export(name, kind), root, run, *picked(name, kind), case=None, outcome=None), "--config", str(config), *[str(e) for e in extra]]


def _flags(name: str, kind: str, root: Path, run: str, *extra: Any, **flags: Any) -> list[str]:
    flags.setdefault("case", _case(kind))
    return wv_argv(export(name, kind), root, run, *picked(name, kind), *extra, **flags)


def _by_score(version: str) -> dict[str, Any]:
    return {case: None if score is None else ("met" if score >= 0.5 else "missed") for case, score in EXACT[version].items()}


def _by_status(version: str) -> dict[str, str]:
    return {case: "missed" if case == ERRORED[version][0] else "met" for case in CASES}


# ---------- TF26-73 ----------


@pytest.mark.parametrize("kind", KINDS)
def test_tf26_73_the_config_stands_in_for_the_case_the_outcome_and_the_cut(tmp_path: Path, kind: str) -> None:
    config = _config(tmp_path, case_field=_case(kind), outcome_field="score:exact", cut=0.5)
    data = imported(_bare("baseline", kind, tmp_path / "config", "r", config))
    flags = imported(_flags("baseline", kind, tmp_path / "flags", "r"))
    assert recs(tmp_path / "config", "r") == recs(tmp_path / "flags", "r")
    assert data["declared"] == flags["declared"]
    assert data["declared"]["case_from"] == _case(kind) and data["declared"]["outcome_from"] == "score:exact"
    assert data["declared"]["cut"] == 0.5 and data["declared"]["side"] == "below"
    for key in ("rows", "cases", "outcomes", "no_outcome", "counts"):
        assert data[key] == flags[key], key


@pytest.mark.parametrize(("case_field", "outcome_field"), [("example", "status"), ("input", "status"), ("none", "status"), ("example:case", "status")])
def test_tf26_73_each_value_is_written_as_the_flag_writes_it(tmp_path: Path, case_field: str, outcome_field: str) -> None:
    config = _config(tmp_path, case_field=case_field, outcome_field=outcome_field)
    data = imported(_bare("baseline", "expanded", tmp_path / "config", "r", config))
    flags = imported(wv_argv(export("baseline", "expanded"), tmp_path / "flags", "r", case=case_field, outcome=outcome_field, cut=None))
    assert data["declared"] == flags["declared"] and data["outcomes"] == flags["outcomes"]
    assert data["declared"]["case_from"] == case_field and data["declared"]["outcome_from"] == outcome_field
    if case_field != "none":
        assert recs(tmp_path / "config", "r") == recs(tmp_path / "flags", "r")


@pytest.mark.parametrize(("field", "value", "flag"), [("case_field", "row", "--case-from"), ("case_field", "record", "--case-from"),
                                                      ("case_field", "inputs.example.case", "--case-from"), ("outcome_field", "error", "--outcome-from"),
                                                      ("outcome_field", "feedback:exact", "--outcome-from")])
def test_tf26_73_a_value_the_flag_would_not_take_is_refused_as_the_flag_s(tmp_path: Path, field: str, value: str, flag: str) -> None:
    signals = {"case_field": "example", "outcome_field": "status", field: value}
    config = _config(tmp_path, **signals)
    line = wrong_line(run_import(_bare("baseline", "pull", tmp_path / "st", "r", config)))
    assert flag in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF26-74 ----------


@pytest.mark.parametrize("score_field", ["exact", "score:exact", "scores.exact", "output.scores.exact", "exact.exact", "output.scores.exact.exact"])
@pytest.mark.parametrize("kind", KINDS)
def test_tf26_74_score_field_names_the_scorer(tmp_path: Path, kind: str, score_field: str) -> None:
    config = _config(tmp_path, case_field=_case(kind), score_field=score_field, cut=0.5)
    data = imported(_bare("candidate", kind, tmp_path / "st", "r", config))
    key = "exact.exact" if score_field.endswith("exact.exact") else "exact"
    assert data["declared"]["outcome_from"] == f"score:{key}"
    assert tally(data) == {"met": 8, "missed": 1} and data["no_outcome"] == {"no score": 1}
    assert {case: r["score"] for case, r in recs(tmp_path / "st", "r").items()} == EXACT["candidate"]


def test_tf26_74_an_outcome_field_beside_it_wins(tmp_path: Path) -> None:
    config = _config(tmp_path, case_field="example", outcome_field="score:gave_answer", score_field="exact", cut=0.5)
    data = imported(_bare("baseline", "pull", tmp_path / "st", "r", config))
    assert data["declared"]["outcome_from"] == "score:gave_answer" and tally(data) == {"met": 8, "missed": 1}
    other = _config(tmp_path, case_field="example", score_field="exact", cut=0.5)
    assert tally(imported(_bare("baseline", "pull", tmp_path / "st2", "r", other))) == {"met": 6, "missed": 3}


# ---------- TF26-75 ----------


def test_tf26_75_a_cut_from_the_config_reads_below_and_a_side_given_is_kept(tmp_path: Path) -> None:
    config = _config(tmp_path, case_field="example", outcome_field="score:exact", cut=1)
    below = imported(_bare("baseline", "pull", tmp_path / "below", "r", config))
    assert (below["declared"]["cut"], below["declared"]["side"]) == (1.0, "below") and tally(below) == {"met": 6, "missed": 3}
    above = imported(_bare("baseline", "pull", tmp_path / "above", "r", config, "--above"))
    assert (above["declared"]["cut"], above["declared"]["side"]) == (1.0, "above") and tally(above) == {"met": 9}


@pytest.mark.parametrize("kind", KINDS)
def test_tf26_75_the_cut_is_not_filled_where_no_score_is_read(tmp_path: Path, kind: str) -> None:
    """A config whose cut serves another import of the project: by the status there is no
    score, and the cut is left out, not refused."""
    config = _config(tmp_path, case_field=_case(kind), outcome_field="status", cut=0.5)
    data = imported(_bare("baseline", kind, tmp_path / "status", "r", config))
    assert "cut" not in data["declared"] and "side" not in data["declared"]
    assert outcomes(tmp_path / "status", "r") == _by_status("baseline")
    # the same holds when the line names the status over a config that reads a score
    config = _config(tmp_path, case_field=_case(kind), outcome_field="score:exact", cut=0.5)
    data = imported(_bare("baseline", kind, tmp_path / "line", "r", config, "--outcome-from", "status"))
    assert "cut" not in data["declared"] and tally(data) == {"met": 9, "missed": 1}


# ---------- TF26-76 ----------


def test_tf26_76_a_flag_given_wins_over_the_config(tmp_path: Path) -> None:
    config = _config(tmp_path, case_field="input", outcome_field="score:exact", cut=0.5)
    case = imported(_bare("baseline", "expanded", tmp_path / "case", "r", config, "--case-from", "example"))
    assert case["declared"]["case_from"] == "example"
    assert sorted(r["case"] for r in records(tmp_path / "case", "r")) == sorted(DIGEST[c] for c in CASES)
    outcome = imported(_bare("baseline", "expanded", tmp_path / "outcome", "r", config, "--outcome-from", "score:gave_answer"))
    assert outcome["declared"]["outcome_from"] == "score:gave_answer" and outcome["declared"]["cut"] == 0.5
    cut = imported(_bare("baseline", "expanded", tmp_path / "cut", "r", config, "--cut", "0", "--below"))
    assert cut["declared"]["cut"] == 0.0 and tally(cut) == {"met": 9}
    every = imported(wv_argv(export("baseline", "expanded"), tmp_path / "every", "r", "--config", config, case="example", outcome="status", cut=None))
    assert every["declared"]["case_from"] == "example" and every["declared"]["outcome_from"] == "status"
    assert "cut" not in every["declared"]


# ---------- TF26-77 ----------


def test_tf26_77_nothing_stands_in_without_signals(tmp_path: Path) -> None:
    files = export("baseline", "pull")
    line = wrong_line(run_import(wv_argv(files, tmp_path / "st", "r", case=None, outcome=None)))
    assert "--case-from" in line and "--outcome-from" in line, line
    empty = tmp_path / "trace.toml"
    empty.write_text("version = 1\n", encoding="utf-8")
    line = wrong_line(run_import(_bare("baseline", "pull", tmp_path / "st", "r", empty)))
    assert "--case-from" in line and "--outcome-from" in line, line
    half = _config(tmp_path, case_field="example")
    line = wrong_line(run_import(_bare("baseline", "pull", tmp_path / "st", "r", half)))
    assert "--outcome-from" in line and "--case-from" not in line, line
    scored = _config(tmp_path, case_field="example", outcome_field="score:exact")
    line = wrong_line(run_import(_bare("baseline", "pull", tmp_path / "st", "r", scored)))
    assert "--cut" in line, line
    assert not (tmp_path / "st").exists()


def test_tf26_77_nothing_stands_in_for_the_evaluation(tmp_path: Path) -> None:
    """``[signals]`` has no field for it: a file that holds several evaluations is still refused
    naming each, with a whole config beside it."""
    from tf26_support import refused

    config = _config(tmp_path, case_field="example", outcome_field="score:exact", cut=0.5)
    argv = [*wv_argv(export("baseline", "ui-json"), tmp_path / "st", "r", case=None, outcome=None), "--config", str(config)]
    line = refused(run_import(argv))
    assert "4 evaluations" in line and "--evaluation" in line, line


def test_tf26_77_the_help_is_the_same_with_a_config_as_without(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with chdir(plain):
        without = trace(["import", "weave", "--help"])
    held = tmp_path / "held"
    held.mkdir()
    _config(held, case_field="example", outcome_field="score:exact", score_field="exact", cut=0.5, cost_field="estimated_cost")
    with chdir(held):
        with_config = trace(["import", "weave", "--help"])
        named = trace(["import", "weave", "--help", "--config", "trace.toml"])
    assert without.code == with_config.code == named.code == 0
    assert without.out == with_config.out == named.out and without.err == with_config.err == named.err == ""


# ---------- TF26-78 ----------


def test_tf26_78_an_import_entry_takes_what_signals_gives_and_what_it_says_wins(tmp_path: Path) -> None:
    import shutil

    from poisson_trace import config as config_module

    folder = work(tmp_path)
    (folder / "exports").mkdir()
    for version, run in (("baseline", "old"), ("candidate", "new")):
        shutil.copy(export(version, "pull")[0], folder / "exports" / f"{run}.jsonl")
    signals = '[signals]\ncase_field = "example"\noutcome_field = "score:exact"\ncut = 0.5\n'
    text = config_text(import_entry("exports/old.jsonl", "weave", "old"),
                       import_entry("exports/new.jsonl", "weave", "new", outcome_from="status"), signals, store=None, events=("missed",))
    held = config_module.parse(text, folder / "trace.toml", "trace.toml", given=False)
    assert [dict(e.options) for e in held.imports] == [{}, {"outcome_from": "status"}]
    write_toml(folder, text)
    checked = setup_check(folder, "--json")
    assert checked.code == 0, checked.text
    lines = [c["line"] for c in checked.json()["checks"] if c["name"] == "import"]
    assert len(lines) == 2 and all("weave, 10 rows" in line for line in lines), lines
    from tf2_support import init_yes

    done = init_yes(folder, "--import")
    assert done.code == 0, done.text
    store = folder / "trace-store"
    assert outcomes(store, "old") == _by_score("baseline")
    # the second entry says the status, so the config's score and its cut are not read for it
    assert outcomes(store, "new") == _by_status("candidate")
    assert all(r["score"] is None for r in recs(store, "new").values())


def test_tf26_78_an_entry_that_signals_does_not_complete_is_refused(tmp_path: Path) -> None:
    from poisson_trace import config as config_module

    folder = work(tmp_path)
    text = config_text(import_entry("exports/old.jsonl", "weave", "old"), '[signals]\ncase_field = "example"\n', store="s")
    with pytest.raises(config_module.ConfigError) as caught:
        config_module.parse(text, folder / "trace.toml", "trace.toml", given=False)
    assert "outcome_from" in str(caught.value) and "line " in str(caught.value), str(caught.value)


def test_tf26_78_the_python_api_takes_them_too(tmp_path: Path) -> None:
    from poisson_trace import api

    config = _config(tmp_path, case_field="example", outcome_field="score:exact", cut=0.5)
    result = api.import_run(str(tmp_path / "st"), "weave", [str(export("baseline", "pull")[0])], config=str(config), run="r")
    assert result.exit_code == 0
    assert outcomes(tmp_path / "st", "r") == _by_score("baseline")
    by = api.import_run(str(tmp_path / "st"), "weave", [str(export("baseline", "pull")[0])], config=str(config), run="by", outcome_from="status")
    assert by.exit_code == 0 and sum(1 for o in outcomes(tmp_path / "st", "by").values() if o == "missed") == 1
    picked_one = api.import_run(str(tmp_path / "st"), "weave", [str(export("baseline", "ui-json")[0])], config=str(config), run="page",
                                evaluation="trace-fixture-slice-candidate")
    assert picked_one.exit_code == 0 and outcomes(tmp_path / "st", "page") == _by_score("candidate")


# ---------- TF26-79 ----------


@pytest.mark.parametrize("kind", ["pull", "expanded", "ui-json", "ui-csv"])
@pytest.mark.parametrize("named", ["estimated_cost", "metrics.estimated_cost", "prompt_tokens_total_cost", "no_such_cost"])
def test_tf26_79_cost_field_is_not_read_and_changes_nothing(tmp_path: Path, kind: str, named: str) -> None:
    config = _config(tmp_path, cost_field=named)
    imported([*_flags("baseline", kind, tmp_path / "named", "r", outcome="status", cut=None), "--config", config])
    imported(_flags("baseline", kind, tmp_path / "plain", "r", outcome="status", cut=None))
    assert recs(tmp_path / "named", "r") == recs(tmp_path / "plain", "r")
    assert metas(tmp_path / "named", "r") == metas(tmp_path / "plain", "r")
    usage = USAGE["baseline"]["c10"]
    assert usage is not None
    # the cost is still Weave's own: the model's prompt cost and its completion cost together
    assert recs(tmp_path / "plain", "r")["c10"]["cost_usd"] == (usage[3] if kind in ("pull", "expanded") else None)
