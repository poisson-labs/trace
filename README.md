# Poisson Trace

Where in the workflow do runs die.

Poisson Trace reads runs that [Prove](https://github.com/poisson-labs/prove) has already
stored, puts every run on one clock (the index of the step it was executing) and draws the
survival curve over that clock: at step 10, what share of runs was still going; at step 20;
at step 30. Runs that ended normally, timed out or hit the capture cap are censored, never
counted as deaths. The curve is split by the kind of step runs die at (model call, tool
call, guardrail, agent turn), each part with a stated interval. Given two stored runs, a
before and an after, it says whether the curves differ, at what confidence, and, when the
design was too small to see the effect asked about, says so instead of pretending.

Every number prints with what the run could not have detected.

This is the first slice, released with the Poisson Labs post responding to LangSmith Engine
v2 (2026-10-01; the post links here). It is a reader of stored runs: it captures nothing,
patches nothing, phones nowhere.

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
the outcomes that count as a death:

```
poisson-trace where RUN --store ROOT --event NAME [--event NAME ...]
                   [--by kind|step] [--at STEP ...] [--boot B] [--seed S]
                   [--svg FILE] [--json]

poisson-trace compare A B --store ROOT --event NAME [--event NAME ...] --max-mde-hr X
                     [--by kind|step] [--at STEP ...] [--alpha A] [--json]
```

- `--store` is required; there is no default store. `--event` is required and repeatable;
  the union of the names is "died". A name no stored row carries is refused, and the
  refusal lists the outcomes the run does carry.
- `--by kind` (the default) labels the step a run died at by the leaf span's kind (`llm`,
  `tool`, `retrieval`, `db`, `http`, `agent`, `other`); `--by step` labels it by the
  nearest declared step name.
- `--at STEP` adds a row reading the curve at that step; repeatable.
- `--json` prints the structure (`poisson-trace.where/1` or `poisson-trace.compare/1`)
  and nothing else; `--svg FILE` writes the curve as an SVG, the one file `where` writes.
- Exit codes: 0 report printed; 1 refusal (one sentence); 2 *too small to tell*
  (`compare` only).

`where` prints the survival curve over step index with a 95% band (Kaplan–Meier,
Greenwood), the median step, the deaths by kind of step with a bootstrap band on each
(Aalen–Johansen), the counts of runs ended, timed out, capped and excluded, and a closing
block of what the curve cannot say.

`compare` prints the log-rank test stratified by config cell over the cells both runs
carry, the direction, the minimum detectable hazard ratio (Schoenfeld, 80% power) and one
of three lines: *different*, *no significant difference*, or *too small to tell*.
`--max-mde-hr` is the largest minimum detectable hazard ratio you will accept; it has no
default, because the tool supplies no number of its own.

### How a run is placed

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

## Worked example

The four stores under `tests/fixtures/` are real runs stored by Prove on our machines,
copied with their observation bodies removed (`tests/fixtures/PROVENANCE.md` has the
sources and digests). Nothing Trace reads is in the bodies, so the output below is
byte-for-byte what the original stores give.

### One run: the OpenAI customer-service demo, recorded

`cs_agents/record` is the OpenAI customer-service agent demo recorded on gpt-4.1-mini: 24
episodes, spans nested three deep (turn > workflow > generation, with guardrail agents
beside them), four failure outcomes.

```
poisson-trace where 20260925T234602Z-3ea0 --store tests/fixtures/cs \
  --event forbidden_action --event unresolved --event max_turns --event app_error \
  --at 20 --at 40 --svg docs/figures/cs-record.svg
```

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

```
poisson-trace compare 20260915T210140Z-4847 20260915T211148Z-965d --store tests/fixtures/tau2 \
  --event unsolved --max-mde-hr 1.3 --at 10 --at 20 --at 30
```

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

## What this cannot say

- The step index is where the run stopped, not why. A run that died at a tool step may have gone wrong three steps earlier.
- Timed-out and capped runs are censored at their last recorded step. If they would have died soon after, the curve is optimistic by that much; the header counts them.
- Excluded rows are not on the curve; the header counts them by reason.
- On one run, this is a description. Only a comparison of two stored runs on the same cells says whether anything moved, and only within what it could not have detected.
```

It exits 2. With `--max-mde-hr 1.5` the same numbers end

```
**no significant difference (p = 0.521); could not have detected a hazard ratio below 1.457**
```

and exit 0. That pair of lines is the point: the same agent run twice, 400 episodes, and
the design could still not have seen a 40% change in the hazard. Re-running a handful of
failing inputs until they pass says less than this.

## What this cannot say

- The step index is where the run stopped, not why. A run that died at a tool step may
  have gone wrong three steps earlier.
- Timed-out and capped runs are censored at their last recorded step. If they would have
  died soon after, the curve is optimistic by that much; the header counts them.
- Excluded rows are not on the curve; the header counts them by reason.
- On one run, this is a description. Only a comparison of two stored runs on the same
  cells says whether anything moved, and only within what it could not have detected.

Two more limits of this slice. The comparison is unpaired: the two tau2 runs share their
seeds, but the log-rank does not use that fact, so the design's extra power is left on the
table (the header says *unpaired* whenever the runs share a `run_salt`). And the per-kind
bands come from a seeded bootstrap (`--boot 1000 --seed 0` by default), not a closed-form
variance.

## What the first slice does not read

Trace reads runs Prove stored. Prove already converts OpenTelemetry spans and LiteLLM logs
into its schema, so an app captured under Prove is already in. Reading a LangSmith export
or a bare OTLP file is the next slice, and it will say what the positioning says:
ingested logs show where failures happened at whatever rate the traffic produced; only a
controlled re-run on the same cells says whether a fix moved anything.

## Development

```
pip install -e '.[dev]'
pip install -e /path/to/prove
python -m pytest
ruff check .
mypy --strict src
```

The suite holds the 36 invariants of the first slice as 100 tests, with lifelines and
Prove's own estimators as oracles. `tests/fixtures/SHA256SUMS` checks the fixtures
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
