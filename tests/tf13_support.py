"""Shared helpers for TF13's tests: the one core and the Python API (spec sections 11.8, 17.2,
17.3 and 18, the step 17 rows of 18.7.2, and RF2: the API's ``check`` waits for the pull-request
check, TF7).

Not a test module and not collected.

The API as these tests read it. The readings the spec leaves open are put to Taylor in
``log/trace-tf13-a/rulings.md``, PA1 on; each test file's opening says which it holds.

The modules.
- ``poisson_trace.api`` is the public surface: ``api.__all__`` names exactly the functions in
  ``FUNCTIONS`` below, the three types ``Refusal``, ``Store`` and ``Config``, and the class of
  every object a public function returns (``RESULT_TYPES`` lists the names the tests expect;
  each is ``api.<name>``). The work may live in ``poisson_trace/core.py``, the "one core" step 17
  names, behind ``api``; nothing here reads ``core`` but the rule that follows TR40 (TF13-31).
- ``poisson_trace.commands`` holds the two verbs that touch the environment rather than a store,
  ``init`` and ``doctor`` (``report`` and ``upload`` are not on main). It is not public.
- The command lines are ``poisson_trace/cli.py``, ``poisson_trace/ingest/cli.py`` and
  ``poisson_trace/__main__.py``. Each exposes its parsers as ``parsers()``: ``cli.parsers()``
  gives ``(top, {verb: parser})`` and ``ingest.cli.parsers()`` gives what it gives today.

The functions and their signatures (PA1, PA4, PA10).
- ``where(store, run, *, ...)``, ``compare(store, a, b, *, ...)``, ``fix_check(store, old, new,
  *, ...)``, ``changes(store, a, b, *, ...)``, ``runs(store, *, ...)``: the first parameter is
  ``store`` (what ``--store`` takes: a path, a name the config names, an ``api.Store``, or None
  for the config's own store or runs read from folders); then the verb's positionals by the
  parser's names; then every option of the verb's parser as a keyword-only parameter named for
  its flag with the dashes dropped and the inner ones as underscores, defaulting to what the
  parser gives when the flag is absent (a list default may be a tuple). Not parameters: what
  shapes the printing (``--help``, ``--json``, ``--plain``, ``--debug``, ``--version``) and what
  delivers a result (``--svg``, ``--save``, ``--out``, ``--force`` on the four counting verbs),
  which are the result's methods and ``api.save``. A keyword passed is a flag given: the saved
  verdict's ``settings.from`` says ``flag`` for it, whatever its value, and ``default`` for one
  left out, as the command line records a flag typed and one not (SV5); the command line passes
  only the flags typed. The four counting verbs also take
  ``**reader_flags``: the reader's flags for runs given as folders (TF22, FI8).
- ``config`` (``--config``) takes the path given to ``--config`` or an ``api.Config``; with
  None the API reads no config at all. The command line finds the current folder's
  ``trace.toml`` itself, and passes it in.
- ``import_run(store, tool, files, *, run=None, started=None, verdicts=None, config=None,
  **reader_flags)``: the import's command line, the reader's flags as keywords named by the
  same rule; ``tool`` may be None when ``files`` is one folder (FI1).
- ``name(store, run, new, *, config=None)`` is ``name RUN NEW``; ``forget_name(store, run, *,
  config=None)`` is ``name RUN --forget``; ``list_names(store, *, config=None)`` is
  ``name --list``.
- ``open_store(path)`` returns an ``api.Store``, which keeps the path it was given as ``path``;
  ``load_config(path)`` returns an ``api.Config``, whose
  ``store(name=None)`` is the path of the store it names (None: its unnamed ``[store]``).
- ``save(result)`` is ``--save``; ``load_bundle(folder)`` reads a bundle back;
  ``validate_bundle(folder)`` is ``handover --check DIR``.
- ``commands.init(*, ...)`` and ``commands.doctor(*, ...)``: every option of the verb's parser
  as a keyword (init's ``--import`` and ``--no-import`` set one setting, ``import_``), but the
  printing options. Read from the parser as it is when the test runs, so the setup agent's new
  flags (TF17) join without a change here.
- Not in 0.1.0's API: ``check`` (TF7, RF2), ``build_pages`` and ``to_html`` (TF18, PA5).

The values (PA7).
- Each keyword takes the value the verb's parser gives for its flag: numbers as numbers, a
  repeatable flag as a list or tuple, ``--max-change`` as ``(measure, share)`` pairs.
- A value the parser itself would refuse (not of the option's type, not among its choices) is a
  ``ValueError``. Every refusal after the command line is read is an ``api.Refusal`` carrying
  the sentence the command line prints after ``error: `` (``message``, also ``str(e)``), the
  commands under it (``next``, a tuple, each printed as ``  next: <command>``), the exit code
  (``exit_code``: 1, 2 or 3) and the ``note:`` sentences printed before it (``notes``). Its
  constructor is ``Refusal(message, *, next=(), exit_code=1, notes=())``.

The results (PA6, PA8, PA9, PA13).
- Frozen dataclasses. Every key of the verb's ``--json`` document is an attribute, and every key
  of the ``result.json`` its bundle holds (``summary``, ``before_you_act``, ``note`` as a list,
  ``versions``, and on the three verbs of two runs ``failure_taxonomy_diff`` and
  ``continuous_measures``), equal to it once read as JSON (``jsonable`` below); ``saved`` is None
  until saved. The four counting verbs' results also carry ``settings``, the artifact's
  ``settings`` (SV5) as ``--save`` records them.
- ``to_json()`` is the ``--json`` stdout byte for byte, its final newline included;
  ``to_markdown()`` is the plain stdout byte for byte, from the verdict line to the ``next:``
  line. ``exit_code`` is the command's exit code. ``notes`` holds, in order, the sentences the
  command prints on stderr as ``note: <sentence>``; the CLI prints them.
- ``save(r)``, ``r.to_bundle(folder, force=False)`` (``--out``, which also saves) and, for
  ``where``, ``r.write_svg(path, force=False)`` (``--svg``) each return a result of the same
  type whose ``to_json()`` and ``to_markdown()`` are what the command line prints with those
  options; ``r.to_svg()`` is the text ``--svg`` writes.
- A result keeps working wherever the process goes next: its attributes and its methods give
  the same after the current folder changes as before (a relative path is the one the call
  read; a folder given to ``to_bundle`` or ``write_svg`` is read where the process is then).

What the API never does (section 11.8). It prints nothing, reads no environment variable, reads
no file and lists no folder it was not given a path to, and writes only in ``to_bundle``,
``save``, ``import_run``, ``name``, ``forget_name`` and ``write_svg``; a folder it makes for its
own work is under the system's temporary folder and gone when it returns.
"""

from __future__ import annotations

import ast
import contextlib
import dataclasses
import hashlib
import importlib
import inspect
import io
import linecache
import os
import re
import shutil
import site
import sys
import sysconfig
import tempfile
from collections.abc import Callable, Iterator, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from conftest import FIXTURES
from tf0_support import Ran, chdir, trace, trace_import

REPO = Path(__file__).resolve().parent.parent
PACKAGE = REPO / "src" / "poisson_trace"
DOCS = REPO / "docs" / "python.md"
PROVE_013 = FIXTURES / "prove-stores" / "prove-0.1.3"
INGEST = FIXTURES / "ingest"

FUNCTIONS = (
    "open_store", "load_config", "where", "compare", "fix_check", "changes", "runs", "name",
    "forget_name", "list_names", "import_run", "save", "load_bundle", "validate_bundle",
)
TYPES = ("Refusal", "Store", "Config")
# the functions that may write, and nothing else (section 11.8 as amended; PA4)
WRITERS = ("import_run", "name", "forget_name", "save")
WRITING_METHODS = ("to_bundle", "write_svg")
# each verb of the main command and the function that is it
VERB_FUNCTION = {"where": "where", "compare": "compare", "fix-check": "fix_check",
                 "changes": "changes", "runs": "runs"}
COUNTING = ("where", "compare", "fix-check", "changes")
# what shapes the printing, never a parameter
PRINTING = frozenset({"-h", "--help", "--json", "--plain", "--debug", "--version"})
# what delivers a result: the result's methods and api.save (PA4)
DELIVERY = {"where": frozenset({"--svg", "--force", "--save", "--out"}),
            "compare": frozenset({"--save", "--out", "--force"}),
            "fix-check": frozenset({"--save", "--out", "--force"}),
            "changes": frozenset({"--save", "--out", "--force"}),
            "runs": frozenset()}
# the import's own options, the same for every reader
IMPORT_COMMON = ("--store", "--config", "--run", "--started", "--verdicts")
# the result classes the tests expect, by what returns them
RESULT_TYPES = {"where": "WhereResult", "compare": "CompareResult", "fix_check": "FixCheckResult",
                "changes": "ChangesResult", "runs": "RunsResult", "name": "NameResult",
                "import_run": "ImportResult", "load_bundle": "Bundle",
                "validate_bundle": "BundleCheck"}
SCHEMAS = {"where": "poisson-trace.where/1", "compare": "poisson-trace.compare/1",
           "fix_check": "poisson-trace.fix-check/2", "changes": "poisson-trace.changes/2",
           "runs": "poisson-trace.runs/1", "import_run": "poisson-trace.import/1"}
# the keys result.json adds to a verb's --json (TF6: SV3, SV4)
RESULT_JSON_ADDS = ("summary", "before_you_act", "note", "versions")
TWO_RUN_ADDS = ("failure_taxonomy_diff", "continuous_measures")


# ---------- the modules ----------


def api() -> Any:
    """``poisson_trace.api``, imported when a test runs, so that on a main without it each test
    fails on its own rather than the file failing to collect."""
    return importlib.import_module("poisson_trace.api")


def commands() -> Any:
    return importlib.import_module("poisson_trace.commands")


def cli_parsers() -> tuple[Any, dict[str, Any]]:
    from poisson_trace import cli

    top, verbs = cli.parsers()
    return top, dict(verbs)


def import_parsers() -> tuple[Any, dict[str, Any]]:
    from poisson_trace.ingest import cli as importer

    top, subs, _further = importer.parsers()
    return top, dict(subs)


# ---------- the naming rule (PA1) ----------


def keyword(action: Any) -> str:
    """The keyword a parser's option is: its longest flag, dashes dropped and the inner ones as
    underscores; the parser's own name for the setting when that is not a Python name (init's
    ``--import`` and ``--no-import``, both ``import_``)."""
    flag = max(action.option_strings, key=len)
    name = flag.lstrip("-").replace("-", "_")
    import keyword as kw

    if kw.iskeyword(name) or name != action.dest and action.dest.rstrip("_") == name.removeprefix("no_"):
        return str(action.dest)
    return name


def plain_default(value: Any) -> Any:
    """A default as the tests compare it: a list and a tuple of the same items are one."""
    if isinstance(value, (list, tuple)):
        return tuple(plain_default(v) for v in value)
    return value


def options_of(parser: Any, skip: frozenset[str] = frozenset()) -> list[Any]:
    """The parser's options that are parameters: not help, not a positional, not in ``skip``."""
    import argparse

    out = []
    for action in parser._actions:
        if isinstance(action, (argparse._HelpAction, argparse._SubParsersAction)):
            continue
        if not action.option_strings:
            continue
        if set(action.option_strings) & (PRINTING | skip):
            continue
        out.append(action)
    return out


def positionals_of(parser: Any) -> list[str]:
    import argparse

    return [a.dest for a in parser._actions
            if not a.option_strings and not isinstance(a, (argparse._HelpAction, argparse._SubParsersAction))]


def expected_keywords(parser: Any, skip: frozenset[str] = frozenset()) -> dict[str, Any]:
    """``{keyword: default}`` for the parser's options; one setting two flags set is one keyword,
    with the default the parser gives."""
    defaults = vars(parser.parse_known_args([*_required_positionals(parser)])[0])
    out: dict[str, Any] = {}
    for action in options_of(parser, skip):
        out[keyword(action)] = plain_default(defaults.get(action.dest, action.default))
    return out


def _required_positionals(parser: Any) -> list[str]:
    words = []
    for a in parser._actions:
        if not a.option_strings and a.required and a.nargs not in ("?", "*"):
            words += ["x"] * (1 if a.nargs in (None, 1) else 1)
    return words


def plain_signature(fn: Callable[..., Any], prefix: str = "api.") -> str:
    """A function's signature as ``docs/python.md`` writes it: its parameters with their
    defaults, no annotations."""
    parts: list[str] = []
    star = False
    for p in inspect.signature(fn).parameters.values():
        if p.kind is p.VAR_POSITIONAL:
            parts.append(f"*{p.name}")
            star = True
            continue
        if p.kind is p.VAR_KEYWORD:
            parts.append(f"**{p.name}")
            continue
        if p.kind is p.KEYWORD_ONLY and not star:
            parts.append("*")
            star = True
        parts.append(p.name if p.default is p.empty else f"{p.name}={p.default!r}")
    return f"{prefix}{fn.__name__}({', '.join(parts)})"


# ---------- values as JSON ----------


def jsonable(value: Any) -> Any:
    """An attribute's value as JSON reads it back: a mapping as a dict, a sequence as a list, a
    dataclass as the dict of its fields."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


# ---------- the workspace every test runs in ----------


STARTS = ("2026-11-01T10:00:00Z", "2026-11-02T10:00:00Z")
TABLE_OUTCOMES = {
    "old": {**{f"c{j}": "failed" if j % 3 == 0 else "passed" for j in range(12)}, "c12": ""},
    "new": {**{f"c{j}": "failed" if j % 4 == 0 else "passed" for j in range(12)}, "c12": "", "c13": ""},
}
CONFIG_TEXT = """\
version = 1

[store]
path = "../store"

[store.tables]
path = "../tables"

[events]
failed = ["violated", "timeout"]

[check]
max_mde = 0.2
max_mde_hr = 1.5
"""


def workspace(tmp: Path, name: str = "work") -> Path:
    """A folder of the test's own, read by relative paths from inside it:

    - ``store``: a copy of the committed Prove 0.1.3 store (runs ``agent before`` and
      ``agent after``, 160 tries each, every one traced);
    - ``tables``: two table imports, ``old`` and ``new``, twelve cases each and one or two
      with no outcome (as TF6's verdict tests build them);
    - ``broken``: the Prove store again, with a third run whose record cannot be read;
    - ``ties``: two table imports, ``zz-old`` and ``aa-new``, that started at the same moment;
    - ``grades.csv``: verdicts for the two unscored cases;
    - ``jstore``: two JUnit imports of the committed HumanEval reports, ``ja`` and ``jb``;
    - ``files/``: the committed result files the imports read, one of each reader's;
    - ``conf/trace.toml``: a config naming ``store`` (and ``tables`` as ``tables``), the
      failures ``violated`` and ``timeout``, and both ceilings.
    """
    work = tmp / name
    work.mkdir(parents=True)
    shutil.copytree(PROVE_013, work / "store")
    # the same store with a third run whose record Prove cannot read: latest, previous and the
    # listing say so in a note
    shutil.copytree(PROVE_013, work / "broken")
    shutil.copytree(PROVE_013 / "20261104T162926Z-b4d5", work / "broken" / "20261104T999999Z-dead")
    (work / "broken" / "20261104T999999Z-dead" / "manifest.json").write_text("{ not json", encoding="utf-8")
    files = work / "files"
    files.mkdir()
    for src in [INGEST / "junit" / "humaneval-a.xml", INGEST / "junit" / "humaneval-b.xml",
                INGEST / "junit" / "trace-suite-1.xml", INGEST / "junit" / "trace-suite-2.xml",
                INGEST / "ragas" / "rag-base.jsonl", INGEST / "ragas" / "rag-raft.jsonl",
                INGEST / "openai-evals" / "old.jsonl", INGEST / "openai-evals" / "new.jsonl",
                INGEST / "promptfoo" / "results.json",
                INGEST / "inspect" / "2026-10-07T04-23-51-00-00_trace-fixture_2nSEDuHHzKiTUjJW3kXknY.json",
                INGEST / "deepeval" / "humaneval-a.json.gz"]:
        shutil.copy2(src, files / src.name)
    (work / "conf").mkdir()
    (work / "conf" / "trace.toml").write_text(CONFIG_TEXT, encoding="utf-8")
    with chdir(work):
        for i, run in enumerate(("old", "new")):
            csv = Path(f"{run}.csv")
            csv.write_text("case,outcome\n" + "".join(f"{c},{o}\n" for c, o in TABLE_OUTCOMES[run].items()),
                           encoding="utf-8")
            made = trace_import(["table", str(csv), "--store", "tables", "--run", run, "--case-column", "case",
                                 "--outcome-column", "outcome", "--failed", "failed", "--started", STARTS[i]])
            assert made.code == 0, made.text
        for run in ("zz-old", "aa-new"):
            # two runs that started at the same moment: latest and previous cannot order them
            made = trace_import(["table", f"{'old' if run == 'zz-old' else 'new'}.csv", "--store", "ties", "--run", run,
                                 "--case-column", "case", "--outcome-column", "outcome", "--failed", "failed",
                                 "--started", STARTS[0]])
            assert made.code == 0, made.text
        Path("grades.csv").write_text("case,outcome\nc12,fail\nc13,pass\n", encoding="utf-8")
        Path("conf/no-match.csv").write_text("case,outcome\nno-such,fail\n", encoding="utf-8")
        Path("files/junit-folder").mkdir()
        shutil.copy2(Path("files/trace-suite-1.xml"), Path("files/junit-folder/trace-suite-1.xml"))
        for i, (run, file) in enumerate((("ja", "humaneval-a.xml"), ("jb", "humaneval-b.xml"))):
            made = trace_import(["junit", f"files/{file}", "--store", "jstore", "--run", run, "--started", STARTS[i]])
            assert made.code == 0, made.text
    return work


EV = ["--event", "violated", "--event", "timeout"]


# Each invocation the tests hold the API to, run from inside a workspace: the main command's
# words. The four counting verbs on each kind of store, the options each verb takes, runs, the
# import of each reader; those that read the larger store are marked slow where they stand.
VERBS_ARGV: dict[str, list[str]] = {
    "where": ["where", "agent after", "--store", "store", *EV, "--at", "3"],
    "where by step": ["where", "agent before", "--store", "store", *EV, "--by", "step", "--boot", "200", "--seed", "3"],
    "where untraced": ["where", "ja", "--store", "jstore", "--event", "missed"],
    "where by number": ["where", "#1", "--store", "store", *EV],
    "where latest": ["where", "latest", "--store", "store", *EV],
    "compare": ["compare", "agent before", "agent after", "--store", "store", *EV, "--max-mde-hr", "1.5"],
    "compare at": ["compare", "agent before", "agent after", "--store", "store", *EV, "--max-mde-hr", "2", "--at", "3", "--alpha", "0.1"],
    "compare previous latest": ["compare", "previous", "latest", "--store", "store", *EV, "--max-mde-hr", "1.5"],
    "fix-check": ["fix-check", "agent before", "agent after", "--store", "store", *EV, "--inputs", "all", "--max-mde", "0.2"],
    "fix-check measures": ["fix-check", "agent before", "agent after", "--store", "store", *EV, "--inputs", "all", "--max-mde", "0.2", "--measures"],
    "fix-check max-change": ["fix-check", "agent before", "agent after", "--store", "store", *EV, "--inputs", "all", "--max-mde", "0.2", "--max-change", "wall_time_s=10%"],
    "fix-check top": ["fix-check", "agent before", "agent after", "--store", "store", "--event", "violated", "--inputs", "all", "--max-mde", "0.3", "--top", "1", "--alpha", "0.1", "--seed", "5"],
    "fix-check tables": ["fix-check", "old", "new", "--store", "tables", "--event", "missed", "--inputs", "all", "--max-mde", "0.5"],
    "fix-check verdicts": ["fix-check", "old", "new", "--store", "tables", "--event", "missed", "--inputs", "all", "--max-mde", "0.5", "--verdicts", "grades.csv"],
    "fix-check junit": ["fix-check", "ja", "jb", "--store", "jstore", "--event", "missed", "--inputs", "all", "--max-mde", "0.1"],
    "changes": ["changes", "agent before", "agent after", "--store", "store", *EV],
    "changes top": ["changes", "agent before", "agent after", "--store", "store", *EV, "--top", "1", "--alpha", "0.2"],
    "changes verdicts": ["changes", "old", "new", "--store", "tables", "--event", "missed", "--verdicts", "grades.csv"],
    "runs": ["runs", "--store", "store", *EV],
    "where with a run Prove cannot read": ["where", "latest", "--store", "broken", *EV],
    "fix-check with a run Prove cannot read": ["fix-check", "previous", "latest", "--store", "broken", *EV, "--inputs", "all", "--max-mde", "0.2"],
    "runs with a run Prove cannot read": ["runs", "--store", "broken", *EV],
    "runs all": ["runs", "--store", "jstore", "--all", "--event", "missed"],
    "runs no event": ["runs", "--store", "tables"],
    "where config": ["where", "agent after", "--config", "conf/trace.toml"],
    "fix-check config": ["fix-check", "agent before", "agent after", "--config", "conf/trace.toml", "--inputs", "all"],
    "compare config": ["compare", "agent before", "agent after", "--config", "conf/trace.toml"],
    "changes config name": ["changes", "old", "new", "--config", "conf/trace.toml", "--store", "tables", "--event", "missed"],
}

# The import of each reader, from inside a workspace, into a new store.
IMPORT_ARGV: dict[str, list[str]] = {
    "junit": ["junit", "files/humaneval-a.xml", "--store", "new-store", "--run", "suite-a", "--started", STARTS[0]],
    "junit two files": ["junit", "files/trace-suite-1.xml", "files/trace-suite-2.xml", "--store", "new-store", "--run", "suites"],
    "ragas": ["ragas", "files/rag-base.jsonl", "--store", "new-store", "--run", "rag", "--metric", "faithfulness", "--cut", "0.5", "--below", "--case-column", "case", "--started", STARTS[0]],
    "table": ["table", "old.csv", "--store", "new-store", "--run", "t", "--case-column", "case", "--outcome-column", "outcome", "--failed", "failed", "--started", STARTS[0]],
    "openai-evals": ["openai-evals", "files/old.jsonl", "--store", "new-store", "--run", "oe"],
    "promptfoo": ["promptfoo", "files/results.json", "--store", "new-store", "--run", "pf", "--prompt", "1", "--case", "var:case"],
    "inspect": ["inspect", "files/2026-10-07T04-23-51-00-00_trace-fixture_2nSEDuHHzKiTUjJW3kXknY.json", "--store", "new-store", "--run", "insp"],
    "deepeval": ["deepeval", "files/humaneval-a.json.gz", "--store", "new-store", "--run", "he-a", "--metric", "Tests Passed", "--cut", "recorded", "--case", "name", "--started", "2026-09-05T18:54:07Z"],
    "table verdicts": ["table", "new.csv", "--store", "new-store", "--run", "t2", "--case-column", "case", "--outcome-column", "outcome", "--failed", "failed", "--verdicts", "grades.csv", "--started", STARTS[1]],
    "folder in the tool's place": ["files/junit-folder", "--store", "new-store", "--run", "jf"],
}
SLOW_IMPORTS = ("deepeval",)

# Refusals after the command line is read, from inside a workspace: the main command's words,
# and the exit code. The TF0 corpus's own refusals are held in the slow lane (TF13-22).
REFUSALS_ARGV: dict[str, tuple[list[str], int]] = {
    "an unknown run": (["where", "no-such-run", "--store", "store", *EV], 1),
    "an unknown event": (["where", "agent after", "--store", "store", "--event", "violatd"], 1),
    "a store that is not there": (["where", "agent after", "--store", "no-such-store", *EV], 1),
    "a store that is a file": (["where", "agent after", "--store", "grades.csv", *EV], 1),
    "a folder that holds no run": (["where", "agent after", "--store", "conf", *EV], 1),
    "no store and no config": (["where", "agent after", *EV], 2),
    "no event and no config": (["where", "agent after", "--store", "store"], 2),
    "a bootstrap of none": (["where", "agent after", "--store", "store", *EV, "--boot", "0"], 1),
    "a negative seed": (["where", "agent after", "--store", "store", *EV, "--seed", "-1"], 1),
    "no hazard-ratio ceiling": (["compare", "agent before", "agent after", "--store", "store", *EV], 1),
    "an alpha out of range": (["compare", "agent before", "agent after", "--store", "store", *EV, "--max-mde-hr", "1.5", "--alpha", "1.5"], 1),
    "a ceiling out of range": (["fix-check", "agent before", "agent after", "--store", "store", *EV, "--inputs", "all", "--max-mde", "20"], 1),
    "no ceiling": (["fix-check", "agent before", "agent after", "--store", "store", *EV, "--inputs", "all"], 1),
    "inputs other than all": (["fix-check", "agent before", "agent after", "--store", "store", *EV, "--inputs", "some", "--max-mde", "0.2"], 1),
    "neither inputs nor failing-from": (["fix-check", "agent before", "agent after", "--store", "store", *EV, "--max-mde", "0.2"], 1),
    "min-failures without failing-from": (["fix-check", "agent before", "agent after", "--store", "store", *EV, "--inputs", "all", "--max-mde", "0.2", "--min-failures", "2"], 1),
    "the same run twice": (["changes", "agent after", "agent after", "--store", "store", *EV], 1),
    "verdicts matching neither run": (["compare", "agent before", "agent after", "--store", "store", *EV, "--max-mde-hr", "1.5", "--verdicts", "grades.csv"], 1),
    "the same run by two words": (["changes", "#2", "agent before", "--store", "store", *EV], 1),
    "the selecting run as an arm": (["fix-check", "ja", "jb", "--store", "jstore", "--event", "missed", "--failing-from", "jb", "--max-mde", "0.2"], 1),
    "a verdicts file that is not there": (["fix-check", "old", "new", "--store", "tables", "--event", "missed", "--inputs", "all", "--max-mde", "0.5", "--verdicts", "nothing.csv"], 1),
    "a verdicts file matching nothing": (["changes", "old", "new", "--store", "tables", "--event", "missed", "--verdicts", "conf/no-match.csv"], 1),
    "compare on runs with no traces": (["compare", "ja", "jb", "--store", "jstore", "--event", "missed", "--max-mde-hr", "1.5"], 1),
    "a config that is not there": (["where", "agent after", "--config", "conf/none.toml"], 1),
    "a store name the config lacks": (["where", "agent after", "--config", "conf/trace.toml", "--store", "nameless"], 1),
    "runs on a store that is not there": (["runs", "--store", "no-such-store"], 1),
    # PA19: the command under this refusal repeats the command with OLDER and NEWER in place of
    # previous and latest; through the API it is the call's, its options in the parser's order,
    # which is how these are typed
    "previous and latest that cannot be ordered": (["fix-check", "previous", "latest", "--store", "ties", "--event", "missed", "--inputs", "all", "--max-mde", "0.2"], 1),
    "latest of two that cannot be ordered": (["changes", "latest", "zz-old", "--store", "ties", "--event", "missed"], 1),
    "latest alone, of two that cannot be ordered": (["where", "latest", "--store", "ties", "--event", "missed"], 1),
}
IMPORT_REFUSALS_ARGV: dict[str, tuple[list[str], int]] = {
    "a file that is not there": (["junit", "files/no-such.xml", "--store", "new-store", "--run", "x"], 1),
    "a run name in use": (["junit", "files/humaneval-a.xml", "--store", "jstore", "--run", "ja"], 1),
    "a metric no case carries": (["ragas", "files/rag-base.jsonl", "--store", "new-store", "--run", "x", "--metric", "faithfulnes", "--cut", "0.5", "--below", "--case-column", "case"], 1),
    "a start with no zone": (["junit", "files/humaneval-a.xml", "--store", "new-store", "--run", "x", "--started", "2025-03-31T06:56:41"], 1),
    "a start that is not a time": (["junit", "files/humaneval-a.xml", "--store", "new-store", "--run", "x", "--started", "yesterday"], 1),
    "a cut with no side": (["ragas", "files/rag-base.jsonl", "--store", "new-store", "--run", "x", "--metric", "faithfulness", "--cut", "0.5", "--case-column", "case"], 1),
    "a run name that cannot be a folder": (["junit", "files/humaneval-a.xml", "--store", "new-store", "--run", "a/b"], 1),
    "no store and no config": (["junit", "files/humaneval-a.xml", "--run", "x"], 2),
    "a tool not in this install": (["otel", "files/old.jsonl", "--store", "new-store", "--run", "x"], 1),
}


# ---------- the command line, in-process, from inside a folder ----------


def cli(work: Path, argv: Sequence[str]) -> Ran:
    with chdir(work):
        return trace(list(argv))


def cli_import(work: Path, argv: Sequence[str]) -> Ran:
    with chdir(work):
        return trace_import(list(argv))


def notes_of(err: str) -> tuple[str, ...]:
    """The sentences of the ``note:`` lines on stderr, in order."""
    return tuple(line[len("note: "):] for line in err.splitlines() if line.startswith("note: "))


def error_of(err: str) -> tuple[str, tuple[str, ...]]:
    """The refusal's sentence and the commands under it."""
    lines = err.splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith("error: "))
    nexts = tuple(line[len("  next: "):] for line in lines[at + 1:] if line.startswith("  next: "))
    return lines[at][len("error: "):], nexts


# ---------- the same invocation through the API ----------


@dataclass(frozen=True)
class Call:
    """One invocation as the API takes it: the function, its arguments, and what the command line
    asked for its delivery."""

    function: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    json: bool = False
    svg: str | None = None
    save: bool = False
    out: str | None = None
    force: bool = False

    def __call__(self) -> Any:
        a = api()
        result = getattr(a, self.function)(*self.args, **self.kwargs)
        if self.svg is not None:
            result = result.write_svg(self.svg, force=self.force)
        if self.out is not None:
            result = result.to_bundle(self.out, force=self.force)
        elif self.save:
            result = a.save(result)
        return result


def _typed(words: Sequence[str]) -> set[str]:
    return {w.split("=", 1)[0] for w in words if w.startswith("--")}


def call_for(argv: Sequence[str]) -> Call:
    """The API call a main-command invocation is, by the naming rule (PA1), read with the verb's
    own parser: the store first, then the positionals, then each option as its keyword."""
    verb, rest = argv[0], list(argv[1:])
    _top, verbs = cli_parsers()
    parser = verbs[verb]
    ns, extra = parser.parse_known_args(rest)
    assert not extra, (argv, extra)
    typed = _typed(rest)
    kwargs = {}
    for action in options_of(parser, DELIVERY[verb] | {"--store"}):
        if set(action.option_strings) & typed:
            kwargs[keyword(action)] = getattr(ns, action.dest)
    args = (ns.store, *[getattr(ns, d) for d in positionals_of(parser)])
    return Call(VERB_FUNCTION[verb], args, kwargs, json=bool(getattr(ns, "json", False)),
                svg=getattr(ns, "svg", None), save=bool(getattr(ns, "save", False)),
                out=getattr(ns, "out", None), force=bool(getattr(ns, "force", False)))


def import_call_for(argv: Sequence[str]) -> Call:
    """The ``import_run`` call an import invocation is (the import's words, the tool first)."""
    from poisson_trace.ingest.folder import is_folder

    _top, subs = import_parsers()
    tool: str | None = argv[0]
    rest = list(argv[1:])
    if tool not in subs and is_folder(tool):
        rest, tool = [tool, *rest], None
    if tool is not None and tool not in subs:
        # a tool this install lacks: the API is handed it as the command line is
        ns_store = rest[rest.index("--store") + 1] if "--store" in rest else None
        run = rest[rest.index("--run") + 1] if "--run" in rest else None
        files = [w for w in rest if not w.startswith("--") and w not in (ns_store, run)]
        return Call("import_run", (ns_store, tool, files), {"run": run} if run is not None else {})
    parser = subs[tool or "junit"]
    if tool is None:
        from poisson_trace.ingest.folder import resolve

        parser = subs[resolve(Path(rest[0]), None).tool]
    ns = parser.parse_args(rest)
    typed = _typed(rest)
    kwargs: dict[str, Any] = {}
    for action in options_of(parser, frozenset({"--store"})):
        if set(action.option_strings) & typed:
            kwargs[keyword(action)] = getattr(ns, action.dest)
    return Call("import_run", (ns.store, tool, list(ns.files)), kwargs, json=bool(ns.json))


# ---------- running the API and watching what it does ----------


@dataclass
class Outcome:
    """What one API call did: its result or its refusal, and what reached the two streams."""

    result: Any = None
    refusal: Any = None
    out: str = ""
    err: str = ""


def attempt(fn: Callable[[], Any], work: Path | None = None) -> Outcome:
    """Run ``fn`` from inside ``work``, streams captured; an ``api.Refusal`` is kept, anything
    else escapes."""
    a = api()
    out, err = io.StringIO(), io.StringIO()
    got = Outcome()
    with contextlib.ExitStack() as stack:
        if work is not None:
            stack.enter_context(chdir(work))
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        try:
            got.result = fn()
        except a.Refusal as e:
            got.refusal = e
    got.out, got.err = out.getvalue(), err.getvalue()
    return got


def expected_cli_output(ran: Ran, as_json: bool) -> str:
    return ran.out


class EnvRecorder(MutableMapping[str, str]):
    """``os.environ``, recording every key the package's own code reads (or ``*`` when it reads
    them all)."""

    def __init__(self, inner: MutableMapping[str, str]) -> None:
        self._inner = inner
        self.read: list[tuple[str, str]] = []

    def _note(self, key: str) -> None:
        frame = sys._getframe(2)
        skip = (os.__file__, __file__, "_collections_abc.py", "<frozen os>", "<frozen _collections_abc>")
        while frame is not None and (frame.f_code.co_filename in skip or frame.f_code.co_filename.endswith(skip)):
            frame = frame.f_back  # type: ignore[assignment]
        if frame is not None and frame.f_code.co_filename.startswith(str(PACKAGE)):
            # the package's own read names the environment on its line; a library's compiled
            # code reading it (pyarrow's time zone switch) has no line of its own here
            line = linecache.getline(frame.f_code.co_filename, frame.f_lineno)
            if "environ" in line or "getenv" in line:
                self.read.append((key, f"{Path(frame.f_code.co_filename).name}:{frame.f_lineno}"))

    def __getitem__(self, key: str) -> str:
        self._note(key)
        return self._inner[key]

    def __setitem__(self, key: str, value: str) -> None:
        self._inner[key] = value

    def __delitem__(self, key: str) -> None:
        del self._inner[key]

    def __iter__(self) -> Iterator[str]:
        self._note("*")
        return iter(self._inner)

    def __len__(self) -> int:
        return len(self._inner)

    def __contains__(self, key: object) -> bool:
        self._note(str(key))
        return key in self._inner

    def copy(self) -> dict[str, str]:
        self._note("*")
        return dict(self._inner)


_WATCHING: list[Watch] = []
_HOOKED = False
_WRITE_EVENTS = {"os.mkdir", "os.rename", "os.remove", "os.rmdir", "shutil.rmtree", "shutil.copyfile",
                 "shutil.copytree", "shutil.move", "os.symlink", "os.link", "os.truncate", "os.chmod",
                 "os.utime", "os.chown"}
_LIST_EVENTS = {"os.listdir", "os.scandir", "glob.glob"}


def _hook(event: str, args: tuple[Any, ...]) -> None:
    if not _WATCHING:
        return
    watch = _WATCHING[-1]
    if event == "open":
        path, mode = args[0], args[1] if len(args) > 1 else "r"
        if isinstance(path, int):
            return
        mode = str(mode) if mode is not None else "r"
        flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
        writing = bool(set(mode) & set("wax+")) or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC))
        (watch.written if writing else watch.opened).append(os.path.abspath(os.fsdecode(path)))
    elif event in _WRITE_EVENTS:
        # a path relative to an open folder (shutil.rmtree's own unlinking) is already seen as
        # the rmtree of the folder it named
        def fd_at(i: int) -> bool:
            return len(args) > i and isinstance(args[i], int) and not isinstance(args[i], bool)

        relative_to = {"os.mkdir": (2,), "os.remove": (1,), "os.rmdir": (1,), "os.chmod": (2,), "os.utime": (3,),
                       "os.chown": (3,), "os.rename": (2, 3), "os.link": (2, 3), "os.symlink": (2, 2)}.get(event, ())
        for i, at in enumerate((0, 1)[: 2 if event in ("os.rename", "shutil.copyfile", "shutil.copytree", "shutil.move", "os.symlink", "os.link") else 1]):
            if len(args) <= at or not isinstance(args[at], (str, bytes, os.PathLike)):
                continue
            path = os.fsdecode(args[at])
            if i < len(relative_to) and fd_at(relative_to[i]) and not os.path.isabs(path):
                continue
            watch.written.append(os.path.abspath(path))
    elif event in _LIST_EVENTS:
        if args and isinstance(args[0], (str, bytes, os.PathLike)):
            watch.listed.append(os.path.abspath(os.fsdecode(args[0])))
        elif event in ("os.listdir", "os.scandir") and args and args[0] is None:
            watch.listed.append(os.path.abspath("."))


@dataclass
class Watch:
    """What the package read, listed and wrote while it was watched, and the environment
    variables its own code read."""

    opened: list[str] = field(default_factory=list)
    written: list[str] = field(default_factory=list)
    listed: list[str] = field(default_factory=list)
    env: list[tuple[str, str]] = field(default_factory=list)


def _real(path: str | Path) -> str:
    return os.path.realpath(os.path.abspath(path))


def python_roots() -> list[str]:
    """Where Python, its libraries and the installed packages live: reading there is the
    interpreter's own business."""
    roots = {sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix, *site.getsitepackages(),
             site.getusersitepackages(), *sysconfig.get_paths().values(), str(PACKAGE),
             "/usr/share/zoneinfo", "/etc/localtime", "/var/db/timezone", "/dev/null", "/dev/urandom"}
    import poisson_prove

    roots.add(str(Path(poisson_prove.__file__).resolve().parent))
    return sorted(_real(r) for r in roots if r)


@contextlib.contextmanager
def watched(temp: Path) -> Iterator[Watch]:
    """Watch the package: the audit events of every file opened, folder listed and path written,
    and every environment variable read; the system's temporary folder pointed at ``temp`` for
    the while, so a folder the API makes for its own work is seen to be gone."""
    global _HOOKED
    if not _HOOKED:
        sys.addaudithook(_hook)
        _HOOKED = True
    watch = Watch()
    recorder = EnvRecorder(os.environ)
    saved_environ, saved_tempdir, saved_bytecode = os.environ, tempfile.tempdir, sys.dont_write_bytecode
    temp.mkdir(parents=True, exist_ok=True)
    # Python's own byte code, written as a module is first imported, is not the package's write
    sys.dont_write_bytecode = True
    os.environ = recorder  # type: ignore[assignment]  # noqa: B003
    tempfile.tempdir = str(temp)
    _WATCHING.append(watch)
    try:
        yield watch
    finally:
        _WATCHING.pop()
        os.environ = saved_environ  # type: ignore[assignment]  # noqa: B003
        tempfile.tempdir = saved_tempdir
        sys.dont_write_bytecode = saved_bytecode
        watch.env = list(recorder.read)


def outside(paths: Sequence[str], roots: Sequence[str | Path]) -> list[str]:
    """The paths that are under none of ``roots``."""
    real_roots = [_real(r) for r in roots]
    bad = []
    for p in paths:
        rp = _real(p)
        if not any(rp == r or rp.startswith(r.rstrip(os.sep) + os.sep) for r in real_roots):
            bad.append(p)
    return bad


def snapshot(root: Path) -> dict[str, str]:
    """Every file and folder under ``root`` with its bytes' digest (folders as ``/``)."""
    out = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        out[rel] = "/" if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest()
    return out


# ---------- reading source ----------


def imports_of(path: Path) -> list[tuple[str, int]]:
    """Every module a source file imports, anywhere in it, as ``module`` or ``module.name`` for
    ``from module import name``, with its line."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = "poisson_trace" + ("." + ".".join(path.relative_to(PACKAGE).parent.parts) if path.parent != PACKAGE else "")
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [(alias.name, node.lineno) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.rsplit(".", node.level - 1)[0] if node.level > 1 else package
                module = f"{base}.{node.module}" if node.module else base
            else:
                module = node.module or ""
            out += [(f"{module}.{alias.name}", node.lineno) for alias in node.names]
            out.append((module, node.lineno))
    return out


def source_modules() -> dict[str, Path]:
    """Every module of the package by its dotted name."""
    out = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        parts = path.relative_to(PACKAGE).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        out[".".join(("poisson_trace", *parts))] = path
    return out


COMMAND_LINES = ("poisson_trace.cli", "poisson_trace.ingest.cli", "poisson_trace.__main__")


def the_module(name: str) -> str:
    """The package's module a dotted import names: ``poisson_trace.ingest.cli.main`` is
    ``poisson_trace.ingest.cli``."""
    known = source_modules()
    parts = name.split(".")
    while parts and ".".join(parts) not in known:
        parts.pop()
    return ".".join(parts)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def doc_sections(text: str) -> dict[str, str]:
    """``docs/python.md``'s sections by the function each opens with: a heading line
    ``## api.<name>`` or ``## commands.<name>``, up to the next ``## `` heading."""
    sections: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^## `?((?:api|commands)\.\w+)`?\s*$", line)
        if m or line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(lines)
            current, lines = (m.group(1) if m else None), []
            continue
        if current is not None:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines)
    return sections


def fenced(text: str) -> list[tuple[str, str]]:
    """Every fenced block in ``text``: its language word and its body."""
    return [(m.group(1), m.group(2)) for m in re.finditer(r"^```(\w*)\n(.*?)^```\s*$", text, re.M | re.S)]
