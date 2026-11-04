# The two Prove stores TF16 and the pin read

Two stores written by Prove's own `sweep` on its keyless mock agent, with no key, no network and
no model: one by the published Prove that Trace pins, one by Prove under its old name, before it
was published. Nothing in either was written or edited by hand.

| store | written by | when | how to get that Prove |
|---|---|---|---|
| `prove-0.1.3/` | `poisson-prove` 0.1.3 (import `poisson_prove`), from PyPI: `poisson-prove==0.1.3` | 2026-11-04 | `pip install poisson-prove==0.1.3` |
| `prove-0.0.1/` | `proofload` 0.0.1, Prove's name before it was published as `poisson-prove` | 2026-10-28 | never on a package index; its wheel was `proofload-0.0.1-py3-none-any.whl` (sha256 `f2fde54ca8bc1ae6ccbfa9f8d057904b526c8a11722360fbb7587e2b6f40a76d`) |

`prove-0.1.3/` was made by `make.py` beside this file in a fresh Python 3.11.7 environment that
held only `poisson-prove==0.1.3` from PyPI and what it pulls in (numpy 2.4.6, pandas 3.1.1,
pyarrow 26.0.1, scipy 1.17.1, rich 15.0.0, textual 8.2.8, threadpoolctl 3.7.0 and their own
needs), with `HOME` a scratch folder. It replaces the store `poisson-prove` 0.1.3 wrote on
2026-11-03, by Taylor's ruling of 2026-11-04 moving the pin; each fixture store made with Prove is
made by the Prove Trace pins.

`prove-0.0.1/` is kept as Prove wrote it: it is the shape of a store from before Prove was
published (no `.poisson/`, no event logs, no names, the version under the old key), which TF16's
tests read beside the new one. No published Prove writes that shape, so it is not made again.

## The recipe

`make.py` beside this file is the whole recipe for `prove-0.1.3/`, and `sweep.toml` the spec it
reads (and the spec `prove-0.0.1/` was swept from): the mock agent over two tasks (`search`,
`refund`) and two tool failure rates (0.0, 0.55), 40 replicates each, 160 rollouts a run,
`t_unit = tool_calls`, target id `mock-agent`.

```
pip install poisson-prove==0.1.3
python make.py DEST
```

It refuses a Python whose `poisson_prove` is not 0.1.3 (`--python PYTHON` names another
interpreter), and runs, in order:

1. `python -m poisson_prove sweep sweep.toml --target poisson_prove.examples.mock_agent:rollout --salt 5eed000000000016 --name "agent before" --max-mde 0.5 --yes --store prove-0.1.3`
2. `python -m poisson_prove sweep sweep.toml --target poisson_prove.examples.mock_agent:rollout_patched --pair-with latest --name "agent after" --max-mde 0.5 --yes --store prove-0.1.3`
3. `python -m poisson_prove diff "agent before" "agent after" --event violated --save --store prove-0.1.3`

`prove-0.0.1/` was swept from the same spec with the same salt by `proofload` 0.0.1's own
`sweep` (`python -m proofload --store prove-0.0.1 sweep sweep.toml --target
proofload.examples.mock_agent:rollout --salt 5eed000000000016 --max-mde 0.5 --yes`, then the
patched agent with `--pair-with` the first run).

The salt is fixed and the mock agents are the same code under both package names, so the two
stores hold the same outcomes, row for row: the first run of each 66 `violated`, 6 `timeout` and
88 `completed` of 160; the second 21, 20 and 119. A second run of the recipe stores the same
outcomes; the run ids, the times and the files that carry them differ.

## What each store holds

- **`prove-0.1.3/`**: runs `20261104T162926Z-b4d5`, named `agent before` at sweep time, and
  `20261104T162928Z-1596`, named `agent after`, paired with it. As poisson-prove 0.1.3 writes a
  store: a `manifest.json` with `poisson_prove_version` 0.1.3 and `name`, an `events.jsonl`
  (`poisson.run-event/1`) beside it, traces under `poisson-prove.trace/1`; and `.poisson/` with
  the store descriptor `store.json` (`poisson.store/1`) and the saved comparison of step 3 under
  `artifacts/comparison/19197f1deb19b9e3/` (its descriptor, result, table and charts).
- **`prove-0.0.1/`**: runs `20261028T154158Z-c830` (the mock agent) and `20261028T154200Z-9ace`
  (the patched agent, paired with it). As 0.0.1 wrote a store: a `manifest.json` with the
  version under `proofload_version` and no `name`, the rows in three Parquet parts per run,
  traces under the schema `proofload.trace/1`; no `.poisson/` folder and no `events.jsonl`.

`SHA256SUMS` lists every file of the two stores (36), in the format `shasum -a 256` prints. Verify
with `cd tests/fixtures/prove-stores && shasum -a 256 -c SHA256SUMS`.
