# From JUnit reports

Your test suite runs your agent, and your runner writes a JUnit XML report: pytest does with
`--junitxml`, and so does every CI system. You have a report from before a change and one from
after. This recipe checks whether the suite fails less after the change. It starts from the
two reports and runs no test.

## 1. The files

Keep one report for each version, from the same suite. Run the suite more than once on each
version if you can, and give one import all of a version's reports together: they are read as
repeats.

Here the files are `humaneval-a.xml` and `humaneval-b.xml` in `tests/fixtures/ingest/junit/`
in a clone of the repository: pytest's reports of one suite of 164 tests, run 4 times against
each of two runs of one agent, with nothing changed between them. The commands run from the
clone's root.

## 2. Import each report as a version

One import is one version. A test that failed or errored is `missed`, a test that passed is
`met`, and a skipped test has no outcome. `--case name` pairs tests across the two reports by
their names; without it a test is paired by its class name and its name together.

<!-- command -->
```
poisson-trace import junit tests/fixtures/ingest/junit/humaneval-a.xml \
  --store ./store --run old --case name
```

<!-- excerpt exit=0 -->
```
ok  wrote run old to ./store: 656 rows, 164 cases, 4 repeats each; 569 passed, 87 failed
```

<!-- command -->
```
poisson-trace import junit tests/fixtures/ingest/junit/humaneval-b.xml \
  --store ./store --run new --case name
```

<!-- excerpt exit=0 -->
```
ok  wrote run new to ./store: 656 rows, 164 cases, 4 repeats each; 573 passed, 83 failed
```

## 3. Check the fix

`--max-mde 0.05` asks that the check be able to see a drop of 5 points in the share of tests
that fail.

<!-- command -->
```
poisson-trace fix-check old new --store ./store --event missed \
  --inputs all --max-mde 0.05
```

<!-- excerpt exit=0 -->
```
no significant difference  the gap could be chance
```

<!-- excerpt exit=0 -->
```
| version | runs | failed | failure share | did not fail |
|---|---|---|---|---|
| old | 656 | 87 | 13.3% | 86.7% |
| new | 656 | 83 | 12.7% | 87.3% |
```

Four fewer failures in 656 tests run is a gap chance makes easily, and the verdict says so: *no
significant difference*, with tries enough to rule out a change of the size asked about. The
[JUnit page](../integrations/junit.md) has every flag and what the reader refuses.

## What this does not do

- It does not run your tests or your runner; it reads the reports.
- It does not read a report as two versions: one import is one version's reports.
- It does not say your change caused a difference: run both versions side by side for that.
- It keeps no failure message and no captured output of a test.
