"""The console script: ``poisson-trace where``, ``compare``, ``fix-check`` and ``changes``.

``proofload`` is imported inside ``main`` and nowhere at module level, so the check that it is
present and at the pinned version runs first and reports in one sentence.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PROVE_VERSION = "0.0.1"
# The by-input reading's seeded sign assignments, when there are too many to enumerate.
_DRAWS = 100_000
_INSTALL = "pip install -e /path/to/prove"


class _Refusal(Exception):
    """One sentence, exit 1."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Any:
        raise _Refusal(f"argument error: {message}")


def _build_parser() -> _Parser:
    parser = _Parser(prog="poisson-trace", description="Where in the workflow runs die.")
    verbs = parser.add_subparsers(
        dest="verb", required=True, metavar="where|compare|fix-check|changes"
    )

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--store", required=True, help="the root of a Prove store")
        p.add_argument(
            "--event",
            action="append",
            required=True,
            metavar="NAME",
            help="an outcome that counts as a death; repeatable",
        )
        p.add_argument("--by", choices=("kind", "step"), default="kind")
        p.add_argument(
            "--at",
            action="append",
            type=int,
            default=[],
            metavar="STEP",
            help="a step to report the curve at; repeatable",
        )
        p.add_argument("--json", action="store_true", help="print the JSON structure only")

    where = verbs.add_parser("where", help="the survival curve over step index for one run")
    where.add_argument("run")
    common(where)
    where.add_argument("--boot", type=int, default=1000, metavar="B")
    where.add_argument("--seed", type=int, default=0, metavar="S")
    where.add_argument("--svg", metavar="FILE", help="write the curve as an SVG file")

    compare = verbs.add_parser("compare", help="a before (A) and an after (B), compared")
    compare.add_argument("a")
    compare.add_argument("b")
    common(compare)
    compare.add_argument(
        "--max-mde-hr",
        type=float,
        required=True,
        metavar="X",
        help="the largest minimum detectable hazard ratio the comparison is allowed",
    )
    compare.add_argument("--alpha", type=float, default=0.05, metavar="A")

    def paired(p: argparse.ArgumentParser) -> None:
        p.add_argument("--store", required=True, help="the root of a Prove store")
        p.add_argument(
            "--event",
            action="append",
            required=True,
            metavar="NAME",
            help="an outcome that counts as a failure; repeatable",
        )
        p.add_argument("--alpha", type=float, default=0.05, metavar="A")
        p.add_argument("--top", type=int, default=10, metavar="N")
        p.add_argument("--json", action="store_true", help="print the JSON structure only")

    fix = verbs.add_parser(
        "fix-check", help="an old and a new version re-run on the same inputs, compared"
    )
    fix.add_argument("old")
    fix.add_argument("new")
    paired(fix)
    fix.add_argument("--failing-from", metavar="RUN")
    fix.add_argument("--min-failures", type=int, metavar="M")
    fix.add_argument("--inputs", metavar="all")
    fix.add_argument("--max-mde", type=float, metavar="X")
    fix.add_argument("--seed", type=int, default=0, metavar="S")

    changes = verbs.add_parser("changes", help="the inputs whose failure share moved")
    changes.add_argument("a")
    changes.add_argument("b")
    paired(changes)
    return parser


def _check_prove() -> str | None:
    try:
        import proofload
    except ImportError:
        return (
            f"Poisson Trace reads Prove's stored runs through the proofload package "
            f"(version {PROVE_VERSION}), which is not importable here; install it from a "
            f"checkout with `{_INSTALL}`."
        )
    found = getattr(proofload, "__version__", None)
    if found != PROVE_VERSION:
        return (
            f"Poisson Trace reads Prove's stored runs through proofload {PROVE_VERSION} and "
            f"found proofload {found}; install that version from a checkout with "
            f"`{_INSTALL}`."
        )
    return None


def main(argv: Sequence[str] | None = None) -> int:
    line = _check_prove()
    if line is not None:
        sys.stderr.write(line + "\n")
        return 1
    try:
        ns = _build_parser().parse_args(argv)
        _validate(ns)
        if ns.verb == "where":
            return _where(ns)
        if ns.verb == "compare":
            return _compare(ns)
        if ns.verb == "fix-check":
            return _fix_check(ns)
        return _changes(ns)
    except _Refusal as e:
        sys.stderr.write(str(e) + "\n")
        return 1


def _validate(ns: argparse.Namespace) -> None:
    if ns.verb == "where" and ns.boot < 1:
        raise _Refusal("--boot must be at least 1")
    if ns.verb == "compare":
        if not 0.0 < ns.alpha < 1.0:
            raise _Refusal("--alpha must be strictly between 0 and 1")
        if not ns.max_mde_hr > 0.0:
            raise _Refusal("--max-mde-hr must be a positive hazard ratio")
    if ns.verb in ("fix-check", "changes"):
        if not 0.0 < ns.alpha < 1.0:
            raise _Refusal("--alpha must be strictly between 0 and 1")
        if ns.top < 0:
            raise _Refusal("--top must be 0 or more")
    if ns.verb == "changes" and ns.a == ns.b:
        raise _Refusal(f"A and B are both {ns.a}; the two runs compared must differ")
    if ns.verb == "fix-check":
        _validate_fix_check(ns)


def _validate_fix_check(ns: argparse.Namespace) -> None:
    if (ns.failing_from is None) == (ns.inputs is None):
        raise _Refusal(
            "exactly one of --failing-from RUN and --inputs all is required; which inputs are "
            "compared has no default"
        )
    if ns.inputs is not None and ns.inputs != "all":
        raise _Refusal(f"--inputs takes only the value all, not {ns.inputs}")
    if ns.min_failures is not None:
        if ns.failing_from is None:
            raise _Refusal("--min-failures applies to --failing-from and was given without it")
        if ns.min_failures < 1:
            raise _Refusal("--min-failures must be at least 1")
    if ns.max_mde is None:
        raise _Refusal(
            "--max-mde is required, as a fraction of failure share (0.20 is twenty points); "
            "it has no default"
        )
    if not 0.0 < ns.max_mde < 1.0:
        raise _Refusal("--max-mde must be strictly between 0 and 1 (0.20 is twenty points)")
    if ns.old == ns.new:
        raise _Refusal(f"OLD and NEW are both {ns.old}; the two runs compared must differ")
    for arm, run in (("old", ns.old), ("new", ns.new)):
        if ns.failing_from == run:
            raise _Refusal(
                f"the selecting run {run} is also the {arm} arm; both arms must be fresh "
                "re-runs, because the selecting run's failures on these inputs are there by "
                "selection"
            )


# ---------- reading through Prove ----------


def _load(store: Any, run: str, *, trace: str = "envelope") -> tuple[Any, Any, Any]:
    """``(manifest, frame, tally)`` for ``run``, or a refusal naming the runs the store holds."""
    runs = store.runs()
    if run not in runs:
        held = ", ".join(runs) if runs else "no runs"
        raise _Refusal(f"unknown run {run}; the store holds: {held}")
    try:
        return (
            store.manifest(run),
            store.read(run, meta=False, trace=trace),
            store.tally(run),
        )
    except Exception as e:
        raise _Refusal(f"run {run} could not be read through Prove: {e}") from e


def _outcomes(frame: Any) -> set[str]:
    return {o for o in frame["outcome"] if o is not None}


def _header(run: str, manifest: Any, placement: Any) -> dict[str, Any]:
    from poisson_trace.clock import REASONS

    counts = {r: sum(1 for p in placement.rows if p.reason == r) for r in REASONS}
    return {
        "run_id": run,
        "target_id": manifest.target_id,
        "t_unit": manifest.t_unit,
        "status": manifest.status,
        "cap": placement.cap,
        "tally": placement.tally.to_dict(),
        "placement": {
            "placed": len(placement.rows),
            **counts,
            "excluded": dict(placement.excluded),
        },
    }


def _ordered(causes: set[str]) -> list[str]:
    from proofload.trace import KINDS

    return [k for k in KINDS if k in causes] + sorted(c for c in causes if c not in KINDS)


def _arrays(placement: Any) -> tuple[Any, Any, Any]:
    import numpy as np

    index = np.array([p.index for p in placement.rows], dtype=np.int64)
    died = np.array([p.died for p in placement.rows], dtype=bool)
    cause = np.array([p.cause for p in placement.rows], dtype=object)
    return index, died, cause


# ---------- where ----------


def _where(ns: argparse.Namespace) -> int:
    import proofload
    from proofload.steps import declaration_check
    from proofload.store import Store

    from poisson_trace.clock import _reached_by, place
    from poisson_trace.report import CANNOT_SAY, WhereReport
    from poisson_trace.survival import _band, aalen_johansen, bootstrap_band, kaplan_meier

    store = Store(ns.store)
    manifest, frame, tally = _load(store, ns.run)
    events = frozenset(ns.event)
    present = _outcomes(frame)
    missing = sorted(events - present)
    if missing:
        raise _Refusal(
            f"unknown event {', '.join(missing)}; the run carries the outcomes: "
            f"{', '.join(sorted(present)) or 'none'}"
        )
    placement = place(manifest, frame, tally, events=events, by=ns.by)
    index, died, cause = _arrays(placement)
    km = kaplan_meier(index, died)
    causes = _ordered({p.cause for p in placement.rows if p.died})
    aj = aalen_johansen(index, died, cause, causes)
    last = [int(km.steps[-1])] if len(km.steps) else []
    bands = (
        bootstrap_band(index, died, cause, causes, last, b=ns.boot, seed=ns.seed) if causes else {}
    )
    curve = []
    for step, at_risk, deaths, s, var in zip(
        km.steps, km.at_risk, km.deaths, km.survival, km.var, strict=True
    ):
        lo, hi = _band(float(s), float(var))
        curve.append(
            {
                "step": int(step),
                "at_risk": int(at_risk),
                "died": int(deaths),
                "survival": float(s),
                "var": float(var),
                "lo": lo,
                "hi": hi,
            }
        )
    at_rows = []
    for q in ns.at:
        s, var = km.at(q)
        lo, hi = _band(s, var)
        at_rows.append({"step": q, "survival": s, "lo": lo, "hi": hi})
    cause_rows = []
    for k in causes:
        f = float(aj.incidence[k][-1]) if len(aj.steps) else 0.0
        cause_rows.append(
            {
                "cause": k,
                "deaths": int(sum(1 for p in placement.rows if p.died and p.cause == k)),
                "f": f,
                "lo": float(bands[k][0][0]),
                "hi": float(bands[k][1][0]),
            }
        )
    data: dict[str, Any] = {
        "schema": "poisson-trace.where/1",
        "prove": {"version": proofload.__version__, "store": ns.store},
        "run": _header(ns.run, manifest, placement),
        "events": sorted(events),
        "clock": {"unit": "leaf span index", "by": ns.by},
        "curve": curve,
        "median_step": km.median(),
        "at": at_rows,
        "causes": cause_rows,
        "bootstrap": {"b": ns.boot, "seed": ns.seed},
    }
    check = declaration_check(manifest, frame)
    if check is not None:
        data["declared"] = check.provenance()
        data["_reached"] = _reached_by(manifest, frame, events=events, by=ns.by)
    data["cannot_say"] = list(CANNOT_SAY)
    report = WhereReport(
        data=data,
        last_step=int(index.max()) if len(index) else 0,
        incidence={k: [float(x) for x in aj.incidence[k]] for k in causes},
    )
    if ns.svg is not None:
        _write_svg(ns.svg, report.to_svg())
    sys.stdout.write(report.to_json() if ns.json else report.to_markdown())
    return 0


def _write_svg(path: str, text: str) -> None:
    Path(path).write_text(text)


# ---------- compare ----------


def _compare(ns: argparse.Namespace) -> int:
    import numpy as np
    import proofload
    from proofload.store import Store

    from poisson_trace.clock import place
    from poisson_trace.report import CANNOT_SAY, CompareReport
    from poisson_trace.survival import (
        bh,
        kaplan_meier,
        logrank_stratified,
        mde_hazard_ratio,
    )

    store = Store(ns.store)
    manifest_a, frame_a, tally_a = _load(store, ns.a)
    manifest_b, frame_b, tally_b = _load(store, ns.b)
    events = frozenset(ns.event)
    out_a, out_b = _outcomes(frame_a), _outcomes(frame_b)
    present = out_a | out_b
    missing = sorted(events - present)
    if missing:
        raise _Refusal(
            f"unknown event {', '.join(missing)}; the runs carry the outcomes: "
            f"{', '.join(sorted(present)) or 'none'}"
        )
    notes = [
        f"event {e}: carried by {'A' if e in out_a else 'B'} only"
        for e in sorted(events)
        if (e in out_a) != (e in out_b)
    ]
    placement_a = place(manifest_a, frame_a, tally_a, events=events, by=ns.by)
    placement_b = place(manifest_b, frame_b, tally_b, events=events, by=ns.by)
    rows_a, rows_b = placement_a.rows, placement_b.rows
    if not any(p.died for p in rows_a) and not any(p.died for p in rows_b):
        raise _Refusal(
            f"no death in either run for the events {', '.join(sorted(events))}; "
            "there is no curve to compare"
        )
    cells_a = {p.config_hash for p in rows_a}
    cells_b = {p.config_hash for p in rows_b}
    common = cells_a & cells_b
    if not common:
        raise _Refusal("the runs share no config cell, so there is nothing to stratify by")
    common_a = [p for p in rows_a if p.config_hash in common]
    common_b = [p for p in rows_b if p.config_hash in common]
    deaths_common = sum(p.died for p in common_a) + sum(p.died for p in common_b)
    if deaths_common == 0:
        raise _Refusal("no death in either run over the common cells; nothing to compare")
    share = len(common_a) / (len(common_a) + len(common_b))
    lr = logrank_stratified(
        [(p.config_hash, p.index, p.died) for p in rows_a],
        [(p.config_hash, p.index, p.died) for p in rows_b],
    )
    mde = mde_hazard_ratio(deaths_common, share, alpha=ns.alpha)
    if lr.observed_a < lr.expected_a:
        direction = "runs die later in A (before) than in B (after): runs die earlier in B"
        in_b = "earlier"
    elif lr.observed_a > lr.expected_a:
        direction = "runs die earlier in A (before) than in B (after): runs die later in B"
        in_b = "later"
    else:
        direction = "no direction"
        in_b = "neither earlier nor later"
    p_text = f"{lr.p:.3f}" if lr.p >= 0.001 else f"{lr.p:.2e}"
    if lr.p < ns.alpha:
        verdict, code = "different", 0
        verdict_line = (
            f"different: runs die {in_b} in B (after) than in A (before) "
            f"(log-rank, stratified by cell, p = {p_text})"
        )
    elif mde <= ns.max_mde_hr:
        verdict, code = "no significant difference", 0
        verdict_line = (
            f"no significant difference (p = {p_text}); could not have detected a hazard "
            f"ratio below {mde:.3f}"
        )
    else:
        verdict, code = "too small to tell", 2
        verdict_line = (
            f"too small to tell: could not have detected a hazard ratio below {mde:.3f}, "
            f"and {ns.max_mde_hr:g} was asked for"
        )
    guidance = None
    if verdict == "too small to tell":
        guidance = _compare_guidance(
            ns, deaths_common, len(common_a) + len(common_b), len(common), share, mde
        )
    km_a = kaplan_meier(*_arrays(placement_a)[:2])
    km_b = kaplan_meier(*_arrays(placement_b)[:2])
    at_rows = []
    for q in ns.at:
        sa, va = km_a.at(q)
        sb, vb = km_b.at(q)
        half = 1.96 * math.sqrt(va + vb)
        at_rows.append(
            {
                "step": q,
                "survival_a": sa,
                "survival_b": sb,
                "diff": sb - sa,
                "lo": sb - sa - half,
                "hi": sb - sa + half,
            }
        )
    causes = _ordered({p.cause for p in rows_a + rows_b if p.died})
    per: list[dict[str, Any]] = []
    for k in causes:
        lr_k = logrank_stratified(
            [(p.config_hash, p.index, p.died and p.cause == k) for p in rows_a],
            [(p.config_hash, p.index, p.died and p.cause == k) for p in rows_b],
        )
        d_k = sum(1 for p in common_a + common_b if p.died and p.cause == k)
        per.append(
            {
                "cause": k,
                "deaths_a": sum(1 for p in rows_a if p.died and p.cause == k),
                "deaths_b": sum(1 for p in rows_b if p.died and p.cause == k),
                "statistic": lr_k.statistic,
                "p": lr_k.p,
                "q": None,
                "mde_hazard_ratio": (
                    mde_hazard_ratio(d_k, share, alpha=ns.alpha) if d_k > 0 else None
                ),
            }
        )
    if per:
        qs = bh(np.array([r["p"] for r in per], dtype=np.float64), ns.alpha)
        for row, q_value in zip(per, qs, strict=True):
            row["q"] = float(q_value)
    data: dict[str, Any] = {
        "schema": "poisson-trace.compare/1",
        "prove": {"version": proofload.__version__, "store": ns.store},
        "runs": {
            "a": _header(ns.a, manifest_a, placement_a),
            "b": _header(ns.b, manifest_b, placement_b),
        },
        "events": sorted(events),
        "clock": {"unit": "leaf span index", "by": ns.by},
        "at": at_rows,
        "comparison": {
            "cells": lr.cells,
            "excluded_cells": {"a_only": len(cells_a - common), "b_only": len(cells_b - common)},
            "observed_a": lr.observed_a,
            "expected_a": lr.expected_a,
            "variance": lr.variance,
            "statistic": lr.statistic,
            "p": lr.p,
            "alpha": ns.alpha,
            "direction": direction,
            "paired": False,
            "mde_hazard_ratio": mde,
            "max_mde_hr": ns.max_mde_hr,
            "verdict": verdict,
            "guidance": guidance,
        },
        "per_cause": per,
        "cannot_say": list(CANNOT_SAY),
        "_observed_b": float(sum(p.died for p in common_b)),
        "_deaths_common": deaths_common,
        "_share_a": share,
        "_verdict_line": verdict_line,
        "_same_salt": manifest_a.run_salt == manifest_b.run_salt,
        "_event_notes": notes,
        "_placed_common": len(common_a) + len(common_b),
    }
    report = CompareReport(data=data)
    sys.stdout.write(report.to_json() if ns.json else report.to_markdown())
    return code


def _compare_guidance(
    ns: argparse.Namespace, deaths: int, placed: int, cells: int, share: float, mde: float
) -> dict[str, Any]:
    """Schoenfeld's line inverted at the ceiling asked for: the deaths needed, and the placed
    runs, inputs and repeats that many deaths take at the present share of deaths. The ceiling
    offered is the detectable hazard ratio rounded up, so it accepts the design as it stands."""
    from poisson_trace.paired import accepts_at
    from poisson_trace.survival import deaths_needed

    offered = accepts_at(mde, decimals=3) if math.isfinite(mde) else None
    try:
        needed = deaths_needed(ns.max_mde_hr, share, alpha=ns.alpha)
    except (ValueError, OverflowError):
        return dict.fromkeys(("deaths", "runs", "inputs", "repeats"), None) | {
            "accepts_at": offered
        }
    return {
        "deaths": needed,
        "runs": _ceil_ratio(placed * needed, deaths),
        "inputs": _ceil_ratio(cells * needed, deaths),
        "repeats": _ceil_ratio(placed * needed, 2 * cells * deaths),
        "accepts_at": offered,
    }


def _ceil_ratio(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)


# ---------- fix-check and changes ----------


@dataclass
class _Input:
    """One input's rows in one arm: how many ran to an outcome, how many of those failed, and
    how many had no outcome, split by Prove's timeout mark."""

    config: Any
    runs: int = 0
    failed: int = 0
    timed_out: int = 0
    no_outcome: int = 0


def _no_value(x: Any) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _by_input(frame: Any, events: frozenset[str]) -> dict[str, _Input]:
    arm: dict[str, _Input] = {}
    for h, config, outcome, error in zip(
        frame["config_hash"], frame["config"], frame["outcome"], frame["error"], strict=True
    ):
        row = arm.setdefault(str(h), _Input(config=config))
        if _no_value(outcome):
            if error == "timeout":
                row.timed_out += 1
            else:
                row.no_outcome += 1
        else:
            row.runs += 1
            row.failed += outcome in events
    return arm


def _declared_repeats(manifest: Any) -> int | None:
    environment = manifest.environment
    sweep = environment.get("sweep") if isinstance(environment, Mapping) else None
    declared = sweep.get("replicates") if isinstance(sweep, Mapping) else None
    if isinstance(declared, bool) or not isinstance(declared, int):
        return None
    return declared


def _paired_header(run: str, manifest: Any, tally: Any) -> dict[str, Any]:
    return {
        "run_id": run,
        "target_id": manifest.target_id,
        "status": manifest.status,
        "created_at": manifest.created_at,
        "declared_repeats": _declared_repeats(manifest),
        "tally": tally.to_dict(),
    }


def _started(run: str, manifest: Any) -> datetime:
    try:
        return datetime.fromisoformat(manifest.created_at)
    except (TypeError, ValueError) as e:
        raise _Refusal(f"run {run} carries no readable start time: {e}") from e


def _check_events(
    events: frozenset[str], frame_a: Any, frame_b: Any, first: str, second: str
) -> list[str]:
    """The first slice's rule: a name neither run carries is refused; a name one run carries
    is allowed, and noted."""
    out_a, out_b = _outcomes(frame_a), _outcomes(frame_b)
    present = {o for o in out_a | out_b if not _no_value(o)}
    missing = sorted(events - present)
    if missing:
        raise _Refusal(
            f"unknown event {', '.join(missing)}; the runs carry the outcomes: "
            f"{', '.join(sorted(present)) or 'none'}"
        )
    return [
        f"event {e}: carried by the {first if e in out_a else second} run only"
        for e in sorted(events)
        if (e in out_a) != (e in out_b)
    ]


def _arm_rows(arm: Mapping[str, _Input], compared: Sequence[str], declared: int | None) -> Any:
    rows = [arm[h] for h in compared]
    return {
        "runs": sum(r.runs for r in rows),
        "failed": sum(r.failed for r in rows),
        "timed_out": sum(r.timed_out for r in rows),
        "no_outcome": sum(r.no_outcome for r in rows),
        "short": 0 if declared is None else sum(1 for r in rows if r.runs < declared),
        "mixed": sum(1 for r in rows if 0 < r.failed < r.runs),
    }


def _changes_block(
    counts: Sequence[Any], configs: Mapping[str, Any], alpha: float
) -> dict[str, Any]:
    """The per-input flags and what the design could not have flagged."""
    from poisson_trace.paired import CANNOT_SAY, Counts, _fisher, flags

    by_hash = {c.config_hash: c for c in counts}
    rows = []
    for f in sorted(flags(counts, alpha=alpha), key=lambda f: (f.p, f.config_hash)):
        c = by_hash[f.config_hash]
        rows.append(
            {
                "config_hash": f.config_hash,
                "config": configs[f.config_hash],
                "failed_a": c.failed_old,
                "runs_a": c.runs_old,
                "failed_b": c.failed_new,
                "runs_b": c.runs_new,
                "change": f.change,
                "p": f.p,
                "q": f.q,
                "flag": f.flag,
                "limit_rise": f.limit_rise,
            }
        )

    def extreme(runs_old: int, runs_new: int) -> float:
        # none of the old arm's runs failed and every one of the new arm's did
        return _fisher(Counts("", 0, runs_old, runs_new, runs_new))

    tested = len(counts)
    smallest = min(extreme(a, b) for a, b in {(c.runs_old, c.runs_new) for c in counts})
    together = next((j for j in range(1, tested + 1) if smallest * tested / j < alpha), None)
    repeats = 1
    while extreme(repeats, repeats) > alpha / tested:
        repeats += 1
    return {
        "tested": tested,
        "flagged": sum(1 for r in rows if r["flag"] is not None),
        "alpha": alpha,
        "lone_threshold": alpha / tested,
        "smallest_attainable_p": smallest,
        "together": together,
        "lone_flip_repeats": repeats,
        "rows": rows,
        "cannot_say": list(CANNOT_SAY),
    }


def _number(x: float) -> float | None:
    return x if math.isfinite(x) else None


def _fix_check(ns: argparse.Namespace) -> int:
    import proofload
    from proofload.store import Store

    from poisson_trace import paired
    from poisson_trace.report import FixCheckReport, _points

    store = Store(ns.store)
    manifest_old, frame_old, tally_old = _load(store, ns.old, trace="none")
    manifest_new, frame_new, tally_new = _load(store, ns.new, trace="none")
    events = frozenset(ns.event)
    notes = _check_events(events, frame_old, frame_new, "old", "new")
    arm_old, arm_new = _by_input(frame_old, events), _by_input(frame_new, events)
    if ns.failing_from is not None:
        min_failures = 1 if ns.min_failures is None else ns.min_failures
        _, frame_sel, _ = _load(store, ns.failing_from, trace="none")
        selected = sorted(
            h for h, row in _by_input(frame_sel, events).items() if row.failed >= min_failures
        )
        rule = {"rule": "failing-from", "failing_from": ns.failing_from}
        rule["min_failures"] = min_failures
    else:
        selected = sorted(set(arm_old) | set(arm_new))
        rule = {"rule": "all", "failing_from": None, "min_failures": None}
    left_out = dict.fromkeys(paired.LEFT_OUT, 0)
    compared = []
    for h in selected:
        if h not in arm_old:
            left_out[paired.LEFT_OUT[0]] += 1
        elif h not in arm_new:
            left_out[paired.LEFT_OUT[1]] += 1
        elif arm_old[h].runs == 0:
            left_out[paired.LEFT_OUT[2]] += 1
        elif arm_new[h].runs == 0:
            left_out[paired.LEFT_OUT[3]] += 1
        else:
            compared.append(h)
    if not compared:
        reasons = "; ".join(f"{reason} {n}" for reason, n in left_out.items() if n)
        raise _Refusal(
            f"no input is left to compare: {len(selected)} selected"
            + (f", left out: {reasons}" if reasons else "")
        )
    counts = [
        paired.Counts(h, arm_old[h].failed, arm_old[h].runs, arm_new[h].failed, arm_new[h].runs)
        for h in compared
    ]
    header_old = _paired_header(ns.old, manifest_old, tally_old)
    header_new = _paired_header(ns.new, manifest_new, tally_new)
    gap = abs((_started(ns.new, manifest_new) - _started(ns.old, manifest_old)).total_seconds())
    rows_old = _arm_rows(arm_old, compared, header_old["declared_repeats"])
    rows_new = _arm_rows(arm_new, compared, header_new["declared_repeats"])

    test = paired.paired_test(counts)
    points, variance, lo, hi = paired.difference(counts, alpha=ns.alpha)
    by_p, moved, method = paired.by_input(counts, seed=ns.seed, draws=_DRAWS)
    drawn = method != "exact"
    share, again, kappa, within, pooled = paired.consistency(counts)
    drop = paired.detection_limit(counts, direction="drop", alpha=ns.alpha)
    rise = paired.detection_limit(counts, direction="rise", alpha=ns.alpha)

    if points < 0:
        direction, word = "failed less in new", "less"
    elif points > 0:
        direction, word = "failed more in new", "more"
    else:
        direction, word = "no direction", ""
    p_text = f"{test.p:.3f}" if test.p >= 0.001 else f"{test.p:.2e}"
    # every failure gone, and every run failing, as shifts in failure share: the largest a
    # proportional change can be on these inputs
    weights = [c.runs_old * c.runs_new / (c.runs_old + c.runs_new) for c in counts]
    rates = [(c.failed_old + c.failed_new) / (c.runs_old + c.runs_new) for c in counts]
    largest_drop = sum(w * r for w, r in zip(weights, rates, strict=True)) / sum(weights)
    asked = f"{100.0 * ns.max_mde:g}"
    limit_text = None if drop is None else _points(drop)
    guidance = None
    if test.p < ns.alpha and points != 0:
        verdict, code = "different", 0
        verdict_line = (
            f"different: the new version failed {word} on these inputs (exact "
            f"Cochran-Mantel-Haenszel, stratified by input, p = {p_text})"
        )
    elif drop is not None and drop <= ns.max_mde:
        verdict, code = "no significant difference", 0
        verdict_line = (
            f"no significant difference (p = {p_text}); could not have detected a drop in "
            f"failure share below {limit_text} points"
        )
    else:
        verdict, code = "too small to tell", 2
        if drop is None:
            verdict_line = (
                "too small to tell: could not have detected a drop in failure share below or "
                f"at {_points(largest_drop)} points, which is every failure gone, and {asked} "
                "was asked for"
            )
        else:
            verdict_line = (
                "too small to tell: could not have detected a drop in failure share below "
                f"{limit_text} points, and {asked} was asked for"
            )
        guidance = {
            "repeats": paired.repeats_needed(counts, ns.max_mde, alpha=ns.alpha),
            "inputs": paired.inputs_needed(counts, ns.max_mde, alpha=ns.alpha),
            "accepts_at": None if drop is None else paired.accepts_at(drop, decimals=4),
        }
    excludes_zero = lo is not None and hi is not None and (lo > 0.0 or hi < 0.0)
    configs = {h: arm_old[h].config for h in compared}
    data: dict[str, Any] = {
        "schema": "poisson-trace.fix-check/1",
        "prove": {"version": proofload.__version__, "store": ns.store},
        "runs": {"old": header_old, "new": header_new},
        "gap_seconds": gap,
        "events": sorted(events),
        "inputs": {
            **rule,
            "selected": len(selected),
            "compared": len(compared),
            "informative": test.informative,
            "left_out": left_out,
        },
        "rows": {"old": rows_old, "new": rows_new},
        "control": {
            "old_did_not_fail_share": 1.0 - rows_old["failed"] / rows_old["runs"],
            "new_did_not_fail_share": 1.0 - rows_new["failed"] / rows_new["runs"],
        },
        "test": {
            "name": "exact conditional Cochran-Mantel-Haenszel",
            "observed_new": test.observed_new,
            "expected_new": test.expected_new,
            "variance": test.variance,
            "weight": test.weight,
            "p": test.p,
            "alpha": ns.alpha,
        },
        "difference": {
            "points": points,
            "lo": lo,
            "hi": hi,
            "variance": variance,
            "interval": "Sato",
        },
        "by_input": {
            "moved": moved,
            "p": by_p,
            "method": method,
            "draws": _DRAWS if drawn else None,
            "seed": ns.seed if drawn else None,
        },
        "consistency": {
            "failure_share": share,
            "fails_again": _number(again),
            "kappa": _number(kappa),
            "within": within,
            "pooled": pooled,
        },
        "limits": {"drop": drop, "rise": rise, "power": 0.8, "max_mde": ns.max_mde},
        "verdict": verdict,
        "direction": direction,
        "guidance": guidance,
        "changes": _changes_block(counts, configs, ns.alpha),
        "cannot_say": list(paired.CANNOT_SAY),
        "_verdict_line": verdict_line,
        "_event_notes": notes,
        "_top": ns.top,
        "_largest": {"drop": largest_drop, "rise": 1.0 - largest_drop},
        "_disagree": variance is not None and ((test.p < ns.alpha) != excludes_zero),
        "_copies": [
            arm
            for arm, held in (("old", arm_old), ("new", arm_new))
            if all(held[h].runs >= 2 and not 0 < held[h].failed < held[h].runs for h in compared)
        ],
    }
    report = FixCheckReport(data=data)
    sys.stdout.write(report.to_json() if ns.json else report.to_markdown())
    return code


def _changes(ns: argparse.Namespace) -> int:
    import proofload
    from proofload.store import Store

    from poisson_trace import paired
    from poisson_trace.report import ChangesReport

    store = Store(ns.store)
    manifest_a, frame_a, tally_a = _load(store, ns.a, trace="none")
    manifest_b, frame_b, tally_b = _load(store, ns.b, trace="none")
    events = frozenset(ns.event)
    notes = _check_events(events, frame_a, frame_b, "A", "B")
    arm_a, arm_b = _by_input(frame_a, events), _by_input(frame_b, events)
    compared = sorted(h for h in set(arm_a) & set(arm_b) if arm_a[h].runs and arm_b[h].runs)
    if not compared:
        raise _Refusal(
            "no input has a run with an outcome in both runs, so there is nothing to compare"
        )
    counts = [
        paired.Counts(h, arm_a[h].failed, arm_a[h].runs, arm_b[h].failed, arm_b[h].runs)
        for h in compared
    ]
    gap = abs((_started(ns.b, manifest_b) - _started(ns.a, manifest_a)).total_seconds())
    data: dict[str, Any] = {
        "schema": "poisson-trace.changes/1",
        "prove": {"version": proofload.__version__, "store": ns.store},
        "runs": {
            "a": _paired_header(ns.a, manifest_a, tally_a),
            "b": _paired_header(ns.b, manifest_b, tally_b),
        },
        "events": sorted(events),
        **_changes_block(counts, {h: arm_a[h].config for h in compared}, ns.alpha),
        "_event_notes": notes,
        "_top": ns.top,
        "_gap_seconds": gap,
        "_inputs": {
            "a": len(arm_a),
            "b": len(arm_b),
            "a_only": len(set(arm_a) - set(arm_b)),
            "b_only": len(set(arm_b) - set(arm_a)),
        },
    }
    report = ChangesReport(data=data)
    sys.stdout.write(report.to_json() if ns.json else report.to_markdown())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
