# From DeepEval

You ran two versions of an agent through DeepEval, and one passed more test cases than the
other. This recipe checks whether that is a real difference. It starts from the result files
DeepEval already saved and runs no test, no metric and no model.

## 1. The files

DeepEval saves a result file for each test run when you set a folder for it:

<!-- skip reason="runs DeepEval, which Trace never does" -->
```
DEEPEVAL_RESULTS_FOLDER=./results deepeval test run test_agent.py
```

Run it once for each version, and more than once if you can: a case run once on each version
is the smallest design there is.

Here the files are `humaneval-a.json.gz` and `humaneval-b.json.gz` in
`tests/fixtures/ingest/deepeval/` in a clone of the repository: one agent run twice, 56 minutes
apart, on 164 HumanEval problems at two temperatures, with nothing changed between the runs.
The commands run from the clone's root.

## 2. Import each file as a version

One import is one version. Say which metric to read, where its cut is, and what identifies a
case. `--cut recorded` takes DeepEval's own pass or fail for the metric, and `--case name`
pairs test cases across the two files by their names.

<!-- command -->
```
poisson-trace import deepeval tests/fixtures/ingest/deepeval/humaneval-a.json.gz \
  --store ./store --run old --metric "Tests Passed" --cut recorded --case name
```

<!-- excerpt exit=0 -->
```
ok  wrote run old to ./store: 10,496 rows, 328 cases, 32 repeats each; 9,158 passed, 1,338 failed
```

<!-- command -->
```
poisson-trace import deepeval tests/fixtures/ingest/deepeval/humaneval-b.json.gz \
  --store ./store --run new --metric "Tests Passed" --cut recorded --case name
```

<!-- excerpt exit=0 -->
```
ok  wrote run new to ./store: 10,496 rows, 328 cases, 32 repeats each; 9,109 passed, 1,387 failed
```

Each test case becomes one row, written as `met` or `missed`, and `missed` is the failure.

## 3. Check the fix

`--inputs all` compares every case both files hold. `--max-mde 0.02` asks that the check be
able to see a drop of 2 points in the share of test cases that fail.

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

The verdict is *different*, on an agent nobody changed. The second run failed 49 more times
than the first, and one problem accounts for most of that. Two runs made at different hours
differ in more than the code, which is why the report says a difference between two runs is
not yet a difference between two versions. The [DeepEval page](../integrations/deepeval.md)
walks through this pair and has every flag.

## What this does not do

- It does not run DeepEval, a metric or a model; it reads the files DeepEval saved.
- It does not choose the cut. You name the metric and say where its cut is.
- It does not say your change caused a difference: run both versions side by side for that.
- It keeps no input and no output text of a test case.
