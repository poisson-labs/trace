# Contributing to Poisson Trace

This page is for someone changing Trace itself: how to get a working copy, how to run the
suite, and the rules a change is held to. If you only want to use Trace, the
[README](README.md) is the place to start.

## A working copy

Trace needs Python 3.11, 3.12 or 3.13. The suite is run on two of them before a change is
merged: Python 3.11, the oldest the package declares, and Python 3.12. Make an environment
for each:

<!-- skip reason="a contributor's commands: shown here, and not run by the docs check" -->
```
git clone https://github.com/poisson-labs/trace
cd trace
python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'
python3.11 -m venv .venv311 && .venv311/bin/pip install -e '.[dev]'
.venv/bin/poisson-trace --version
```

The development install also brings Poisson Tasks, which one recipe the suite runs needs
(`docs/recipes/with-tasks-and-prove.md`). Tasks needs a tokenizer file it does not ship. Fetch
it once in each environment, or that recipe's tests fail at its first command:
`.venv/bin/poisson-tasks doctor --fix --yes`, and the same with `.venv311`.

The last line prints the version of Trace, of Prove and of Python. Prove is the
`poisson-prove` package, which Trace reads stored runs through. `pyproject.toml` declares the
oldest version Trace reads, 0.4.0, and sets no upper limit, so `pip` brings the newest.

## The suite

The tests are in four lanes, told apart by marks that `pyproject.toml` names. Each line below
is one lane, and `-n 10` runs it on ten workers:

<!-- skip reason="a contributor's commands: shown here, and not run by the docs check" -->
```
env -u CI .venv/bin/python -m pytest -n 10 -m "not math and not lane_j and not slow" tests
env -u CI .venv/bin/python -m pytest -n 10 -m slow tests
env -u CI .venv/bin/python -m pytest -n 10 -m math tests
env -u CI .venv/bin/python -m pytest -m lane_j tests
```

- The first is the pull-request lane: everything that is quick. It runs on every pull request.
- `-m slow` holds the long form of tests whose short form is in the pull-request lane: every
  case of a set where the quick lane runs a few.
- `-m math` holds the statistics' slow checks against their references. Run it when you change
  `src/poisson_trace/paired.py`, `survival.py` or anything under `src/poisson_trace/stats`, or
  when numpy, scipy, pandas or lifelines move.
- `-m lane_j` is the one lane that reaches the package index: it installs the real DeepEval
  and Ragas and runs them. It is left out unless you ask for it.

`env -u CI` matters: Trace reads `CI` as a reason to print plain text, and the tests pin what
it prints without it.

Apart from `-m lane_j`, the suite makes no network call and no paid call, and reads no key.
The readers for LangSmith, Braintrust and Weave are tested against answers those services
gave once, kept under `tests/fixtures/ingest/`.

Then the linter and the type checker, on both Pythons, each with a cache of its own so that
one Python's cache is never read by the other:

<!-- skip reason="a contributor's commands: shown here, and not run by the docs check" -->
```
.venv/bin/ruff check src tests
.venv/bin/mypy --strict --cache-dir .mypy_cache_312
.venv311/bin/ruff check src tests
.venv311/bin/mypy --strict --cache-dir .mypy_cache_311
```

`tools/lane.py` runs any of these for you, with the Python it is started with:

<!-- skip reason="a contributor's commands: shown here, and not run by the docs check" -->
```
.venv/bin/python tools/lane.py pr
.venv/bin/python tools/lane.py slow
.venv/bin/python tools/lane.py mypy
.venv311/bin/python tools/lane.py pr tests/test_cli.py
```

Its first word is the lane (`pr`, `slow`, `math` or `lane_j`), or `ruff` or `mypy`, and every
word after it goes to that command as written. It takes `CI` out of the environment, gives the
run a temporary folder of its own and removes the folder when the run ends, and gives mypy the
cache named for the running Python. Use it when you run a lane more than once, or two
checkouts side by side: a lane's temporary files are large, and `pyproject.toml` already tells
pytest to remove a test's folder as soon as the test passes.

## The docs are tested too

Every command a page shows is run, and what the page says it printed is held to what it
printed. `tools/docs_check.py` does it, with whatever `poisson-trace` is first on your `PATH`:

<!-- skip reason="a contributor's commands: shown here, and not run by the docs check" -->
```
PATH="$PWD/.venv/bin:$PATH" python tools/docs_check.py
PATH="$PWD/.venv/bin:$PATH" python tools/docs_check.py docs/recipes/first-look.md
```

With no page it checks the README, this page and every page under `docs/` but the look
standard. A page marks each block with a comment on the line above it: `<!-- command -->`
for a block to run, `<!-- output exit=0 -->` for the whole of what it printed,
`<!-- excerpt exit=0 -->` for a run of its lines, and `<!-- skip reason="..." -->` for a block
that is shown and not run. The opening of `tools/docs_check.py` has the whole list. When you
change what a command prints, run the check and update the pages it names.

A page under `docs/` is written for a reader who has never seen Trace: plain words, every
number with its unit, and every claim shown by a command that runs. The README's blocks are
each a block of a recipe under `docs/recipes/`, so change the recipe and the README together.

## Frozen tests

The test files are frozen: they were written and agreed before the code they test, and they
do not change to make a build pass. One list, `tests/frozen.sha256`, holds the SHA-256 digest
of every one of them, of each support module beside them and of the pins they read, and one
test, in `tests/test_frozen.py`, fails when a listed file is edited and when a test file is
not on the list.

A frozen file changes only in a commit of its own that says why, with the file's line in the
list moved in that commit. The failing test prints the line to write, and `shasum` checks the
whole list:

<!-- skip reason="a contributor's commands: shown here, and not run by the docs check" -->
```
shasum -a 256 -c tests/frozen.sha256
```

A new test file joins the list in the commit that adds it. If a frozen test seems wrong, stop
and ask: do not edit it, and do not add a test that says the opposite.

## Fixtures

The files under `tests/fixtures/` are real: runs that Prove stored, and result files that
each tool wrote. None is written by hand. `tests/fixtures/PROVENANCE.md` says where each came
from and how it was made, and `tests/fixtures/SHA256SUMS` holds the digest of each:

<!-- skip reason="a contributor's commands: shown here, and not run by the docs check" -->
```
cd tests/fixtures && shasum -a 256 -c SHA256SUMS
```

A new reader needs a real export of its tool among the fixtures before its page may name the
tool, and a line in both files.

## The look standard

`docs/cli-look.md` says how every Poisson Labs command prints: the verdict line, the exit
codes, the colours, the plain form. It is a copy of the lab's own file, kept byte for byte,
and a test holds it to that. Do not edit it here.

## Commits and releases

Sign your commits. Keep a commit to one thing, and say in its message what changed for a
user. `CHANGELOG.md` gets a line for every change a user can see.

A release is a signed tag: `.github/workflows/release.yml` builds the package from the tag,
runs the lanes above on Python 3.11, 3.12 and 3.13, and publishes. `.github/workflows/ci.yml` runs
the same lanes on pull requests and on `main`.
