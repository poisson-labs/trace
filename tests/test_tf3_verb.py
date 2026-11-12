"""TF3-1 to TF3-7: the import is a verb of the main command, and the old command is its alias
(spec sections 3.1, 5.1, 8.5 and 9.1 rule L1; ruled 2026-10-12: "poisson-trace import", with
poisson-trace-import kept working with the same behaviour, help and exit codes).

- TF3-1: ``poisson-trace import …`` and ``poisson-trace-import …`` print the same bytes on both
  streams, exit with the same code and write the same run, for every kind of invocation: help,
  the version, each refusal, each wrong command line, each reader's import, text and JSON.
- TF3-2: the same holds without Prove and with Prove at another version; help needs no Prove.
- TF3-3: the import's options may stand before the verb, between the verb and the tool, or after.
- TF3-4: ``python -m poisson_trace import`` is the verb.
- TF3-5: Ctrl-C while the verb writes is the alias's stopped line and exit 130.
- TF3-6: the main help lists ``import`` among its verbs, and the main command's own refusals
  name it among them.
- TF3-7: nothing the package prints or holds as text names ``poisson-trace-import`` as the command
  to run: every help example, every next line, init's and doctor's lines say ``poisson-trace import``.
"""

from __future__ import annotations

import ast
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from poisson_prove.store import Store

from tf0_support import Ran, chdir, examples, ragas_import, run_module, run_sub, trace
from tf1_support import shell_words
from tf2_support import config_of, deepeval_file, doctor_doc, init_yes, scratch_home, work, write_config  # noqa: F401
from tf3_support import (
    NEW_READERS, OLD, PRESENT, SUITE_1, TABLE_A, alias, both, junit_argv, read_rows, src_files, table_argv, verb,
    write_table,
)

# ---------- a folder every invocation of the corpus can run in ----------


def _prepared(folder: Path) -> Path:
    """The files the corpus names, by relative path: a DeepEval run, a table, a JUnit report, a
    file that is not XML, and a store already holding a run named ``held``."""
    folder.mkdir(parents=True, exist_ok=True)
    deepeval_file(folder / "results" / "test_run_20261002_101500.json")
    shutil.copy(TABLE_A, folder / "he-a.csv")
    shutil.copy(SUITE_1, folder / "suite-1.xml")
    (folder / "not-xml.xml").write_text("this is not XML\n", encoding="utf-8")
    write_table(folder / "small.csv", [{"case": "a", "outcome": "fail", "score": 0.2}, {"case": "b", "outcome": "ok", "score": 0.9}])
    with chdir(folder):
        assert alias(table_argv("small.csv", "held-store", "held")).code == 0
    return folder


DE = ["deepeval", "results/test_run_20261002_101500.json", "--store", "st", "--run", "r1", "--metric", "Tests Passed",
      "--cut", "recorded", "--case", "name", "--started", "2026-10-02T10:15:00Z"]
CORPUS: dict[str, list[str]] = {
    "the import's help": ["--help"],
    **{f"{tool}'s help": [tool, "--help"] for tool in PRESENT},
    "the version": ["--version"],
    "no tool": [],
    "an unknown tool": ["otel", "x.json", "--store", "st", "--run", "r1"],
    "an unknown option": [*DE, "--bogus"],
    "an abbreviated option": [*DE[:-2], "--start", "2026-10-02T10:15:00Z"],
    "no --run": DE[:4] + DE[6:],
    "a run name with a slash": [*DE[:5], "a/b", *DE[6:]],
    "a run the store holds": table_argv("small.csv", "held-store", "held"),
    "a DeepEval import": DE,
    "a DeepEval import as JSON": [*DE, "--json"],
    "a Ragas import": ragas_import("st", "r1"),
    "a table import": table_argv("he-a.csv", "st", "r1", "--started", "2026-09-05T18:54:07Z", failed=("failed_assertion", "crashed")),
    "a table import as JSON": table_argv("small.csv", "st", "r1", "--json", "--started", "2026-10-02T10:15:00Z"),
    "a table import by score": table_argv("small.csv", "st", "r1", "--started", "2026-10-02T10:15:00Z", score="score", cut="0.5", side="below"),
    "a table with neither column": ["table", "small.csv", "--store", "st", "--run", "r1", "--case-column", "case"],
    "a table column it does not hold": table_argv("small.csv", "st", "r1", outcome="status"),
    "a JUnit import": junit_argv("suite-1.xml", "st", "r1"),
    "a JUnit import as JSON": junit_argv("suite-1.xml", "st", "r1", "--json", "--case", "name"),
    "a JUnit file that is not XML": junit_argv("not-xml.xml", "st", "r1"),
    "a JUnit case form it does not know": junit_argv("suite-1.xml", "st", "r1", "--case", "file"),
}


def _same_store(a: Path, b: Path) -> None:
    runs_a = Store(a).runs() if a.exists() else []
    runs_b = Store(b).runs() if b.exists() else []
    assert runs_a == runs_b
    for run in runs_a:
        ma, mb = Store(a).manifest(run), Store(b).manifest(run)
        assert (ma.target_id, ma.backend, ma.created_at, ma.status, ma.environment) == (mb.target_id, mb.backend, mb.created_at, mb.status, mb.environment)
        assert read_rows(a, run) == read_rows(b, run)


@pytest.mark.parametrize("label", list(CORPUS))
def test_tf3_01_the_verb_and_the_alias_are_one_command(tmp_path: Path, label: str) -> None:
    argv = CORPUS[label]
    prepared = _prepared(tmp_path / "prepared")
    places = {}
    results: dict[str, Ran] = {}
    for spelling in ("verb", "alias"):
        places[spelling] = shutil.copytree(prepared, tmp_path / spelling)
        with chdir(places[spelling]):
            results[spelling] = (verb if spelling == "verb" else alias)(argv)
    a, b = results["verb"], results["alias"]
    assert (a.code, a.out, a.err) == (b.code, b.out, b.err), (label, a.text, b.text)
    assert a.code != -1, a.text
    _same_store(places["verb"] / "st", places["alias"] / "st")


def test_tf3_01_every_help_reads_the_verb(tmp_path: Path) -> None:
    """The usage line of the import's help and of each reader's help is the verb's, under both
    spellings: the alias's help is the verb's help."""
    for words in ([], *[[tool] for tool in PRESENT]):
        a, b = both([*words, "--help"])
        assert a.code == 0 and a.out == b.out and a.err == b.err == "", (words, a.text, b.text)
        usage = a.out.split("\n\n")[0]
        assert usage.startswith("usage: poisson-trace import" + (f" {words[0]}" if words else "")), usage
        if not words:
            for tool in PRESENT:
                assert re.search(rf"^ +{tool} {{2,}}\S", a.out, re.M), (tool, a.out)
    # the readers this install reads, named when a tool is not one of them
    unknown = verb(["otel", "x.json", "--store", "st", "--run", "r1"])
    assert unknown.code == 1 and all(tool in unknown.lines()[0] for tool in PRESENT), unknown.err


# ---------- TF3-2: without Prove ----------


@pytest.mark.parametrize("prove", ["absent", "0.0.0-other"])
def test_tf3_02_without_prove_both_spellings_refuse_alike(tmp_path: Path, prove: str) -> None:
    folder = _prepared(tmp_path / "f")
    argv = table_argv("small.csv", "st", "r1")
    a = run_sub("trace", ["import", *argv], prove=prove, cwd=folder)
    b = run_sub("import", argv, prove=prove, cwd=folder)
    assert a.code == b.code == 1 and (a.out, a.err) == (b.out, b.err), (a.text, b.text)
    assert "pip install" in a.err and not (folder / "st").exists()
    for words in (["--help"], ["table", "--help"], ["junit", "--help"], ["--version"]):
        a = run_sub("trace", ["import", *words], prove=prove, cwd=folder)
        b = run_sub("import", words, prove=prove, cwd=folder)
        assert a.code == b.code == 0 and (a.out, a.err) == (b.out, b.err), (words, a.text, b.text)


# ---------- TF3-3: where the options stand ----------


def _de_json(store: str) -> list[str]:
    return ["--store", store, "--run", "r1", "--metric", "Tests Passed", "--cut", "recorded", "--case", "name",
            "--started", "2026-10-02T10:15:00Z", "--json"]


PLACES = {
    "after the tool": lambda f, o: ["import", "deepeval", f, *o],
    "between the verb and the tool": lambda f, o: ["import", *o, "deepeval", f],
    "before the verb": lambda f, o: [*o, "import", "deepeval", f],
    "on both sides": lambda f, o: [*o[:4], "import", "deepeval", f, *o[4:]],
}


@pytest.mark.parametrize("place", list(PLACES))
def test_tf3_03_options_may_stand_anywhere(tmp_path: Path, place: str) -> None:
    base = work(tmp_path, "base")
    deepeval_file(base / "r.json")
    with chdir(base):
        want = alias(["deepeval", "r.json", *_de_json("st")])
    folder = work(tmp_path, "here")
    deepeval_file(folder / "r.json")
    with chdir(folder):
        got = trace(PLACES[place]("r.json", _de_json("st")))
    assert (got.code, got.out, got.err) == (want.code, want.out, want.err), got.text
    _same_store(base / "st", folder / "st")


@pytest.mark.parametrize("option", ["--bogus", "--star"], ids=["unknown", "abbreviated"])
def test_tf3_03_a_wrong_option_before_the_verb_is_the_alias_s_wrong_option(tmp_path: Path, option: str) -> None:
    folder = _prepared(tmp_path / "f")
    argv = [option, "x", "deepeval", "results/test_run_20261002_101500.json", "--store", "st", "--run", "r1"]
    with chdir(folder):
        a = trace([*argv[:2], "import", *argv[2:]])
        b = alias(argv)
    assert a.code == b.code == 2 and (a.out, a.err) == (b.out, b.err), (a.text, b.text)


def test_tf3_03_the_config_given_before_the_verb_names_the_store(tmp_path: Path) -> None:
    folder = work(tmp_path)
    deepeval_file(folder / "r.json")
    write_config(folder, 'version = 1\n\n[store]\npath = "from-config"\n', "other.toml")
    argv = ["r.json", "--run", "r1", "--metric", "Tests Passed", "--cut", "recorded", "--case", "name"]
    with chdir(folder):
        result = trace(["--config", "other.toml", "import", "deepeval", *argv])
    assert result.code == 0, result.text
    assert Store(folder / "from-config").runs() == ["r1"]


# ---------- TF3-4 and TF3-5 ----------


def test_tf3_04_python_m_runs_the_verb(tmp_path: Path) -> None:
    folder = _prepared(tmp_path / "f")
    help_text = run_module(["import", "table", "--help"], cwd=folder)
    assert help_text.code == 0 and help_text.out == verb(["table", "--help"]).out, help_text.text
    done = run_module(["import", *junit_argv("suite-1.xml", "st", "r1")], cwd=folder)
    assert done.code == 0, done.text
    assert Store(folder / "st").runs() == ["r1"]


def test_tf3_05_ctrl_c_while_the_verb_writes_is_the_alias_stop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def stop(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    results = {}
    for spelling, command in (("verb", verb), ("alias", alias)):
        folder = _prepared(tmp_path / spelling)
        with monkeypatch.context() as patched, chdir(folder):
            patched.setattr(Store, "append", stop)
            results[spelling] = command(junit_argv("suite-1.xml", "st", "r1"))
    a, b = results["verb"], results["alias"]
    assert a.code == b.code == 130 and (a.out, a.err) == (b.out, b.err), (a.text, b.text)
    assert a.out.startswith("stopped  ") and "r1" in a.out.splitlines()[0], a.out


# ---------- TF3-6: the main command knows the verb ----------


def test_tf3_06_the_main_help_lists_import_as_a_verb() -> None:
    result = trace(["--help"])
    assert result.code == 0, result.text
    # an entry of the help's list: the word indented, then its help after two spaces or more
    assert re.search(r"^ +import {2,}\S", result.out, re.M), result.out
    assert OLD not in result.out


@pytest.mark.parametrize("argv", [[], ["imports"], ["--json"]], ids=["no verb", "an unknown verb", "options alone"])
def test_tf3_06_the_main_command_names_import_among_its_verbs(argv: list[str]) -> None:
    result = trace(argv)
    assert result.code == 2, result.text
    assert "import" in result.lines()[0].replace(",", " ").split(), result.err


# ---------- TF3-7: the old name is never the command shown ----------


def _shown(tmp_path: Path) -> list[tuple[str, Ran]]:
    """Every output that names a command to run: the helps of both spellings, the refusals and
    wrong command lines of the corpus, init's lines, doctor's line for a config with no store."""
    out: list[tuple[str, Ran]] = []
    folder = _prepared(tmp_path / "shown")
    with chdir(folder):
        for label, argv in CORPUS.items():
            if "--help" in argv or not label.startswith(("a DeepEval import", "a Ragas import", "a table import", "a JUnit import")):
                out.append((f"verb: {label}", verb(argv)))
                out.append((f"alias: {label}", alias(argv)))
    nothing = work(tmp_path, "nothing")
    out.append(("init with nothing found", init_yes(nothing)))
    two = work(tmp_path, "two-tools")
    deepeval_file(two / "results" / "test_run_20261002_101500.json")
    shutil.copy(SUITE_1, two / "suite-1.xml")
    out.append(("init with two tools' files", init_yes(two)))
    one = work(tmp_path, "one-tool")
    deepeval_file(one / "results" / "test_run_20261002_101500.json")
    out.append(("init importing", init_yes(one, "--metric", "Tests Passed", "--cut", "recorded", "--case", "name")))
    bare = work(tmp_path, "bare")
    write_config(bare, "version = 1\n")
    code, data = doctor_doc(bare)
    out.append(("doctor on a config with no store", Ran(code, "\n".join(str(c["line"]) + " " + str(c["next"]) for c in data["checks"]), "")))
    return out


def test_tf3_07_no_output_names_the_old_command(tmp_path: Path) -> None:
    for label, result in _shown(tmp_path):
        assert OLD not in result.text, (label, result.text)


def test_tf3_07_init_and_doctor_point_at_the_verb(tmp_path: Path) -> None:
    shown = dict(_shown(tmp_path))
    for label in ("init with nothing found", "init with two tools' files", "init importing", "doctor on a config with no store"):
        assert "poisson-trace import" in shown[label].text, (label, shown[label].text)
    # the import lines init prints run as written, under the verb
    lines = [line.strip() for line in shown["init importing"].out.splitlines() if "poisson-trace import deepeval" in line]
    assert lines, shown["init importing"].out
    for line in lines:
        words = shell_words(line[line.index("poisson-trace import"):])
        assert words[:3] == ["poisson-trace", "import", "deepeval"], words


@pytest.mark.parametrize("words", [[], *[[t] for t in PRESENT]], ids=["import", *PRESENT])
def test_tf3_07_every_help_example_is_the_verb(words: list[str]) -> None:
    for command in (verb, alias):
        text = command([*words, "--help"]).out
        found = examples(text, ["poisson-trace", OLD])
        assert found, text
        for example in found:
            assert shell_words(example)[:2] == ["poisson-trace", "import"], example
            if words:
                assert shell_words(example)[2] == words[0], example


def _docstrings(tree: ast.AST) -> set[int]:
    """The ids of the string nodes that are docstrings."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                out.add(id(first.value))
    return out


def test_tf3_07_no_string_of_the_package_spells_the_old_command() -> None:
    """Outside docstrings, which may say that the alias exists, no string the package holds
    spells the old name: a line nothing above reaches would print it."""
    for path in src_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = _docstrings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
                assert OLD not in node.value, f"{path.name}:{node.lineno}: {node.value!r}"


@pytest.mark.parametrize("tool", NEW_READERS)
def test_tf3_07_the_new_readers_help_examples_run_as_written(tmp_path: Path, tool: str) -> None:
    """Every example of the table and JUnit helps runs where the files it names hold the
    committed fixtures' data."""
    text = verb([tool, "--help"]).out
    found = examples(text, ["poisson-trace import"])
    assert found, text
    for i, example in enumerate(found):
        folder = work(tmp_path, f"example-{i}")
        words = shell_words(example)
        assert words[:3] == ["poisson-trace", "import", tool], example
        for word in words[3:]:
            if word.startswith("-"):
                break
            target = folder / word
            target.parent.mkdir(parents=True, exist_ok=True)
            if tool == "table":
                _table_for(example, target)
            else:
                shutil.copy(SUITE_1, target)
        with chdir(folder):
            result = trace(words[1:])
        assert result.code == 0, (example, result.text)


def _table_for(example: str, target: Path) -> None:
    """A table at ``target`` holding the HumanEval fixture's rows under the columns the example
    names: its case column, and its outcome column with its failure values, or its score column
    with a score of 1 for a pass and 0 otherwise."""
    import csv

    words = shell_words(example)

    def value(flag: str) -> str | None:
        return words[words.index(flag) + 1] if flag in words else None

    failed = [words[i + 1] for i, w in enumerate(words) if w == "--failed"]
    case, outcome, score = value("--case-column"), value("--outcome-column"), value("--score-column")
    assert case is not None, example
    with open(TABLE_A, encoding="utf-8", newline="") as f:
        source = list(csv.DictReader(f))
    rows: list[dict[str, Any]] = []
    for row in source:
        made: dict[str, Any] = {case: row["case"]}
        if outcome is not None:
            made[outcome] = failed[0] if row["outcome"] != "passed" else "passed"
        if score is not None:
            made[score] = 1.0 if row["outcome"] == "passed" else 0.0
        rows.append(made)
    write_table(target, rows)
