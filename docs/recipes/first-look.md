# A first look

You have a folder of runs that Prove stored, and you have not used Trace on it yet. This
recipe sets Trace up on that folder, lists its runs, and shows where the tries of the newest
run die. It takes three commands. It runs no agent and calls no model.

The example is the store under `tests/fixtures/cs` in a clone of
[the repository](https://github.com/poisson-labs/trace): two recordings of OpenAI's
customer-service agent demo, 24 tries each. Run the commands from the clone's root, or put your
own folder where the copy goes.

## 1. Set up

A store is the folder Prove writes its runs into, and `prove-runs` is the name Prove gives it.
`poisson-trace init` looks for one under the folder you run it in:

<!-- command -->
```
mkdir -p my-agent && cp -R tests/fixtures/cs my-agent/prove-runs
cd my-agent && poisson-trace init --yes
```

It says what it found:

<!-- excerpt exit=0 -->
```
  found 1 store:
    1) prove-runs                2 runs · cs_agents · newest 2026-09-25
Using prove-runs, the store found.
```

and what it did:

<!-- excerpt exit=0 -->
```
ok  wrote trace.toml: store prove-runs (2 runs), failures app_error, forbidden_action, unresolved, max_turns
  names    2 runs, named from their manifests (cs_agents 2026-09-25 b, cs_agents 2026-09-25 a); none named by you yet: poisson-trace name RUN "a name"
  prove    poisson-prove is installed at the version Trace reads
```

`init` wrote one file, `trace.toml`, which names the store and the outcomes that count as a
failure. Every later command reads it, so none of them needs a flag. With `--yes` it took every
outcome whose name is not a word for success. On a terminal, leave `--yes` out and it asks you.

## 2. List the runs

<!-- command -->
```
cd my-agent && poisson-trace runs
```

<!-- output exit=0 -->
```
ok  2 runs in prove-runs (newest first); 0 named by you, 2 named from their manifests

  #  name                    rows  failed  traces  started           status
  1  cs_agents 2026-09-25 b    24       7  yes     2026-09-25 23:54  complete
  2  cs_agents 2026-09-25 a    24       7  yes     2026-09-25 23:46  complete

next: poisson-trace where "cs_agents 2026-09-25 b"
```

A run is one stored sweep: every try of one version of the agent. Each has a name, made from
its target, its day and a letter. The newest is also `latest` and the one before it `previous`,
and `"#1"` is the first row of this listing. A command takes any of those.

## 3. See where its tries die

<!-- command -->
```
cd my-agent && poisson-trace where latest
```

The first line is the answer in a sentence:

<!-- excerpt exit=0 -->
```
ok  7 of 21 tries failed; their last steps: 4 at a model call and 3 at an agent step (not necessarily the cause)
```

Then the report. It puts every try on one clock, the step it had reached, and gives the share
of tries that had not failed by each step where one did:

<!-- excerpt exit=0 -->
```
## Share not yet failed, by turn

Aalen–Johansen over leaf-span index: finishing without failing and timing out are ends of their own, and only capped tries are censored; band: bootstrap 95%, resampling inputs, B = 1,000, seed = 0.

| turn | at risk | failed | not yet failed | 95% band |
|---|---|---|---|---|
| 24 | 15 | 1 | 0.952 | 0.857 – 1.000 |
| 30 | 12 | 1 | 0.905 | 0.714 – 1.000 |
| 33 | 11 | 1 | 0.857 | 0.667 – 1.000 |
| 35 | 10 | 1 | 0.810 | 0.619 – 1.000 |
| 48 | 5 | 1 | 0.762 | 0.571 – 1.000 |
| 50 | 4 | 1 | 0.714 | 0.429 – 1.000 |
| 58 | 2 | 1 | 0.667 | 0.381 – 1.000 |
```

and the kind of step each failed try stopped at:

<!-- excerpt exit=0 -->
```
## Where they die, by kind of step

Aalen–Johansen: each kind's share of tries failed by turn 59, and the share that timed out; band: bootstrap 95%, resampling inputs, B = 1,000, seed = 0.

| kind | tries | share by turn 59 | 95% band |
|---|---|---|---|
| llm | 4 | 0.190 | 0.000 – 0.381 |
| agent | 3 | 0.143 | 0.000 – 0.286 |
| timed out | 0 | 0.000 | 0.000 – 0.000 |
```

Four tries stopped at a model call (`llm`) and three at a guardrail agent (`agent`). The bands
are wide because the run is small. The report ends with what it
cannot say; [What it cannot say](what-it-cannot-say.md) reads that part.

## 4. Draw the curve

`--svg FILE` writes the same curve as a picture. Without a `trace.toml`, name the store and
the failures by flag. This is how the picture of the first recording in the repository was
made (`--force` because the clone already holds the file):

<!-- command -->
```
poisson-trace where "cs_agents 2026-09-25 a" --store tests/fixtures/cs \
  --event forbidden_action --event unresolved --event max_turns --event app_error \
  --at 20 --at 40 --svg docs/figures/cs-record.svg --force
```

<!-- excerpt exit=0 -->
```
ok  7 of 24 tries failed; their last steps: 4 at a model call and 3 at an agent step (not necessarily the cause)
  wrote  docs/figures/cs-record.svg
```

Next: [Check a fix](check-a-fix.md) compares two runs.

## What this does not do

- It does not run your agent or call a model. Trace reads runs that are already stored.
- It does not say whether a change helped. One run shows where tries stop, and only a
  comparison of two runs says whether anything moved.
- It does not say why a try failed. The step is where the try stopped, which may be later than
  where it went wrong.
