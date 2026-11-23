"""The clock and the placement: leaves, step index, step labels, and where each row lands.

Reads a run only through ``poisson_prove.store.Store``, ``poisson_prove.steps.declaration_check``
and ``poisson_prove.trace.KINDS``. Spans are walked as plain mappings off the envelope.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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


def _label(
    span: Mapping[str, Any], by_id: Mapping[str, Mapping[str, Any]], by: Literal["kind", "step"]
) -> str:
    """A step's label: its span's kind, or the nearest step name up its parents. A parent chain
    that comes back to a span it has passed carries no step name, so the walk stops there."""
    if by == "kind":
        kind = span.get("kind")
        return kind if isinstance(kind, str) else _UNKNOWN_KIND
    node: Mapping[str, Any] | None = span
    passed: set[int] = set()
    while node is not None and id(node) not in passed:
        passed.add(id(node))
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


@dataclass(frozen=True)
class Conversation:
    """One row of a run: which conversation it is, where the clock placed it or why it did not,
    its spans, and its steps: the leaves in the clock's order, each with its label."""

    config_hash: str
    seed: int
    replicate_index: int
    placed: Placed | None
    exclusion: str | None
    spans: list[Mapping[str, Any]] | None
    leaves: tuple[Mapping[str, Any], ...] = ()
    labels: tuple[str, ...] = ()


def conversations(
    manifest: RunManifest,
    frame: pd.DataFrame,
    *,
    events: frozenset[str],
    by: Literal["kind", "step"],
) -> list[Conversation]:
    """Each row of the run in the store's order, read once: exactly one of ``placed`` and
    ``exclusion`` is set, and a placed row carries the label of every one of its steps."""
    cap = _cap_of(manifest)
    columns = (
        frame["config_hash"],
        frame["seed"],
        frame["replicate_index"],
        frame["outcome"],
        frame["error"],
        frame["trace"],
    )
    out: list[Conversation] = []
    for config_hash, seed, replicate, outcome, error, envelope in zip(*columns, strict=True):
        who = (str(config_hash), int(seed), int(replicate))
        if envelope is None:
            out.append(Conversation(*who, None, "no trace", None))
            continue
        spans = _spans_of(envelope)
        if spans is None:
            out.append(Conversation(*who, None, "unreadable trace", None))
            continue
        found = _leaves(spans)
        if not found:
            out.append(Conversation(*who, None, "no leaf span", spans))
            continue
        if outcome is None and error != _TIMEOUT:
            out.append(Conversation(*who, None, "no outcome, not a timeout", spans))
            continue
        if outcome is None:
            reason = "timed out"
        elif cap is not None and len(spans) >= cap:
            reason = "capped"
        elif outcome in events:
            reason = "died"
        else:
            reason = "ended"
        by_id = {span["span_id"]: span for span in spans} if by == "step" else {}
        labels = tuple(_label(leaf, by_id, by) for leaf in found)
        placed = Placed(
            config_hash=who[0],
            index=len(found),
            died=reason == "died",
            cause=labels[-1],
            reason=reason,
        )
        out.append(Conversation(*who, placed, None, spans, tuple(found), labels))
    return out


def placement(rows: Sequence[Conversation], manifest: RunManifest, tally: RunTally) -> Placement:
    """Where the rows landed: the placed ones in order, and the count of each exclusion."""
    excluded = {reason: 0 for reason in EXCLUSIONS}
    for row in rows:
        if row.exclusion is not None:
            excluded[row.exclusion] += 1
    return Placement(
        rows=tuple(row.placed for row in rows if row.placed is not None),
        excluded=excluded,
        tally=tally,
        cap=_cap_of(manifest),
    )


def place(
    manifest: RunManifest,
    frame: pd.DataFrame,
    tally: RunTally,
    *,
    events: frozenset[str],
    by: Literal["kind", "step"],
) -> Placement:
    return placement(conversations(manifest, frame, events=events, by=by), manifest, tally)


def _reached_by(rows: Sequence[Conversation]) -> dict[str, int]:
    """For each ``step_name`` any span carries, the number of placed rows carrying it."""
    counts: dict[str, int] = {}
    for row in rows:
        if row.placed is None or row.spans is None:
            continue
        names = {span.get("step_name") for span in row.spans}
        for name in names:
            if isinstance(name, str):
                counts[name] = counts.get(name, 0) + 1
    return counts
