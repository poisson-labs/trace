# Check a fix

You have a run of your agent with failures in it, and a new version that is meant to fix
them. This recipe checks whether the new version fails less, with a control beside it. It ends
with one of three verdicts, and with what would settle the question if it is not yet clear.

The usual check is to run the failed inputs again on the new version and count how many now
pass. That count has no control. Run the old version again on the same inputs and some of them
pass too, with nothing changed. A fix check shows that number beside the new version's.

## 1. The design

Trace runs nothing: the runs are yours to make, with Prove or any other harness.

1. Take a run of the old version that has failures. It chooses the inputs: the ones that
   failed in it.
2. Run both versions on those same inputs, side by side: the old version again and the new
   version, on the same day, with the same provider and the same number of repeats of each
   input.
3. Give Trace the two fresh runs, and name the first run as the one that chose the inputs.

With Prove, step 2 is two sweeps of one sweep file that holds the failed inputs:

<!-- skip reason="runs your agent with Prove, which Trace never does" -->
```
poisson-prove sweep failed-inputs.toml --target my_agent.rollout:old_version --replicates 16
poisson-prove sweep failed-inputs.toml --target my_agent.rollout:new_version --replicates 16
```

## 2. The example runs

`tests/fixtures/tau2` in a clone of [the repository](https://github.com/poisson-labs/trace)
holds three runs of an airline agent. Two are the same agent run twice, ten minutes apart, with
nothing changed. The third is the agent with a guardrail patch, run once on ten tasks. Run the
commands from the clone's root.

<!-- command -->
```
mkdir -p airline-agent && cp -R tests/fixtures/tau2 airline-agent/prove-runs
cd airline-agent && poisson-trace init --yes
```

<!-- excerpt exit=0 -->
```
ok  wrote trace.toml: store prove-runs (3 runs), failures unsolved
```

<!-- command -->
```
cd airline-agent && poisson-trace runs
```

<!-- output exit=0 -->
```
ok  3 runs in prove-runs (newest first); 0 named by you, 3 named from their manifests

  #  name                       rows  failed  traces  started           status
  1  tau2-airline 2026-09-17 a    10       3  no      2026-09-17 14:02  complete
  2  tau2-airline 2026-09-15 b   200     112  yes     2026-09-15 21:11  complete
  3  tau2-airline 2026-09-15 a   200     110  yes     2026-09-15 21:01  complete

next: poisson-trace where "tau2-airline 2026-09-15 b"
```

The first run, at the bottom, is the old version with its failures. The second is the old
version run again, and it is `previous`. The patched run is the newest, so it is `latest`.

## 3. A first check

The shortest fix check compares every input both runs hold. `--inputs all` says so, and
`--max-mde 0.2` asks that the check be able to see a drop of 20 points in the share of tries
that fail. Neither has a default.

<!-- command -->
```
cd airline-agent && poisson-trace fix-check previous latest --inputs all --max-mde 0.2
```

<!-- excerpt exit=0 -->
```
too small to tell  too few tries to see a 20-point drop
```

That is every task the patched run holds. The next check takes only the ones that failed.

## 4. The fix check on the inputs that failed

`--failing-from` names the run that chose the inputs, in place of `--inputs all`:

<!-- command -->
```
cd airline-agent && poisson-trace fix-check previous latest \
  --failing-from "tau2-airline 2026-09-15 a" --max-mde 0.20
```

<!-- excerpt exit=0 -->
```
too small to tell  too few tries to see a 20-point drop
```

The control is the table to read first:

<!-- excerpt exit=0 -->
```
## The control

The old version's run on the inputs that failed in tau2-airline 2026-09-15 a, beside the new.

| version | runs | failed | failure share | did not fail on re-run |
|---|---|---|---|---|
| old | 24 | 18 | 75.0% | 25.0% |
| new | 6 | 3 | 50.0% | 50.0% |

Re-running these inputs and counting the runs that did not fail would have read 25.0% on the old version, where nothing changed.
```

On the patched version, 3 of 6 tries passed. Counting those would read as half the failures
fixed. The control shows the old version passing 6 of 24 tries on the same inputs with nothing
changed, so some of those passes are chance. The report then tests the two shares against each
other, inside each input, and says how small a change these tries could have shown:

<!-- excerpt exit=0 -->
```
## What it could not have detected

proportional change on every input, 80% power, α = 0.05, continuity-corrected normal approximation to the stratified statistic.

- a drop in failure share: could not have detected one below 64.3 points
- a rise in failure share: no limit; even every run failing, a rise of 30.0 points, would have been detected less than four times in five

**too small to tell: could not have detected a drop in failure share below 64.3 points, and 20 was asked for**

## Guidance

- repeats: 16 per arm on these 6 inputs would bring the limit to 20 points
```

So the patch is not shown to work and not shown to fail. The Guidance block says what would
settle a 20-point question: 16 repeats of each of these 6 inputs on each version.
[How it decides](../how-it-decides.md) gives the test behind each of the three verdicts.

## What this does not do

- It does not run either version. The two fresh runs are yours to make.
- It does not show that your change caused a difference. It compares two runs, and whatever
  else differed between them is part of the difference.
- It does not accept the run that chose the inputs as the old version: its failures on those
  inputs are there by selection, and the command refuses it.
