"""PL-10 to PL-14: a team names its labels' kinds in ``trace.toml``, and ``doctor`` checks it
(``pl_support``'s opening, readings 3 and 5).

- PL-10: ``[taxonomy.labels]`` is read into ``Config.labels``, sorted by label; none, or an
  empty table, is an empty mapping; it may be written inline, and beside ``[[taxonomy.rules]]``.
- PL-11: a fault in it is refused in one sentence naming the file and the line, before anything
  else is read, by every verb and by ``doctor``: a kind that is not one of the 13 (with the one
  nearest, when one is two edits away or less, else the 13 listed), a value that is not text, an
  empty label, a ``labels`` that is not a table. An unknown key of ``[taxonomy]`` now lists both
  of its settings.
- PL-12: ``doctor``'s config line, when the table names a kind, ends with the kinds it names, in
  the plain report and ``--json`` alike; with no table, or an empty one, it is as main prints
  it. ``doctor --setup`` prints the same with a table as without.
- PL-13: under a table, a run Prove swept is classified by ``taxonomy_sha256((), None, labels)``
  and the section says ``by your own rules and the built-in ones``; an import's digest does not
  hold the table, so an imported run beside a swept one reads as classified by different rules.
- PL-14: ``init --force`` writes the config as main writes it (it keeps no table).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pl_support import KINDS, Try, config, run, section, two_runs

from poisson_trace import config as config_module
from poisson_trace.ingest.taxonomy import taxonomy_sha256

ALL_KINDS = ", ".join(KINDS[:-1]) + " and " + KINDS[-1]
BUILT_IN = "by the built-in rules"
OWN_RULES = "by your own rules and the built-in ones"


def _load(tmp: Path, text: str) -> Any:
    path = tmp / "trace.toml"
    path.write_text(text, encoding="utf-8")
    return config_module.load(str(path))


def _refused(tmp: Path, text: str) -> str:
    path = tmp / "trace.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(config_module.ConfigError) as caught:
        config_module.load(str(path))
    return str(caught.value).replace(str(path), "PATH")


HEAD = 'version = 1\n\n[store]\npath = "store"\n\n[events]\nfailed = ["wrong_state"]\n'


# ---------- PL-10: the table ----------


def test_pl_10_the_table_is_read_sorted(tmp_path: Path) -> None:
    held = _load(tmp_path, HEAD + '\n[taxonomy.labels]\nwrong_state = "tool_error"\nforbidden_action = "guardrail_blocked"\n'
                 '"not solved" = "wrong_answer"\n')
    assert dict(held.labels) == {"forbidden_action": "guardrail_blocked", "not solved": "wrong_answer", "wrong_state": "tool_error"}
    assert list(held.labels) == ["forbidden_action", "not solved", "wrong_state"]


def test_pl_10_no_table_and_an_empty_table_are_empty(tmp_path: Path) -> None:
    assert dict(_load(tmp_path, HEAD).labels) == {}
    assert dict(_load(tmp_path, HEAD + "\n[taxonomy.labels]\n").labels) == {}
    assert dict(config_module.Config(path=tmp_path / "x", shown="x", given=False, text="").labels) == {}


def test_pl_10_inline_and_beside_rules(tmp_path: Path) -> None:
    held = _load(tmp_path, HEAD + '\n[taxonomy]\nlabels = { wrong_state = "crash" }\n\n[[taxonomy.rules]]\nfailure_kind = "crash"\n'
                 'when_span_kind = "tool"\n')
    assert dict(held.labels) == {"wrong_state": "crash"}
    assert len(held.rules) == 1


def test_pl_10_every_kind_may_be_named(tmp_path: Path) -> None:
    lines = "".join(f'label_{i} = "{k}"\n' for i, k in enumerate(KINDS))
    held = _load(tmp_path, HEAD + "\n[taxonomy.labels]\n" + lines)
    assert sorted(held.labels.values()) == sorted(KINDS)


def test_pl_10_the_imports_digest_does_not_hold_the_table(tmp_path: Path) -> None:
    held = _load(tmp_path, HEAD + '\n[taxonomy.labels]\nwrong_state = "crash"\n')
    assert held.taxonomy_sha256 == taxonomy_sha256((), None)


# ---------- PL-11: its faults ----------

FAULTS: dict[str, tuple[str, str]] = {
    "a kind one edit away": ('[taxonomy.labels]\nwrong_state = "wrong_anwser"\n',
                             'PATH line 10: [taxonomy.labels] wrong_state is given "wrong_anwser", which is not a kind; '
                             'did you mean "wrong_answer"?'),
    "a kind two edits away": ('[taxonomy.labels]\nmalformed_call = "fromat_error"\n',
                              'PATH line 10: [taxonomy.labels] malformed_call is given "fromat_error", which is not a kind; '
                              'did you mean "format_error"?'),
    "no kind near": ('[taxonomy.labels]\nwrong_state = "wrong"\n',
                     f'PATH line 10: [taxonomy.labels] wrong_state is given "wrong", which is not a kind; the kinds are {ALL_KINDS}'),
    "a capital": ('[taxonomy.labels]\nwrong_state = "Crash"\n',
                  'PATH line 10: [taxonomy.labels] wrong_state is given "Crash", which is not a kind; did you mean "crash"?'),
    "a number": ('[taxonomy.labels]\nwrong_state = 3\n',
                 f"PATH line 10: [taxonomy.labels] wrong_state is given 3, which is not a kind; the kinds are {ALL_KINDS}"),
    "true": ('[taxonomy.labels]\nwrong_state = true\n',
             f"PATH line 10: [taxonomy.labels] wrong_state is given true, which is not a kind; the kinds are {ALL_KINDS}"),
    "a list": ('[taxonomy.labels]\nwrong_state = ["crash"]\n',
               f"PATH line 10: [taxonomy.labels] wrong_state is given a list, which is not a kind; the kinds are {ALL_KINDS}"),
    "a table": ('[taxonomy.labels.wrong_state]\nkind = "crash"\n',
                f"PATH line 9: [taxonomy.labels] wrong_state is given a table, which is not a kind; the kinds are {ALL_KINDS}"),
    "a quoted label": ('[taxonomy.labels]\nwrong_state = "crash"\n"not solved" = "nope"\n',
                       f'PATH line 11: [taxonomy.labels] "not solved" is given "nope", which is not a kind; the kinds are {ALL_KINDS}'),
    "an empty label": ('[taxonomy.labels]\n"" = "crash"\n',
                       'PATH line 10: [taxonomy.labels] "" is no label: a label is an outcome as Prove stores it'),
    "labels as text": ('[taxonomy]\nlabels = "wrong_state"\n',
                       '[taxonomy] labels is a table, written [taxonomy.labels] on a line of its own, not "wrong_state"'),
    "labels as a list": ('[taxonomy]\nlabels = ["wrong_state"]\n',
                         "[taxonomy] labels is a table, written [taxonomy.labels] on a line of its own, not a list"),
    "a near setting": ('[taxonomy]\nlabel = { wrong_state = "crash" }\n',
                       'PATH line 10: [taxonomy] "label" is not a setting; did you mean "labels"?'),
    "an unknown setting": ('[taxonomy]\nkinds = { wrong_state = "crash" }\n',
                           'PATH line 10: [taxonomy] "kinds" is not a setting; [taxonomy] has rules and labels'),
}


@pytest.mark.parametrize("case", sorted(FAULTS))
def test_pl_11_each_fault_is_refused_naming_its_line(tmp_path: Path, case: str) -> None:
    text, said = FAULTS[case]
    got = _refused(tmp_path, HEAD + "\n" + text)
    if said.startswith("PATH line"):
        assert got == said
    else:
        assert got == "PATH line 10: " + said


def test_pl_11_a_verb_and_doctor_refuse_it(tmp_path: Path) -> None:
    root = two_runs(tmp_path, [Try("t", "wrong_state")], [Try("t", "passed")])
    path = config(tmp_path, root.name, ["wrong_state"], labels='wrong_state = "wrong_anwser"\n')
    said = f'{path} line 10: [taxonomy.labels] wrong_state is given "wrong_anwser", which is not a kind; did you mean "wrong_answer"?'
    rules = config(tmp_path / "r" if (tmp_path / "r").mkdir() is None else tmp_path, root.name, ["wrong_state"],
                   extra='\n[[taxonomy.rules]]\nfailure_kind = "wrong_anwser"\nwhen_span_kind = "tool"\n')
    ran_rules = run(["changes", "old", "new", "--config", rules])
    ran = run(["changes", "old", "new", "--config", path])
    assert ran_rules.code == ran.code != 0
    assert said in ran.err and ran.out == ""
    doc = run(["doctor", "--config", path, "--json"]).json()
    check = next(c for c in doc["checks"] if c["name"] == "config")
    assert check["ok"] is False and check["line"] == said


# ---------- PL-12: doctor ----------


def _doctor_line(argv: list[Any]) -> tuple[str, str]:
    plain = run(["doctor", *argv])
    doc = run(["doctor", *argv, "--json"]).json()
    check = next(c for c in doc["checks"] if c["name"] == "config")
    assert check["ok"] is True, check
    line = next(x for x in plain.out.splitlines() if x.lstrip().startswith("config "))
    return line, check["line"]


def test_pl_12_doctor_names_the_kinds_the_table_gives(tmp_path: Path) -> None:
    root = two_runs(tmp_path, [Try("t", "wrong_state"), Try("u", "malformed_call")], [Try("t", "passed"), Try("u", "passed")])
    path = config(tmp_path, root.name, ["wrong_state", "malformed_call"])
    plain_line, json_line = _doctor_line(["--config", path])
    config(tmp_path, root.name, ["wrong_state", "malformed_call"],
           labels='wrong_state = "tool_error"\nforbidden_action = "guardrail_blocked"\n')
    named_plain, named_json = _doctor_line(["--config", path])
    added = f"; kinds named in {path}: forbidden_action is guardrail_blocked, wrong_state is tool_error"
    assert named_json == json_line + added
    assert named_plain == plain_line + added


def test_pl_12_an_empty_table_changes_nothing_doctor_prints(tmp_path: Path) -> None:
    root = two_runs(tmp_path, [Try("t", "wrong_state")], [Try("t", "passed")])
    path = config(tmp_path, root.name, ["wrong_state"])
    before = (run(["doctor", "--config", path]).out, run(["doctor", "--config", path, "--json"]).out)
    config(tmp_path, root.name, ["wrong_state"], labels="")
    after = (run(["doctor", "--config", path]).out, run(["doctor", "--config", path, "--json"]).out)
    assert after == before


def test_pl_12_doctor_names_the_file_as_typed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = two_runs(tmp_path, [Try("t", "wrong_state")], [Try("t", "passed")])
    (tmp_path / "conf").mkdir()
    text = f'version = 1\n\n[store]\npath = "../{root.name}"\n\n[events]\nfailed = ["wrong_state"]\n\n[taxonomy.labels]\nwrong_state = "crash"\n'
    (tmp_path / "conf" / "team.toml").write_text(text, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    _, line = _doctor_line(["--config", "conf/team.toml"])
    assert line.endswith("; kinds named in conf/team.toml: wrong_state is crash")


def test_pl_12_doctor_setup_prints_the_same_with_a_table(tmp_path: Path) -> None:
    root = two_runs(tmp_path, [Try("t", "wrong_state")], [Try("t", "passed")])
    path = config(tmp_path, root.name, ["wrong_state"])
    before = [run(["doctor", "--setup", "--config", path, *j]) for j in ([], ["--json"])]
    config(tmp_path, root.name, ["wrong_state"], labels='wrong_state = "crash"\n')
    after = [run(["doctor", "--setup", "--config", path, *j]) for j in ([], ["--json"])]
    assert [(r.code, r.out, r.err) for r in after] == [(r.code, r.out, r.err) for r in before]


# ---------- PL-13: the digest the verbs give ----------


def test_pl_13_under_a_table_both_swept_runs_are_classified_by_it(tmp_path: Path) -> None:
    root = two_runs(tmp_path, [Try("t", "wrong_state"), Try("u", "forbidden_action")], [Try("t", "passed"), Try("u", "passed")])
    path = config(tmp_path, root.name, ["wrong_state", "forbidden_action"])
    argv = ["fix-check", "old", "new", "--inputs", "all", "--max-mde", "0.9", "--config", path]
    plain = run([*argv, "--json"]).json()["failure_taxonomy_diff"]
    assert plain["taxonomy_sha256"] == {"old": taxonomy_sha256((), None), "new": taxonomy_sha256((), None)}
    assert BUILT_IN in section(run(argv).out)[2]
    table = {"forbidden_action": "guardrail_blocked"}
    config(tmp_path, root.name, ["wrong_state", "forbidden_action"], labels='forbidden_action = "guardrail_blocked"\n')
    named = run([*argv, "--json"]).json()["failure_taxonomy_diff"]
    digest = taxonomy_sha256((), None, table)
    assert named["taxonomy_sha256"] == {"old": digest, "new": digest} and named["same_rules"] is True
    assert named["kinds"] == [{"failure_kind": "guardrail_blocked", "old": 1, "new": 0},
                              {"failure_kind": "wrong_answer", "old": 1, "new": 0}]
    assert section(run(argv).out)[2].startswith(f"Each failed try's kind of failure, {OWN_RULES}; the same rules classified both runs.")


def test_pl_13_an_import_beside_a_swept_run_under_a_table(tmp_path: Path) -> None:
    root = two_runs(tmp_path, [Try("c1", "wrong_state"), Try("c2", "passed")], [Try("c1", "passed"), Try("c2", "passed")], axis="case")
    table = tmp_path / "results.csv"
    table.write_text("case,outcome\nc1,wrong_state\nc2,passed\n", encoding="utf-8")
    ran = run(["import", "table", table, "--store", root, "--run", "imp", "--case-column", "case", "--outcome-column", "outcome",
               "--failed", "wrong_state", "--started", "2026-11-16T09:30:00Z"])
    assert ran.code == 0, ran.text
    path = config(tmp_path, root.name, ["wrong_state"])
    argv = ["changes", "old", "imp", "--config", path, "--json"]
    assert run(argv).json()["failure_taxonomy_diff"]["same_rules"] is True
    config(tmp_path, root.name, ["wrong_state"], labels='wrong_state = "crash"\n')
    diff = run(argv).json()["failure_taxonomy_diff"]
    assert diff["same_rules"] is False and diff["kinds"] is None
    assert diff["taxonomy_sha256"] == {"a": taxonomy_sha256((), None, {"wrong_state": "crash"}), "b": taxonomy_sha256((), None)}
    assert "labels_without_kind" not in diff


# ---------- PL-14: init ----------


def test_pl_14_init_force_writes_no_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = two_runs(tmp_path, [Try("t", "wrong_state")], [Try("t", "passed")])
    monkeypatch.chdir(tmp_path)
    config(tmp_path, root.name, ["wrong_state"], labels='wrong_state = "crash"\n')
    ran = run(["init", "--force", "--yes", "--store", root.name, "--event", "wrong_state"])
    assert ran.code == 0, ran.text
    text = (tmp_path / "trace.toml").read_text(encoding="utf-8")
    assert "[taxonomy" not in text and "labels" not in text
    assert json.dumps("wrong_state") in text
