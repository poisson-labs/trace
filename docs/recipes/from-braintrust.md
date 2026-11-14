# From Braintrust

You ran two versions of an agent as Braintrust experiments on one dataset, and one scored
better. This recipe checks whether that is a real difference. It starts from the experiments
Braintrust already holds and runs no agent.

## 1. The experiments

Get each experiment out of Braintrust in one of two ways. Pull it with your key: set
`BRAINTRUST_API_KEY` and give `braintrust:PROJECT/EXPERIMENT` where the file would go. Or
download it from the experiment's page, as JSON or CSV. The
[Braintrust page](../integrations/braintrust.md) says what each one holds.

Here the files are two experiments of a small stock-desk agent on ten dataset records, as
Braintrust's API returned them: `slice-baseline.fetch.json` and `slice-candidate.fetch.json`
in `tests/fixtures/ingest/braintrust/api/` in a clone of the repository. The commands run from
the clone's root.

## 2. Import each experiment as a version

One import is one version. Say what pairs the two versions' rows, here the dataset record, and
what counts as failed, here the scorer's `exact` score below 0.5.

<!-- command -->
```
poisson-trace import braintrust tests/fixtures/ingest/braintrust/api/slice-baseline.fetch.json \
  --store ./store --run old --case-from record --outcome-from score:exact --cut 0.5 --below
```

<!-- excerpt exit=0 -->
```
ok  wrote run old to ./store: 10 rows, 10 cases, 1 repeat each; 6 passed, 3 failed, 1 with no outcome
```

<!-- command -->
```
poisson-trace import braintrust tests/fixtures/ingest/braintrust/api/slice-candidate.fetch.json \
  --store ./store --run new --case-from record --outcome-from score:exact --cut 0.5 --below
```

<!-- excerpt exit=0 -->
```
ok  wrote run new to ./store: 10 rows, 10 cases, 1 repeat each; 8 passed, 1 failed, 1 with no outcome
```

In each version one case ended in error. Braintrust scores no case that ended in error, so it
has no outcome here: it is not counted as a pass or as a fail. To count it as failed, read the
outcome from the error instead, with `--outcome-from error`.

Each import also keeps what Braintrust recorded of a case, without its text: how long it took,
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
| old | 8 | 3 | 37.5% | 62.5% |
| new | 8 | 1 | 12.5% | 87.5% |
```

The check counts the eight inputs that have an outcome in both versions. Three failures down
to one, on eight inputs run once each, is too few to tell from chance. The report's Guidance
section says how many repeats of each input would be enough: run both experiments that many
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

With `BRAINTRUST_API_KEY` set, an address goes where the file went: `braintrust:`, the project's name, a slash and the experiment's name. The pull saves a copy of what
Braintrust returned under the store, in `.poisson/raw/`, with the input and output text left out,
and reads that copy as it reads a file. On this page the pull is answered from Braintrust's own
answers, saved with the example files, so it needs no key and no network. With your key the
same command asks Braintrust.

<!-- command pull -->
```
poisson-trace import braintrust braintrust:trace-fixture/slice-baseline \
  --store ./pulled --run pulled-old --case-from input --outcome-from score:exact --cut 0.5 --below
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

- It does not run Braintrust, your agent or a model; it reads the experiments Braintrust holds.
- It does not make a comparison out of one experiment: run both versions on the same dataset.
- From the page's download there are no steps, so there is no step to place a failure on.
- It keeps no prompt, input, output or error text.
