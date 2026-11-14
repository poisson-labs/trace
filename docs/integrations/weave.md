# W&B Weave

You ran two versions of an agent as Weave evaluations on the same dataset, and one scored
better. This page shows how to read both into Poisson Trace, ask whether the difference is
real, and see at which step the failing cases stop.

Poisson Trace reads the evaluations Weave already holds. It runs no agent and calls no model,
and it keeps no prompt, input, output or error text.

## Install

<!-- skip reason="installs from the package index, which the docs check does not reach" -->
```
pip install poisson-trace
```

Nothing here imports Weave's or W&B's packages. Tested on evaluations written by weave 0.54.1
(the Python SDK), as Weave's service returns them and as its Traces page downloads them.

## Get your evaluation out

There are two ways, and both read to the same cases and outcomes.

### Pull it with your key

Put your W&B key in `WANDB_API_KEY` and name the evaluation where the files would go, as
`weave:ENTITY/PROJECT/EVALUATION`: the entity and the project as W&B shows them, then the
evaluation.

<!-- skip reason="needs your own key and your own project: the words in capitals are yours to fill in" -->
```
export WANDB_API_KEY=...
poisson-trace import weave weave:ENTITY/PROJECT/EVALUATION --store ./store --run old \
  --case-from example --outcome-from score:correct --cut 0.5 --below
```

The evaluation is named by the evaluation's own name, by the name Weave shows for one run of
it (such as `eval-2026-11-09-unique-pine`), or by that run's call id. One evaluation run
against two models is two runs of one name: the pull then stops and names each run, and you
give the run's own name or id.

The pull makes one kind of request, `POST /calls/stream_query`, for two things and no other:
the project's root calls, to find the evaluation you named, and then every call of that
evaluation's trace. It saves a raw copy first, in `./store/.poisson/raw/weave/old/`, as two
files: `raw.jsonl`, the calls, one a line; and `pull.json`, which says what was pulled, when,
and the file's digest. Then it reads that folder as it reads any file.

- Every request asks for the costs and the feedback (`include_costs`, `include_feedback`).
  Weave leaves both out of an answer that does not ask.
- The project's root calls are read whole, with no filter by op: on a project whose root
  calls are mostly not evaluations, finding the one you named reads them all.
- An evaluation run inside another traced call is not a root call, so the pull does not find
  it and stops as it does for a name no evaluation has: download that one from the Traces
  page instead.
- The pull reads every call of the evaluation, however old. It sends nothing that bounds the
  calls by time, and it asks for the next page until one comes back empty: a page shorter
  than asked is not the end.
- The inputs and outputs of every call are measured and left out of the raw copy. What stays
  of the inputs is the references that say which evaluation, which model and which dataset
  row; of a case's output, the scores that are numbers or true or false and Weave's figure
  for the model's run. An exception keeps only its class. Also left out: a scorer's text,
  such as a judge's reason; a note and an annotation; who ran the calls; and the calls'
  attributes, which hold the build of the machine that ran them, but for a call's kind.
  `--keep-raw-text` saves the calls as Weave returned them instead.
- The dataset row is among what is left out, so a pull that names the case by a key of the
  row (`--case-from example:KEY`) needs `--keep-raw-text`, and is refused before any request
  without it. `--case-from example` and `--case-from input` need nothing kept.
- A raw copy is never written over. To read the same calls again, with another cut or another
  case, import the folder: `poisson-trace import weave ./store/.poisson/raw/weave/old --store
  ./store --run old-again ...`. That asks Weave nothing and needs no key.
- Only `WANDB_API_KEY` is read. The key goes to Weave's service as basic auth and nowhere
  else: it is not printed and not written to any file.
- `WF_TRACE_SERVER_URL`, the variable Weave's own SDK reads, names another host for every
  request, such as your company's own deployment. It must be an https address, or http on
  this machine. `WANDB_BASE_URL` is W&B's other API and changes nothing here.
- `--page-size N` asks for N calls per request, from 1 to 1000 (the default is 1000). When
  Weave answers that it is being asked too often, the pull waits as long as the answer says
  and asks again.
- Without the key, with a key Weave refuses, or with a name no evaluation of the project has,
  the import stops with one `error:` line and exit code 1, and nothing is saved. A failure
  part way through a pull exits 3, and nothing is saved either.

### Download it from the Traces page

The Traces page downloads what it shows, as JSON, JSON Lines, CSV or TSV. With no filter it
shows one row for each evaluation, with totals and no case, and Poisson Trace refuses that
file saying so. Filter the page to the op `Evaluation.predict_and_score` first: the download
then holds one row for each case.

- The download holds every evaluation of the project in one file. `--evaluation NAME` says
  which one to read, by the evaluation's name or by the id of its `Evaluation.evaluate` call.
  Without it, a file that holds several is refused, naming each.
- It holds the rows alone: no call under a case and no exception. So there are no steps, tool
  calls or retries, `poisson-trace where` has no step to place a failure on, and a case that
  errored has no class.
- It carries no cost and no feedback: Weave puts both in an answer only when asked
  (`summary.weave.costs`, `summary.weave.feedback`), and the page does not ask. The summary
  counts the rows that record tokens and no cost.
- The CSV and the TSV hold a model's total tokens and no prompt or completion count, and they
  leave out the reference to the dataset row. So `--case-from example` is refused on them:
  name the case by a key of the row (`example:KEY`) or by `--case-from input`. Their cells
  are text, so a table pairs with the other exports by `--case-from input` only where the
  row's values are all text.

The service's answers are read too, saved as they came, a call a line. Pages of one answer
are given together. An answer that was not asked to expand the example
(`expand_columns: ["inputs.example"]`) holds a reference where the dataset row is: the case
is then `--case-from example`, and the input's length is not recorded. One import reads one
export of an evaluation: giving the same call twice, or the page's download beside an answer
of the service, is refused.

## Import and compare

One import is one version. Each import writes one new run into a store in Prove's format;
`poisson-trace fix-check` then compares the two runs.

<!-- skip reason="the form of the command: the words in capitals are yours to fill in" -->
```
poisson-trace import weave FILE [FILE ...] --store ROOT --run NAME
        --case-from ( example | example:KEY | input | none )
        --outcome-from ( status | score:KEY )
        [--cut X ( --below | --above )] [--evaluation NAME]
        [--keep-raw-text] [--page-size N]
        [--started ISO-8601] [--verdicts FILE] [--json]
```

- One `Evaluation.predict_and_score` call is one row: one case of the dataset, run once. An
  evaluation with several trials has several rows a case. Rows are in the order their calls
  started.
- `--case-from` says what pairs a row with the same input in the other version. `example` is
  the dataset row the case was run on, by the row's own digest in the reference to it, which
  is the same in both versions. `example:KEY` is a key of that row. `input` is a short key
  made from the row's values, never their text; it is also what a `--verdicts` file joins by.
  `none` reads every row as one input, which is right only if both versions saw the same mix
  of inputs, and the summary says so.
- `--outcome-from` says what counts as failed. `status`: the case errored, which is when its
  own call raised, or when something under it raised and it holds no output and no score. A
  step that failed and was tried again under a case that answered does not fail the case,
  though Weave marks that case's call `descendant_error`. `score:KEY`: a scorer's output,
  read at `--cut X` with `--below` or `--above`.
- A score is a number, or true or false: true is 1 and false is 0, and the summary counts the
  rows read so. A score is named by its path under the scorer (`judge.correct`), and by the
  scorer alone where the value sits under the scorer's own name (`exact`). A scorer's text is
  not kept.
- Weave runs no scorer on a case whose model raised. So a case that errored has no score, in
  every export. Read by a score it has no outcome: it is never read as a pass or as a fail,
  and the summary counts it.
- Also read, where the export holds them: how long the model's run took, which is Weave's own
  `model_latency`; the tokens and cost in the call's summary, a cost being the prompt's and
  the completion's together; the lengths of the dataset row and of the model's output; the
  steps and retries under the model's call; the calls Weave marks as model calls or as tool
  calls; a reaction, as feedback; and the class of the exception and the kind of step a
  failure came from. The scorers' calls are not counted as steps. What an export does not
  hold is recorded as not recorded, never as zero. Weave records no time to first token.
- The start is the first row's start.

In a `trace.toml`, `[signals]` can stand in for the flags: `case_field` for `--case-from`,
`outcome_field` for `--outcome-from`, `score_field` for a score's key (`KEY`, `score:KEY`,
`scores.KEY` or `output.scores.KEY`), and `cut` for `--cut`, which is used only where a score
is read. `cost_field` is not read here. A flag you give wins, and nothing stands in for
`--evaluation`. An `[[import]]` entry may name `weave:ENTITY/PROJECT/EVALUATION` as its file:
`poisson-trace init` pulls it, and `poisson-trace doctor` never does.

## The worked example

The files are in `tests/fixtures/ingest/weave/`: two evaluations on one dataset of ten rows,
run once each. The agent is a small stock desk (a lookup, a stock check, a model call and a
step that reads the reply), in a baseline and a candidate version, and a scorer scores each
answer true or false under the name `exact`. The commands run from the root of a clone and
write the store to `./store`.

The baseline, as Weave's service returned it:

<!-- command -->
```
poisson-trace import weave tests/fixtures/ingest/weave/api/trace-fixture-slice-baseline.jsonl \
  --store ./store --run old --case-from example --outcome-from score:exact --cut 0.5 --below
```

<!-- output exit=0 -->
```
ok  wrote run old to ./store: 10 rows, 10 cases, 1 repeat each; 6 passed, 3 failed, 1 with no outcome

# Poisson Trace · import · old

## Summary

- Wrote: old into ./store, from trace-fixture-slice-baseline.jsonl (weave): 10 tries on 10 inputs.
- Failures: 3 failed and 6 passed; 1 had no outcome. A try counts as failed when its exact score is below 0.5.
- Compared: Nothing yet. One import is one version.
- Next: Import the other version's file the same way: `poisson-trace import weave OTHER.jsonl --store ./store --run OTHER --case-from example --outcome-from score:exact --cut 0.5 --below`.

## Before you act on this

- Its start time is the earliest span's start in the file.
- When you compare, choose the smallest drop that matters to you (--max-mde) before you look at any results; Trace then says whether these tries could catch it.

## What was written

- run written: old · store: ./store
- tool: weave
- file: trace-fixture-slice-baseline.jsonl · sha256 50ad06bd4b62d01527dceee5f54d59fb73723eb126a58b4fa2753de524ced260
- declared: case_from example · outcome_from score:exact · cut 0.5 · side below · shapes ["call"]
- started: 2026-11-09T20:28:05.644964Z · from: earliest span
- rows 10 · cases 10 · repeats of a case: smallest 1, largest 1
- outcomes: met 6 · missed 3
- rows with no outcome: no score 1
- calls: 78
- predict_and_score calls: 10
- selected: 10
- no case: 0
- no cost recorded: 0
- scores that are true or false, read as 1 and 0: 9

In the command below, OLD and NEW are this run and the other version's run, imported into the same store, the older version first. X is the largest limit of detection you accept, as a share: 0.05 is five points.

next: poisson-trace fix-check OLD NEW --store ./store --event missed --inputs all --max-mde X  # old is OLD or NEW
```

One case errored, so it has no score and no outcome. The candidate, the same way:

<!-- command -->
```
poisson-trace import weave tests/fixtures/ingest/weave/api/trace-fixture-slice-candidate.jsonl \
  --store ./store --run new --case-from example --outcome-from score:exact --cut 0.5 --below
```

<!-- excerpt exit=0 -->
```
- rows 10 · cases 10 · repeats of a case: smallest 1, largest 1
- outcomes: met 8 · missed 1
- rows with no outcome: no score 1
```

<!-- command -->
```
poisson-trace fix-check old new --store ./store --event missed \
  --inputs all --max-mde 0.2
```

<!-- excerpt exit=0 -->
```
too small to tell  too few tries to see a drop of any size
```

<!-- excerpt exit=0 -->
```
| version | runs | failed | failure share | did not fail |
|---|---|---|---|---|
| old | 8 | 3 | 37.5% | 62.5% |
| new | 8 | 1 | 12.5% | 87.5% |
```

Each version has one case with no outcome, and they are different cases, so the check counts
the eight inputs that have an outcome on both sides and says which two it left out. Three
failures down to one, on eight inputs run once each, is too few to tell from chance. The
report's Guidance section says how many repeats of each input would be enough.

Where the baseline's failing cases stop:

<!-- command -->
```
poisson-trace where old --store ./store --event missed
```

<!-- excerpt exit=0 -->
```
ok  3 of 9 tries failed; each one's last step was another kind of step (not necessarily the cause)
```

The same baseline out of the Traces page's JSON, which holds all four evaluations of the
project, read by whether the case errored and paired by the input:

<!-- command -->
```
poisson-trace import weave tests/fixtures/ingest/weave/ui/predict-and-score.json \
  --store ./store --run old-by-status --case-from input --outcome-from status \
  --evaluation trace-fixture-slice-baseline
```

<!-- excerpt exit=0 -->
```
ok  wrote run old-by-status to ./store: 10 rows, 10 cases, 1 repeat each; 9 passed, 1 failed
```

And the candidate out of the page's CSV:

<!-- command -->
```
poisson-trace import weave tests/fixtures/ingest/weave/ui/predict-and-score.csv \
  --store ./store --run new-from-the-table --case-from input \
  --outcome-from score:exact --cut 0.5 --below --evaluation trace-fixture-slice-candidate
```

<!-- excerpt exit=0 -->
```
ok  wrote run new-from-the-table to ./store: 10 rows, 10 cases, 1 repeat each; 8 passed, 1 failed, 1 with no outcome
```

## What this does not do

- It does not run Weave, your agent or any model. It reads evaluations Weave already holds,
  from files you saved or from one pull with your own key.
- It does not make a comparison out of one run. A fix check is two versions on the same
  inputs, each imported as its own run.
- It is tested on evaluations written by weave 0.54.1 and reads other versions by the same
  field names. It does not read traces that are not an evaluation, a scorer's word as the
  outcome, or a human's annotation.
- It keeps no prompt, input, output or expected text, no error message and no note.
