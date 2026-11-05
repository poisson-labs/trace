"""TF17-13 to TF17-21 and TF17-23: ``[[import]]`` in ``trace.toml`` (spec section 17.4, AD14, and
section 3.2's strict rules; folders through TF22's resolver; addresses as section 18.3.2 places
them).

- TF17-13: the spec's example entry reads; ``config.load`` gives the entries in the file's
  order as ``Config.imports``, each with its ``file`` as written, its ``tool``, its ``name`` and
  its reader's ``options`` by the keys as written; a config with no ``[[import]]`` has none.
  ``file``, ``tool`` and ``name`` are each required and each a non-empty string.
- TF17-14: an unknown key is refused naming the line and the nearest known key or the reader's
  options; ``[import]`` written as one table is refused saying it is written ``[[import]]``;
  ``[[imprt]]`` says "did you mean [[import]]?".
- TF17-15: a ``tool`` not in the install is refused by every verb that reads the config, naming
  the tool and the readers the install has; a reader section 6.1 names but whose module is not
  present (``langsmith``) is "not in this install".
- TF17-16: the reader's options are checked as its flags are: a key is one of the reader's own
  flags without ``--`` (``case_column`` for ``--case-column``), never the import's own (``run``,
  ``store``, ``started``, ``verdicts``); a flag that takes no value is ``true`` or ``false``;
  ``below`` and ``above`` are not both true; a flag with choices takes one of them (DeepEval's
  ``case``, JUnit's ``case``); ``cut`` is a number, or ``"recorded"`` for DeepEval; ``failed``
  is a list of strings; a flag the reader requires is present.
- TF17-17: ``name`` is a name the import accepts (section 5.2; ``names.import_name_refusal``)
  and is used once: two entries of one name are refused naming both lines.
- TF17-18: ``file`` is a relative path inside the repository: an absolute path, or one that
  leaves the config's folder (``..``), is refused; it is kept as written, read from the config's
  folder; two entries may name one file (one promptfoo file holds both versions).
- TF17-19: ``file`` may name a folder: the entry is read through the folder resolver with its
  ``tool``, so a folder of that tool's files is one run and a folder of another tool's, of two
  tools', or a Prove store is refused by ``doctor --setup`` naming what it holds (the config
  itself reads: nothing opens the folder but ``doctor`` and ``init``).
- TF17-20: a ``file`` that is an address to pull from (``langsmith:…``, ``braintrust:…``,
  ``weave:…``, ``lemma:…``, section 18.3.2) is refused plainly by every verb, naming the puller
  this install does not have and saying to save the export as a file first.
- TF17-21: every verb reads the config and checks ``[[import]]``'s keys and types, and no verb
  but ``doctor`` and ``init`` opens the files: ``runs`` with an entry whose file is missing
  still lists the store's runs, and with an entry whose tool is unknown is refused.
- TF17-23: the one sentence of section 3.2 that changes: an unknown table is refused with
  "a config has version, the tables [store], [events], [check], [names], [upload], [signals] and
  [taxonomy], and [[import]] tables" (TF21-63 moves to it in this commit, its guard line with
  it).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from poisson_trace import config
from tf1_support import tau2_copy
from tf2_support import scratch_home, work  # noqa: F401
from tf17_support import (
    PULLERS, READERS_HERE, config_text, import_entry, junit_entry, ragas_entry, ragas_pair,
    trace_in, write_toml,
)

EXAMPLE = """\
[[import]]                              # a file another tool wrote, for `init` to import after asking
file = "evals/results/ragas-base.csv"   # relative to trace.toml, inside the repository
tool = "ragas"                          # a reader in the install
name = "rag base"                       # the run's name
metric = "faithfulness"                 # the reader's own options, by their flag names
cut = 0.5
below = true
case_column = "question_id"
"""


def parse(text: str, folder: Path) -> config.Config:
    return config.parse(text, folder / "trace.toml", "trace.toml", given=False)


def fault(text: str, folder: Path) -> str:
    with pytest.raises(config.ConfigError) as caught:
        parse(text, folder)
    return str(caught.value)


def line_of(text: str, needle: str) -> int:
    for n, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return n
    raise AssertionError(needle)


# ---------- TF17-13 ----------


def test_tf17_13_the_specs_example_reads_and_the_entries_are_given_in_order(tmp_path: Path) -> None:
    folder = work(tmp_path)
    text = config_text(EXAMPLE, junit_entry("reports/new.xml", "tests new"), store="proofload-runs")
    held = parse(text, folder)
    imports = list(held.imports)
    assert [i.file for i in imports] == ["evals/results/ragas-base.csv", "reports/new.xml"]
    assert [i.tool for i in imports] == ["ragas", "junit"]
    assert [i.name for i in imports] == ["rag base", "tests new"]
    assert dict(imports[0].options) == {"metric": "faithfulness", "cut": 0.5, "below": True, "case_column": "question_id"}
    assert dict(imports[1].options) == {"case": "name"}
    assert list(parse(config_text(store="proofload-runs"), folder).imports) == []
    # the rest of the config reads as before
    assert str(held.store).endswith("proofload-runs") and held.events == ("forbidden_action", "unresolved", "max_turns", "app_error")


@pytest.mark.parametrize("missing", ["file", "tool", "name"])
def test_tf17_13_file_tool_and_name_are_each_required_and_non_empty(tmp_path: Path, missing: str) -> None:
    folder = work(tmp_path)
    keys = {"file": '"evals/rag-base.jsonl"', "tool": '"ragas"', "name": '"rag-base"'}
    options = 'metric = "faithfulness"\ncut = 0.5\nbelow = true\ncase_column = "case"\n'

    def entry(**given: str) -> str:
        head = "".join(f"{k} = {v}\n" for k, v in given.items())
        return "[[import]]\n" + head + options

    without = entry(**{k: v for k, v in keys.items() if k != missing})
    text = config_text(without, store="s")
    said = fault(text, folder)
    assert "[[import]]" in said and missing in said and f"line {line_of(text, '[[import]]')}" in said, said
    for wrong in ('""', "1", "true", "[]"):
        text = config_text(entry(**{**keys, missing: wrong}), store="s")
        said = fault(text, folder)
        assert "[[import]]" in said and missing in said and f"line {line_of(text, f'{missing} = ')}" in said, said


# ---------- TF17-14 ----------


def test_tf17_14_an_unknown_key_is_refused_naming_the_line_and_the_nearest(tmp_path: Path) -> None:
    folder = work(tmp_path)
    text = config_text(ragas_entry("evals/rag-base.jsonl", "rag-base", metrc="x"), store="s")
    said = fault(text, folder)
    assert f"line {line_of(text, 'metrc')}" in said and "metrc" in said and 'did you mean "metric"' in said, said
    text = config_text(ragas_entry("evals/rag-base.jsonl", "rag-base", colour="x"), store="s")
    said = fault(text, folder)
    assert "colour" in said and "ragas" in said and all(o in said for o in ("metric", "cut", "below", "above", "case_column")), said


def test_tf17_14_import_as_one_table_and_a_near_miss_are_refused(tmp_path: Path) -> None:
    folder = work(tmp_path)
    one = 'version = 1\n\n[import]\nfile = "a.csv"\ntool = "table"\nname = "a"\n'
    said = fault(one, folder)
    assert "line 3" in said and "[[import]]" in said, said
    near = 'version = 1\n\n[[imprt]]\nfile = "a.csv"\ntool = "table"\nname = "a"\n'
    said = fault(near, folder)
    assert "line 3" in said and "did you mean [[import]]?" in said, said


# ---------- TF17-15 ----------


@pytest.mark.parametrize("tool", ["langsmith", "otel", "lemma", "braintrust", "weave", "nothing"])
def test_tf17_15_a_tool_not_in_the_install_is_refused_naming_the_readers_here(tmp_path: Path, tool: str) -> None:
    folder = work(tmp_path)
    text = config_text(import_entry("a.jsonl", tool, "a"), store="s")
    said = fault(text, folder)
    assert f"line {line_of(text, 'tool = ')}" in said and tool in said, said
    assert all(reader in said for reader in READERS_HERE), said
    assert "not in this install" in said, said


# ---------- TF17-16 ----------

WRONG_OPTIONS = [
    ("the import's own key", ragas_entry("e/r.jsonl", "r", run="x"), ("run",)),
    ("the import's store", ragas_entry("e/r.jsonl", "r", store="x"), ("store",)),
    ("the import's started", ragas_entry("e/r.jsonl", "r", started="2026-01-01T00:00:00Z"), ("started",)),
    ("the import's verdicts", ragas_entry("e/r.jsonl", "r", verdicts="v.csv"), ("verdicts",)),
    ("a bare flag with a value", ragas_entry("e/r.jsonl", "r", below="yes"), ("below", "true", "false")),
    ("both sides", ragas_entry("e/r.jsonl", "r", above=True), ("below", "above")),
    ("a choice not offered", import_entry("d.json", "deepeval", "d", metric="m", cut="recorded", case="row"), ("case", "name", "input", "position")),
    ("junit's case not a choice", junit_entry("r.xml", "r", case="input"), ("case", "name")),
    ("a cut that is text", ragas_entry("e/r.jsonl", "r", cut="half"), ("cut", "number")),
    ("a cut in quotes", ragas_entry("e/r.jsonl", "r", cut="0.5"), ("cut", "number")),
    ("recorded for ragas", ragas_entry("e/r.jsonl", "r", cut="recorded"), ("cut", "number")),
    ("failed not a list", import_entry("t.csv", "table", "t", case_column="case", outcome_column="o", failed="x"), ("failed", "list")),
    ("failed holding a number", import_entry("t.csv", "table", "t", case_column="case", outcome_column="o", failed=["x", 1]), ("failed",)),
    ("a required flag missing", import_entry("e/r.jsonl", "ragas", "r", metric="faithfulness", cut=0.5, below=True), ("case_column",)),
    ("deepeval's metric missing", import_entry("d.json", "deepeval", "d", cut="recorded", case="name"), ("metric",)),
]


@pytest.mark.parametrize("case,entry,facts", WRONG_OPTIONS, ids=[c for c, _, _ in WRONG_OPTIONS])
def test_tf17_16_the_readers_options_are_checked_as_its_flags_are(tmp_path: Path, case: str, entry: str, facts: tuple[str, ...]) -> None:
    folder = work(tmp_path)
    text = config_text(entry, store="s")
    said = fault(text, folder)
    assert "[[import]]" in said, said
    for fact in facts:
        assert fact in said, (fact, said)
    assert re.search(r"\bline \d+\b", said), said


RIGHT_OPTIONS = [
    ("deepeval recorded", import_entry("d.json", "deepeval", "d", metric="m", cut="recorded", case="name")),
    ("deepeval a number with a side", import_entry("d.json", "deepeval", "d", metric="m", cut=0.7, above=True, case="input")),
    ("junit by its default", import_entry("r.xml", "junit", "r")),
    ("junit by name", junit_entry("r.xml", "r")),
    ("a table by its outcomes", import_entry("t.csv", "table", "t", case_column="case", outcome_column="o", failed=["x", "y"])),
    ("a table by its scores", import_entry("t.csv", "table", "t", case_column="case", score_column="s", cut=1, below=True)),
    ("ragas with a whole-number cut", ragas_entry("e/r.jsonl", "r", cut=1)),
]


@pytest.mark.parametrize("case,entry", RIGHT_OPTIONS, ids=[c for c, _ in RIGHT_OPTIONS])
def test_tf17_16_each_readers_right_options_read(tmp_path: Path, case: str, entry: str) -> None:
    folder = work(tmp_path)
    held = parse(config_text(entry, store="s"), folder)
    assert len(held.imports) == 1


# ---------- TF17-17 ----------


def test_tf17_17_a_name_is_one_the_import_accepts_and_is_used_once(tmp_path: Path) -> None:
    folder = work(tmp_path)
    for bad in ("latest", "trace-names.toml", " spaced", "a/b", "."):
        text = config_text(ragas_entry("e/r.jsonl", bad), store="s")
        said = fault(text, folder)
        assert f"line {line_of(text, 'name = ')}" in said and "[[import]]" in said, (bad, said)
    text = config_text(ragas_entry("e/a.jsonl", "same"), ragas_entry("e/b.jsonl", "same"), store="s")
    said = fault(text, folder)
    lines = [n for n, line in enumerate(text.splitlines(), start=1) if line.startswith("[[import]]")]
    assert len(lines) == 2 and all(f"line {n}" in said for n in lines) and "same" in said, said


# ---------- TF17-18 ----------


def test_tf17_18_file_is_a_relative_path_inside_the_repository_kept_as_written(tmp_path: Path) -> None:
    folder = work(tmp_path)
    for outside in ("/tmp/r.jsonl", "../r.jsonl", "evals/../../r.jsonl"):
        text = config_text(ragas_entry(outside, "r"), store="s")
        said = fault(text, folder)
        assert f"line {line_of(text, 'file = ')}" in said and outside in said, (outside, said)
    held = parse(config_text(ragas_entry("evals/./rag-base.jsonl", "r"), store="s"), folder)
    assert held.imports[0].file == "evals/./rag-base.jsonl"
    # one file, two entries: one promptfoo file holds both versions
    two = parse(config_text(ragas_entry("e/r.jsonl", "old"), ragas_entry("e/r.jsonl", "new", cut=0.6), store="s"), folder)
    assert [i.name for i in two.imports] == ["old", "new"]


# ---------- TF17-19 ----------


def test_tf17_19_a_folder_reads_at_the_config_level_and_opens_nothing(tmp_path: Path) -> None:
    folder = work(tmp_path)
    (folder / "evals" / "old").mkdir(parents=True)
    held = parse(config_text(ragas_entry("evals/old", "old"), store="s"), folder)
    assert held.imports[0].file == "evals/old"
    # a folder that is not there reads the same: nothing here opens it
    held = parse(config_text(ragas_entry("evals/missing", "old"), store="s"), folder)
    assert held.imports[0].file == "evals/missing"


# ---------- TF17-20 ----------


@pytest.mark.parametrize("address", [f"{p}:{rest}" for p, rest in zip(PULLERS, ("my-project", "exp_9f8a7b6c", "me/proj/eval", "tr_1"), strict=True)])
def test_tf17_20_an_address_to_pull_from_is_refused_naming_the_missing_puller(tmp_path: Path, address: str) -> None:
    folder = work(tmp_path)
    puller = address.split(":", 1)[0]
    text = config_text(import_entry(address, "table", "pulled", case_column="c", outcome_column="o", failed=["x"]), store="s")
    said = fault(text, folder)
    assert f"line {line_of(text, 'file = ')}" in said and address in said, said
    assert puller in said and "not in this install" in said, said
    assert re.search(r"save|export", said), said


def test_tf17_20_a_file_whose_name_holds_a_colon_is_a_file(tmp_path: Path) -> None:
    folder = work(tmp_path)
    held = parse(config_text(ragas_entry("evals/run:3.jsonl", "r"), store="s"), folder)
    assert held.imports[0].file == "evals/run:3.jsonl"


# ---------- TF17-21 ----------


def test_tf17_21_every_verb_checks_the_entries_and_none_but_doctor_and_init_opens_the_files(tmp_path: Path) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    write_toml(folder, config_text(ragas_entry("evals/missing.jsonl", "r"), store="proofload-runs", events=("unsolved",)))
    r = trace_in(folder, ["runs"])
    assert r.code == 0 and "3 runs in proofload-runs" in r.out, r.text
    write_toml(folder, config_text(import_entry("evals/missing.jsonl", "langsmith", "r"), store="proofload-runs", events=("unsolved",)))
    for argv in (["runs"], ["where", "20260915T210140Z-4847"], ["compare", "20260915T210140Z-4847", "20260915T211148Z-965d"], ["doctor"]):
        r = trace_in(folder, argv)
        assert r.code in (1, 4), (argv, r.text)
        assert "langsmith" in r.text and "line" in r.text, (argv, r.text)
    base, _ = ragas_pair(folder)
    write_toml(folder, config_text(ragas_entry(base, "r"), store="proofload-runs", events=("unsolved",)))
    assert trace_in(folder, ["where", "20260915T210140Z-4847"]).code == 0


# ---------- TF17-23 ----------


def test_tf17_23_an_unknown_table_names_the_import_tables(tmp_path: Path) -> None:
    folder = work(tmp_path)
    said = fault('version = 1\n[colours]\nx = 1\n', folder)
    assert said == (
        "trace.toml line 2: [colours] is not a table; a config has version, the tables "
        "[store], [events], [check], [names], [upload], [signals] and [taxonomy], and "
        "[[import]] tables"
    ), said
