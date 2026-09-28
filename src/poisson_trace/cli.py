"""The console script: ``poisson-trace where`` and ``poisson-trace compare``.

``proofload`` is imported inside ``main`` and nowhere at module level, so the check that it is
present and at the pinned version runs first and reports in one sentence.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

PROVE_VERSION = "0.0.1"
_INSTALL = "pip install -e /path/to/prove"


class _Refusal(Exception):
    """One sentence, exit 1."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Any:
        raise _Refusal(f"argument error: {message}")


def _build_parser() -> _Parser:
    parser = _Parser(prog="poisson-trace", description="Where in the workflow runs die.")
    verbs = parser.add_subparsers(dest="verb", required=True, metavar="where|compare")

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
        return _where(ns) if ns.verb == "where" else _compare(ns)
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


# ---------- reading through Prove ----------


def _load(store: Any, run: str) -> tuple[Any, Any, Any]:
    """``(manifest, frame, tally)`` for ``run``, or a refusal naming the runs the store holds."""
    runs = store.runs()
    if run not in runs:
        held = ", ".join(runs) if runs else "no runs"
        raise _Refusal(f"unknown run {run}; the store holds: {held}")
    try:
        return (
            store.manifest(run),
            store.read(run, meta=False, trace="envelope"),
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
        },
        "per_cause": per,
        "cannot_say": list(CANNOT_SAY),
        "_observed_b": float(sum(p.died for p in common_b)),
        "_deaths_common": deaths_common,
        "_share_a": share,
        "_verdict_line": verdict_line,
        "_same_salt": manifest_a.run_salt == manifest_b.run_salt,
        "_event_notes": notes,
    }
    report = CompareReport(data=data)
    sys.stdout.write(report.to_json() if ns.json else report.to_markdown())
    return code


if __name__ == "__main__":
    raise SystemExit(main())
