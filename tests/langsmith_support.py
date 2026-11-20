"""Shared helpers for TF24's tests: the LangSmith reader and its raw-saving API pull (it follows
TF21's and TF22's rules as the other readers do). Not collected.

What these tests hold, in one place (each test file's docstring says which invariant it holds):

``poisson_trace.ingest.langsmith``
    A reader module of the shape ``ingest/cli.py`` documents (``add_arguments``, ``read``,
    ``usage``, ``DESCRIPTION``, ``EXAMPLE``, ``looks_like``), with ``SHAPES`` naming the row
    shapes it reads: ``run`` (the v1 runs query and the SDK), ``query`` (the v2 runs query),
    ``cli`` (the ``langsmith`` command's exports) and ``ui`` (the CSV an experiment's page
    downloads). It imports nothing from LangSmith's packages or from ``poisson_prove``.
``poisson_trace.ingest.pulling``
    The pull's two seams, which these tests replace: ``send(method, url, headers, body,
    timeout) -> (status, headers, body)``, the one function in the package that reaches the
    network (standard library only), and ``sleep(seconds)``, the one wait between tries.
``docs/integrations/langsmith.md`` and ``docs/recipes/from-langsmith.md``
    The page and the recipe, of the other readers' shape.

The rules these tests hold:

the command
    ``poisson-trace import langsmith FILE [FILE ...] --store ROOT --run NAME --case-from (example
    | metadata:KEY | input | none) --outcome-from (status | feedback:KEY | metadata:KEY) [--cut X
    (--below | --above)] [--failed VALUE ...] [--select metadata:KEY=VALUE ...]``. Every
    outcome is written ``met``
    or ``missed`` (``status``: missed when the root run ended in error; ``feedback:KEY``: the
    score at the cut; ``metadata:KEY``: missed when its value is one of ``--failed``, or its
    number at the cut), and ``--case-from input`` gives TF22's input key (``input:`` and 12 hex
    characters), which is also what ``--verdicts`` joins by.
the files
    ``.json`` (a list of rows, or an object holding it under ``runs`` or ``items``: the v1 and
    v2 answers as the API returns them), ``.jsonl`` (a row a line) and ``.csv`` (the UI's). Each
    row's shape is told by its keys: ``run_id`` the command's, a ``parent_run_id`` key the v1
    and SDK shape, else ``is_root`` or ``parent_run_ids`` the v2 shape; a row with ``key`` and
    ``feedback_source`` and no ``run_type`` is a feedback record, joined to its run by
    ``run_id``. Pages of one pull are given together. A run given twice is refused.
a row
    One trace is one row; its root (the run with no parent) decides the case and the outcome; a
    trace with no root is left out and counted. Rows are in the order of their roots' starts.
    A root with no score under ``feedback:KEY`` has no outcome (reason ``no score``); it is
    censored when the root ended in error and unscored otherwise.
feedback
    A key's value is the mean of its feedback records' scores (or their one word, for a key
    with no score) where records are given, else the root's ``feedback_stats`` average (or
    its one word). Records are the fuller record: they fill a key the statistics lack. A key all
    of whose sources are ``model`` is a score; any other (``api``, ``app``) is feedback; the
    sources are kept beside the row (``meta["import"]["feedback_sources"]``). The UI's CSV does
    not say who gave a score, so its numbers are all scores and its words feedback.
signals
    Wall time from the root's start and end; time to first token from the earliest
    ``first_token_time`` of the trace's ``llm`` runs; input and output lengths as the characters
    of every value in the root's inputs and outputs (keys and punctuation not counted, null
    nothing); tokens and cost summed over the trace's ``llm`` runs, else the root's own; steps
    the runs with no child; LLM calls the ``llm`` runs; tool calls the ``tool`` runs in start
    order, a call that follows a failed call of the same name under the same parent being the
    next attempt and one retry. The UI's CSV gives the root alone: latency, total tokens, total
    cost, the lengths; no step, call or span.
failure kinds
    Through TF21's one rule set, from what the reader records: the exception's class as the
    error's type, and the kind of the run that failed (``tool``, ``retriever``, ``parser``,
    ``llm``, else ``other``); a first line of the error saying a timeout, a rate limit or a
    context overflow gives that kind as the source's own; a failed row whose root succeeded and
    which holds three calls in a row to one tool is a loop.
the pull
    ``langsmith:NAME`` in the files' place pulls the project or experiment NAME with
    ``LANGSMITH_API_KEY``: ``GET /api/v1/sessions?name=``, ``POST /api/v2/runs/query`` (the
    committed request's body, following ``next_cursor``), ``GET /api/v1/feedback`` (by
    ``offset``); saves ``raw.jsonl`` (runs, then feedback records) and ``pull.json`` under
    ``STORE/.poisson/raw/langsmith/RUN/``; then reads that folder with the file reader.
"""

from __future__ import annotations

import contextlib
import copy
import csv
import io
import json
import os
import shutil
import urllib.parse
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from signals_support import INGEST, Result, records, run_import

LS = INGEST / "langsmith"
API = LS / "api"
CLI = LS / "cli"
UI = LS / "ui"
HOST = "https://api.smith.langchain.com"
KEY_VARIABLE = "LANGSMITH_API_KEY"
ENDPOINT_VARIABLE = "LANGSMITH_ENDPOINT"
#: A key no service ever issued: what the tests put in the environment, and look for afterwards.
PLANTED_KEY = "lsv2_pt_0f1e2d3c4b5a69788796a5b4c3d2e1f0_planted00"
MAIN = "a4bc065"

VERSIONS = ("baseline", "candidate")
EXPERIMENT = {"baseline": "trace-fixture-baseline-bbb64b8e", "candidate": "trace-fixture-candidate-7e3f7200"}
SESSION = {"baseline": "7f82d36e-3c38-43c8-832b-f04be0072bfc", "candidate": "3886d3da-3e3b-4277-a0b2-d913d9109da4"}
CASES = tuple(f"c{n:02d}" for n in range(1, 11))


def example_ids() -> dict[str, str]:
    """The dataset example each case is, as ``api/examples.json`` holds them."""
    held = json.loads((API / "examples.json").read_text(encoding="utf-8"))
    return {str(e["metadata"]["case"]): str(e["id"]) for e in held}


#: Every export of one version, by a short name: the files an import of it is given.
TRACE_EXPORTS = ("v1", "v2", "v2-subtree", "cli-runs", "cli-traces")
EXPORTS = (*TRACE_EXPORTS, "ui")
#: The exports the candidate also has in pages of 25.
PAGED = ("v1-pages", "v2-pages")


def export(version: str, kind: str) -> list[Path]:
    """The files of one export of one version."""
    if kind == "v1":
        return [API / f"{version}.runs-v1.json"]
    if kind == "v2":
        return [API / f"{version}.runs-v2.json"]
    if kind == "v2-subtree":
        return [API / f"{version}.runs-v2.subtree.json"]
    if kind == "cli-runs":
        return [CLI / f"{version}-runs.jsonl"]
    if kind == "cli-traces":
        return sorted((CLI / f"{version}-traces").glob("*.jsonl"))
    if kind == "ui":
        return [UI / f"{EXPERIMENT[version]}.csv"]
    if kind in PAGED:
        assert version == "candidate", "only the candidate was pulled in pages"
        return [API / f"candidate.runs-{kind[:2]}.page-{n}.json" for n in (1, 2, 3)]
    raise KeyError(kind)


def feedback_file(version: str) -> Path:
    return API / f"{version}.feedback.json"


def feedback_pages() -> list[Path]:
    return [API / f"candidate.feedback.page-{n}.json" for n in (1, 2, 3)]


# ---------- what the captures hold, written out (read off the files; see PROVENANCE.md) ----------

#: The evaluator's ``exact`` score of every root, as the feedback records hold it.
EXACT = {
    "baseline": {"c01": 1.0, "c02": 1.0, "c03": 0.0, "c04": 1.0, "c05": 1.0, "c06": 0.0, "c07": 1.0, "c08": 0.0, "c09": 1.0, "c10": 0.0},
    "candidate": {"c01": 1.0, "c02": 1.0, "c03": 1.0, "c04": 1.0, "c05": 1.0, "c06": 0.0, "c07": 1.0, "c08": 1.0, "c09": 0.0, "c10": 1.0},
}
#: The roots whose ``feedback_stats`` lack ``exact`` in the v2 pulls and the command's exports
#: (the statistics had not caught up with the feedback records): the baseline's two.
LATE = {"baseline": ("c08", "c10"), "candidate": ()}
#: The root that ended in error, by version, with the class its error names, the kind of the run
#: that failed and the kind TF21's rules reach.
ERRORED = {
    "baseline": ("c08", "TimeoutError", "tool", "timeout"),
    "candidate": ("c09", "ValueError", "parser", "format_error"),
}
#: The judge's score: every root but the errored one.
JUDGE = {
    "baseline": {"c01": 1.0, "c02": 1.0, "c03": 0.0, "c04": 1.0, "c05": 1.0, "c06": 0.0, "c07": 1.0, "c09": 1.0, "c10": 0.0},
    "candidate": {"c01": 1.0, "c02": 1.0, "c03": 1.0, "c04": 1.0, "c05": 1.0, "c06": 0.0, "c07": 1.0, "c08": 1.0, "c10": 1.0},
}
#: The categorical ``review`` (source ``api``), which has no score.
REVIEW = {
    "baseline": {"c01": "ok", "c02": "ok", "c03": "wrong_answer", "c04": "ok", "c05": "ok", "c06": "wrong_answer", "c07": "ok", "c08": "errored", "c09": "ok", "c10": "abstained"},
    "candidate": {"c01": "ok", "c02": "ok", "c03": "ok", "c04": "ok", "c05": "ok", "c06": "wrong_answer", "c07": "ok", "c08": "ok", "c09": "errored", "c10": "ok"},
}
#: The two thumbs made by hand in the UI (source ``app``): the candidate's alone.
HUMAN_THUMBS = {"baseline": {}, "candidate": {"c01": 1.0, "c06": 0.0}}
#: Tokens (input, output, total) and cost in US dollars of each trace's one ``llm`` run; None
#: where the trace made no model call.
USAGE: dict[str, dict[str, tuple[int, int, int, float] | None]] = {
    "baseline": {
        "c01": (71, 1, 72, 3e-05), "c02": (71, 2, 73, 3.16e-05), "c03": (71, 1, 72, 3e-05), "c04": (71, 1, 72, 3e-05),
        "c05": (71, 2, 73, 3.16e-05), "c06": (71, 2, 73, 3.16e-05), "c07": (71, 1, 72, 3e-05), "c08": None,
        "c09": (71, 1, 72, 3e-05), "c10": (65, 1, 66, 2.76e-05),
    },
    "candidate": {
        "c01": (86, 6, 92, 4.4e-05), "c02": (86, 7, 93, 4.56e-05), "c03": (86, 7, 93, 4.56e-05), "c04": (86, 6, 92, 4.4e-05),
        "c05": (86, 7, 93, 4.56e-05), "c06": (86, 7, 93, 4.56e-05), "c07": (86, 6, 92, 4.4e-05), "c08": (86, 7, 93, 4.56e-05),
        "c09": (86, 3, 89, 3.92e-05), "c10": (86, 7, 93, 4.56e-05),
    },
}
#: The root's latency in seconds, as the UI's CSV prints it.
LATENCY = {
    "baseline": {"c01": 0.39697, "c02": 0.56927, "c03": 0.465431, "c04": 0.782906, "c05": 0.41435, "c06": 0.538556, "c07": 0.979232, "c08": 0.000642, "c09": 0.457097, "c10": 0.696942},
    "candidate": {"c01": 0.444018, "c02": 0.49716, "c03": 0.624191, "c04": 0.606103, "c05": 0.549371, "c06": 0.505516, "c07": 0.705365, "c08": 0.606408, "c09": 0.552476, "c10": 0.564351},
}
#: The item each case asks about (its input is ``{"case": CASE, "item": ITEM}``) and the answer
#: each version gave (its output is ``{"answer": ANSWER}``; None where the run errored and the
#: output is ``{"output": null}``).
ITEM = {"c01": "widget", "c02": "gasket", "c03": "valve", "c04": "flange", "c05": "bearing", "c06": "coupling", "c07": "washer", "c08": "spindle", "c09": "bracket", "c10": "seal"}
ANSWER = {
    "baseline": {"c01": "hold", "c02": "reorder", "c03": "hold", "c04": "hold", "c05": "reorder", "c06": "reorder", "c07": "hold", "c08": None, "c09": "hold", "c10": "unknown"},
    "candidate": {"c01": "hold", "c02": "reorder", "c03": "reorder", "c04": "hold", "c05": "reorder", "c06": "reorder", "c07": "hold", "c08": "reorder", "c09": None, "c10": "reorder"},
}
#: The runs under each root, in start order, as (run type, ended in error): every trace is a
#: retriever, a tool, an llm and a parser, but for these.
USUAL = (("retriever", False), ("tool", False), ("llm", False), ("parser", False))
CHILDREN = {
    ("baseline", "c08"): (("retriever", False), ("tool", True)),
    ("candidate", "c04"): (("retriever", False), ("tool", True), ("tool", False), ("llm", False), ("parser", False)),
    ("candidate", "c09"): (("retriever", False), ("tool", False), ("llm", False), ("parser", True)),
}
RUNS = {"baseline": 48, "candidate": 51}
FEEDBACK = {"baseline": 39, "candidate": 41}
#: Text of the captures that an import must keep nowhere: a prompt's, an input's, an output's, an
#: error's, a comment's.
CONTENT = (
    "You are a stock desk", "Reply with one word only", "Reorder bracket when stock is below",
    "check_stock timed out after 2.0s", "reply is not the JSON asked for", "rate limit exceeded for check_stock",
    "Traceback (most recent call last)", "chatcmpl-",
)


def children(version: str, case: str) -> tuple[tuple[str, bool], ...]:
    return CHILDREN.get((version, case), USUAL)


def passed(version: str, cut: float = 0.5) -> dict[str, bool]:
    """Whether each case's ``exact`` met the cut read below."""
    return {case: score >= cut for case, score in EXACT[version].items()}


# ---------- argv ----------


def ls_argv(files: Sequence[Path | str] | Path | str, root: Path | str, run: str | None, *extra: Any,
            case: str | None = "metadata:ls_example_case", outcome: str | None = "feedback:exact",
            cut: str | None = "0.5", side: str | None = "--below") -> list[str]:
    """``langsmith FILE ... --store ROOT --run NAME`` with the flags that read the fixture: the
    case from the example's own ``case`` (which every trace export carries), the outcome from the
    evaluator's ``exact`` at 0.5. Pass ``cut=None`` with an outcome that reads no score."""
    paths = [files] if isinstance(files, (str, Path)) else list(files)
    argv = ["langsmith", *[str(p) for p in paths], "--store", str(root)]
    if run is not None:
        argv += ["--run", run]
    if case is not None:
        argv += ["--case-from", case]
    if outcome is not None:
        argv += ["--outcome-from", outcome]
    if cut is not None and outcome is not None and outcome != "status":
        argv += ["--cut", cut]
        if side is not None:
            argv.append(side)
    return [*argv, *[str(e) for e in extra]]


def by_status(files: Sequence[Path | str] | Path | str, root: Path | str, run: str, *extra: Any, case: str = "metadata:ls_example_case") -> list[str]:
    return ls_argv(files, root, run, *extra, case=case, outcome="status", cut=None)


def imported(argv: Sequence[Any]) -> dict[str, Any]:
    """The import's ``--json`` summary of a run that was written."""
    result = run_import([*argv, "--json"])
    assert result.code == 0, result.out + result.err
    data: dict[str, Any] = json.loads(result.out)
    assert data["schema"] == "poisson-trace.import/1" and data["verdict"] == "ok", data
    return data


def refused(result: Result) -> str:
    """Exit 1, nothing on stdout, one ``error:`` line with only ``  next:`` lines under it."""
    assert result.code == 1 and result.out == "", result.out + result.err
    lines = result.err.splitlines()
    assert lines and lines[0].startswith("error: "), result.err
    assert all(line.startswith("  next: ") for line in lines[1:]), result.err
    assert "Traceback" not in result.err, result.err
    return lines[0]


def wrong_line(result: Result) -> str:
    """Exit 2, nothing on stdout, an ``error:`` line."""
    assert result.code == 2 and result.out == "", result.out + result.err
    lines = [line for line in result.err.splitlines() if line.startswith("error: ")]
    assert lines, result.err
    return lines[0]


def recs(root: Path, run: str) -> dict[str, dict[str, Any]]:
    """The stored signals record of each case (one try a case, as the fixture has them)."""
    out: dict[str, dict[str, Any]] = {}
    for rec in records(root, run):
        assert rec["case"] not in out, rec["case"]
        out[rec["case"]] = rec
    return out


def metas(root: Path, run: str) -> dict[str, dict[str, Any]]:
    """Each case's whole ``meta`` as the store holds it."""
    from signals_support import frame

    return {m["trace_signals"]["case"]: dict(m) for m in frame(root, run)["meta"]}


def columns(root: Path, run: str) -> dict[str, dict[str, Any]]:
    """Each case's stored columns a verb reads: ``outcome``, ``error``, ``t``, ``wall_time``."""
    from poisson_prove.store import Store

    df = Store(root).read(run, meta=False, trace="envelope")
    out = {}
    for r in df.to_dict("records"):
        out[r["config"]["case"]] = r
    return out


def stored_bytes(root: Path) -> bytes:
    """Every file under ``root``, and every Parquet part decoded cell by cell."""
    import pyarrow.parquet as pq

    out = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        out.append(path.read_bytes())
        if path.suffix == ".parquet":
            out.append(json.dumps(pq.read_table(path).to_pylist(), default=str).encode("utf-8"))
    return b"\n".join(out)


def snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def approx(a: Any, b: Any, tol: float = 1e-9) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


# ---------- the captures, read and edited ----------


def rows_of(path: Path) -> list[dict[str, Any]]:
    """The rows a committed ``.json`` or ``.jsonl`` export holds."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    doc = json.loads(text)
    if isinstance(doc, dict):
        doc = doc.get("runs", doc.get("items"))
    assert isinstance(doc, list), path
    return doc


def run_id(row: Mapping[str, Any]) -> str:
    return str(row["run_id"] if "run_id" in row else row["id"])


def parent_of(row: Mapping[str, Any]) -> str | None:
    if "parent_run_id" in row:
        return row["parent_run_id"]
    chain = row.get("parent_run_ids") or []
    return chain[-1] if chain else None


def case_of_root(row: Mapping[str, Any]) -> str:
    meta = row.get("custom_metadata") or row.get("metadata") or (row.get("extra") or {}).get("metadata") or {}
    return str(meta["ls_example_case"])


def roots(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """Each case's root run."""
    return {case_of_root(r): r for r in rows if parent_of(r) is None}


def seconds(stamp: str) -> float:
    """A LangSmith time as seconds since the epoch, read as UTC when it carries no zone."""
    text = stamp[:-1] if stamp.endswith("Z") else stamp
    whole, _, frac = text.partition(".")
    at = datetime.fromisoformat(whole + "+00:00")
    return at.timestamp() + (int(frac.ljust(6, "0")[:6]) / 1e6 if frac else 0.0)


def ttft(version: str) -> dict[str, float | None]:
    """Seconds from each root's start to its ``llm`` run's first token, read off the v1 pull."""
    rows = rows_of(export(version, "v1")[0])
    out: dict[str, float | None] = {}
    for case, root in roots(rows).items():
        firsts = [r["first_token_time"] for r in rows if r["trace_id"] == root["trace_id"] and r["run_type"] == "llm"]
        out[case] = seconds(firsts[0]) - seconds(root["start_time"]) if firsts else None
    return out


def write_rows(path: Path, source: Path, edit: Callable[[list[dict[str, Any]]], None] | None = None) -> Path:
    """A committed export copied to ``path`` in its own container, with ``edit`` applied to a deep
    copy of its rows first."""
    text = source.read_text(encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix == ".jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        if edit is not None:
            edit(rows)
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return path
    doc = copy.deepcopy(json.loads(text))
    rows = doc if isinstance(doc, list) else doc["runs" if "runs" in doc else "items"]
    if edit is not None:
        edit(rows)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def write_csv(path: Path, source: Path, edit: Callable[[list[dict[str, str]]], None] | None = None,
              header: Callable[[list[str]], list[str]] | None = None) -> Path:
    """The UI's CSV copied to ``path`` with ``edit`` applied to its rows."""
    with open(source, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]
    if edit is not None:
        edit(rows)
    if header is not None:
        fields = header(fields)
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(out.getvalue(), encoding="utf-8")
    return path


def trace_rows(rows: Sequence[dict[str, Any]], case: str) -> list[dict[str, Any]]:
    """The rows of the trace whose root is ``case``, the root first."""
    root = roots(rows)[case]
    rest = [r for r in rows if r["trace_id"] == root["trace_id"] and r is not root]
    return [root, *rest]  # type: ignore[list-item]


def set_error(row: dict[str, Any], text: str) -> None:
    """A run's error text replaced, wherever its shape keeps it."""
    row["error"] = text
    if "error_preview" in row:
        row["error_preview"] = text


def copy_fixture(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dest)
    return dest


# ---------- the fake transport ----------


class Refuse(Exception):
    """A request the captures hold no answer to."""


class Transport:
    """Stands in for ``poisson_trace.ingest.pulling.send``: answers each request with the
    response LangSmith gave to that request, as ``api/requests.json`` records it, and keeps every
    call. A request no capture answers fails the test. ``script`` maps a count of calls (from 1)
    to a canned ``(status, headers, body)`` or an exception to raise in its place; ``host`` is
    where the requests are expected to go."""

    def __init__(self, script: Mapping[int, Any] | None = None, host: str = HOST) -> None:
        self.calls: list[dict[str, Any]] = []
        self.script = dict(script or {})
        self.host = host
        self.table = json.loads((API / "requests.json").read_text(encoding="utf-8"))

    def __call__(self, method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float) -> tuple[int, Mapping[str, str], bytes]:
        assert isinstance(method, str) and isinstance(url, str), (method, url)
        assert body is None or isinstance(body, bytes), type(body)
        assert isinstance(timeout, (int, float)) and 0 < timeout <= 120, timeout
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        canned = self.script.get(len(self.calls))
        if isinstance(canned, BaseException):
            raise canned
        if canned is not None:
            return canned
        return 200, {"Content-Type": "application/json"}, self.answer(method, url, body)

    def answer(self, method: str, url: str, body: bytes | None) -> bytes:
        assert url.startswith(self.host + "/"), f"a request went to {url}, not to {self.host}"
        asked = self.normal(method, HOST + url[len(self.host):], None if body is None else json.loads(body.decode("utf-8")))
        for entry in self.table:
            if entry["status"] == 200 and self.normal(entry["method"], entry["url"], entry["body"]) == asked:
                return (API / entry["file"]).read_bytes()
        raise Refuse(f"the pull asked for something no capture answers: {method} {url} {body!r}")

    @staticmethod
    def normal(method: str, url: str, body: Any) -> tuple[Any, ...]:
        parts = urllib.parse.urlsplit(url)
        query = dict(urllib.parse.parse_qsl(parts.query))
        if parts.path.endswith("/feedback"):
            query.setdefault("offset", "0")
        held = None
        if body is not None:
            held = dict(body)
            # the captures were asked with no lower bound on the runs' start, within the day
            # the runs were made; the pull sends one (TF24-33), and the answers are the same
            held.pop("min_start_time", None)
            if "selects" in held:
                held["selects"] = sorted(held["selects"])
        return method.upper(), parts.path, sorted(query.items()), json.dumps(held, sort_keys=True)

    def paths(self) -> list[str]:
        return [f"{c['method']} {urllib.parse.urlsplit(c['url']).path}" for c in self.calls]


@contextlib.contextmanager
def pulling(transport: Transport | Callable[..., Any] | None = None, key: str | None = PLANTED_KEY,
            endpoint: str | None = None) -> Iterator[tuple[Any, list[float]]]:
    """The pull's seams replaced for the block: ``pulling.send`` by ``transport`` (a new
    ``Transport`` when None), ``pulling.sleep`` by a recorder; the key and the endpoint set (or
    unset, when None) in the environment; and every socket connection refused, so that a pull
    that goes round the seam fails instead of reaching the network. Yields the transport and
    the list of waits asked for."""
    import socket
    from importlib import import_module

    module = import_module("poisson_trace.ingest.pulling")
    sender = Transport() if transport is None else transport
    waits: list[float] = []
    old_send, old_sleep = module.send, module.sleep
    saved = {name: os.environ.get(name) for name in (KEY_VARIABLE, ENDPOINT_VARIABLE, "LANGCHAIN_API_KEY", "LANGCHAIN_ENDPOINT")}

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a test reached for the network")

    old_connect, old_create = socket.socket.connect, socket.create_connection
    try:
        module.send = sender
        module.sleep = waits.append
        socket.socket.connect = no_network  # type: ignore[method-assign]
        socket.create_connection = no_network
        for name in saved:
            os.environ.pop(name, None)
        if key is not None:
            os.environ[KEY_VARIABLE] = key
        if endpoint is not None:
            os.environ[ENDPOINT_VARIABLE] = endpoint
        yield sender, waits
    finally:
        module.send, module.sleep = old_send, old_sleep
        socket.socket.connect = old_connect  # type: ignore[method-assign]
        socket.create_connection = old_create
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def address(version: str) -> str:
    return f"langsmith:{EXPERIMENT[version]}"


def raw_folder(root: Path, run: str) -> Path:
    return root / ".poisson" / "raw" / "langsmith" / run


def raw_lines(root: Path, run: str) -> list[dict[str, Any]]:
    text = (raw_folder(root, run) / "raw.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# ---------- each export imported once, for the tests that only read it ----------

_WORLD: dict[tuple[Any, ...], tuple[Path, dict[str, Any]]] = {}
RUN = "r"


def world(factory: Any, version: str, kind: str, mode: str = "exact", feedback: bool = False) -> tuple[Path, dict[str, Any]]:
    """The export ``kind`` of ``version`` imported once into a store of its own as the run
    ``RUN``, with its ``--json`` summary: by the ``exact`` score at 0.5 (``mode`` ``exact``) or by
    the root's status (``status``), the case the example's own ``case``; ``feedback`` gives the
    version's feedback list beside the run files. Read-only: a test that writes takes its own."""
    key = (version, kind, mode, feedback)
    if key not in _WORLD:
        root = factory.mktemp(f"ls-{version}-{kind}-{mode}-{int(feedback)}") / "st"
        files = [*export(version, kind), *([feedback_file(version)] if feedback else [])]
        argv = by_status(files, root, RUN) if mode == "status" else ls_argv(files, root, RUN)
        _WORLD[key] = (root, imported(argv))
    return _WORLD[key]


def tally(data: Mapping[str, Any]) -> dict[str, int]:
    """The summary's outcomes that have a row."""
    return {word: n for word, n in data["outcomes"].items() if n}


# ---------- what main prints, pinned ----------


#: The readers main has, whose helps stay as main prints them.
EARLIER = ("deepeval", "ragas", "table", "junit", "promptfoo", "inspect", "openai-evals")
ABSENT = ["otel", "files/old.jsonl", "--store", "new-store", "--run", "x"]

#: The invocations whose output this reader changes, pinned from main as text to say exactly how:
#: the import's help gains the reader and its example; the refusal of a tool the install lacks
#: names one reader more.
CHANGED: dict[str, tuple[str, str, list[list[str]]]] = {
    "help: import": ("work", "trace", [["import", "--help"]]),
    "import refusal: a tool not in this install": ("work", "import", [ABSENT, [*ABSENT, "--json"]]),
}


def pin_corpus() -> dict[str, tuple[str, str, list[list[str]]]]:
    """Every invocation whose plain and ``--json`` output this reader leaves as main prints it,
    piped: TF19's corpus whole (TF18's and the failure breakdown's inside it: every verb on
    each kind of store, each option, the refusals, the imports, the names, the saves, ``ui`` and
    ``report``), the outputs TF19 changed as main now prints them (the top help, the bare
    options), ``report``'s help and ``report`` on a page already there,
    and each earlier reader's help under both spellings."""
    from pages_support import SAVES
    from app_support import CHANGED as tf19_changed
    from app_support import pin_corpus as tf19_corpus

    out = dict(tf19_corpus())
    out.update(tf19_changed)
    fix = SAVES["fix-check"][1]
    out["help: report"] = ("work", "trace", [["report", "--help"]])
    out["report: again"] = ("work", "trace", [[*fix, "--out", "ra"], ["report", "ra"], ["report", "ra"], ["report", "ra", "--open"]])
    for tool in EARLIER:
        out[f"help: import {tool}"] = ("work", "trace", [["import", tool, "--help"]])
        out[f"help: alias {tool}"] = ("work", "import", [[tool, "--help"]])
    for label in CHANGED:
        out.pop(label, None)
    return out


def pin_slow() -> frozenset[str]:
    from app_support import slow

    return slow()


def ran_case(tmp: Path, place: str, kind: str, steps: Sequence[Sequence[str]]) -> list[tuple[int, str, str]]:
    """A corpus case run in a workspace of its own: each step's exit code, stdout and stderr, the
    workspace's path written ``<ROOT>``."""
    from look_support import REPO
    from api_support import workspace
    from app_support import normal, run_steps

    work = workspace(tmp) if place == "work" else REPO
    env = {name: os.environ.pop(name) for name in ("BROWSER",) if name in os.environ}
    try:
        return [(r.code, normal(r.out, work), normal(r.err, work)) for r in run_steps(work, place, kind, [list(s) for s in steps])]
    finally:
        os.environ.update(env)


def app_pins(work: Path) -> dict[str, str]:
    """Each screen of the terminal app over TF19's workspace, as its rows of text, 120 by 40, the
    workspace's path written ``<ROOT>`` and every time ``<TIME>``. Each saved verdict's save time
    is first set to one moment, as ``app_support.pages_pins`` sets it, so that the order the app
    lists them in is by kind and id alone (the workspace saves them within a second or two, which
    may straddle a second)."""
    from app_support import NAV_KEYS, TIME, drive, normal

    for path in sorted(work.glob("*/.poisson/artifacts/*/*/artifact.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("tool") == "poisson-trace" or path.parts[-3] in ("where", "compare", "fix-check", "changes"):
            doc["created_at"] = "2026-11-08T00:00:00Z"
            path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    out: dict[str, str] = {}
    for screen, keys in NAV_KEYS.items():
        session = drive(work, keys, size=(120, 40))
        text = "\n".join(row.rstrip() for row in session.last.rows)
        out[screen] = TIME.sub("<TIME>", normal(text, work))
    return out
