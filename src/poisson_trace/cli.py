"""The console script: ``poisson-trace init``, ``runs``, ``name``, ``where``, ``compare``,
``fix-check``, ``changes``, ``handover``, ``import`` and ``doctor``.

``import`` is the import's own command (``poisson_trace.ingest.cli``), handed every word of the
command line but ``import`` itself, so that it prints what ``poisson-trace-import`` prints.

The command line is read first, so ``--help`` and ``--version`` need nothing installed; the
check that ``poisson_prove`` is present at the version this package reads runs next, and
``poisson_prove`` is imported inside the verbs and nowhere at module level. Every line printed,
every refusal and every exit code is the look's (``look.py``, ``docs/cli-look.md``).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from poisson_trace import look
from poisson_trace.look import count

# The by-input reading's seeded sign assignments, when there are too many to enumerate.
_DRAWS = 100_000
# The most bootstrap resamples where takes: a thousand times the default.
_MOST_BOOT = 1_000_000
_DOES = "Poisson Trace reads stored runs"
_VERBS = ("runs", "name", "where", "compare", "fix-check", "changes", "handover")
_NAMED = "init, runs, name, where, compare, fix-check, changes, handover, import and doctor"
# the verbs that count failures, and so need them from a flag or the config
_COUNTING = ("where", "compare", "fix-check", "changes")
# the complete runs the listing shows, newest first, before it says how many more there are
_LISTED = 50
# the command's own option, which stays where it is written; --help before a verb is that
# verb's help, as every other option before a verb is that verb's
_KEPT = ("--version",)


class _Refusal(look.Refused):
    """One sentence, exit 1, and the commands to run next under it, if any."""


_ABOUT = """\
Poisson Trace reads the runs Prove has stored and says where in the workflow their episodes
died, and whether a change made them fail less. A store is the folder Prove writes its runs
into; a run is one stored sweep, and its episodes are its rows. Every number prints with what
the runs could not have detected.

A run is named by a name you gave it with poisson-trace name; by the name it has from its
manifest, the record Prove keeps of it (its target, the day it started in UTC and a letter, such
as "tau2-airline 2026-09-15 a"); by latest or previous, the newest complete runs, or
latest:TARGET and previous:TARGET, a target's ("latest:tau2-airline"); by its number in the
runs listing ("#3"); or by its full id.

Results another tool wrote (DeepEval, Ragas, a table of results, JUnit reports) are read in
with poisson-trace import. where, compare, fix-check and changes also take a folder in a run's
place, when no stored run answers to the word: a run Prove stored, a store of one run, or one
tool's result files, read with the flags poisson-trace import takes for that tool. Nothing is
written; the folder's name is the run's name in the report.

To begin, run poisson-trace init: it finds the results already here, asks what counts as a
failure and writes trace.toml, from which every verb then takes its store and its failures.
Then poisson-trace doctor says whether this environment is ready.
"""


def _example(*commands: str) -> str:
    return "examples:\n" + "".join(f"  {command}\n" for command in commands)


_STORE_HELP = (
    "the folder Prove stored the runs in, or the name of a store trace.toml names (default: the "
    "store trace.toml names)"
)
_CONFIG_HELP = "the config file to read (default: trace.toml in the current folder, if any)"
_RUN_HELP = 'by its name, latest, previous or its number in the runs listing ("#3")'
_RUN_OR_FOLDER = (
    'by its name, latest, previous or its number in the runs listing ("#3"), or a folder of '
    "results"
)
_SAVE_HELP = (
    "save the verdict as an artifact in the runs' store, under .poisson/artifacts (no default: "
    "nothing is written without it)"
)
_OUT_HELP = (
    "also write the saved verdict as a handover bundle into DIR, created; a DIR that exists is "
    "refused without --force (no default)"
)
_VERDICTS_HELP = (
    "a .csv or .jsonl of verdicts (case, outcome, score, failure_kind) joined onto both runs "
    "where they recorded none; nothing is written (no default)"
)


def _build_parser() -> tuple[look.Parser, dict[str, look.Parser]]:
    parser = look.Parser(
        prog="poisson-trace",
        description=_ABOUT,
        epilog=_example(
            "poisson-trace runs --store proofload-runs --event unsolved",
            "poisson-trace where previous --store proofload-runs --event unsolved --at 20",
            "poisson-trace fix-check previous latest --store proofload-runs --event unsolved \\",
            "    --inputs all --max-mde 0.2",
        ),
    )
    parser.add_argument(
        "--version", action="store_true", help="print the versions of Trace, Prove and Python"
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="print plain text with no colour, as on a pipe; may come before or after the verb",
    )
    parser.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)
    verbs = parser.add_subparsers(dest="verb", metavar="VERB", title="verbs")
    init = _init_parser(verbs)

    runs = verbs.add_parser(
        "runs",
        help="the runs of a store, newest first, with their names and numbers",
        description=(
            "Lists the runs of a store, newest first: each complete run's number, its name, its\n"
            "rows, how many of them failed for the --event names, whether any row carries a\n"
            "trace (where and compare read traces; fix-check and changes do not need them), when\n"
            "it started (UTC) and its status. The newest 50 complete runs are listed. A run's\n"
            'number, such as "#1", names it to every verb.'
        ),
        epilog=_example("poisson-trace runs --store proofload-runs --event unsolved"),
    )
    runs.add_argument("--store", metavar="ROOT", help=_STORE_HELP)
    runs.add_argument(
        "--event",
        action="append",
        metavar="NAME",
        help="an outcome that counts as a failure in the failed column; repeatable (default: "
        "the failures trace.toml names, else none, and the column is not counted)",
    )
    runs.add_argument("--config", metavar="PATH", help=_CONFIG_HELP)
    runs.add_argument(
        "--all",
        action="store_true",
        help="list every run, partial runs and those past the newest 50 included",
    )

    name = verbs.add_parser(
        "name",
        help="give a stored run a name of yours, take it back, or list the names",
        description=(
            "Gives a stored run a name of yours, which every verb then takes for the run and\n"
            "every report shows. The names are kept in trace-names.toml at the store's root; no\n"
            "run's own files change. --forget takes a name back, and the run goes by the name it\n"
            "has from its manifest again. --list shows the names of yours."
        ),
        epilog=_example(
            'poisson-trace name previous "tau2 old re-run" --store proofload-runs',
            "poisson-trace name --list --store proofload-runs",
        ),
    )
    name.add_argument("run", nargs="?", metavar="RUN", help=f"the run to name, {_RUN_HELP}")
    name.add_argument(
        "new", nargs="?", metavar="NAME", help="the name to give it, at most 80 characters"
    )
    name.add_argument("--store", metavar="ROOT", help=_STORE_HELP)
    name.add_argument("--config", metavar="PATH", help=_CONFIG_HELP)
    name.add_argument(
        "--forget", action="store_true", help="take back the name of yours that RUN has"
    )
    name.add_argument("--list", action="store_true", help="list the names of yours")

    def common(p: argparse.ArgumentParser, died: str) -> None:
        p.add_argument("--store", metavar="ROOT", help=_STORE_HELP)
        p.add_argument(
            "--event",
            action="append",
            metavar="NAME",
            help=f"an outcome that counts as {died}; repeatable (default: the failures "
            "trace.toml names)",
        )
        p.add_argument("--config", metavar="PATH", help=_CONFIG_HELP)

    def where_and_compare(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--by",
            choices=("kind", "step"),
            default="kind",
            metavar="kind|step",
            help="label the step an episode died at by the kind of its last step, or by the "
            "nearest declared step name (default: kind)",
        )
        p.add_argument(
            "--at",
            action="append",
            type=int,
            default=[],
            metavar="STEP",
            help="a step to read the curve at; repeatable (no default)",
        )

    def saving(p: argparse.ArgumentParser, force: bool = True) -> None:
        p.add_argument("--save", action="store_true", help=_SAVE_HELP)
        p.add_argument("--out", metavar="DIR", help=_OUT_HELP)
        if force:
            p.add_argument(
                "--force", action="store_true", help="let --out replace a folder that exists"
            )

    def verdicts(p: argparse.ArgumentParser) -> None:
        p.add_argument("--verdicts", metavar="FILE", help=_VERDICTS_HELP)

    def tail(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--json", action="store_true", help="print the JSON structure instead of the report"
        )
        p.add_argument(
            "--debug",
            action="store_true",
            help="on an unexpected failure, print its details on stderr as well as in the log",
        )

    where = verbs.add_parser(
        "where",
        help="where in the workflow the episodes of one stored run died",
        description=(
            "The share of one stored run's episodes not yet failed at each step index, the\n"
            "median step of the failed ones, and where they stopped, by kind of step. An\n"
            "episode failed when its outcome is one of the --event names; finishing otherwise\n"
            "and timing out are ends of their own, and only episodes at the capture cap are\n"
            "censored."
        ),
        epilog=_example(
            "poisson-trace where previous --store proofload-runs --event unsolved --at 20",
        ),
    )
    where.add_argument("run", metavar="RUN", help=f"the run, {_RUN_OR_FOLDER}")
    common(where, "a death")
    where_and_compare(where)
    where.add_argument(
        "--boot",
        type=int,
        default=1000,
        metavar="B",
        help="bootstrap resamples of the inputs, for the bands (default: 1000)",
    )
    where.add_argument(
        "--seed", type=int, default=0, metavar="S", help="the bootstrap's seed (default: 0)"
    )
    where.add_argument(
        "--svg",
        metavar="FILE",
        help="also write the curve as an SVG file; a file that exists is refused without "
        "--force (no default)",
    )
    where.add_argument(
        "--force", action="store_true", help="let --svg or --out replace what exists"
    )
    saving(where, force=False)
    tail(where)

    compare = verbs.add_parser(
        "compare",
        help="a before (A) and an after (B), compared",
        description=(
            "Two stored runs, a before (A) and an after (B), compared: the log-rank test\n"
            "stratified by config cell over the cells both runs carry, the direction, the\n"
            "smallest hazard ratio the design could have detected, and one of three lines:\n"
            "different, no significant difference, or too small to tell. --max-mde-hr is the\n"
            "largest detectable hazard ratio you accept, and it has no default."
        ),
        epilog=_example(
            'poisson-trace compare "#3" previous --store proofload-runs --event unsolved \\',
            "    --max-mde-hr 1.5",
        ),
    )
    compare.add_argument("a", metavar="A", help=f"the run before the change, {_RUN_OR_FOLDER}")
    compare.add_argument("b", metavar="B", help="the run after the change")
    common(compare, "a death")
    where_and_compare(compare)
    ceiling = compare.add_argument(
        "--max-mde-hr",
        type=float,
        metavar="X",
        help="the largest minimum detectable hazard ratio you accept, such as 1.5 "
        "(default: max_mde_hr in trace.toml's [check], else none)",
    )
    compare.show_required(ceiling)
    compare.add_argument(
        "--alpha", type=float, default=0.05, metavar="A", help="the test's level (default: 0.05)"
    )
    verdicts(compare)
    saving(compare)
    tail(compare)

    def paired(p: argparse.ArgumentParser) -> None:
        common(p, "a failure")
        p.add_argument(
            "--alpha",
            type=float,
            default=0.05,
            metavar="A",
            help="the tests' level (default: 0.05)",
        )
        p.add_argument(
            "--top",
            type=int,
            default=10,
            metavar="N",
            help="the inputs the report's table shows; every flagged input shows, whatever N "
            "is, and --json lists all (default: 10)",
        )

    fix = verbs.add_parser(
        "fix-check",
        help="an old and a new version re-run on the same inputs, compared",
        description=(
            "An old and a new version, each re-run on the same inputs, compared input by input\n"
            "with the old version as the control: how often the old version failed again with\n"
            "nothing changed, the exact stratified test, the difference with its interval, the\n"
            "smallest change the design could have detected, and one of three lines: different,\n"
            "no significant difference, or too small to tell. An input is one config cell of the\n"
            "sweep. Which inputs are compared has no default (--failing-from or --inputs all),\n"
            "and neither has --max-mde."
        ),
        epilog=_example(
            "poisson-trace fix-check previous latest --store proofload-runs --event unsolved \\",
            "    --inputs all --max-mde 0.2",
        ),
    )
    fix.add_argument("old", metavar="OLD", help=f"the old version's run, {_RUN_OR_FOLDER}")
    fix.add_argument("new", metavar="NEW", help="the new version's run")
    paired(fix)
    fix.add_argument(
        "--failing-from",
        metavar="RUN",
        help="compare the inputs that failed in RUN, a third run that is neither OLD nor NEW "
        "(no default)",
    )
    fix.add_argument(
        "--min-failures",
        type=int,
        metavar="M",
        help="with --failing-from, the failures an input needs in RUN to be compared (default: 1)",
    )
    fix.add_argument(
        "--inputs",
        metavar="all",
        help="all: compare every input either run carries (no default)",
    )
    limit = fix.add_argument(
        "--max-mde",
        type=float,
        metavar="X",
        help="the largest detection limit you accept, as a share of failures: 0.2 is twenty "
        "points (default: max_mde in trace.toml's [check], else none)",
    )
    fix.show_required(limit)
    fix.add_argument(
        "--seed",
        type=int,
        default=0,
        metavar="S",
        help="the seed of the by-input reading's draws (default: 0)",
    )
    fix.add_argument(
        "--measures",
        action="store_true",
        help="also compare the runs' time, length, tokens and cost, case by case, in a section "
        "of the report (no default: the section prints only when asked)",
    )
    fix.add_argument(
        "--max-change",
        action="append",
        type=_max_change,
        default=[],
        metavar="MEASURE=N%",
        help="the change in a measure's mean you accept as none, as a share of the old mean, "
        "such as wall_time_s=10%%; repeatable, and implies --measures (default: max_change in "
        "trace.toml's [check], else none)",
    )
    verdicts(fix)
    saving(fix)
    tail(fix)

    changes = verbs.add_parser(
        "changes",
        help="the inputs whose failure share moved between two runs",
        description=(
            "Lists the inputs whose failure share moved between two runs, each with Fisher's\n"
            "exact test and a Benjamini-Hochberg correction across the inputs, and says which\n"
            "changes this design could not have flagged. An input is one config cell."
        ),
        epilog=_example(
            "poisson-trace changes previous latest --store proofload-runs --event unsolved",
        ),
    )
    changes.add_argument("a", metavar="A", help=f"the first run, {_RUN_OR_FOLDER}")
    changes.add_argument("b", metavar="B", help="the second run")
    paired(changes)
    verdicts(changes)
    saving(changes)
    tail(changes)
    tail(runs)
    name.add_argument(
        "--debug",
        action="store_true",
        help="on an unexpected failure, print its details on stderr as well as in the log",
    )
    tail(init)
    # listed for the help alone: the import's own command reads its command line
    verbs.add_parser(
        "import",
        help="read in the results another tool wrote, as one new run of a store",
        add_help=False,
    )
    doctor = verbs.add_parser(
        "doctor",
        help="whether this environment is ready, and what to run when it is not",
        description=(
            "Says whether this environment is ready for Trace, one line for each thing it\n"
            "checks: the Python running it, the Trace package and where it was imported from,\n"
            "Prove, the config file and the stores it names, the names of yours, and the\n"
            "readers of other tools' files in the install. A line that fails ends with the\n"
            "command to run. It fixes nothing and asks nothing; it exits 4 when not ready."
        ),
        epilog=_example("poisson-trace doctor", "poisson-trace doctor --config team.toml"),
    )
    doctor.add_argument("--config", metavar="PATH", help=_CONFIG_HELP)
    tail(doctor)
    handover = verbs.add_parser(
        "handover",
        help="check a handover bundle --out wrote: every file, digest and promised key",
        description=(
            "Checks a handover bundle that where, compare, fix-check or changes wrote with\n"
            "--out DIR: every file handover.json and artifact.json list is there with its\n"
            "digest and size, result.json is the verb's JSON with every key the handover\n"
            "promises, report.md opens with the verdict line, and nothing in it is content\n"
            "Trace never hands over. It exits 4 with the first failing line when the bundle\n"
            "does not hold what it promises, and 1 when DIR is not a bundle."
        ),
        epilog=_example("poisson-trace handover --check verdicts/fix-check-2026-11-04"),
    )
    checked = handover.add_argument("--check", metavar="DIR", help="the bundle to check")
    handover.show_required(checked)
    handover.add_argument(
        "--debug",
        action="store_true",
        help="on an unexpected failure, print its details on stderr as well as in the log",
    )
    return parser, {
        "init": init,
        "runs": runs,
        "name": name,
        "where": where,
        "compare": compare,
        "fix-check": fix,
        "changes": changes,
        "handover": handover,
        "doctor": doctor,
    }


def _form(text: str) -> str:
    """``--names from=FORM``: the form, or a wrong command line."""
    from poisson_trace.config import FORMS

    key, _, form = text.partition("=")
    if key != "from" or form not in FORMS:
        raise argparse.ArgumentTypeError(
            f'takes from=target, from=date or from=target-date, not "{text}"'
        )
    return form


def _fail_on(text: str) -> tuple[str, ...]:
    """``--fail-on``: the check's results that fail its job, comma-separated."""
    from poisson_trace.config import FAIL_ON

    picked = [p.strip() for p in text.split(",")] if text.strip() else []
    if any(p not in FAIL_ON for p in picked):
        raise argparse.ArgumentTypeError(
            f'takes failed-more, too-small or both, comma-separated, not "{text}"'
        )
    return tuple(dict.fromkeys(picked))


def _max_change(text: str) -> tuple[str, float]:
    """``--max-change MEASURE=N%``: the measure and its ceiling as a share, or a wrong command
    line (TF23's reading of the words, CS10)."""
    from poisson_trace.stats.continuous import parse_max_change

    try:
        return parse_max_change(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from None


def _init_parser(verbs: Any) -> look.Parser:
    init: look.Parser = verbs.add_parser(
        "init",
        help="guided setup: finds your results, asks what counts as a failure, writes trace.toml",
        description=(
            "Finds the results already in this folder's tree (the stores Prove wrote, and the\n"
            "result files of the readers in this install), asks which store to start with when\n"
            "there are several, or offers to import the result files when there is no store,\n"
            "asks which outcomes count as a failure, shows the runs' names, and writes\n"
            "trace.toml once, after the last answer. Every verb then takes its store and its\n"
            "failures from it. It runs nothing, spends nothing and writes under no store but\n"
            "the runs an import you agree to writes. Every question has a flag: with --yes it\n"
            "asks nothing. It never searches the home folder or a folder above it."
        ),
        epilog=_example(
            "poisson-trace init",
            "poisson-trace init --yes --store proofload-runs --event unsolved",
            "poisson-trace init --add-store imported",
        ),
    )
    init.add_argument(
        "--store",
        action="append",
        metavar="PATH",
        help="a store to set up, and nothing is searched; repeatable: the first is the store "
        "every verb reads, each other is named by its folder (default: the one found here, or "
        "the one you pick)",
    )
    init.add_argument(
        "--add-store",
        metavar="PATH",
        help="add the store at PATH to the config there already, named by its folder; nothing "
        "else is asked or changed (no default)",
    )
    init.add_argument(
        "--event",
        action="append",
        metavar="NAME",
        help="an outcome that counts as a failure; repeatable (default: every outcome of the "
        "newest 20 runs whose name is not a word for success, shown for you to confirm)",
    )
    init.add_argument(
        "--names",
        type=_form,
        metavar="from=FORM",
        help="how a run with no name of yours is named: from=target, from=date or "
        "from=target-date (default: from=target)",
    )
    init.add_argument(
        "--import",
        dest="import_",
        action="store_true",
        default=None,
        help="import the result files found when there is no store, without the question",
    )
    init.add_argument(
        "--no-import",
        dest="import_",
        action="store_false",
        help="leave them as they are and write the config with no store",
    )
    init.add_argument(
        "--metric",
        metavar="NAME",
        help="for the import: the metric, or the score column, to read (no default)",
    )
    init.add_argument(
        "--cut",
        metavar="recorded|X",
        help="for the import: where a score misses; recorded, for DeepEval's own decision, or "
        "a number with --below or --above (no default)",
    )
    init.add_argument(
        "--below", action="store_true", help="for the import: a score under the cut missed it"
    )
    init.add_argument(
        "--above", action="store_true", help="for the import: a score over the cut missed it"
    )
    init.add_argument(
        "--case",
        choices=("name", "input", "position"),
        metavar="name|input|position",
        help="for a DeepEval import: what identifies a test case across versions; for JUnit "
        "reports, name reads them by the test's name alone (no default)",
    )
    init.add_argument(
        "--case-column",
        metavar="COLUMN",
        help="for a Ragas import or a table's: the column that identifies a case (no default)",
    )
    init.add_argument(
        "--outcome-column",
        metavar="COLUMN",
        help="for a table's import: the column that holds each row's outcome (no default)",
    )
    init.add_argument(
        "--failed",
        action="append",
        metavar="VALUE",
        help="for a table's import: a value of the outcome column that means a failure; "
        "repeatable (no default)",
    )
    init.add_argument(
        "--max-mde",
        type=float,
        metavar="X",
        help="the largest detection limit fix-check and the check accept, written to [check] "
        "(no default; written only when given)",
    )
    init.add_argument(
        "--max-mde-hr",
        type=float,
        metavar="X",
        help="the largest detectable hazard ratio compare accepts, written to [check] (no "
        "default; written only when given)",
    )
    init.add_argument(
        "--fail-on",
        type=_fail_on,
        metavar="LIST",
        help="the check's results that fail its job, comma-separated: failed-more, too-small or "
        "both (no default; written only when given)",
    )
    init.add_argument("--force", action="store_true", help="replace a config that is there already")
    init.add_argument(
        "--config",
        metavar="PATH",
        help="the config file to write (default: trace.toml in the current folder)",
    )
    init.add_argument(
        "--yes",
        action="store_true",
        help="ask nothing: every answer from a flag or its default",
    )
    return init


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    return look.run("poisson-trace", args, _main, (_Refusal,))


def _main(session: look.Session) -> int:
    parser, verbs = _build_parser()
    parsers = [parser, *verbs.values()]
    at = _import_at(session.argv, parsers, verbs)
    if at is not None:
        from poisson_trace.ingest import cli as importer

        return importer.main([*session.argv[:at], *session.argv[at + 1 :]])
    valued = look.takes_value(parsers)
    if look.asks(session.argv, valued, "--version"):
        look.out(look.version_line())
        return look.DONE
    args, at = look.verb_first(session.argv, valued, _KEPT, look.options(parsers), "poisson-trace")
    if at is not None and args[at] not in verbs:
        raise look.Usage(
            f'"{args[at]}" is not a verb; the verbs are {_NAMED}', "poisson-trace --help"
        )
    ns, extra = parser.parse_known_args(args)
    if ns.verb is None or ns.verb not in verbs:
        # "import" read as a verb here is an option's value: the import's own command takes the
        # verb wherever it stands
        raise look.Usage(f"no verb was given; the verbs are {_NAMED}", "poisson-trace --help")
    # a run word may name a folder of results, whose reader's flags the verb's parser leaves
    # over; whether it is a folder is known once the store is (TF22)
    words = _run_words(ns)
    folders = [w for _, w in words if _is_folder(w)]
    if extra and not folders:
        verbs[ns.verb].error(f"unrecognized arguments: {' '.join(extra)}")
    if ns.verb == "name":
        _name_line(ns)
    session.debug = ns.debug
    if getattr(ns, "json", False):
        schema = f"poisson-trace.{ns.verb}/1"
        session.render = lambda line: _stopped_json(schema, line)
    if ns.verb == "doctor":
        return _doctor(ns)
    # the options the command line gave, for the saved verdict's record of where each setting
    # came from (SV5)
    ns.typed_flags = {w.split("=", 1)[0] for w in args if w.startswith("--")}
    if ns.verb not in ("init", "handover"):
        _from_config(ns, folders=bool(words) and len(folders) == len(words))
    refusal = look.prove_refusal(_DOES if ns.verb != "init" else "poisson-trace init reads stores")
    if refusal is not None:
        raise _Refusal(refusal, look.INSTALL_PROVE)
    if ns.verb == "init":
        return _init(session, ns)
    if ns.verb == "handover":
        return _handover(ns)
    _validate(ns)
    verb: Callable[[argparse.Namespace], int] = {
        "runs": _runs,
        "name": _name,
        "where": _where,
        "compare": _compare,
        "fix-check": _fix_check,
        "changes": _changes,
    }[ns.verb]
    from poisson_trace.names import Unordered

    try:
        if folders:
            return _on_folders(ns, verb, extra, verbs[ns.verb])
        return verb(ns)
    except Unordered as e:
        raise _unordered(e, ns.verb, session.argv, valued) from None


# the verbs that read two runs, the older version's first
_TWO_RUNS = ("compare", "fix-check", "changes")
_PLACEHOLDERS = ("OLDER", "NEWER")


def _unordered(e: Any, verb: str, argv: Sequence[str], valued: Collection[str]) -> _Refusal:
    """latest or previous refused because the start times cannot order the runs: for a verb of
    two runs, the command as it was typed with OLDER and NEWER in place of each reserved word,
    so that it cannot be run the wrong way round as it stands."""
    words: list[str] = []
    replaced: list[str] = []
    place = -1  # -1 until the verb is passed; then the place of each run given
    i = 0
    while i < len(argv):
        word = argv[i]
        if word.startswith("-") and word != "-":
            words.append(_typed_option(word))
            if "=" not in word and word in valued and i + 1 < len(argv):
                words.append(look.word(argv[i + 1]))
                i += 1
        elif place < 0:
            words.append(look.word(word))
            place = 0
        else:
            if verb in _TWO_RUNS and place < 2 and _by_start(word):
                words.append(_PLACEHOLDERS[place])
                replaced.append(_PLACEHOLDERS[place])
            else:
                words.append(look.word(word))
            place += 1
        i += 1
    if not replaced:
        return _Refusal(e.sentence(two=False), e.listing)
    runs = " and ".join(f'"{r}"' for r in e.runs)
    if len(replaced) == 2:
        said = f"OLDER and NEWER are {runs}, in the order you know"
    else:
        said = f"{replaced[0]} is one of {runs}, as you know them"
    line = look.command("poisson-trace", *words) + f"  # {said}"
    return _Refusal(e.sentence(two=True), line, e.listing)


def _by_start(word: str) -> bool:
    """Whether a run is given by a word that goes by when runs started: latest or previous."""
    text = word.strip()
    return text in ("latest", "previous") or text.startswith(("latest:", "previous:"))


def _typed_option(word: str) -> str:
    """An option as typed, its value after ``=`` quoted for a shell."""
    flag, joined, value = word.partition("=")
    return f"{flag}={look.word(value)}" if joined else word


def _import_at(
    args: Sequence[str], parsers: Sequence[argparse.ArgumentParser], verbs: Mapping[str, Any]
) -> int | None:
    """Where ``import`` stands as the verb, or None. An option before it is read as the verbs
    and the import read it, so that its value is never taken for the verb. After an option none
    of them knows, what follows cannot be told for its value or the verb: the first verb's name
    after it decides, so that the import refuses an option written before ``import`` as it
    refuses one written before its tool."""
    from poisson_trace.ingest import cli as importer

    _, subs, _ = importer.parsers()
    every = [*parsers, *subs.values()]
    known, valued = look.options(every), look.takes_value(every)
    i = 0
    while i < len(args) and args[i] != "--":
        word = args[i]
        if not word.startswith("-") or word == "-":
            return i if word == "import" else None
        name = word.split("=", 1)[0]
        if name not in known:
            return _first_verb(args[i + 1 :], i + 1, known, valued, verbs)
        i += 2 if "=" not in word and name in valued else 1
    return None


def _first_verb(
    rest: Sequence[str], at: int, known: Collection[str], valued: Collection[str], verbs: Any
) -> int | None:
    """After an option nobody knows: the place of ``import`` when it is the first verb's name
    among the words that are not options or their values, else None."""
    i = 0
    while i < len(rest) and rest[i] != "--":
        word = rest[i]
        if word.startswith("-") and word != "-":
            name = word.split("=", 1)[0]
            i += 2 if "=" not in word and name in known and name in valued else 1
            continue
        if word == "import":
            return at + i
        if word in verbs:
            return None
        i += 1
    return None


def _from_config(ns: argparse.Namespace, *, folders: bool = False) -> None:
    """The store, the failures and the ceilings a verb takes from the config when no flag gives
    them; a store name the config holds is that store. What neither gives is a wrong command
    line, as it is with no config, but for a store when every run is given as a folder."""
    from poisson_trace import config

    ns.folder_words = {}
    ns.reader_flags = []
    ns.from_folders = False
    held = config.load(ns.config)
    ns.form = held.names_from if held is not None else "target"
    ns.typed_store = ns.store
    ns.typed_events = list(getattr(ns, "event", None) or ())
    ns.config_flags = held.flags() if held is not None else ()
    ns.settings = held
    if ns.store is not None and held is not None and ns.store in held.named:
        ns.store = held.named[ns.store]
    elif ns.store is None and held is not None:
        ns.store = held.store
    if hasattr(ns, "event") and ns.event is None and held is not None and held.events is not None:
        ns.event = list(held.events)
    flags = []
    if ns.store is None and not folders:
        flags.append("--store")
    if ns.verb in _COUNTING and not ns.event:
        flags.append("--event")
    if flags:
        said = {"--store": "a store", "--event": "the failures"}
        if held is None:
            why = "no trace.toml here gives " + " or ".join(said[f] for f in flags)
        else:
            why = f"{held.shown} gives no " + " and no ".join(
                said[f].removeprefix("a ").removeprefix("the ") for f in flags
            )
        raise look.Usage(
            f"{' and '.join(flags)} {'is' if len(flags) == 1 else 'are'} required: {why}",
            f"poisson-trace {ns.verb} --help",
        )
    if held is not None:
        if ns.verb == "compare" and ns.max_mde_hr is None:
            ns.max_mde_hr = held.max_mde_hr
        if ns.verb == "fix-check" and ns.max_mde is None:
            ns.max_mde = held.max_mde
    # the continuous measures' ceilings: the config's, a flag winning for its measure (CT2,
    # CS10); every verb of two runs saves the measures with them, fix-check prints them
    ns.ceilings = _ceilings(held, getattr(ns, "max_change", None) or [])
    ns.joined = None  # the --verdicts join, once made (SV10)
    ns.temp_store = False  # the runs were read from tool folders into a store that does not last
    ns.save = getattr(ns, "save", False)
    ns.out = getattr(ns, "out", None)
    ns.verdicts = getattr(ns, "verdicts", None)


def _ceilings(held: Any, flags: Sequence[tuple[str, float]]) -> dict[str, float]:
    from poisson_trace.stats.continuous import MEASURES

    merged: dict[str, float] = dict(held.max_change) if held is not None else {}
    for measure, fraction in flags:
        merged[measure] = fraction
    return {m: merged[m] for m in MEASURES if m in merged}


def _init(session: look.Session, ns: argparse.Namespace) -> int:
    from poisson_trace import setup

    session.stopped = lambda: setup.STOPPED

    def written(line: str) -> None:
        # once anything is on disk, Ctrl-C says what was kept
        session.stopped = lambda: line

    done = setup.init(ns, written)
    look.out(json.dumps(done.data, indent=2, allow_nan=False) + "\n" if ns.json else done.text)
    return look.DONE


def _doctor(ns: argparse.Namespace) -> int:
    from poisson_trace import doctor

    report = doctor.check(ns.config)
    if ns.json:
        look.out(json.dumps(report, indent=2, allow_nan=False) + "\n")
    else:
        look.out(doctor.text(report))
    return look.DONE if report["verdict"] == "ok" else look.CHECK_FAILED


def _stopped_json(schema: str, line: str) -> str:
    """The stopped line as the verb's JSON document: stdout stays one document."""
    verdict, _, sentence = line.partition("  ")
    doc = {"schema": schema, "verdict": verdict, "sentence": sentence, "next": None}
    return json.dumps(doc, indent=2) + "\n"


def _name_line(ns: argparse.Namespace) -> None:
    """``name`` says one whole thing: a run and a name, a run and --forget, or --list alone."""
    usage = "poisson-trace name --help"
    if ns.list:
        if ns.run is not None or ns.forget:
            raise look.Usage("--list takes no run and no --forget", usage)
        return
    if ns.run is None:
        raise look.Usage("name takes a run and a name, a run and --forget, or --list", usage)
    if ns.forget and ns.new is not None:
        raise look.Usage("--forget takes the run alone, without a new name", usage)
    if not ns.forget and ns.new is None:
        raise look.Usage(f'no name was given for the run "{ns.run}"', usage)


def _validate(ns: argparse.Namespace) -> None:
    if ns.verb == "where":
        if not 1 <= ns.boot <= _MOST_BOOT:
            raise _Refusal(f"--boot takes 1 to {count(_MOST_BOOT)} resamples, not {ns.boot}")
        if ns.svg == "":
            raise _Refusal("--svg takes the name of the file to write")
        if ns.force and ns.svg is None and ns.out is None:
            raise _Refusal("--force applies to --svg and --out and was given without either")
    elif ns.verb in _TWO_RUNS and ns.force and ns.out is None:
        raise _Refusal("--force applies to --out and was given without it")
    if ns.verb in _COUNTING:
        if ns.out == "":
            raise _Refusal("--out takes the name of the folder to write")
        if ns.verdicts == "":
            raise _Refusal("--verdicts takes the name of the file to read")
    if ns.verb in ("where", "fix-check") and ns.seed < 0:
        raise _Refusal(f"--seed takes 0 or more, not {ns.seed}")
    if ns.verb == "compare":
        if ns.max_mde_hr is None:
            raise _Refusal(
                "--max-mde-hr is required: the largest minimum detectable hazard ratio you "
                "accept, such as 1.5; it has no default"
            )
        if not 0.0 < ns.alpha < 1.0:
            raise _Refusal("--alpha must be strictly between 0 and 1")
        if not ns.max_mde_hr > 0.0:
            raise _Refusal("--max-mde-hr must be a positive hazard ratio")
    if ns.verb in ("fix-check", "changes"):
        if not 0.0 < ns.alpha < 1.0:
            raise _Refusal("--alpha must be strictly between 0 and 1")
        if ns.top < 0:
            raise _Refusal("--top must be 0 or more")
    if ns.verb == "changes" and ns.a == ns.b:
        raise _Refusal(f"A and B are both {ns.a}; the two runs compared must differ")
    if ns.verb == "fix-check":
        _validate_fix_check(ns)


def _validate_fix_check(ns: argparse.Namespace) -> None:
    if (ns.failing_from is None) == (ns.inputs is None):
        raise _Refusal(
            "exactly one of --failing-from RUN and --inputs all is required; which inputs are "
            "compared has no default"
        )
    if ns.inputs is not None and ns.inputs != "all":
        raise _Refusal(f"--inputs takes only the value all, not {ns.inputs}")
    if ns.min_failures is not None:
        if ns.failing_from is None:
            raise _Refusal("--min-failures applies to --failing-from and was given without it")
        if ns.min_failures < 1:
            raise _Refusal("--min-failures must be at least 1")
    if ns.max_mde is None:
        raise _Refusal(
            "--max-mde is required, as a fraction of failure share (0.20 is twenty points); "
            "it has no default"
        )
    if not 0.0 < ns.max_mde < 1.0:
        raise _Refusal("--max-mde must be strictly between 0 and 1 (0.20 is twenty points)")
    if ns.old == ns.new:
        raise _Refusal(f"OLD and NEW are both {ns.old}; the two runs compared must differ")
    for arm, run in (("old", ns.old), ("new", ns.new)):
        if ns.failing_from == run:
            raise _Refusal(
                f"the selecting run {run} is also the {arm} arm; both arms must be fresh "
                "re-runs, because the selecting run's failures on these inputs are there by "
                "selection"
            )


# ---------- runs given as folders (TF22, spec section 18.3.1) ----------

# each verb's run words, by the attribute its parser gives them
_RUN_WORDS: dict[str, tuple[str, ...]] = {
    "where": ("run",),
    "compare": ("a", "b"),
    "fix-check": ("old", "new", "failing_from"),
    "changes": ("a", "b"),
}


def _run_words(ns: argparse.Namespace) -> list[tuple[str, str]]:
    """``(attribute, word)`` for each run the command line gives the verb."""
    given = [(attr, getattr(ns, attr, None)) for attr in _RUN_WORDS.get(ns.verb, ())]
    return [(attr, word) for attr, word in given if isinstance(word, str)]


def _is_folder(word: str) -> bool:
    from poisson_trace.ingest.folder import is_folder

    return is_folder(word)


def _typed(words: Sequence[str]) -> list[str]:
    """Options and their values as typed, each quoted for a shell where it needs it."""
    return [_typed_option(w) if w.startswith("-") and w != "-" else look.word(w) for w in words]


def _reached(ns: argparse.Namespace, words: Sequence[str]) -> list[str]:
    """The words that reach a stored run of the verb's store; none when there is no store or
    it cannot be read, since a word that reaches nothing may still name a folder."""
    if ns.store is None:
        return []
    try:
        _, index = _named(ns)
    except Exception:
        return []
    out = []
    for word in words:
        try:
            index.resolve(word)
        except Exception:
            continue
        out.append(word)
    return out


def _on_folders(
    ns: argparse.Namespace,
    verb: Callable[[argparse.Namespace], int],
    extra: Sequence[str],
    parser: look.Parser,
) -> int:
    """The verb on runs given as folders (FI8, FI12 to FI14). A word that reaches a stored run
    is that run, as before; a word that reaches none and names a folder is the folder. A Prove
    folder is read where it is. Tool folders are read by their reader, with its flags from the
    verb's command line, into a store that does not outlive the command. Runs from two places
    on one report are refused."""
    from poisson_trace.ingest.rows import Refusal

    words = _run_words(ns)
    stored = set(_reached(ns, [w for _, w in words if _is_folder(w)]))
    given = [(attr, w) for attr, w in words if _is_folder(w) and w not in stored]
    if not given:
        if extra:
            parser.error(f"unrecognized arguments: {' '.join(extra)}")
        return verb(ns)
    others = [w for attr, w in words if (attr, w) not in given]
    if others:
        # each must reach a stored run, refused as before where it does not
        _, index = _named(ns)
        for word in others:
            index.resolve(word)
        folders = _listed([w for _, w in given])
        raise _Refusal(
            f"{folders} {'is a folder' if len(given) == 1 else 'are folders'} and "
            f"{_listed(others)} a stored run; a report reads its runs from one place, so import "
            "the folder into the store and give its run by name",
            *(
                look.command(
                    "poisson-trace", "import", look.word(w), *_reach(ns), *_typed(extra)
                )
                for _, w in given
            ),
        )
    try:
        return _read_folders(ns, verb, extra, given, parser)
    except Refusal as e:
        raise _Refusal(str(e), *e.nexts) from None


def _listed(words: Sequence[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def _read_folders(
    ns: argparse.Namespace,
    verb: Callable[[argparse.Namespace], int],
    extra: Sequence[str],
    given: Sequence[tuple[str, str]],
    parser: look.Parser,
) -> int:
    from poisson_trace.ingest.folder import resolve

    found = [(attr, word, resolve(Path(word))) for attr, word in given]
    prove = [(a, w, r) for a, w, r in found if r.kind in ("run", "store")]
    tools = [(a, w, r) for a, w, r in found if r.kind not in ("run", "store")]
    if prove and tools:
        raise _Refusal(
            f"{_listed([w for _, w, _ in prove])} {'is' if len(prove) == 1 else 'are'} Prove's "
            f"and {_listed([w for _, w, _ in tools])} another tool's results; a report reads its "
            "runs from one place, so import the results into that store and give the runs by "
            "name"
        )
    if prove:
        if extra:
            # a Prove folder has no reader, so no reader's flag applies
            parser.error(f"unrecognized arguments: {' '.join(extra)}")
        return _read_prove_folders(ns, verb, prove)
    return _read_tool_folders(ns, verb, extra, tools)


def _read_prove_folders(
    ns: argparse.Namespace,
    verb: Callable[[argparse.Namespace], int],
    found: Sequence[tuple[str, str, Any]],
) -> int:
    """Prove folders, read where they are: their one store, each run by its id."""
    stores = {Path(r.store).resolve() for _, _, r in found}
    if len(stores) > 1:
        raise _Refusal(
            f"{_listed([w for _, w, _ in found])} are runs of {len(stores)} different stores; "
            "a report reads its runs from one store"
        )
    _, first, resolved = found[0]
    ns.store = str(resolved.store)
    words: dict[str, str] = {}
    if resolved.kind == "run":
        # every run of the store is a folder beside the one typed, and named so
        from poisson_trace.ingest.writer import runs_in

        for run_id in runs_in(Path(ns.store)):
            words[run_id] = str(Path(first).parent / run_id)
    for attr, word, r in found:
        setattr(ns, attr, r.run_id)
        words[r.run_id] = word
    ns.typed_store = None
    ns.folder_words = words
    ns.from_folders = True
    return verb(ns)


def _read_tool_folders(
    ns: argparse.Namespace,
    verb: Callable[[argparse.Namespace], int],
    extra: Sequence[str],
    found: Sequence[tuple[str, str, Any]],
) -> int:
    """Tool folders, read by their reader with its flags into a store that does not outlive the
    command, each run under its folder's name."""
    import shutil
    import tempfile

    from poisson_trace.ingest import cli as importer
    from poisson_trace.names import import_name_refusal

    tools = list(dict.fromkeys(str(r.tool) for _, _, r in found))
    if len(tools) > 1:
        each = ", ".join(f"{w} ({r.tool})" for _, w, r in found)
        raise _Refusal(
            f"the folders hold the results of {len(tools)} tools, {each}; a report compares "
            "runs of one tool's, read with its reader's flags"
        )
    named: dict[str, str] = {}
    for _, word, r in found:
        if r.name in named:
            raise _Refusal(
                f"{named[r.name]} and {word} are both named {r.name}, and a run read from a "
                "folder takes its folder's name; import them under two names and give the runs "
                "by name"
            )
        named[r.name] = word
        hole = import_name_refusal(r.name)
        if hole is not None:
            raise _Refusal(f"a run read from a folder takes its folder's name, and {hole}")
    tool = tools[0]
    module = importer.reader(tool)
    reader = look.Parser(prog=f"poisson-trace {ns.verb}", add_help=False)
    module.add_arguments(reader)
    flags = reader.parse_args(list(extra))
    wrong = getattr(module, "usage", None)
    said = wrong(flags) if wrong is not None else None
    if said is not None:
        reader.error(said)
    from poisson_trace.ingest.writer import write

    settings = ns.settings
    held = tempfile.mkdtemp(prefix="poisson-trace-")
    try:
        read: list[tuple[str, Any, Any]] = []
        for attr, _, r in found:
            read_ns = argparse.Namespace(
                **vars(flags),
                files=[str(f) for f in r.files],
                run=r.name,
                store=held,
                signals=dict(settings.signals) if settings is not None else {},
            )
            run = module.read(read_ns)
            importer.one_run(tool, read_ns, r, run, ())
            read.append((attr, r, run))
        if ns.verdicts is not None:
            # the join as the folders are read, so a verdict joins by the input key the reader
            # computed as well as by case (SV10 item 8); over both runs' rows at once
            read = _join_read(ns, read)
        for attr, r, run in read:
            importer.checked(run)
            write(
                run,
                Path(held),
                ns.form,
                rules=settings.rules if settings is not None else (),
                budgets=settings.budgets if settings is not None else None,
            )
            setattr(ns, attr, r.name)
        ns.store = held
        ns.temp_store = True
        ns.typed_store = None
        ns.folder_words = {r.name: word for _, word, r in found}
        ns.reader_flags = _typed(extra)
        ns.from_folders = True
        return verb(ns)
    finally:
        shutil.rmtree(held, ignore_errors=True)


def _join_read(
    ns: argparse.Namespace, read: Sequence[tuple[str, Any, Any]]
) -> list[tuple[str, Any, Any]]:
    """The verdicts file joined onto the runs read from folders that the verb compares (the
    two arms, not a selecting run), by case then by input key, in memory."""
    from dataclasses import replace

    from poisson_trace.ingest import verdicts

    arms = [(attr, r, run) for attr, r, run in read if attr in _ARMS]
    rows: list[Any] = []
    inputs: dict[str, str] = {}
    for _, _, run in arms:
        rows.extend(run.rows)
        for case, key in run.inputs.items():
            inputs.setdefault(case, key)
    joined = verdicts.join(rows, Path(ns.verdicts), inputs or None)
    ns.joined = verdicts.block(Path(ns.verdicts), joined)
    out: list[tuple[str, Any, Any]] = []
    at = 0
    for attr, r, run in read:
        if attr in _ARMS:
            run = replace(run, rows=joined.rows[at : at + len(run.rows)])
            at += len(run.rows)
        out.append((attr, r, run))
    return out


# the attributes that hold a verb's two compared runs, which --verdicts joins onto
_ARMS = ("a", "b", "old", "new")


# ---------- reading through Prove ----------


def _open(path: str) -> tuple[Any, list[str]]:
    """The store and the runs it holds, or a refusal when no folder under the path holds a run
    Prove stored: a path that is not there, an empty folder and a plain file alike."""
    from poisson_prove.store import Store

    store = Store(path)
    try:
        held = store.runs()
    except OSError as e:
        raise _Refusal(f"cannot read the store at {look.shown(path)} ({look.why(e)})") from e
    if not held:
        raise _Refusal(
            f"no store at {look.shown(path)} (no folder under it holds a run Prove stored)"
        )
    return store, held


def _named(ns: argparse.Namespace, *, lenient: bool = False) -> tuple[Any, Any]:
    """The store and its runs, each with its name: a store that is not there, a names file
    that is not one and an entry for a run the store lacks are refused."""
    from poisson_trace import names

    store, held = _open(ns.store)
    if ns.from_folders:
        # the runs were read from folders: a command names each by its folder and carries no
        # store, and one that names no run carries nothing
        index = names.index(store, held, ns.store, lenient=lenient, form=ns.form, carried=())
        index.given = dict(ns.folder_words)
        return store, index
    return store, names.index(
        store, held, ns.store, lenient=lenient, form=ns.form, carried=tuple(_reach(ns))
    )


def _load(store: Any, run: Any, *, trace: str = "envelope") -> tuple[Any, Any, Any]:
    """``(manifest, frame, tally)`` for a run the words given reached."""
    try:
        return (
            store.manifest(run.run_id),
            store.read(run.run_id, meta=False, trace=trace),
            store.tally(run.run_id),
        )
    except Exception as e:
        raise _Refusal(f"Prove could not read the run {run.shown()} ({look.why(e)})") from e


def _store_shown(ns: argparse.Namespace) -> Any:
    """The store a verb's JSON names: none when the runs were read from folders, since no
    store the user has holds them (FI13)."""
    return None if ns.from_folders else ns.store


def _two(index: Any, first: str, second: str, labels: tuple[str, str]) -> tuple[Any, Any]:
    """The two runs two words reach, refused when they are one run."""
    a, b = index.resolve(first), index.resolve(second)
    if a.run_id == b.run_id:
        raise _Refusal(
            f"{labels[0]} and {labels[1]} are both {a.shown()}; the two runs compared must differ"
        )
    return a, b


def _reach(ns: argparse.Namespace) -> list[str]:
    """What a next command carries to read the same store: ``--store`` as it was typed, and
    the config file when it was named by flag; nothing for a store the config gave."""
    words = [] if ns.typed_store is None else [look.option("--store", ns.typed_store)]
    return [*words, *ns.config_flags, *ns.reader_flags]


def _flags(ns: argparse.Namespace) -> list[str]:
    """What a next command carries: the store and each ``--event`` as they were typed, and the
    config file when it was named by flag; what the config gave is left out, since the command
    reads the same config."""
    words = [] if ns.typed_store is None else [look.option("--store", ns.typed_store)]
    for event in dict.fromkeys(ns.typed_events):
        words.append(look.option("--event", event))
    return [*words, *ns.config_flags, *ns.reader_flags]


def _next(index: Any, verb: str, runs: Sequence[Any], ns: argparse.Namespace, *extra: str) -> str:
    """A next command: the runs by the words that reach them, the store and the events given."""
    words = (look.word(index.word_for(r)) for r in runs)
    return look.command("poisson-trace", verb, *words, *_flags(ns), *extra)


def _enveloped(
    data: Mapping[str, Any], verdict: str, sentence: str, following: str | None
) -> dict[str, Any]:
    """The verb's JSON in its order: the schema, the verdict and its sentence, every key the
    verb had, and the next command last."""
    head = {"schema": data["schema"], "verdict": verdict, "sentence": sentence}
    rest = {k: v for k, v in data.items() if k != "schema"}
    # a run's header holds what the markdown alone reads, in keys that open with an underscore
    if isinstance(rest.get("run"), Mapping):
        rest["run"] = _public(rest["run"])
    if isinstance(rest.get("runs"), Mapping):
        rest["runs"] = {k: _public(v) for k, v in rest["runs"].items()}
    return {**head, **rest, "next": following}


def _public(header: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in header.items() if not k.startswith("_")}


def _start_of(manifest: Any) -> dict[str, Any] | None:
    """Where an imported run's start came from, as its import recorded it: the import's word
    for the source (``file time``, ``given``, ``file name``, ``file``, ``earliest span``), the
    tool, and for a time read from a file's name the zone it was read in (None when the run
    was imported before the zone was recorded). None for a run Prove stored."""
    environment = getattr(manifest, "environment", None)
    recorded = environment.get("import") if isinstance(environment, Mapping) else None
    if not isinstance(recorded, Mapping):
        return None
    zone = recorded.get("zone")
    return {
        "from": recorded.get("started_from"),
        "tool": recorded.get("tool"),
        "zone": dict(zone) if isinstance(zone, Mapping) else None,
    }


def _said(verdict: str, sentence: str, report: str, following: str, *details: str) -> str:
    """The text: the verdict line, each detail line under it (what was joined, what was
    written, what was saved), a blank line, the report and the next command."""
    head = f"{verdict}  {sentence}\n" + "".join(f"{line}\n" for line in details)
    return f"{head}\n{report}\nnext: {following}\n"


def _run_before(index: Any, run: Any) -> Any | None:
    """The complete run of the same target that started just before ``run``."""
    order = list(reversed(index.runs))
    at = next((i for i, r in enumerate(order) if r.run_id == run.run_id), None)
    if at is None:
        # a run whose start Prove's record does not give has no place in the order
        return None
    return next((r for r in reversed(order[:at]) if r.complete and r.target == run.target), None)


def _outcomes(frame: Any) -> set[str]:
    return {o for o in frame["outcome"] if o is not None}


def _traced(frame: Any) -> bool:
    """Whether any row of the run carries a trace."""
    return bool(frame["trace"].notna().any()) if len(frame) else False


def _from(run: Any) -> str:
    """Where an untraced run came from, for the sentence that says why it has no traces."""
    return f" (it was imported from {run.backend[len('import:') :]})" if run.imported else ""


def _no_traces(run: Any) -> str:
    """The line every report of a run with no traces carries in place of its curve."""
    return (
        f"This run has no traces{_from(run)}, so there is no step to place it on; fix-check and "
        "changes read it."
    )


def _header(run: Any, manifest: Any, placement: Any) -> dict[str, Any]:
    from poisson_trace.clock import REASONS

    counts = {r: sum(1 for p in placement.rows if p.reason == r) for r in REASONS}
    return {
        "run_id": run.run_id,
        "run_name": run.name,
        "target_id": manifest.target_id,
        "t_unit": manifest.t_unit,
        "status": manifest.status,
        "cap": placement.cap,
        "tally": placement.tally.to_dict(),
        "placement": {
            "placed": len(placement.rows),
            **counts,
            "excluded": dict(placement.excluded),
        },
        "_imported": run.imported,
        "_start": _start_of(manifest),
    }


def _ordered(causes: set[str]) -> list[str]:
    from poisson_prove.trace import KINDS

    return [k for k in KINDS if k in causes] + sorted(c for c in causes if c not in KINDS)


def _tries(placement: Any) -> list[tuple[str, int, str, str]]:
    """Each placed try as the competing-ends estimator reads it: its input, its step, how it
    ended, and the kind of step it failed at."""
    return [(p.config_hash, int(p.index), p.reason, p.cause) for p in placement.rows]


def _arrays(placement: Any) -> tuple[Any, Any, Any]:
    import numpy as np

    index = np.array([p.index for p in placement.rows], dtype=np.int64)
    died = np.array([p.died for p in placement.rows], dtype=bool)
    cause = np.array([p.cause for p in placement.rows], dtype=object)
    return index, died, cause


# ---------- the saved verdict, the handover bundle and the measures (TF6) ----------


def _check_out(path: str, force: bool) -> None:
    """Refuse, before any work, a bundle folder that is there already without --force, a file
    in its place, or a parent that cannot be written to."""
    target = Path(path)
    try:
        there = target.exists() or target.is_symlink()
        if there and (not target.is_dir() or target.is_symlink()):
            raise _Refusal(f"cannot write {path}: it is a file, not a folder for a bundle")
        if there and not force:
            raise _Refusal(f"{path} exists; add --force to replace it with the bundle")
        parent = target.parent
        if parent.exists() and not parent.is_dir():
            raise _Refusal(f"cannot write {path}: {parent} is not a folder")
        if parent.is_dir() and not os.access(parent, os.W_OK):
            raise _Refusal(f"cannot write {path}: the folder {parent} cannot be written to")
    except OSError as e:
        raise _Refusal(f"cannot write {path} ({look.why(e)})") from e


def _signals(
    ns: argparse.Namespace, arms: Sequence[tuple[str, Any]], events: frozenset[str]
) -> tuple[dict[str, tuple[Any, ...]], dict[str, tuple[Any, ...]]]:
    """Each arm's rows as TF21's reader classifies them, before and after the ``--verdicts``
    join (the same rows when there is no file). On stored runs the join is made here, over both
    runs' rows at once, by case (SV10); on tool folders it was made as they were read."""
    from poisson_trace.ingest.prove import read_rows

    root = Path(ns.store)
    before = {arm: read_rows(root, run.run_id, sorted(events)) for arm, run in arms}
    after = dict(before)
    if ns.verdicts is not None and ns.joined is None:
        from poisson_trace.ingest import verdicts
        from poisson_trace.ingest.rows import Refusal

        rows = [row for arm, _ in arms for row in before[arm]]
        try:
            joined = verdicts.join(rows, Path(ns.verdicts), None)
        except Refusal as e:
            raise _Refusal(str(e), *e.nexts) from None
        ns.joined = verdicts.block(Path(ns.verdicts), joined)
        at = 0
        for arm, _ in arms:
            n = len(before[arm])
            after[arm] = tuple(joined.rows[at : at + n])
            at += n
    return before, after


_MISALIGNED = "the run's rows and its signals do not line up; the report was not printed"


def _filled(frame: Any, before: Sequence[Any], after: Sequence[Any], events: frozenset[str]) -> Any:
    """The run's frame with the outcomes a verdict filled: a filled ``fail`` counts as failed
    whatever the run's failure words, a filled success as not (SV10 item 4); a try with a
    recorded outcome is as it was, since a verdict that differed was refused."""
    changed = [
        (i, a)
        for i, (b, a) in enumerate(zip(before, after, strict=True))
        if (a.outcome, a.error) != (b.outcome, b.error)
    ]
    if not changed:
        return frame
    if len(frame) != len(before):
        raise look.Failed(_MISALIGNED)
    frame = frame.copy()
    for column in ("outcome", "error"):
        frame[column] = frame[column].astype(object)
    words = sorted(events)
    at_outcome, at_error = frame.columns.get_loc("outcome"), frame.columns.get_loc("error")
    for i, row in changed:
        config = frame["config"].iloc[i]
        same = frame["config_hash"].iloc[i] == row.case or (
            isinstance(config, Mapping) and config.get("case") == row.case
        )
        if not same:
            raise look.Failed(_MISALIGNED)
        outcome = row.outcome
        if row.result == "fail" and outcome not in events:
            outcome = words[0]
        frame.iat[i, at_outcome] = outcome
        frame.iat[i, at_error] = None
    return frame


def _verdicts_line(block: Mapping[str, Any]) -> str:
    return (
        f"  verdicts  {block['name']} · rows {count(block['rows'])} · joined by case "
        f"{count(block['by_case'])} · by input {count(block['by_input'])} · matched no case "
        f"{count(block['unmatched'])}"
    )


def _absolute(ns: argparse.Namespace) -> dict[str, str]:
    """Each absolute path the command carried, and the name it is written as in what is saved:
    its last folder's or file's name (section 11.2's rule, SV7; section 17.3 item 9)."""
    paths: list[str] = []
    for word in (ns.store, ns.typed_store, ns.config):
        if isinstance(word, str) and word:
            paths.append(word)
    held = ns.settings
    if held is not None and held.given:
        paths.append(str(held.path))
    paths.extend(w for w in ns.folder_words.values() if isinstance(w, str))
    out: dict[str, str] = {}
    for path in paths:
        if os.path.isabs(path):
            name = Path(path).name or Path(path).resolve().name
            out[path] = name
    return out


def _came(ns: argparse.Namespace, flag: str, in_config: bool = False) -> str:
    """Where a setting came from: the flag, trace.toml or the default (SV5)."""
    if flag in ns.typed_flags:
        return "flag"
    return "trace.toml" if in_config else "default"


def _file_digest(path: str) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _settings(ns: argparse.Namespace, verb: str, selecting: Any = None) -> dict[str, Any]:
    """The result-changing settings of a verb, in their order (SV5), then where each came from
    and the config's names of the stores read."""
    held = ns.settings
    events = sorted(ns.event)
    verdicts = None if ns.verdicts is None else _file_digest(ns.verdicts)
    settings: dict[str, Any] = {"events": events}
    came: dict[str, str] = {
        "events": _came(ns, "--event", held is not None and held.events is not None)
    }
    if verb in ("where", "compare"):
        settings["by"], came["by"] = ns.by, _came(ns, "--by")
        settings["at"], came["at"] = list(ns.at), _came(ns, "--at")
    if verb == "where":
        settings.update({"boot": ns.boot, "seed": ns.seed})
        came.update({"boot": _came(ns, "--boot"), "seed": _came(ns, "--seed")})
    if verb == "compare":
        settings["max_mde_hr"] = ns.max_mde_hr
        in_config = held is not None and held.max_mde_hr is not None
        came["max_mde_hr"] = _came(ns, "--max-mde-hr", in_config)
    if verb == "fix-check":
        settings["inputs"], came["inputs"] = ns.inputs, _came(ns, "--inputs")
        settings["failing_from"] = None if selecting is None else selecting.run_id
        came["failing_from"] = _came(ns, "--failing-from")
        settings["min_failures"] = (
            None if selecting is None else (1 if ns.min_failures is None else ns.min_failures)
        )
        came["min_failures"] = _came(ns, "--min-failures")
        settings["max_mde"] = ns.max_mde
        came["max_mde"] = _came(ns, "--max-mde", held is not None and held.max_mde is not None)
    if verb in _TWO_RUNS:
        settings["alpha"], came["alpha"] = ns.alpha, _came(ns, "--alpha")
    if verb == "fix-check":
        settings.update({"seed": ns.seed, "max_change": dict(ns.ceilings)})
        came.update({"seed": _came(ns, "--seed")})
        came["max_change"] = _came(ns, "--max-change", held is not None and bool(held.max_change))
    if verb in _TWO_RUNS:
        settings["verdicts"], came["verdicts"] = verdicts, _came(ns, "--verdicts")
    settings["from"] = came
    settings["stores"] = (
        [ns.typed_store] if held is not None and ns.typed_store in held.named else []
    )
    return settings


def _digest_of(manifest: Any) -> str:
    """The digest of the rules a run's failure types were decided by: the one its import
    recorded, or the built-in rules' for a run Prove swept (SV4 item 4)."""
    from poisson_trace.ingest.taxonomy import taxonomy_sha256

    environment = getattr(manifest, "environment", None)
    recorded = environment.get("import") if isinstance(environment, Mapping) else None
    digest = recorded.get("taxonomy_sha256") if isinstance(recorded, Mapping) else None
    return digest if isinstance(digest, str) else taxonomy_sha256((), None)


DIFFERENT_RULES = (
    "The failure types of the two runs were decided by different rules, so their counts are "
    "not set side by side; the digest of each run's rules is given."
)


def _taxonomy_diff(
    arms: Sequence[str], rows: Mapping[str, Sequence[Any]], manifests: Mapping[str, Any]
) -> tuple[dict[str, Any], str | None]:
    """The saved verdict's failure-type diff (SV4 item 4, SV9): each run's taxonomy digest,
    whether the rules are the same, the tries, and each kind's and signal's count in each run
    in section 18.5.1's order; no counts, and a note, when the rules differ."""
    from poisson_trace.ingest.rows import FAILURE_KINDS, SIGNALS

    digests = {arm: _digest_of(manifests[arm]) for arm in arms}
    same = len(set(digests.values())) == 1
    kinds = signals = None
    if same:
        kinds = [
            {
                "failure_kind": k,
                **{arm: sum(1 for r in rows[arm] if r.failure_kind == k) for arm in arms},
            }
            for k in FAILURE_KINDS
            if any(r.failure_kind == k for arm in arms for r in rows[arm])
        ]
        signals = [
            {"signal": s, **{arm: sum(1 for r in rows[arm] if s in r.signals) for arm in arms}}
            for s in SIGNALS
            if any(s in r.signals for arm in arms for r in rows[arm])
        ]
    diff = {
        "taxonomy_sha256": digests,
        "same_rules": same,
        "tries": {arm: len(rows[arm]) for arm in arms},
        "kinds": kinds,
        "signals": signals,
    }
    return diff, None if same else DIFFERENT_RULES


def _measures(
    ns: argparse.Namespace,
    rows: Mapping[str, Sequence[Any]],
    arms: Sequence[tuple[str, Any]],
    labels: tuple[str, str],
) -> Any:
    """TF23's comparison of the two runs' time, length, tokens and cost over every case both
    hold (SV6), at the verb's level, the ceilings the config and the flags set."""
    from poisson_trace.ingest.tries import version_of
    from poisson_trace.stats.continuous import compare

    (arm_a, run_a), (arm_b, run_b) = arms
    return compare(
        version_of(rows[arm_a], run_a.run_id, labels[0]),
        version_of(rows[arm_b], run_b.run_id, labels[1]),
        ceilings=ns.ceilings or None,
        alpha=ns.alpha,
    )


MEASURES_HEADING = "## Time, length, tokens and cost"
NOTHING_MEASURED = "No try in either run recorded a time, a length, tokens or a cost."


def _measures_section(comparison: Any) -> list[str]:
    """The report's section: the heading, the table, and each measure shown with its lines."""
    from poisson_trace.stats.continuous import table

    header, rows = table(comparison)
    if not rows:
        return [MEASURES_HEADING, "", NOTHING_MEASURED]
    body = look.table(header, rows).rstrip("\n").split("\n")
    bullets = [f"- {row[0]}: " + " ".join(comparison.measures[row[0]].lines) for row in rows]
    return [MEASURES_HEADING, "", *body, "", *bullets]


def _none(x: Any) -> float | None:
    return None if x is None else float(x)


def _where_rows(data: Mapping[str, Any]) -> list[Any]:
    from poisson_trace.saved import Row

    placement = data["run"]["placement"]
    band = 0.95
    rows = [Row("tries", placement["placed"], "a"), Row("failed", placement["died"], "a")]
    for point in data["curve"]:
        step = int(point["step"])
        rows.append(Row("survival", point["survival"], "a", step=step))
        for bound in ("lo", "hi"):
            value = _none(point[bound])
            rows.append(Row(f"survival_{bound}", value, "a", level=band, step=step, note="no band"))
    rows.append(Row("median_step", _none(data["median_step"]), "a", note="none failed"))
    for cause in data["causes"]:
        k = cause["cause"]
        rows.append(Row("share", cause["f"], "a", cause=k))
        rows.append(Row("share_lo", _none(cause["lo"]), "a", level=band, cause=k, note="no band"))
        rows.append(Row("share_hi", _none(cause["hi"]), "a", level=band, cause=k, note="no band"))
    return rows


def _compare_rows(data: Mapping[str, Any]) -> list[Any]:
    from poisson_trace.saved import Row

    c = data["comparison"]
    band = 0.95
    rows = []
    for arm in ("a", "b"):
        placement = data["runs"][arm]["placement"]
        rows += [Row("tries", placement["placed"], arm), Row("failed", placement["died"], arm)]
    rows += [
        Row("p", c["p"]),
        Row("hr", _none(c["hazard_ratio"]), note="no information"),
        Row("hr_lo", _none(c["hazard_ratio_lo"]), level=band, note="no information"),
        Row("hr_hi", _none(c["hazard_ratio_hi"]), level=band, note="no information"),
        Row("mde_hr", _none(c["mde_hazard_ratio"]), note="no information"),
        Row("max_mde_hr", c["max_mde_hr"]),
    ]
    for per in data["per_cause"]:
        k = per["cause"]
        rows += [
            Row("failed", per["deaths_a"], "a", cause=k),
            Row("failed", per["deaths_b"], "b", cause=k),
            Row("p", per["p"], cause=k),
            Row("q", _none(per["q"]), cause=k, note="no correction"),
            Row("mde_hr", _none(per["mde_hazard_ratio"]), cause=k, note="no information"),
        ]
    for at in data["at"]:
        step = int(at["step"])
        rows += [
            Row("survival", at["survival_a"], "a", step=step),
            Row("survival", at["survival_b"], "b", step=step),
            Row("diff", at["diff"], step=step),
            Row("diff_lo", at["lo"], level=band, step=step),
            Row("diff_hi", at["hi"], level=band, step=step),
        ]
    return rows


def _input_rows(input_: Mapping[str, Any]) -> list[Any]:
    from poisson_trace.saved import Row

    condition, h = input_["config"], input_["config_hash"]
    rows = []
    for arm, key in (("a", "a"), ("b", "b")):
        runs, failed = input_[f"runs_{key}"], input_[f"failed_{key}"]
        rows += [
            Row("tries", runs, arm, condition, h),
            Row("failed", failed, arm, condition, h),
            Row("share", failed / runs if runs else None, arm, condition, h, note="no try"),
        ]
    rows.append(Row("p", input_["p"], "both", condition, h))
    rows.append(Row("q", _none(input_["q"]), "both", condition, h, note="no correction"))
    return rows


def _fix_check_rows(data: Mapping[str, Any]) -> list[Any]:
    from poisson_trace.saved import Row

    level = 1.0 - data["test"]["alpha"]
    rows = []
    for arm, key in (("a", "old"), ("b", "new")):
        held = data["rows"][key]
        runs, failed = held["runs"], held["failed"]
        rows += [
            Row("tries", runs, arm),
            Row("failed", failed, arm),
            Row("share", failed / runs if runs else None, arm, note="no try"),
        ]
    d, limits = data["difference"], data["limits"]
    rows += [
        Row("difference", d["points"]),
        Row("range_lo", _none(d["lo"]), level=level, note="no interval"),
        Row("range_hi", _none(d["hi"]), level=level, note="no interval"),
        Row("p", data["test"]["p"]),
        Row("drop_limit", _none(limits["drop"]), level=level, note="none detectable"),
        Row("rise_limit", _none(limits["rise"]), level=level, note="none detectable"),
        Row("max_mde", limits["max_mde"]),
    ]
    for input_ in data["changes"]["rows"]:
        rows += _input_rows(input_)
    return rows


def _changes_rows(data: Mapping[str, Any]) -> list[Any]:
    from poisson_trace.saved import Row

    rows = []
    for arm, key in (("a", "a"), ("b", "b")):
        runs = sum(r[f"runs_{key}"] for r in data["rows"])
        failed = sum(r[f"failed_{key}"] for r in data["rows"])
        rows += [
            Row("tries", runs, arm),
            Row("failed", failed, arm),
            Row("share", failed / runs if runs else None, arm, note="no try"),
        ]
    for input_ in data["rows"]:
        rows += _input_rows(input_)
    return rows


_TABLE_ROWS: dict[str, Callable[[Mapping[str, Any]], list[Any]]] = {
    "where": _where_rows,
    "compare": _compare_rows,
    "fix-check": _fix_check_rows,
    "changes": _changes_rows,
}


def _with_tail(doc: Mapping[str, Any], tail: Mapping[str, Any]) -> dict[str, Any]:
    """The verb's JSON with ``tail``'s keys before ``next``."""
    out = {k: v for k, v in doc.items() if k != "next"}
    out.update(tail)
    out["next"] = doc["next"]
    return out


def _result_document(
    printed: Mapping[str, Any],
    data: Mapping[str, Any],
    added: Mapping[str, Any],
    notes: Sequence[str],
    saved_at: str | None,
) -> dict[str, Any]:
    """``result.json``: the printed JSON with section 11.3's keys and TF6's (SV3, SV4): the
    summary's lines, the caveats, ``note`` as a list, the versions, and the two-run blocks;
    ``saved`` and ``next`` last."""
    from poisson_trace import saved

    body = {k: v for k, v in printed.items() if k not in ("saved", "next")}
    out: dict[str, Any] = {}
    for key, value in body.items():
        if key == "note":
            held = [value] if isinstance(value, str) else list(value)
            out[key] = [*held, *[n for n in notes if n not in held]]
        else:
            out[key] = value
    more = {
        "summary": [[label, text] for label, text in data.get("_summary") or ()],
        "before_you_act": list(data.get("_before_you_act") or ()),
        "note": list(notes),
        "versions": {"trace": saved.trace_version(), "prove": saved.prove_version()},
        **added,
    }
    for key, value in more.items():
        if key not in out:
            out[key] = value
    out["saved"] = saved_at
    out["next"] = printed["next"]
    return out


def _deliver(
    ns: argparse.Namespace,
    data: dict[str, Any],
    verdict: str,
    sentence: str,
    following: str,
    *,
    kind: str,
    report: Any,
    runs: Sequence[tuple[str, Any, Any]],
    settings: Mapping[str, Any],
    diff: tuple[Mapping[str, Any], str | None] | None = None,
    measures: Any = None,
    charts: Sequence[tuple[str, str, Mapping[str, Any]]] = (),
    wrote_svg: str | None = None,
) -> int:
    """Print the verb's report or JSON, with what the new options add: the measures and the
    join in the JSON before ``next``, the detail lines under the verdict line in their order
    (verdicts, wrote, wrote, saved), and the verdict saved as an artifact and handed over as a
    bundle where ``--save`` or ``--out`` asked (section 17.3 items 3 to 5)."""
    import shutil
    import tempfile

    from poisson_trace import saved

    tail: dict[str, Any] = {}
    if measures is not None and getattr(ns, "measures", False):
        tail["continuous_measures"] = measures.to_dict()
    if ns.joined is not None:
        tail["verdicts"] = ns.joined
    enveloped = _enveloped(data, verdict, sentence, following)
    doc = _with_tail({k: v for k, v in enveloped.items() if not k.startswith("_")}, tail)
    markdown = report.to_markdown()
    details = []
    if ns.joined is not None:
        details.append(_verdicts_line(ns.joined))
    if wrote_svg is not None:
        details.append(f"  wrote  {wrote_svg}")
    saved_at = None
    if ns.save or ns.out is not None:
        absolute = _absolute(ns)
        added: dict[str, Any] = {}
        notes: list[str] = []
        if diff is not None:
            added["failure_taxonomy_diff"] = diff[0]
            if diff[1] is not None:
                notes.append(diff[1])
        if measures is not None:
            added["continuous_measures"] = measures.to_dict()
        ids = [run.run_id for _, run, _ in runs]
        identity = saved.artifact_id(kind, {"runs": ids}, settings)
        place = None if ns.temp_store else saved.saved_path(kind, identity)
        result = saved.shortened(_result_document(doc, data, added, notes, place), absolute)
        joined_line = details[:1] if ns.joined is not None else []
        text = saved.short(_said(verdict, sentence, markdown, following, *joined_line), absolute)
        artifact = saved.Artifact(
            kind=kind,
            runs=ids,
            settings=settings,
            result=result,
            report=text,
            events=sorted(ns.event),
            rows=_TABLE_ROWS[kind](result),
            detail=[(label, text) for label, text in result["summary"]],
            charts=charts,
        )
        staging = Path(tempfile.mkdtemp(prefix="poisson-trace-"))
        try:
            saved.build_artifact(staging, artifact)
            if ns.temp_store:
                look.err(
                    "note: the verdict was not saved: the runs were read from folders, not a "
                    "store\n"
                )
            else:
                try:
                    saved.save_artifact(Path(ns.store), staging, kind, identity)
                except OSError as e:
                    look.err(f"note: the verdict was not saved: {look.why(e)}\n")
                else:
                    saved_at = saved.saved_path(kind, identity)
            if ns.out is not None:
                held = None if ns.from_folders else saved.short(ns.store, absolute)
                refs = [saved.RunRef(run.run_id, run.name, held) for _, run, _ in runs]
                # the bundle is a copy of the artifact as the store holds it, so a second --out
                # on the same runs hands over the same bytes (section 11.6, TF6-19); the
                # staging folder stands in when the store could not be written to
                source = staging if saved_at is None else Path(ns.store) / saved_at
                try:
                    saved.write_bundle(source, Path(ns.out), kind, refs, force=ns.force)
                except OSError as e:
                    raise look.Failed(
                        f"could not write {ns.out} ({look.why(e)}); the report was not printed"
                    ) from e
                details.append(f"  wrote  {ns.out}")
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    if saved_at is not None:
        doc["saved"] = saved_at
        doc = _with_tail(doc, {})
        details.append(f"  saved  {kind} {identity[:12]}")
    if ns.json:
        look.out(json.dumps(doc, indent=2, allow_nan=False) + "\n")
    else:
        look.out(_said(verdict, sentence, markdown, following, *details))
    return look.DONE


def _handover(ns: argparse.Namespace) -> int:
    """``poisson-trace handover --check DIR``: ok and exit 0 on a bundle that holds what it
    promises, ``not valid`` with the first failing line and exit 4 otherwise, a refusal when
    DIR is not a bundle (section 11.2's validator, SV8)."""
    from poisson_trace import saved

    if ns.check is None:
        raise look.Usage(
            "--check DIR is required: the bundle to check", "poisson-trace handover --help"
        )
    try:
        checked = saved.check_bundle(Path(ns.check))
    except saved.NotABundle as e:
        raise _Refusal(str(e)) from None
    except saved.Invalid as e:
        look.out(f"not valid  {e}\n")
        return look.CHECK_FAILED
    look.out(f"ok  {checked.sentence}\n")
    return look.DONE


# ---------- runs ----------


def _plural(n: int, one: str, many: str) -> str:
    return f"{count(n)} {one if n == 1 else many}"


# the key under the listing for a start that is a file's modification time
FILE_MARK = "(file): the start is when the file was written or copied, not when the run ran"


def _utc_minute(run: Any) -> str:
    return str(run.started.strftime("%Y-%m-%d %H:%M"))


def _runs(ns: argparse.Namespace) -> int:
    store, index = _named(ns)
    events = list(dict.fromkeys(ns.event or ()))
    complete = index.complete
    if ns.all:
        listed = list(index.runs)
    else:
        listed = [r for r in index.runs if r.complete and r.number <= _LISTED]
    if not events:
        where = "" if ns.settings is None else f" and {ns.settings.shown} names no failures"
        look.err(f"note: no --event was given{where}, so the failed column is not counted\n")
    if ns.all and len(complete) > _LISTED:
        look.err(
            f"note: --all reads the rows of every one of the {count(len(index.runs))} runs, "
            "which may take a while on a store this size\n"
        )
    if index.unreadable:
        unread = _plural(len(index.unreadable), "run", "runs")
        look.err(
            f"note: Prove could not read the record or the start time of {unread} of this store, "
            "not listed: "
            f"{', '.join(index.unreadable)}\n"
        )
    rows = []
    carried: set[str] = set()
    read: list[Any] = []
    for run in listed:
        try:
            tally = store.tally(run.run_id)
            frame = store.read(run.run_id, meta=False, trace="envelope")
        except Exception as e:
            # one run whose rows cannot be read leaves the listing of the others whole
            look.err(
                f"note: Prove could not read the rows of {run.shown()} ({look.why(e)}), "
                "not listed\n"
            )
            continue
        read.append(run)
        outcomes = [o for o in frame["outcome"] if not _no_value(o)]
        carried.update(outcomes)
        rows.append(
            {
                "number": run.number,
                "name": run.name,
                "run_id": run.run_id,
                "named_by": run.named_by,
                "rows": int(tally.rows),
                "failed": sum(1 for o in outcomes if o in events) if events else None,
                "traced": bool(frame["trace"].notna().any()) if len(frame) else False,
                "created_at": run.created_at,
                "status": run.status,
                "target_id": run.target_id,
                "backend": run.backend,
            }
        )
    missing = [e for e in events if e not in carried]
    if listed and len(missing) == len(events) and events:
        raise _Refusal(
            f"unknown event {', '.join(missing)}; the runs listed carry the outcomes: "
            f"{', '.join(sorted(carried)) or 'none'}"
        )
    yours = sum(1 for r in index.runs if r.named_by == "you")
    total = len(index.runs)
    theirs = total - yours
    sentence = (
        f"{_plural(total, 'run', 'runs')} in {ns.store} (newest first); {count(yours)} named "
        f"by you, {count(theirs)} named from {'its manifest' if theirs == 1 else 'their manifests'}"
    )
    traced = next(
        (index.by_id(r["run_id"]) for r in rows if r["traced"] and r["status"] == "complete"),
        None,
    )
    if traced is None:
        following = look.command("poisson-trace", "fix-check", "--help")
    else:
        following = _next(index, "where", (traced,), ns)
    if ns.json:
        doc = {
            "schema": "poisson-trace.runs/1",
            "verdict": "ok",
            "sentence": sentence,
            "store": ns.store,
            "runs": rows,
            "next": following,
        }
        look.out(json.dumps(doc, indent=2, allow_nan=False) + "\n")
        return look.DONE
    hidden = 0 if ns.all else total - len(complete)
    older = 0 if ns.all else max(0, len(complete) - _LISTED)
    from poisson_trace.names import FILE_TIME

    filed = [run.started_from == FILE_TIME for run in read]
    lines = _runs_table(
        rows,
        [_utc_minute(run) + (" (file)" if f else "") for run, f in zip(read, filed, strict=True)],
    )
    if any(filed):
        lines.append(FILE_MARK)
    if older:
        lines.append(
            f"  {_plural(older, 'older complete run is', 'older complete runs are')} not listed; "
            "--all lists them"
        )
    if hidden:
        lines.append(
            f"  {_plural(hidden, 'partial run is', 'partial runs are')} not listed; "
            "--all lists them"
        )
    report = "\n".join(lines) + "\n\n" if lines else ""
    look.out(f"ok  {sentence}\n\n{report}next: {following}\n")
    return look.DONE


def _runs_table(rows: Sequence[Mapping[str, Any]], started: Sequence[str]) -> list[str]:
    """The listing's columns, numbers to the right; the start as UTC to the minute."""
    if not rows:
        return []
    cells = [
        (
            "–" if r["number"] is None else str(r["number"]),
            r["name"],
            count(r["rows"]),
            "–" if r["failed"] is None else count(r["failed"]),
            "yes" if r["traced"] else "no",
            at,
            r["status"],
        )
        for r, at in zip(rows, started, strict=True)
    ]
    head = ("#", "name", "rows", "failed", "traces", "started", "status")
    widths = [max(len(c[i]) for c in [head, *cells]) for i in range(len(head))]
    right = (True, False, True, True, False, False, False)

    def line(cell: Sequence[str]) -> str:
        parts = [
            c.rjust(w) if r else c.ljust(w) for c, w, r in zip(cell, widths, right, strict=True)
        ]
        return ("  " + "  ".join(parts)).rstrip()

    return [line(head), *(line(c) for c in cells)]


# ---------- name ----------


def _name(ns: argparse.Namespace) -> int:
    from poisson_trace import names

    store, index = _named(ns, lenient=True)
    shown = index.names_shown()
    listing = index.listing()
    if ns.list:
        return _name_list(index, shown, listing)
    given = ns.run.strip()
    entries = dict(index.entries)
    damage = index.damage()
    if ns.forget:
        if damage is not None and given in entries:
            # an entry the file should not hold: this one name is taken back, and no other
            held = entries.pop(given)
            names.write_names_file(index.root, shown, entries)
            where = "" if index.by_id(held) is not None else ", which this store does not hold"
            look.out(
                f'ok  forgot the name "{given}" of the run {held}{where}, in {shown}\n\n'
                f"next: {listing}\n"
            )
            return look.DONE
        if damage is not None:
            raise damage
        run = index.resolve(ns.run)
        mine = [n for n, r in entries.items() if r == run.run_id]
        if not mine:
            if run.imported:
                whose = "the one it was imported under"
            elif run.swept is not None:
                whose = "the one it was given when it was swept"
            else:
                whose = "from its manifest"
            raise _Refusal(f"{run.shown()} has no name of yours to forget; its name is {whose}")
        for old in mine:
            del entries[old]
        names.write_names_file(index.root, shown, entries)
        again = run.without_yours
        look.out(
            f'ok  forgot the name "{mine[0]}" of {run.run_id}, which is named "{again}" again, '
            f"in {shown}\n\nnext: {listing}\n"
        )
        return look.DONE
    if damage is not None:
        raise damage
    run = index.resolve(ns.run)
    if run.status == "unreadable":
        raise _Refusal(
            f"Prove could not read the record or the start time of the run {run.run_id}, so it "
            "cannot be named; it is reached by its id"
        )
    new = ns.new.strip()
    why = names.unfit(new)
    if why is not None:
        raise _Refusal(f'"{new or ns.new}" cannot be a name: {why}')
    if any(r.run_id == new for r in index.runs) or new in index.unreadable:
        raise _Refusal(f'"{new}" cannot be a name: it is the id of a run of this store')
    others = index.holder(new) - {run.run_id}
    if others:
        other = index.by_id(sorted(others)[0])
        whose = other.shown() if other is not None else "another run"
        raise _Refusal(f'"{new}" cannot be a name: {whose} answers to it already')
    if entries.get(new) == run.run_id:
        look.out(f'ok  {run.run_id} is named "{new}" already, in {shown}\n\nnext: {listing}\n')
        return look.DONE
    entries = {n: r for n, r in entries.items() if r != run.run_id}
    entries[new] = run.run_id
    names.write_names_file(index.root, shown, entries)
    look.out(f'ok  named {run.run_id} "{new}" in {shown}\n\nnext: {listing}\n')
    return look.DONE


def _name_list(index: Any, shown: str, listing: str) -> int:
    entries = index.entries
    if not entries:
        look.out(f"ok  no names of yours in {index.store}\n\nnext: {listing}\n")
        return look.DONE
    cells = []
    for name in sorted(entries):
        run = index.by_id(entries[name])
        if run is None and entries[name] in index.unreadable:
            own = "its record cannot be read"
        elif run is None:
            own = "not in this store"
        else:
            own = run.without_yours
        cells.append((name, own, entries[name]))
    head = ("name", "name from its manifest", "run")
    widths = [max(len(c[i]) for c in [head, *cells]) for i in range(3)]
    lines = [
        ("  " + "  ".join(c.ljust(w) for c, w in zip(cell, widths, strict=True))).rstrip()
        for cell in [head, *cells]
    ]
    sentence = f"{_plural(len(entries), 'name', 'names')} of yours in {shown}"
    look.out(f"ok  {sentence}\n\n" + "\n".join(lines) + f"\n\nnext: {listing}\n")
    return look.DONE


# ---------- where ----------


def _where(ns: argparse.Namespace) -> int:
    import poisson_prove
    from poisson_prove.steps import declaration_check

    from poisson_trace import summary
    from poisson_trace.clock import _reached_by, place
    from poisson_trace.report import CANNOT_SAY, WhereReport
    from poisson_trace.survival import competing, competing_band

    if ns.svg is not None:
        _check_svg(ns.svg, ns.force)
    if ns.out is not None:
        _check_out(ns.out, ns.force)
    store, index = _named(ns)
    run = index.resolve(ns.run)
    manifest, frame, tally = _load(store, run)
    events = frozenset(ns.event)
    present = _outcomes(frame)
    missing = sorted(events - present)
    if missing:
        raise _Refusal(
            f"unknown event {', '.join(missing)}; the run carries the outcomes: "
            f"{', '.join(sorted(present)) or 'none'}"
        )
    placement = place(manifest, frame, tally, events=events, by=ns.by)
    index_steps = _arrays(placement)[0]
    causes = _ordered({p.cause for p in placement.rows if p.died})
    tries = _tries(placement)
    aj = competing(tries, causes)
    band = competing_band(tries, causes, ns.at, b=ns.boot, seed=ns.seed) if tries else None
    curve = []
    for i, step in enumerate(aj.steps):
        curve.append(
            {
                "step": int(step),
                "at_risk": int(aj.at_risk[i]),
                "died": int(aj.failed[i]),
                "survival": float(aj.share[i]),
                # the band resamples inputs; no variance formula stands behind it
                "var": None,
                "lo": None if band is None else float(band.curve[0][i]),
                "hi": None if band is None else float(band.curve[1][i]),
            }
        )
    at_rows = []
    for j, (q, s) in enumerate(zip(ns.at, aj.at(ns.at), strict=True)):
        at_rows.append(
            {
                "step": q,
                "survival": float(s),
                "lo": None if band is None else float(band.at[0][j]),
                "hi": None if band is None else float(band.at[1][j]),
            }
        )
    cause_rows = []
    for k in causes:
        cause_rows.append(
            {
                "cause": k,
                "deaths": int(sum(1 for p in placement.rows if p.died and p.cause == k)),
                "f": aj.final[k],
                "lo": None if band is None else band.final[k][0],
                "hi": None if band is None else band.final[k][1],
            }
        )
    failed_steps = sorted(p.index for p in placement.rows if p.died)
    # the median step of the failed tries: the lower middle one where their number is even
    median = failed_steps[(len(failed_steps) - 1) // 2] if failed_steps else None
    data: dict[str, Any] = {
        "schema": "poisson-trace.where/1",
        "prove": {"version": poisson_prove.__version__, "store": _store_shown(ns)},
        "run": _header(run, manifest, placement),
        "events": sorted(events),
        "clock": {"unit": "leaf span index", "by": ns.by},
        "curve": curve,
        "median_step": median,
        "at": at_rows,
        "causes": cause_rows,
        "bootstrap": {"b": ns.boot, "seed": ns.seed},
        # the share of tries that timed out, an end of its own beside the kinds, with its band;
        # the first step by which half of all tries had failed; the last step a try reached
        "_timed_out": {
            "count": sum(1 for p in placement.rows if p.reason == "timed out"),
            "f": aj.timed_out,
            "lo": None if band is None else band.timed_out[0],
            "hi": None if band is None else band.timed_out[1],
        },
        "_half_step": aj.half(),
        "_last_step": int(index_steps.max()) if len(index_steps) else None,
    }
    check = declaration_check(manifest, frame)
    if check is not None:
        data["declared"] = check.provenance()
        data["_reached"] = _reached_by(manifest, frame, events=events, by=ns.by)
    data["cannot_say"] = list(CANNOT_SAY)
    traced = _traced(frame)
    if not traced:
        if ns.svg is not None:
            raise _Refusal(
                f"{look.word(index.word_for(run))} has no traces{_from(run)}, so there is no "
                "curve for --svg to draw; fix-check and changes read it"
            )
        data["note"] = _no_traces(run)
    before = _run_before(index, run)
    if before is None:
        following = look.command("poisson-trace", "fix-check", "--help")
    elif traced:
        following = _next(index, "compare", (before, run), ns)
    else:
        # compare reads traces, and this run has none: the fix check reads its outcomes
        following = _next(index, "fix-check", (before, run), ns, "--inputs", "all")
    this = look.word(index.word_for(run))
    data["_how"] = (
        f"it was imported from {run.backend[len('import:') :]}"
        if run.imported
        else "it was stored without traces"
    )
    plain = summary.where(
        data,
        compare=None if before is None else _next(index, "compare", (before, run), ns),
        passing=look.command(
            "poisson-trace", "where", this, *_reach(ns), "--event", "PASSING-OUTCOME"
        ),
        fix_check=(
            look.command("poisson-trace", "fix-check", "OLD", this, *_flags(ns), "--inputs", "all")
            if before is None
            else _next(index, "fix-check", (before, run), ns, "--inputs", "all")
        ),
    )
    data["_summary"], data["_before_you_act"] = plain.lines, plain.caveats
    sentence = plain.sentence
    report = WhereReport(
        data=data,
        last_step=int(index_steps.max()) if len(index_steps) else 0,
        incidence={k: [float(x) for x in aj.incidence[k]] for k in causes},
    )
    if ns.svg is not None:
        _write_svg(ns.svg, report.to_svg())
    charts: list[tuple[str, str, dict[str, Any]]] = []
    if traced and (ns.save or ns.out is not None):
        chart = {"curve": data["curve"], "at": data["at"], "causes": data["causes"]}
        charts.append(("curve", report.to_svg(), chart))
    return _deliver(
        ns,
        data,
        "ok",
        sentence,
        following,
        kind="where",
        report=report,
        runs=[("a", run, manifest)],
        settings=_settings(ns, "where"),
        charts=charts,
        wrote_svg=ns.svg,
    )


def _check_svg(path: str, force: bool) -> None:
    """Refuse, before any work, an SVG path that cannot be written or would replace a file
    without --force."""
    try:
        _refuse_svg(path, force)
    except OSError as e:
        raise _Refusal(f"cannot write {path} ({look.why(e)})") from e


def _refuse_svg(path: str, force: bool) -> None:
    target = Path(path)
    folder = target.parent
    # a link counts as there, even when what it points to is not
    there = target.exists() or target.is_symlink()
    if target.is_dir():
        raise _Refusal(f"cannot write {path}: it is a folder")
    if not folder.is_dir():
        what = "is not a folder" if folder.exists() else "does not exist"
        raise _Refusal(f"cannot write {path}: the folder {folder} {what}")
    if not os.access(folder, os.W_OK):
        raise _Refusal(f"cannot write {path}: the folder {folder} cannot be written to")
    if there and not force:
        raise _Refusal(f"{path} exists; add --force to replace it")
    if target.exists() and not os.access(target, os.W_OK):
        raise _Refusal(f"cannot write {path}: the file cannot be written to")


def _write_svg(path: str, text: str) -> None:
    try:
        Path(path).write_text(text, encoding="utf-8")
    except OSError as e:
        raise look.Failed(
            f"could not write {path} ({look.why(e)}); the report was not printed"
        ) from e


# ---------- compare ----------


def _compare(ns: argparse.Namespace) -> int:
    import numpy as np
    import poisson_prove

    from poisson_trace import summary
    from poisson_trace.clock import place
    from poisson_trace.report import CANNOT_SAY, CompareReport
    from poisson_trace.survival import (
        bh,
        competing,
        difference_band,
        information_limit,
        logrank_stratified,
        one_step,
    )

    if ns.out is not None:
        _check_out(ns.out, ns.force)
    store, index = _named(ns)
    # compare has never refused one run given twice; it reads the runs the words reach
    run_a, run_b = index.resolve(ns.a), index.resolve(ns.b)
    manifest_a, frame_a, tally_a = _load(store, run_a)
    manifest_b, frame_b, tally_b = _load(store, run_b)
    signals = None
    if ns.verdicts is not None or ns.save or ns.out is not None:
        signals = _signals(ns, [("a", run_a), ("b", run_b)], frozenset(ns.event))
        frame_a = _filled(frame_a, signals[0]["a"], signals[1]["a"], frozenset(ns.event))
        frame_b = _filled(frame_b, signals[0]["b"], signals[1]["b"], frozenset(ns.event))
    untraced = [r for r, f in ((run_a, frame_a), (run_b, frame_b)) if not _traced(f)]
    if untraced:
        # compare places deaths at steps, which a run with no traces has none of; the fix check
        # reads the outcomes alone
        named = {r.run_id: r for r in untraced}.values()
        said = " and ".join(f"{look.word(index.word_for(r))}{_from(r)}" for r in named)
        has, its = ("has", "its") if len(named) == 1 else ("have", "their")
        raise _Refusal(
            f"{said} {has} no traces, so compare has no step to place {its} episodes on; "
            "fix-check compares the runs by their outcomes",
            _next(index, "fix-check", (run_a, run_b), ns, "--inputs", "all"),
        )
    events = frozenset(ns.event)
    out_a, out_b = _outcomes(frame_a), _outcomes(frame_b)
    present = out_a | out_b
    missing = sorted(events - present)
    if missing:
        raise _Refusal(
            f"unknown event {', '.join(missing)}; the runs carry the outcomes: "
            f"{', '.join(sorted(present)) or 'none'}"
        )
    notes = [
        f"event {e}: carried by {'A' if e in out_a else 'B'} only"
        for e in sorted(events)
        if (e in out_a) != (e in out_b)
    ]
    placement_a = place(manifest_a, frame_a, tally_a, events=events, by=ns.by)
    placement_b = place(manifest_b, frame_b, tally_b, events=events, by=ns.by)
    rows_a, rows_b = placement_a.rows, placement_b.rows
    if not any(p.died for p in rows_a) and not any(p.died for p in rows_b):
        raise _Refusal(
            f"no death in either run for the events {', '.join(sorted(events))}; "
            "there is no curve to compare"
        )
    cells_a = {p.config_hash for p in rows_a}
    cells_b = {p.config_hash for p in rows_b}
    common = cells_a & cells_b
    if not common:
        raise _Refusal("the runs share no config cell, so there is nothing to stratify by")
    common_a = [p for p in rows_a if p.config_hash in common]
    common_b = [p for p in rows_b if p.config_hash in common]
    deaths_common = sum(p.died for p in common_a) + sum(p.died for p in common_b)
    if deaths_common == 0:
        raise _Refusal("no death in either run over the common cells; nothing to compare")
    lr = logrank_stratified(
        [(p.config_hash, p.index, p.died) for p in rows_a],
        [(p.config_hash, p.index, p.died) for p in rows_b],
    )
    # ST5: the limit from the log-rank's own information over the common cells
    mde = information_limit(lr.variance, alpha=ns.alpha)
    estimate = one_step(lr)
    if lr.observed_a < lr.expected_a:
        direction = "runs die later in A (before) than in B (after): runs die earlier in B"
        in_b = "earlier"
    elif lr.observed_a > lr.expected_a:
        direction = "runs die earlier in A (before) than in B (after): runs die later in B"
        in_b = "later"
    else:
        direction = "no direction"
        in_b = "neither earlier nor later"
    p_text = f"{lr.p:.3f}" if lr.p >= 0.001 else f"{lr.p:.2e}"
    if lr.p < ns.alpha:
        verdict = "different"
        sentence = (
            f"runs die {in_b} in B (after) than in A (before) "
            f"(log-rank, stratified by cell, p = {p_text})"
        )
        verdict_line = f"different: {sentence}"
    elif mde is not None and mde <= ns.max_mde_hr:
        verdict = "no significant difference"
        limit = f"could not have detected a hazard ratio below {mde:.3f}"
        sentence = f"p = {p_text}; {limit}"
        verdict_line = f"no significant difference (p = {p_text}); {limit}"
    else:
        verdict = "too small to tell"
        if mde is None:
            sentence = (
                "the log-rank has no information on these runs, so it could not have detected "
                f"any hazard ratio, and {ns.max_mde_hr:g} was asked for"
            )
        else:
            sentence = (
                f"could not have detected a hazard ratio below {mde:.3f}, "
                f"and {ns.max_mde_hr:g} was asked for"
            )
        verdict_line = f"too small to tell: {sentence}"
    guidance = information = None
    if verdict == "too small to tell":
        guidance, information = _compare_guidance(ns, common_a, common_b, mde)
    causes = _ordered({p.cause for p in rows_a + rows_b if p.died})
    tries_a, tries_b = _tries(placement_a), _tries(placement_b)
    at_rows = []
    if ns.at:
        share_a = competing(tries_a, causes).at(ns.at)
        share_b = competing(tries_b, causes).at(ns.at)
        lo, hi = difference_band(tries_a, tries_b, causes, ns.at, draws=_AT_DRAWS, seed=0)
        for j, q in enumerate(ns.at):
            at_rows.append(
                {
                    "step": q,
                    "survival_a": float(share_a[j]),
                    "survival_b": float(share_b[j]),
                    "diff": float(share_b[j] - share_a[j]),
                    "lo": float(lo[j]),
                    "hi": float(hi[j]),
                }
            )
    per: list[dict[str, Any]] = []
    for k in causes:
        lr_k = logrank_stratified(
            [(p.config_hash, p.index, p.died and p.cause == k) for p in rows_a],
            [(p.config_hash, p.index, p.died and p.cause == k) for p in rows_b],
        )
        per.append(
            {
                "cause": k,
                "deaths_a": sum(1 for p in rows_a if p.died and p.cause == k),
                "deaths_b": sum(1 for p in rows_b if p.died and p.cause == k),
                "statistic": lr_k.statistic,
                "p": lr_k.p,
                "q": None,
                # each kind's limit from its own cause-specific log-rank information
                "mde_hazard_ratio": information_limit(lr_k.variance, alpha=ns.alpha),
            }
        )
    if per:
        qs = bh(np.array([r["p"] for r in per], dtype=np.float64), ns.alpha)
        for row, q_value in zip(per, qs, strict=True):
            row["q"] = float(q_value)
    data: dict[str, Any] = {
        "schema": "poisson-trace.compare/1",
        "prove": {"version": poisson_prove.__version__, "store": _store_shown(ns)},
        "runs": {
            "a": _header(run_a, manifest_a, placement_a),
            "b": _header(run_b, manifest_b, placement_b),
        },
        "events": sorted(events),
        "clock": {"unit": "leaf span index", "by": ns.by},
        "at": at_rows,
        "comparison": {
            "cells": lr.cells,
            "excluded_cells": {"a_only": len(cells_a - common), "b_only": len(cells_b - common)},
            "observed_a": lr.observed_a,
            "expected_a": lr.expected_a,
            "variance": lr.variance,
            "statistic": lr.statistic,
            "p": lr.p,
            "alpha": ns.alpha,
            "direction": direction,
            "paired": False,
            # ST6: after against before, Peto's one-step estimate from the numbers above
            "hazard_ratio": None if estimate is None else estimate[0],
            "hazard_ratio_lo": None if estimate is None else estimate[1],
            "hazard_ratio_hi": None if estimate is None else estimate[2],
            "mde_hazard_ratio": mde,
            "max_mde_hr": ns.max_mde_hr,
            "verdict": verdict,
            "guidance": guidance,
        },
        "per_cause": per,
        "cannot_say": list(CANNOT_SAY),
        "_observed_b": float(sum(p.died for p in common_b)),
        "_deaths_common": deaths_common,
        "_verdict_line": verdict_line,
        "_same_salt": manifest_a.run_salt == manifest_b.run_salt,
        "_event_notes": notes,
        "_placed_common": len(common_a) + len(common_b),
        "_at_draws": _AT_DRAWS,
        # the information a hazard ratio of the size asked needs, and what the tries offered
        # are expected to give, for the guidance
        "_information": information,
        "_tries_per_input": _tries_per_input(common_a, common_b),
        # for the summary: the tries and failures over the common cells, how far apart the two
        # started, and whether every common input failed as often of as many tries in both
        "_common": {
            arm: {"tries": len(rows), "failed": sum(1 for p in rows if p.died)}
            for arm, rows in (("a", common_a), ("b", common_b))
        },
        "_gap_seconds": _gap_between(run_a, manifest_a, run_b, manifest_b),
        "_matching": _per_cell(common_a) == _per_cell(common_b),
        # for the summary: when a try counts as failed in each run
        "_rules": {
            "a": summary.failed_when(manifest_a, sorted(events)),
            "b": summary.failed_when(manifest_b, sorted(events)),
        },
    }
    following = _next(index, "fix-check", (run_a, run_b), ns, "--inputs", "all")
    plain = summary.compare(data, verdict, following)
    data["_summary"], data["_before_you_act"] = plain.lines, plain.caveats
    sentence = plain.sentence
    diff = measures = None
    if signals is not None and (ns.save or ns.out is not None):
        arms = [("a", run_a), ("b", run_b)]
        diff = _taxonomy_diff(("a", "b"), signals[1], {"a": manifest_a, "b": manifest_b})
        measures = _measures(ns, signals[1], arms, ("A", "B"))
    return _deliver(
        ns,
        data,
        verdict,
        sentence,
        following,
        kind="compare",
        report=CompareReport(data=data),
        runs=[("a", run_a, manifest_a), ("b", run_b, manifest_b)],
        settings=_settings(ns, "compare"),
        diff=diff,
        measures=measures,
    )


# compare's --at band: resamples of the inputs, and their seed
_AT_DRAWS = 2_000


def _per_cell(rows: Sequence[Any]) -> dict[str, tuple[int, int]]:
    """Each cell's tries and failures among placed tries."""
    held: dict[str, tuple[int, int]] = {}
    for p in rows:
        n, died = held.get(p.config_hash, (0, 0))
        held[p.config_hash] = (n + 1, died + int(p.died))
    return held


def _gap_between(run_a: Any, manifest_a: Any, run_b: Any, manifest_b: Any) -> float | None:
    """How far apart two runs started, in seconds; None where a start cannot be read."""
    try:
        return abs((_started(run_b, manifest_b) - _started(run_a, manifest_a)).total_seconds())
    except _Refusal:
        return None


def _tries_per_input(common_a: Sequence[Any], common_b: Sequence[Any]) -> int | None:
    """The tries per input per run over the common cells, where every one carries the same
    number; ``None`` where they differ."""
    held: dict[tuple[int, str], int] = {}
    for arm, rows in enumerate((common_a, common_b)):
        for p in rows:
            held[(arm, p.config_hash)] = held.get((arm, p.config_hash), 0) + 1
    numbers = set(held.values())
    return numbers.pop() if len(numbers) == 1 else None


def _compare_guidance(
    ns: argparse.Namespace, common_a: Sequence[Any], common_b: Sequence[Any], mde: float | None
) -> tuple[dict[str, Any], dict[str, float | None]]:
    """The tries per input per version whose expected log-rank information under no change,
    on the per-input model fitted to the two runs' common cells, reaches what the ratio asked
    for needs, and more than any input had in either run: these runs fell short, so the model
    reaching the target at their own tries does not make them enough. The ceiling offered is
    the detectable hazard ratio rounded up, so it accepts the design as it stands. Deaths, runs
    and inputs no longer size the guidance and hold no value."""
    from poisson_trace.paired import accepts_at
    from poisson_trace.survival import (
        expected_information,
        fit_cells,
        information_needed,
        tries_needed,
    )

    fit = fit_cells([(p.config_hash, p.index, p.died) for p in [*common_a, *common_b]])
    repeats = tries_needed(fit, ns.max_mde_hr, alpha=ns.alpha)
    if repeats is not None:
        had = Counter(("a", p.config_hash) for p in common_a)
        had.update(("b", p.config_hash) for p in common_b)
        repeats = max(repeats, max(had.values()) + 1)
    return {
        "deaths": None,
        "runs": None,
        "inputs": None,
        "repeats": repeats,
        "accepts_at": None if mde is None else accepts_at(mde, decimals=3),
    }, {
        "needed": information_needed(ns.max_mde_hr, alpha=ns.alpha),
        "expected": None if repeats is None else expected_information(fit, repeats),
    }


# ---------- fix-check and changes ----------


@dataclass
class _Input:
    """One input's rows in one arm: how many ran to an outcome, how many of those failed, and
    how many had no outcome, split by Prove's timeout mark."""

    config: Any
    runs: int = 0
    failed: int = 0
    timed_out: int = 0
    no_outcome: int = 0


def _no_value(x: Any) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _by_input(frame: Any, events: frozenset[str]) -> dict[str, _Input]:
    arm: dict[str, _Input] = {}
    for h, config, outcome, error in zip(
        frame["config_hash"], frame["config"], frame["outcome"], frame["error"], strict=True
    ):
        row = arm.setdefault(str(h), _Input(config=config))
        if _no_value(outcome):
            if error == "timeout":
                row.timed_out += 1
            else:
                row.no_outcome += 1
        else:
            row.runs += 1
            row.failed += outcome in events
    return arm


def _declared_repeats(manifest: Any) -> int | None:
    environment = manifest.environment
    sweep = environment.get("sweep") if isinstance(environment, Mapping) else None
    declared = sweep.get("replicates") if isinstance(sweep, Mapping) else None
    if isinstance(declared, bool) or not isinstance(declared, int):
        return None
    return declared


def _paired_header(run: Any, manifest: Any, tally: Any) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "run_name": run.name,
        "target_id": manifest.target_id,
        "status": manifest.status,
        "created_at": manifest.created_at,
        "declared_repeats": _declared_repeats(manifest),
        "tally": tally.to_dict(),
        "_imported": run.imported,
        "_start": _start_of(manifest),
    }


def _started(run: Any, manifest: Any) -> datetime:
    try:
        at = datetime.fromisoformat(manifest.created_at)
        # a start with no zone is read as UTC, as Prove writes every start and as names read it
        return at.replace(tzinfo=UTC) if at.tzinfo is None else at
    except (TypeError, ValueError) as e:
        held = manifest.created_at
        shown = f' ("{held}")' if isinstance(held, str) else ""
        raise _Refusal(
            f"the run {run.shown()} carries no readable start time{shown}, so the gap between "
            "the two runs cannot be told"
        ) from e


def _check_events(
    events: frozenset[str], frame_a: Any, frame_b: Any, first: str, second: str
) -> list[str]:
    """The first slice's rule: a name neither run carries is refused; a name one run carries
    is allowed, and noted."""
    out_a, out_b = _outcomes(frame_a), _outcomes(frame_b)
    present = {o for o in out_a | out_b if not _no_value(o)}
    missing = sorted(events - present)
    if missing:
        raise _Refusal(
            f"unknown event {', '.join(missing)}; the runs carry the outcomes: "
            f"{', '.join(sorted(present)) or 'none'}"
        )
    return [
        f"event {e}: carried by the {first if e in out_a else second} run only"
        for e in sorted(events)
        if (e in out_a) != (e in out_b)
    ]


def _arm_rows(arm: Mapping[str, _Input], compared: Sequence[str], declared: int | None) -> Any:
    rows = [arm[h] for h in compared]
    return {
        "runs": sum(r.runs for r in rows),
        "failed": sum(r.failed for r in rows),
        "timed_out": sum(r.timed_out for r in rows),
        "no_outcome": sum(r.no_outcome for r in rows),
        "short": 0 if declared is None else sum(1 for r in rows if r.runs < declared),
        "mixed": sum(1 for r in rows if 0 < r.failed < r.runs),
    }


def _changes_block(
    counts: Sequence[Any], configs: Mapping[str, Any], alpha: float
) -> dict[str, Any]:
    """The per-input flags and what the design could not have flagged."""
    from poisson_trace.paired import CANNOT_SAY, Counts, _fisher, flags

    by_hash = {c.config_hash: c for c in counts}
    rows = []
    for f in sorted(flags(counts, alpha=alpha), key=lambda f: (f.p, f.config_hash)):
        c = by_hash[f.config_hash]
        rows.append(
            {
                "config_hash": f.config_hash,
                "config": configs[f.config_hash],
                "failed_a": c.failed_old,
                "runs_a": c.runs_old,
                "failed_b": c.failed_new,
                "runs_b": c.runs_new,
                "change": f.change,
                "p": f.p,
                "q": f.q,
                "flag": f.flag,
            }
        )

    def extreme(runs_old: int, runs_new: int) -> float:
        # none of the old arm's runs failed and every one of the new arm's did
        return _fisher(Counts("", 0, runs_old, runs_new, runs_new))

    tested = len(counts)
    smallest = min(extreme(a, b) for a, b in {(c.runs_old, c.runs_new) for c in counts})
    together = next((j for j in range(1, tested + 1) if smallest * tested / j < alpha), None)
    repeats = 1
    while extreme(repeats, repeats) > alpha / tested:
        repeats += 1
    return {
        "tested": tested,
        "flagged": sum(1 for r in rows if r["flag"] is not None),
        "alpha": alpha,
        "lone_threshold": alpha / tested,
        "smallest_attainable_p": smallest,
        "together": together,
        "lone_flip_repeats": repeats,
        "rows": rows,
        "cannot_say": list(CANNOT_SAY),
    }


def _number(x: float) -> float | None:
    return x if math.isfinite(x) else None


def _fix_check(ns: argparse.Namespace) -> int:
    import poisson_prove

    from poisson_trace import paired, summary
    from poisson_trace.report import FixCheckReport, _p_is, _points

    if ns.out is not None:
        _check_out(ns.out, ns.force)
    ns.measures = ns.measures or bool(ns.max_change)
    store, index = _named(ns)
    run_old, run_new = _two(index, ns.old, ns.new, ("OLD", "NEW"))
    selecting = None if ns.failing_from is None else index.resolve(ns.failing_from)
    for arm, run in (("old", run_old), ("new", run_new)):
        if selecting is not None and selecting.run_id == run.run_id:
            raise _Refusal(
                f"the selecting run {selecting.shown()} is also the {arm} arm; both arms must "
                "be fresh re-runs, because the selecting run's failures on these inputs are "
                "there by selection"
            )
    manifest_old, frame_old, tally_old = _load(store, run_old, trace="none")
    manifest_new, frame_new, tally_new = _load(store, run_new, trace="none")
    events = frozenset(ns.event)
    signals = None
    if ns.verdicts is not None or ns.save or ns.out is not None or ns.measures:
        signals = _signals(ns, [("old", run_old), ("new", run_new)], events)
        frame_old = _filled(frame_old, signals[0]["old"], signals[1]["old"], events)
        frame_new = _filled(frame_new, signals[0]["new"], signals[1]["new"], events)
    notes = _check_events(events, frame_old, frame_new, "old", "new")
    arm_old, arm_new = _by_input(frame_old, events), _by_input(frame_new, events)
    if selecting is not None:
        min_failures = 1 if ns.min_failures is None else ns.min_failures
        _, frame_sel, _ = _load(store, selecting, trace="none")
        selected = sorted(
            h for h, row in _by_input(frame_sel, events).items() if row.failed >= min_failures
        )
        rule = {"rule": "failing-from", "failing_from": selecting.run_id}
        rule["min_failures"] = min_failures
    else:
        selected = sorted(set(arm_old) | set(arm_new))
        rule = {"rule": "all", "failing_from": None, "min_failures": None}
    left_out = dict.fromkeys(paired.LEFT_OUT, 0)
    compared = []
    for h in selected:
        if h not in arm_old:
            left_out[paired.LEFT_OUT[0]] += 1
        elif h not in arm_new:
            left_out[paired.LEFT_OUT[1]] += 1
        elif arm_old[h].runs == 0:
            left_out[paired.LEFT_OUT[2]] += 1
        elif arm_new[h].runs == 0:
            left_out[paired.LEFT_OUT[3]] += 1
        else:
            compared.append(h)
    if not compared:
        reasons = "; ".join(f"{reason} {count(n)}" for reason, n in left_out.items() if n)
        raise _Refusal(
            f"no input is left to compare: {count(len(selected))} selected"
            + (f", left out: {reasons}" if reasons else "")
        )
    counts = [
        paired.Counts(h, arm_old[h].failed, arm_old[h].runs, arm_new[h].failed, arm_new[h].runs)
        for h in compared
    ]
    header_old = _paired_header(run_old, manifest_old, tally_old)
    header_new = _paired_header(run_new, manifest_new, tally_new)
    started_old, started_new = _started(run_old, manifest_old), _started(run_new, manifest_new)
    gap = abs((started_new - started_old).total_seconds())
    rows_old = _arm_rows(arm_old, compared, header_old["declared_repeats"])
    rows_new = _arm_rows(arm_new, compared, header_new["declared_repeats"])

    test = paired.paired_test(counts)
    points, variance, lo, hi = paired.difference(counts, alpha=ns.alpha)
    by_p, moved, method = paired.by_input(counts, seed=ns.seed, draws=_DRAWS)
    drawn = method != "exact"
    share, again, kappa, within, pooled = paired.consistency(counts)
    # with one run per input per version, no input was run twice on one version, and the
    # only pairs of runs there are compare the versions, not a version with itself
    one_run = all(c.runs_old == 1 and c.runs_new == 1 for c in counts)
    # an input repeats when one version holds two or more of its runs with an outcome; where
    # fewer than half the compared inputs repeat, most pairs of runs of one input still set
    # the two versions side by side rather than a version beside itself
    repeating = sum(1 for c in counts if c.runs_old >= 2 or c.runs_new >= 2)
    few_repeat = 0 < 2 * repeating < len(counts)
    if one_run or few_repeat:
        again = kappa = math.nan
    drop = paired.detection_limit(counts, direction="drop", alpha=ns.alpha)
    rise = paired.detection_limit(counts, direction="rise", alpha=ns.alpha)

    if points < 0:
        direction, word = "failed less in new", "less"
    elif points > 0:
        direction, word = "failed more in new", "more"
    else:
        direction, word = "no direction", ""
    p_is = _p_is(test.p)
    # every failure gone, and every run failing, as shifts in failure share: the largest a
    # proportional change can be on these inputs
    weights = [c.runs_old * c.runs_new / (c.runs_old + c.runs_new) for c in counts]
    rates = [(c.failed_old + c.failed_new) / (c.runs_old + c.runs_new) for c in counts]
    largest_drop = sum(w * r for w, r in zip(weights, rates, strict=True)) / sum(weights)
    asked = f"{100.0 * ns.max_mde:g}"
    limit_text = None if drop is None else _points(drop)
    excludes_zero = lo is not None and hi is not None and (lo > 0.0 or hi < 0.0)
    disagree = variance is not None and ((test.p < ns.alpha) != excludes_zero)
    # the range reads the verdict only where it is reliable (section 9.5's gate); where it is
    # not, the drop limit against the size asked reads it, as before
    rough = paired.rough(counts, informative=test.informative, disagree=disagree)
    reliable = lo is not None and hi is not None and not rough
    inside = (
        reliable and lo is not None and hi is not None and -ns.max_mde <= lo and hi <= ns.max_mde
    )
    enough = drop is not None and drop <= ns.max_mde
    guidance = None
    if test.p < ns.alpha and points != 0:
        verdict, decided = "different", "test"
        sentence = (
            f"the new version failed {word} on these inputs (exact "
            f"Cochran-Mantel-Haenszel, stratified by input, {p_is})"
        )
        verdict_line = f"different: {sentence}"
    elif reliable:
        decided = "range"
        span = _range_text(lo, hi, ns.alpha)
        if inside:
            verdict = "no significant difference"
            sentence = f"{p_is}; {span}, lies inside ±{asked}"
            verdict_line = f"no significant difference ({p_is}); {span}, lies inside ±{asked}"
        else:
            verdict = "too small to tell"
            sentence = f"{span}, does not lie inside ±{asked}, which was asked for"
            verdict_line = f"too small to tell: {sentence}"
    elif enough:
        verdict, decided = "no significant difference", "limit"
        limit = f"could not have detected a drop in failure share below {limit_text} points"
        sentence = f"{p_is}; {limit}"
        verdict_line = f"no significant difference ({p_is}); {limit}"
    else:
        verdict, decided = "too small to tell", "limit"
        if drop is None:
            sentence = (
                "could not have detected a drop in failure share below or "
                f"at {_points(largest_drop)} points, which is every failure gone, and {asked} "
                "was asked for"
            )
        else:
            sentence = (
                "could not have detected a drop in failure share below "
                f"{limit_text} points, and {asked} was asked for"
            )
        verdict_line = f"too small to tell: {sentence}"
    if verdict == "too small to tell":
        guidance = _fix_check_guidance(ns, counts, drop, lo, hi, reliable=reliable, enough=enough)
    configs = {h: arm_old[h].config for h in compared}
    block = _changes_block(counts, configs, ns.alpha)
    data: dict[str, Any] = {
        "schema": "poisson-trace.fix-check/2",
        "prove": {"version": poisson_prove.__version__, "store": _store_shown(ns)},
        "runs": {"old": header_old, "new": header_new},
        "gap_seconds": gap,
        "events": sorted(events),
        "inputs": {
            **rule,
            "selected": len(selected),
            "compared": len(compared),
            "informative": test.informative,
            "left_out": left_out,
        },
        "rows": {"old": rows_old, "new": rows_new},
        "control": {
            "old_did_not_fail_share": 1.0 - rows_old["failed"] / rows_old["runs"],
            "new_did_not_fail_share": 1.0 - rows_new["failed"] / rows_new["runs"],
        },
        "test": {
            "name": "exact conditional Cochran-Mantel-Haenszel",
            "observed_new": test.observed_new,
            "expected_new": test.expected_new,
            "variance": test.variance,
            "weight": test.weight,
            "p": test.p,
            "alpha": ns.alpha,
        },
        "difference": {
            "points": points,
            "lo": lo,
            "hi": hi,
            "variance": variance,
            "interval": paired.INTERVAL,
        },
        "by_input": {
            "moved": moved,
            "p": by_p,
            "method": method,
            "draws": _DRAWS if drawn else None,
            "seed": ns.seed if drawn else None,
        },
        "consistency": {
            "failure_share": share,
            "fails_again": _number(again),
            "kappa": _number(kappa),
            "within": within,
            "pooled": pooled,
        },
        "limits": {"drop": drop, "rise": rise, "power": 0.8, "max_mde": ns.max_mde},
        "direction": direction,
        "guidance": guidance,
        "changes": block,
        "cannot_say": list(paired.CANNOT_SAY),
        "_verdict_line": verdict_line,
        "_failing_from": None if selecting is None else selecting.name,
        "_event_notes": notes,
        "_top": ns.top,
        "_one_run": one_run,
        "_few_repeat": (repeating, len(counts)) if few_repeat else None,
        "_largest": {"drop": largest_drop, "rise": 1.0 - largest_drop},
        "_disagree": disagree,
        # what the verdict rests on, for the summary: "test", "range" or "limit"
        "_decided_by": decided,
        # the range's level in percent, and why it is rough here (empty where it is reliable)
        "_level": 100.0 * (1.0 - ns.alpha),
        "_rough": list(rough),
        "_reliable": reliable,
        # the drop limit is at or under the size asked
        "_tries_enough": enough,
        # the size asked, where a reliable range leaves out a drop (or a rise) of that size or more
        "_drop_ruled_out": ns.max_mde if reliable and lo is not None and lo > -ns.max_mde else None,
        "_rise_ruled_out": ns.max_mde if reliable and hi is not None and hi < ns.max_mde else None,
        "_unconfirmed": (
            _unconfirmed(counts, block) if verdict == "different" and by_p >= ns.alpha else None
        ),
        "_copies": [
            arm
            for arm, held in (("old", arm_old), ("new", arm_new))
            if all(held[h].runs >= 2 and not 0 < held[h].failed < held[h].runs for h in compared)
        ],
        # for the summary: when a try counts as failed in each run, whether the run given as new
        # started first, and each version's tries with no outcome on the inputs selected
        "_rules": {
            "old": summary.failed_when(manifest_old, sorted(events)),
            "new": summary.failed_when(manifest_new, sorted(events)),
        },
        "_new_first": started_new < started_old,
        "_no_outcome": {
            name: sum(arm[h].no_outcome + arm[h].timed_out for h in selected if h in arm)
            for name, arm in (("old", arm_old), ("new", arm_new))
        },
    }
    plain = summary.fix_check(data, verdict, _next(index, "changes", (run_old, run_new), ns))
    data["_summary"], data["_before_you_act"] = plain.lines, plain.caveats
    sentence = plain.sentence
    following = plain.follows or _fix_check_next(
        index, ns, run_old, run_new, guidance, len(compared)
    )
    diff = measures = None
    if signals is not None:
        arms = [("old", run_old), ("new", run_new)]
        measures = _measures(ns, signals[1], arms, ("old", "new"))
        if ns.measures:
            data["_measures_section"] = _measures_section(measures)
        if ns.save or ns.out is not None:
            diff = _taxonomy_diff(
                ("old", "new"), signals[1], {"old": manifest_old, "new": manifest_new}
            )
    return _deliver(
        ns,
        data,
        verdict,
        sentence,
        following,
        kind="fix-check",
        report=FixCheckReport(data=data),
        runs=[("old", run_old, manifest_old), ("new", run_new, manifest_new)],
        settings=_settings(ns, "fix-check", selecting),
        diff=diff,
        measures=measures,
    )


def _range_text(lo: float | None, hi: float | None, alpha: float) -> str:
    """``the 95% range, -6.0 to +8.1 points``, at the level the range was computed at."""
    from poisson_trace.report import _points

    assert lo is not None and hi is not None
    places = 2 if all(abs(100.0 * x) < 1.0 for x in (lo, hi)) else 1
    low, high = (_points(x, signed=True, places=places) for x in (lo, hi))
    return f"the {100.0 * (1.0 - alpha):g}% range, {low} to {high} points"


def _fix_check_guidance(
    ns: argparse.Namespace,
    counts: Sequence[Any],
    drop: float | None,
    lo: float | None,
    hi: float | None,
    *,
    reliable: bool,
    enough: bool,
) -> dict[str, Any]:
    """What too small to tell offers: the repeats and the inputs that bring the drop limit to
    the size asked, and the ceiling that accepts the design as it stands. Where a reliable range
    decided and the drop limit is already under the size asked, more tries of the same design
    are not what is short, and nothing is offered. Where a reliable range decides, the ceiling
    offered is the smallest the range lies inside, so that given, it reads otherwise."""
    from poisson_trace import paired

    if reliable and enough:
        return {"repeats": None, "inputs": None, "accepts_at": None}
    ceiling = drop
    if reliable and lo is not None and hi is not None:
        # the range alone decides: the smallest size asked that it lies inside, whatever the
        # drop limit says
        ceiling = max(-lo, hi)
    return {
        "repeats": paired.repeats_needed(counts, ns.max_mde, alpha=ns.alpha),
        "inputs": paired.inputs_needed(counts, ns.max_mde, alpha=ns.alpha),
        "accepts_at": None if ceiling is None else paired.accepts_at(ceiling, decimals=4),
    }


def _unconfirmed(counts: Sequence[Any], block: Mapping[str, Any]) -> dict[str, Any]:
    """For a difference the by-input check does not bear out: the inputs the per-input check
    flagged, their share of the net extra failures, and the gap and the exact test without
    them. An input's extra failures are its new failures less the old version's rate at the
    new version's tries; the net is their sum over every compared input."""
    from poisson_trace import paired

    flagged = {r["config_hash"]: r for r in block["rows"] if r["flag"] is not None}

    def extra(c: Any) -> float:
        return float(c.failed_new - c.failed_old * c.runs_new / c.runs_old)

    rest = [c for c in counts if c.config_hash not in flagged]
    points_without = p_without = None
    if flagged and rest:
        points_without = paired.difference(rest)[0]
        p_without = paired.paired_test(rest).p
    return {
        "inputs": [
            {
                "config_hash": c.config_hash,
                "config": flagged[c.config_hash]["config"],
                "extra": extra(c),
            }
            for c in counts
            if c.config_hash in flagged
        ],
        "extra": sum(extra(c) for c in counts if c.config_hash in flagged),
        "net_extra": sum(extra(c) for c in counts),
        "compared_without": len(rest),
        "points_without": points_without,
        "p_without": p_without,
    }


def _fix_check_next(
    index: Any,
    ns: argparse.Namespace,
    old: Any,
    new: Any,
    guidance: Mapping[str, Any] | None,
    inputs: int,
) -> str:
    """Too small to tell: the repeats or the inputs the guidance gives, then the fix check
    again. Otherwise the inputs that moved, on the same two runs."""
    if guidance is None:
        return _next(index, "changes", (old, new), ns)
    again = "then poisson-trace fix-check on the two new runs"
    if guidance["repeats"] is not None:
        return (
            f"run {count(guidance['repeats'])} repeats per arm on these {count(inputs)} "
            f"{'input' if inputs == 1 else 'inputs'}, {again}"
        )
    if guidance["inputs"] is not None:
        return f"run {count(guidance['inputs'])} inputs like these at the present repeats, {again}"
    return look.command("poisson-trace", "fix-check", "--help")


def _changes(ns: argparse.Namespace) -> int:
    import poisson_prove

    from poisson_trace import paired, summary
    from poisson_trace.report import ChangesReport

    if ns.out is not None:
        _check_out(ns.out, ns.force)
    store, index = _named(ns)
    run_a, run_b = _two(index, ns.a, ns.b, ("A", "B"))
    manifest_a, frame_a, tally_a = _load(store, run_a, trace="none")
    manifest_b, frame_b, tally_b = _load(store, run_b, trace="none")
    events = frozenset(ns.event)
    signals = None
    if ns.verdicts is not None or ns.save or ns.out is not None:
        signals = _signals(ns, [("a", run_a), ("b", run_b)], events)
        frame_a = _filled(frame_a, signals[0]["a"], signals[1]["a"], events)
        frame_b = _filled(frame_b, signals[0]["b"], signals[1]["b"], events)
    notes = _check_events(events, frame_a, frame_b, "A", "B")
    arm_a, arm_b = _by_input(frame_a, events), _by_input(frame_b, events)
    compared = sorted(h for h in set(arm_a) & set(arm_b) if arm_a[h].runs and arm_b[h].runs)
    if not compared:
        raise _Refusal(
            "no input has a run with an outcome in both runs, so there is nothing to compare"
        )
    counts = [
        paired.Counts(h, arm_a[h].failed, arm_a[h].runs, arm_b[h].failed, arm_b[h].runs)
        for h in compared
    ]
    gap = abs((_started(run_b, manifest_b) - _started(run_a, manifest_a)).total_seconds())
    data: dict[str, Any] = {
        "schema": "poisson-trace.changes/2",
        "prove": {"version": poisson_prove.__version__, "store": _store_shown(ns)},
        "runs": {
            "a": _paired_header(run_a, manifest_a, tally_a),
            "b": _paired_header(run_b, manifest_b, tally_b),
        },
        "events": sorted(events),
        **_changes_block(counts, {h: arm_a[h].config for h in compared}, ns.alpha),
        "_event_notes": notes,
        "_top": ns.top,
        "_gap_seconds": gap,
        "_inputs": {
            "a": len(arm_a),
            "b": len(arm_b),
            "a_only": len(set(arm_a) - set(arm_b)),
            "b_only": len(set(arm_b) - set(arm_a)),
        },
    }
    # for the summary: each run's tries with no outcome, and the inputs both carry that one of
    # them gives no outcome on
    data["_no_outcome"] = {
        "a": sum(r.no_outcome + r.timed_out for r in arm_a.values()),
        "b": sum(r.no_outcome + r.timed_out for r in arm_b.values()),
        "left_out": sum(
            1 for h in set(arm_a) & set(arm_b) if not (arm_a[h].runs and arm_b[h].runs)
        ),
    }
    following = _next(index, "fix-check", (run_a, run_b), ns, "--inputs", "all")
    plain = summary.changes(data, following)
    data["_summary"], data["_before_you_act"] = plain.lines, plain.caveats
    sentence = plain.sentence
    diff = measures = None
    if signals is not None and (ns.save or ns.out is not None):
        arms = [("a", run_a), ("b", run_b)]
        diff = _taxonomy_diff(("a", "b"), signals[1], {"a": manifest_a, "b": manifest_b})
        measures = _measures(ns, signals[1], arms, ("A", "B"))
    return _deliver(
        ns,
        data,
        "ok",
        sentence,
        following,
        kind="changes",
        report=ChangesReport(data=data),
        runs=[("a", run_a, manifest_a), ("b", run_b, manifest_b)],
        settings=_settings(ns, "changes"),
        diff=diff,
        measures=measures,
    )


if __name__ == "__main__":
    raise SystemExit(main())
