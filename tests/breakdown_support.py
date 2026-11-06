"""Shared helpers for the failure breakdown and table fixes' tests (Taylor's rulings DM1 to DM4
and DM15 of 2026-11-05, ``log/trace-design/rulings.md``; this pair's own readings are FD1 on,
``log/trace-breakdown-a/rulings.md``).

Not a test module and not collected.

The rules as these tests read them:

- **The failure breakdown (DM1, DM2).** ``fix-check``, ``compare`` and ``changes`` print a report
  section, ``## Failures by kind``: one sentence on what is counted; a table ``kind | old | old
  share | new | new share | change`` (``compare`` and ``changes`` name their runs ``A`` and ``B``,
  as their reports and their continuous measures do), one row a kind either run has, ordered by
  its count over both runs (the larger first, a tie in section 18.5.1's order), and an
  ``all failures`` row last; the line ``of N tries of … and M of …; a try has one kind``; then,
  when either run has a signal, ``Signals seen on tries, failed or not:`` and a table ``signal |
  old | old share | new | new share``. A share is the count over the run's tries, one decimal
  (the report's ``45.0%``); the change is the new share less the old in points, as the
  per-input table prints its change (one decimal, signed, no sign on no change). The counts are the failure-type
  diff TF6 saves (``failure_taxonomy_diff``) over both whole runs.
- **Where it stands.** ``fix-check``: right after ``The two versions`` (``The control`` when
  ``--failing-from`` picked the inputs), before ``The comparison``. ``compare``: at the end of
  ``Comparison``, right after its bold verdict line, before ``Guidance`` and the pointer to
  ``fix-check``. ``changes``: right after ``Runs``, before ``Inputs that changed``.
- **The JSON (rule 2).** ``--json`` of the three verbs carries ``failure_taxonomy_diff``, the very
  object the saved verdict holds, before ``continuous_measures`` (when printed), ``verdicts``
  (when joined) and ``next``. The API's result carries it as before, and its ``to_json()`` and
  ``to_markdown()`` are the command's.
- **The continuous table (DM3).** ``measure | old | new | change | verdict``: the change the
  relative change alone (``+0.88%``), ``none`` when nothing changed, ``-`` when there is no share
  to give; the direction, when there is one, after the verdict word (``different, slower``).
- **No cell broken (DM4).** In every table the pretty renderer draws, at every width, a body cell
  stands whole on one line; when the aligned table cannot fit so, it folds, then prints records.
- **The verdict word's colour (DM15).** In a pretty table, a cell of the column headed
  ``verdict`` that holds a verdict word is drawn in the word's meaning (``too small to tell`` and
  ``no significant difference`` yellow, ``different`` bold, ``identical``, ``not tested`` and
  ``not recorded`` plain); a direction after it stays plain; no digit is coloured; the text under
  the escapes is plain's.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

from conftest import FIXTURES
from tf0_support import Ran, trace, trace_import

BD = FIXTURES / "breakdown"
MOCKUPS = BD / "mockups"
PROVE_013 = FIXTURES / "prove-stores" / "prove-0.1.3"
INGEST = FIXTURES / "ingest"
EV = ["--event", "violated", "--event", "timeout"]
BEFORE, AFTER = "agent before", "agent after"

HEADING = "## Failures by kind"
SIGNALS_LINE = "Signals seen on tries, failed or not:"
BUILT_IN = "by the built-in rules"
OWN_RULES = "by your own rules and the built-in ones"
# section 18.5.1's order: the kinds by precedence, then the signals
KINDS = (
    "timeout", "rate_limit", "context_overflow", "loop_detected", "step_limit", "guardrail_blocked",
    "tool_error", "retrieval_error", "format_error", "abstained", "crash", "wrong_answer",
    "unclassified_error",
)
SIGNALS = ("gave_up", "retry_storm", "over_budget")
TWO_RUNS = ("fix-check", "compare", "changes")
# each verb's arms as its JSON names them, and the words its breakdown names them by
ARMS = {"fix-check": ("old", "new"), "compare": ("a", "b"), "changes": ("a", "b")}
LABELS = {"fix-check": ("old", "new"), "compare": ("A", "B"), "changes": ("A", "B")}
# what the sentence under the heading says the verdict is about (FD5)
ABOUT = {
    "fix-check": "all failures together",
    "compare": "all failures together",
    "changes": "inputs one by one",
}
DIFFERENT_RULES = (
    "The failure types of the two runs were decided by different rules, so their counts are "
    "not set side by side; the digest of each run's rules is given."
)

# the committed Prove 0.1.3 store's breakdown, as the mockup draws it (old = agent before)
PROVE_KINDS = {"tool_error": (66, 21), "loop_detected": (6, 15), "step_limit": (0, 5)}
PROVE_SIGNALS = {"retry_storm": (78, 50), "over_budget": (6, 23)}
PROVE_TRIES = (160, 160)


# ---------- the words a cell holds ----------


def share(n: int, tries: int) -> str:
    """A count over the run's tries, as the report prints a failure share."""
    return f"{100.0 * (n / tries):.1f}%"


def points(n_old: int, t_old: int, n_new: int, t_new: int) -> str:
    """The new share less the old, in points, as the per-input table prints its change: one
    decimal, signed, no sign on no change (FD6)."""
    value = 100.0 * (n_new / t_new - n_old / t_old)
    text = f"{value:+.1f}" if value != 0.0 else f"{value:.1f}"
    return f"{text} points"


def thousands(n: int) -> str:
    return f"{n:,}"


def header(verb: str) -> list[str]:
    a, b = LABELS[verb]
    return ["kind", a, f"{a} share", b, f"{b} share", "change"]


def signals_header(verb: str) -> list[str]:
    a, b = LABELS[verb]
    return ["signal", a, f"{a} share", b, f"{b} share"]


def of_line(verb: str, tries: tuple[int, int]) -> str:
    if verb == "fix-check":
        return f"of {thousands(tries[0])} tries of the old version and {thousands(tries[1])} of the new; a try has one kind"
    a, b = LABELS[verb]
    return f"of {thousands(tries[0])} tries of {a} and {thousands(tries[1])} of {b}; a try has one kind"


def opening(verb: str, whose: str = BUILT_IN) -> str:
    return (
        f"Each failed try's kind of failure, {whose}; the same rules classified both runs. "
        f"Counts, not a test: the verdict above is about {ABOUT[verb]}."
    )


def md_table(head: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + [
        "| " + " | ".join(r) + " |" for r in rows
    ]


def expected_section(
    verb: str,
    kinds: Mapping[str, tuple[int, int]],
    signals: Mapping[str, tuple[int, int]],
    tries: tuple[int, int],
    whose: str = BUILT_IN,
) -> list[str]:
    """The section's lines as the plain report prints them, from the counts: the reference the
    build is held to (DM1, DM2, FD3 to FD7)."""
    ta, tb = tries
    order = sorted(kinds, key=lambda k: (-(kinds[k][0] + kinds[k][1]), KINDS.index(k)))
    rows = [[k, thousands(kinds[k][0]), share(kinds[k][0], ta), thousands(kinds[k][1]), share(kinds[k][1], tb),
             points(kinds[k][0], ta, kinds[k][1], tb)] for k in order]
    sa, sb = sum(v[0] for v in kinds.values()), sum(v[1] for v in kinds.values())
    rows.append(["all failures", thousands(sa), share(sa, ta), thousands(sb), share(sb, tb), points(sa, ta, sb, tb)])
    lines = [HEADING, "", opening(verb, whose), "", *md_table(header(verb), rows), "", of_line(verb, tries)]
    present = [s for s in SIGNALS if s in signals]
    if present:
        srows = [[s, thousands(signals[s][0]), share(signals[s][0], ta), thousands(signals[s][1]), share(signals[s][1], tb)]
                 for s in present]
        lines += ["", SIGNALS_LINE, "", *md_table(signals_header(verb), srows)]
    return lines


def different_rules_section(verb: str, digests: tuple[str, str]) -> list[str]:
    a, b = LABELS[verb]
    return [HEADING, "", DIFFERENT_RULES, "", f"- {a}: {digests[0]}", f"- {b}: {digests[1]}"]


# ---------- reading a report ----------

#: Where a part of a report starts that is not a section's own: a ``## `` heading, or compare's
#: pointer to fix-check, which follows its Comparison section (and its Guidance).
NEXT_PART = ("## ", "For the share of runs that fail")
MEASURES_HEADING = "## Time, length, tokens and cost"


def section(text: str, heading: str = HEADING) -> list[str]:
    """The lines of one ``## `` section of a plain report, from its heading to the line before
    the next part (a ``## `` heading, or compare's pointer line; else the end), trailing blank
    lines dropped."""
    lines = text.splitlines()
    start = lines.index(heading)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith(NEXT_PART)), len(lines))
    body = lines[start:end]
    while body and not body[-1].strip():
        body.pop()
    return body


def headings(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("## ")]




def without_section(text: str, heading: str = HEADING) -> str:
    """The report with one section taken out whole, its heading to the line before the next
    part (a ``## `` heading, or compare's pointer line); the text as it was when the section is
    not there."""
    lines = text.split("\n")
    if heading not in lines:
        return text
    start = lines.index(heading)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith(NEXT_PART)), len(lines))
    return "\n".join(lines[:start] + lines[end:])


def outside_new_parts(argv: Sequence[str], out: str) -> str:
    """What this pair leaves as it was: a verb's plain stdout with the failure breakdown and the
    continuous-measures section taken out (DM1, DM3 change those), its ``--json`` with
    ``failure_taxonomy_diff`` taken out (rule 2 adds it); any other output as it is."""
    if not out or (argv and argv[0] not in TWO_RUNS):
        return out
    if "--json" in argv:
        try:
            json.loads(out)
        except ValueError:
            return out
        return without_key(out)
    if argv[0] not in TWO_RUNS:
        return out
    return without_section(without_section(out), MEASURES_HEADING)


def without_key(doc_text: str, key: str = "failure_taxonomy_diff") -> str:
    """A verb's ``--json`` with one key taken out, written back as the verb writes JSON."""
    doc = json.loads(doc_text)
    doc.pop(key, None)
    return json.dumps(doc, indent=2, allow_nan=False) + "\n"


def table_rows(lines: Sequence[str], which: int = 0) -> list[list[str]]:
    """The body rows of the ``which``-th markdown table among the lines, as cells (its header and
    rule row left out)."""
    tables: list[list[str]] = []
    inside = False
    for line in lines:
        if line.startswith("|"):
            if not inside:
                tables.append([])
            tables[-1].append(line)
            inside = True
        else:
            inside = False
    rows = tables[which] if which < len(tables) else []
    return [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows[2:]]


# ---------- runs ----------


def ok(argv: Sequence[str]) -> Ran:
    ran = trace(list(argv))
    assert ran.code == 0, (list(argv), ran.out, ran.err)
    return ran


def prove_store(tmp: Path, name: str = "store") -> Path:
    """A copy of the committed Prove 0.1.3 store, so that a save writes into the test's folder."""
    dest = tmp / name
    shutil.copytree(PROVE_013, dest)
    return dest


def argv_of(verb: str, store: Path | str, *extra: str) -> list[str]:
    """Each verb of two runs on the Prove store, as the mockup's fix-check was run."""
    base = [verb, BEFORE, AFTER, "--store", str(store), *EV]
    if verb == "fix-check":
        base += ["--inputs", "all", "--max-mde", "0.10"]
    if verb == "compare":
        base += ["--max-mde-hr", "1.5"]
    return [*base, *extra]


def junit_store(tmp: Path) -> Path:
    """Two JUnit imports of the committed HumanEval reports, ``ja`` and ``jb``."""
    store = tmp / "jstore"
    for i, (run, file) in enumerate((("ja", "humaneval-a.xml"), ("jb", "humaneval-b.xml"))):
        made = trace_import(["junit", str(INGEST / "junit" / file), "--store", str(store), "--run", run,
                             "--started", f"2026-10-0{i + 1}T00:00:00Z"])
        assert made.code == 0, made.text
    return store


def table_store(tmp: Path, outcomes: Mapping[str, Mapping[str, str]], *, extra_columns: str = "",
                cells: Mapping[str, Mapping[str, str]] | None = None, config: Path | None = None,
                configs: Mapping[str, Path] | None = None) -> Path:
    """Table imports into one store, one run per entry of ``outcomes`` (case to outcome word, an
    empty word no outcome); ``cells`` adds, per run and case, the text of ``extra_columns`` after
    the outcome; ``config`` is given to every import, ``configs`` to the run it names."""
    store = tmp / "tstore"
    for i, (run, rows) in enumerate(outcomes.items()):
        csv = tmp / f"{run}.csv"
        head = "case,outcome" + (f",{extra_columns}" if extra_columns else "")
        body = "".join(
            f"{c},{o}" + (f",{(cells or {}).get(run, {}).get(c, '')}" if extra_columns else "") + "\n"
            for c, o in rows.items()
        )
        csv.write_text(head + "\n" + body, encoding="utf-8")
        argv = ["table", str(csv), "--store", str(store), "--run", run, "--case-column", "case",
                "--outcome-column", "outcome", "--failed", "failed", "--started", f"2026-10-0{i + 1}T00:00:00Z"]
        given = (configs or {}).get(run, config)
        if given is not None:
            argv += ["--config", str(given)]
        made = trace_import(argv)
        assert made.code == 0, made.text
    return store


def deepeval_store(tmp: Path) -> Path:
    """The DeepEval import of the committed humaneval-a and humaneval-b fixtures, as the
    design session's continuous-measures captures read it (328 cases, 32 repeats)."""
    store = tmp / "de"
    for run, start in (("humaneval-a", "2026-09-05T18:54:07Z"), ("humaneval-b", "2026-09-05T19:54:07Z")):
        made = trace_import(["deepeval", str(INGEST / "deepeval" / f"{run}.json.gz"), "--store", str(store),
                             "--run", run, "--metric", "Tests Passed", "--cut", "recorded", "--case", "name",
                             "--started", start])
        assert made.code == 0, made.text
    return store


def inspect_store(tmp: Path) -> Path:
    """The Inspect import of the committed ``.eval`` and ``.json`` logs (3 cases, 2 repeats)."""
    store = tmp / "insp"
    folder = INGEST / "inspect"
    for run, file in (("trace-fixture eval", next(folder.glob("*.eval"))), ("trace-fixture json", next(folder.glob("*.json")))):
        made = trace_import(["inspect", str(file), "--store", str(store), "--run", run])
        assert made.code == 0, made.text
    return store


DEEPEVAL_ARGV = ["fix-check", "humaneval-a", "humaneval-b", "--event", "missed", "--inputs", "all",
                 "--max-mde", "0.10", "--measures"]
INSPECT_ARGV = ["fix-check", "trace-fixture eval", "trace-fixture json", "--event", "missed", "--inputs", "all",
                "--max-mde", "0.10", "--measures"]


# ---------- the mockups ----------


def mockup(name: str) -> list[str]:
    """A capture of the design session's terminal (every byte the terminal received, escapes
    removed), as lines."""
    return (MOCKUPS / f"{name}.txt").read_text(encoding="utf-8").split("\n")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()




# ---------- what main prints (rule 5) ----------

#: The commit the pins in ``fixtures/breakdown/main-pins.json`` were taken on.
MAIN = "7e6fef6"
PINS = BD / "main-pins.json"
#: Widths the terminal pins are taken at, and the verbs of one run whose terminal output is pinned.
PTY_WIDTHS = (60, 80, 100, 120, 140, 160)


def piped_corpus() -> dict[str, tuple[str, str, list[list[str]]]]:
    """Every invocation rule 5 holds, piped: label to (where it runs, the command, its steps).
    ``work`` runs inside TF13's workspace, ``repo`` on the committed fixtures by their paths.
    TF13-32's corpus (every verb on each kind of store, each option, the refusals, the imports,
    the names) and TF6-1's larger fixtures, plain and ``--json``."""
    from tf0_support import changes_he, compare_tau2, fix_check_he, fix_check_tau2, fix_check_tau2_all, where_cs
    from tf13_support import IMPORT_ARGV, IMPORT_REFUSALS_ARGV, REFUSALS_ARGV, VERBS_ARGV

    out: dict[str, tuple[str, str, list[list[str]]]] = {}
    for label, argv in VERBS_ARGV.items():
        out[f"verb: {label}"] = ("work", "trace", [argv, [*argv, "--json"]])
    for label, (argv, _code) in REFUSALS_ARGV.items():
        out[f"refusal: {label}"] = ("work", "trace", [argv, [*argv, "--json"]])
    for label, argv in IMPORT_ARGV.items():
        out[f"import: {label}"] = ("work", "import", [argv])
        out[f"import json: {label}"] = ("work", "import", [[*argv, "--json"]])
    for label, (argv, _code) in IMPORT_REFUSALS_ARGV.items():
        out[f"import refusal: {label}"] = ("work", "import", [argv, [*argv, "--json"]])
    out["names"] = ("work", "trace", [
        ["name", "agent after", "shipped", "--store", "store"], ["name", "--list", "--store", "store"],
        ["where", "shipped", "--store", "store", *EV], ["runs", "--store", "store", "--json"],
        ["name", "shipped", "--forget", "--store", "store"], ["name", "--list", "--store", "store"],
    ])
    for label, argv in (("where cs", where_cs("--at", "20")), ("compare tau2", compare_tau2("1.3", "--at", "10")),
                        ("fix-check tau2", fix_check_tau2()), ("fix-check tau2 all", fix_check_tau2_all("0.2")),
                        ("fix-check humaneval", fix_check_he()), ("changes humaneval", changes_he())):
        out[f"fixture: {label}"] = ("repo", "trace", [argv, [*argv, "--json"]])
    return out


#: The slow ones: the larger fixtures and the DeepEval import.
SLOW_PIPED = frozenset({"import: deepeval", "import json: deepeval", "fixture: where cs", "fixture: compare tau2", "fixture: fix-check tau2",
                        "fixture: fix-check tau2 all", "fixture: fix-check humaneval", "fixture: changes humaneval"})


def pty_corpus() -> dict[str, list[str]]:
    """The verbs of one run (``where``, ``runs``), inside TF13's workspace, held on a terminal:
    their pretty and ``--plain`` bytes at each of :data:`PTY_WIDTHS` are main's."""
    from tf13_support import VERBS_ARGV

    return {label: argv for label, argv in VERBS_ARGV.items() if argv[0] in ("where", "runs")}


def normal(text: str, *roots: Path) -> str:
    for root in roots:
        text = text.replace(str(root), "<ROOT>")
    return text
