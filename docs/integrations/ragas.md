# Ragas

You score two versions of your system with Ragas and compare two means. This page shows
how to find out whether the difference is real, or whether the run was too small to tell.

Poisson Trace reads the score table you saved. It runs no metric and calls no model.

## Install

```
pip install poisson-trace
pip install git+https://github.com/poisson-labs/prove
```

Nothing here imports Ragas. Tested on tables written by Ragas 0.4.3.

## Save your scores

Ragas's `evaluate()` writes no result file. It returns a result; save its table, once per
version:

```python
result.to_pandas().to_json("base.jsonl", orient="records", lines=True)
```

The table needs a column that names each case and is the same in both versions: a question
id, or the question itself. Use the same cases for both versions. If you can, score each case
more than once per version: one run per case is the smallest design there is. Decide the cut
before you look: the score under which, or over which, a case counts as missed.

A file written by Ragas's `@experiment` is read the same way, by whatever columns your
function returned. pandas's `to_json` writes each score to at most ten decimal digits, and
that is the score the import reads.

One thing about Ragas itself, which this reader never runs. In Ragas 0.4.3 `evaluate()`
posts usage events to Ragas's own server unless `RAGAS_DO_NOT_TRACK=true` is set before Ragas
is imported. With it set, `evaluate()` made no network call in our runs, and Ragas still wrote
a random usage id to a file, `uuid.json`, in its folder under the user data directory.

## Import and compare

One import is one version. Each import reads one score column and writes one new run into a
store in Prove's format; `poisson-trace fix-check` then compares the two runs.

```
poisson-trace import ragas FILE [FILE ...] --store ROOT --run NAME
        --metric COLUMN
        --cut X ( --below | --above )
        --case-column COLUMN
        [--started ISO-8601] [--json]
```

Nothing has a default but the start time. You say which column holds the score, where the
cut is and which column identifies a case.

- `FILE` is `.csv`, `.jsonl`, `.json` (a list of objects) or `.parquet`, told by its
  extension; `.gz` is read on the first three. Any other extension is refused, and so is a
  file that is not what its extension says.
- `--metric` is the score column. A column the file lacks is refused, and the refusal lists
  the file's columns. A number outside 0 to 1 is kept as it is: the cut decides.
- `--cut` takes a number and exactly one side: `--cut 0.5 --below` counts a score under 0.5
  as missed, `--cut 0.3 --above` counts a score over 0.3 as missed. A score equal to the cut
  met it. The outcome is the word `met` or the word `missed`. A Ragas table records no
  threshold, so there is none to fall back on.
- A cell that is empty, `NaN`, `null` or not a number has no score. Its row has no outcome,
  the summary counts it as `no score`, and Trace leaves it out and counts it in the header
  of its report. A missing score is never read as 0.
- `--case-column` is the column that identifies a case. Rows that share a value are repeats
  of that case, in the order read, and several files given to one import are read as one
  version, in the order given. A row with no value there refuses the whole import, and the
  refusal names the row. In a CSV the value is the text as written: `007` and `7` are two
  cases.
- `--started` is when that version's run started, with its zone. Without it the first
  file's modification time is used, and the summary says which of the two it was.
- `--store` may be left out when a `trace.toml` in the current folder (or the file `--config
  PATH` names) names a store: the import writes into it. `--store NAME` takes the store that
  file names so.

## The worked example

The two files are in `tests/fixtures/ingest/ragas/`. They hold the faithfulness, answer
correctness and answer relevancy scores of two published result sets, a base model and the
same model fine-tuned, on the same 150 rows of 146 questions: one question is asked three
times and two are asked twice
(`huggingface.co/datasets/R0bfried/RAGAS-BASE-llama-3-2-1B-eval2` and
`…RAGAS-RAFT-llama-3-2-1B-eval2`). Those sets carry no licence, so the files hold a hash of
each question and the scores, and no text; `make.py` beside them is the recipe. The Ragas
version that scored them is not stated. Over the rows that have a score, mean faithfulness
is 0.550 for the base model and 0.566 for the fine-tuned one.

The commands run from the root of a clone and write the store to `./store`. The start times
are when each set was last changed where it is published.

<!-- command -->
```
poisson-trace import ragas tests/fixtures/ingest/ragas/rag-base.jsonl \
  --store ./store --run rag-base-faithfulness --metric faithfulness --cut 0.5 --below \
  --case-column case --started 2025-03-31T06:56:41Z
```

<!-- output exit=0 -->
```
ok  wrote run rag-base-faithfulness to ./store: 150 rows, 146 cases, 1 to 3 repeats; 95 passed, 52 failed, 3 with no outcome

# Poisson Trace · import · rag-base-faithfulness

## Summary

- Wrote: rag-base-faithfulness into ./store, from rag-base.jsonl (ragas): 150 tries on 146 inputs.
- Failures: 52 failed and 95 passed; 3 had no outcome. A try counts as failed when its faithfulness score is below 0.5.
- Compared: Nothing yet. One import is one version.
- Next: Import the other version's file the same way: `poisson-trace import ragas OTHER.jsonl --store ./store --run OTHER --metric faithfulness --cut 0.5 --below --case-column case`.

## Before you act on this

- When you compare, choose the smallest drop that matters to you (--max-mde) before you look at any results; Trace then says whether these tries could catch it.

## What was written

- run written: rag-base-faithfulness · store: ./store
- tool: ragas
- file: rag-base.jsonl · sha256 48e8afe8ab3913ab7a0126124bc4eb67357a626c3e78bd7ad2428bae0cfee19f
- declared: metric faithfulness · cut 0.5 · side below · case_column case
- started: 2025-03-31T06:56:41Z · from: given
- rows 150 · cases 146 · repeats of a case: smallest 1, largest 3
- outcomes: met 95 · missed 52
- rows with no outcome: no score 3

In the command below, OLD and NEW are this run and the other version's run, imported into the same store, the older version first. X is the largest limit of detection you accept, as a share: 0.05 is five points.

next: poisson-trace fix-check OLD NEW --store ./store --event missed --inputs all --max-mde X  # rag-base-faithfulness is OLD or NEW
```

<!-- command -->
```
poisson-trace import ragas tests/fixtures/ingest/ragas/rag-raft.jsonl \
  --store ./store --run rag-raft-faithfulness --metric faithfulness --cut 0.5 --below \
  --case-column case --started 2025-03-31T07:16:07Z
```

<!-- excerpt exit=0 -->
```
# Poisson Trace · import · rag-raft-faithfulness

## Summary

- Wrote: rag-raft-faithfulness into ./store, from rag-raft.jsonl (ragas): 150 tries on 146 inputs.
- Failures: 47 failed and 95 passed; 8 had no outcome. A try counts as failed when its faithfulness score is below 0.5.
- Compared: Nothing yet. One import is one version.
- Next: Import the other version's file the same way: `poisson-trace import ragas OTHER.jsonl --store ./store --run OTHER --metric faithfulness --cut 0.5 --below --case-column case`.

## Before you act on this

- When you compare, choose the smallest drop that matters to you (--max-mde) before you look at any results; Trace then says whether these tries could catch it.

## What was written

- run written: rag-raft-faithfulness · store: ./store
- tool: ragas
- file: rag-raft.jsonl · sha256 5f5a986fade2bf12531e50e72c3f0532734a5882e18b8bb5bf6304c133975fe7
- declared: metric faithfulness · cut 0.5 · side below · case_column case
- started: 2025-03-31T07:16:07Z · from: given
- rows 150 · cases 146 · repeats of a case: smallest 1, largest 3
- outcomes: met 95 · missed 47
- rows with no outcome: no score 8
```

<!-- command -->
```
poisson-trace fix-check rag-base-faithfulness rag-raft-faithfulness --store ./store \
  --event missed --inputs all --max-mde 0.10 --top 0
```

<!-- excerpt exit=0 -->
```
# Poisson Trace · fix check · rag-base-faithfulness (old) and rag-raft-faithfulness (new)

## Summary

- Compared: old rag-base-faithfulness against new rag-raft-faithfulness, on the same 137 inputs: 141 tries of each. A try counts as failed when its faithfulness score is below 0.5.
- Question: Did the new version fail more or less often than the old? You asked that the run be able to catch a 10-point drop in how often it fails.
- Answer: Can't tell yet. The new version failed 46 of 141 tries and the old 51 of 141; by Trace's rough estimate, these tries would catch a 16-point drop 4 times in 5 and smaller ones less often, and you asked for 10; the gap is no bigger than the gap in tries with no outcome.
- Next: First find out why the new version has more tries with no outcome; then run each version 3 times on each of these 137 inputs with your own harness, then run `poisson-trace fix-check` on the two new runs.

## Before you act on this

- They started 19 min apart. Trace can't tell whether they were run side by side, so anything else that changed between them (the provider, the model behind the API, the day) may be part of the difference, in either direction.
- Both runs name the same target (import/ragas); Trace can't tell what differs between them, only what you tell it.
- 3 tries of the old and 8 of the new had no outcome; the 9 inputs that leaves without a result on one side are left out on both versions. If no outcome means a bad answer, the new version, which has more of them, fails more often than it looks. The difference in them (5) is as large as the whole gap in failures (5).
- These results fit anything from 16 fewer failures per 100 tries to 8.8 more, but that range is only a rough guide here and may be off either way (one try per input on the new version (134 of 137 inputs) and one try per input on the old version (134 of 137 inputs)): don't use it to rule sizes in or out.
- Tries of the same input are counted as separate chances, and if they are near copies the answer is more confident than it should be.
- The 3 times per input is an estimate from these runs' failure rates (one try per input on one version, so rough). 356 inputs like these at the present tries would do the same, more than the 137 here. Even with good estimates, about half of runs built to it end up a little too small. Make it a fresh run, judged on its own: don't add tries to these and test again.
- If a 16-point drop is the smallest that matters to you (the old version failed 36.2% of tries), and you would have said so before seeing this, `--max-mde 0.1588` accepts this design as it stands. That changes the label only, not the evidence.

## Runs

- old: rag-base-faithfulness · target: import/ragas · status: complete · started: 2025-03-31T06:56:41Z (given with --started) · declared repeats: not recorded
- the run's tally (old): rows 150 · with outcome 147 · no outcome 3 · timed out 0 · infra 0 · other 3
- new: rag-raft-faithfulness · target: import/ragas · status: complete · started: 2025-03-31T07:16:07Z (given with --started) · declared repeats: not recorded
- the run's tally (new): rows 150 · with outcome 142 · no outcome 8 · timed out 0 · infra 0 · other 8
- the two runs started 19 min apart
- events: missed
- inputs: every input either run carries · selected 146 · compared 137 · left out 9 (no outcome on the old version 3; no outcome on the new version 6)
- rows used: old 141 (timed out 0, no outcome 0) · new 141 (timed out 0, no outcome 0)
- inputs short of the declared repeats: old no repeats declared · new no repeats declared
- inputs with mixed outcomes across their repeats: old 1 · new 0

## The two versions

The old version and the new on the same inputs.

| version | runs | failed | failure share | did not fail |
|---|---|---|---|---|
| old | 141 | 51 | 36.2% | 63.8% |
| new | 141 | 46 | 32.6% | 67.4% |

The old version did not fail on 63.8% of its episodes on these inputs.

## The comparison

exact conditional Cochran-Mantel-Haenszel test, stratified by input over 137 inputs (68 informative), two-sided; α = 0.05.

new failures: observed 46, expected 48.500, variance 17.083; p = 0.629
difference: -3.5 points, new minus old (-16.4 to +8.8; Mantel-Haenszel weights; range: stratified Miettinen-Nurminen score interval, 95%, for these inputs as run; rough here: one try per input on the new version (134 of 137 inputs) and one try per input on the old version (134 of 137 inputs))
by input: p = 0.636 (sign-flip over the 68 inputs that moved, 100,000 draws, seed = 0); not part of the line below

## Consistency

failure share 0.344
consistency cannot be measured with 3 of 137 inputs run more than once on a version: it takes at least half the inputs run two or more times on a version to see whether a failure repeats

## What it could not have detected

proportional change on every input, 80% power, α = 0.05, continuity-corrected normal approximation to the stratified statistic.

- a drop in failure share: could not have detected one below 15.9 points
- a rise in failure share: could not have detected one below 17.7 points

**too small to tell: could not have detected a drop in failure share below 15.9 points, and 10 was asked for**

## Guidance

- repeats: 3 per arm on these 137 inputs would bring the limit to 10 points
- inputs: 356 inputs like these, at the present repeats, would do the same
- ceiling: --max-mde 0.1588 accepts this design as it stands
```

The report goes on with a note on its guidance, the inputs that changed (no question has
enough runs to be flagged) and its block *What this cannot say*, left out here for length.

Mean faithfulness rose from 0.550 to 0.566. The run could not have detected a drop in the
share of misses smaller than 15.9 points, and 10 was asked for, so it cannot say whether
faithfulness moved. It says what would: each question three times per version, or 356
questions.

The Consistency block prints no κ because only three of the 137 questions compared were
asked more than once on a version: on the other 134 the only pairs of runs set the base
model beside the fine-tuned one, not a model beside itself.

The same two files at the same cut, on the other two scores:

<!-- command -->
```
poisson-trace import ragas tests/fixtures/ingest/ragas/rag-base.jsonl \
  --store ./store --run rag-base-correctness --metric answer_correctness --cut 0.5 --below \
  --case-column case --started 2025-03-31T06:56:41Z
```

<!-- excerpt exit=0 -->
```
- outcomes: met 43 · missed 107
- rows with no outcome: 0
```

<!-- command -->
```
poisson-trace import ragas tests/fixtures/ingest/ragas/rag-raft.jsonl \
  --store ./store --run rag-raft-correctness --metric answer_correctness --cut 0.5 --below \
  --case-column case --started 2025-03-31T07:16:07Z
```

<!-- excerpt exit=0 -->
```
- outcomes: met 63 · missed 87
- rows with no outcome: 0
```

<!-- command -->
```
poisson-trace fix-check rag-base-correctness rag-raft-correctness --store ./store \
  --event missed --inputs all --max-mde 0.10 --top 0
```

<!-- excerpt exit=0 -->
```
new failures: observed 87, expected 97.000, variance 14.333; p = 0.011
difference: -13.3 points, new minus old (-25.5 to -3.0; Mantel-Haenszel weights; range: stratified Miettinen-Nurminen score interval, 95%, for these inputs as run; rough here: one try per input on the new version (143 of 146 inputs) and one try per input on the old version (143 of 146 inputs))
```

<!-- excerpt exit=0 -->
```
**different: the new version failed less on these inputs (exact Cochran-Mantel-Haenszel, stratified by input, p = 0.011)**
```

<!-- command -->
```
poisson-trace import ragas tests/fixtures/ingest/ragas/rag-base.jsonl \
  --store ./store --run rag-base-relevancy --metric answer_relevancy --cut 0.5 --below \
  --case-column case --started 2025-03-31T06:56:41Z
```

<!-- excerpt exit=0 -->
```
- outcomes: met 101 · missed 49
- rows with no outcome: 0
```

<!-- command -->
```
poisson-trace import ragas tests/fixtures/ingest/ragas/rag-raft.jsonl \
  --store ./store --run rag-raft-relevancy --metric answer_relevancy --cut 0.5 --below \
  --case-column case --started 2025-03-31T07:16:07Z
```

<!-- excerpt exit=0 -->
```
- outcomes: met 118 · missed 32
- rows with no outcome: 0
```

<!-- command -->
```
poisson-trace fix-check rag-base-relevancy rag-raft-relevancy --store ./store \
  --event missed --inputs all --max-mde 0.10 --top 0
```

<!-- excerpt exit=0 -->
```
new failures: observed 32, expected 40.500, variance 9.750; p = 0.009
difference: -11.3 points, new minus old (-22.6 to -2.6; Mantel-Haenszel weights; range: stratified Miettinen-Nurminen score interval, 95%, for these inputs as run; rough here: one try per input on the new version (143 of 146 inputs) and one try per input on the old version (143 of 146 inputs))
```

<!-- excerpt exit=0 -->
```
**different: the new version failed less on these inputs (exact Cochran-Mantel-Haenszel, stratified by input, p = 0.009)**
```

On both, the fine-tuned model missed the cut less often: 107 rows of 150, then 87, on answer
correctness, and 49 of 150, then 32, on answer relevancy. Three scores at one cut are three
tests. The cut, 0.5, was written down before any of them was run.

These are two stored tables. Whether the two models were scored on the same day, with the
same retrieval and the same judge, is not in the files, and the report's closing block says
that a difference between two runs is a difference between the runs.

## A score Ragas could not give

Ragas gives `NaN` where a metric cannot be computed, and a saved table holds it as an empty
cell, a `null` or a `NaN`. Trace leaves those cases out of both versions and counts them at
the top of the report.

`memory-causal.jsonl.gz` and `memory-strong.jsonl.gz`, in the same folder, are the tables
Ragas 0.4.3 gave for a stored memory-retrieval experiment: the same 1,800 lookups on a memory
with causal reads and on one with strong reads. Each row holds the ids the memory returned
and the ids that answer the question, and Ragas's two id-based context metrics, which call
no model, scored them. Context precision has no score on 1,130 of the 1,800 rows of the
causal memory: the rows where nothing was retrieved. The start times given are the two
stored runs' own.

<!-- command -->
```
poisson-trace import ragas tests/fixtures/ingest/ragas/memory-causal.jsonl.gz \
  --store ./store --run memory-causal-precision --metric id_based_context_precision \
  --cut 0.5 --below --case-column user_input --started 2026-09-28T19:37:36Z
```

<!-- excerpt exit=0 -->
```
- rows 1,800 · cases 1,800 · repeats of a case: smallest 1, largest 1
- outcomes: met 331 · missed 339
- rows with no outcome: no score 1,130
```

<!-- command -->
```
poisson-trace import ragas tests/fixtures/ingest/ragas/memory-strong.jsonl.gz \
  --store ./store --run memory-strong-precision --metric id_based_context_precision \
  --cut 0.5 --below --case-column user_input --started 2026-09-29T08:26:16Z
```

<!-- excerpt exit=0 -->
```
- rows 1,800 · cases 1,800 · repeats of a case: smallest 1, largest 1
- outcomes: met 900 · missed 900
- rows with no outcome: 0
```

<!-- command -->
```
poisson-trace fix-check memory-causal-precision memory-strong-precision --store ./store \
  --event missed --inputs all --max-mde 0.05 --top 0
```

<!-- excerpt exit=0 -->
```
- inputs: every input either run carries · selected 1,800 · compared 670 · left out 1,130 (no outcome on the old version 1,130)
```

<!-- excerpt exit=0 -->
```
new failures: observed 338, expected 338.500, variance 0.750; p = 1.000
difference: -0.1 points, new minus old (-1.6 to +1.1; Mantel-Haenszel weights; range: stratified Miettinen-Nurminen score interval, 95%, for these inputs as run; rough here: fewer than 10 inputs vary and one try per input on the new version and one try per input on the old version)
```

<!-- excerpt exit=0 -->
```
**no significant difference (p = 1.000); could not have detected a drop in failure share below 1.7 points**
```

On the 670 cases left the report reads *no significant difference*: 339 misses, then 338,
a 0.15-point drop, in a design that could have detected a drop of 1.7 points. The header says
that 1,130 cases were left out and why, and they are the cases where the causal memory
returned nothing. Read that line before the verdict. The two means do not show it: 0.453
over the 670 rows Ragas scored, against 0.458 over 1,800.

## From `poisson-trace init`

`poisson-trace init`, run in a folder with no Prove store under it, lists the tables that look
like Ragas scored them (a `.csv`, `.jsonl` or `.json` file with a column named like a Ragas
metric, `faithfulness` or `answer_relevancy` and the others, within its first 4 KB; a `.json`
file is a list of rows) and offers to import them. Its questions are the import's flags,
asked in their order; with `--yes` it takes them as flags instead. Each file becomes one run,
named after the file, in a store `trace-store` beside `trace.toml`, and `trace.toml` names
that store with `missed` as the failure. Here it is on the base model's table:

<!-- command -->
```
mkdir -p from-ragas && cp tests/fixtures/ingest/ragas/rag-base.jsonl from-ragas/
cd from-ragas && poisson-trace init --yes --metric faithfulness --cut 0.5 --below --case-column case
```

<!-- excerpt exit=0 -->
```
  found 1 result file:
    1) rag-base.jsonl            a JSON Lines table with the Ragas metrics faithfulness, answer_relevancy, answer_correctness
```

<!-- excerpt exit=0 -->
```
ok  wrote trace.toml and imported 1 run into trace-store, failures missed
  names    1 run, named at import (rag-base)
  prove    poisson-prove is installed at the version Trace reads
  import   poisson-trace import ragas rag-base.jsonl --store trace-store --run rag-base --metric faithfulness --cut 0.5 --below --case-column case
  the same setup, without questions:
    poisson-trace init --yes --import --metric faithfulness --cut 0.5 \
      --below --case-column case --event missed
next: poisson-trace runs
```

With `trace.toml` there, the import takes its store from it too, so `--store` may be left out.

## What this does not do

- It does not run Ragas, a metric or a model. It reads a table.
- It reads one score column per import, at one cut. The cut and its side are yours to
  declare; there is no default.
- It does not pair rows by position. Name the column that identifies the case. Rows that
  share a case are read as repeats of it.
- It does not compare means. It compares the share of cases that missed the cut, case by
  case. The score is kept on every row that has one.
- It keeps nothing of any column but the two you name: no answer, context or reference
  text. The case column's value is kept as written when it is at most 80 printable
  characters, and as a SHA-256 digest of it otherwise. If you name the question column as
  the case, a short question is stored as it is; name an id column to keep questions out.
- It does not skip a line it cannot read. A JSON Lines file with a line that is not a JSON
  object is refused whole, where Ragas's own loader skips the line.
- It does not choose a cut. Trying several cuts or several scores and keeping the one that
  reads well is not covered by the confidence printed.
- With one run per case per version, no single case can be flagged and the consistency of
  failures cannot be measured, and consistency stays unmeasured while fewer than half the
  cases compared have been run more than once on a version. Repeats fix both.
- It does not add to a run. A run name the store already holds is refused.
- A store the importer wrote is for Trace's verbs. Prove's own `diff` pairs rows by seed,
  and a score table records none.
- Tables from Ragas versions other than 0.4.3 are read by their column names, like any
  table, and no test runs another version. The published pair above is such a table: the
  version that scored it is not stated.
