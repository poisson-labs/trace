# Tables

Your tool or your own script saves a table of results, one row per test case and run, and you
compare two versions by their pass rates. This page shows how to find out whether the
difference between them is real.

Poisson Trace reads the table as it is. It runs nothing and calls no model.

## Install

<!-- skip reason="installs from the package index, which the docs check does not reach" -->
```
pip install poisson-trace
```

Nothing here imports the tool that wrote the table. Tested on CSV written by Python's `csv`
module, and on JSON Lines, JSON and Parquet written by Python and pandas in the tests.

## Save your results

Save one table per version, with one row for each time a case was run. It needs a column that
names each case and is the same in both versions, and a column that gives the row's result:
an outcome word (`passed`, `failed`, `error`), or a score. Run the old version and the new one
on the same cases. If you can, run each case more than once per version: one run per case is
the smallest design there is.

## Import and compare

One import is one version. Each import reads one result column and writes one new run into a
store in Prove's format; `poisson-trace fix-check` then compares the two runs.

<!-- skip reason="the form of the command: the words in capitals are yours to fill in" -->
```
poisson-trace import table FILE [FILE ...] --store ROOT --run NAME
        --case-column COLUMN
        ( --outcome-column COLUMN --failed VALUE [--failed VALUE ...]
        | --score-column COLUMN --cut X ( --below | --above ) )
        [--started ISO-8601] [--verdicts FILE] [--json]
```

Nothing has a default but the start time. You say which column identifies a case, which column
gives the result, and what counts as a failure.

- `FILE` is `.csv`, `.jsonl`, `.json` (a list of objects) or `.parquet`, told by its
  extension; `.gz` is read on the first three. Any other extension is refused, and so is a
  file that is not what its extension says.
- `--outcome-column` reads the result as words. A cell equal to a `--failed` value is
  `missed`; any other cell is `met`. Equal means the same text: `FAIL` is not `fail`, and
  neither is ` fail` with a space. A true, false or number in a JSON or Parquet table is
  compared as JSON writes it, so `--failed false` or `--failed 1`; but a column of whole numbers
  that pandas saved with a missing value holds decimals, and its `1` is `1.0`. The summary counts
  the rows each `--failed` value matched, so a value that matched nothing shows as `0`.
- `--score-column` reads the result as a number at the cut you declare, with exactly one side:
  `--cut 0.5 --below` counts a score under 0.5 as missed. A score equal to the cut met it.
  A cell that holds no number has no outcome; it is never read as a score of 0.
- An empty cell (empty text, `null`, a key a JSON row leaves out) has no outcome. The summary
  counts it, and Trace leaves it out and counts it in the header of its report.
- Giving neither form, both, or one form's flags beside the other's is a wrong command line
  (exit 2).
- `--case-column` is the column that identifies a case. Rows that share a value are repeats
  of that case, in the order read, and several files given to one import are read as one
  version, in the order given. A row with no value there refuses the whole import, and the
  refusal names the row. In a CSV the value is the text as written: `007` and `7` are two
  cases.
- A column the file lacks is refused, and the refusal lists the file's columns; so is a column
  the file names twice.
- `--started` is when that version's run started, with its zone. Without it the first
  file's modification time is used, and the summary says which of the two it was.
- `--verdicts FILE` joins outcomes given outside the table onto the rows: a `.csv` with the
  columns `case`, `input`, `outcome` (`pass` or `fail`), `score` and `failure_kind`, or a
  `.jsonl` with the same keys. A row of it joins every try of the case it names. It fills
  what the files left out, a try with no outcome above all; a verdict that differs from
  what the files recorded refuses the import, naming the case, and nothing is written.
- `--store` may be left out when a `trace.toml` in the current folder (or the file `--config
  PATH` names) names a store: the import writes into it. `--store NAME` takes the store that
  file names so.

`poisson-trace init` offers a table with a column named like a Ragas metric to the
[Ragas reader](ragas.md), by its score, and not to this one; `poisson-trace import table` reads
any table you name.

## The worked example

The two files are in `tests/fixtures/ingest/table/`. They are one agent run twice, 56 minutes
apart, with nothing changed: 164 HumanEval problems at two temperatures, 32 runs of each,
10,496 rows per file, the same runs as the [DeepEval page](deepeval.md)'s example. Each row
is one stored run: `case` is the problem and the temperature, and `outcome` is `passed`,
`failed_assertion` or `crashed`. The tables were written from the stored runs with Python's
`csv` module; `make.py` beside them is the recipe.

The commands run from the root of a clone and write the store to `./store`.

<!-- command -->
```
poisson-trace import table tests/fixtures/ingest/table/humaneval-a.csv \
  --store ./store --run humaneval-a --case-column case \
  --outcome-column outcome --failed failed_assertion --failed crashed \
  --started 2026-09-05T18:54:07Z
```

<!-- output exit=0 -->
```
ok  wrote run humaneval-a to ./store: 10,496 rows, 328 cases, 32 repeats each; 9,158 passed, 1,338 failed

# Poisson Trace · import · humaneval-a

## Summary

- Wrote: humaneval-a into ./store, from humaneval-a.csv (table): 10,496 tries on 328 inputs.
- Failures: 1,338 failed and 9,158 passed. A try counts as failed when its outcome column reads "failed_assertion" or "crashed"; any other value counts as a pass.
- Compared: Nothing yet. One import is one version.
- Next: Import the other version's file the same way: `poisson-trace import table OTHER.csv --store ./store --run OTHER --case-column case --outcome-column outcome --failed failed_assertion --failed crashed`.

## Before you act on this

- Every other value of the outcome column counts as a pass.
- When you compare, choose the smallest drop that matters to you (--max-mde) before you look at any results; Trace then says whether these tries could catch it.

## What was written

- run written: humaneval-a · store: ./store
- tool: table
- file: humaneval-a.csv · sha256 4bcab307a0268f69a648d43902b84af930e11ca525e92e7ffd5f813bea085720
- declared: case_column case · outcome_column outcome · failed ["failed_assertion", "crashed"]
- started: 2026-09-05T18:54:07Z · from: given
- rows 10,496 · cases 328 · repeats of a case: smallest 32, largest 32
- outcomes: met 9,158 · missed 1,338
- rows with no outcome: 0
- the outcome column's values: "passed" 9,158 rows (counted as passed) · "failed_assertion" 1,330 rows (counted as failed) · "crashed" 8 rows (counted as failed)

In the command below, OLD and NEW are this run and the other version's run, imported into the same store, the older version first. X is the largest limit of detection you accept, as a share: 0.05 is five points.

next: poisson-trace fix-check OLD NEW --store ./store --event missed --inputs all --max-mde X  # humaneval-a is OLD or NEW
```

<!-- command -->
```
poisson-trace import table tests/fixtures/ingest/table/humaneval-b.csv \
  --store ./store --run humaneval-b --case-column case \
  --outcome-column outcome --failed failed_assertion --failed crashed \
  --started 2026-09-05T19:50:09Z
```

<!-- excerpt exit=0 -->
```
- outcomes: met 9,109 · missed 1,387
- rows with no outcome: 0
- the outcome column's values: "passed" 9,109 rows (counted as passed) · "failed_assertion" 1,376 rows (counted as failed) · "crashed" 11 rows (counted as failed)
```

<!-- command -->
```
poisson-trace fix-check humaneval-a humaneval-b --store ./store --event missed \
  --inputs all --max-mde 0.02 --top 3
```

<!-- excerpt exit=0 -->
```
**different: the new version failed more on these inputs (exact Cochran-Mantel-Haenszel, stratified by input, p = 0.036)**
```

<!-- excerpt exit=0 -->
```
| input | old failed/runs | new failed/runs | change | p | q | flag |
|---|---|---|---|---|---|---|
| {"case":"HumanEval/129@0.7"} | 12/32 | 32/32 | +62.5 points | 2.30e-08 | 7.55e-06 | failed more in new |
| {"case":"HumanEval/129@0.0"} | 20/32 | 32/32 | +37.5 points | 1.38e-04 | 0.023 | failed more in new |
```

The table gives what the DeepEval page's files give, number for number: the runs are the
same, and the import read the same outcomes from them. The two pass rates are 87.3% and
86.8%. The runs do differ (p = 0.036), and 32 of the 49 extra misses are one problem,
HumanEval/129, in an agent nobody changed. A difference between two runs is a difference
between the runs; the version and the hour changed together.

## From `poisson-trace init`

`poisson-trace init`, run in a folder with no Prove store under it, lists the tables that look
like results (a `.csv`, `.jsonl` or `.json` file with a column named exactly `outcome`,
`passed`, `result` or `status` within its first 4 KB, and no column named like a Ragas metric;
a `.json` file is a list of rows) and offers to import them. It asks the import's questions in
the order of its flags: the case column, the outcome column, and the values that mean a
failure, separated by commas. With `--yes` it takes them as `--case-column`,
`--outcome-column` and `--failed` instead. Each file becomes one run, named after the file, in
a store `trace-store` beside `trace.toml`, and `trace.toml` names that store with `missed` as
the failure. Here it is on the two worked tables:

<!-- command -->
```
mkdir -p from-table && cp tests/fixtures/ingest/table/humaneval-*.csv from-table/
cd from-table && poisson-trace init --yes --case-column case --outcome-column outcome \
  --failed failed_assertion --failed crashed
```

<!-- excerpt exit=0 -->
```
  found 2 result files:
    1) humaneval-a.csv           a CSV table with the outcome column outcome
    2) humaneval-b.csv           a CSV table with the outcome column outcome
```

<!-- excerpt exit=0 -->
```
  import   poisson-trace import table humaneval-a.csv --store trace-store --run humaneval-a --case-column case --outcome-column outcome --failed failed_assertion --failed crashed
  import   poisson-trace import table humaneval-b.csv --store trace-store --run humaneval-b --case-column case --outcome-column outcome --failed failed_assertion --failed crashed
  the same setup, without questions:
    poisson-trace init --yes --import --case-column case --outcome-column outcome \
      --failed failed_assertion --failed crashed --event missed
next: poisson-trace runs
```

With `trace.toml` there, the import takes its store from it too, so `--store` may be left out.

## What this does not do

- It does not run the tool or the script that wrote the table. It reads the file.
- It does not make a comparison out of one run: a fix check is two versions on the same
  inputs, side by side.
- It knows no tool's own format: it reads a table by the column names you give, and the
  summary prints them.
- It keeps no prompt, answer, expected or sampled text: of each row it keeps the case and met
  or missed, or the score, and nothing of any other column.
