"""Shared fixtures: the committed stores, a CLI runner, and a builder for synthetic stores.

Synthetic stores are written through Prove's own ``Store.create_run`` / ``Store.append`` from
hand-built envelopes, so every row a test places is a row Prove wrote. Nothing here touches a
Parquet file or a manifest directly.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from poisson_prove.store import EpisodeRecord, RunManifest, Store
from poisson_prove.trace import Declaration, Span, Trace

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TAU2 = FIXTURES / "tau2"
CS = FIXTURES / "cs"
TAU2_A = "20260915T210140Z-4847"
TAU2_B = "20260915T211148Z-965d"
CS_RECORD = "20260925T234602Z-3ea0"
CS_REPLAY = "20260925T235434Z-af48"
TAU2_EVENTS = ("unsolved",)
CS_EVENTS = ("forbidden_action", "unresolved", "max_turns", "app_error")

CANNOT_SAY = (
    "The step index is where the run stopped, not why. A run that died at a tool step may "
    "have gone wrong three steps earlier.",
    # PENDING (TF15 Session A yes/no): under ST8 a timed-out run is an end of its own, not censored
    "Capped runs are censored at their last recorded step. If they would have died soon after, "
    "the curve is optimistic by that much. A run that timed out ends where it stopped, counted "
    "beside the kinds and not as a death; the header counts both.",
    "Excluded rows are not on the curve; the header counts them by reason.",
    "On one run, this is a description. Only a comparison of two stored runs on the same "
    "cells says whether anything moved, and only within what it could not have detected.",
)

# the verdict and its sentence after the schema, next last (spec section 9.4, rule L9)
WHERE_KEYS = (
    "schema", "verdict", "sentence", "prove", "run", "events", "clock", "curve", "median_step",
    "at", "causes", "bootstrap", "declared", "cannot_say", "next",
)
COMPARE_KEYS = (
    "schema", "verdict", "sentence", "prove", "runs", "events", "clock", "at", "comparison",
    "per_cause", "cannot_say", "failure_taxonomy_diff", "next",
)


def events_args(events: Sequence[str]) -> list[str]:
    out: list[str] = []
    for e in events:
        out += ["--event", e]
    return out


@dataclass(frozen=True)
class CliResult:
    code: int
    out: str
    err: str

    @property
    def text(self) -> str:
        return self.out + self.err

    def json(self) -> dict[str, Any]:
        return json.loads(self.out, parse_constant=_no_constants)


def _no_constants(name: str) -> Any:
    raise ValueError(f"JSON constant {name!r} is not a number")


def run_cli(argv: Sequence[str]) -> CliResult:
    """``poisson_trace.cli.main`` in-process, with both streams captured."""
    from poisson_trace.cli import main

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return CliResult(code=int(code), out=out.getvalue(), err=err.getvalue())


def where(store: Path | str, run: str, events: Sequence[str], *extra: str) -> CliResult:
    return run_cli(["where", run, "--store", str(store), *events_args(events), *extra])


def compare(
    store: Path | str, a: str, b: str, events: Sequence[str], max_mde_hr: float | None, *extra: str
) -> CliResult:
    argv = ["compare", a, b, "--store", str(store), *events_args(events), *extra]
    if max_mde_hr is not None:
        argv += ["--max-mde-hr", str(max_mde_hr)]
    return run_cli(argv)


def norm(text: str) -> str:
    """Whitespace collapsed and dashes unified, for wording checks that must not pin layout."""
    return " ".join(text.replace("–", "-").replace("—", "-").split())


# ---------- synthetic stores ----------


def span(
    span_id: str,
    parent_id: str | None,
    kind: str,
    start_ns: int,
    *,
    step_name: str | None = None,
    gate: str | None = None,
    name: str = "span",
) -> Span:
    return Span(
        span_id=span_id, parent_id=parent_id, kind=kind, name=name, start_ns=start_ns,
        end_ns=start_ns + 1, step_name=step_name, gate=gate,
    )


@dataclass(frozen=True)
class Row:
    """One synthetic episode. ``spans=None`` stores no trace; ``spans=()`` stores an empty one."""

    config: Mapping[str, Any]
    outcome: str | None
    spans: Sequence[Span] | None
    error: str | None = None
    replicate_index: int = 0
    seed: int = 0
    t: float = 1.0
    horizon: float = 10.0


def build_store(
    root: Path,
    run_id: str,
    rows: Sequence[Row],
    *,
    cap: int | None = None,
    declared: Declaration | None = None,
    t_unit: str = "steps",
    run_salt: str = "salt",
    target_id: str = "synthetic/target",
) -> Store:
    store = Store(root)
    manifest = RunManifest(
        run_id=run_id, target_id=target_id, t_unit=t_unit, run_salt=run_salt, axis_types={},
        backend="local", environment={"capture": {"max_spans": cap}}, declared=declared,
    )
    store.create_run(manifest)
    records = []
    for row in rows:
        meta: dict[str, Any] = {}
        if row.spans is not None:
            meta["trace"] = Trace(spans=tuple(row.spans), source="record").to_dict()
        if row.outcome is None:
            assert row.error is not None
            rec = EpisodeRecord.errored(
                run_id=run_id, config=row.config, seed=row.seed,
                replicate_index=row.replicate_index, error=row.error, wall_time=1.0, meta=meta,
            )
        else:
            from poisson_prove.store import config_hash

            rec = EpisodeRecord(
                run_id=run_id, config_hash=config_hash(row.config), config=dict(row.config),
                seed=row.seed, replicate_index=row.replicate_index, outcome=row.outcome,
                t=row.t, horizon=row.horizon, confidence=None, meta=meta, error=row.error,
                wall_time=1.0, backend_meta={},
            )
        records.append(rec)
    store.append(run_id, records)
    store.mark_complete(run_id)
    return store


def roots(kinds: Sequence[str], start: int = 1, **kw: Any) -> list[Span]:
    """``len(kinds)`` root spans in start order, ids ``r1``, ``r2``, ..."""
    return [span(f"r{i + 1}", None, k, start + i, **kw) for i, k in enumerate(kinds)]


CELL_A = {"cell": "A"}
CELL_B = {"cell": "B"}
SYNTH_CAP = 6
SYNTH_EVENTS = ("fail",)
SYNTH_DECLARED = Declaration(steps=["plan", "act", "check"], outcomes=["ok", "fail"], gates=["check"])


def synth_rows(*, cap_row_spans: int = SYNTH_CAP) -> list[Row]:
    """The TR36 store, every header count fixed by construction (see test_golden)."""
    return [
        # 1: died at leaf 2 (root "plan" > c1 > g1; c2 "act" beside c1): leaves c2 then g1
        Row(CELL_A, "fail", [
            span("root", None, "agent", 10, step_name="plan"),
            span("c1", "root", "llm", 11),
            span("c2", "root", "tool", 12, step_name="act"),
            span("g1", "c1", "llm", 13),
        ], replicate_index=0),
        # 2: ended at 3; carries "act" and an undeclared "extra"
        Row(CELL_A, "ok", [
            span("r1", None, "llm", 1), span("r2", None, "tool", 2, step_name="act"),
            span("r3", None, "llm", 3, step_name="extra"),
        ], replicate_index=1),
        # 3: timed out at 2, censored
        Row(CELL_B, None, roots(["llm", "llm"]), error="timeout", replicate_index=0),
        # 4: at the cap, censored, never a death although its outcome is an event
        Row(CELL_B, "fail", roots(["llm"] * cap_row_spans), replicate_index=1),
        # 5: infra, excluded as no outcome and not a timeout
        # (its "act" span is observed by Prove but counts for no placed run)
        Row(CELL_B, None, [span("r1", None, "llm", 1), span("r2", None, "tool", 2, step_name="act")],
            error="infra: container lost", replicate_index=2),
        # 6: no trace, excluded
        Row(CELL_A, "fail", None, replicate_index=2),
        # 7: a trace with no span, excluded as no leaf span
        Row(CELL_B, "fail", (), replicate_index=3),
    ]


SYNTH_COUNTS = {
    "rows": 7, "with_outcome": 5, "no_outcome": 2, "timed_out": 1, "infra": 1, "other": 0,
    "placed": 4, "died": 1, "ended": 1, "timed out": 1, "capped": 1,
    "excluded": {"no trace": 1, "unreadable trace": 0, "no leaf span": 1, "no outcome, not a timeout": 1},
}


@pytest.fixture(autouse=True)
def _no_real_browser(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """No test opens a real browser tab. The suite runs ``poisson-trace`` in-process, and a case
    such as ``report ra --open`` or ``ui --open`` reaches ``webbrowser.open``; here every open is
    recorded and returns as a browser would. A test that fakes the browser itself patches over
    this; one that runs the command in a subprocess fakes it there with ``BROWSER``."""
    import webbrowser

    opened: list[str] = []

    def recorded(url: str, *a: object, **k: object) -> bool:
        opened.append(url)
        return True

    for name in ("open", "open_new", "open_new_tab"):
        monkeypatch.setattr(webbrowser, name, recorded)
    return opened


@pytest.fixture
def synth(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "synth"
    build_store(root, "synth", synth_rows(), cap=SYNTH_CAP, declared=SYNTH_DECLARED)
    return root, "synth"


@pytest.fixture
def make_store(tmp_path: Path) -> Callable[..., tuple[Path, str]]:
    """``make_store(rows, name="run", **manifest)`` -> (root, run_id), each call its own store."""
    counter = {"n": 0}

    def _make(rows: Sequence[Row], name: str = "run", **kw: Any) -> tuple[Path, str]:
        counter["n"] += 1
        root = tmp_path / f"store{counter['n']}"
        build_store(root, name, rows, **kw)
        return root, name

    return _make


@pytest.fixture
def two_run_store(tmp_path: Path) -> Callable[..., Path]:
    """``two_run_store(rows_a, rows_b, **manifest)`` -> root holding runs ``a`` and ``b``."""
    counter = {"n": 0}

    def _make(rows_a: Sequence[Row], rows_b: Sequence[Row], **kw: Any) -> Path:
        counter["n"] += 1
        root = tmp_path / f"pair{counter['n']}"
        build_store(root, "a", rows_a, **kw)
        build_store(root, "b", rows_b, **kw)
        return root

    return _make


def deaths_rows(
    steps: Sequence[int], *, died: bool = True, cell: Mapping[str, Any] = CELL_A, kind: str = "llm",
    start_rep: int = 0,
) -> list[Row]:
    """One row per step: ``steps[i]`` root spans, all leaves, outcome ``fail`` or ``ok``."""
    return [
        Row(cell, "fail" if died else "ok", roots([kind] * s), replicate_index=start_rep + i)
        for i, s in enumerate(steps)
    ]


@contextlib.contextmanager
def chdir(path: Path):  # type: ignore[no-untyped-def]
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)
