# Poisson Trace

Where in the workflow do your agent's runs die, and did your change make them fail less?

Trace answers both from results you already have: in LangSmith, Braintrust or Weave, in the
files your evaluation tool wrote, or in runs stored by
[Prove](https://github.com/poisson-labs/prove). It tells you:

- **where runs die**: at which step of the workflow, and at which kind of step, such as a
  model call or a tool call;
- **which inputs got worse** and **which kinds of failure grew**, between an old version and
  a new one;
- **whether it is real or noise**: one of *different*, *no significant difference* and
  *too small to tell*, and under the last, how many more tries would settle it.

    pip install poisson-trace
    poisson-trace init
    poisson-trace fix-check previous latest --inputs all --max-mde 0.2

- `poisson-trace init` finds the results in your folder, asks which outcomes count as a
  failure, and writes `trace.toml`. It runs nothing.
- `poisson-trace fix-check previous latest` compares your two newest runs, the old version
  beside the new one. `--inputs all` takes every input both runs hold, and `--max-mde 0.2`
  asks that the check be able to see a drop of 20 points in the share of tries that fail.
- `poisson-trace where latest` shows where the tries of the newest run die.
- `poisson-trace import` reads in results another tool holds: an experiment in LangSmith,
  Braintrust or Weave by its address, or a result file.
- `poisson-trace` on its own opens the terminal app: your runs, a comparison, a fix check and
  the verdict, a screen each.
- `poisson-trace init --agent` writes a setup file that your own coding agent follows to set
  Trace up, for you to review.

Trace finds the step where runs fail and sorts each failure into one of thirteen types, such
as a timeout, a tool error or a wrong answer. More about it is on the Trace page at
[poissonlabs.ai/tools/trace](https://poissonlabs.ai/tools/trace/).

Python 3.11 to 3.13 on macOS and Linux. Trace runs nothing, captures nothing and sends nothing.

---

## Install

<!-- skip reason="installs from the package index, which the docs check does not reach" -->
```
pip install poisson-trace
```

That one line is all Trace needs. It brings Prove, the `poisson-prove` package that Trace
reads stored runs through, at version 0.4.0 or later. `poisson-trace --version`
prints the versions of Trace, Prove and Python, and `poisson-trace doctor` says whether the
setup is ready.

The examples on this page, and on every page under `docs/`, read example files that are in
the repository and not in the installed package. To run them as written, work in a clone of
the repository:

<!-- skip reason="fetches the repository, which the docs check does not reach" -->
```
git clone https://github.com/poisson-labs/trace
cd trace
```

Every command shown on these pages is run, and what a page says it printed is checked
against what it printed, each time the pages change.

## This is a pre-release

The package on PyPI today is Poisson Trace `0.1.0a1`, a pre-release, and this section stands
only until 0.1.0 is released. pip takes a pre-release only when you name its version. The
plain line above still gets `0.0.1`, a placeholder that does not run. Name the version:

<!-- skip reason="installs from the package index, which the docs check does not reach" -->
```
python3 -m venv trace-env
. trace-env/bin/activate
pip install poisson-trace==0.1.0a1
```

`poisson-trace --version` then prints the version it installed.

Trace needs Python 3.11, 3.12 or 3.13, and the `python3` that macOS ships is older. If
`python3 --version` prints a version below Python 3.11, type `python3.11`, `python3.12` or
`python3.13` in the first line, whichever your machine has.

The example files and every page this one names are also in the source archive, which is on
PyPI beside the package. To work inside it in place of a clone, fetch it:

<!-- skip reason="fetches from the package index, which the docs check does not reach" -->
```
pip download --no-deps --no-binary poisson-trace poisson-trace==0.1.0a1
tar -xzf poisson_trace-0.1.0a1.tar.gz
cd poisson_trace-0.1.0a1
```

Commands, flags and what they print may still change before 0.1.0. Send problems to
work@poissonlabs.ai, with the command you typed, what it printed, and what
`poisson-trace --version` prints.

## What a first run looks like

Five words come up on every page. A try is one attempt of your agent at one task. A run is
one stored sweep: every try of one version of your agent, kept together. A store is the
folder that holds runs. An input is one thing the agent was asked to do, and a run usually
tries each input more than once. A case is what an evaluation tool calls an input: a test
case, a dataset row, a question. An event is an outcome that counts as a failure, and you say
which outcomes those are.

### On runs Prove stored

`poisson-trace init` looks for results under the folder you run it in. Here that folder holds
two recordings of a customer-service agent demo, which Prove stored:

<!-- command -->
```
mkdir -p my-agent && cp -R tests/fixtures/cs my-agent/prove-runs
cd my-agent && poisson-trace init --yes
```

It says what it found:

<!-- excerpt exit=0 -->
```
  found 1 store:
    1) prove-runs                2 runs · cs_agents · newest 2026-09-25
Using prove-runs, the store found.
```

and what it did:

<!-- excerpt exit=0 -->
```
ok  wrote trace.toml: store prove-runs (2 runs), failures app_error, forbidden_action, unresolved, max_turns
  names    2 runs, named from their manifests (cs_agents 2026-09-25 b, cs_agents 2026-09-25 a); none named by you yet: poisson-trace name RUN "a name"
  prove    poisson-prove is installed at a version Trace reads
```

`trace.toml` now names the store and the failures, so the commands after it need no flags.
`runs` lists what the store holds:

<!-- command -->
```
cd my-agent && poisson-trace runs
```

<!-- output exit=0 -->
```
ok  2 runs in prove-runs (newest first); 0 named by you, 2 named from their manifests

  #  name                    rows  failed  traces  started           status
  1  cs_agents 2026-09-25 b    24       7  yes     2026-09-25 23:54  complete
  2  cs_agents 2026-09-25 a    24       7  yes     2026-09-25 23:46  complete

next: poisson-trace where "cs_agents 2026-09-25 b"
```

and `where` reads the newest run:

<!-- command -->
```
cd my-agent && poisson-trace where latest
```

<!-- excerpt exit=0 -->
```
ok  7 of 21 tries failed; their last steps: 4 at a model call and 3 at an agent step (not necessarily the cause)
```

The report puts every try on one clock, the step it had reached, and gives the share of
tries that had not failed by each step where one did:

<!-- excerpt exit=0 -->
```
## Share not yet failed, by turn

Aalen–Johansen over leaf-span index: finishing without failing and timing out are ends of their own, and only capped tries are censored; band: bootstrap 95%, resampling inputs, B = 1,000, seed = 0.

| turn | at risk | failed | not yet failed | 95% band |
|---|---|---|---|---|
| 24 | 15 | 1 | 0.952 | 0.857 – 1.000 |
| 30 | 12 | 1 | 0.905 | 0.714 – 1.000 |
| 33 | 11 | 1 | 0.857 | 0.667 – 1.000 |
| 35 | 10 | 1 | 0.810 | 0.619 – 1.000 |
| 48 | 5 | 1 | 0.762 | 0.571 – 1.000 |
| 50 | 4 | 1 | 0.714 | 0.429 – 1.000 |
| 58 | 2 | 1 | 0.667 | 0.381 – 1.000 |
```

and the kind of step each failed try stopped at:

<!-- excerpt exit=0 -->
```
## Where they die, by kind of step

Aalen–Johansen: each kind's share of tries failed by turn 59, and the share that timed out; band: bootstrap 95%, resampling inputs, B = 1,000, seed = 0.

| kind | tries | share by turn 59 | 95% band |
|---|---|---|---|
| llm | 4 | 0.190 | 0.000 – 0.381 |
| agent | 3 | 0.143 | 0.000 – 0.286 |
| timed out | 0 | 0.000 | 0.000 – 0.000 |
```

`--svg FILE` writes the curve as a picture. Without a `trace.toml`, name the store and the
failures by flag:

<!-- command -->
```
poisson-trace where "cs_agents 2026-09-25 a" --store tests/fixtures/cs \
  --event forbidden_action --event unresolved --event max_turns --event app_error \
  --at 20 --at 40 --svg docs/figures/cs-record.svg --force
```

<!-- excerpt exit=0 -->
```
ok  7 of 24 tries failed; their last steps: 4 at a model call and 3 at an agent step (not necessarily the cause)
  wrote  docs/figures/cs-record.svg
```

[The picture](https://github.com/poisson-labs/trace/blob/main/docs/figures/cs-record.svg)
that command writes is in the repository. The recipe
[A first look](https://github.com/poisson-labs/trace/blob/main/docs/recipes/first-look.md)
goes through these steps one at a time.

### On results in LangSmith, Braintrust or Weave

Results a service holds come in with one `poisson-trace import` for each version. Give the
experiment's address where a file would go, with your key in the environment. Here the two
experiments are a small agent before and after a change, in LangSmith. On this page the two
pulls are answered from LangSmith's own answers, saved with the example files, so the page
runs with no key and no network:

<!-- command pull -->
```
poisson-trace import langsmith langsmith:trace-fixture-baseline-bbb64b8e \
  --store ./experiments --run old --case-from example --outcome-from feedback:exact --cut 0.5 --below
```

<!-- excerpt exit=0 -->
```
ok  wrote run old to ./experiments: 10 rows, 10 cases, 1 repeat each; 6 passed, 4 failed
```

<!-- command pull -->
```
poisson-trace import langsmith langsmith:trace-fixture-candidate-7e3f7200 \
  --store ./experiments --run new --case-from example --outcome-from feedback:exact --cut 0.5 --below
```

<!-- excerpt exit=0 -->
```
ok  wrote run new to ./experiments: 10 rows, 10 cases, 1 repeat each; 8 passed, 2 failed
```

`where` then shows where the old version's failing tries stopped, by step:

<!-- command -->
```
poisson-trace where old --store ./experiments --event missed
```

<!-- excerpt exit=0 -->
```
## Share not yet failed, by step

Aalen–Johansen over leaf-span index: finishing without failing and timing out are ends of their own, and only capped tries are censored; band: bootstrap 95%, resampling inputs, B = 1,000, seed = 0.

| step | at risk | failed | not yet failed | 95% band |
|---|---|---|---|---|
| 2 | 10 | 1 | 0.900 | 0.700 – 1.000 |
| 4 | 9 | 3 | 0.600 | 0.300 – 0.900 |
```

and by kind of step:

<!-- excerpt exit=0 -->
```
## Where they die, by kind of step

Aalen–Johansen: each kind's share of tries failed by step 4, and the share that timed out; band: bootstrap 95%, resampling inputs, B = 1,000, seed = 0.

| kind | tries | share by step 4 | 95% band |
|---|---|---|---|
| tool | 1 | 0.100 | 0.000 – 0.300 |
| other | 3 | 0.300 | 0.000 – 0.600 |
| timed out | 0 | 0.000 | 0.000 – 0.000 |
```

and `fix-check` says whether the new version fails less:

<!-- command -->
```
poisson-trace fix-check old new --store ./experiments --event missed \
  --inputs all --max-mde 0.2
```

<!-- excerpt exit=0 -->
```
too small to tell  too few tries to see a drop of any size
```

Four failures down to two, on ten examples run once each, is too few to tell from chance, and
the report says how many repeats would be enough. It also counts each kind of failure in the
two versions, which shows what grew and what shrank:

<!-- excerpt exit=0 -->
```
## Failures by kind

Each failed try's kind of failure, by the built-in rules; the same rules classified both runs. Counts, not a test: the verdict above is about all failures together.

| kind | old | old share | new | new share | change |
|---|---|---|---|---|---|
| wrong_answer | 3 | 30.0% | 1 | 10.0% | -20.0 points |
| timeout | 1 | 10.0% | 0 | 0.0% | -10.0 points |
| format_error | 0 | 0.0% | 1 | 10.0% | +10.0 points |
| all failures | 4 | 40.0% | 2 | 20.0% | -20.0 points |
```

`where` and `compare` read the steps of each try, so they need a run that carries traces: a
run Prove stored with its traces, or a run imported from LangSmith, Braintrust or Weave by a
pull or from a file of the service's API. The CSV or summary that a service's page downloads
holds no steps, so on a run imported from one `where` says so and `compare` points to
`fix-check`, which needs no traces. The recipes are
[From LangSmith](https://github.com/poisson-labs/trace/blob/main/docs/recipes/from-langsmith.md),
[From Braintrust](https://github.com/poisson-labs/trace/blob/main/docs/recipes/from-braintrust.md)
and [From Weave](https://github.com/poisson-labs/trace/blob/main/docs/recipes/from-weave.md).

## Let your coding agent set it up

`poisson-trace init --agent` writes a skill and a prompt into the two folders coding agents
read skills from, `.agents/skills/` and `.claude/skills/`, and nothing else. Trace makes no
model call and reads no key. Give your agent the prompt:

```text
Use the poisson-trace-setup skill in this repository: set Poisson Trace up for me to review, then stop.
```

Your agent reads the repository, runs none of your code, writes `trace.toml`, runs
`poisson-trace doctor --setup` until it passes, and stops. Review what it wrote, then run
`poisson-trace init` yourself: it shows the files the config names and imports them after you
say yes. [Set up Trace with your coding agent](https://github.com/poisson-labs/trace/blob/main/docs/setup-with-your-agent.md)
has the steps the agent follows, the check and the hand-over.

## What a fix check says, and what it does not

The usual way to check a fix is to run the failed inputs again on the new version and count
how many now pass. That count has no control: run the old version again on the same inputs,
with nothing changed, and some of them pass too. A fix check puts that number beside the new
version's.

The example is an airline agent, in three runs that Prove stored. The oldest run chose the
inputs: the ones that failed in it. The second is the old version run again, and the newest
is the agent with a guardrail patch:

<!-- command -->
```
mkdir -p airline-agent && cp -R tests/fixtures/tau2 airline-agent/prove-runs
cd airline-agent && poisson-trace init --yes
```

<!-- excerpt exit=0 -->
```
ok  wrote trace.toml: store prove-runs (3 runs), failures unsolved
```

<!-- command -->
```
cd airline-agent && poisson-trace runs
```

<!-- output exit=0 -->
```
ok  3 runs in prove-runs (newest first); 0 named by you, 3 named from their manifests

  #  name                       rows  failed  traces  started           status
  1  tau2-airline 2026-09-17 a    10       3  no      2026-09-17 14:02  complete
  2  tau2-airline 2026-09-15 b   200     112  yes     2026-09-15 21:11  complete
  3  tau2-airline 2026-09-15 a   200     110  yes     2026-09-15 21:01  complete

next: poisson-trace where "tau2-airline 2026-09-15 b"
```

The shortest fix check is the one on the first screen. `--inputs all` compares every input
both runs hold. `--max-mde` is the smallest drop in the share of tries that fail that you
want the check to be able to see, as a fraction: `0.2` is 20 points. Choose it before you
look at a result. Neither has a default.

<!-- command -->
```
cd airline-agent && poisson-trace fix-check previous latest --inputs all --max-mde 0.2
```

<!-- excerpt exit=0 -->
```
too small to tell  too few tries to see a 20-point drop
```

That takes every task the patched run holds. The fix was for the inputs that failed, and
`--failing-from` names the run that chose them, in place of `--inputs all`:

<!-- command -->
```
cd airline-agent && poisson-trace fix-check previous latest \
  --failing-from "tau2-airline 2026-09-15 a" --max-mde 0.20
```

<!-- excerpt exit=0 -->
```
too small to tell  too few tries to see a 20-point drop
```

<!-- excerpt exit=0 -->
```
## The control

The old version's run on the inputs that failed in tau2-airline 2026-09-15 a, beside the new.

| version | runs | failed | failure share | did not fail on re-run |
|---|---|---|---|---|
| old | 24 | 18 | 75.0% | 25.0% |
| new | 6 | 3 | 50.0% | 50.0% |

Re-running these inputs and counting the runs that did not fail would have read 25.0% on the old version, where nothing changed.
```

Half the tries of the patched version passed, and a quarter of the old version's did too,
with nothing changed. The report then says how small a change these tries could have shown,
and how many repeats of each input would settle the question:

<!-- excerpt exit=0 -->
```
## What it could not have detected

proportional change on every input, 80% power, α = 0.05, continuity-corrected normal approximation to the stratified statistic.

- a drop in failure share: could not have detected one below 64.3 points
- a rise in failure share: no limit; even every run failing, a rise of 30.0 points, would have been detected less than four times in five

**too small to tell: could not have detected a drop in failure share below 64.3 points, and 20 was asked for**

## Guidance

- repeats: 16 per arm on these 6 inputs would bring the limit to 20 points
```

The first line of every fix check is its verdict, one of three:

- *different*: the two runs differ, in the direction the line names. It says the runs differ,
  not why: by itself it does not show that your change caused it.
- *no significant difference*: the gap could be chance, and the tries rule out a change of
  the size you asked about with `--max-mde`. The range of differences the tries fit lies
  inside plus or minus that size. A smaller change may still be there.
- *too small to tell*: the tries cannot rule out a change of the size you asked about. Where
  more tries would settle it, the report says how many.

And every fix check ends with what it cannot say:

- A difference between two runs is a difference between the runs. The version, the provider
  and the hour changed together unless the two were run side by side.
- Repeat tries of one input are read as separate draws, never as replays: nothing matches a
  try of the old version to a try of the new by seed.
- If repeat tries of one input are near copies of one another, the test is more confident
  than it should be. The report's reading by input does not depend on that.
- A try with no outcome is left out of both versions and counted in the header. A new version
  that times out where the old one failed does not show as a failure.
- Trace reads the runs it is given. If the inputs were chosen by the old run's own outcomes,
  or the better of several runs was handed over, the stated confidence does not hold.
- The limit and the number of tries it suggests come from these runs' own failure rates,
  which are estimates. They guide the next run and do not promise its result.

`changes` reads two runs input by input and names the inputs that moved. Here the two runs
are one coding agent run twice, 56 minutes apart, on the same problems, with nothing changed,
saved as two tables of results:

<!-- command -->
```
poisson-trace import table tests/fixtures/ingest/table/humaneval-a.csv \
  --store ./store --run old --case-column case --outcome-column outcome \
  --failed failed_assertion --failed crashed
```

<!-- excerpt exit=0 -->
```
ok  wrote run old to ./store: 10,496 rows, 328 cases, 32 repeats each; 9,158 passed, 1,338 failed
```

<!-- command -->
```
poisson-trace import table tests/fixtures/ingest/table/humaneval-b.csv \
  --store ./store --run new --case-column case --outcome-column outcome \
  --failed failed_assertion --failed crashed
```

<!-- excerpt exit=0 -->
```
ok  wrote run new to ./store: 10,496 rows, 328 cases, 32 repeats each; 9,109 passed, 1,387 failed
```

<!-- command -->
```
poisson-trace changes old new --store ./store --event missed --top 2
```

<!-- excerpt exit=0 -->
```
ok  2 of 328 inputs stand out: case HumanEval/129@0.7 failed more in B; case HumanEval/129@0.0 failed more in B
```

<!-- excerpt exit=0 -->
```
## Inputs that changed

Fisher's exact test per input, Benjamini-Hochberg at q = 0.05 over 328 inputs; 2 flagged.

| input | A failed/runs | B failed/runs | change | p | q | flag |
|---|---|---|---|---|---|---|
| {"case":"HumanEval/129@0.7"} | 12/32 | 32/32 | +62.5 points | 2.30e-08 | 7.55e-06 | failed more in B |
| {"case":"HumanEval/129@0.0"} | 20/32 | 32/32 | +37.5 points | 1.38e-04 | 0.023 | failed more in B |
```

One problem failed on every try of the second run, and nothing else is flagged. The recipes
are [Check a fix](https://github.com/poisson-labs/trace/blob/main/docs/recipes/check-a-fix.md)
and [What it cannot say](https://github.com/poisson-labs/trace/blob/main/docs/recipes/what-it-cannot-say.md).

[Tasks, Prove and Trace together](https://github.com/poisson-labs/trace/blob/main/docs/recipes/with-tasks-and-prove.md)
runs the three tools end to end with no model: Poisson Tasks makes tasks whose right answer is
known, Prove runs an agent on them before and after a change, and Trace says whether the new
version fails less and at which step the old one stopped.

## The commands

- `poisson-trace init`: set Trace up in a folder, by questions or by flags.
- `poisson-trace runs`: list the runs of a store.
- `poisson-trace name`: give a run a name of yours.
- `poisson-trace where`: where the tries of one run die, by step and by kind of step.
- `poisson-trace compare`: whether tries fail sooner or later in one run than in another.
- `poisson-trace fix-check`: whether a new version fails less than the old, with a control.
- `poisson-trace changes`: which inputs moved between two runs.
- `poisson-trace import`: read in the results another tool wrote, as a run.
- `poisson-trace doctor`: say whether the setup is ready.
- `poisson-trace handover`: check a result written as files.
- `poisson-trace ui`: build pages over a store's runs and saved verdicts.
- `poisson-trace report`: write a result as one HTML page.
- `poisson-trace` on its own: open [the terminal app](https://github.com/poisson-labs/trace/blob/main/docs/app.md).

[The commands](https://github.com/poisson-labs/trace/blob/main/docs/commands.md) shows the
help of every one, the options they share and the exit codes.
[The config file](https://github.com/poisson-labs/trace/blob/main/docs/config.md) goes through
`trace.toml` key by key. The same commands are functions in
[the Python API](https://github.com/poisson-labs/trace/blob/main/docs/python.md).

## Results from other tools

Trace reads eleven sources: the runs Prove stored, and the results of ten other tools, which
are DeepEval, Ragas, tables, JUnit, promptfoo, Inspect, OpenAI Evals, LangSmith, Braintrust
and Weave. `poisson-trace import` reads one version's results and writes them as one run, and
every command then reads that run like any other. You say what counts as a failure and what
identifies a case, where the tool's files do not. No prompt and no answer text is kept.

- [DeepEval](https://github.com/poisson-labs/trace/blob/main/docs/integrations/deepeval.md): its saved test runs, one metric an import. Recipe: [From DeepEval](https://github.com/poisson-labs/trace/blob/main/docs/recipes/from-deepeval.md).
- [Ragas](https://github.com/poisson-labs/trace/blob/main/docs/integrations/ragas.md): a score table you saved, one score an import. Recipe: [From Ragas](https://github.com/poisson-labs/trace/blob/main/docs/recipes/from-ragas.md).
- [Tables](https://github.com/poisson-labs/trace/blob/main/docs/integrations/table.md): any table of results, as CSV, JSON Lines, JSON or Parquet. Recipe: [From a table of results](https://github.com/poisson-labs/trace/blob/main/docs/recipes/from-a-table.md).
- [JUnit](https://github.com/poisson-labs/trace/blob/main/docs/integrations/junit.md): the XML reports pytest and CI systems write. Recipe: [From JUnit reports](https://github.com/poisson-labs/trace/blob/main/docs/recipes/from-junit.md).
- [promptfoo](https://github.com/poisson-labs/trace/blob/main/docs/integrations/promptfoo.md): its results file, one prompt an import. Recipe: [From promptfoo](https://github.com/poisson-labs/trace/blob/main/docs/recipes/from-promptfoo.md).
- [Inspect](https://github.com/poisson-labs/trace/blob/main/docs/integrations/inspect.md): its `.eval` and `.json` logs. Recipe: [From Inspect](https://github.com/poisson-labs/trace/blob/main/docs/recipes/from-inspect.md).
- [OpenAI Evals](https://github.com/poisson-labs/trace/blob/main/docs/integrations/openai-evals.md): the records `oaieval` writes. Recipe: [From OpenAI Evals](https://github.com/poisson-labs/trace/blob/main/docs/recipes/from-openai-evals.md).
- [LangSmith](https://github.com/poisson-labs/trace/blob/main/docs/integrations/langsmith.md): an experiment pulled with your key, or its exported runs. Recipe: [From LangSmith](https://github.com/poisson-labs/trace/blob/main/docs/recipes/from-langsmith.md).
- [Braintrust](https://github.com/poisson-labs/trace/blob/main/docs/integrations/braintrust.md): an experiment pulled with your key, or its exported events. Recipe: [From Braintrust](https://github.com/poisson-labs/trace/blob/main/docs/recipes/from-braintrust.md).
- [Weave](https://github.com/poisson-labs/trace/blob/main/docs/integrations/weave.md): an evaluation pulled with your key, or its exported calls. Recipe: [From Weave](https://github.com/poisson-labs/trace/blob/main/docs/recipes/from-weave.md).

A tool is listed here only when a real export of it is among the example files committed to
the repository, and its page shows a command run on that file with what Trace printed.

## Into the product

`--out DIR` on `where`, `compare`, `fix-check` or `changes` writes the result as a folder of
files: the result as JSON, the report as text, its table, its charts, and a list of every
file with its digest. `poisson-trace handover --check DIR` holds such a folder to that list
before your code reads it. [The handover](https://github.com/poisson-labs/trace/blob/main/docs/handover.md)
says what each file holds and which keys are promised, and the recipe is
[Into the product](https://github.com/poisson-labs/trace/blob/main/docs/recipes/into-the-product.md).

**The pages.** `poisson-trace report DIR` turns that folder into one HTML page that opens from
disk with nothing else present, to send to someone who does not have Trace: the recipe is
[A page to send](https://github.com/poisson-labs/trace/blob/main/docs/recipes/a-page-to-send.md).
`poisson-trace ui` builds pages over a whole store, its runs and every saved verdict. Neither
loads anything from the network.

## How it decides

Every verdict comes from a named statistical test with a stated level, chosen for small
numbers of tries: exact tests where they exist, and resampling for the bands. A fix check
compares the two versions inside each input, so an input that is hard for both does not
count against either. Each report prints the test it used, the level, and the smallest change
the tries could have shown.

[How it decides](https://github.com/poisson-labs/trace/blob/main/docs/how-it-decides.md)
names each test, says how the three verdicts are chosen, and lists the flags that set a size,
a level or a seed. The test suite holds every one of them against an independent reference.

## What is built and what is not claimed

Trace reads stored results. It does not run your agent, record its calls or change its code,
and nothing it reads leaves your machine.

A verdict is about the two runs you gave it, not about the two versions: whatever else
differed between the runs is part of the difference. Looking after every few tries and
stopping when the verdict reads well is not covered by the stated confidence, and no report
can see it. `compare` does not pair tries by seed, even when two runs share their seeds.
The example files hold one pair that reads *different* with fewer failures: a base model and
its fine-tuned version, scored by Ragas, on two of its three scores, which
[the Ragas page](https://github.com/poisson-labs/trace/blob/main/docs/integrations/ragas.md)
shows. The pairs on this page read *too small to tell*, or *different* where nothing was
changed, and the page says why each time.

## Development

[CONTRIBUTING.md](https://github.com/poisson-labs/trace/blob/main/CONTRIBUTING.md) has the
working copy, the test lanes, the docs check and the rules a change is held to.
[CHANGELOG.md](https://github.com/poisson-labs/trace/blob/main/CHANGELOG.md) says what each
release holds.

## Licence

MIT. See [LICENSE](https://github.com/poisson-labs/trace/blob/main/LICENSE) and
[NOTICE](https://github.com/poisson-labs/trace/blob/main/NOTICE).

## Citation

```text
@software{poisson_trace,
  author = {Poisson Labs},
  title = {Poisson Trace: where in the workflow runs die},
  year = {2026},
  url = {https://github.com/poisson-labs/trace}
}
```
