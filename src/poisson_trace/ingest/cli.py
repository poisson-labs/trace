"""The import: ``poisson-trace import``, and the console script ``poisson-trace-import``.

``poisson-trace import TOOL FILE [FILE ...] --store ROOT --run NAME`` reads the files with the
tool's reader, writes one new run through the writer, and prints a summary that ends with the
Trace command to run next. ``poisson-trace-import`` is the same command under its first name:
the main command hands it every word but ``import``, so both print the same bytes. Options may
come before or after the tool. A refusal is one ``error:`` line on stderr, exit 1, nothing
written; a wrong command line exits 2; Ctrl-C and an unexpected failure follow the look
(``poisson_trace.look``).

A thin caller of the Python API (spec section 11.8): it reads the command line, calls
``poisson_trace.api.import_run`` once with what was typed, and prints what the result gives.
The readers, their options and the import's work are ``poisson_trace.ingest.importing``,
reached through ``api``; ``READERS``, ``module_name``, ``reader`` and ``present`` are kept
here under their old names for what imports them.

A config's ``[signals]`` field mappings stand in for a reader's flags when the command line
leaves them out (SA8): they are filled into the command line before it is parsed, so each
reader's help and its refusal of a missing flag are as they were, and a flag given wins.
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from poisson_trace import api, look

_Further = Callable[[argparse.Namespace], int]

SCHEMA = "poisson-trace.import/1"

PROG = "poisson-trace import"

# the command's own option, which stays where it is written
_KEPT = ("--version",)

_ABOUT = """\
Read the result files another tool already wrote and write them as one new run of a store in
Prove's format, for Poisson Trace's verbs to read. One import is one version: import the old
version and the new one into the same store, then compare them with poisson-trace fix-check.
A store is the folder Prove keeps runs in; a case is one test case or question of the tool's
files, and the rows that share a case are its repeats.

A folder of results may be given in place of the files, and in place of the tool too
(poisson-trace import ./results --store trace-store): its files are found by the readers'
own detectors and read as one run, named after the folder unless --run names it.
"""

READERS: tuple[str, ...] = api._readers()


def module_name(tool: str) -> str:
    """The reader module of the tool ``tool``: its name with ``-`` as ``_``."""
    return api._module_name(tool)


def reader(tool: str) -> Any:
    """The reader module of the tool ``tool``."""
    return api._reader(tool)


def present() -> tuple[str, ...]:
    """The readers whose modules are in the install, in the order ``READERS`` names them."""
    return api._present()


def _examples(commands: Sequence[str]) -> str | None:
    return "examples:\n" + "".join(f"  {c}\n" for c in commands) if commands else None


def _build_parser(
    present: Sequence[str],
) -> tuple[look.Parser, dict[str, look.Parser], dict[str, _Further]]:
    modules = {name: reader(name) for name in present}
    shown = [module.EXAMPLE for module in modules.values() if hasattr(module, "EXAMPLE")]
    parser = look.Parser(prog=PROG, description=_ABOUT, epilog=_examples(shown))
    parser.add_argument(
        "--version", action="store_true", help="print the versions of Trace, Prove and Python"
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="print plain text with no colour, as on a pipe; may come before or after the tool",
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
            "files",
            nargs="+",
            metavar="FILE",
            help="a result file of the tool's, repeatable, or one folder of them: its files of "
            "the tool's are read as one run, and a folder holding more than one run is refused",
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
            metavar="NAME",
            help="the new run's name, which the store must not hold yet (default: the folder's "
            "name, for a folder; for files there is none, and it is required)",
        )
        sub.add_argument(
            "--started",
            metavar="ISO-8601",
            help="when this version's run started, with its zone, such as "
            "2026-09-05T18:54:07Z (default: read from the files)",
        )
        sub.add_argument(
            "--verdicts",
            metavar="FILE",
            help="a .csv or .jsonl file of outcomes, scores, failure kinds and feedback to join "
            "onto the rows, by case or else by input; it fills what the files left out and is "
            "refused where it differs from what they recorded (no default)",
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


@functools.cache
def parsers() -> tuple[look.Parser, dict[str, look.Parser], dict[str, _Further]]:
    """The import's parser, each reader's and each further command's, for this install,
    built once (as ``cli.parsers`` is)."""
    return _build_parser(present())


# the flags every tool's parser has, the import's own: never a reader's option
_OWN = ("files", "store", "config", "run", "started", "verdicts", "json", "debug", "help")


def _config_word(args: Sequence[str]) -> str | None:
    """The value ``--config`` carries on the command line, the last when it is given twice."""
    found = None
    words = list(args)
    for i, word in enumerate(words):
        if word == "--config" and i + 1 < len(words):
            found = words[i + 1]
        elif word.startswith("--config="):
            found = word[len("--config=") :]
    return found


def _with_stand_ins(args: Sequence[str], tool: str, filled: Mapping[str, Any]) -> list[str]:
    """The command line with the flags ``[signals]`` stands in for (``filled``, by dest)
    filled in where the line leaves them out. A cut from the config with no side on the line
    reads below. For a table, the form the line reads (its outcome column, or its score
    column) is the one filled, and the outcome form when the line says neither and the config
    gives both."""
    given = {w.split("=", 1)[0] for w in args if w.startswith("--")}
    held = dict(filled)
    if tool == "table":
        by_outcome = bool({"--outcome-column", "--failed"} & given)
        by_score = bool({"--score-column", "--cut", "--below", "--above"} & given)
        if by_outcome or (not by_score and "outcome_column" in held):
            held.pop("score_column", None)
            held.pop("cut", None)
        if by_score:
            held.pop("outcome_column", None)
    out = list(args)
    for dest, value in held.items():
        flag = "--" + dest.replace("_", "-")
        if flag in given:
            continue
        if dest == "cut":
            out += ["--cut", repr(float(value))]
            if not {"--below", "--above"} & given:
                out.append("--below")
        else:
            out += [flag, str(value)]
    return out


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    return look.run(PROG, args, _main, ())


def _main(session: look.Session) -> int:
    parser, subs, further = parsers()
    every = [parser, *subs.values()]
    valued = look.takes_value(every)
    if look.asks(session.argv, valued, "--version"):
        look.out(look.version_line())
        return look.DONE
    args, at = look.verb_first(session.argv, valued, _KEPT, look.options(every), PROG)
    try:
        return _read(session, parser, subs, further, args, at)
    except api.Refusal as e:
        raise _raised(e) from None


def _read(
    session: look.Session,
    parser: look.Parser,
    subs: Mapping[str, look.Parser],
    further: Mapping[str, _Further],
    args: list[str],
    at: int | None,
) -> int:
    if at is not None and args[at] not in subs and api._is_folder(args[at]):
        # a folder in the tool's place: the tool is the one whose files it holds
        args = [*args[:at], api._import_folder_tool(args[at]), *args[at:]]
    if at is not None and args[at] not in subs:
        raise look.Refused(
            f"unknown tool {look.shown(args[at])}; this install reads: "
            f"{', '.join(subs) or 'nothing'}",
            f"{PROG} --help",
        )
    config: Any = None
    if at is not None and args[at] not in further:
        # the config is read before the command line is parsed, so that what [signals] stands
        # in for is on the line when the reader's required flags are checked
        word = _config_word(args)
        config = api.load_config(word) if word is not None else api._config_here()
        if config is not None:
            filled = api._stand_ins(args[at], config, args)
            if filled:
                args = _with_stand_ins(args, args[at], filled)
        if word is not None:
            config = word
    ns, extra = parser.parse_known_args(args)
    if ns.tool is None:
        raise look.Usage(
            f"no tool was given; this install reads: {', '.join(subs) or 'nothing'}",
            f"{PROG} --help",
        )
    if extra:
        subs[ns.tool].error(f"unrecognized arguments: {' '.join(extra)}")
    folders = [] if ns.tool in further else [f for f in ns.files if api._is_folder(f)]
    if ns.tool not in further and not folders and ns.run is None:
        subs[ns.tool].error("the following arguments are required: --run")
    if len(folders) > 1 or (folders and len(ns.files) > 1):
        subs[ns.tool].error(
            "a folder is given alone, in place of the files: give one folder, or files"
        )
    if ns.tool not in further:
        said = api._import_usage(ns)
        if said is not None:
            subs[ns.tool].error(said)
    session.debug = bool(getattr(ns, "debug", False))
    if getattr(ns, "json", False):
        session.render = _stopped_json
    if ns.tool in further:
        return further[ns.tool](ns)
    typed = {w.split("=", 1)[0] for w in args if w.startswith("--")}
    kwargs: dict[str, Any] = {}
    for action in subs[ns.tool]._actions:
        if not action.option_strings or action.dest not in ("run", "started", "verdicts"):
            continue
        if set(action.option_strings) & typed:
            kwargs[action.dest] = getattr(ns, action.dest)
    if config is not None:
        kwargs["config"] = config
    kwargs.update(_reader_flags(subs[ns.tool], ns, args))
    result = api.import_run(ns.store, ns.tool, list(ns.files), **kwargs)
    look.out(result.to_json() if ns.json else result.to_markdown())
    return int(result.exit_code)


def _reader_flags(
    parser: look.Parser, ns: argparse.Namespace, args: Sequence[str]
) -> dict[str, Any]:
    """The reader's flags typed, each as its keyword with the value the parser gave, in the
    order typed."""
    by_flag = {o: a for a in parser._actions if a.dest not in _OWN for o in a.option_strings}
    out: dict[str, Any] = {}
    for word in args:
        if word.startswith("-") and word != "-":
            action = by_flag.get(word.split("=", 1)[0])
            if action is not None:
                name = max(action.option_strings, key=len).lstrip("-").replace("-", "_")
                out[name] = getattr(ns, action.dest)
    return out


def _raised(e: api.Refusal) -> BaseException:
    """The API's refusal as the command prints it: its notes first, then one ``error:`` line
    with the commands under it, at its exit code."""
    for note in e.notes:
        look.err(f"note: {note}\n")
    if e.exit_code == look.USAGE:
        return look.Usage(e.message, *e.next)
    if e.exit_code == look.FAILED:
        return look.Failed(e.message)
    return look.Refused(e.message, *e.next)


def _stopped_json(line: str) -> str:
    """The stopped line as the import's JSON document: stdout stays one document."""
    verdict, _, sentence = line.partition("  ")
    doc = {"schema": SCHEMA, "verdict": verdict, "sentence": sentence, "next": None}
    return json.dumps(doc, indent=2) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
