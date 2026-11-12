"""Shared helpers for the run-record pair's tests: what Poisson Trace's import records about each
run (spec section 17.3 item 6, AD10), created by Taylor's ruling SV1 of 2026-11-04, read with
Poisson's artifact format (``Poisson — Spec Artifact Format``, format 1.1) and with what Prove
0.1.3 writes (the committed ``prove-0.1.3`` store). Not a test module and not collected.

The invariants (the README of ``log/trace-runrec-a`` maps each to its tests; the readings the
spec leaves open are put to Taylor in ``log/trace-runrec-a/rulings.md``, RR1 on):

1. Each import writes the store descriptor (``<store>/.poisson/store.json``,
   ``poisson.store/1``) as Prove 0.1.3 writes its own, and Prove 0.1.3 lists and reads every
   store Trace writes, its dashboard included (RR5).
2. Each import writes the run's full event log (``events.jsonl``, ``poisson.run-event/1``):
   ``planned``, ``started``, ``progress`` at most once a second plus once just before the end,
   then ``finished``, or ``interrupted`` when Ctrl-C leaves the run partial; in Prove's line
   format, with Prove's counts (RR1); nothing in it that section 11.4 or TF21's no-text rules
   keep out.
3. Each manifest records ``produced_by`` naming Trace and the tool the run came from, read as
   plain JSON from ``manifest.json`` as the static pages will read it (RR2, RR3).
4. Imports through folders (TF22), through every reader on main, and through ``init`` record
   the same way.
5. No verb's existing plain or ``--json`` output changes, and the import's ``--json`` keeps
   TF21's SA5 shape.
6. TF21's frozen event-log tests change only where this record requires it, each change in its
   own commit with its guard line.
7. What else the spec and the format require (each in the README): a newer major or broken
   descriptor refused with nothing written; a format-0 store gains ``.poisson/store.json`` and
   nothing else changes; the event log is whole lines; times as Prove writes them.

What Session B builds, in one place:

``poisson_trace.ingest.writer.write`` (its signature as today)
    On the first write into a store (the run's folder made), the store descriptor as
    ``poisson_trace.saved.write_store_descriptor`` already writes it for a saved verdict:
    created when absent, else ``{"tool": "poisson-trace", "version", "first_write"}`` appended
    to ``writers`` once per major.minor version, every other key and byte left alone, through
    a temporary file renamed in. A refused import writes no descriptor. A descriptor in a newer
    major (``poisson.store/2``) or one that is not a JSON object is refused before anything is
    written, the refusal naming the file or both formats.

    The event log, appended line by line as Prove's ``_Events`` does (each line
    ``{"schema": "poisson.run-event/1", "at": <UTC, microseconds, Z>, "kind", "detail"}``):

    - ``planned``  ``{"run_id": <run>, "reader": <tool>, "files": [<each file's name, no
      folder>], "rows": <rows to write>}`` (RR2)
    - ``started``  ``{"run_id": <run>}``
    - ``progress`` ``{"done", "kept", "errored", "total"}`` in rows: ``done`` the rows prepared
      for the write so far, ``errored`` those with no outcome (Prove's errored records),
      ``kept`` the rest, ``total`` the planned rows (RR1); never within a second of the last
      one, except the one just before the end, which always comes: all rows on a finished
      import, what Prove holds on an interrupted one
    - ``finished`` ``{"status": "complete", "kept": <rows with an outcome>}`` (RR1)
    - ``interrupted`` ``{"kept": <rows Prove holds>, "status": "partial"}`` when Ctrl-C stops
      the import after its run folder exists (spec section 9.1 L6), after a closing
      ``progress``; the exit stays 130

    and no other kind, no ``note``, no tool kind.

    ``produced_by`` in the run's ``manifest.json`` (Prove's ``RunManifest`` does not carry the
    key and drops it on every write, so it is added after Prove's last manifest write):
    ``{"version": <Trace's version>, "from": [{"name", "sha256"} for each file the import
    --json lists, then the --verdicts file when given], "tool": "poisson-trace",
    "reader": <tool>, "options": <the import's declared, as --json prints it>}`` (RR3, RR4).

    A row with an outcome and no recorded steps and no spans is stored with ``t`` and
    ``horizon`` 1, so Prove 0.1.3's pages build over a store holding imports (RR5).

``poisson_trace.setup`` (``init``)
    A rolled-back ``init`` removes the descriptor it wrote with the store folder it made, so
    nothing is left behind, as today.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from importlib.metadata import version
from pathlib import Path
from typing import Any

from tf10_support import IN_EVAL, IN_JSON, OE_NEW, OE_OLD, PF_JSON, eval_members, in_argv, oe_argv, pf_argv
from tf21_support import IMPORTS, STARTED, Result, run_import

TOOL = "poisson-trace"
STORE_FORMAT = "poisson.store/1"
EVENT_SCHEMA = "poisson.run-event/1"
DESCRIPTOR_KEYS = ["format", "created_by", "created_at", "writers"]
WRITER_KEYS = ["tool", "version", "first_write"]
EVENT_KEYS = ("schema", "at", "kind", "detail")
PLANNED_KEYS = ("run_id", "reader", "files", "rows")
PROGRESS_KEYS = ("done", "kept", "errored", "total")
PRODUCED_BY_KEYS = {"version", "from", "tool", "reader", "options"}
# Prove's event time (``Event.at``) and its descriptor time (``utc_now``)
AT = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z")
SECOND = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
HEX64 = re.compile(r"[0-9a-f]{64}")
# what no event line holds: TF21's signals record and its keys (SA4), a hash chain or receipt
# (section 11.4), a platform or provenance key
NEVER_KEYS = ("failure_kind", "input_tokens", "output_tokens", "total_tokens", "cost_usd",
              "signals", "scores", "feedback", "trace_signals", "error", "error_type",
              "sha256", "receipt", "signature", "previous", "chain", "platform", "python",
              "import_path", "path")


def trace_version() -> str:
    return version(TOOL)


def major_minor(text: str) -> str:
    return ".".join(text.split(".")[:2])


# ---------- the imports: every reader on main, from committed fixtures ----------


def _tf21(key: str) -> Callable[[Path, str], list[str]]:
    def argv(root: Path, run: str) -> list[str]:
        return [*IMPORTS[key], "--store", str(root), "--run", run, "--started", STARTED]
    return argv


def _unpacked(folder: Path) -> Path:
    """The committed ``.eval`` unpacked as Inspect writes a log folder (TF10, TF22-13)."""
    if not (folder / "header.json").is_file():
        (folder / "samples").mkdir(parents=True, exist_ok=True)
        for name, value in eval_members(IN_EVAL).items():
            if name == "header.json" or name.startswith("samples/"):
                (folder / name).write_text(json.dumps(value) + "\n", encoding="utf-8")
    return folder


def _langsmith(kind: str, root: Path, run: str) -> list[str]:
    """A committed LangSmith capture read by its root runs' status (the reader pair's TF24)."""
    from tf24_support import by_status, export

    return by_status(export("baseline", kind), root, run)


def _braintrust(kind: str, root: Path, run: str) -> list[str]:
    """A committed Braintrust capture read by its root spans' error (the reader pair's TF25)."""
    from tf25_support import by_error, export

    return by_error(export("baseline", kind), root, run)


# key -> (reader, argv builder (store, run) -> argv without --json)
READERS: dict[str, tuple[str, Callable[[Path, str], list[str]]]] = {
    "deepeval-a": ("deepeval", _tf21("deepeval-a")),
    "junit-a": ("junit", _tf21("junit-a")),
    "junit-suite": ("junit", _tf21("junit-suite")),
    "ragas-base": ("ragas", _tf21("ragas-base")),
    "ragas-causal": ("ragas", _tf21("ragas-causal")),
    "table-a": ("table", _tf21("table-a")),
    "promptfoo-old": ("promptfoo", lambda root, run: pf_argv(PF_JSON, root, run)),
    "promptfoo-new": ("promptfoo", lambda root, run: pf_argv(PF_JSON, root, run, prompt="2")),
    "inspect-eval": ("inspect", lambda root, run: in_argv(IN_EVAL, root, run)),
    "inspect-json": ("inspect", lambda root, run: in_argv(IN_JSON, root, run)),
    "openai-evals-old": ("openai-evals", lambda root, run: oe_argv(OE_OLD, root, run)),
    "openai-evals-new": ("openai-evals", lambda root, run: oe_argv(OE_NEW, root, run)),
    "langsmith-v2": ("langsmith", lambda root, run: _langsmith("v2", root, run)),
    "langsmith-traces": ("langsmith", lambda root, run: _langsmith("cli-traces", root, run)),
    "langsmith-csv": ("langsmith", lambda root, run: _langsmith("ui", root, run)),
    "braintrust-fetch": ("braintrust", lambda root, run: _braintrust("fetch", root, run)),
    "braintrust-summary": ("braintrust", lambda root, run: _braintrust("summary", root, run)),
    "braintrust-page": ("braintrust", lambda root, run: _braintrust("ui-csv", root, run)),
}
# the pull-request lane imports these whole; the slow lane imports every one
FAST = ("junit-a", "junit-suite", "ragas-base", "promptfoo-old", "inspect-eval", "inspect-json",
        "openai-evals-old", "langsmith-v2", "langsmith-traces", "langsmith-csv",
        "braintrust-fetch", "braintrust-summary", "braintrust-page")
SLOW = tuple(k for k in READERS if k not in FAST)
# every reader on main has a fast key
assert {READERS[k][0] for k in FAST} | {"deepeval", "table"} == {r for r, _ in READERS.values()}


SUITE_1 = Path(__file__).resolve().parent / "fixtures" / "ingest" / "junit" / "trace-suite-1.xml"


def suite_verdicts(path: Path) -> Path:
    """A verdicts file for ``trace-suite-1.xml`` that fills its one skipped test as failed (as
    TF22-40 joins it): one row, joined by case."""
    from tf22_support import junit_cases

    skipped = next(c for c, e in junit_cases(SUITE_1) if e == "skipped")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"case,outcome\n{skipped},fail\n", encoding="utf-8")
    return path


def unpacked_inspect(tmp: Path) -> Path:
    return _unpacked(tmp / "inspect-log")


def ok(result: Result) -> Result:
    assert result.code == 0, result.out + result.err
    return result


def import_key(key: str, root: Path, run: str | None = None, *extra: Any) -> Result:
    """The committed fixture ``key`` imported into ``root`` as ``run`` (default: the key)."""
    _, argv = READERS[key]
    return ok(run_import([*argv(root, run or key), *[str(e) for e in extra]]))


def import_json(key: str, root: Path, run: str | None = None, *extra: Any) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(import_key(key, root, run, "--json", *extra).out)
    return data


# ---------- reading what an import wrote ----------


def descriptor_file(root: Path) -> Path:
    return root / ".poisson" / "store.json"


def descriptor(root: Path) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(descriptor_file(root).read_text(encoding="utf-8"))
    return doc


def events_text(root: Path, run: str) -> str:
    return (root / run / "events.jsonl").read_text(encoding="utf-8")


def events(root: Path, run: str) -> list[dict[str, Any]]:
    text = events_text(root, run)
    assert text.endswith("\n"), "every line of the log is whole"
    return [json.loads(line) for line in text.splitlines()]


def manifest_json(root: Path, run: str) -> dict[str, Any]:
    """The manifest as the static pages read it: plain JSON, not through Prove's RunManifest
    (which does not carry ``produced_by``)."""
    doc: dict[str, Any] = json.loads((root / run / "manifest.json").read_text(encoding="utf-8"))
    return doc


def produced_by(root: Path, run: str) -> dict[str, Any]:
    doc = manifest_json(root, run)
    assert "produced_by" in doc, sorted(doc)
    got: dict[str, Any] = doc["produced_by"]
    return got


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stored_rows(root: Path, run: str) -> int:
    """The rows Prove holds in a run's parts, read whether or not the run is complete."""
    import pyarrow.parquet as pq

    return sum(pq.read_metadata(p).num_rows for p in sorted((root / run / "episodes").glob("*.parquet")))


def outcome_counts(root: Path, run: str) -> tuple[int, int]:
    """(rows with an outcome, rows without) as Prove stores the run."""
    from poisson_prove.store import Store

    df = Store(root).read(run, meta=False)
    errored = int(df["outcome"].isna().sum())
    return len(df) - errored, errored


def tree(root: Path) -> dict[str, str]:
    """Every file under ``root`` by its relative path, with its bytes' digest."""
    return {p.relative_to(root).as_posix(): sha256_file(p)
            for p in sorted(root.rglob("*")) if p.is_file()}


def copy_store(source: Path, dest: Path) -> Path:
    shutil.copytree(source, dest)
    return dest


# ---------- the event log's grammar ----------


def seconds(at: str) -> float:
    from datetime import datetime

    return datetime.strptime(at, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()


def check_log(log: Sequence[Mapping[str, Any]], run: str, rows: int, *,
              ending: str = "finished") -> dict[str, Any]:
    """The log's grammar for an import of ``rows`` rows into ``run``: ``planned``, ``started``,
    one or more ``progress``, then ``ending``; each line Prove's shape, times in order, progress
    paced at most once a second but for the closing one, which holds the final counts. Returns
    the events by kind (the last of each)."""
    kinds = [e["kind"] for e in log]
    assert kinds[:2] == ["planned", "started"], kinds
    assert kinds[-1] == ending, kinds
    middle = kinds[2:-1]
    assert middle and set(middle) == {"progress"}, kinds
    for e in log:
        assert tuple(e) == EVENT_KEYS, e
        assert e["schema"] == EVENT_SCHEMA and AT.fullmatch(e["at"]), e
        assert isinstance(e["detail"], dict), e
    times = [seconds(e["at"]) for e in log]
    assert times == sorted(times), [e["at"] for e in log]
    planned, started = log[0]["detail"], log[1]["detail"]
    assert tuple(planned) == PLANNED_KEYS, planned
    assert planned["run_id"] == run and planned["rows"] == rows, planned
    assert started == {"run_id": run}, started
    progress = [e for e in log if e["kind"] == "progress"]
    done = -1
    # progress rises as rows are prepared; on Ctrl-C the closing one says what Prove holds, as
    # Prove's own closing progress reads the store, so it alone may fall back (RR1)
    rising = progress[:-1] if ending == "interrupted" else progress
    for e in progress:
        d = e["detail"]
        assert tuple(d) == PROGRESS_KEYS, d
        assert all(isinstance(d[k], int) and not isinstance(d[k], bool) for k in PROGRESS_KEYS), d
        assert d["kept"] + d["errored"] == d["done"] and d["total"] == rows, d
    kept = errored = -1
    for e in rising:
        d = e["detail"]
        assert d["done"] >= done and d["kept"] >= kept and d["errored"] >= errored, [
            p["detail"] for p in progress]
        done, kept, errored = d["done"], d["kept"], d["errored"]
    paced = [seconds(e["at"]) for e in progress[:-1]]
    gaps = [b - a for a, b in zip(paced, paced[1:], strict=False)]
    # a second by the wall clock the times are written in, to the millisecond: a writer pacing
    # by a monotonic clock may see the wall clock slewed by a few parts per million
    assert all(g >= 0.999 for g in gaps), [e["at"] for e in progress]
    return {e["kind"]: e for e in log}


def check_finished(root: Path, run: str, rows: int) -> dict[str, Any]:
    """A complete import's log, its closing counts read against what Prove stores (RR1)."""
    by = check_log(events(root, run), run, rows)
    kept, errored = outcome_counts(root, run)
    assert kept + errored == rows
    closing = [e for e in events(root, run) if e["kind"] == "progress"][-1]["detail"]
    assert closing == {"done": rows, "kept": kept, "errored": errored, "total": rows}, closing
    assert by["finished"]["detail"] == {"status": "complete", "kept": kept}
    for e in events(root, run):
        if e["kind"] == "progress":
            assert e["detail"]["kept"] <= kept and e["detail"]["errored"] <= errored, e
    return by


def all_keys(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, Mapping):
        for k, v in value.items():
            out.append(str(k))
            out.extend(all_keys(v))
    elif isinstance(value, (list, tuple)):
        for v in value:
            out.extend(all_keys(v))
    return out


def all_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [s for k, v in value.items() for s in (str(k), *all_strings(v))]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in all_strings(v)]
    return []


# ---------- Prove reading the store ----------


def prove(root: Path, *argv: str) -> tuple[int, str, str]:
    """``poisson-prove --store ROOT ARGV --plain`` in a fresh interpreter (Prove's own CLI, at the
    version this install pins)."""
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "poisson_prove", "--store", str(root), *argv, "--plain"],
        capture_output=True, stdin=subprocess.DEVNULL, timeout=600,
    )
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")
