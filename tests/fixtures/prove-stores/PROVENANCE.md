# The two Prove stores TF16 reads

Two stores written by Prove's own `sweep` on its keyless mock agent, on 2026-10-28, with no key,
no network and no model: one by the Prove Trace pinned before TF16, one by Prove's main. Nothing
in either was written or edited by hand.

| store | written by | Prove commit | wheel built from it (sha256) |
|---|---|---|---|
| `prove-0.0.1/` | `proofload` 0.0.1 | `98dc6af0e8b66f733c98d3867035e21bba5c219d` (2026-09-28) | `proofload-0.0.1-py3-none-any.whl` (`f2fde54ca8bc1ae6ccbfa9f8d057904b526c8a11722360fbb7587e2b6f40a76d`) |
| `prove-main/` | `poisson-prove` 0.0.1 (import `poisson_prove`) | `fa31d791d87f0582b7642511cb4e263e49515765` (2026-10-28) | `poisson_prove-0.0.1-py3-none-any.whl` (`7b3505742d98411c2eadbe56adce4fb5e5d1a3bf74ad7a0b62f2d73573246ff0`) |

Each wheel was built with `uv build --wheel` from a checkout of that commit and installed into its
own Python 3.11.15 environment (pyarrow 26.0.0, pandas 3.1.0, numpy 2.4.6), with `HOME` a scratch
folder.

## The recipe

`make.py` beside this file is the whole recipe, and `sweep.toml` the spec both sweeps read: the
mock agent over two tasks (`search`, `refund`) and two tool failure rates (0.0, 0.55), 40
replicates each, 160 rollouts a run, `t_unit = tool_calls`, target id `mock-agent`.

```
python make.py DEST --old PYTHON_WITH_PROOFLOAD_0.0.1 --new PYTHON_WITH_POISSON_PROVE
```

It runs, in order:

1. `python -m proofload --store prove-0.0.1 sweep sweep.toml --target proofload.examples.mock_agent:rollout --salt 5eed000000000016 --max-mde 0.5 --yes`
2. `python -m proofload --store prove-0.0.1 sweep sweep.toml --target proofload.examples.mock_agent:rollout_patched --pair-with <run 1> --max-mde 0.5 --yes`
3. `python -m poisson_prove sweep sweep.toml --target poisson_prove.examples.mock_agent:rollout --salt 5eed000000000016 --name "agent before" --max-mde 0.5 --yes --store prove-main`
4. `python -m poisson_prove sweep sweep.toml --target poisson_prove.examples.mock_agent:rollout_patched --pair-with latest --name "agent after" --max-mde 0.5 --yes --store prove-main`
5. `python -m poisson_prove diff "agent before" "agent after" --event violated --save --store prove-main`

The salt is fixed and the two mock agents are the same code under two package names, so the two
stores hold the same outcomes, row for row: the first run of each 66 `violated`, 6 `timeout` and
88 `completed` of 160; the second 21, 20 and 119. A second run of the recipe stores the same
outcomes; the run ids, the times and the files that carry them differ.

## What each store holds

- **`prove-0.0.1/`**: runs `20261028T154158Z-c830` (the mock agent) and `20261028T154200Z-9ace`
  (the patched agent, paired with it). As 0.0.1 writes a store: a `manifest.json` with the
  version under `proofload_version` and no `name`, the rows in three Parquet parts per run,
  traces under the schema `proofload.trace/1`; no `.poisson/` folder and no `events.jsonl`.
- **`prove-main/`**: runs `20261028T154201Z-888d`, named `agent before` at sweep time, and
  `20261028T154203Z-0132`, named `agent after`, paired with it. As Prove's main writes a store: a
  `manifest.json` with `poisson_prove_version` and `name`, an `events.jsonl`
  (`poisson.run-event/1`) beside it, traces under `poisson-prove.trace/1`; and `.poisson/` with
  the store descriptor `store.json` (`poisson.store/1`) and the saved comparison of step 5 under
  `artifacts/comparison/057bd21b07d412f9/` (its descriptor, result, table and charts).

`SHA256SUMS` lists every file of the two stores (36), in the format `shasum -a 256` prints. Verify
with `cd tests/fixtures/prove-stores && shasum -a 256 -c SHA256SUMS`.
