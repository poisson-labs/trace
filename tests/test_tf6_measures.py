"""TF6-25 to TF6-29: the continuous measures and the failure types in the verdict (spec sections
18.5, 18.6 with CS1 to CS14 as ruled, 18.7.2 step 16; rulings CT2, CB2, HY1, SA11).

- TF6-25: ``fix-check --measures`` prints the continuous-measures table (TF23's ``table``) and each
  measure's lines in a section of its report, ``## Time, length, tokens and cost``, right before
  ``## What this cannot say``; nothing else printed moves (SV2). ``--json`` gains
  ``continuous_measures``, TF23's ``Comparison.to_dict()``, before ``next``. The comparison is
  TF23's ``compare`` over TF21's ``read_rows`` and ``version_of`` of the two runs, every shared
  case (SV6), labelled ``old`` and ``new``, at the verb's ``--alpha``.
- TF6-26: ``--max-change measure=N%`` (repeatable) sets a measure's ceiling and implies
  ``--measures``; ``trace.toml``'s ``[check] max_change`` sets them too, a flag winning for its
  measure; a bad value is a wrong command line (exit 2), a bad config value a refusal (exit 1)
  naming its line; ``total_tokens`` takes none (CB2).
- TF6-27: HY1: a near-zero old mean leaves the relative change out instead of raising, through
  ``compare`` and through the verb. (``test_hy11_finding_hy1_…`` in ``test_hy_statistics.py`` is a
  strict expected failure; Session B removes its mark in the commit that fixes it.)
- TF6-28: the saved verdict of each verb of two runs carries ``continuous_measures`` whether or not
  ``--measures`` was given, the config's ceilings applied, and ``failure_taxonomy_diff``: each
  run's taxonomy digest, whether the rules are the same, the tries, and the count of each failure
  kind and signal in each run, in section 18.5.1's order.
- TF6-29: runs classified by different rules are not refused (SA11's deferral, SV9): the diff
  says so, gives no counts, and ``note`` carries a sentence saying so.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import pytest
from tf0_support import TAU2, TAU2_A, TAU2_B, trace
from tf6_support import (
    AFTER_ID, ARMS, BEFORE_ID, LABELS, TWO_RUNS, argv012, junit_store, measures_store, result_of,
    run_ok, store012, table_store, the_artifact, write,
)

from poisson_trace.ingest.rows import FAILURE_KINDS, SIGNALS

HEADING = "## Time, length, tokens and cost"
CANNOT = "## What this cannot say"


class Pair:
    """Two runs and the fix-check that reads them: the small synthetic store in the pull-request
    lane (``measures_store``: a tested call, an identical measure, a quiet one, a few changed
    and total tokens), and its slow twin, the committed tau2 pair, 200 tries a run."""

    def __init__(self, store: Path, a: str, b: str, events: list[str], ceiling: str) -> None:
        self.store, self.a, self.b, self.events = store, a, b, events
        self.argv = ["fix-check", a, b, "--store", str(store), *[x for e in events for x in ("--event", e)],
                     "--inputs", "all", "--max-mde", ceiling]

    def ref(self, **kw: Any) -> Any:
        return reference(self.store, self.a, self.b, self.events, **kw)


@pytest.fixture(params=["small", pytest.param("tau2", marks=pytest.mark.slow)])
def pair(request: pytest.FixtureRequest, tmp_path: Path) -> Pair:
    if request.param == "small":
        return Pair(measures_store(tmp_path), "old", "new", ["missed"], "0.5")
    return Pair(TAU2, TAU2_A, TAU2_B, ["unsolved"], "0.2")


def reference(store: Path, a: str, b: str, events: list[str], labels: tuple[str, str] = ("old", "new"),
              ceilings: dict[str, float] | None = None, alpha: float = 0.05) -> Any:
    """The comparison the verb must print and save: TF23's compare over TF21's rows."""
    from poisson_trace.ingest.prove import read_rows
    from poisson_trace.ingest.tries import version_of
    from poisson_trace.stats.continuous import compare

    va = version_of(read_rows(Path(store), a, events), a, labels[0])
    vb = version_of(read_rows(Path(store), b, events), b, labels[1])
    return compare(va, vb, ceilings=ceilings, alpha=alpha)


def section(comparison: Any) -> str:
    """The section as TF6 prints it: the heading, the table, and each measure shown with its
    lines, in the table's order."""
    from poisson_trace import look
    from poisson_trace.stats.continuous import table

    header, rows = table(comparison)
    bullets = [f"- {row[0]}: " + " ".join(comparison.measures[row[0]].lines) for row in rows]
    body = look.table(header, rows) if rows else "No try in either run recorded a time, a length, tokens or a cost."
    return f"{HEADING}\n\n{body.rstrip(chr(10))}\n\n" + ("\n".join(bullets) + "\n\n" if bullets else "")


# ---------- TF6-25 ----------


def test_tf6_25_measures_adds_one_section_before_what_it_cannot_say(pair: Pair) -> None:
    plain = run_ok(pair.argv)
    shown = run_ok([*pair.argv, "--measures"])
    want = section(pair.ref())
    assert want in shown.out
    assert shown.out.index(want) + len(want) == shown.out.index(CANNOT)
    assert shown.out.replace(want, "", 1) == plain.out
    assert HEADING not in plain.out


def test_tf6_25_the_json_gains_continuous_measures_before_next(pair: Pair) -> None:
    printed = run_ok([*pair.argv, "--json"]).json()
    shown = run_ok([*pair.argv, "--measures", "--json"]).json()
    assert list(shown)[-2:] == ["continuous_measures", "next"]
    assert {k: v for k, v in shown.items() if k != "continuous_measures"} == printed
    assert shown["continuous_measures"] == pair.ref().to_dict()
    assert "continuous_measures" not in printed


def test_tf6_25_the_level_is_the_verbs_alpha(pair: Pair) -> None:
    shown = run_ok([*pair.argv, "--measures", "--alpha", "0.1", "--json"]).json()
    assert shown["continuous_measures"] == pair.ref(alpha=0.1).to_dict()


def test_tf6_25_the_small_store_shows_every_kind_of_reading(tmp_path: Path) -> None:
    """The fast store is worth its place: each status TF23 reads is in its table."""
    ref = Pair(measures_store(tmp_path), "old", "new", ["missed"], "0.5").ref()
    statuses = {m.measure: (m.status, m.verdict) for m in ref.measures.values()}
    assert statuses["wall_time_s"] == ("tested", "different")
    assert statuses["output_chars"][0] == "identical" and statuses["output_tokens"][0] == "few_changed"
    assert statuses["input_tokens"] == ("tested", "too small to tell") and statuses["total_tokens"][0] == "not_tested"


def test_tf6_25_every_shared_case_is_read_whatever_inputs_are_compared(tmp_path: Path) -> None:
    store = measures_store(tmp_path)
    csv = write(tmp_path / "sel.csv", "case,outcome\n" + "".join(f"c{j},{'failed' if j < 3 else 'passed'}\n" for j in range(16)))
    assert trace(["import", "table", str(csv), "--store", str(store), "--run", "sel", "--case-column", "case",
                  "--outcome-column", "outcome", "--failed", "failed", "--started", "2026-10-30T10:00:00Z"]).code == 0
    argv = ["fix-check", "old", "new", "--store", str(store), "--event", "missed", "--failing-from", "sel",
            "--max-mde", "0.5", "--measures", "--json"]
    shown = run_ok(argv).json()
    assert shown["inputs"]["compared"] == 3
    assert shown["continuous_measures"] == reference(store, "old", "new", ["missed"]).to_dict()


@pytest.mark.slow
def test_tf6_25_every_shared_case_is_read_on_tau2(tmp_path: Path) -> None:
    from tf0_support import PILOT

    argv = ["fix-check", TAU2_B, PILOT, "--store", str(TAU2), "--event", "unsolved", "--failing-from", TAU2_A,
            "--max-mde", "0.2", "--measures", "--json"]
    shown = run_ok(argv).json()
    assert shown["continuous_measures"] == reference(TAU2, TAU2_B, PILOT, ["unsolved"]).to_dict()


def test_tf6_25_a_run_pair_with_nothing_recorded_says_so(tmp_path: Path) -> None:
    store = tmp_path / "s"
    for i, run in enumerate(("p", "q")):
        csv = write(tmp_path / f"{run}.csv", "case,outcome\n" + "".join(f"c{j},{'failed' if j % 3 == i else 'passed'}\n" for j in range(12)))
        assert trace(["import", "table", str(csv), "--store", str(store), "--run", run, "--case-column", "case",
                      "--outcome-column", "outcome", "--failed", "failed", "--started", f"2026-11-0{i + 1}T10:00:00Z"]).code == 0
    argv = ["fix-check", "p", "q", "--store", str(store), "--event", "missed", "--inputs", "all", "--max-mde", "0.5"]
    plain, shown = run_ok(argv), run_ok([*argv, "--measures"])
    want = section(reference(store, "p", "q", ["missed"]))
    assert "No try in either run recorded" in want and want in shown.out
    assert shown.out.replace(want, "", 1) == plain.out


# ---------- TF6-26 ----------


def test_tf6_26_max_change_sets_a_ceiling_and_shows_the_table(pair: Pair) -> None:
    given = [*pair.argv, "--max-change", "wall_time_s=10%", "--max-change", "input_tokens=5%"]
    shown = run_ok([*given, "--json"]).json()
    ref = pair.ref(ceilings={"wall_time_s": 0.10, "input_tokens": 0.05})
    assert shown["continuous_measures"] == ref.to_dict()
    assert section(ref) in run_ok(given).out


@pytest.mark.parametrize("value", ["wall_time_s", "wall_time_s=10", "speed=10%", "wall_time_s=0%", "total_tokens=10%", "wall_time_s=-5%"])
def test_tf6_26_a_bad_max_change_is_a_wrong_command_line(tmp_path: Path, value: str) -> None:
    argv = Pair(measures_store(tmp_path), "old", "new", ["missed"], "0.5").argv
    # the control: the option is there, and a good value is taken
    assert trace([*argv, "--max-change", "wall_time_s=10%"]).code == 0
    ran = trace([*argv, "--max-change", value])
    assert ran.code == 2 and ran.out == "", ran.text
    assert "--max-change" in ran.err


def test_tf6_26_the_config_sets_ceilings_and_a_flag_wins_for_its_measure(pair: Pair, tmp_path: Path) -> None:
    config = write(tmp_path / "trace.toml",
                   'version = 1\n\n[check]\nmax_change = { wall_time_s = "20%", output_tokens = "5%" }\n')
    shown = run_ok([*pair.argv, "--config", str(config), "--max-change", "wall_time_s=10%", "--json"]).json()
    assert shown["continuous_measures"] == pair.ref(ceilings={"wall_time_s": 0.10, "output_tokens": 0.05}).to_dict()
    only_config = run_ok([*pair.argv, "--config", str(config), "--measures", "--json"]).json()
    assert only_config["continuous_measures"] == pair.ref(ceilings={"wall_time_s": 0.20, "output_tokens": 0.05}).to_dict()


@pytest.mark.parametrize("text,line", [
    ('version = 1\n\n[check]\nmax_change = { speed = "10%" }\n', 4),
    ('version = 1\n\n[check]\nmax_change = { wall_time_s = "ten" }\n', 4),
    ('version = 1\n\n[check]\nmax_change = { total_tokens = "10%" }\n', 4),
    ('version = 1\n\n[check]\nmax_change = "wall_time_s=10%"\n', 4),
    ('version = 1\n\n[check]\nmax_change = { wall_time_s = 0.1 }\n', 4),
])
def test_tf6_26_a_bad_config_value_is_refused_naming_its_line(tmp_path: Path, text: str, line: int) -> None:
    argv = Pair(measures_store(tmp_path), "old", "new", ["missed"], "0.5").argv
    good = write(tmp_path / "good.toml", 'version = 1\n\n[check]\nmax_change = { wall_time_s = "10%" }\n')
    assert trace([*argv, "--config", str(good)]).code == 0
    config = write(tmp_path / "trace.toml", text)
    ran = trace([*argv, "--config", str(config)])
    assert ran.code == 1 and ran.out == "", ran.text
    first = ran.err.splitlines()[0]
    assert first.startswith("error: ") and f"line {line}" in first and "max_change" in first, first


def test_tf6_26_the_config_key_is_a_setting_doctor_accepts(tmp_path: Path) -> None:
    from poisson_trace import config as cfg

    store = store012(tmp_path)
    path = write(tmp_path / "trace.toml", f'version = 1\n\n[store]\npath = "{store}"\n\n[events]\nfailed = ["violated"]\n\n[check]\nmax_change = {{ wall_time_s = "10%", cost_usd = "2.5%" }}\n')
    held = cfg.load(str(path))
    assert held is not None and held.max_change == {"wall_time_s": 0.10, "cost_usd": 0.025}
    bare = cfg.load(str(write(tmp_path / "bare.toml", "version = 1\n")))
    assert bare is not None and bare.max_change == {}
    doc = json.loads(trace(["doctor", "--config", str(path), "--json"]).out)
    assert next(c for c in doc["checks"] if c["name"] == "config")["ok"] is True, doc


# ---------- TF6-27: HY1 ----------


def _versions(old: list[float], new: list[float]) -> tuple[Any, Any]:
    from poisson_trace.stats.continuous import Try, Version

    def v(name: str, label: str, values: list[float]) -> Any:
        return Version(name, {f"c{i}": (Try({"cost_usd": x}),) for i, x in enumerate(values)}, label)

    return v("a", "old", old), v("b", "new", new)


NEAR_ZERO = [
    # HY11's shrunk example: one case
    ([2.225073858507203e-309], [1.0]),
    # the smallest float, under the floor
    ([5e-324] * 4, [1.0, 2.0, 3.0, 4.0]),
    # tested, called different
    ([1e-310 * (i + 1) for i in range(12)], [1.0 + 0.01 * i for i in range(12)]),
    # tested and quiet: the smallest catchable change's share and, with a ceiling, the cases
    # needed are read against the old mean too (SV11)
    ([1e-310 * (i + 1) for i in range(20)], [1e-3 * (i + 1) * (-1) ** i for i in range(20)]),
]


@pytest.mark.parametrize("ceiling", [None, 0.1])
@pytest.mark.parametrize("old,new", NEAR_ZERO)
def test_tf6_27_a_near_zero_old_mean_gives_no_relative_change(old: list[float], new: list[float], ceiling: float | None) -> None:
    from poisson_trace.stats.continuous import compare, table

    comparison = compare(*_versions(old, new), ceilings=None if ceiling is None else {"cost_usd": ceiling})
    m = comparison.measures["cost_usd"]
    assert m.relative is None or math.isfinite(m.relative)
    # every line stays a line: none past section 11.2's 400 characters
    assert all(len(line) <= 400 for line in m.lines), [len(line) for line in m.lines]
    text = " ".join(m.lines) + json.dumps(comparison.to_dict(), allow_nan=False)
    header, rows = table(comparison, technical=True)
    text += " ".join(cell for row in rows for cell in row)
    assert not re.search(r"\b(inf|infinity|nan)\b", text, re.IGNORECASE), text


def test_tf6_27_the_verb_answers_on_a_near_zero_old_cost(tmp_path: Path) -> None:
    old = {f"c{i}": [1e-310 * (i + 1)] for i in range(12)}
    new = {f"c{i}": [1.0 + 0.01 * i] for i in range(12)}
    store = table_store(tmp_path, old, new)
    ran = run_ok(["fix-check", "old", "new", "--store", str(store), "--event", "missed", "--inputs", "all",
                  "--max-mde", "0.5", "--measures"])
    row = next(line for line in ran.out.splitlines() if line.startswith("| cost_usd"))
    change = [c.strip() for c in row.strip("|").split("|")][3]
    assert "%" not in change, row


# ---------- TF6-28 ----------


def _counts(store: Path, run: str, events: list[str]) -> tuple[dict[str, int], dict[str, int], int]:
    from poisson_trace.ingest.prove import read_rows

    rows = read_rows(store, run, events)
    kinds = {k: sum(1 for r in rows if r.failure_kind == k) for k in FAILURE_KINDS}
    signals = {s: sum(1 for r in rows if s in r.signals) for s in SIGNALS}
    return kinds, signals, len(rows)


@pytest.mark.parametrize("verb", TWO_RUNS)
def test_tf6_28_the_saved_verdict_carries_both(tmp_path: Path, verb: str) -> None:
    from poisson_trace.ingest.taxonomy import taxonomy_sha256

    store = store012(tmp_path)
    run_ok(argv012(verb, store, "--save"))
    result = result_of(the_artifact(store, verb))
    a, b = ARMS[verb]
    events = ["violated", "timeout"]
    ref = reference(store, BEFORE_ID, AFTER_ID, events, labels=LABELS[verb])
    assert result["continuous_measures"] == ref.to_dict()
    built_in = taxonomy_sha256((), None)
    diff = result["failure_taxonomy_diff"]
    assert list(diff) == ["taxonomy_sha256", "same_rules", "tries", "kinds", "signals"]
    assert diff["taxonomy_sha256"] == {a: built_in, b: built_in} and diff["same_rules"] is True
    ka, sa, na = _counts(store, BEFORE_ID, events)
    kb, sb, nb = _counts(store, AFTER_ID, events)
    assert diff["tries"] == {a: na, b: nb} == {a: 160, b: 160}
    assert diff["kinds"] == [{"failure_kind": k, a: ka[k], b: kb[k]} for k in FAILURE_KINDS if ka[k] or kb[k]]
    assert diff["signals"] == [{"signal": s, a: sa[s], b: sb[s]} for s in SIGNALS if sa[s] or sb[s]]
    # the committed store's counts, as TF21's follow-up recorded them (SB2)
    assert {d["failure_kind"]: (d[a], d[b]) for d in diff["kinds"]} == {
        "loop_detected": (6, 15), "step_limit": (0, 5), "tool_error": (66, 21)}


def test_tf6_28_where_carries_neither(tmp_path: Path) -> None:
    store = store012(tmp_path)
    run_ok(argv012("where", store, "--save"))
    result = result_of(the_artifact(store, "where"))
    assert "failure_taxonomy_diff" not in result and "continuous_measures" not in result


def test_tf6_28_the_configs_ceilings_reach_the_saved_measures(tmp_path: Path) -> None:
    store = store012(tmp_path)
    config = write(tmp_path / "trace.toml", 'version = 1\n\n[check]\nmax_change = { wall_time_s = "15%" }\n')
    run_ok([*argv012("fix-check", store), "--config", str(config), "--save"])
    result = result_of(the_artifact(store, "fix-check"))
    ref = reference(store, BEFORE_ID, AFTER_ID, ["violated", "timeout"], ceilings={"wall_time_s": 0.15})
    assert result["continuous_measures"] == ref.to_dict()
    from tf6_support import descriptor

    settings = descriptor(the_artifact(store, "fix-check"))["settings"]
    assert settings["max_change"] == {"wall_time_s": 0.15} and settings["from"]["max_change"] == "trace.toml"


def test_tf6_28_imported_runs_carry_their_import_digest(tmp_path: Path) -> None:
    from poisson_prove.store import Store

    store = junit_store(tmp_path)
    run_ok(["fix-check", "ja", "jb", "--store", str(store), "--event", "missed", "--inputs", "all",
            "--max-mde", "0.2", "--save"])
    diff = result_of(the_artifact(store, "fix-check"))["failure_taxonomy_diff"]
    digests = {arm: Store(store).manifest(run).environment["import"]["taxonomy_sha256"]
               for arm, run in (("old", "ja"), ("new", "jb"))}
    assert diff["taxonomy_sha256"] == digests and diff["same_rules"] is True


# ---------- TF6-29 ----------


def test_tf6_29_runs_under_different_rules_are_not_refused_and_say_so(tmp_path: Path) -> None:
    rules = write(tmp_path / "rules.toml",
                  'version = 1\n\n[[taxonomy.rules]]\nfailure_kind = "crash"\nwhen_error_matches = "AssertionError"\n')
    store = tmp_path / "s"
    from tf6_support import JUNIT

    for i, (run, extra) in enumerate((("ja", []), ("jb", ["--config", str(rules)]))):
        made = trace(["import", "junit", str(JUNIT / f"humaneval-{'ab'[i]}.xml"), "--store", str(store), "--run", run,
                      "--started", f"2026-11-0{i + 1}T10:00:00Z", *extra])
        assert made.code == 0, made.text
    argv = ["fix-check", "ja", "jb", "--store", str(store), "--event", "missed", "--inputs", "all", "--max-mde", "0.2"]
    plain = run_ok(argv)
    saved = run_ok([*argv, "--save"])
    assert saved.out.splitlines()[0] == plain.out.splitlines()[0]
    result = result_of(the_artifact(store, "fix-check"))
    diff = result["failure_taxonomy_diff"]
    assert diff["same_rules"] is False
    assert diff["taxonomy_sha256"]["old"] != diff["taxonomy_sha256"]["new"]
    assert diff["kinds"] is None and diff["signals"] is None
    from poisson_trace.ingest.prove import read_rows

    assert diff["tries"] == {"old": len(read_rows(store, "ja", ["missed"])), "new": len(read_rows(store, "jb", ["missed"]))}
    assert any("different rules" in n for n in result["note"]), result["note"]
