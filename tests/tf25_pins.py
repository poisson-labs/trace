"""What main prints, pinned for TF25: the corpus of invocations whose output the Braintrust
reader leaves byte for byte as the pinned main prints it, the few it changes, and how each is
run. Not collected.

The corpus is TF24's whole (TF19's and TF18's inside it: every verb's plain and ``--json`` output
on each kind of store, each option, the refusals, the earlier imports, the names, the saves,
``ui`` and ``report``), and beside it what main gained with the LangSmith reader: its help
under both spellings, its imports of each kind of export in text and ``--json``, the verbs over
two imported versions and over two folders of trace files, its refusals, a pull through TF24's
transport, and ``init`` on the files it finds.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tf21_support import FIXTURES, INGEST

TF25 = FIXTURES / "tf25"
PINS = TF25 / "main-pins.json"
MAIN = "729a678"
#: The readers main has, whose helps stay as main prints them.
EARLIER = ("deepeval", "ragas", "table", "junit", "promptfoo", "inspect", "openai-evals", "langsmith")
ABSENT = ["otel", "files/old.jsonl", "--store", "new-store", "--run", "x"]

_LS = ["--case-from", "example", "--outcome-from", "feedback:exact", "--cut", "0.5", "--below"]
_BY_STATUS = ["--case-from", "metadata:ls_example_case", "--outcome-from", "status"]
_STARTED = {"old": "2026-11-09T20:38:00Z", "new": "2026-11-09T20:38:19Z"}
_VERSION = {"old": "baseline", "new": "candidate"}
_CSV = {"old": "ls/ui/trace-fixture-baseline-bbb64b8e.csv", "new": "ls/ui/trace-fixture-candidate-7e3f7200.csv"}


def _ls_import(run: str, store: str = "lst", *extra: str) -> list[str]:
    version = _VERSION[run]
    return ["import", "langsmith", f"ls/api/{version}.runs-v2.json", f"ls/api/{version}.feedback.json", "--store", store, "--run", run, *_LS, *extra]


def _ls_verbs() -> list[list[str]]:
    steps = [_ls_import("old"), _ls_import("new")]
    for verb in (["runs", "--store", "lst"], ["where", "new", "--store", "lst", "--event", "missed"],
                 ["compare", "old", "new", "--store", "lst", "--event", "missed", "--max-mde-hr", "1.5"],
                 ["fix-check", "old", "new", "--store", "lst", "--event", "missed", "--inputs", "all", "--max-mde", "0.5"],
                 ["changes", "old", "new", "--store", "lst", "--event", "missed"]):
        steps += [verb, [*verb, "--json"]]
    return steps


#: What main gained with the LangSmith reader, as it prints it: label to (where it runs, the
#: command, its steps). ``ls`` is TF13's workspace with the LangSmith captures copied in as
#: ``ls/``; ``ls-pull`` the same with the pull's seams replaced by TF24's transport.
LANGSMITH: dict[str, tuple[str, str, list[list[str]]]] = {
    "help: import langsmith": ("work", "trace", [["import", "langsmith", "--help"]]),
    "help: alias langsmith": ("work", "import", [["langsmith", "--help"]]),
    "langsmith: import": ("ls", "trace", [_ls_import("old"), _ls_import("new"), _ls_import("new")]),
    "langsmith: import json": ("ls", "trace", [_ls_import("old", "lst", "--json"), _ls_import("new", "lst", "--json")]),
    "langsmith: import by status": ("ls", "trace", [
        ["import", "langsmith", "ls/api/baseline.runs-v2.json", "--store", "lst", "--run", "old", *_BY_STATUS],
        ["import", "langsmith", "ls/api/candidate.runs-v1.json", "--store", "lst", "--run", "new", *_BY_STATUS, "--json"]]),
    "langsmith: import the page's csv": ("ls", "trace", [
        ["import", "langsmith", _CSV["old"], "--store", "lst", "--run", "old", *_LS, "--started", _STARTED["old"]],
        ["import", "langsmith", _CSV["new"], "--store", "lst", "--run", "new", *_LS, "--started", _STARTED["new"], "--json"]]),
    "langsmith: import a folder of trace files": ("ls", "trace", [
        ["import", "ls/cli/baseline-traces", "--store", "lst", *_BY_STATUS],
        ["import", "langsmith", "ls/cli/candidate-traces", "--store", "lst", *_BY_STATUS, "--json"]]),
    "langsmith: import the command's runs": ("ls", "import", [
        ["langsmith", "ls/cli/baseline-runs.jsonl", "--store", "lst", "--run", "old", *_BY_STATUS, "--select", "metadata:version=baseline"]]),
    "langsmith: the verbs": ("ls", "trace", _ls_verbs()),
    "langsmith: the verbs on folders": ("ls", "trace", [
        ["fix-check", "ls/cli/baseline-traces", "ls/cli/candidate-traces", "--event", "missed", "--inputs", "all", "--max-mde", "0.5", *_BY_STATUS],
        ["compare", "ls/cli/baseline-traces", "ls/cli/candidate-traces", "--event", "missed", "--max-mde-hr", "1.5", *_BY_STATUS, "--json"]]),
    "langsmith: refusals": ("ls", "trace", [
        ["import", "langsmith", "files/results.json", "--store", "lst", "--run", "x", *_BY_STATUS],
        ["import", "langsmith", "ls/api/baseline.runs-v2.json", "--store", "lst", "--run", "x", "--outcome-from", "status"],
        ["import", "langsmith", "ls/api/baseline.runs-v2.json", "--store", "lst", "--run", "x", "--case-from", "example", "--outcome-from", "feedback:exact"],
        ["import", "langsmith", "ls/api/baseline.feedback.json", "--store", "lst", "--run", "x", *_LS],
        ["import", "langsmith", "ls/cli/baseline-runs.jsonl", "--store", "lst", "--run", "x", "--case-from", "example", "--outcome-from", "status", "--json"]]),
    "langsmith: a pull": ("ls-pull", "trace", [
        ["import", "langsmith", "langsmith:trace-fixture-baseline-bbb64b8e", "--store", "lst", "--run", "old", *_LS],
        ["import", "langsmith", "langsmith:trace-fixture-candidate-7e3f7200", "--store", "lst", "--run", "new", *_LS, "--json"],
        ["import", "langsmith", "langsmith:trace-fixture-candidate-7e3f7200", "--store", "lst", "--run", "new", *_LS],
        ["import", "langsmith", "lst/.poisson/raw/langsmith/old", "--store", "lst", "--run", "again", *_LS],
        ["fix-check", "old", "new", "--store", "lst", "--event", "missed", "--inputs", "all", "--max-mde", "0.5"]]),
}

#: ``init`` on the files it finds, pinned from main as text: label to (what the folder holds,
#: the steps). TF25 holds one rule for the three API readers together, so
#: what main prints is kept in words, to say exactly what moves and what does not.
INIT: dict[str, tuple[str, list[list[str]]]] = {
    "init: langsmith runs": ("runs", [["init", "--yes"], ["init", "--yes", "--no-import"]]),
    "init: langsmith runs and feedback": ("runs+feedback", [["init", "--yes"], ["init", "--yes", "--no-import"]]),
    "init: langsmith csv": ("csv", [["init", "--yes"], ["init", "--yes", "--no-import"]]),
    "init: braintrust files": ("braintrust", [["init", "--yes"], ["init", "--yes", "--no-import"]]),
}

#: What a found-files folder holds under ``results/``, by its word in ``INIT``.
FOUND: dict[str, tuple[tuple[str, str], ...]] = {
    "runs": (("langsmith/api/baseline.runs-v2.json", "old.json"), ("langsmith/api/candidate.runs-v2.json", "new.json")),
    "runs+feedback": (
        ("langsmith/api/baseline.runs-v2.json", "old.json"), ("langsmith/api/baseline.feedback.json", "old-feedback.json"),
        ("langsmith/api/candidate.runs-v2.json", "new.json"), ("langsmith/api/candidate.feedback.json", "new-feedback.json")),
    "csv": (("langsmith/ui/trace-fixture-baseline-bbb64b8e.csv", "old.csv"), ("langsmith/ui/trace-fixture-candidate-7e3f7200.csv", "new.csv")),
    "braintrust": (
        ("braintrust/api/slice-baseline.fetch.json", "old.json"), ("braintrust/api/slice-candidate.fetch.json", "new.json"),
        ("braintrust/ui/slice-baseline.csv", "old-ui.csv"), ("braintrust/ui/slice-candidate.json", "new-ui.json")),
}

#: The invocations whose output this reader changes, pinned from main as text to say exactly how:
#: the import's help gains the reader and its example; the refusal of a tool the install lacks
#: names one reader more; and ``braintrust`` itself stops being a tool the install lacks.
CHANGED: dict[str, tuple[str, str, list[list[str]]]] = {
    "help: import": ("work", "trace", [["import", "--help"]]),
    "import refusal: a tool not in this install": ("work", "import", [ABSENT, [*ABSENT, "--json"]]),
    "import refusal: braintrust": ("work", "import", [["braintrust", "files/old.jsonl", "--store", "new-store", "--run", "x"]]),
}


def pin_corpus() -> dict[str, tuple[str, str, list[list[str]]]]:
    """Every invocation whose plain and ``--json`` output this reader leaves as main prints it,
    piped (see the module's opening)."""
    from tf24_support import pin_corpus as tf24_corpus

    out = dict(tf24_corpus())
    out.update(LANGSMITH)
    for label in CHANGED:
        out.pop(label, None)
    return out


def pin_slow() -> frozenset[str]:
    from tf19_support import slow

    return slow()


def found_folder(tmp: Path, holds: str) -> Path:
    """A folder of the test's own whose ``results/`` holds committed captures under plain
    names, each with its modification time set to one moment (a listing orders by it)."""
    folder = tmp / "work"
    (folder / "results").mkdir(parents=True)
    for i, (source, name) in enumerate(FOUND[holds]):
        shutil.copy(INGEST / source, folder / "results" / name)
        os.utime(folder / "results" / name, (1_794_000_000 + i, 1_794_000_000 + i))
    return folder


def ran_case(tmp: Path, place: str, kind: str, steps: Sequence[Sequence[str]]) -> list[tuple[int, str, str]]:
    """A corpus case run in a workspace of its own: each step's exit code, stdout and stderr, the
    workspace's path written ``<ROOT>``. ``work`` and the repository are TF24's places; ``ls``
    is the workspace with the LangSmith captures copied in as ``ls/``; ``ls-pull`` the same
    with the pull answered by TF24's transport and no network."""
    from tf24_support import ran_case as tf24_ran

    if place not in ("ls", "ls-pull"):
        return tf24_ran(tmp, place, kind, steps)
    from tf13_support import workspace
    from tf19_support import normal, run_steps

    work = workspace(tmp)
    shutil.copytree(INGEST / "langsmith", work / "ls")
    env = {name: os.environ.pop(name) for name in ("BROWSER",) if name in os.environ}
    try:
        if place == "ls":
            return [(r.code, normal(r.out, work), normal(r.err, work)) for r in run_steps(work, "work", kind, [list(s) for s in steps])]
        from tf24_support import pulling

        with pulling():
            return [(r.code, normal(r.out, work), normal(r.err, work)) for r in run_steps(work, "work", kind, [list(s) for s in steps])]
    finally:
        os.environ.update(env)


def ran_init(tmp: Path, holds: str, steps: Sequence[Sequence[str]]) -> list[tuple[int, str, str]]:
    """``init`` in a folder of found files, each step in a fresh copy of the folder: its exit
    code, stdout and stderr, the folder's path written ``<ROOT>``."""
    from tf2_support import here
    from tf19_support import normal

    out = []
    for i, step in enumerate(steps):
        folder = found_folder(tmp / f"step{i}", holds)
        ran = here(folder, list(step))
        out.append((ran.code, normal(ran.out, folder), normal(ran.err, folder)))
    return out


def app_pins(work: Path) -> dict[str, str]:
    from tf24_support import app_pins as tf24_app

    return tf24_app(work)


def digest_steps(got: Sequence[tuple[int, str, str]]) -> list[list[Any]]:
    from tf19_support import digest

    return [[code, digest(out), digest(err)] for code, out, err in got]
