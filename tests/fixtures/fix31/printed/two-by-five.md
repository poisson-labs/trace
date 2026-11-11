too small to tell  too few tries to see a drop of any size

# Poisson Trace · fix check · synthetic 2026-01-01 a (old) and synthetic 2026-01-01 b (new)

## Summary

- Compared: old synthetic 2026-01-01 a against new synthetic 2026-01-01 b, on the same 2 inputs: 10 tries of each. A try counts as failed when it ended fail.
- Question: Did the new version fail more or less often than the old? You asked that the run be able to catch a 20-point drop in how often it fails.
- Answer: Can't tell. The new version failed 0 of 10 tries and the old 0 of 10, and with these tries Trace can't reliably catch a drop of any size.
- Next: Plan a bigger run with your own harness (more tries per input on both versions), then run `poisson-trace fix-check` on it.

## Before you act on this

- They started 1 h 0 min apart. Trace can't tell whether they were run side by side, so anything else that changed between them (the provider, the model behind the API, the day) may be part of the difference, in either direction.
- Both runs name the same target (synthetic/target); Trace can't tell what differs between them, only what you tell it.
- These results fit anything from 30 fewer failures per 100 tries to 30 more, but that range is only a rough guide here and may be off either way (fewer than 3 inputs): don't use it to rule sizes in or out.
- Tries of the same input are counted as separate chances, and if they are near copies the answer is more confident than it should be.

## Runs

- old: synthetic 2026-01-01 a (old) · target: synthetic/target · status: complete · started: 2026-01-01T00:00:00.000000Z · declared repeats: not recorded
- Prove's tally (old): rows 10 · with outcome 10 · no outcome 0 · timed out 0 · infra 0 · other 0
- new: synthetic 2026-01-01 b (new) · target: synthetic/target · status: complete · started: 2026-01-01T01:00:00.000000Z · declared repeats: not recorded
- Prove's tally (new): rows 10 · with outcome 10 · no outcome 0 · timed out 0 · infra 0 · other 0
- the two runs started 1 h 0 min apart
- events: fail
- event fail: carried by neither run
- inputs: every input either run carries · selected 2 · compared 2 · left out 0
- rows used: old 10 (timed out 0, no outcome 0) · new 10 (timed out 0, no outcome 0)
- inputs short of the declared repeats: old no repeats declared · new no repeats declared
- inputs with mixed outcomes across their repeats: old 0 · new 0
- no input gave mixed outcomes across its repeats in the old arm: the repeats may be copies of one another, and the by-input reading is the safer one
- no input gave mixed outcomes across its repeats in the new arm: the repeats may be copies of one another, and the by-input reading is the safer one

## The two versions

The old version and the new on the same inputs.

| version | runs | failed | failure share | did not fail |
|---|---|---|---|---|
| old | 10 | 0 | 0.0% | 100.0% |
| new | 10 | 0 | 0.0% | 100.0% |

The old version did not fail on 100.0% of its episodes on these inputs.

## Failures by kind

Each failed try's kind of failure, by the built-in rules; the same rules classified both runs. Counts, not a test: the verdict above is about all failures together.

| kind | old | old share | new | new share | change |
|---|---|---|---|---|---|
| all failures | 0 | 0.0% | 0 | 0.0% | 0.0 points |

of 10 tries of the old version and 10 of the new; a try has one kind

## The comparison

exact conditional Cochran-Mantel-Haenszel test, stratified by input over 2 inputs (0 informative), two-sided; α = 0.05.

new failures: observed 0, expected 0.000, variance 0.000; p = 1.000
difference: 0.0 points, new minus old (-29.9 to +29.9; Mantel-Haenszel weights; range: stratified Miettinen-Nurminen score interval, 95%, for these inputs as run; rough here: fewer than 3 inputs)
by input: p = 1.000 (sign-flip over the 0 inputs that moved, exact); not part of the line below

## Consistency

failure share 0.000 · fails again – · κ – · within-input variance 0.000 against pooled 0.000

## What it could not have detected

proportional change on every input, 80% power, α = 0.05, continuity-corrected normal approximation to the stratified statistic.

- a drop in failure share: no limit; neither version failed on these inputs, so there is no failure to drop
- a rise in failure share: could not have detected one below 64.8 points

**too small to tell: could not have detected a drop in failure share below or at 0.00 points, which is every failure gone, and 20 was asked for**

## Guidance

- no number of repeats on these inputs reaches 20 points
- no number of inputs at the present repeats reaches 20 points
- ceiling: no value of --max-mde accepts this design as it stands

These numbers assume the next runs fail at the rates these did, input by input, and that new inputs resemble the present ones: for failing inputs chosen by a rule, chosen by the same rule. It is a guide to the next design and not a promise about it: a design built to the number has an expected limit at the ceiling asked for, so about half the time its own limit will land a little above.

## Inputs that changed

Fisher's exact test per input, Benjamini-Hochberg at q = 0.05 over 2 inputs; 0 flagged.

| input | old failed/runs | new failed/runs | change | p | q | flag |
|---|---|---|---|---|---|---|
| {"input":"i1"} | 0/5 | 0/5 | 0.0 points | 1.000 | 1.000 | – |
| {"input":"i0"} | 0/5 | 0/5 | 0.0 points | 1.000 | 1.000 | – |

A lone changed input is flagged only if its p is below α / M = 0.025, and the smallest p an input of this design can give is 0.00794: a lone change can be flagged; a lone complete flip needs 5 repeats per arm. An input with no flag is not an input that did not change.

## What this cannot say

- A difference between two stored runs is a difference between the runs. The version, the provider and the hour changed together unless the two were run side by side, and this test cannot separate them.
- Repeat runs of one input are read as separate draws and never as replays: a served model is not bit-identical on repeat, so nothing here matches a run of the old version to a run of the new by seed.
- If repeat runs of one input are near copies of one another, the run-level test overstates its confidence. The by-input line does not depend on that.
- Rows with no outcome are left out of both arms and counted in the header. A new version that times out where the old one failed does not show as a failure here.
- Trace reads the runs it is given. If the inputs were chosen by the old arm's own outcomes, or the more favourable of several runs was handed over, the confidence printed does not hold.
- The detection limit and the run counts are computed from these runs' own failure rates, which are estimates. They are a guide to the next design, not a promise about it.

next: poisson-trace fix-check --help
