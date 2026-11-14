# LangSmith

You ran two versions of an agent as LangSmith experiments on the same dataset, and one scored
better. This page shows how to read both into Poisson Trace, ask whether the difference is
real, and see at which step the failing runs stop.

Poisson Trace reads the runs LangSmith already holds. It runs no agent and calls no model, and
it keeps no prompt, input, output or error text.

## Install

<!-- skip reason="installs from the package index, which the docs check does not reach" -->
```
pip install poisson-trace
```

Nothing here imports LangSmith's packages. Tested on runs written by langsmith 0.14.17 (the
Python SDK), as LangSmith's API returns them, as the `langsmith` command v0.3.13 exports them,
and as an experiment's page downloads them.

## Get your runs out

There are three ways, and all three read to the same rows.

### Pull them with your key

Put your key in `LANGSMITH_API_KEY` and name the project or experiment where the files would
go, as `langsmith:NAME`:

<!-- skip reason="needs your own key and your own project: the words in capitals are yours to fill in" -->
```
export LANGSMITH_API_KEY=...
poisson-trace import langsmith langsmith:NAME --store ./store --run old \
  --case-from example --outcome-from feedback:correct --cut 0.5 --below
```

The pull makes three kinds of request and no other: the project by its name
(`GET /api/v1/sessions`), its runs (`POST /api/v2/runs/query`, a page at a time) and its
feedback records (`GET /api/v1/feedback`). It saves a raw copy first, in
`./store/.poisson/raw/langsmith/old/`, as two files: `raw.jsonl`, the runs and then the
feedback records, one a line; and `pull.json`, which says what was pulled, when, and the
file's digest. Then it reads that folder as it reads any file.

- The inputs and outputs are measured and left out of the raw copy, an error keeps only the
  name of its exception, and a feedback record's comment is emptied. A run's `manifest`, the
  saved form of the component that ran, is left out too, since it can hold a prompt template. `--keep-raw-text` saves
  the rows as LangSmith returned them instead.
- A raw copy is never written over. To read the same runs again, with another cut or another
  case, import the folder: `poisson-trace import langsmith ./store/.poisson/raw/langsmith/old
  --store ./store --run old-again ...`. That asks LangSmith nothing and needs no key.
- Only `LANGSMITH_API_KEY` is read. The key goes to LangSmith in a header and nowhere else: it
  is not printed and not written to any file.
- `LANGSMITH_ENDPOINT` names another host for every request, such as the EU region's or your
  company's own. It must be an https address, or http on this machine.
- The pull reads every run of the project, however old: it asks for the runs started since
  a day before the project itself began.
- `--page-size N` asks for N runs or feedback records per request, from 1 to 100 (the default
  is 100). When LangSmith answers that it is being asked too often, the pull waits as long as
  the answer says and asks again.
- Without the key, with a key LangSmith refuses, or with a name no project has, the import
  stops with one `error:` line and exit code 1, and nothing is saved. A failure part way
  through a pull exits 3, and nothing is saved either.

### Export them with the `langsmith` command

Give `--full`, which is what carries each run's inputs, outputs, error, tokens and metadata:

<!-- skip reason="runs the langsmith command, which Trace never does" -->
```
langsmith runs export old.jsonl --project my-experiment --full
langsmith traces export ./old-traces --project my-experiment --full
```

The first writes one file with a run on each line. The second writes a folder with one
`.jsonl` file for each trace; give the folder in the files' place and it is read as one run.
This export leaves out the dataset example's id, so `--case-from example` is refused on it:
name the case by a metadata key instead, as below.

### Download the CSV from the experiment's page

The page's download is a CSV file, with one row for each example. It holds the root run alone:
its status, its error, its latency, its total tokens and cost, and one column for each
feedback key. It holds no steps, so `poisson-trace where` has no step to place a failure on,
and the CSV does not say who gave a score.

The API's answers are read too, saved as they came: the body of `POST /api/v2/runs/query` or
of `POST /api/v1/runs/query`, with the body of `GET /api/v1/feedback` beside it where you have
it. Pages of one experiment are given together. One import reads the runs of one export:
giving the same run twice, or the CSV beside a run export, is refused.

## Import and compare

One import is one version. Each import writes one new run into a store in Prove's format;
`poisson-trace fix-check` then compares the two runs.

<!-- skip reason="the form of the command: the words in capitals are yours to fill in" -->
```
poisson-trace import langsmith FILE [FILE ...] --store ROOT --run NAME
        --case-from ( example | metadata:KEY | input | none )
        --outcome-from ( status | feedback:KEY | metadata:KEY )
        [--cut X ( --below | --above )] [--failed VALUE ...]
        [--select metadata:KEY=VALUE ...]
        [--keep-raw-text] [--page-size N]
        [--started ISO-8601] [--verdicts FILE] [--json]
```

- One trace is one row, and its root run, the one with no parent, decides the case and the
  outcome. A trace whose root run is missing from the file is left out and counted. Rows are
  in the order their root runs started.
- `--case-from` says what pairs a row with the same input in the other version. `example` is
  the dataset example's id. `metadata:KEY` is a value on the root run; an experiment copies
  each example's own metadata there as `ls_example_KEY`. `input` is a short key made from the
  root run's input, never the input's text, and it is also what a `--verdicts` file joins by.
  `none` reads every row as one input, which is right only if both versions saw the same mix
  of inputs, and the summary says so.
- `--outcome-from` says what counts as failed. `status`: the root run ended in error; an error
  in a step that was then retried does not fail the run. `feedback:KEY`: the key's score, read
  at `--cut X` with `--below` or `--above`. `metadata:KEY`: a value on the root run, failed
  when it is one of `--failed`, or a number read at `--cut`.
- A score decides the outcome even when the run ended in error. A root run with no score for
  the key has no outcome: it is never read as a pass or as a fail.
- LangSmith keeps each run's scores twice: as feedback records, and as statistics on the run
  that can lag behind the records. Give the feedback list beside the runs when you have it;
  the records win where both hold a key and fill the scores the statistics lack, and the
  summary counts how many they filled. A pull always reads the records.
- A key that only evaluators scored is kept as a score. A key given through the API or by
  hand in LangSmith is kept as feedback, and each key's source is recorded with the row.
- Also read, where the export holds them: how long the run took and its time to the first
  token, the tokens and cost of its model calls, its steps, its tool calls and retries, the
  lengths of its input and output, and the name of the exception and the kind of step a
  failure came from. What an export does not hold is recorded as not recorded, never as zero.
- `--select metadata:KEY=VALUE` keeps only the traces whose root run holds that value, for a
  file that holds more than one version.
- The start is the earliest run's start. LangSmith's times with no zone are UTC.

In a `trace.toml`, `[signals]` can stand in for the flags: `case_field` for `--case-from`,
`outcome_field` for `--outcome-from`, `score_field` for a feedback key, and `cut` for `--cut`,
which is used only where a score is read. `cost_field` names the field the cost is read from.
A flag you give wins. An `[[import]]` entry may name `langsmith:NAME` as its file:
`poisson-trace init` pulls it, and `poisson-trace doctor` never does.

## The worked example

The files are in `tests/fixtures/ingest/langsmith/`: two experiments on one dataset of ten
examples, run once each. The agent is a small stock desk (a retriever, a tool, a model call
and a parser), in a baseline and a candidate version, and an evaluator scores each answer
under the key `exact`. The commands run from the root of a clone and write the store to
`./store`.

The baseline, as the API returned it:

<!-- command -->
```
poisson-trace import langsmith tests/fixtures/ingest/langsmith/api/baseline.runs-v1.json \
  --store ./store --run old --case-from example --outcome-from feedback:exact --cut 0.5 --below
```

<!-- output exit=0 -->
```
ok  wrote run old to ./store: 10 rows, 10 cases, 1 repeat each; 6 passed, 4 failed

# Poisson Trace · import · old

## Summary

- Wrote: old into ./store, from baseline.runs-v1.json (langsmith): 10 tries on 10 inputs.
- Failures: 4 failed and 6 passed. A try counts as failed when its exact feedback score is below 0.5.
- Compared: Nothing yet. One import is one version.
- Next: Import the other version's file the same way: `poisson-trace import langsmith OTHER.json --store ./store --run OTHER --case-from example --outcome-from feedback:exact --cut 0.5 --below`.

## Before you act on this

- Its start time is the earliest span's start in the file.
- When you compare, choose the smallest drop that matters to you (--max-mde) before you look at any results; Trace then says whether these tries could catch it.

## What was written

- run written: old · store: ./store
- tool: langsmith
- file: baseline.runs-v1.json · sha256 7f3596ab9a24cdccd656954748a3ebff79b7b3912cb3dcc5a8751fa4a592a020
- declared: case_from example · outcome_from feedback:exact · cut 0.5 · side below · shapes ["run"]
- started: 2026-11-09T20:38:00.809772Z · from: earliest span
- rows 10 · cases 10 · repeats of a case: smallest 1, largest 1
- outcomes: met 6 · missed 4
- rows with no outcome: 0
- runs: 48
- traces: 10
- selected: 10
- feedback records: 0
- no root run: 0
- no case: 0
- scores the run statistics lacked: 0

In the command below, OLD and NEW are this run and the other version's run, imported into the same store, the older version first. X is the largest limit of detection you accept, as a share: 0.05 is five points.

next: poisson-trace fix-check OLD NEW --store ./store --event missed --inputs all --max-mde X  # old is OLD or NEW
```

The candidate, the same way:

<!-- command -->
```
poisson-trace import langsmith tests/fixtures/ingest/langsmith/api/candidate.runs-v1.json \
  --store ./store --run new --case-from example --outcome-from feedback:exact --cut 0.5 --below
```

<!-- excerpt exit=0 -->
```
- rows 10 · cases 10 · repeats of a case: smallest 1, largest 1
- outcomes: met 8 · missed 2
- rows with no outcome: 0
```

<!-- command -->
```
poisson-trace fix-check old new --store ./store --event missed \
  --inputs all --max-mde 0.2
```

<!-- excerpt exit=0 -->
```
too small to tell  too few tries to see a drop of any size
```

<!-- excerpt exit=0 -->
```
| version | runs | failed | failure share | did not fail |
|---|---|---|---|---|
| old | 10 | 4 | 40.0% | 60.0% |
| new | 10 | 2 | 20.0% | 80.0% |
```

Four failures down to two, on ten examples run once each, is too few to tell from chance. The
report's Guidance section says how many repeats of each example would be enough.

Where the baseline's failing runs stop:

<!-- command -->
```
poisson-trace where old --store ./store --event missed
```

<!-- excerpt exit=0 -->
```
ok  4 of 10 tries failed; their last steps: 1 at a tool call and 3 at another kind of step (not necessarily the cause)
```

The same baseline as the `langsmith` command exported it, a folder of traces, read by the root
run's status and paired by the example's own `case`:

<!-- command -->
```
poisson-trace import langsmith tests/fixtures/ingest/langsmith/cli/baseline-traces \
  --store ./store --run old-by-status --case-from metadata:ls_example_case --outcome-from status
```

<!-- excerpt exit=0 -->
```
ok  wrote run old-by-status to ./store: 10 rows, 10 cases, 1 repeat each; 9 passed, 1 failed
```

And as the experiment's page downloaded it:

<!-- command -->
```
poisson-trace import langsmith \
  tests/fixtures/ingest/langsmith/ui/trace-fixture-baseline-bbb64b8e.csv \
  --store ./store --run old-from-the-page --case-from example \
  --outcome-from feedback:exact --cut 0.5 --below
```

<!-- excerpt exit=0 -->
```
ok  wrote run old-from-the-page to ./store: 10 rows, 10 cases, 1 repeat each; 6 passed, 4 failed
```

## What this does not do

- It does not run LangSmith, your agent or any model. It reads runs LangSmith already holds,
  from files you exported or from one pull with your own key.
- It does not make a comparison out of one run. A fix check is two versions on the same
  inputs, each imported as its own run.
- It is tested on runs written by langsmith 0.14.17 and reads other versions by the same
  field names. It does not read the Parquet files of a bulk export, or threads.
- It keeps no prompt, input, output or reference text, no error message and no comment.
