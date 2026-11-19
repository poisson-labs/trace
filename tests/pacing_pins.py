"""What main prints, pinned for the pacing tests: the corpus of invocations whose output the
pacing fix leaves byte for byte as the pinned main prints it, and how each is run. Not
collected. ``fixtures/pacing/make_main_pins.py`` takes the pins with this module.

The corpus is TF26's whole (TF25's, TF24's, TF19's and TF18's inside it: every verb's plain and
``--json`` output on each kind of store, each option, the refusals, the earlier imports and
LangSmith's and Braintrust's, the names, the saves, ``ui`` and ``report``, the top help and the
bare options), TF26's three changed invocations and its ``init`` cases (all of them as main
prints them), and beside them what main gained with the Weave reader: its
help under both spellings, its imports of each kind of export in text and ``--json``, the verbs
over two imported versions, its refusals, and a pull through TF26's transport.

The pacing fix changes only the times written in a run's ``events.jsonl``, which no verb prints;
every one of these stays.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tf21_support import FIXTURES, INGEST

PACING = FIXTURES / "pacing"
PINS = PACING / "main-pins.json"
MAIN = "2ff191b"
#: The readers main has, each of whose helps stays as main prints it.
READERS = ("deepeval", "ragas", "table", "junit", "promptfoo", "inspect", "openai-evals", "langsmith", "braintrust", "weave")

_WV = ["--case-from", "example", "--outcome-from", "score:exact", "--cut", "0.5", "--below"]
_STATUS = ["--case-from", "example", "--outcome-from", "status"]
_PULL = {"old": "wv/api/trace-fixture-slice-baseline.jsonl", "new": "wv/api/trace-fixture-slice-candidate.jsonl"}
_ADDRESS = {"old": "weave:example-entity/trace-fixture/trace-fixture-slice-baseline",
            "new": "weave:example-entity/trace-fixture/trace-fixture-slice-candidate"}


def _wv_import(run: str, store: str = "wst", *extra: str) -> list[str]:
    return ["import", "weave", _PULL[run], "--store", store, "--run", run, *_WV, *extra]


def _wv_verbs() -> list[list[str]]:
    steps = [_wv_import("old"), _wv_import("new")]
    for verb in (["runs", "--store", "wst"], ["where", "new", "--store", "wst", "--event", "missed"],
                 ["compare", "old", "new", "--store", "wst", "--event", "missed", "--max-mde-hr", "1.5"],
                 ["fix-check", "old", "new", "--store", "wst", "--event", "missed", "--inputs", "all", "--max-mde", "0.5"],
                 ["changes", "old", "new", "--store", "wst", "--event", "missed"]):
        steps += [verb, [*verb, "--json"]]
    return steps


#: What main gained with the Weave reader, as it prints it: label to (where it runs, the
#: command, its steps). ``wv`` is TF13's workspace with the Weave captures copied in as ``wv/``;
#: ``wv-pull`` the same with the pull's seams replaced by TF26's transport.
WEAVE: dict[str, tuple[str, str, list[list[str]]]] = {
    "help: import weave": ("work", "trace", [["import", "weave", "--help"]]),
    "help: alias weave": ("work", "import", [["weave", "--help"]]),
    "weave: import": ("wv", "trace", [_wv_import("old"), _wv_import("new"), _wv_import("new")]),
    "weave: import json": ("wv", "trace", [_wv_import("old", "wst", "--json"), _wv_import("new", "wst", "--json")]),
    "weave: import by status": ("wv", "trace", [
        ["import", "weave", "wv/api/trace-fixture-slice-baseline.jsonl", "--store", "wst", "--run", "old", *_STATUS],
        ["import", "weave", "wv/api/trace-fixture-slice-candidate.expanded.jsonl", "--store", "wst", "--run", "new", *_STATUS, "--json"]]),
    "weave: import the page's files": ("wv", "trace", [
        ["import", "weave", "wv/ui/predict-and-score.json", "--store", "wst", "--run", "old",
         "--evaluation", "trace-fixture-slice-baseline", *_WV],
        ["import", "weave", "wv/ui/predict-and-score.csv", "--store", "wst", "--run", "new",
         "--evaluation", "trace-fixture-slice-candidate", "--case-from", "example:id", "--outcome-from", "score:exact",
         "--cut", "0.5", "--below", "--json"]]),
    "weave: import the paged pull": ("wv", "import", [
        ["weave", *[f"wv/api/trace-fixture-slice-candidate.page-{n}.jsonl" for n in (1, 2, 3, 4)], "--store", "wst", "--run", "new", *_WV]]),
    "weave: the verbs": ("wv", "trace", _wv_verbs()),
    "weave: refusals": ("wv", "trace", [
        ["import", "weave", "files/results.json", "--store", "wst", "--run", "x", *_STATUS],
        ["import", "weave", "wv/api/trace-fixture-slice-baseline.jsonl", "--store", "wst", "--run", "x", "--outcome-from", "status"],
        ["import", "weave", "wv/api/trace-fixture-slice-baseline.jsonl", "--store", "wst", "--run", "x", "--case-from", "example",
         "--outcome-from", "score:exact"],
        ["import", "weave", "wv/ui/predict-and-score.json", "--store", "wst", "--run", "x", *_WV],
        ["import", "weave", "wv/api/roots.jsonl", "--store", "wst", "--run", "x", *_WV, "--json"],
        ["import", "weave", "wv/ui", "--store", "wst", *_WV]]),
    "weave: a pull": ("wv-pull", "trace", [
        ["import", "weave", _ADDRESS["old"], "--store", "wst", "--run", "old", *_WV],
        ["import", "weave", _ADDRESS["new"], "--store", "wst", "--run", "new", *_WV, "--json"],
        ["import", "weave", _ADDRESS["new"], "--store", "wst", "--run", "new", *_WV],
        ["import", "weave", "wst/.poisson/raw/weave/old", "--store", "wst", "--run", "again", *_WV],
        ["fix-check", "old", "new", "--store", "wst", "--event", "missed", "--inputs", "all", "--max-mde", "0.5"]]),
}


def pin_corpus() -> dict[str, tuple[str, str, list[list[str]]]]:
    """Every invocation whose plain and ``--json`` output the pacing fix leaves as main prints
    it, piped (see the module's opening)."""
    from tf26_pins import CHANGED
    from tf26_pins import pin_corpus as tf26_corpus

    out = dict(tf26_corpus())
    out.update(CHANGED)
    out.update(WEAVE)
    return out


def init_corpus() -> dict[str, tuple[str, list[list[str]]]]:
    """``init`` on the files it finds, as TF26 ran it: label to (what the folder holds, steps)."""
    from tf26_pins import INIT

    return dict(INIT)


def pin_slow() -> frozenset[str]:
    from tf19_support import slow

    return slow()


def ran_case(tmp: Path, place: str, kind: str, steps: Sequence[Sequence[str]]) -> list[tuple[int, str, str]]:
    """A corpus case run in a workspace of its own: each step's exit code, stdout and stderr, the
    workspace's path written ``<ROOT>``. ``wv`` is the workspace with the Weave captures copied
    in as ``wv/``; ``wv-pull`` the same with the pull answered by TF26's transport and no
    network; every other place is TF26's."""
    from tf26_pins import ran_case as tf26_ran

    if place not in ("wv", "wv-pull"):
        return tf26_ran(tmp, place, kind, steps)
    from tf13_support import workspace
    from tf19_support import normal, run_steps

    work = workspace(tmp)
    shutil.copytree(INGEST / "weave", work / "wv")
    env = {name: os.environ.pop(name) for name in ("BROWSER",) if name in os.environ}
    try:
        if place == "wv":
            return [(r.code, normal(r.out, work), normal(r.err, work)) for r in run_steps(work, "work", kind, [list(s) for s in steps])]
        from tf26_support import pulling

        with pulling():
            return [(r.code, normal(r.out, work), normal(r.err, work)) for r in run_steps(work, "work", kind, [list(s) for s in steps])]
    finally:
        os.environ.update(env)


def ran_init(tmp: Path, holds: str, steps: Sequence[Sequence[str]]) -> list[tuple[int, str, str]]:
    from tf26_pins import ran_init as tf26_init

    return tf26_init(tmp, holds, steps)


def app_pins(work: Path) -> dict[str, str]:
    from tf26_pins import app_pins as tf26_app

    return tf26_app(work)


def digest_steps(got: Sequence[tuple[int, str, str]]) -> list[list[Any]]:
    from tf19_support import digest

    return [[code, digest(out), digest(err)] for code, out, err in got]
