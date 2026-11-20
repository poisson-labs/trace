"""TF24-73 to TF24-79: ``[signals]`` stands in for the LangSmith reader's flags, as it does for the
Ragas, DeepEval and table readers (``docs/config.md``, under ``[signals]``). Every test reads a
committed capture.

- TF24-73: ``case_field`` stands in for ``--case-from`` and ``outcome_field`` for
  ``--outcome-from``, each written as the flag writes it (``"example"``, ``"metadata:KEY"``,
  ``"input"``; ``"status"``, ``"feedback:KEY"``, ``"metadata:KEY"``), and ``cut`` for ``--cut``:
  an import given the config and no reader flag writes the run the flags write, from the API's
  answer, the command's export and the CSV, and records what it used.
- TF24-74: ``score_field`` names the feedback key whose score is read, as ``KEY`` or as
  ``feedback:KEY``; an ``outcome_field`` beside it wins.
- TF24-75: a cut from the config with no side on the line reads below, and a side given is
  kept; the cut is filled only where a score is read (not with ``status``, and not with a
  metadata value read by ``--failed``), so a config that holds a cut does not make those wrong.
- TF24-76: a flag given wins over the config, each of the three.
- TF24-77: nothing stands in without a config or without ``[signals]``: a missing flag is still
  the parser's refusal, exit 2, and the reader's help is byte for byte the same with a config as
  without.
- TF24-78: an ``[[import]]`` entry and the Python API too may leave to ``[signals]`` what they do
  not say; what an entry says wins.
- TF24-79: ``cost_field`` names the run's field the cost is read from in place of
  ``total_cost``: the API's field, the command's under ``costs``, the CSV's column; a field no
  run holds records no cost.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from look_support import chdir, trace
from setup_support import scratch_home, work  # noqa: F401
from setup_agent_support import config_text, import_entry, setup_check, write_toml
from signals_support import run_import
from langsmith_support import (
    CASES, ERRORED, EXACT, approx, by_status, columns, export, imported, ls_argv, metas, recs, rows_of, roots, tally,
    trace_rows, wrong_line,
)

KINDS = ("v1", "cli-runs", "ui")


def _config(tmp: Path, **signals: Any) -> Path:
    lines = ["version = 1", "[signals]"]
    for key, value in signals.items():
        lines.append(f"{key} = {value!r}" if not isinstance(value, str) else f'{key} = "{value}"')
    path = tmp / "trace.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _bare(files: Any, root: Path, run: str, config: Path, *extra: Any) -> list[str]:
    """An import that gives the reader no flag of its own, only the config."""
    return [*ls_argv(files, root, run, case=None, outcome=None), "--config", str(config), *[str(e) for e in extra]]


def _outcomes(root: Path, run: str = "r") -> dict[str, Any]:
    return {case: row["outcome"] for case, row in columns(root, run).items()}


# ---------- TF24-73 ----------


@pytest.mark.parametrize("kind", KINDS)
def test_tf24_73_the_config_stands_in_for_the_case_the_outcome_and_the_cut(tmp_path: Path, kind: str) -> None:
    config = _config(tmp_path, case_field="metadata:ls_example_case", outcome_field="feedback:exact", cut=0.5)
    data = imported(_bare(export("baseline", kind), tmp_path / "config", "r", config))
    flags = imported(ls_argv(export("baseline", kind), tmp_path / "flags", "r"))
    assert recs(tmp_path / "config", "r") == recs(tmp_path / "flags", "r")
    assert data["declared"] == flags["declared"]
    assert data["declared"]["case_from"] == "metadata:ls_example_case" and data["declared"]["outcome_from"] == "feedback:exact"
    assert data["declared"]["cut"] == 0.5 and data["declared"]["side"] == "below"
    for key in ("rows", "cases", "outcomes", "no_outcome", "counts"):
        assert data[key] == flags[key], key


@pytest.mark.parametrize(("case_field", "outcome_field"), [("example", "status"), ("input", "status"),
                                                           ("metadata:ls_example_case", "metadata:version")])
def test_tf24_73_each_value_is_written_as_the_flag_writes_it(tmp_path: Path, case_field: str, outcome_field: str) -> None:
    config = _config(tmp_path, case_field=case_field, outcome_field=outcome_field)
    extra = ["--failed", "baseline"] if outcome_field.startswith("metadata:") else []
    data = imported(_bare(export("baseline", "v1"), tmp_path / "config", "r", config, *extra))
    flags = imported(ls_argv(export("baseline", "v1"), tmp_path / "flags", "r", *extra, case=case_field, outcome=outcome_field, cut=None))
    assert recs(tmp_path / "config", "r") == recs(tmp_path / "flags", "r")
    assert data["declared"] == flags["declared"] and data["outcomes"] == flags["outcomes"]


def test_tf24_73_a_value_the_flag_would_not_take_is_refused_as_the_flag_s(tmp_path: Path) -> None:
    config = _config(tmp_path, case_field="row", outcome_field="status")
    line = wrong_line(run_import(_bare(export("baseline", "v1"), tmp_path / "st", "r", config)))
    assert "--case-from" in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF24-74 ----------


# the spelling is settled before a file is opened: one spelling on every format, every spelling on one
@pytest.mark.parametrize(("kind", "score_field"), [*[(kind, "exact") for kind in KINDS], (KINDS[0], "feedback:exact")])
def test_tf24_74_score_field_names_the_feedback_key(tmp_path: Path, kind: str, score_field: str) -> None:
    config = _config(tmp_path, case_field="metadata:ls_example_case", score_field=score_field, cut=0.5)
    data = imported(_bare(export("candidate", kind), tmp_path / "st", "r", config))
    assert data["declared"]["outcome_from"] == "feedback:exact"
    assert tally(data) == {"met": 8, "missed": 2}
    assert {case: r["score"] for case, r in recs(tmp_path / "st", "r").items()} == EXACT["candidate"]


def test_tf24_74_an_outcome_field_beside_it_wins(tmp_path: Path) -> None:
    config = _config(tmp_path, case_field="metadata:ls_example_case", outcome_field="feedback:thumbs", score_field="judge_correct", cut=0.5)
    data = imported(_bare(export("candidate", "v1"), tmp_path / "st", "r", config))
    assert data["declared"]["outcome_from"] == "feedback:thumbs" and data["no_outcome"] == {}
    # judge_correct is missing on the errored root, so it would have left a row with no outcome
    other = _config(tmp_path, case_field="metadata:ls_example_case", score_field="judge_correct", cut=0.5)
    assert imported(_bare(export("candidate", "v1"), tmp_path / "st2", "r", other))["no_outcome"] == {"no score": 1}


# ---------- TF24-75 ----------


def test_tf24_75_a_cut_from_the_config_reads_below_and_a_side_given_is_kept(tmp_path: Path) -> None:
    config = _config(tmp_path, case_field="metadata:ls_example_case", outcome_field="feedback:exact", cut=1)
    below = imported(_bare(export("baseline", "v1"), tmp_path / "below", "r", config))
    assert (below["declared"]["cut"], below["declared"]["side"]) == (1.0, "below") and tally(below) == {"met": 6, "missed": 4}
    above = imported(_bare(export("baseline", "v1"), tmp_path / "above", "r", config, "--above"))
    assert (above["declared"]["cut"], above["declared"]["side"]) == (1.0, "above") and tally(above) == {"met": 10}


@pytest.mark.parametrize("kind", KINDS)
def test_tf24_75_the_cut_is_not_filled_where_no_score_is_read(tmp_path: Path, kind: str) -> None:
    """A config whose cut serves another import of the project: by the status, and by a
    metadata value named as failed, there is no score, and the cut is left out, not refused."""
    config = _config(tmp_path, case_field="metadata:ls_example_case", outcome_field="status", cut=0.5)
    data = imported(_bare(export("baseline", kind), tmp_path / "status", "r", config))
    assert "cut" not in data["declared"] and "side" not in data["declared"]
    bad = ERRORED["baseline"][0]
    assert _outcomes(tmp_path / "status") == {case: "missed" if case == bad else "met" for case in CASES}
    config = _config(tmp_path, case_field="metadata:ls_example_case", outcome_field="metadata:version", cut=0.5)
    data = imported(_bare(export("baseline", kind), tmp_path / "failed", "r", config, "--failed", "baseline"))
    assert "cut" not in data["declared"] and tally(data) == {"missed": 10}
    # the same holds when the line names the status over a config that reads a score
    config = _config(tmp_path, case_field="metadata:ls_example_case", outcome_field="feedback:exact", cut=0.5)
    data = imported(_bare(export("baseline", kind), tmp_path / "line", "r", config, "--outcome-from", "status"))
    assert "cut" not in data["declared"] and tally(data) == {"met": 9, "missed": 1}


def test_tf24_75_a_metadata_number_takes_the_config_s_cut(tmp_path: Path) -> None:
    from langsmith_support import write_rows

    def grade(rows: list[dict[str, Any]]) -> None:
        for case, root in roots(rows).items():
            root["extra"]["metadata"]["grade"] = EXACT["baseline"][case]  # type: ignore[index]

    path = write_rows(tmp_path / "runs.json", export("baseline", "v1")[0], grade)
    config = _config(tmp_path, case_field="metadata:ls_example_case", outcome_field="metadata:grade", cut=0.5)
    data = imported(_bare(path, tmp_path / "st", "r", config))
    assert data["declared"]["cut"] == 0.5 and tally(data) == {"met": 6, "missed": 4}


# ---------- TF24-76 ----------


def test_tf24_76_a_flag_given_wins_over_the_config(tmp_path: Path) -> None:
    config = _config(tmp_path, case_field="metadata:ls_example_case", outcome_field="feedback:exact", cut=0.5)
    files = export("baseline", "v1")
    case = imported(_bare(files, tmp_path / "case", "r", config, "--case-from", "input"))
    assert case["declared"]["case_from"] == "input" and all(c.startswith("input:") for c in recs(tmp_path / "case", "r"))
    outcome = imported(_bare(files, tmp_path / "outcome", "r", config, "--outcome-from", "feedback:thumbs"))
    assert outcome["declared"]["outcome_from"] == "feedback:thumbs" and outcome["declared"]["cut"] == 0.5
    cut = imported(_bare(files, tmp_path / "cut", "r", config, "--cut", "0", "--below"))
    assert cut["declared"]["cut"] == 0.0 and tally(cut) == {"met": 10}
    every = imported(ls_argv(files, tmp_path / "every", "r", "--config", config, case="example", outcome="status", cut=None))
    assert every["declared"]["case_from"] == "example" and every["declared"]["outcome_from"] == "status"
    assert "cut" not in every["declared"]


# ---------- TF24-77 ----------


def test_tf24_77_nothing_stands_in_without_signals(tmp_path: Path) -> None:
    files = export("baseline", "v1")
    line = wrong_line(run_import(ls_argv(files, tmp_path / "st", "r", case=None, outcome=None)))
    assert "--case-from" in line and "--outcome-from" in line, line
    empty = tmp_path / "trace.toml"
    empty.write_text("version = 1\n", encoding="utf-8")
    line = wrong_line(run_import(_bare(files, tmp_path / "st", "r", empty)))
    assert "--case-from" in line and "--outcome-from" in line, line
    half = _config(tmp_path, case_field="example")
    line = wrong_line(run_import(_bare(files, tmp_path / "st", "r", half)))
    assert "--outcome-from" in line and "--case-from" not in line, line
    scored = _config(tmp_path, case_field="example", outcome_field="feedback:exact")
    line = wrong_line(run_import(_bare(files, tmp_path / "st", "r", scored)))
    assert "--cut" in line, line
    assert not (tmp_path / "st").exists()


def test_tf24_77_the_help_is_the_same_with_a_config_as_without(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with chdir(plain):
        without = trace(["import", "langsmith", "--help"])
    held = tmp_path / "held"
    held.mkdir()
    _config(held, case_field="example", outcome_field="feedback:exact", score_field="exact", cut=0.5, cost_field="prompt_cost")
    with chdir(held):
        with_config = trace(["import", "langsmith", "--help"])
        named = trace(["import", "langsmith", "--help", "--config", "trace.toml"])
    assert without.code == with_config.code == named.code == 0
    assert without.out == with_config.out == named.out and without.err == with_config.err == named.err == ""


# ---------- TF24-78 ----------


def test_tf24_78_an_import_entry_takes_what_signals_gives_and_what_it_says_wins(tmp_path: Path) -> None:
    import shutil

    from poisson_trace import config as config_module

    folder = work(tmp_path)
    (folder / "exports").mkdir()
    for version, run in (("baseline", "old"), ("candidate", "new")):
        shutil.copy(export(version, "v1")[0], folder / "exports" / f"{run}.json")
    signals = '[signals]\ncase_field = "metadata:ls_example_case"\noutcome_field = "feedback:exact"\ncut = 0.5\n'
    text = config_text(import_entry("exports/old.json", "langsmith", "old"),
                       import_entry("exports/new.json", "langsmith", "new", outcome_from="status"), signals, store=None, events=("missed",))
    held = config_module.parse(text, folder / "trace.toml", "trace.toml", given=False)
    assert [dict(e.options) for e in held.imports] == [{}, {"outcome_from": "status"}]
    write_toml(folder, text)
    checked = setup_check(folder, "--json")
    assert checked.code == 0, checked.text
    lines = [c["line"] for c in checked.json()["checks"] if c["name"] == "import"]
    assert len(lines) == 2 and all("langsmith, 10 rows" in line for line in lines), lines
    from setup_support import init_yes

    done = init_yes(folder, "--import")
    assert done.code == 0, done.text
    store = folder / "trace-store"
    assert {c: r["outcome"] for c, r in columns(store, "old").items()} == {c: "met" if EXACT["baseline"][c] >= 0.5 else "missed" for c in CASES}
    # the second entry says the status, so the config's score and its cut are not read for it
    assert {c: r["outcome"] for c, r in columns(store, "new").items()} == {c: "missed" if c == ERRORED["candidate"][0] else "met" for c in CASES}
    assert all(r["score"] is None for r in recs(store, "new").values())


def test_tf24_78_an_entry_that_signals_does_not_complete_is_refused(tmp_path: Path) -> None:
    from poisson_trace import config as config_module

    folder = work(tmp_path)
    text = config_text(import_entry("exports/old.json", "langsmith", "old"), '[signals]\ncase_field = "example"\n', store="s")
    with pytest.raises(config_module.ConfigError) as caught:
        config_module.parse(text, folder / "trace.toml", "trace.toml", given=False)
    assert "outcome_from" in str(caught.value) and "line " in str(caught.value), str(caught.value)


def test_tf24_78_the_python_api_takes_them_too(tmp_path: Path) -> None:
    from poisson_trace import api

    config = _config(tmp_path, case_field="metadata:ls_example_case", outcome_field="feedback:exact", cut=0.5)
    result = api.import_run(str(tmp_path / "st"), "langsmith", [str(export("baseline", "v1")[0])], config=str(config), run="r")
    assert result.exit_code == 0
    assert _outcomes(tmp_path / "st") == {c: "met" if EXACT["baseline"][c] >= 0.5 else "missed" for c in CASES}
    by = api.import_run(str(tmp_path / "st"), "langsmith", [str(export("baseline", "v1")[0])], config=str(config), run="by", outcome_from="status")
    assert by.exit_code == 0 and sum(1 for o in _outcomes(tmp_path / "st", "by").values() if o == "missed") == 1


# ---------- TF24-79 ----------


def _prompt_cost(kind: str) -> dict[str, float | None]:
    """Each case's prompt cost, read off its ``llm`` run in the export."""
    rows = [r for path in export("baseline", kind) for r in rows_of(path)]
    out: dict[str, float | None] = {}
    for case in roots(rows):
        llm = [r for r in trace_rows(rows, case) if r["run_type"] == "llm"]
        if not llm:
            out[case] = None
        elif "costs" in llm[0]:
            out[case] = llm[0]["costs"]["prompt_cost"]
        else:
            out[case] = llm[0]["prompt_cost"]
    return out


@pytest.mark.parametrize("kind", ["v1", "v2", "cli-runs"])
def test_tf24_79_cost_field_names_the_field_the_cost_is_read_from(tmp_path: Path, kind: str) -> None:
    config = _config(tmp_path, cost_field="prompt_cost")
    imported([*by_status(export("baseline", kind), tmp_path / "st", "r"), "--config", config])
    stored, held, want = recs(tmp_path / "st", "r"), metas(tmp_path / "st", "r"), _prompt_cost(kind)
    assert approx(want["c09"], 2.84e-05, 1e-12)
    for case in CASES:
        if want[case] is None:
            assert stored[case]["cost_usd"] is None and "cost_usd" not in held[case], case
        else:
            assert approx(stored[case]["cost_usd"], want[case], 1e-12) and approx(held[case]["cost_usd"], want[case], 1e-12), case
            assert held[case]["import"]["cost_from"] == "llm runs"
    # the default is the total, and naming it changes nothing
    total = _config(tmp_path, cost_field="total_cost")
    imported([*by_status(export("baseline", kind), tmp_path / "total", "r"), "--config", total])
    imported(by_status(export("baseline", kind), tmp_path / "plain", "r"))
    assert recs(tmp_path / "total", "r") == recs(tmp_path / "plain", "r")
    assert approx(recs(tmp_path / "plain", "r")["c09"]["cost_usd"], 3e-05, 1e-12)


@pytest.mark.parametrize("kind", ["v1", "cli-runs", "ui"])
def test_tf24_79_a_field_no_run_holds_records_no_cost(tmp_path: Path, kind: str) -> None:
    config = _config(tmp_path, cost_field="no_such_cost")
    data = imported([*by_status(export("baseline", kind), tmp_path / "st", "r"), "--config", config])
    assert data["rows"] == 10
    for case, rec in recs(tmp_path / "st", "r").items():
        assert rec["cost_usd"] is None, case
        assert "cost_usd" not in metas(tmp_path / "st", "r")[case] and "cost_from" not in metas(tmp_path / "st", "r")[case]["import"]


def test_tf24_79_the_csv_s_cost_column_is_named_the_same_way(tmp_path: Path) -> None:
    from langsmith_support import write_csv

    def rename(rows: list[dict[str, str]]) -> None:
        for row in rows:
            row["spend"] = row["total_cost"]

    path = write_csv(tmp_path / "page.csv", export("baseline", "ui")[0], rename, header=lambda fields: [f if f != "total_cost" else "spend" for f in fields])
    config = _config(tmp_path, cost_field="spend")
    imported([*by_status(path, tmp_path / "st", "r"), "--config", config])
    imported(by_status(export("baseline", "ui"), tmp_path / "plain", "r"))
    got, want = recs(tmp_path / "st", "r"), recs(tmp_path / "plain", "r")
    for case in CASES:
        assert got[case]["cost_usd"] == want[case]["cost_usd"], case
        # the column named as the cost is not also read as a feedback score
        assert "spend" not in got[case]["scores"] and "spend" not in got[case]["feedback"], case
