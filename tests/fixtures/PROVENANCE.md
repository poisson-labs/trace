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

`SHA256SUMS` beside this file lists the sha256 of every fixture file (770 files: the 429 of
the first four runs, their lines unchanged, and 341 for the three added on 2026-09-29), in the
format `shasum -a 256` prints. Verify with `cd tests/fixtures && shasum -a 256 -c SHA256SUMS`.

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
