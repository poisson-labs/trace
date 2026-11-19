"""Shared helpers for the import tests. Not collected.

DeepEval files are built here as plain dictionaries in the shapes DeepEval 4.2.6 writes (camelCase
keys; a key whose value would be ``None`` is absent). The importer runs in-process through
``poisson_trace.ingest.cli.main`` or in a subprocess, and a store is compared before and after
by the digest of every path under it.
"""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import poisson_trace

TESTS = Path(__file__).resolve().parent.parent
REPO = TESTS.parent
FIXTURES = TESTS / "fixtures"
DEEPEVAL_FIXTURES = FIXTURES / "ingest" / "deepeval"
PAIR = (DEEPEVAL_FIXTURES / "humaneval-a.json.gz", DEEPEVAL_FIXTURES / "humaneval-b.json.gz")
HUMANEVAL = FIXTURES / "humaneval"
HE_A, HE_B = "20260905T185407Z-0313", "20260905T195009Z-18ac"
# the package as imported, so that the source scans read the code the tests run against
PACKAGE = Path(poisson_trace.__file__).resolve().parent
INGEST = PACKAGE / "ingest"

IMPORT_SCHEMA = "poisson-trace.import/1"
# the ten words none of Trace's outputs uses
BANNED = (
    "unchanged", "verified", "guaranteed", "pass", "sure", "better", "worse", "fixed",
    "validated", "confirmed",
)


# ---------- running the importer ----------


@dataclass(frozen=True)
class Result:
    code: int
    out: str
    err: str

    @property
    def text(self) -> str:
        return self.out + self.err

    def json(self) -> Any:
        return json.loads(self.out)


def run_import(argv: Sequence[Any]) -> Result:
    """``poisson_trace.ingest.cli.main`` in-process, both streams captured; a ``SystemExit`` is
    read as the exit code it carries, as the console script would."""
    from poisson_trace.ingest.cli import main

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main([str(a) for a in argv])
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return Result(code=int(code), out=out.getvalue(), err=err.getvalue())


def run_python(code: str, args: Sequence[Any] = (), *, env: Mapping[str, str] | None = None,
               cwd: Path | None = None, timeout: int = 600) -> Result:
    proc = subprocess.run(
        [sys.executable, "-c", code, *[str(a) for a in args]],
        capture_output=True, text=True, env=dict(os.environ if env is None else env),
        cwd=cwd, timeout=timeout,
    )
    return Result(code=proc.returncode, out=proc.stdout, err=proc.stderr)


IMPORT_MAIN = "import sys\nfrom poisson_trace.ingest.cli import main\nsys.exit(main(sys.argv[1:]))\n"


def run_trace(argv: Sequence[Any]) -> Result:
    """Trace's own verbs: ``poisson_trace.cli.main`` in-process, both streams captured apart; a
    ``SystemExit`` is read as the exit code it carries, as the console script would. Nothing
    its callers hold needs a process of its own."""
    from poisson_trace.cli import main

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main([str(a) for a in argv])
        except SystemExit as e:
            if e.code is not None and not isinstance(e.code, int):
                print(e.code, file=sys.stderr)
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return Result(code=int(code or 0), out=out.getvalue(), err=err.getvalue())


def deepeval_argv(files: Sequence[Path] | Path, store: Path, run: str, *, metric: str = "Score",
                  cut: Sequence[str] = ("0.5", "--below"), case: str = "name",
                  extra: Sequence[str] = ()) -> list[str]:
    paths = [files] if isinstance(files, Path) else list(files)
    return [
        "deepeval", *[str(p) for p in paths], "--store", str(store), "--run", run,
        "--metric", metric, "--cut", *cut, "--case", case, *extra,
    ]


def refused(result: Result) -> None:
    """Exit 1, nothing on stdout, one line on stderr and the command to run under it on its own
    next: lines. No message words are matched."""
    assert result.code == 1, result.text
    assert result.out.strip() == "", result.out
    lines = [line for line in result.err.splitlines() if line.strip()]
    assert lines and all(line.startswith("  next: ") for line in lines[1:]), result.err


# ---------- the store ----------


def tree(root: Path) -> dict[str, str]:
    """Every path under ``root``: a file by its sha256, a directory as ``dir``."""
    if not root.exists():
        return {}
    out = {}
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        out[rel] = "dir" if path.is_dir() else hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def read_rows(root: Path, run: str) -> list[dict[str, Any]]:
    """The run's rows through Prove, as plain dicts: case, repeat, outcome, error, seed, t,
    horizon and ``meta["import"]``."""
    from poisson_prove.store import Store

    frame = Store(root).read(run, meta=True, trace="none")
    out = []
    for row in frame.to_dict("records"):
        out.append({
            "case": row["config"]["case"], "config": row["config"],
            "config_hash": row["config_hash"], "repeat": int(row["replicate_index"]),
            "outcome": row["outcome"], "error": row["error"], "seed": int(row["seed"]),
            "t": _null(row["t"]), "horizon": _null(row["horizon"]), "import": row["meta"].get("import"),
            "meta": row["meta"],
        })
    return sorted(out, key=lambda r: (r["case"], r["repeat"]))


def _null(value: Any) -> Any:
    """A stored null in a float column reads back as NaN through pandas; here it is None."""
    return None if value is None or (isinstance(value, float) and value != value) else value


def by_case(rows: Iterable[Mapping[str, Any]], key: str = "outcome") -> dict[str, list[Any]]:
    """Case -> the rows' ``key`` values in repeat order."""
    out: dict[str, list[Any]] = {}
    for row in sorted(rows, key=lambda r: (r["case"], r["repeat"])):
        out.setdefault(row["case"], []).append(row[key])
    return out


def all_bytes(root: Path) -> list[tuple[str, bytes]]:
    """Every file under ``root`` as raw bytes, and every Parquet part decoded cell by cell
    (a compressed page can hide a string from a byte search)."""
    import pyarrow.parquet as pq

    out = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        out.append((str(path), path.read_bytes()))
        if path.suffix == ".parquet":
            table = pq.read_table(path)
            cells = json.dumps(table.to_pylist(), default=str).encode("utf-8")
            out.append((f"{path} (decoded)", cells))
    return out


def holds(root: Path, needle: str) -> list[str]:
    raw = needle.encode("utf-8")
    return [name for name, data in all_bytes(root) if raw in data]


# ---------- DeepEval files ----------


def metric(name: str = "Score", score: float | None = None, *, threshold: float = 0.5,
           success: bool | None = None, error: str | None = None,
           reason: str | None = None) -> dict[str, Any]:
    """One ``metricsData`` entry. ``success`` defaults to DeepEval's own decision for a metric
    where higher is better; a metric that raised has no ``score`` key and has ``error``."""
    out: dict[str, Any] = {"name": name, "threshold": threshold}
    if success is None:
        success = score is not None and error is None and score >= threshold
    out["success"] = success
    if score is not None:
        out["score"] = score
    if reason is not None:
        out["reason"] = reason
    out["strictMode"] = False
    out["flaky"] = False
    if error is not None:
        out["error"] = error
    return out


def case(name: str, metrics: Sequence[Mapping[str, Any]], *, order: int = 0,
         input: str | None = None, success: bool | None = None,
         **fields: Any) -> dict[str, Any]:
    """One single-turn test case (``testCases[]``)."""
    out: dict[str, Any] = {
        "name": name,
        "input": f"the question for {name}" if input is None else input,
        "actualOutput": f"the answer for {name}",
    }
    out.update(fields)
    out["flaky"] = False
    out["success"] = all(m.get("success") for m in metrics) if success is None else success
    out["metricsData"] = [dict(m) for m in metrics]
    out["runDuration"] = 0.001
    out["order"] = order
    return out


def conversation(name: str, metrics: Sequence[Mapping[str, Any]], *, order: int = 0,
                 **fields: Any) -> dict[str, Any]:
    """One conversational test case (``conversationalTestCases[]``): no ``input`` key."""
    out: dict[str, Any] = {"name": name, "success": all(m.get("success") for m in metrics)}
    out.update(fields)
    out["metricsData"] = [dict(m) for m in metrics]
    out["runDuration"] = 0.001
    out["order"] = order
    out.setdefault("turns", [{"role": "user", "content": f"hello from {name}", "order": 0}])
    return out


def run_doc(cases: Sequence[Mapping[str, Any]] = (),
             conversations: Sequence[Mapping[str, Any]] = (), **fields: Any) -> dict[str, Any]:
    """A test run as DeepEval's results folder and ``.latest_run_full.json`` hold it."""
    passed = sum(1 for c in [*cases, *conversations] if c.get("success"))
    out: dict[str, Any] = {"testCases": [dict(c) for c in cases]}
    out["conversationalTestCases"] = [dict(c) for c in conversations]
    out["metricsScores"] = []
    out.update(fields)
    out["prompts"] = []
    out["testPassed"] = passed
    out["testFailed"] = len(cases) + len(conversations) - passed
    out["runDuration"] = 0.01
    out["official"] = False
    return out


def save(path: Path, doc: Any, *, gz: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(doc).encode("utf-8")
    path.write_bytes(gzip.compress(raw, mtime=0) if gz else raw)
    return path


def scored(name: str, scores: Sequence[float | None], *, metric_name: str = "Score",
           threshold: float = 0.5, start: int = 0) -> list[dict[str, Any]]:
    """One single-turn test case per score, all named ``name``; ``None`` is a metric that
    raised."""
    out = []
    for i, s in enumerate(scores):
        m = (metric(metric_name, None, threshold=threshold, error="RuntimeError: raised")
             if s is None else metric(metric_name, s, threshold=threshold))
        out.append(case(name, [m], order=start + i))
    return out


# ---------- the summary ----------


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def scalars(value: Any) -> list[Any]:
    """Every scalar anywhere in a JSON value, keys included."""
    if isinstance(value, Mapping):
        out: list[Any] = []
        for k, v in value.items():
            out.append(k)
            out += scalars(v)
        return out
    if isinstance(value, (list, tuple)):
        return [x for v in value for x in scalars(v)]
    return [value]


def in_order(text: str, patterns: Sequence[str]) -> list[int]:
    """Each regular expression found after the one before it; the positions found."""
    at, out = 0, []
    for pattern in patterns:
        match = re.compile(pattern).search(text, at)
        assert match is not None, f"{pattern!r} not found after position {at} in:\n{text}"
        out.append(match.start())
        at = match.end()
    return out
