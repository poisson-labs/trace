"""Choices the import under the main command and the two readers make where the frozen
tests leave room: the table's summary counts the rows each failure value matched, so a
value that matched nothing shows; a start given on the command line drops the note a JUnit
timestamp with no zone carries; init's table import replays a failure value that opens with a
dash; an option nobody knows, before a verb that is not import, stays the main command's to
refuse though a later word is "import"; an option joined to its value by "=" before the verb is
read as one word; and the table's wrong command lines are read before Prove is looked for."""

from __future__ import annotations

from pathlib import Path

from poisson_prove.store import Store

from look_support import chdir, run_sub, trace
from names_support import shell_words
from setup_support import copy_tree, doc, here, init_yes, scratch_home, work  # noqa: F401
from junit_table_support import Case, imported, junit_argv, outcome_rows, report, suite, table_argv, verb, write_report, write_table


def test_the_table_summary_counts_each_failure_value_a_value_that_matched_nothing_as_0(tmp_path: Path) -> None:
    write_table(tmp_path / "t.csv", outcome_rows([("a", "fail"), ("b", "fail"), ("c", "ok")]))
    with chdir(tmp_path):
        data = imported(verb([*table_argv("t.csv", "st", "r", failed=("fail", "FAIL")), "--json"]))
    counted = {label: n for label, n in data["counts"].items() if "fail" in label or "FAIL" in label}
    assert sorted(counted.values()) == [0, 2], data["counts"]
    assert any("FAIL" in label and n == 0 for label, n in counted.items()), data["counts"]


def test_a_start_given_drops_the_note_of_a_timestamp_with_no_zone(tmp_path: Path) -> None:
    write_report(tmp_path / "r.xml", report(suite([Case("test_a"), Case("test_b", result="failure")], timestamp="2026-10-12T09:30:15")))
    with chdir(tmp_path):
        said = imported(verb([*junit_argv("r.xml", "st", "said"), "--json"]))
        given = imported(verb([*junit_argv("r.xml", "st", "given", "--started", "2026-10-12T09:30:15Z"), "--json"]))
        text = verb(junit_argv("r.xml", "st", "text", "--started", "2026-10-12T09:30:15Z"))
    assert set(said["started"]) > {"at", "from"}, said["started"]
    assert set(given["started"]) == {"at", "from"} and given["started"]["from"] == "given", given["started"]
    started = next(line for line in text.out.splitlines() if line.startswith("- started:"))
    assert started.endswith("from: given"), started


def test_init_replays_a_table_failure_value_that_opens_with_a_dash(tmp_path: Path) -> None:
    folder = work(tmp_path, "source")
    write_table(folder / "runs" / "old.csv", [{"case": c, "outcome": "-1" if c == "a" else "0"} for c in "abcd" for _ in range(2)])
    pristine = copy_tree(folder, tmp_path / "pristine")
    replayed_folder, text_folder, line_folder = (copy_tree(pristine, tmp_path / n) for n in ("replay", "text", "line"))
    result = init_yes(folder, "--case-column", "case", "--outcome-column", "outcome", "--failed=-1", "--json")
    assert result.code == 0, result.text
    command = doc(result)["equivalent_command"]
    assert "--failed=-1" in command, command
    replayed = here(replayed_folder, command[1:])
    assert replayed.code == 0, (command, replayed.text)
    assert (replayed_folder / "trace.toml").read_bytes() == (folder / "trace.toml").read_bytes()
    text = init_yes(text_folder, "--case-column", "case", "--outcome-column", "outcome", "--failed=-1")
    line = next(line.strip() for line in text.out.splitlines() if "poisson-trace import table" in line)
    words = shell_words(line[line.index("poisson-trace import"):])
    assert "--failed=-1" in words and here(line_folder, words[1:]).code == 0, words


def test_an_unknown_option_before_another_verb_is_the_main_command_s_though_import_follows(tmp_path: Path) -> None:
    with chdir(work(tmp_path)):
        result = trace(["--bogus", "runs", "import"])
    assert result.code == 2 and result.out == "", result.text
    nexts = [line[len("  next: "):] for line in result.lines() if line.startswith("  next: ")]
    assert nexts and shell_words(nexts[0])[:2] == ["poisson-trace", "--help"], result.err


def test_an_option_joined_to_its_value_before_the_verb_is_the_import_s(tmp_path: Path) -> None:
    folder = work(tmp_path)
    write_report(folder / "r.xml", report(suite([Case("test_a"), Case("test_b", result="failure")])))
    with chdir(folder):
        result = trace(["--store=st", "import", "junit", "r.xml", "--run", "r"])
    assert result.code == 0, result.text
    assert Store(folder / "st").runs() == ["r"]


def test_a_wrong_table_command_line_is_exit_2_without_prove(tmp_path: Path) -> None:
    folder = work(tmp_path)
    write_table(folder / "t.csv", outcome_rows([("a", "fail")]))
    argv = ["import", "table", "t.csv", "--store", "st", "--run", "r", "--case-column", "case"]
    for prove in ("absent", "0.0.0-other"):
        result = run_sub("trace", argv, prove=prove, cwd=folder)
        assert result.code == 2 and "pip install" not in result.err, (prove, result.text)
    assert not (folder / "st").exists()
