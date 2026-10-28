"""The import: ``poisson-trace import``, and the console script ``poisson-trace-import``.

``poisson-trace import TOOL FILE [FILE ...] --store ROOT --run NAME`` reads the files with the
tool's reader, writes one new run through the writer, and prints a summary that ends with the
Trace command to run next. ``poisson-trace-import`` is the same command under its first name:
the main command hands it every word but ``import``, so both print the same bytes. Options may
come before or after the tool. A refusal is one ``error:`` line on stderr, exit 1, nothing
written; a wrong command line exits 2; Ctrl-C and an unexpected failure follow the look
(``poisson_trace.look``).

The readers are found from ``READERS`` by presence: a module that is not in the install is
not in ``--help`` and its name is refused. A reader module defines ``add_arguments(parser)``
and ``read(ns) -> Run``, and may define ``DESCRIPTION`` (its help's paragraph), ``EXAMPLE``
(a command its help and the import's show) and ``usage(ns) -> str | None`` (why a command line
its parser takes is still wrong, exit 2). It may also define ``FURTHER``, a mapping from one
further command name to ``(add_arguments, run)`` with ``run(ns) -> int``, for a command that
writes no store and takes its own flags.

``proofload`` is imported by the writer alone, and the writer is imported after the check that
``proofload`` is present at the version this package reads, which runs once the command line
is read and before any file is opened.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING, Any

from poisson_trace import look
from poisson_trace.ingest.cut import MET, MISSED
from poisson_trace.ingest.rows import Refusal, Run, zone_of
from poisson_trace.look import count
from poisson_trace.names import import_name_refusal

if TYPE_CHECKING:
    from poisson_trace.ingest.writer import Written

READERS: tuple[str, ...] = ("deepeval", "ragas", "table", "junit", "langsmith", "otel", "lemma")
SCHEMA = "poisson-trace.import/1"
# the command as every help, refusal and next line names it, under either spelling
PROG = "poisson-trace import"

_DOES = f"{PROG} writes runs"
_Further = Callable[[argparse.Namespace], int]
# the command's own option, which stays where it is written; --help before a tool is that
# tool's help, as every other option before a tool is that tool's
_KEPT = ("--version",)

_ABOUT = """\
Read the result files another tool already wrote and write them as one new run of a store in
Prove's format, for Poisson Trace's verbs to read. One import is one version: import the old
version and the new one into the same store, then compare them with poisson-trace fix-check.
A store is the folder Prove keeps runs in; a case is one test case or question of the tool's
files, and the rows that share a case are its repeats.
"""


def present() -> tuple[str, ...]:
    """The readers whose modules are in the install, in the order ``READERS`` names them."""
    return tuple(name for name in READERS if find_spec(f"{__package__}.{name}") is not None)


def _examples(commands: Sequence[str]) -> str | None:
    return "examples:\n" + "".join(f"  {c}\n" for c in commands) if commands else None


def _build_parser(
    present: Sequence[str],
) -> tuple[look.Parser, dict[str, look.Parser], dict[str, _Further]]:
    modules = {name: import_module(f"{__package__}.{name}") for name in present}
    shown = [module.EXAMPLE for module in modules.values() if hasattr(module, "EXAMPLE")]
    parser = look.Parser(prog=PROG, description=_ABOUT, epilog=_examples(shown))
    parser.add_argument(
        "--version", action="store_true", help="print the versions of Trace, Prove and Python"
    )
    parser.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)
    tools = parser.add_subparsers(dest="tool", metavar="TOOL", title="tools")
    subs: dict[str, look.Parser] = {}
    further: dict[str, _Further] = {}
    for name, module in modules.items():
        about = (module.__doc__ or name).strip().splitlines()[0]
        example = getattr(module, "EXAMPLE", None)
        sub = tools.add_parser(
            name,
            help=about,
            description=getattr(module, "DESCRIPTION", about),
            epilog=_examples([example] if example else []),
        )
        sub.add_argument(
            "files", nargs="+", metavar="FILE", help="a result file of the tool's; repeatable"
        )
        sub.add_argument(
            "--store",
            metavar="ROOT",
            help="the store to write the run into, made if it is not there, or the name of a "
            "store trace.toml names (default: the store trace.toml names)",
        )
        sub.add_argument(
            "--config",
            metavar="PATH",
            help="the config file to read (default: trace.toml in the current folder, if any)",
        )
        sub.add_argument(
            "--run",
            required=True,
            metavar="NAME",
            help="the new run's name, which the store must not hold yet (no default)",
        )
        sub.add_argument(
            "--started",
            metavar="ISO-8601",
            help="when this version's run started, with its zone, such as "
            "2026-09-05T18:54:07Z (default: read from the files)",
        )
        sub.add_argument(
            "--json", action="store_true", help="print the summary as JSON instead of text"
        )
        sub.add_argument(
            "--debug",
            action="store_true",
            help="on an unexpected failure, print its details on stderr as well as in the log",
        )
        module.add_arguments(sub)
        subs[name] = sub
        for extra, (add, run) in getattr(module, "FURTHER", {}).items():
            about = (run.__doc__ or extra).strip().splitlines()[0]
            subs[extra] = tools.add_parser(extra, help=about, description=about)
            add(subs[extra])
            further[extra] = run
    return parser, subs, further


def parsers() -> tuple[look.Parser, dict[str, look.Parser], dict[str, _Further]]:
    """The import's parser, each reader's and each further command's, for this install."""
    return _build_parser(present())


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
    if "outcome_column" in declared:
        values = _or([json.dumps(v, ensure_ascii=False) for v in declared["failed"]])
        return f"its {declared['outcome_column']} column reads {values}"
    if declared.get("cut") == "recorded":
        return f"DeepEval marked its {declared['metric']} metric as not passed"
    scored = declared.get("score_column", declared.get("metric"))
    side = "below" if declared.get("side") == "below" else "above"
    return f"its {scored} score is {side} {_value(declared['cut'])}"


def _import_flags(declared: Mapping[str, Any]) -> list[str]:
    """The flags that read another file as this one was read, from what was declared."""
    words: list[str] = []
    for key, flag in (
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
    return words


def _extension(name: str) -> str:
    """The extensions that say a file's format: ``.csv``, ``.jsonl.gz``."""
    lowered = name.lower()
    for ext in (".csv", ".jsonl", ".json", ".parquet", ".xml"):
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
    other = "OTHER" + _extension(files[0])
    command = look.command(
        "poisson-trace",
        "import",
        d["tool"],
        other,
        *reach,
        "--run OTHER",
        *_import_flags(d["declared"]),
    )
    whose = "file" if len(files) == 1 else "files"
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
        said.append("Its start time is a time the tool wrote in the file.")
    elif source in _STARTED_SAID:
        said.append(_STARTED_SAID[source])
    if "outcome_column" in d["declared"]:
        said.append(
            f"Every other value of the {d['declared']['outcome_column']} column counts as a pass."
        )
    if tool == "junit":
        said.append("A skipped test has no outcome and is left out.")
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
        "- declared: " + " · ".join(f"{k} {_value(v)}" for k, v in declared.items()),
        f"- started: {started['at']} · from: {source}",
        f"- rows {count(d['rows'])} · cases {count(d['cases'])} · repeats of a case: smallest "
        f"{count(d['repeats']['min'])}, largest {count(d['repeats']['max'])}",
        "- outcomes: " + " · ".join(f"{word} {count(n)}" for word, n in d["outcomes"].items()),
        "- rows with no outcome: "
        + (" · ".join(f"{reason} {count(n)}" for reason, n in none.items()) if none else "0"),
        *counted,
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


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    return look.run(PROG, args, _main, (Refusal,))


def _main(session: look.Session) -> int:
    parser, subs, further = parsers()
    every = [parser, *subs.values()]
    valued = look.takes_value(every)
    if look.asks(session.argv, valued, "--version"):
        look.out(look.version_line())
        return look.DONE
    args, at = look.verb_first(session.argv, valued, _KEPT, look.options(every), PROG)
    if at is not None and args[at] not in subs:
        raise Refusal(
            f"unknown tool {look.shown(args[at])}; this install reads: "
            f"{', '.join(subs) or 'nothing'}",
            f"{PROG} --help",
        )
    ns, extra = parser.parse_known_args(args)
    if ns.tool is None:
        raise look.Usage(
            f"no tool was given; this install reads: {', '.join(subs) or 'nothing'}",
            f"{PROG} --help",
        )
    if extra:
        subs[ns.tool].error(f"unrecognized arguments: {' '.join(extra)}")
    if ns.tool not in further:
        wrong = getattr(import_module(f"{__package__}.{ns.tool}"), "usage", None)
        said = wrong(ns) if wrong is not None else None
        if said is not None:
            subs[ns.tool].error(said)
    session.debug = bool(getattr(ns, "debug", False))
    if getattr(ns, "json", False):
        session.render = _stopped_json
    form = "target"
    if ns.tool not in further:
        from poisson_trace import config

        settings = config.load(ns.config)
        form = settings.names_from if settings is not None else "target"
        typed = ns.store
        if typed is not None and settings is not None and typed in settings.named:
            ns.store = settings.named[typed]
        elif typed is None and settings is not None:
            ns.store = settings.store
        if ns.store is None:
            gives = (
                "no trace.toml here gives one"
                if settings is None
                else f"{settings.shown} names none"
            )
            raise look.Usage(f"--store is required: {gives}", f"{subs[ns.tool].prog} --help")
        # what the next command carries to reach the same store
        reach = [look.option("--store", typed)] if typed is not None else []
        reach += list(settings.flags()) if settings is not None else []
        # a run's name is its folder and the word for it: checked before Prove is asked anything
        hole = import_name_refusal(ns.run)
        if hole is not None:
            raise Refusal(hole)
    refusal = look.prove_refusal(_DOES)
    if refusal is not None:
        raise Refusal(refusal, look.INSTALL_PROVE)
    if ns.tool in further:
        return further[ns.tool](ns)
    store = Path(ns.store)
    try:
        held = (store / ns.run).exists()
    except OSError:
        # a name the system cannot look up is never this import's to call partial
        held = True
    session.stopped = lambda: _stopped(store, ns.run, held)
    given = None if ns.started is None else _started(ns.started)
    run: Run = import_module(f"{__package__}.{ns.tool}").read(ns)
    if given is not None:
        run = replace(run, started=given, started_from="given", started_note=None)
    if not run.rows:
        raise Refusal("no row was read from the files, so there is no run to write")
    if all(row.outcome is None for row in run.rows):
        raise Refusal(
            f"none of the {count(len(run.rows))} rows read has an outcome, so there is nothing "
            "to compare and no run was written"
        )
    from poisson_trace.ingest.writer import write

    written = write(run, store, form)
    data = _summary(run, written, str(ns.store), reach)
    look.out(
        json.dumps(data, indent=2, allow_nan=False) + "\n"
        if ns.json
        else _markdown(data, run.cells, reach)
    )
    return look.DONE


def _stopped_json(line: str) -> str:
    """The stopped line as the import's JSON document: stdout stays one document."""
    verdict, _, sentence = line.partition("  ")
    doc = {"schema": SCHEMA, "verdict": verdict, "sentence": sentence, "next": None}
    return json.dumps(doc, indent=2) + "\n"


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


if __name__ == "__main__":
    raise SystemExit(main())
