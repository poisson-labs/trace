"""TF26-80 to TF26-84: ``init`` and the files it finds, for the readers that pull from a
service's API (LangSmith, Braintrust and Weave together).

``init`` does not import such files by itself. An import of
them needs two answers ``init`` has no question and no flag for (what pairs a case across
versions, and what says a case failed), so it refuses in one sentence and prints one import line
for each run, with what it can read from the file filled in and a word in capitals for what is
the user's to say. Files named under ``[[import]]`` in ``trace.toml`` are imported by ``init``, as
TF26-57 holds. Weave's sample is part of TF25-80 itself.

- TF26-80: Weave's files are refused as the other two readers' are: exit 1, nothing written,
  one ``next:`` line an import; ``--import`` is the same refusal; ``--no-import`` writes the
  config with no store and prints the same lines. Held by TF25-80 in ``test_braintrust_init.py`` on
  Weave's sample.
- TF26-81: what does not move. LangSmith's and Braintrust's files print what the pinned main
  prints, byte for byte (the feedback list on its runs' line among them). Weave's files are
  found as well.
- TF26-82: Weave's files are listed as Weave's and each run has its line. The case is
  ``example`` where every row of the file carries the reference to its dataset row (the
  service's answers, the page's JSON and JSON Lines) and ``input`` where none can (the page's
  table); the outcome is the user's. A file that holds several evaluations has a line for
  each, naming it with ``--evaluation``; a file that holds no case (the Traces page with no
  filter) is listed and has no line. ``init`` finds the page's TSV as it finds its CSV. Each
  line runs as printed once its capitals are filled in, and ``init --force --store`` then sets
  up over the store, as the refusal says.
- TF26-83: a LangSmith feedback list stays on the line of the runs it belongs to when Weave's
  files are found beside it.
- TF26-84: files of two of these tools together are refused as files of two tools are, with a
  line for each run under its own reader.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from names_support import shell_words
from setup_support import here, numbered, work
from signals_support import INGEST
from weave_pins import INIT, PINS, found_folder, ran_init
from weave_support import CASES, EVALUATION, NAMES, ROOTS_ONLY, columns, export

PINNED: dict[str, Any] = json.loads(PINS.read_text(encoding="utf-8"))
LS = INGEST / "langsmith"
BT = INGEST / "braintrust"

#: Weave's sample, as TF25-80 holds it for every reader that pulls: (source, name, the case its
#: line fills in).
SAMPLE: tuple[tuple[Path, str, str], ...] = (
    (export("baseline", "pull")[0], "old.jsonl", "example"),
    (export("candidate", "expanded")[0], "new.jsonl", "example"),
)


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


# ---------- TF26-81 ----------


@pytest.mark.parametrize("label", ["init: langsmith runs", "init: langsmith runs and feedback", "init: langsmith csv", "init: braintrust files"])
def test_tf26_81_the_other_readers_files_print_what_main_prints(tmp_path: Path, label: str) -> None:
    holds, steps = INIT[label]
    got = [list(step) for step in ran_init(tmp_path, holds, steps)]
    assert got == PINNED["init"][label]
    assert got[0][0] == 1 and got[1][0] == 0


def test_tf26_81_init_finds_the_weave_files(tmp_path: Path) -> None:
    for label in ("init: weave files", "init: weave tables"):
        holds, steps = INIT[label]
        got = ran_init(tmp_path / label.split()[-1], holds, steps)
        assert got[0][0] == 1 and "written by weave" in got[0][2], got[0]
        assert got[1][0] == 0 and "poisson-trace import weave results/" in got[1][1], got[1]


# ---------- TF26-82 ----------

#: Files of one evaluation each: the name init finds it under, its source and the case its line
#: fills in.
WEAVE: dict[str, tuple[Path, str]] = {
    "old.jsonl": (export("baseline", "pull")[0], "example"),
    "new.jsonl": (export("candidate", "expanded")[0], "example"),
    "new-plain.jsonl": (export("candidate", "plain")[0], "example"),
    "lookup.jsonl": (export("old", "pull")[0], "example"),
}
#: The page's downloads, which hold all four evaluations: the case each one's lines fill in.
PAGE: dict[str, tuple[Path, str]] = {
    "page.json": (export("baseline", "ui-json")[0], "example"),
    "page.jsonl": (export("baseline", "ui-jsonl")[0], "example"),
    "page.csv": (export("baseline", "ui-csv")[0], "input"),
    "page.tsv": (export("baseline", "ui-tsv")[0], "input"),
}


def test_tf26_82_weave_s_files_are_listed_and_each_has_its_line(tmp_path: Path) -> None:
    folder = _folder(tmp_path, [(source, name) for name, (source, _) in WEAVE.items()])
    ran = here(folder, ["init", "--yes"])
    assert ran.code == 1, ran.text
    listed = {line.split()[0]: line for line in numbered(ran.err).values()}
    assert sorted(listed) == sorted(f"results/{name}" for name in WEAVE), ran.err
    assert all("Weave" in line for line in listed.values()), listed
    lines = _import_lines(ran.err, "  next: ")
    assert len(lines) == len(WEAVE)
    for name, (_, case) in WEAVE.items():
        words = next(w for w in lines if f"results/{name}" in w)
        assert words[:3] == ["poisson-trace", "import", "weave"], words
        assert words[words.index("--case-from") + 1] == case, (name, words)
        assert words[words.index("--outcome-from") + 1] == "OUTCOME", words
        assert "--cut" not in words and "OTHER" not in words and "--evaluation" not in words, words


@pytest.mark.parametrize("name", list(PAGE))
def test_tf26_82_a_file_of_several_evaluations_has_a_line_for_each(tmp_path: Path, name: str) -> None:
    source, case = PAGE[name]
    folder = _folder(tmp_path, [(source, name)])
    ran = here(folder, ["init", "--yes"])
    assert ran.code == 1, ran.text
    listed = [line for line in numbered(ran.err).values()]
    assert len(listed) == 1 and listed[0].split()[0] == f"results/{name}" and "Weave" in listed[0], ran.err
    lines = _import_lines(ran.err, "  next: ")
    assert len(lines) == 4 and all(w[:4] == ["poisson-trace", "import", "weave", f"results/{name}"] for w in lines), ran.err
    assert sorted(w[w.index("--evaluation") + 1] for w in lines) == sorted(EVALUATION.values())
    runs = [w[w.index("--run") + 1] for w in lines]
    assert len(set(runs)) == 4, "each line names its own run"
    for words in lines:
        assert words[words.index("--case-from") + 1] == case and words[words.index("--outcome-from") + 1] == "OUTCOME", words


@pytest.mark.parametrize("path", ROOTS_ONLY, ids=[p.name for p in ROOTS_ONLY])
def test_tf26_82_a_file_that_holds_no_case_is_listed_and_has_no_line(tmp_path: Path, path: Path) -> None:
    folder = _folder(tmp_path, [(path, f"roots{path.suffix}"), *[(source, name) for source, name, _ in SAMPLE]])
    ran = here(folder, ["init", "--yes"])
    assert ran.code == 1, ran.text
    listed = {line.split()[0] for line in numbered(ran.err).values()}
    assert f"results/roots{path.suffix}" in listed and len(listed) == 3, ran.err
    lines = _import_lines(ran.err, "  next: ")
    assert len(lines) == 2 and not [w for w in lines if f"results/roots{path.suffix}" in w], ran.err


@pytest.mark.parametrize("names", [("old.jsonl", "new.jsonl"), ("old.jsonl", "new-plain.jsonl")])
def test_tf26_82_each_line_runs_once_its_capital_is_filled_in(tmp_path: Path, names: tuple[str, str]) -> None:
    from look_support import chdir, trace

    folder = _folder(tmp_path, [(WEAVE[name][0], name) for name in names])
    ran = here(folder, ["init", "--yes"])
    lines = _import_lines(ran.err, "  next: ")
    assert len(lines) == 2
    with chdir(folder):
        for words in lines:
            filled = [w if w != "OUTCOME" else "status" for w in words]
            done = trace(filled[1:])
            assert done.code == 0, done.text
    runs = [words[words.index("--run") + 1] for words in lines]
    for run in runs:
        assert sorted(columns(folder / "trace-store", run)) == list(CASES)
    # then init sets up over the store, as the refusal says
    after = here(folder, ["init", "--yes", "--force", "--store", "trace-store"])
    assert after.code == 0 and (folder / "trace.toml").is_file(), after.text


@pytest.mark.parametrize("name", ["page.json", "page.tsv"])
def test_tf26_82_the_lines_of_a_file_of_several_evaluations_run_too(tmp_path: Path, name: str) -> None:
    from look_support import chdir, trace

    folder = _folder(tmp_path, [(PAGE[name][0], name)])
    ran = here(folder, ["init", "--yes"])
    with chdir(folder):
        for words in _import_lines(ran.err, "  next: "):
            filled = [w if w != "OUTCOME" else "status" for w in words]
            done = trace(filled[1:])
            assert done.code == 0, done.text
    held = {EVALUATION[n]: (10 if n in ("baseline", "candidate") else 3) for n in NAMES}
    for evaluation, cases in held.items():
        assert len(columns(folder / "trace-store", evaluation)) == cases, evaluation


# ---------- TF26-83 ----------


def test_tf26_83_a_langsmith_feedback_list_stays_on_its_runs_line_beside_weave_s_files(tmp_path: Path) -> None:
    folder = found_folder(tmp_path, "runs+feedback")
    for source, name, _ in SAMPLE:
        shutil.copy(source, folder / "results" / f"wv-{name}")
    ran = here(folder, ["init", "--yes"])
    assert ran.code == 1, ran.text
    lines = _import_lines(ran.err, "  next: ")
    # two LangSmith runs, each with its feedback list beside it, and two Weave runs
    assert len(lines) == 4 and len(numbered(ran.err)) == 6, ran.err
    for run in ("old", "new"):
        words = next(w for w in lines if w[2] == "langsmith" and f"results/{run}.json" in w)
        assert words[3:5] == [f"results/{run}.json", f"results/{run}-feedback.json"], words
    assert sorted(w[3] for w in lines if w[2] == "weave") == ["results/wv-new.jsonl", "results/wv-old.jsonl"]


# ---------- TF26-84 ----------


def test_tf26_84_files_of_two_of_these_tools_are_refused_with_a_line_for_each(tmp_path: Path) -> None:
    files = [*SAMPLE, (BT / "api" / "slice-baseline.fetch.json", "bt-old.json", "record"), (BT / "ui" / "slice-candidate.csv", "bt-new.csv", "input")]
    folder = _folder(tmp_path, files)
    before = _tree(folder)
    ran = here(folder, ["init", "--yes"])
    assert ran.code == 1 and ran.out == "", ran.text
    error = next(line for line in ran.err.splitlines() if line.startswith("error: "))
    assert "2 tools" in error and "braintrust" in error and "weave" in error and "imported none" in error, error
    lines = _import_lines(ran.err, "  next: ")
    assert len(lines) == 4
    for _, name, case in files:
        words = next(w for w in lines if f"results/{name}" in w)
        assert words[2] == ("braintrust" if name.startswith("bt-") else "weave"), words
        assert words[words.index("--case-from") + 1] == case, words
    assert _tree(folder) == before
