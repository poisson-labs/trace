"""The ``steps`` and ``timings`` keys of the ``where`` and ``compare`` JSON.

``steps`` counts, for every step on the clock, the conversations that reached it and those that
ended there. ``timings`` lists each conversation's steps with when each started and how long it
took, and the spans above them, so a reader can draw the tree. Both are made from the rows the
clock has already read (``clock.conversations``), and carry times, kinds, ids, labels and counts
only: no span name and nothing a span recorded.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from poisson_trace.clock import REASONS, Conversation

#: The reason ``not_listed`` gives for a conversation that one run of a comparison does not hold.
NOT_IN_RUN = "not in the run"
# the longest span id written as it is stored; a longer one is written as a digest
_LONGEST_ID = 80
_UNKNOWN_KIND = "unknown"

Named = tuple[str, int]


def last_step(rows: Sequence[Conversation]) -> int:
    """The last step any placed conversation reached; 0 when none is placed."""
    return max((row.placed.index for row in rows if row.placed is not None), default=0)


def _counts(counted: Counter[str], order: Sequence[str]) -> list[dict[str, Any]]:
    return [{"label": label, "count": counted[label]} for label in order if counted[label] > 0]


def steps_of(
    rows: Sequence[Conversation],
    causes: Sequence[str],
    last: int,
    ordered: Callable[[set[str]], list[str]],
) -> list[dict[str, Any]]:
    """One entry for each step from 1 to ``last``: how many placed conversations reached it, how
    many ended there and how, the deaths there by label in the order of ``causes``, and the
    labels the step had for those that reached it, in the order ``ordered`` gives. A step past
    the run's own last step is listed with zeros, so two runs can share one axis."""
    ends = [dict.fromkeys(REASONS, 0) for _ in range(last)]
    died: list[Counter[str]] = [Counter() for _ in range(last)]
    labels: list[Counter[str]] = [Counter() for _ in range(last)]
    for row in rows:
        if row.placed is None:
            continue
        at = row.placed.index - 1
        ends[at][row.placed.reason] += 1
        if row.placed.died:
            died[at][row.placed.cause] += 1
        for i, label in enumerate(row.labels):
            labels[i][label] += 1
    out: list[dict[str, Any]] = []
    reached = 0
    for at in reversed(range(last)):
        ended_here = sum(ends[at].values())
        reached += ended_here
        out.append(
            {
                "step": at + 1,
                "reached": reached,
                "ended_here": ended_here,
                "ends": ends[at],
                "died_by": _counts(died[at], causes),
                "labels": _counts(labels[at], ordered(set(labels[at]))),
            }
        )
    out.reverse()
    return out


def written_id(span_id: str) -> str:
    """A span id as it is written: as stored when it is printable and at most 80 characters,
    else ``sha256:`` and the first 16 hex of its digest. A span's own id and a child's link to
    it go through this one rule, so the two are equal as text."""
    if len(span_id) <= _LONGEST_ID and span_id.isprintable():
        return span_id
    return "sha256:" + hashlib.sha256(span_id.encode("utf-8")).hexdigest()[:16]


def _is_whole(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _duration(span: Mapping[str, Any]) -> int | None:
    """The span's end less its start; None for a span with no end, or with an end that is not a
    whole number or is before its start."""
    end, start = span.get("end_ns"), span["start_ns"]
    if not _is_whole(end) or end < start:
        return None
    return int(end - start)


def _kind(span: Mapping[str, Any]) -> str:
    from poisson_prove.trace import KINDS

    kind = span.get("kind")
    return kind if isinstance(kind, str) and kind in KINDS else _UNKNOWN_KIND


def _by_id(spans: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]] | None:
    """The spans by id when their parent links form a forest; None when two spans share an id
    or a chain of parents comes back on itself, since the links cannot then be followed."""
    by_id: dict[str, Mapping[str, Any]] = {}
    for span in spans:
        if span["span_id"] in by_id:
            return None
        by_id[span["span_id"]] = span
    ends_at_a_root: set[str] = set()
    for span in spans:
        chain: set[str] = set()
        at: Any = span["span_id"]
        while isinstance(at, str) and at in by_id and at not in ends_at_a_root:
            if at in chain:
                return None
            chain.add(at)
            at = by_id[at].get("parent_id")
        ends_at_a_root |= chain
    return by_id


def item_of(row: Conversation) -> dict[str, Any]:
    """A placed conversation in ``timings``: which it is, how it ended, each step's times, and
    the spans above the steps. Offsets are from the earliest start of all its spans. A link to a
    parent that is not a span of the trace is written as none, so the span reads as a root."""
    assert row.placed is not None and row.spans is not None
    spans = row.spans
    start = min(span["start_ns"] for span in spans)
    by_id = _by_id(spans)

    def parent_of(span: Mapping[str, Any]) -> str | None:
        parent = span.get("parent_id")
        if by_id is None or not isinstance(parent, str) or parent not in by_id:
            return None
        return written_id(parent)

    steps = [
        {
            "step": i + 1,
            "offset_ns": int(leaf["start_ns"] - start),
            "duration_ns": _duration(leaf),
            "kind": _kind(leaf),
            "label": label,
            "span_id": written_id(leaf["span_id"]),
            "parent_id": parent_of(leaf),
        }
        for i, (leaf, label) in enumerate(zip(row.leaves, row.labels, strict=True))
    ]
    parents: list[dict[str, Any]] | None = None
    if by_id is not None:
        leaves = {id(leaf) for leaf in row.leaves}
        above = sorted(
            (span for span in spans if id(span) not in leaves),
            key=lambda span: (span["start_ns"], span["span_id"]),
        )
        parents = [
            {
                "span_id": written_id(span["span_id"]),
                "parent_id": parent_of(span),
                "kind": _kind(span),
                "offset_ns": int(span["start_ns"] - start),
                "duration_ns": _duration(span),
            }
            for span in above
        ]
    return {
        "config_hash": row.config_hash,
        "seed": row.seed,
        "replicate_index": row.replicate_index,
        "end": row.placed.reason,
        "cause": row.placed.cause if row.placed.died else None,
        "steps": steps,
        "parents": parents,
    }


def _size(item: Mapping[str, Any]) -> int:
    """What an item counts toward the ceiling: its steps and its parent spans."""
    return len(item["steps"]) + len(item["parents"] or ())


@dataclass(frozen=True)
class Timings:
    """One run's ``timings`` object, and whether the ceiling stopped its list short."""

    document: dict[str, Any]
    cut: bool


def held(rows: Sequence[Conversation]) -> set[Named]:
    """The conversations a run holds, placed or not."""
    return {(row.config_hash, row.replicate_index) for row in rows}


def timings_of(rows: Sequence[Conversation], named: Sequence[Named] | None, most: int) -> Timings:
    """A run's ``timings``. With ``named`` None, every placed conversation in the store's order,
    each whole, stopping before the first that would take the steps and parent spans listed
    past ``most``. With ``named``, those conversations only and no ceiling: each is listed
    whole when the run placed it, and is otherwise in ``not_listed`` with why."""
    placed = [row for row in rows if row.placed is not None]
    items: list[dict[str, Any]] = []
    not_listed: list[dict[str, Any]] = []
    cut = False
    if named is None:
        room = most
        for row in placed:
            item = item_of(row)
            if _size(item) > room:
                cut = True
                break
            room -= _size(item)
            items.append(item)
    else:
        by_name = {(row.config_hash, row.replicate_index): row for row in rows}
        for name in named:
            found = by_name.get(name)
            if found is not None and found.placed is not None:
                items.append(item_of(found))
                continue
            why = NOT_IN_RUN if found is None else found.exclusion
            not_listed.append({"config_hash": name[0], "replicate_index": name[1], "why": why})
    steps = [step for item in items for step in item["steps"]]
    parents = [parent for item in items for parent in item["parents"] or ()]
    document = {
        "most_steps": most if named is None else None,
        "conversations": len(placed),
        "listed": len(items),
        "no_end": sum(1 for step in steps if step["duration_ns"] is None),
        "parents_no_end": sum(1 for parent in parents if parent["duration_ns"] is None),
        "no_tree": sum(1 for item in items if item["parents"] is None),
        "asked": None
        if named is None
        else [{"config_hash": h, "replicate_index": i} for h, i in named],
        "not_listed": not_listed,
        "items": items,
    }
    return Timings(document, cut)


def name_word(name: Named, hash_width: int | None = None) -> str:
    """A conversation as ``--timings-of`` takes it, ``HASH:REPLICATE``; the hash cut to
    ``hash_width`` characters where a line of text shows it."""
    return f"{name[0][:hash_width]}:{name[1]}"


def missing(named: Sequence[Named], holds: Collection[Named]) -> list[Named]:
    """The named conversations that are in none of the runs read."""
    return [name for name in named if name not in holds]


def not_listed_line(document: Mapping[str, Any], side: str = "") -> str:
    """The line for a named request some of whose conversations are not listed, each with why."""
    from poisson_trace.look import count

    missed = ", ".join(
        f"{name_word((entry['config_hash'], entry['replicate_index']), 12)} ({entry['why']})"
        for entry in document["not_listed"]
    )
    return (
        f"timings lists {count(document['listed'])} of the {count(len(document['asked']))} "
        f"conversations asked{side}; not listed: {missed}"
    )
