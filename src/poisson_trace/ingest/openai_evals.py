"""OpenAI Evals records, as ``oaieval ... --record_path log.jsonl`` writes them.

A record is JSON Lines: a ``spec`` line, a ``final_report`` line, then events. Each ``match``
event is one row: ``missed`` when its ``data.correct`` is false, ``met`` when true; its case is
its ``sample_id``, and the ``match`` events of one sample are its repeats in ``event_id`` order.
Every other event type is counted and is not a row. The start is the spec's ``created_at``, read
as UTC when it carries no zone, which the summary says; the eval's name and its completion
functions are declared.

The signals read of a ``match`` event: the length of its sampled answer, and its ``score`` where
written; a missed match is a wrong answer, or abstained when the answer is empty. Nothing of the
sampled answer, the expected answer, the options, the pick or the spec's run configuration is kept.

Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from poisson_trace.ingest.cut import MET, MISSED
from poisson_trace.ingest.rows import Refusal, Row, Run, case_id
from poisson_trace.look import why

DESCRIPTION = """\
Read OpenAI Evals records (oaieval's --record_path file) and write them as one new run. Each
match event is one row: met when it was correct, missed when it was not; its case is its
sample, and the match events of one sample are its repeats, in the order of their event ids.
Other events are counted, not read as rows. The start is the spec line's created_at, read as UTC
when it carries no zone. Nothing of a sampled or expected answer is kept.
"""
EXAMPLE = "poisson-trace import openai-evals old.jsonl --store trace-store --run old"

TOOL = "openai-evals"
MATCH = "match"
UNZONED = "the spec's created_at carries no zone, so it was read as UTC"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """The record says everything an import needs: no flag of its own."""


@dataclass
class _Record:
    """One record file: its digest, its spec, and its match events with the line each is on."""

    path: Path
    sha256: str
    spec: Mapping[str, Any]
    matches: list[tuple[int, int, Mapping[str, Any]]] = field(default_factory=list)
    events: Counter[str] = field(default_factory=Counter)


def _not_a_record(path: Path, what: str) -> Refusal:
    return Refusal(f"{path} is not an OpenAI Evals record: {what}")


def _load(path: Path) -> _Record:
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise Refusal(f"{path} could not be read: {why(e)}") from e
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _not_a_record(path, "it is not UTF-8 text") from None
    if not text.strip():
        raise _not_a_record(path, "it is empty")
    spec: Mapping[str, Any] | None = None
    matches: list[tuple[int, int, Mapping[str, Any]]] = []
    events: Counter[str] = Counter()
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            doc = json.loads(line)
        except ValueError:
            raise _not_a_record(path, f"line {number} is not JSON") from None
        if not isinstance(doc, Mapping):
            raise _not_a_record(path, f"line {number} is not a JSON object")
        if "spec" in doc:
            if not isinstance(doc["spec"], Mapping):
                raise _not_a_record(path, f"line {number}'s spec is not an object")
            spec = spec if spec is not None else doc["spec"]
            continue
        if "final_report" in doc:
            continue
        kind = doc.get("type")
        if not isinstance(kind, str) or not kind:
            raise _not_a_record(path, f"line {number} is neither the spec, the report nor an event")
        events[kind] += 1
        if kind == MATCH:
            matches.append((_event_id(path, number, doc), number, doc))
    if spec is None:
        raise _not_a_record(path, "it has no spec line")
    if not matches:
        raise Refusal(f"{path} holds no match event, so there is no row to read")
    return _Record(path, hashlib.sha256(raw).hexdigest(), spec, matches, events)


def _event_id(path: Path, number: int, doc: Mapping[str, Any]) -> int:
    value = doc.get("event_id")
    if isinstance(value, bool) or not isinstance(value, int):
        raise Refusal(f"{path} line {number} is a match event with no event_id")
    return value


def _case(path: Path, number: int, doc: Mapping[str, Any]) -> str:
    sample = doc.get("sample_id")
    if not isinstance(sample, str) or not sample:
        raise Refusal(f"{path} line {number} is a match event with no sample_id")
    return case_id(sample)


def _row(path: Path, number: int, doc: Mapping[str, Any]) -> Row:
    case = _case(path, number, doc)
    data = doc.get("data")
    correct = data.get("correct") if isinstance(data, Mapping) else None
    if not isinstance(correct, bool):
        raise Refusal(
            f"{path} line {number} is a match event whose data.correct is not true or false"
        )
    assert isinstance(data, Mapping)
    sampled = data.get("sampled")
    score = data.get("score")
    signals: dict[str, Any] = {
        "output_chars": len(sampled) if isinstance(sampled, str) else None,
    }
    number_score = (
        float(score)
        if not isinstance(score, bool) and isinstance(score, (int, float)) and math.isfinite(score)
        else None
    )
    if correct:
        return Row(case, MET, None, number_score, None, {}, result="pass", **signals)
    return Row(
        case,
        MISSED,
        None,
        number_score,
        None,
        {},
        result="fail",
        error_span_kind="grader",
        **signals,
    )


def _started(path: Path, spec: Mapping[str, Any]) -> tuple[str, bool] | None:
    """The spec's ``created_at`` as UTC, and whether it carried a zone; None when it has none."""
    stamp = spec.get("created_at")
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        at = datetime.fromisoformat(stamp)
    except ValueError:
        raise Refusal(f'{path} holds a spec created_at that is not a time: "{stamp}"') from None
    zoned = at.tzinfo is not None and at.utcoffset() is not None
    utc = at.astimezone(UTC) if zoned else at.replace(tzinfo=UTC)
    return utc.replace(tzinfo=None).isoformat() + "Z", zoned


def _file_time(path: Path) -> str:
    try:
        modified = path.stat().st_mtime
    except OSError as e:
        raise Refusal(f"{path} could not be read: {why(e)}") from e
    return datetime.fromtimestamp(modified, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def read(ns: argparse.Namespace) -> Run:
    records = [_load(Path(f)) for f in ns.files]
    rows: list[Row] = []
    events: Counter[str] = Counter()
    for record in records:
        events.update(record.events)
        # a sample's matches are its repeats in event_id order, whatever the order written
        for _, number, doc in sorted(record.matches, key=lambda m: m[0]):
            rows.append(_row(record.path, number, doc))
    starts = [s for r in records if (s := _started(r.path, r.spec)) is not None]
    note = None
    if starts:
        started, started_from = min(at for at, _ in starts), "file"
        note = None if all(zoned for _, zoned in starts) else UNZONED
    else:
        started, started_from = _file_time(records[0].path), "file time"
    spec = records[0].spec
    declared: dict[str, Any] = {}
    for key in ("eval_name", "completion_fns"):
        if key in spec:
            declared[key] = spec[key]
    kinds = [MATCH, *sorted(k for k in events if k != MATCH)]
    return Run(
        name=ns.run,
        tool=TOOL,
        rows=tuple(rows),
        started=started,
        started_from=started_from,
        declared=declared,
        files=tuple({"name": r.path.name, "sha256": r.sha256} for r in records),
        counts={f"{kind} events": events[kind] for kind in kinds},
        started_note=note,
    )


def looks_like(path: Path | str) -> str | None:
    """One line describing ``path`` when it is an OpenAI Evals record, else None; it never
    raises. A ``.jsonl`` file whose first line is a ``spec`` object naming the eval."""
    try:
        found = Path(path)
        if not found.name.lower().endswith(".jsonl") or not found.is_file():
            return None
        with open(found, "rb") as f:
            first = b""
            for line in f:
                if line.strip():
                    first = line
                    break
        doc = json.loads(first.decode("utf-8"))
        spec = doc.get("spec") if isinstance(doc, Mapping) else None
        if not isinstance(spec, Mapping) or not isinstance(spec.get("eval_name"), str):
            return None
        return f"an OpenAI Evals record of {spec['eval_name']}"
    except Exception:
        return None
