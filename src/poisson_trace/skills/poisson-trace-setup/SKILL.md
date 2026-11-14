---
name: poisson-trace-setup
description: Set up Poisson Trace in this repository so the person can check whether a change made their agent fail less, from results they already have. Use when asked to set up Trace or poisson-trace.
metadata:
  poisson-setup-format: "1"
  poisson-tool: poisson-trace
  poisson-tool-version: "filled in when the skill is written"
  poisson-writes: trace.toml
  poisson-check: poisson-trace doctor --setup
---

# Set up Trace in this repository

## What you are doing

Poisson Trace reads results the team already has, the runs Poisson Prove recorded of their agent and the result files their other tools wrote, and says whether a change made the agent fail less, with its limits of detection stated. You write one file, `trace.toml`, that tells Trace where those results are, which outcomes count as a failure, which result files to import and what each is, and which results come from before the change and which from after. You run Trace's check, which reads what you wrote and spends nothing, and you hand the result over for the person to review; the person runs the import themselves, never you.

## Rules

- Do only what these steps say. Change nothing outside the files listed under "Files you write".
- Run nothing that can spend money or call a model. The only poisson-trace commands you run are the ones
  these steps show, and the check runs with its own flag that spends nothing.
- Never pass --yes, or any flag that answers a question for the person.
- Never read, print, copy or write an API key, a token or a .env file, and never ask the person for one.
- Install nothing. If poisson-trace is not installed where this repository runs, stop and tell the person
  the install command from https://pypi.org/project/poisson-trace/.
- When something is unclear, choose the smaller change and say in the hand-over what you chose and why.
- Quote Trace's output as it prints it. Never reword a verdict, a number or an error.
- If you cannot finish, stop and say what blocked you.

### Trace's own rules

- Run no `poisson-trace` command but `poisson-trace doctor --setup` and the `--help` of a command.
- Never write into a store (a folder of runs Prove recorded, `trace-store` included) or into `.poisson/`.
- Never run the person's evaluations, tests or agent to make results. Trace runs nothing and captures nothing; it reads what is already on disk.
- Open a result file only as far as its tool, its outcome values and its run names need. Never copy its rows into the hand-over.

## Files you write

- `trace.toml`: where the results are, what counts as a failure, the files to import and what each is, and how runs are named.

## Steps

1. **The results already on disk.** Read; run nothing. Find every Prove store: a folder of run folders, each holding a `manifest.json`. Find every file a reader in this install reads: DeepEval's saved test runs under `.deepeval/`, Ragas tables (`.csv` or `.jsonl`), tables of results with a case column, JUnit reports (`.xml`), promptfoo results (`results.json`, `.jsonl` or `.csv`), Inspect logs (`.eval` or `.json`), OpenAI Evals records (`.jsonl`), LangSmith run and trace exports (`.json`, `.jsonl`, or the `.csv` an experiment's page downloads), Braintrust experiment exports (`.json` or `.csv`), Weave evaluation exports (`.json`, `.jsonl`, `.csv` or `.tsv`), and the files of any reader added later; `poisson-trace import --help` lists the readers this install has, and each reader's own `--help` says which files it reads and which options it takes. Note the path of each and the tool that wrote it.
2. **The tools that wrote them.** Read the repository's dependencies and the tools' own configuration: promptfoo's config file, pytest's JUnit option, DeepEval's tests, Inspect's tasks, the CI workflow. The tool that wrote a file decides which reader imports it. When you cannot tell which tool wrote a file, leave it out and say so in the hand-over.
3. **The outcomes.** From the code that scores, find which outcome values count as a failure: the assertions, the names an episode can end with, a metric's threshold. For a scored file, find the metric and the cut the team's code uses. When the code names no cut, leave the file out and say so in the hand-over: you never choose a cut.
4. **The old and the new version.** Work out which runs or files come from before the change and which from after: file names, dates, the history of the code that wrote them. Say which is old and which is new in each `[[import]]` entry's `name` (`rag-base` and `rag-raft`, `tests-old` and `tests-new`), and for Prove runs in the hand-over.
5. **Write trace.toml.** Write `trace.toml` in the repository's root with `version = 1`; `[store]` with `path` for the Prove store when there is one; `[events]` with `failed`, the list of outcome values that count as a failure; one `[[import]]` table for each file to import, with `file` (its path, relative to `trace.toml`), `tool` (its reader), `name` (the run's name, saying old or new) and the reader's own options by their flags' names without the dashes (`metric`, `cut`, `below` or `above`, `case_column`, `case`, `outcome_column`, `failed`); and `[names]` with `from = "target"`. Nothing else: the store the imports go to is not the agent's to write, `poisson-trace init` adds it.
6. **Run the check.** Run it as "The check" below shows, from the folder that holds `trace.toml`, and fix what it names.
7. **Stop and hand over.** Do what "Hand over" below says, and nothing more.

## The check

Run this. It reads what you wrote, spends nothing and changes nothing.

```bash
poisson-trace doctor --setup
```

- If it exits 0, its first line starts with a word such as `plan` or `ok`: the setup is ready for the
  person to review. Go to "Hand over".
- If it exits 1, it printed `error:` and then `next:` lines. Do what the `error:` line names, using
  the `next:` lines, and run the check again.
- If it exits 2, the command line or a setting it needs was wrong; the `error:` line says which. Fix
  what it names.
- Fix at most three times. If the check still fails, stop and hand over what you have, with the last
  output.

## Hand over

Stop here and tell the person, in this order:

1. Each file you wrote, with one line on why it is there.
2. The last output of the check, exactly as printed.
3. What they must confirm before running anything for real (the list below).
4. The one command they run next themselves, in its own block:

   ```text
   poisson-trace init
   ```

Do not run that command for them.

What the person must confirm:

- The stores and files found, and those left out and why.
- The failure outcomes, and where in the code each came from.
- The metric and the cut for each scored file, and where in the code each came from.
- Which run or file is old and which is new, and why.

## Words Trace uses

- `different`: the new version's failure share moved against the old, beyond what chance explains; the report says which way.
- `no significant difference`: the gap could be chance, and the runs rule out a change of the size the person asked about.
- `too small to tell`: these runs cannot rule out a change of the size the person asked about.
- `detection limit`: the smallest change these runs could have shown.
