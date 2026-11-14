# From Inspect

You ran an Inspect AI task on two versions of your model or agent and one scored better. This
recipe checks whether that is a real difference. It starts from the logs Inspect already wrote
and runs no task.

## 1. The logs

Inspect writes a log for each run, in `./logs`. Reading a `.eval` log needs the `zstandard`
package:

<!-- skip reason="installs from the package index, which the docs check does not reach" -->
```
pip install 'poisson-trace[inspect]'
```

Here the logs are Inspect's own, written by inspect_ai 0.3.277 with its `mockllm/model` on
three samples, two epochs each: the old version's `.eval` log and the new version's `.json`
log in `tests/fixtures/ingest/inspect/` in a clone of the repository. The commands run from
the clone's root.

## 2. Import each log as a version

One import is one version. Each sample is a row, its epochs its repeats, and the scorer's
letters the outcome: `C` passed, `I`, `P` and `N` failed.

<!-- command -->
```
poisson-trace import inspect \
  tests/fixtures/ingest/inspect/2026-10-07T04-23-47-00-00_trace-fixture_CV3jq8f7FTjwkaYb3zj3m2.eval \
  --store ./store --run old
```

<!-- excerpt exit=0 -->
```
ok  wrote run old to ./store: 6 rows, 3 cases, 2 repeats each; 3 passed, 3 failed
```

<!-- excerpt exit=0 -->
```
- declared: scorer includes · outcome correct · model mockllm/model · task trace_fixture
```

<!-- command -->
```
poisson-trace import inspect \
  tests/fixtures/ingest/inspect/2026-10-07T04-23-51-00-00_trace-fixture_2nSEDuHHzKiTUjJW3kXknY.json \
  --store ./store --run new
```

<!-- excerpt exit=0 -->
```
ok  wrote run new to ./store: 6 rows, 3 cases, 2 repeats each; 5 passed, 1 failed
```

A log whose samples hold several scores needs `--scorer NAME`; the import lists the scorers
when it is missing.

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
| old | 6 | 3 | 50.0% | 50.0% |
| new | 6 | 1 | 16.7% | 83.3% |
```

Three failures down to one, on three samples run twice, is too few to tell from chance. The
report's Guidance section says how many epochs would: give the task that many and run both
versions again.

The [Inspect page](../integrations/inspect.md) has every flag and what the reader refuses.

## What this does not do

- It does not run Inspect, a task or a model; it reads the logs Inspect wrote.
- It reads a log whole into memory and refuses one over 200 MB.
- It keeps no input, target, message, output, tool argument or score explanation.
