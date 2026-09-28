# Changelog

## 0.1.0 — 2026-10-01

First slice. `where` and `compare` over leaf-span index; Kaplan–Meier with Greenwood;
Aalen–Johansen by kind with a bootstrap band; stratified log-rank with the minimum
detectable hazard ratio; reads Prove's stored runs.

- `poisson-trace where RUN --store ROOT --event NAME`: the survival curve over step index
  with a plain Greenwood 95% band, the median step, the cumulative incidence by kind of
  step (or by step name with `--by step`) with a seeded bootstrap band, the header counts
  (Prove's tally and Trace's placement: died, ended, timed out, capped, excluded by reason),
  the declared-steps table when the run declared, and the block of what the curve cannot
  say. `--json` prints `poisson-trace.where/1`; `--svg FILE` writes the curve.
- `poisson-trace compare A B --store ROOT --event NAME --max-mde-hr X`: the two-sample
  log-rank stratified by config cell over the common cells, unpaired; the direction; the
  per-step difference with a Wald interval (`--at`); the cause-specific log-rank per kind
  with Benjamini–Hochberg; Schoenfeld's minimum detectable hazard ratio at 80% power; and
  one of three lines, *different*, *no significant difference* or *too small to tell*
  (exit 2). `--json` prints `poisson-trace.compare/1`.
- Reads a Prove store only through Prove's public API (`Store`, `RunTally`,
  `declaration_check`, `KINDS`); writes nothing but the requested SVG; refuses in one
  sentence when `proofload` 0.0.1 is not importable.
- Four fixtures: two tau2-airline runs and two cs_agents runs stored by Prove, observation
  bodies removed, with provenance and checksums.
