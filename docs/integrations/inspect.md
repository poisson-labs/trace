# Inspect

You run an Inspect AI task on two versions of your model or agent, and one scores better. This
page shows how to find out whether the difference between the two logs is real.

Poisson Trace reads the logs Inspect already wrote. It runs no task and calls no model.

## Install

<!-- skip reason="installs from the package index, which the docs check does not reach" -->
```
pip install poisson-trace
```

Nothing here imports Inspect. Tested on logs written by inspect_ai 0.3.277.

## Reading .eval logs

Inspect's default log is a `.eval` file: a zip whose members are Zstandard-compressed, which
Python's own `zipfile` cannot read before Python 3.14. Reading one needs the `zstandard`
package, which this extra installs:

<!-- skip reason="installs from the package index, which the docs check does not reach" -->
```
pip install 'poisson-trace[inspect]'
```

Without it, a `.eval` file is refused in one line, which names the extra and the other way:
convert the log to JSON with Inspect itself, `inspect log convert FILE --to json`, and import
that. A `.json` log needs nothing beyond the one install line.

A log is read whole into memory, so a log over 200 MB is refused, naming its size, before any
of it is read.

## Save your results

Inspect writes a log for every run of a task, in `./logs` unless told otherwise. Run the old
version and the new one on the same samples. Give the task `epochs` to run each sample more
than once per version: one run per sample is the smallest design there is. Run with
`--log-format json` for `.json` logs, or keep the default `.eval`.

## Import and compare

One import is one version. Each import writes one new run into a store in Prove's format;
`poisson-trace fix-check` then compares the two runs.

<!-- skip reason="the form of the command: the words in capitals are yours to fill in" -->
```
poisson-trace import inspect FILE [FILE ...] --store ROOT --run NAME
        [--scorer NAME] [--outcome ( correct | score --cut X ( --below | --above ) | value --failed V [--failed V ...] )]
        [--started ISO-8601] [--verdicts FILE] [--json]
```

- A sample is one row; its case is its `id`. Its epochs are its repeats, in epoch order,
  whatever order the log holds them in.
- The outcome is the scorer's value. `--outcome correct`, the default, reads Inspect's
  letters: `C` is `met`, and `I`, `P` (partial) and `N` (no answer) are `missed`; any other
  value is refused, listing the values the log holds. `--outcome score --cut X --below` reads
  a number at a cut. `--outcome value --failed V` names the values that mean a failure, for a
  scorer with words of its own.
- A sample holding several scores needs `--scorer NAME`; the import is refused, listing the
  scorers, without it. The summary names the scorer read.
- A log whose status is `error` is refused with the first line of its error. A sample with an
  error has no outcome: the summary counts it, and its error's text says only what kind of
  failure it was (a timeout, a rate limit, a context overflow, else a crash). The text is not
  kept.
- The start is the log's `eval.created`; `--started` gives it instead, with its zone. The
  model and the task are recorded with what was declared.
- `--verdicts FILE` joins outcomes given outside Inspect onto the rows: a `.csv` with the
  columns `case`, `input`, `outcome` (`pass` or `fail`), `score` and `failure_kind`, or a
  `.jsonl` with the same keys. A row of it joins every try of the case it names. It fills
  what the files left out, a try with no outcome above all; a verdict that differs from
  what the files recorded refuses the import, naming the case, and nothing is written.
- The file is a `.eval` or a `.json` log, told by its extension. A folder holding
  `header.json` beside `samples/`, as a `.eval` unpacked, is read as that log.

## The worked example

The logs are in `tests/fixtures/ingest/inspect/`, written by inspect_ai 0.3.277 with its
`mockllm/model`, which answers from a fixed list: no model, no key. `fixture_task.py` and
`run_fixture.py` beside them are the recipe. Three samples, each run for two epochs and scored
by `includes`: the `.eval` log is the old version, the `.json` log the new. The commands run
from the root of a clone and write the store to `./store`.

<!-- command -->
```
poisson-trace import inspect \
  tests/fixtures/ingest/inspect/2026-10-07T04-23-47-00-00_trace-fixture_CV3jq8f7FTjwkaYb3zj3m2.eval \
  --store ./store --run old
```

<!-- output exit=0 -->
```
ok  wrote run old to ./store: 6 rows, 3 cases, 2 repeats each; 3 passed, 3 failed

# Poisson Trace · import · old

## Summary

- Wrote: old into ./store, from 2026-10-07T04-23-47-00-00_trace-fixture_CV3jq8f7FTjwkaYb3zj3m2.eval (inspect): 6 tries on 3 inputs.
- Failures: 3 failed and 3 passed. A try counts as failed when its includes score is not C (I, P and N count as failed).
- Compared: Nothing yet. One import is one version.
- Next: Import the other version's file the same way: `poisson-trace import inspect OTHER.eval --store ./store --run OTHER --scorer includes`.

## Before you act on this

- Its start time is a time the tool wrote in the file.
- When you compare, choose the smallest drop that matters to you (--max-mde) before you look at any results; Trace then says whether these tries could catch it.

## What was written

- run written: old · store: ./store
- tool: inspect
- file: 2026-10-07T04-23-47-00-00_trace-fixture_CV3jq8f7FTjwkaYb3zj3m2.eval · sha256 4d9922029b8b960f9ff1a5d4cf75df6900fb88921922d0ac2c454aca97ba69b0
- declared: scorer includes · outcome correct · model mockllm/model · task trace_fixture
- started: 2026-10-07T04:23:47Z · from: file
- rows 6 · cases 3 · repeats of a case: smallest 2, largest 2
- outcomes: met 3 · missed 3
- rows with no outcome: 0
- samples: 3
- epochs: 2
- samples that errored: 0

In the command below, OLD and NEW are this run and the other version's run, imported into the same store, the older version first. X is the largest limit of detection you accept, as a share: 0.05 is five points.

next: poisson-trace fix-check OLD NEW --store ./store --event missed --inputs all --max-mde X  # old is OLD or NEW
```

<!-- command -->
```
poisson-trace import inspect \
  tests/fixtures/ingest/inspect/2026-10-07T04-23-51-00-00_trace-fixture_2nSEDuHHzKiTUjJW3kXknY.json \
  --store ./store --run new
```

<!-- excerpt exit=0 -->
```
- declared: scorer includes · outcome correct · model mockllm/model · task trace_fixture
- started: 2026-10-07T04:23:51Z · from: file
- rows 6 · cases 3 · repeats of a case: smallest 2, largest 2
- outcomes: met 5 · missed 1
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
| old | 6 | 3 | 50.0% | 50.0% |
| new | 6 | 1 | 16.7% | 83.3% |
```

Three samples run twice are too few to tell a drop from chance, and the report says how many
epochs would.

## From `poisson-trace init`

`poisson-trace init`, run in a folder with no Prove store under it, lists the Inspect logs it
finds (a `.eval` zip holding `header.json`, or a `.json` log with Inspect's `eval` block) and
prints the line that imports each. It does not import them itself yet. With `--no-import` it
writes `trace.toml` with no store:

<!-- command -->
```
mkdir -p from-inspect && cp tests/fixtures/ingest/inspect/*.eval tests/fixtures/ingest/inspect/*.json from-inspect/
cd from-inspect && poisson-trace init --yes --no-import
```

<!-- excerpt exit=0 -->
```
  found 2 result files:
    1) 2026-10-07T04-23-47-00-00_trace-fixture_CV3jq8f7FTjwkaYb3zj3m2.eval  an Inspect .eval log, 6 samples
    2) 2026-10-07T04-23-51-00-00_trace-fixture_2nSEDuHHzKiTUjJW3kXknY.json  an Inspect .json log of the task trace_fixture, 6 samples
```

## What this does not do

- It does not run Inspect, a task or a model. It reads the logs.
- It does not make a comparison out of one run: a fix check is two versions on the same
  inputs, side by side.
- It reads logs from versions of Inspect other than 0.3.277 by the fields they share, and no
  test runs another version.
- It keeps no prompt, answer, expected or sampled text: of a sample it keeps its id, its
  epoch, its scores, its times, its token counts and its tool calls' names and errors' types,
  and nothing of its input, target, messages, output or a score's explanation.
