# promptfoo

You test two prompts with promptfoo and one of them passes more of your tests. This page shows
how to find out whether the difference is real or the luck of a few tests.

Poisson Trace reads the results file promptfoo already wrote. It runs no prompt and calls no
model.

## Install

<!-- skip reason="installs from the package index, which the docs check does not reach" -->
```
pip install poisson-trace
```

Nothing here imports promptfoo. Tested on files written by promptfoo 0.120.19.

## Save your results

Ask promptfoo for its results as JSON:

<!-- skip reason="runs promptfoo, which Trace never does" -->
```
promptfoo eval -o results.json
```

`-o results.jsonl` writes the same results one per line, and reads the same. One file holds
every prompt by every provider by every test, so the old prompt and the new one can sit in
the same file: each import picks one. promptfoo's `.csv` sets the prompts side by side under
repeated column names, and is refused, pointing at the JSON export. If a test can pass on one
run and fail on the next, run the evaluation more than once, each run to a file of its own,
and give one import a version's files together: its results are read as repeats.

## Import and compare

One import is one version: one prompt, from one provider. Each import writes one new run into
a store in Prove's format; `poisson-trace fix-check` then compares the two runs.

<!-- skip reason="the form of the command: the words in capitals are yours to fill in" -->
```
poisson-trace import promptfoo FILE [FILE ...] --store ROOT --run NAME
        [--prompt ( LABEL | N )] [--provider ID]
        --case ( var:NAME | test )
        [--outcome ( success | score --cut X ( --below | --above ) )]
        [--started ISO-8601] [--verdicts FILE] [--json]
```

- `--prompt` names the version by its label, or by its number in the order the file holds
  the prompts, the first being `1`. A file with one prompt needs none; a file with several and no
  `--prompt` is refused, listing them. When promptfoo is given no label, it makes one from the
  prompt itself, so the label printed may be your prompt's template; the filled-in prompts are
  kept nowhere. `--provider` names the provider by its id when the file has more than one.
- `--case var:NAME` identifies a test by the test variable `NAME`; `--case test` by the
  test's position in the file (`test:0`, `test:1`, ...), which holds only while both versions
  come from the same tests in the same order. Results that share a case are repeats of it, in
  the order read. A result without the variable named refuses the import.
- A result is `missed` when promptfoo did not pass it and `met` when it did (`--outcome
  success`, the default). `--outcome score --cut X --below` reads the result's score instead:
  a score under the cut missed it, a score equal to it met it.
- A result promptfoo marks as an error, not as a failed assertion, has no outcome: the summary
  counts it, and its error's text says only what kind of failure it was (a timeout, a rate
  limit, a context overflow, else a crash). The text is not kept.
- The start is the JSON file's `timestamp`. A `.jsonl` file carries none, so it is the file's
  modification time unless `--started` gives it, with its zone. The summary prints which.
- `--verdicts FILE` joins outcomes given outside promptfoo onto the rows: a `.csv` with the
  columns `case`, `input`, `outcome` (`pass` or `fail`), `score` and `failure_kind`, or a
  `.jsonl` with the same keys. A row of it joins every try of the case it names. It fills
  what the files left out, a try with no outcome above all; a verdict that differs from
  what the files recorded refuses the import, naming the case, and nothing is written.
- The summary counts the file's results per prompt and per provider, so a version picked by
  mistake shows.

## The worked example

The files are in `tests/fixtures/ingest/promptfoo/`, written by promptfoo 0.120.19 with its
`echo` provider, which answers with the prompt itself: no model, no key. `promptfooconfig.yaml`
beside them is the recipe. Two prompts, `old: {{text}}` and `new: {{text}} with the word
banana`, are run on four tests, each asserting that the answer contains `banana`. The old
prompt fails two of them. The commands run from the root of a clone and write the store to
`./store`.

<!-- command -->
```
poisson-trace import promptfoo tests/fixtures/ingest/promptfoo/results.json \
  --store ./store --run old --prompt 1 --case var:case
```

<!-- output exit=0 -->
```
ok  wrote run old to ./store: 4 rows, 4 cases, 1 repeat each; 2 passed, 2 failed

# Poisson Trace · import · old

## Summary

- Wrote: old into ./store, from results.json (promptfoo): 4 tries on 4 inputs.
- Failures: 2 failed and 2 passed. A try counts as failed when promptfoo marked it as not passed.
- Compared: Nothing yet. One import is one version.
- Next: Import the other version's prompt the same way: `poisson-trace import promptfoo results.json --store ./store --run OTHER --prompt PROMPT --provider echo --case var:case`.

## Before you act on this

- Its start time is a time the tool wrote in the file.
- When you compare, choose the smallest drop that matters to you (--max-mde) before you look at any results; Trace then says whether these tries could catch it.

## What was written

- run written: old · store: ./store
- tool: promptfoo
- file: results.json · sha256 97c14a69b337e987cba953997fea816e7894a88465f8c318604c6e4b85dd07a8
- declared: case var:case · prompt old: {{text}} · provider echo · outcome success
- started: 2026-10-07T04:22:52.124000Z · from: file
- rows 4 · cases 4 · repeats of a case: smallest 1, largest 1
- outcomes: met 2 · missed 2
- rows with no outcome: 0
- results of prompt 1 (old: {{text}}): 4
- results of prompt 2 (new: {{text}} with the word banana): 4
- results of provider echo: 8

In the command below, OLD and NEW are this run and the other version's run, imported into the same store, the older version first. X is the largest limit of detection you accept, as a share: 0.05 is five points.

next: poisson-trace fix-check OLD NEW --store ./store --event missed --inputs all --max-mde X  # old is OLD or NEW
```

The new prompt, picked by its label:

<!-- command -->
```
poisson-trace import promptfoo tests/fixtures/ingest/promptfoo/results.json \
  --store ./store --run new --prompt "new: {{text}} with the word banana" --case var:case
```

<!-- excerpt exit=0 -->
```
- outcomes: met 4 · missed 0
- rows with no outcome: 0
- results of prompt 1 (old: {{text}}): 4
- results of prompt 2 (new: {{text}} with the word banana): 4
- results of provider echo: 8
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
| old | 4 | 2 | 50.0% | 50.0% |
| new | 4 | 0 | 0.0% | 100.0% |
```

Two failures gone out of four tests is no evidence either way: four tests run once each cannot
show a drop of any size, and the report says how many repeats would.

The CSV of the same evaluation is refused:

<!-- command -->
```
poisson-trace import promptfoo tests/fixtures/ingest/promptfoo/results.csv \
  --store ./store --run old-csv --prompt 1 --case var:case
```

<!-- output exit=1 -->
```
error: tests/fixtures/ingest/promptfoo/results.csv is promptfoo's CSV, which sets the prompts side by side under repeated column names; export the JSON instead (promptfoo eval -o results.json) and import that
```

## From `poisson-trace init`

`poisson-trace init`, run in a folder with no Prove store under it, lists the promptfoo files
it finds (a `.json` file whose `results.results` holds promptfoo's results, or a `.jsonl` file
whose first line is one) and prints the line that imports each. It does not import them
itself: one file holds both versions, and init imports one run per file. With `--no-import`
it writes `trace.toml` with no store:

<!-- command -->
```
mkdir -p from-promptfoo && cp tests/fixtures/ingest/promptfoo/results.json from-promptfoo/
cd from-promptfoo && poisson-trace init --yes --no-import
```

<!-- excerpt exit=0 -->
```
  found 1 result file:
    1) results.json              promptfoo results, 8 results of 2 prompts
```

<!-- excerpt exit=0 -->
```
    poisson-trace import promptfoo results.json --store trace-store --run results --prompt PROMPT --case var:case
```

Run that line once for each prompt, each under a name of its own, then `poisson-trace init
--force --store trace-store`.

## What this does not do

- It does not run promptfoo, a prompt or a provider. It reads the results file.
- It does not make a comparison out of one run: a fix check is two versions on the same
  inputs, side by side.
- It reads files from versions of promptfoo other than 0.120.19 by the fields they share, and
  no test runs another version.
- It keeps no prompt, answer, expected or sampled text: of a result it keeps its case, its
  outcome, its scores, its time, its token counts and its cost, and nothing of a variable but
  the case, an error's text or a grader's reason.
