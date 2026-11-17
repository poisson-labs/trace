# The config file: `trace.toml`

`trace.toml` tells Trace where your results are and which outcomes count as a failure, so
that no command needs a flag for either. `poisson-trace init` writes it, you may edit it by
hand, and `poisson-trace doctor` checks it. This page goes through it key by key, and then
through `trace-names.toml`, the one file Trace keeps in a store.

## Where it is read from

Every command reads `trace.toml` in the folder you run it in, and never one in a folder
above. `--config PATH`, before or after the verb, names another file. A store path in the
file is read from the folder that holds the file, not from the folder you are in.

A flag wins over the file. `--event` given on the command line replaces the file's failures,
it does not add to them. What neither the file nor a flag gives is a mistake in the command
line, as it is with no file at all.

## A config, as `init` writes it

The example is the store under `tests/fixtures/tau2` in a clone of the repository, copied
into a folder of its own. `--max-mde` asks `init` to write the `[check]` table too:

<!-- command -->
```
mkdir -p airline-agent && cp -R tests/fixtures/tau2 airline-agent/prove-runs
cd airline-agent && poisson-trace init --yes --max-mde 0.2 > /dev/null 2>&1 && cat trace.toml
```

<!-- output exit=0 -->
```
# Poisson Trace: where your results are, and what counts as a failure.
# Written by `poisson-trace init`. Edit it freely; `poisson-trace doctor` checks it.
version = 1

[store]
path = "prove-runs"

[events]
failed = ["unsolved"]

[check]
max_mde = 0.2

[names]
from = "target"
```

`version` is always `1`. A file with another version, a table or a key Trace does not know,
or a value of the wrong kind is refused by every command, in one line that names the file and
the line the fault is on:

<!-- command -->
```
cd airline-agent && sed 's/^failed/faild/' trace.toml > typo.toml
poisson-trace runs --config typo.toml
```

<!-- output exit=1 -->
```
error: typo.toml line 9: [events] "faild" is not a setting; did you mean "failed"?
```

## The tables

### `[store]` and `[store.NAME]`: where the results are

`path` is the folder that holds the runs: the store every command reads. A second store goes
in a table of its own, `[store.NAME]`, with its own `path`, and `--store NAME` then reaches
it. A name is 1 to 40 letters, digits, `-` and `_`. `poisson-trace init --add-store PATH`
adds one, named after its folder.

### `[events]`: what counts as a failure

`failed` is the list of outcomes that count as a failure, one or more, each once. An outcome
is the word a try ended with: Prove records one for each try, and an import writes `met` or
`missed`. A try whose outcome is in the list failed; a try with any other outcome did not.

### `[check]`: the sizes you ask about

- `max_mde` is the `--max-mde` that `fix-check` takes when you give none: the smallest drop in
  the share of tries that fail that you want the check to be able to see, as a fraction above
  `0` and below `1`. `0.2` is 20 points.
- `max_mde_hr` is the `--max-mde-hr` that `compare` takes when you give none: a number above
  `1`, such as `1.5`.
- `max_change` is the `--max-change` that `fix-check` takes when you give none: for each
  measure, the change in its mean that you accept as none, written as a table such as
  `{ wall_time_s = "10%" }`.
- `fail_on` is a list drawn from `failed-more` and `too-small`. It is checked today and read
  by no command of this release: it is kept for a check on pull requests that is not built.

None of the four has a default, and `init` writes the table only when you give one of the
flags. Choose a size before you look at a result.

### `[names]`: how a run is named

`from` says how a run you have not named yourself is named in listings and reports:

| `from` | a run is named | example |
|---|---|---|
| `target` | by its target up to the first slash, its day and a letter (the default) | `tau2-airline 2026-09-15 a` |
| `date` | by its day and a letter | `2026-09-15 a` |
| `target-date` | by its target, its model, its day and a letter | `tau2-airline gpt-4.1-mini 2026-09-15 a` |

The day is the day the run started, in UTC. The letter orders the runs that would otherwise
share a name, by when they started.

### `[upload]`: kept for later

`enabled`, `url` and `token_env` are checked today and read by no command of this release:
Trace sends nothing anywhere. `enabled` is true or false, `url` an https address, and
`token_env` the name of the environment variable that would hold a token, never the token
itself.

### `[signals]`: where an import finds what it reads

These stand in for an import's flags, so a team writes them once. A flag you give wins.

- `case_field` is the field or column that identifies a case.
- `outcome_field` is the field or column that holds the outcome.
- `score_field` is the field or column that holds a score, read at `cut`.
- `cut` is the number a score is read at.
- `cost_field` is the field the cost of a try is read from.
- `budgets` is the table `[signals.budgets]`: the limits a try is held to. Its keys are
  `max_wall_time_s`, `max_total_tokens` and `max_cost_usd`, each a number from `0`. A try
  over one of them carries the signal `over_budget` in the reports.

Each reader's page under [integrations](integrations/) says which of its flags these stand
in for.

### `[taxonomy]`: your own rules for the kind of a failure

Every import gives each failed try one of thirteen kinds of failure, by built-in rules.
`rules` holds rules of your own, tried first and in the order written. Each is a table
`[[taxonomy.rules]]` with the `failure_kind` it gives and at least one condition:
`when_error_matches` (text the error's type or message must match), `when_span_kind` (the kind
of step the error happened at), or `when_metric_below` (`{ metric = "NAME", cut = X }`). Every
condition of a rule must hold for it to apply.

```toml
[[taxonomy.rules]]
failure_kind = "tool_error"
when_error_matches = "BookingServiceError"
```

Your `rules` apply to a run Prove swept as they do to an import, after any kind the try
recorded itself, and so do your `budgets` under `[signals]`. A try of a run Prove swept is held
to `max_wall_time_s` by its wall time, to `max_total_tokens` by its steps' tokens in and out
together, and to `max_cost_usd` by the `cost_usd` its rollout records; a try that does not
record one of these is never over it.

The thirteen kinds are `timeout`, `rate_limit`, `context_overflow`, `loop_detected`,
`step_limit`, `guardrail_blocked`, `tool_error`, `retrieval_error`, `format_error`,
`abstained`, `crash`, `wrong_answer` and `unclassified_error`.

`labels` names the kind of a Prove run's outcome labels. A run Prove swept records each try's
outcome as a label, and a failed try takes its label's kind when nothing on its record says why
it failed. Each line of `[taxonomy.labels]` is a label, as Prove stores it, and the kind it
names:

```toml
[taxonomy.labels]
forbidden_action = "guardrail_blocked"
"not solved" = "wrong_answer"
```

A label that is the name of a kind gives that kind without a line here, and so do the labels
Poisson Tasks gives a failure: `wrong_state`, `overshoot` and `collateral_mutation` give
`wrong_answer`, `malformed_call` gives `format_error`, `turn_limit` gives `step_limit`,
`wall_timeout` gives `timeout`, and `api_error`, `verifier_error` and `replay_mismatch` give
`crash`. A line of yours wins over these. A label is matched letter for letter.

A failed try of a run Prove swept takes its kind from the first of these that gives one: the
kind the try recorded itself, Prove's own `timeout` short of the step limit, your `rules`, the
built-in rules that find a cause on the try's record, then its label's kind. A try none of
these names is `wrong_answer` when it was graded and `unclassified_error` otherwise, and the
report's `Failures by kind` names the labels left without a kind. `labels` applies only to
runs Prove swept: an import's kinds were decided when it was imported.

## `[[import]]`: the files to import

One table for each result file another tool wrote. `poisson-trace init` shows the list and
imports the files after you say yes; `poisson-trace doctor --setup` checks them and imports
nothing.

```toml
[[import]]
file = "reports/junit-old.xml"
tool = "junit"
name = "tests-old"
case = "name"
```

- `file` is the file, relative to `trace.toml`.
- `tool` is the reader that reads it, one of the ten in the install: `deepeval`, `ragas`,
  `table`, `junit`, `promptfoo`, `inspect`, `openai-evals`, `langsmith`, `braintrust` or
  `weave`.
- `name` is the name the imported run gets.
- Every other key is one of that reader's own flags, by the flag's name without its dashes and
  with `_` for `-`: `case = "name"` is `--case name`.

[Set up Trace with your coding agent](setup-with-your-agent.md) shows a config with four of
these, checked and imported.

## `trace-names.toml`: your names for runs

`poisson-trace name RUN "a name"` gives a run a name of yours. The names are kept in
`trace-names.toml` at the store's root, the one file Trace writes in a store Prove wrote; no
file of a run changes.

<!-- command -->
```
cd airline-agent && poisson-trace name previous "old version, run again" > /dev/null
cat prove-runs/trace-names.toml
```

<!-- output exit=0 -->
```
# Poisson Trace: your names for the runs in this store. Written by `poisson-trace name`.
version = 1

[names]
"old version, run again" = "20260915T211148Z-965d"
```

`poisson-trace name RUN --forget` takes a name back, and `poisson-trace name --list` shows
them. A name of yours comes first wherever a command takes a run.
