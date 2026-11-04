"""The module under ``ingest/`` that writes through ``poisson_prove``: a Run becomes one new run.

Every record is built before the store is touched, so a row Prove would not take is refused
with nothing written. The run is created, its rows appended in one part, and it is marked
complete; a run name the store already holds is refused, never appended to.

Each row is classified by the taxonomy before it is written, and its normalised signals go into
the record's ``meta["trace_signals"]`` as the ``poisson.trace-signals/1`` record (spec section
18.4.2 as SA1 reads it on the Prove Trace reads): ``wall_time``, ``t``, ``horizon`` and
``confidence`` take the row's signals where recorded, ``meta["cost_usd"]`` is written where a
cost was recorded, a row without an outcome stays an errored record, and the digest of the rules
that classified the run is recorded in the manifest beside what the import declared (SA5). The
run's ``events.jsonl`` holds Prove's own ``started`` and ``finished`` events and nothing more
(SA4).
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from poisson_prove.store import EpisodeRecord, RunManifest, Store, config_hash
from poisson_prove.trace import CONTENT_KEYS, OBSERVATION_KEYS, Trace, from_otel

import poisson_trace
from poisson_trace.ingest.cut import MET, MISSED
from poisson_trace.ingest.rows import STARTED_FROM, Refusal, Row, Run, zone_of
from poisson_trace.ingest.taxonomy import Budgets, Rule, classify, taxonomy_sha256
from poisson_trace.look import why
from poisson_trace.names import taken

#: The signals record's schema, and its keys in the order written (section 18.4.2, plus horizon).
RECORD_SCHEMA = "poisson.trace-signals/1"
RECORD_KEYS: tuple[str, ...] = (
    "schema",
    "case",
    "repeat",
    "outcome",
    "failure_kind",
    "error_type",
    "error_span_kind",
    "wall_time_s",
    "working_time_s",
    "ttft_s",
    "input_chars",
    "output_chars",
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "reasoning_tokens",
    "total_tokens",
    "cost_usd",
    "steps",
    "horizon",
    "llm_calls",
    "tool_call_count",
    "tool_error_count",
    "tool_calls",
    "retries",
    "score",
    "scores",
    "feedback",
    "signals",
)
#: The fields of the record copied from the row under their own name.
_COPIED: tuple[str, ...] = (
    "failure_kind",
    "error_type",
    "error_span_kind",
    "wall_time_s",
    "working_time_s",
    "ttft_s",
    "input_chars",
    "output_chars",
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "reasoning_tokens",
    "total_tokens",
    "cost_usd",
    "steps",
    "horizon",
    "llm_calls",
)
EVENT_SCHEMA = "poisson.run-event/1"
EVENTS = "events.jsonl"


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


def trace_signals(row: Row, repeat: int) -> dict[str, Any]:
    """The ``poisson.trace-signals/1`` record of ``row`` as the repeat ``repeat`` of its case:
    every key of section 18.4.2 in order, ``None`` kept where the source recorded nothing. Its
    ``outcome`` is the row's normalised result. It carries no error text (IC7)."""
    calls = row.tool_calls
    record: dict[str, Any] = {
        "schema": RECORD_SCHEMA,
        "case": row.case,
        "repeat": repeat,
        "outcome": row.result,
    }
    for name in _COPIED:
        record[name] = getattr(row, name)
    record["tool_call_count"] = None if calls is None else len(calls)
    record["tool_error_count"] = (
        None if calls is None else sum(1 for c in calls if c.status == "error")
    )
    record["tool_calls"] = (
        None
        if calls is None
        else [
            {
                "name": c.name,
                "status": c.status,
                "duration_s": c.duration_s,
                "error_type": c.error_type,
                "attempt": c.attempt,
            }
            for c in calls
        ]
    )
    record["retries"] = row.retries
    record["score"] = row.score
    record["scores"] = dict(row.scores)
    record["feedback"] = dict(row.feedback)
    record["signals"] = list(row.signals)
    return record


def _record(run: str, row: Row, repeat: int) -> EpisodeRecord:
    """``row``, already classified, as the record Prove stores (section 18.4.2 as SA1 reads it)."""
    config = {"case": row.case}
    meta: dict[str, Any] = {"import": {"score": row.score, **row.detail}}
    if row.cost_usd is not None:
        meta["cost_usd"] = row.cost_usd
    steps = 0.0
    if row.spans:
        trace = from_otel([_without_content(span) for span in row.spans])
        meta["trace"] = trace.to_dict()
        steps = float(_leaves(trace))
    meta["trace_signals"] = trace_signals(row, repeat)
    # the column cannot say "not recorded": the record keeps that apart
    wall_time = 0.0 if row.wall_time_s is None else row.wall_time_s
    if row.outcome is None:
        if row.error is None:
            raise Refusal(f"a row of case {row.case} has neither an outcome nor a reason")
        return EpisodeRecord.errored(
            run_id=run,
            config=config,
            seed=0,
            replicate_index=repeat,
            error=row.error,
            wall_time=wall_time,
            meta=meta,
        )
    t = steps if row.steps is None else float(row.steps)
    return EpisodeRecord(
        run_id=run,
        config_hash=config_hash(config),
        config=config,
        seed=0,
        replicate_index=repeat,
        outcome=row.outcome,
        t=t,
        horizon=t if row.horizon is None else float(row.horizon),
        confidence=row.score,
        meta=meta,
        error=row.error,
        wall_time=wall_time,
        backend_meta={},
    )


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _event(at: str, kind: str, detail: Mapping[str, Any]) -> str:
    return json.dumps({"schema": EVENT_SCHEMA, "at": at, "kind": kind, "detail": dict(detail)})


def stored(root: Path, name: str) -> Any:
    """Every row of the run ``name`` of the store at ``root``, with its meta and its whole trace,
    as Prove reads them: the frame the Prove reader (``ingest/prove.py``) reads rows from, here
    so that this module stays the one under ``ingest/`` that imports ``poisson_prove``."""
    return Store(root).read(name, meta=True, trace="full")


def status(root: Path, name: str) -> str | None:
    """The status Prove records for a run of the store, or None when it cannot be read."""
    try:
        return Store(root).manifest(name).status
    except Exception:
        return None


def write(
    run: Run,
    root: Path,
    form: str = "target",
    *,
    rules: Sequence[Rule] = (),
    budgets: Budgets | None = None,
) -> Written:
    """Write ``run`` as one new run of the store at ``root``; ``form`` is how the store's runs
    are named from their manifests, for the check that no other run answers to its name. Each
    row is classified with ``rules`` and ``budgets`` (the config's, or none) before it is
    written, and their digest is recorded in the manifest."""
    if run.started_from not in STARTED_FROM:
        raise Refusal(f"the start time's source is one of {', '.join(STARTED_FROM)}")
    store = Store(root)
    try:
        stored = store.runs()
        held = run.name in stored or (Path(root) / run.name).exists()
    except OSError as e:
        raise Refusal(
            f"the store at {root} cannot take a run named {run.name} ({why(e)}); nothing was "
            "written"
        ) from e
    if held:
        raise Refusal(
            f"the store at {root} already holds a run named {run.name}; an import writes a "
            "new run and never adds to one, so give this one another name"
        )
    # the import's name is the word for its run, so no other run may answer to it
    in_use = taken(store, stored, Path(root), run.name, form) if stored else None
    if in_use is not None:
        raise Refusal(in_use)
    seen: Counter[str] = Counter()
    records = []
    try:
        for row in run.rows:
            records.append(_record(run.name, classify(row, rules, budgets), seen[row.case]))
            seen[row.case] += 1
    except (TypeError, ValueError) as e:
        raise Refusal(f"a row could not be written as Prove stores it ({why(e)})") from e
    recorded: dict[str, Any] = {
        "tool": run.tool,
        "started_from": run.started_from,
        "declared": dict(run.declared),
        "taxonomy_sha256": taxonomy_sha256(rules, budgets),
        "files": [dict(f) for f in run.files],
        "poisson_trace": poisson_trace.__version__,
    }
    if run.started_from == "file name":
        # a time in a file's name carries no zone: the one it was read in is kept with it
        recorded["zone"] = zone_of(run.started)
    manifest = RunManifest(
        run_id=run.name,
        target_id=f"import/{run.tool}",
        t_unit="steps",
        run_salt="import",
        axis_types={"case": "categorical"},
        backend=f"import:{run.tool}",
        environment={"import": recorded},
        created_at=run.started,
    )
    started_at = _now()
    try:
        store.create_run(manifest)
    except Exception as e:
        raise Refusal(
            f"Prove could not create the run {run.name} in {root} ({why(e)}); nothing was written"
        ) from e
    try:
        store.append(run.name, records)
        store.mark_complete(run.name)
        lines = [
            _event(started_at, "started", {"run_id": run.name}),
            _event(_now(), "finished", {"status": "complete", "kept": len(records)}),
        ]
        text = "".join(f"{line}\n" for line in lines)
        (Path(root) / run.name / EVENTS).write_text(text, encoding="utf-8")
    except Exception as e:
        # the run directory is this call's own: it did not exist when the call began
        shutil.rmtree(Path(root) / run.name, ignore_errors=True)
        raise Refusal(
            f"Prove could not write the run {run.name} into {root} ({why(e)}); nothing was kept"
        ) from e
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
