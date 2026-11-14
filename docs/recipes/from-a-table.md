# From a table of results

You have two tables of results, one for each version of your agent, written by your own
script or by a tool Trace has no reader for. This recipe checks whether the new version fails
less than the old. It starts from the two files and runs nothing.

## 1. The files

A table is a CSV, JSON Lines, JSON or Parquet file with one row for each try. It needs a
column that says which case a row is, and a column that holds the row's result. Rows that
share a case are repeats of it.

Here the files are `humaneval-a.csv` and `humaneval-b.csv` in `tests/fixtures/ingest/table/`
in a clone of the repository: one agent run twice on 164 HumanEval problems at two
temperatures, with nothing changed between the runs. The first lines of one of them:

<!-- command -->
```
head -3 tests/fixtures/ingest/table/humaneval-a.csv
```

<!-- output exit=0 -->
```
case,task_id,temperature,replicate,outcome
HumanEval/152@0.0,HumanEval/152,0.0,0,passed
HumanEval/152@0.0,HumanEval/152,0.0,1,passed
```

The commands run from the clone's root.

## 2. Import each table as a version

One import is one version. Name the case column, the result column, and the values of the
result that mean a failure:

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

A table whose result is a number takes `--score-column` with `--cut` and a side in place of
the last two flags.

## 3. Check the fix

<!-- command -->
```
poisson-trace fix-check old new --store ./store --event missed \
  --inputs all --max-mde 0.02
```

<!-- excerpt exit=0 -->
```
different  the new version failed slightly more often
```

<!-- excerpt exit=0 -->
```
| version | runs | failed | failure share | did not fail |
|---|---|---|---|---|
| old | 10,496 | 1,338 | 12.7% | 87.3% |
| new | 10,496 | 1,387 | 13.2% | 86.8% |
```

The verdict is *different*, on an agent nobody changed: the second run failed 49 more times
than the first.

## 4. Find the inputs that changed

`changes` reads the same two runs input by input and names the ones that moved:

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

One problem, HumanEval/129, failed on every try of the second run at both temperatures, and
nothing else is flagged. A run made an hour later differs in more than the code, which is why
a difference between two runs is not yet a difference between two versions. The
[tables page](../integrations/table.md) has every flag and what each kind of file may hold.

## What this does not do

- It does not run the tool or the script that wrote the tables; it reads the files.
- It does not guess which column is the case or the result. You name both.
- It does not say your change caused a difference: run both versions side by side for that.
- It keeps the value of the case column and nothing else of a row's text, so name an id
  column and not the question.
