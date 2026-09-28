# Fixture provenance

Four of Prove's stored runs, copied from this machine on 2026-09-28 with every observation
body removed. Each fixture directory is a Prove store root: `tau2/` holds the two
tau2-airline runs and `cs/` the two cs_agents runs, so `Store(root).runs()` lists them and
`compare` can take both runs of a pair from one `--store`.

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

`SHA256SUMS` beside this file lists the sha256 of every fixture file (429 files), in the
format `shasum -a 256` prints; its own sha256 is `63d0e0c1c83101836b89025fa2541dac5c0dd846a440c735139a0be30a644ed5`.
Verify with `cd tests/fixtures && shasum -a 256 -c SHA256SUMS`.

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

## The nulling recipe

For each source run: `manifest.json` copied byte for byte; each `episodes/part-*.parquet`
read with pyarrow, its `trace_obs` column replaced by an all-null string column of the same
length, and written back under the same name. Nothing else in any column changed: the
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

## Known content

The cs replay fixture's three `error` values are Python tracebacks recorded by the replay
harness. They name the file paths of the machine that recorded them. They are kept as the
originals were stored.
