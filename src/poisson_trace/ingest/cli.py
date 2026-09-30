"""The console script ``poisson-trace-import``.

``poisson-trace-import TOOL FILE [FILE ...] --store ROOT --run NAME`` reads the files with
the tool's reader, writes one new run through the writer, and prints a summary that ends with
the Trace command to run next. A refusal is one sentence on stderr, exit 1, nothing written.

The readers are found from ``READERS`` by presence: a module that is not in the install is
not in ``--help`` and its name is refused. A reader module defines ``add_arguments(parser)``
and ``read(ns) -> Run``. It may also define ``FURTHER``, a mapping from one further command
name to ``(add_arguments, run)`` with ``run(ns) -> int``, for a command that writes no store
and takes its own flags.

``proofload`` is imported by the writer alone, and the writer is imported inside ``main``
after the check that ``proofload`` is present at the pinned version, so the check runs before
any file is opened.
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
from typing import Any

from poisson_trace.ingest.cut import MISSED
from poisson_trace.ingest.rows import Refusal, Run

READERS: tuple[str, ...] = ("deepeval", "ragas", "langsmith", "otel", "lemma")
SCHEMA = "poisson-trace.import/1"

_DOES = "poisson-trace-import writes a store in Prove's format"
_Further = Callable[[argparse.Namespace], int]


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Any:
        raise Refusal(f"argument error: {message}")


def _present() -> tuple[str, ...]:
    return tuple(name for name in READERS if find_spec(f"{__package__}.{name}") is not None)


def _build_parser(present: Sequence[str]) -> tuple[_Parser, dict[str, _Further]]:
    parser = _Parser(
        prog="poisson-trace-import",
        description=(
            "Read the result files another tool already wrote and write them as one new run "
            "of a store in Prove's format, for Poisson Trace's verbs to read. One import is "
            "one version."
        ),
    )
    tools = parser.add_subparsers(dest="tool", required=True, metavar="TOOL")
    further: dict[str, _Further] = {}
    for name in present:
        module = import_module(f"{__package__}.{name}")
        sub = tools.add_parser(name, help=(module.__doc__ or name).strip().splitlines()[0])
        sub.add_argument("files", nargs="+", metavar="FILE", help="a result file; repeatable")
        sub.add_argument("--store", required=True, metavar="ROOT", help="the root of the store")
        sub.add_argument("--run", required=True, metavar="NAME", help="the new run's name")
        sub.add_argument(
            "--started",
            metavar="ISO-8601",
            help="when this version's run started, with its zone; else read from the files",
        )
        sub.add_argument("--json", action="store_true", help="print the summary as JSON")
        module.add_arguments(sub)
        for extra, (add, run) in getattr(module, "FURTHER", {}).items():
            add(tools.add_parser(extra, help=(run.__doc__ or extra).strip().splitlines()[0]))
            further[extra] = run
    return parser, further


def _started(text: str) -> str:
    """``--started`` as UTC with a ``Z``. A time with no zone is refused: the gap Trace prints
    between two runs is only as good as the two instants it is taken from."""
    try:
        at = datetime.fromisoformat(text)
    except ValueError:
        raise Refusal(
            f"--started takes an ISO-8601 time such as 2026-09-05T18:54:07Z, not {text!r}"
        ) from None
    if at.tzinfo is None or at.utcoffset() is None:
        raise Refusal(
            f"--started {text} carries no zone; end it with Z for UTC or with an offset such "
            "as +02:00"
        )
    return at.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _zone(started: str) -> tuple[str, str]:
    """The name and the offset from UTC of this machine's zone at that instant."""
    local = datetime.fromisoformat(started.replace("Z", "+00:00")).astimezone()
    offset = local.strftime("%z")
    return local.strftime("%Z"), f"UTC{offset[:3]}:{offset[3:5]}"


def _summary(run: Run, written: Any, store: str) -> dict[str, Any]:
    started: dict[str, Any] = {"at": run.started, "from": run.started_from}
    if run.started_from == "file name":
        name, offset = _zone(run.started)
        started["zone"] = {"name": name, "offset": offset}
    return {
        "schema": SCHEMA,
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
        f"# Poisson Trace · import · {d['run']}",
        "",
        f"- run written: {d['run']} · store: {d['store']}",
        f"- tool: {d['tool']}",
        *[f"- file: {f['name']} · sha256 {f['sha256']}" for f in d["files"]],
        "- declared: " + " · ".join(f"{k} {_value(v)}" for k, v in d["declared"].items()),
        f"- started: {started['at']} · from: {source}",
        f"- rows {d['rows']} · cases {d['cases']} · repeats of a case: smallest "
        f"{d['repeats']['min']}, largest {d['repeats']['max']}",
        "- outcomes: " + " · ".join(f"{word} {n}" for word, n in d["outcomes"].items()),
        "- rows with no outcome: "
        + (" · ".join(f"{reason} {n}" for reason, n in none.items()) if none else "0"),
        *[f"- {label}: {n}" for label, n in d["counts"].items()],
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
    from poisson_trace.cli import _check_prove

    line = _check_prove(_DOES)
    if line is not None:
        sys.stderr.write(line + "\n")
        return 1
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        present = _present()
        parser, further = _build_parser(present)
        if args and not args[0].startswith("-") and args[0] not in (*present, *further):
            raise Refusal(
                f"unknown tool {args[0]}; this install reads: "
                f"{', '.join((*present, *further)) or 'nothing'}"
            )
        ns = parser.parse_args(args)
        if ns.tool in further:
            return further[ns.tool](ns)
        given = None if ns.started is None else _started(ns.started)
        run: Run = import_module(f"{__package__}.{ns.tool}").read(ns)
        if given is not None:
            run = replace(run, started=given, started_from="given")
        if not run.rows:
            raise Refusal("no row was read from the files, so there is no run to write")
        if all(row.outcome is None for row in run.rows):
            raise Refusal(
                f"none of the {len(run.rows)} rows read has an outcome, so there is nothing "
                "to compare and no run was written"
            )
        from poisson_trace.ingest.writer import write

        written = write(run, Path(ns.store))
    except Refusal as e:
        sys.stderr.write(" ".join(str(e).split()) + "\n")
        return 1
    data = _summary(run, written, str(ns.store))
    text = json.dumps(data, indent=2, allow_nan=False) + "\n" if ns.json else _markdown(data)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
