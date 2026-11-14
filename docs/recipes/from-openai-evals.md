# From OpenAI Evals

You ran an eval with `oaieval` on two versions and one got more samples right. This recipe
checks whether that is a real difference. It starts from the records `oaieval` already wrote
and runs no eval.

## 1. The records

Save a record for each version:

<!-- skip reason="runs oaieval, which Trace never does" -->
```
oaieval my-completion-fn my-eval --record_path old.jsonl
oaieval my-new-completion-fn my-eval --record_path new.jsonl
```

Here the records are `oaieval`'s own, written by evals 3.0.1.post1 with its `dummy` completion
function on the bundled `test-match` eval: `tests/fixtures/ingest/openai-evals/old.jsonl` and
`new.jsonl` in a clone of the repository. The commands run from the clone's root.

## 2. Import each record as a version

One import is one version. The record says what was right, so nothing needs declaring:

<!-- command -->
```
poisson-trace import openai-evals tests/fixtures/ingest/openai-evals/old.jsonl \
  --store ./store --run old
```

<!-- excerpt exit=0 -->
```
ok  wrote run old to ./store: 3 rows, 3 cases, 1 repeat each; 0 passed, 3 failed
```

<!-- command -->
```
poisson-trace import openai-evals tests/fixtures/ingest/openai-evals/new.jsonl \
  --store ./store --run new
```

<!-- excerpt exit=0 -->
```
ok  wrote run new to ./store: 3 rows, 3 cases, 1 repeat each; 0 passed, 3 failed
```

`oaieval` writes the spec's time with no zone, so the start is read as UTC, and the summary
says so:

<!-- excerpt exit=0 -->
```
- started: 2026-10-07T04:25:47.575509Z · from: file (the spec's created_at carries no zone, so it was read as UTC)
```

## 3. Check the fix

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

`dummy` gets every sample wrong in both records, and three samples run once cannot show a
change either way. The report's Guidance section says how many runs would.

The [OpenAI Evals page](../integrations/openai-evals.md) has every flag and what the reader refuses.

## What this does not do

- It does not run `oaieval` or call a model; it reads the records it wrote.
- It reads `match` events as rows and counts the other events; it does not join `sampling`
  events to them.
- It keeps no prompt, sampled answer, expected answer, option or pick.
