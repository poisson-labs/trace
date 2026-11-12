"""The import's core: the readers, their options, what ``[signals]`` stands in for, the
import of one run, and its summary in text and JSON. ``poisson-trace import`` and
``poisson-trace-import`` (``ingest/cli.py``) parse the command line and call this through
``poisson_trace.api.import_run``; ``init``, ``doctor --setup`` and the folder resolver read
files through it too.

The readers are found from ``READERS`` by presence: a module that is not in the install is
not in ``--help`` and its name is refused. A tool's module is its name with ``-`` as ``_``
(``openai-evals`` is ``openai_evals``), since a module's name cannot hold a hyphen. A reader
module defines ``add_arguments(parser)`` and ``read(ns) -> Run``, and may define
``DESCRIPTION`` (its help's paragraph), ``EXAMPLE`` (a command its help and the import's show)
and ``usage(ns) -> str | None`` (why a command line its parser takes is still wrong, exit 2).
It may also define ``FURTHER``, a mapping from one further command name to ``(add_arguments,
run)`` with ``run(ns) -> int``, for a command that writes no store and takes its own flags.

``poisson_prove`` is imported by the writer (and by the Prove reader, which no tool here
names), and the writer is imported after the check that ``poisson_prove`` is present at the
version this package reads, which runs once the call is read and before any file is opened.

A config's ``[signals]`` field mappings reach a reader as ``ns.signals``, where
``cost_field`` is read; ``case_field``, ``outcome_field``, ``score_field`` and ``cut`` stand in
for the reader's own flags when the call leaves them out (``stand_ins``, ``filled_stand_ins``):
the command line fills them into its words before it is parsed, so each reader's help and its
refusal of a missing flag are as they were, and a flag given wins. Its budgets and
``[[taxonomy.rules]]`` go to the writer, which classifies every row with them and records
their digest.

``reader_options`` says which keys, types and choices each reader's flags take, for the config
to check an ``[[import]]`` entry's options without opening anything.

Nothing here prints: the summary comes back as text and as the JSON document, and every
refusal is raised (``look.Refused``, ``look.Usage``, ``ingest.rows.Refusal``).
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING, Any

from poisson_trace import look
from poisson_trace.ingest.cut import MET, MISSED
from poisson_trace.ingest.folder import Resolved, resolve
from poisson_trace.ingest.rows import Refusal, Run, zone_of
from poisson_trace.look import count
from poisson_trace.names import import_name_refusal

if TYPE_CHECKING:
    from poisson_trace.ingest.writer import Written

READERS: tuple[str, ...] = (
    "deepeval",
    "ragas",
    "table",
    "junit",
    "promptfoo",
    "inspect",
    "openai-evals",
    "langsmith",
    "braintrust",
    "weave",
    "otel",
    "lemma",
)

SCHEMA = "poisson-trace.import/1"

PROG = "poisson-trace import"

_DOES = f"{PROG} writes runs"


def module_name(tool: str) -> str:
    """The reader module of the tool ``tool``: its name with ``-`` as ``_``."""
    return f"{__package__}.{tool.replace('-', '_')}"


def reader(tool: str) -> Any:
    """The reader module of the tool ``tool``."""
    return import_module(module_name(tool))


def present() -> tuple[str, ...]:
    """The readers whose modules are in the install, in the order ``READERS`` names them."""
    return tuple(name for name in READERS if find_spec(module_name(name)) is not None)


# the flags every tool's parser has, the import's own: never a reader's option
_OWN = ("files", "store", "config", "run", "started", "verdicts", "json", "debug", "help")

# the import's own options, as the parser gives them when they are not given
OWN_DEFAULTS: dict[str, Any] = {
    "store": None,
    "config": None,
    "run": None,
    "started": None,
    "verdicts": None,
    "json": False,
    "debug": False,
}


def reader_parser(tool: str, prog: str = "poisson-trace import") -> argparse.ArgumentParser:
    """A parser holding the reader's own flags and nothing else: what ``add_arguments`` adds.
    A plain parser, not the look's, since building the look's reads the environment for the
    help's width, and the core reads no environment variable."""
    parser = argparse.ArgumentParser(prog=f"{prog} {tool}", add_help=False, allow_abbrev=False)
    reader(tool).add_arguments(parser)
    return parser


def reader_actions(tool: str) -> list[argparse.Action]:
    """The reader's own options, in the order its parser adds them."""
    return [
        a
        for a in reader_parser(tool)._actions
        if a.option_strings and a.dest not in _OWN and a.help is not argparse.SUPPRESS
    ]


@dataclass(frozen=True)
class Option:
    """One flag of a reader, as an ``[[import]]`` entry writes it: ``dest`` is the key (the
    flag's name without ``--`` and with ``_`` for ``-``)."""

    dest: str
    flag: str
    required: bool
    takes_value: bool
    many: bool  # repeatable: a list in the config
    choices: tuple[str, ...]
    takes: str  # what the value is, for a refusal


def reader_options(tool: str) -> dict[str, Option]:
    """The options the reader of ``tool`` takes, by key, in the order its parser adds them."""
    out: dict[str, Option] = {}
    for action in reader_actions(tool):
        long = [o for o in action.option_strings if o.startswith("--")]
        flag = long[0] if long else action.option_strings[0]
        metavar = str(action.metavar or action.dest.upper())
        out[action.dest] = Option(
            dest=action.dest,
            flag=flag,
            required=bool(action.required),
            takes_value=action.nargs != 0,
            many=isinstance(action, argparse._AppendAction),
            choices=tuple(str(c) for c in action.choices) if action.choices else (),
            takes=_TAKES.get(metavar, "the " + metavar.lower().replace("|", " or ")),
        )
    return out


def reader_defaults(tool: str) -> dict[str, Any]:
    """Each flag's default, by dest, as the parser gives it when the flag is not given: the
    import's own options and the reader's."""
    out: dict[str, Any] = {"files": None, **OWN_DEFAULTS}
    for action in reader_parser(tool)._actions:
        if action.dest not in ("help",) and action.default is not argparse.SUPPRESS:
            out[action.dest] = action.default
    return out


_TAKES = {
    "NAME": "a name",
    "COLUMN": "a column's name",
    "ID": "an id",
    "LABEL|N": "a label or a number",
}

# what [signals] stands in for, by reader: the field mapping, and the reader's flag it fills
# (SA8): the case field for the case column, the outcome field for the outcome column, the
# score field for the metric or the score column, and the cut for the cut
_STAND_INS: dict[str, tuple[tuple[str, str], ...]] = {
    "ragas": (("case_field", "case_column"), ("score_field", "metric"), ("cut", "cut")),
    "deepeval": (("score_field", "metric"), ("cut", "cut")),
    "table": (
        ("case_field", "case_column"),
        ("outcome_field", "outcome_column"),
        ("score_field", "score_column"),
        ("cut", "cut"),
    ),
}


def pulls(tool: str) -> str | None:
    """What an address the reader of ``tool`` pulls from starts with (``langsmith:``), or None
    when the install has no such reader, or the reader reads files alone."""
    if find_spec(module_name(tool)) is None:
        return None
    address = getattr(reader(tool), "ADDRESS", None)
    return address if isinstance(address, str) and address else None


def stand_ins(
    tool: str, signals: Mapping[str, Any], said: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """The reader's options ``[signals]`` stands in for, by dest, with the values it gives.
    A reader whose flags name their sources in their own words (LangSmith's ``--outcome-from
    feedback:KEY``) says what stands in for them itself, in its ``stand_ins(signals, said)``;
    ``said`` holds what the call itself gave, by dest, which decides whether a cut is read."""
    if tool not in _STAND_INS and find_spec(module_name(tool)) is not None:
        own = getattr(reader(tool), "stand_ins", None)
        if own is not None:
            return dict(own(signals, said or {}))
    return {
        dest: signals[field]
        for field, dest in _STAND_INS.get(tool, ())
        if field in signals and signals[field] is not None
    }


def filled_stand_ins(
    tool: str,
    signals: Mapping[str, Any],
    given: Collection[str],
    values: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The reader's options ``[signals]`` fills in where the call leaves them out, by dest,
    with the values the parser would give for the words the command line fills in: a cut from
    the config with no side given reads below. For a table, the form the call reads (its
    outcome column, or its score column) is the one filled, and the outcome form when the call
    says neither and the config gives both. ``given`` names the dests the call gave, and
    ``values`` holds what it gave for them."""
    held = set(given)
    filled = stand_ins(tool, signals, {dest: (values or {}).get(dest, True) for dest in held})
    if tool == "table":
        by_outcome = bool({"outcome_column", "failed"} & held)
        by_score = bool({"score_column", "cut", "below", "above"} & held)
        if by_outcome or (not by_score and "outcome_column" in filled):
            filled.pop("score_column", None)
            filled.pop("cut", None)
        if by_score:
            filled.pop("outcome_column", None)
    out: dict[str, Any] = {}
    for dest, value in filled.items():
        if dest in held:
            continue
        if dest == "cut":
            out["cut"] = repr(float(value))
            if not {"below", "above"} & held:
                out["below"] = True
        else:
            out[dest] = str(value)
    return out


def _started(text: str) -> str:
    """``--started`` as UTC with a ``Z``. A time with no zone is refused: the gap Trace prints
    between two runs is only as good as the two instants it is taken from."""
    try:
        at = datetime.fromisoformat(text)
    except ValueError:
        raise Refusal(
            f'--started takes an ISO-8601 time such as 2026-09-05T18:54:07Z, not "{text}"'
        ) from None
    if at.tzinfo is None or at.utcoffset() is None:
        raise Refusal(
            f"--started {text} carries no zone; end it with Z for UTC or with an offset such "
            "as +02:00"
        )
    try:
        utc = at.astimezone(UTC)
    except OverflowError:
        raise Refusal(f"--started {text} falls outside the years 1 to 9999 in UTC") from None
    return utc.isoformat().replace("+00:00", "Z")


def _outcomes_said(written: Written, sep: str) -> str:
    """The outcomes in the summary's words: passed for met, failed for missed."""
    said = {MET: "passed", MISSED: "failed"}
    return sep.join(f"{count(n)} {said.get(word, word)}" for word, n in written.outcomes.items())


def _sentence(written: Written, store: str) -> str:
    """The run, the store, the rows, the cases and their repeats, and the outcomes."""
    low, high = written.repeats_min, written.repeats_max
    repeats = f"{count(low)} {'repeat' if low == 1 else 'repeats'} each"
    if low != high:
        repeats = f"{count(low)} to {count(high)} repeats"
    none = sum(written.no_outcome.values())
    no_outcome = f", {count(none)} with no outcome" if none else ""
    return (
        f"wrote run {written.run} to {store}: {count(written.rows)} rows, "
        f"{count(written.cases)} cases, {repeats}; {_outcomes_said(written, ', ')}{no_outcome}"
    )


def _summary(run: Run, written: Written, store: str, reach: Sequence[str]) -> dict[str, Any]:
    started: dict[str, Any] = {"at": run.started, "from": run.started_from}
    if run.started_from == "file name":
        started["zone"] = zone_of(run.started)
    if run.started_note is not None:
        started["note"] = run.started_note
    return {
        "schema": SCHEMA,
        "verdict": "ok",
        "sentence": _sentence(written, store),
        "run": written.run,
        "store": store,
        "tool": run.tool,
        "files": [dict(f) for f in run.files],
        "declared": dict(run.declared),
        "started": started,
        "rows": written.rows,
        "cases": written.cases,
        "repeats": {"min": written.repeats_min, "max": written.repeats_max},
        "outcomes": dict(written.outcomes),
        "no_outcome": dict(written.no_outcome),
        "counts": dict(run.counts),
        "next": (
            f"poisson-trace fix-check OLD NEW {' '.join([*reach, f'--event {MISSED}'])} "
            "--inputs all "
            f"--max-mde X  # {written.run} is OLD or NEW"
        ),
    }


def _value(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value)


def _plural(n: int, one: str, many: str) -> str:
    return f"{count(n)} {one if n == 1 else many}"


def _or(words: Sequence[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " or " + words[-1]


def _and(words: Sequence[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def _failed_when(d: Mapping[str, Any]) -> str:
    """When a try counts as failed, in the summary's words, from what was declared."""
    declared, tool = d["declared"], d["tool"]
    if tool == "junit":
        return "its test failed or errored"
    if tool == "openai-evals":
        return "its match event was not correct"
    if tool == "langsmith":
        return _langsmith_failed_when(declared)
    if tool == "braintrust":
        return _braintrust_failed_when(declared)
    if tool == "weave":
        return _weave_failed_when(declared)
    side = "below" if declared.get("side") == "below" else "above"
    if tool == "promptfoo":
        if declared.get("outcome") == "score":
            return f"its score is {side} {_value(declared['cut'])}"
        return "promptfoo marked it as not passed"
    if tool == "inspect":
        scorer = declared["scorer"]
        if declared.get("outcome") == "score":
            return f"its {scorer} score is {side} {_value(declared['cut'])}"
        if declared.get("outcome") == "value":
            values = _or([json.dumps(v, ensure_ascii=False) for v in declared["failed"]])
            return f"its {scorer} score reads {values}"
        return f"its {scorer} score is not C (I, P and N count as failed)"
    if "outcome_column" in declared:
        values = _or([json.dumps(v, ensure_ascii=False) for v in declared["failed"]])
        return f"its {declared['outcome_column']} column reads {values}"
    if declared.get("cut") == "recorded":
        return f"DeepEval marked its {declared['metric']} metric as not passed"
    scored = declared.get("score_column", declared.get("metric"))
    return f"its {scored} score is {side} {_value(declared['cut'])}"


def _langsmith_failed_when(declared: Mapping[str, Any]) -> str:
    """When a LangSmith try counts as failed: by its root run's status, by a feedback score
    or a metadata number at the cut, or by a metadata value named as failed."""
    source = str(declared["outcome_from"])
    if source == "status":
        return "its root run ended in error"
    where, _, key = source.partition(":")
    if "cut" in declared:
        side = "below" if declared.get("side") == "below" else "above"
        what = "feedback score" if where == "feedback" else "metadata value"
        return f"its {key} {what} is {side} {_value(declared['cut'])}"
    values = _or([json.dumps(v, ensure_ascii=False) for v in declared["failed"]])
    return f"its root run's {key} metadata reads {values}"


def _braintrust_failed_when(declared: Mapping[str, Any]) -> str:
    """When a Braintrust try counts as failed: by its root span's error, by a score or a
    metadata number at the cut, or by a metadata value named as failed."""
    source = str(declared["outcome_from"])
    if source == "error":
        return "its root span ended in error"
    where, _, key = source.partition(":")
    if "cut" in declared:
        side = "below" if declared.get("side") == "below" else "above"
        what = "score" if where == "score" else "metadata value"
        return f"its {key} {what} is {side} {_value(declared['cut'])}"
    values = _or([json.dumps(v, ensure_ascii=False) for v in declared["failed"]])
    return f"its root span's {key} metadata reads {values}"


def _weave_failed_when(declared: Mapping[str, Any]) -> str:
    """When a Weave try counts as failed: by its case having errored, or by a scorer's output
    at the cut."""
    source = str(declared["outcome_from"])
    if source == "status":
        return "its case errored"
    side = "below" if declared.get("side") == "below" else "above"
    return f"its {source.partition(':')[2]} score is {side} {_value(declared['cut'])}"


def _import_flags(declared: Mapping[str, Any]) -> list[str]:
    """The flags that read another file as this one was read, from what was declared."""
    words: list[str] = []
    if declared.get("outcome") in ("success", "correct"):
        # a reader's default outcome, which the line need not spell
        declared = {k: v for k, v in declared.items() if k != "outcome"}
    for key, flag in (
        ("case_from", "--case-from"),
        ("outcome_from", "--outcome-from"),
        ("prompt", "--prompt"),
        ("scorer", "--scorer"),
        ("provider", "--provider"),
        ("outcome", "--outcome"),
        ("metric", "--metric"),
        ("score_column", "--score-column"),
        ("cut", "--cut"),
    ):
        if key in declared:
            words.append(look.option(flag, _value(declared[key])))
    if declared.get("side") in ("below", "above"):
        words.append(f"--{declared['side']}")
    for key, flag in (
        ("case", "--case"),
        ("case_column", "--case-column"),
        ("outcome_column", "--outcome-column"),
    ):
        if key in declared:
            words.append(look.option(flag, _value(declared[key])))
    words += [look.option("--failed", str(v)) for v in declared.get("failed", ())]
    words += [look.option("--select", str(v)) for v in declared.get("select", ())]
    if "evaluation" in declared:
        words.append(look.option("--evaluation", str(declared["evaluation"])))
    return words


def _extension(name: str) -> str:
    """The extensions that say a file's format: ``.csv``, ``.jsonl.gz``."""
    lowered = name.lower()
    for ext in (".csv", ".tsv", ".jsonl", ".json", ".parquet", ".xml", ".eval"):
        for whole in (ext + ".gz", ext):
            if lowered.endswith(whole):
                return name[-len(whole) :]
    return ""


def _summary_lines(d: Mapping[str, Any], reach: Sequence[str]) -> list[str]:
    """The four lines of the plain summary: what was written, what counts as failed, what it
    is compared with, and the command to run next."""
    files = [str(f["name"]) for f in d["files"]]
    outcomes = d["outcomes"]
    failed, passed = outcomes.get(MISSED, 0), outcomes.get(MET, 0)
    none = sum(d["no_outcome"].values())
    counted = f"{count(failed)} failed and {count(passed)} passed"
    if none:
        counted += f"; {count(none)} had no outcome"
    other = ["OTHER" + _extension(files[0])]
    picked: list[str] = []
    declared = d["declared"]
    whose = "file" if len(files) == 1 else "files"
    if d["tool"] == "promptfoo":
        # one promptfoo file holds every prompt: the other version is usually another of them
        other = [look.word(name) for name in files]
        picked = ["--prompt PROMPT"]
        whose = "prompt"
        declared = {k: v for k, v in declared.items() if k != "prompt"}
    command = look.command(
        "poisson-trace",
        "import",
        d["tool"],
        *other,
        *reach,
        "--run OTHER",
        *picked,
        *_import_flags(declared),
    )
    tail = ""
    if "outcome_column" in d["declared"]:
        tail = "; any other value counts as a pass"
    return [
        f"- Wrote: {d['run']} into {d['store']}, from {_and(files)} ({d['tool']}): "
        f"{_plural(d['rows'], 'try', 'tries')} on {_plural(d['cases'], 'input', 'inputs')}.",
        f"- Failures: {counted}. A try counts as failed when {_failed_when(d)}{tail}.",
        "- Compared: Nothing yet. One import is one version.",
        f"- Next: Import the other version's {whose} the same way: `{command}`.",
    ]


# where a start came from, as the caveat says it
_STARTED_SAID = {
    "file time": (
        "Its start time is when its file was written or copied, so latest and previous won't "
        "order it: name the runs when you compare them, the older first."
    ),
    "earliest span": "Its start time is the earliest span's start in the file.",
}
MAX_MDE_ADVICE = (
    "When you compare, choose the smallest drop that matters to you (--max-mde) before you look "
    "at any results; Trace then says whether these tries could catch it."
)


def _caveats(d: Mapping[str, Any]) -> list[str]:
    """What to know before acting on the import: where its start came from, the values counted
    as a pass, the tests left out, and the ceiling to choose before comparing."""
    started, tool = d["started"], d["tool"]
    said: list[str] = []
    source = started["from"]
    if source == "file name":
        zone = started["zone"]
        said.append(
            "Its start time is taken from the file's name, which DeepEval writes on its own "
            f"clock, read as if in this machine's zone, which is a guess ({zone['name']}, "
            f"{zone['offset']}); if the name was written in another zone, the start is off by "
            "the difference."
        )
    elif source == "file" and tool == "junit":
        note = f" ({started['note']})" if "note" in started else ""
        said.append(f"Its start time is the report's earliest suite timestamp{note}.")
    elif source == "file":
        note = f" ({started['note']})" if "note" in started else ""
        said.append(f"Its start time is a time the tool wrote in the file{note}.")
    elif source in _STARTED_SAID:
        said.append(_STARTED_SAID[source])
    if "outcome_column" in d["declared"]:
        said.append(
            f"Every other value of the {d['declared']['outcome_column']} column counts as a pass."
        )
    if tool == "junit":
        said.append("A skipped test has no outcome and is left out.")
    lacking = d["no_outcome"].get("no score", 0)
    if tool == "langsmith" and lacking and not d["counts"].get("feedback records", 0):
        # the run statistics of an export can trail the feedback records (the captures' TC-11):
        # the score is never guessed, and this says where the records are
        said.append(
            f"{_plural(lacking, 'root run has', 'root runs have')} no score for the key read, "
            "so no outcome. LangSmith's run statistics can trail its feedback records: give "
            "the feedback list beside the runs (GET /api/v1/feedback), or pull with "
            "langsmith:NAME, which reads the records."
        )
    said.append(MAX_MDE_ADVICE)
    return said


def _written_lines(d: Mapping[str, Any], cells: Mapping[str, int]) -> list[str]:
    """What was written, as the record of it: the run, the files, what was declared, the start,
    the counts; for a table read by its outcome column, every value the column holds."""
    started = d["started"]
    source = started["from"]
    if "zone" in started:
        zone = started["zone"]
        source += (
            ": the time in the first file's name, which is when the file was saved, read in "
            f"this machine's zone ({zone['name']}, {zone['offset']})"
        )
    if "note" in started:
        source += f" ({started['note']})"
    none = d["no_outcome"]
    declared = d["declared"]
    if "outcome_column" in declared:
        failed = [str(v) for v in declared["failed"]]
        held = sorted(cells.items(), key=lambda kv: (-kv[1], kv[0]))
        held += [(v, 0) for v in failed if v not in cells]
        listed = " · ".join(
            f"{json.dumps(value, ensure_ascii=False)} {_plural(n, 'row', 'rows')}"
            + (" (counted as failed)" if value in failed else " (counted as passed)")
            for value, n in held
        )
        counted = [f"- the {declared['outcome_column']} column's values: {listed}"]
    else:
        counted = [f"- {label}: {count(n)}" for label, n in d["counts"].items()]
    return [
        f"- run written: {d['run']} · store: {d['store']}",
        f"- tool: {d['tool']}",
        *[f"- file: {f['name']} · sha256 {f['sha256']}" for f in d["files"]],
        *_verdicts_line(d),
        *_pulled_line(d),
        "- declared: " + " · ".join(f"{k} {_value(v)}" for k, v in declared.items()),
        f"- started: {started['at']} · from: {source}",
        f"- rows {count(d['rows'])} · cases {count(d['cases'])} · repeats of a case: smallest "
        f"{count(d['repeats']['min'])}, largest {count(d['repeats']['max'])}",
        "- outcomes: " + " · ".join(f"{word} {count(n)}" for word, n in d["outcomes"].items()),
        "- rows with no outcome: "
        + (" · ".join(f"{reason} {count(n)}" for reason, n in none.items()) if none else "0"),
        *counted,
    ]


def _pulled_line(d: Mapping[str, Any]) -> list[str]:
    """The pull, as one line of what was written, when the run was pulled from an API."""
    if "pull" not in d:
        return []
    p = d["pull"]
    text = "inputs and outputs measured and left out" if p["raw_text_stripped"] else "raw text kept"
    # a pull says what it read in its own service's words: runs and feedback records, events,
    # or calls
    if "calls" in p:
        held = f"calls {count(p['calls'])}"
    elif "events" in p:
        held = f"events {count(p['events'])}"
    else:
        held = f"runs {count(p['runs'])} · feedback records {count(p['feedback'])}"
    return [f"- pulled: {p['source_uri']} · raw copy {p['folder']} · {held} · {text}"]


def _verdicts_line(d: Mapping[str, Any]) -> list[str]:
    """The join, as one line of what was written, when ``--verdicts`` was given."""
    if "verdicts" not in d:
        return []
    v = d["verdicts"]
    return [
        f"- verdicts: {v['name']} · sha256 {v['sha256']} · rows {count(v['rows'])} · joined by "
        f"case {count(v['by_case'])} · by input {count(v['by_input'])} · matched no case "
        f"{count(v['unmatched'])}"
    ]


def _markdown(d: Mapping[str, Any], cells: Mapping[str, int], reach: Sequence[str]) -> str:
    lines = [
        f"{d['verdict']}  {d['sentence']}",
        "",
        f"# Poisson Trace · import · {d['run']}",
        "",
        "## Summary",
        "",
        *_summary_lines(d, reach),
        "",
        "## Before you act on this",
        "",
        *[f"- {caveat}" for caveat in _caveats(d)],
        "",
        "## What was written",
        "",
        *_written_lines(d, cells),
        "",
        "In the command below, OLD and NEW are this run and the other version's run, "
        "imported into the same store, the older version first. X is the largest limit of "
        "detection you accept, as a share: 0.05 is five points.",
        "",
        f"next: {d['next']}",
        "",
    ]
    return "\n".join(lines)


# ---------- one import, as the API and the command line call it ----------


@dataclass(frozen=True)
class Imported:
    """What one import did: the summary as the JSON document and as text."""

    data: dict[str, Any]
    text: str


def prepare(ns: argparse.Namespace, settings: Any) -> tuple[Any, Any, list[str]]:
    """The store the import writes into, the rules and the reach of its next command, from
    the call and the config: a store name the config holds is that store; with none, the
    config's; a run's name checked before Prove is asked anything. ``(form, (rules, budgets),
    reach)``; ``ns.store`` is the store's path once this returns."""
    form = settings.names_from if settings is not None else "target"
    ns.signals = dict(settings.signals) if settings is not None else {}
    rules: Sequence[Any] = ()
    budgets = None
    if settings is not None:
        rules, budgets = settings.rules, settings.budgets
    typed = ns.store
    if typed is not None and settings is not None and typed in settings.named:
        ns.store = settings.named[typed]
    elif typed is None and settings is not None:
        ns.store = settings.store
    if ns.store is None:
        gives = (
            "no trace.toml here gives one" if settings is None else f"{settings.shown} names none"
        )
        raise look.Usage(f"--store is required: {gives}", f"{PROG} {ns.tool} --help")
    reach = [look.option("--store", typed)] if typed is not None else []
    reach += list(settings.flags()) if settings is not None else []
    if ns.run is not None:
        hole = import_name_refusal(ns.run)
        if hole is not None:
            raise Refusal(hole)
    return form, (rules, budgets), reach


def usage_fault(ns: argparse.Namespace) -> str | None:
    """Why a call the reader's parser takes is still wrong, in the reader's words, or None."""
    wrong = getattr(reader(ns.tool), "usage", None)
    if wrong is None:
        return None
    said = wrong(ns)
    return None if said is None else str(said)


def import_run(ns: argparse.Namespace, settings: Any, folders: Sequence[str]) -> Imported:
    """The import: the reader reads the files (or the one folder) into one run, the verdicts
    file is joined on, and the writer writes the run into the store. ``ns`` holds the import's
    own options and the reader's, as the parser gives them; ``settings`` the config, or None.
    Ctrl-C after the writer may have begun raises ``look.Interrupted`` with the line that
    says what the store holds."""
    form, (rules, budgets), reach = prepare(ns, settings)
    _prove_present()
    found: Resolved | None = None
    if folders:
        found = _resolved(folders[0], ns.tool)
        ns.files = [str(f) for f in found.files]
        if ns.run is None:
            ns.run = found.name
            hole = import_name_refusal(ns.run)
            if hole is not None:
                raise Refusal(f"the folder's name is the run's when --run is not given, and {hole}")
    store = Path(ns.store)
    try:
        held = (store / ns.run).exists()
    except OSError:
        # a name the system cannot look up is never this import's to call partial
        held = True
    try:
        return _read_and_write(ns, store, found, form, rules, budgets, reach)
    except KeyboardInterrupt as e:
        raise look.Interrupted(_stopped(store, ns.run, held)) from e


def _read_and_write(
    ns: argparse.Namespace,
    store: Path,
    found: Resolved | None,
    form: str,
    rules: Sequence[Any],
    budgets: Any,
    reach: Sequence[str],
) -> Imported:
    given = None if ns.started is None else _started(ns.started)
    run: Run = reader(ns.tool).read(ns)
    if given is not None:
        run = replace(run, started=given, started_from="given", started_note=None)
    if found is not None:
        one_run(ns.tool, ns, found, run, reach)
    if not run.rows:
        raise Refusal("no row was read from the files, so there is no run to write")
    joined = None
    if ns.verdicts is not None:
        from poisson_trace.ingest import verdicts

        result = verdicts.join(run.rows, Path(ns.verdicts), run.inputs or None)
        run = replace(run, rows=result.rows)
        joined = verdicts.block(Path(ns.verdicts), result)
    checked(run)
    from poisson_trace.ingest.writer import write

    written = write(run, store, form, rules=rules, budgets=budgets, verdicts=joined)
    data = _summary(run, written, str(ns.store), reach)
    if run.pull is not None:
        data = _with_pull(data, run.pull)
    if joined is not None:
        data = _with_verdicts(data, joined)
    return Imported(data, _markdown(data, run.cells, reach))


def _prove_present() -> None:
    """Refused when ``poisson_prove`` is not present at the version this package reads."""
    refusal = look.prove_refusal(_DOES)
    if refusal is not None:
        raise Refusal(refusal, look.INSTALL_PROVE)


def _resolved(path: str, tool: str | None) -> Resolved:
    """What the folder given holds, through the folder resolver; a folder Prove stored is
    already a store, and is not imported (FI15)."""
    found = resolve(Path(path), tool)
    if found.kind in ("run", "store"):
        assert found.store is not None
        what = (
            f"{path} is a run Prove stored, in the store {found.store}"
            if found.kind == "run"
            else f"{path} is a store Prove wrote, holding the run {found.run_id}"
        )
        raise Refusal(
            f"{what}; it is read where it is, so there is nothing to import",
            look.command("poisson-trace", "runs", look.option("--store", str(found.store))),
        )
    return found


def checked(run: Run) -> None:
    """Refused when the run read holds no row, or no row with an outcome."""
    if not run.rows:
        raise Refusal("no row was read from the files, so there is no run to write")
    if all(row.outcome is None for row in run.rows):
        raise Refusal(
            f"none of the {count(len(run.rows))} rows read has an outcome, so there is nothing "
            "to compare and no run was written"
        )


def one_run(
    tool: str, ns: argparse.Namespace, found: Resolved, run: Run, reach: Sequence[str]
) -> None:
    """Refused when a folder's files are more than one run (FI6): several DeepEval test runs,
    or a case in two files. Shards hold each case once; two versions or two re-runs of one
    suite hold the same cases. A pull's files are one run by its own record."""
    files = found.files
    if found.kind != "files" or len(files) < 2:
        return
    flags = _import_flags(run.declared)

    def nexts() -> list[str]:
        out = []
        for f in files:
            name = f.name.split(".", 1)[0]
            name = name if import_name_refusal(name) is None else "NAME"
            out.append(
                look.command(
                    "poisson-trace",
                    "import",
                    tool,
                    look.word(str(f)),
                    *reach,
                    look.option("--run", name),
                    *flags,
                )
            )
        return out

    listed = _and([f.name for f in files])
    if tool == "deepeval":
        raise Refusal(
            f"{found.path} holds {len(files)} DeepEval test runs, {listed}; each test run "
            "DeepEval saves is one run, and one import is one version, so import each on its own",
            *nexts(),
        )
    module = reader(tool)
    seen: dict[str, Path] = {}
    for f in files:
        one = module.read(argparse.Namespace(**{**vars(ns), "files": [str(f)]}))
        for case in dict.fromkeys(row.case for row in one.rows):
            if case in seen:
                raise Refusal(
                    f"{found.path} holds more than one run: the case {case} is in both "
                    f"{seen[case].name} and {f.name}, so its files ({listed}) are not shards of "
                    "one run; one import is one version, so import each on its own",
                    *nexts(),
                )
            seen[case] = f


def _with_pull(data: Mapping[str, Any], pull: Mapping[str, Any]) -> dict[str, Any]:
    """The summary with what the pull did, before the command to run next."""
    out = {key: value for key, value in data.items() if key != "next"}
    out["pull"] = dict(pull)
    out["next"] = data["next"]
    return out


def _with_verdicts(data: Mapping[str, Any], joined: Mapping[str, Any]) -> dict[str, Any]:
    """The summary with what the join did, after the files it read (FI20)."""
    out: dict[str, Any] = {}
    for key, value in data.items():
        out[key] = value
        if key == "files":
            out["verdicts"] = dict(joined)
    return out


def _stopped(store: Path, name: str, held: bool) -> str:
    """The line Ctrl-C prints: what the interrupted import left in the store. A folder of that
    name that was there before the import began is never this import's."""
    if held or not (store / name).exists():
        return look.NOTHING_WRITTEN
    from poisson_trace.ingest.writer import status

    if status(store, name) == "complete":
        return f"stopped  interrupted: the run {name} was written whole to {store}"
    return (
        f"stopped  interrupted: the run {name} is partial; remove its folder in {store} "
        "before importing it again"
    )
