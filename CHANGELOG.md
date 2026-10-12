# Changelog

## Unreleased

### Guided setup, the config file and doctor

A first-time user types `poisson-trace init`, answers in plain words, and every verb then
knows where their results are and what counts as a failure.

- **`poisson-trace init`** finds the results in the current folder's tree: the stores Prove
  wrote, then DeepEval's saved test runs and tables that look like Ragas scored them. It
  searches breadth first and in name order, six folders down, reading at most 10,000 entries
  and saying so when it stops short; it skips `.git`, `.venv`, `venv`, `node_modules`,
  `__pycache__`, `.work`, `site-packages` and every dot folder but `.deepeval`, follows no
  link, and never searches the home folder or a folder above it. It lists what it found on
  stderr: each store with its runs, its targets and its newest day.
- It asks which store when there are several (`[1]`, the first listed, by default), offers
  to import the result files when there is no store (the import's own questions, each file
  one run named after it, in `trace-store` beside the config), and asks which outcomes count
  as a failure over the newest 20 runs, showing as its default every outcome that is not a
  word for success (`poisson_trace.setup.SUCCESS_WORDS`).
- It writes `trace.toml` once, after the last answer; Ctrl-C at any question writes nothing.
  It prints the same setup as one command that asks nothing, which writes the same file in a
  copy of the folder, and `next: poisson-trace runs`. Every question has a flag, and `--yes`
  asks nothing; stdin that is not a terminal is refused without it. `--names from=FORM`
  writes the names form, and `--max-mde`, `--max-mde-hr` and `--fail-on` write `[check]`,
  only when given. A config there already is refused without `--force`, but for one with a
  store and no failures, which `init` completes. `--add-store PATH` adds a store to a config,
  named by its folder (or as the store every verb reads, when the config names none), keeping
  every line, and says when its runs carry none of the config's failures. `init` never writes
  `trace.toml` into a store or a run's folder, and does not import when both tools' files are
  found. Without Prove, `init` refuses before it searches.
  `--json` prints `poisson-trace.init/1`.
- **`trace.toml`** is read by every verb and by `poisson-trace-import`, from the current
  folder or `--config PATH`, never from a folder above: the store and named stores (a path
  read from the file's folder), the failures, `[check]` (`fix-check` and `compare` take their
  ceiling from it when no flag gives one), `[names] from` and `[upload]`. A flag replaces what
  it gives; `--store NAME` is the store it names so before a folder of that name; what
  neither gives is a mistake in the command line, as before. A file that is not a version 1
  config is refused by every verb, naming the file and the line, with the setting meant when
  one is within two edits.
- **Two more forms of a run's name**, set by `[names] from`: `date` (`2026-09-15 a`, the
  letters running across the day's runs) and `target-date` (`tau2-airline gpt-4.1-mini
  2026-09-15 a`, the model taken from the target id after its first `/`, up to an `@`,
  without a date stamp at its end). Names of yours and imports' names stay what they are.
- **`poisson-trace doctor`** checks six things, one line each: the Python, the package and
  where it was imported from (a note when that is outside the interpreter's environment),
  Prove, the config and the stores it names, the names of yours, and the readers in the
  install. A failing line ends with the command that mends it, where one does;
  not ready exits 4. It fixes
  nothing. `--json` prints `poisson-trace.doctor/1`.
- **The readers say which files they read**: `looks_like(path)` on the DeepEval and Ragas
  readers gives the one line a listing shows, or nothing, and never raises.
- **A next command leaves out what the config gave** and carries what you typed: `--store`,
  each `--event`, and `--config`.
- The line that installs Prove is now said once, on the `  next:` line under the refusal,
  and no longer inside the sentence too. An unknown option before the verb gives its error on
  one line and the command's help on the next.
- An interrupted import still names the partial run and the folder to remove.

### Names and runs

Every stored run now has a name a person can read and type, and no command asks for a run's
id.

- **Every run has a name.** A run with no name of yours is named from its manifest: its
  target up to the first `/`, the day it started in UTC and a letter in start order among
  that target's runs that day (`tau2-airline 2026-09-15 a`, `… b`, past `z` `aa`, `ab`). A run
  written by `poisson-trace-import` is named by the name it was imported under. These names
  are worked out from the store each time, never stored, so they are the same on every
  machine that holds the same store.
- **`poisson-trace name RUN NAME`** gives a run a name of yours, kept in `trace-names.toml`
  at the store's root; no run's own files change, and deleting the file loses nothing but
  the names. `name RUN --forget` takes it back; `name --list` shows each name of yours with
  the name its run has from its manifest. A name is at most 80 characters of text on one
  line, with no control character but the tab, and cannot be a name another run answers to, a run's id, `latest`, `previous`, or begin
  `latest:`, `previous:`, `#` or a dash.
- **Every verb takes a run by any of its words**: a name of yours, a name from the
  manifest, `latest` and `previous` (the newest complete runs), `latest:TARGET` and
  `previous:TARGET`, `#N` (row N of `poisson-trace runs`) or the full id. A word that reaches
  no run is refused with the store's runs listed by name; a word that reaches two runs is
  refused, never guessed; a part of an id is not taken.
- **`poisson-trace runs`** lists a store's runs, newest first: number, name, rows, how many
  failed for the `--event` names given, whether any row carries a trace, when it started
  (UTC) and its status. Partial runs and runs past the newest 50 are listed with `--all`.
  `--json` prints `poisson-trace.runs/1`.
- **The result comes first.** Every verb's first line is its verdict line (`ok`,
  *different*, *no significant difference* or *too small to tell*, then the sentence), then
  a blank line and the report, which keeps its bold line; every verb ends with a `next:`
  line, the command to run next, naming runs by name and carrying the `--store` and
  `--event` given. `where` and `changes` gain a verdict, `ok`.
- **Reports name runs by name**: the title by name, each run's line by name with its id
  once (`tau2-airline 2026-09-15 a (20260915T210140Z-4847)`), the selecting run of a fix
  check by name, the SVG by name. The JSON opens with `schema`, `verdict` and `sentence`,
  ends with `next`, and carries `run_name` right after each `run_id`; no key is removed.
- **A refusal's command goes on its own line**, `  next:`, where there is one to give: the
  store's listing under a run it does not hold, the verb's help under a mistake in the
  command line, the forget command under a name for a run the store no longer holds, the
  install line when Prove is missing.
- The import refuses, before Prove is asked anything and with nothing written, a run name
  that is not a folder name (empty, `.`, `..`, a slash, a backslash, over 80 characters), and
  a name no command could give back: `latest`, `previous`, `latest:…`, `previous:…`, `#…`, a
  space at either end, two lines, a first dash, the names file's own name, or a name another
  run of the store answers to. Its summary opens with its verdict line.
- A run Prove cannot read, or whose start it cannot read, is left out of the names and the
  listing with a note, and stops nothing else; the rows of one run that cannot be read leave
  the listing of the others whole. A names file entry that cannot be a name, or a second name
  for one run, is refused by every verb with the command that takes it back.
- Ctrl-C under `--json` prints one JSON document, verdict `stopped`.
- The README and the two integration pages name runs by name and are re-run; the figures
  under `docs/figures/` carry the run's name.

### The command-line look

Both commands, `poisson-trace` and `poisson-trace-import`, now keep the command-line look
written down in `docs/cli-look.md`, which every Poisson Labs tool follows.

- **The exit codes changed.** 0: the result is printed, whatever it says, so *too small to
  tell* now exits 0 where it exited 2. 1: refused, with nothing written, as before; a value
  the command checks itself (`--max-mde 1.5`, `--inputs some`, `--boot 0`) is refused this way.
  2: the command line is wrong (no verb, an unknown verb or option, a flag missing, a value
  outside an option's listed choices or not a number where one is asked, a word too many),
  where it exited 1. 3: a failure after work started, or an unexpected one. 130: interrupted. A script that waited for exit 2 on *too small to
  tell* reads the verdict from `--json` instead.
- Every refusal and every mistake in the command line is one line on stderr that starts
  `error:`, with nothing on stdout, under `--json` too, and the command to run instead on a
  `  next:` line under it where there is one. No refusal carries a library's own
  error text or a value printed the way Python prints it; a value is in double quotes or
  bare.
- `--help` and `--version` work without Prove: Prove is checked once the command line is
  read, and a command that needs it, without it or at another version, names the install
  command `pip install git+https://github.com/poisson-labs/prove` and the version it found.
- `--version` prints one line: `poisson-trace 0.1.0 (poisson-prove 0.0.1, Python 3.11.7)`,
  with Prove's version as installed, or `poisson-prove not installed`.
- `python -m poisson_trace` is the same command as `poisson-trace`.
- `--seed` below 0 is refused, and `--boot` above 1,000,000; a store that cannot be read, a
  name too long for the system and a `--started` outside the years 1 to 9999 are refused in
  one line, where each ended in a traceback.
- Every help gives a description, every option with its default or "no default", and an
  example. `--max-mde` and `--max-mde-hr` show as required in the usage line; a missing one
  is still refused in one line, exit 1.
- Options may come before or after the verb, and before or after the import's tool. An
  option cut short (`--ev` for `--event`) is refused in `poisson-trace` as it already was in
  `poisson-trace-import`.
- A store that is not there, an empty folder or a plain file given as `--store` is refused
  as *no store at PATH*, instead of as an unknown run.
- `where --svg FILE` refuses, before any work, a folder that is not there or cannot be
  written, a path that is a folder, and a file (or a link) that is already there unless
  `--force` is given; `--force` without `--svg` is refused. When it writes, the line under the verdict line is `  wrote  FILE`; with `--json`
  stdout stays one document. The SVG is written as UTF-8 whatever the locale.
- An unexpected failure prints one line naming its type and
  `~/.cache/poisson-trace/errors.log`, where the details are added to what the log holds;
  `--debug`, before or after the verb, prints them on stderr too.
- Ctrl-C prints `stopped  interrupted; nothing was written` and exits 130. An import stopped
  while it writes leaves its run marked partial and says so, naming the run and the store
  whose folder to remove before importing it again; a run of that name is still refused
  until then.
- A stdout that cannot encode the report's glyphs (`·`, `–`, `α`, `χ²`, `κ`) gets the same
  report spelt in ASCII, line for line; the JSON is the same bytes on any stdout. A reader
  that goes away (`| head`) ends the command quietly.
- Every count of 1,000 or more prints with thousands separators (`rows 10,496`), in every
  report, the import's summary, refusals and the SVG, the bootstrap's `B = 1,000` included;
  the JSON keeps plain numbers. The two figures under `docs/figures/` are re-drawn for it.
- The README and the two integration pages give the install line above, and their example
  outputs are re-run.

## 0.1.0 — 2026-10-01

First release, three parts. The first two read Prove's stored runs; the third writes a
store in Prove's format from the result files of another tool.

Where runs die: `where` and `compare` over leaf-span index; Kaplan–Meier with Greenwood;
Aalen–Johansen by kind with a bootstrap band; stratified log-rank with the minimum
detectable hazard ratio.

Whether a change made runs fail less: `fix-check` and `changes` over the outcome alone; the
exact conditional Cochran–Mantel–Haenszel test stratified by input, with the old version
re-run as the control; the Mantel–Haenszel difference with Sato's interval; per-input flags
with Benjamini–Hochberg; and, wherever the line is *too small to tell*, how many repeats or
inputs would settle it.

Results from other tools: `poisson-trace-import` reads the files a tool already wrote and
writes one new run per version, for `fix-check` and `changes` to compare. The readers are
DeepEval's and Ragas's.

- `poisson-trace where RUN --store ROOT --event NAME`: the survival curve over step index
  with a plain Greenwood 95% band, the median step, the cumulative incidence by kind of
  step (or by step name with `--by step`) with a seeded bootstrap band, the header counts
  (Prove's tally and Trace's placement: died, ended, timed out, capped, excluded by reason),
  the declared-steps table when the run declared, and the block of what the curve cannot
  say. `--json` prints `poisson-trace.where/1`; `--svg FILE` writes the curve.
- `poisson-trace compare A B --store ROOT --event NAME --max-mde-hr X`: the two-sample
  log-rank stratified by config cell over the common cells, unpaired; the direction; the
  per-step difference with a Wald interval (`--at`); the cause-specific log-rank per kind
  with Benjamini–Hochberg; Schoenfeld's minimum detectable hazard ratio at 80% power; and
  one of three lines, *different*, *no significant difference* or *too small to tell*
  (exit 2). `--json` prints `poisson-trace.compare/1`.
- Reads a Prove store only through Prove's public API (`Store`, `RunTally`,
  `declaration_check`, `KINDS`); writes nothing but the requested SVG; refuses in one
  sentence when `proofload` 0.0.1 is not importable.
- Four fixtures: two tau2-airline runs and two cs_agents runs stored by Prove, observation
  bodies removed, with provenance and checksums.
- `poisson-trace fix-check OLD NEW --store ROOT --event NAME (--failing-from RUN
  [--min-failures M] | --inputs all) --max-mde X`: the old version re-run on the same inputs
  beside the new (the control); the exact conditional Cochran–Mantel–Haenszel test
  stratified by input, two-sided, which is Fisher's exact test on one input and the exact
  McNemar test on one run per arm; the Mantel–Haenszel risk difference in points with
  Sato's large-sample interval; a by-input sign-flip reading, exact up to 14 moved inputs
  and 100,000 seeded draws beyond (`--seed`), printed beside the test with no part in the
  line; failure share, the chance a failure repeats, κ, and within-input against pooled
  variance; the smallest proportional drop and rise in failure share detectable at 80%
  power; and one of three lines, *different* (failed less, or failed more), *no significant
  difference* or *too small to tell* (exit 2). `--json` prints `poisson-trace.fix-check/1`.
- The selecting run is refused as an arm: `--failing-from` must name neither OLD nor NEW.
  Which inputs are compared has no default, and `--max-mde` has none.
- `poisson-trace changes A B --store ROOT --event NAME`: Fisher's exact test per input,
  Benjamini–Hochberg across the inputs compared, the inputs flagged as *failed more in B* or
  *failed less in B*, each row with Prove's per-cell limit, and what the design could not
  have flagged (the smallest p an input can give against α / M, how many inputs would have
  to flip together, the repeats a lone complete flip needs). The numbers are Prove's `diff`
  with `fisher_bh`. `--json` prints `poisson-trace.changes/1`; `--top N` bounds the
  markdown table. The same table closes every `fix-check` report.
- Guidance under every *too small to tell*. `fix-check` prints the repeats per arm on these
  inputs, the inputs like these at the present repeats, and the `--max-mde` that accepts the
  design as it stands, computed with the function that stated the limit. `compare` prints
  the deaths needed, the placed runs, inputs and repeats that many deaths take, and the
  `--max-mde-hr` that accepts the design; its JSON gains `comparison.guidance`. `compare`
  also closes with one line naming `fix-check`.
- Neither new verb reads a trace, a seed or a replicate index: repeat runs of one input are
  separate draws, never replays, and a run stored with no capture is read like any other.
- No output of any verb uses *fixed*, *validated* or *confirmed*, beside the first slice's
  list. A run that did not fail is written *did not fail*.
- Three more fixtures: the patched tau2 pilot, copied whole, and two HumanEval runs,
  outcome-only, with provenance and checksums.
- `poisson-trace-import TOOL FILE [FILE ...] --store ROOT --run NAME [--started ISO-8601]
  [--json]`: one import is one version, written as one new run through Prove's public API
  (`Store`, `RunManifest`, `EpisodeRecord`, `from_otel`). A run name the store holds is
  refused; nothing is added to a run. A score becomes the outcome `met` or `missed` at a cut
  the user declares with its side, and a score equal to the cut met it. Rows that share a
  case are repeats of it, in the order read. No prompt, answer or reason text is written,
  but for the value of the column a user names as the case to the Ragas reader (below), and
  span attributes that Prove lists as content are dropped before a span is stored. The
  summary prints the files with their digests, the rules as declared, the start time and
  where it came from, the counts, and the Trace command to run next; `--json` prints
  `poisson-trace.import/1`. A refusal is one sentence, exit 1, with nothing written.
- `poisson-trace-import deepeval … --metric NAME --cut (recorded | X (--below | --above))
  --case (name | input | position)`: reads DeepEval's saved test runs as DeepEval 4.2.6
  writes them (`docs/integrations/deepeval.md`), one metric per import. `--cut recorded`
  takes DeepEval's own decision for that metric; `--case input` is a digest of the input,
  never its text; a metric that raised is a row with no outcome. Nothing imports DeepEval.
- `fix-check` prints a p below 1e-300 as the bound `p < 1e-300`, in the comparison line and
  in the line that states the result. With one run per input per version its consistency
  block says consistency cannot be measured and prints no κ; in `--json`,
  `consistency.fails_again` and `consistency.kappa` are then `null`.
- Two more fixtures: the HumanEval pair as two result files written by DeepEval 4.2.6, with
  the recipe beside them, provenance and checksums.
- `poisson-trace-import ragas … --metric COLUMN --cut X (--below | --above) --case-column
  COLUMN`: reads the score table a team saves from Ragas's `to_pandas()`, or an
  `@experiment` file, as CSV, JSON Lines, JSON or Parquet, told by the file's extension,
  with `.gz` read on the first three (`docs/integrations/ragas.md`); one score column per
  import. A cell that is empty, `NaN`, `null` or not a number is a row with no outcome,
  never a zero. Rows that share a case value are repeats of that case. Only the two named
  columns are kept: the score, and the case as written when it is at most 80 printable
  characters and as a digest otherwise. A named column the file lacks is refused with the
  file's columns listed, and a JSON Lines file with a line that is not an object is refused
  whole, as is a `.gz` that cannot be read. Nothing imports Ragas; tested on tables written
  by Ragas 0.4.3.
- Four more fixtures: two pairs of Ragas score tables, one from a stored memory-retrieval
  experiment scored by Ragas 0.4.3 and one a published base and fine-tuned pair reduced to
  question hashes and scores, with the recipe beside them, provenance and checksums.
- `fix-check` prints no κ where fewer than half the compared inputs were run more than once
  on a version, an input counting when either version holds two or more of its runs with an
  outcome: its consistency block then prints the failure share and says how many of the
  compared inputs repeat. In `--json`, `consistency.fails_again` and `consistency.kappa` are
  `null` and the other figures stay as computed. One run per input per version keeps its own
  sentence, and a design where at least half the inputs repeat prints as before.
- A DeepEval file that begins as gzip and cannot be read, because its stream cannot be
  inflated, its checksum does not match or it is cut short, is refused in one line that
  names the file: *FILE is a gzip file that cannot be read: it is damaged or cut short*.
  Nothing is written, and no text of the library reaches the line.
