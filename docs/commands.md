# The commands

`poisson-trace` has twelve verbs. This page shows the help of the command and of every verb,
whole and as the installed command prints it, in the order the command lists them. Before the
verbs, it says what they all share: how a run is named, where the store and the failures come
from, the forms a result prints in, and the exit codes.

## The command

<!-- command -->
```
poisson-trace --help
```

<!-- output exit=0 -->
```
usage: poisson-trace [-h] [--version] [--plain] [--store PATH] [--config PATH]
                     VERB ...

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

options:
  -h, --help   show this help message and exit
  --version    print the versions of Trace, Prove and Python
  --plain      print plain text with no colour, as on a pipe; may come before
               or after the verb
  --store PATH
               with no verb, open the terminal app on this store, a folder or
               a name trace.toml gives (default: the store trace.toml names)
  --config PATH
               with no verb, open the terminal app on this config file
               (default: trace.toml in the current folder, if any)

verbs:
  VERB
    init       guided setup: finds your results, asks what counts as a
               failure, writes trace.toml
    runs       the runs of a store, newest first, with their names and numbers
    name       give a stored run a name of yours, take it back, or list the
               names
    where      where in the workflow the episodes of one stored run died
    compare    a before (A) and an after (B), compared
    fix-check  an old and a new version re-run on the same inputs, compared
    changes    the inputs whose failure share moved between two runs
    import     read in the results another tool wrote, as one new run of a
               store
    doctor     whether this environment is ready, and what to run when it is
               not
    handover   check a handover bundle --out wrote: every file, digest and
               promised key
    ui         build the pages over a store's runs and saved verdicts, opened
               from disk
    report     write a handover bundle's verdict as one HTML page into it

examples:
  poisson-trace runs --store prove-runs --event unsolved
  poisson-trace where previous --store prove-runs --event unsolved --at 20
  poisson-trace fix-check previous latest --store prove-runs --event unsolved \
      --inputs all --max-mde 0.2
```

`poisson-trace` with no verb opens the terminal app on a terminal ([the app](app.md)).
`python -m poisson_trace` is the same command.

## What every verb shares

**The store and the failures.** A store is a folder of runs, and the failures are the
outcomes that count as one. `--store` and `--event` give them on the command line, and
`--event` may be given more than once. With a `trace.toml` in the current folder, or the file
`--config` names, every verb takes both from it and needs neither flag
([the config page](config.md)). There is no default store.

**Naming a run.** Wherever a verb takes a run, it takes any of these:

- a name you gave it with `poisson-trace name`;
- the name it has from its manifest, such as `"tau2-airline 2026-09-15 a"`;
- latest or previous, the newest and the second newest complete run, and `latest:TARGET` or
  `previous:TARGET` for the same among one target's runs;
- its number in the `runs` listing, `#1` for the first row, which a shell needs quoted: `"#1"`;
- its full id.

A word that reaches no run, or two runs, is refused and never guessed. Latest and previous go by when
each run started, and are refused, naming the runs to give instead, where the start times
cannot order the runs: two runs that started at the same moment, or an imported run whose
start is only the time its file was written. In place of a run,
`where`, `compare`, `fix-check` and `changes` also take a folder of another tool's result
files, read with the flags `poisson-trace import` takes for that tool, and write nothing.

**What a verb prints.** The first line is the verdict: a word (`ok`, or one of *different*,
*no significant difference* and *too small to tell*) and a sentence. Then comes the report,
and last a line `next:` with the command to run next. On a pipe the report is plain text. On
a terminal the same facts are drawn with colour and wrapped to the window; `--plain` prints
the plain text there too, and so does `NO_COLOR` set to anything. `--json` prints the result
as one JSON document and nothing else, the same bytes whenever the inputs are the same.

**Options that are everywhere.** `--help` on the command and on every verb. `--version`
prints the versions of Trace, Prove and Python. `--debug` prints the details of an
unexpected failure on stderr; without it they go to `~/.cache/poisson-trace/errors.log`, and
one line names that file. An option may come before or after the verb. An option cut short,
such as `--ev` for `--event`, is refused.

**Refusals.** A refusal or a mistake in the command line is one line on stderr that opens
`error:`, with nothing on stdout. Where a command would move you on, it follows on a line of
its own that opens `next:`.

## Exit codes

| code | meaning |
|---|---|
| `0` | the result is printed, whatever it says; *too small to tell* is a result |
| `1` | refused; nothing was written |
| `2` | the command line is wrong |
| `3` | a failure after work started, or an unexpected failure |
| `4` | a check you asked for did not pass: `doctor` not ready, `handover --check` not whole |
| `130` | stopped with Ctrl-C |

## `poisson-trace init`

`init` sets Trace up in a folder: it finds the results there, asks which outcomes count as a failure, and writes `trace.toml`. It runs nothing. With `--agent` it writes a setup file for your coding agent instead ([Set up Trace with your coding agent](setup-with-your-agent.md)).

<!-- command -->
```
poisson-trace init --help
```

<!-- output exit=0 -->
```
usage: poisson-trace init [-h] [--agent] [--repo DIR] [--print] [--store PATH]
                          [--add-store PATH] [--event NAME]
                          [--names from=FORM] [--import] [--no-import]
                          [--metric NAME] [--cut recorded|X] [--below]
                          [--above] [--case name|input|position|var:NAME|test]
                          [--case-column COLUMN] [--outcome-column COLUMN]
                          [--failed VALUE] [--max-mde X] [--max-mde-hr X]
                          [--fail-on LIST] [--force] [--config PATH] [--yes]
                          [--json] [--debug]

Finds the results already in this folder's tree (the stores Prove wrote, and the
result files of the readers in this install), asks which store to start with when
there are several, or offers to import the result files when there is no store,
asks which outcomes count as a failure, shows the runs' names, and writes
trace.toml once, after the last answer. Every verb then takes its store and its
failures from it. It runs nothing, spends nothing and writes under no store but
the runs an import you agree to writes. Every question has a flag: with --yes it
asks nothing. It never searches the home folder or a folder above it.
On a trace.toml with [[import]] files not imported yet, as your coding agent
writes one, it shows them and asks whether to import them. With --agent, it
writes instead the setup your own coding agent follows (a skill and the prompt
to give it), in the two folders coding agents read skills from, and nothing else.

options:
  -h, --help            show this help message and exit
  --agent               write the setup your own coding agent follows, a skill
                        and its prompt, instead of setting up here; it makes
                        no model call and reads no key
  --repo DIR            with --agent: the repository to write the setup into
                        (default: this folder)
  --print               with --agent: print the skill and write nothing
                        (default: write the files)
  --store PATH          a store to set up, and nothing is searched;
                        repeatable: the first is the store every verb reads,
                        each other is named by its folder (default: the one
                        found here, or the one you pick)
  --add-store PATH      add the store at PATH to the config there already,
                        named by its folder; nothing else is asked or changed
                        (no default)
  --event NAME          an outcome that counts as a failure; repeatable
                        (default: every outcome of the newest 20 runs whose
                        name is not a word for success, shown for you to
                        confirm)
  --names from=FORM     how a run with no name of yours is named: from=target,
                        from=date or from=target-date (default: from=target)
  --import              import the result files found when there is no store,
                        without the question
  --no-import           leave them as they are and write the config with no
                        store
  --metric NAME         for the import: the metric, or the score column, to
                        read (no default)
  --cut recorded|X      for the import: where a score misses; recorded, for
                        DeepEval's own decision, or a number with --below or
                        --above (no default)
  --below               for the import: a score under the cut missed it
  --above               for the import: a score over the cut missed it
  --case name|input|position|var:NAME|test
                        for a DeepEval import: what identifies a test case
                        across versions (name, input or position); for JUnit
                        reports, name reads them by the test's name alone; for
                        a promptfoo import, var:NAME, the test variable NAME,
                        or test, the test's position (no default)
  --case-column COLUMN  for a Ragas import or a table's: the column that
                        identifies a case (no default)
  --outcome-column COLUMN
                        for a table's import: the column that holds each row's
                        outcome (no default)
  --failed VALUE        for a table's import: a value of the outcome column
                        that means a failure; repeatable (no default)
  --max-mde X           the largest detection limit fix-check and the check
                        accept, written to [check] (no default; written only
                        when given)
  --max-mde-hr X        the largest detectable hazard ratio compare accepts,
                        written to [check] (no default; written only when
                        given)
  --fail-on LIST        the check's results that fail its job, comma-
                        separated: failed-more, too-small or both (no default;
                        written only when given)
  --force               replace a config that is there already
  --config PATH         the config file to write (default: trace.toml in the
                        current folder)
  --yes                 ask nothing: every answer from a flag or its default
  --json                print the JSON structure instead of the report
  --debug               on an unexpected failure, print its details on stderr
                        as well as in the log

examples:
  poisson-trace init
  poisson-trace init --yes --store prove-runs --event unsolved
  poisson-trace init --add-store imported
  poisson-trace init --agent
```

**How it searches.** `init` looks in the folder you run it in and the folders below it, six
deep, in name order, and reads at most 10,000 entries; it says so when it stops short. It
skips `.git`, `.venv`, `venv`, `node_modules`, `__pycache__`, `.work`, `site-packages` and
every folder whose name opens with a dot but `.deepeval`, and it follows no link. It never
searches your home folder or a folder above it: there, name the store with `--store`.

**What it asks.** On a terminal it asks on stderr and reads your answers a line at a time:
which store to start with, when it finds several; which outcomes count as a failure, showing
the outcomes of the newest 20 runs with a guess in brackets (every outcome whose name is not
a word for success, such as `solved`, `passed` or `met`); and, when it finds result files and
no store, whether to import them, with the import's own questions. It writes `trace.toml`
once, after the last answer: until then, Ctrl-C leaves nothing behind. A `trace.toml` that is
there already is kept unless you give `--force`. Where stdin is not a terminal, `init` is
refused unless you give `--yes`, which takes every answer from its flag or its default.

## `poisson-trace runs`

`runs` lists the runs of a store, newest first, each with its name, its rows, how many of them failed, and whether it carries traces.

<!-- command -->
```
poisson-trace runs --help
```

<!-- output exit=0 -->
```
usage: poisson-trace runs [-h] [--store ROOT] [--event NAME] [--config PATH]
                          [--all] [--json] [--debug]

Lists the runs of a store, newest first: each complete run's number, its name, its
rows, how many of them failed for the --event names, whether any row carries a
trace (where and compare read traces; fix-check and changes do not need them), when
it started (UTC) and its status. The newest 50 complete runs are listed. A run's
number, such as "#1", names it to every verb.

options:
  -h, --help     show this help message and exit
  --store ROOT   the folder Prove stored the runs in, or the name of a store
                 trace.toml names (default: the store trace.toml names)
  --event NAME   an outcome that counts as a failure in the failed column;
                 repeatable (default: the failures trace.toml names, else
                 none, and the column is not counted)
  --config PATH  the config file to read (default: trace.toml in the current
                 folder, if any)
  --all          list every run, partial runs and those past the newest 50
                 included
  --json         print the JSON structure instead of the report
  --debug        on an unexpected failure, print its details on stderr as well
                 as in the log

examples:
  poisson-trace runs --store prove-runs --event unsolved
```

## `poisson-trace name`

`name` gives a run a name of yours, takes one back, or lists them. The names are kept in `trace-names.toml` at the store's root ([the config page](config.md)).

<!-- command -->
```
poisson-trace name --help
```

<!-- output exit=0 -->
```
usage: poisson-trace name [-h] [--store ROOT] [--config PATH] [--forget]
                          [--list] [--debug]
                          [RUN] [NAME]

Gives a stored run a name of yours, which every verb then takes for the run and
every report shows. The names are kept in trace-names.toml at the store's root; no
run's own files change. --forget takes a name back, and the run goes by the name it
has from its manifest again. --list shows the names of yours.

positional arguments:
  RUN            the run to name, by its name, latest, previous or its number
                 in the runs listing ("#3")
  NAME           the name to give it, at most 80 characters

options:
  -h, --help     show this help message and exit
  --store ROOT   the folder Prove stored the runs in, or the name of a store
                 trace.toml names (default: the store trace.toml names)
  --config PATH  the config file to read (default: trace.toml in the current
                 folder, if any)
  --forget       take back the name of yours that RUN has
  --list         list the names of yours
  --debug        on an unexpected failure, print its details on stderr as well
                 as in the log

examples:
  poisson-trace name previous "tau2 old re-run" --store prove-runs
  poisson-trace name --list --store prove-runs
```

## `poisson-trace where`

`where` reads one run and says at which step, and at which kind of step, its failing tries stopped. It needs a run that carries traces. The recipe is [A first look](recipes/first-look.md).

<!-- command -->
```
poisson-trace where --help
```

<!-- output exit=0 -->
```
usage: poisson-trace where [-h] [--store ROOT] [--event NAME] [--config PATH]
                           [--by kind|step] [--at STEP] [--boot B] [--seed S]
                           [--svg FILE] [--force] [--save] [--out DIR]
                           [--json] [--debug]
                           RUN

The share of one stored run's episodes not yet failed at each step index, the
median step of the failed ones, and where they stopped, by kind of step. An
episode failed when its outcome is one of the --event names; finishing otherwise
and timing out are ends of their own, and only episodes at the capture cap are
censored.

positional arguments:
  RUN             the run, by its name, latest, previous or its number in the
                  runs listing ("#3"), or a folder of results

options:
  -h, --help      show this help message and exit
  --store ROOT    the folder Prove stored the runs in, or the name of a store
                  trace.toml names (default: the store trace.toml names)
  --event NAME    an outcome that counts as a death; repeatable (default: the
                  failures trace.toml names)
  --config PATH   the config file to read (default: trace.toml in the current
                  folder, if any)
  --by kind|step  label the step an episode died at by the kind of its last
                  step, or by the nearest declared step name (default: kind)
  --at STEP       a step to read the curve at; repeatable (no default)
  --boot B        bootstrap resamples of the inputs, for the bands (default:
                  1000)
  --seed S        the bootstrap's seed (default: 0)
  --svg FILE      also write the curve as an SVG file; a file that exists is
                  refused without --force (no default)
  --force         let --svg or --out replace what exists
  --save          save the verdict as an artifact in the runs' store, under
                  .poisson/artifacts (no default: nothing is written without
                  it)
  --out DIR       also write the saved verdict as a handover bundle into DIR,
                  created; a DIR that exists is refused without --force (no
                  default)
  --json          print the JSON structure instead of the report
  --debug         on an unexpected failure, print its details on stderr as
                  well as in the log

examples:
  poisson-trace where previous --store prove-runs --event unsolved --at 20
```

## `poisson-trace compare`

`compare` reads two runs, a before and an after, and says whether tries fail sooner or later along the workflow in one than in the other. It needs runs that carry traces.

<!-- command -->
```
poisson-trace compare --help
```

<!-- output exit=0 -->
```
usage: poisson-trace compare [-h] [--store ROOT] [--event NAME]
                             [--config PATH] [--by kind|step] [--at STEP]
                             --max-mde-hr X [--alpha A] [--verdicts FILE]
                             [--save] [--out DIR] [--force] [--json] [--debug]
                             A B

Two stored runs, a before (A) and an after (B), compared: the log-rank test
stratified by config cell over the cells both runs carry, the direction, the
smallest hazard ratio the design could have detected, and one of three lines:
different, no significant difference, or too small to tell. --max-mde-hr is the
largest detectable hazard ratio you accept, and it has no default.

positional arguments:
  A                the run before the change, by its name, latest, previous or
                   its number in the runs listing ("#3"), or a folder of
                   results
  B                the run after the change

options:
  -h, --help       show this help message and exit
  --store ROOT     the folder Prove stored the runs in, or the name of a store
                   trace.toml names (default: the store trace.toml names)
  --event NAME     an outcome that counts as a death; repeatable (default: the
                   failures trace.toml names)
  --config PATH    the config file to read (default: trace.toml in the current
                   folder, if any)
  --by kind|step   label the step an episode died at by the kind of its last
                   step, or by the nearest declared step name (default: kind)
  --at STEP        a step to read the curve at; repeatable (no default)
  --max-mde-hr X   the largest minimum detectable hazard ratio you accept,
                   such as 1.5 (default: max_mde_hr in trace.toml's [check],
                   else none)
  --alpha A        the test's level (default: 0.05)
  --verdicts FILE  a .csv or .jsonl of verdicts (case, outcome, score,
                   failure_kind) joined onto both runs where they recorded
                   none; nothing is written (no default)
  --save           save the verdict as an artifact in the runs' store, under
                   .poisson/artifacts (no default: nothing is written without
                   it)
  --out DIR        also write the saved verdict as a handover bundle into DIR,
                   created; a DIR that exists is refused without --force (no
                   default)
  --force          let --out replace a folder that exists
  --json           print the JSON structure instead of the report
  --debug          on an unexpected failure, print its details on stderr as
                   well as in the log

examples:
  poisson-trace compare "#3" previous --store prove-runs --event unsolved \
      --max-mde-hr 1.5
```

An example, on the two runs of one airline agent under `tests/fixtures/tau2` in a clone of
the repository, ten minutes apart with nothing changed between them:

<!-- command -->
```
poisson-trace compare "tau2-airline 2026-09-15 a" "tau2-airline 2026-09-15 b" \
  --store tests/fixtures/tau2 --event unsolved --max-mde-hr 1.3
```

<!-- excerpt exit=0 -->
```
too small to tell  too few failures to see a 1.3-fold change
```

<!-- excerpt exit=0 -->
```
hazard ratio, after against before: 1.11 (0.80 to 1.55, 95%); Peto's one-step estimate from the observed, expected and variance above
```

The two runs are the same agent, and the verdict does not say they are the same: it says
these tries are too few to see a change of the size asked about, and the report's Guidance
block says how many tries of each input would be enough.

## `poisson-trace fix-check`

`fix-check` reads an old and a new version run on the same inputs and says whether the new one fails less, with the old version as the control. It needs no traces. The recipe is [Check a fix](recipes/check-a-fix.md).

<!-- command -->
```
poisson-trace fix-check --help
```

<!-- output exit=0 -->
```
usage: poisson-trace fix-check [-h] [--store ROOT] [--event NAME]
                               [--config PATH] [--alpha A] [--top N]
                               [--failing-from RUN] [--min-failures M]
                               [--inputs all] --max-mde X [--seed S]
                               [--measures] [--max-change MEASURE=N%]
                               [--verdicts FILE] [--save] [--out DIR]
                               [--force] [--json] [--debug]
                               OLD NEW

An old and a new version, each re-run on the same inputs, compared input by input
with the old version as the control: how often the old version failed again with
nothing changed, the exact stratified test, the difference with its interval, the
smallest change the design could have detected, and one of three lines: different,
no significant difference, or too small to tell. An input is one config cell of the
sweep. Which inputs are compared has no default (--failing-from or --inputs all),
and neither has --max-mde.

positional arguments:
  OLD                   the old version's run, by its name, latest, previous
                        or its number in the runs listing ("#3"), or a folder
                        of results
  NEW                   the new version's run

options:
  -h, --help            show this help message and exit
  --store ROOT          the folder Prove stored the runs in, or the name of a
                        store trace.toml names (default: the store trace.toml
                        names)
  --event NAME          an outcome that counts as a failure; repeatable
                        (default: the failures trace.toml names)
  --config PATH         the config file to read (default: trace.toml in the
                        current folder, if any)
  --alpha A             the tests' level (default: 0.05)
  --top N               the inputs the report's table shows; every flagged
                        input shows, whatever N is, and --json lists all
                        (default: 10)
  --failing-from RUN    compare the inputs that failed in RUN, a third run
                        that is neither OLD nor NEW (no default)
  --min-failures M      with --failing-from, the failures an input needs in
                        RUN to be compared (default: 1)
  --inputs all          all: compare every input either run carries (no
                        default)
  --max-mde X           the largest detection limit you accept, as a share of
                        failures: 0.2 is twenty points (default: max_mde in
                        trace.toml's [check], else none)
  --seed S              the seed of the by-input reading's draws (default: 0)
  --measures            also compare the runs' time, length, tokens and cost,
                        case by case, in a section of the report (no default:
                        the section prints only when asked)
  --max-change MEASURE=N%
                        the change in a measure's mean you accept as none, as
                        a share of the old mean, such as wall_time_s=10%;
                        repeatable, and implies --measures (default:
                        max_change in trace.toml's [check], else none)
  --verdicts FILE       a .csv or .jsonl of verdicts (case, outcome, score,
                        failure_kind) joined onto both runs where they
                        recorded none; nothing is written (no default)
  --save                save the verdict as an artifact in the runs' store,
                        under .poisson/artifacts (no default: nothing is
                        written without it)
  --out DIR             also write the saved verdict as a handover bundle into
                        DIR, created; a DIR that exists is refused without
                        --force (no default)
  --force               let --out replace a folder that exists
  --json                print the JSON structure instead of the report
  --debug               on an unexpected failure, print its details on stderr
                        as well as in the log

examples:
  poisson-trace fix-check previous latest --store prove-runs --event unsolved \
      --inputs all --max-mde 0.2
```

## `poisson-trace changes`

`changes` reads two runs input by input and names the inputs whose share of failures moved. It needs no traces.

<!-- command -->
```
poisson-trace changes --help
```

<!-- output exit=0 -->
```
usage: poisson-trace changes [-h] [--store ROOT] [--event NAME]
                             [--config PATH] [--alpha A] [--top N]
                             [--verdicts FILE] [--save] [--out DIR] [--force]
                             [--json] [--debug]
                             A B

Lists the inputs whose failure share moved between two runs, each with Fisher's
exact test and a Benjamini-Hochberg correction across the inputs, and says which
changes this design could not have flagged. An input is one config cell.

positional arguments:
  A                the first run, by its name, latest, previous or its number
                   in the runs listing ("#3"), or a folder of results
  B                the second run

options:
  -h, --help       show this help message and exit
  --store ROOT     the folder Prove stored the runs in, or the name of a store
                   trace.toml names (default: the store trace.toml names)
  --event NAME     an outcome that counts as a failure; repeatable (default:
                   the failures trace.toml names)
  --config PATH    the config file to read (default: trace.toml in the current
                   folder, if any)
  --alpha A        the tests' level (default: 0.05)
  --top N          the inputs the report's table shows; every flagged input
                   shows, whatever N is, and --json lists all (default: 10)
  --verdicts FILE  a .csv or .jsonl of verdicts (case, outcome, score,
                   failure_kind) joined onto both runs where they recorded
                   none; nothing is written (no default)
  --save           save the verdict as an artifact in the runs' store, under
                   .poisson/artifacts (no default: nothing is written without
                   it)
  --out DIR        also write the saved verdict as a handover bundle into DIR,
                   created; a DIR that exists is refused without --force (no
                   default)
  --force          let --out replace a folder that exists
  --json           print the JSON structure instead of the report
  --debug          on an unexpected failure, print its details on stderr as
                   well as in the log

examples:
  poisson-trace changes previous latest --store prove-runs --event unsolved
```

## `poisson-trace import`

`import` reads the result files another tool wrote and writes them as one new run of a store,
one import for each version. The verbs above then read that run like any other.
`poisson-trace-import` is the same command under its earlier name, and it stays.

<!-- command -->
```
poisson-trace import --help
```

<!-- output exit=0 -->
```
usage: poisson-trace import [-h] [--version] [--plain] TOOL ...

Read the result files another tool already wrote and write them as one new run of a store in
Prove's format, for Poisson Trace's verbs to read. One import is one version: import the old
version and the new one into the same store, then compare them with poisson-trace fix-check.
A store is the folder Prove keeps runs in; a case is one test case or question of the tool's
files, and the rows that share a case are its repeats.

A folder of results may be given in place of the files, and in place of the tool too
(poisson-trace import ./results --store trace-store): its files are found by the readers'
own detectors and read as one run, named after the folder unless --run names it.

options:
  -h, --help      show this help message and exit
  --version       print the versions of Trace, Prove and Python
  --plain         print plain text with no colour, as on a pipe; may come
                  before or after the tool

tools:
  TOOL
    deepeval      DeepEval's saved test runs, as DeepEval 4.2.6 writes them.
    ragas         Ragas's per-row score tables, saved as CSV, JSON Lines, JSON
                  or Parquet.
    table         Any table of results a tool or a script saved: CSV, JSON
                  Lines, JSON or Parquet.
    junit         JUnit XML reports, as pytest, Jest, Go, Maven and CI systems
                  write them.
    promptfoo     promptfoo results, as ``promptfoo eval -o results.json`` (or
                  ``.jsonl``) writes them.
    inspect       Inspect AI logs: the ``.eval`` archive, the ``.json`` log,
                  and an unpacked ``.eval`` folder.
    openai-evals  OpenAI Evals records, as ``oaieval ... --record_path
                  log.jsonl`` writes them.
    langsmith     LangSmith runs: the API's answers, the langsmith command's
                  exports and an experiment's CSV.
    braintrust    Braintrust experiments: the API's answers, and the JSON and
                  CSV an experiment's page downloads.
    weave         W&B Weave evaluations: the calls Weave's service answers
                  with, and the files its Traces page

examples:
  poisson-trace import deepeval results/test_run_20260905_185407.json \
      --store trace-store --run before --metric "Tests Passed" --cut recorded --case name
  poisson-trace import ragas base-scores.jsonl --store trace-store --run base \
      --metric faithfulness --cut 0.5 --below --case-column question_id
  poisson-trace import table results-old.csv --store trace-store --run old \
      --case-column case --outcome-column outcome --failed failed --failed crashed
  poisson-trace import junit reports/old.xml --store trace-store --run old
  poisson-trace import promptfoo results.json --store trace-store --run old --prompt 1 --case var:case
  poisson-trace import inspect logs/old.eval --store trace-store --run old
  poisson-trace import openai-evals old.jsonl --store trace-store --run old
  poisson-trace import langsmith old.json --store trace-store --run old --case-from example --outcome-from feedback:exact --cut 0.5 --below
  poisson-trace import braintrust old.json --store trace-store --run old --case-from input --outcome-from score:exact --cut 0.5 --below
  poisson-trace import weave old.jsonl --store trace-store --run old --case-from example --outcome-from score:exact --cut 0.5 --below
```

Each tool has flags of its own, which `poisson-trace import TOOL --help` lists and its page
explains:

- [DeepEval](integrations/deepeval.md): `poisson-trace import deepeval`
- [Ragas](integrations/ragas.md): `poisson-trace import ragas`
- [Tables](integrations/table.md): `poisson-trace import table`
- [JUnit](integrations/junit.md): `poisson-trace import junit`
- [promptfoo](integrations/promptfoo.md): `poisson-trace import promptfoo`
- [Inspect](integrations/inspect.md): `poisson-trace import inspect`
- [OpenAI Evals](integrations/openai-evals.md): `poisson-trace import openai-evals`
- [LangSmith](integrations/langsmith.md): `poisson-trace import langsmith`
- [Braintrust](integrations/braintrust.md): `poisson-trace import braintrust`
- [Weave](integrations/weave.md): `poisson-trace import weave`

LangSmith, Braintrust and Weave can also be pulled with your key, by an address in place of
the files. Each of the three pages says how.

## `poisson-trace doctor`

`doctor` says whether this environment is ready, one line for each thing it checks, and exits 4 when it is not. It fixes nothing and asks nothing. `--setup` also checks the files a `trace.toml` lists to import.

<!-- command -->
```
poisson-trace doctor --help
```

<!-- output exit=0 -->
```
usage: poisson-trace doctor [-h] [--config PATH] [--setup] [--json] [--debug]

Says whether this environment is ready for Trace, one line for each thing it
checks: the Python running it, the Trace package and where it was imported from,
Prove, the config file and the stores it names, the names of yours, and the
readers of other tools' files in the install. A line that fails ends with the
command to run. It fixes nothing and asks nothing; it exits 4 when not ready.
With --setup it is the check a coding agent runs on the trace.toml it wrote:
the same, read as a setup needs it, and each [[import]] file not imported yet
read with its reader; ready exits 0, not ready 1 with error: and next: lines on
stderr, a wrong setting 2.

options:
  -h, --help     show this help message and exit
  --config PATH  the config file to read (default: trace.toml in the current
                 folder, if any)
  --setup        check a trace.toml written for review, its [[import]] files
                 included, with the setup check's exit codes (0 ready, 1 not
                 ready, 2 a wrong setting)
  --json         print the JSON structure instead of the report
  --debug        on an unexpected failure, print its details on stderr as well
                 as in the log

examples:
  poisson-trace doctor
  poisson-trace doctor --config team.toml
  poisson-trace doctor --setup
```

## `poisson-trace handover`

`handover` checks a bundle that `--out DIR` wrote: every file against the digest listed for it. It exits 0 when the bundle is whole and exits 4 when it is not ([the handover page](handover.md)).

<!-- command -->
```
poisson-trace handover --help
```

<!-- output exit=0 -->
```
usage: poisson-trace handover [-h] --check DIR [--debug]

Checks a handover bundle that where, compare, fix-check or changes wrote with
--out DIR: every file handover.json and artifact.json list is there with its
digest and size, result.json is the verb's JSON with every key the handover
promises, report.md opens with the verdict line, and nothing in it is content
Trace never hands over. It exits 4 with the first failing line when the bundle
does not hold what it promises, and 1 when DIR is not a bundle.

options:
  -h, --help   show this help message and exit
  --check DIR  the bundle to check
  --debug      on an unexpected failure, print its details on stderr as well
               as in the log

examples:
  poisson-trace handover --check verdicts/fix-check-2026-11-04
```

## `poisson-trace ui`

`ui` builds Trace's pages over a store's runs and saved verdicts, as files that open from disk, and prints where they are.

<!-- command -->
```
poisson-trace ui --help
```

<!-- output exit=0 -->
```
usage: poisson-trace ui [-h] [--open] [--store ROOT] [--config PATH] [--json]
                        [--debug]

Builds Trace's pages in the store's .poisson/ui/trace/: the runs and the saved
verdicts, each verdict's page and what it cannot say, opened from disk with
nothing loaded from the network. With a config, every store it names gets its
pages, and they link one another. Prove's own dashboard beside them is never
touched. Every command that saves a verdict rebuilds the pages too.

options:
  -h, --help     show this help message and exit
  --open         open the pages in the browser (default: not opened)
  --store ROOT   the folder Prove stored the runs in, or the name of a store
                 trace.toml names (default: the store trace.toml names)
  --config PATH  the config file to read (default: trace.toml in the current
                 folder, if any)
  --json         print the JSON structure instead of the report
  --debug        on an unexpected failure, print its details on stderr as well
                 as in the log

examples:
  poisson-trace ui
  poisson-trace ui --open
```

## `poisson-trace report`

`report` writes one HTML page into a bundle, the verdict as a page that opens from disk with nothing else present. The recipe is [A page to send](recipes/a-page-to-send.md).

<!-- command -->
```
poisson-trace report --help
```

<!-- output exit=0 -->
```
usage: poisson-trace report [-h] [--open] [--force] [--debug] DIR

Writes report.html into a bundle that where, compare, fix-check or changes wrote
with --out DIR: the verdict's page as the static UI shows it, self-contained, with
no script and nothing loaded from the network, and lists it in handover.json. A
bundle that does not hold what it promises is refused first, as handover --check
refuses it.

positional arguments:
  DIR         the bundle --out wrote (no default)

options:
  -h, --help  show this help message and exit
  --open      open the page in the browser; a report.html that is there is
              opened as it is, not written again (default: not opened)
  --force     replace a report.html that is there (default: refused, or opened
              with --open)
  --debug     on an unexpected failure, print its details on stderr as well as
              in the log

examples:
  poisson-trace report verdicts/fix-check-2026-11-04
  poisson-trace report verdicts/fix-check-2026-11-04 --open
```
