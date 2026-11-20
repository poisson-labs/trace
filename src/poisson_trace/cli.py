"""The console script: ``poisson-trace init``, ``runs``, ``name``, ``where``, ``compare``,
``fix-check``, ``changes``, ``handover``, ``import``, ``doctor``, ``ui`` and ``report``.

A thin caller of the Python API: it reads the command line, calls the verb's one function in
``poisson_trace.api`` (``init``, ``doctor`` and ``report`` in
``poisson_trace.commands``) once with what was typed, and prints what the result gives. Of the
package it imports ``api``, ``commands`` and the shared look alone; it computes nothing, and
reads, writes and lists no file itself.

``import`` is the import's own command (``poisson_trace.ingest.cli``), handed every word of the
command line but ``import`` itself, so that it prints what ``poisson-trace-import`` prints.

The command line is read first, so ``--help`` and ``--version`` need nothing installed; the
check that ``poisson_prove`` is present at the version this package reads is the API's, and
``poisson_prove`` is imported nowhere here. Every line printed, every refusal and every exit
code is the look's (``look.py``, ``docs/cli-look.md``).
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
from collections.abc import Callable, Collection, Mapping, Sequence
from typing import Any

from poisson_trace import api, commands, look

_NAMED = (
    "init, runs, name, where, compare, fix-check, changes, import, doctor, handover, ui and report"
)
# the column the top help's words start at; the bare command's two options are too long for it
# and print their helps on the line under them
_HELP_COLUMN = 15
# the bare command's options: with no verb, on a terminal, they open the app
_BARE = ("--store", "--config")
# the verbs that count failures, and whose results are delivered with --save, --out and --svg
_COUNTING = ("where", "compare", "fix-check", "changes")
# the command's own option, which stays where it is written; --help before a verb is that
# verb's help, as every other option before a verb is that verb's
_KEPT = ("--version",)
# what shapes the printing, and what delivers a result: never a keyword of the verb's function
_PRINTING = frozenset({"-h", "--help", "--json", "--plain", "--debug", "--version"})
_DELIVERY = frozenset({"--svg", "--save", "--out", "--force"})
# each verb of the store and the function that is it
_FUNCTION = {
    "where": "where",
    "compare": "compare",
    "fix-check": "fix_check",
    "changes": "changes",
    "runs": "runs",
}


class _Refusal(look.Refused):
    """One sentence, exit 1, and the commands to run next under it, if any."""


_ABOUT = """\
Poisson Trace reads the runs Prove has stored and the results ten other tools wrote, and says
where in the workflow their episodes died, and whether a change made them fail less. A store is
the folder Prove writes its runs into; a run is one stored sweep, and its episodes are its rows.
Every number prints with what the runs could not have detected.

A run is named by a name you gave it with poisson-trace name; by the name it has from its
manifest, the record Prove keeps of it (its target, the day it started in UTC and a letter, such
as "tau2-airline 2026-09-15 a"); by latest or previous, the newest complete runs, or
latest:TARGET and previous:TARGET, a target's ("latest:tau2-airline"); by its number in the
runs listing ("#3"); or by its full id.

Results another tool wrote (DeepEval, Ragas, a table of results, JUnit reports, promptfoo,
Inspect, OpenAI Evals, LangSmith, Braintrust, Weave) are read in with poisson-trace import.
where, compare, fix-check and changes also take a folder in a run's place, when no stored run
answers to the word: a run Prove stored, a store of one run, or one tool's result files, read
with the flags poisson-trace import takes for that tool. Nothing is written; the folder's name
is the run's name in the report.

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
    'by its name, latest, previous or its number in the runs listing ("#3"), or a folder of results'
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
        # the two options of the bare command do not widen the help's column, so their helps
        # start on the line under them and nothing else on the page moves
        formatter_class=lambda prog: look._HelpFormatter(prog, max_help_position=_HELP_COLUMN),
        description=_ABOUT,
        epilog=_example(
            "poisson-trace runs --store prove-runs --event unsolved",
            "poisson-trace where previous --store prove-runs --event unsolved --at 20",
            "poisson-trace fix-check previous latest --store prove-runs --event unsolved \\",
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
    parser.add_argument(
        "--store",
        metavar="PATH",
        help="with no verb, open the terminal app on this store, a folder or a name trace.toml "
        "gives (default: the store trace.toml names)",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="with no verb, open the terminal app on this config file (default: trace.toml in "
        "the current folder, if any)",
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
        epilog=_example("poisson-trace runs --store prove-runs --event unsolved"),
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
            'poisson-trace name previous "tau2 old re-run" --store prove-runs',
            "poisson-trace name --list --store prove-runs",
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
            "poisson-trace where previous --store prove-runs --event unsolved --at 20",
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
            'poisson-trace compare "#3" previous --store prove-runs --event unsolved \\',
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
            "poisson-trace fix-check previous latest --store prove-runs --event unsolved \\",
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
            "poisson-trace changes previous latest --store prove-runs --event unsolved",
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
            "command to run. It fixes nothing and asks nothing; it exits 4 when not ready.\n"
            "With --setup it is the check a coding agent runs on the trace.toml it wrote:\n"
            "the same, read as a setup needs it, and each [[import]] file not imported yet\n"
            "read with its reader; ready exits 0, not ready 1 with error: and next: lines on\n"
            "stderr, a wrong setting 2."
        ),
        epilog=_example(
            "poisson-trace doctor",
            "poisson-trace doctor --config team.toml",
            "poisson-trace doctor --setup",
        ),
    )
    doctor.add_argument("--config", metavar="PATH", help=_CONFIG_HELP)
    doctor.add_argument(
        "--setup",
        action="store_true",
        help="check a trace.toml written for review, its [[import]] files included, with the "
        "setup check's exit codes (0 ready, 1 not ready, 2 a wrong setting)",
    )
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
    ui = verbs.add_parser(
        "ui",
        help="build the pages over a store's runs and saved verdicts, opened from disk",
        description=(
            "Builds Trace's pages in the store's .poisson/ui/trace/: the runs and the saved\n"
            "verdicts, each verdict's page and what it cannot say, opened from disk with\n"
            "nothing loaded from the network. With a config, every store it names gets its\n"
            "pages, and they link one another. Prove's own dashboard beside them is never\n"
            "touched. Every command that saves a verdict rebuilds the pages too."
        ),
        epilog=_example("poisson-trace ui", "poisson-trace ui --open"),
    )
    ui.add_argument(
        "--open", action="store_true", help="open the pages in the browser (default: not opened)"
    )
    ui.add_argument("--store", metavar="ROOT", help=_STORE_HELP)
    ui.add_argument("--config", metavar="PATH", help=_CONFIG_HELP)
    tail(ui)
    rep = verbs.add_parser(
        "report",
        help="write a handover bundle's verdict as one HTML page into it",
        description=(
            "Writes report.html into a bundle that where, compare, fix-check or changes wrote\n"
            "with --out DIR: the verdict's page as the static UI shows it, self-contained, with\n"
            "no script and nothing loaded from the network, and lists it in handover.json. A\n"
            "bundle that does not hold what it promises is refused first, as handover --check\n"
            "refuses it."
        ),
        epilog=_example(
            "poisson-trace report verdicts/fix-check-2026-11-04",
            "poisson-trace report verdicts/fix-check-2026-11-04 --open",
        ),
    )
    rep.add_argument("dir", metavar="DIR", help="the bundle --out wrote (no default)")
    rep.add_argument(
        "--open",
        action="store_true",
        help=(
            "open the page in the browser; a report.html that is there is opened as it is, "
            "not written again (default: not opened)"
        ),
    )
    rep.add_argument(
        "--force",
        action="store_true",
        help="replace a report.html that is there (default: refused, or opened with --open)",
    )
    rep.add_argument(
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
        "ui": ui,
        "report": rep,
    }


def _form(text: str) -> str:
    """``--names from=FORM``: the form, or a wrong command line."""
    try:
        return api._form_word(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from None


def _fail_on(text: str) -> tuple[str, ...]:
    """``--fail-on``: the check's results that fail its job, comma-separated."""
    try:
        return api._fail_on_word(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from None


def _max_change(text: str) -> tuple[str, float]:
    """``--max-change MEASURE=N%``: the measure and its ceiling as a share, or a wrong command
    line."""
    try:
        return api._max_change_word(text)
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
            "asks nothing. It never searches the home folder or a folder above it.\n"
            "On a trace.toml with [[import]] files not imported yet, as your coding agent\n"
            "writes one, it shows them and asks whether to import them. With --agent, it\n"
            "writes instead the setup your own coding agent follows (a skill and the prompt\n"
            "to give it), in the two folders coding agents read skills from, and nothing else."
        ),
        epilog=_example(
            "poisson-trace init",
            "poisson-trace init --yes --store prove-runs --event unsolved",
            "poisson-trace init --add-store imported",
            "poisson-trace init --agent",
        ),
    )
    init.add_argument(
        "--agent",
        action="store_true",
        help="write the setup your own coding agent follows, a skill and its prompt, instead of "
        "setting up here; it makes no model call and reads no key",
    )
    init.add_argument(
        "--repo",
        metavar="DIR",
        help="with --agent: the repository to write the setup into (default: this folder)",
    )
    init.add_argument(
        "--print",
        action="store_true",
        help="with --agent: print the skill and write nothing (default: write the files)",
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
        metavar="name|input|position|var:NAME|test",
        help="for a DeepEval import: what identifies a test case across versions (name, input "
        "or position); for JUnit reports, name reads them by the test's name alone; for a "
        "promptfoo import, var:NAME, the test variable NAME, or test, the test's position (no "
        "default)",
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


@functools.cache
def parsers() -> tuple[look.Parser, dict[str, look.Parser]]:
    """The command's parser and each verb's, built once: what reads the parsers (the tests
    of the API's parity with them) reads the same objects, and building them reads the
    environment for the help's width, which a function of the API never does."""
    return _build_parser()


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    return look.run("poisson-trace", args, _main, (_Refusal,))


def _bare_options(argv: Sequence[str]) -> tuple[str | None, str | None] | None:
    """``(config, store)`` when the command line is the bare command's alone: nothing, or
    ``--config PATH`` and ``--store PATH`` in either form; None for any other command line."""
    held: dict[str, str | None] = {"--config": None, "--store": None}
    i = 0
    while i < len(argv):
        word = argv[i]
        name, joined, value = word.partition("=")
        if name not in _BARE:
            return None
        if joined:
            held[name] = value
        elif i + 1 < len(argv):
            held[name] = argv[i + 1]
            i += 1
        else:
            return None
        i += 1
    return held["--config"], held["--store"]


def _open_app(config: str | None, store: str | None) -> int:
    """The terminal app, until it is left: what it leaves to say once it
    has left the terminal (Ctrl-C's ``stopped`` line) is printed as a verb prints it."""
    built = commands.app(config=config, store=store)
    code = commands.run_app(built)
    if built.after:
        look.out(f"{built.after}\n")
    return code


def _main(session: look.Session) -> int:
    bare = _bare_options(session.argv)
    if bare is not None and not session.plain and look.opens_app():
        return _open_app(*bare)
    parser, verbs = _build_parser()
    parsers_ = [parser, *verbs.values()]
    at = _import_at(session.argv, parsers_, verbs)
    if at is not None:
        from poisson_trace.ingest import cli as importer

        return importer.main([*session.argv[:at], *session.argv[at + 1 :]])
    valued = look.takes_value(parsers_)
    if look.asks(session.argv, valued, "--version"):
        look.out(look.version_line())
        return look.DONE
    args, at = look.verb_first(session.argv, valued, _KEPT, look.options(parsers_), "poisson-trace")
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
    # over; whether it is a folder is known once the store is
    folders = [w for _, w in _run_words(ns) if api._is_folder(w)]
    if extra and not folders:
        verbs[ns.verb].error(f"unrecognized arguments: {' '.join(extra)}")
    if ns.verb == "name":
        _name_line(ns)
    session.debug = ns.debug
    if getattr(ns, "json", False):
        schema = f"poisson-trace.{ns.verb}/1"
        session.render = lambda line: _stopped_json(schema, line)
    # the options the command line gave: the function is called with those alone
    typed = {w.split("=", 1)[0] for w in args if w.startswith("--")}
    try:
        if ns.verb == "doctor":
            return _doctor(ns, verbs["doctor"], typed)
        if ns.verb == "init":
            return _init(ns, verbs["init"], typed)
        if ns.verb == "handover":
            return _handover(ns)
        if ns.verb == "ui":
            return _ui(ns, verbs["ui"], typed)
        if ns.verb == "report":
            return _report(ns)
        if ns.verb == "name":
            return _name(ns, verbs["name"], typed)
        if ns.verb == "runs":
            return _runs(ns, verbs["runs"], typed)
        return _counting(ns, verbs[ns.verb], typed, extra)
    except api.Refusal as e:
        raise _raised(e, session.argv, valued) from None


def _raised(e: api.Refusal, argv: Sequence[str], valued: Collection[str]) -> BaseException:
    """The API's refusal as the command prints it: its notes first, then one ``error:`` line
    with the commands under it, at its exit code. latest or previous refused because the runs
    cannot be ordered gets its first next command from the command line's own words."""
    for note in e.notes:
        look.err(f"note: {note}\n")
    message, nexts = e.message, e.next
    if isinstance(e, api.Unordered):
        message, nexts = api._unordered_line(e, argv, valued)
    if e.exit_code == look.USAGE:
        return look.Usage(message, *nexts)
    if e.exit_code == look.FAILED:
        return look.Failed(message)
    return _Refusal(message, *nexts)


def _keyword(action: argparse.Action) -> str:
    """The keyword a parser's option is: its longest flag, dashes dropped and the inner ones
    as underscores; init's ``--import`` and ``--no-import`` are both ``import_``."""
    flag = max(action.option_strings, key=len)
    name = flag.lstrip("-").replace("-", "_")
    return str(action.dest) if action.dest == "import_" else name


def _given(
    ns: argparse.Namespace, parser: argparse.ArgumentParser, typed: Collection[str], *skip: str
) -> dict[str, Any]:
    """The options typed, as the verb's function takes them: each keyword with the value the
    parser gave; nothing that shapes the printing or delivers a result."""
    out: dict[str, Any] = {}
    for action in parser._actions:
        if not action.option_strings or isinstance(action, argparse._HelpAction):
            continue
        flags = set(action.option_strings)
        delivery = _DELIVERY if ns.verb in _COUNTING else frozenset()
        if flags & (_PRINTING | delivery | set(skip)) or not flags & set(typed):
            continue
        out[_keyword(action)] = getattr(ns, action.dest)
    return out


def _with_config(kwargs: dict[str, Any]) -> dict[str, Any]:
    """The config: the file ``--config`` names, as typed, else the current folder's
    ``trace.toml`` when there is one, which the command line finds and passes in."""
    if "config" in kwargs:
        return kwargs
    found = api._config_here()
    return kwargs if found is None else {**kwargs, "config": found}


def _printed(result: Any, as_json: bool) -> int:
    """What the result gives, printed: its notes on stderr, then its JSON or its text."""
    for note in result.notes:
        look.err(f"note: {note}\n")
    look.out(result.to_json() if as_json else result.to_markdown())
    return int(result.exit_code)


# ---------- the verbs of a store ----------


def _runs(ns: argparse.Namespace, parser: look.Parser, typed: Collection[str]) -> int:
    kwargs = _with_config(_given(ns, parser, typed, "--store"))
    return _printed(api.runs(ns.store, **kwargs), ns.json)


def _name(ns: argparse.Namespace, parser: look.Parser, typed: Collection[str]) -> int:
    kwargs = _with_config(_given(ns, parser, typed, "--store", "--list", "--forget"))
    if ns.list:
        result = api.list_names(ns.store, **kwargs)
    elif ns.forget:
        result = api.forget_name(ns.store, ns.run, **kwargs)
    else:
        result = api.name(ns.store, ns.run, ns.new, **kwargs)
    return _printed(result, False)


def _counting(
    ns: argparse.Namespace, parser: look.Parser, typed: Collection[str], extra: Sequence[str]
) -> int:
    """where, compare, fix-check and changes: the verb's function once, with the run words,
    the options typed and the reader's flags for runs given as folders; then its deliveries,
    the result's own methods; then what it gives, printed."""
    _own_checks(ns)
    # where the deliveries write is looked at before any run is read; each asks again when it
    # writes, as the API's own callers need
    api._check_deliveries(svg=getattr(ns, "svg", None), out=ns.out, force=ns.force)
    kwargs = _with_config(_given(ns, parser, typed, "--store"))
    positionals = {a.dest: getattr(ns, a.dest) for a in parser._actions if not a.option_strings}
    reader_flags: dict[str, Any] = {}
    if extra:
        tool = api._folder_reader(ns.verb, ns.store, positionals, kwargs)
        if tool is None:
            parser.error(f"unrecognized arguments: {' '.join(extra)}")
        reader_flags = _reader_flags(ns.verb, tool, extra)
    function: Callable[..., Any] = getattr(api, _FUNCTION[ns.verb])
    result = function(ns.store, *positionals.values(), **kwargs, **reader_flags)
    if getattr(ns, "svg", None) is not None:
        result = result.write_svg(ns.svg, force=ns.force)
    if ns.out is not None:
        result = result.to_bundle(ns.out, force=ns.force)
    elif ns.save:
        result = api.save(result)
    return _printed(result, ns.json)


def _own_checks(ns: argparse.Namespace) -> None:
    """What the command line refuses about how it was typed, before anything is read: an
    empty ``--svg`` or ``--out``, and ``--force`` with neither."""
    svg = getattr(ns, "svg", None)
    if ns.verb == "where":
        if svg == "":
            raise _Refusal("--svg takes the name of the file to write")
        if ns.force and svg is None and ns.out is None:
            raise _Refusal("--force applies to --svg and --out and was given without either")
    elif ns.force and ns.out is None:
        raise _Refusal("--force applies to --out and was given without it")
    if ns.out == "":
        raise _Refusal("--out takes the name of the folder to write")


def _reader_flags(verb: str, tool: str, extra: Sequence[str]) -> dict[str, Any]:
    """The words the verb's parser left over, read with the reader's own parser (a wrong one
    is a wrong command line), each flag typed as its keyword, in the order typed."""
    reader = look.Parser(prog=f"poisson-trace {verb}", add_help=False)
    api._reader(tool).add_arguments(reader)
    flags = reader.parse_args(list(extra))
    by_flag = {o: a for a in reader._actions for o in a.option_strings}
    out: dict[str, Any] = {}
    for word in extra:
        if word.startswith("-") and word != "-":
            action = by_flag.get(word.split("=", 1)[0])
            if action is not None:
                out[_keyword(action)] = getattr(flags, action.dest)
    return out


# ---------- the pages and the report ----------


def _ui(ns: argparse.Namespace, parser: look.Parser, typed: Collection[str]) -> int:
    kwargs = _with_config(_given(ns, parser, typed, "--store", "--open"))
    result = api.build_pages(ns.store, **kwargs)
    code = _printed(result, ns.json)
    if ns.open:
        commands.show_page(result.location)
    return code


def _report(ns: argparse.Namespace) -> int:
    return _printed(commands.report(ns.dir, open=ns.open, force=ns.force), False)


# ---------- handover, doctor and init ----------


def _handover(ns: argparse.Namespace) -> int:
    if ns.check is None:
        raise look.Usage(
            "--check DIR is required: the bundle to check", "poisson-trace handover --help"
        )
    return _printed(api.validate_bundle(ns.check), False)


def _doctor(ns: argparse.Namespace, parser: look.Parser, typed: Collection[str]) -> int:
    result = commands.doctor(**_given(ns, parser, typed))
    if ns.json:
        look.out(result.to_json())
        return int(result.exit_code)
    if result.refusal is not None:
        raise result.refusal
    look.out(result.to_markdown())
    return int(result.exit_code)


# the flags init --agent takes beside --agent; every other flag of init is the guided setup's
_AGENT_FLAGS = frozenset({"--agent", "--repo", "--print", "--force", "--json", "--debug"})


def _init(ns: argparse.Namespace, parser: look.Parser, typed: Collection[str]) -> int:
    if ns.agent or ns.repo is not None or ns.print:
        _agent_line(ns, typed)
    result = commands.init(**_given(ns, parser, typed))
    look.out(result.to_json() if ns.json else result.to_markdown())
    return int(result.exit_code)


def _agent_line(ns: argparse.Namespace, typed: Collection[str]) -> None:
    """``init --agent`` says one whole thing: what it takes beside ``--agent`` is its own."""
    if not ns.agent:
        flag = "--repo" if ns.repo is not None else "--print"
        raise look.Usage(f"{flag} goes with --agent", "poisson-trace init --agent --help")
    other = sorted(set(typed) - _AGENT_FLAGS)
    if other:
        raise look.Usage(
            f"--agent writes the setup for your coding agent and takes no {', '.join(other)}",
            "poisson-trace init --agent",
            "poisson-trace init --help",
        )
    if ns.print and ns.json:
        raise look.Usage(
            "--print prints the skill as text and takes no --json",
            "poisson-trace init --agent --print",
        )


if __name__ == "__main__":
    raise SystemExit(main())
