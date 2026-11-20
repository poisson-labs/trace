# The terminal app

`poisson-trace` with no verb opens an app in your terminal: your runs, the files you could
import, a comparison of two runs, a fix check, and the verdict with what it cannot say. It is
for looking around a store without typing a command for each look. This page says how it
opens, what is on each screen, and every key.

## How it opens

Type the command alone, on a terminal:

<!-- skip reason="the bare command opens the terminal app, which needs a terminal" -->
```
poisson-trace
```

It opens on the `trace.toml` in the current folder. With `--config` and a path it opens on
another config, and with `--store` and a folder on a store that has no config. With no
`trace.toml` and no store, the first screen says how to make one: `poisson-trace init`.

The app needs a window of at least 80 columns by 24 rows. Where a screen has more lines than
the window, the lines that do not fit move behind one key and nothing is cut.

It opens only where a person is looking. Where stdin or stdout is not a terminal, as in a
script or a pipe, or where `CI` is set, the bare command is a mistake in the command line and
exits 2:

<!-- command -->
```
poisson-trace
```

<!-- output exit=2 -->
```
error: no verb was given; the verbs are init, runs, name, where, compare, fix-check, changes, import, doctor, handover, ui and report
  next: poisson-trace --help
```

`--plain` with no verb never opens the app. `NO_COLOR` set to anything keeps
the app and drops its colours.

## The screens

Every screen shows what a plain command prints for the same runs and settings: every fact
and every number on a screen is the plain command's. The app works nothing out by itself.

| screen | how you reach it | its own keys | what is on it |
|---|---|---|---|
| home | the app opens here | `c` `f` `r` `i` | the stores, the failures, the newest runs and the saved verdicts, and the next thing to do. `r` the runs, `i` the imports, `c` and `f` the two pickers |
| runs | `r` on home | `n` `c` `f` `s` | what `poisson-trace runs` lists. `n` names the run in focus, after a question. `s` moves to the next store the config names |
| run | `enter` on a run | `c` `t` `d` | one run's `where`: the verdict line, the summary and where its tries die by kind of step. `t` shows the share not yet failed by step, `d` what it cannot say |
| imports | `i` on home | `s` | the runs an import wrote, each with its tool and file, and the result files found and not imported. `enter` on a file shows its import line and runs it after a question |
| compare | `c` on home, runs or a run | `space` `l` `h` | a picker of two runs for `compare`. `space` chooses the run in focus, the before and then the after. `l` chooses previous and latest. `h` sets the size asked about when `trace.toml` gives none |
| fix-check | `f` on home, runs or a compare verdict | `space` `l` `h` | the same picker for `fix-check`: the old run and then the new |
| verdict of a compare | `enter` in the compare picker | `k` `d` `f` | the compare verdict in full: the summary, then every line of *Before you act on this*, then the numbers. `k` the failures by kind, `d` what it cannot say, `f` a fix-check of the same two runs |
| verdict of a fix-check | `enter` in the fix-check picker | `k` `t` `d` `g` | the fix-check verdict in full. `k` the failures by kind, `t` the table of inputs that changed, `d` what it cannot say, `g` the changes screen |
| changes | `g` on a fix-check verdict | `d` | the inputs whose share of failures moved, as `poisson-trace changes` prints them |
| could not say | `d` on a run, a verdict or changes | none | the sentences the report ends with: what this result cannot say |
| help | `?` on any screen | none | every key |

Every verdict the app shows is saved in the store, as `--save` saves it, and a line says so.
The app draws no chart: where a result has one, the screen holds a link to its page, which
`enter` opens in your browser.

## The keys on every screen

| key | what it does |
|---|---|
| `↑↓` | move the focus one row; `PgUp`, `PgDn`, `Home` and `End` move it further |
| `enter` | open the row in focus, or its link in the browser |
| `esc` | go back, with the focus where it was; during a question, no |
| `tab` | move the focus between the links and the table |
| `/` | filter the table's rows by text; `esc` clears it |
| `y` | copy the link or the command in focus; during a question, yes |
| `m` | show the lines above the table that the window has no room for; `m` again shows the table |
| `?` | the help screen |
| `q` | quit, with exit code 0; during a question, no |

Ctrl-C quits with exit code 130 and says what was kept. Work under way is let go, unsaved.

## What it never does

The app runs nothing of yours and makes no model call. It reads no key and reaches no
network. It writes only what you said yes to, an import or a name, and what a plain command
would write for the same result: a saved verdict and the pages it links to.
