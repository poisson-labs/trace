# A page to send

You have a result from Trace and someone to show it to who does not have Trace. This recipe
writes the result as a folder of files, a bundle, and makes one HTML page from it that opens
from disk in any browser. You end with a single file you can attach to a message.

The example is the store under `tests/fixtures/cs` in a clone of the repository: two
recordings of a customer-service agent demo. Run the commands from the clone's root.

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

## 2. Write the result as a bundle

`--out DIR` on `where`, `compare`, `fix-check` or `changes` writes what the command printed,
and the numbers behind it, into a new folder:

<!-- command -->
```
cd my-agent && poisson-trace where latest --out verdict
```

<!-- excerpt exit=0 -->
```
ok  7 of 21 tries failed; their last steps: 4 at a model call and 3 at an agent step (not necessarily the cause)
  wrote  verdict
```

The report prints as it always does, and the second line says where the bundle went. A folder
that is there already is refused unless you give `--force`.

## 3. Make the page

<!-- command -->
```
cd my-agent && poisson-trace report verdict
```

<!-- output exit=0 -->
```
ok  the where verdict in verdict as one page that opens from disk with nothing else present
  wrote  verdict/report.html
next: poisson-trace handover --check verdict
```

`report.html` now sits in the bundle beside the other files:

<!-- command -->
```
ls my-agent/verdict
```

<!-- output exit=0 -->
```
artifact.json
charts
handover.json
report.html
report.md
result.json
table.parquet
```

The page holds the verdict line, the summary, every table of the report and the curve, drawn
in the page itself. It has no script and loads nothing from the network, so it reads the same
on a machine with no connection. Send that one file.

`poisson-trace report verdict --open` opens the page in your browser. With `--open`, a page
that is there already is opened as it is and not written again.

[Into the product](into-the-product.md) says what the bundle's other files hold.

## What this does not do

- It does not upload or send anything. The page is a file on your disk until you send it.
- It does not put prompts, answers or keys on the page: a bundle holds none.
- It does not make a page from a folder Trace did not write, or from a bundle a file of which
  was changed afterwards. `report` checks the bundle first and refuses one that fails.
