# From LangSmith

You ran two versions of an agent as LangSmith experiments on one dataset, and one scored
better. This recipe shows where the failing runs stop, and checks whether the better score is
a real difference. It starts from the runs LangSmith already holds and runs no agent.

## 1. The runs

Get each experiment's runs out of LangSmith in one of three ways. Pull them with your key:
set `LANGSMITH_API_KEY` and give `langsmith:NAME` where a file would go. Export them with
the `langsmith` command: `langsmith runs export old.jsonl --project NAME --full`. Or download
the CSV from the experiment's page. The [LangSmith page](../integrations/langsmith.md) says
what each one holds.

Here the two experiments are a small stock-desk agent on ten examples, before and after a
change. On this page the pulls are answered from LangSmith's own answers, saved with the
example files in a clone of the repository, so they need no key and no network. With your key
the same commands ask LangSmith. The commands run from the clone's root.

## 2. Pull each experiment as a version

One import is one version. Say what pairs the two versions' rows, here the dataset example,
and what counts as failed, here the evaluator's `exact` score below 0.5.

<!-- command pull -->
```
poisson-trace import langsmith langsmith:trace-fixture-baseline-bbb64b8e \
  --store ./experiments --run old --case-from example --outcome-from feedback:exact --cut 0.5 --below
```

<!-- excerpt exit=0 -->
```
ok  wrote run old to ./experiments: 10 rows, 10 cases, 1 repeat each; 6 passed, 4 failed
```

<!-- command pull -->
```
poisson-trace import langsmith langsmith:trace-fixture-candidate-7e3f7200 \
  --store ./experiments --run new --case-from example --outcome-from feedback:exact --cut 0.5 --below
```

<!-- excerpt exit=0 -->
```
ok  wrote run new to ./experiments: 10 rows, 10 cases, 1 repeat each; 8 passed, 2 failed
```

Each pull saves a copy of what LangSmith returned under the store, in `.poisson/raw/`, with
the input and output text left out.

## 3. See where the failing runs stop

<!-- command -->
```
poisson-trace where old --store ./experiments --event missed
```

The report gives the share of tries that had not failed by each step where one did:

<!-- excerpt exit=0 -->
```
## Share not yet failed, by step

Aalen–Johansen over leaf-span index: finishing without failing and timing out are ends of their own, and only capped tries are censored; band: bootstrap 95%, resampling inputs, B = 1,000, seed = 0.

| step | at risk | failed | not yet failed | 95% band |
|---|---|---|---|---|
| 2 | 10 | 1 | 0.900 | 0.700 – 1.000 |
| 4 | 9 | 3 | 0.600 | 0.300 – 0.900 |
```

and the kind of step each failed try stopped at:

<!-- excerpt exit=0 -->
```
## Where they die, by kind of step

Aalen–Johansen: each kind's share of tries failed by step 4, and the share that timed out; band: bootstrap 95%, resampling inputs, B = 1,000, seed = 0.

| kind | tries | share by step 4 | 95% band |
|---|---|---|---|
| tool | 1 | 0.100 | 0.000 – 0.300 |
| other | 3 | 0.300 | 0.000 – 0.600 |
| timed out | 0 | 0.000 | 0.000 – 0.000 |
```

## 4. Check the fix

<!-- command -->
```
poisson-trace fix-check old new --store ./experiments --event missed \
  --inputs all --max-mde 0.2
```

<!-- excerpt exit=0 -->
```
too small to tell  too few tries to see a drop of any size
```

Four failures down to two, on ten examples run once each, is too few to tell from chance. The
report's Guidance section says how many repeats of each example would be enough. The report
also counts each kind of failure in the two versions, which shows what grew and what shrank:

<!-- excerpt exit=0 -->
```
## Failures by kind

Each failed try's kind of failure, by the built-in rules; the same rules classified both runs. Counts, not a test: the verdict above is about all failures together.

| kind | old | old share | new | new share | change |
|---|---|---|---|---|---|
| wrong_answer | 3 | 30.0% | 1 | 10.0% | -20.0 points |
| timeout | 1 | 10.0% | 0 | 0.0% | -10.0 points |
| format_error | 0 | 0.0% | 1 | 10.0% | +10.0 points |
| all failures | 4 | 40.0% | 2 | 20.0% | -20.0 points |
```

## 5. From files instead

A file exported from LangSmith goes where the address went, with the same flags:

<!-- command -->
```
poisson-trace import langsmith tests/fixtures/ingest/langsmith/api/baseline.runs-v1.json \
  --store ./from-files --run file-old --case-from example --outcome-from feedback:exact --cut 0.5 --below
```

<!-- excerpt exit=0 -->
```
ok  wrote run file-old to ./from-files: 10 rows, 10 cases, 1 repeat each; 6 passed, 4 failed
```

<!-- command -->
```
poisson-trace import langsmith tests/fixtures/ingest/langsmith/api/candidate.runs-v1.json \
  --store ./from-files --run file-new --case-from example --outcome-from feedback:exact --cut 0.5 --below
```

<!-- excerpt exit=0 -->
```
ok  wrote run file-new to ./from-files: 10 rows, 10 cases, 1 repeat each; 8 passed, 2 failed
```

## What this does not do

- It does not run LangSmith, your agent or a model; it reads the runs LangSmith holds.
- It does not make a comparison out of one experiment: run both versions on the same dataset.
- From the page's CSV there are no steps, so there is no step to place a failure on.
- It keeps no prompt, input, output or error text.
