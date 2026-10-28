"""TR37 to TR42, TR50 (the verdict), TR54, TR55, TR56 (compare), TR61 to TR65 and TR70: the
``fix-check`` command line on synthetic stores written through Prove, and on the committed
fixtures where a real store is the point. Every test makes at least one call that must print a
report before it checks anything else, so none is green on a build without the verb."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from conftest import (
    FIXTURES, TAU2, TAU2_A, TAU2_B, chdir, compare, deaths_rows, norm,
)
from fixcheck_support import (
    BANNED, BY_INPUT_KEYS, CHANGES_BLOCK_KEYS, CONSISTENCY_KEYS, CONTROL_KEYS, DIFFERENCE_KEYS,
    FIX_KEYS, FLAG_ROW_KEYS, GUIDANCE_KEYS, HE_A, HE_B, HE_EVENTS, HEADER_KEYS, HUMANEVAL, INPUTS_KEYS,
    LIMITS_KEYS, PILOT, POINTER, ROWS_KEYS, SPEC_CANNOT_SAY, SPEC_LEFT_OUT, TAU2_EVENTS, TEST_KEYS,
    VERDICT_PHRASES, WORKED, Obs, build_run, changes, counts_of, exact_p_enumerated, fix_check, ok,
    one_sentence, pair_store, rebuild, scrambles,
)

MAX = ("--max-mde", "0.5")
ALL = ("--inputs", "all")


def _json(result):  # type: ignore[no-untyped-def]
    ok(result)
    return result.json()


# ---------- the TR70 store ----------

T0 = "2026-01-01T00:00:00.000000Z"
T1 = "2026-01-02T01:30:00.000000Z"  # 25 h 30 min after T0


def tr70_store(root: Path) -> Path:
    """A selecting run ``sel``, an old arm ``old`` (declared 3 repeats) and a new arm ``new``
    (declared 2). Every count the tests read off it follows from these rows:

    input  sel        old                              new
    in1    F .        F . F + timed out                . .          compared; old mixed; unbalanced 4 rows vs 2
    in2    F          (absent)                         . .          not re-run on the old version
    in3    F F        F F . . .                        F F          compared; unbalanced 5 vs 2
    in4    F          . .                              (absent)     not re-run on the new version
    in5    F          F . + no outcome                 . .          compared; old short (2 of 3)
    in6    F          no outcome only                  . .          no outcome on the old version
    in7    . .        F F                              . .          not selected by sel; compared under --inputs all
    in8    F          F .                              timed out    no outcome on the new version

    The new arm holds two outcome rows on every compared input and no mixed input: an arm of
    copies."""
    F, P = "fail", "ok"
    sel = [("in1", F), ("in1", P), ("in2", F), ("in3", F), ("in3", F), ("in4", F), ("in5", F),
           ("in6", F), ("in7", P), ("in7", P), ("in8", F)]
    old = [("in1", F), ("in1", P), ("in1", F), ("in1", None, "timeout"),
           ("in3", F), ("in3", F), ("in3", P), ("in3", P), ("in3", P),
           ("in4", P), ("in4", P),
           ("in5", F), ("in5", P), ("in5", None, "infra: container lost"),
           ("in6", None, "boom"),
           ("in7", F), ("in7", F),
           ("in8", F), ("in8", P)]
    new = [("in1", P), ("in1", P), ("in2", P), ("in2", P), ("in3", F), ("in3", F),
           ("in5", P), ("in5", P), ("in6", P), ("in6", P), ("in7", P), ("in7", P),
           ("in8", None, "timeout")]

    def rows(spec):  # type: ignore[no-untyped-def]
        seen: dict[str, int] = {}
        out = []
        for item in spec:
            name, outcome = item[0], item[1]
            error = item[2] if len(item) > 2 else None
            rep = seen.get(name, 0)
            seen[name] = rep + 1
            out.append(Obs(name, outcome, error, replicate_index=rep, seed=7 * rep + len(name)))
        return out

    build_run(root, "sel", rows(sel), created_at="2025-12-31T00:00:00.000000Z")
    build_run(root, "old", rows(old), replicates=3, created_at=T0)
    build_run(root, "new", rows(new), replicates=2, created_at=T1)
    return root


@pytest.fixture
def store70(tmp_path: Path) -> Path:
    return tr70_store(tmp_path / "tr70")


def _sel(root: Path, *extra: str):  # type: ignore[no-untyped-def]
    return fix_check(root, "old", "new", ["fail"], "--failing-from", "sel", *MAX, *extra)


# ---------- TR70 (and TR37, TR38, TR42, TR65 on it) ----------


def test_tr70_every_header_count_by_construction(store70: Path) -> None:
    d = _json(_sel(store70, "--json"))
    assert d["inputs"] == {
        "rule": "failing-from", "failing_from": "sel", "min_failures": 1, "selected": 7,
        "compared": 3, "informative": d["inputs"]["informative"],
        "left_out": {reason: 1 for reason in SPEC_LEFT_OUT},
    }
    assert d["rows"]["old"] == {"runs": 10, "failed": 5, "timed_out": 1, "no_outcome": 1, "short": 1, "mixed": 3}
    assert d["rows"]["new"] == {"runs": 6, "failed": 2, "timed_out": 0, "no_outcome": 0, "short": 0, "mixed": 0}
    assert d["runs"]["old"]["declared_repeats"] == 3 and d["runs"]["new"]["declared_repeats"] == 2
    assert d["gap_seconds"] == pytest.approx(91800.0, abs=1e-6)
    tab = [(2, 3, 0, 2), (2, 5, 2, 2), (1, 2, 0, 2)]  # in1, in3, in5
    assert d["test"]["observed_new"] == 2
    assert d["test"]["p"] == pytest.approx(exact_p_enumerated(tab), abs=1e-12)
    assert d["inputs"]["informative"] == 3
    assert d["control"]["old_did_not_fail_share"] == pytest.approx(0.5, abs=1e-12)
    assert d["control"]["new_did_not_fail_share"] == pytest.approx(4 / 6, abs=1e-12)


def test_tr70_min_failures_narrows_the_selection(store70: Path) -> None:
    d = _json(_sel(store70, "--min-failures", "2", "--json"))
    assert (d["inputs"]["selected"], d["inputs"]["compared"], d["inputs"]["min_failures"]) == (1, 1, 2)
    assert d["rows"]["old"]["runs"] == 5 and d["rows"]["new"]["runs"] == 2


def test_tr70_inputs_all_compares_every_input_with_an_outcome_in_both(store70: Path) -> None:
    d = _json(fix_check(store70, "old", "new", ["fail"], *ALL, *MAX, "--json"))
    inputs = d["inputs"]
    assert (inputs["rule"], inputs["failing_from"], inputs["min_failures"]) == ("all", None, None)
    assert inputs["compared"] == 4
    assert set(inputs["left_out"]) == set(SPEC_LEFT_OUT)
    assert inputs["selected"] == inputs["compared"] + sum(inputs["left_out"].values())
    assert inputs["left_out"]["no outcome on the old version"] == 1
    assert inputs["left_out"]["no outcome on the new version"] == 1
    assert d["rows"]["old"] == {"runs": 12, "failed": 7, "timed_out": 1, "no_outcome": 1, "short": 2, "mixed": 3}
    assert d["rows"]["new"] == {"runs": 8, "failed": 2, "timed_out": 0, "no_outcome": 0, "short": 0, "mixed": 0}


def test_tr70_inputs_all_counts_an_input_carried_by_one_run_as_left_out(store70: Path) -> None:
    """Session A ruling 1, ruled yes 2026-09-29: under ``--inputs all`` the selection is every
    input either run carries, and an input in one run only is left out under the first reason of
    section 3.3 that applies (in2 is in the new arm only, in4 in the old arm only)."""
    d = _json(fix_check(store70, "old", "new", ["fail"], *ALL, *MAX, "--json"))
    assert d["inputs"]["selected"] == 8
    assert d["inputs"]["left_out"] == {
        "not re-run on the old version": 1, "not re-run on the new version": 1,
        "no outcome on the old version": 1, "no outcome on the new version": 1,
    }
    assert d["inputs"]["compared"] == 4


# ---------- TR37 ----------


def test_tr37_a_row_failed_exactly_when_its_outcome_is_an_event(tmp_path: Path) -> None:
    rows_old = [Obs("a", "crash", replicate_index=0), Obs("a", "wrong", replicate_index=1),
                Obs("a", "ok", replicate_index=2), Obs("a", "other", replicate_index=3)]
    rows_new = [Obs("a", "ok", replicate_index=0), Obs("a", "wrong", replicate_index=1),
                Obs("a", "ok", replicate_index=2), Obs("a", "ok", replicate_index=3)]
    build_run(tmp_path, "old", rows_old)
    build_run(tmp_path, "new", rows_new, created_at="2026-01-01T00:10:00.000000Z")
    two = _json(fix_check(tmp_path, "old", "new", ["crash", "wrong"], *ALL, *MAX, "--json"))
    assert (two["rows"]["old"]["failed"], two["rows"]["new"]["failed"]) == (2, 1)
    one = _json(fix_check(tmp_path, "old", "new", ["wrong"], *ALL, *MAX, "--json"))
    assert (one["rows"]["old"]["failed"], one["rows"]["new"]["failed"]) == (1, 1)
    assert one["rows"]["old"]["runs"] == 4


def test_tr37_rows_with_no_outcome_are_in_no_count_and_the_rows_add_up(store70: Path) -> None:
    from poisson_prove.store import Store

    d = _json(_sel(store70, "--json"))
    store = Store(store70)
    compared = {"in1", "in3", "in5"}
    for arm in ("old", "new"):
        frame = store.read(arm, meta=False, trace="none")
        stored = sum(1 for c in frame["config"] if c["input"] in compared)
        r = d["rows"][arm]
        assert r["runs"] + r["timed_out"] + r["no_outcome"] == stored
    assert d["rows"]["old"]["runs"] == 10  # the timed-out and the infra row of in1 and in5 are not runs


def test_tr37_timed_out_and_no_outcome_are_counted_apart(tmp_path: Path) -> None:
    old = [Obs("a", "fail", replicate_index=0), Obs("a", "ok", replicate_index=1),
           Obs("a", None, "timeout", replicate_index=2), Obs("a", None, "timeout", replicate_index=3),
           Obs("a", None, "infra: container lost", replicate_index=4)]
    new = [Obs("a", "ok", replicate_index=0), Obs("a", None, "boom", replicate_index=1),
           Obs("a", None, "worker exited", replicate_index=2), Obs("a", None, "timeout", replicate_index=3)]
    build_run(tmp_path, "old", old)
    build_run(tmp_path, "new", new, created_at="2026-01-01T00:10:00.000000Z")
    d = _json(fix_check(tmp_path, "old", "new", ["fail"], *ALL, *MAX, "--json"))
    assert (d["rows"]["old"]["runs"], d["rows"]["old"]["timed_out"], d["rows"]["old"]["no_outcome"]) == (2, 2, 1)
    assert (d["rows"]["new"]["runs"], d["rows"]["new"]["timed_out"], d["rows"]["new"]["no_outcome"]) == (1, 1, 2)


def test_tr37_the_same_numbers_on_runs_whose_traces_are_all_null(tmp_path: Path) -> None:
    from poisson_prove.store import Store

    bare = tmp_path / "bare"
    for run in (TAU2_A, TAU2_B):
        rebuild(TAU2, run, bare)
        assert all(e is None for e in Store(bare).read(run, meta=False, trace="envelope")["trace"])
    with_traces = _json(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.12", "--json"))
    without = _json(fix_check(bare, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.12", "--json"))
    with_traces.pop("prove")
    without.pop("prove")
    # next: carries the store's path, as prove does
    with_traces.pop("next")
    without.pop("next")
    assert with_traces == without


# ---------- TR38 ----------


def test_tr38_selection_is_by_failed_rows_in_the_selecting_run(tmp_path: Path) -> None:
    sel = [Obs("a", "fail", replicate_index=0), Obs("a", "fail", replicate_index=1),
           Obs("b", "fail", replicate_index=0), Obs("b", "ok", replicate_index=1),
           Obs("c", "ok", replicate_index=0), Obs("c", "crash", replicate_index=1)]
    arm = [Obs(x, o, replicate_index=j) for x in "ab" for j, o in enumerate(("fail", "ok"))]
    arm += [Obs("c", "crash", replicate_index=0), Obs("c", "ok", replicate_index=1)]
    build_run(tmp_path, "sel", sel)
    build_run(tmp_path, "old", arm)
    build_run(tmp_path, "new", arm)
    one = _json(fix_check(tmp_path, "old", "new", ["fail"], "--failing-from", "sel", *MAX, "--json"))
    assert (one["inputs"]["selected"], one["inputs"]["compared"]) == (2, 2)
    two = _json(fix_check(tmp_path, "old", "new", ["fail"], "--failing-from", "sel", "--min-failures", "2", *MAX, "--json"))
    assert (two["inputs"]["selected"], two["inputs"]["compared"]) == (1, 1)
    both = _json(fix_check(tmp_path, "old", "new", ["fail", "crash"], "--failing-from", "sel", *MAX, "--json"))
    assert both["inputs"]["selected"] == 3


def test_tr38_each_left_out_input_is_counted_under_the_first_reason(tmp_path: Path) -> None:
    # "z" is absent from both arms: counted once, as not re-run on the old version.
    # "y" has only no-outcome rows in both arms: counted once, as no outcome on the old version.
    sel = [Obs(x, "fail") for x in ("x", "y", "z")]
    old = [Obs("x", "fail"), Obs("x", "ok", replicate_index=1), Obs("y", None, "timeout")]
    new = [Obs("x", "ok"), Obs("x", "ok", replicate_index=1), Obs("y", None, "boom")]
    build_run(tmp_path, "sel", sel)
    build_run(tmp_path, "old", old)
    build_run(tmp_path, "new", new)
    d = _json(fix_check(tmp_path, "old", "new", ["fail"], "--failing-from", "sel", *MAX, "--json"))
    assert d["inputs"]["left_out"] == {
        "not re-run on the old version": 1, "not re-run on the new version": 0,
        "no outcome on the old version": 1, "no outcome on the new version": 0,
    }
    assert (d["inputs"]["selected"], d["inputs"]["compared"]) == (3, 1)


# ---------- TR39 ----------


def test_tr39_the_input_rule_is_required_and_exclusive(store70: Path) -> None:
    ok(_sel(store70))
    one_sentence(fix_check(store70, "old", "new", ["fail"], *MAX))
    one_sentence(fix_check(store70, "old", "new", ["fail"], "--failing-from", "sel", *ALL, *MAX))
    one_sentence(fix_check(store70, "old", "new", ["fail"], "--inputs", "some", *MAX))


def test_tr39_the_selecting_run_cannot_be_an_arm(store70: Path) -> None:
    """Sole catch for a build that accepts the selecting run as the old arm."""
    ok(_sel(store70))
    one_sentence(fix_check(store70, "old", "new", ["fail"], "--failing-from", "old", *MAX))
    one_sentence(fix_check(store70, "old", "new", ["fail"], "--failing-from", "new", *MAX))
    ok(fix_check(TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.2"))
    one_sentence(fix_check(TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_B, "--max-mde", "0.2"))


def test_tr39_old_and_new_must_differ(store70: Path) -> None:
    ok(fix_check(store70, "old", "new", ["fail"], *ALL, *MAX))
    one_sentence(fix_check(store70, "old", "old", ["fail"], *ALL, *MAX))


def test_tr39_min_failures(store70: Path) -> None:
    ok(_sel(store70, "--min-failures", "1"))
    one_sentence(_sel(store70, "--min-failures", "0"))
    one_sentence(_sel(store70, "--min-failures", "-1"))
    one_sentence(fix_check(store70, "old", "new", ["fail"], *ALL, "--min-failures", "1", *MAX))


@pytest.mark.parametrize("value", [None, "0", "1", "1.5", "-0.1", "0.0"])
def test_tr39_max_mde_is_required_and_inside_zero_one(store70: Path, value: str | None) -> None:
    ok(_sel(store70))
    argv = ["--failing-from", "sel"] + ([] if value is None else ["--max-mde", value])
    one_sentence(fix_check(store70, "old", "new", ["fail"], *argv))


def test_tr39_no_input_left_to_compare(store70: Path, tmp_path: Path) -> None:
    ok(_sel(store70))
    one_sentence(_sel(store70, "--min-failures", "3"))
    build_run(tmp_path, "sel", [Obs("a", "fail")])
    build_run(tmp_path, "old", [Obs("a", "fail"), Obs("b", "ok")])
    build_run(tmp_path, "new", [Obs("b", "fail")])
    one_sentence(fix_check(tmp_path, "old", "new", ["fail"], "--failing-from", "sel", *MAX))


def test_tr39_events_are_the_first_slice_rule(store70: Path, tmp_path: Path) -> None:
    ok(_sel(store70))
    refused = fix_check(store70, "old", "new", ["nope"], "--failing-from", "sel", *MAX)
    one_sentence(refused)
    assert "fail" in refused.text and "ok" in refused.text
    build_run(tmp_path, "old", [Obs("a", "crash"), Obs("a", "ok", replicate_index=1)])
    build_run(tmp_path, "new", [Obs("a", "fail"), Obs("a", "ok", replicate_index=1)])
    ok(fix_check(tmp_path, "old", "new", ["crash", "fail"], *ALL, *MAX))


# ---------- TR40 ----------


def _same_bytes(tmp_path: Path, runs: list[tuple[Path, str]], argv_for, rng: np.random.Generator) -> None:  # type: ignore[no-untyped-def]
    plain, scrambled = tmp_path / "plain", tmp_path / "scrambled"
    for d in (plain, scrambled):
        d.mkdir(parents=True)
    for src, run in runs:
        rebuild(src, run, plain / "store")
        reindex, seeds = scrambles(src, run, rng)
        rebuild(src, run, scrambled / "store", reindex=reindex, seeds=seeds)
    outs = []
    for d in (plain, scrambled):
        with chdir(d):
            result = argv_for("store")
        ok(result)
        outs.append(result.out)
    assert outs[0] == outs[1]


def test_tr40_runs_are_not_replays_fix_check(tmp_path: Path) -> None:
    rng = np.random.default_rng(40)
    _same_bytes(tmp_path / "all", [(TAU2, TAU2_A), (TAU2, TAU2_B)],
                lambda s: fix_check(s, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.1", "--json"), rng)
    _same_bytes(tmp_path / "sel", [(TAU2, TAU2_A), (TAU2, TAU2_B), (TAU2, PILOT)],
                lambda s: fix_check(s, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.2", "--json"), rng)


def test_tr40_runs_are_not_replays_changes(tmp_path: Path) -> None:
    rng = np.random.default_rng(41)
    _same_bytes(tmp_path, [(TAU2, TAU2_A), (TAU2, TAU2_B)],
                lambda s: changes(s, TAU2_A, TAU2_B, TAU2_EVENTS, "--json"), rng)


def test_tr40_the_new_modules_read_neither_column() -> None:
    """In ``paired.py`` and ``cli.py``: no string constant ``"replicate_index"`` and no attribute
    of that name; no string constant ``"seed"`` except as a key of a dict literal (a report's
    ``{"seed": ...}``); no attribute ``.seed`` on anything but the parsed arguments ``ns``."""
    ok(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.1"))
    import poisson_trace

    here = Path(poisson_trace.__file__).resolve().parent
    for name in ("paired.py", "cli.py"):
        tree = ast.parse((here / name).read_text())
        dict_keys = {id(k) for node in ast.walk(tree) if isinstance(node, ast.Dict) for k in node.keys if k is not None}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "replicate_index":
                raise AssertionError(f"{name}:{node.lineno}: replicate_index")
            if isinstance(node, ast.Constant) and node.value == "seed" and id(node) not in dict_keys:
                raise AssertionError(f"{name}:{node.lineno}: 'seed' read")
            if isinstance(node, ast.Attribute) and node.attr == "replicate_index":
                raise AssertionError(f"{name}:{node.lineno}: .replicate_index")
            if isinstance(node, ast.Attribute) and node.attr == "seed":
                assert isinstance(node.value, ast.Name) and node.value.id == "ns", f"{name}:{node.lineno}: .seed"


# ---------- TR41 ----------


def _snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    out = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        st = path.stat()
        out[str(path.relative_to(root))] = (st.st_size, st.st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
    return out


def test_tr41_nothing_under_the_store_changes() -> None:
    before = _snapshot(FIXTURES)
    ok(fix_check(TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.2", "--json"))
    ok(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.1"))
    ok(changes(HUMANEVAL, HE_A, HE_B, HE_EVENTS))
    assert _snapshot(FIXTURES) == before


ALLOWED_PROVE_IMPORTS = {
    "poisson_prove": set(),
    "poisson_prove.store": {"Store", "RunManifest", "RunTally"},
    "poisson_prove.steps": {"declaration_check", "DeclarationCheck"},
    "poisson_prove.trace": {"KINDS"},
}


def test_tr41_every_read_is_a_prove_call() -> None:
    ok(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.1"))
    import poisson_trace

    for path in sorted(Path(poisson_trace.__file__).resolve().parent.glob("*.py")):
        text = path.read_text()
        assert "pyarrow" not in text and "from_dict" not in text, path.name
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name == "poisson_prove" or not alias.name.startswith("poisson_prove"), (path.name, alias.name)
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("poisson_prove"):
                assert node.module in ALLOWED_PROVE_IMPORTS, (path.name, node.module)
                assert {a.name for a in node.names} <= ALLOWED_PROVE_IMPORTS[node.module], (path.name, node.module)
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert "parquet" not in node.value.lower() and "manifest.json" not in node.value.lower(), path.name


def test_tr41_refusals_are_one_sentence_and_exit_one(store70: Path) -> None:
    ok(_sel(store70))
    one_sentence(fix_check(store70, "old", "nope", ["fail"], *ALL, *MAX))
    one_sentence(fix_check(store70, "old", "new", ["fail"], "--failing-from", "nope", *MAX))
    one_sentence(changes(store70, "old", "nope", ["fail"]))
    one_sentence(changes(store70, "old", "new", ["nope"]))
    no_event = changes(store70, "old", "new", [])  # R17: no --event is a wrong command line, exit 2
    no_event_lines = [line for line in no_event.text.splitlines() if line.strip()]
    assert no_event.code == 2 and no_event_lines and all(line.startswith("  next: ") for line in no_event_lines[1:]), no_event.text


def _sub(code: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120)


NEW_CALLS = (
    ["fix-check", "a", "b", "--store", "no-such-store", "--event", "fail", "--inputs", "all", "--max-mde", "0.2"],
    ["changes", "a", "b", "--store", "no-such-store", "--event", "fail"],
)


@pytest.mark.parametrize("argv", NEW_CALLS)
def test_tr41_without_prove_both_verbs_refuse_before_the_store(argv) -> None:  # type: ignore[no-untyped-def]
    ok(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.1"))
    code = f"import sys; sys.modules['poisson_prove'] = None; from poisson_trace.cli import main; sys.exit(main({argv!r}))"
    proc = _sub(code, dict(os.environ))
    lines = [line for line in (proc.stdout + proc.stderr).splitlines() if line.strip()]
    assert proc.returncode == 1 and lines and all(line.startswith("  next: ") for line in lines[1:]), proc.stdout + proc.stderr
    assert "poisson-prove" in lines[0] and "0.0.1" in lines[0] and "no-such-store" not in " ".join(lines)


@pytest.mark.parametrize("argv", NEW_CALLS)
def test_tr41_on_the_wrong_prove_both_verbs_refuse(tmp_path: Path, argv) -> None:  # type: ignore[no-untyped-def]
    ok(changes(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS))
    fake = tmp_path / "fake" / "poisson_prove"
    fake.mkdir(parents=True)
    (fake / "__init__.py").write_text('__version__ = "9.9.9"\n')
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path / "fake") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    proc = _sub(f"import sys; from poisson_trace.cli import main; sys.exit(main({argv!r}))", env)
    lines = [line for line in (proc.stdout + proc.stderr).splitlines() if line.strip()]
    assert proc.returncode == 1 and lines and all(line.startswith("  next: ") for line in lines[1:]), proc.stdout + proc.stderr
    assert "9.9.9" in lines[0] and "0.0.1" in lines[0]


# ---------- TR42 ----------


def test_tr42_declared_repeats_short_mixed_and_the_gap(tmp_path: Path) -> None:
    tab = [(2, 4, 1, 4), (4, 4, 0, 3), (0, 2, 1, 4)]
    pair_store(tmp_path, tab, old_created="2026-03-01T10:00:00.000000Z",
               new_created="2026-02-28T09:30:15.500000Z", replicates=(4, None))
    d = _json(fix_check(tmp_path, "old", "new", ["fail"], *ALL, *MAX, "--json"))
    assert d["runs"]["old"]["declared_repeats"] == 4
    assert d["runs"]["new"]["declared_repeats"] is None
    assert d["rows"]["old"]["short"] == 1 and d["rows"]["new"]["short"] == 0
    assert d["rows"]["old"]["mixed"] == 1 and d["rows"]["new"]["mixed"] == 2
    assert d["gap_seconds"] == pytest.approx(88184.5, abs=1e-6)
    assert d["runs"]["old"]["created_at"] == "2026-03-01T10:00:00.000000Z"
    assert set(d["runs"]["old"]) == HEADER_KEYS


def test_tr42_on_the_patched_pilot() -> None:
    d = _json(fix_check(TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.2", "--json"))
    assert (d["runs"]["old"]["declared_repeats"], d["runs"]["new"]["declared_repeats"]) == (4, 1)
    assert d["gap_seconds"] == pytest.approx(147031.906942, abs=1e-6)
    assert (d["rows"]["old"]["short"], d["rows"]["new"]["short"]) == (0, 0)
    assert (d["rows"]["old"]["mixed"], d["rows"]["new"]["mixed"]) == (4, 0)


# ---------- TR50 (the verdict) ----------


def test_tr50_the_by_input_line_never_enters_the_verdict(tmp_path: Path) -> None:
    """Sole catch for a build that gates on the smaller p."""
    strong = pair_store(tmp_path / "strong", [(15, 20, 2, 20)] * 3)  # exact p tiny; 3 moved, by-input >= 0.25
    d = _json(fix_check(strong, "old", "new", ["fail"], *ALL, *MAX, "--json"))
    assert d["test"]["p"] < 0.05 <= d["by_input"]["p"]
    assert d["verdict"] == "different"
    md = fix_check(strong, "old", "new", ["fail"], *ALL, *MAX)
    assert md.code == 0 and "different: the new version failed less on these inputs" in norm(md.out)
    broad = pair_store(tmp_path / "broad", [(10, 20, 11, 20)] * 14)  # 14 moved alike; exact p ~0.24
    e = _json(fix_check(broad, "old", "new", ["fail"], *ALL, *MAX, "--json"))
    assert e["by_input"]["p"] < 0.05 <= e["test"]["p"]
    assert e["verdict"] != "different"
    assert "different:" not in fix_check(broad, "old", "new", ["fail"], *ALL, *MAX).out


def test_tr50_the_draws_are_seeded_through_the_command_line() -> None:
    runs = [fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.1", "--json", "--seed", s) for s in ("0", "0", "1", "2")]
    for r in runs:
        ok(r)
    assert runs[0].out == runs[1].out
    bis = [r.json()["by_input"] for r in runs]
    assert all(b["method"] == "monte carlo" and b["draws"] == 100_000 for b in bis)
    assert [b["seed"] for b in bis] == [0, 0, 1, 2]
    assert len({b["p"] for b in bis[1:]}) > 1
    exact = _json(fix_check(TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.2", "--json"))
    assert exact["by_input"] == {"moved": 4, "p": 0.375, "method": "exact", "draws": None, "seed": None}


# ---------- TR54 ----------


def _verdict_pairs(tmp_path: Path) -> dict[str, tuple[Path, str]]:
    return {
        "less": (pair_store(tmp_path / "less", [(3, 4, 0, 4)] * 20), "0.5"),
        "more": (pair_store(tmp_path / "more", [(0, 4, 3, 4)] * 20), "0.5"),
        "nsd": (pair_store(tmp_path / "nsd", [(2, 4, 2, 4)] * 60), "0.5"),
        "small": (pair_store(tmp_path / "small", [(1, 2, 1, 2)] * 3), "0.05"),
        "nolimit": (pair_store(tmp_path / "nolimit", [(1, 1, 0, 1)]), "0.5"),
    }


EXPECT = {
    "less": ("different", "failed less in new", 0, "different: the new version failed less on these inputs"),
    "more": ("different", "failed more in new", 0, "different: the new version failed more on these inputs"),
    # ST2 (ruled 2026-10-20): a reliable range inside plus or minus the size asked decides it
    "nsd": ("no significant difference", None, 0, "lies inside ±50"),
    "small": ("too small to tell", None, 0, "too small to tell: could not have detected a drop in failure share below"),  # R17
    "nolimit": ("too small to tell", None, 0, "too small to tell:"),  # R17
}


def test_tr54_the_verdict_table_is_exhaustive_and_exclusive(tmp_path: Path) -> None:
    for name, (root, x) in _verdict_pairs(tmp_path).items():
        verdict, direction, code, phrase = EXPECT[name]
        j = fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", x, "--json")
        md = fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", x)
        assert j.code == md.code == code, (name, md.text)
        d = j.json()
        assert d["verdict"] == verdict, name
        assert d["direction"] in ("failed less in new", "failed more in new", "no direction")
        if direction is not None:
            assert d["direction"] == direction
        text = norm(md.out)
        assert phrase in text, (name, text)
        assert sum(p in text for p in VERDICT_PHRASES) == 1, name
        if name == "small":
            assert "was asked for" in text
        if name == "nsd":
            assert d["limits"]["drop"] is not None and d["limits"]["drop"] <= 0.5 and d["test"]["p"] >= 0.05
        if name == "nolimit":
            assert d["limits"]["drop"] is None


def test_tr54_the_verdict_reads_the_stated_alpha(tmp_path: Path) -> None:
    root = pair_store(tmp_path, WORKED)  # exact p 0.115
    d = _json(fix_check(root, "old", "new", ["fail"], *ALL, *MAX, "--alpha", "0.2", "--json"))
    assert d["test"]["alpha"] == 0.2
    assert (d["verdict"], d["direction"]) == ("different", "failed less in new")
    assert _json(fix_check(root, "old", "new", ["fail"], *ALL, *MAX, "--json"))["verdict"] != "different"


def test_tr54_no_direction_when_nothing_moved(tmp_path: Path) -> None:
    root = pair_store(tmp_path, [(2, 4, 2, 4), (1, 3, 1, 3)])
    d = _json(fix_check(root, "old", "new", ["fail"], *ALL, *MAX, "--json"))
    assert d["direction"] == "no direction"


# ---------- TR55 (the command line) ----------


def test_tr55_guidance_exactly_under_too_small_to_tell(tmp_path: Path) -> None:
    from poisson_trace.paired import detection_limit

    for name, (root, x) in _verdict_pairs(tmp_path).items():
        d = _json(fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", x, "--json"))
        assert "guidance" in d
        if d["verdict"] != "too small to tell":
            assert d["guidance"] is None, name
            continue
        g = d["guidance"]
        assert set(g) == GUIDANCE_KEYS
        if name == "nolimit":
            assert g["accepts_at"] is None
    root = pair_store(tmp_path / "g", WORKED)
    d = _json(fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", "0.3", "--json"))
    assert d["verdict"] == "too small to tell"
    g = d["guidance"]
    counts = counts_of(WORKED)
    r, k = g["repeats"], g["inputs"]
    assert detection_limit(counts, direction="drop", repeats=r) <= 0.3
    below = detection_limit(counts, direction="drop", repeats=r - 1)
    assert below is None or below > 0.3
    assert detection_limit(counts, direction="drop", scale=k / 5) <= 0.3
    below = detection_limit(counts, direction="drop", scale=(k - 1) / 5)
    assert below is None or below > 0.3
    assert g["accepts_at"] == pytest.approx(math.ceil(d["limits"]["drop"] * 1e4) / 1e4, abs=1e-12)


def test_tr55_guidance_is_computed_at_the_stated_alpha(tmp_path: Path) -> None:
    from poisson_trace.paired import detection_limit

    root = pair_store(tmp_path, WORKED)
    d = _json(fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", "0.3", "--alpha", "0.01", "--json"))
    assert d["verdict"] == "too small to tell"
    counts = counts_of(WORKED)
    drop = detection_limit(counts, direction="drop", alpha=0.01)
    assert d["limits"]["drop"] == pytest.approx(drop, abs=1e-12)
    r, k = d["guidance"]["repeats"], d["guidance"]["inputs"]
    assert detection_limit(counts, direction="drop", alpha=0.01, repeats=r) <= 0.3
    assert detection_limit(counts, direction="drop", alpha=0.01, repeats=r - 1) > 0.3
    assert detection_limit(counts, direction="drop", alpha=0.01, scale=k / 5) <= 0.3
    assert detection_limit(counts, direction="drop", alpha=0.01, scale=(k - 1) / 5) > 0.3
    again = fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", repr(d["guidance"]["accepts_at"]), "--alpha", "0.01")
    assert again.code == 0, again.text


def test_tr55_the_suggested_ceiling_is_accepted() -> None:
    """Sole catch for a suggestion that is refused again."""
    for argv in (
        (TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL),
        (TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A),
    ):
        # ST2 (ruled 2026-10-20): tau2 on all inputs reads no significant difference at 0.1 (its
        # range lies inside plus or minus 10); at 0.075 it still reads too small to tell
        tight = fix_check(*argv, "--max-mde", "0.075", "--json")
        assert tight.code == 0, tight.text  # R17: a result exits 0, too small to tell included
        assert tight.json()["verdict"] == "too small to tell"
        g = tight.json()["guidance"]
        again = fix_check(*argv, "--max-mde", repr(g["accepts_at"]), "--json")
        assert again.code == 0, again.text
        assert again.json()["verdict"] == "no significant difference"
        assert again.json()["guidance"] is None


# ---------- TR56 (compare) ----------


def test_tr56_compare_guidance_and_the_pointer_line(two_run_store) -> None:  # type: ignore[no-untyped-def]
    """ST5 (ruled 2026-10-20): the guidance is the smallest number of tries per input per version
    whose expected log-rank information, under the per-input model fitted to the two runs, reaches
    ((z_0.975 + z_0.8) / ln 1.3)^2; Schoenfeld's deaths no longer size it. Checked here with the
    statistics check's model (tf15_support) at 1,000 seeded draws: one try more adds about 0.375 to
    the expected information on this store, and the allowance of 0.6 admits a seeded estimate one
    try either side of the exact answer, about 304, and nothing Schoenfeld's rule gives (about 265,
    whose expected information is 99)."""
    from poisson_trace.survival import logrank_stratified
    from tf15_support import draw_run, fit_cells, z_sum

    root = two_run_store(deaths_rows(list(range(2, 12))) + deaths_rows([12, 13, 14], died=False, start_rep=20),
                         deaths_rows(list(range(3, 11)) + [4, 6]) )
    tight = compare(root, "a", "b", ["fail"], 1.3, "--json")
    assert tight.code == 0, tight.text  # R17: a result exits 0, too small to tell included
    d = tight.json()
    c = d["comparison"]
    g = c["guidance"]
    a = [("A", s, True) for s in range(2, 12)] + [("A", s, False) for s in (12, 13, 14)]
    b = [("A", s, True) for s in [*range(3, 11), 4, 6]]
    fit = fit_cells(a + b)
    target = (z_sum() / math.log(1.3)) ** 2

    def expected(r: int) -> float:
        rng = np.random.default_rng(r)
        return float(np.mean([logrank_stratified(draw_run(rng, fit, r), draw_run(rng, fit, r)).variance for _ in range(1000)]))

    r = g["repeats"]
    assert expected(r) >= target - 0.6, (r, expected(r), target)
    assert expected(r - 2) < target, (r, expected(r - 2), target)
    assert g["accepts_at"] >= c["mde_hazard_ratio"] and g["accepts_at"] == pytest.approx(math.ceil(c["mde_hazard_ratio"] * 1000) / 1000, abs=1e-12)
    again = compare(root, "a", "b", ["fail"], g["accepts_at"], "--json")
    assert again.code == 0, again.text
    assert again.json()["comparison"]["guidance"] is None
    for x in (1.3, 100.0):
        assert POINTER in norm(compare(root, "a", "b", ["fail"], x).out)


def test_tr56_compare_accepts_at_rounds_up(two_run_store) -> None:  # type: ignore[no-untyped-def]
    # ST5 (ruled 2026-10-20): the limit is exp(2.8016 / sqrt(V)); this store's V is 5.883454, its
    # limit 3.174071, which rounds down at three decimals (the store of 22 deaths no longer does)
    root = two_run_store(deaths_rows(list(range(2, 16))), deaths_rows(list(range(3, 17))))  # 28 deaths, share 1/2
    d = compare(root, "a", "b", ["fail"], 1.3, "--json")
    assert d.code == 0, d.text  # R17: a result exits 0, too small to tell included
    c = d.json()["comparison"]
    assert c["variance"] == pytest.approx(5.883454, abs=1e-6)
    assert c["mde_hazard_ratio"] == pytest.approx(3.174071, abs=1e-6)  # rounds down at three decimals
    assert c["guidance"]["accepts_at"] == pytest.approx(3.175, abs=1e-12)
    assert compare(root, "a", "b", ["fail"], c["guidance"]["accepts_at"]).code == 0


def test_tr56_compare_guidance_is_null_unless_too_small_to_tell(two_run_store) -> None:  # type: ignore[no-untyped-def]
    different = two_run_store(deaths_rows(list(range(1, 21))), deaths_rows(list(range(21, 41))))
    d = compare(different, "a", "b", ["fail"], 100.0, "--json")
    assert d.code == 0 and d.json()["comparison"]["verdict"] == "different"
    assert "guidance" in d.json()["comparison"] and d.json()["comparison"]["guidance"] is None
    assert POINTER in norm(compare(different, "a", "b", ["fail"], 100.0).out)
    # ST5 (ruled 2026-10-20): tau2's limit is 1.603, so 1.5 reads too small to tell and 1.604 is accepted
    loose = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.604, "--json")
    assert loose.code == 0 and loose.json()["comparison"]["guidance"] is None
    tight = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.3)
    assert tight.code == 0 and "--max-mde-hr 1.604" in tight.out  # R17: a result exits 0, too small to tell included
    assert set(compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.3, "--json").json()["comparison"]["guidance"]) == {
        "deaths", "runs", "inputs", "repeats", "accepts_at"}


# ---------- TR61 ----------


def test_tr61_the_json_keys_bytes_and_numbers() -> None:
    argv = (TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.12", "--json")
    a, b = fix_check(*argv), fix_check(*argv)
    ok(a)
    assert a.out == b.out
    d = a.json()
    assert tuple(d) == FIX_KEYS
    assert d["schema"] == "poisson-trace.fix-check/2"  # ST9 (ruled 2026-10-20)
    assert set(d["prove"]) == {"version", "store"} and d["prove"]["version"] == "0.0.1"
    assert set(d["runs"]) == {"old", "new"} and all(set(h) == HEADER_KEYS for h in d["runs"].values())
    assert set(d["inputs"]) == INPUTS_KEYS
    assert set(d["rows"]) == {"old", "new"} and all(set(r) == ROWS_KEYS for r in d["rows"].values())
    for key, keys in (("control", CONTROL_KEYS), ("test", TEST_KEYS), ("difference", DIFFERENCE_KEYS),
                      ("by_input", BY_INPUT_KEYS), ("consistency", CONSISTENCY_KEYS), ("limits", LIMITS_KEYS)):
        assert set(d[key]) == keys, key
    assert d["test"]["name"] == "exact conditional Cochran-Mantel-Haenszel"
    assert "Miettinen-Nurminen" in d["difference"]["interval"]  # ST3 (ruled 2026-10-20)
    assert d["limits"]["power"] == 0.8 and d["limits"]["max_mde"] == 0.12
    assert d["verdict"] == "no significant difference" and d["guidance"] is None
    assert tuple(d["changes"]) == CHANGES_BLOCK_KEYS
    assert all(set(r) == FLAG_ROW_KEYS for r in d["changes"]["rows"])
    assert d["events"] == ["unsolved"]
    assert "NaN" not in a.out and "Infinity" not in a.out
    # ST2 (ruled 2026-10-20): at 0.10 the range decides no significant difference; 0.075 is too small to tell
    tight = fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.075", "--json")
    assert tight.code == 0 and tuple(tight.json()) == FIX_KEYS and set(tight.json()["guidance"]) == GUIDANCE_KEYS


def test_tr61_json_is_one_object_and_nothing_else(store70: Path) -> None:
    out = _sel(store70, "--json").out
    assert out.lstrip().startswith("{") and out.rstrip().endswith("}")
    json.loads(out)
    assert tuple(json.loads(out)) == FIX_KEYS


# ---------- TR62 ----------


# ST3 (ruled 2026-10-20): the range is the stratified Miettinen-Nurminen score interval
FIX_CAPTION_WORDS = ("Cochran-Mantel-Haenszel", "exact", "stratified by input", "Mantel-Haenszel", "Miettinen-Nurminen",
                     "sign-flip", "Fisher", "Benjamini-Hochberg", "continuity")


def test_tr62_every_caption_names_its_method() -> None:
    for result in (
        fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.12"),
        fix_check(TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.2"),
    ):
        text = norm(ok(result).out)
        for word in FIX_CAPTION_WORDS:
            assert word in text, word
    drawn = norm(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.12", "--seed", "3").out)
    assert re.search(r"seed = 3\b", drawn)
    ch = norm(ok(changes(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS)).out)
    assert "Fisher" in ch and "Benjamini-Hochberg" in ch


# ---------- TR63 ----------


def test_tr63_no_banned_word_in_any_output(tmp_path: Path, two_run_store) -> None:  # type: ignore[no-untyped-def]
    pattern = re.compile(r"\b(" + "|".join(BANNED) + r")\b", re.IGNORECASE)
    outputs = []
    for root, x in _verdict_pairs(tmp_path).values():
        outputs.append(ok(fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", x)).out)
        outputs.append(ok(fix_check(root, "old", "new", ["fail"], *ALL, "--max-mde", x, "--json")).out)
    outputs.append(ok(fix_check(TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.2")).out)
    outputs.append(ok(changes(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS)).out)
    outputs.append(ok(changes(HUMANEVAL, HE_A, HE_B, HE_EVENTS)).out)
    tight = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.3)
    assert tight.code == 0 and "--max-mde-hr 1.604" in tight.out  # R17; ST5 (ruled 2026-10-20)
    outputs.append(tight.out)
    outputs.append(compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.5).out)
    different = two_run_store(deaths_rows(list(range(1, 21))), deaths_rows(list(range(21, 41))))
    outputs.append(compare(different, "a", "b", ["fail"], 100.0).out)
    for text in outputs:
        for line in text.splitlines():
            assert not pattern.search(line), line


# ---------- TR64 ----------


def test_tr64_the_six_sentences_under_every_report() -> None:
    from poisson_trace.paired import CANNOT_SAY, LEFT_OUT

    assert CANNOT_SAY == SPEC_CANNOT_SAY
    assert LEFT_OUT == SPEC_LEFT_OUT
    for result in (
        fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.1"),
        fix_check(TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.2"),
        changes(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS),
    ):
        text = norm(ok(result).out)
        for sentence in SPEC_CANNOT_SAY:
            assert sentence in text, sentence
    fj = _json(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.1", "--json"))
    cj = _json(changes(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, "--json"))
    assert fj["cannot_say"] == list(SPEC_CANNOT_SAY)
    assert fj["changes"]["cannot_say"] == list(SPEC_CANNOT_SAY)
    assert cj["cannot_say"] == list(SPEC_CANNOT_SAY)


# ---------- TR65 ----------


DISAGREE = "the interval and the test disagree; the line above follows the test"


def _copies(arm: str) -> str:
    return f"no input gave mixed outcomes across its repeats in the {arm} arm"


# ST3 (ruled 2026-10-20): the Miettinen-Nurminen interval on WORKED holds 0 (-50.1 to +0.43), so
# it agrees with the test there; this table's range (-54.4 to -1.2) leaves 0 out at exact p 0.0746
DISAGREEING = [(0, 2, 1, 2), (2, 2, 1, 2), (2, 2, 0, 2), (0, 2, 0, 2), (0, 2, 0, 2), (2, 2, 1, 2), (1, 2, 1, 2),
               (2, 2, 0, 2), (1, 2, 0, 2), (1, 2, 1, 2), (1, 2, 1, 2), (2, 2, 1, 2)]


def test_tr65_the_interval_and_test_sentence(tmp_path: Path) -> None:
    worked = pair_store(tmp_path / "worked", DISAGREEING)  # p 0.0746, interval excludes 0
    d = _json(fix_check(worked, "old", "new", ["fail"], *ALL, *MAX, "--json"))
    assert d["test"]["p"] >= 0.05 and d["difference"]["hi"] < 0
    assert DISAGREE in norm(fix_check(worked, "old", "new", ["fail"], *ALL, *MAX).out)
    plain = pair_store(tmp_path / "plain", WORKED)
    w = _json(fix_check(plain, "old", "new", ["fail"], *ALL, *MAX, "--json"))
    assert w["difference"]["lo"] < 0 < w["difference"]["hi"]
    assert DISAGREE not in norm(fix_check(plain, "old", "new", ["fail"], *ALL, *MAX).out)
    agree_small = norm(ok(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.12")).out)
    assert DISAGREE not in agree_small
    strong = pair_store(tmp_path / "strong", [(3, 4, 1, 4)] * 12)
    s = _json(fix_check(strong, "old", "new", ["fail"], *ALL, *MAX, "--json"))
    assert s["test"]["p"] < 0.05 and s["difference"]["hi"] < 0
    assert DISAGREE not in norm(fix_check(strong, "old", "new", ["fail"], *ALL, *MAX).out)


NO_INTERVAL = "no interval: Sato's variance is not positive on these counts"


def test_tr49_the_no_interval_sentence_prints_exactly_when_the_variance_is_null(tmp_path: Path) -> None:
    """Session A ruling 2, ruled yes 2026-09-29: the fixed sentence prints exactly when
    ``difference.variance`` is null, whatever the test says."""
    separated = pair_store(tmp_path / "separated", [(4, 4, 0, 4)] * 3)  # Sato's variance 0, exact p tiny
    single = pair_store(tmp_path / "single", [(1, 1, 0, 1)])  # Sato's variance 0, exact p 1
    for root in (separated, single):
        d = _json(fix_check(root, "old", "new", ["fail"], *ALL, *MAX, "--json"))
        assert d["difference"]["variance"] is None and d["difference"]["lo"] is None and d["difference"]["hi"] is None
        assert NO_INTERVAL in norm(ok(fix_check(root, "old", "new", ["fail"], *ALL, *MAX)).out)
    worked = pair_store(tmp_path / "worked", WORKED)
    for argv in ((worked, "old", "new", ["fail"], *ALL, *MAX),
                 (TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.12"),
                 (TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.2")):
        assert _json(fix_check(*argv, "--json"))["difference"]["variance"] is not None
        assert NO_INTERVAL not in norm(ok(fix_check(*argv)).out)


def test_tr65_the_interval_and_test_sentence_needs_an_interval(tmp_path: Path) -> None:
    """Session A ruling 2, ruled yes 2026-09-29: with no interval printed, the interval-and-test
    sentence does not print, even where the test calls a difference."""
    separated = pair_store(tmp_path / "separated", [(4, 4, 0, 4)] * 3)
    d = _json(fix_check(separated, "old", "new", ["fail"], *ALL, *MAX, "--json"))
    assert d["test"]["p"] < 0.05 and d["difference"]["variance"] is None
    assert d["verdict"] == "different"
    text = norm(ok(fix_check(separated, "old", "new", ["fail"], *ALL, *MAX)).out)
    assert DISAGREE not in text and NO_INTERVAL in text
    single = pair_store(tmp_path / "single", [(1, 1, 0, 1)])
    assert DISAGREE not in norm(ok(fix_check(single, "old", "new", ["fail"], *ALL, *MAX)).out)


def test_tr65_the_copies_sentence_and_the_gap(store70: Path, tmp_path: Path) -> None:
    text = norm(ok(_sel(store70)).out)
    assert _copies("new") in text and _copies("old") not in text
    assert "the repeats may be copies of one another" in text
    assert re.search(r"the two runs started .+ apart", text)
    text = norm(ok(fix_check(store70, "old", "new", ["fail"], *ALL, *MAX)).out)
    assert _copies("new") in text and _copies("old") not in text
    # one outcome row on an input: the new arm does not qualify although nothing is mixed
    single = pair_store(tmp_path / "single", [(1, 2, 0, 1), (2, 2, 2, 2)])
    text = norm(ok(fix_check(single, "old", "new", ["fail"], *ALL, *MAX)).out)
    assert _copies("new") not in text and _copies("old") not in text
    assert re.search(r"the two runs started .+ apart", text)
    both = pair_store(tmp_path / "both", [(2, 2, 0, 2), (0, 3, 3, 3)])
    text = norm(ok(fix_check(both, "old", "new", ["fail"], *ALL, *MAX)).out)
    assert _copies("new") in text and _copies("old") in text
    mixed = norm(ok(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, *ALL, "--max-mde", "0.12")).out)
    assert _copies("new") not in mixed and _copies("old") not in mixed
