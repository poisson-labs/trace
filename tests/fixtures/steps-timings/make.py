"""Make the Prove store the steps and timings tests read, ``store/``: four small runs written
through Prove's own ``Store.create_run`` and ``Store.append``, the calls Trace's importer uses,
with traces built by hand at fixed whole-nanosecond times. No model, no network, no key.

usage: python make.py DEST [--python PYTHON]

PYTHON is an interpreter with poisson-prove 0.4.0 installed (default: the one running this
script); the recipe refuses any other version. The run ids, the salts, the times, the span ids
and the manifests' creation times are all fixed, so a second run writes the same rows.

The runs, all on the inputs ``alpha``, ``beta`` and ``gamma`` (config ``{"task": ...}``):

- ``A`` (salt ``5a17000000000001``, capture cap 6 spans): six conversations, two on each input.
  One dies, one ends, one is capped (six spans, the cap), one is flat (every span a root and a
  leaf), and two more die and end. Spans nest two deep, with a ``step_name`` on some parents;
  in one conversation a leaf starts before its root, so the conversation starts with a step.
- ``B`` (the same salt): six conversations, three on ``alpha``, two on ``beta``, one on
  ``gamma``; it reaches more steps than ``A`` and holds ``alpha`` replicate 2, which ``A`` does
  not. One conversation nests four deep (a root agent, a handed-to agent, two spans with step
  names that start in the same nanosecond, a parent whose id is 81 characters with two leaves
  under it), with two leaves that run in parallel, two that start in the same nanosecond, a
  leaf that starts before its parent, and a leaf id of exactly 80 characters. Others: two roots,
  the earlier starting first; an orphan (a span whose parent is no span of its trace) with a leaf
  under it, beside two leaves whose ids are written as digests (90 characters, and one holding a
  tab); a timeout, whose last leaf, its agent and its root have no end; a row with no span at
  all; and a row with no outcome that did not time out.
- ``C`` (salt ``5a17000000000002``): ``A``'s conversations again under another salt, so the
  same input and replicate get another seed.
- ``D`` (salt ``5a17000000000001``): four conversations written as the others are, then three
  rows' envelopes rewritten in the episodes file with pyarrow, deliberately, as a store written
  by hand would hold them. Prove refuses each of these traces, so ``append`` cannot store them:
  two spans sharing one ``span_id``; a parent cycle of two spans with two leaves under it and no
  step name anywhere; and parents whose ``end_ns`` is below the start or is not a whole number,
  beside a leaf whose ``end_ns`` is below its start. Each row keeps its outcome.

Planted markers sit in span names, inputs, outputs and a tool-call-arguments attribute, on
parents and on leaves: ``PLANTED-NAME``, ``PLANTED-PROMPT``, ``PLANTED-OUTPUT``,
``PLANTED-ARG``. Prove moves the inputs, outputs and the attribute out of the envelope when it
stores the trace; the names stay in it.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PROVE = "0.4.0"  # poisson-prove==0.4.0, from PyPI
SALT = "5a17000000000001"
OTHER_SALT = "5a17000000000002"
INPUTS = ("alpha", "beta", "gamma")
EVENT, OTHER = "failed", "passed"
CAP = 6
BASE = 1_763_895_600_000_000_000  # 2025-11-23T11:00:00Z, in nanoseconds
MS = 1_000_000
LONG_ID = "handoff-" + "x" * 73  # 81 characters
EIGHTY = "leaf-" + "y" * 75  # 80 characters
LONG_LEAF = "leaf-" + "z" * 85  # 90 characters
TAB_LEAF = "leaf\twith a tab"  # not printable
RUNS = {
    "A": ("20261123T110000Z-5a0a", SALT, "2026-11-23T11:00:00Z"),
    "B": ("20261123T111000Z-5a0b", SALT, "2026-11-23T11:10:00Z"),
    "C": ("20261123T112000Z-5a0c", OTHER_SALT, "2026-11-23T11:20:00Z"),
    "D": ("20261123T113000Z-5a0d", SALT, "2026-11-23T11:30:00Z"),
}


def sid(conversation: int, n: int) -> str:
    """A span id as Prove's recorder mints them: 16 hex characters."""
    return f"{conversation:08x}{n:08x}"


def span(span_id: str, parent: str | None, kind: str, start: int, end: int | None, *,
         name: str = "", step: str | None = None, prompt: bool = False, output: bool = False,
         arg: bool = False) -> dict[str, Any]:
    """A span as the arguments of Prove's ``Span``, at ``start`` and ``end`` milliseconds after
    the conversation's base time (``end`` None: never seen to close)."""
    return {"span_id": span_id, "parent_id": parent, "kind": kind, "name": name or kind,
            "start_ms": start, "end_ms": end, "step_name": step,
            "input": "PLANTED-PROMPT: the user's words" if prompt else None,
            "output": "PLANTED-OUTPUT: the model's words" if output else None,
            "attrs": {"gen_ai.tool.call.arguments": "PLANTED-ARG: {\"q\": 1}"} if arg else {}}


def run_a(c: int) -> list[tuple[str, int, str | None, str | None, list[dict[str, Any]]]]:
    """Run A's rows (and C's): (input, replicate, outcome, error, spans)."""
    k = c * 100
    return [
        ("alpha", 0, EVENT, None, [
            span(sid(k + 1, 1), None, "agent", 0, 400, name="PLANTED-NAME root", prompt=True),
            span(sid(k + 1, 2), sid(k + 1, 1), "agent", 10, 390, step="plan", output=True),
            span(sid(k + 1, 3), sid(k + 1, 2), "llm", 20, 200, prompt=True, output=True),
            span(sid(k + 1, 4), sid(k + 1, 2), "tool", 210, 380, arg=True),
        ]),
        ("alpha", 1, OTHER, None, [
            span(sid(k + 2, 1), None, "agent", 0, 500),
            span(sid(k + 2, 2), sid(k + 2, 1), "llm", 10, 100),
            span(sid(k + 2, 3), sid(k + 2, 1), "tool", 110, 200),
            span(sid(k + 2, 4), sid(k + 2, 1), "llm", 210, 490),
            # a leaf that starts before its root, the one parent: the conversation's start
            span(sid(k + 2, 5), sid(k + 2, 1), "tool", -10, 3),
        ]),
        ("beta", 0, OTHER, None, [
            span(sid(k + 3, 1), None, "agent", 0, 900),
            *[span(sid(k + 3, 1 + n), sid(k + 3, 1), "llm" if n % 2 else "tool", 100 * n, 100 * n + 50)
              for n in range(1, CAP)],
        ]),
        ("beta", 1, EVENT, None, [
            span(sid(k + 4, 1), None, "llm", 0, 100),
            span(sid(k + 4, 2), None, "tool", 150, 220),
            span(sid(k + 4, 3), None, "retrieval", 230, 300),
        ]),
        ("gamma", 0, OTHER, None, [
            span(sid(k + 5, 1), None, "agent", 0, 300, step="fetch"),
            span(sid(k + 5, 2), sid(k + 5, 1), "retrieval", 5, 100),
            span(sid(k + 5, 3), sid(k + 5, 1), "llm", 105, 290),
        ]),
        ("gamma", 1, EVENT, None, [
            span(sid(k + 6, 1), None, "agent", 0, 300),
            span(sid(k + 6, 2), sid(k + 6, 1), "llm", 5, 100),
            span(sid(k + 6, 3), sid(k + 6, 1), "tool", 105, 290),
        ]),
    ]


def run_b() -> list[tuple[str, int, str | None, str | None, list[dict[str, Any]]]]:
    k = 200
    root, hand, search, answer = sid(k + 1, 1), sid(k + 1, 2), sid(k + 1, 3), sid(k + 1, 4)
    return [
        # four deep: root agent, the agent it handed to, two spans with step names that start in
        # the same nanosecond, and under "answer" a parent whose id is 81 characters
        ("alpha", 0, EVENT, None, [
            span(root, None, "agent", 0, 1000, name="PLANTED-NAME orchestrator"),
            span(hand, root, "agent", 10, 990, prompt=True),
            span(search, hand, "other", 20, 500, step="search"),
            span(answer, hand, "agent", 20, 980, step="answer", output=True, arg=True),
            span(sid(k + 1, 5), answer, "llm", 15, 400, name="PLANTED-NAME starts before its parent"),
            span(sid(k + 1, 6), search, "retrieval", 30, 120, name="PLANTED-NAME search", prompt=True),
            span(sid(k + 1, 7), search, "tool", 30, 90, arg=True),
            span(EIGHTY, search, "llm", 100, 300, prompt=True, output=True),
            span(LONG_ID, answer, "agent", 600, 900, name="PLANTED-NAME handoff", prompt=True),
            span(sid(k + 1, 9), LONG_ID, "tool", 610, 700, arg=True),
            span(sid(k + 1, 10), LONG_ID, "http", 700, 880),
        ]),
        ("alpha", 1, OTHER, None, [
            span(sid(k + 2, 1), None, "agent", 0, 90),
            span(sid(k + 2, 2), sid(k + 2, 1), "llm", 5, 50),
            span(sid(k + 2, 3), sid(k + 2, 1), "tool", 60, 80),
            span(sid(k + 2, 4), None, "agent", 100, 210),
            span(sid(k + 2, 5), sid(k + 2, 4), "llm", 110, 200),
        ]),
        ("alpha", 2, EVENT, None, [
            span(sid(k + 3, 1), None, "agent", 0, 100),
            span(sid(k + 3, 2), sid(k + 3, 1), "llm", 5, 90),
            span(LONG_LEAF, sid(k + 3, 1), "retrieval", 6, 40),
            span(TAB_LEAF, sid(k + 3, 1), "db", 7, 50),
            span(sid(k + 3, 3), "0000ffff0000ffff", "agent", 120, 300),
            span(sid(k + 3, 4), sid(k + 3, 3), "tool", 130, 290),
        ]),
        ("beta", 0, None, "timeout", [
            span(sid(k + 4, 1), None, "agent", 0, None),
            span(sid(k + 4, 2), sid(k + 4, 1), "agent", 5, None),
            span(sid(k + 4, 3), sid(k + 4, 2), "llm", 10, 200),
            span(sid(k + 4, 4), sid(k + 4, 2), "tool", 210, None),
        ]),
        ("beta", 1, OTHER, None, []),
        ("gamma", 0, None, "crashed", [
            span(sid(k + 6, 1), None, "agent", 0, 100),
            span(sid(k + 6, 2), sid(k + 6, 1), "llm", 5, 90),
        ]),
    ]


def run_d() -> list[tuple[str, int, str | None, str | None, list[dict[str, Any]]]]:
    """Run D as Prove takes it: rows 2 to 4 are rewritten afterwards (``HAND_WRITTEN``)."""
    k = 400
    return [
        ("alpha", 0, EVENT, None, [
            span(sid(k + 1, 1), None, "agent", 0, 300),
            span(sid(k + 1, 2), sid(k + 1, 1), "llm", 5, 100),
            span(sid(k + 1, 3), sid(k + 1, 1), "tool", 105, 290),
        ]),
        ("alpha", 1, OTHER, None, [span(sid(k + 2, 1), None, "llm", 0, 100)]),
        ("beta", 0, EVENT, None, [span(sid(k + 3, 1), None, "llm", 0, 100)]),
        ("beta", 1, OTHER, None, [span(sid(k + 4, 1), None, "llm", 0, 100)]),
    ]


def hand_written() -> dict[tuple[str, int], list[dict[str, Any]]]:
    """The three envelopes of run D that Prove would refuse, by (input, replicate)."""
    k = 400
    dup, p1, p2 = sid(k + 2, 2), sid(k + 3, 1), sid(k + 3, 2)
    return {
        # two spans share one id: neither leaf's parent can be told apart
        ("alpha", 1): [
            span(sid(k + 2, 1), None, "agent", 0, 300),
            span(dup, sid(k + 2, 1), "agent", 10, 120),
            span(dup, sid(k + 2, 1), "agent", 130, 290),
            span(sid(k + 2, 3), dup, "llm", 20, 110),
            span(sid(k + 2, 4), dup, "tool", 140, 280),
        ],
        # a parent cycle with the leaves under it, and no step name on any span
        ("beta", 0): [
            span(p1, p2, "agent", 0, 300),
            span(p2, p1, "agent", 5, 295),
            span(sid(k + 3, 3), p1, "llm", 10, 100),
            span(sid(k + 3, 4), p1, "tool", 110, 290),
        ],
        # a parent ending before it starts, one whose end is not a whole number, and a leaf
        # ending before it starts
        ("beta", 1): [
            span(sid(k + 4, 1), None, "agent", 0, 500),
            span(sid(k + 4, 2), sid(k + 4, 1), "agent", 10, 5),
            span(sid(k + 4, 3), sid(k + 4, 2), "llm", 20, 100),
            span(sid(k + 4, 4), sid(k + 4, 1), "agent", 200, 450),
            span(sid(k + 4, 5), sid(k + 4, 4), "tool", 210, 300),
            span(sid(k + 4, 6), sid(k + 4, 1), "llm", 460, 455),
        ],
    }


def write(dest: Path) -> Path:
    from poisson_prove.executor import derive_seed
    from poisson_prove.store import EpisodeRecord, RunManifest, Store, config_hash
    from poisson_prove.trace import Span, Trace, split

    root = dest / "store"
    store = Store(root)
    rows = {"A": run_a(0), "B": run_b(), "C": run_a(3), "D": run_d()}
    for c, (name, (run_id, salt, created)) in enumerate(RUNS.items()):
        environment: dict[str, Any] = {"made_by": "tests/fixtures/steps-timings/make.py"}
        if name == "A":
            environment["capture"] = {"requested": True, "active": True, "reason": None,
                                      "instrumented": [], "max_spans": CAP}
        store.create_run(RunManifest(
            run_id=run_id, target_id="steps-timings/fixture", t_unit="steps", run_salt=salt,
            axis_types={"task": "categorical"}, backend="local", environment=environment,
            created_at=created, name=name))
        records = []
        for i, (task, replicate, outcome, error, spans) in enumerate(rows[name]):
            base = BASE + (c * 10 + i) * 60_000 * MS
            trace = Trace(spans=tuple(_span(Span, s, base) for s in spans), source="record",
                          truncated="timeout" if error == "timeout" else None)
            config = {"task": task}
            seed = derive_seed(salt, config_hash(config), replicate)
            leaves = len(spans) - len({s["parent_id"] for s in spans} & {s["span_id"] for s in spans})
            meta = {"trace": trace.to_dict()}
            if outcome is None:
                records.append(EpisodeRecord.errored(
                    run_id=run_id, config=config, seed=seed, replicate_index=replicate,
                    error=str(error), wall_time=1.0, meta=meta))
            else:
                records.append(EpisodeRecord(
                    run_id=run_id, config_hash=config_hash(config), config=config, seed=seed,
                    replicate_index=replicate, outcome=outcome, t=float(leaves),
                    horizon=float(CAP if name == "A" else 12), confidence=None, meta=meta,
                    error=None, wall_time=1.0, backend_meta={}))
        store.append(run_id, records)
        store.mark_complete(run_id)
    _rewrite_d(root / RUNS["D"][0], split, Span, Trace, config_hash)
    return root


def _span(cls: Any, s: dict[str, Any], base: int) -> Any:
    return cls(span_id=s["span_id"], parent_id=s["parent_id"], kind=s["kind"], name=s["name"],
               start_ns=base + s["start_ms"] * MS,
               end_ns=None if s["end_ms"] is None else base + s["end_ms"] * MS,
               input=s["input"], output=s["output"], attrs=s["attrs"], step_name=s["step_name"])


def _rewrite_d(run: Path, split: Any, span_cls: Any, trace_cls: Any, config_hash: Any) -> None:
    """Run D's three hand-written envelopes, put in place of what Prove stored for those rows:
    each is the envelope ``split`` would give, built span by span, then edited where Prove would
    refuse it. A store written by hand can hold these; Prove's ``append`` cannot write them."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    parts = sorted((run / "episodes").glob("part-*.parquet"))
    assert len(parts) == 1, parts
    table = pq.read_table(parts[0])
    hashes = table.column("config_hash").to_pylist()
    replicates = table.column("replicate_index").to_pylist()
    traces = table.column("trace").to_pylist()
    base = {json.loads(t)["spans"][0]["span_id"][:8]: json.loads(t)["spans"][0]["start_ns"]
            for t in traces}
    for (task, replicate), spans in hand_written().items():
        at = next(i for i, (h, r) in enumerate(zip(hashes, replicates, strict=True))
                  if h == config_hash({"task": task}) and r == replicate)
        start = base[spans[0]["span_id"][:8]]
        envelope = json.loads(traces[at])
        out = []
        for s in spans:
            # a span Prove would take, as the envelope holds it, then the times as written by hand
            valid = dict(s, end_ms=None)
            one = split(trace_cls(spans=(_span(span_cls, valid, start),), source="record"))[0]
            held = one["spans"][0]
            if s["end_ms"] is not None:
                held["end_ns"] = start + s["end_ms"] * MS
            out.append(held)
        if (task, replicate) == ("beta", 1):
            # the second parent's end is a JSON float, not a whole number
            out[3]["end_ns"] = start + 450.5 * MS
        envelope["spans"] = out
        traces[at] = json.dumps(envelope, separators=(",", ":"))
    index = table.schema.get_field_index("trace")
    table = table.set_column(index, table.schema.field(index), pa.array(traces, type=pa.string()))
    pq.write_table(table, parts[0])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dest", type=Path)
    parser.add_argument("--python", default=sys.executable,
                        help=f"a Python with poisson-prove=={PROVE} installed from PyPI")
    ns = parser.parse_args()
    if ns.python != sys.executable:
        sys.exit(subprocess.call([ns.python, __file__, str(ns.dest)]))
    import poisson_prove

    if poisson_prove.__version__ != PROVE:
        sys.exit(f"{sys.executable} has poisson-prove {poisson_prove.__version__}; this recipe "
                 f"needs {PROVE}: pip install poisson-prove=={PROVE}")
    dest = ns.dest.resolve()
    if (dest / "store").exists():
        shutil.rmtree(dest / "store")
    dest.mkdir(parents=True, exist_ok=True)
    print(f"made {write(dest)}")


if __name__ == "__main__":
    main()
