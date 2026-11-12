"""LangSmith runs: the API's answers, the langsmith command's exports and an experiment's CSV.

What is read, each told by its extension and then by its rows' keys (the reader's ``SHAPES``):

- ``run``: the answer of the v1 runs query, and the SDK's ``Run`` (a ``parent_run_id`` key);
- ``query``: the answer of the v2 runs query (``is_root`` or ``parent_run_ids``);
- ``cli``: what ``langsmith runs export`` and ``langsmith traces export`` write (``run_id``);
- ``ui``: the CSV an experiment's page downloads, one row an example with the root run alone.

A ``.json`` file is a list of rows, or the API's answer holding the list under ``runs`` or
``items``; a ``.jsonl`` file is a row a line. A row with ``key`` and ``feedback_source`` and no
``run_type`` is a feedback record, joined to its run by ``run_id``. Pages of one pull are given
together; a run given twice is refused, as is the CSV beside run exports. In the files' place,
``langsmith:NAME`` pulls the project or experiment NAME through ``ingest/pulling.py``, which
saves a raw copy under the store first; the saved copy is then read as any other file.

One trace is one row. Its root, the run with no parent, decides the case (``--case-from``) and
the outcome (``--outcome-from``), written ``met`` or ``missed``; a trace with no root is left
out and counted. Rows come in the order their roots started, so every export of one experiment
gives the same rows in the same order.

Feedback: a key's value is the mean of its records' scores (or their one word) where records
are given, else the average (or the one word) of the root's ``feedback_stats``. The records
are the fuller source and fill a key the statistics lack; a score neither holds is never
guessed, and the row has no outcome. A key all of whose sources are ``model`` is a score, any
other is feedback, and the sources are kept beside the row.

Signals: wall time from the root's start and end; time to first token from the trace's first
model token; lengths as the characters of every value in the root's inputs and outputs; tokens
and cost summed over the ``llm`` runs, else the root's own; steps the runs with no child; tool
calls the ``tool`` runs in start order, a call that follows a failed call of the same name
under the same parent being the next attempt and one retry. The error's type is the
exception's class and the kind of the step that failed its run type; nothing of an error's
words is kept. Each run is one stored span.

No prompt, input, output, error or comment text is kept. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from poisson_trace.ingest.cut import MET, MISSED, Cut
from poisson_trace.ingest.rows import Refusal, Row, Run, ToolCallRecord, case_id
from poisson_trace.ingest.taxonomy import CONTEXT, RATE_LIMIT, TIMEOUT
from poisson_trace.look import option, why

DESCRIPTION = """\
Read LangSmith runs and write them as one new run: the answers of the runs query (v1 or v2)
and of the feedback list, the langsmith command's run and trace exports, or the CSV an
experiment's page downloads. Each trace is one row; its root run decides the case and the
outcome, as --case-from and --outcome-from say. In place of the files, langsmith:NAME pulls
the project or experiment NAME with the key in LANGSMITH_API_KEY, saves a raw copy under the
store and reads that. No input, output or error text is kept.
"""
EXAMPLE = (
    "poisson-trace import langsmith old.json --store trace-store --run old "
    "--case-from example --outcome-from feedback:exact --cut 0.5 --below"
)

TOOL = "langsmith"
#: The row shapes read: the v1 query and the SDK, the v2 query, the command's exports, the CSV.
SHAPES: tuple[str, ...] = ("run", "query", "cli", "ui")
#: What an address to pull from starts with, in the files' place.
ADDRESS = "langsmith:"

#: What a pull stamps on a run it strips, so that the saved copy reads as the answer did.
INPUT_CHARS = "_poisson_input_chars"
OUTPUT_CHARS = "_poisson_output_chars"
INPUT_KEY = "_poisson_input_key"
ERROR_KIND = "_poisson_error_kind"

#: What the detector says of a file of feedback records alone, which is no run of its own.
FEEDBACK_SAID = "LangSmith feedback records"

#: Why a row has no outcome.
NO_SCORE = "no score"
NO_OUTCOME = "no outcome recorded"
PENDING = "pending"

#: The case every row shares under ``--case-from none``.
UNPAIRED = "unpaired"

_PAGE_SIZE = "100"
_TOKENS = ("input_tokens", "output_tokens", "total_tokens", "cached_tokens", "reasoning_tokens")
# a run type as the span's operation, and as the kind of the step that failed
_OPERATION = {
    "llm": "chat",
    "tool": "execute_tool",
    "retriever": "retrieval",
    "embedding": "embeddings",
}
_STEP_KIND = {
    "tool": "tool",
    "retriever": "retriever",
    "parser": "parser",
    "llm": "llm",
    "embedding": "retrieval",
}
_CLASS = re.compile(r"^([A-Za-z_][\w.]*)(?:\(|$)")
_TIME = re.compile(r"^(\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|z|[+-]\d\d:?\d\d)?$")
# the columns of the page's CSV that are the run's own; every other is a feedback key
_CSV_NEEDS = ("id", "inputs", "outputs", "run", "status")
_CSV_OWN = (
    "id",
    "inputs",
    "reference_outputs",
    "session_name",
    "repetition",
    "outputs",
    "run",
    "status",
    "error",
    "latency",
    "tokens",
    "total_cost",
)


# ---------- the command line ----------


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--case-from",
        required=True,
        metavar="WHERE",
        help="what identifies a case across the two versions: example (the dataset example's "
        "id), metadata:KEY, input (a key of the root run's input, never its text) or none "
        "(no default)",
    )
    parser.add_argument(
        "--outcome-from",
        required=True,
        metavar="WHERE",
        help="what says a run failed: status (the root run ended in error), feedback:KEY (a "
        "score, read at --cut) or metadata:KEY (with --failed, or --cut) (no default)",
    )
    parser.add_argument(
        "--cut",
        metavar="X",
        help="the cut a score is read at, with --below or --above (no default)",
    )
    parser.add_argument("--below", action="store_true", help="a score below the cut missed it")
    parser.add_argument("--above", action="store_true", help="a score above the cut missed it")
    parser.add_argument(
        "--failed",
        action="append",
        metavar="VALUE",
        help="a value of the metadata key that means the run failed, repeatable (no default)",
    )
    parser.add_argument(
        "--select",
        action="append",
        metavar="metadata:KEY=VALUE",
        help="keep only the traces whose root run holds this, repeatable (default: every trace)",
    )
    parser.add_argument(
        "--keep-raw-text",
        action="store_true",
        help="with langsmith:NAME, save the raw copy as LangSmith returned it (default: the "
        "inputs and outputs are measured and left out, and an error keeps its class alone)",
    )
    parser.add_argument(
        "--page-size",
        metavar="N",
        default=_PAGE_SIZE,
        help="with langsmith:NAME, how many runs or feedback records one request asks for, "
        "1 to 100 (default: 100)",
    )


def _keyed(word: Any, prefix: str) -> bool:
    """Whether ``word`` is ``PREFIX:KEY`` with a key."""
    return isinstance(word, str) and word.startswith(prefix + ":") and len(word) > len(prefix) + 1


def _key(word: str) -> str:
    return word.split(":", 1)[1]


def reads_a_score(outcome_from: Any, failed: bool) -> bool:
    """Whether the outcome is read at a cut: a feedback score, or a metadata value with no
    failing value named."""
    return _keyed(outcome_from, "feedback") or (_keyed(outcome_from, "metadata") and not failed)


def stand_ins(signals: Mapping[str, Any], said: Mapping[str, Any]) -> dict[str, Any]:
    """The flags ``[signals]`` stands in for, by dest: ``case_field`` for
    ``--case-from`` and ``outcome_field`` for ``--outcome-from``, each written as the flag
    writes it; ``score_field`` a feedback key, as ``KEY`` or ``feedback:KEY``, which an
    ``outcome_field`` beside it wins over; and ``cut`` for ``--cut``, only where a score is
    read, so that a cut that serves one import does not make another, read by its status,
    a wrong command line. ``said`` holds what the call itself gave, by dest."""
    found: dict[str, Any] = {}
    if signals.get("case_field") is not None:
        found["case_from"] = signals["case_field"]
    outcome, score = signals.get("outcome_field"), signals.get("score_field")
    if outcome is not None:
        found["outcome_from"] = outcome
    elif score is not None:
        found["outcome_from"] = score if _keyed(score, "feedback") else f"feedback:{score}"
    read = said.get("outcome_from") or found.get("outcome_from")
    if signals.get("cut") is not None and reads_a_score(read, bool(said.get("failed"))):
        found["cut"] = signals["cut"]
    return found


def _addresses(files: Iterable[Any]) -> list[str]:
    return [str(f) for f in files if str(f).startswith(ADDRESS)]


def usage(ns: argparse.Namespace) -> str | None:
    """Why a command line the parser takes is still wrong, or None. A verb reading a folder
    asks with the flags alone, so nothing here needs the files to be there."""
    files = [str(f) for f in getattr(ns, "files", None) or ()]
    pulled = _addresses(files)
    if pulled and len(files) > 1:
        return "an address to pull from is given alone, in place of the files"
    case = ns.case_from
    if case not in ("example", "input", "none") and not _keyed(case, "metadata"):
        return "--case-from takes example, metadata:KEY, input or none"
    out, cut, failed = ns.outcome_from, ns.cut, list(ns.failed or ())
    sides = [side for side in ("below", "above") if getattr(ns, side, False)]
    if out == "status":
        if cut is not None or sides or failed:
            return "--outcome-from status reads no score and no value: leave out --cut and --failed"
    elif _keyed(out, "feedback"):
        if failed:
            return "--failed goes with --outcome-from metadata:KEY"
        if cut is None:
            return "--outcome-from feedback:KEY reads a score: give --cut X with --below or --above"
    elif _keyed(out, "metadata"):
        if (cut is None) == (not failed):
            return "--outcome-from metadata:KEY needs --failed VALUE, or --cut X with its side"
    else:
        return "--outcome-from takes status, feedback:KEY or metadata:KEY"
    if cut is None and sides:
        return "--below and --above go with --cut"
    if cut is not None:
        if len(sides) != 1:
            return "--cut needs one of --below and --above"
        if _finite(cut) is None:
            return f"--cut takes a number, not {cut}"
    for chosen in ns.select or ():
        left, equals, _ = str(chosen).partition("=")
        if not equals or not _keyed(left, "metadata"):
            return "--select takes metadata:KEY=VALUE"
    size = str(getattr(ns, "page_size", _PAGE_SIZE))
    if _page_size(size) is None:
        return "--page-size takes a whole number from 1 to 100"
    if not pulled and files and (getattr(ns, "keep_raw_text", False) or size != _PAGE_SIZE):
        return "--keep-raw-text and --page-size go with an address to pull from, langsmith:NAME"
    return None


def _page_size(word: str) -> int | None:
    try:
        size = int(word)
    except ValueError:
        return None
    return size if 1 <= size <= 100 else None


def _finite(word: Any) -> float | None:
    """The word as a finite number, or None."""
    try:
        value = float(word)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


# ---------- what is measured of a text, and then left out ----------


def chars(value: Any) -> int | None:
    """The characters of every value in ``value``: text as written, a number or true/false as
    JSON writes it, null nothing; keys and punctuation are not counted. None when there is no
    value at all, which is "not recorded" and not zero."""
    return None if value is None else _characters(value)


def _characters(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value)
    if isinstance(value, Mapping):
        return sum(_characters(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return sum(_characters(v) for v in value)
    return len(json.dumps(value))


def input_key(value: Any) -> str:
    """The key of an input (``input:`` and 12 hex characters), which ``--verdicts`` joins
    by; it holds nothing of the input's text."""
    from poisson_trace.ingest.verdicts import input_case

    return input_case(value)


def error_class(text: Any) -> str | None:
    """The exception's class an error names: the words before its first bracket."""
    if not isinstance(text, str):
        return None
    found = _CLASS.match(text)
    return found.group(1) if found else None


def error_kind(text: Any) -> str | None:
    """The failure kind the first line of an error says, as the source's own: a timeout, a
    rate limit or a context overflow; else None, and the taxonomy's rules decide."""
    if not isinstance(text, str) or not text:
        return None
    line = text.splitlines()[0] if text.splitlines() else ""
    if TIMEOUT.search(line):
        return "timeout"
    if RATE_LIMIT.search(line):
        return "rate_limit"
    if CONTEXT.search(line):
        return "context_overflow"
    return None


# ---------- one run, whichever shape wrote it ----------


def nanoseconds(stamp: Any) -> int | None:
    """A LangSmith time as nanoseconds since the epoch, or None. v1 writes no zone (it is
    UTC) and six digits; v2 and the command write a ``Z`` and drop trailing zeros
    (``02.95192Z``), which ``datetime.fromisoformat`` does not read on Python 3.11, so the
    fraction is read here."""
    if not isinstance(stamp, str):
        return None
    found = _TIME.match(stamp.strip())
    if found is None:
        return None
    whole, fraction, zone = found.groups()
    offset = "+00:00" if zone in (None, "Z", "z") else zone
    try:
        at = datetime.fromisoformat(whole + offset)
    except ValueError:
        return None
    return int(at.timestamp()) * 1_000_000_000 + int((fraction or "")[:9].ljust(9, "0"))


def _count(value: Any) -> int | None:
    """A whole number that is not negative, or None."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _number(value: Any) -> float | None:
    """A finite number as written in JSON, or None; never a number read out of text."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _spelt(value: Any) -> str:
    """A metadata value as ``--select`` and ``--failed`` write it."""
    return value if isinstance(value, str) else json.dumps(value)


@dataclass(frozen=True)
class _Item:
    """One run as its file wrote it, with the shape its keys tell and the file it is in."""

    shape: str
    file: str
    doc: Mapping[str, Any]

    @property
    def id(self) -> str:
        return str(self.doc.get("run_id" if self.shape == "cli" else "id"))

    @property
    def parent(self) -> str | None:
        """The run this one is under. A v2 run names every ancestor, the nearest last."""
        if self.shape == "query":
            chain = self.doc.get("parent_run_ids")
            return str(chain[-1]) if isinstance(chain, list) and chain else None
        parent = self.doc.get("parent_run_id")
        return None if parent is None else str(parent)

    @property
    def trace(self) -> str:
        return str(self.doc.get("trace_id"))

    @property
    def type(self) -> str:
        return str(self.doc.get("run_type") or "").lower()

    @property
    def name(self) -> str:
        return str(self.doc.get("name") or "")

    @property
    def start(self) -> int | None:
        return nanoseconds(self.doc.get("start_time"))

    @property
    def end(self) -> int | None:
        return nanoseconds(self.doc.get("end_time"))

    @property
    def first_token(self) -> int | None:
        return nanoseconds(self.doc.get("first_token_time"))

    @property
    def meta(self) -> Mapping[str, Any]:
        """The run's metadata: the command's ``custom_metadata``, v2's ``metadata``, else
        ``extra.metadata``."""
        if self.shape == "cli":
            return _mapping(self.doc.get("custom_metadata"))
        if self.shape == "query" and isinstance(self.doc.get("metadata"), Mapping):
            return _mapping(self.doc.get("metadata"))
        return _mapping(_mapping(self.doc.get("extra")).get("metadata"))

    @property
    def status(self) -> str:
        """The status in lower case (the API writes ``success`` and ``error``; either case is
        read), empty where the export wrote none, as the command's does."""
        return str(self.doc.get("status") or "").lower()

    @property
    def errored(self) -> bool:
        """Whether the run ended in error: its status says so, or, with no status, it holds
        an error (the command's export with ``--full`` writes an empty status on every run)."""
        return self.status == "error" if self.status else bool(self.doc.get("error"))

    @property
    def ended(self) -> bool:
        return self.status != "pending" and self.end is not None

    @property
    def says_how_it_ended(self) -> bool:
        return bool(self.status) or "error" in self.doc

    def duration(self) -> float | None:
        start, end = self.start, self.end
        return None if start is None or end is None or end < start else (end - start) / 1e9

    def tokens(self) -> dict[str, int | None]:
        """The run's own token counts. The API splits cached and reasoning tokens out (v2
        under ``raw``); the command's export does not, so there they are not recorded."""
        if self.shape == "cli":
            held = _mapping(self.doc.get("token_usage"))
            return {
                "input_tokens": _count(held.get("prompt_tokens")),
                "output_tokens": _count(held.get("completion_tokens")),
                "total_tokens": _count(held.get("total_tokens")),
                "cached_tokens": None,
                "reasoning_tokens": None,
            }
        return {
            "input_tokens": _count(self.doc.get("prompt_tokens")),
            "output_tokens": _count(self.doc.get("completion_tokens")),
            "total_tokens": _count(self.doc.get("total_tokens")),
            "cached_tokens": self._detail("prompt_token_details", "cache_read"),
            "reasoning_tokens": self._detail("completion_token_details", "reasoning"),
        }

    def _detail(self, key: str, name: str) -> int | None:
        held = _mapping(self.doc.get(key))
        if isinstance(held.get("raw"), Mapping):
            held = held["raw"]
        return _count(held.get(name))

    def cost(self, cost_field: str) -> float | None:
        """The run's own cost in US dollars, from the field named (the command's export
        holds it under ``costs``)."""
        held = _mapping(self.doc.get("costs")) if self.shape == "cli" else self.doc
        return _number(held.get(cost_field))


# ---------- the files ----------


@dataclass
class _File:
    """One file read: its digest, and the runs, feedback records and CSV rows it holds."""

    path: Path
    sha256: str
    runs: list[_Item] = field(default_factory=list)
    feedback: list[Mapping[str, Any]] = field(default_factory=list)
    table: list[tuple[int, Mapping[str, str]]] = field(default_factory=list)


def _not_an_export(path: Path, what: str) -> Refusal:
    return Refusal(f"{path} is not a LangSmith export: {what}")


def _load(path: Path) -> _File:
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise Refusal(f"{path} could not be read: {why(e)}") from e
    name = path.name.lower()
    if not name.endswith((".json", ".jsonl", ".csv")):
        raise Refusal(
            f"{path} is not a file the LangSmith reader reads: it reads .json, .jsonl and .csv"
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise _not_an_export(path, "it is not UTF-8 text") from None
    if not text.strip():
        raise _not_an_export(path, "it is empty")
    held = _File(path, hashlib.sha256(raw).hexdigest())
    if name.endswith(".csv"):
        _load_csv(held, text)
    elif name.endswith(".jsonl"):
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
            except ValueError:
                raise _not_an_export(path, f"line {number} is not JSON") from None
            _take(held, doc, f"line {number}")
    else:
        try:
            doc = json.loads(text)
        except ValueError:
            raise _not_an_export(path, "it is not JSON") from None
        for number, item in enumerate(_listed(path, doc), start=1):
            _take(held, item, f"item {number}")
    return held


def _listed(path: Path, doc: Any) -> list[Any]:
    """The rows of a ``.json`` file: the list it is, or the one the API's answer holds."""
    if isinstance(doc, Mapping):
        for key in ("runs", "items"):
            if isinstance(doc.get(key), list):
                return list(doc[key])
        raise _not_an_export(path, "it holds no list of runs (under runs or items)")
    if not isinstance(doc, list):
        raise _not_an_export(path, "it is not a list of runs or of feedback records")
    return doc


def _shape(doc: Mapping[str, Any]) -> str | None:
    """The shape a row's keys tell: ``feedback``, one of the run shapes, or None."""
    if "run_type" not in doc:
        return "feedback" if "key" in doc and "feedback_source" in doc else None
    if "run_id" in doc:
        return "cli"
    if "parent_run_id" in doc:
        return "run"
    if "is_root" in doc or "parent_run_ids" in doc:
        return "query"
    return None


def _take(held: _File, doc: Any, where: str) -> None:
    if not isinstance(doc, Mapping):
        raise _not_an_export(held.path, f"{where} is not a JSON object")
    shape = _shape(doc)
    if shape is None:
        raise _not_an_export(held.path, f"{where} is neither a run nor a feedback record")
    if shape == "feedback":
        held.feedback.append(doc)
    else:
        held.runs.append(_Item(shape, held.path.name, doc))


def _load_csv(held: _File, text: str) -> None:
    reader = csv.DictReader(io.StringIO(text, newline=""))
    columns = list(reader.fieldnames or ())
    lacking = [column for column in _CSV_NEEDS if column not in columns]
    if lacking:
        raise Refusal(
            f"{held.path} is not the CSV a LangSmith experiment's page downloads: it has no "
            f"{lacking[0]} column"
        )
    try:
        for row in reader:
            held.table.append((reader.line_num, {k: v for k, v in row.items() if k is not None}))
    except csv.Error as e:
        raise Refusal(f"{held.path} line {reader.line_num} cannot be read as CSV: {why(e)}") from e


def _cell(path: Path, line: int, row: Mapping[str, str], column: str) -> Any:
    """A cell the page writes as JSON, or None when it is empty."""
    text = row.get(column) or ""
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except ValueError:
        raise Refusal(
            f"{path} line {line}: the {column} cell is not the JSON the page writes"
        ) from None


# ---------- feedback ----------

#: A key's value (its score, or its one word) and the types of its sources.
_Held = dict[str, tuple[Any, list[str]]]


def _from_statistics(root: _Item) -> _Held:
    """Each key of the root's ``feedback_stats``. The average is read only where a score was
    counted: the command's export writes ``avg: 0`` with ``n: 0`` for a key that has words
    and no score."""
    out: _Held = {}
    for key, held in _mapping(root.doc.get("feedback_stats")).items():
        if not isinstance(held, Mapping):
            continue
        counted = held.get("n")
        value: Any = _number(held.get("avg")) if counted is None or counted else None
        if value is None:
            words = held.get("values")
            if isinstance(words, Mapping) and len(words) == 1:
                value = next(iter(words))
        if value is None:
            continue
        types = set()
        for source in held.get("sources") or ():
            try:
                doc = json.loads(source) if isinstance(source, str) else source
            except ValueError:
                continue
            if isinstance(doc, Mapping) and isinstance(doc.get("type"), str):
                types.add(doc["type"])
        out[str(key)] = (value, sorted(types))
    return out


def _from_records(records: Sequence[Mapping[str, Any]]) -> _Held:
    """Each key of the run's feedback records: the mean of its scores, or its one word."""
    by_key: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        by_key.setdefault(str(record.get("key")), []).append(record)
    out: _Held = {}
    for key, held in by_key.items():
        scores = [s for s in (_number(r.get("score")) for r in held) if s is not None]
        value: Any = None
        if scores:
            value = math.fsum(scores) / len(scores)
        else:
            words = {r.get("value") for r in held if isinstance(r.get("value"), str)}
            if len(words) == 1:
                value = next(iter(words))
        if value is None:
            continue
        types = {
            str(source["type"])
            for source in (_mapping(r.get("feedback_source")) for r in held)
            if isinstance(source.get("type"), str)
        }
        out[key] = (value, sorted(types))
    return out


def _scores_and_feedback(found: _Held) -> tuple[dict[str, float], dict[str, Any]]:
    """A key all of whose sources are ``model`` is a score; any other is feedback."""
    scores: dict[str, float] = {}
    feedback: dict[str, Any] = {}
    for key, (value, types) in found.items():
        if isinstance(value, float) and types and all(t == "model" for t in types):
            scores[key] = value
        else:
            feedback[key] = value
    return scores, feedback


# ---------- the case and the outcome ----------


@dataclass(frozen=True)
class _How:
    """How the rows are read: what the flags said."""

    case_from: str
    outcome_from: str
    cut: Cut | None
    failed: tuple[str, ...]
    selects: tuple[tuple[str, str], ...]
    cost_field: str

    def selected(self, meta: Mapping[str, Any]) -> bool:
        for key, value in self.selects:
            held = meta.get(key)
            if held is None or _spelt(held) != value:
                return False
        return True

    def case(self, example: Any, meta: Mapping[str, Any], keyed: str | None) -> str | None:
        """The row's case, or None when its root holds none."""
        if self.case_from == "none":
            return UNPAIRED
        if self.case_from == "example":
            return case_id(str(example)) if example else None
        if self.case_from == "input":
            return keyed
        value = meta.get(_key(self.case_from))
        return None if value is None or value == "" else case_id(_spelt(value))

    def outcome(
        self, errored: bool, ended: bool, values: Mapping[str, Any], meta: Mapping[str, Any]
    ) -> tuple[str | None, str | None, float | None]:
        """The outcome word, the reason a row has none, and the score read."""
        if self.outcome_from == "status":
            if not ended:
                return None, PENDING, None
            return (MISSED if errored else MET), None, None
        key = _key(self.outcome_from)
        if _keyed(self.outcome_from, "feedback"):
            score = _number(values.get(key))
            if score is None or self.cut is None:
                return None, NO_SCORE, None
            return self.cut.outcome(score), None, score
        value = meta.get(key)
        if value is None or value == "":
            return None, NO_OUTCOME, None
        if self.cut is None:
            return (MISSED if _spelt(value) in self.failed else MET), None, None
        score = _number(value)
        if score is None:
            score = _finite(value) if isinstance(value, str) else None
        if score is None:
            raise Refusal(
                f"--cut reads {self.outcome_from} as a score, and a root run holds "
                f"{json.dumps(value)} there, which is not a number"
            )
        return self.cut.outcome(score), None, score


def _how(ns: argparse.Namespace) -> _How:
    cut = None
    if ns.cut is not None:
        cut = Cut(float(ns.cut), "below" if ns.below else "above")
    selects = []
    for chosen in ns.select or ():
        left, _, value = str(chosen).partition("=")
        selects.append((_key(left), value))
    signals = getattr(ns, "signals", None) or {}
    return _How(
        case_from=str(ns.case_from),
        outcome_from=str(ns.outcome_from),
        cut=cut,
        failed=tuple(str(v) for v in ns.failed or ()),
        selects=tuple(selects),
        cost_field=str(signals.get("cost_field") or "total_cost"),
    )


def _result(outcome: str | None, errored: bool) -> str | None:
    """The normalised result: a row with no outcome is censored when its root ended in
    error, and unscored (None) otherwise, which a verdicts file may still fill."""
    if outcome == MET:
        return "pass"
    if outcome == MISSED:
        return "fail"
    return "censored" if errored else None


# ---------- one trace, one row ----------


def _tool_calls(tools: Sequence[_Item]) -> tuple[tuple[ToolCallRecord, ...], int]:
    """The trace's tool calls in start order, and its retries. LangSmith records no retry
    event, so a call that follows a failed call of the same name under the same parent is
    the next attempt, and one retry."""
    calls: list[ToolCallRecord] = []
    last: dict[tuple[str | None, str], tuple[bool, int]] = {}
    retries = 0
    for tool in tools:
        at = (tool.parent, tool.name)
        attempt = 1
        if at in last and last[at][0]:
            attempt = last[at][1] + 1
            retries += 1
        last[at] = (tool.errored, attempt)
        calls.append(
            ToolCallRecord(
                name=tool.name or "tool",
                status="error" if tool.errored else "ok",
                duration_s=tool.duration(),
                error_type=error_class(tool.doc.get("error")) if tool.errored else None,
                attempt=attempt,
            )
        )
    return tuple(calls), retries


def _loops(calls: Sequence[ToolCallRecord]) -> bool:
    """Whether three calls in a row went to one tool."""
    run = 0
    for i, call in enumerate(calls):
        run = run + 1 if i and calls[i - 1].name == call.name else 1
        if run >= 3:
            return True
    return False


def _attribute(key: str, value: Any) -> dict[str, Any]:
    """One attribute as OTLP lists it, which is the form the writer's spans take; a plain
    mapping of attributes is dropped without a word."""
    held = {"intValue": value} if isinstance(value, int) else {"stringValue": value}
    return {"key": key, "value": held}


def _span(item: _Item) -> dict[str, Any] | None:
    """The run as one span: its id (the run's own, without dashes), its parent, its kind,
    the model's name, its token counts and its error's class. No text of the run."""
    start = item.start
    if start is None:
        return None
    attributes: dict[str, Any] = {"source.type": item.type}
    if item.type in _OPERATION:
        attributes["gen_ai.operation.name"] = _OPERATION[item.type]
    model = item.meta.get("ls_model_name")
    if isinstance(model, str):
        attributes["llm.model_name"] = model
    tokens = item.tokens()
    for name in ("input_tokens", "output_tokens"):
        if tokens[name] is not None:
            attributes[f"gen_ai.usage.{name}"] = tokens[name]
    failed = error_class(item.doc.get("error"))
    if item.errored and failed is not None:
        attributes["error.type"] = failed
    parent = item.parent
    return {
        "spanId": item.id.replace("-", "").lower(),
        "parentSpanId": None if parent is None else parent.replace("-", "").lower(),
        "name": item.name,
        "startTimeUnixNano": start,
        "endTimeUnixNano": item.end,
        "attributes": [_attribute(k, v) for k, v in attributes.items()],
        "status": {"code": 2 if item.errored else 1},
    }


def _usage_signals(
    root: _Item, llms: Sequence[_Item], cost_field: str
) -> tuple[dict[str, Any], dict[str, str]]:
    """Tokens and cost, summed over the trace's model calls, else the root's own figures (a
    pull of roots alone); and where each was read from. What no run recorded stays None."""
    signals: dict[str, Any] = dict.fromkeys(_TOKENS)
    sources: dict[str, str] = {}
    each = [llm.tokens() for llm in llms]
    for name in _TOKENS:
        counted = [n for n in (tokens[name] for tokens in each) if n is not None]
        if counted:
            signals[name] = sum(counted)
            sources["tokens_from"] = "llm runs"
    if "tokens_from" not in sources:
        own = root.tokens()
        if any(v is not None for v in own.values()):
            signals.update(own)
            sources["tokens_from"] = "root run"
    costs = [c for c in (llm.cost(cost_field) for llm in llms) if c is not None]
    if costs:
        signals["cost_usd"] = math.fsum(costs)
        sources["cost_from"] = "llm runs"
    else:
        signals["cost_usd"] = root.cost(cost_field)
        if signals["cost_usd"] is not None:
            sources["cost_from"] = "root run"
    return signals, sources


def _length(root: _Item, stamp: str, key: str) -> int | None:
    """The length a pull stamped before it left the text out, else the text's own."""
    stamped = _count(root.doc.get(stamp))
    return stamped if stamped is not None else chars(root.doc.get(key))


def _keyed_input(root: _Item) -> str | None:
    stamped = root.doc.get(INPUT_KEY)
    if isinstance(stamped, str) and stamped:
        return stamped
    given = root.doc.get("inputs")
    return None if given is None else input_key(given)


def _trace_row(
    how: _How,
    root: _Item,
    held: Sequence[_Item],
    records: Sequence[Mapping[str, Any]],
    counts: Counter[str],
    inputs: dict[str, str],
) -> Row | None:
    keyed = _keyed_input(root)
    case = how.case(root.doc.get("reference_example_id"), root.meta, keyed)
    if case is None:
        counts["no case"] += 1
        return None
    if keyed is not None:
        inputs.setdefault(case, keyed)
    found = _from_statistics(root)
    filled = _from_records(records)
    counts["scores the run statistics lacked"] += sum(1 for key in filled if key not in found)
    found.update(filled)
    scores, feedback = _scores_and_feedback(found)
    errored = root.errored
    values = {key: value for key, (value, _) in found.items()}
    outcome, reason, score = how.outcome(errored, root.ended, values, root.meta)
    result = _result(outcome, errored)

    ordered = sorted(held, key=lambda item: (item.start or 0, item.id))
    parents = {item.parent for item in ordered}
    leaves = [item for item in ordered if item.id not in parents]
    llms = [item for item in ordered if item.type == "llm"]
    calls, retries = _tool_calls([item for item in ordered if item.type == "tool"])

    start = root.start
    firsts = [t for t in (llm.first_token for llm in llms) if t is not None]
    if not firsts and root.first_token is not None:
        firsts = [root.first_token]
    first = min(firsts) if firsts else None
    signals, sources = _usage_signals(root, llms, how.cost_field)
    signals.update(
        wall_time_s=root.duration(),
        ttft_s=None if first is None or start is None or first < start else (first - start) / 1e9,
        input_chars=_length(root, INPUT_CHARS, "inputs"),
        output_chars=_length(root, OUTPUT_CHARS, "outputs"),
        steps=len(leaves),
        llm_calls=len(llms),
        tool_calls=calls,
        retries=retries,
    )
    kind = None
    if errored:
        # the step that failed is the last leaf that ended in error; its run type is the kind
        failing = [leaf for leaf in leaves if leaf.errored]
        text = root.doc.get("error")
        signals["error_type"] = error_class(text)
        if failing:
            step = failing[-1]
            signals["error_span_kind"] = _STEP_KIND.get(step.type, "other")
            if signals["error_type"] is None:
                signals["error_type"] = error_class(step.doc.get("error"))
            text = text or step.doc.get("error")
        if result in ("fail", "censored"):
            stamped = [
                item.doc[ERROR_KIND]
                for item in (root, *failing)
                if isinstance(item.doc.get(ERROR_KIND), str)
            ]
            kind = stamped[0] if stamped else error_kind(text)
    elif result == "fail" and _loops(calls):
        kind = "loop_detected"
    detail: dict[str, Any] = {}
    kept = {key: types for key, (_, types) in sorted(found.items()) if types}
    if kept:
        detail["feedback_sources"] = kept
    detail.update(sources)
    spans = [span for span in (_span(item) for item in ordered) if span is not None]
    return Row(
        case,
        outcome,
        reason,
        score,
        tuple(spans),
        detail,
        result=result,
        failure_kind=kind,
        scores=scores,
        feedback=feedback,
        **signals,
    )


def _trace_rows(
    how: _How, files: Sequence[_File], counts: Counter[str], inputs: dict[str, str]
) -> tuple[list[Row], list[int]]:
    """The rows of the run exports, in the order their roots started, and the earliest start
    of each trace kept."""
    runs = [item for held in files for item in held.runs]
    seen: dict[str, str] = {}
    for item in runs:
        if item.id in seen:
            both = (
                f"{item.file} twice"
                if seen[item.id] == item.file
                else f"both {seen[item.id]} and {item.file}"
            )
            raise Refusal(
                f"the run {item.id} is in {both}: give one export of each run, since two "
                "would count it twice"
            )
        seen[item.id] = item.file
    if how.outcome_from == "status" and not any(item.says_how_it_ended for item in runs):
        raise Refusal(
            "no run of the export carries a status or an error, so --outcome-from status has "
            "nothing to read: export with --full, or name a feedback or metadata key"
        )
    by_run: dict[str, list[Mapping[str, Any]]] = {}
    records = [record for held in files for record in held.feedback]
    for record in records:
        by_run.setdefault(str(record.get("run_id")), []).append(record)
    traces: dict[str, list[_Item]] = {}
    for item in runs:
        traces.setdefault(item.trace, []).append(item)
    counts["runs"] = len(runs)
    counts["traces"] = len(traces)
    counts["feedback records"] = len(records)
    picked: list[tuple[_Item, list[_Item]]] = []
    for held in traces.values():
        roots = [item for item in held if item.parent is None]
        if len(roots) != 1:
            counts["no root run"] += 1
        elif how.selected(roots[0].meta):
            counts["selected"] += 1
            picked.append((roots[0], held))
    if how.case_from == "example" and any(root.shape == "cli" for root, _ in picked):
        raise Refusal(
            "--case-from example needs the dataset example's id, which the langsmith command's "
            "export leaves out: export through the API or the SDK, or name the case another "
            "way, such as --case-from metadata:KEY"
        )
    if how.case_from == "input" and picked and all(_keyed_input(r) is None for r, _ in picked):
        raise Refusal("--case-from input needs the root runs' inputs, and the export holds none")
    made: list[tuple[tuple[int, str], Row, int]] = []
    for root, held in picked:
        row = _trace_row(how, root, held, by_run.get(root.id, ()), counts, inputs)
        if row is not None:
            earliest = min((s for s in (item.start for item in held) if s is not None), default=0)
            made.append(((root.start or 0, root.trace), row, earliest))
    made.sort(key=lambda entry: entry[0])
    return [row for _, row, _ in made], [earliest for _, _, earliest in made if earliest]


# ---------- the page's CSV ----------


def _csv_number(row: Mapping[str, str], column: str) -> float | None:
    value = _finite(row.get(column) or None)
    return value if value is not None and value >= 0 else None


def _csv_row(
    how: _How,
    path: Path,
    line: int,
    row: Mapping[str, str],
    counts: Counter[str],
    inputs: dict[str, str],
) -> Row | None:
    """One row of the CSV: the root run alone, so no step, call or span. The CSV does not
    say who gave a score, so its numbers are all scores and its words feedback."""
    run = _mapping(_cell(path, line, row, "run"))
    meta = _mapping(_mapping(run.get("extra")).get("metadata"))
    if not how.selected(meta):
        return None
    counts["selected"] += 1
    given = _cell(path, line, row, "inputs")
    keyed = None if given is None else input_key(given)
    case = how.case(row.get("id"), meta, keyed)
    if case is None:
        counts["no case"] += 1
        return None
    if keyed is not None:
        inputs.setdefault(case, keyed)
    found: dict[str, Any] = {}
    for column, cell in row.items():
        # the column named as the cost is the cost, and not a score as well
        if column in _CSV_OWN or column == how.cost_field or not cell:
            continue
        number = _finite(cell)
        found[column] = cell if number is None else number
    status = (row.get("status") or "").lower()
    errored = status == "error"
    outcome, reason, score = how.outcome(errored, status in ("success", "error"), found, meta)
    result = _result(outcome, errored)
    tokens = _csv_number(row, "tokens")
    signals: dict[str, Any] = {
        "wall_time_s": _csv_number(row, "latency"),
        "input_chars": chars(given),
        "output_chars": chars(_cell(path, line, row, "outputs")),
        "total_tokens": None if tokens is None or tokens != int(tokens) else int(tokens),
        "cost_usd": _csv_number(row, how.cost_field),
    }
    kind = None
    if errored:
        signals["error_type"] = error_class(row.get("error"))
        if result in ("fail", "censored"):
            kind = error_kind(row.get("error"))
    detail: dict[str, Any] = {}
    if signals["total_tokens"] is not None:
        detail["tokens_from"] = "root run"
    if signals["cost_usd"] is not None:
        detail["cost_from"] = "root run"
    return Row(
        case,
        outcome,
        reason,
        score,
        None,
        detail,
        result=result,
        failure_kind=kind,
        scores={k: v for k, v in found.items() if isinstance(v, float)},
        feedback={k: v for k, v in found.items() if not isinstance(v, float)},
        **signals,
    )


# ---------- the read ----------

_TRACE_COUNTS = (
    "runs",
    "traces",
    "selected",
    "feedback records",
    "no root run",
    "no case",
    "scores the run statistics lacked",
)
_CSV_COUNTS = ("traces", "selected", "no case")
_ONE_INPUT = (
    "traces read as one input, which is right only if both versions saw the same mix of inputs"
)


def _instant(ns_since_epoch: int) -> str:
    seconds, rest = divmod(ns_since_epoch, 1_000_000_000)
    at = datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{at}.{rest // 1000:06d}Z"


def _file_time(path: Path) -> str:
    try:
        modified = path.stat().st_mtime
    except OSError as e:
        raise Refusal(f"{path} could not be read: {why(e)}") from e
    return datetime.fromtimestamp(modified, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def read(ns: argparse.Namespace) -> Run:
    said = usage(ns)
    if said is not None:
        raise Refusal(said)
    words = [str(f) for f in ns.files]
    if _addresses(words):
        from poisson_trace.ingest import pulling

        pulled = pulling.pull_langsmith(
            words[0],
            Path(ns.store),
            ns.run,
            keep_raw_text=bool(ns.keep_raw_text),
            page_size=int(ns.page_size),
            flags=_flags(ns),
        )
        run = _read(ns, [_load(path) for path in pulled.files])
        return replace(run, pull=pulled.summary)
    return _read(ns, [_load(Path(word)) for word in words])


def _flags(ns: argparse.Namespace) -> list[str]:
    """The flags that read a file as this call reads, for the command that reads a raw copy
    already saved."""
    words = [
        option("--case-from", str(ns.case_from)),
        option("--outcome-from", str(ns.outcome_from)),
    ]
    if ns.cut is not None:
        words += [option("--cut", str(ns.cut)), "--below" if ns.below else "--above"]
    words += [option("--failed", str(value)) for value in ns.failed or ()]
    words += [option("--select", str(chosen)) for chosen in ns.select or ()]
    return words


def _read(ns: argparse.Namespace, files: Sequence[_File]) -> Run:
    how = _how(ns)
    recorded = tuple({"name": held.path.name, "sha256": held.sha256} for held in files)
    table = [(held.path, line, row) for held in files for line, row in held.table]
    has_runs = any(held.runs for held in files)
    if table and has_runs:
        raise Refusal(
            "the files hold an experiment page's CSV and run exports; one import reads one or "
            "the other, since both would count each run twice"
        )
    if not table and not has_runs:
        # feedback records alone are no run: no row, and the import says so. Never a refusal
        # here, since a folder's files are each read alone to check that they are one run.
        return Run(
            name=ns.run,
            tool=TOOL,
            rows=(),
            started=_file_time(files[0].path),
            started_from="file time",
            declared={},
            files=recorded,
        )
    counts: Counter[str] = Counter()
    inputs: dict[str, str] = {}
    if table:
        shapes = ["ui"]
        counts["traces"] = len(table)
        rows = [
            row
            for path, line, cells in table
            if (row := _csv_row(how, path, line, cells, counts, inputs)) is not None
        ]
        started, started_from = _file_time(files[0].path), "file time"
        labels: tuple[str, ...] = _CSV_COUNTS
    else:
        shapes = list(dict.fromkeys(item.shape for held in files for item in held.runs))
        rows, starts = _trace_rows(how, files, counts, inputs)
        if starts:
            started, started_from = _instant(min(starts)), "earliest span"
        else:
            started, started_from = _file_time(files[0].path), "file time"
        labels = _TRACE_COUNTS
    declared: dict[str, Any] = {"case_from": how.case_from, "outcome_from": how.outcome_from}
    if how.cut is not None:
        declared["cut"] = how.cut.cut
        declared["side"] = how.cut.side
    if how.failed:
        declared["failed"] = list(how.failed)
    if ns.select:
        declared["select"] = [str(chosen) for chosen in ns.select]
    declared["shapes"] = shapes
    shown = {label: counts[label] for label in labels}
    if how.case_from == "none":
        shown[_ONE_INPUT] = len(rows)
    return Run(
        name=ns.run,
        tool=TOOL,
        rows=tuple(rows),
        started=started,
        started_from=started_from,
        declared=declared,
        files=recorded,
        counts=shown,
        inputs=inputs,
    )


# ---------- the detector ----------

_CSV_SAYS = (*_CSV_NEEDS, "session_name")
_WHOLE_FILE_MAX = 64 * 1024 * 1024


def _first_row(found: Path) -> Any:
    """The first row of a ``.json`` or ``.jsonl`` file, or None."""
    if found.name.lower().endswith(".jsonl"):
        with open(found, "rb") as f:
            for line in f:
                if line.strip():
                    return json.loads(line.decode("utf-8-sig"))
        return None
    if found.stat().st_size > _WHOLE_FILE_MAX:
        return None
    doc = json.loads(found.read_bytes().decode("utf-8-sig"))
    if isinstance(doc, Mapping):
        doc = next((doc[k] for k in ("runs", "items") if isinstance(doc.get(k), list)), None)
    return doc[0] if isinstance(doc, list) and doc else None


def carries_examples(path: Path | str) -> bool:
    """Whether the file's runs carry the dataset example each was run on, so that
    ``--case-from example`` reads it: the page's CSV, or an export of the API whose root runs
    hold a ``reference_example_id``. It never raises."""
    try:
        held = _load(Path(path))
    except Exception:
        return False
    if held.table:
        return any(row.get("id") for _, row in held.table)
    roots = [item for item in held.runs if item.parent is None]
    return bool(roots) and all(
        item.shape != "cli" and item.doc.get("reference_example_id") for item in roots
    )


def feedback_beside(paths: Sequence[Path | str]) -> dict[str, str | None]:
    """Each of the files that holds feedback records and no run, with the file among them
    whose runs its records score: the runs it is given beside in one import. None where no
    file given holds those runs. A file that cannot be read is neither. It never raises."""
    held: dict[str, _File] = {}
    for path in paths:
        try:
            held[str(path)] = _load(Path(path))
        except Exception:
            continue
    runs = {path: {item.id for item in file.runs} for path, file in held.items() if file.runs}
    beside: dict[str, str | None] = {}
    for path, file in held.items():
        if file.runs or file.table or not file.feedback:
            continue
        scored = {str(record.get("run_id")) for record in file.feedback}
        beside[path] = next((r for r, ids in runs.items() if not scored.isdisjoint(ids)), None)
    return beside


def looks_like(path: Path | str) -> str | None:
    """One line describing ``path`` when it is a LangSmith export, else None; it never
    raises. The CSV is told by its header; a ``.json`` or ``.jsonl`` file by its first row: a
    feedback record, or a run with a trace id, a start and the keys of one of the shapes."""
    try:
        found = Path(path)
        name = found.name.lower()
        if not found.is_file():
            return None
        if name.endswith(".csv"):
            with open(found, encoding="utf-8-sig", newline="") as f:
                header = next(csv.reader(f), [])
            if all(column in header for column in _CSV_SAYS):
                return "a LangSmith experiment's CSV"
            return None
        if not name.endswith((".json", ".jsonl")):
            return None
        doc = _first_row(found)
        if not isinstance(doc, Mapping):
            return None
        shape = _shape(doc)
        if shape == "feedback":
            return FEEDBACK_SAID if "run_id" in doc else None
        if shape is None or "trace_id" not in doc or "start_time" not in doc:
            return None
        if shape == "cli":
            if "custom_metadata" in doc or "duration_ms" in doc:
                return "LangSmith runs, as the langsmith command exports them"
            return None
        if "id" in doc and any(k in doc for k in ("dotted_order", "session_id", "is_root")):
            return "LangSmith runs, as the runs query returns them"
        return None
    except Exception:
        return None
