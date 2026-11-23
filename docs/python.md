# The Python API

`poisson_trace.api` is the one core every face of Poisson Trace calls: its command line, and
your own code. One function per verb, taking what the verb's command line takes: the store
first (a path, a name the config names, a `Store` from `open_store`, or None for the config's
own store or for runs given as folders), the verb's positionals, then every option of the verb
as a keyword named for its flag with the dashes as underscores and the same default (`--max-mde
0.2` is `max_mde=0.2`; a repeatable `--event` is `event=[...]`). A keyword passed is a flag
given, whatever its value.

Each function returns a dataclass, read-only, whose attributes are the keys of the verb's `--json`,
and, on the four verbs that count failures, what a save writes beside them: `summary` and
`before_you_act` (the report's lines), `note`, `versions`, `settings`, and on a verb of two
runs `failure_taxonomy_diff` and `continuous_measures`. On every result:

- `to_json()` is the `--json` output byte for byte, and `to_markdown()` the plain output;
- `exit_code` is the command's, and `notes` the sentences it prints as `note:` lines;
- on `where`, `compare`, `fix_check` and `changes`: `to_bundle(folder, force=False)` is
  `--out DIR`, `api.save(result)` is `--save`, and on `where` `to_svg()` is the curve as SVG
  text and `write_svg(path, force=False)` is `--svg FILE`; each delivery returns the result as
  the command prints it with that option, so they chain;
- on the same four: `to_html()` is the HTML report, the text `poisson-trace report DIR` writes
  for the bundle `to_bundle` writes, whether or not the result was saved; nothing is written.

Every refusal is `api.Refusal`, carrying `message` (the sentence the command prints after
`error:`), `next` (the commands under it), `exit_code` (1 for a refusal; exit code 2 for a setting the
verb needs that nothing gives; exit code 3 for a failure after work started) and `notes`. A value the flag itself would
refuse (a wrong type, a choice it lacks, a flag the verb or the reader does not take) is a
`ValueError`, raised before anything is read.

A store written in a newer format than this Trace reads is refused before anything in it is
read, with the message
`the store at store holds poisson.store/2, a newer format than this Trace reads (poisson.store/1)`.
An installed Prove that lacks something Trace imports from it is refused by every function
that reads through Prove, with exit code 1, no `next` and the message
`Poisson Trace reads stored runs through Prove (the poisson-prove package, version 0.4.0 or later) and found poisson-prove 0.9.0, which has no poisson_prove.store.RunTally`;
on the command line, `poisson-trace doctor`'s Prove check fails on it and exits 4.
A store whose `.poisson/store.json` is not a store descriptor is refused by every function that
opens the store, and by `api.save` and a result's `to_bundle`, which write nothing, with exit
code 1, no `next` and the message
`store/.poisson/store.json is not a store descriptor (not a JSON object); nothing was written`,
or `(JSONDecodeError)` in the brackets for a file that is not JSON.

The API prints nothing, reads no environment variable, reads no file and lists no folder it was
not given a path to, and writes only in `import_run`, `name`, `forget_name`, `save`,
`to_bundle`, `write_svg` and `build_pages`, each only where it is pointed. It does not look for a `trace.toml`:
load one with `load_config` and pass it as `config`.

Poisson's products reach Trace through its command line, not through this API. The API is for
users and for Trace's own command line.

The examples below run from inside a folder holding: `store`, a copy of the Prove store the
tests use (the runs `agent before` and `agent after`); `tables`, two table imports named `old`
and `new`; `jstore`, two JUnit imports; `grades.csv`, verdicts for two unscored cases; `files/`,
one result file of each reader's (`humaneval-a.xml` among them); and `conf/trace.toml`, a config
naming `store` and `tables`, the failures `violated` and `timeout`, and both ceilings. Each
prints exactly what is shown under it.

## api.open_store

```python
api.open_store(path)
```

A store Prove wrote, opened by its path. Every verb takes the `Store` in place of the path; a name given through it is seen through it.

**Refusals.** `api.Refusal` when no folder under the path holds a run Prove stored (a path that is not there, an empty folder and a plain file alike). `ValueError` when the path is not text.

```python
from poisson_trace import api

store = api.open_store("store")
print(store.path)
```

```text
store
```

## api.load_config

```python
api.load_config(path)
```

A config file (`trace.toml`), read and checked. `cfg.store()` is the path of the store its `[store]` names, `cfg.store("tables")` the path of the store named `[store.tables]`. Every verb takes the `Config` as its `config`; with `config=None` the API reads no config at all, so pass it in.

**Refusals.** `api.Refusal` when the file is not there, is a folder, is not UTF-8 text, is not TOML, or is not a version 1 config, each naming the file and, where it can, the line. `ValueError` when the path is not text.

```python
from poisson_trace import api

cfg = api.load_config("conf/trace.toml")
print(cfg.store())
print(cfg.store("tables"))
```

```text
store
tables
```

## api.where

```python
api.where(store, run, *, event=None, config=None, by='kind', at=(), timings=False, timings_of=(), boot=1000, seed=0, **reader_flags)
```

`poisson-trace where`: where in the workflow the episodes of one stored run died. `WhereResult` holds the JSON's keys (`run`, `curve`, `median_step`, `at`, `causes`, `bootstrap`, `steps`, `timings`, `note`, `next`) and the report's `summary` and `before_you_act`; `to_svg()` is the curve as SVG text and `write_svg(path, force=False)` writes it, as `--svg` does. `steps` is always there. `timings` is `None` unless the call asks for it: `timings=True` for every try of the run, as `--timings` does, or `timings_of=[(config_hash, replicate_index), ...]` for the tries named, as `--timings-of` does ([the handover page](handover.md#steps-and-timings)).

**Refusals.** `api.Refusal` for an unknown run, an unknown event, a store that is not there, a names file that is not one, a bootstrap of none, a negative seed, a `timings_of` pair that is no try of the run; with exit code 2 when neither the call nor the config gives a store or the failures. `ValueError` for a value the flag would refuse: a `by` that is neither `kind` nor `step`, a `boot` or an `at` step that is not a whole number, an `event` that is not a list, a `timings_of` item that is not a `(config_hash, replicate_index)` pair, a reader's flag for runs read from a store.

```python
from poisson_trace import api

r = api.where("store", "agent after", event=["violated", "timeout"], at=[3])
print(r.verdict, r.sentence)
print(r.median_step, [point["step"] for point in r.at])
print(r.next)
```

```text
ok 41 of 160 tries failed; each one's last step was a tool call (not necessarily the cause)
18 [3]
poisson-trace compare "agent before" "agent after" --store store --event violated --event timeout
```

## api.compare

```python
api.compare(store, a, b, *, event=None, config=None, by='kind', at=(), timings=False, timings_of=(), max_mde_hr=None, alpha=0.05, verdicts=None, **reader_flags)
```

`poisson-trace compare`: a before (A) and an after (B), compared by the log-rank test stratified by config cell. `CompareResult` holds `comparison`, `per_cause`, `at`, `steps`, `timings` and the rest of the JSON, with `failure_taxonomy_diff` and `continuous_measures` as a save writes them. `steps` holds a list for each run under `a` and `b`. `timings` is `None` unless asked for with `timings=True` or `timings_of=[...]`, as on `api.where`; the pairs named apply to both runs.

**Refusals.** `api.Refusal` for a run with no traces (fix-check reads it), no death in either run, no common config cell, an alpha outside 0 to 1, a `timings_of` pair that is a try of neither run; with exit code 2 when nothing gives a store or the failures. `max_mde_hr` has no default: left out, with none in the config, it is refused. `ValueError` for a value the flag would refuse (an `alpha` given as text).

```python
from poisson_trace import api

r = api.compare("store", "agent before", "agent after", event=["violated", "timeout"], max_mde_hr=1.5)
print(r.verdict)
print(r.comparison["verdict"], r.comparison["cells"])
```

```text
different
different 4
```

## api.fix_check

```python
api.fix_check(store, old, new, *, event=None, config=None, alpha=0.05, top=10, failing_from=None, min_failures=None, inputs=None, max_mde=None, seed=0, measures=False, max_change=(), verdicts=None, **reader_flags)
```

`poisson-trace fix-check`: an old and a new version re-run on the same inputs, compared input by input. `FixCheckResult` holds `inputs`, `rows`, `test`, `difference`, `limits`, `changes` and the rest of the JSON; `measures=True` adds the time, length, tokens and cost section, as `--measures` does.

**Refusals.** `api.Refusal` when neither `inputs="all"` nor `failing_from` is given, when `max_mde` is neither given nor in the config, for a ceiling outside 0 to 1, for OLD and NEW that are one run, for a selecting run that is also an arm, for no input left to compare; with exit code 2 when nothing gives a store or the failures. `ValueError` for a value the flag would refuse (a `max_mde` given as text, a `max_change` that is not a list of `(measure, share)` pairs).

```python
from poisson_trace import api

r = api.fix_check("store", "agent before", "agent after", event=["violated", "timeout"], inputs="all", max_mde=0.2)
print(r.verdict)
print(r.inputs["compared"], r.rows["old"]["failed"], r.rows["new"]["failed"])
```

```text
different
4 72 41
```

## api.changes

```python
api.changes(store, a, b, *, event=None, config=None, alpha=0.05, top=10, verdicts=None, **reader_flags)
```

`poisson-trace changes`: the inputs whose failure share moved between two runs, each with Fisher's exact test and a Benjamini-Hochberg correction. `ChangesResult` holds `rows`, `tested`, `flagged` and the rest of the JSON.

**Refusals.** `api.Refusal` for A and B that are one run, no input with an outcome in both runs, an unknown event; with exit code 2 when nothing gives a store or the failures. `ValueError` for a value the flag would refuse (a `top` that is not a whole number).

```python
from poisson_trace import api

r = api.changes("tables", "old", "new", event=["missed"])
print(r.verdict, r.tested, r.flagged)
print(r.sentence)
```

```text
ok 12 0
0 of 12 inputs stand out; on this design, no single input could on its own
```

## api.runs

```python
api.runs(store, *, event=None, config=None, all=False)
```

`poisson-trace runs`: the runs of a store, newest first, with their names and numbers. `RunsResult.runs` is the listing's rows; `notes` holds what the command prints as `note:` lines (no failures given, a run Prove could not read).

**Refusals.** `api.Refusal` for a store that is not there, an unknown event; with exit code 2 when nothing gives a store. `ValueError` when `all` is not True or False.

```python
from poisson_trace import api

r = api.runs("store", event=["violated", "timeout"])
print(r.to_markdown())
```

```text
ok  2 runs in store (newest first); 2 named by you, 0 named from their manifests

  #  name          rows  failed  traces  started           status
  1  agent after    160      41  yes     2026-11-04 16:29  complete
  2  agent before   160      72  yes     2026-11-04 16:29  complete

next: poisson-trace where "agent after" --store store --event violated --event timeout

```

## api.name

```python
api.name(store, run, new, *, config=None)
```

`poisson-trace name RUN NEW`: give a stored run a name of yours, kept in `trace-names.toml` at the store's root.

**Refusals.** `api.Refusal` for a name that cannot be one (too long, a reserved word such as `latest`, the id of a run), a name another run answers to already, a run Prove could not read.

```python
from poisson_trace import api

r = api.name("store", "agent after", "shipped")
print(r.to_markdown())
```

```text
ok  named 20261104T162928Z-1596 "shipped" in store/trace-names.toml

next: poisson-trace runs --store store

```

## api.forget_name

```python
api.forget_name(store, run, *, config=None)
```

`poisson-trace name RUN --forget`: take back the name of yours that the run has.

**Refusals.** `api.Refusal` for a run that has no name of yours.

```python
from poisson_trace import api

api.name("store", "agent after", "shipped")
r = api.forget_name("store", "shipped")
print(r.to_markdown())
```

```text
ok  forgot the name "shipped" of 20261104T162928Z-1596, which is named "agent after" again, in store/trace-names.toml

next: poisson-trace runs --store store

```

## api.list_names

```python
api.list_names(store, *, config=None)
```

`poisson-trace name --list`: the names of yours in the store.

**Refusals.** `api.Refusal` for a store that is not there, a names file that is not one.

```python
from poisson_trace import api

api.name("store", "agent after", "shipped")
r = api.list_names("store")
print(r.to_markdown())
```

```text
ok  1 name of yours in store/trace-names.toml

  name     name from its manifest  run
  shipped  agent after             20261104T162928Z-1596

next: poisson-trace runs --store store

```

## api.import_run

```python
api.import_run(store, tool, files, *, config=None, run=None, started=None, verdicts=None, **reader_flags)
```

`poisson-trace import TOOL FILE [FILE ...]`: the files read with the tool's reader (`deepeval`, `ragas`, `table`, `junit`, `promptfoo`, `inspect`, `openai-evals`, `langsmith`, `braintrust` or `weave`), written as one new run of the store. Each reader's flags are keywords named by the same rule (`case_column="case"` for `--case-column case`). `tool` may be None when `files` is one folder, whose files say which tool wrote them. `ImportResult` holds the summary's keys (`run`, `store`, `tool`, `files`, `declared`, `started`, `rows`, `cases`, `outcomes`).

**Refusals.** `api.Refusal` for a file that is not there, a run name the store holds already or that cannot be a folder's name, a metric no case carries, a start with no zone, a tool this install lacks; with exit code 2 when `run` is not given for files, when a reader's required flag is left out, or when nothing gives a store. `ValueError` for a flag the reader lacks, a flag of the wrong type, or a choice it lacks.

```python
from poisson_trace import api

r = api.import_run("new-store", "junit", ["files/humaneval-a.xml"], run="suite-a", started="2026-11-01T10:00:00Z")
print(r.verdict, r.sentence)
print(r.rows, r.cases, r.outcomes)
```

```text
ok wrote run suite-a to new-store: 656 rows, 656 cases, 1 repeat each; 569 passed, 87 failed
656 656 {'met': 569, 'missed': 87}
```

## api.save

```python
api.save(result)
```

`--save`: the verdict saved as an artifact in the runs' store, under `.poisson/artifacts`. The result it returns is of the same type, with `saved` set and the `saved` line the command prints; a store that cannot be written to is a note on `notes`, and the result goes on with `saved` None.

**Refusals.** `api.Refusal` as the verb's own; `ValueError` when given anything but the result of `where`, `compare`, `fix_check` or `changes`. `api.Refusal` also, with exit code 1 and nothing written, when the store's `.poisson/store.json` is not a store descriptor: `store/.poisson/store.json is not a store descriptor (not a JSON object); nothing was written`, or `(JSONDecodeError)` in the brackets for a file that is not JSON.

```python
from poisson_trace import api

r = api.save(api.where("store", "agent after", event=["violated", "timeout"]))
print(r.saved)
print(r.to_markdown().splitlines()[1])
```

```text
.poisson/artifacts/where/13c7d6008e73d824
  saved  where 13c7d6008e73
```

## api.load_bundle

```python
api.load_bundle(folder)
```

A handover bundle that `to_bundle` (or `--out`) wrote, read back: `verb`, `result` (`result.json`), `handover` (`handover.json`), `artifact` (`artifact.json`) and `report` (`report.md`).

**Refusals.** `api.Refusal` when the folder is not there, is not a folder, holds no `handover.json`, or does not hold what it promises (the first failing line, as `validate_bundle` finds it).

```python
from poisson_trace import api

r = api.fix_check("store", "agent before", "agent after", event=["violated", "timeout"], inputs="all", max_mde=0.2)
r.to_bundle("bundle")
b = api.load_bundle("bundle")
print(b.verb, b.result["verdict"], sorted(b.handover))
```

```text
fix-check different ['files', 'runs', 'schema', 'verb', 'versions', 'written_at']
```

## api.validate_bundle

```python
api.validate_bundle(folder)
```

`poisson-trace handover --check DIR`: whether a bundle holds what it promises. `BundleCheck.verdict` is `ok` (exit code 0) or `not valid` with the first failing line as its sentence (exit code 4).

On `ok`, `BundleCheck.next` is the HTML report's command: `poisson-trace report DIR`, which
writes `report.html` into the bundle, or, once the bundle holds it, `poisson-trace report DIR
--open`, which opens that page as it is and writes nothing. Without `--open` a `report.html`
that is there is refused unless `--force` replaces it; when the page is not the one `report`
would write now (from another version of Trace, or edited and re-listed), `--open` still opens
it and a `note:` names the command that writes it again.

**Refusals.** `api.Refusal` when the folder is not there, is not a folder, or holds no `handover.json`.

```python
from poisson_trace import api

r = api.where("store", "agent after", event=["violated", "timeout"])
r.to_bundle("bundle")
check = api.validate_bundle("bundle")
print(check.verdict, check.exit_code)
```

```text
ok 0
```

## api.build_pages

```python
api.build_pages(store, *, config=None)
```

`poisson-trace ui`: Trace's pages over the store's runs and saved verdicts, built into its
`.poisson/ui/trace/` and opened from disk: the runs and the saved verdicts (`index.html`), one
page per saved verdict with every line of its report, and one page per verdict for what it
cannot say. With `config`, every other store the config names gets its pages too, and they
link one another. Prove's own dashboard beside them is never touched; every command that saves
a verdict rebuilds the pages as well. `PagesResult.location` is the index's `file:` address,
and `to_markdown()` is the one line `ui` prints.

**Refusals.** `api.Refusal` for a store that cannot be read, as `api.runs` refuses it (with
exit code 2 when nothing gives a store), and for pages that cannot be written.

```python
from poisson_trace import api

r = api.build_pages("store")
print(r.verdict, r.location.endswith("/store/.poisson/ui/trace/index.html"))
```

```text
ok True
```

## What the JSON promises

`to_json()` is the document `--json` prints, and `to_bundle` writes the `result.json` that
`--out` writes, so both keep the promise those make. Within one schema number no public key is
renamed or removed, and keys are only added. A public key is any key that does not start with
an underscore; one that does is internal and may change in any release. The whole promise is
on [the handover page](handover.md#what-resultjson-promises).
