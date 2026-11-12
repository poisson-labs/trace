# From LangSmith

You ran two versions of an agent as LangSmith experiments on one dataset, and one scored
better. This recipe checks whether that is a real difference. It starts from the runs
LangSmith already holds and runs no agent.

## 1. The runs

Get each experiment's runs out of LangSmith in one of three ways. Pull them with your key:
set `LANGSMITH_API_KEY` and give `langsmith:NAME` where the file would go. Export them with
the `langsmith` command: `langsmith runs export old.jsonl --project NAME --full`. Or download
the CSV from the experiment's page. The [LangSmith page](../integrations/langsmith.md) says
what each one holds.

Here the files are two experiments of a small stock-desk agent on ten examples, as LangSmith's
API returned them: `baseline.runs-v1.json` and `candidate.runs-v1.json` in
`tests/fixtures/ingest/langsmith/api/` in a clone of the repository. The commands run from
the clone's root.

## 2. Import each experiment as a version

One import is one version. Say what pairs the two versions' rows, here the dataset example,
and what counts as failed, here the evaluator's `exact` score below 0.5.

<!-- command -->
```
poisson-trace import langsmith tests/fixtures/ingest/langsmith/api/baseline.runs-v1.json \
  --store ./store --run old --case-from example --outcome-from feedback:exact --cut 0.5 --below
```

<!-- excerpt exit=0 -->
```
ok  wrote run old to ./store: 10 rows, 10 cases, 1 repeat each; 6 passed, 4 failed
```

<!-- command -->
```
poisson-trace import langsmith tests/fixtures/ingest/langsmith/api/candidate.runs-v1.json \
  --store ./store --run new --case-from example --outcome-from feedback:exact --cut 0.5 --below
```

<!-- excerpt exit=0 -->
```
ok  wrote run new to ./store: 10 rows, 10 cases, 1 repeat each; 8 passed, 2 failed
```

Each import also keeps what LangSmith recorded of a run, without its text: how long it took,
its tokens and cost, its steps and tool calls, and the kind of each failure.

## 3. Check the fix

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
report's Guidance section says how many repeats of each example would be enough: run both
experiments that many times and import them again.

## 4. See where the failing runs stop

<!-- command -->
```
poisson-trace where old --store ./store --event missed
```

<!-- excerpt exit=0 -->
```
ok  4 of 10 tries failed; their last steps: 1 at a tool call and 3 at another kind of step (not necessarily the cause)
```

## What this does not do

- It does not run LangSmith, your agent or a model; it reads the runs LangSmith holds.
- It does not make a comparison out of one experiment: run both versions on the same dataset.
- From the page's CSV there are no steps, so there is no step to place a failure on.
- It keeps no prompt, input, output or error text.
