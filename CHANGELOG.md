# Changelog

## 0.1.0 — 2026-10-01

First release, three parts. The first two read Prove's stored runs; the third writes a
store in Prove's format from the result files of another tool.

Where runs die: `where` and `compare` over leaf-span index; Kaplan–Meier with Greenwood;
Aalen–Johansen by kind with a bootstrap band; stratified log-rank with the minimum
detectable hazard ratio.

Whether a change made runs fail less: `fix-check` and `changes` over the outcome alone; the
exact conditional Cochran–Mantel–Haenszel test stratified by input, with the old version
re-run as the control; the Mantel–Haenszel difference with Sato's interval; per-input flags
with Benjamini–Hochberg; and, wherever the line is *too small to tell*, how many repeats or
inputs would settle it.

Results from other tools: `poisson-trace-import` reads the files a tool already wrote and
writes one new run per version, for `fix-check` and `changes` to compare. The readers are
DeepEval's and Ragas's.

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
- `poisson-trace fix-check OLD NEW --store ROOT --event NAME (--failing-from RUN
  [--min-failures M] | --inputs all) --max-mde X`: the old version re-run on the same inputs
  beside the new (the control); the exact conditional Cochran–Mantel–Haenszel test
  stratified by input, two-sided, which is Fisher's exact test on one input and the exact
  McNemar test on one run per arm; the Mantel–Haenszel risk difference in points with
  Sato's large-sample interval; a by-input sign-flip reading, exact up to 14 moved inputs
  and 100,000 seeded draws beyond (`--seed`), printed beside the test with no part in the
  line; failure share, the chance a failure repeats, κ, and within-input against pooled
  variance; the smallest proportional drop and rise in failure share detectable at 80%
  power; and one of three lines, *different* (failed less, or failed more), *no significant
  difference* or *too small to tell* (exit 2). `--json` prints `poisson-trace.fix-check/1`.
- The selecting run is refused as an arm: `--failing-from` must name neither OLD nor NEW.
  Which inputs are compared has no default, and `--max-mde` has none.
- `poisson-trace changes A B --store ROOT --event NAME`: Fisher's exact test per input,
  Benjamini–Hochberg across the inputs compared, the inputs flagged as *failed more in B* or
  *failed less in B*, each row with Prove's per-cell limit, and what the design could not
  have flagged (the smallest p an input can give against α / M, how many inputs would have
  to flip together, the repeats a lone complete flip needs). The numbers are Prove's `diff`
  with `fisher_bh`. `--json` prints `poisson-trace.changes/1`; `--top N` bounds the
  markdown table. The same table closes every `fix-check` report.
- Guidance under every *too small to tell*. `fix-check` prints the repeats per arm on these
  inputs, the inputs like these at the present repeats, and the `--max-mde` that accepts the
  design as it stands, computed with the function that stated the limit. `compare` prints
  the deaths needed, the placed runs, inputs and repeats that many deaths take, and the
  `--max-mde-hr` that accepts the design; its JSON gains `comparison.guidance`. `compare`
  also closes with one line naming `fix-check`.
- Neither new verb reads a trace, a seed or a replicate index: repeat runs of one input are
  separate draws, never replays, and a run stored with no capture is read like any other.
- No output of any verb uses *fixed*, *validated* or *confirmed*, beside the first slice's
  list. A run that did not fail is written *did not fail*.
- Three more fixtures: the patched tau2 pilot, copied whole, and two HumanEval runs,
  outcome-only, with provenance and checksums.
- `poisson-trace-import TOOL FILE [FILE ...] --store ROOT --run NAME [--started ISO-8601]
  [--json]`: one import is one version, written as one new run through Prove's public API
  (`Store`, `RunManifest`, `EpisodeRecord`, `from_otel`). A run name the store holds is
  refused; nothing is added to a run. A score becomes the outcome `met` or `missed` at a cut
  the user declares with its side, and a score equal to the cut met it. Rows that share a
  case are repeats of it, in the order read. No prompt, answer or reason text is written,
  but for the value of the column a user names as the case to the Ragas reader (below), and
  span attributes that Prove lists as content are dropped before a span is stored. The
  summary prints the files with their digests, the rules as declared, the start time and
  where it came from, the counts, and the Trace command to run next; `--json` prints
  `poisson-trace.import/1`. A refusal is one sentence, exit 1, with nothing written.
- `poisson-trace-import deepeval … --metric NAME --cut (recorded | X (--below | --above))
  --case (name | input | position)`: reads DeepEval's saved test runs as DeepEval 4.2.6
  writes them (`docs/integrations/deepeval.md`), one metric per import. `--cut recorded`
  takes DeepEval's own decision for that metric; `--case input` is a digest of the input,
  never its text; a metric that raised is a row with no outcome. Nothing imports DeepEval.
- `fix-check` prints a p below 1e-300 as the bound `p < 1e-300`, in the comparison line and
  in the line that states the result. With one run per input per version its consistency
  block says consistency cannot be measured and prints no κ; in `--json`,
  `consistency.fails_again` and `consistency.kappa` are then `null`.
- Two more fixtures: the HumanEval pair as two result files written by DeepEval 4.2.6, with
  the recipe beside them, provenance and checksums.
- `poisson-trace-import ragas … --metric COLUMN --cut X (--below | --above) --case-column
  COLUMN`: reads the score table a team saves from Ragas's `to_pandas()`, or an
  `@experiment` file, as CSV, JSON Lines, JSON or Parquet, told by the file's extension,
  with `.gz` read on the first three (`docs/integrations/ragas.md`); one score column per
  import. A cell that is empty, `NaN`, `null` or not a number is a row with no outcome,
  never a zero. Rows that share a case value are repeats of that case. Only the two named
  columns are kept: the score, and the case as written when it is at most 80 printable
  characters and as a digest otherwise. A named column the file lacks is refused with the
  file's columns listed, and a JSON Lines file with a line that is not an object is refused
  whole, as is a `.gz` that cannot be read. Nothing imports Ragas; tested on tables written
  by Ragas 0.4.3.
- Four more fixtures: two pairs of Ragas score tables, one from a stored memory-retrieval
  experiment scored by Ragas 0.4.3 and one a published base and fine-tuned pair reduced to
  question hashes and scores, with the recipe beside them, provenance and checksums.
