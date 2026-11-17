"""A stored run as normalised rows: the Prove reader (spec section 18.1.1 row 1, 18.5.2; SA1, SA6).

A run Trace imported comes back from each record's ``meta["trace_signals"]`` exactly as the
writer put it there. A run Prove swept is read from Prove's own columns and its trace: the case
is the condition's hash, as every verb pairs; the repeat is the replicate; the result is
``fail`` when the outcome is one of the words given as failures, ``censored`` for an errored
row, else ``pass``; the time is the ``wall_time`` column; steps and the horizon are ``t`` and
``horizon``; tokens are summed from the spans' ``in`` and ``out``; the LLM calls are the ``llm``
spans; the tool calls are the ``tool`` spans; the error's type is the last line's class of a
traceback, else the first failing span's error, and the span kind where it happened is that
span's; a cost is read only from ``meta["cost_usd"]``. Nothing is read from a span's content.

A failed or errored try of a run Prove swept takes its kind from the first of these that gives
one: the kind its rollout recorded itself (``failure_kind`` in a ``poisson.trace-signals/1``
record with no ``case``, one of the 13 kinds; nothing else of that record is read); Prove's own
word ``timeout`` short of the step cap; the team's ``[[taxonomy.rules]]``, the first that
matches in the order written; the built-in rules that find a cause; the kind its outcome label
names (the team's ``[taxonomy.labels]``, else ``LABEL_KINDS``); ``wrong_answer`` for a graded
try; else ``unclassified_error``. Every try, failed or not, is held to the team's
``[signals.budgets]`` by what it records: its wall time, its tokens in and out together when
both are recorded, and its ``cost_usd``. An imported run's rows are not classified again.

Reading writes nothing, and goes through the writer's ``stored``, so that the writer stays the
one module under ``ingest/`` that imports ``poisson_prove``. This is not an import tool:
``cli.READERS`` does not name it.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from poisson_trace.ingest.rows import FAILURE_KINDS, Row, SpanRecord, ToolCallRecord
from poisson_trace.ingest.taxonomy import LABEL_KINDS, Budgets, Rule, classify
from poisson_trace.ingest.writer import RECORD_SCHEMA, stored

#: The class a traceback's last line names, ``package.module.Error: message`` or the class alone.
CLASS = re.compile(r"^([A-Za-z_][\w.]*)(?::|$)")
#: Prove's own error for a harness failure: a prefix, not a class.
INFRA = "infra:"
#: Prove's outcome word for a try its executor stopped at its time or step cap (SA3, reading 6
#: as ruled): read as the source's own ``timeout`` when the try did not reach its step cap.
TIMEOUT_WORD = "timeout"


def _num(x: Any) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        value = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(value) else value


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _count(x: Any) -> int | None:
    """A stored float that is a whole number, as the count it is; None otherwise."""
    value = _num(x)
    if value is None or not value.is_integer() or value < 0:
        return None
    return int(value)


def _spans(meta: Any) -> list[dict[str, Any]]:
    """The stored spans, in the order of their start then their id."""
    trace = meta.get("trace") if isinstance(meta, Mapping) else None
    spans = trace.get("spans") if isinstance(trace, Mapping) else None
    if not isinstance(spans, list):
        return []
    held = [dict(s) for s in spans if isinstance(s, Mapping)]
    return sorted(held, key=lambda s: (s.get("start_ns") or 0, str(s.get("span_id"))))


def _tokens(span: Mapping[str, Any], side: str) -> int | None:
    tokens = span.get("tokens")
    if not isinstance(tokens, Mapping):
        return None
    return _count(tokens.get(side))


def _span_record(span: Mapping[str, Any]) -> SpanRecord:
    ins, outs = _tokens(span, "in"), _tokens(span, "out")
    total = None if ins is None and outs is None else (ins or 0) + (outs or 0)
    return SpanRecord(
        span_id=str(span.get("span_id")),
        parent_id=_str(span.get("parent_id")),
        kind=str(span.get("kind")),
        name=str(span.get("name") or ""),
        start_ns=int(span.get("start_ns") or 0),
        end_ns=None if span.get("end_ns") is None else int(span["end_ns"]),
        tokens=total,
        input_tokens=ins,
        output_tokens=outs,
        error=_str(span.get("error")),
        code=_str(span.get("code")),
        operation=_str(span.get("operation")),
        step_name=_str(span.get("step_name")),
        outcome=_str(span.get("outcome")),
        outcome_by=_str(span.get("outcome_by")),
        attempt=_count(span.get("attempt")) or None,
        gate=_str(span.get("gate")),
        truncated=_str(span.get("truncated")),
        bytes_original=_count(span.get("bytes_original")),
    )


def _str(x: Any) -> str | None:
    return None if x is None else str(x)


def _tool_call(span: Mapping[str, Any]) -> ToolCallRecord:
    start, end = span.get("start_ns"), span.get("end_ns")
    duration = None if end is None or start is None else max(0.0, (end - start) / 1e9)
    error = _str(span.get("error"))
    return ToolCallRecord(
        name=str(span.get("name") or ""),
        status="error" if error else "ok",
        duration_s=duration,
        error_type=error if error else None,
        attempt=_count(span.get("attempt")) or 1,
    )


def _class_of(error: str | None) -> str | None:
    """The class the last line of a traceback names; None for an error that is no traceback,
    or that is Prove's own ``infra:`` word."""
    if error is None:
        return None
    lines = [line for line in error.strip().splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    last = lines[-1].strip()
    if last.startswith(INFRA):
        return None
    found = CLASS.match(last)
    return found.group(1) if found else None


def _swept(record: Mapping[str, Any], failed: Sequence[str], own: Any = None) -> Row:
    """A row of a run Prove swept, from its columns and its trace. ``own`` is the kind its
    rollout recorded itself, if any: kept on a failed or errored try when it is one of the 13
    kinds, before Prove's own ``timeout``."""
    meta = record.get("meta") if isinstance(record.get("meta"), Mapping) else {}
    outcome = _str(record.get("outcome"))
    error = _str(record.get("error"))
    spans = _spans(meta)
    failing = [s for s in spans if s.get("error")]
    ins = [t for t in (_tokens(s, "in") for s in spans) if t is not None]
    outs = [t for t in (_tokens(s, "out") for s in spans) if t is not None]
    attempts = [a for a in (_count(s.get("attempt")) for s in spans) if a is not None]
    steps, horizon = _count(record.get("t")), _count(record.get("horizon"))
    if error is not None:
        result = "censored"
    else:
        result = "fail" if outcome in failed else "pass"
    kind = None
    at_cap = steps is not None and horizon is not None and horizon > 0 and steps >= horizon
    if result in ("fail", "censored") and isinstance(own, str) and own in FAILURE_KINDS:
        kind = own
    elif result == "fail" and outcome == TIMEOUT_WORD and not at_cap:
        kind = TIMEOUT_WORD
    error_type = _class_of(error)
    if error_type is None and failing:
        error_type = _str(failing[0].get("error"))
    cost = meta.get("cost_usd") if isinstance(meta, Mapping) else None
    return Row(
        str(record["config_hash"]),
        outcome,
        error,
        _num(record.get("confidence")),
        None,
        {},
        repeat=int(record["replicate_index"]),
        result=result,
        failure_kind=kind,
        error_type=error_type,
        error_span_kind=str(failing[0]["kind"]) if failing else None,
        wall_time_s=_num(record.get("wall_time")),
        input_tokens=sum(ins) if ins else None,
        output_tokens=sum(outs) if outs else None,
        cost_usd=_num(cost) if _is_number(cost) else None,
        steps=steps,
        horizon=horizon,
        llm_calls=sum(1 for s in spans if s.get("kind") == "llm") if spans else None,
        tool_calls=tuple(_tool_call(s) for s in spans if s.get("kind") == "tool")
        if spans
        else None,
        retries=sum(a - 1 for a in attempts) if attempts else None,
        span_records=tuple(_span_record(s) for s in spans) if spans else None,
    )


def _imported(record: Mapping[str, Any], signals: Mapping[str, Any]) -> Row:
    """A row of a run Trace imported, from the record the writer kept."""
    calls = signals.get("tool_calls")
    return Row(
        str(signals["case"]),
        _str(record.get("outcome")),
        _str(record.get("error")),
        signals.get("score"),
        None,
        {},
        repeat=signals.get("repeat"),
        result=signals.get("outcome"),
        failure_kind=signals.get("failure_kind"),
        error_type=signals.get("error_type"),
        error_span_kind=signals.get("error_span_kind"),
        wall_time_s=signals.get("wall_time_s"),
        working_time_s=signals.get("working_time_s"),
        ttft_s=signals.get("ttft_s"),
        input_chars=signals.get("input_chars"),
        output_chars=signals.get("output_chars"),
        input_tokens=signals.get("input_tokens"),
        output_tokens=signals.get("output_tokens"),
        cached_tokens=signals.get("cached_tokens"),
        reasoning_tokens=signals.get("reasoning_tokens"),
        total_tokens=signals.get("total_tokens"),
        cost_usd=signals.get("cost_usd"),
        steps=signals.get("steps"),
        horizon=signals.get("horizon"),
        llm_calls=signals.get("llm_calls"),
        tool_calls=None if calls is None else tuple(ToolCallRecord(**c) for c in calls),
        retries=signals.get("retries"),
        scores=signals.get("scores") or {},
        feedback=signals.get("feedback") or {},
        signals=tuple(signals.get("signals") or ()),
    )


def read_rows(
    root: Path,
    run_id: str,
    failed: Sequence[str],
    labels: Mapping[str, str] | None = None,
    rules: Sequence[Rule] = (),
    budgets: Budgets | None = None,
) -> tuple[Row, ...]:
    """The rows of the run ``run_id`` of the store at ``root``, classified. ``failed`` names the
    outcome words that are failures of a run Prove swept; ``labels`` is the team's
    ``[taxonomy.labels]``, which wins over ``LABEL_KINDS``; ``rules`` and ``budgets`` are the
    team's ``[[taxonomy.rules]]`` and ``[signals.budgets]``. An imported run's result, kind and
    signals were decided at the import, and none of the four is read for it."""
    frame = stored(root, run_id)
    named = {**LABEL_KINDS, **(labels or {})}
    rows = []
    for record in frame.to_dict("records"):
        meta = record.get("meta")
        signals = meta.get("trace_signals") if isinstance(meta, Mapping) else None
        if not isinstance(signals, Mapping) or signals.get("schema") != RECORD_SCHEMA:
            signals = None
        if signals is not None and "case" in signals:
            # the whole record Trace's own import wrote
            rows.append(_imported(record, signals))
        else:
            # a rollout's own record of that schema carries no case: only its kind is read
            own = None if signals is None else signals.get("failure_kind")
            row = _swept(record, tuple(failed), own)
            rows.append(classify(row, tuple(rules), budgets, labels=named))
    return tuple(rows)
