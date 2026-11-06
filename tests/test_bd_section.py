"""BD-1: the failure breakdown, a report section on fix-check, compare and changes (Taylor's DM1
and DM2 of 2026-11-05; FD1 and FD3 to FD8, ``log/trace-breakdown-a/rulings.md``).

**BD-1a** Where it stands. ``fix-check``: right after ``The two versions`` (``The control`` when
``--failing-from`` picked the inputs), before ``The comparison``; ``compare``: right after the
Comparison section's bold verdict line, before ``Guidance`` and the pointer to ``fix-check``;
``changes``: right after ``Runs``, before ``Inputs that changed``. ``where`` prints none.

**BD-1b** What it says on the committed Prove 0.1.3 store, line for line: the mockup's section
(``log/trace-design/terminal/breakdown-prove-*``), with ``compare`` and ``changes`` naming their
runs ``A`` and ``B``.

**BD-1c** The counts are the failure-type diff TF6 saves, read here independently through TF21's
reader: one row a kind either run has, ordered by its count over both runs and a tie by section
18.5.1's order, an ``all failures`` row last; shares over each run's tries; the change in points
as the report prints points.

**BD-1d** The edges: no failure in either run, no signal, a tie, a thousand tries, a change under
one point, no change, the user's own rules on both runs, and different rules on the two.

**BD-1e** It follows the rows the verb read: a ``--verdicts`` file's filled failures, each with a
kind (FD8), and runs read from tool folders.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from breakdown_support import (
    AFTER, BEFORE, BUILT_IN, DIFFERENT_RULES, HEADING, KINDS, LABELS, OWN_RULES, PROVE_013, PROVE_KINDS,
    PROVE_SIGNALS, PROVE_TRIES, SIGNALS, SIGNALS_LINE, TWO_RUNS, argv_of, different_rules_section,
    expected_section, headings, junit_store, ok, opening, points, section, share, table_rows, table_store,
)

# ---------- BD-1a ----------


def _after(heads: list[str], first: str) -> str:
    return heads[heads.index(first) + 1]


def test_bd_1a_fix_check_after_the_two_versions() -> None:
    heads = headings(ok(argv_of("fix-check", PROVE_013)).out)
    assert heads.count(HEADING) == 1
    assert _after(heads, "## The two versions") == HEADING
    assert _after(heads, HEADING) == "## The comparison"


def test_bd_1a_fix_check_with_measures_keeps_its_measures_where_they_were() -> None:
    heads = headings(ok(argv_of("fix-check", PROVE_013, "--measures")).out)
    assert _after(heads, "## The two versions") == HEADING
    assert _after(heads, HEADING) == "## The comparison"
    assert _after(heads, "## Time, length, tokens and cost") == "## What this cannot say"


def test_bd_1a_fix_check_after_the_control(tmp_path: Path) -> None:
    """``--failing-from`` picks the inputs: the section follows The control."""
    outcomes = {
        "sel": {f"c{i}": ("failed" if i < 6 else "passed") for i in range(10)},
        "old": {f"c{i}": ("failed" if i < 5 else "passed") for i in range(10)},
        "new": {f"c{i}": ("failed" if i < 2 else "passed") for i in range(10)},
    }
    store = table_store(tmp_path, outcomes)
    out = ok(["fix-check", "old", "new", "--store", str(store), "--event", "missed", "--failing-from", "sel",
              "--max-mde", "0.5"]).out
    heads = headings(out)
    assert "## The control" in heads and "## The two versions" not in heads
    assert _after(heads, "## The control") == HEADING
    assert _after(heads, HEADING) == "## The comparison"


def _compare_parts(out: str) -> list[str]:
    """compare's report from its bold verdict line on: the line, then each part's first line."""
    lines = out.split("\n")
    bold = next(i for i, line in enumerate(lines) if line.startswith("**") and line.endswith("**"))
    return [line for line in lines[bold:] if line.startswith(("**", "## ", "For the share of runs"))]


def test_bd_1a_compare_after_its_verdict_line_before_the_pointer() -> None:
    parts = _compare_parts(ok(argv_of("compare", PROVE_013)).out)
    assert parts[0].startswith("**different")
    assert parts[1:4] == [HEADING, parts[2], "## What this cannot say"]
    assert parts[2].startswith("For the share of runs that fail")
    lines = ok(argv_of("compare", PROVE_013)).out.split("\n")
    at = lines.index(HEADING)
    assert lines[at - 2].startswith("**") and lines[at - 1] == ""


def test_bd_1a_compare_before_its_guidance() -> None:
    """Asked for a ceiling the run cannot reach, compare prints Guidance after Comparison."""
    argv = ["compare", BEFORE, AFTER, "--store", str(PROVE_013), "--event", "timeout", "--max-mde-hr", "1.5"]
    parts = _compare_parts(ok(argv).out)
    assert parts[0].startswith("**too small to tell")
    assert parts[1:3] == [HEADING, "## Guidance"]
    assert parts[3].startswith("For the share of runs that fail")


def test_bd_1a_changes_after_runs() -> None:
    heads = headings(ok(argv_of("changes", PROVE_013)).out)
    assert _after(heads, "## Runs") == HEADING
    assert _after(heads, HEADING) == "## Inputs that changed"


def test_bd_1a_where_prints_none() -> None:
    out = ok(["where", AFTER, "--store", str(PROVE_013), "--event", "violated", "--event", "timeout"]).out
    assert HEADING not in out and SIGNALS_LINE not in out


@pytest.mark.parametrize("verb", TWO_RUNS)
def test_bd_1a_one_blank_line_around_it(verb: str) -> None:
    lines = ok(argv_of(verb, PROVE_013)).out.split("\n")
    at = lines.index(HEADING)
    assert lines[at - 1] == "" and lines[at - 2] != ""
    body = section("\n".join(lines))
    after = at + len(body)
    assert lines[after] == "" and lines[after + 1] != ""


# ---------- BD-1b ----------


@pytest.mark.parametrize("verb", TWO_RUNS)
def test_bd_1b_the_prove_stores_section(verb: str) -> None:
    got = section(ok(argv_of(verb, PROVE_013)).out)
    assert got == expected_section(verb, PROVE_KINDS, PROVE_SIGNALS, PROVE_TRIES)


def test_bd_1b_fix_checks_section_is_the_mockups_word_for_word() -> None:
    """The mockup's plain capture at 140 columns, its one wrapped paragraph joined again: the plain
    report piped prints one line per fact (the terminal's wrapping is BD-1 in test_bd_terminal)."""
    from breakdown_support import mockup

    lines = mockup("breakdown-prove-140-plain")
    start, end = lines.index(HEADING), lines.index("next: " + lines[-2].removeprefix("next: "))
    drawn = lines[start:end]
    while drawn and not drawn[-1]:
        drawn.pop()
    joined: list[str] = []
    for line in drawn:
        if line.startswith("  ") and joined:
            joined[-1] += " " + line.strip()
        else:
            joined.append(line)
    assert section(ok(argv_of("fix-check", PROVE_013)).out) == joined


# ---------- BD-1c ----------


def _counts(store: Path, run: str, events: list[str]) -> tuple[dict[str, int], dict[str, int], int]:
    """A run's kinds and signals, read through TF21's reader: the reference the diff is."""
    from poisson_trace.ingest.prove import read_rows

    rows = read_rows(store, run, events)
    kinds = {k: sum(1 for r in rows if r.failure_kind == k) for k in KINDS}
    signals = {s: sum(1 for r in rows if s in r.signals) for s in SIGNALS}
    return kinds, signals, len(rows)


def _reference(store: Path, runs: tuple[str, str], run_ids: tuple[str, str], events: list[str], verb: str) -> list[str]:
    (ka, sa, ta), (kb, sb, tb) = (_counts(store, r, events) for r in run_ids)
    kinds = {k: (ka[k], kb[k]) for k in KINDS if ka[k] or kb[k]}
    signals = {s: (sa[s], sb[s]) for s in SIGNALS if sa[s] or sb[s]}
    return expected_section(verb, kinds, signals, (ta, tb))


def _ids(store: Path, *names: str) -> tuple[str, ...]:
    out = []
    for name in names:
        hits = [p.name for p in store.iterdir() if p.is_dir() and not p.name.startswith(".")
                and json.loads((p / "manifest.json").read_text(encoding="utf-8")).get("run_name", p.name) == name]
        out.append(hits[0] if hits else name)
    return tuple(out)


def test_bd_1c_the_prove_store_by_the_reader() -> None:
    ids = ("20261104T162926Z-b4d5", "20261104T162928Z-1596")
    for verb in TWO_RUNS:
        want = _reference(PROVE_013, (BEFORE, AFTER), ids, ["timeout", "violated"], verb)
        assert section(ok(argv_of(verb, PROVE_013)).out) == want, verb


def test_bd_1c_the_prove_store_with_one_event() -> None:
    """Which tries failed is the verb's ``--event``: with ``timeout`` alone, fewer kinds."""
    ids = ("20261104T162926Z-b4d5", "20261104T162928Z-1596")
    argv = ["changes", BEFORE, AFTER, "--store", str(PROVE_013), "--event", "timeout"]
    want = _reference(PROVE_013, (BEFORE, AFTER), ids, ["timeout"], "changes")
    assert section(ok(argv).out) == want
    assert table_rows(want)[0][0] == "loop_detected"


@pytest.mark.parametrize("verb", ["fix-check", "changes"])  # compare needs traces, which JUnit has none of
def test_bd_1c_junit_imports(tmp_path: Path, verb: str) -> None:
    store = junit_store(tmp_path)
    argv = [verb, "ja", "jb", "--store", str(store), "--event", "missed"]
    if verb == "fix-check":
        argv += ["--inputs", "all", "--max-mde", "0.1"]
    got = section(ok(argv).out)
    assert got == _reference(store, ("ja", "jb"), _ids(store, "ja", "jb"), ["missed"], verb)
    # JUnit records no signal: the signals' part is left out (FD4)
    assert SIGNALS_LINE not in got


def test_bd_1c_kinds_by_their_count_over_both_runs_then_precedence(tmp_path: Path) -> None:
    """timeout and crash tie at 3 over both runs: timeout first (precedence 1 before 11); wrong
    answer has 4 and comes first of all."""
    old = {f"c{i}": "failed" for i in range(10)}
    new = {f"c{i}": "failed" for i in range(10)}
    kinds_old = {"c0": "crash", "c1": "crash", "c2": "timeout", "c3": "wrong_answer", "c4": "wrong_answer"}
    kinds_new = {"c0": "crash", "c1": "timeout", "c2": "timeout", "c3": "wrong_answer", "c4": "wrong_answer"}
    for c in list(old):
        if c not in kinds_old:
            old[c] = "passed"
        if c not in kinds_new:
            new[c] = "passed"
    store = table_store(tmp_path, {"old": old, "new": new}, extra_columns="failure_kind",
                        cells={"old": kinds_old, "new": kinds_new})
    out = ok(["changes", "old", "new", "--store", str(store), "--event", "missed"]).out
    rows = table_rows(section(out))
    assert [r[0] for r in rows[:3]] == ["wrong_answer", "timeout", "crash"]
    assert rows[-1][0] == "all failures"
    assert rows[-1][1:] == ["5", "50.0%", "5", "50.0%", "0.0 points"]


# ---------- BD-1d ----------


def test_bd_1d_no_failure_in_the_old_run(tmp_path: Path) -> None:
    """A run with no failure has its zeros; a kind only the other run has is listed. (No failure
    in either run cannot be asked: the verb refuses an event neither run carries.)"""
    old = {f"c{i}": "passed" for i in range(8)}
    new = {f"c{i}": ("failed" if i < 2 else "passed") for i in range(8)}
    store = table_store(tmp_path, {"old": old, "new": new})
    got = section(ok(["changes", "old", "new", "--store", str(store), "--event", "missed"]).out)
    rows = table_rows(got)
    assert rows[-1] == ["all failures", "0", "0.0%", "2", "25.0%", "+25.0 points"]
    assert all(r[1] == "0" and r[2] == "0.0%" for r in rows)


def test_bd_1d_a_thousand_tries_and_a_change_under_one_point(tmp_path: Path) -> None:
    old = {f"c{i:04d}": ("failed" if i < 4 else "passed") for i in range(1200)}
    new = {f"c{i:04d}": ("failed" if i < 7 else "passed") for i in range(1200)}
    store = table_store(tmp_path, {"old": old, "new": new})
    got = section(ok(["changes", "old", "new", "--store", str(store), "--event", "missed"]).out)
    assert "of 1,200 tries of A and 1,200 of B; a try has one kind" in got
    last = table_rows(got)[-1]
    assert last == ["all failures", "4", share(4, 1200), "7", share(7, 1200), points(4, 1200, 7, 1200)]
    assert last[2] == "0.3%" and last[4] == "0.6%"
    assert last[-1] in ("+0.2 points", "+0.3 points")  # one decimal under one point too (FD6)


def test_bd_1d_the_points_as_the_report_prints_them() -> None:
    assert points(66, 160, 21, 160) == "-28.1 points"
    assert points(0, 160, 5, 160) == "+3.1 points"
    assert points(1, 400, 3, 400) == "+0.5 points"
    assert points(3, 10, 3, 10) == "0.0 points"
    assert points(8, 10, 1, 10) == "-70.0 points"
    assert share(66, 160) == "41.2%" and share(78, 160) == "48.8%"


def _rules_config(path: Path, pattern: str) -> Path:
    path.write_text(
        'version = 1\n\n[[taxonomy.rules]]\nfailure_kind = "tool_error"\n'
        f'when_error_matches = "{pattern}"\n', encoding="utf-8")
    return path


def test_bd_1d_the_same_rules_of_the_users_own(tmp_path: Path) -> None:
    config = _rules_config(tmp_path / "trace.toml", "SqlDeadlockError")
    outcomes = {"old": {f"c{i}": ("failed" if i < 3 else "passed") for i in range(6)},
                "new": {f"c{i}": ("failed" if i < 1 else "passed") for i in range(6)}}
    store = table_store(tmp_path, outcomes, config=config)
    got = section(ok(["changes", "old", "new", "--store", str(store), "--event", "missed"]).out)
    assert got[2] == opening("changes", OWN_RULES)
    assert BUILT_IN not in got[2]


def test_bd_1d_different_rules(tmp_path: Path) -> None:
    """Runs classified by different rules: no counts, the sentence the saved note holds, and each
    run's digest (TF6-29's case, SV9)."""
    from poisson_trace.ingest.taxonomy import taxonomy_sha256

    rules = _rules_config(tmp_path / "rules.toml", "SqlDeadlockError")
    outcomes = {"old": {f"c{i}": ("failed" if i < 3 else "passed") for i in range(6)},
                "new": {f"c{i}": ("failed" if i < 1 else "passed") for i in range(6)}}
    store = table_store(tmp_path, outcomes, configs={"new": rules})
    ran = ok(["changes", "old", "new", "--store", str(store), "--event", "missed", "--json"])
    diff = ran.json()["failure_taxonomy_diff"]
    assert diff["same_rules"] is False
    digests = (diff["taxonomy_sha256"]["a"], diff["taxonomy_sha256"]["b"])
    assert digests[0] == taxonomy_sha256((), None) and digests[1] != digests[0]
    got = section(ok(["changes", "old", "new", "--store", str(store), "--event", "missed"]).out)
    assert got == different_rules_section("changes", digests)
    assert DIFFERENT_RULES in got and not any(line.startswith("|") for line in got)


# ---------- BD-1e ----------


def test_bd_1e_a_verdicts_files_filled_failures_are_counted(tmp_path: Path) -> None:
    """Two tries with no outcome, one graded ``fail`` by the file: it is counted as a failure of
    its run, as the saved diff counts it (TF6-34)."""
    old = {**{f"c{i}": ("failed" if i < 2 else "passed") for i in range(8)}, "c8": "", "c9": ""}
    new = {**{f"c{i}": ("failed" if i < 1 else "passed") for i in range(8)}, "c8": "", "c9": ""}
    store = table_store(tmp_path, {"old": old, "new": new})
    grades = tmp_path / "grades.csv"
    grades.write_text("case,outcome\nc8,fail\nc9,pass\n", encoding="utf-8")
    base = ["changes", "old", "new", "--store", str(store), "--event", "missed"]
    before = table_rows(section(ok(base).out))[-1]
    after = table_rows(section(ok([*base, "--verdicts", str(grades)]).out))[-1]
    # the file grades by case: c8 is filled as a failure in both runs
    assert (int(after[1]), int(after[3])) == (int(before[1]) + 1, int(before[3]) + 1)
    saved = ok([*base, "--verdicts", str(grades), "--json"]).json()["failure_taxonomy_diff"]
    assert int(after[1]) == sum(k["a"] for k in saved["kinds"])
    assert int(after[3]) == sum(k["b"] for k in saved["kinds"])


def test_bd_1e_runs_read_from_tool_folders(tmp_path: Path) -> None:
    """The two JUnit reports given as folders: the same section as from their imports."""
    from breakdown_support import INGEST

    folders = []
    for name in ("humaneval-a.xml", "humaneval-b.xml"):
        folder = tmp_path / name.removesuffix(".xml")
        folder.mkdir()
        (folder / name).write_bytes((INGEST / "junit" / name).read_bytes())
        folders.append(str(folder))
    stored = junit_store(tmp_path)
    from_store = section(ok(["changes", "ja", "jb", "--store", str(stored), "--event", "missed"]).out)
    from_folders = section(ok(["changes", *folders, "--event", "missed"]).out)
    assert from_folders == from_store


@pytest.mark.parametrize("verb", TWO_RUNS)
def test_bd_1e_the_labels_are_the_verbs_own(verb: str) -> None:
    got = section(ok(argv_of(verb, PROVE_013)).out)
    a, b = LABELS[verb]
    assert got[4] == f"| kind | {a} | {a} share | {b} | {b} share | change |"
