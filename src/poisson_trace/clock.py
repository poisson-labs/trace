"""The clock and the placement: leaves, step index, cause labels, and where each row lands.

Reads a run only through ``poisson_prove.store.Store``, ``poisson_prove.steps.declaration_check``
and ``poisson_prove.trace.KINDS``. Spans are walked as plain mappings off the envelope.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd
from poisson_prove.store import RunManifest, RunTally

REASONS: tuple[str, ...] = ("died", "ended", "timed out", "capped")
EXCLUSIONS: tuple[str, ...] = (
    "no trace",
    "unreadable trace",
    "no leaf span",
    "no outcome, not a timeout",
)

_TIMEOUT = "timeout"
_UNKNOWN_KIND = "unknown"
_UNNAMED = "unnamed"


@dataclass(frozen=True)
class Placed:
    config_hash: str
    index: int
    died: bool
    cause: str
    reason: str


@dataclass(frozen=True)
class Placement:
    rows: tuple[Placed, ...]
    excluded: Mapping[str, int]
    tally: RunTally
    cap: int | None


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _spans_of(envelope: Any) -> list[Mapping[str, Any]] | None:
    """The envelope's spans as mappings, or ``None`` when the trace cannot be read."""
    if not isinstance(envelope, Mapping):
        return None
    raw = envelope.get("spans")
    if not isinstance(raw, (list, tuple)):
        return None
    spans: list[Mapping[str, Any]] = []
    for span in raw:
        if not isinstance(span, Mapping):
            return None
        if not isinstance(span.get("span_id"), str) or not _is_int(span.get("start_ns")):
            return None
        spans.append(span)
    return spans


def _leaves(spans: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The spans that parent no other span, in ``(start_ns, span_id)`` order."""
    parents = {span.get("parent_id") for span in spans}
    found = [span for span in spans if span["span_id"] not in parents]
    found.sort(key=lambda span: (span["start_ns"], span["span_id"]))
    return found


def _cause_of(
    leaf: Mapping[str, Any], spans: list[Mapping[str, Any]], by: Literal["kind", "step"]
) -> str:
    if by == "kind":
        kind = leaf.get("kind")
        return kind if isinstance(kind, str) else _UNKNOWN_KIND
    by_id = {span["span_id"]: span for span in spans}
    node: Mapping[str, Any] | None = leaf
    while node is not None:
        name = node.get("step_name")
        if isinstance(name, str):
            return name
        parent = node.get("parent_id")
        node = by_id.get(parent) if isinstance(parent, str) else None
    return _UNNAMED


def _cap_of(manifest: RunManifest) -> int | None:
    capture = manifest.environment.get("capture")
    if not isinstance(capture, Mapping):
        return None
    value = capture.get("max_spans")
    return value if _is_int(value) else None


def _rows(
    manifest: RunManifest,
    frame: pd.DataFrame,
    *,
    events: frozenset[str],
    by: Literal["kind", "step"],
) -> Iterator[tuple[Placed | None, str | None, list[Mapping[str, Any]] | None]]:
    """Each row as ``(placed, exclusion, spans)``: exactly one of the first two is set."""
    cap = _cap_of(manifest)
    columns = (frame["config_hash"], frame["outcome"], frame["error"], frame["trace"])
    for config_hash, outcome, error, envelope in zip(*columns, strict=True):
        if envelope is None:
            yield None, "no trace", None
            continue
        spans = _spans_of(envelope)
        if spans is None:
            yield None, "unreadable trace", None
            continue
        found = _leaves(spans)
        if not found:
            yield None, "no leaf span", spans
            continue
        if outcome is None and error != _TIMEOUT:
            yield None, "no outcome, not a timeout", spans
            continue
        if outcome is None:
            reason = "timed out"
        elif cap is not None and len(spans) >= cap:
            reason = "capped"
        elif outcome in events:
            reason = "died"
        else:
            reason = "ended"
        placed = Placed(
            config_hash=str(config_hash),
            index=len(found),
            died=reason == "died",
            cause=_cause_of(found[-1], spans, by),
            reason=reason,
        )
        yield placed, None, spans


def place(
    manifest: RunManifest,
    frame: pd.DataFrame,
    tally: RunTally,
    *,
    events: frozenset[str],
    by: Literal["kind", "step"],
) -> Placement:
    rows: list[Placed] = []
    excluded = {reason: 0 for reason in EXCLUSIONS}
    for placed, exclusion, _ in _rows(manifest, frame, events=events, by=by):
        if placed is not None:
            rows.append(placed)
        elif exclusion is not None:
            excluded[exclusion] += 1
    return Placement(rows=tuple(rows), excluded=excluded, tally=tally, cap=_cap_of(manifest))


def _reached_by(
    manifest: RunManifest,
    frame: pd.DataFrame,
    *,
    events: frozenset[str],
    by: Literal["kind", "step"],
) -> dict[str, int]:
    """For each ``step_name`` any span carries, the number of placed rows carrying it."""
    counts: dict[str, int] = {}
    for placed, _, spans in _rows(manifest, frame, events=events, by=by):
        if placed is None or spans is None:
            continue
        names = {span.get("step_name") for span in spans}
        for name in names:
            if isinstance(name, str):
                counts[name] = counts.get(name, 0) + 1
    return counts
