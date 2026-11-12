"""What main prints, pinned for TF26 (the brief's rule 6): the corpus of invocations whose output
the Weave pair leaves byte for byte as main bfda500 prints it, the few it changes, and how each
is run. Not collected. ``fixtures/tf26/make_main_pins.py`` takes the pins with this module alone,
so it imports nothing the Weave reader brings.

The corpus is TF25's whole (TF24's, TF19's and TF18's inside it: every verb's plain and
``--json`` output on each kind of store, each option, the refusals, the earlier imports and
LangSmith's, the names, the saves, ``ui`` and ``report``), and beside it what main gained with
the Braintrust reader: its help under both spellings, its imports of each kind of export in text
and ``--json``, the verbs over two imported versions, its refusals, a pull through TF25's
transport, and ``init`` on the files it finds.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tf21_support import FIXTURES, INGEST

TF26 = FIXTURES / "tf26"
PINS = TF26 / "main-pins.json"
MAIN = "bfda500"
#: The readers main has, whose helps stay as main prints them.
EARLIER = ("deepeval", "ragas", "table", "junit", "promptfoo", "inspect", "openai-evals", "langsmith", "braintrust")
ABSENT = ["otel", "files/old.jsonl", "--store", "new-store", "--run", "x"]

_BT = ["--case-from", "input", "--outcome-from", "score:exact", "--cut", "0.5", "--below"]
_BY_ERROR = ["--case-from", "record", "--outcome-from", "error"]
_FETCH = {"old": "bt/api/slice-baseline.fetch.json", "new": "bt/api/slice-candidate.fetch.json"}


def _bt_import(run: str, store: str = "bst", *extra: str) -> list[str]:
    return ["import", "braintrust", _FETCH[run], "--store", store, "--run", run, *_BT, *extra]


def _bt_verbs() -> list[list[str]]:
    steps = [_bt_import("old"), _bt_import("new")]
    for verb in (["runs", "--store", "bst"], ["where", "new", "--store", "bst", "--event", "missed"],
                 ["compare", "old", "new", "--store", "bst", "--event", "missed", "--max-mde-hr", "1.5"],
                 ["fix-check", "old", "new", "--store", "bst", "--event", "missed", "--inputs", "all", "--max-mde", "0.5"],
                 ["changes", "old", "new", "--store", "bst", "--event", "missed"]):
        steps += [verb, [*verb, "--json"]]
    return steps


#: What main gained with the Braintrust reader, as it prints it: label to (where it runs, the
#: command, its steps). ``bt`` is TF13's workspace with the Braintrust captures copied in as
#: ``bt/``; ``bt-pull`` the same with the pull's seams replaced by TF25's transport.
BRAINTRUST: dict[str, tuple[str, str, list[list[str]]]] = {
    "help: import braintrust": ("work", "trace", [["import", "braintrust", "--help"]]),
    "help: alias braintrust": ("work", "import", [["braintrust", "--help"]]),
    "braintrust: import": ("bt", "trace", [_bt_import("old"), _bt_import("new"), _bt_import("new")]),
    "braintrust: import json": ("bt", "trace", [_bt_import("old", "bst", "--json"), _bt_import("new", "bst", "--json")]),
    "braintrust: import by error": ("bt", "trace", [
        ["import", "braintrust", "bt/api/slice-baseline.fetch.json", "--store", "bst", "--run", "old", *_BY_ERROR],
        ["import", "braintrust", "bt/api/slice-candidate.btql-summary.json", "--store", "bst", "--run", "new", *_BY_ERROR, "--json"]]),
    "braintrust: import the page's files": ("bt", "trace", [
        ["import", "braintrust", "bt/ui/slice-baseline.csv", "--store", "bst", "--run", "old", *_BT],
        ["import", "braintrust", "bt/ui/slice-candidate.json", "--store", "bst", "--run", "new", *_BT, "--json"]]),
    "braintrust: import the paged fetch": ("bt", "import", [
        ["braintrust", *[f"bt/api/slice-candidate.fetch.page-{n}.json" for n in (1, 2, 3, 4, 5)], "--store", "bst", "--run", "new", *_BT]]),
    "braintrust: the verbs": ("bt", "trace", _bt_verbs()),
    "braintrust: the verbs on the page's files": ("bt", "trace", [
        ["import", "braintrust", "bt/ui/slice-baseline.json", "--store", "bst", "--run", "old", *_BT],
        ["import", "braintrust", "bt/ui/slice-candidate.json", "--store", "bst", "--run", "new", *_BT],
        ["where", "new", "--store", "bst", "--event", "missed"],
        ["compare", "old", "new", "--store", "bst", "--event", "missed", "--max-mde-hr", "1.5"],
        ["fix-check", "old", "new", "--store", "bst", "--event", "missed", "--inputs", "all", "--max-mde", "0.5", "--json"]]),
    "braintrust: refusals": ("bt", "trace", [
        ["import", "braintrust", "files/results.json", "--store", "bst", "--run", "x", *_BY_ERROR],
        ["import", "braintrust", "bt/api/slice-baseline.fetch.json", "--store", "bst", "--run", "x", "--outcome-from", "error"],
        ["import", "braintrust", "bt/api/slice-baseline.fetch.json", "--store", "bst", "--run", "x", "--case-from", "input", "--outcome-from", "score:exact"],
        ["import", "braintrust", "bt/ui/slice-baseline.json", "--store", "bst", "--run", "x", *_BY_ERROR],
        ["import", "braintrust", "bt/ui/slice-baseline.json", "bt/ui/slice-baseline.csv", "--store", "bst", "--run", "x", *_BT, "--json"],
        ["import", "braintrust", "bt/ui", "--store", "bst", *_BT]]),
    "braintrust: a pull": ("bt-pull", "trace", [
        ["import", "braintrust", "braintrust:trace-fixture/slice-baseline", "--store", "bst", "--run", "old", *_BT],
        ["import", "braintrust", "braintrust:trace-fixture/slice-candidate", "--store", "bst", "--run", "new", *_BT, "--json"],
        ["import", "braintrust", "braintrust:trace-fixture/slice-candidate", "--store", "bst", "--run", "new", *_BT],
        ["import", "braintrust", "bst/.poisson/raw/braintrust/old", "--store", "bst", "--run", "again", *_BT],
        ["fix-check", "old", "new", "--store", "bst", "--event", "missed", "--inputs", "all", "--max-mde", "0.5"]]),
}

_INIT_STEPS = [["init", "--yes"], ["init", "--yes", "--no-import"]]
#: ``init`` on the files it finds, pinned from main as text: label to (what the folder holds,
#: the steps). BT-35 ruled this for the three API readers together; what main prints on
#: LangSmith's and Braintrust's files stays, and what it prints on Weave's is kept in words, to
#: say exactly what moves.
INIT: dict[str, tuple[str, list[list[str]]]] = {
    "init: langsmith runs": ("runs", _INIT_STEPS),
    "init: langsmith runs and feedback": ("runs+feedback", _INIT_STEPS),
    "init: langsmith csv": ("csv", _INIT_STEPS),
    "init: braintrust files": ("braintrust", _INIT_STEPS),
    "init: weave files": ("weave", _INIT_STEPS),
    "init: weave tables": ("weave-tables", _INIT_STEPS),
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
    "weave": (
        ("weave/api/trace-fixture-slice-baseline.jsonl", "old.jsonl"), ("weave/api/trace-fixture-slice-candidate.expanded.jsonl", "new.jsonl"),
        ("weave/ui/predict-and-score.json", "page.json"), ("weave/ui/traces-roots.jsonl", "roots.jsonl")),
    "weave-tables": (("weave/ui/predict-and-score.csv", "page.csv"), ("weave/ui/predict-and-score.tsv", "page.tsv"), ("weave/ui/traces-roots.csv", "roots.csv")),
}

#: The invocations whose output this pair changes, pinned from main as text to say exactly how:
#: the import's help gains the reader and its example; the refusal of a tool the install lacks
#: names one reader more; and ``weave`` itself stops being a tool the install lacks.
CHANGED: dict[str, tuple[str, str, list[list[str]]]] = {
    "help: import": ("work", "trace", [["import", "--help"]]),
    "import refusal: a tool not in this install": ("work", "import", [ABSENT, [*ABSENT, "--json"]]),
    "import refusal: weave": ("work", "import", [["weave", "files/old.jsonl", "--store", "new-store", "--run", "x"]]),
}


def pin_corpus() -> dict[str, tuple[str, str, list[list[str]]]]:
    """Every invocation whose plain and ``--json`` output this pair leaves as main prints it,
    piped (see the module's opening)."""
    from tf25_pins import pin_corpus as tf25_corpus

    out = dict(tf25_corpus())
    out.update(BRAINTRUST)
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
    workspace's path written ``<ROOT>``. ``bt`` is the workspace with the Braintrust captures
    copied in as ``bt/``; ``bt-pull`` the same with the pull answered by TF25's transport and
    no network; every other place is TF25's."""
    from tf25_pins import ran_case as tf25_ran

    if place not in ("bt", "bt-pull"):
        return tf25_ran(tmp, place, kind, steps)
    from tf13_support import workspace
    from tf19_support import normal, run_steps

    work = workspace(tmp)
    shutil.copytree(INGEST / "braintrust", work / "bt")
    env = {name: os.environ.pop(name) for name in ("BROWSER",) if name in os.environ}
    try:
        if place == "bt":
            return [(r.code, normal(r.out, work), normal(r.err, work)) for r in run_steps(work, "work", kind, [list(s) for s in steps])]
        from tf25_support import pulling

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
