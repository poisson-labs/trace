"""The console script ``poisson-trace-import``.

``poisson-trace-import TOOL FILE [FILE ...] --store ROOT --run NAME`` reads the files with
the tool's reader, writes one new run through the writer, and prints a summary that ends with
the Trace command to run next. Options may come before or after the tool. A refusal is one
``error:`` line on stderr, exit 1, nothing written; a wrong command line exits 2; Ctrl-C and an
unexpected failure follow the look (``poisson_trace.look``).

The readers are found from ``READERS`` by presence: a module that is not in the install is
not in ``--help`` and its name is refused. A reader module defines ``add_arguments(parser)``
and ``read(ns) -> Run``, and may define ``DESCRIPTION`` (its help's paragraph) and ``EXAMPLE``
(a command its help and the import's show). It may also define ``FURTHER``, a mapping from one
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
from poisson_trace.ingest.cut import MISSED
from poisson_trace.ingest.rows import Refusal, Run
from poisson_trace.look import count
from poisson_trace.names import import_name_refusal

if TYPE_CHECKING:
    from poisson_trace.ingest.writer import Written

READERS: tuple[str, ...] = ("deepeval", "ragas", "langsmith", "otel", "lemma")
SCHEMA = "poisson-trace.import/1"

_DOES = "poisson-trace-import writes runs"
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


def _present() -> tuple[str, ...]:
    return tuple(name for name in READERS if find_spec(f"{__package__}.{name}") is not None)


def _examples(commands: Sequence[str]) -> str | None:
    return "examples:\n" + "".join(f"  {c}\n" for c in commands) if commands else None


def _build_parser(
    present: Sequence[str],
) -> tuple[look.Parser, dict[str, look.Parser], dict[str, _Further]]:
    modules = {name: import_module(f"{__package__}.{name}") for name in present}
    shown = [module.EXAMPLE for module in modules.values() if hasattr(module, "EXAMPLE")]
    parser = look.Parser(prog="poisson-trace-import", description=_ABOUT, epilog=_examples(shown))
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
            required=True,
            metavar="ROOT",
            help="the store to write the run into, made if it is not there (no default)",
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


def _zone(started: str) -> tuple[str, str]:
    """The name and the offset from UTC of this machine's zone at that instant."""
    local = datetime.fromisoformat(started.replace("Z", "+00:00")).astimezone()
    offset = local.strftime("%z")
    return local.strftime("%Z"), f"UTC{offset[:3]}:{offset[3:5]}"


def _sentence(written: Written, store: str) -> str:
    """The run, the store, the rows, the cases and their repeats, and the outcomes."""
    low, high = written.repeats_min, written.repeats_max
    repeats = f"{count(low)} repeats each"
    if low != high:
        repeats = f"{count(low)} to {count(high)} repeats"
    outcomes = ", ".join(f"{word} {count(n)}" for word, n in written.outcomes.items())
    none = sum(written.no_outcome.values())
    no_outcome = f", {count(none)} with no outcome" if none else ""
    return (
        f"wrote run {written.run} to {store}: {count(written.rows)} rows, "
        f"{count(written.cases)} cases, {repeats}; {outcomes}{no_outcome}"
    )


def _summary(run: Run, written: Written, store: str) -> dict[str, Any]:
    started: dict[str, Any] = {"at": run.started, "from": run.started_from}
    if run.started_from == "file name":
        name, offset = _zone(run.started)
        started["zone"] = {"name": name, "offset": offset}
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
            f"poisson-trace fix-check OLD NEW --store {store} --event {MISSED} --inputs all "
            f"--max-mde X  # {written.run} is OLD or NEW"
        ),
    }


def _value(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value)


def _markdown(d: Mapping[str, Any]) -> str:
    started = d["started"]
    source = started["from"]
    if "zone" in started:
        zone = started["zone"]
        source += (
            ": the time in the first file's name, which is when the file was saved, read in "
            f"this machine's zone ({zone['name']}, {zone['offset']})"
        )
    none = d["no_outcome"]
    lines = [
        f"{d['verdict']}  {d['sentence']}",
        "",
        f"# Poisson Trace · import · {d['run']}",
        "",
        f"- run written: {d['run']} · store: {d['store']}",
        f"- tool: {d['tool']}",
        *[f"- file: {f['name']} · sha256 {f['sha256']}" for f in d["files"]],
        "- declared: " + " · ".join(f"{k} {_value(v)}" for k, v in d["declared"].items()),
        f"- started: {started['at']} · from: {source}",
        f"- rows {count(d['rows'])} · cases {count(d['cases'])} · repeats of a case: smallest "
        f"{count(d['repeats']['min'])}, largest {count(d['repeats']['max'])}",
        "- outcomes: " + " · ".join(f"{word} {count(n)}" for word, n in d["outcomes"].items()),
        "- rows with no outcome: "
        + (" · ".join(f"{reason} {count(n)}" for reason, n in none.items()) if none else "0"),
        *[f"- {label}: {count(n)}" for label, n in d["counts"].items()],
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
    return look.run("poisson-trace-import", args, _main, (Refusal,))


def _main(session: look.Session) -> int:
    present = _present()
    parser, subs, further = _build_parser(present)
    parsers = [parser, *subs.values()]
    valued = look.takes_value(parsers)
    if look.asks(session.argv, valued, "--version"):
        look.out(look.version_line())
        return look.DONE
    args, at = look.verb_first(
        session.argv, valued, _KEPT, look.options(parsers), "poisson-trace-import"
    )
    if at is not None and args[at] not in subs:
        raise Refusal(
            f"unknown tool {look.shown(args[at])}; this install reads: "
            f"{', '.join(subs) or 'nothing'}",
            "poisson-trace-import --help",
        )
    ns, extra = parser.parse_known_args(args)
    if ns.tool is None:
        raise look.Usage(
            f"no tool was given; this install reads: {', '.join(subs) or 'nothing'}",
            "poisson-trace-import --help",
        )
    if extra:
        subs[ns.tool].error(f"unrecognized arguments: {' '.join(extra)}")
    session.debug = bool(getattr(ns, "debug", False))
    if getattr(ns, "json", False):
        session.render = _stopped_json
    if ns.tool not in further:
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
        run = replace(run, started=given, started_from="given")
    if not run.rows:
        raise Refusal("no row was read from the files, so there is no run to write")
    if all(row.outcome is None for row in run.rows):
        raise Refusal(
            f"none of the {count(len(run.rows))} rows read has an outcome, so there is nothing "
            "to compare and no run was written"
        )
    from poisson_trace.ingest.writer import write

    written = write(run, store)
    data = _summary(run, written, str(ns.store))
    look.out(json.dumps(data, indent=2, allow_nan=False) + "\n" if ns.json else _markdown(data))
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
