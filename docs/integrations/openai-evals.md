# OpenAI Evals

You run an eval with OpenAI Evals on two versions of your model or prompt, and one gets more
samples right. This page shows how to find out whether the difference is real.

Poisson Trace reads the records `oaieval` already wrote. It runs no eval and calls no model.

## Install

```
pip install poisson-trace
```

Nothing here imports OpenAI Evals. Tested on records written by evals 3.0.1.post1.

## Save your results

Ask `oaieval` for its record, once per version:

```
oaieval my-completion-fn my-eval --record_path old.jsonl
```

Run the old version and the new one on the same samples. A sample that can be right on one
run and wrong on the next is worth running more than once per version: each run's `match`
events of one sample are read as its repeats.

## Import and compare

One import is one version. Each import writes one new run into a store in Prove's format;
`poisson-trace fix-check` then compares the two runs.

```
poisson-trace import openai-evals FILE [FILE ...] --store ROOT --run NAME
        [--started ISO-8601] [--json]
```

Nothing needs declaring: the record says what was right.

- A record is JSON Lines: a `spec` line, a `final_report` line, then events. Each `match`
  event is one row: `met` when it was correct, `missed` when it was not. Its case is its
  `sample_id`; the `match` events of one sample are its repeats, in the order of their
  `event_id`, whatever order the file holds them in.
- Other events (`sampling`, `metrics` and the rest) are counted in the summary and are not
  rows. A record with no `spec` line or no `match` event is refused, and so is a line that is
  not JSON or a `match` whose `correct` is not true or false, naming the file and the line.
- The start is the spec's `created_at`. `oaieval` writes it with no zone, so it is read as
  UTC, and the summary says so. `--started` gives it instead, with its zone.
- The eval's name and its completion functions are recorded with what was declared.

## The worked example

The records are in `tests/fixtures/ingest/openai-evals/`, written by evals 3.0.1.post1 with
its `dummy` completion function on the bundled `test-match` eval: no model, no key. `dummy`
answers every sample the same way, so both records hold three samples, all of them not
correct. The commands run from the root of a clone and write the store to `./store`.

<!-- command -->
```
poisson-trace import openai-evals tests/fixtures/ingest/openai-evals/old.jsonl \
  --store ./store --run old
```

<!-- output exit=0 -->
```
ok  wrote run old to ./store: 3 rows, 3 cases, 1 repeat each; 0 passed, 3 failed

# Poisson Trace · import · old

## Summary

- Wrote: old into ./store, from old.jsonl (openai-evals): 3 tries on 3 inputs.
- Failures: 3 failed and 0 passed. A try counts as failed when its match event was not correct.
- Compared: Nothing yet. One import is one version.
- Next: Import the other version's file the same way: `poisson-trace import openai-evals OTHER.jsonl --store ./store --run OTHER`.

## Before you act on this

- Its start time is a time the tool wrote in the file (the spec's created_at carries no zone, so it was read as UTC).
- When you compare, choose the smallest drop that matters to you (--max-mde) before you look at any results; Trace then says whether these tries could catch it.

## What was written

- run written: old · store: ./store
- tool: openai-evals
- file: old.jsonl · sha256 8c25e2fa6ab2e9e988b488b1992664408d51895dfa118495fe26c048867b0794
- declared: eval_name test-match.s1.simple-v0 · completion_fns ["dummy"]
- started: 2026-10-07T04:24:29.594390Z · from: file (the spec's created_at carries no zone, so it was read as UTC)
- rows 3 · cases 3 · repeats of a case: smallest 1, largest 1
- outcomes: met 0 · missed 3
- rows with no outcome: 0
- match events: 3

In the command below, OLD and NEW are this run and the other version's run, imported into the same store, the older version first. X is the largest limit of detection you accept, as a share: 0.05 is five points.

next: poisson-trace fix-check OLD NEW --store ./store --event missed --inputs all --max-mde X  # old is OLD or NEW
```

<!-- command -->
```
poisson-trace import openai-evals tests/fixtures/ingest/openai-evals/new.jsonl \
  --store ./store --run new
```

<!-- excerpt exit=0 -->
```
- rows 3 · cases 3 · repeats of a case: smallest 1, largest 1
- outcomes: met 0 · missed 3
```

<!-- command -->
```
poisson-trace fix-check old new --store ./store --event missed \
  --inputs all --max-mde 0.5
```

<!-- excerpt exit=0 -->
```
too small to tell  too few tries to see a drop of any size
```

<!-- excerpt exit=0 -->
```
| version | runs | failed | failure share | did not fail |
|---|---|---|---|---|
| old | 3 | 3 | 100.0% | 0.0% |
| new | 3 | 3 | 100.0% | 0.0% |
```

The two records fail every sample alike, and three samples run once are too few to show a
change of any size either way.

## From `poisson-trace init`

`poisson-trace init`, run in a folder with no Prove store under it, lists the OpenAI Evals
records it finds (a `.jsonl` file whose first line is a `spec` naming the eval) and prints the
line that imports each. It does not import them itself yet. With `--no-import` it writes
`trace.toml` with no store:

<!-- command -->
```
mkdir -p from-evals && cp tests/fixtures/ingest/openai-evals/*.jsonl from-evals/
cd from-evals && poisson-trace init --yes --no-import
```

<!-- excerpt exit=0 -->
```
  found 2 result files:
    1) new.jsonl                 an OpenAI Evals record of test-match.s1.simple-v0
    2) old.jsonl                 an OpenAI Evals record of test-match.s1.simple-v0
```

## What this does not do

- It does not run OpenAI Evals, an eval or a completion function. It reads the records.
- It does not make a comparison out of one run: a fix check is two versions on the same
  inputs, side by side.
- It reads records from versions of OpenAI Evals other than 3.0.1.post1 by the fields they
  share, and no test runs another version.
- It keeps no prompt, answer, expected or sampled text: of a `match` event it keeps its
  sample, its outcome, its score and the length of its answer, and nothing of the answer, the
  expected answer, the options or the spec's run configuration.
