# Into the product

You want a result from Trace inside something of your own: a dashboard, a release gate, a
record you keep beside each release. This recipe writes a result as a bundle, shows what the
bundle holds, and checks it the way your code should before it reads it. You end with a
folder of files whose shape Trace promises to keep.

The example is the store under `tests/fixtures/cs` in a clone of the repository. Run the
commands from the clone's root.

## 1. Set up

<!-- command -->
```
mkdir -p my-agent && cp -R tests/fixtures/cs my-agent/prove-runs
cd my-agent && poisson-trace init --yes
```

<!-- excerpt exit=0 -->
```
ok  wrote trace.toml: store prove-runs (2 runs), failures app_error, forbidden_action, unresolved, max_turns
```

## 2. Write a bundle

`--out DIR` on `where`, `compare`, `fix-check` or `changes` writes the result into a new
folder:

<!-- command -->
```
cd my-agent && poisson-trace where latest --out bundle
```

<!-- excerpt exit=0 -->
```
ok  7 of 21 tries failed; their last steps: 4 at a model call and 3 at an agent step (not necessarily the cause)
  wrote  bundle
```

## 3. What the bundle holds

<!-- command -->
```
cd my-agent && ls bundle bundle/charts
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

- `result.json` is the result as data: the verdict, its sentence, the runs it read, every
  number of the report, and what the report cannot say. It is what `--json` prints.
- `report.md` is the report as text, as the command printed it.
- `table.parquet` holds the report's main table, one row for each of its rows.
- `charts/curve.svg` is the curve as a picture and `charts/curve.json` the points behind it.
  A `where` and a `compare` bundle have charts; a `fix-check` and a `changes` bundle do not.
- `artifact.json` says what made the bundle: the command, its settings and where each came
  from.
- `handover.json` lists every file with its size and its SHA-256 digest, and names the
  versions of Trace and Prove that wrote it.

## 4. Check it before you read it

<!-- command -->
```
cd my-agent && poisson-trace handover --check bundle
```

<!-- output exit=0 -->
```
ok  bundle holds what it promises: a where verdict over one run, 6 files of the digests and sizes listed, result.json with every key of the table, and nothing Trace does not hand over

next: poisson-trace report bundle
```

The check reads `handover.json` and holds every file to the digest listed for it. It exits 0
when the bundle is whole and exits 4 when it is not, so a script can stop on it. Change one file and
it says which:

<!-- command -->
```
cd my-agent && echo edited >> bundle/report.md && poisson-trace handover --check bundle
```

<!-- output exit=4 -->
```
not valid  report.md does not have the digest handover.json lists for it
```

[The handover page](../handover.md) lists every file and every key Trace promises, and what
is never in a bundle. [A page to send](a-page-to-send.md) turns a bundle into one HTML page.

## What this does not do

- It does not send the bundle anywhere. Your code reads the folder from disk.
- It does not hold a prompt, an answer, a key or an absolute path of your machine.
- It does not promise every key of `result.json`: the handover page lists the ones it does.
