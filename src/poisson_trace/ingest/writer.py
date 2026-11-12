"""The module under ``ingest/`` that writes through ``poisson_prove``: a Run becomes one new run.

Every record is built before the store is touched, so a row Prove would not take is refused
with nothing written. The run is created, its rows appended in one part, and it is marked
complete; a run name the store already holds is refused, never appended to.

Each row is classified by the taxonomy before it is written, and its normalised signals go into
the record's ``meta["trace_signals"]`` as the ``poisson.trace-signals/1`` record (spec section
18.4.2 as SA1 reads it on the Prove Trace reads): ``wall_time``, ``t``, ``horizon`` and
``confidence`` take the row's signals where recorded, ``meta["cost_usd"]`` is written where a
cost was recorded, a row without an outcome stays an errored record, and the digest of the rules
that classified the run is recorded in the manifest beside what the import declared (SA5).

The run record (spec section 17.3 item 6, SV1; the artifact format sections 2 to 4): the store
descriptor ``.poisson/store.json`` is written on the first write into a store, or Trace is added
to its ``writers`` once, as a saved verdict writes it (``saved.write_store_descriptor``), after
a descriptor in a newer major, or one that is not a descriptor, has been refused with nothing
written. The run's ``events.jsonl`` is Prove's full log: ``planned``, ``started``, ``progress``
at most once a second and once at the end, then ``finished``; or a closing ``progress`` and
``interrupted`` when Ctrl-C stops the import after its run folder exists, with what Prove holds.
Rows are counted as Prove counts its own: a row with no outcome is ``errored``, the rest
``kept`` (RR1). Each manifest gains ``produced_by`` (Trace's version, the files the run was
made from with the verdicts file last, the tool, the reader and the import's options; RR3, RR4),
added after Prove's last write of the manifest, which does not carry the key. A row with an
outcome and no recorded steps and no spans is stored as one step, so Prove's pages build over
the store (RR5). The rows of a run whose source recorded no horizon share one, the most steps
any of them took, so that the pages also build over a run whose rows took different numbers of
steps.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from poisson_prove.store import EpisodeRecord, RunManifest, Store, config_hash
from poisson_prove.trace import CONTENT_KEYS, OBSERVATION_KEYS, Trace, from_otel

import poisson_trace
from poisson_trace import saved
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
MANIFEST = "manifest.json"
#: The kind of store descriptor Trace writes, and the major it reads (the format's section 3).
STORE_KIND, STORE_MAJOR = saved.STORE_FORMAT.rsplit("/", 1)


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
    # no recorded steps and no spans: one step, so that Prove's pages build over the store (RR5)
    steps = 1.0
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


def _sharing_a_horizon(rows: Sequence[Row], records: list[EpisodeRecord]) -> list[EpisodeRecord]:
    """The records, with one horizon for the rows whose source recorded none: the most steps
    any of them took. Each such row's horizon was its own step count, which Prove's pages
    refuse once the rows of a run take different numbers of steps ("mixed horizons within a
    run"). A horizon the source recorded is kept, a row with no outcome has none, and the
    signals record still says the horizon was not recorded."""
    free = [i for i, row in enumerate(rows) if row.outcome is not None and row.horizon is None]
    if not free:
        return records
    shared = max(records[i].t or 0.0 for i in free)
    out = list(records)
    for i in free:
        out[i] = replace(records[i], horizon=shared)
    return out


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _event(at: str, kind: str, detail: Mapping[str, Any]) -> str:
    return json.dumps({"schema": EVENT_SCHEMA, "at": at, "kind": kind, "detail": dict(detail)})


class _Log:
    """The run's event log, kept as Prove's own ``_Events`` keeps it: one line per event in
    Prove's line format, each stamped when it is emitted; a line emitted before the run's
    folder exists is held and written once the folder is there, ahead of the next; progress
    at most once a second, plus the closing one the writer emits itself."""

    def __init__(self, root: Path, run: str) -> None:
        self.path = root / run / EVENTS
        self.held: list[str] = []
        self.last_progress: float | None = None

    def emit(self, kind: str, detail: Mapping[str, Any]) -> None:
        self.held.append(_event(_now(), kind, detail))
        self.flush()

    def flush(self) -> None:
        if self.held and self.path.parent.is_dir():
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write("".join(f"{line}\n" for line in self.held))
                fh.flush()
            self.held.clear()

    def progress(self, done: int, kept: int, errored: int, total: int) -> None:
        now = time.monotonic()
        if self.last_progress is None or now - self.last_progress >= 1.0:
            self.last_progress = now
            self.emit("progress", {"done": done, "kept": kept, "errored": errored, "total": total})


def _check_descriptor(root: Path) -> None:
    """Refuse a store whose descriptor is in a newer major than Trace writes, or is not a
    descriptor at all (the format's sections 3 and 9), before anything is written."""
    path = saved.descriptor_path(root)
    if not path.is_file():
        return
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise Refusal(f"{path} is not a store descriptor ({why(e)}); nothing was written") from e
    if not isinstance(doc, Mapping):
        raise Refusal(f"{path} is not a store descriptor (not a JSON object); nothing was written")
    found = doc.get("format")
    if isinstance(found, str) and found.rsplit("/", 1)[0] == STORE_KIND:
        try:
            major = int(found.rsplit("/", 1)[1])
        except (IndexError, ValueError):
            return
        if major > int(STORE_MAJOR):
            raise Refusal(
                f"the store at {root} holds {found}, a newer format than this Trace writes "
                f"({saved.STORE_FORMAT}); nothing was written"
            )


def _produced_by(run: Run, verdicts: Mapping[str, Any] | None) -> dict[str, Any]:
    """The manifest's ``produced_by`` (the format's section 4.1; RR3, RR4): the shared
    ``version`` and ``from``, then Trace's own ``tool``, ``reader`` and ``options``."""
    made_from = [{"name": str(f["name"]), "sha256": str(f["sha256"])} for f in run.files]
    if verdicts is not None:
        made_from.append({"name": str(verdicts["name"]), "sha256": str(verdicts["sha256"])})
    return {
        "version": poisson_trace.__version__,
        "from": made_from,
        "tool": saved.TOOL,
        "reader": run.tool,
        "options": dict(run.declared),
    }


def _add_produced_by(path: Path, produced_by: Mapping[str, Any]) -> None:
    """``produced_by`` added to the manifest at ``path`` as Prove last wrote it (Prove's
    ``RunManifest`` does not carry the key), the document otherwise as Prove writes it, through
    a temporary sibling renamed in."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["produced_by"] = dict(produced_by)
    staging = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        staging.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(staging, path)
    finally:
        if staging.exists():
            staging.unlink()


def _held(store: Store, run: str) -> int:
    """The rows Prove holds of a run stopped short, as Prove's own closing progress reads them."""
    try:
        return store.count(run)
    except Exception:
        return 0


def stored(root: Path, name: str) -> Any:
    """Every row of the run ``name`` of the store at ``root``, with its meta and its whole trace,
    as Prove reads them: the frame the Prove reader (``ingest/prove.py``) reads rows from, here
    so that this module stays the one under ``ingest/`` that imports ``poisson_prove``."""
    return Store(root).read(name, meta=True, trace="full")


def runs_in(root: Path) -> list[str]:
    """The runs Prove reads in the folder ``root`` as a store, by their folders' names in
    order; none for a folder Prove does not read as one. A name starting with a dot (the store's
    own ``.poisson`` folder) is never a run (SB1). Here so that the folder resolver
    (``ingest/folder.py``) asks Prove without importing it."""
    try:
        held = Store(root).runs()
    except OSError:
        return []
    return [run_id for run_id in held if not run_id.startswith(".")]


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
    verdicts: Mapping[str, Any] | None = None,
) -> Written:
    """Write ``run`` as one new run of the store at ``root``; ``form`` is how the store's runs
    are named from their manifests, for the check that no other run answers to its name. Each
    row is classified with ``rules`` and ``budgets`` (the config's, or none) before it is
    written, and their digest is recorded in the manifest; so is ``verdicts``, what a
    ``--verdicts`` join did, when one was given (FI20)."""
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
    _check_descriptor(Path(root))
    log = _Log(Path(root), run.name)
    total = len(run.rows)
    log.emit(
        "planned",
        {
            "run_id": run.name,
            "reader": run.tool,
            "files": [str(f["name"]) for f in run.files],
            "rows": total,
        },
    )
    log.emit("started", {"run_id": run.name})
    seen: Counter[str] = Counter()
    records = []
    kept = errored = 0
    try:
        for row in run.rows:
            records.append(_record(run.name, classify(row, rules, budgets), seen[row.case]))
            seen[row.case] += 1
            if row.outcome is None:
                errored += 1
            else:
                kept += 1
            log.progress(kept + errored, kept, errored, total)
        records = _sharing_a_horizon(run.rows, records)
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
    if verdicts is not None:
        recorded["verdicts"] = dict(verdicts)
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
    try:
        store.create_run(manifest)
    except Exception as e:
        raise Refusal(
            f"Prove could not create the run {run.name} in {root} ({why(e)}); nothing was written"
        ) from e
    # the descriptor once the run's folder is there, as Prove writes its own
    try:
        saved.write_store_descriptor(Path(root))
    except (OSError, ValueError) as e:
        shutil.rmtree(Path(root) / run.name, ignore_errors=True)
        raise Refusal(
            f"the store at {root} cannot be written to ({why(e)}); nothing was written"
        ) from e
    ended = False
    try:
        log.flush()
        store.append(run.name, records)
        store.mark_complete(run.name)
        log.emit("progress", {"done": total, "kept": kept, "errored": errored, "total": total})
        ended = True
        log.emit("finished", {"status": "complete", "kept": kept})
        _add_produced_by(Path(root) / run.name / MANIFEST, _produced_by(run, verdicts))
    except KeyboardInterrupt:
        # the run stays, partial (section 9.1 L6); the closing count is what Prove holds
        if not ended:
            held_rows = _held(store, run.name)
            log.emit(
                "progress", {"done": held_rows, "kept": held_rows, "errored": 0, "total": total}
            )
            log.emit("interrupted", {"kept": held_rows, "status": "partial"})
        raise
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


def read_produced_by(root: Path | str, run: str) -> dict[str, Any]:
    """An imported run's ``produced_by``, as its record keeps it (the files it was read from,
    each with its digest, and the reader): empty for a run Prove stored, and for a record that
    cannot be read. Read here, beside the writer, since Prove's own reading of a record leaves
    the key out."""
    try:
        doc = json.loads((Path(root) / run / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    held = doc.get("produced_by") if isinstance(doc, Mapping) else None
    return dict(held) if isinstance(held, Mapping) else {}
