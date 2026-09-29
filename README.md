# Poisson Trace

Where in the workflow do runs die, and did the change make them fail less.

Poisson Trace reads runs that [Prove](https://github.com/poisson-labs/prove) has already
stored and answers two questions about them, each with a stated confidence and with what the
design could not have detected.

**Where runs die.** `where` puts every run on one clock (the index of the step it was
executing) and draws the survival curve over that clock: at step 10, what share of runs was
still going; at step 20; at step 30. Runs that ended normally, timed out or hit the capture
cap are censored, never counted as deaths. The curve is split by the kind of step runs die at
(model call, tool call, guardrail, agent turn), each part with a stated interval. `compare`
takes two stored runs, a before and an after, and says whether the curves differ.

**Whether a change made runs fail less.** Teams check a change by re-running the inputs that
failed and counting how many now succeed. That count has no control: on an agent where
nothing changed, some of those inputs succeed on a re-run anyway, and the count cannot say
how many. `fix-check` does the same job with the missing parts added: the old version re-run
on the same inputs beside the new one, a test that compares the two inside each input, the
difference with an interval, and one line that reads *different*, *no significant
difference* or *too small to tell*. `changes` names the inputs whose failure share moved
between two runs, with a multiple-testing correction. Whenever the line is *too small to
tell*, the report says how many repeats or how many inputs would settle it.

Every number prints with what the run could not have detected.

Released with the Poisson Labs post responding to LangSmith Engine v2 (2026-10-01; the post
links here). Trace is a reader of stored runs: it runs nothing, captures nothing, patches
nothing, phones nowhere.

## Install

Prove is not yet public, so it is installed from a checkout and is not a declared
dependency of this package:

```
pip install poisson-trace
pip install -e /path/to/prove
```

Nobody outside Poisson Labs can run Trace until Prove is public. The command refuses at
start, in one sentence, when the `proofload` package is missing or is not version 0.0.1.

From a clone of this repository, with the same two lines:

```
git clone https://github.com/poisson-labs/trace
cd trace
python -m venv .venv && . .venv/bin/activate
pip install .
pip install -e /path/to/prove
poisson-trace where 20260925T234602Z-3ea0 --store tests/fixtures/cs --event unresolved
```

## Use

Point Trace at a Prove store (the directory that holds one `manifest.json` per run) and name
the outcomes that count as a failure:

```
poisson-trace where RUN --store ROOT --event NAME [--event NAME ...]
                   [--by kind|step] [--at STEP ...] [--boot B] [--seed S]
                   [--svg FILE] [--json]

poisson-trace compare A B --store ROOT --event NAME [--event NAME ...] --max-mde-hr X
                     [--by kind|step] [--at STEP ...] [--alpha A] [--json]

poisson-trace fix-check OLD NEW --store ROOT --event NAME [--event NAME ...]
                       ( --failing-from RUN [--min-failures M] | --inputs all )
                       --max-mde X [--alpha A] [--seed S] [--top N] [--json]

poisson-trace changes A B --store ROOT --event NAME [--event NAME ...]
                     [--alpha A] [--top N] [--json]
```

- `--store` is required; there is no default store. `--event` is required and repeatable;
  the union of the names is "died" for `where` and `compare` and "failed" for `fix-check`
  and `changes`. A name no stored row carries is refused, and the refusal lists the outcomes
  the runs do carry.
- `--json` prints the structure (`poisson-trace.where/1`, `.compare/1`, `.fix-check/1` or
  `.changes/1`) and nothing else. It is byte-identical across invocations on equal inputs.
- Exit codes: 0 report printed; 1 refusal (one sentence); 2 *too small to tell* (`compare`
  and `fix-check`).

For `where` and `compare`:

- `--by kind` (the default) labels the step a run died at by the leaf span's kind (`llm`,
  `tool`, `retrieval`, `db`, `http`, `agent`, `other`); `--by step` labels it by the
  nearest declared step name.
- `--at STEP` adds a row reading the curve at that step; repeatable.
- `--svg FILE` writes the curve as an SVG, the one file `where` writes.
- `--max-mde-hr` is the largest minimum detectable hazard ratio you will accept; it has no
  default, because the tool supplies no number of its own.

For `fix-check` and `changes`:

- An **input** is one config cell of a Prove sweep (one `config_hash`). On the tau2 runs
  below an input is a task; where a sweep crosses tasks with another setting, each (task,
  setting) cell is its own input.
- Exactly one of `--failing-from RUN` and `--inputs all` is required; there is no default,
  because which inputs are compared is the decision that makes the check honest.
  `--failing-from RUN` takes the inputs of RUN with at least `--min-failures` failed rows
  (default 1). RUN is the *selecting run*, and it must be neither OLD nor NEW: its failures
  on those inputs are there by selection, so both arms must be fresh re-runs. `--inputs all`
  takes every input either run carries, with no selection.
- `--max-mde` is the largest detection limit you will accept, as a fraction of failure share
  (`0.20` is twenty points). It is required and has no default.
- `--seed` seeds the by-input reading's draws when more than 14 inputs moved. `--top N`
  (default 10) bounds the table of inputs in the markdown; every flagged input prints
  whatever `--top` says, and the JSON lists every input.
- Neither verb reads a trace, a seed or a replicate index. They work on a run stored with no
  capture, and repeat runs of one input are read as separate draws, never as replays.

`where` prints the survival curve over step index with a 95% band (Kaplan–Meier,
Greenwood), the median step, the deaths by kind of step with a bootstrap band on each
(Aalen–Johansen), the counts of runs ended, timed out, capped and excluded, and a closing
block of what the curve cannot say.

`compare` prints the log-rank test stratified by config cell over the cells both runs
carry, the direction, the minimum detectable hazard ratio (Schoenfeld, 80% power) and one
of three lines: *different*, *no significant difference*, or *too small to tell*.

`fix-check` prints the control (how often the old version failed when re-run on the same
inputs, beside the new), the exact conditional Cochran–Mantel–Haenszel test stratified by
input, the difference in points with Sato's interval, a second reading by input that does
not assume repeats are independent, how consistent the failures were, the smallest drop and
rise in failure share it could have detected, one of the three lines, and the per-input
table of `changes`.

`changes` prints Fisher's exact test per input with Benjamini–Hochberg across the inputs,
the inputs flagged, and what the design could not have flagged.

### How a run is placed (`where`, `compare`)

A step is a leaf span (a span that is the parent of no other span), in `(start_ns,
span_id)` order; a run with `L` leaves ran `L` steps. Each stored row lands as one of:

| Placement | Rule, in this order | On the curve |
|---|---|---|
| excluded | no trace; an unreadable trace; zero leaves; no outcome and not a timeout | not placed; counted by reason |
| timed out | no outcome and Prove's timeout mark | censored at `L` |
| capped | the trace holds at least `capture.max_spans` spans | censored at `L` |
| died | the outcome is one of the `--event` names | died at `L`; cause = kind of leaf `L` |
| ended | any other outcome | censored at `L` |

Timed out and capped are checked before died: a run whose trace stops early has an unknown
death step even if its outcome says it failed.

### How a row is counted (`fix-check`, `changes`)

| Row or input | Rule | Where it shows |
|---|---|---|
| row whose outcome is an event | failed | both counts |
| row with any other outcome | did not fail | the runs count |
| row with no outcome and Prove's timeout mark | left out | header, *timed out*, per arm |
| row with no outcome otherwise | left out | header, *no outcome*, per arm |
| input selected but absent from OLD | left out | *not re-run on the old version* |
| input present in OLD, absent from NEW | left out | *not re-run on the new version* |
| input whose every row in an arm has no outcome | left out | *no outcome on the old / new version* |

Reasons are tried in that order and an input is counted under the first that applies. Rows
with no outcome are left out of numerator and denominator, as Prove's `diff` does. This is
the one rule that can hide a real effect (a new version that times out where the old one
failed), so the header prints the counts per arm.

## Checking a change: the recipe

Trace runs nothing; the re-runs are Prove sweeps.

1. A Prove run S of the old version has failures. `--failing-from S` will name its failing
   inputs.
2. Write one sweep file holding those inputs and a number of repeats. `poisson-trace
   fix-check` on any earlier pair prints the number under *Guidance*.
3. Run that sweep with Prove twice, once per version, side by side, not the old version
   from last week.
4. `poisson-trace fix-check OLD NEW --store ROOT --event NAME --failing-from S --max-mde X`.

## Worked examples

The seven stores under `tests/fixtures/` are real runs stored by Prove on our machines.
Four were copied with their observation bodies removed, one was copied whole (it was stored
with no capture) and two are outcome-only copies (`tests/fixtures/PROVENANCE.md` has the
sources, the recipes and the digests). Nothing Trace reads was removed, so every block below
is byte-for-byte what the original stores give, and what a clean clone prints.

### One run: the OpenAI customer-service demo, recorded

`cs_agents/record` is the OpenAI customer-service agent demo recorded on gpt-4.1-mini: 24
episodes, spans nested three deep (turn > workflow > generation, with guardrail agents
beside them), four failure outcomes.

<!-- command -->
```
poisson-trace where 20260925T234602Z-3ea0 --store tests/fixtures/cs \
  --event forbidden_action --event unresolved --event max_turns --event app_error \
  --at 20 --at 40 --svg docs/figures/cs-record.svg
```

<!-- output exit=0 -->
```
# Poisson Trace · where runs die · 20260925T234602Z-3ea0

## Run

- run: 20260925T234602Z-3ea0 · target: cs_agents/record · t_unit: turns · status: complete · no cap
- Prove's tally: rows 24 · with outcome 24 · no outcome 0 · timed out 0 · infra 0 · other 0
- placement: placed 24 · died 7 · ended 17 · timed out 0 · capped 0 · excluded 0
- events: app_error, forbidden_action, max_turns, unresolved

## Survival over step index

Kaplan–Meier over leaf-span index; band: Greenwood, plain, 95%.

| step | at risk | died | S | 95% band |
|---|---|---|---|---|
| 24 | 18 | 1 | 0.944 | 0.839 – 1.000 |
| 30 | 15 | 1 | 0.881 | 0.727 – 1.000 |
| 33 | 11 | 1 | 0.801 | 0.596 – 1.000 |
| 35 | 10 | 1 | 0.721 | 0.484 – 0.959 |
| 48 | 5 | 1 | 0.577 | 0.261 – 0.893 |
| 50 | 4 | 1 | 0.433 | 0.092 – 0.774 |
| 58 | 2 | 1 | 0.216 | 0.000 – 0.561 |

median step: 50
S(20) = 1.000 (1.000 – 1.000)
S(40) = 0.721 (0.484 – 0.959)

## Where they die, by kind of step

Aalen–Johansen cumulative incidence; band: bootstrap 95%, B = 1000, seed = 0.

| kind | deaths | F at step 58 | 95% band |
|---|---|---|---|
| llm | 4 | 0.343 | 0.056 – 0.679 |
| agent | 3 | 0.441 | 0.000 – 0.871 |

sum of F = 1 − S = 0.784 (1 − 0.216)

## What this cannot say

- The step index is where the run stopped, not why. A run that died at a tool step may have gone wrong three steps earlier.
- Timed-out and capped runs are censored at their last recorded step. If they would have died soon after, the curve is optimistic by that much; the header counts them.
- Excluded rows are not on the curve; the header counts them by reason.
- On one run, this is a description. Only a comparison of two stored runs on the same cells says whether anything moved, and only within what it could not have detected.
```

Seven of 24 runs died, four at a model call and three at a guardrail agent. The Greenwood
band at step 40 spans a quarter of the axis and the bootstrap bands on the two kinds span
most of `[0, 1]`: 24 episodes is a description, and the report says so.

[`docs/figures/cs-record.svg`](docs/figures/cs-record.svg) is the `--svg` output of that
command.

### Two runs: the same agent twice, nothing changed

`tests/fixtures/tau2` holds two runs of `tau2-airline/gpt-4.1-mini-2025-04-14@v0`: 50
tasks × 4 replicates each, the same seeds, ten minutes apart, nothing changed between them.
On the first, `where` places 200 runs, 110 died and 90 ended; steps run from 6 to 44 with a
median step of 22; `S(10)`, `S(20)` and `S(30)` are 0.964, 0.599 and 0.163
([`docs/figures/tau2-a.svg`](docs/figures/tau2-a.svg)). Comparing the two as a before and
an after, with a ceiling of 1.3 on the minimum detectable hazard ratio:

<!-- command -->
```
poisson-trace compare 20260915T210140Z-4847 20260915T211148Z-965d --store tests/fixtures/tau2 \
  --event unsolved --max-mde-hr 1.3 --at 10 --at 20 --at 30
```

<!-- output exit=2 -->
```
# Poisson Trace · compare · 20260915T210140Z-4847 (before) and 20260915T211148Z-965d (after)

## Run A (before)

- run: 20260915T210140Z-4847 · target: tau2-airline/gpt-4.1-mini-2025-04-14@v0 · t_unit: steps · status: complete · cap: 200 spans
- Prove's tally: rows 200 · with outcome 200 · no outcome 0 · timed out 0 · infra 0 · other 0
- placement: placed 200 · died 110 · ended 90 · timed out 0 · capped 0 · excluded 0
- events: unsolved

## Run B (after)

- run: 20260915T211148Z-965d · target: tau2-airline/gpt-4.1-mini-2025-04-14@v0 · t_unit: steps · status: complete · cap: 200 spans
- Prove's tally: rows 200 · with outcome 200 · no outcome 0 · timed out 0 · infra 0 · other 0
- placement: placed 200 · died 112 · ended 88 · timed out 0 · capped 0 · excluded 0
- events: unsolved

## Comparison

log-rank, stratified by config cell over 50 common cells (excluded: 0 in A only, 0 in B only), unpaired (the runs share a run_salt); α = 0.05.

| arm | placed | died | observed | expected |
|---|---|---|---|---|
| A (before) | 200 | 110 | 110 | 113.805 |
| B (after) | 200 | 112 | 112 | 108.195 |

statistic: χ² = 0.411 on 1 d.f., variance 35.223, p = 0.521
direction: runs die later in A (before) than in B (after): runs die earlier in B
S_B(10) − S_A(10) = 0.005 (-0.031 – 0.041, Wald 95%)
S_B(20) − S_A(20) = -0.050 (-0.164 – 0.065, Wald 95%)
S_B(30) − S_A(30) = 0.064 (-0.048 – 0.176, Wald 95%)

### Per kind

cause-specific log-rank, stratified by config cell, deaths of other kinds censored at their step; Benjamini–Hochberg at q = 0.05.

| kind | deaths A | deaths B | χ² | p | q | could not have detected a hazard ratio below |
|---|---|---|---|---|---|---|
| llm | 110 | 112 | 0.411 | 0.521 | 0.521 | 1.457 |

could not have detected a hazard ratio below 1.457 (Schoenfeld, 80% power, α = 0.05, 222 deaths over the common cells, allocation 0.500)

**too small to tell: could not have detected a hazard ratio below 1.457, and 1.3 was asked for**

## Guidance

- deaths: 457 would bring the detectable hazard ratio to 1.3; this design has 222
- runs: 824 placed runs at the present share of deaths, which is 103 inputs at the present repeats, or 9 repeats per arm on these 50; this design has 400 placed runs
- ceiling: --max-mde-hr 1.457 accepts this design as it stands

These numbers assume the share of runs that die holds in the next runs, and that new inputs resemble the present ones. It is a guide to the next design and not a promise about it: a design built to the number has an expected limit at the ceiling asked for, so about half the time its own limit will land a little above.

For the share of runs that fail, input by input, and the inputs that changed: poisson-trace fix-check A B --inputs all

## What this cannot say

- The step index is where the run stopped, not why. A run that died at a tool step may have gone wrong three steps earlier.
- Timed-out and capped runs are censored at their last recorded step. If they would have died soon after, the curve is optimistic by that much; the header counts them.
- Excluded rows are not on the curve; the header counts them by reason.
- On one run, this is a description. Only a comparison of two stored runs on the same cells says whether anything moved, and only within what it could not have detected.
```

It exits 2, and the guidance says what would settle it: 457 deaths, which is 824 placed
runs, 103 inputs at 4 repeats or 9 repeats per arm on these 50. With the ceiling the report
offers,

<!-- command -->
```
poisson-trace compare 20260915T210140Z-4847 20260915T211148Z-965d --store tests/fixtures/tau2 \
  --event unsolved --max-mde-hr 1.457
```

the same numbers end

<!-- excerpt exit=0 -->
```
**no significant difference (p = 0.521); could not have detected a hazard ratio below 1.457**
```

and exit 0, with no guidance block. That pair of lines is the point: the same agent run
twice, 400 episodes, and the design could still not have seen a 40% change in the hazard.

### A real before and after: the patched pilot

`tests/fixtures/tau2` also holds a real change: the same agent with a guardrail patch
(`tau2_pilot.rollout:rollout_patched`), run once on tasks 0 to 9 and stored with no capture.
Ten runs is the size of check teams make. The tau2 pair gives the design its other two
runs: the first run (`4847`) selects the inputs that failed, and the second (`965d`) is the
old version re-run fresh on them.

<!-- command -->
```
poisson-trace fix-check 20260915T211148Z-965d 20260917T140219Z-2b2d --store tests/fixtures/tau2 \
  --event unsolved --failing-from 20260915T210140Z-4847 --max-mde 0.20
```

<!-- output exit=2 -->
```
# Poisson Trace · fix check · 20260915T211148Z-965d (old) and 20260917T140219Z-2b2d (new)

## Runs

- old: 20260915T211148Z-965d · target: tau2-airline/gpt-4.1-mini-2025-04-14@v0 · status: complete · started: 2026-09-15T21:11:49.277633Z · declared repeats: 4
- Prove's tally (old): rows 200 · with outcome 200 · no outcome 0 · timed out 0 · infra 0 · other 0
- new: 20260917T140219Z-2b2d · target: tau2-airline/gpt-4.1-mini-2025-04-14@v0 · status: complete · started: 2026-09-17T14:02:21.184575Z · declared repeats: 1
- Prove's tally (new): rows 10 · with outcome 10 · no outcome 0 · timed out 0 · infra 0 · other 0
- the two runs started 40 h 50 min apart
- events: unsolved
- inputs: inputs that failed at least 1 time in 20260915T210140Z-4847 · selected 37 · compared 6 · left out 31 (not re-run on the new version 31)
- rows used: old 24 (timed out 0, no outcome 0) · new 6 (timed out 0, no outcome 0)
- inputs short of the declared repeats: old 0 · new 0
- inputs with mixed outcomes across their repeats: old 4 · new 0

## The control

The old version, re-run on the same inputs with nothing changed.

| version | runs | failed | failure share | did not fail on re-run |
|---|---|---|---|---|
| old | 24 | 18 | 75.0% | 25.0% |
| new | 6 | 3 | 50.0% | 50.0% |

Re-running these inputs and counting the runs that did not fail would have read 25.0% on the old version, where nothing changed.

## The comparison

exact conditional Cochran-Mantel-Haenszel test, stratified by input over 6 inputs (4 informative), two-sided; α = 0.05.

new failures: observed 3, expected 4.200, variance 0.800; p = 0.269
difference: -25.0 points, new minus old (-60.1 to +10.1; Mantel-Haenszel weights; interval: Sato variance, large-sample, 95%)
by input: p = 0.375 (sign-flip over the 4 inputs that moved, exact); not part of the line below

## Consistency

failure share 0.700 · fails again 0.762 · κ 0.206 · within-input variance 0.167 against pooled 0.210
a comparison that ignored the inputs would need 1/(1 − κ) = 1.26 times the runs

## What it could not have detected

proportional change on every input, 80% power, α = 0.05, continuity-corrected normal approximation to the stratified statistic.

- a drop in failure share: could not have detected one below 64.3 points
- a rise in failure share: no limit; even every run failing, a rise of 30.0 points, would have been detected less than four times in five

**too small to tell: could not have detected a drop in failure share below 64.3 points, and 20 was asked for**

## Guidance

- repeats: 16 per arm on these 6 inputs would bring the limit to 20 points
- inputs: 55 inputs like these, at the present repeats, would do the same
- ceiling: --max-mde 0.6430 accepts this design as it stands

These numbers assume the next runs fail at the rates these did, input by input, and that new inputs resemble the present ones: for failing inputs chosen by a rule, chosen by the same rule. It is a guide to the next design and not a promise about it: a design built to the number has an expected limit at the ceiling asked for, so about half the time its own limit will land a little above.

## Inputs that changed

Fisher's exact test per input, Benjamini-Hochberg at q = 0.05 over 6 inputs; 0 flagged.

| input | old failed/runs | new failed/runs | change | p | q | flag | could not have detected a rise below |
|---|---|---|---|---|---|---|---|
| {"task_id":"2"} | 3/4 | 0/1 | -75.0 points | 0.400 | 1.000 | – | 25.0 points |
| {"task_id":"5"} | 3/4 | 0/1 | -75.0 points | 0.400 | 1.000 | – | 25.0 points |
| {"task_id":"7"} | 4/4 | 1/1 | 0.0 points | 1.000 | 1.000 | – | 12.5 points |
| {"task_id":"9"} | 4/4 | 1/1 | 0.0 points | 1.000 | 1.000 | – | 12.5 points |
| {"task_id":"1"} | 3/4 | 1/1 | +25.0 points | 1.000 | 1.000 | – | 25.0 points |
| {"task_id":"3"} | 1/4 | 0/1 | -25.0 points | 1.000 | 1.000 | – | 75.0 points |

A lone changed input is flagged only if its p is below α / M = 0.00833, and the smallest p an input of this design can give is 0.2: no input can be flagged whatever happens; a lone complete flip needs 5 repeats per arm. An input with no flag is not an input that did not change.

## What this cannot say

- A difference between two stored runs is a difference between the runs. The version, the provider and the hour changed together unless the two were run side by side, and this test cannot separate them.
- Repeat runs of one input are read as separate draws and never as replays: a served model is not bit-identical on repeat, so nothing here matches a run of the old version to a run of the new by seed.
- If repeat runs of one input are near copies of one another, the run-level test overstates its confidence. The by-input line does not depend on that.
- Rows with no outcome are left out of both arms and counted in the header. A new version that times out where the old one failed does not show as a failure here.
- Trace reads the runs it is given. If the inputs were chosen by the old arm's own outcomes, or the more favourable of several runs was handed over, the confidence printed does not hold.
- The detection limit and the run counts are computed from these runs' own failure rates, which are estimates. They are a guide to the next design, not a promise about it.
```

It exits 2. Counting re-runs reads "3 of 6 failing inputs now succeed". The control says a
quarter of the old version's runs on those inputs did too, with nothing changed, and the
design cannot tell the patch from that: it could not have detected a drop smaller than 64.3
points, and the interval runs from a 60.1-point drop to a 10.1-point rise. The guidance
says what would settle a 20-point question: 16 repeats per arm on these 6 inputs, or 55
inputs like these. The pilot was ten runs and was never meant to settle anything.

Naming the selecting run as the old arm is refused, in one sentence and with exit 1:

<!-- command -->
```
poisson-trace fix-check 20260915T211148Z-965d 20260917T140219Z-2b2d --store tests/fixtures/tau2 \
  --event unsolved --failing-from 20260915T211148Z-965d --max-mde 0.20
```

<!-- output exit=1 -->
```
the selecting run 20260915T211148Z-965d is also the old arm; both arms must be fresh re-runs, because the selecting run's failures on these inputs are there by selection
```

### The inputs that changed: HumanEval/129

`tests/fixtures/humaneval` holds two runs of one HumanEval agent (gpt-4o-mini): 164 problems
at temperatures 0.0 and 0.7, so 328 inputs, × 32 repeats each, 56 minutes apart, nothing
changed by us between them.

<!-- command -->
```
poisson-trace changes 20260905T185407Z-0313 20260905T195009Z-18ac --store tests/fixtures/humaneval \
  --event failed_assertion --event crashed --top 2
```

<!-- output exit=0 -->
```
# Poisson Trace · changes · 20260905T185407Z-0313 (A) and 20260905T195009Z-18ac (B)

## Runs

- A: 20260905T185407Z-0313 · target: golden-pilot/gpt-4o-mini-2024-07-18@v0 · status: complete · started: 2026-09-05T18:54:08.373078Z · declared repeats: 32
- Prove's tally (A): rows 10496 · with outcome 10496 · no outcome 0 · timed out 0 · infra 0 · other 0
- B: 20260905T195009Z-18ac · target: golden-pilot/gpt-4o-mini-2024-07-18@v0 · status: complete · started: 2026-09-05T19:50:10.199374Z · declared repeats: 32
- Prove's tally (B): rows 10496 · with outcome 10496 · no outcome 0 · timed out 0 · infra 0 · other 0
- the two runs started 56 min apart
- events: crashed, failed_assertion
- inputs: A carries 328, B carries 328 · compared 328, each with an outcome in both runs · in A only 0 · in B only 0

## Inputs that changed

Fisher's exact test per input, Benjamini-Hochberg at q = 0.05 over 328 inputs; 2 flagged.

| input | A failed/runs | B failed/runs | change | p | q | flag | could not have detected a rise below |
|---|---|---|---|---|---|---|---|
| {"task_id":"HumanEval/129","temperature":0.7} | 12/32 | 32/32 | +62.5 points | 2.30e-08 | 7.55e-06 | failed more in B | 34.2 points |
| {"task_id":"HumanEval/129","temperature":0.0} | 20/32 | 32/32 | +37.5 points | 1.38e-04 | 0.023 | failed more in B | 28.9 points |

2 of 328 inputs shown, by ascending p; --json lists all.

A lone changed input is flagged only if its p is below α / M = 0.000152, and the smallest p an input of this design can give is 1.09e-18: a lone change can be flagged; a lone complete flip needs 9 repeats per arm. An input with no flag is not an input that did not change.

## What this cannot say

- A difference between two stored runs is a difference between the runs. The version, the provider and the hour changed together unless the two were run side by side, and this test cannot separate them.
- Repeat runs of one input are read as separate draws and never as replays: a served model is not bit-identical on repeat, so nothing here matches a run of the old version to a run of the new by seed.
- If repeat runs of one input are near copies of one another, the run-level test overstates its confidence. The by-input line does not depend on that.
- Rows with no outcome are left out of both arms and counted in the header. A new version that times out where the old one failed does not show as a failure here.
- Trace reads the runs it is given. If the inputs were chosen by the old arm's own outcomes, or the more favourable of several runs was handed over, the confidence printed does not hold.
- The detection limit and the run counts are computed from these runs' own failure rates, which are estimates. They are a guide to the next design, not a promise about it.
```

Two of 328 inputs are flagged, both HumanEval/129, and nothing else. Prove's own `diff`
with `fisher_bh`, on the event `failed_assertion`, flags the same two cells with the same p
and q. One problem broke between the two runs, on an agent nobody touched. `fix-check` on the same pair reads the whole of it:

<!-- command -->
```
poisson-trace fix-check 20260905T185407Z-0313 20260905T195009Z-18ac --store tests/fixtures/humaneval \
  --event failed_assertion --event crashed --inputs all --max-mde 0.05
```

<!-- excerpt exit=0 -->
```
## The comparison

exact conditional Cochran-Mantel-Haenszel test, stratified by input over 328 inputs (58 informative), two-sided; α = 0.05.

new failures: observed 1387, expected 1362.500, variance 131.139; p = 0.036
difference: +0.47 points, new minus old (+0.04 to +0.90; Mantel-Haenszel weights; interval: Sato variance, large-sample, 95%)
by input: p = 0.127 (sign-flip over the 47 inputs that moved, 100,000 draws, seed = 0); not part of the line below
```

<!-- excerpt exit=0 -->
```
**different: the new version failed more on these inputs (exact Cochran-Mantel-Haenszel, stratified by input, p = 0.036)**
```

The runs differ (p = 0.036), the inputs did not move as a body (by input, p = 0.127), and
the flags name the one problem that did. That is a true statement about two runs and a false
one about two versions, which is why the report's first closing sentence is that a
difference between two stored runs is a difference between the runs, and why the recipe says
side by side.

### Guidance: what would settle it

The tau2 pair again, nothing changed, this time asking whether the share of runs that fail
moved by 10 points:

<!-- command -->
```
poisson-trace fix-check 20260915T210140Z-4847 20260915T211148Z-965d --store tests/fixtures/tau2 \
  --event unsolved --inputs all --max-mde 0.10
```

<!-- excerpt exit=2 -->
```
## Consistency

failure share 0.555 · fails again 0.792 · κ 0.531 · within-input variance 0.116 against pooled 0.247
a comparison that ignored the inputs would need 1/(1 − κ) = 2.13 times the runs

## What it could not have detected

proportional change on every input, 80% power, α = 0.05, continuity-corrected normal approximation to the stratified statistic.

- a drop in failure share: could not have detected one below 11.1 points
- a rise in failure share: could not have detected one below 10.8 points

**too small to tell: could not have detected a drop in failure share below 11.1 points, and 10 was asked for**

## Guidance

- repeats: 5 per arm on these 50 inputs would bring the limit to 10 points
- inputs: 61 inputs like these, at the present repeats, would do the same
- ceiling: --max-mde 0.1109 accepts this design as it stands

These numbers assume the next runs fail at the rates these did, input by input, and that new inputs resemble the present ones: for failing inputs chosen by a rule, chosen by the same rule. It is a guide to the next design and not a promise about it: a design built to the number has an expected limit at the ceiling asked for, so about half the time its own limit will land a little above.
```

Failures on these tasks are consistent (an input that failed once fails again 79% of the
time), so comparing inside each input needs fewer than half the runs a pooled comparison
would. Even so, 200 runs per arm could not have detected a drop smaller than 11.1 points.
With `--max-mde 0.1109`, the ceiling the report offers, the same numbers read *no
significant difference* and exit 0. The per-input table of the same report ends

<!-- excerpt exit=2 -->
```
A lone changed input is flagged only if its p is below α / M = 0.001, and the smallest p an input of this design can give is 0.0286: a lone changed input cannot be flagged; at least 29 inputs would have to flip completely together; a lone complete flip needs 7 repeats per arm. An input with no flag is not an input that did not change.
```

so on this design no change to a single task could have been flagged at all.

## How the fix check decides

- **The test** is the exact conditional Cochran–Mantel–Haenszel test, stratified by input.
  Each input is a 2 × 2 table (version × failed or not). Given each input's total failures,
  the new version's count on it is hypergeometric under the null, whatever that input's
  failure rate; the distribution of the sum is computed in full and the p-value is exact,
  two-sided, with no normal approximation. An input that always fails, or never does, adds
  nothing: no signal and no noise. With one input it is Fisher's exact test; with one run
  per arm per input it is the exact McNemar test.
- **The difference** is the Mantel–Haenszel risk difference in points, new minus old, with
  Sato's variance for the interval. The interval is large-sample and labelled so. The line
  follows the test, never the interval, and the report says so when the two disagree.
- **The by-input reading** treats each input as one observation and flips its sign. It does
  not need repeat runs to be independent, so it is the check on the case where repeats are
  near copies of one another. It prints beside the test and has no part in the line.
- **The detection limit** is the smallest proportional drop in every input's failure rate
  that the test would have detected four times in five, stated in points of failure share.
  `--max-mde` gates on the drop; the rise prints beside it.
- **The flags** are Fisher's exact test per input, then Benjamini–Hochberg across all the
  inputs compared, number for number what Prove's `diff` does with `fisher_bh`.
- **The guidance** is computed with the function that stated the limit, so the number it
  suggests cannot drift from the number that refused the design, and the ceiling it offers
  is accepted when handed back.

## What this cannot say

`where` and `compare`:

- The step index is where the run stopped, not why. A run that died at a tool step may
  have gone wrong three steps earlier.
- Timed-out and capped runs are censored at their last recorded step. If they would have
  died soon after, the curve is optimistic by that much; the header counts them.
- Excluded rows are not on the curve; the header counts them by reason.
- On one run, this is a description. Only a comparison of two stored runs on the same
  cells says whether anything moved, and only within what it could not have detected.

`fix-check` and `changes`:

- A difference between two stored runs is a difference between the runs. The version, the
  provider and the hour changed together unless the two were run side by side, and this
  test cannot separate them.
- Repeat runs of one input are read as separate draws and never as replays: a served model
  is not bit-identical on repeat, so nothing here matches a run of the old version to a run
  of the new by seed.
- If repeat runs of one input are near copies of one another, the run-level test overstates
  its confidence. The by-input line does not depend on that.
- Rows with no outcome are left out of both arms and counted in the header. A new version
  that times out where the old one failed does not show as a failure here.
- Trace reads the runs it is given. If the inputs were chosen by the old arm's own outcomes,
  or the more favourable of several runs was handed over, the confidence printed does not
  hold.
- The detection limit and the run counts are computed from these runs' own failure rates,
  which are estimates. They are a guide to the next design, not a promise about it.

More limits. `compare` is unpaired: the two tau2 runs share their seeds, but the log-rank
does not use that fact (the header says *unpaired* whenever the runs share a `run_salt`),
and `fix-check` matches nothing by seed on purpose. The per-kind bands of `where` come from a
seeded bootstrap (`--boot 1000 --seed 0` by default), not a closed-form variance. Looking
after every few runs and stopping when the line reads well is not covered by the stated
confidence, and no report can see it. No fixture here is a changed agent at a size that
reads *different: the new version failed less*; that line is exercised on synthetic runs
only.

## What Trace does not read

Trace reads runs Prove stored. Prove already converts OpenTelemetry spans and LiteLLM logs
into its schema, so an app captured under Prove is already in. Reading a LangSmith export
or a bare OTLP file is the next slice, and it will say what the positioning says:
ingested logs show where failures happened at whatever rate the traffic produced; only a
controlled re-run on the same inputs says whether a change moved anything.

## Development

```
pip install -e '.[dev]'
pip install -e /path/to/prove
python -m pytest
ruff check .
mypy --strict src
```

The suite holds 70 invariants as 224 tests: the 36 of `where` and `compare` as 100, and the
34 of `fix-check` and `changes` as 124. The oracles are lifelines, scipy, full enumeration in
exact fractions, and Prove's own estimators. `tests/fixtures/SHA256SUMS` checks the fixtures
(`cd tests/fixtures && shasum -a 256 -c SHA256SUMS`).

## Licence

MIT. See `LICENSE` and `NOTICE`.

## Citation

```bibtex
@software{poisson_trace,
  author = {Poisson Labs},
  title = {Poisson Trace: where in the workflow runs die},
  year = {2026},
  url = {https://github.com/poisson-labs/trace}
}
```
