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

## Status

The first slice is being built. The test suite and the fixtures in this repository are
frozen; the estimators, the placement and the command-line tool are not yet implemented.
The worked example below is filled in when they are.

## Install

Prove is not yet public, so it is installed from a checkout and is not a declared
dependency of this package:

```
pip install poisson-trace
pip install -e /path/to/prove
```

Nobody outside Poisson Labs can run Trace until Prove is public. The command refuses at
start, in one sentence, when the `proofload` package is missing or is not version 0.0.1.

## Use

```
poisson-trace where RUN --store ROOT --event NAME [--event NAME ...]
                   [--by kind|step] [--at STEP ...] [--boot B] [--seed S]
                   [--svg FILE] [--json]

poisson-trace compare A B --store ROOT --event NAME [--event NAME ...] --max-mde-hr X
                     [--by kind|step] [--at STEP ...] [--alpha A] [--json]
```

`where` prints the survival curve over step index with a 95% band (Kaplan–Meier,
Greenwood), the median step, the deaths by kind of step with a bootstrap band on each
(Aalen–Johansen), the counts of runs ended, timed out, capped and excluded, and a closing
block of what the curve cannot say.

`compare` prints the log-rank test stratified by config cell, the direction, the minimum
detectable hazard ratio (Schoenfeld, 80% power), and one of three lines: *different*,
*no significant difference*, or *too small to tell*. It exits 0 on the first two and 2 on
the third. A refusal exits 1.

## Worked example

To be filled in from the committed fixtures once the tool is built: `where` on a stored
tau2-airline run of 200 episodes, and `compare` on the same agent run twice with nothing
changed.

## What this cannot say

- The step index is where the run stopped, not why. A run that died at a tool step may
  have gone wrong three steps earlier.
- Timed-out and capped runs are censored at their last recorded step. If they would have
  died soon after, the curve is optimistic by that much; the header counts them.
- Excluded rows are not on the curve; the header counts them by reason.
- On one run, this is a description. Only a comparison of two stored runs on the same
  cells says whether anything moved, and only within what it could not have detected.

## What the first slice does not read

Trace reads runs Prove stored. Prove already converts OpenTelemetry spans and LiteLLM logs
into its schema, so an app captured under Prove is already in. Reading a LangSmith export
or a bare OTLP file is the next slice, and it will say what the positioning says:
ingested logs show where failures happened at whatever rate the traffic produced; only a
controlled re-run on the same cells says whether a fix moved anything.

## Fixtures

`tests/fixtures/` holds four of Prove's stored runs with their observation bodies removed;
`tests/fixtures/PROVENANCE.md` records where each came from and its digest.

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
