# JUnit

Your test suite runs under pytest, Jest, Go or Maven, or in CI, and writes a JUnit XML report.
You change something, run the suite again, and fewer tests fail, or more. This page shows how
to find out whether the difference between the two runs is real.

Poisson Trace reads the reports your runner already wrote. It runs no test.

## Install

```
pip install poisson-trace
```

Nothing here imports a test runner. Tested on reports written by pytest 9.1.1.

## Save your results

Ask your runner for a report, once per version: `pytest --junitxml=old.xml`, then
`pytest --junitxml=new.xml` after the change. Run the same tests on both. A test that can
pass on one run and fail on the next (an agent, a model, anything with a seed you do not fix)
is worth running more than once per version: give each run its own report, and import the
reports of one version together, as repeats.

## Import and compare

One import is one version. Each import writes one new run into a store in Prove's format;
`poisson-trace fix-check` then compares the two runs.

```
poisson-trace import junit FILE [FILE ...] --store ROOT --run NAME
        [--case ( classname-name | name )] [--started ISO-8601] [--json]
```

Nothing needs declaring: a JUnit report says what failed.

- Each `<testcase>` is one row. One with a `<failure>` or an `<error>` is `missed`, however
  many it holds; one with `<skipped>` has no outcome, and the summary counts it; any other is
  `met`. A report whose root is `<testsuites>` or a lone `<testsuite>` is read, suites inside
  suites included.
- `--case classname-name`, the default, identifies a test by its class name and its name, kept
  apart. `--case name` identifies it by its name alone, so that the same test in several
  classes is one case. A test with no class name is identified by its name under either form;
  a test with no name refuses the import.
- Tests that share a case, within a file or across the files of one import, are repeats of
  that case in the order read; several files given to one import are read as one version, in
  the order given.
- The start is the earliest `timestamp` of any suite read, as UTC. A timestamp with no zone is
  read as UTC, and the summary says so; one that is not a time refuses the import. With no
  timestamp, the first file's modification time is used. `--started` gives it instead, with
  its zone. The summary prints which it was.
- A file that is not XML, whose root is another element, that holds no test case or a test
  case inside another, whose declaration names an encoding the reader does not take, or that
  declares a document type is refused. No runner writes a document type, and a report that
  declares one is not read at all, so nothing it names is opened.
- `--store` may be left out when a `trace.toml` in the current folder (or the file `--config
  PATH` names) names a store: the import writes into it. `--store NAME` takes the store that
  file names so.

## The worked example

The reports are in `tests/fixtures/ingest/junit/`, written by pytest 9.1.1. `humaneval-a.xml`
and `humaneval-b.xml` are one small suite, `replay_humaneval.py` beside them, run against each
of the two stored runs of one agent that the [DeepEval page](deepeval.md) and the [tables
page](table.md) compare: one test per HumanEval problem at temperature 0.7, in four classes,
one per repeat. A test passes when the stored run passed, fails when it failed its assertions,
and errors when it crashed. `make.py` beside them is the recipe.

With `--case name`, the four classes' tests of one problem are four repeats of one case. The
commands run from the root of a clone and write the store to `./store`.

<!-- command -->
```
poisson-trace import junit tests/fixtures/ingest/junit/humaneval-a.xml \
  --store ./store --run replay-a --case name
```

<!-- output exit=0 -->
```
ok  wrote run replay-a to ./store: 656 rows, 164 cases, 4 repeats each; 569 passed, 87 failed

# Poisson Trace · import · replay-a

## Summary

- Wrote: replay-a into ./store, from humaneval-a.xml (junit): 656 tries on 164 inputs.
- Failures: 87 failed and 569 passed. A try counts as failed when its test failed or errored.
- Compared: Nothing yet. One import is one version.
- Next: Import the other version's file the same way: `poisson-trace import junit OTHER.xml --store ./store --run OTHER --case name`.

## Before you act on this

- Its start time is the report's earliest suite timestamp.
- A skipped test has no outcome and is left out.
- When you compare, choose the smallest drop that matters to you (--max-mde) before you look at any results; Trace then says whether these tries could catch it.

## What was written

- run written: replay-a · store: ./store
- tool: junit
- file: humaneval-a.xml · sha256 c513d191ba7ac89a6ed35505ba67cd90d8a640037ed007548def0297f7dbbc3c
- declared: case name
- started: 2026-10-13T04:20:34.510483Z · from: file
- rows 656 · cases 164 · repeats of a case: smallest 4, largest 4
- outcomes: met 569 · missed 87
- rows with no outcome: 0
- test cases with a failure: 86
- test cases with an error: 1

In the command below, OLD and NEW are this run and the other version's run, imported into the same store, the older version first. X is the largest limit of detection you accept, as a share: 0.05 is five points.

next: poisson-trace fix-check OLD NEW --store ./store --event missed --inputs all --max-mde X  # replay-a is OLD or NEW
```

<!-- command -->
```
poisson-trace import junit tests/fixtures/ingest/junit/humaneval-b.xml \
  --store ./store --run replay-b --case name
```

<!-- excerpt exit=0 -->
```
- outcomes: met 573 · missed 83
- rows with no outcome: 0
- test cases with a failure: 83
- test cases with an error: 0
```

<!-- command -->
```
poisson-trace fix-check replay-a replay-b --store ./store --event missed \
  --inputs all --max-mde 0.05 --top 3
```

<!-- excerpt exit=0 -->
```
no significant difference  the gap could be chance
```

<!-- excerpt exit=0 -->
```
| version | runs | failed | failure share | did not fail |
|---|---|---|---|---|
| old | 656 | 87 | 13.3% | 86.7% |
| new | 656 | 83 | 12.7% | 87.3% |
```

These are the same two runs that read *different* (p = 0.036) on the tables page, where every
stored run is a row: 32 at each of two temperatures. The suite reads four of them, at one
temperature, and at that size the difference is not there to see. The line says so, and how
small a change it could have seen.

The other pair, `trace-suite-1.xml` and `trace-suite-2.xml`, is three of Trace's own test
files run twice. Nothing in it fails, so `--event missed` names nothing to compare; one test
skips itself, and has no outcome:

<!-- command -->
```
poisson-trace import junit tests/fixtures/ingest/junit/trace-suite-1.xml \
  --store ./store --run own-1
```

<!-- excerpt exit=0 -->
```
- started: 2026-10-13T04:01:11.564615Z · from: file
- rows 91 · cases 91 · repeats of a case: smallest 1, largest 1
- outcomes: met 90 · missed 0
- rows with no outcome: skipped 1
```

## From `poisson-trace init`

`poisson-trace init`, run in a folder with no Prove store under it, lists the JUnit reports it
finds (a `.xml` file whose root element, within its first 4 KB, is `<testsuites>` or
`<testsuite>`) and offers to import them. It asks no question of the reader: each report
becomes one run, named after the file without `.xml`, in a store `trace-store` beside
`trace.toml`, read by class name and name, and `trace.toml` names that store with `missed` as
the failure. `--case name` reads the reports by the test's name instead. Here it is on the
worked pair:

<!-- command -->
```
mkdir -p from-junit && cp tests/fixtures/ingest/junit/humaneval-*.xml from-junit/
cd from-junit && poisson-trace init --yes --case name
```

<!-- excerpt exit=0 -->
```
  found 2 result files:
    1) humaneval-a.xml           a JUnit XML report, its root <testsuites>
    2) humaneval-b.xml           a JUnit XML report, its root <testsuites>
```

<!-- excerpt exit=0 -->
```
ok  wrote trace.toml and imported 2 runs into trace-store, failures missed
  names    2 runs, named at import (humaneval-b, humaneval-a)
  prove    poisson-prove is installed at the version Trace reads
  import   poisson-trace import junit humaneval-a.xml --store trace-store --run humaneval-a --case name
  import   poisson-trace import junit humaneval-b.xml --store trace-store --run humaneval-b --case name
  the same setup, without questions:
    poisson-trace init --yes --import --case name --event missed
next: poisson-trace runs
```

With `trace.toml` there, the import takes its store from it too, so `--store` may be left out.

A report that holds no test case, as a runner writes when it collected no test (pytest exits 5
and still writes one), has nothing to import. init lists it, leaves it out in one line naming
it, and imports the other reports; it does not count as a second tool's file either. A report
that cannot be read still stops the import, naming it, and `poisson-trace import junit` given
an empty report refuses it:

<!-- command -->
```
mkdir -p with-empty && cp tests/fixtures/ingest/junit/humaneval-*.xml with-empty/
printf '<testsuites><testsuite name="pytest" tests="0" /></testsuites>\n' > with-empty/nothing-collected.xml
cd with-empty && poisson-trace init --yes --case name
```

<!-- excerpt exit=0 -->
```
  found 3 result files:
    1) humaneval-a.xml           a JUnit XML report, its root <testsuites>
    2) humaneval-b.xml           a JUnit XML report, its root <testsuites>
    3) nothing-collected.xml     a JUnit XML report, its root <testsuites>
Leaving out nothing-collected.xml: a JUnit report with no test case in it, as a runner writes when it collected no test.
```

## What this does not do

- It does not run your tests or your runner. It reads the reports.
- It does not make a comparison out of one run: a fix check is two versions on the same
  inputs, side by side.
- It reads reports from runners and versions other than pytest 9.1.1 by the JUnit elements
  they share, and no test runs another runner.
- It keeps no prompt, answer, expected or sampled text: of a test it keeps its class name and
  name, and nothing of a message, a failure's text, its output or a property.
