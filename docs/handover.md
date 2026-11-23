# The handover: a result as files

A result from Trace can leave the terminal as a folder of files, a bundle, that another
program reads: a dashboard, a release gate, a record kept beside a release. This page is the
contract for that folder. It says how a bundle is written, what each file holds key by key,
which keys are promised, how to check a bundle before reading it, and what is never in one.
The recipe is [Into the product](recipes/into-the-product.md).

## Writing a bundle

`--out DIR` on `where`, `compare`, `fix-check` or `changes` prints the report as usual and
also writes the result into `DIR`, which it creates. A `DIR` that is there already is refused
unless you give `--force`. `--save` alone keeps the same result inside the store, under
`.poisson/artifacts/`, and writes no folder; `--out` does both.

The example is the store under `tests/fixtures/cs` in a clone of the repository:

<!-- command -->
```
mkdir -p my-agent && cp -R tests/fixtures/cs my-agent/prove-runs
cd my-agent && poisson-trace init --yes > /dev/null 2>&1
poisson-trace where latest --out bundle > /dev/null && ls bundle bundle/charts
```

<!-- output exit=0 -->
```
bundle:
artifact.json
charts
handover.json
report.md
result.json
table.parquet

bundle/charts:
curve.json
curve.svg
```

## The files

| file | what it holds |
|---|---|
| `result.json` | the result as data: what `--json` prints. What its keys promise is in the next section |
| `report.md` | the report as text, as the command printed it, the verdict line first |
| `table.parquet` | the report's numbers in long form, one row for each number, in the schema `poisson.table/1` |
| `charts/curve.svg`, `charts/curve.json` | from `where`: the curve as a picture, and the points behind it in the schema `poisson-trace.chart/1` |
| `charts/curves.svg`, `charts/curves.json`, `charts/hazard-ratio.svg`, `charts/hazard-ratio.json` | from `compare`: the two curves, and the ratio with its range. A `fix-check` or `changes` bundle has no chart |
| `artifact.json` | what made the result. `format` is `poisson.artifact/1`, `kind` is the verb, `id` the result's id, `tool` and `tool_version` what wrote it, `created_at` when. `inputs` holds `runs`, the ids of the runs read. `settings` holds every setting that changes the result, and where each came from. `summary` holds the `verdict`, its `sentence` and the `detail` lines under it. `files` lists the files above, each with its `path`, `role`, `media_type`, `schema` and `sha256`; a chart's entry has `data`, the path of its data file |
| `handover.json` | the list a reader checks first. `schema` is `poisson-trace.handover/1` and `verb` is the verb. `files` lists every other file of the bundle with its `name`, `sha256` and `bytes`. `versions` holds `trace` and `prove`, the two packages' versions. `written_at` is when, in UTC. `runs` lists each run read, with its `run_id`, its `run_name` and its `store` |
| `report.html` | the result as one page, once `poisson-trace report` has made it |

The first lines of a `handover.json`:

<!-- command -->
```
cd my-agent && head -7 bundle/handover.json
```

<!-- output exit=0 varies -->
```
{
  "schema": "poisson-trace.handover/1",
  "verb": "where",
  "files": [
    {
      "name": "artifact.json",
      "sha256": "…",
```

## What `result.json` promises

`result.json` holds every number of the report. It is one of the JSON documents Trace writes,
and each carries its schema id as its first key: `poisson-trace.where/1`,
`poisson-trace.compare/1`, `poisson-trace.runs/1`, `poisson-trace.fix-check/2`,
`poisson-trace.changes/2`, `poisson-trace.init/1` and `poisson-trace.doctor/1`. For every one
of them, as `--json` prints it and as a bundle's `result.json` holds it:

- within one number, no public key is renamed or removed, and keys are only added;
- a rename or a removal moves the number;
- a public key is any key that does not start with an underscore;
- keys that start with an underscore are internal and may change in any release.

What the main keys of `result.json` mean:

| key | what it is |
|---|---|
| `schema` | the first key: `poisson-trace.where/1`, `poisson-trace.compare/1`, `poisson-trace.fix-check/2` or `poisson-trace.changes/2`. Within one number, keys are only added |
| `verdict` | the verdict word: `ok` on `where` and `changes`; *different*, *no significant difference* or *too small to tell* on `compare` and `fix-check`, written without the stars |
| `sentence` | the sentence of the verdict line, exactly as printed |
| `next` | the command of the `next:` line, or null |
| `note` | a list of sentences, empty when there is none |
| `run` or `runs` | the run or the two runs read, each with its `run_id` and its `run_name` |
| `steps` | on `where` and `compare`: for every step, how many tries reached it and how many ended there. Optional; see [Steps and timings](#steps-and-timings) |
| `timings` | on `where` and `compare` run with `--timings` or `--timings-of`: each try's step times. Optional; see [Steps and timings](#steps-and-timings) |
| `cannot_say` | the sentences the report ends with: what this result cannot say |
| `versions` | the versions of Trace and Prove that wrote it |

A number is a JSON number and never `NaN`; a value that is missing is null. The same inputs
give the same bytes.

## Steps and timings

The JSON of `where` and `compare` carries two keys for a reader that draws the run step by
step: `steps`, which counts the tries at each step, and `timings`, which gives each try's
step times. Both are in `--json` and in `result.json`, just before `cannot_say`. Neither is
in the report, the table or the charts.

Both keys are optional. A reader must accept a `where/1` or `compare/1` document without
them: one written before they were added has neither, and `timings` is there only when it was
asked for. A verdict saved by an earlier Trace keeps the `result.json` it was saved with, so a
bundle written from it today has no `steps`.

### `steps`

A step is one leaf span of a try's trace, in the order the spans started: step 1 is its first
leaf, step 2 its second. `steps` lists every step, from the first to the last step any try
reached, with none left out. On a run with no traces it is an empty list.

<!-- command -->
```
cd my-agent && poisson-trace where latest --json
```

<!-- excerpt exit=0 -->
```
  "steps": [
    {
      "step": 1,
      "reached": 21,
      "ended_here": 0,
      "ends": {
        "died": 0,
        "ended": 0,
        "timed out": 0,
        "capped": 0
      },
      "died_by": [],
      "labels": [
        {
          "label": "llm",
          "count": 21
        }
      ]
    },
```

| key | what it is |
|---|---|
| `step` | the step's number, from 1 |
| `reached` | the tries that got to this step or past it. Only tries placed on a step are counted: at step 1 it equals `run.placement.placed` |
| `ended_here` | the tries whose last step this is, however they ended. At every step, `reached` less the next step's `reached` is `ended_here` |
| `ends` | `ended_here` split by how the try ended, always with the four words `died`, `ended`, `timed out` and `capped`, zeros kept. `capped` means the try's record stops here because its trace reached the run's span limit |
| `died_by` | the tries that failed here, by the step's label: a list of `{label, count}` in the order of `causes`, with no zero counts |
| `labels` | the tries that reached this step, by the label the step had for each of them: a list of `{label, count}` with no zero counts. Two tries' third steps can be of different kinds, so one step can have several labels |

A label is the kind of the step's span under `--by kind`, and the nearest declared step name
above it under `--by step`. `--by` changes the labels and nothing else: the step numbers and
the counts are the same under both.

The curve and the header agree with `steps`. The curve's points are the steps where a try
failed, with `at_risk` equal to `reached` and `died` equal to `ends.died`; each row of
`causes` has the deaths its label has in `died_by` over all steps; and the sum of each `ends`
word over the steps is that word's count in `run.placement`.

On `compare`, `steps` is `{"a": [...], "b": [...]}`, one list for each run. Both lists run to
the later of the two runs' last steps, so entry `i` of each is the same step. A step one run
never reached is listed for it with every count zero and empty lists. Each list counts every
try its run placed, not only those on the inputs both runs share.

### `timings`

`timings` is written when the command carries `--timings`, for every try of the run, or
`--timings-of HASH:REPLICATE`, for the tries named. It holds times, kinds, ids and labels. It
holds no span name and nothing a span recorded: no prompt, no output, no tool argument.

<!-- command -->
```
cd my-agent && poisson-trace where latest --timings-of 1a2aa279c5e046bc:0 --json
```

<!-- excerpt exit=0 -->
```
  "timings": {
    "most_steps": null,
    "conversations": 21,
    "listed": 1,
    "no_end": 0,
    "parents_no_end": 0,
    "no_tree": 0,
    "asked": [
      {
        "config_hash": "1a2aa279c5e046bc",
        "replicate_index": 0
      }
    ],
    "not_listed": [],
```

After these comes `items`, one object for each try listed. Shape only, with made-up values:

```json
{
  "config_hash": "3f9c0a1b2d4e5f60",
  "seed": 1832749261,
  "replicate_index": 0,
  "end": "died",
  "cause": "tool",
  "steps": [
    {"step": 1, "offset_ns": 1250000, "duration_ns": 812340000, "kind": "llm", "label": "llm", "span_id": "0000000a5e1f9c2b", "parent_id": "00000009c4d2a7e0"},
    {"step": 2, "offset_ns": 815002000, "duration_ns": 40211000, "kind": "tool", "label": "tool", "span_id": "0000000b77d0e3a1", "parent_id": "00000009c4d2a7e0"}
  ],
  "parents": [
    {"span_id": "0000000812ab90f1", "parent_id": null, "kind": "agent", "offset_ns": 0, "duration_ns": 861500000},
    {"span_id": "00000009c4d2a7e0", "parent_id": "0000000812ab90f1", "kind": "agent", "offset_ns": 1100000, "duration_ns": 856000000}
  ]
}
```

| key | what it is |
|---|---|
| `most_steps` | with `--timings`, the most steps and parent spans listed for one run, 20,000; null with `--timings-of`, which has no limit |
| `conversations` | the tries the run placed on a step, `run.placement.placed` |
| `listed` | the tries in `items` |
| `no_end` | the listed steps whose `duration_ns` is null |
| `parents_no_end` | the listed parent spans whose `duration_ns` is null |
| `no_tree` | the listed tries whose `parents` is null |
| `asked` | null with `--timings`; with `--timings-of`, the tries named, each `{config_hash, replicate_index}`, once each and in that order |
| `not_listed` | the tries named and not listed, each `{config_hash, replicate_index, why}`; always empty with `--timings` |
| `items[].config_hash`, `seed`, `replicate_index` | which try it is, as Prove stored it. `config_hash` and `replicate_index` together name one try of a run |
| `items[].end` | how it ended: `died`, `ended`, `timed out` or `capped` |
| `items[].cause` | the label of its last step when it died, else null |
| `items[].steps` | its steps, from 1 to its own last step |
| `offset_ns` | when the span started, in whole nanoseconds after the earliest start of any span of the try. It is never negative |
| `duration_ns` | the span's end less its start, in whole nanoseconds; null for a span with no recorded end, such as the one open when a try timed out |
| `kind` | the span's kind: `llm`, `tool`, `retrieval`, `db`, `http`, `agent` or `other`, or `unknown` |
| `label` | the step's label, the word `steps` and `causes` use |
| `span_id` | the span's id as stored when it is printable and at most 80 characters, else `sha256:` and 16 hex digits of its digest |
| `parent_id` | the `span_id` of the span's parent in the same try, written by the same rule so the two are equal as text; null for a span with no parent, and for one whose parent is not a span of the trace |
| `items[].parents` | the spans above the steps, such as an agent around its model and tool calls: each once, by start, with `span_id`, `parent_id`, `kind`, `offset_ns` and `duration_ns`. Empty when every span is a step |

To draw a try as a tree, join each `parent_id` to the `span_id` it names in `parents`. Every
`parent_id` that is not null names exactly one entry of the same item's `parents`, and a span
with a null `parent_id` is a root; a try can have several. `parents` is null, and every
`parent_id` with it, when the links of a trace cannot be followed, because two of its spans
share an id or its parent links go round in a circle. A store Prove wrote holds no such trace.

Only tries placed on a step are listed, the same tries `steps` counts, in the order of
`config_hash` and then `replicate_index`. On `compare`, `timings` is `{"a": {...}, "b": {...}}`,
each side as above for its run. A try and its pair in the other run have the same
`config_hash` and `replicate_index`.

**The limit, with `--timings`.** One run's list holds at most 20,000 spans, its steps and
parent spans counted together: it stops before the first try that would take it past that. A
try is listed whole or not at all, so `listed` is
then below `conversations`, and the report and `result.json`'s `note` say so in one line, such
as `timings lists 812 of 1,024 conversations: listing more would pass 20,000 steps and parent
spans`. `steps` is never cut.

**Named tries, with `--timings-of`.** `HASH` is the try's `config_hash` in full and
`REPLICATE` its `replicate_index`, as `timings` prints them. The option repeats, and on
`compare` one list of names applies to both runs, so one name fetches a pair. Each try named
is listed whole, with no limit. A name the run holds and did not place is in `not_listed`
with why: `no trace`, `unreadable trace`, `no leaf span` or `no outcome, not a timeout`. On
`compare`, a name only one run holds is in the other run's `not_listed` as `not in the run`.
A name that no run of the command holds is refused with exit code 1 and nothing written.

## Checking a bundle

`poisson-trace handover --check DIR` reads a bundle and holds it to what this page says:

<!-- command -->
```
cd my-agent && poisson-trace handover --check bundle
```

<!-- output exit=0 -->
```
ok  bundle holds what it promises: a where verdict over one run, 6 files of the digests and sizes listed, result.json with every key of the table, and nothing Trace does not hand over

next: poisson-trace report bundle
```

It checks that every file `handover.json` and `artifact.json` list is there with the digest
and the size listed; that `result.json` has every key of the table above; that `steps` and
`timings`, when a `where` or `compare` bundle has them, have the keys and the types the last
section gives; that the first line of `report.md` is the verdict and the sentence of
`result.json`; and that nothing Trace never hands over is in it. It exits 0 when the bundle is whole. It exits 4 when it is not,
with one line that says what is wrong. It exits 1 when `DIR` is missing, is not a folder or
holds no `handover.json`. Run it in your own tests over what Trace wrote: it is the test both
sides share.

## What is never in a bundle

No file of a bundle holds a prompt, an answer or any other text of a try; no key and no
token; no hostname; and no absolute path of your machine. A store is named as you gave it
when that was a relative path, and by its last folder alone when it was not. No text in
`result.json` is longer than 400 characters, and the check refuses a bundle where one is.

## How the promise is kept

Renaming or removing a public key is a breaking change. The number at the end of the
`schema` moves, the check refuses a bundle of the old number and names the version that wrote
it, and the CHANGELOG says so. Adding a key moves nothing, so a reader passes over a key it
does not know. Trace's own tests hold every public key of each document as it is written
today, and fail when one is renamed or removed without the number moving.

## The page, and the pages

`poisson-trace report DIR` writes `report.html` into a bundle and adds it to `handover.json`.
The page is the result for a person: the verdict line, the summary, every table, and the
curve drawn in the page. It has no script and loads nothing from the network, and the check
holds it to that. The recipe is [A page to send](recipes/a-page-to-send.md).

`poisson-trace ui` builds pages over a whole store: its runs and every verdict saved in it.
They are written under the store, in `.poisson/ui/trace/`, and open from disk. They are made
from the saved results and can be made again at any time.

## Beside an imported run

`poisson-trace import` writes a run into a store, and three records beside it:

- `.poisson/store.json` says who wrote the store, in the format `poisson.store/1`: `format`,
  `created_by` (a `tool` and its `version`), `created_at`, and `writers`, one entry for each
  tool that has written into the store, with its `tool`, its `version` and its `first_write`.
- `manifest.json` is the run's own record. Its `produced_by` says what made the run: `tool`
  and `version` (Trace's), `reader` (the tool whose files were read), `options` (what you
  declared for the import), and `from`, the files read, each with its `name` and its `sha256`.
- `events.jsonl` is the log of the import, one line for each event, in the schema
  `poisson.run-event/1`. Every line has `schema`, `at`, `kind` and `detail`. The kinds are
  `planned` (its detail: `run_id`, `reader`, `files` and `rows`), `started`, `progress` (its
  detail: `done`, `kept`, `errored` and `total`, in rows) and `finished` (its detail: `status`
  and `kept`). An import stopped with Ctrl-C ends with `interrupted` in place of `finished`.

## Into MLflow or W&B

Trace builds no exporter. If you keep runs in MLflow or in W&B, each thing Trace writes maps
onto a run there, and every key the mapping needs is in the files above:

| what Trace writes | MLflow | W&B |
|---|---|---|
| an imported run's run record | a run: `run_name` the run's name, params the `options` of `produced_by`, tags `poisson.tool` and `poisson.run_id` | a run: `name` the run's name, `config` the same options |
| `events.jsonl` | an artifact file of that run | an artifact file of that run |
| a `where` verdict | a run tagged `poisson.kind=where`, the run's id as a param, the verdict as a tag, `table.parquet` as an artifact | a run of its own, `table.parquet` as a `wandb.Table`, the verdict in the summary |
| a `compare` verdict | a run tagged `poisson.kind=compare`, the two run ids as params, the verdict as a tag, `table.parquet` as an artifact | a run of its own, `table.parquet` as a `wandb.Table`, the verdict in the summary |
| a `fix-check` verdict | a run tagged `poisson.kind=fix-check`, the two run ids as params, the verdict as a tag, `table.parquet` as an artifact | a run of its own, `table.parquet` as a `wandb.Table`, the verdict in the summary |
| a `changes` verdict | a run tagged `poisson.kind=changes`, the two run ids as params, `table.parquet` as an artifact | a run of its own, `table.parquet` as a `wandb.Table` |
| a chart | an artifact file: the SVG, with its data file | a `wandb.Html` of the SVG, or an image |
