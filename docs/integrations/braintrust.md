# Braintrust

You ran two versions of an agent as Braintrust experiments on the same dataset, and one scored
better. This page shows how to read both into Poisson Trace, ask whether the difference is
real, and see at which step the failing cases stop.

Poisson Trace reads the experiments Braintrust already holds. It runs no agent and calls no
model, and it keeps no prompt, input, output or error text.

## Install

<!-- skip reason="installs from the package index, which the docs check does not reach" -->
```
pip install poisson-trace
```

Nothing here imports Braintrust's packages. Tested on experiments written by braintrust 0.49.3
(the Python SDK), as Braintrust's API returns them and as an experiment's page downloads them.

## Get your experiment out

There are two ways, and both read to the same cases and outcomes.

### Pull it with your key

Put your key in `BRAINTRUST_API_KEY` and name the experiment where the files would go, as
`braintrust:PROJECT/EXPERIMENT`: the project's name and the experiment's name as Braintrust
shows them, the project before the first slash.

<!-- skip reason="needs your own key and your own project: the words in capitals are yours to fill in" -->
```
export BRAINTRUST_API_KEY=...
poisson-trace import braintrust braintrust:PROJECT/EXPERIMENT --store ./store --run old \
  --case-from record --outcome-from score:correct --cut 0.5 --below
```

The pull makes two kinds of request and no other: the project's experiments
(`GET /v1/experiment`), to find the one you named, and that experiment's events
(`GET /v1/experiment/{id}/fetch`, a page at a time). It saves a raw copy first, in
`./store/.poisson/raw/braintrust/old/`, as two files: `raw.jsonl`, the events, one a line;
and `pull.json`, which says what was pulled, when, and the file's digest. Then it reads that
folder as it reads any file.

- The experiment is found however many the project holds: Braintrust lists 1,000 experiments
  an answer, and the pull asks for the next 1,000 experiments until it has them all.
- The pull reads every event of the experiment, however old. It sends nothing that narrows
  them, and it keeps asking for the next page until one comes back empty: a page shorter than
  asked is not the end.
- The inputs, outputs and expected values are measured and left out of the raw copy, and an
  error keeps only the name of its exception. Also left out: `context`, which holds the paths
  and line numbers of the machine that ran the experiment; `audit_data`, which repeats the
  metadata and says who wrote it; any comment; and the metadata of every span under the root
  but for the model's name and provider, since a scorer's metadata can hold its reasoning and
  a model call's its prompt. The root span's own metadata is kept. `--keep-raw-text` saves the
  events as Braintrust returned them instead.
- A raw copy is never written over. To read the same events again, with another cut or
  another case, import the folder: `poisson-trace import braintrust
  ./store/.poisson/raw/braintrust/old --store ./store --run old-again ...`. That asks
  Braintrust nothing and needs no key.
- Only `BRAINTRUST_API_KEY` is read. The key goes to Braintrust as a bearer token and nowhere
  else: it is not printed and not written to any file.
- `BRAINTRUST_API_URL` names another host for every request, such as your company's own data
  plane. It must be an https address, or http on this machine.
- `--page-size N` asks for N events per request, from 1 to 1000 (the default is 1000). When
  Braintrust answers that it is being asked too often, the pull waits as long as the answer
  says and asks again.
- Without the key, with a key Braintrust refuses, or with a name no experiment of the project
  has, the import stops with one `error:` line and exit code 1, and nothing is saved. A
  failure part way through a pull exits 3, and nothing is saved either.

### Download it from the experiment's page

The page downloads an experiment as JSON or as CSV, with one row for each case. A row holds
the case's input and output, its scores, its error, and its metrics rolled up: its start and
end, its tokens and cost, and how many model calls it made. It holds no steps, so
`poisson-trace where` has no step to place a failure on.

The download holds no id: not the experiment's, not a row's, and not the dataset record's. So
two versions downloaded from the page pair by the input, with `--case-from input`, and one
import reads one such file: two downloads cannot be told from one experiment given twice.

The API's answers are read too, saved as they came: the body of the fetch, or of a BTQL query
for an experiment's `spans`, `traces` or `summary`. Pages of one fetch are given together. One
import reads one export of an experiment: giving the same event twice, or the page's download
beside an answer of the API, is refused.

## Import and compare

One import is one version. Each import writes one new run into a store in Prove's format;
`poisson-trace fix-check` then compares the two runs.

<!-- skip reason="the form of the command: the words in capitals are yours to fill in" -->
```
poisson-trace import braintrust FILE [FILE ...] --store ROOT --run NAME
        --case-from ( record | metadata:KEY | input | none )
        --outcome-from ( error | score:KEY | metadata:KEY )
        [--cut X ( --below | --above )] [--failed VALUE ...]
        [--select metadata:KEY=VALUE ...]
        [--keep-raw-text] [--page-size N]
        [--started ISO-8601] [--verdicts FILE] [--json]
```

- One trace is one row, and its root span, the one with no parent, decides the case and the
  outcome. A trace whose root span is missing from the file is left out and counted. Rows are
  in the order their root spans started.
- `--case-from` says what pairs a row with the same input in the other version. `record` is
  the id of the dataset record the case was run on, which the API's answers carry and the
  page's downloads do not. `metadata:KEY` is a value on the root span. `input` is a short key
  made from the root span's input, never the input's text; every export carries it, and it is
  also what a `--verdicts` file joins by. `none` reads every row as one input, which is right
  only if both versions saw the same mix of inputs, and the summary says so.
- `--outcome-from` says what counts as failed. `error`: the root span ended in error; an error
  in a step that was then retried does not fail the case. `score:KEY`: the key's score, read
  at `--cut X` with `--below` or `--above`. `metadata:KEY`: a value on the root span, failed
  when it is one of `--failed`, or a number read at `--cut`.
- Braintrust runs no scorer on a case whose task raised, and the task never got to write its
  metadata. So a case that ended in error has no score and no metadata, in every export. Read
  by a score it has no outcome: it is never read as a pass or as a fail, and the summary
  counts it. Read by a metadata key it has no case or no outcome. The record's id and the
  input do identify it.
- In the API's answers each score is on its own span under the root. A key's value is the mean
  of the spans of the trace that hold it. A classification is kept as feedback, by the ids of
  its items. Tags are read only for the name of a failure kind, and comments are not read.
- Also read, where the export holds them: how long the case took and its time to the first
  token, the tokens and cost of its model calls, its steps, its tool calls and retries, the
  lengths of its input and output, and the name of the exception and the kind of step a
  failure came from. The spans that score a case are not counted as its steps. What an export
  does not hold is recorded as not recorded, never as zero.
- `--select metadata:KEY=VALUE` keeps only the traces whose root span holds that value.
- The start is the earliest span's start.

In a `trace.toml`, `[signals]` can stand in for the flags: `case_field` for `--case-from`,
`outcome_field` for `--outcome-from`, `score_field` for a score's key (`KEY`, `score:KEY` or
`scores.KEY`), and `cut` for `--cut`, which is used only where a score is read. `cost_field`
names the metric the cost is read from (`estimated_cost` unless you say otherwise). A flag you
give wins. An `[[import]]` entry may name `braintrust:PROJECT/EXPERIMENT` as its file:
`poisson-trace init` pulls it, and `poisson-trace doctor` never does.

## The worked example

The files are in `tests/fixtures/ingest/braintrust/`: two experiments on one dataset of ten
records, run once each. The agent is a small stock desk (a lookup, a tool, a model call and a
step that reads the reply), in a baseline and a candidate version, and a scorer scores each
answer under the key `exact`. The commands run from the root of a clone and write the store to
`./store`.

The baseline, as the API returned it:

<!-- command -->
```
poisson-trace import braintrust tests/fixtures/ingest/braintrust/api/slice-baseline.fetch.json \
  --store ./store --run old --case-from record --outcome-from score:exact --cut 0.5 --below
```

<!-- output exit=0 -->
```
ok  wrote run old to ./store: 10 rows, 10 cases, 1 repeat each; 6 passed, 3 failed, 1 with no outcome

# Poisson Trace · import · old

## Summary

- Wrote: old into ./store, from slice-baseline.fetch.json (braintrust): 10 tries on 10 inputs.
- Failures: 3 failed and 6 passed; 1 had no outcome. A try counts as failed when its exact score is below 0.5.
- Compared: Nothing yet. One import is one version.
- Next: Import the other version's file the same way: `poisson-trace import braintrust OTHER.json --store ./store --run OTHER --case-from record --outcome-from score:exact --cut 0.5 --below`.

## Before you act on this

- Its start time is the earliest span's start in the file.
- When you compare, choose the smallest drop that matters to you (--max-mde) before you look at any results; Trace then says whether these tries could catch it.

## What was written

- run written: old · store: ./store
- tool: braintrust
- file: slice-baseline.fetch.json · sha256 a774c0fa94c71f11467802b479c93d2e4e37b8d4a5db1827a00326a38fd557d9
- declared: case_from record · outcome_from score:exact · cut 0.5 · side below · shapes ["span"]
- started: 2026-11-09T20:24:15.158221Z · from: earliest span
- rows 10 · cases 10 · repeats of a case: smallest 1, largest 1
- outcomes: met 6 · missed 3
- rows with no outcome: no score 1
- events: 85
- traces: 10
- selected: 10
- no root span: 0
- no case: 0

In the command below, OLD and NEW are this run and the other version's run, imported into the same store, the older version first. X is the largest limit of detection you accept, as a share: 0.05 is five points.

next: poisson-trace fix-check OLD NEW --store ./store --event missed --inputs all --max-mde X  # old is OLD or NEW
```

One case ended in error, so it has no score and no outcome. The candidate, the same way:

<!-- command -->
```
poisson-trace import braintrust tests/fixtures/ingest/braintrust/api/slice-candidate.fetch.json \
  --store ./store --run new --case-from record --outcome-from score:exact --cut 0.5 --below
```

<!-- excerpt exit=0 -->
```
- rows 10 · cases 10 · repeats of a case: smallest 1, largest 1
- outcomes: met 8 · missed 1
- rows with no outcome: no score 1
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
| old | 8 | 3 | 37.5% | 62.5% |
| new | 8 | 1 | 12.5% | 87.5% |
```

Each version has one case with no outcome, and they are different cases, so the check counts
the eight inputs that have an outcome on both sides and says which two it left out. Three
failures down to one, on eight inputs run once each, is too few to tell from chance. The
report's Guidance section says how many repeats of each input would be enough.

Where the baseline's failing cases stop:

<!-- command -->
```
poisson-trace where old --store ./store --event missed
```

<!-- excerpt exit=0 -->
```
ok  3 of 9 tries failed; each one's last step was another kind of step (not necessarily the cause)
```

The same baseline as the experiment's page downloaded it as JSON, read by the root span's
error and paired by the input:

<!-- command -->
```
poisson-trace import braintrust tests/fixtures/ingest/braintrust/ui/slice-baseline.json \
  --store ./store --run old-by-error --case-from input --outcome-from error
```

<!-- excerpt exit=0 -->
```
ok  wrote run old-by-error to ./store: 10 rows, 10 cases, 1 repeat each; 9 passed, 1 failed
```

And the candidate as the page downloaded it as CSV:

<!-- command -->
```
poisson-trace import braintrust tests/fixtures/ingest/braintrust/ui/slice-candidate.csv \
  --store ./store --run new-from-the-page --case-from input \
  --outcome-from score:exact --cut 0.5 --below
```

<!-- excerpt exit=0 -->
```
ok  wrote run new-from-the-page to ./store: 10 rows, 10 cases, 1 repeat each; 8 passed, 1 failed, 1 with no outcome
```

## What this does not do

- It does not run Braintrust, your agent or any model. It reads experiments Braintrust already
  holds, from files you saved or from one pull with your own key.
- It does not make a comparison out of one run. A fix check is two versions on the same
  inputs, each imported as its own run.
- It is tested on experiments written by braintrust 0.49.3 and reads other versions by the
  same field names. It does not read a BTQL answer saved as Parquet, project logs outside an
  experiment, or datasets.
- It keeps no prompt, input, output or expected text, no error message and no comment.
