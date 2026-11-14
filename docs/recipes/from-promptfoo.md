# From promptfoo

You changed a prompt, ran promptfoo on the old one and the new one, and the new one passes more
tests. This recipe checks whether that is a real difference or the luck of a few tests. It
starts from the file promptfoo already wrote and runs no prompt.

## 1. The file

Save the evaluation as JSON, both prompts in one file:

<!-- skip reason="runs promptfoo, which Trace never does" -->
```
promptfoo eval -o results.json
```

Here the file is promptfoo's own, written by promptfoo 0.120.19 with its `echo` provider on
two prompts and four tests: `tests/fixtures/ingest/promptfoo/results.json` in a clone of the
repository. The commands run from the clone's root.

## 2. Import each prompt as a version

One import is one version. `--prompt` picks it, by its number or its label, and `--case
var:case` names the test variable that identifies a test in both:

<!-- command -->
```
poisson-trace import promptfoo tests/fixtures/ingest/promptfoo/results.json \
  --store ./store --run old --prompt 1 --case var:case
```

<!-- excerpt exit=0 -->
```
ok  wrote run old to ./store: 4 rows, 4 cases, 1 repeat each; 2 passed, 2 failed
```

<!-- excerpt exit=0 -->
```
- declared: case var:case · prompt old: {{text}} · provider echo · outcome success
```

<!-- command -->
```
poisson-trace import promptfoo tests/fixtures/ingest/promptfoo/results.json \
  --store ./store --run new --prompt 2 --case var:case
```

<!-- excerpt exit=0 -->
```
ok  wrote run new to ./store: 4 rows, 4 cases, 1 repeat each; 4 passed, 0 failed
```

The summary counts the file's results per prompt, so a prompt picked by mistake shows:

<!-- excerpt exit=0 -->
```
- results of prompt 1 (old: {{text}}): 4
- results of prompt 2 (new: {{text}} with the word banana): 4
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
| old | 4 | 2 | 50.0% | 50.0% |
| new | 4 | 0 | 0.0% | 100.0% |
```

Two failures gone out of four tests run once is no evidence either way. The report's Guidance
section says how many repeats of these tests would be: run the evaluation that many times, each
run to a file of its own, and give each import a version's files together.

The [promptfoo page](../integrations/promptfoo.md) has every flag and what the reader refuses.

## What this does not do

- It does not run promptfoo or call a provider; it reads the file promptfoo wrote.
- It does not read promptfoo's CSV, which sets the prompts side by side; export the JSON.
- It keeps no prompt, answer, variable but the case, error or grader's reason.
