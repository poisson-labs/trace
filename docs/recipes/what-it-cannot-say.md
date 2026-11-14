# What it cannot say

You have a report from Trace and a decision to make from it. This recipe reads the three
parts of a report that say how far it can be trusted: the limit, the guidance, and the list of
what the report cannot say. You end knowing which sentences to read before the verdict.

The example is the store under `tests/fixtures/tau2` in a clone of the repository: an airline
agent run twice, ten minutes apart, with nothing changed. Run the commands from the clone's
root.

## 1. Set up

<!-- command -->
```
mkdir -p airline-agent && cp -R tests/fixtures/tau2 airline-agent/prove-runs
cd airline-agent && poisson-trace init --yes
```

<!-- excerpt exit=0 -->
```
ok  wrote trace.toml: store prove-runs (3 runs), failures unsolved
```

## 2. One run

<!-- command -->
```
cd airline-agent && poisson-trace where previous
```

<!-- excerpt exit=0 -->
```
ok  112 of 200 tries failed; each one's last step was a model call (not necessarily the cause)
```

A `where` report describes one run. It ends with what that description cannot carry:

<!-- excerpt exit=0 -->
```
## What this cannot say

- The step index is where the run stopped, not why. A run that died at a tool step may have gone wrong three steps earlier.
- Capped runs are censored at their last recorded step. If they would have died soon after, the curve is optimistic by that much. A run that timed out ends where it stopped, counted beside the kinds and not as a death; the header counts both.
- Excluded rows are not on the curve; the header counts them by reason.
- On one run, this is a description. Only a comparison of two stored runs on the same cells says whether anything moved, and only within what it could not have detected.
```

The first sentence matters most: the step a try stopped at is not the step where it went
wrong. Before blaming a step, run `where` on an outcome that passed and see where those tries
stop too.

## 3. Two runs

The same agent twice, asking whether the share of tries that fail moved by 7.5 points:

<!-- command -->
```
cd airline-agent && poisson-trace fix-check "tau2-airline 2026-09-15 a" \
  "tau2-airline 2026-09-15 b" --inputs all --max-mde 0.075
```

<!-- excerpt exit=0 -->
```
too small to tell  too few tries to see a 7.5-point drop by Trace's rule; a drop that size does not fit the results
```

**The limit.** The report says how small a change these tries could have shown:

<!-- excerpt exit=0 -->
```
## What it could not have detected

proportional change on every input, 80% power, α = 0.05, continuity-corrected normal approximation to the stratified statistic.

- a drop in failure share: could not have detected one below 11.1 points
- a rise in failure share: could not have detected one below 10.8 points

The line below follows the range, which is reliable here; these limits are for planning the next run.

**too small to tell: the 95% range, -6.0 to +8.1 points, does not lie inside ±7.5, which was asked for**
```

A verdict of *no significant difference* means no change of the size you asked about, and
nothing about smaller ones. The limit says how small is too small for these tries.

**The guidance.** When the verdict is *too small to tell*, the report says what would settle
it:

<!-- excerpt exit=0 -->
```
## Guidance

- repeats: 9 per arm on these 50 inputs would bring the limit to 7.5 points
- inputs: 101 inputs like these, at the present repeats, would do the same
- ceiling: --max-mde 0.0812 accepts this design as it stands
```

The last line offers the size these tries can already answer. Use it only if that size is the
smallest that matters to you, and you would have said so before looking.

**What it cannot say.** Every report on two runs ends with these six sentences:

<!-- excerpt exit=0 -->
```
## What this cannot say

- A difference between two stored runs is a difference between the runs. The version, the provider and the hour changed together unless the two were run side by side, and this test cannot separate them.
- Repeat runs of one input are read as separate draws and never as replays: a served model is not bit-identical on repeat, so nothing here matches a run of the old version to a run of the new by seed.
- If repeat runs of one input are near copies of one another, the run-level test overstates its confidence. The by-input line does not depend on that.
- Rows with no outcome are left out of both arms and counted in the header. A new version that times out where the old one failed does not show as a failure here.
- Trace reads the runs it is given. If the inputs were chosen by the old arm's own outcomes, or the more favourable of several runs was handed over, the confidence printed does not hold.
- The detection limit and the run counts are computed from these runs' own failure rates, which are estimates. They are a guide to the next design, not a promise about it.
```

They hold for every pair of runs, whatever the verdict. The first is why
[Check a fix](check-a-fix.md) asks for both versions to be run side by side.

## What this does not do

- It does not tell you which change to make. It says how far the numbers can be trusted.
- It does not see how many times you looked. Stopping as soon as a verdict reads well is not
  covered by the confidence the report states.
- It does not replace the report's own section *Before you act on this*, which is written for
  the runs you gave it and is the part to read first.
