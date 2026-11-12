"""TF26-86: the terminal app's list of found files follows ``init``'s lines (B-4, ruled yes by
Taylor on 2026-11-12).

The app's imports screen lists the files ``init`` finds and has not imported, each with the
import line ``init`` prints for it (``core.found_results``, TF19-A7). The list was built by
pairing every found file with one line, which fails where a file has no line of its own or more
than one. Held here on three folders:

- a Weave file that holds no case (the Traces page with no filter) beside an evaluation: ``init``
  lists it and prints no line for it (TF26-82), so it is not in the app's list;
- a Weave file that holds several evaluations: ``init`` prints a line for each, naming it with
  ``--evaluation``, so the file is in the app's list once for each;
- a LangSmith feedback list beside its runs: it goes on its runs' line (TF26-83), so the runs'
  file is in the list once, with that line, and the feedback list is not.

For each, the core's list is ``init``'s lines, line for line and in ``init``'s order, and the
imports screen of the app opens over the folder and shows a row for each entry of that list
and no other.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tf1_support import shell_words
from tf2_support import here, work
from tf19_support import drive
from tf21_support import INGEST
from tf26_support import EVALUATION, by_status, export, imported

WV = INGEST / "weave"
LS = INGEST / "langsmith"

#: Each folder: the files under ``results/`` (source, name), then the path of each entry of the
#: list, in ``init``'s order.
FOLDERS: dict[str, tuple[tuple[tuple[Path, str], ...], tuple[str, ...]]] = {
    "a Weave file with no case": (
        ((WV / "api" / "roots.jsonl", "roots.jsonl"), (WV / "api" / "trace-fixture-slice-baseline.jsonl", "old.jsonl")),
        ("results/old.jsonl",),
    ),
    "a Weave file of several evaluations": (
        ((WV / "ui" / "predict-and-score.json", "page.json"),),
        ("results/page.json",) * 4,
    ),
    "a LangSmith feedback list beside its runs": (
        ((LS / "api" / "baseline.runs-v2.json", "old.json"), (LS / "api" / "baseline.feedback.json", "old-feedback.json")),
        ("results/old.json",),
    ),
}


def _folder(tmp: Path, label: str) -> Path:
    folder = work(tmp)
    (folder / "results").mkdir()
    for source, name in FOLDERS[label][0]:
        shutil.copy(source, folder / "results" / name)
    return folder


def _init_lines(folder: Path) -> list[list[str]]:
    """The import lines ``init`` prints under its refusal, each as its words."""
    ran = here(folder, ["init", "--yes"])
    assert ran.code == 1 and ran.out == "", ran.text
    prefix = "  next: "
    return [shell_words(line[len(prefix):].strip()) for line in ran.err.splitlines()
            if line.startswith(prefix) and line[len(prefix):].strip().startswith("poisson-trace import ") and "--help" not in line]


@pytest.mark.parametrize("label", sorted(FOLDERS))
def test_tf26_86_the_app_s_found_files_are_init_s_lines(tmp_path: Path, label: str) -> None:
    from poisson_trace import core

    folder = _folder(tmp_path, label)
    paths = list(FOLDERS[label][1])
    lines = _init_lines(folder)
    assert [words[3] for words in lines] == paths, lines

    found = core.found_results(folder)
    assert [f.path for f in found] == paths
    assert [shell_words(f.command) for f in found] == lines
    assert all(not f.imported for f in found)
    for f in found:
        assert f.fill == tuple(w for w in f.command.split() if w.isupper() and w.isalpha()) and f.fill, f

    if label == "a Weave file of several evaluations":
        named = [words[words.index("--evaluation") + 1] for words in lines]
        assert sorted(named) == sorted(EVALUATION.values()), named
        runs = [words[words.index("--run") + 1] for words in lines]
        assert len(set(runs)) == len(runs), runs
    elif label == "a Weave file with no case":
        assert all("roots.jsonl" not in f.command for f in found)
    else:
        assert "results/old-feedback.json" in shell_words(found[0].command), found[0].command

    # the screen itself: a store beside the files, written from a file that is not among them
    imported(by_status(export("candidate", "plain"), folder / "trace-store", "held"))
    listed = core.found_results(folder)
    assert [(f.path, f.command) for f in listed] == [(f.path, f.command) for f in found]
    s = drive(folder, ["i"], size=(160, 50), store="trace-store")
    shown = s.last
    assert s.code is None and shown.title() == "imports", shown.text()
    rows = [r[2:].split()[0] for r in shown.body if r[2:].startswith("results/")]
    assert rows == paths, shown.text()
    assert any("found by init, not imported: enter runs the line after a question" in r for r in shown.body), shown.text()
