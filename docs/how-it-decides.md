# How it decides

Every report from Trace ends in a verdict, and every verdict comes from a named statistical
test with a stated level. This page says which test stands behind each command, how the three
verdicts are chosen, and which flags set a size, a level or a seed. It is written to be
checked: each method is named so that you can look it up, and the test suite holds each one
against an independent reference.

The four commands that decide are `where`, `compare`, `fix-check` and `changes`. The first
two read the steps of each try and need runs that carry traces. The last two read only
whether each try failed, and work on any run.

## The three verdicts

`compare` and `fix-check` end in one of three:

- *different*: the test says the two runs differ, at the level `--alpha` sets (default 0.05).
- *no significant difference*: the test does not say so, and the tries were enough to rule
  out a change of the size you asked about.
- *too small to tell*: the test does not say so, and the tries were not enough to rule that
  size out. The report says how many more would be.

The size you ask about has no default, because only you know what change would matter. It is
`--max-mde` on `fix-check` and `--max-mde-hr` on `compare`. Choose it before you look at a
result: a size chosen after seeing the report no longer says what the tries could show.

`where` describes one run and `changes` lists inputs, so both end in `ok` with a sentence.

## `where`: where the tries of one run die

A step is one unit of work inside a try: a model call, a tool call, a retrieval. Trace puts
every try on one clock, the number of the step it had reached when it stopped, and each try
ends in one of these ways:

| a try | when | on the curve |
|---|---|---|
| failed | its outcome is one of the failures you named | a failure at its last step |
| ended | it finished with any other outcome | leaves the curve at its last step, as an end of its own |
| timed out | it has no outcome and Prove marked a timeout | leaves the curve at its last step, as an end of its own |
| capped | its trace reached the recorder's limit on steps | censored at its last step: what came after is unknown |
| left out | it has no trace, an unreadable one, or no outcome and no timeout | not on the curve; counted by reason |

The curve is the share of tries that had not failed by each step, by the Aalen–Johansen
estimator: finishing and timing out are competing ends, so a try that finished early is not
counted as one that might still fail. The same estimator gives each kind of step its share of
the failures. A try that timed out or was capped is checked for that before its outcome is
read, because a trace that stops early cannot say at which step the try failed.

The bands are a bootstrap: the inputs are drawn again with replacement, `--boot` times
(default 1,000), and the middle 95% of the results is the band. `--seed` (default 0) fixes the
draws, so the same command prints the same band. Tries of one input are drawn together.

## `compare`: sooner or later, between two runs

`compare` asks whether, step by step, tries still going fail at a different rate in one run
than in the other. The test is the log-rank test, stratified by input, over the inputs both
runs hold. It prints the hazard ratio of the after run against the before run with a 95%
range, and the smallest ratio the test could have caught 4 times in 5 (80% power).

The verdict is *different* when the log-rank test says so at `--alpha`. Otherwise it is *no
significant difference* when that smallest ratio is at or under `--max-mde-hr`, and *too small
to tell* when it is above. The same test is run for each kind of step on its own, and those
are corrected together by the Benjamini–Hochberg rule.

This is a question about when tries fail, not how often. A version whose tries finish sooner
can differ in one and not in the other, which is why the report points to `fix-check` for the
second question.

## `fix-check`: fewer failures, with a control

`fix-check` takes an old and a new version run on the same inputs. `--failing-from RUN` takes
the inputs that failed in a third run, the one that chose them, and `--inputs all` takes every
input both runs hold. One of the two is required: which inputs are compared is the choice
that makes the check honest, so it has no default. The run that chose the inputs can be
neither the old nor the new run, because its failures on those inputs are there by selection.

- **The control.** The report first shows how often the old version failed on these inputs
  when run again with nothing changed. Counting the inputs that pass on the new version, with
  no such number beside it, credits the fix with what chance does.
- **The test** is the exact conditional Cochran–Mantel–Haenszel test, stratified by input.
  Each input is its own small table of version against failed or not, and the test asks
  whether the new version's failures, summed over the inputs, are fewer or more than chance
  gives. It is exact: no approximation that needs many tries. An input that always fails, or
  never does, adds nothing either way. With one input it is the Fisher exact test, and with
  one try of each version on every input it is the exact McNemar test.
- **The difference** is the Mantel–Haenszel difference in the share of tries that fail, new
  minus old, in points. Its range is the stratified Miettinen–Nurminen interval at 95%. The
  report calls the range reliable when at least 10 inputs vary and neither version ran only
  once on most inputs, and rough otherwise, and says which.
- **The verdict** is *different* when the test says so. Otherwise, where the range is
  reliable, it is *no significant difference* when the whole range lies inside plus or minus
  `--max-mde`, and *too small to tell* when it does not. Where the range is rough, the
  smallest drop the tries could have caught decides instead.
- **The reading by input** counts each input once, whichever way it moved, and asks whether
  the moves lean one way. It does not need repeat tries of an input to be independent, so it
  is the check on repeats that are near copies of one another. It prints beside the test and
  has no part in the verdict. When many inputs moved it is computed from random draws, which
  `--seed` fixes.
- **The limit** is the smallest drop in the share of failures that the test would have caught
  4 times in 5, in points. It is printed under every verdict.
- **The guidance** under a *too small to tell* is worked out by the same rule that stated the
  limit, so the number of repeats it suggests is the number that would have passed.

What is counted, and what is left out:

| a try or an input | how `fix-check` and `changes` count it |
|---|---|
| a try whose outcome is one of the failures you named | failed |
| a try with any other outcome | did not fail |
| a try with no outcome | left out, and counted in the header for each version |
| an input the old run does not hold | left out: not run again on the old version |
| an input the new run does not hold | left out: not run again on the new version |
| an input whose every try on one version has no outcome | left out |

Leaving out a try with no outcome is the one rule that can hide a real effect, a new version
that times out where the old one failed, so the count is printed for each version.

## `changes`: which inputs moved

`changes` runs the Fisher exact test on each input by itself, old against new, and then
corrects all the inputs together by the Benjamini–Hochberg rule at `--alpha`, so that of the
inputs it flags, about one in twenty at most is a false alarm. The report also says what this
design could not have flagged: with few repeats of an input, even a complete flip cannot stand
out, and an input with no flag is not an input that did not change.

## What no test here covers

- Looking after every few tries and stopping when the verdict reads well. The stated level
  holds for one look, decided beforehand.
- What else differed between the two runs. A difference between two runs is a difference
  between the runs: the version, the provider and the hour changed together unless the two
  were run side by side.
- Repeats that are near copies of one another. The tests count tries of one input as separate
  chances, and the reading by input is the check on that.

[What it cannot say](recipes/what-it-cannot-say.md) reads these parts of a real report.
