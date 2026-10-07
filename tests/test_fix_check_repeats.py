"""TR73: the consistency block where only a few inputs repeat (ruled 2026-09-30, Integrations
Ragas Session A ruling 8; written 2026-10-05, Trace pre-tag Session A).

TR72 covers one run per input per version. TR73 extends it: an input repeats when one version
holds two or more of its runs with an outcome, and κ, *fails again* and the 1/(1 − κ) sentence
print only when at least half the compared inputs repeat. Below that the block prints the
failure share and one sentence naming how many inputs repeat; the JSON's ``fails_again`` and
``kappa`` are null and its other three figures stay as computed. One run everywhere keeps
TR72's sentence; a design at or above half prints as before.
"""

from __future__ import annotations

import contextlib
import io
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from conftest import FIXTURES, Row, build_store, norm
from fixcheck_support import CONSISTENCY_KEYS, FIX_KEYS, INPUTS_KEYS, PILOT, SPEC_CANNOT_SAY, fix_check

# spec section 4.2, as amended for TR73; {k} and {m} print as the header prints its counts
FEW = (
    "consistency cannot be measured with {k} of {m} inputs run more than once on a version: it "
    "takes at least half the inputs run two or more times on a version to see whether a failure "
    "repeats"
)
TIMEOUT, ERRORED = "timeout", "errored"

# One input of a design: its outcomes on the old version and on the new one, a run each.
# "fail" fails and "ok" does not; TIMEOUT and ERRORED are rows with no outcome. ``None`` is an
# input the version does not carry at all.
Arm = Sequence[str] | None


def _rows(arm: Sequence[tuple[int, Arm]]) -> list[Row]:
    rows = []
    for i, outcomes in arm:
        for j, o in enumerate(outcomes or ()):
            if o == TIMEOUT:
                rows.append(Row({"input": i}, None, None, error="timeout", replicate_index=j, seed=j))
            elif o == ERRORED:
                rows.append(Row({"input": i}, None, None, error="RuntimeError", replicate_index=j, seed=j))
            else:
                rows.append(Row({"input": i}, o, None, replicate_index=j, seed=j))
    return rows


def _store(root: Path, design: Sequence[tuple[Arm, Arm]]) -> Path:
    build_store(root, "a", _rows([(i, old) for i, (old, _) in enumerate(design) if old is not None]))
    build_store(root, "b", _rows([(i, new) for i, (_, new) in enumerate(design) if new is not None]))
    return root


def _mixed(i: int) -> str:
    """Outcomes that vary across inputs, so that κ is defined and below 1."""
    return "fail" if i % 3 != 1 else "ok"


def _design(m: int, k: int) -> list[tuple[Arm, Arm]]:
    """``m`` inputs, the first ``k`` run twice on each version and the rest once."""
    out: list[tuple[Arm, Arm]] = []
    for i in range(m):
        o = _mixed(i)
        if i < k:
            out.append(([o, "fail"], [o, "ok"]))
        else:
            out.append(([o], ["ok" if i % 2 else o]))
    return out


def _block(out: str) -> list[str]:
    """The Consistency block's lines, its heading and blank lines left out."""
    start = out.index("## Consistency\n")
    end = out.index("\n## ", start + 3)
    return [line for line in out[start:end].splitlines()[1:] if line.strip()]


def _check(root: Path, *, full: bool = False) -> Any:
    """The Consistency block and the JSON, from one store; with ``full``, the markdown too."""
    r = fix_check(root, "a", "b", ("fail",), "--inputs", "all", "--max-mde", "0.5")
    assert r.code in (0, 2), r.text
    j = fix_check(root, "a", "b", ("fail",), "--inputs", "all", "--max-mde", "0.5", "--json")
    assert j.code == r.code, j.text
    return (_block(r.out), j.json(), r.out) if full else (_block(r.out), j.json())


def _suppressed(block: list[str], d: dict[str, Any], k: int, m: int) -> None:
    c = d["consistency"]
    assert block == [f"failure share {c['failure_share']:.3f}", FEW.format(k=f"{k:,}", m=f"{m:,}")], block  # R18: counts with separators
    assert c["fails_again"] is None and c["kappa"] is None, c


def _printed(block: list[str], d: dict[str, Any]) -> None:
    """The block as it printed before TR73: TR51's figures, and the 1/(1 − κ) sentence."""
    c = d["consistency"]
    assert c["kappa"] is not None and c["fails_again"] is not None, c
    assert c["kappa"] < 1.0, c
    assert block == [
        f"failure share {c['failure_share']:.3f} · fails again {c['fails_again']:.3f} · "
        f"κ {c['kappa']:.3f} · within-input variance {c['within']:.3f} against pooled "
        f"{c['pooled']:.3f}",
        f"a comparison that ignored the inputs would need 1/(1 − κ) = "
        f"{1.0 / (1.0 - c['kappa']):.2f} times the runs",
    ], block


def _counts(d: dict[str, Any]) -> list[Any]:
    from poisson_trace.paired import Counts

    return [
        Counts(r["config_hash"], r["failed_a"], r["runs_a"], r["failed_b"], r["runs_b"])
        for r in d["changes"]["rows"]
    ]


def test_tr73_two_of_ten_inputs_repeat_the_block_prints_no_kappa_and_the_json_keeps_the_rest(
    tmp_path: Path,
) -> None:
    block, d, text = _check(_store(tmp_path, _design(10, 2)), full=True)
    assert d["inputs"]["compared"] == 10
    _suppressed(block, d, 2, 10)
    from poisson_trace.paired import consistency, paired_test

    share, _, _, within, pooled = consistency(_counts(d))
    c = d["consistency"]
    assert (c["failure_share"], c["within"], c["pooled"]) == (
        pytest.approx(share, abs=1e-12), pytest.approx(within, abs=1e-12), pytest.approx(pooled, abs=1e-12))
    assert d["test"]["p"] == pytest.approx(paired_test(_counts(d)).p, rel=1e-12)
    # the JSON keeps its shape (TR61), and the design is named in the Consistency block alone
    assert tuple(d) == FIX_KEYS
    assert set(c) == CONSISTENCY_KEYS and set(d["inputs"]) == INPUTS_KEYS
    assert tuple(d["cannot_say"]) == SPEC_CANNOT_SAY
    outside = text.replace("\n".join(block), "")
    assert "run more than once" not in outside and "cannot be measured" not in outside


@pytest.mark.parametrize(
    "m,k,prints", [(7, 3, False), (7, 4, True), (8, 3, False), (8, 4, True), (1000, 1, False)]
)
def test_tr73_kappa_prints_when_at_least_half_the_compared_inputs_repeat(
    tmp_path: Path, m: int, k: int, prints: bool
) -> None:
    block, d = _check(_store(tmp_path, _design(m, k)))
    assert d["inputs"]["compared"] == m
    if prints:
        _printed(block, d)
    else:
        _suppressed(block, d, k, m)


@pytest.mark.parametrize("version", ["old", "new"])
def test_tr73_an_input_repeats_when_either_version_holds_two_of_its_runs(
    tmp_path: Path, version: str
) -> None:
    """Every input three times on one version and once on the other: every input repeats."""
    design: list[tuple[Arm, Arm]] = []
    for i in range(6):
        many, one = [_mixed(i), "fail", "ok"], ["ok" if i % 2 else "fail"]
        design.append((many, one) if version == "old" else (one, many))
    block, d = _check(_store(tmp_path, design))
    _printed(block, d)


def test_tr73_the_patched_pilot_repeats_on_the_old_version_only_and_prints_kappa() -> None:
    """The README's real before and after: six inputs, four runs each on the old version, one on
    the new. Its consistency block is the README's, unchanged."""
    tau2 = FIXTURES / "tau2"
    argv = ("--failing-from", "20260915T210140Z-4847", "--max-mde", "0.5")
    r = fix_check(tau2, "20260915T211148Z-965d", PILOT, ("unsolved",), *argv)
    d = fix_check(tau2, "20260915T211148Z-965d", PILOT, ("unsolved",), *argv, "--json").json()
    assert d["inputs"]["compared"] == 6
    assert {(row["runs_a"], row["runs_b"]) for row in d["changes"]["rows"]} == {(4, 1)}
    block = norm(" ".join(_block(r.out)))
    assert "fails again 0.762 · κ 0.206" in block
    assert "1/(1 − κ) = 1.26 times the runs" in block


def test_tr73_rows_with_no_outcome_do_not_make_an_input_repeat(tmp_path: Path) -> None:
    """Four inputs. One has two runs on the old version; two have one run and one row with no
    outcome (one timed out, one errored); one has one run. One of four repeats."""
    design: list[tuple[Arm, Arm]] = [
        (["fail", "ok"], ["fail"]),
        (["fail", TIMEOUT], ["ok"]),
        (["ok", ERRORED], ["fail"]),
        (["fail"], ["ok"]),
    ]
    block, d = _check(_store(tmp_path, design))
    assert (d["rows"]["old"]["timed_out"], d["rows"]["old"]["no_outcome"]) == (1, 1)
    _suppressed(block, d, 1, 4)


def test_tr73_inputs_left_out_count_neither_way(tmp_path: Path) -> None:
    """Only compared inputs count. (a) Two of four compared inputs repeat, and two inputs the
    new version does not carry, run once, would bring the share under half: it prints. (b) Two
    of six compared inputs repeat, and two inputs the new version does not carry, run twice,
    would bring the share to half or more: it does not."""
    a = _design(4, 2) + [(["fail"], None), (["ok"], None)]
    block, d = _check(_store(tmp_path / "a", a))
    assert (d["inputs"]["selected"], d["inputs"]["compared"]) == (6, 4)
    _printed(block, d)

    b = _design(6, 2) + [(["fail", "ok"], None), (["fail", "fail"], None)]
    block, d = _check(_store(tmp_path / "b", b))
    assert (d["inputs"]["selected"], d["inputs"]["compared"]) == (8, 6)
    _suppressed(block, d, 2, 6)


@pytest.mark.parametrize("outcome,share", [("ok", "0.000"), ("fail", "1.000")])
def test_tr73_few_repeats_with_no_failure_or_every_run_failing_still_names_the_design(
    tmp_path: Path, outcome: str, share: str
) -> None:
    """κ is undefined here whatever the design (Session A ruling 3 of 2026-09-29); the design's
    sentence prints, and not the dash line. "No failure" is among the compared inputs: the event
    has to be one a run carries, so one input the new version does not carry fails, and is left
    out."""
    design: list[tuple[Arm, Arm]] = [([outcome, outcome], [outcome, outcome])]
    design += [([outcome], [outcome]) for _ in range(4)]
    design.append((["fail"], None))
    block, d = _check(_store(tmp_path, design))
    assert d["inputs"]["compared"] == 5
    assert block == [f"failure share {share}", FEW.format(k=1, m=5)], block
    assert d["consistency"]["fails_again"] is None and d["consistency"]["kappa"] is None


def _import(root: Path, name: str) -> None:
    from poisson_trace.ingest.cli import main

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main([
            "ragas", str(FIXTURES / "ingest" / "ragas" / f"{name}.jsonl"), "--store", str(root),
            "--run", name, "--metric", "faithfulness", "--cut", "0.5", "--below", "--case-column",
            "case", "--started", "2025-03-31T00:00:00Z",
        ])
    assert code == 0, out.getvalue() + err.getvalue()


def test_tr73_the_public_ragas_pair_on_faithfulness_prints_no_kappa(tmp_path: Path) -> None:
    """The case that exposed it (Ragas Session A ruling 8): 3 of the 137 compared questions
    were asked more than once, and the block printed κ −0.080 and 0.93 times the runs."""
    root = tmp_path / "store"
    _import(root, "rag-base")
    _import(root, "rag-raft")
    argv = ("--inputs", "all", "--max-mde", "0.10")
    r = fix_check(root, "rag-base", "rag-raft", ("missed",), *argv)
    d = fix_check(root, "rag-base", "rag-raft", ("missed",), *argv, "--json").json()
    assert r.code == 2, r.text
    assert d["inputs"]["compared"] == 137
    _suppressed(_block(r.out), d, 3, 137)
    c = d["consistency"]
    assert (c["failure_share"], c["within"], c["pooled"]) == (
        pytest.approx(0.3440, abs=1e-4), pytest.approx(0.2451, abs=1e-4), pytest.approx(0.2257, abs=1e-4))
    assert d["test"]["p"] == pytest.approx(0.629, abs=1e-3)
