# Fixture provenance

Four of Prove's stored runs, copied from this machine on 2026-09-28 with every observation
body removed, and three more added on 2026-09-29 for the fix check (the last section below).
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

`SHA256SUMS` beside this file lists the sha256 of every fixture file (782 files: the 429 of
the first four runs, their lines unchanged, 341 for the three added on 2026-09-29, two for the
DeepEval import, four for the Ragas import, two for the table import and four for the JUnit
import), in the format `shasum -a 256` prints. Verify with `cd tests/fixtures && shasum -a 256 -c SHA256SUMS`.

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
python tests/fixtures/build_fixtures.py DEST --runs RUNS_ROOT --cs CS_ROOT
```

The source stores are not public, so the script is the record of how the fixtures were made;
with the sources and pyarrow 25.0.1 it reproduces the 770 committed files byte for byte. It is
not listed in `SHA256SUMS`, which covers the fixture stores only.

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
are 46 MB per tau2 run; nothing Trace reads is in them. What each fixture cannot express is
in the spec's section 9: the tau2 pair has one kind, no nesting, no timeout, no cap reached,
no errored row and no declaration; the cs pair has nesting and two kinds but no timeout, no
cap and no declaration. Timed-out, capped, unreadable, no-leaf and declared-step paths run
on the synthetic store the tests build through `Store.create_run` / `Store.append`
(`tests/conftest.py`, `synth_rows`).

## One edit beyond the nulling

The cs replay fixture's three `error` values are Python tracebacks recorded by the replay
harness, and the originals name the home directory of the machine that recorded them. In
the copy, the prefix `/Users/<user>/` in those three strings reads `~/` (ruled 2026-09-28);
the rest of each traceback, and every other value in every column, is the original. The
digests in `SHA256SUMS` are of the copy as committed.

## Added for the fix check (2026-09-29)

Three more of Prove's stored runs, copied on 2026-09-29 under rulings 9 and 10 of that day,
after a scan of every byte that is committed (below). The recipe is `build_fixtures.py`
beside this file.

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
  the T.4 guardrail pilot, on `tau2-airline/gpt-4.1-mini-2025-04-14@v0` on Modal, tasks 0 to 9
  with one replicate each (declared `replicates` 1), stored with no capture, so it holds no
  trace. Outcomes stored: `solved`, `unsolved`. Its config `{"task_id": …}` hashes as the tau2
  pair's does, so the three runs share their cells. The spec's worked fix check reads it as the
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

## Added for the DeepEval import (2026-09-29)

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

## Added for the Ragas import (2026-09-30)

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
public; their manifests' sha256 are
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

## Added for the table import (2026-10-13)

Two tables of this machine's HumanEval outcomes, one per run of the HumanEval pair above, written
as CSV, for the `poisson-trace import table` tests. They are not Prove stores. The recipe is
`make.py` beside them, in `ingest/table/`.

| Fixture | Made from | Rows | Cases | Columns | failed_assertion / crashed / passed | Size |
|---|---|---|---|---|---|---|
| `ingest/table/humaneval-a.csv` | `humaneval/20260905T185407Z-0313` | 10,496 | 328 | `case`, `task_id`, `temperature`, `replicate`, `outcome` | 1,330 / 8 / 9,158 | 478,807 B |
| `ingest/table/humaneval-b.csv` | `humaneval/20260905T195009Z-18ac` | 10,496 | 328 | the same five | 1,376 / 11 / 9,109 | 479,270 B |

**How.** Each stored row of the run, read through `proofload.store.Store` (Prove 0.0.1, under
its name before it was published; read again through `poisson_prove.store.Store` of
`poisson-prove==0.1.2` from PyPI on 2026-11-03, the recipe writes the same two files byte for
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
(`tests/test_tf3_fixtures.py`).

**What each cannot express.** One outcome column of words, no score, no empty cell, no other
format than CSV. Every other shape (JSON Lines, JSON, Parquet, gzip, scores at a cut, empty
cells, true and false, refusals) is built in the tests (`tests/test_tf3_table.py`).

## Added for the JUnit import (2026-10-13)

Four JUnit XML reports written by pytest 9.1.1 (Python 3.11.7), two pairs, for the
`poisson-trace import junit` tests. They are not Prove stores. The recipe is `make.py` beside
them, in `ingest/junit/`, with the suite `replay_humaneval.py` and the plugin `fixture_host.py`.

| Fixture | The suite | Test cases | Passed / failed / errors / skipped | Suite timestamp | Size |
|---|---|---|---|---|---|
| `ingest/junit/trace-suite-1.xml` | three of Trace's own test files at `a1abc6c` | 91 | 90 / 0 / 0 / 1 | `2026-10-13T00:01:11.564615-04:00` | 14,727 B |
| `ingest/junit/trace-suite-2.xml` | the same, run again | 91 | 90 / 0 / 0 / 1 | `2026-10-13T00:01:23.261977-04:00` | 14,727 B |
| `ingest/junit/humaneval-a.xml` | `replay_humaneval.py` on `humaneval/20260905T185407Z-0313` | 656 | 569 / 86 / 1 / 0 | `2026-10-13T00:20:34.510483-04:00` | 92,702 B |
| `ingest/junit/humaneval-b.xml` | `replay_humaneval.py` on `humaneval/20260905T195009Z-18ac` | 656 | 573 / 83 / 0 / 0 | `2026-10-13T00:20:35.677086-04:00` | 91,387 B |

**Trace's own tests, run twice.** `tests/test_tf1_names.py`, `tests/ingest/test_cut.py` and
`tests/ingest/test_rows.py` of Trace's `main` at `a1abc6c`, run from a `git archive` of that
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
problem (`tests/test_tf3_fixtures.py`).

**What each cannot express.** Trace's own tests fail nothing, so `--event missed` names no
outcome on that pair, and each test runs once. The replay pair has one error (in the first run
only), no skip and no test case without a class name. Suites nested in suites, a lone
`<testsuite>` root, a timestamp with no zone, a test case with no name, and every refusal are
built in the tests (`tests/test_tf3_junit.py`).

## Added for the promptfoo import (2026-11-04)

Three files promptfoo 0.120.19 (npm, Node v22.14.0) wrote in one evaluation on 2026-10-07, for the
`poisson-trace import promptfoo` tests. They are not Prove stores. They were made by the front-door
spec's session (vault `log/trace-front-door-spec/tool-exports/promptfoo/`, its `provenance.md`)
and copied here byte for byte. The config is `promptfooconfig.yaml` beside them.

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
(`tests/test_tf10_promptfoo.py`).

## Added for the Inspect import (2026-11-04)

Two logs inspect_ai 0.3.277 (Python 3.11) wrote on 2026-10-07, for the `poisson-trace import
inspect` tests, copied byte for byte from the front-door spec's session (vault
`log/trace-front-door-spec/tool-exports/inspect/`). The task is `fixture_task.py` and the run
`run_fixture.py`, beside them, with `INSPECT_DISABLE_TELEMETRY=1`; `run_fixture.py` is the vault's
with its one unused import (`sys`) removed, so the repository's lint passes on it.

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
in the tests from these files with one field changed (`tests/test_tf10_inspect.py`).

## Added for the OpenAI Evals import (2026-11-04)

Two records evals 3.0.1.post1 (`oaieval`, Python 3.11) wrote on 2026-10-07, for the `poisson-trace
import openai-evals` tests, from the front-door spec's session (vault
`log/trace-front-door-spec/tool-exports/openai-evals/`).

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
`087171f6390b76e0612402f30f88b73a15f15ddcd9bd789fdb4d1ddf60f93af2` (new), and are kept in the vault.

**Checks made.** After the edit, every string was scanned for key-like material, home-directory
paths, the machine owner's name and email addresses: no hit.

**What it cannot express.** No passing sample, no repeat of a sample, no `sampling` or `metrics`
event, no empty answer. Those and every refusal are built in the tests from these files with one
line added or changed (`tests/test_tf10_openai_evals.py`).

## Added for the setup agent (2026-11-04)

`setup-agent/setup-file-format-1.txt` is the shared text of the Poisson setup file, format 1
(the rules, the check, the prompt and the hand-over opening), byte for byte as the shared page
writes it on 2026-10-23, with the placeholders a tool fills; the same text Prove's copy of
2026-10-24 carries. `tests/test_tf17_skill.py` checks the skill `poisson-trace init --agent`
writes against it.

`setup-agent/sample-repo/` is a small repository written by hand for the scripted run of
`tests/test_tf17_scripted.py`: a stand-in support agent that calls no model (`agent/`, naming the
failure outcomes), a scoring module naming the cut a Ragas row must reach (`evals/score_rag.py`),
the agent's own tests (`tests/agent_checks.py`), a `pyproject.toml` naming the tools, and a
README saying which results are old and which new. The store and the result files are not
copied in: each test builds its copy of the repository by copying the `cs` store to `store/`,
`ingest/ragas/rag-base.jsonl` and `rag-raft.jsonl` to `evals/results/`, and
`ingest/junit/humaneval-a.xml` and `humaneval-b.xml` to `reports/junit-old.xml` and
`reports/junit-new.xml`. `setup-agent/expected/trace.toml` is the config a correct agent writes
for it. No key, no model and no network were used.
