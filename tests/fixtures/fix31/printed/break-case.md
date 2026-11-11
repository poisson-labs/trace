no significant difference  neither version failed

# Poisson Trace · fix check · sound-agent 2026-11-10 a (old) and sound-agent 2026-11-10 c (new)

## Summary

- Compared: old sound-agent 2026-11-10 a against new sound-agent 2026-11-10 c, on the same 6 inputs: 30 tries of each. A try counts as failed when it ended failed.
- Question: Did the new version fail more or less often than the old? You asked that the run be able to catch a 20-point drop in how often it fails.
- Answer: Neither version failed. The new version failed 0 of 30 tries and the old 0 of 30; the results fit anything from 12 fewer failures per 100 tries to 12 more, so a change of 20 points or more either way does not fit them (if tries of an input are independent).
- Next: If a change inside that range matters to you, plan a bigger run with your own harness, then run `poisson-trace fix-check` on it.

## Before you act on this

- They started 2 min apart. Trace can't tell whether they were run side by side, so anything else that changed between them (the provider, the model behind the API, the day) may be part of the difference, in either direction.
- Both runs name the same target (sound-agent); Trace can't tell what differs between them, only what you tell it.
- These results fit anything from 12 fewer failures per 100 tries to 12 more (ranges built this way hold the true difference about 95 times in 100, if tries are independent), which does not include a 20-point drop.
- Tries of the same input are counted as separate chances, and if they are near copies the answer is more confident than it should be.
- Trace would catch a 28-point rise 4 times in 5, a smaller rise less often.

## Runs

- old: sound-agent 2026-11-10 a (confirm-control) · target: sound-agent · status: complete · started: 2026-11-10T12:00:00.000000Z · declared repeats: 5
- Prove's tally (old): rows 30 · with outcome 30 · no outcome 0 · timed out 0 · infra 0 · other 0
- new: sound-agent 2026-11-10 c (confirm-2) · target: sound-agent · status: complete · started: 2026-11-10T12:02:00.000000Z · declared repeats: 5
- Prove's tally (new): rows 30 · with outcome 30 · no outcome 0 · timed out 0 · infra 0 · other 0
- the two runs started 2 min apart
- events: failed
- event failed: carried by neither run
- inputs: every input either run carries · selected 6 · compared 6 · left out 0
- rows used: old 30 (timed out 0, no outcome 0) · new 30 (timed out 0, no outcome 0)
- inputs short of the declared repeats: old 0 · new 0
- inputs with mixed outcomes across their repeats: old 0 · new 0
- no input gave mixed outcomes across its repeats in the old arm: the repeats may be copies of one another, and the by-input reading is the safer one
- no input gave mixed outcomes across its repeats in the new arm: the repeats may be copies of one another, and the by-input reading is the safer one

## The two versions

The old version and the new on the same inputs.

| version | runs | failed | failure share | did not fail |
|---|---|---|---|---|
| old | 30 | 0 | 0.0% | 100.0% |
| new | 30 | 0 | 0.0% | 100.0% |

The old version did not fail on 100.0% of its episodes on these inputs.

## Failures by kind

Each failed try's kind of failure, by the built-in rules; the same rules classified both runs. Counts, not a test: the verdict above is about all failures together.

| kind | old | old share | new | new share | change |
|---|---|---|---|---|---|
| all failures | 0 | 0.0% | 0 | 0.0% | 0.0 points |

of 30 tries of the old version and 30 of the new; a try has one kind

## The comparison

exact conditional Cochran-Mantel-Haenszel test, stratified by input over 6 inputs (0 informative), two-sided; α = 0.05.

new failures: observed 0, expected 0.000, variance 0.000; p = 1.000
difference: 0.0 points, new minus old (-12.5 to +12.5; Mantel-Haenszel weights; range: stratified Miettinen-Nurminen score interval, 95%, for these inputs as run)
by input: p = 1.000 (sign-flip over the 0 inputs that moved, exact); not part of the line below

## Consistency

failure share 0.000 · fails again – · κ – · within-input variance 0.000 against pooled 0.000

## What it could not have detected

proportional change on every input, 80% power, α = 0.05, continuity-corrected normal approximation to the stratified statistic.

- a drop in failure share: no limit; neither version failed on these inputs, so there is no failure to drop
- a rise in failure share: could not have detected one below 27.9 points

The line below follows the range, which is reliable here; these limits are for planning the next run.

**no significant difference (p = 1.000); the 95% range, -12.5 to +12.5 points, lies inside ±20**

## Inputs that changed

Fisher's exact test per input, Benjamini-Hochberg at q = 0.05 over 6 inputs; 0 flagged.

| input | old failed/runs | new failed/runs | change | p | q | flag |
|---|---|---|---|---|---|---|
| {"case":"case-1"} | 0/5 | 0/5 | 0.0 points | 1.000 | 1.000 | – |
| {"case":"case-4"} | 0/5 | 0/5 | 0.0 points | 1.000 | 1.000 | – |
| {"case":"case-6"} | 0/5 | 0/5 | 0.0 points | 1.000 | 1.000 | – |
| {"case":"case-3"} | 0/5 | 0/5 | 0.0 points | 1.000 | 1.000 | – |
| {"case":"case-5"} | 0/5 | 0/5 | 0.0 points | 1.000 | 1.000 | – |
| {"case":"case-2"} | 0/5 | 0/5 | 0.0 points | 1.000 | 1.000 | – |

A lone changed input is flagged only if its p is below α / M = 0.00833, and the smallest p an input of this design can give is 0.00794: a lone change can be flagged; a lone complete flip needs 5 repeats per arm. An input with no flag is not an input that did not change.

## What this cannot say

- A difference between two stored runs is a difference between the runs. The version, the provider and the hour changed together unless the two were run side by side, and this test cannot separate them.
- Repeat runs of one input are read as separate draws and never as replays: a served model is not bit-identical on repeat, so nothing here matches a run of the old version to a run of the new by seed.
- If repeat runs of one input are near copies of one another, the run-level test overstates its confidence. The by-input line does not depend on that.
- Rows with no outcome are left out of both arms and counted in the header. A new version that times out where the old one failed does not show as a failure here.
- Trace reads the runs it is given. If the inputs were chosen by the old arm's own outcomes, or the more favourable of several runs was handed over, the confidence printed does not hold.
- The detection limit and the run counts are computed from these runs' own failure rates, which are estimates. They are a guide to the next design, not a promise about it.

next: poisson-trace fix-check --help
