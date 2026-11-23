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
| `cannot_say` | the sentences the report ends with: what this result cannot say |
| `versions` | the versions of Trace and Prove that wrote it |

A number is a JSON number and never `NaN`; a value that is missing is null. The same inputs
give the same bytes.

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
and the size listed; that `result.json` has every key of the table above; that the first
line of `report.md` is the verdict and the sentence of `result.json`; and that nothing Trace
never hands over is in it. It exits 0 when the bundle is whole. It exits 4 when it is not,
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
