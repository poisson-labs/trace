# Poisson Trace

Where in the workflow do runs die, and did the change make them fail less.

Poisson Trace reads runs that [Prove](https://github.com/poisson-labs/prove) has already
stored and answers two questions about them, each with a stated confidence and with what the
design could not have detected.

**Where runs die.** `where` puts every run on one clock (the index of the step it was
executing) and draws the survival curve over that clock: at step 10, what share of runs was
still going; at step 20; at step 30. Runs that ended normally, timed out or hit the capture
cap are censored, never counted as deaths. The curve is split by the kind of step runs die at
(model call, tool call, guardrail, agent turn), each part with a stated interval. `compare`
takes two stored runs, a before and an after, and says whether the curves differ.

**Whether a change made runs fail less.** Teams check a change by re-running the inputs that
failed and counting how many now succeed. That count has no control: on an agent where
nothing changed, some of those inputs succeed on a re-run anyway, and the count cannot say
how many. `fix-check` does the same job with the missing parts added: the old version re-run
on the same inputs beside the new one, a test that compares the two inside each input, the
difference with an interval, and one line that reads *different*, *no significant
difference* or *too small to tell*. `changes` names the inputs whose failure share moved
between two runs, with a multiple-testing correction. Whenever the line is *too small to
tell*, the report says how many repeats or how many inputs would settle it.

Every number prints with what the run could not have detected.

Released with the Poisson Labs post responding to LangSmith Engine v2 (2026-10-01; the post
links here). Trace is a reader of stored runs: it runs nothing, captures nothing, patches
nothing, phones nowhere.

## Pre-release for design partners

This is Poisson Trace `0.1.0rc1`, a private pre-release for design partners. It is not on
PyPI: the `poisson-trace` and `proofload` you would get there by name are placeholders that do
not run, so install from the files sent with this README. You get three:

| File | What it is |
|---|---|
| `poisson_trace-0.1.0rc1-py3-none-any.whl` | Trace |
| `proofload-0.0.1-py3-none-any.whl` | Prove, whose stores Trace reads, and writes other tools' results into |
| `poisson_trace-0.1.0rc1.tar.gz` | Trace's source: this README, the pages under `docs/`, and the example files the commands below read |

The links to github.com/poisson-labs on this page lead to repositories that are private for
now; every page they name is in the source archive.

### Install from the files

Trace needs Python 3.11 or newer. Check yours first: the `python3` that macOS ships is 3.9,
and pip refuses this package on it. If `python3 --version` prints a version below 3.11, type
`python3.11`, `python3.12` or `python3.13` where the first line says `python3`. In the folder
holding the three files:

```
python3 -m venv trace-env
. trace-env/bin/activate
pip install ./poisson_trace-0.1.0rc1-py3-none-any.whl ./proofload-0.0.1-py3-none-any.whl
poisson-trace --version
```

pip takes numpy, scipy, pandas and pyarrow from PyPI. The last line prints
`poisson-trace 0.1.0rc1 (poisson-prove 0.0.1, Python 3.11.7)`, with your Python's version in
place of 3.11.7. Then unpack the source archive and work inside it; every command below, and
every page under `docs/`, runs from there:

```
tar -xzf poisson_trace-0.1.0rc1.tar.gz
cd poisson_trace-0.1.0rc1
```

The [Install](#install) section further down is for the public release and does not apply to
this one. If a command says Prove is missing and names
`pip install git+https://github.com/poisson-labs/prove`, install the Prove wheel as above
instead.

### A first result on each reader

Each block puts one reader's example pair in a folder of its own, sets it up with
`poisson-trace init`, and asks `fix-check` whether the second version failed less than the
first. `--max-mde` is the smallest drop in failure share you need to be able to see (0.10 is
ten points); every verdict says what it could not have detected. With your own results, run
`poisson-trace init` in the folder that holds them: it finds Prove stores and the other four
readers' files on its own, and asks what it needs to know.

Prove's stored runs, the tau2-airline agent run twice with nothing changed:

<!-- command -->
```
mkdir -p try-prove && cp -R tests/fixtures/tau2 try-prove/proofload-runs
cd try-prove && poisson-trace init --yes
poisson-trace fix-check "tau2-airline 2026-09-15 a" "tau2-airline 2026-09-15 b" --inputs all --max-mde 0.10
```

<!-- excerpt exit=0 -->
```
ok  wrote trace.toml: store proofload-runs (3 runs), failures unsolved
```

<!-- excerpt exit=0 -->
```
too small to tell  could not have detected a drop in failure share below 11.1 points, and 10 was asked for
```

DeepEval's saved test runs: one agent run twice on 164 HumanEval problems, 56 minutes apart,
with nothing changed, written through DeepEval:

<!-- command -->
```
mkdir -p try-deepeval/results
gunzip -c tests/fixtures/ingest/deepeval/humaneval-a.json.gz > try-deepeval/results/test_run_20260905_185407.json
gunzip -c tests/fixtures/ingest/deepeval/humaneval-b.json.gz > try-deepeval/results/test_run_20260905_195009.json
cd try-deepeval && poisson-trace init --yes --metric "Tests Passed" --cut recorded --case name
poisson-trace fix-check test_run_20260905_185407 test_run_20260905_195009 --inputs all --max-mde 0.02
```

<!-- excerpt exit=0 -->
```
ok  wrote trace.toml and imported 2 runs into trace-store, failures missed
```

<!-- excerpt exit=0 -->
```
different  the new version failed more on these inputs (exact Cochran-Mantel-Haenszel, stratified by input, p = 0.036)
```

Ragas's score table, a base model and its fine-tuned version, a faithfulness below 0.5 a miss:

<!-- command -->
```
mkdir -p try-ragas && cp tests/fixtures/ingest/ragas/rag-base.jsonl tests/fixtures/ingest/ragas/rag-raft.jsonl try-ragas/
cd try-ragas && poisson-trace init --yes --metric faithfulness --cut 0.5 --below --case-column case
poisson-trace fix-check rag-base rag-raft --inputs all --max-mde 0.10
```

<!-- excerpt exit=0 -->
```
ok  wrote trace.toml and imported 2 runs into trace-store, failures missed
```

<!-- excerpt exit=0 -->
```
too small to tell  could not have detected a drop in failure share below 15.9 points, and 10 was asked for
```

Any table of results: the same HumanEval pair saved as CSV, with an outcome column:

<!-- command -->
```
mkdir -p try-table && cp tests/fixtures/ingest/table/humaneval-*.csv try-table/
cd try-table && poisson-trace init --yes --case-column case --outcome-column outcome --failed failed_assertion --failed crashed
poisson-trace fix-check humaneval-a humaneval-b --inputs all --max-mde 0.02
```

<!-- excerpt exit=0 -->
```
ok  wrote trace.toml and imported 2 runs into trace-store, failures missed
```

<!-- excerpt exit=0 -->
```
different  the new version failed more on these inputs (exact Cochran-Mantel-Haenszel, stratified by input, p = 0.036)
```

JUnit XML reports: pytest replaying the same pair, four repeats at one temperature where the
files above hold 32 at two:

<!-- command -->
```
mkdir -p try-junit && cp tests/fixtures/ingest/junit/humaneval-*.xml try-junit/
cd try-junit && poisson-trace init --yes --case name
poisson-trace fix-check humaneval-a humaneval-b --inputs all --max-mde 0.05
```

<!-- excerpt exit=0 -->
```
ok  wrote trace.toml and imported 2 runs into trace-store, failures missed
```

<!-- excerpt exit=0 -->
```
no significant difference  p = 0.639; could not have detected a drop in failure share below 3.2 points
```

A pair with nothing changed can read *different*: the [DeepEval page](docs/integrations/deepeval.md)
says what that one means, and the [JUnit page](docs/integrations/junit.md) why its smaller
replay cannot see it. In any of these folders, `poisson-trace runs` lists the runs and `poisson-trace doctor` says
whether the setup is ready. Each reader's page under `docs/integrations/` shows its import
command and every flag.

### What works today

- Five readers: Prove's stored runs, and the result files of DeepEval, Ragas, any table of
  results (CSV, JSON Lines, JSON or Parquet) and JUnit XML reports.
- The commands: `init`, `doctor`, `runs`, `name`, `import`, `fix-check` and `changes` on any
  of the five; `where` and `compare` on Prove's runs, which carry traces. An imported run
  carries none, so on one `where` says so and `compare` points to `fix-check`.
- Checked on macOS with Python 3.11, 3.12 and 3.13, from the three files alone.

### What is coming

- Readers for promptfoo, Inspect, OpenAI Evals, Braintrust, Weave, LangSmith, OpenTelemetry
  and Lemma.
- A pull-request check that puts the fix check's verdict on the pull request.

### Problems

Send them to work@poissonlabs.ai, with the command you typed, what it printed and what
`poisson-trace --version` prints. When a command fails unexpectedly it prints one line naming
`~/.cache/poisson-trace/errors.log`; attach that file too.

## Install

Prove is not yet on PyPI, so it is installed from its repository and is not a declared
dependency of this package:

```
pip install poisson-trace
pip install git+https://github.com/poisson-labs/prove
```

Nobody outside Poisson Labs can run Trace until Prove is public. `--help` and `--version`
work without it; a command that reads runs refuses, in one line that names the install
command above, when the `proofload` package is missing or is not version 0.0.1.

From a clone of this repository, with the same two lines:

```
git clone https://github.com/poisson-labs/trace
cd trace
python -m venv .venv && . .venv/bin/activate
pip install .
pip install git+https://github.com/poisson-labs/prove
poisson-trace runs --store tests/fixtures/cs --event unresolved
poisson-trace where "cs_agents 2026-09-25 a" --store tests/fixtures/cs --event unresolved
```

## Set up: `poisson-trace init`

Run `poisson-trace init` in your project's folder. It finds the results already there (the
stores Prove wrote, and the result files of DeepEval, Ragas, a table of results or a JUnit
report), asks what counts as a failure,
and writes `trace.toml`, from which every verb then takes its store and its failures: the
commands after it need neither `--store` nor `--event`. It runs nothing and spends nothing,
and it writes under no store but the runs of an import you agree to; it never writes
`trace.toml` into a store or a run's folder.

It searches the folder you run it in and the folders below it, six deep, breadth first and in
name order, reading at most 10,000 entries (it says so when it stops short); it skips `.git`,
`.venv`, `venv`, `node_modules`, `__pycache__`, `.work`, `site-packages` and every folder
whose name opens with a dot but `.deepeval`, and follows no link. It never searches your home
folder or a folder above it; there, give the store with `--store PATH`.

On a terminal it asks, on stderr, and reads your answers a line at a time:

- **Which store**, when it finds several: `Which results do you want to start with? [1]`.
  The others can be added later with `poisson-trace init --add-store PATH`, which the summary
  shows; a store added is named by its folder, and `--store NAME` then reaches it (added to a
  config that names no store yet, it becomes the store every verb reads).
- **What counts as a failure**: the outcomes the newest 20 runs carry, each with its count of
  episodes. The default, in brackets, is every outcome whose name is not a word for success
  (`solved`, `resolved`, `passed`, `met`, `ok`, `success`, `fixed`, `planned`, `cited`,
  `survived`, `correct`, `fresh`, `fast`; `poisson_trace.setup.SUCCESS_WORDS`). It is a guess,
  shown for you to confirm or replace with the numbers you type.
- **Whether to import**, when there is no store but there are result files another tool wrote:
  `Import them as runs Trace can read? [Y/n]`, then the import's own questions (for DeepEval and
  Ragas the metric, the cut and its side, what identifies a case; for a table the case column,
  the outcome column and the values that mean a failure; JUnit reports need none). Each file
  becomes one run, named after the file, in a store `trace-store` beside `trace.toml`. See
  [DeepEval](docs/integrations/deepeval.md), [Ragas](docs/integrations/ragas.md),
  [tables](docs/integrations/table.md) and [JUnit](docs/integrations/junit.md).

Every question has a flag (`poisson-trace init --help` lists them), and `--yes` asks nothing,
taking each answer from its flag or its default. The import's questions have no default: with
`--yes` and result files found, give the import's flags, or `--no-import` to write the config
with no store. When files of more than one tool are found, `init` imports none of them (one
set of answers fits one tool); give `--no-import` and import each with `poisson-trace import`. The
listing comes first on stderr, so a refusal after it is the last lines there. Here it is on the tau2 fixture, copied into a
folder of its own:

<!-- command -->
```
mkdir -p my-agent && cp -R tests/fixtures/tau2 my-agent/proofload-runs
cd my-agent && poisson-trace init --yes
```

What it found, on stderr:

<!-- excerpt exit=0 -->
```
  found 1 Prove store:
    1) proofload-runs            3 runs · tau2-airline · newest 2026-09-17
Using proofload-runs, the store found.
```

and its summary, on stdout, with the same setup as one command that asks nothing:

<!-- excerpt exit=0 -->
```
ok  wrote trace.toml: store proofload-runs (3 runs), failures unsolved
  names    3 runs, named from their manifests (tau2-airline 2026-09-17 a, tau2-airline 2026-09-15 b, tau2-airline 2026-09-15 a); none named by you yet: poisson-trace name RUN "a name"
  prove    poisson-prove is installed at the version Trace reads
  the same setup, without questions:
    poisson-trace init --yes --store proofload-runs --event unsolved
next: poisson-trace runs
```

It writes the file once, after the last answer; until then, Ctrl-C leaves nothing behind. A
`trace.toml` that is there already is left as it is unless you give `--force`, but for one
that names a store and no failures, which `init` completes, keeping every other line. Stdin
that is not a terminal is refused unless you give `--yes`.

### `trace.toml`

<!-- command -->
```
cat my-agent/trace.toml
```

<!-- output exit=0 -->
```
# Poisson Trace: where your results are, and what counts as a failure.
# Written by `poisson-trace init`. Edit it freely; `poisson-trace doctor` checks it.
version = 1

[store]
path = "proofload-runs"

[events]
failed = ["unsolved"]

[names]
from = "target"
```

Every verb, `import` among them, reads `trace.toml` in the current folder, never one in
a folder above, or the file `--config PATH` names (before or after the verb). A store path in
it is read from the folder that holds the file. The commands then need no flags:

<!-- command -->
```
cd my-agent && poisson-trace runs
```

<!-- output exit=0 -->
```
ok  3 runs in proofload-runs (newest first); 0 named by you, 3 named from their manifests

  #  name                       rows  failed  traces  started           status
  1  tau2-airline 2026-09-17 a    10       3  no      2026-09-17 14:02  complete
  2  tau2-airline 2026-09-15 b   200     112  yes     2026-09-15 21:11  complete
  3  tau2-airline 2026-09-15 a   200     110  yes     2026-09-15 21:01  complete

next: poisson-trace where "tau2-airline 2026-09-15 b"
```

| setting | what it holds |
|---|---|
| `version` | `1` |
| `[store] path`, `[store.NAME] path` | the store every verb reads, and stores named by you; a name is 1 to 40 letters, digits, `-` and `_` |
| `[events] failed` | the outcomes that count as a failure, one or more, each once |
| `[check] max_mde` | the `--max-mde` that `fix-check` takes when none is given, strictly between 0 and 1 |
| `[check] max_mde_hr` | the `--max-mde-hr` that `compare` takes when none is given, above 1 |
| `[check] fail_on` | a list drawn from `failed-more` and `too-small`, for the pull-request check to come |
| `[names] from` | how a run with no name of yours is named: `target` (`tau2-airline 2026-09-15 a`, the default), `date` (`2026-09-15 a`) or `target-date` (`tau2-airline gpt-4.1-mini 2026-09-15 a`, the model taken from the target id) |
| `[upload]` | `enabled`, `url` and `token_env`, checked now and read by the upload to come |

A flag replaces what the file gives: an `--event` given replaces its failures, it does not add
to them, and `--store NAME` takes the store the file names so before a folder of that name.
What neither gives is a mistake in the command line, as it is with no file. The ceilings have
no default: `init` writes `[check]` only when you give `--max-mde`, `--max-mde-hr` or
`--fail-on`. A file that is not a version 1 config is refused, by every verb, naming the file
and the line the fault is on:

<!-- command -->
```
cd my-agent && sed 's/^failed/faild/' trace.toml > typo.toml && poisson-trace runs --config typo.toml
```

<!-- output exit=1 -->
```
error: typo.toml line 9: [events] "faild" is not a setting; did you mean "failed"?
```

### `poisson-trace doctor`

`doctor` says whether this environment is ready, one line for each thing it checks: the
Python running Trace, the package and where it was imported from (with a note when that is
outside the interpreter's environment, as an editable install is), Prove, the config and the
stores it names, the names of yours, and the readers in the install. A line that fails ends
with the command that mends it, where one does (a config that is a folder, or runs that carry
no outcome, say what is wrong instead), and `next:` is the first of them; not ready exits 4.
A store named in `trace.toml` whose runs carry none of its failures is noted: give `--event`
with `--store NAME` for it. It fixes nothing and asks nothing.

<!-- command -->
```
cd my-agent && poisson-trace doctor
```

<!-- excerpt exit=0 -->
```
ok  this environment is ready
```

<!-- excerpt exit=0 -->
```
  prove     poisson-prove 0.0.1 (the version Trace reads)
  config    trace.toml: store proofload-runs (3 runs, 3 complete, 0 partial), failures unsolved
  names     proofload-runs: no names of yours yet
  readers   deepeval, ragas, table, junit
next: poisson-trace runs
```

## Use

Point Trace at a Prove store (the directory that holds one `manifest.json` per run) and name
the outcomes that count as a failure, by flag or in `trace.toml`:

```
poisson-trace init [--store PATH ...] [--event NAME ...] [--names from=FORM] [--yes] [--json]
                  [--import | --no-import] [--max-mde X] [--max-mde-hr X] [--fail-on LIST]
                  [--force] [--config PATH]
poisson-trace init --add-store PATH [--config PATH]
poisson-trace doctor [--config PATH] [--json]

poisson-trace runs --store ROOT [--event NAME ...] [--all] [--json]

poisson-trace name RUN NAME --store ROOT
poisson-trace name RUN --forget --store ROOT
poisson-trace name --list --store ROOT

poisson-trace where RUN --store ROOT --event NAME [--event NAME ...]
                   [--by kind|step] [--at STEP ...] [--boot B] [--seed S]
                   [--svg FILE [--force]] [--json]

poisson-trace compare A B --store ROOT --event NAME [--event NAME ...] --max-mde-hr X
                     [--by kind|step] [--at STEP ...] [--alpha A] [--json]

poisson-trace fix-check OLD NEW --store ROOT --event NAME [--event NAME ...]
                       ( --failing-from RUN [--min-failures M] | --inputs all )
                       --max-mde X [--alpha A] [--seed S] [--top N] [--json]

poisson-trace changes A B --store ROOT --event NAME [--event NAME ...]
                     [--alpha A] [--top N] [--json]

poisson-trace import TOOL FILE [FILE ...] --store ROOT --run NAME [the reader's flags]
                    [--started ISO-8601] [--json]
```

- `--store` and `--event` may come from `trace.toml`, and then every command here takes them
  from it; every verb also takes `--config PATH`. Written out above, they are the flags you
  give when there is no config.
- Every run has a name. A run you have not named is named from its manifest: its target up
  to the first `/`, the day it started (UTC) and a letter in start order among the runs that
  would otherwise share the name, such as `tau2-airline 2026-09-15 a` (`[names] from` in
  `trace.toml` gives two other forms). A run written by
  `poisson-trace import` is named by the name it was imported under. `name` gives a run a
  name of yours, kept in `trace-names.toml` at the store's root, the one file Trace writes in
  a store; no run's own files change, and `name RUN --forget` takes the name back.
- Wherever a verb takes a run (`RUN`, `A`, `B`, `OLD`, `NEW`, `--failing-from`), it takes a
  name of yours, a name from the manifest, `latest` or `previous` (the newest and second
  newest complete runs), `latest:TARGET` or `previous:TARGET` (the same among one target's
  runs), `#N` (row N of `runs`; a shell needs it quoted, `"#3"`) or the full run id. A word
  that reaches no run, or two, is refused, never guessed; a part of an id is not a name.
- `runs` lists a store's runs, newest first: each complete run's number and name, its rows,
  how many of them failed for the `--event` names given, whether any row carries a trace
  (`where` and `compare` read traces; `fix-check` and `changes` do not need them), when it
  started (UTC) and its status. It lists the newest 50 complete runs; `--all` lists partial
  runs and older ones too.
- Every verb prints its verdict line first, the verdict word (`ok`, or one of *different*,
  *no significant difference* and *too small to tell*) and its sentence, then a blank line,
  the report, and a `next:` line with the command to run next. A `next:` command names runs
  by name and carries what you typed (`--store`, each `--event`, `--config`); what `trace.toml`
  gave it leaves out, since it reads the same file. What it lacks is a ceiling that neither you
  nor `trace.toml` gave, which is yours to choose. A report names each run by its name, and
  gives its id once for the record.
- With no `trace.toml` giving them, `--store` is required, and so is `--event` (on `runs` it
  is optional); there is no default store. `--event` is repeatable, and
  the union of the names is "died" for `where` and `compare` and "failed" for `fix-check`
  and `changes`. A name no stored row carries is refused, and the refusal lists the outcomes
  the runs do carry.
- `--json` prints the structure (`poisson-trace.runs/1`, `.where/1`, `.compare/1`,
  `.fix-check/1`, `.changes/1`, `.init/1` or `.doctor/1`) and nothing else. It opens with `schema`, `verdict` and
  `sentence`, the verdict line's two parts, ends with `next`, and carries `run_name` beside
  each `run_id`. It is byte-identical across invocations on equal inputs.
- Options may come before or after the verb. An option cut short (`--ev` for `--event`) is
  refused rather than guessed.
- A refusal or a mistake in the command line is one line on stderr that starts `error:`, and
  nothing on stdout; where there is a command that moves you on (the listing of the store's
  runs, the verb's help, the install line), it follows on a line of its own, `  next:`.
  `--help` on the command and on each verb gives a description, every option with its
  default and an example; `--version` prints the versions of Trace, Prove and Python.
  `python -m poisson_trace` is the same command.
- Exit codes, the same in every Poisson Labs tool ([`docs/cli-look.md`](docs/cli-look.md)):
  0 the report is printed, whatever it says, *too small to tell* included; 1 refused, nothing
  written; 2 the command line is wrong; 3 a failure after work started, or an unexpected one;
  4 a check you asked for failed (`doctor`, not ready); 130 interrupted (Ctrl-C prints a
  `stopped` line, as one JSON document under `--json`).
- An unexpected failure prints one line naming `~/.cache/poisson-trace/errors.log`, where the
  details are added; `--debug` prints them on stderr too.

For `where` and `compare`:

- `--by kind` (the default) labels the step a run died at by the leaf span's kind (`llm`,
  `tool`, `retrieval`, `db`, `http`, `agent`, `other`); `--by step` labels it by the
  nearest declared step name.
- `--at STEP` adds a row reading the curve at that step; repeatable.
- `--svg FILE` writes the curve as an SVG, the one file `where` writes, and the line under
  the verdict line says so. A file that is already there is refused unless `--force` is given,
  and a folder that is not there or cannot be written is refused before any work.
- `--max-mde-hr` is the largest minimum detectable hazard ratio you will accept; it has no
  default, because the tool supplies no number of its own.

For `fix-check` and `changes`:

- An **input** is one config cell of a Prove sweep (one `config_hash`). On the tau2 runs
  below an input is a task; where a sweep crosses tasks with another setting, each (task,
  setting) cell is its own input.
- Exactly one of `--failing-from RUN` and `--inputs all` is required; there is no default,
  because which inputs are compared is the decision that makes the check honest.
  `--failing-from RUN` takes the inputs of RUN with at least `--min-failures` failed rows
  (default 1). RUN is the *selecting run*, and it must be neither OLD nor NEW: its failures
  on those inputs are there by selection, so both arms must be fresh re-runs. `--inputs all`
  takes every input either run carries, with no selection.
- `--max-mde` is the largest detection limit you will accept, as a fraction of failure share
  (`0.20` is twenty points). It is required and has no default.
- `--seed` seeds the by-input reading's draws when more than 14 inputs moved. `--top N`
  (default 10) bounds the table of inputs in the markdown; every flagged input prints
  whatever `--top` says, and the JSON lists every input.
- Neither verb reads a trace, a seed or a replicate index. They work on a run stored with no
  capture, and repeat runs of one input are read as separate draws, never as replays.

`where` prints the survival curve over step index with a 95% band (Kaplan–Meier,
Greenwood), the median step, the deaths by kind of step with a bootstrap band on each
(Aalen–Johansen), the counts of runs ended, timed out, capped and excluded, and a closing
block of what the curve cannot say.

`compare` prints the log-rank test stratified by config cell over the cells both runs
carry, the direction, the minimum detectable hazard ratio (Schoenfeld, 80% power) and one
of three lines: *different*, *no significant difference*, or *too small to tell*.

`fix-check` prints the control (how often the old version failed when re-run on the same
inputs, beside the new), the exact conditional Cochran–Mantel–Haenszel test stratified by
input, the difference in points with Sato's interval, a second reading by input that does
not assume repeats are independent, how consistent the failures were, the smallest drop and
rise in failure share it could have detected, one of the three lines, and the per-input
table of `changes`.

`changes` prints Fisher's exact test per input with Benjamini–Hochberg across the inputs,
the inputs flagged, and what the design could not have flagged.

### How a run is placed (`where`, `compare`)

A step is a leaf span (a span that is the parent of no other span), in `(start_ns,
span_id)` order; a run with `L` leaves ran `L` steps. Each stored row lands as one of:

| Placement | Rule, in this order | On the curve |
|---|---|---|
| excluded | no trace; an unreadable trace; zero leaves; no outcome and not a timeout | not placed; counted by reason |
| timed out | no outcome and Prove's timeout mark | censored at `L` |
| capped | the trace holds at least `capture.max_spans` spans | censored at `L` |
| died | the outcome is one of the `--event` names | died at `L`; cause = kind of leaf `L` |
| ended | any other outcome | censored at `L` |

Timed out and capped are checked before died: a run whose trace stops early has an unknown
death step even if its outcome says it failed.

### How a row is counted (`fix-check`, `changes`)

| Row or input | Rule | Where it shows |
|---|---|---|
| row whose outcome is an event | failed | both counts |
| row with any other outcome | did not fail | the runs count |
| row with no outcome and Prove's timeout mark | left out | header, *timed out*, per arm |
| row with no outcome otherwise | left out | header, *no outcome*, per arm |
| input selected but absent from OLD | left out | *not re-run on the old version* |
| input present in OLD, absent from NEW | left out | *not re-run on the new version* |
| input whose every row in an arm has no outcome | left out | *no outcome on the old / new version* |

Reasons are tried in that order and an input is counted under the first that applies. Rows
with no outcome are left out of numerator and denominator, as Prove's `diff` does. This is
the one rule that can hide a real effect (a new version that times out where the old one
failed), so the header prints the counts per arm.

## Checking a change: the recipe

Trace runs nothing; the re-runs are Prove sweeps.

1. A Prove run S of the old version has failures. `--failing-from S` will name its failing
   inputs.
2. Write one sweep file holding those inputs and a number of repeats. `poisson-trace
   fix-check` on any earlier pair prints the number under *Guidance*.
3. Run that sweep with Prove twice, once per version, side by side, not the old version
   from last week.
4. `poisson-trace fix-check OLD NEW --store ROOT --event NAME --failing-from S --max-mde X`.

## Worked examples

The seven stores under `tests/fixtures/` are real runs stored by Prove on our machines.
Four were copied with their observation bodies removed, one was copied whole (it was stored
with no capture) and two are outcome-only copies (`tests/fixtures/PROVENANCE.md` has the
sources, the recipes and the digests). Nothing Trace reads was removed, so every block below
is byte-for-byte what the original stores give, and what a clean clone prints.

### One run: the OpenAI customer-service demo, recorded

`cs_agents/record` is the OpenAI customer-service agent demo recorded on gpt-4.1-mini: 24
episodes, spans nested three deep (turn > workflow > generation, with guardrail agents
beside them), four failure outcomes.

<!-- command -->
```
poisson-trace where "cs_agents 2026-09-25 a" --store tests/fixtures/cs \
  --event forbidden_action --event unresolved --event max_turns --event app_error \
  --at 20 --at 40 --svg docs/figures/cs-record.svg --force
```

<!-- output exit=0 -->
```
ok  7 of 24 placed episodes died, 4 at a model call and 3 at an agent step; median step 50
  wrote  docs/figures/cs-record.svg

# Poisson Trace · where runs die · cs_agents 2026-09-25 a

## Run

- run: cs_agents 2026-09-25 a (20260925T234602Z-3ea0) · target: cs_agents/record · t_unit: turns · status: complete · no cap
- Prove's tally: rows 24 · with outcome 24 · no outcome 0 · timed out 0 · infra 0 · other 0
- placement: placed 24 · died 7 · ended 17 · timed out 0 · capped 0 · excluded 0
- events: app_error, forbidden_action, max_turns, unresolved

## Survival over step index

Kaplan–Meier over leaf-span index; band: Greenwood, plain, 95%.

| step | at risk | died | S | 95% band |
|---|---|---|---|---|
| 24 | 18 | 1 | 0.944 | 0.839 – 1.000 |
| 30 | 15 | 1 | 0.881 | 0.727 – 1.000 |
| 33 | 11 | 1 | 0.801 | 0.596 – 1.000 |
| 35 | 10 | 1 | 0.721 | 0.484 – 0.959 |
| 48 | 5 | 1 | 0.577 | 0.261 – 0.893 |
| 50 | 4 | 1 | 0.433 | 0.092 – 0.774 |
| 58 | 2 | 1 | 0.216 | 0.000 – 0.561 |

median step: 50
S(20) = 1.000 (1.000 – 1.000)
S(40) = 0.721 (0.484 – 0.959)

## Where they die, by kind of step

Aalen–Johansen cumulative incidence; band: bootstrap 95%, B = 1,000, seed = 0.

| kind | deaths | F at step 58 | 95% band |
|---|---|---|---|
| llm | 4 | 0.343 | 0.056 – 0.679 |
| agent | 3 | 0.441 | 0.000 – 0.871 |

sum of F = 1 − S = 0.784 (1 − 0.216)

## What this cannot say

- The step index is where the run stopped, not why. A run that died at a tool step may have gone wrong three steps earlier.
- Timed-out and capped runs are censored at their last recorded step. If they would have died soon after, the curve is optimistic by that much; the header counts them.
- Excluded rows are not on the curve; the header counts them by reason.
- On one run, this is a description. Only a comparison of two stored runs on the same cells says whether anything moved, and only within what it could not have detected.

next: poisson-trace fix-check --help
```

Seven of 24 runs died, four at a model call and three at a guardrail agent. The Greenwood
band at step 40 spans a quarter of the axis and the bootstrap bands on the two kinds span
most of `[0, 1]`: 24 episodes is a description, and the report says so.

[`docs/figures/cs-record.svg`](docs/figures/cs-record.svg) is the `--svg` output of that
command (`--force` because the clone already holds it).

### Two runs: the same agent twice, nothing changed

`tests/fixtures/tau2` holds two runs of `tau2-airline/gpt-4.1-mini-2025-04-14@v0`: 50
tasks × 4 replicates each, the same seeds, ten minutes apart, nothing changed between them.
On the first, `where` places 200 runs, 110 died and 90 ended; steps run from 6 to 44 with a
median step of 22; `S(10)`, `S(20)` and `S(30)` are 0.964, 0.599 and 0.163
([`docs/figures/tau2-a.svg`](docs/figures/tau2-a.svg)). Comparing the two as a before and
an after, with a ceiling of 1.3 on the minimum detectable hazard ratio:

<!-- command -->
```
poisson-trace compare "tau2-airline 2026-09-15 a" "tau2-airline 2026-09-15 b" \
  --store tests/fixtures/tau2 --event unsolved --max-mde-hr 1.3 --at 10 --at 20 --at 30
```

<!-- output exit=0 -->
```
too small to tell  could not have detected a hazard ratio below 1.457, and 1.3 was asked for

# Poisson Trace · compare · tau2-airline 2026-09-15 a (before) and tau2-airline 2026-09-15 b (after)

## Run A (before)

- run: tau2-airline 2026-09-15 a (20260915T210140Z-4847) · target: tau2-airline/gpt-4.1-mini-2025-04-14@v0 · t_unit: steps · status: complete · cap: 200 spans
- Prove's tally: rows 200 · with outcome 200 · no outcome 0 · timed out 0 · infra 0 · other 0
- placement: placed 200 · died 110 · ended 90 · timed out 0 · capped 0 · excluded 0
- events: unsolved

## Run B (after)

- run: tau2-airline 2026-09-15 b (20260915T211148Z-965d) · target: tau2-airline/gpt-4.1-mini-2025-04-14@v0 · t_unit: steps · status: complete · cap: 200 spans
- Prove's tally: rows 200 · with outcome 200 · no outcome 0 · timed out 0 · infra 0 · other 0
- placement: placed 200 · died 112 · ended 88 · timed out 0 · capped 0 · excluded 0
- events: unsolved

## Comparison

log-rank, stratified by config cell over 50 common cells (excluded: 0 in A only, 0 in B only), unpaired (the runs share a run_salt); α = 0.05.

| arm | placed | died | observed | expected |
|---|---|---|---|---|
| A (before) | 200 | 110 | 110 | 113.805 |
| B (after) | 200 | 112 | 112 | 108.195 |

statistic: χ² = 0.411 on 1 d.f., variance 35.223, p = 0.521
direction: runs die later in A (before) than in B (after): runs die earlier in B
S_B(10) − S_A(10) = 0.005 (-0.031 – 0.041, Wald 95%)
S_B(20) − S_A(20) = -0.050 (-0.164 – 0.065, Wald 95%)
S_B(30) − S_A(30) = 0.064 (-0.048 – 0.176, Wald 95%)

### Per kind

cause-specific log-rank, stratified by config cell, deaths of other kinds censored at their step; Benjamini–Hochberg at q = 0.05.

| kind | deaths A | deaths B | χ² | p | q | could not have detected a hazard ratio below |
|---|---|---|---|---|---|---|
| llm | 110 | 112 | 0.411 | 0.521 | 0.521 | 1.457 |

could not have detected a hazard ratio below 1.457 (Schoenfeld, 80% power, α = 0.05, 222 deaths over the common cells, allocation 0.500)

**too small to tell: could not have detected a hazard ratio below 1.457, and 1.3 was asked for**

## Guidance

- deaths: 457 would bring the detectable hazard ratio to 1.3; this design has 222
- runs: 824 placed runs at the present share of deaths, which is 103 inputs at the present repeats, or 9 repeats per arm on these 50; this design has 400 placed runs
- ceiling: --max-mde-hr 1.457 accepts this design as it stands

These numbers assume the share of runs that die holds in the next runs, and that new inputs resemble the present ones. It is a guide to the next design and not a promise about it: a design built to the number has an expected limit at the ceiling asked for, so about half the time its own limit will land a little above.

For the share of runs that fail, input by input, and the inputs that changed: poisson-trace fix-check A B --inputs all

## What this cannot say

- The step index is where the run stopped, not why. A run that died at a tool step may have gone wrong three steps earlier.
- Timed-out and capped runs are censored at their last recorded step. If they would have died soon after, the curve is optimistic by that much; the header counts them.
- Excluded rows are not on the curve; the header counts them by reason.
- On one run, this is a description. Only a comparison of two stored runs on the same cells says whether anything moved, and only within what it could not have detected.

next: poisson-trace fix-check "tau2-airline 2026-09-15 a" "tau2-airline 2026-09-15 b" --store tests/fixtures/tau2 --event unsolved --inputs all
```

It exits 0, as every printed result does, and the guidance says what would settle it: 457
deaths, which is 824 placed runs, 103 inputs at 4 repeats or 9 repeats per arm on these 50.
With the ceiling the report offers,

<!-- command -->
```
poisson-trace compare "tau2-airline 2026-09-15 a" "tau2-airline 2026-09-15 b" \
  --store tests/fixtures/tau2 --event unsolved --max-mde-hr 1.457
```

the same numbers end

<!-- excerpt exit=0 -->
```
**no significant difference (p = 0.521); could not have detected a hazard ratio below 1.457**
```

with no guidance block. That pair of lines is the point: the same agent run twice, 400
episodes, and the design could still not have seen a 40% change in the hazard.

### A real before and after: the patched pilot

`tests/fixtures/tau2` also holds a real change: the same agent with a guardrail patch
(`tau2_pilot.rollout:rollout_patched`), run once on tasks 0 to 9 and stored with no capture.
Ten runs is the size of check teams make. The tau2 pair gives the design its other two
runs: the first (`tau2-airline 2026-09-15 a`) selects the inputs that failed, and the second
(`tau2-airline 2026-09-15 b`) is the old version re-run fresh on them. The patched pilot is
the store's newest run, so it is also `latest`, and the second is `previous`.

<!-- command -->
```
poisson-trace fix-check previous latest --store tests/fixtures/tau2 --event unsolved \
  --failing-from "tau2-airline 2026-09-15 a" --max-mde 0.20
```

<!-- output exit=0 -->
```
too small to tell  could not have detected a drop in failure share below 64.3 points, and 20 was asked for

# Poisson Trace · fix check · tau2-airline 2026-09-15 b (old) and tau2-airline 2026-09-17 a (new)

## Runs

- old: tau2-airline 2026-09-15 b (20260915T211148Z-965d) · target: tau2-airline/gpt-4.1-mini-2025-04-14@v0 · status: complete · started: 2026-09-15T21:11:49.277633Z · declared repeats: 4
- Prove's tally (old): rows 200 · with outcome 200 · no outcome 0 · timed out 0 · infra 0 · other 0
- new: tau2-airline 2026-09-17 a (20260917T140219Z-2b2d) · target: tau2-airline/gpt-4.1-mini-2025-04-14@v0 · status: complete · started: 2026-09-17T14:02:21.184575Z · declared repeats: 1
- Prove's tally (new): rows 10 · with outcome 10 · no outcome 0 · timed out 0 · infra 0 · other 0
- the two runs started 40 h 50 min apart
- events: unsolved
- inputs: inputs that failed at least 1 time in tau2-airline 2026-09-15 a · selected 37 · compared 6 · left out 31 (not re-run on the new version 31)
- rows used: old 24 (timed out 0, no outcome 0) · new 6 (timed out 0, no outcome 0)
- inputs short of the declared repeats: old 0 · new 0
- inputs with mixed outcomes across their repeats: old 4 · new 0

## The control

The old version, re-run on the same inputs with nothing changed.

| version | runs | failed | failure share | did not fail on re-run |
|---|---|---|---|---|
| old | 24 | 18 | 75.0% | 25.0% |
| new | 6 | 3 | 50.0% | 50.0% |

Re-running these inputs and counting the runs that did not fail would have read 25.0% on the old version, where nothing changed.

## The comparison

exact conditional Cochran-Mantel-Haenszel test, stratified by input over 6 inputs (4 informative), two-sided; α = 0.05.

new failures: observed 3, expected 4.200, variance 0.800; p = 0.269
difference: -25.0 points, new minus old (-60.1 to +10.1; Mantel-Haenszel weights; interval: Sato variance, large-sample, 95%)
by input: p = 0.375 (sign-flip over the 4 inputs that moved, exact); not part of the line below

## Consistency

failure share 0.700 · fails again 0.762 · κ 0.206 · within-input variance 0.167 against pooled 0.210
a comparison that ignored the inputs would need 1/(1 − κ) = 1.26 times the runs

## What it could not have detected

proportional change on every input, 80% power, α = 0.05, continuity-corrected normal approximation to the stratified statistic.

- a drop in failure share: could not have detected one below 64.3 points
- a rise in failure share: no limit; even every run failing, a rise of 30.0 points, would have been detected less than four times in five

**too small to tell: could not have detected a drop in failure share below 64.3 points, and 20 was asked for**

## Guidance

- repeats: 16 per arm on these 6 inputs would bring the limit to 20 points
- inputs: 55 inputs like these, at the present repeats, would do the same
- ceiling: --max-mde 0.6430 accepts this design as it stands

These numbers assume the next runs fail at the rates these did, input by input, and that new inputs resemble the present ones: for failing inputs chosen by a rule, chosen by the same rule. It is a guide to the next design and not a promise about it: a design built to the number has an expected limit at the ceiling asked for, so about half the time its own limit will land a little above.

## Inputs that changed

Fisher's exact test per input, Benjamini-Hochberg at q = 0.05 over 6 inputs; 0 flagged.

| input | old failed/runs | new failed/runs | change | p | q | flag | could not have detected a rise below |
|---|---|---|---|---|---|---|---|
| {"task_id":"2"} | 3/4 | 0/1 | -75.0 points | 0.400 | 1.000 | – | 25.0 points |
| {"task_id":"5"} | 3/4 | 0/1 | -75.0 points | 0.400 | 1.000 | – | 25.0 points |
| {"task_id":"7"} | 4/4 | 1/1 | 0.0 points | 1.000 | 1.000 | – | 12.5 points |
| {"task_id":"9"} | 4/4 | 1/1 | 0.0 points | 1.000 | 1.000 | – | 12.5 points |
| {"task_id":"1"} | 3/4 | 1/1 | +25.0 points | 1.000 | 1.000 | – | 25.0 points |
| {"task_id":"3"} | 1/4 | 0/1 | -25.0 points | 1.000 | 1.000 | – | 75.0 points |

A lone changed input is flagged only if its p is below α / M = 0.00833, and the smallest p an input of this design can give is 0.2: no input can be flagged whatever happens; a lone complete flip needs 5 repeats per arm. An input with no flag is not an input that did not change.

## What this cannot say

- A difference between two stored runs is a difference between the runs. The version, the provider and the hour changed together unless the two were run side by side, and this test cannot separate them.
- Repeat runs of one input are read as separate draws and never as replays: a served model is not bit-identical on repeat, so nothing here matches a run of the old version to a run of the new by seed.
- If repeat runs of one input are near copies of one another, the run-level test overstates its confidence. The by-input line does not depend on that.
- Rows with no outcome are left out of both arms and counted in the header. A new version that times out where the old one failed does not show as a failure here.
- Trace reads the runs it is given. If the inputs were chosen by the old arm's own outcomes, or the more favourable of several runs was handed over, the confidence printed does not hold.
- The detection limit and the run counts are computed from these runs' own failure rates, which are estimates. They are a guide to the next design, not a promise about it.

next: run 16 repeats per arm on these 6 inputs, then poisson-trace fix-check again
```

Counting re-runs reads "3 of 6 failing inputs now succeed". The control says a
quarter of the old version's runs on those inputs did too, with nothing changed, and the
design cannot tell the patch from that: it could not have detected a drop smaller than 64.3
points, and the interval runs from a 60.1-point drop to a 10.1-point rise. The guidance
says what would settle a 20-point question: 16 repeats per arm on these 6 inputs, or 55
inputs like these. The pilot was ten runs and was never meant to settle anything.

Naming the selecting run as the old arm is refused, in one line on stderr and with exit 1:

<!-- command -->
```
poisson-trace fix-check previous latest --store tests/fixtures/tau2 --event unsolved \
  --failing-from "tau2-airline 2026-09-15 b" --max-mde 0.20
```

<!-- output exit=1 -->
```
error: the selecting run "tau2-airline 2026-09-15 b" (20260915T211148Z-965d) is also the old arm; both arms must be fresh re-runs, because the selecting run's failures on these inputs are there by selection
```

### The inputs that changed: HumanEval/129

`tests/fixtures/humaneval` holds two runs of one HumanEval agent (gpt-4o-mini): 164 problems
at temperatures 0.0 and 0.7, so 328 inputs, × 32 repeats each, 56 minutes apart, nothing
changed by us between them.

<!-- command -->
```
poisson-trace changes "golden-pilot 2026-09-05 a" "golden-pilot 2026-09-05 b" \
  --store tests/fixtures/humaneval --event failed_assertion --event crashed --top 2
```

<!-- output exit=0 -->
```
ok  2 of 328 inputs changed: task_id HumanEval/129 at temperature 0.7 failed more in B; task_id HumanEval/129 at temperature 0.0 failed more in B

# Poisson Trace · changes · golden-pilot 2026-09-05 a (A) and golden-pilot 2026-09-05 b (B)

## Runs

- A: golden-pilot 2026-09-05 a (20260905T185407Z-0313) · target: golden-pilot/gpt-4o-mini-2024-07-18@v0 · status: complete · started: 2026-09-05T18:54:08.373078Z · declared repeats: 32
- Prove's tally (A): rows 10,496 · with outcome 10,496 · no outcome 0 · timed out 0 · infra 0 · other 0
- B: golden-pilot 2026-09-05 b (20260905T195009Z-18ac) · target: golden-pilot/gpt-4o-mini-2024-07-18@v0 · status: complete · started: 2026-09-05T19:50:10.199374Z · declared repeats: 32
- Prove's tally (B): rows 10,496 · with outcome 10,496 · no outcome 0 · timed out 0 · infra 0 · other 0
- the two runs started 56 min apart
- events: crashed, failed_assertion
- inputs: A carries 328, B carries 328 · compared 328, each with an outcome in both runs · in A only 0 · in B only 0

## Inputs that changed

Fisher's exact test per input, Benjamini-Hochberg at q = 0.05 over 328 inputs; 2 flagged.

| input | A failed/runs | B failed/runs | change | p | q | flag | could not have detected a rise below |
|---|---|---|---|---|---|---|---|
| {"task_id":"HumanEval/129","temperature":0.7} | 12/32 | 32/32 | +62.5 points | 2.30e-08 | 7.55e-06 | failed more in B | 34.2 points |
| {"task_id":"HumanEval/129","temperature":0.0} | 20/32 | 32/32 | +37.5 points | 1.38e-04 | 0.023 | failed more in B | 28.9 points |

2 of 328 inputs shown, by ascending p; --json lists all.

A lone changed input is flagged only if its p is below α / M = 0.000152, and the smallest p an input of this design can give is 1.09e-18: a lone change can be flagged; a lone complete flip needs 9 repeats per arm. An input with no flag is not an input that did not change.

## What this cannot say

- A difference between two stored runs is a difference between the runs. The version, the provider and the hour changed together unless the two were run side by side, and this test cannot separate them.
- Repeat runs of one input are read as separate draws and never as replays: a served model is not bit-identical on repeat, so nothing here matches a run of the old version to a run of the new by seed.
- If repeat runs of one input are near copies of one another, the run-level test overstates its confidence. The by-input line does not depend on that.
- Rows with no outcome are left out of both arms and counted in the header. A new version that times out where the old one failed does not show as a failure here.
- Trace reads the runs it is given. If the inputs were chosen by the old arm's own outcomes, or the more favourable of several runs was handed over, the confidence printed does not hold.
- The detection limit and the run counts are computed from these runs' own failure rates, which are estimates. They are a guide to the next design, not a promise about it.

next: poisson-trace fix-check "golden-pilot 2026-09-05 a" "golden-pilot 2026-09-05 b" --store tests/fixtures/humaneval --event failed_assertion --event crashed --inputs all
```

Two of 328 inputs are flagged, both HumanEval/129, and nothing else. Prove's own `diff`
with `fisher_bh`, on the event `failed_assertion`, flags the same two cells with the same p
and q. One problem broke between the two runs, on an agent nobody touched. `fix-check` on the same pair reads the whole of it:

<!-- command -->
```
poisson-trace fix-check "golden-pilot 2026-09-05 a" "golden-pilot 2026-09-05 b" \
  --store tests/fixtures/humaneval --event failed_assertion --event crashed --inputs all \
  --max-mde 0.05
```

<!-- excerpt exit=0 -->
```
## The comparison

exact conditional Cochran-Mantel-Haenszel test, stratified by input over 328 inputs (58 informative), two-sided; α = 0.05.

new failures: observed 1,387, expected 1,362.500, variance 131.139; p = 0.036
difference: +0.47 points, new minus old (+0.04 to +0.90; Mantel-Haenszel weights; interval: Sato variance, large-sample, 95%)
by input: p = 0.127 (sign-flip over the 47 inputs that moved, 100,000 draws, seed = 0); not part of the line below
```

<!-- excerpt exit=0 -->
```
**different: the new version failed more on these inputs (exact Cochran-Mantel-Haenszel, stratified by input, p = 0.036)**
```

The runs differ (p = 0.036), the inputs did not move as a body (by input, p = 0.127), and
the flags name the one problem that did. That is a true statement about two runs and a false
one about two versions, which is why the report's first closing sentence is that a
difference between two stored runs is a difference between the runs, and why the recipe says
side by side.

### Guidance: what would settle it

The tau2 pair again, nothing changed, this time asking whether the share of runs that fail
moved by 10 points:

<!-- command -->
```
poisson-trace fix-check "tau2-airline 2026-09-15 a" "tau2-airline 2026-09-15 b" \
  --store tests/fixtures/tau2 --event unsolved --inputs all --max-mde 0.10
```

<!-- excerpt exit=0 -->
```
## Consistency

failure share 0.555 · fails again 0.792 · κ 0.531 · within-input variance 0.116 against pooled 0.247
a comparison that ignored the inputs would need 1/(1 − κ) = 2.13 times the runs

## What it could not have detected

proportional change on every input, 80% power, α = 0.05, continuity-corrected normal approximation to the stratified statistic.

- a drop in failure share: could not have detected one below 11.1 points
- a rise in failure share: could not have detected one below 10.8 points

**too small to tell: could not have detected a drop in failure share below 11.1 points, and 10 was asked for**

## Guidance

- repeats: 5 per arm on these 50 inputs would bring the limit to 10 points
- inputs: 61 inputs like these, at the present repeats, would do the same
- ceiling: --max-mde 0.1109 accepts this design as it stands

These numbers assume the next runs fail at the rates these did, input by input, and that new inputs resemble the present ones: for failing inputs chosen by a rule, chosen by the same rule. It is a guide to the next design and not a promise about it: a design built to the number has an expected limit at the ceiling asked for, so about half the time its own limit will land a little above.
```

Failures on these tasks are consistent (an input that failed once fails again 79% of the
time), so comparing inside each input needs fewer than half the runs a pooled comparison
would. Even so, 200 runs per arm could not have detected a drop smaller than 11.1 points.
With `--max-mde 0.1109`, the ceiling the report offers, the same numbers read *no
significant difference*. The per-input table of the same report ends

<!-- excerpt exit=0 -->
```
A lone changed input is flagged only if its p is below α / M = 0.001, and the smallest p an input of this design can give is 0.0286: a lone changed input cannot be flagged; at least 29 inputs would have to flip completely together; a lone complete flip needs 7 repeats per arm. An input with no flag is not an input that did not change.
```

so on this design no change to a single task could have been flagged at all.

## How the fix check decides

- **The test** is the exact conditional Cochran–Mantel–Haenszel test, stratified by input.
  Each input is a 2 × 2 table (version × failed or not). Given each input's total failures,
  the new version's count on it is hypergeometric under the null, whatever that input's
  failure rate; the distribution of the sum is computed in full and the p-value is exact,
  two-sided, with no normal approximation. An input that always fails, or never does, adds
  nothing: no signal and no noise. With one input it is Fisher's exact test; with one run
  per arm per input it is the exact McNemar test.
- **The difference** is the Mantel–Haenszel risk difference in points, new minus old, with
  Sato's variance for the interval. The interval is large-sample and labelled so. The line
  follows the test, never the interval, and the report says so when the two disagree.
- **The by-input reading** treats each input as one observation and flips its sign. It does
  not need repeat runs to be independent, so it is the check on the case where repeats are
  near copies of one another. It prints beside the test and has no part in the line.
- **The detection limit** is the smallest proportional drop in every input's failure rate
  that the test would have detected four times in five, stated in points of failure share.
  `--max-mde` gates on the drop; the rise prints beside it.
- **The flags** are Fisher's exact test per input, then Benjamini–Hochberg across all the
  inputs compared, number for number what Prove's `diff` does with `fisher_bh`.
- **The guidance** is computed with the function that stated the limit, so the number it
  suggests cannot drift from the number that refused the design, and the ceiling it offers
  is accepted when handed back.

## What this cannot say

`where` and `compare`:

- The step index is where the run stopped, not why. A run that died at a tool step may
  have gone wrong three steps earlier.
- Timed-out and capped runs are censored at their last recorded step. If they would have
  died soon after, the curve is optimistic by that much; the header counts them.
- Excluded rows are not on the curve; the header counts them by reason.
- On one run, this is a description. Only a comparison of two stored runs on the same
  cells says whether anything moved, and only within what it could not have detected.

`fix-check` and `changes`:

- A difference between two stored runs is a difference between the runs. The version, the
  provider and the hour changed together unless the two were run side by side, and this
  test cannot separate them.
- Repeat runs of one input are read as separate draws and never as replays: a served model
  is not bit-identical on repeat, so nothing here matches a run of the old version to a run
  of the new by seed.
- If repeat runs of one input are near copies of one another, the run-level test overstates
  its confidence. The by-input line does not depend on that.
- Rows with no outcome are left out of both arms and counted in the header. A new version
  that times out where the old one failed does not show as a failure here.
- Trace reads the runs it is given. If the inputs were chosen by the old arm's own outcomes,
  or the more favourable of several runs was handed over, the confidence printed does not
  hold.
- The detection limit and the run counts are computed from these runs' own failure rates,
  which are estimates. They are a guide to the next design, not a promise about it.

More limits. `compare` is unpaired: the two tau2 runs share their seeds, but the log-rank
does not use that fact (the header says *unpaired* whenever the runs share a `run_salt`),
and `fix-check` matches nothing by seed on purpose. The per-kind bands of `where` come from a
seeded bootstrap (`--boot 1000 --seed 0` by default), not a closed-form variance. Looking
after every few runs and stopping when the line reads well is not covered by the stated
confidence, and no report can see it. No store among the fixtures is a changed agent at a
size that reads *different: the new version failed less*; on stored runs that line is
exercised on synthetic ones only. Among the fixtures it is read through the Ragas import
alone: on a published pair of score tables, a base model and the same model fine-tuned, on
two of its three scores (`docs/integrations/ragas.md`), and on the memory pair at recall
(`tests/ingest/test_ragas_fixture.py`).

## Results from other tools

`poisson-trace import` reads the result files another tool already wrote and writes them as
one new run of a store in Prove's format, one import per version. `fix-check` and `changes`
then read the two runs like any stored run; `where` and `compare` read traces, which an
imported run has none of, and say so. You declare what counts as a failure (a metric's cut
with its side, or the values of an outcome column) and what identifies a case, where the
tool's files do not say. No prompt or answer text is kept, with one exception that is yours
to choose: the Ragas and table readers keep the value of the column you name as the case, as
written when it is short, so name an id column and not the question. `poisson-trace-import`,
its earlier name, is the same command and stays.

- [DeepEval](docs/integrations/deepeval.md): DeepEval's saved test runs, one metric per
  import, with a worked example on the HumanEval pair written through DeepEval.
- [Ragas](docs/integrations/ragas.md): the score table saved from Ragas, as CSV, JSON Lines,
  JSON or Parquet, one score column per import, with a worked example on a published base
  and fine-tuned pair and one on a score Ragas could not give.
- [Tables](docs/integrations/table.md): any table of results a tool or a script saved, in the
  same formats, read by an outcome column or by a score at a cut, with a worked example on
  this repository's HumanEval pair saved as CSV.
- [JUnit](docs/integrations/junit.md): the JUnit XML reports pytest and every CI system
  write, a failure or an error as missed, with a worked example on pytest's reports of a suite
  run against the same HumanEval pair.

## What Trace does not read

Trace reads runs Prove stored. Prove already converts OpenTelemetry spans and LiteLLM logs
into its schema, so an app captured under Prove is already in. Reading a LangSmith export
or a bare OTLP file is the next slice, and it will say what the positioning says:
ingested logs show where failures happened at whatever rate the traffic produced; only a
controlled re-run on the same inputs says whether a change moved anything.

## Development

```
pip install -e '.[dev]'
pip install git+https://github.com/poisson-labs/prove
python -m pytest
ruff check .
mypy --strict src
```

The suite holds 1,475 tests: 100 for `where` and `compare`, 143 for `fix-check` and `changes`
(3 of them its display rules), 124 for the import and its DeepEval reader, 80 for
its Ragas reader, 186 that hold both commands to the shared command-line look
([`docs/cli-look.md`](docs/cli-look.md)): the exit codes, the `error:` lines, the help and
`--version`, options before or after the verb, the ASCII fallback, a closed pipe and plain
words; 316 for names and runs: the names file, the name every run has, the words a verb
takes for a run, `runs` and `name`, the verdict line and `next:`, and the import's run names;
276 for the setup: `init`, `trace.toml` and how every verb reads it, the two further forms
of a run's name, `doctor`, and the readers' `looks_like`; and 250 for `import` under the main
command, its table and JUnit readers, `init`'s part in them, and runs with no traces.
Four of the 1,475 run DeepEval or Ragas itself, installed from PyPI, and are left out
unless asked for (`python -m pytest -m lane_j`). The figures the tests check against come
from lifelines, scipy, full enumeration in exact fractions, and Prove's own estimators. `tests/fixtures/SHA256SUMS` checks
the fixtures (`cd tests/fixtures && shasum -a 256 -c SHA256SUMS`).

## Licence

MIT. See `LICENSE` and `NOTICE`.

## Citation

```bibtex
@software{poisson_trace,
  author = {Poisson Labs},
  title = {Poisson Trace: where in the workflow runs die},
  year = {2026},
  url = {https://github.com/poisson-labs/trace}
}
```
