# Fixture provenance

Four of Prove's stored runs, copied from the machine that made them with every observation
body removed, and three more added for the fix check (their section below).
Each fixture directory is a Prove store root: `tau2/` holds the two tau2-airline runs and the
patched pilot, `cs/` the two cs_agents runs and `humaneval/` the two HumanEval runs, so
`Store(root).runs()` lists them and `compare`, `fix-check` and `changes` can take every run of
a comparison from one `--store`.

| Fixture | Source (on the machine that made it) | Source manifest sha256 | Parts | Rows | Envelopes | `trace_obs` nulled | Size before | Size after |
|---|---|---|---|---|---|---|---|---|
| `tau2/20260915T210140Z-4847` | `~/code/poisson-labs/proofload-runs/20260915T210140Z-4847` | `cb190d2991963897…` | 200 | 200 | 200 | 200 | 10.9 MB | 2.23 MB |
| `tau2/20260915T211148Z-965d` | `~/code/poisson-labs/proofload-runs/20260915T211148Z-965d` | `1d1c05d10c215718…` | 200 | 200 | 200 | 200 | 11.2 MB | 2.22 MB |
| `cs/20260925T234602Z-3ea0` | `~/code/poisson-labs/demo-stack/store/20260925T234602Z-3ea0` | `f1bc2e6c15525850…` | 24 | 24 | 24 | 24 | 1.2 MB | 0.46 MB |
| `cs/20260925T235434Z-af48` | `~/code/poisson-labs/demo-stack/store/20260925T235434Z-af48` | `89640893c800d812…` | 1 | 24 | 24 | 24 | 1.0 MB | 0.25 MB |

The manifest of every fixture is byte-identical to its source (same sha256):

- `tau2/20260915T210140Z-4847/manifest.json`: `cb190d29919638971e49d5f6eb10c38bc2ba755c736921cd81686c7db0e7ac5c`
- `tau2/20260915T211148Z-965d/manifest.json`: `1d1c05d10c21571820f009194b7c84cee38f5f156e4b997f619b7c5738c33604`
- `cs/20260925T234602Z-3ea0/manifest.json`: `f1bc2e6c15525850af28c64d7e7e950e58cc41911cf6df13b03572bfd8437851`
- `cs/20260925T235434Z-af48/manifest.json`: `89640893c800d81203a41bcbd54f8f5de804ef9849345a3ad5700619c5a65c50`

`SHA256SUMS` beside this file lists the sha256 of every fixture file (808 files: the 429 of
the first four runs, their lines unchanged, 341 for the three added for the fix check, two for the
DeepEval import, four for the Ragas import, two for the table import, four for the JUnit
import, then twelve under `breakdown/`, seven under `setup-agent/`, three for the promptfoo
import, two for the Inspect import and two for the OpenAI Evals import), in the format
`shasum -a 256` prints. Verify with `cd tests/fixtures && shasum -a 256 -c SHA256SUMS`.

## The runs

- **`tau2/20260915T210140Z-4847` (A) and `tau2/20260915T211148Z-965d` (B).** Two runs of
  `tau2-airline/gpt-4.1-mini-2025-04-14@v0` on Modal, 50 tasks × 4 replicates, the same
  `run_salt`, ten minutes apart, `t_unit = steps`, traces via `from_otel` (semconv 1.42.0),
  every span an `llm` root, `capture.max_spans = 200`, no declaration. The same agent twice
  with nothing changed. Outcomes stored: `solved`, `unsolved`. Each run holds 200 parts of
  one row.
- **`cs/20260925T234602Z-3ea0` (record).** `cs_agents/record`, the OpenAI Agents SDK
  customer-service example recorded on gpt-4.1-mini, 24 episodes over 8 scenarios,
  `t_unit = turns`, nested spans (`agent` and `llm` leaves), no cap, no declaration.
  Outcomes stored: `app_error`, `forbidden_action`, `max_turns`, `resolved`, `unresolved`.
- **`cs/20260925T235434Z-af48` (replay).** `cs_agents/replay` of the same scenarios; 21
  rows with an outcome and 3 errored rows whose `error` is a `ReplayMiss` traceback (no
  outcome, not a timeout).

## The recipe as a script

`build_fixtures.py` beside this file holds the three recipes described below (bodies removed,
copied whole, outcome-only) and the one edit beyond them. Given the two source stores it
rebuilds all seven fixtures into an empty directory, checks each copy through Prove's own
reader, and compares every file it wrote with `SHA256SUMS`:

```
pip install pyarrow==25.0.1    # after Prove: pyarrow 25.0.1 exactly, as below
python tests/fixtures/build_fixtures.py DEST --runs RUNS_ROOT --cs CS_ROOT
```

The source stores are not public, so the script is the record of how the fixtures were made;
with the sources and pyarrow 25.0.1 it reproduces the 770 committed files byte for byte. On
another pyarrow the rewritten parts can differ in bytes (pyarrow 26.0.1, which a fresh install
of Prove brings, rewrites 753 of the 770 files differently), and the script's `FAIL` line then
names the pyarrow it found beside the 25.0.1 that wrote the fixtures. It is not listed in
`SHA256SUMS`, which covers the fixture stores only.

## The nulling recipe

For each source run: `manifest.json` copied byte for byte; each `episodes/part-*.parquet`
read with pyarrow, its `trace_obs` column replaced by an all-null string column of the same
length, and written back under the same name. Nothing else in any column changed (one exception, below): the
envelope (`trace`), `meta`, `config`, `backend_meta`, `outcome`, `error`, `t`, `horizon`,
`seed`, `replicate_index`, `wall_time` and `confidence` are the originals.

Checks made on each copy, through Prove's own reader:
- `Store.read(run, meta=False, trace="envelope")` returns the same number of rows as the
  source and the same envelope on every row (compared as canonical JSON);
- `config_hash`, `outcome`, `error`, `seed`, `replicate_index`, `t` and `horizon` are equal
  to the source's, row for row;
- `Store.read(run, meta=True, trace="full")` reassembles every trace with no `input` and no
  `output` on any span (`obs_left = 0` in the table);
- every string column (`config`, `meta`, `backend_meta`, `outcome`, `error`) was scanned
  for key-like material (`sk-…`, `api_key`, `bearer`, `password`, `secret`, `token`,
  `authorization`): no hit. The tau2 manifests' `environment.secrets` holds the Modal
  secret *name* `golden-pilot` and no value; the cs manifests hold no `secrets` entry.

The `trace_obs` bodies were removed because they hold prompt and completion content and
are 46 MB per tau2 run; nothing Trace reads is in them. What each fixture cannot express: the
tau2 pair has one kind, no nesting, no timeout, no cap reached,
no errored row and no declaration; the cs pair has nesting and two kinds but no timeout, no
cap and no declaration. Timed-out, capped, unreadable, no-leaf and declared-step paths run
on the synthetic store the tests build through `Store.create_run` / `Store.append`
(`tests/conftest.py`, `synth_rows`).

## One edit beyond the nulling

The cs replay fixture's three `error` values are Python tracebacks recorded by the replay
harness, and the originals name the home directory of the machine that recorded them. In
the copy, the prefix `/Users/<user>/` in those three strings reads `~/`; the rest of each
traceback, and every other value in every column, is the original. The
digests in `SHA256SUMS` are of the copy as committed.

## Added for the fix check

Three more of Prove's stored runs, copied after a scan of every byte that is committed
(below). The recipe is `build_fixtures.py` beside this file.

| Fixture | Source (on the machine that made it) | Source manifest sha256 | Parts | Rows | Made how | Size before | Size after |
|---|---|---|---|---|---|---|---|
| `tau2/20260917T140219Z-2b2d` | `~/code/poisson-labs/proofload-runs/20260917T140219Z-2b2d` | `99372c78184c30ad…` | 10 | 10 | copied whole | 84,934 B | 84,934 B |
| `humaneval/20260905T185407Z-0313` | `~/code/poisson-labs/proofload-runs/20260905T185407Z-0313` | `e13cfbc69907d8d8…` | 164 | 10,496 | outcome-only | 5.02 MB | 0.86 MB |
| `humaneval/20260905T195009Z-18ac` | `~/code/poisson-labs/proofload-runs/20260905T195009Z-18ac` | `23ed7fed99b338aa…` | 164 | 10,496 | outcome-only | 5.01 MB | 0.86 MB |

Every manifest is byte-identical to its source:

- `tau2/20260917T140219Z-2b2d/manifest.json`: `99372c78184c30adc34cbf889aa58743853bed4d34e975cda553a8c37613ff5d`
- `humaneval/20260905T185407Z-0313/manifest.json`: `e13cfbc69907d8d8ecd7005fb3d7d4ef36fe9712813cc6507bc967410b670d41`
- `humaneval/20260905T195009Z-18ac/manifest.json`: `23ed7fed99b338aab23f0c877f01bc2563a5c9b515e566ee3cd734ceb97eea05`

**The runs.**

- **`tau2/20260917T140219Z-2b2d` (the patched pilot).** `tau2_pilot.rollout:rollout_patched`,
  the guardrail pilot, on `tau2-airline/gpt-4.1-mini-2025-04-14@v0` on Modal, tasks 0 to 9
  with one replicate each (declared `replicates` 1), stored with no capture, so it holds no
  trace. Outcomes stored: `solved`, `unsolved`. Its config `{"task_id": …}` hashes as the tau2
  pair's does, so the three runs share their cells. A fix check on the three reads it as the
  new version against `965d` re-run, with `4847` selecting the inputs.
- **`humaneval/20260905T185407Z-0313` (A) and `humaneval/20260905T195009Z-18ac` (B).** Two runs
  of the golden-pilot HumanEval agent (`golden_pilot.agent:rollout`, gpt-4o-mini) on Modal, 164
  problems at temperatures 0.0 and 0.7 (328 cells) × 32 replicates, the same agent 56 minutes
  apart with nothing changed. Outcomes stored: `passed`, `failed_assertion`, `crashed`; no row
  without an outcome.

**Copied whole** (`2b2d`): the manifest and the ten parts byte for byte. Its `meta` holds the
episode's counters (messages, tool calls, tokens, cost), reward, termination reason, model names,
temperature and the sha256 of the system prompt and the guardrail; no prompt or completion text.

**Outcome-only** (the HumanEval pair): the manifest byte for byte; each part read with pyarrow
and written back with its two JSON columns `meta` and `backend_meta` replaced by `"{}"` (both
are non-nullable in Prove's schema). These parts predate Prove's trace split, so the trace was
inside `meta` and leaves with it. The eleven columns `Store.read(meta=False)` returns (run id,
config hash, config, seed, replicate index, outcome, t, horizon, confidence, error, wall time)
are the originals.

**Checks made on each copy, through Prove's own reader:** the same rows, and the eleven columns
equal row for row; `Store.tally` equal to the source's; no trace under `trace="envelope"` or
`trace="full"`; and every string in the manifest and in every cell of every column scanned for
key-like material (`sk-…`, `sk-ant-…`, `AKIA…`, GitHub tokens, `bearer …`, `api_key`,
`password`, `secret`, `authorization`, `token`), home-directory paths, the machine owner's name
and email addresses. The only hits are the manifest key `secrets`, which holds the Modal
secret *name* `golden-pilot` and no value (as in the tau2 pair), and the `meta` key `tokens` in
`2b2d`, which holds token counts.

**What each cannot express.** The patched pilot has one run per input, so its per-input flags
can never fire. The HumanEval pair is balanced and complete; it is the only real fixture on
which a flag fires. Unbalanced inputs, rows without an outcome, copies and every left-out
reason exist on the synthetic stores the tests build (`tests/fixcheck_support.py`,
`tests/test_fix_check_cli.py`).

## Added for the DeepEval import

Two result files written by DeepEval itself, one per run of the HumanEval pair above, for the
`poisson-trace-import deepeval` tests (`tests/ingest/`). They are not Prove stores: each is the
file DeepEval's `evaluate()` wrote into its results folder, gzipped. The recipe is `make.py`
beside them, in `ingest/deepeval/`.

| Fixture | Made from | Test cases | Tests Passed met / missed | File DeepEval wrote | Its sha256 (before gzip) | Size gzipped |
|---|---|---|---|---|---|---|
| `ingest/deepeval/humaneval-a.json.gz` | `humaneval/20260905T185407Z-0313` | 10,496 | 9,158 / 1,338 | `test_run_20260929_143252.json`, 3,902,440 B | `8782a23fd56704d6f68cf0677e8ca5a2a7ece84e680ce900187f00fe2d1ce0e6` | 160,114 B |
| `ingest/deepeval/humaneval-b.json.gz` | `humaneval/20260905T195009Z-18ac` | 10,496 | 9,109 / 1,387 | `test_run_20260929_143257.json`, 3,903,646 B | `81a8d2f3fed0c09fa42b8c581284d739d74f9fa10caa1b5035ff09bc62139bb2` | 159,847 B |

**How.** DeepEval 4.2.6 (PyPI, Apache-2.0) in its own environment, with
`DEEPEVAL_TELEMETRY_OPT_OUT=YES` and no model and no network call. Each stored row of the run,
read through `proofload.store.Store` in the order `Store.read` returns (by config hash, then
replicate index), became one `LLMTestCase`: `name` `<task_id>@<temperature>`, `input`
`<task_id> at temperature <temperature>`, `actual_output` the stored outcome
(`passed`, `failed_assertion` or `crashed`), `expected_output` `passed`. One custom metric,
`Tests Passed` (DeepEval's documented `BaseMetric`), scored 1.0 when the stored outcome was
`passed` and 0.0 otherwise, threshold 1.0, and DeepEval recorded its own `success` from that.
`evaluate()` ran with `DEEPEVAL_RESULTS_FOLDER` set, printing, caching and async off, and wrote
`test_run_<YYYYMMDD_HHMMSS>.json`. That file was gzipped as it is, level 9, with no name and
mtime 0 in the gzip header:

```
python tests/fixtures/ingest/deepeval/make.py rows WORK        # with proofload importable
python tests/fixtures/ingest/deepeval/make.py deepeval WORK    # with deepeval 4.2.6 importable
python tests/fixtures/ingest/deepeval/make.py gzip WORK tests/fixtures/ingest/deepeval
```

**What a rebuild gives.** DeepEval records wall-clock timings (`runDuration`, per test case and
per run) in the file, so a rebuild differs from the committed files in those values and in
nothing else; `make.py compare A B` says so. The name DeepEval gives the file carries the
local time of the machine that ran it, and is not kept. The digests in `SHA256SUMS` are of the
gzipped files as committed.

**Checks made.** Every string in both files was scanned for key-like material (`sk-…`,
`sk-ant-…`, `AKIA…`, GitHub tokens, `bearer …`, `api_key`, `password`, `secret`,
`authorization`, `token`), home-directory paths, the machine owner's name and email addresses:
no hit. The only text is the case names above, the outcome words and the metric's name. Read
back through the reader and Prove, each file gives the case counts of its source run, case by
case (`tests/ingest/test_deepeval_fixture.py`).

**What each cannot express.** One metric, no metric that raised, no conversational test case,
one threshold, and names the user set. Every other shape (a wrapped file, a link-only file, a
metric that raised, two metrics, positional names, a conversational case, differing
thresholds) is built as a dictionary in the tests. No file is a changed agent: the pair is the
same agent run twice.

## Added for the Ragas import

Four score tables in the shape Ragas's `EvaluationResult.to_pandas()` gives, for the
`poisson-trace-import ragas` tests (`tests/ingest/`). They are not Prove stores. The recipe is
`make.py` beside them, in `ingest/ragas/`.

| Fixture | Made from | Rows | Cases | Columns | Size |
|---|---|---|---|---|---|
| `ingest/ragas/memory-causal.jsonl.gz` | a stored memory-retrieval run, causal reads | 1,800 | 1,800 | `user_input`, `retrieved_context_ids`, `reference_context_ids`, `id_based_context_recall`, `id_based_context_precision` | 69,662 B |
| `ingest/ragas/memory-strong.jsonl.gz` | the same experiment, strong reads | 1,800 | 1,800 | the same five | 107,182 B |
| `ingest/ragas/rag-base.jsonl` | `R0bfried/RAGAS-BASE-llama-3-2-1B-eval2` on Hugging Face, commit `ebed5a6e42407ee10fc63abff17f5b270b7e0aa4` | 150 | 146 | `case`, `faithfulness`, `answer_relevancy`, `answer_correctness` | 17,599 B |
| `ingest/ragas/rag-raft.jsonl` | `R0bfried/RAGAS-RAFT-llama-3-2-1B-eval2` on Hugging Face, commit `5b131e43163020e01e13f2d9b195481ce3317c11` | 150 | 146 | the same four | 17,602 B |

**The memory pair.** Two runs of one stored memory-retrieval experiment: 18 conditions × 100
generated customer histories, the same 1,800 lookups on a memory with causal reads and on one
with strong reads. Each stored row holds the fact ids the memory returned and the fact ids that
answer the question; no model is involved. The two source runs are Prove stores that are not
public: run `20260928T193736Z-d407` (causal) and run `20260929T082616Z-6883` (strong). Their
manifests' sha256 are
`fc979bc6e7e925fe4866899a18e2e40e5af0290accde68c0aedde60c006ba601` (causal) and
`613fe6fd1eef4e19e3bfb1e99070a84f017ee80641468041c158990a812a4548` (strong).

Each stored row, read through `proofload.store.Store` in the order `Store.read` returns, became
one Ragas `SingleTurnSample`: `user_input` the row's own id, `<config_hash>:<seed>`;
`retrieved_context_ids` and `reference_context_ids` the two lists of fact ids. Ragas 0.4.3
(PyPI, Apache-2.0), installed beside `langchain-community` 0.3.31 because it does not import
beside 0.4.2, scored every sample with its `IDBasedContextRecall` and `IDBasedContextPrecision`,
which call no model, with its usage tracking off (`RAGAS_DO_NOT_TRACK=true`; without it Ragas
posts usage events to its own server). The table `to_pandas()` gave was saved with
`to_json(orient="records", lines=True)` and gzipped as it is, level 9, with no name and mtime 0
in the gzip header:

```
python tests/fixtures/ingest/ragas/make.py memory-rows SOURCE CAUSAL STRONG WORK   # proofload importable
python tests/fixtures/ingest/ragas/make.py memory-score WORK                       # ragas 0.4.3 importable
python tests/fixtures/ingest/ragas/make.py memory-gzip WORK tests/fixtures/ingest/ragas
```

| Table as Ragas's `to_json` wrote it | sha256 | Bytes |
|---|---|---|
| `memory-causal.jsonl` | `8573a43b5ffb70d49f45f9438528ab69e1830600253b8f0e0abd18f1cf44b6ca` | 416,358 |
| `memory-strong.jsonl` | `be6037eb6c884e56955ccd9e28b1f9ec666c160072882514029611550cb4f95d` | 526,032 |

On the 1,130 samples of the causal run where the memory returned nothing, Ragas printed that it
cannot calculate precision without retrieved ids and wrote `NaN`, saved as `null`. Recall is 0
or 1 on every row: 1,140 rows of the causal run are 0, none of the strong run.

**The public pair.** Two result sets published on Hugging Face by one author on 2025-03-31, each
the table `to_pandas()` gives: 150 rows, the same questions in the same order, three
model-judged Ragas scores per row, a base Llama 3.2 1B and the same model fine-tuned. The Ragas
version that made them is not stated. Neither set carries a licence (each dataset card holds its
schema and nothing else), so the fixture keeps a hash of each question and the three scores, and
no question, context, answer or reference text: `case` is `q-` and the first 16 hex characters of
the SHA-256 of `user_input`'s UTF-8 bytes; `faithfulness`, `answer_relevancy` and
`answer_correctness` are the published values as pandas's JSON writer renders them, at its default
ten decimal digits: the largest change from a published value is 5e-11, and no outcome at any cut
the tests use moves. `make.py` reads each Parquet file by URL at the commit above and refuses it
unless its sha256 is the one pinned:

```
python tests/fixtures/ingest/ragas/make.py pair WORK tests/fixtures/ingest/ragas   # pandas and pyarrow; reads two URLs
```

| Source file at the pinned commit | sha256 | Bytes |
|---|---|---|
| `RAGAS-BASE-llama-3-2-1B-eval2/data/train-00000-of-00001.parquet` | `fc76783271005b0f538bef880692da45edbe0ccee5f4accc44593fce3388426b` | 993,825 |
| `RAGAS-RAFT-llama-3-2-1B-eval2/data/train-00000-of-00001.parquet` | `52485d1ce1c8758cdec2ce174f4af82ae61e777c879c39a599791b3f8146acca` | 802,977 |

In each set the 150 rows hold 146 questions: one asked three times and two asked twice.
`faithfulness` has no score on 3 rows of the base set and 8 of the fine-tuned one; the other two
scores are on every row.

**What a rebuild gives.** Given the source stores and the two URLs, `make.py` reproduces all four
files byte for byte (pandas 3.0.6, pyarrow 25.0.1). The digests in `SHA256SUMS` are of the files
as committed.

**Rebuilt end to end.** All four recipe steps were run, from the two source stores
and from huggingface.co, with `make.py` as committed, in three clean environments on Python
3.11.7. No model was called, no key was set (each step ran with only `HOME` and `PATH` in its
environment), nothing was paid.

| Step | Environment | Result |
|---|---|---|
| `memory-rows` | poisson-prove 0.1.2 (pandas 3.1.1, pyarrow 26.0.1) | 1,800 rows from each run; the manifest sha256 it printed for each run is the one recorded above |
| `memory-score` | ragas 0.4.3, langchain-community 0.3.31, pandas 3.0.6, pyarrow 25.0.1 | 1,800 samples scored per run; Ragas printed its no-retrieved-ids notice 1,130 times, all on the causal run |
| `memory-gzip` | the same | `memory-causal.jsonl` and `memory-strong.jsonl` have the sha256 and byte counts in the table above; the two `.jsonl.gz` files are `cmp`-equal to the committed ones and to their `SHA256SUMS` lines |
| `pair` | pandas 3.0.6, pyarrow 25.0.1 | both Parquet files had the pinned sha256 (`make.py` refuses them otherwise); `rag-base.jsonl` and `rag-raft.jsonl` are `cmp`-equal to the committed files and to their `SHA256SUMS` lines |

All four outputs equal the committed files byte for byte, so no fixture changed. The sources
were copied to a scratch folder first, and the copies' manifests have the two sha256 above
(the copies were byte for byte the originals); the stores themselves were not written to.
An earlier run, which could not read the stores or reach huggingface.co, ran
`memory-score` and `memory-gzip` alone, on rows written from the committed tables' own
columns, and also found them equal.

**Checks made.** Every string in the four files is one of three generated shapes: a row id (16 hex
characters, a colon and digits), a fact id (`F-` and 12 hex characters) or a question hash (`q-`
and 16 hex characters); no other text is present. Every string was also scanned for key-like
material (`sk-…`, `AKIA…`, GitHub tokens, `bearer …`, `api_key`, `password`, `secret`,
`authorization`, `token`), home-directory paths, the machine owner's name and email addresses:
no hit.

**What each cannot express.** The memory pair has one run per case, recall scores that are 0 or
1, and missing scores on one version only; it cannot produce a flag or a mixed outcome. The
public pair has continuous scores, missing scores on both versions and three repeated questions,
so a few cases carry more than one run; none has enough runs to be flagged on its own. Neither
pair is a designed experiment with repeats. CSV text cells, an `@experiment` file with the user's
own columns, a missing case value and every refusal are built in the tests
(`tests/ingest/test_ragas.py`), and Ragas's own output is read once in lane J
(`tests/ingest/test_ragas_package.py`).

## Added for the table import

Two tables of this machine's HumanEval outcomes, one per run of the HumanEval pair above, written
as CSV, for the `poisson-trace import table` tests. They are not Prove stores. The recipe is
`make.py` beside them, in `ingest/table/`.

| Fixture | Made from | Rows | Cases | Columns | failed_assertion / crashed / passed | Size |
|---|---|---|---|---|---|---|
| `ingest/table/humaneval-a.csv` | `humaneval/20260905T185407Z-0313` | 10,496 | 328 | `case`, `task_id`, `temperature`, `replicate`, `outcome` | 1,330 / 8 / 9,158 | 478,807 B |
| `ingest/table/humaneval-b.csv` | `humaneval/20260905T195009Z-18ac` | 10,496 | 328 | the same five | 1,376 / 11 / 9,109 | 479,270 B |

**How.** Each stored row of the run, read through `proofload.store.Store` (Prove 0.0.1, under
its name before it was published; read again through `poisson_prove.store.Store` of
`poisson-prove==0.1.2` from PyPI, the recipe writes the same two files byte for
byte) in the order `Store.read` returns it, became one line: `case` is
`<task_id>@<temperature>`, as the DeepEval fixture names its test cases; `task_id`,
`temperature` and `replicate` are the row's config and replicate index; `outcome` is the stored
outcome word. Nothing else of the row is written. Python's `csv` module wrote the file, UTF-8,
a header line, a line feed after every line:

```
python tests/fixtures/ingest/table/make.py tests/fixtures/humaneval tests/fixtures/ingest/table
```

**What a rebuild gives.** The same two files byte for byte, from the committed store.

**Checks made.** The only text is the column names, the HumanEval task ids, the two
temperatures, the replicate numbers and the three outcome words. Read back through the table
reader and Prove with `--case-column case --outcome-column outcome --failed failed_assertion
--failed crashed`, each file gives its source run's failures case by case, and the fix check and
the changes on the two imported runs give the source runs' numbers
(`tests/test_junit_table_fixtures.py`).

**What each cannot express.** One outcome column of words, no score, no empty cell, no other
format than CSV. Every other shape (JSON Lines, JSON, Parquet, gzip, scores at a cut, empty
cells, true and false, refusals) is built in the tests (`tests/test_junit_table.py`).

## Added for the JUnit import

Four JUnit XML reports written by pytest 9.1.1 (Python 3.11.7), two pairs, for the
`poisson-trace import junit` tests. They are not Prove stores. The recipe is `make.py` beside
them, in `ingest/junit/`, with the suite `replay_humaneval.py` and the plugin `fixture_host.py`.

| Fixture | The suite | Test cases | Passed / failed / errors / skipped | Suite timestamp | Size |
|---|---|---|---|---|---|
| `ingest/junit/trace-suite-1.xml` | three of Trace's own test files at `3862811` | 91 | 90 / 0 / 0 / 1 | `2026-10-13T00:01:11.564615-04:00` | 14,727 B |
| `ingest/junit/trace-suite-2.xml` | the same, run again | 91 | 90 / 0 / 0 / 1 | `2026-10-13T00:01:23.261977-04:00` | 14,727 B |
| `ingest/junit/humaneval-a.xml` | `replay_humaneval.py` on `humaneval/20260905T185407Z-0313` | 656 | 569 / 86 / 1 / 0 | `2026-10-13T00:20:34.510483-04:00` | 92,702 B |
| `ingest/junit/humaneval-b.xml` | `replay_humaneval.py` on `humaneval/20260905T195009Z-18ac` | 656 | 573 / 83 / 0 / 0 | `2026-10-13T00:20:35.677086-04:00` | 91,387 B |

**Trace's own tests, run twice.** `tests/test_tf1_names.py`, `tests/ingest/test_cut.py` and
`tests/ingest/test_rows.py` of Trace's `main` at `3862811`, run from a `git archive` of that
commit extracted at `/Users/Shared/trace-fixture/trace` (so the one path pytest writes, a skip's
location, names no home folder), one run after the other, nothing changed between them. One test
skips itself; nothing fails. pytest writes each run's Hypothesis statistics as properties.

```
python tests/fixtures/ingest/junit/make.py own tests/fixtures/ingest/junit   # from the root of that checkout
```

**The replay suite, run against each stored run.** `replay_humaneval.py` holds one test per
HumanEval problem at temperature 0.7 in each of four classes, `TestRepeat0` to `TestRepeat3`,
one per replicate: a test passes when the stored episode passed, fails on its assertion when the
episode failed its assertions, and errors in its setup when the episode crashed. Its name does
not begin with `test_`, so Trace's own suite never collects it. It was run in
`/Users/Shared/trace-fixture/replay`, beside a copy of the committed HumanEval store, with an
empty pytest config so that the class names are the suite's own (`replay_humaneval.TestRepeat0`):

```
python tests/fixtures/ingest/junit/make.py replay tests/fixtures/ingest/junit store   # from that folder
```

With `--case name` the four classes' tests of one problem are four repeats of one case, so each
report reads as the run's 164 problems at four repeats each.

**The plugin.** pytest writes the machine's name into each report's `hostname`; the plugin
`fixture_host.py`, loaded with `-p fixture_host`, gives it `localhost`. Nothing is edited after
pytest writes a report.

**What a rebuild gives.** pytest records wall-clock times (each test case's `time`, each suite's
`time` and `timestamp`) and Hypothesis's statistics, so a rebuild differs from the committed files
in those values and in nothing else.

**Checks made.** Every string in the four files, the Hypothesis statistics decoded, was scanned
for key-like material (`sk-…`, `AKIA…`, GitHub tokens, `bearer …`, `api_key`, `password`,
`secret`, `authorization`, `token`), home-directory paths, the machine owner's name and email
addresses: no hit. The only text is test names, class names, the replay suite's assertion
messages and tracebacks (its own file and line), the skip's reason and location, and the
statistics. Read back through the JUnit reader and Prove, each report of Trace's own tests is
91 test cases, 90 passed and 1 skipped; each replay report gives its run's failures problem by
problem (`tests/test_junit_table_fixtures.py`).

**What each cannot express.** Trace's own tests fail nothing, so `--event missed` names no
outcome on that pair, and each test runs once. The replay pair has one error (in the first run
only), no skip and no test case without a class name. Suites nested in suites, a lone
`<testsuite>` root, a timestamp with no zone, a test case with no name, and every refusal are
built in the tests (`tests/test_junit_table_junit.py`).

## Added for the promptfoo import

Three files promptfoo 0.120.19 (npm, Node v22.14.0) wrote in one evaluation on 2026-10-07, for the
`poisson-trace import promptfoo` tests. They are not Prove stores. They are copied here byte for
byte as the tool wrote them. The config is `promptfooconfig.yaml` beside them.

| Fixture | What it is | Rows | Size |
|---|---|---|---|
| `ingest/promptfoo/results.json` | `-o results.json`: `evalId`, `results` (`version` 3, `timestamp` `2026-10-07T04:22:52.124Z`, `prompts`, `results`, `stats`), `config`, `shareableUrl` (null), `metadata` | 8 | 21,527 B |
| `ingest/promptfoo/results.jsonl` | `-o results.jsonl`: one result object per line, no `evalId` and no timestamp | 8 | 10,818 B |
| `ingest/promptfoo/results.csv` | `-o results.csv`: one row per test, one column group per prompt, `Status` and the rest repeated | 4 | 790 B |

```
PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_DISABLE_UPDATE=1 PROMPTFOO_CONFIG_DIR=<a scratch folder> \
  promptfoo eval -c promptfooconfig.yaml -o results.json -o results.jsonl -o results.csv --no-cache --no-progress-bar
```

The `echo` provider returns the rendered prompt as the output: no key, no model call, $0. Two
prompts (`old: {{text}}` and `new: {{text}} with the word banana`, promptfoo's labels being the
prompts themselves) by four tests (`case` q1 to q4), each with one `contains` assertion: the old
prompt fails q1 and q2 (`failureReason` 1, an assertion) and passes q3 and q4; the new prompt passes
all four. No row has `failureReason` 2 (an error). The provider records its tokens as zero and its
cost as zero; it records no cached or reasoning tokens.

**What a rebuild gives.** promptfoo records an `evalId`, ids, timestamps and latencies, so a rebuild
differs in those and in nothing else.

**Checks made.** Every string was scanned for key-like material, home-directory paths, the machine
owner's name and email addresses: no hit.

**What it cannot express.** One provider; no error row; no assertion other than `contains`; no
named scores; no token, cost or latency a model gave. The other assertion types, an error row, a
second provider and every refusal are built in the tests from this file with one field changed
(`tests/test_three_tools_promptfoo.py`).

## Added for the Inspect import

Two logs inspect_ai 0.3.277 (Python 3.11) wrote on 2026-10-07, for the `poisson-trace import
inspect` tests, copied byte for byte as the tool wrote them. The task is `fixture_task.py` and the
run `run_fixture.py`, beside them, with `INSPECT_DISABLE_TELEMETRY=1`; `run_fixture.py` is the
script as it was run with its one unused import (`sys`) removed, so the repository's lint passes
on it.

| Fixture | What it is | Samples × epochs | Size |
|---|---|---|---|
| `ingest/inspect/2026-10-07T04-23-47-00-00_trace-fixture_CV3jq8f7FTjwkaYb3zj3m2.eval` | the old version, `log_format="eval"`: a zip whose every member is Zstandard-compressed (compress type 93), with `header.json`, `samples/<id>_epoch_<n>.json`, `summaries.json`, `reductions.json` and `_journal/` | 3 × 2 | 14,528 B |
| `ingest/inspect/2026-10-07T04-23-51-00-00_trace-fixture_2nSEDuHHzKiTUjJW3kXknY.json` | the new version, `log_format="json"`: one object, `version` 2, `status` `success` | 3 × 2 | 68,795 B |

```
python run_fixture.py   # in a folder holding fixture_task.py, inspect_ai 0.3.277 installed
```

The model is `mockllm/model` with its outputs given (`custom_outputs`): no key, no model call, $0.
Scored by `includes` (`C` or `I`). Old: q1 right twice, q2 wrong then right, q3 wrong twice. New:
right on every sample but q3's second epoch. Python 3.11's `zipfile` cannot read the `.eval`
members (`NotImplementedError`); the `zstandard` package can.

**What a rebuild gives.** Inspect records ids, timestamps and timings, so a rebuild differs in
those and in nothing else.

**Checks made.** Every string, the `.eval` members decompressed, was scanned for key-like
material, home-directory paths, the machine owner's name and email addresses: no hit.

**What it cannot express.** One scorer with letter values; no sample error, no limit, no tool
call, no stop reason but `stop`, no log whose status is `error`. Those and every refusal are built
in the tests from these files with one field changed (`tests/test_three_tools_inspect.py`).

## Added for the OpenAI Evals import

Two records evals 3.0.1.post1 (`oaieval`, Python 3.11) wrote on 2026-10-07, for the `poisson-trace
import openai-evals` tests.

| Fixture | What it is | `match` events | Size |
|---|---|---|---|
| `ingest/openai-evals/old.jsonl` | `oaieval dummy test-match --record_path old.jsonl --max_samples 5` | 3 | 1,625 B |
| `ingest/openai-evals/new.jsonl` | the same into `new.jsonl` | 3 | 1,625 B |

The `dummy` completion function answers every sample with the same sentence: no model call, $0
(the package constructs an OpenAI client when imported, so `OPENAI_API_KEY=placeholder-no-call` was
set). The bundled `test-match` eval has three samples, so each file holds a `spec` line, a
`final_report` line and three `match` events, every one with `data.correct` false: the pair shows
the import and a fix check with nothing to compare, not a difference. No `sampling` event was
written ("Found 0/0 sampling events with usage data").

**One edit.** The `spec` line's `run_config.eval_spec.registry_path` named the scratch virtualenv
the tool ran in, under the machine owner's home-derived temporary folder; that prefix is replaced
by `/opt/venv` in both files, and nothing else is changed. The files as the tool wrote them have
SHA-256 `661b49d0c386d7afe1d3f8558099c6ee356f5934c167f5d33d2a64275010e1d6` (old) and
`087171f6390b76e0612402f30f88b73a15f15ddcd9bd789fdb4d1ddf60f93af2` (new), and are not committed.

**Checks made.** After the edit, every string was scanned for key-like material, home-directory
paths, the machine owner's name and email addresses: no hit.

**What it cannot express.** No passing sample, no repeat of a sample, no `sampling` or `metrics`
event, no empty answer. Those and every refusal are built in the tests from these files with one
line added or changed (`tests/test_three_tools_openai_evals.py`).

## Added for the setup agent

`setup-agent/setup-file-format-1.txt` is the shared text of the Poisson setup file, format 1
(the rules, the check, the prompt and the hand-over opening), byte for byte as the shared page
writes it, with the placeholders a tool fills; the same text Prove's copy carries.
`tests/test_setup_agent_skill.py` checks the skill `poisson-trace init --agent` writes against it.

`setup-agent/sample-repo/` is a small repository written by hand for the scripted run of
`tests/test_setup_agent_scripted.py`: a stand-in support agent that calls no model (`agent/`, naming the
failure outcomes), a scoring module naming the cut a Ragas row must reach (`evals/score_rag.py`),
the agent's own tests (`tests/agent_checks.py`), a `pyproject.toml` naming the tools, and a
README saying which results are old and which new. The store and the result files are not
copied in: each test builds its copy of the repository by copying the `cs` store to `store/`,
`ingest/ragas/rag-base.jsonl` and `rag-raft.jsonl` to `evals/results/`, and
`ingest/junit/humaneval-a.xml` and `humaneval-b.xml` to `reports/junit-old.xml` and
`reports/junit-new.xml`. `setup-agent/expected/trace.toml` is the config a correct agent writes
for it. No key, no model and no network were used.

## Added for the failure breakdown and the table fixes

`breakdown/mockups/` holds eight captures of a real pseudo-terminal, copied byte for byte: every
character the terminal received from Trace, the escape sequences removed. The failure breakdown on
the committed Prove 0.1.3 store at 80 and 140 columns, pretty and `--plain`
(`breakdown-prove-*`); the continuous-measures table as proposed for the DeepEval and Inspect
imports of the committed `ingest/deepeval/humaneval-{a,b}.json.gz` and `ingest/inspect/` logs at
80 and 140 columns (`continuous-proposed-*`). The tests of
`tests/test_bd_*.py` hold Trace's output to them (with one cell corrected).

`breakdown/main-pins.json` holds the digests of what an earlier main, `7d601f5`, printed, so that
`tests/test_breakdown_unchanged.py` can check every other output stays as it was; taken by
`breakdown/make_main_pins.py` on that commit, twice, with the same result. Paths are written
`<ROOT>`. No key, no model and no network were used.

## Added for the Braintrust captures

Real captures from Braintrust's service, made on 2026-11-09 against a free account, for the
Braintrust reader's tests. They are not Prove stores. Tools: braintrust 0.49.3 (Python SDK and
its `braintrust eval` command), openai 3.48.0, Python 3.12.13, macOS. The UI's own JSON and CSV
downloads are in `ingest/braintrust/ui/`.

**The runs.** Project `trace-fixture` (id `5fc53fc7-f099-43a1-b281-9e45c708bf38`), four experiments:

| Experiment | Id | Created (UTC) | Script | Cases | Model |
|---|---|---|---|---|---|
| `old` | `c12245bf-c48d-4128-b0c0-b30183901c26` | 20:24:00 | `fixture.eval.py` | 6 (3 × 2) | none (a lookup) |
| `new` | `6fda40a5-37d0-4586-b75f-ba552174780a` | 20:24:02 | `fixture.eval.py` | 6 (3 × 2) | none (a lookup) |
| `slice-baseline` | `5eddbe35-a975-4a3c-a34c-c59ad5ab4896` | 20:24:14 | `slice.eval.py` | 10 | gpt-4.1-mini |
| `slice-candidate` | `def2b2e5-9c1a-4e05-8861-3e9f3c14d332` | 20:24:15 | `slice.eval.py` | 10 | gpt-4.1-mini |

```
braintrust eval fixture.eval.py
CAPTURE_LEDGER=<a file> CAPTURE_CAP_USD=0.25 braintrust eval slice.eval.py
python pull.py api
```

`fixture.eval.py` is the script as it was run, byte for byte: `old` is the baseline and
`new` the candidate, inline data, one `exact` score. `old` fails q2 and q3 (four of six rows);
**`new` has no failing row.** `slice.eval.py` is the paid slice: a stock-desk agent in two versions
over a Braintrust dataset (`stock-10`, id `754aa7c9-75b6-40ef-b927-13037f5fee97`, record ids `c01`
to `c10`), four steps a case (`find_policy`, a function span; `check_stock`, a tool span; the model
call, an llm span through `wrap_openai`; `parse_answer`, a function span), two scores (`exact`,
`gave_answer`), one classifier (`failure_kind`) and a tag naming the version. Its failures are
planted and listed at the top of the script: baseline c03 and c06 wrong, c08 an error
(`TimeoutError` in the tool), c10 wrong by answering `unknown`; candidate c04 a tool refusal
retried into a pass, c06 wrong, c09 an error (`ValueError` in `parse_answer`, the reply cut at
three tokens). `braintrust eval slice.eval.py` exits 1 because of the two planted errors.

**The files** (`ingest/braintrust/api/`, each a response body as the service sent it, but for the
replacements below; `pull.py`'s docstring gives each request, and `requests.json` lists the 28
requests made with their statuses):

| Files | Request | What they hold |
|---|---|---|
| `experiments.json` | `GET /v1/experiment?project_name=trace-fixture` | the four experiments, with `repo_info`, `dataset_id`, `metadata` |
| `<name>.fetch.json` × 4 | `GET /v1/experiment/{id}/fetch?limit=1000` | `events`, `cursor`: 18, 18, 85 and 88 span events |
| `<name>.btql-spans.json` × 4 | `POST /btql`, `from: experiment('{id}') spans` | `data`, `schema`, `cursor`: the same events |
| `<name>.btql-traces.json` × 4 | `POST /btql`, `… traces` | the same events grouped by trace |
| `<name>.btql-summary.json` × 4 | `POST /btql`, `… summary` | one row a case (6, 6, 10, 10), with scores, metrics and error counts rolled up, `comparison_key`, `span_type_info` |
| `slice-candidate.fetch.page-1…5.json` | the fetch in pages of 25, by `cursor` | 25, 25, 25, 13 and 0 events |
| `slice-candidate.btql-spans.page-1…5.json` | the spans query in pages of 25, by `cursor` | the same paging |

**The UI downloads** (`ingest/braintrust/ui/`, eight files): `old`, `new`, `slice-baseline` and
`slice-candidate`, each as `.json` and `.csv`, downloaded by hand at 21:04 to 21:05 UTC from each
experiment's own table (the experiment opened from the project's Experiments list, then the
table's download control, once a format) and named by hand after the experiment. The JSON is a
list with one object a case (6, 6, 10, 10); the CSV has the same rows, with `input`, `tags`,
`classifications`, `scores`, `metrics` and `metadata` each a cell of JSON text. Columns: `name`
(`eval`), `input`, `output`, `expected`, `tags`, `scores`, `metrics`, `metadata`, `comments`,
`created` (milliseconds), `__bt_assignments`, and in the slice `classifications` and `error`.
It is the `summary` shape with the ids taken out: scores and the rolled-up `metrics`
(`estimated_cost`, token counts, `errors`, `tool_errors`, `llm_calls`, `duration`) are on the
row, but **there is no row id, no span id, no experiment id and no `origin`**, so the case is
known only from `input` (or from what the script put in `metadata`), and the experiment only
from the file. An errored row has `output` null, every score null (`{"exact":null,…}`),
`metadata` null and the traceback in `error`; in the JSON the `error` key is present on that row
alone, in the CSV the column is there for every row. A classification's value is a string of
JSON (`"[{\"id\":\"wrong_answer\"}]"`). The only replacements made in these files are the two
paths in the tracebacks.

**What a reader finds.** In `fetch` and in the `spans` and `traces` shapes the root (`eval`) span
carries `input`, `output`, `expected`, `error`, `tags`, `classifications`, `origin` (the dataset
record's `id`, in the slice only: the lookup fixture's inline data has `origin` null) and
`metrics` with `start`, `end` and `duration` alone; **its `scores` is null: each score is on a
child span of type `score`**. Only the `summary` shape gives a root row its scores, and its
`metrics` there add `prompt_tokens`, `completion_tokens`, `total_tokens`, `estimated_cost`,
`llm_calls`, `tool_calls`, `errors`, `llm_errors`, `tool_errors`, `time_to_first_token`. Token
counts, `time_to_first_token` and `estimated_cost` are on each llm span in every shape (71 prompt
and 1 completion token give `3.0000000000000004e-05`); the lookup experiments have
`estimated_cost` null. An errored case has a traceback in `error` on the failing step, on the
`task` span and on the root, `output` null, and no score span. Span types present: `eval`,
`task`, `function`, `tool`, `llm`, `score`, `classifier`. `comments` is null everywhere: nothing
was commented in the UI.

**Spend.** 19 calls to gpt-4.1-mini (`gpt-4.1-mini-2025-04-14`), 1,493 prompt and 75 completion
tokens, **$0.000717** at list price ($0.40 and $1.60 a million tokens), counted call by call by the
script; the cap was $0.25. The lookup experiments called no model.

**Replacements (the one edit).** The repository is public, so account identifiers were replaced
as plain strings wherever they occur, by `ingest/scrub_identifiers.py` with a list of pairs that
is not committed; nothing else was changed, and every file still parses. The digests of the files
as received are not committed either.

| Where | Replaced by |
|---|---|
| the home folder in `context.caller_filename` and in tracebacks (`error`) | `/Users/user` |
| the scratch virtualenv's path in tracebacks | `/venv` (a copy the service had cut short: `/tmp/capture`) |
| `user_id`, `span_attributes.created_by_user_id`, `audit_data[].metadata.user_id` | `00000000-0000-4000-8000-000000000001` |
| `span_attributes.created_by_api_key_id` | `00000000-0000-4000-8000-000000000002` |
| `repo_info.author_email`, `repo_info.author_name` | `dev@example.com`, `Example Author` |

Kept: experiment, project, dataset, span and event ids, and `repo_info`'s branch, commit and
commit message (this public repository's). **Checks made:** every file was scanned afterwards for
the originals, for email addresses, for the organisation's name and for any ten-character piece
of the four keys used: no hit.

**What a rebuild gives.** New ids, times, durations and cursors; the model's replies are
single words at temperature 0 and came out the same on each of the three platforms.

## Added for the Weave captures

Real captures from W&B Weave's service, made on 2026-11-09 against a free account, for the Weave
reader's tests. Tools: weave 0.54.1, openai 3.48.0, Python 3.12.13,
macOS. The UI's downloads are in `ingest/weave/ui/`: CSV, TSV, JSON
and JSONL, the four formats the Traces page offers. **It offers no Parquet.**

**The runs.** Project `trace-fixture`, four evaluations, one trace each:

| Evaluation | `Evaluation.evaluate` call id | Trace id | Started (UTC) | Script | Examples |
|---|---|---|---|---|---|
| `trace-fixture-old` | `01a1c1fe-e770-71bc-b51a-26161d46a267` | `01a1c1fe-e76e-7817-a336-454239eba743` | 20:27:50 | `fixture_weave.py` | 6 |
| `trace-fixture-new` | `01a1c1fe-e79c-7aa4-b7d8-221692d3ee20` | `01a1c1fe-e79c-74f0-94e4-85d34ca3a60b` | 20:27:50 | `fixture_weave.py` | 6 |
| `trace-fixture-slice-baseline` | `01a1c1ff-2284-7c7c-bb3a-8952efef33a7` | `01a1c1ff-2284-72e4-a62f-c0878cf8186f` | 20:28:05 | `slice_weave.py` | 10 |
| `trace-fixture-slice-candidate` | `01a1c1ff-2bbb-7221-a0b3-98fe793f6940` | `01a1c1ff-2bba-7cc7-a8b2-b104a623be0c` | 20:28:07 | `slice_weave.py` | 10 |

```
python fixture_weave.py
CAPTURE_LEDGER=<a file> CAPTURE_CAP_USD=0.25 python slice_weave.py
python slice_weave.py feedback 01a1c1ff-2284-7c7c-bb3a-8952efef33a7 01a1c1ff-2bbb-7221-a0b3-98fe793f6940
python pull.py <entity>/trace-fixture api
```

`fixture_weave.py` is the script as it was run; afterwards its one line
`import asyncio, weave` was split in two so that `ruff check tests` passes, and nothing else
differs. `trace-fixture-old` fails q2 and q3; **`trace-fixture-new` has no failing row.**
`slice_weave.py` is the same stock-desk agent as Braintrust's slice (the Braintrust section
describes it and its planted failures), as a `weave.Model` whose `predict` calls three ops and the
OpenAI client Weave patches, with two scorers (`exact`, `gave_answer`). The feedback (a thumbs-up
or thumbs-down reaction on each `predict_and_score` call of the slice, and a note on each case
that did not pass) was added by the script's `feedback` form in a second run: on the first run
the step listed the calls before they had reached the server and added none; the script now
flushes first.

**The files** (`ingest/weave/api/`; every one is the body of a
`POST https://trace.wandb.ai/calls/stream_query`, JSON Lines, sorted by `started_at`, with
`include_costs` and `include_feedback` true unless said; `requests.json` lists the 14 requests):

| Files | Request | Calls |
|---|---|---|
| `roots.jsonl` | `filter.trace_roots_only` | 4, one `Evaluation.evaluate` call an evaluation |
| `<evaluation>.jsonl` × 4 | `filter.trace_ids` | 20, 20, 78, 81 |
| `<evaluation>.expanded.jsonl` × 4 | the same with `expand_columns: ["inputs.example"]` | the same |
| `trace-fixture-slice-candidate.plain.jsonl` | the same with neither include flag | 81 |
| `trace-fixture-slice-candidate.page-1…4.jsonl` | the same with `limit` 40 and `offset` | 40, 40, 1, 0 (an empty body) |

**The UI downloads** (`ingest/weave/ui/`, eight files), downloaded by hand at 21:12 to 21:21 UTC
from the project's Traces page with its download control, and renamed by hand (every download
is named `weave_export_trace-fixture_2026-11-09.<format>`):

| Files | The page's view | Rows |
|---|---|---|
| `traces-roots.csv`, `.tsv`, `.json`, `.jsonl` | no filter: the root call of each trace | 4, the four `Evaluation.evaluate` calls |
| `predict-and-score.csv`, `.tsv`, `.json`, `.jsonl` | filtered to the op `Evaluation.predict_and_score` | 32: 6, 6, 10 and 10 |

The JSON is a list and the JSONL the same objects one a line; each object is a call as the API
gives it (`id`, `trace_id`, `parent_id`, `op_name`, `inputs`, `output`, `summary`, `attributes`,
…). The CSV and the TSV hold the same cells, one column a leaf, named by its dotted path
(`inputs.example.case`, `output.scores.exact.exact`, `summary.weave.status`), 47 columns in the
roots view and 65 in the other. **No format carries a cost or any feedback:** in the JSON
`summary.weave` has `status`, `latency_ms` and a name, and no `costs` or `feedback` key; the CSV
has `summary.weave.costs.*` and `summary.weave.feedback.*` columns, and every one of their cells
is empty. Token counts are there (`summary.usage.<model>`). **`inputs.example` is the row itself**
(with `_ref`), not a reference, so the case is in the file. `exception` is null on all 32 rows:
the three cases with a failure under them (baseline c08, candidate c04 and c09) show as
`summary.weave.status` `descendant_error`, the two errored ones with `output.output` null and
`output.scores` `{}`; the child calls that raised are not in this view. The replacements made
in these files are the entity and `wb_user_id`.

**What a reader finds.** Each call has `id`, `trace_id`, `parent_id`, `op_name` (a `weave:///`
reference), `display_name`, `started_at`, `ended_at`, `inputs`, `output`, `exception`,
`attributes`, `summary`. Status is `summary.weave.status`: `success`, `error` (the op raised;
`exception` then holds a JSON string with `type`, `message` and `traceback`) or
`descendant_error` (something under it raised). **Costs are at `summary.weave.costs.<model>`**
(not `summary.costs`), present only with `include_costs`, on the model call and summed on each
call above it, with `prompt_tokens_total_cost` and `completion_tokens_total_cost`;
`summary.usage.<model>` holds the token counts with or without the flag. The model's name is the
dated one, `gpt-4.1-mini-2025-04-14`. **Feedback is at `summary.weave.feedback`**, present only
with `include_feedback`: `wandb.runnable.<scorer>` entries on each `predict` call (the scorer's
output), and `wandb.reaction.1` and `wandb.note.1` on the slice's `predict_and_score` calls. The
verdict a reader needs is in `Evaluation.predict_and_score`'s `output` (`output`, `scores`,
`model_latency`); on an errored case `output.output` is null and `scores` is `{}`. **A
`predict_and_score` call's `inputs.example` is a reference to the dataset row, not the row**; the
`expanded` files carry the row inline (with `_ref`), and the case is also in the child
`predict` call's own inputs. The `attributes.weave.kind` of the model call is `llm`; the other
ops have no kind. There is no time-to-first-token field.

**Spend.** 19 calls to gpt-4.1-mini, 1,493 prompt and 75 completion tokens, **$0.000717**; the cap
was $0.25. The lookup evaluations and the feedback run called no model.

**Replacements (the one edit).** As for Braintrust, by `ingest/scrub_identifiers.py`:

| Where | Replaced by |
|---|---|
| the W&B entity in `project_id`, in every `weave:///` reference, and in `requests.json` | `example-entity` |
| `wb_user_id` (on calls and on feedback entries) | `VXNlcjow` |
| the home folder and the scratch virtualenv's path in `exception` tracebacks | `/Users/user`, `/venv` |

Kept: call and trace ids, object digests, and `attributes.weave`'s `os_version`, `sys_version`
and `client_version` (a machine's build strings, no account). The same scan found no hit.

## Added for the LangSmith captures

Real captures from LangSmith's service, made on 2026-11-09 against a free Developer account, for
the LangSmith reader's tests. Tools: langsmith 0.14.17 (Python SDK),
openai 3.48.0, Python 3.12.13, macOS, and the `langsmith` command built from the source of
langchain-ai/langsmith-cli at tag v0.3.13 (`go install …/cmd/langsmith@v0.3.13`; built this way it
reports its version as `dev`). The UI's CSV downloads are in
`ingest/langsmith/ui/`; **there is no JSON download from the UI: the experiment page offers CSV
only**.

**The runs.** Dataset `trace-fixture-stock-10` (id `d3ab7a03-3d76-4b85-9e30-cdb126f88222`, ten
examples, `metadata.case` c01 to c10) and two experiments on it:

| Experiment | Session id | Started (UTC) | Runs | Traces |
|---|---|---|---|---|
| `trace-fixture-baseline-bbb64b8e` | `7f82d36e-3c38-43c8-832b-f04be0072bfc` | 20:38:00 | 48 | 10 |
| `trace-fixture-candidate-7e3f7200` | `3886d3da-3e3b-4277-a0b2-d913d9109da4` | 20:38:19 | 51 | 10 |

```
CAPTURE_LEDGER=<a file> CAPTURE_CAP_USD=0.50 python fixture_langsmith.py
python pull.py api trace-fixture-baseline-bbb64b8e trace-fixture-candidate-7e3f7200
langsmith traces export cli/baseline-traces --project trace-fixture-baseline-bbb64b8e --full --limit 100
langsmith runs export cli/baseline-runs.jsonl --project trace-fixture-baseline-bbb64b8e --full --limit 1000
(the same two for candidate)
```

`fixture_langsmith.py` is the same stock-desk agent (the Braintrust section describes it and its
planted failures) run by `Client.evaluate`: each example is one trace, a `chain` root (`Target`)
over a `retriever` run, one or two `tool` runs, an `llm` run (`ChatOpenAI`, streamed, through
`wrap_openai`) and a `parser` run. Feedback on each root: `exact` (the evaluator, source `model`),
`judge_correct` (`create_feedback` with source `model`, a 0 or 1 from a second gpt-4.1-mini call;
not given to the errored root), `thumbs` (`create_feedback` with the default source `api`, 1 or 0,
a comment on a 0) and `review` (a categorical value, no score). The `thumbs` were made through the
API, so their source is `api`. **Two roots of the candidate also carry `human_thumbs`, feedback
made by hand in the UI, whose source is `app`:** 1 on c01 and 0 on c06, added at 22:07 UTC from
each run's own page with "Add feedback" (the UI would not offer the script-made `thumbs` key and
would not let a second key take its name, so the key is a new one). The baseline has none.
An earlier pair of experiments (`trace-fixture-baseline-52aca45a`, `trace-fixture-candidate-6b4f7f81`)
was run first without streaming, which left `first_token_time` null; it was run again streamed
and nothing here comes from the first pair. The pull and the exports were made at 20:45 UTC,
seven minutes after the runs. **After the two `human_thumbs` were added, the pull and the exports
were made again at 22:08 UTC and the thirteen candidate files they changed were replaced:** the
candidate's feedback list and its pages, its v2, v2 `subtree` and v1 run queries and their first
two pages, `cli/candidate-runs.jsonl`, and the two trace files of c01 and c06. In the run files
the only difference from the first pull is `feedback_stats` on those two roots. The baseline's
files, the third page of each paged pull and `requests.json` are the 20:45 pull's.

**The files.** `ingest/langsmith/api/` (response bodies; `requests.json` lists the 21 requests):

| Files | Request | What they hold |
|---|---|---|
| `dataset.json`, `examples.json` | `GET /api/v1/datasets?name=…`, `GET /api/v1/examples?dataset={id}` | the dataset and its ten examples: what `reference_example_id` points at |
| `<name>.session.json` × 2 | `GET /api/v1/sessions?name={experiment}` | the experiment: `reference_dataset_id`, `extra.metadata` |
| `<name>.runs-v2.json` × 2 | `POST /api/v2/runs/query`, `project_ids`, all 46 select fields, `page_size` 100 | `items` (48, 51), `next_cursor` |
| `<name>.runs-v2.subtree.json` × 2 | the same with `include_subtree_usage: true` | the same runs, tokens and cost summed onto each parent |
| `<name>.runs-v1.json` × 2 | `POST /api/v1/runs/query`, `session`, `limit` 100 | `runs` (48, 51), `cursors` |
| `<name>.feedback.json` × 2 | `GET /api/v1/feedback?session={id}&limit=100` | 39 feedback objects for the baseline, 41 for the candidate |
| `candidate.runs-v2.page-1…3.json`, `candidate.runs-v1.page-1…3.json`, `candidate.feedback.page-1…3.json` | the same three in pages of 25 | 25, 25, 1 runs twice; 25, 16, 0 feedback objects |

`ingest/langsmith/cli/`: `<name>-runs.jsonl` (one run a line: 48, 51) and `<name>-traces/` (one
`{trace_id}.jsonl` a trace, ten each, one run a line; **the command writes `.jsonl`, not
`.json`**).

`ingest/langsmith/ui/`: `trace-fixture-baseline-bbb64b8e.csv` and
`trace-fixture-candidate-7e3f7200.csv`, downloaded by hand at 21:07 and 21:09 UTC from each
experiment's page under the dataset, under the names the site gave them. Ten rows each, one an
example, with columns `id` (the example's id, which is the runs' `reference_example_id`),
`inputs`, `reference_outputs`, `session_name`, `repetition`, `outputs`, `run`, `status`, `error`,
`latency`, `tokens`, `total_cost`, and one column a feedback key (`exact`, `judge_correct`,
`review`, `thumbs`). `inputs`, `reference_outputs`, `outputs` and `run` are cells of JSON text;
`run` is the root run alone (`id`, `inputs`, `outputs`, `session_id`, `extra`, `run_type`,
`status`). **There are no child runs in this file**, so no step, no tool error and no span can
be read from it. A score column holds the average (`1.0`, `0.0`), `review` holds its value
(`ok`, `wrong_answer`, `abstained`, `errored`), and a root with no judge score has an empty
`judge_correct` cell; the source of a score is not in the file. The errored row has `status`
`error`, the exception's text in `error` and `{"output":null}` in `outputs`. The only
replacement made is the home folder in the candidate's traceback.

**What a reader finds.**
- *v2* (`items`): `status` is lower-case (`success`, `error`); there is `parent_run_ids` (empty on
  a root) and `is_root`, and no `parent_run_id`; a field with no value is left out of the row, so
  `error`, the token and cost fields and `feedback_stats` are present only on the runs that have
  them. Tokens and cost are on the `llm` run alone (`prompt_tokens`, `completion_tokens`,
  `total_tokens`, `prompt_cost`, `completion_cost`, `total_cost`, numbers); **a root carries them
  only in the `subtree` files**. `reference_example_id` and `feedback_stats` are on the roots.
  `first_token_time` is on each `llm` run.
- *v1* (`runs`): `parent_run_id` and `parent_run_ids` both; tokens, cost and `first_token_time` are already summed onto the root; `events` holds one
  `new_token` event on each `llm` run and nothing else (**no retry event exists**: the retried
  tool call is two sibling `tool` runs, the first in error).
- *the command's export*: `run_id` (not `id`), `parent_run_id` (null on a root), `duration_ms`,
  `token_usage`, `costs`, `custom_metadata`, `feedback_stats`; **no `reference_example_id` and no
  `dotted_order`**; the example's own metadata arrives as
  `custom_metadata.ls_example_case`, which is the only case identity in this shape.
- *feedback*: `feedback_stats` gives `n` and `avg` a key, and `values` for the categorical
  `review`; the feedback objects give `key`, `score`, `value`, `comment`, `run_id`, and
  `feedback_source.type` (`model` for `exact` and `judge_correct`, `api` for `thumbs` and
  `review`, `app` for the two `human_thumbs`; an `app` object has the same fields as the others,
  with `feedback_source.metadata` null). In `feedback_stats` the source is inside each key's
  `sources`, a list of JSON strings. **In the baseline, v2 and the command's export show `exact` in `feedback_stats` on 8
  of the 10 roots (not on c08 and c10), while v1 shows it on all 10 and `baseline.feedback.json`
  holds all 10 `exact` objects.** Three pulls over seven minutes gave the same; the candidate
  agrees everywhere. The feedback objects are the complete record. **The two arrived later:** a
  pull at 21:56 UTC, 78 minutes after the runs, showed `exact` on all 10 baseline roots in v2 and
  in the command's export. The baseline files were kept as first pulled, on purpose, so that a
  reader meets statistics that had not yet caught up with the feedback objects.
- An errored run has `error` (the exception's repr, then a traceback) on the failing step and on
  the root, and the root's `outputs` is `{"output": null}`.

**Spend.** 74 calls to gpt-4.1-mini, 4,318 prompt and 186 completion tokens, **$0.002025**; the
cap was $0.50. Of these, 37 calls ($0.001012) were the first, unstreamed pair and its judge, and
37 ($0.001013) the pair captured here: 19 agent calls and 18 judge calls.

**Replacements (the one edit).** As for Braintrust, by `ingest/scrub_identifiers.py`:

| Where | Replaced by |
|---|---|
| `tenant_id`, and the same id inside `app_path` and share URLs | `00000000-0000-4000-8000-000000000003` |
| `feedback_source.user_id`, and the same id inside `feedback_stats.*.sources` | `00000000-0000-4000-8000-000000000004` |
| `ls_user_id`, and the same id inside `feedback_stats.*.sources` | `00000000-0000-4000-8000-000000000005` |
| `extra.metadata.git.author_email`, `…author_name` in the session files | `dev@example.com`, `Example Author` |
| the home folder in tracebacks (`error`, `error_preview`) | `/Users/user` |

Kept: run, trace, session, dataset and example ids, and the session's git `remote_url`, branch
and commit (this public repository's). The same scan found no hit.

## Added for the steps and timings keys

`steps-timings/store/` is a Prove store of four small runs, written on 2026-11-23 by
`steps-timings/make.py` with poisson-prove 0.4.0 (from PyPI) under Python 3.12.13, for the tests
of `steps` and `timings` in `where` and `compare`. No model was called and nothing was fetched:
every trace is built by hand at fixed times, and the recipe writes it through Prove's own
`Store.create_run` and `Store.append`, the calls Trace's importer makes, so Prove checked each
trace and split it into its envelope and its content as it does for every run. The run ids, salts,
times and span ids are fixed in the recipe, so a second run writes the same files byte for byte
(checked: two runs, no difference).

```
python tests/fixtures/steps-timings/make.py tests/fixtures/steps-timings
```

The four runs, named `A`, `B`, `C` and `D`, are on three inputs (`alpha`, `beta`, `gamma`). The
recipe's opening says what each conversation holds: deaths, ends, a capped conversation and a
timeout; traces nested four deep, two roots, an orphan, a flat trace, parents with no end, a
parent id of 81 characters, a leaf id of 80, and two leaf ids that are written as digests (90
characters, and one holding a tab); leaves that start before their parent or their root, that run
in parallel, and that start in the same nanosecond; a row with no span and a row with no outcome that
did not time out. `C` repeats `A` under another salt.

Marked text is planted in span names, inputs, outputs and a tool-call-arguments attribute
(`PLANTED-NAME`, `PLANTED-PROMPT`, `PLANTED-OUTPUT`, `PLANTED-ARG`), so the tests can show that none
of it reaches Trace's JSON. Prove moves the inputs, outputs and the attribute out of the envelope;
the names stay in it, as they do in every store.

**The one edit, on purpose.** Run `D` holds three traces Prove refuses: two spans with one id, a
parent cycle, and spans whose end is before their start or is not a whole number. Prove's `append`
cannot store such a trace (it keeps it out of the trace columns), so the recipe writes `D` through
`Store` like the others and then rewrites those three rows' envelopes in the episodes file with
pyarrow, as a store written by hand could hold them. Every other value of those rows, and every
other row, is as Prove wrote it. Prove's reader hands such an envelope to Trace unchecked, which is
what the tests need: Trace's handling of a trace it cannot follow.
