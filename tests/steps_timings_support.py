"""Shared helpers for the tests of ``steps`` and ``timings`` (``test_steps_timings.py`` and
``test_steps_timings_promise.py``). Not a test module and not collected.

- The stores read: the suite's workspace (``api_support.workspace``), with the steps and timings
  fixture copied in as ``st``, the ``cs`` store as ``cs`` and the ``tau2`` store as ``tau2``. One
  copy is built in each process for the commands that only read (``read_only``); a test that
  writes (``--out``, ``--save``, an import) takes a copy of its own (``fresh``), with ``cs`` and
  ``tau2`` only when it names them.
- ``stored``: a run read from its episodes files with pyarrow, apart from Trace and from Prove's
  reader: each row's identity, outcome, error and envelope spans. ``placed``, ``label``,
  ``written`` and ``expected_item`` say from those rows alone what the clock places, how it
  labels a step, how an id is written and what ``timings`` lists for a conversation.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from api_support import EV, cli, workspace
from conftest import CS, CS_EVENTS, CS_RECORD, CS_REPLAY, FIXTURES, TAU2, TAU2_A, TAU2_B
from look_support import Ran

FIXTURE = FIXTURES / "steps-timings" / "store"
EVENT = ["--event", "failed"]
RUN_IDS = {"A": "20261123T110000Z-5a0a", "B": "20261123T111000Z-5a0b",
           "C": "20261123T112000Z-5a0c", "D": "20261123T113000Z-5a0d"}
TAU2_PILOT = "20260917T140219Z-2b2d"
CS_EV = [w for e in CS_EVENTS for w in ("--event", e)]
TAU2_EV = ["--event", "unsolved"]

REASONS = ("died", "ended", "timed out", "capped")
EXCLUSIONS = ("no trace", "unreadable trace", "no leaf span", "no outcome, not a timeout")
WHY = (*EXCLUSIONS, "not in the run")
KINDS = ("llm", "tool", "retrieval", "db", "http", "agent", "other")
MARKERS = ("PLANTED-PROMPT", "PLANTED-OUTPUT", "PLANTED-NAME", "PLANTED-ARG")
MOST_STEPS = 20_000

STEP_KEYS = ("step", "reached", "ended_here", "ends", "died_by", "labels")
HEADER_KEYS = ("most_steps", "conversations", "listed", "no_end", "parents_no_end", "no_tree",
               "asked", "not_listed", "items")
ITEM_KEYS = ("config_hash", "seed", "replicate_index", "end", "cause", "steps", "parents")
TIMED_KEYS = ("step", "offset_ns", "duration_ns", "kind", "label", "span_id", "parent_id")
PARENT_KEYS = ("span_id", "parent_id", "kind", "offset_ns", "duration_ns")

#: Each run ``where`` is held on, as (the store's folder in the workspace, the run's word, its
#: run id, its events).
WHERE_RUNS: dict[str, tuple[str, str, str, list[str]]] = {
    "agent before": ("store", "agent before", "20261104T162926Z-b4d5", EV),
    "agent after": ("store", "agent after", "20261104T162928Z-1596", EV),
    "tau2 a": ("tau2", TAU2_A, TAU2_A, TAU2_EV),
    "tau2 b": ("tau2", TAU2_B, TAU2_B, TAU2_EV),
    "cs record": ("cs", CS_RECORD, CS_RECORD, CS_EV),
    "cs replay": ("cs", CS_REPLAY, CS_REPLAY, CS_EV),
    "fixture A": ("st", "A", RUN_IDS["A"], EVENT),
    "fixture B": ("st", "B", RUN_IDS["B"], EVENT),
    "fixture C": ("st", "C", RUN_IDS["C"], EVENT),
    "fixture D": ("st", "D", RUN_IDS["D"], EVENT),
}
#: The runs Prove wrote (run D's three hand-written rows are not), with every span of a trace
#: Prove accepted.
PROVE_WRITTEN = ("agent before", "agent after", "tau2 a", "tau2 b", "cs record", "cs replay",
                 "fixture A", "fixture B", "fixture C")


def where_argv(run: str, *extra: str) -> list[str]:
    folder, word, _run_id, events = WHERE_RUNS[run]
    return ["where", word, "--store", folder, *events, *extra]


#: Each pair ``compare`` is held on: the words, and the two runs' labels in ``WHERE_RUNS``.
COMPARE_RUNS: dict[str, tuple[list[str], str, str]] = {
    "workspace": (["compare", "agent before", "agent after", "--store", "store", *EV, "--max-mde-hr", "1.5"],
                  "agent before", "agent after"),
    "fixture A B": (["compare", "A", "B", "--store", "st", *EVENT, "--max-mde-hr", "2"], "fixture A", "fixture B"),
    "fixture A C": (["compare", "A", "C", "--store", "st", *EVENT, "--max-mde-hr", "2"], "fixture A", "fixture C"),
}


def compare_argv(pair: str, *extra: str) -> list[str]:
    return [*COMPARE_RUNS[pair][0], *extra]


# ---------- the stores, copied ----------


def _furnish(work: Path, stores: tuple[str, ...] = ("cs", "tau2")) -> None:
    shutil.copytree(FIXTURE, work / "st")
    for name in stores:
        shutil.copytree({"cs": CS, "tau2": TAU2}[name], work / name)


_READ_ONLY: Path | None = None


def read_only() -> Path:
    """The workspace with the three stores beside it, built once in each process: for commands
    that write nothing."""
    global _READ_ONLY
    if _READ_ONLY is None:
        root = Path(tempfile.mkdtemp(prefix="steps-timings-"))
        atexit.register(shutil.rmtree, root, ignore_errors=True)
        work = workspace(root)
        _furnish(work)
        _READ_ONLY = work
    return _READ_ONLY


def fresh(tmp: Path, *stores: str) -> Path:
    """A workspace with the fixture beside it, and ``cs`` or ``tau2`` when named, the test's own
    to write into."""
    work = workspace(tmp)
    _furnish(work, stores)
    return work


@cache
def _ran(argv: tuple[str, ...]) -> Ran:
    return cli(read_only(), argv)


def ran(argv: Sequence[str]) -> Ran:
    """A command that writes nothing, run once in each process in the read-only workspace."""
    return _ran(tuple(argv))


def doc(argv: Sequence[str]) -> Any:
    """The ``--json`` document of a command that writes nothing; exit 0 is required."""
    out = ran([*argv, "--json"])
    assert out.code == 0, out.text
    return json.loads(out.out)


def bundled(work: Path, argv: Sequence[str], folder: str = "bundle") -> Any:
    """``result.json`` of the bundle ``--out`` writes for the command, in ``work``."""
    out = cli(work, [*argv, "--out", folder])
    assert out.code == 0, out.text
    return json.loads((work / folder / "result.json").read_text(encoding="utf-8"))


def details(text: str) -> list[str]:
    """The detail lines under the verdict line of a text report, as written, stripped."""
    lines = text.splitlines()
    out = []
    for line in lines[1:]:
        if not line.strip():
            break
        out.append(line.strip())
    return out


# ---------- the stored runs, read apart from Trace ----------


@dataclass(frozen=True)
class Row:
    config_hash: str
    seed: int
    replicate_index: int
    outcome: str | None
    error: str | None
    spans: Any


def run_folder(run: str) -> Path:
    folder, _word, run_id, _events = WHERE_RUNS[run]
    return read_only() / folder / run_id


@cache
def stored(run: str) -> tuple[Row, ...]:
    """The run's rows from its episodes files, in ``(config_hash, replicate_index)`` order, each
    with the spans of its envelope as stored (None for a row with no trace)."""
    rows = []
    for part in sorted((run_folder(run) / "episodes").glob("part-*.parquet")):
        table = pq.read_table(part, columns=["config_hash", "seed", "replicate_index", "outcome",
                                             "error", "trace"]).to_pydict()
        for i in range(len(table["config_hash"])):
            envelope = table["trace"][i]
            spans = None if envelope is None else json.loads(envelope).get("spans")
            rows.append(Row(table["config_hash"][i], int(table["seed"][i]), int(table["replicate_index"][i]),
                            table["outcome"][i], table["error"][i], spans))
    rows.sort(key=lambda r: (r.config_hash, r.replicate_index))
    return tuple(rows)


def cap_of(run: str) -> int | None:
    manifest = json.loads((run_folder(run) / "manifest.json").read_text(encoding="utf-8"))
    capture = (manifest.get("environment") or {}).get("capture")
    value = capture.get("max_spans") if isinstance(capture, Mapping) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _whole(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def leaves(spans: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The spans no span names as its parent, by start and then id."""
    named = {s.get("parent_id") for s in spans}
    return sorted((s for s in spans if s["span_id"] not in named), key=lambda s: (s["start_ns"], s["span_id"]))


def placed(run: str, row: Row) -> tuple[str | None, str | None]:
    """(how the conversation ended, or None) and (why it is off the clock, or None)."""
    events = set(WHERE_RUNS[run][3][1::2])
    spans = row.spans
    if spans is None:
        return None, "no trace"
    if not isinstance(spans, list) or not all(
            isinstance(s, Mapping) and isinstance(s.get("span_id"), str) and _whole(s.get("start_ns")) for s in spans):
        return None, "unreadable trace"
    if not leaves(spans):
        return None, "no leaf span"
    if row.outcome is None and row.error != "timeout":
        return None, "no outcome, not a timeout"
    cap = cap_of(run)
    if row.outcome is None:
        return "timed out", None
    if cap is not None and len(spans) >= cap:
        return "capped", None
    return ("died" if row.outcome in events else "ended"), None


def label(leaf: Mapping[str, Any], spans: Sequence[Mapping[str, Any]], by: str) -> str:
    """The step's label: the leaf's kind, or the nearest step name up its parents (a chain that
    comes back on itself has none)."""
    if by == "kind":
        kind = leaf.get("kind")
        return kind if isinstance(kind, str) else "unknown"
    by_id = {s["span_id"]: s for s in spans}
    node: Mapping[str, Any] | None = leaf
    seen: list[int] = []
    while node is not None and id(node) not in seen:
        seen.append(id(node))
        if isinstance(node.get("step_name"), str):
            return str(node["step_name"])
        parent = node.get("parent_id")
        node = by_id.get(parent) if isinstance(parent, str) else None
    return "unnamed"


def written(span_id: str) -> str:
    """An id as written: itself when printable and at most 80 characters, else ``sha256:`` and
    the first 16 hex of its digest."""
    if len(span_id) <= 80 and span_id.isprintable():
        return span_id
    return "sha256:" + hashlib.sha256(span_id.encode("utf-8")).hexdigest()[:16]


def followable(spans: Sequence[Mapping[str, Any]]) -> bool:
    """Whether the parent links can be followed: no id twice, no cycle."""
    ids = [s["span_id"] for s in spans]
    if len(ids) != len(set(ids)):
        return False
    by_id = {s["span_id"]: s for s in spans}
    for s in spans:
        seen = {s["span_id"]}
        parent = s.get("parent_id")
        while isinstance(parent, str) and parent in by_id:
            if parent in seen:
                return False
            seen.add(parent)
            parent = by_id[parent].get("parent_id")
    return True


def duration(span: Mapping[str, Any]) -> int | None:
    end = span.get("end_ns")
    return end - span["start_ns"] if _whole(end) and end >= span["start_ns"] else None


def expected_item(run: str, row: Row, by: str) -> dict[str, Any]:
    """What ``timings`` lists for a placed conversation, from its stored spans alone."""
    reason, _ = placed(run, row)
    spans = row.spans
    start = min(s["start_ns"] for s in spans)
    tree = followable(spans)
    ids = {s["span_id"] for s in spans}
    found = leaves(spans)
    leaf_ids = {id(s) for s in found}

    def parent_of(s: Mapping[str, Any]) -> str | None:
        parent = s.get("parent_id")
        return written(parent) if tree and isinstance(parent, str) and parent in ids else None

    def kind_of(s: Mapping[str, Any]) -> str:
        return s["kind"] if s.get("kind") in KINDS else "unknown"

    labels = [label(leaf, spans, by) for leaf in found]
    steps = [{"step": i + 1, "offset_ns": leaf["start_ns"] - start, "duration_ns": duration(leaf),
              "kind": kind_of(leaf), "label": labels[i], "span_id": written(leaf["span_id"]),
              "parent_id": parent_of(leaf)} for i, leaf in enumerate(found)]
    parents = None
    if tree:
        others = sorted((s for s in spans if id(s) not in leaf_ids), key=lambda s: (s["start_ns"], s["span_id"]))
        parents = [{"span_id": written(s["span_id"]), "parent_id": parent_of(s), "kind": kind_of(s),
                    "offset_ns": s["start_ns"] - start, "duration_ns": duration(s)} for s in others]
    return {"config_hash": row.config_hash, "seed": row.seed, "replicate_index": row.replicate_index,
            "end": reason, "cause": labels[-1] if reason == "died" else None, "steps": steps, "parents": parents}


def placed_rows(run: str) -> list[Row]:
    return [row for row in stored(run) if placed(run, row)[0] is not None]


def the_row(run: str, config: str, replicate: int) -> Row:
    """The fixture's row of the input ``config`` (``{"task": config}``) and the replicate."""
    from poisson_prove.store import config_hash

    h = config_hash({"task": config})
    return next(r for r in stored(run) if r.config_hash == h and r.replicate_index == replicate)


def pair(row: Row) -> str:
    return f"{row.config_hash}:{row.replicate_index}"


def strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [s for v in value.values() for s in strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in strings(v)]
    return []


def numbers(value: Any) -> list[Any]:
    if isinstance(value, Mapping):
        return [n for v in value.values() for n in numbers(v)]
    if isinstance(value, list):
        return [n for v in value for n in numbers(v)]
    return [value] if isinstance(value, (int, float)) and not isinstance(value, bool) else []
