"""TF25-80 to TF25-84: ``init`` and the files it finds, decided for the readers that pull from a
service's API together: LangSmith, Braintrust, and Weave when its reader lands (the LangSmith
pair's B-3 and B-4, handed here; the brief's item 5).

The reading frozen: ``init`` does not import such files by itself. An import of them needs two
answers ``init`` has no question and no flag for (what pairs a case across versions, and what
says a case failed), so it refuses in one sentence and prints one import line for each run,
with what it can read from the file filled in and a word in capitals for what is the user's to
say. A file that is no run of its own (a LangSmith feedback list) goes on the line of the runs
it belongs to. Files named under ``[[import]]`` in ``trace.toml`` are imported by ``init``, as
TF24-57 and TF25-57 hold.

- TF25-80: every reader in the install that pulls is refused the same way: exit 1, nothing
  written, one ``next:`` line an import; ``--import`` is the same refusal; ``--no-import``
  writes the config with no store and prints the same lines. A reader that pulls and has no
  sample here fails this test, so the next such reader (Weave) is decided with these.
- TF25-81: LangSmith's files with no feedback list among them print what main 729a678 prints,
  byte for byte: the runs query's answers, and the page's CSV.
- TF25-82: Braintrust's files are listed as Braintrust's and each has its line: the case is
  ``record`` where every root in the file carries its dataset record's id and ``input`` where
  none can (the page's downloads, an experiment on inline data); the outcome is the user's.
  Each line runs as printed once its capital is filled in, and ``init --force --store`` then
  sets up over the store, as the refusal says.
- TF25-83: a LangSmith feedback list is shown on the line of the runs it belongs to: what main
  prints for the runs, with the feedback list's path after the runs file's and no line of its
  own. That line, its capital filled in, reads the records. A feedback list whose runs are not
  among the files found has no line.
- TF25-84: files of two of these tools together are refused as files of two tools are, with a
  line for each run under its own reader.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from tf1_support import shell_words
from tf2_support import here, numbered, work
from tf21_support import INGEST
from tf25_pins import INIT, PINS, found_folder, ran_init
from tf25_support import columns, export

PINNED: dict[str, Any] = json.loads(PINS.read_text(encoding="utf-8"))
LS = INGEST / "langsmith"

#: Each reader that pulls, with two of its files as ``init`` finds them: (source, name, the
#: case its line fills in).
SAMPLES: dict[str, tuple[tuple[Path, str, str], ...]] = {
    "langsmith": ((LS / "api" / "baseline.runs-v2.json", "old.json", "example"), (LS / "api" / "candidate.runs-v2.json", "new.json", "example")),
    "braintrust": ((export("baseline", "fetch")[0], "old.json", "record"), (export("candidate", "ui-json")[0], "new.json", "input")),
}


def _folder(tmp: Path, files: Any) -> Path:
    folder = work(tmp)
    (folder / "results").mkdir()
    for source, name, *_ in files:
        shutil.copy(source, folder / "results" / name)
    return folder


def _import_lines(text: str, prefix: str) -> list[list[str]]:
    return [shell_words(line[len(prefix):].strip()) for line in text.splitlines()
            if line.startswith(prefix) and line[len(prefix):].strip().startswith("poisson-trace import ") and "--help" not in line]


def _tree(folder: Path) -> list[str]:
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*"))


# ---------- TF25-80 ----------


def test_tf25_80_every_reader_that_pulls_has_its_sample_here() -> None:
    from poisson_trace.ingest.importing import present, pulls

    pullers = [tool for tool in present() if pulls(tool) is not None]
    assert pullers and set(pullers) == set(SAMPLES), pullers


@pytest.mark.parametrize("tool", list(SAMPLES))
@pytest.mark.parametrize("flags", [(), ("--import",)])
def test_tf25_80_init_refuses_the_files_of_a_reader_that_pulls_and_prints_a_line_for_each(tmp_path: Path, tool: str, flags: tuple[str, ...]) -> None:
    folder = _folder(tmp_path, SAMPLES[tool])
    before = _tree(folder)
    ran = here(folder, ["init", "--yes", *flags])
    assert ran.code == 1 and ran.out == "", ran.text
    error = next(line for line in ran.err.splitlines() if line.startswith("error: "))
    assert f"written by {tool}" in error and "--case-from and --outcome-from" in error and "does not ask for" in error, error
    assert "imported none" in error and "[[import]]" in error and "--no-import" in error, error
    lines = _import_lines(ran.err, "  next: ")
    assert len(lines) == len(SAMPLES[tool]), ran.err
    for _, name, case in SAMPLES[tool]:
        words = next(w for w in lines if f"results/{name}" in w)
        assert words[:4] == ["poisson-trace", "import", tool, f"results/{name}"], words
        assert words[words.index("--store") + 1] == "trace-store" and words[words.index("--run") + 1] == name.split(".")[0], words
        assert words[words.index("--case-from") + 1] == case and words[words.index("--outcome-from") + 1] == "OUTCOME", words
    assert _tree(folder) == before, "a refusal writes nothing"


@pytest.mark.parametrize("tool", list(SAMPLES))
def test_tf25_80_no_import_writes_the_config_and_prints_the_same_lines(tmp_path: Path, tool: str) -> None:
    folder = _folder(tmp_path, SAMPLES[tool])
    refused = here(folder, ["init", "--yes"])
    ran = here(folder, ["init", "--yes", "--no-import"])
    assert ran.code == 0 and ran.out.startswith("ok  wrote trace.toml with no store yet"), ran.text
    assert _import_lines(ran.out, "    ") == _import_lines(refused.err, "  next: ")
    assert (folder / "trace.toml").is_file() and not (folder / "trace-store").exists()


# ---------- TF25-81 ----------


@pytest.mark.parametrize("label", ["init: langsmith runs", "init: langsmith csv"])
def test_tf25_81_langsmith_s_files_with_no_feedback_list_print_what_main_prints(tmp_path: Path, label: str) -> None:
    holds, steps = INIT[label]
    got = [list(step) for step in ran_init(tmp_path, holds, steps)]
    assert got == PINNED["init"][label]
    assert got[0][0] == 1 and got[1][0] == 0


# ---------- TF25-82 ----------

BRAINTRUST: dict[str, tuple[Path, str]] = {
    "old.json": (export("baseline", "fetch")[0], "record"),
    "new-traces.json": (export("candidate", "btql-traces")[0], "record"),
    "new-summary.json": (export("candidate", "summary")[0], "record"),
    "old-page.json": (export("baseline", "ui-json")[0], "input"),
    "new-page.csv": (export("candidate", "ui-csv")[0], "input"),
    "lookup.json": (export("old", "fetch")[0], "input"),
}


def test_tf25_82_braintrust_s_files_are_listed_and_each_has_its_line(tmp_path: Path) -> None:
    folder = _folder(tmp_path, [(source, name) for name, (source, _) in BRAINTRUST.items()])
    ran = here(folder, ["init", "--yes"])
    assert ran.code == 1, ran.text
    listed = {line.split()[0]: line for line in numbered(ran.err).values()}
    assert sorted(listed) == sorted(f"results/{name}" for name in BRAINTRUST), ran.err
    assert all("Braintrust" in line for line in listed.values()), listed
    lines = _import_lines(ran.err, "  next: ")
    assert len(lines) == len(BRAINTRUST)
    for name, (_, case) in BRAINTRUST.items():
        words = next(w for w in lines if f"results/{name}" in w)
        assert words[:3] == ["poisson-trace", "import", "braintrust"], words
        assert words[words.index("--case-from") + 1] == case, (name, words)
        assert words[words.index("--outcome-from") + 1] == "OUTCOME", words
        assert "--cut" not in words and "OTHER" not in words, words


def test_tf25_82_before_this_reader_init_found_none_of_them() -> None:
    """What main prints on Braintrust's files, kept in words: it finds no result file there."""
    refused, written = PINNED["init"]["init: braintrust files"]
    assert refused[0] == 0 and written[0] == 0
    assert "found no store and no result file a reader of this install reads" in refused[2]


@pytest.mark.parametrize("names", [("old.json", "new-traces.json"), ("old-page.json", "new-page.csv")])
def test_tf25_82_each_line_runs_once_its_capital_is_filled_in(tmp_path: Path, names: tuple[str, str]) -> None:
    from tf0_support import chdir, trace

    folder = _folder(tmp_path, [(BRAINTRUST[name][0], name) for name in names])
    ran = here(folder, ["init", "--yes"])
    lines = _import_lines(ran.err, "  next: ")
    assert len(lines) == 2
    with chdir(folder):
        for words in lines:
            filled = [w if w != "OUTCOME" else "error" for w in words]
            done = trace(filled[1:])
            assert done.code == 0, done.text
    runs = [words[words.index("--run") + 1] for words in lines]
    for run in runs:
        assert len(columns(folder / "trace-store", run)) == 10
    # then init sets up over the store, as the refusal says
    after = here(folder, ["init", "--yes", "--force", "--store", "trace-store"])
    assert after.code == 0 and (folder / "trace.toml").is_file(), after.text


# ---------- TF25-83 ----------


def _folded(text: str) -> str:
    """Main's output on runs and their feedback lists, as it is with each feedback list on its
    runs' line: the line of a feedback list alone gone, and its path after its runs file's."""
    out = []
    for line in text.split("\n"):
        if "poisson-trace import langsmith results/" in line and "-feedback.json --store" in line:
            continue
        for run in ("old", "new"):
            line = line.replace(f"import langsmith results/{run}.json --store", f"import langsmith results/{run}.json results/{run}-feedback.json --store")
        out.append(line)
    return "\n".join(out)


def test_tf25_83_a_feedback_list_is_shown_on_the_line_of_the_runs_it_belongs_to(tmp_path: Path) -> None:
    label = "init: langsmith runs and feedback"
    holds, steps = INIT[label]
    got = [list(step) for step in ran_init(tmp_path, holds, steps)]
    main = PINNED["init"][label]
    want = [[code, _folded(out), _folded(err)] for code, out, err in main]
    assert got == want
    assert got != main, "main gives the feedback list a line of its own"
    # main's own lines, to say what moved: four import lines, two of them a feedback list alone
    assert len(_import_lines(main[0][2], "  next: ")) == 4 and len(_import_lines(got[0][2], "  next: ")) == 2
    for words in _import_lines(got[0][2], "  next: "):
        run = words[words.index("--run") + 1]
        assert words[3:5] == [f"results/{run}.json", f"results/{run}-feedback.json"], words
    # every file found is still listed
    assert len(numbered(got[0][2])) == 4


def test_tf25_83_the_folded_line_reads_the_feedback_records(tmp_path: Path) -> None:
    from tf0_support import chdir, trace
    from tf24_support import columns as ls_columns

    folder = found_folder(tmp_path, "runs+feedback")
    ran = here(folder, ["init", "--yes"])
    words = next(w for w in _import_lines(ran.err, "  next: ") if "results/old.json" in w)
    at = words.index("OUTCOME")
    filled = [*words[:at], "feedback:exact", "--cut", "0.5", "--below", *words[at + 1:]]
    with chdir(folder):
        done = trace(filled[1:])
    assert done.code == 0, done.text
    # the baseline's run statistics lack the score on two roots; the records beside them fill it
    outcomes = [row["outcome"] for row in ls_columns(folder / "trace-store", "old").values()]
    assert (outcomes.count("met"), outcomes.count("missed")) == (6, 4)


@pytest.mark.parametrize("held", [
    (("api/baseline.feedback.json", "old-feedback.json"),),
    (("api/candidate.runs-v2.json", "new.json"), ("api/baseline.feedback.json", "old-feedback.json")),
])
def test_tf25_83_a_feedback_list_whose_runs_are_not_found_has_no_line(tmp_path: Path, held: Any) -> None:
    folder = _folder(tmp_path, [(LS / source, name) for source, name in held])
    ran = here(folder, ["init", "--yes", "--no-import"])
    assert ran.code == 0, ran.text
    lines = _import_lines(ran.out, "    ")
    assert not [w for w in lines if "results/old-feedback.json" in w], lines
    assert len(lines) == len(held) - 1
    assert any("results/old-feedback.json" in line for line in numbered(ran.err).values()), ran.err


# ---------- TF25-84 ----------


def test_tf25_84_files_of_two_of_these_tools_are_refused_with_a_line_for_each(tmp_path: Path) -> None:
    files = [*SAMPLES["langsmith"], (export("baseline", "fetch")[0], "bt-old.json", "record"), (export("candidate", "fetch")[0], "bt-new.json", "record")]
    folder = _folder(tmp_path, files)
    before = _tree(folder)
    ran = here(folder, ["init", "--yes"])
    assert ran.code == 1 and ran.out == "", ran.text
    error = next(line for line in ran.err.splitlines() if line.startswith("error: "))
    assert "2 tools" in error and "braintrust" in error and "langsmith" in error and "imported none" in error, error
    lines = _import_lines(ran.err, "  next: ")
    assert len(lines) == 4
    for _, name, case in files:
        words = next(w for w in lines if f"results/{name}" in w)
        assert words[2] == ("braintrust" if name.startswith("bt-") else "langsmith"), words
        assert words[words.index("--case-from") + 1] == case, words
    assert _tree(folder) == before
