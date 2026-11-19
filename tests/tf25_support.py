"""Shared helpers for TF25's tests: the Braintrust reader and its raw-saving API pull (it follows
TF21's and TF22's rules as the other readers do, and keeps the LangSmith reader's shape wherever
Braintrust's files allow). Not collected.

What these tests hold, in one place (each test file's docstring says which invariant it holds):

``poisson_trace.ingest.braintrust``
    A reader module of the shape ``ingest/cli.py`` documents (``add_arguments``, ``read``,
    ``usage``, ``DESCRIPTION``, ``EXAMPLE``, ``looks_like``), with ``SHAPES`` naming the row
    shapes it reads: ``span`` (one event a span: the experiment fetch, and BTQL's ``spans`` and
    ``traces`` shapes), ``summary`` (BTQL's ``summary`` shape: one row a case, with its ids) and
    ``ui`` (the JSON and the CSV an experiment's page downloads: one row a case, no id); and
    ``ADDRESS``, ``braintrust:``. It imports nothing from Braintrust's packages or from
    ``poisson_prove``.
``poisson_trace.ingest.pulling``
    The Braintrust pull, through the two seams the LangSmith pull already has and these tests
    replace: ``send(method, url, headers, body, timeout) -> (status, headers, body)``, the one
    function in the package that reaches the network, and ``sleep(seconds)``.
``docs/integrations/braintrust.md`` and ``docs/recipes/from-braintrust.md``
    The page and the recipe, of the other readers' shape.

The rules these tests hold:

the command
    ``poisson-trace import braintrust FILE [FILE ...] --store ROOT --run NAME --case-from (record
    | metadata:KEY | input | none) --outcome-from (error | score:KEY | metadata:KEY) [--cut X
    (--below | --above)] [--failed VALUE ...] [--select metadata:KEY=VALUE ...]``. LangSmith's
    command in Braintrust's words: ``record`` is the dataset record's id (``origin.id``),
    ``error`` reads the root span's error, ``score:KEY`` a score at the cut. Every outcome is
    written ``met`` or ``missed``. ``--case-from input`` gives TF22's input key (``input:`` and
    12 hex characters), which is also what ``--verdicts`` joins by, and is the only way two
    versions pair from the page's downloads, which carry no id.
the files
    ``.json`` (a list of rows, or an object holding it under ``events``, as the fetch answers,
    or ``data``, as BTQL answers), ``.jsonl`` (a row a line) and ``.csv`` (the page's). Each
    row's shape is told by its keys: ``span_id`` and ``root_span_id`` with ``comparison_key`` or
    ``span_type_info`` the summary shape, without them a span; a row with no id that holds
    ``input``, ``scores``, ``metrics`` and ``created`` the page's. Pages of one fetch are given
    together. An event given twice is refused, as is the page's download beside the API's
    answers, and two of the page's downloads together (with no id, two files cannot be told
    from one experiment given twice).
a row
    One trace is one row; its root (the span with no parent) decides the case and the outcome;
    a trace with no root is left out and counted. Rows are in the order of their roots' starts.
    Scores are on child spans of type ``score`` in the span shape (the root's own ``scores`` is
    null) and on the row in the other two; a key's value is the mean of the trace's spans that
    hold it. A root with no score under ``score:KEY`` has no outcome (reason ``no score``); it
    is censored when the root ended in error and unscored otherwise. An errored case has no
    score span at all, so read by a score it is always censored.
feedback
    ``scores`` are the row's scores. ``classifications`` are its feedback, each key's word the
    ids of its items; the page's downloads write the items as a string of JSON, read the same.
    Tags are read only for a failure kind's name; comments are never read.
signals
    Wall time from the root's start and end (``metrics.start``, ``metrics.end``), in every
    shape (the summary's ``metrics.duration`` is the task span's, and is not read). Time to
    first token is Braintrust's own figure, the first model call's ``time_to_first_token``,
    which the summary and the page's files roll up to the row. Lengths are the characters of
    every value in the root's input and output (keys and punctuation not counted, null not
    recorded). Tokens and cost are summed over the trace's ``llm`` spans in the span shape and
    read off the row's rolled-up metrics in the other two. Steps are the spans with no child,
    the grading spans (``score``, ``classifier``) left out; LLM calls the ``llm`` spans; tool
    calls the ``tool`` spans in start order, a call that follows a failed call of the same name
    under the same parent being the next attempt and one retry. The summary and the page's files
    give the count of model calls and nothing else of the structure: no step, tool call, retry
    or span.
failure kinds
    Through TF21's one rule set, from what the reader records: the class the last line of the
    traceback names as the error's type, and the kind of the span that failed (``tool``,
    ``llm``, else ``other``; from the rolled-up ``tool_errors`` and ``llm_errors`` where the
    spans are not in the file); a last line saying a timeout, a rate limit or a context overflow
    gives that kind as the source's own; a failed row that did not error takes the kind a
    classification or a tag names; a failed row whose root succeeded and which holds three calls
    in a row to one tool is a loop.
the pull
    ``braintrust:PROJECT/EXPERIMENT`` in the files' place pulls the experiment with
    ``BRAINTRUST_API_KEY``: ``GET /v1/experiment?project_name=PROJECT``, then ``GET
    /v1/experiment/{id}/fetch?limit=N``, following ``cursor`` until a page comes back empty or
    names none (a short page is not the end, so no event is left behind however old); saves
    ``raw.jsonl`` (the events, one a line) and ``pull.json`` under
    ``STORE/.poisson/raw/braintrust/RUN/``; then reads that folder with the file reader.
"""

from __future__ import annotations

import contextlib
import copy
import csv
import hashlib
import io
import json
import os
import shutil
import urllib.parse
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from tf21_support import INGEST, Result, records, run_import

BT = INGEST / "braintrust"
API = BT / "api"
UI = BT / "ui"
HOST = "https://api.braintrust.dev"
KEY_VARIABLE = "BRAINTRUST_API_KEY"
ENDPOINT_VARIABLE = "BRAINTRUST_API_URL"
#: A key no service ever issued: what the tests put in the environment, and look for afterwards.
PLANTED_KEY = "sk-0f1e2d3c4b5a69788796a5b4c3d2e1f0PlantedKey00"
PROJECT = "trace-fixture"

VERSIONS = ("baseline", "candidate")
#: The paid slice (ten dataset records, one try each) and the lookup fixture (three inline
#: inputs, two tries each), by experiment name, with the id Braintrust gave each.
EXPERIMENT = {"baseline": "slice-baseline", "candidate": "slice-candidate"}
LOOKUP = ("old", "new")
EXPERIMENTS = ("old", "new", "slice-baseline", "slice-candidate")
EXPERIMENT_ID = {
    "old": "c12245bf-c48d-4128-b0c0-b30183901c26", "new": "6fda40a5-37d0-4586-b75f-ba552174780a",
    "slice-baseline": "5eddbe35-a975-4a3c-a34c-c59ad5ab4896", "slice-candidate": "def2b2e5-9c1a-4e05-8861-3e9f3c14d332",
}
CASES = tuple(f"c{n:02d}" for n in range(1, 11))
QUESTIONS = ("q1", "q2", "q3")

#: Every export of one experiment, by a short name: the files an import of it is given.
SPAN_EXPORTS = ("fetch", "btql-spans", "btql-traces")
ROW_EXPORTS = ("summary", "ui-json", "ui-csv")
EXPORTS = (*SPAN_EXPORTS, *ROW_EXPORTS)
#: The shape the reader names for each.
SHAPE = {"fetch": "span", "btql-spans": "span", "btql-traces": "span", "summary": "summary", "ui-json": "ui", "ui-csv": "ui"}
#: The exports the candidate also has in pages of 25 (the last page of each is empty).
PAGED = ("fetch-pages", "btql-pages")


def experiment(name: str) -> str:
    """The experiment's name: a version of the slice, or the name itself."""
    return EXPERIMENT.get(name, name)


def export(name: str, kind: str) -> list[Path]:
    """The files of one export of one experiment (``name`` a version of the slice or an
    experiment's name)."""
    exp = experiment(name)
    if kind == "fetch":
        return [API / f"{exp}.fetch.json"]
    if kind in ("btql-spans", "btql-traces"):
        return [API / f"{exp}.{kind}.json"]
    if kind == "summary":
        return [API / f"{exp}.btql-summary.json"]
    if kind == "ui-json":
        return [UI / f"{exp}.json"]
    if kind == "ui-csv":
        return [UI / f"{exp}.csv"]
    if kind in PAGED:
        assert exp == "slice-candidate", "only the candidate was pulled in pages"
        stem = "fetch" if kind == "fetch-pages" else "btql-spans"
        return [API / f"slice-candidate.{stem}.page-{n}.json" for n in (1, 2, 3, 4, 5)]
    raise KeyError(kind)


# ---------- what the captures hold, written out (read off the files; see PROVENANCE.md) ----------

#: The item each case asks about (its input is ``{"case": CASE, "item": ITEM}``) and the answer
#: each version gave (None where the case errored and the output is null).
ITEM = {"c01": "widget", "c02": "gasket", "c03": "valve", "c04": "flange", "c05": "bearing", "c06": "coupling", "c07": "washer", "c08": "spindle", "c09": "bracket", "c10": "seal"}
ANSWER = {
    "baseline": {"c01": "hold", "c02": "reorder", "c03": "hold", "c04": "hold", "c05": "reorder", "c06": "reorder", "c07": "hold", "c08": None, "c09": "hold", "c10": "unknown"},
    "candidate": {"c01": "hold", "c02": "reorder", "c03": "reorder", "c04": "hold", "c05": "reorder", "c06": "reorder", "c07": "hold", "c08": "reorder", "c09": None, "c10": "reorder"},
}
#: The ``exact`` score of every case; None where the case errored, which has no score span.
EXACT: dict[str, dict[str, float | None]] = {
    "baseline": {"c01": 1.0, "c02": 1.0, "c03": 0.0, "c04": 1.0, "c05": 1.0, "c06": 0.0, "c07": 1.0, "c08": None, "c09": 1.0, "c10": 0.0},
    "candidate": {"c01": 1.0, "c02": 1.0, "c03": 1.0, "c04": 1.0, "c05": 1.0, "c06": 0.0, "c07": 1.0, "c08": 1.0, "c09": None, "c10": 1.0},
}
#: The ``gave_answer`` score: 0 where the answer was ``unknown``.
GAVE_ANSWER: dict[str, dict[str, float | None]] = {
    "baseline": {**dict.fromkeys(CASES, 1.0), "c08": None, "c10": 0.0},
    "candidate": {**dict.fromkeys(CASES, 1.0), "c09": None},
}
#: The ``failure_kind`` classification the script's classifier gave the cases it failed.
CLASSIFIED = {
    "baseline": {"c03": "wrong_answer", "c06": "wrong_answer", "c10": "abstained"},
    "candidate": {"c06": "wrong_answer"},
}
#: The case that ended in error, by version: the class the traceback's last line names, the
#: type of the span that failed, the kind of step the reader records for it, and the failure
#: kind TF21's rules reach from the spans.
ERRORED = {
    "baseline": ("c08", "TimeoutError", "tool", "tool", "timeout"),
    "candidate": ("c09", "ValueError", "function", "other", "crash"),
}
#: Tokens (input, output, total) and cost in US dollars of each trace's one ``llm`` span; None
#: where the trace made no model call.
USAGE: dict[str, dict[str, tuple[int, int, int, float] | None]] = {
    "baseline": {
        "c01": (71, 1, 72, 3.0000000000000004e-05), "c02": (71, 2, 73, 3.16e-05), "c03": (71, 1, 72, 3.0000000000000004e-05),
        "c04": (71, 1, 72, 3.0000000000000004e-05), "c05": (71, 2, 73, 3.16e-05), "c06": (71, 2, 73, 3.16e-05),
        "c07": (71, 1, 72, 3.0000000000000004e-05), "c08": None, "c09": (71, 1, 72, 3.0000000000000004e-05), "c10": (65, 1, 66, 2.76e-05),
    },
    "candidate": {
        "c01": (86, 6, 92, 4.4e-05), "c02": (86, 7, 93, 4.56e-05), "c03": (86, 7, 93, 4.56e-05), "c04": (86, 6, 92, 4.4e-05),
        "c05": (86, 7, 93, 4.56e-05), "c06": (86, 7, 93, 4.56e-05), "c07": (86, 6, 92, 4.4e-05), "c08": (86, 7, 93, 4.56e-05),
        "c09": (86, 3, 89, 3.92e-05), "c10": (86, 7, 93, 4.56e-05),
    },
}
#: The root span's end less its start, in seconds, to the microsecond.
WALL = {
    "baseline": {"c01": 0.516576, "c02": 0.425441, "c03": 0.492587, "c04": 0.407068, "c05": 0.860147, "c06": 1.008695, "c07": 0.45062, "c08": 0.002342, "c09": 1.882213, "c10": 1.955552},
    "candidate": {"c01": 2.005762, "c02": 0.501285, "c03": 0.619492, "c04": 0.558708, "c05": 0.506324, "c06": 0.60909, "c07": 0.750599, "c08": 0.4368, "c09": 1.940643, "c10": 2.225687},
}
#: The model call's ``time_to_first_token``, in seconds, as Braintrust recorded it.
TTFT: dict[str, dict[str, float | None]] = {
    "baseline": {"c01": 0.5126278400421143, "c02": 0.41802215576171875, "c03": 0.48278093338012695, "c04": 0.39922213554382324, "c05": 0.8533802032470703,
                 "c06": 0.9988019466400146, "c07": 0.4438810348510742, "c08": None, "c09": 1.871093988418579, "c10": 1.9484939575195312},
    "candidate": {"c01": 0.48438239097595215, "c02": 0.494718074798584, "c03": 0.6152782440185547, "c04": 0.5515608787536621, "c05": 0.49864816665649414,
                  "c06": 0.6059508323669434, "c07": 0.7478721141815186, "c08": 0.43376898765563965, "c09": 1.9178550243377686, "c10": 2.2083866596221924},
}
#: The spans under each case's task, in start order, as (span type, ended in error): every
#: trace is a function, a tool, an llm and a function, but for these.
USUAL = (("function", False), ("tool", False), ("llm", False), ("function", False))
CHILDREN = {
    ("baseline", "c08"): (("function", False), ("tool", True)),
    ("candidate", "c04"): (("function", False), ("tool", True), ("tool", False), ("llm", False), ("function", False)),
    ("candidate", "c09"): (("function", False), ("tool", False), ("llm", False), ("function", True)),
}
#: The span events of each experiment's fetch.
EVENTS = {"old": 18, "new": 18, "slice-baseline": 85, "slice-candidate": 88}
#: The earliest span's start of each experiment, as the import says it.
EARLIEST = {"old": "2026-11-09T20:24:02.134266Z", "new": "2026-11-09T20:24:02.137586Z",
            "slice-baseline": "2026-11-09T20:24:15.158221Z", "slice-candidate": "2026-11-09T20:24:15.161063Z"}
#: The lookup fixture: each question's ``exact`` score in each experiment (both tries alike).
LOOKUP_EXACT = {"old": {"q1": 1.0, "q2": 0.0, "q3": 0.0}, "new": {"q1": 1.0, "q2": 1.0, "q3": 1.0}}
#: Text of the captures that an import must keep nowhere: a prompt's, an input's, an output's,
#: an error's, and the paths of the machine that ran the experiment.
CONTENT = (
    "You are a stock desk", "Reply with one word only", "Reorder bracket when stock is below",
    "check_stock timed out after 2.0s", "reply is not the JSON asked for", "rate limit exceeded for check_stock",
    "Traceback (most recent call last)", "finish_reason", "slice.eval.py", "/Users/user",
)


def children(version: str, case: str) -> tuple[tuple[str, bool], ...]:
    return CHILDREN.get((version, case), USUAL)


def passed(version: str, cut: float = 0.5) -> dict[str, bool | None]:
    """Whether each case's ``exact`` met the cut read below; None where it has no score."""
    return {case: None if score is None else score >= cut for case, score in EXACT[version].items()}


def input_key(value: Any) -> str:
    """TF22's key of an input: ``input:`` and 12 hex characters of the SHA-256 of a string as
    written, or of anything else as compact JSON with sorted keys."""
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "input:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def case_input(case: str) -> Any:
    return case if case in QUESTIONS else {"case": case, "item": ITEM[case]}


#: Each case's input key, and the case each key is.
KEY = {case: input_key(case_input(case)) for case in (*CASES, *QUESTIONS)}
CASE_OF = {key: case for case, key in KEY.items()}


def named(case: str) -> str:
    """A stored case as the fixture names it: an input's key as the case it is the input of."""
    return CASE_OF.get(case, case)


# ---------- argv ----------


def bt_argv(files: Sequence[Path | str] | Path | str, root: Path | str, run: str | None, *extra: Any,
            case: str | None = "input", outcome: str | None = "score:exact",
            cut: str | None = "0.5", side: str | None = "--below") -> list[str]:
    """``braintrust FILE ... --store ROOT --run NAME`` with the flags that read the fixture from
    every export: the case from the input (the one identity the page's downloads carry), the
    outcome from the ``exact`` score at 0.5. Pass ``cut=None`` with an outcome that reads no
    score."""
    paths = [files] if isinstance(files, (str, Path)) else list(files)
    argv = ["braintrust", *[str(p) for p in paths], "--store", str(root)]
    if run is not None:
        argv += ["--run", run]
    if case is not None:
        argv += ["--case-from", case]
    if outcome is not None:
        argv += ["--outcome-from", outcome]
    if cut is not None and outcome is not None and outcome != "error":
        argv += ["--cut", cut]
        if side is not None:
            argv.append(side)
    return [*argv, *[str(e) for e in extra]]


def by_error(files: Sequence[Path | str] | Path | str, root: Path | str, run: str | None, *extra: Any, case: str = "input") -> list[str]:
    return bt_argv(files, root, run, *extra, case=case, outcome="error", cut=None)


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
    """The stored signals record of each case of a run with one try a case, by the fixture's
    name for the case."""
    out: dict[str, dict[str, Any]] = {}
    for rec in records(root, run):
        case = named(rec["case"])
        assert case not in out, case
        out[case] = rec
    return out


def tries(root: Path, run: str) -> dict[tuple[str, int], dict[str, Any]]:
    """The stored signals record of each try of each case."""
    return {(named(rec["case"]), rec["repeat"]): rec for rec in records(root, run)}


def metas(root: Path, run: str) -> dict[str, dict[str, Any]]:
    """Each case's whole ``meta`` as the store holds it."""
    from tf21_support import frame

    return {named(m["trace_signals"]["case"]): dict(m) for m in frame(root, run)["meta"]}


def columns(root: Path, run: str) -> dict[str, dict[str, Any]]:
    """Each case's stored columns a verb reads: ``outcome``, ``error``, ``t``, ``wall_time``."""
    from poisson_prove.store import Store

    df = Store(root).read(run, meta=False, trace="envelope")
    out = {}
    for r in df.to_dict("records"):
        out[named(r["config"]["case"])] = r
    return out


def outcomes(root: Path, run: str) -> dict[str, Any]:
    return {case: r["outcome"] for case, r in columns(root, run).items()}


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


def tally(data: Mapping[str, Any]) -> dict[str, int]:
    """The summary's outcomes that have a row."""
    return {word: n for word, n in data["outcomes"].items() if n}


# ---------- the captures, read and edited ----------


def _container(doc: Any) -> list[dict[str, Any]]:
    if isinstance(doc, dict):
        doc = doc["events"] if "events" in doc else doc["data"]
    assert isinstance(doc, list)
    return doc


def rows_of(path: Path) -> list[dict[str, Any]]:
    """The rows a committed export holds: a ``.json`` file's list (or the one under ``events``
    or ``data``), a ``.jsonl`` file's lines, or the CSV's rows with each JSON cell read."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    if path.suffix == ".csv":
        out = []
        for row in csv.DictReader(io.StringIO(text, newline="")):
            out.append({k: (json.loads(v) if k in CSV_JSON and v.strip() else (None if k in CSV_JSON else v)) for k, v in row.items()})
        return out
    return _container(json.loads(text))


#: The CSV's columns whose cells are JSON text.
CSV_JSON = ("input", "output", "expected", "tags", "classifications", "scores", "metrics", "metadata", "error")


def is_root(row: Mapping[str, Any]) -> bool:
    return not row.get("span_parents")


def case_of(row: Mapping[str, Any]) -> str:
    """The fixture's name for the case a root (or a row) is: its input's ``case``, or the
    lookup fixture's question."""
    given = row["input"]
    return str(given["case"]) if isinstance(given, dict) else str(given)


def roots(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """Each case's root span (or its one row), for an experiment with one try a case."""
    return {case_of(r): r for r in rows if is_root(r)}


def trace_rows(rows: Sequence[dict[str, Any]], case: str) -> list[dict[str, Any]]:
    """The spans of the trace whose root is ``case``, the root first, the rest in start order."""
    root = roots(rows)[case]
    rest = [r for r in rows if r["root_span_id"] == root["root_span_id"] and r is not root]
    rest.sort(key=lambda r: (r["metrics"] or {}).get("start", 0))
    return [root, *rest]  # type: ignore[list-item]


def span_type(row: Mapping[str, Any]) -> str:
    return str(row["span_attributes"]["type"])


def work_spans(rows: Sequence[dict[str, Any]], case: str) -> list[dict[str, Any]]:
    """The spans under the case's task: the steps the agent took, in start order."""
    return [r for r in trace_rows(rows, case)[1:] if span_type(r) not in ("task", "score", "classifier")]


def write_rows(path: Path, source: Path, edit: Callable[[list[dict[str, Any]]], None] | None = None) -> Path:
    """A committed ``.json`` export copied to ``path`` in its own container, with ``edit``
    applied to a deep copy of its rows first; to a ``.jsonl`` path, the rows one a line."""
    doc = copy.deepcopy(json.loads(source.read_text(encoding="utf-8")))
    rows = _container(doc)
    if edit is not None:
        edit(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".jsonl":
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    else:
        path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def write_csv(path: Path, source: Path, edit: Callable[[list[dict[str, str]]], None] | None = None,
              header: Callable[[list[str]], list[str]] | None = None) -> Path:
    """The page's CSV copied to ``path`` with ``edit`` applied to its rows (cells as text)."""
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


def edited(tmp: Path, name: str, kind: str, edit: Callable[[list[dict[str, Any]]], None], stem: str = "edited") -> Path:
    """One export of one experiment with ``edit`` applied to its rows, in a file of its own
    extension. The CSV's rows are edited as objects and written back as the page writes them."""
    source = export(name, kind)[0]
    if kind != "ui-csv":
        return write_rows(tmp / f"{stem}.json", source, edit)
    rows = rows_of(source)
    edit(rows)
    with open(source, encoding="utf-8", newline="") as f:
        fields = list(csv.DictReader(f).fieldnames or [])
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if row.get(k) is None else json.dumps(row[k], separators=(",", ":")) if k in CSV_JSON else row[k]) for k in fields})
    path = tmp / f"{stem}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(out.getvalue(), encoding="utf-8")
    return path


def traceback_of(line: str) -> str:
    """A traceback as Braintrust saves one, ending in ``line``."""
    return f'Traceback (most recent call last):\n  File "/venv/lib/python3.12/site-packages/x.py", line 1, in f\n    raise\n{line}\n'


def copy_fixture(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dest)
    return dest


# ---------- the fake transport ----------


class Refuse(Exception):
    """A request the captures hold no answer to."""


#: The page Braintrust answers a cursor at an experiment's end with, as committed: no event and
#: no cursor.
END_PAGE = API / "slice-candidate.fetch.page-5.json"


def end_cursors() -> dict[str, str]:
    """The cursor each experiment's whole fetch ends with, by the experiment's id."""
    return {EXPERIMENT_ID[name]: json.loads((API / f"{name}.fetch.json").read_text(encoding="utf-8"))["cursor"] for name in EXPERIMENTS}


class Transport:
    """Stands in for ``poisson_trace.ingest.pulling.send``: answers each request with the
    response Braintrust gave to that request, as ``api/requests.json`` records it, and keeps
    every call. A request no capture answers fails the test, with one exception said plainly:
    every whole fetch ends with a cursor, and the one request the captures hold for a cursor at
    an experiment's end (the candidate's, in pages of 25) was answered with a page of no events
    and no cursor; that committed page answers the end cursor of every experiment, whatever the
    page size. ``script`` maps a count of calls (from 1) to a canned ``(status, headers,
    body)`` or an exception to raise in its place; ``host`` is where the requests are expected
    to go."""

    def __init__(self, script: Mapping[int, Any] | None = None, host: str = HOST) -> None:
        self.calls: list[dict[str, Any]] = []
        self.script = dict(script or {})
        self.host = host
        self.table = json.loads((API / "requests.json").read_text(encoding="utf-8"))
        self.ends = end_cursors()

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
        parts = urllib.parse.urlsplit(url)
        query = dict(urllib.parse.parse_qsl(parts.query))
        pieces = parts.path.strip("/").split("/")
        if method.upper() == "GET" and len(pieces) == 4 and pieces[:2] == ["v1", "experiment"] and pieces[3] == "fetch":
            if query.get("cursor") and query["cursor"] == self.ends.get(pieces[2]) and set(query) == {"limit", "cursor"}:
                return END_PAGE.read_bytes()
        raise Refuse(f"the pull asked for something no capture answers: {method} {url} {body!r}")

    @staticmethod
    def normal(method: str, url: str, body: Any) -> tuple[Any, ...]:
        parts = urllib.parse.urlsplit(url)
        query = sorted(urllib.parse.parse_qsl(parts.query))
        return method.upper(), parts.path, query, json.dumps(body, sort_keys=True)

    def paths(self) -> list[str]:
        """Each call as its method and path, the experiment's id written ``{id}``."""
        out = []
        for c in self.calls:
            path = urllib.parse.urlsplit(c["url"]).path
            for exp_id in EXPERIMENT_ID.values():
                path = path.replace(exp_id, "{id}")
            out.append(f"{c['method']} {path}")
        return out

    def queries(self) -> list[dict[str, str]]:
        return [dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(c["url"]).query)) for c in self.calls]


LISTING = "GET /v1/experiment"
FETCH = "GET /v1/experiment/{id}/fetch"
#: The variables a pull might read, all taken out of the environment while a test pulls.
_VARIABLES = (KEY_VARIABLE, ENDPOINT_VARIABLE, "BRAINTRUST_APP_URL", "BRAINTRUST_ORG_NAME", "LANGSMITH_API_KEY", "LANGSMITH_ENDPOINT",
              "LANGCHAIN_API_KEY", "LANGCHAIN_ENDPOINT")


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
    saved = {name: os.environ.get(name) for name in _VARIABLES}

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


def never() -> Transport:
    """A transport that fails the test if anything is asked of it."""
    class Never(Transport):
        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("a request was made")

    return Never()


def address(name: str) -> str:
    return f"braintrust:{PROJECT}/{experiment(name)}"


def raw_folder(root: Path, run: str) -> Path:
    return root / ".poisson" / "raw" / "braintrust" / run


def raw_lines(root: Path, run: str) -> list[dict[str, Any]]:
    text = (raw_folder(root, run) / "raw.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# ---------- each export imported once, for the tests that only read it ----------

_WORLD: dict[tuple[Any, ...], tuple[Path, dict[str, Any]]] = {}
RUN = "r"


def world(factory: Any, name: str, kind: str, mode: str = "exact") -> tuple[Path, dict[str, Any]]:
    """The export ``kind`` of the experiment ``name`` imported once into a store of its own as
    the run ``RUN``, with its ``--json`` summary: by the ``exact`` score at 0.5 (``mode``
    ``exact``) or by the root's error (``error``), the case the input's key. Read-only: a test
    that writes takes its own."""
    key = (experiment(name), kind, mode)
    if key not in _WORLD:
        root = factory.mktemp(f"bt-{name}-{kind}-{mode}") / "st"
        argv = by_error(export(name, kind), root, RUN) if mode == "error" else bt_argv(export(name, kind), root, RUN)
        _WORLD[key] = (root, imported(argv))
    return _WORLD[key]
