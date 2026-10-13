# DeepEval

You score two versions of your agent with DeepEval and get two pass rates. This page shows
how to find out whether the difference between them is real.

Poisson Trace reads the result files DeepEval already wrote. It runs no metric and calls no
model. The example below does not use one of DeepEval's own metrics. It uses a custom metric
over stored test results, written with DeepEval's `BaseMetric`: the files are DeepEval's own,
the metric is ours.

## Install

```
pip install poisson-trace
pip install git+https://github.com/poisson-labs/prove
```

Nothing here imports DeepEval. Tested on files written by DeepEval 4.2.6.

## Save your results

DeepEval writes a result file when you set a folder for it:

```
DEEPEVAL_RESULTS_FOLDER=./results deepeval test run test_agent.py
```

Give every test case a `name` that is the same in both versions. Run the old version and
the new one on the same cases. If you can, run each case more than once per version: one
run per case is the smallest design there is.

## Import and compare

One import is one version. Each import reads one metric and writes one new run into a store
in Prove's format; `poisson-trace fix-check` then compares the two runs.

```
poisson-trace import deepeval FILE [FILE ...] --store ROOT --run NAME
        --metric NAME
        --cut ( recorded | X ( --below | --above ) )
        --case ( name | input | position )
        [--started ISO-8601] [--json]
```

Nothing has a default but the start time. You say which metric, where the cut is and what
identifies a test case.

- `--metric` is the metric's name as the file has it. A name no test case carries is
  refused, and the refusal lists the names the file does carry.
- `--cut recorded` uses the threshold DeepEval stored and DeepEval's own decision for that
  metric. To use your own, pass a number and a side: `--cut 0.7 --below` counts a score
  under 0.7 as missed, `--cut 0.3 --above` counts a score over 0.3 as missed. A score equal
  to the cut met it. The outcome is the word `met` or the word `missed`.
- `--case name` identifies a test case by its `name`. `--case input` identifies it by a
  SHA-256 digest of its input, and the input's text is not kept. `--case position`
  identifies it by its place in the file, and assumes both files list the cases in the same
  order.
- Test cases that share a case within one import are repeats of that case. Several files
  given to one import are read as one version, in the order given.
- A test case whose metric raised, or has no score, has no outcome. It is counted in the
  summary as `no score` and Trace leaves it out of both versions.
- `--started` is when that version's run started, with its zone. Without it the time is
  read from the first file's name, `test_run_YYYYMMDD_HHMMSS.json`, which DeepEval takes
  from the clock of the machine that saved the file and writes with no zone. It is read in
  the zone of the machine running the import, and the summary says so and names the zone.
  A file with another name gives its modification time. The summary prints which of the
  three was used.
- `.json` and `.json.gz` are read: the file in the results folder,
  `.deepeval/.latest_run_full.json`, and `.deepeval/.latest_test_run.json` when it holds
  results.
- `--store` may be left out when a `trace.toml` in the current folder (or the file `--config
  PATH` names) names a store: the import writes into it. `--store NAME` takes the store that
  file names so.

## The worked example

The two files are in `tests/fixtures/ingest/deepeval/`. They are one agent run twice, 56
minutes apart, with nothing changed: 164 HumanEval problems at two temperatures, 32 runs of
each, 10,496 test cases per file. Each test case is named by its problem and temperature,
and the metric `Tests Passed` scores 1.0 when the stored run passed the problem's tests and
0.0 when it did not, with a threshold of 1.0. DeepEval's `evaluate()` ran that metric and
wrote both files; `make.py` beside them is the recipe. DeepEval reports 9,158 of 10,496
passed, then 9,109: 87.3%, then 86.8%.

The commands run from the root of a clone and write the store to `./store`.

<!-- command -->
```
poisson-trace import deepeval tests/fixtures/ingest/deepeval/humaneval-a.json.gz \
  --store ./store --run humaneval-a --metric "Tests Passed" --cut recorded --case name \
  --started 2026-09-05T18:54:07Z
```

<!-- output exit=0 -->
```
ok  wrote run humaneval-a to ./store: 10,496 rows, 328 cases, 32 repeats each; met 9,158, missed 1,338

# Poisson Trace · import · humaneval-a

- run written: humaneval-a · store: ./store
- tool: deepeval
- file: humaneval-a.json.gz · sha256 81a50f22e5f14af4093c6e3bb07bb55a658913cae3fcb7ec72372cf9189909d9
- declared: metric Tests Passed · cut recorded · case name
- started: 2026-09-05T18:54:07Z · from: given
- rows 10,496 · cases 328 · repeats of a case: smallest 32, largest 32
- outcomes: met 9,158 · missed 1,338
- rows with no outcome: 0
- without this metric: 0
- recorded threshold 1.0: 10,496

In the command below, OLD and NEW are this run and the other version's run, imported into the same store, the older version first. X is the largest limit of detection you accept, as a share: 0.05 is five points.

next: poisson-trace fix-check OLD NEW --store ./store --event missed --inputs all --max-mde X  # humaneval-a is OLD or NEW
```

<!-- command -->
```
poisson-trace import deepeval tests/fixtures/ingest/deepeval/humaneval-b.json.gz \
  --store ./store --run humaneval-b --metric "Tests Passed" --cut recorded --case name \
  --started 2026-09-05T19:50:09Z
```

<!-- excerpt exit=0 -->
```
# Poisson Trace · import · humaneval-b

- run written: humaneval-b · store: ./store
- tool: deepeval
- file: humaneval-b.json.gz · sha256 c5577283c078591bd8cf719d1ebea95fcdcd75d018e5ccbadff629cc56bf2464
- declared: metric Tests Passed · cut recorded · case name
- started: 2026-09-05T19:50:09Z · from: given
- rows 10,496 · cases 328 · repeats of a case: smallest 32, largest 32
- outcomes: met 9,109 · missed 1,387
- rows with no outcome: 0
- without this metric: 0
- recorded threshold 1.0: 10,496
```

<!-- command -->
```
poisson-trace fix-check humaneval-a humaneval-b --store ./store --event missed \
  --inputs all --max-mde 0.02 --top 3
```

<!-- excerpt exit=0 -->
```
# Poisson Trace · fix check · humaneval-a (old) and humaneval-b (new)

## Runs

- old: humaneval-a · target: import/deepeval · status: complete · started: 2026-09-05T18:54:07Z · declared repeats: not recorded
- Prove's tally (old): rows 10,496 · with outcome 10,496 · no outcome 0 · timed out 0 · infra 0 · other 0
- new: humaneval-b · target: import/deepeval · status: complete · started: 2026-09-05T19:50:09Z · declared repeats: not recorded
- Prove's tally (new): rows 10,496 · with outcome 10,496 · no outcome 0 · timed out 0 · infra 0 · other 0
- the two runs started 56 min apart
- events: missed
- inputs: every input either run carries · selected 328 · compared 328 · left out 0
- rows used: old 10,496 (timed out 0, no outcome 0) · new 10,496 (timed out 0, no outcome 0)
- inputs short of the declared repeats: old 0 · new 0
- inputs with mixed outcomes across their repeats: old 54 · new 48

## The control

The old version, re-run on the same inputs with nothing changed.

| version | runs | failed | failure share | did not fail on re-run |
|---|---|---|---|---|
| old | 10,496 | 1,338 | 12.7% | 87.3% |
| new | 10,496 | 1,387 | 13.2% | 86.8% |

Re-running these inputs and counting the runs that did not fail would have read 87.3% on the old version, where nothing changed.

## The comparison

exact conditional Cochran-Mantel-Haenszel test, stratified by input over 328 inputs (58 informative), two-sided; α = 0.05.

new failures: observed 1,387, expected 1,362.500, variance 131.139; p = 0.036
difference: +0.47 points, new minus old (+0.04 to +0.90; Mantel-Haenszel weights; interval: Sato variance, large-sample, 95%)
by input: p = 0.127 (sign-flip over the 47 inputs that moved, 100,000 draws, seed = 0); not part of the line below

## Consistency

failure share 0.130 · fails again 0.808 · κ 0.779 · within-input variance 0.025 against pooled 0.113
a comparison that ignored the inputs would need 1/(1 − κ) = 4.52 times the runs

## What it could not have detected

proportional change on every input, 80% power, α = 0.05, continuity-corrected normal approximation to the stratified statistic.

- a drop in failure share: could not have detected one below 0.64 points
- a rise in failure share: could not have detected one below 0.66 points

**different: the new version failed more on these inputs (exact Cochran-Mantel-Haenszel, stratified by input, p = 0.036)**

## Inputs that changed

Fisher's exact test per input, Benjamini-Hochberg at q = 0.05 over 328 inputs; 2 flagged.

| input | old failed/runs | new failed/runs | change | p | q | flag | could not have detected a rise below |
|---|---|---|---|---|---|---|---|
| {"case":"HumanEval/129@0.7"} | 12/32 | 32/32 | +62.5 points | 2.30e-08 | 7.55e-06 | failed more in new | 34.2 points |
| {"case":"HumanEval/129@0.0"} | 20/32 | 32/32 | +37.5 points | 1.38e-04 | 0.023 | failed more in new | 28.9 points |
| {"case":"HumanEval/91@0.7"} | 28/32 | 32/32 | +12.5 points | 0.113 | 1.000 | – | 12.5 points |

3 of 328 inputs shown, by ascending p; --json lists all.

A lone changed input is flagged only if its p is below α / M = 0.000152, and the smallest p an input of this design can give is 1.09e-18: a lone change can be flagged; a lone complete flip needs 9 repeats per arm. An input with no flag is not an input that did not change.
```

The report closes with its block *What this cannot say*, left out here for length.

Half a point separates the two pass rates. The two runs do differ (p = 0.036): the second
missed 49 more times than the first, and 32 of those 49 are one problem. HumanEval/129
missed 12 times in 32, then 32 in 32, at temperature 0.7, and 20 in 32, then 32 in 32, at
temperature 0.0, in an agent nobody changed. No other case is flagged. The by-input line
(p = 0.127) says the cases did not move as a body. The report says what it cannot say: a
difference between two runs is a difference between the runs, and the version and the hour
changed together.

## From `poisson-trace init`

`poisson-trace init`, run in a folder with no Prove store under it, lists the test runs
DeepEval saved, by folder (a `test_run_*.json` file, and `.latest_test_run.json` in a
`.deepeval` folder; a `.gz` copy is read by the import and not offered), and offers to import
them. Its questions are the import's flags, asked in their order; with `--yes` it takes them
as flags instead. Each file becomes one run, named after the file, in a store `trace-store`
beside `trace.toml`, and `trace.toml` names that store with `missed` as the failure. Every
file is read before any run is written, so a file the import refuses writes no run of the
others. Here it is on the first worked file, saved under the name DeepEval gives:

<!-- command -->
```
mkdir -p from-deepeval/results
gunzip -c tests/fixtures/ingest/deepeval/humaneval-a.json.gz > from-deepeval/results/test_run_20260905_185407.json
cd from-deepeval && poisson-trace init --yes --metric "Tests Passed" --cut recorded --case name
```

<!-- excerpt exit=0 -->
```
  found 1 DeepEval results folder:
    1) results                   1 saved test run · newest 2026-09-05
```

<!-- excerpt exit=0 -->
```
ok  wrote trace.toml and imported 1 run into trace-store, failures missed
  names    1 run, named at import (test_run_20260905_185407)
  prove    poisson-prove is installed at the version Trace reads
  import   poisson-trace import deepeval results/test_run_20260905_185407.json --store trace-store --run test_run_20260905_185407 --metric "Tests Passed" --cut recorded --case name
  the same setup, without questions:
    poisson-trace init --yes --import --metric "Tests Passed" --cut recorded \
      --case name --event missed
next: poisson-trace runs
```

With `trace.toml` there, the import takes its store from it too, so `--store` may be left out.

## What this does not do

- It does not run DeepEval, a metric or a model. It reads files.
- The worked example does not show one of DeepEval's model-judged metrics. Its metric is a
  custom one that calls no model.
- It reads one metric per import. A test case's overall success across several metrics is
  not read.
- It does not read Confident AI. A `.latest_test_run.json` written while logged in holds a
  link and no results, and is refused.
- It does not read DeepEval's SQLite store, or metrics attached to a trace or a span inside
  a test case.
- It does not find your cases for you. If your test cases have no `name`, DeepEval numbers
  them by position. With `--case name` such a file is refused, and you must say
  `--case position` and keep the order the same in both files.
- It keeps no prompt, answer or reason text. The store holds the case, the score, the
  outcome and the rule you declared.
- It does not add to a run. A run name the store already holds is refused.
- It does not choose a cut. Trying several cuts or several metrics and keeping the one
  that reads well is not covered by the confidence printed.
- It does not compare the scores themselves. It compares the share of cases that missed
  the cut.
- A store the importer wrote is for Trace's verbs. Prove's own `diff` pairs rows by seed,
  and the files record none.
- Files from DeepEval versions other than 4.2.6 are not tested.
