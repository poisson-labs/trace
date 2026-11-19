# Set up Trace with your coding agent

You have results already: the runs Poisson Prove recorded of your agent, or the files your
evaluation tools wrote. Setting Trace up means telling it where those results are, which
outcomes count as a failure, which files to import and what each is, and which results come
from before a change and which from after. `poisson-trace init` asks you those questions.
`poisson-trace init --agent` hands them to your own coding agent instead: it writes a skill
and a prompt into your repository, your agent reads the repository and writes `trace.toml`,
runs Trace's check until it passes, and stops for you to review. Trace makes no model call
and reads no key; your agent does the work, with the model and the key it already has.

## What `init --agent` writes

Four files, in the two folders coding agents read skills from, and nothing else:

| folder | read by | files |
|---|---|---|
| `.agents/skills/` | Codex, Cursor | `poisson-trace-setup/SKILL.md`, `poisson-trace-setup/prompt.txt` |
| `.claude/skills/` | Claude Code, Cursor | the same two files, byte for byte |

`SKILL.md` is the setup file in the Poisson setup-file format (version 1): an Agent Skills
skill with the steps, the rules and the check. `prompt.txt` holds the one line you give your
agent. Trace never writes `AGENTS.md`, `CLAUDE.md`, a rules file or anything else you own; a
file of the four that is there already is refused unless you give `--force`, which replaces
those four alone. `--repo DIR` writes into another folder; `--print` prints the skill and
writes nothing.

Here it is in a small repository made from the example files of a clone of Trace's repository:
a Prove store, two Ragas score tables and two JUnit reports.

<!-- command -->
```
mkdir -p my-repo/evals/results my-repo/reports
cp -R tests/fixtures/cs my-repo/store
cp tests/fixtures/ingest/ragas/rag-base.jsonl tests/fixtures/ingest/ragas/rag-raft.jsonl my-repo/evals/results/
cp tests/fixtures/ingest/junit/humaneval-a.xml my-repo/reports/junit-old.xml
cp tests/fixtures/ingest/junit/humaneval-b.xml my-repo/reports/junit-new.xml
cd my-repo && poisson-trace init --agent
```

<!-- output exit=0 -->
```
ok  wrote the setup for your coding agent (4 files)
  wrote  .agents/skills/poisson-trace-setup/SKILL.md
  wrote  .agents/skills/poisson-trace-setup/prompt.txt
  wrote  .claude/skills/poisson-trace-setup/SKILL.md
  wrote  .claude/skills/poisson-trace-setup/prompt.txt
  prompt  Use the poisson-trace-setup skill in this repository: set Poisson Trace up for me to review, then stop.
  next: give your coding agent the prompt above, then review what it wrote
```

## The prompt

Give your agent this line, in the repository the files were written into:

```text
Use the poisson-trace-setup skill in this repository: set Poisson Trace up for me to review, then stop.
```

## What the agent does

The skill tells the agent to read and run nothing, in seven steps: find the results on disk
(Prove stores, and every file a reader in the install reads: DeepEval's saved test runs, Ragas
tables, tables of results, JUnit reports, promptfoo results, Inspect logs, OpenAI Evals records,
and LangSmith, Braintrust and Weave exports; the readers are `deepeval`, `ragas`, `table`,
`junit`, `promptfoo`, `inspect`, `openai-evals`, `langsmith`, `braintrust` and `weave`); work out which tool wrote each from the repository's dependencies and the
tools' own configuration; find the outcomes that count as a failure, and for a scored file the
metric and the cut, in the code that scores (the agent never chooses a cut: a file whose cut
the code does not name is left out, and the hand-over says so); work out which results are old
and which new; write `trace.toml` with `[store]`, `[events]`, one `[[import]]` table per file
and `[names]`, and nothing else; run the check; stop and hand over.

The rules it follows: it runs no `poisson-trace` command but the check and `--help`, passes
no `--yes`, reads no key and no `.env` file, installs nothing, writes into no store, and never
runs your evaluations, tests or agent to make results.

## The check

The agent runs `poisson-trace doctor --setup` until it passes, at most three fixes. It reads
what `doctor` reads and each `[[import]]` file not imported yet, with its reader, and writes
nothing.

No agent runs on this page, so the `trace.toml` an agent would write for the small repository
is copied in from the example files. This is the file:

<!-- command -->
```
cp tests/fixtures/setup-agent/expected/trace.toml my-repo/trace.toml
cat my-repo/trace.toml
```

<!-- excerpt exit=0 -->
```
[store]
path = "store"

[events]
failed = ["forbidden_action", "unresolved", "max_turns", "app_error"]

[[import]]
file = "evals/results/rag-base.jsonl"
tool = "ragas"
name = "rag-base"
metric = "faithfulness"
cut = 0.5
below = true
case_column = "case"
```

And the check on it:

<!-- command -->
```
cd my-repo && poisson-trace doctor --setup
```

Ready is exit 0. The first line is the verdict:

<!-- excerpt exit=0 -->
```
ok  trace.toml is ready for the person to review
```

Under it come two lines that name your Python and where the package is installed, and then
one line for each thing checked, with one line per pending file:

<!-- excerpt exit=0 varies -->
```
  prove     poisson-prove … (Trace reads version 0.4.0 or later)
  config    trace.toml: store store (2 runs, 2 complete, 0 partial), failures forbidden_action, unresolved, max_turns, app_error
  names     store: no names of yours yet
  readers   deepeval, ragas, table, junit, promptfoo, inspect, openai-evals, langsmith, braintrust, weave
  import    evals/results/rag-base.jsonl: ragas, 150 rows, faithfulness at 0.5, not imported yet
  import    evals/results/rag-raft.jsonl: ragas, 150 rows, faithfulness at 0.5, not imported yet
  import    reports/junit-old.xml: junit, 656 rows, not imported yet
  import    reports/junit-new.xml: junit, 656 rows, not imported yet
next: poisson-trace init
```

Not ready is exit 1, with `error:` naming the first failing check and a `next:` line for
each; a setting wrong under `trace.toml`'s rules (an unknown key, a tool not in the install,
a name used twice, a required option missing) is exit 2 with the line it is on.

## The hand-over, and what you do next

The agent stops and tells you what it wrote, the check's last output, and what you must
confirm: the stores and files it found and those it left out, the failure outcomes and where
in the code each came from, the metric and cut per scored file, and which run is old and
which new. Then you run `poisson-trace init` yourself, on a terminal. Here the question is
answered `y`:

<!-- command tty answers="y" -->
```
cd my-repo && poisson-trace init
```

It shows what the config names, on stderr, and asks:

<!-- excerpt exit=0 -->
```
  store store: 2 runs
  failures: forbidden_action, unresolved, max_turns, app_error
  files to import:
    evals/results/rag-base.jsonl  as the run rag-base (ragas)
    evals/results/rag-raft.jsonl  as the run rag-raft (ragas)
    reports/junit-old.xml  as the run tests-old (junit)
    reports/junit-new.xml  as the run tests-new (junit)
```

and on a yes it imports them and says what it did, on stdout:

<!-- excerpt exit=0 -->
```
ok  imported 4 runs into trace-store, failures forbidden_action, unresolved, max_turns, app_error; [store.imported] added to trace.toml
  prove    poisson-prove is installed at a version Trace reads
  import   poisson-trace import ragas evals/results/rag-base.jsonl --store trace-store --run rag-base --metric faithfulness --cut 0.5 --below --case-column case
  import   poisson-trace import ragas evals/results/rag-raft.jsonl --store trace-store --run rag-raft --metric faithfulness --cut 0.5 --below --case-column case
  import   poisson-trace import junit reports/junit-old.xml --store trace-store --run tests-old --case name
  import   poisson-trace import junit reports/junit-new.xml --store trace-store --run tests-new --case name
  the same setup, without questions:
    poisson-trace init --yes --import
next: poisson-trace doctor
```

On a `trace.toml` with `[[import]]` files not imported yet, `init` shows the stores, the
failures and the files, and asks `Import these 4 files as the runs named here? [y/N]`. On a
yes it imports them into `trace-store` beside `trace.toml` (or the store the config names for
them), writes `trace.toml` once more keeping every line the agent wrote and adding the store's
table, and ends with `next: poisson-trace doctor`; `doctor` then reads ready, and its next
command is the first fix-check on the first pair of one tool's runs. `--yes` or `--import`
answers yes without the question; `--no-import` leaves the files pending.

## `[[import]]`

One table per file to import, with the reader's options by their flags' names without the
dashes:

```toml
[[import]]
file = "evals/results/rag-base.jsonl"   # relative to trace.toml, inside the repository
tool = "ragas"                          # a reader in the install
name = "rag-base"                       # the run's name
metric = "faithfulness"                 # the reader's own options, by their flag names
cut = 0.5
below = true
case_column = "case"
```

Every command that reads `trace.toml` checks the keys, the types and the choices; only
`doctor --setup` and `init` open the files. A `[signals]` table's `case_field`,
`outcome_field`, `score_field` and `cut` stand in for an entry's `case_column`,
`outcome_column`, `metric` or `score_column`, and `cut` where the entry leaves them out, as
they do for `poisson-trace import`'s flags.

## What it does not do

It does not call a model, read a key or contact a host. It does not run your evaluations or
your tests. It does not choose a cut. It does not import anything: the import is yours, after
the review.
