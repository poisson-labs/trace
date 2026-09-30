"""The one module under ``ingest/`` that imports ``proofload``: a Run becomes one new run.

Every record is built before the store is touched, so a row Prove would not take is refused
with nothing written. The run is created, its rows appended in one part, and it is marked
complete; a run name the store already holds is refused, never appended to.
"""

from __future__ import annotations

import shutil
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from proofload.store import EpisodeRecord, RunManifest, Store, config_hash
from proofload.trace import CONTENT_KEYS, OBSERVATION_KEYS, Trace, from_otel

import poisson_trace
from poisson_trace.ingest.cut import MET, MISSED
from poisson_trace.ingest.rows import STARTED_FROM, Refusal, Row, Run


@dataclass(frozen=True)
class Written:
    run: str
    rows: int
    cases: int
    repeats_min: int
    repeats_max: int
    outcomes: Mapping[str, int]
    no_outcome: Mapping[str, int]


def _is_content(key: Any) -> bool:
    return key in CONTENT_KEYS or key in OBSERVATION_KEYS


def _without_content(span: Mapping[str, Any]) -> dict[str, Any]:
    """The span with every attribute dropped whose key is one of Prove's content keys. The
    list of content keys is Prove's and exists once."""
    out = dict(span)
    attributes = out.get("attributes")
    if isinstance(attributes, Mapping):
        out["attributes"] = {k: v for k, v in attributes.items() if not _is_content(k)}
    elif isinstance(attributes, (list, tuple)):
        out["attributes"] = [
            item
            for item in attributes
            if not (isinstance(item, Mapping) and _is_content(item.get("key")))
        ]
    return out


def _leaves(trace: Trace) -> int:
    parents = {span.parent_id for span in trace.spans}
    return sum(1 for span in trace.spans if span.span_id not in parents)


def _record(run: str, row: Row, repeat: int) -> EpisodeRecord:
    config = {"case": row.case}
    meta: dict[str, Any] = {"import": {"score": row.score, **row.detail}}
    steps = 0.0
    if row.spans:
        trace = from_otel([_without_content(span) for span in row.spans])
        meta["trace"] = trace.to_dict()
        steps = float(_leaves(trace))
    if row.outcome is None:
        if row.error is None:
            raise Refusal(f"a row of case {row.case} has neither an outcome nor a reason")
        return EpisodeRecord.errored(
            run_id=run,
            config=config,
            seed=0,
            replicate_index=repeat,
            error=row.error,
            wall_time=0.0,
            meta=meta,
        )
    return EpisodeRecord(
        run_id=run,
        config_hash=config_hash(config),
        config=config,
        seed=0,
        replicate_index=repeat,
        outcome=row.outcome,
        t=steps,
        horizon=steps,
        confidence=None,
        meta=meta,
        error=row.error,
        wall_time=0.0,
        backend_meta={},
    )


def write(run: Run, root: Path) -> Written:
    if run.started_from not in STARTED_FROM:
        raise Refusal(f"the start time's source is one of {', '.join(STARTED_FROM)}")
    store = Store(root)
    if run.name in store.runs() or (Path(root) / run.name).exists():
        raise Refusal(
            f"the store at {root} already holds a run named {run.name}; an import writes a "
            "new run and never adds to one, so give this one another name"
        )
    seen: Counter[str] = Counter()
    records = []
    try:
        for row in run.rows:
            records.append(_record(run.name, row, seen[row.case]))
            seen[row.case] += 1
    except (TypeError, ValueError) as e:
        raise Refusal(f"a row could not be written as Prove stores it: {e}") from e
    manifest = RunManifest(
        run_id=run.name,
        target_id=f"import/{run.tool}",
        t_unit="steps",
        run_salt="import",
        axis_types={"case": "categorical"},
        backend=f"import:{run.tool}",
        environment={
            "import": {
                "tool": run.tool,
                "started_from": run.started_from,
                "declared": dict(run.declared),
                "files": [dict(f) for f in run.files],
                "poisson_trace": poisson_trace.__version__,
            }
        },
        created_at=run.started,
    )
    try:
        store.create_run(manifest)
    except Exception as e:
        raise Refusal(f"the run {run.name} could not be created in the store: {e}") from e
    try:
        store.append(run.name, records)
        store.mark_complete(run.name)
    except Exception as e:
        # the run directory is this call's own: it did not exist when the call began
        shutil.rmtree(Path(root) / run.name, ignore_errors=True)
        raise Refusal(f"the run {run.name} could not be written: {e}") from e
    outcomes = Counter(row.outcome for row in run.rows if row.outcome is not None)
    words = [MET, MISSED, *sorted(o for o in outcomes if o not in (MET, MISSED))]
    no_outcome = Counter(str(row.error) for row in run.rows if row.outcome is None)
    return Written(
        run=run.name,
        rows=len(run.rows),
        cases=len(seen),
        repeats_min=min(seen.values(), default=0),
        repeats_max=max(seen.values(), default=0),
        outcomes={word: outcomes[word] for word in words},
        no_outcome={reason: no_outcome[reason] for reason in sorted(no_outcome)},
    )
