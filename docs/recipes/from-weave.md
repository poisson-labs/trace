# From W&B Weave

You ran two versions of an agent as Weave evaluations on one dataset, and one scored better.
This recipe checks whether that is a real difference. It starts from the evaluations Weave
already holds and runs no agent.

## 1. The evaluations

Get each evaluation out of Weave in one of two ways. Pull it with your key: set
`WANDB_API_KEY` and give `weave:ENTITY/PROJECT/EVALUATION` where the file would go. Or
download it from the Traces page, filtered to the op `Evaluation.predict_and_score`, as JSON,
JSON Lines, CSV or TSV. The [Weave page](../integrations/weave.md) says what each one holds.

Here the files are two evaluations of a small stock-desk agent on ten dataset rows, as
Weave's service returned them: `trace-fixture-slice-baseline.jsonl` and
`trace-fixture-slice-candidate.jsonl` in `tests/fixtures/ingest/weave/api/` in a clone of the
repository. The commands run from the clone's root.

## 2. Import each evaluation as a version

One import is one version. Say what pairs the two versions' rows, here the dataset row, and
what counts as failed, here a score below 0.5 on the scorer's `exact` output (true is 1 and false is 0).

<!-- command -->
```
poisson-trace import weave tests/fixtures/ingest/weave/api/trace-fixture-slice-baseline.jsonl \
  --store ./store --run old --case-from example --outcome-from score:exact --cut 0.5 --below
```

<!-- excerpt exit=0 -->
```
ok  wrote run old to ./store: 10 rows, 10 cases, 1 repeat each; 6 passed, 3 failed, 1 with no outcome
```

<!-- command -->
```
poisson-trace import weave tests/fixtures/ingest/weave/api/trace-fixture-slice-candidate.jsonl \
  --store ./store --run new --case-from example --outcome-from score:exact --cut 0.5 --below
```

<!-- excerpt exit=0 -->
```
ok  wrote run new to ./store: 10 rows, 10 cases, 1 repeat each; 8 passed, 1 failed, 1 with no outcome
```

In each version one case errored. Weave runs no scorer on a case that errored, so it has no
outcome here: it is not counted as a pass or as a fail. To count it as failed, read the
outcome from the case's status instead, with `--outcome-from status`.

Each import also keeps what Weave recorded of a case, without its text: how long the model's
run took, its tokens and cost, its steps and retries, and the kind of each failure.

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
| old | 8 | 3 | 37.5% | 62.5% |
| new | 8 | 1 | 12.5% | 87.5% |
```

The check counts the eight inputs that have an outcome in both versions. Three failures down
to one, on eight inputs run once each, is too few to tell from chance. The report's Guidance
section says how many repeats of each input would be enough: run both evaluations that many
times and import them again.

## 4. See where the failing cases stop

<!-- command -->
```
poisson-trace where old --store ./store --event missed
```

<!-- excerpt exit=0 -->
```
ok  3 of 9 tries failed; each one's last step was another kind of step (not necessarily the cause)
```

## 5. Or pull it with your key

With `WANDB_API_KEY` set, an address goes where the file went: `weave:`, then the entity, the project and the evaluation, with a slash between. The pull saves a copy of what
Weave returned under the store, in `.poisson/raw/`, with the input and output text left out,
and reads that copy as it reads a file. On this page the pull is answered from Weave's own
answers, saved with the example files, so it needs no key and no network. With your key the
same command asks Weave.

<!-- command pull -->
```
poisson-trace import weave weave:example-entity/trace-fixture/trace-fixture-slice-baseline \
  --store ./pulled --run pulled-old --case-from example --outcome-from score:exact --cut 0.5 --below
```

<!-- excerpt exit=0 -->
```
ok  wrote run pulled-old to ./pulled: 10 rows, 10 cases, 1 repeat each; 6 passed, 3 failed, 1 with no outcome
```

The pulled run carries its steps, so `where` reads it:

<!-- command -->
```
poisson-trace where pulled-old --store ./pulled --event missed
```

<!-- excerpt exit=0 -->
```
ok  3 of 9 tries failed; each one's last step was another kind of step (not necessarily the cause)
```

## What this does not do

- It does not run Weave, your agent or a model; it reads the evaluations Weave holds.
- It does not make a comparison out of one evaluation: run both versions on the same dataset.
- From the Traces page's download there are no steps, so there is no step to place a failure on.
- It keeps no prompt, input, output or error text.
