"""What main prints, pinned for TF5: the corpus of invocations whose output TF5 leaves byte
for byte as the pinned main (``MAIN``) prints it, the few it changes, and how each is run. Not
collected. ``fixtures/docs/make_main_pins.py`` takes the pins with this module alone.

The corpus is TF26's whole (TF25's, TF24's, TF19's and TF18's inside it: every verb's plain and
``--json`` output on each kind of store, each option, the refusals, the earlier imports,
LangSmith's and Braintrust's, the names, the saves, ``ui`` and ``report``), the three cases TF26
changed and main now prints (the import's help, the refusal of a tool the install lacks), and
beside it what main gained with the Weave reader: its help under both spellings, its imports of
each kind of export in text and ``--json``, the verbs over two imported versions, its refusals,
a pull through TF26's transport, and ``init`` on the files it finds.

TF5 changes four things a command prints: three in a help, one in a refusal. The store folder
the help examples name: ``proofload-runs`` was Prove's default store before it was published;
the published Prove's is ``prove-runs``. ``CHANGED`` holds the eight helps that carry such an
example, pinned as text: each must be main's with that one word replaced and nothing else. And,
in the top help alone, the one sentence that lists the tools whose files the import reads:
main's names four of the ten (``TOP_LIST``), and help must agree with the pages, so that
sentence names all ten in the one order, and the paragraph it stands in is wrapped again. In
the top help's first sentence: main's says Trace reads the runs Prove has stored and no more
(``TOP_SENTENCE``); it says Trace reads Prove's runs and the results the other ten tools
wrote, the rest of that paragraph is main's, wrapped again, and every other paragraph of the
top help is main's. And the refusal of the bare command: main's lists the verbs in an order of
its own (``NO_VERB_MAIN``); it lists them in the top help's (``NO_VERB``), in each of the nine
invocations that print it (``NO_VERB_CASES``). The refusal of a word that is no verb lists
them from the same list, so it moves the same way (``NOT_A_VERB``, the one case ``verb:
unknown``): the build keeps one list.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from signals_support import FIXTURES, INGEST

DOCS_FIXTURES = FIXTURES / "docs"
PINS = DOCS_FIXTURES / "main-pins.json"
MAIN = "a688e14"
#: The ten tools main reads beside Prove's own stores, in the order every listing gives them.
TOOLS = ("deepeval", "ragas", "table", "junit", "promptfoo", "inspect", "openai-evals", "langsmith", "braintrust", "weave")
ABSENT = ["otel", "files/old.jsonl", "--store", "new-store", "--run", "x"]
OLD_STORE, NEW_STORE = "proofload-runs", "prove-runs"

_WV = ["--case-from", "example", "--outcome-from", "score:exact", "--cut", "0.5", "--below"]
_BY_STATUS = ["--case-from", "example", "--outcome-from", "status"]
_API = {"old": "wv/api/trace-fixture-slice-baseline.jsonl", "new": "wv/api/trace-fixture-slice-candidate.jsonl"}
_EVAL = {"old": "trace-fixture-slice-baseline", "new": "trace-fixture-slice-candidate"}
_ENTITY = "example-entity/trace-fixture"


def _wv_import(run: str, store: str = "wst", *extra: str) -> list[str]:
    return ["import", "weave", _API[run], "--store", store, "--run", run, *_WV, *extra]


def _wv_page(run: str, file: str, *extra: str, case: str = "example") -> list[str]:
    return ["import", "weave", f"wv/ui/{file}", "--store", "wst", "--run", run, "--evaluation", _EVAL[run],
            "--case-from", case, "--outcome-from", "score:exact", "--cut", "0.5", "--below", *extra]


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
    "help: import": ("work", "trace", [["import", "--help"]]),
    "import refusal: a tool not in this install": ("work", "import", [ABSENT, [*ABSENT, "--json"]]),
    "weave: import": ("wv", "trace", [_wv_import("old"), _wv_import("new"), _wv_import("new")]),
    "weave: import json": ("wv", "trace", [_wv_import("old", "wst", "--json"), _wv_import("new", "wst", "--json")]),
    "weave: import by status": ("wv", "trace", [
        ["import", "weave", _API["old"], "--store", "wst", "--run", "old", *_BY_STATUS],
        ["import", "weave", "wv/api/trace-fixture-slice-candidate.expanded.jsonl", "--store", "wst", "--run", "new", *_BY_STATUS, "--json"]]),
    "weave: import the page's files": ("wv", "trace", [
        _wv_page("old", "predict-and-score.json"),
        _wv_page("new", "predict-and-score.csv", "--json", case="example:id")]),
    "weave: import the paged answer": ("wv", "import", [
        ["weave", *[f"wv/api/trace-fixture-slice-candidate.page-{n}.jsonl" for n in (1, 2, 3, 4)], "--store", "wst", "--run", "new", *_WV]]),
    "weave: the verbs": ("wv", "trace", _wv_verbs()),
    "weave: the verbs on the page's files": ("wv", "trace", [
        _wv_page("old", "predict-and-score.jsonl"),
        _wv_page("new", "predict-and-score.tsv", case="example:id"),
        ["where", "new", "--store", "wst", "--event", "missed"],
        ["compare", "old", "new", "--store", "wst", "--event", "missed", "--max-mde-hr", "1.5"],
        ["fix-check", "old", "new", "--store", "wst", "--event", "missed", "--inputs", "all", "--max-mde", "0.5", "--json"]]),
    "weave: refusals": ("wv", "trace", [
        ["import", "weave", "files/results.json", "--store", "wst", "--run", "x", *_BY_STATUS],
        ["import", "weave", _API["old"], "--store", "wst", "--run", "x", "--outcome-from", "status"],
        ["import", "weave", _API["old"], "--store", "wst", "--run", "x", "--case-from", "example", "--outcome-from", "score:exact"],
        ["import", "weave", "wv/ui/predict-and-score.json", "--store", "wst", "--run", "x", *_WV],
        ["import", "weave", "wv/ui/traces-roots.jsonl", "--store", "wst", "--run", "x", *_WV, "--json"],
        ["import", "weave", "wv/api/trace-fixture-slice-candidate.plain.jsonl", "--store", "wst", "--run", "x", "--case-from", "input", "--outcome-from", "status"],
        ["import", "weave", "wv/ui", "--store", "wst", *_WV]]),
    "weave: a pull": ("wv-pull", "trace", [
        ["import", "weave", f"weave:{_ENTITY}/{_EVAL['old']}", "--store", "wst", "--run", "old", *_WV],
        ["import", "weave", f"weave:{_ENTITY}/{_EVAL['new']}", "--store", "wst", "--run", "new", *_WV, "--json"],
        ["import", "weave", f"weave:{_ENTITY}/{_EVAL['new']}", "--store", "wst", "--run", "new", *_WV],
        ["import", "weave", "wst/.poisson/raw/weave/old", "--store", "wst", "--run", "again", *_WV],
        ["fix-check", "old", "new", "--store", "wst", "--event", "missed", "--inputs", "all", "--max-mde", "0.5"]]),
}

#: ``init`` on the files it finds, pinned from main as text and left as main prints it: TF26's
#: six folders (LangSmith's, Braintrust's and Weave's files, each refused with its import lines).
_INIT_STEPS = [["init", "--yes"], ["init", "--yes", "--no-import"]]
INIT: dict[str, tuple[str, list[list[str]]]] = {
    "init: langsmith runs": ("runs", _INIT_STEPS),
    "init: langsmith runs and feedback": ("runs+feedback", _INIT_STEPS),
    "init: langsmith csv": ("csv", _INIT_STEPS),
    "init: braintrust files": ("braintrust", _INIT_STEPS),
    "init: weave files": ("weave", _INIT_STEPS),
    "init: weave tables": ("weave-tables", _INIT_STEPS),
}

#: One committed file of each of the ten tools, under the plain name it gets in a folder
#: ``init`` searches: (the tool, the fixture under ``ingest/``, the name; a ``.gz`` is unpacked).
EVERY_TOOL: tuple[tuple[str, str, str], ...] = (
    ("deepeval", "deepeval/humaneval-a.json.gz", "test_run_20260905_185407.json"),
    ("ragas", "ragas/rag-base.jsonl", "rag-base.jsonl"),
    ("table", "table/humaneval-a.csv", "humaneval-a.csv"),
    ("junit", "junit/humaneval-a.xml", "humaneval-a.xml"),
    ("promptfoo", "promptfoo/results.json", "promptfoo-results.json"),
    ("inspect", "inspect/2026-10-07T04-23-47-00-00_trace-fixture_CV3jq8f7FTjwkaYb3zj3m2.eval", "inspect-log.eval"),
    ("openai-evals", "openai-evals/old.jsonl", "oaieval-old.jsonl"),
    ("langsmith", "langsmith/api/baseline.runs-v2.json", "langsmith-old.json"),
    ("braintrust", "braintrust/api/slice-baseline.fetch.json", "braintrust-old.json"),
    ("weave", "weave/api/trace-fixture-slice-baseline.jsonl", "weave-old.jsonl"),
)
EVERY_LABEL = "init: a file of every tool"

#: The eight helps whose examples name the store folder, pinned from main as text: the top
#: help and the seven verbs' whose examples read a Prove store.
CHANGED: dict[str, tuple[str, str, list[list[str]]]] = {
    "help: top": ("work", "trace", [["--help"]]),
    **{f"help: {verb}": ("work", "trace", [[verb, "--help"]]) for verb in ("init", "runs", "name", "where", "compare", "fix-check", "changes")},
}

#: The facts the lists of readers are checked against, pinned from main as text: ``doctor``'s
#: readers line, the import's help and the refusal of a tool the install lacks.
READERS_SAID: dict[str, tuple[str, str, list[list[str]]]] = {
    "doctor": ("work", "trace", [["doctor", "--config", "conf/trace.toml"]]),
    "help: import": WEAVE["help: import"],
    "import refusal": ("work", "import", [ABSENT]),
}


_INIT_STORE = ["init", "--yes", "--store", "store", "--event", "violated"]
#: The two verbs no earlier series pinned whole, because what they print names the machine:
#: ``doctor`` (its Python and where the package was imported from) and ``init`` on a store.
#: Pinned as text, the machine's own words written ``<PYTHON>`` and ``<PACKAGE>`` (``machine``).
SETUP: dict[str, tuple[str, str, list[list[str]]]] = {
    "doctor: a config": ("work", "trace", [["doctor", "--config", "conf/trace.toml"], ["doctor", "--config", "conf/trace.toml", "--json"]]),
    "doctor: no config": ("work", "trace", [["doctor"], ["doctor", "--json"]]),
    "doctor: setup": ("work", "trace", [["doctor", "--setup", "--config", "conf/trace.toml"], ["doctor", "--setup", "--config", "conf/trace.toml", "--json"]]),
    "init: a store": ("work", "trace", [_INIT_STORE, ["doctor"], ["runs"], _INIT_STORE, [*_INIT_STORE, "--force", "--json"]]),
    "init: a store, json first": ("work", "trace", [[*_INIT_STORE, "--json"], ["doctor", "--json"]]),
    "init: the agent's files": ("work", "trace", [["init", "--agent"], ["init", "--agent"], ["init", "--agent", "--force"]]),
}
#: ``init --agent --print`` prints the setup skill, whose list of the readers TF5 makes
#: whole: pinned as text, every other line main's.
SKILL: tuple[str, str, list[list[str]]] = ("work", "trace", [["init", "--agent", "--print"]])
SKILL_STEP = "1. **The results already on disk.**"


def machine(text: str) -> str:
    """A ``doctor`` or ``init`` output with what names the machine written out: the Python's
    path and version, and where the package was imported from with the note an editable
    install adds; in the report and in ``--json`` alike."""
    import re

    text = re.sub(r"(?m)^(  python +).*$", r"\1<PYTHON>", text)
    text = re.sub(r"(?m)^(  package +poisson-trace \S+ at ).*$", r"\1<PACKAGE>", text)
    text = re.sub(r'("name": "python",\s*"ok": \w+,\s*"line": ")[^"]*"', r'\1<PYTHON>"', text)
    text = re.sub(r'("name": "package",\s*"ok": \w+,\s*"line": "poisson-trace \S+ at )[^"]*"', r'\1<PACKAGE>"', text)
    return re.sub(r"Python \d+\.\d+\.\d+", "Python <VERSION>", text)


def pin_corpus() -> dict[str, tuple[str, str, list[list[str]]]]:
    """Every invocation whose plain and ``--json`` output TF5 leaves as main prints it,
    piped (see the module's opening)."""
    from weave_pins import pin_corpus as tf26_corpus

    out = dict(tf26_corpus())
    out.update(WEAVE)
    for label in CHANGED:
        out.pop(label, None)
    return out


def pin_slow() -> frozenset[str]:
    from app_support import slow

    return slow()


def ran_case(tmp: Path, place: str, kind: str, steps: Sequence[Sequence[str]]) -> list[tuple[int, str, str]]:
    """A corpus case run in a workspace of its own: each step's exit code, stdout and stderr, the
    workspace's path written ``<ROOT>``. ``wv`` is the workspace with the Weave captures copied
    in as ``wv/``; ``wv-pull`` the same with the pull answered by TF26's transport and no
    network; every other place is TF26's."""
    from weave_pins import ran_case as tf26_ran

    if place not in ("wv", "wv-pull"):
        return tf26_ran(tmp, place, kind, steps)
    from api_support import workspace
    from app_support import normal, run_steps

    work = workspace(tmp)
    shutil.copytree(INGEST / "weave", work / "wv")
    env = {name: os.environ.pop(name) for name in ("BROWSER",) if name in os.environ}
    try:
        if place == "wv":
            return [(r.code, normal(r.out, work), normal(r.err, work)) for r in run_steps(work, "work", kind, [list(s) for s in steps])]
        from weave_support import pulling

        with pulling():
            return [(r.code, normal(r.out, work), normal(r.err, work)) for r in run_steps(work, "work", kind, [list(s) for s in steps])]
    finally:
        os.environ.update(env)


def ran_init(tmp: Path, holds: str, steps: Sequence[Sequence[str]]) -> list[tuple[int, str, str]]:
    from weave_pins import ran_init as tf26_init

    return tf26_init(tmp, holds, steps)


def every_tool_folder(tmp: Path) -> Path:
    """A folder whose ``results/`` holds one committed file of each of the ten tools, each with
    its modification time set to one moment (a listing orders by it)."""
    import gzip

    folder = tmp / "work"
    (folder / "results").mkdir(parents=True)
    for i, (_, source, name) in enumerate(EVERY_TOOL):
        data = (INGEST / source).read_bytes()
        (folder / "results" / name).write_bytes(gzip.decompress(data) if source.endswith(".gz") else data)
        os.utime(folder / "results" / name, (1_794_000_000 + i, 1_794_000_000 + i))
    return folder


def ran_every_tool(tmp: Path) -> list[tuple[int, str, str]]:
    """``init --yes --no-import`` in that folder: its exit code, stdout and stderr, the folder's
    path written ``<ROOT>``."""
    from setup_support import here
    from app_support import normal

    folder = every_tool_folder(tmp)
    ran = here(folder, ["init", "--yes", "--no-import"])
    return [(ran.code, normal(ran.out, folder), normal(ran.err, folder))]


def app_pins(work: Path) -> dict[str, str]:
    from langsmith_support import app_pins as tf24_app

    return tf24_app(work)


def digest_steps(got: Sequence[tuple[int, str, str]]) -> list[list[Any]]:
    from app_support import digest

    return [[code, digest(out), digest(err)] for code, out, err in got]


#: The top help's sentence that lists the tools, as main prints it, and the paragraph it opens.
TOP_LIST = "(DeepEval, Ragas, a table of results, JUnit reports)"
TOP_PARAGRAPH = "Results another tool wrote "


#: That paragraph whole, as main prints it.
TOP_MAIN = (
    "Results another tool wrote (DeepEval, Ragas, a table of results, JUnit reports) are read in\n"
    "with poisson-trace import. where, compare, fix-check and changes also take a folder in a run's\n"
    "place, when no stored run answers to the word: a run Prove stored, a store of one run, or one\n"
    "tool's result files, read with the flags poisson-trace import takes for that tool. Nothing is\n"
    "written; the folder's name is the run's name in the report.\n"
).rstrip("\n")


#: The top help's first paragraph, which every such paragraph opens with, and as main prints
#: it; its first sentence as main prints it, and the part of that sentence that stays.
TOP_FIRST = "Poisson Trace reads "
TOP_FIRST_MAIN = (
    "Poisson Trace reads the runs Prove has stored and says where in the workflow their episodes\n"
    "died, and whether a change made them fail less. A store is the folder Prove writes its runs\n"
    "into; a run is one stored sweep, and its episodes are its rows. Every number prints with what\n"
    "the runs could not have detected.\n"
).rstrip("\n")
TOP_SAYS = "says where in the workflow their episodes died, and whether a change made them fail less."
TOP_SENTENCE = "Poisson Trace reads the runs Prove has stored and " + TOP_SAYS

#: The refusal of the bare command: as main prints it, and with the verbs in the top help's
#: order; and the nine invocations of the corpus that print it.
_NO_VERB = "error: no verb was given; the verbs are "
VERBS_MAIN = "init, runs, name, where, compare, fix-check, changes, handover, import, doctor, ui and report"
VERBS_SAID = "init, runs, name, where, compare, fix-check, changes, import, doctor, handover, ui and report"
NO_VERB_MAIN = _NO_VERB + VERBS_MAIN
NO_VERB = _NO_VERB + VERBS_SAID
#: The refusal of a word that is no verb, which names the word and lists the verbs the same
#: way, and the one invocation of the corpus that prints it.
NOT_A_VERB = " is not a verb; the verbs are "
NOT_A_VERB_CASES = ("verb: unknown",)
NO_VERB_NEXT = "  next: poisson-trace --help"
NO_VERB_CASES = ("verb: none", "bare: plain", "bare: json", "bare: debug", "bare: config=", "bare: config", "bare: store", "bare: both",
                 "bare: plain config")


def as_main_printed(label: str, text: str) -> str:
    """What TF5 leaves changed, written back as the pinned main printed it: in a help the
    examples' store folder, and in the top help the paragraph that lists the tools and the
    first paragraph; in the nine invocations of the bare command and the one of a word that
    is no verb, the refusal's list of verbs.
    For the earlier series' pins, which go on holding every other byte through this; TF5-3
    holds the changes themselves. Any other invocation's text is returned as it is."""
    if label in NO_VERB_CASES:
        return text.replace(NO_VERB, NO_VERB_MAIN)
    if label in NOT_A_VERB_CASES:
        return text.replace(NOT_A_VERB + VERBS_SAID, NOT_A_VERB + VERBS_MAIN)
    if not label.startswith("help") and "help" not in label.split():
        return text
    paragraphs = text.replace(NEW_STORE, OLD_STORE).split("\n\n")
    main = {TOP_PARAGRAPH: TOP_MAIN, TOP_FIRST: TOP_FIRST_MAIN}
    return "\n\n".join(next((whole for opening, whole in main.items() if paragraph.startswith(opening)), paragraph) for paragraph in paragraphs)


def renamed(text: str) -> str:
    """Main's text with the examples' store folder renamed: the one change TF5 makes to what a
    command prints."""
    return text.replace(OLD_STORE, NEW_STORE)
