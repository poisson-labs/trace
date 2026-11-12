"""Braintrust experiments: the API's answers, and the JSON and CSV an experiment's page downloads.

What is read, each told by its extension and then by its rows' keys (the reader's ``SHAPES``):

- ``span``: one event a span, as the experiment fetch answers (a list under ``events``) and as
  BTQL's ``spans`` and ``traces`` shapes answer (a list under ``data``);
- ``summary``: one row a case with its ids, as BTQL's ``summary`` shape answers
  (``comparison_key`` or ``span_type_info``);
- ``ui``: one row a case with no id, as the JSON and the CSV an experiment's page downloads.

A ``.json`` file is a list of rows, or the API's answer holding the list under ``events`` or
``data``; a ``.jsonl`` file is a row a line; a ``.csv`` file is the page's, whose cells are
JSON. Pages of one fetch are given together, the empty last page among them. An event given
twice is refused, as is the page's download beside the API's answers, and two of the page's
downloads together: with no id in them, one experiment given twice cannot be told from two.
In the files' place, ``braintrust:PROJECT/EXPERIMENT`` pulls the experiment through
``ingest/pulling.py``, which saves a raw copy under the store first; the saved copy is then
read as any other file.

One trace is one row. Its root, the span with no parent, decides the case (``--case-from``)
and the outcome (``--outcome-from``), written ``met`` or ``missed``; a trace with no root is
left out and counted. Rows come in the order their roots started, so every export of one
experiment gives the same rows in the same order.

Scores: in the span shape each score sits on a span of type ``score`` under the root, so a
key's value is the mean of the trace's spans that hold it, the root's own included; in the
other two shapes it is the row's. A case that errored has no score, and none is guessed: read
by a score, it has no outcome. Classifications are the row's feedback, each key's word the ids
of its items. Tags are read only for the name of a failure kind; comments are never read.

Signals: wall time from the root's start and end; time to first token as Braintrust measured
it, on the first model call or rolled up to the row; lengths as the characters of every value
in the root's input and output; tokens and cost summed over the ``llm`` spans, or read off the
row's rolled-up metrics, with where each was read from kept beside the row; steps the spans
with no child; tool calls the ``tool`` spans in start order, a call that follows a failed call
of the same name under the same parent being the next attempt and one retry. The spans that
grade a case (``score``, ``classifier``) are read for what they hold; they are no step of the
agent's and no stored span. The summary and the page's rows hold the count of model calls and
nothing else of the structure, so their steps, tool calls and retries are not recorded and no
trace is stored. The error's type is the class the last line of its traceback names; nothing
of an error's words is kept.

No prompt, input, output, expected value, error or comment text is kept. Standard library only.
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
from poisson_trace.ingest.rows import FAILURE_KINDS, Refusal, Row, Run, ToolCallRecord, case_id
from poisson_trace.ingest.taxonomy import CONTEXT, RATE_LIMIT, TIMEOUT
from poisson_trace.look import option, why

DESCRIPTION = """\
Read a Braintrust experiment and write it as one new run: the answers of the experiment fetch
and of a BTQL query (its spans, traces or summary shape), or the JSON or CSV an experiment's
page downloads. Each trace is one row; its root span decides the case and the outcome, as
--case-from and --outcome-from say. In place of the files, braintrust:PROJECT/EXPERIMENT pulls
the experiment with the key in BRAINTRUST_API_KEY, saves a raw copy under the store and reads
that. No input, output or error text is kept.
"""
EXAMPLE = (
    "poisson-trace import braintrust old.json --store trace-store --run old "
    "--case-from input --outcome-from score:exact --cut 0.5 --below"
)

TOOL = "braintrust"
#: The row shapes read: one event a span, BTQL's summary row, the page's row.
SHAPES: tuple[str, ...] = ("span", "summary", "ui")
#: What an address to pull from starts with, in the files' place.
ADDRESS = "braintrust:"

#: What a pull stamps on an event it strips, so that the saved copy reads as the answer did.
INPUT_CHARS = "_poisson_input_chars"
OUTPUT_CHARS = "_poisson_output_chars"
INPUT_KEY = "_poisson_input_key"
ERROR_KIND = "_poisson_error_kind"

#: Why a row has no outcome.
NO_SCORE = "no score"
NO_OUTCOME = "no outcome recorded"
PENDING = "pending"

#: The case every row shares under ``--case-from none``.
UNPAIRED = "unpaired"

#: The metric a cost is read from, unless ``[signals]`` names another.
COST_METRIC = "estimated_cost"

_PAGE_SIZE = "1000"
_LARGEST_PAGE = 1000
# each token signal's metric: on a model call's span, and on a rolled-up row
_SPAN_TOKENS = {
    "input_tokens": "prompt_tokens",
    "output_tokens": "completion_tokens",
    "total_tokens": "tokens",
    "cached_tokens": "prompt_cached_tokens",
    "reasoning_tokens": "completion_reasoning_tokens",
}
_ROW_TOKENS = {**_SPAN_TOKENS, "total_tokens": "total_tokens"}
# a span type as the span's operation, and as the kind of the step that failed
_OPERATION = {"llm": "chat", "tool": "execute_tool"}
_STEP_KIND = {"tool": "tool", "llm": "llm"}
# the spans that grade a case: read for their scores and classifications, never a step
_GRADING = ("score", "classifier")
# a class as a traceback's last line names it: dotted names, then a colon, a bracket or the end
_CLASS = re.compile(r"^([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)(?::|\(|$)")
# the columns the page's CSV always has, and those whose cells are JSON
_CSV_NEEDS = ("input", "output", "scores", "metrics", "created")
_CSV_JSON = (
    "input",
    "output",
    "expected",
    "tags",
    "classifications",
    "scores",
    "metrics",
    "metadata",
    "error",
)
# what a row of the page's download holds, by which it is told from any other list of objects
_UI_NEEDS = ("input", "scores", "metrics", "created")


# ---------- the command line ----------


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--case-from",
        required=True,
        metavar="WHERE",
        help="what identifies a case across the two versions: record (the dataset record's "
        "id), metadata:KEY, input (a key of the root span's input, never its text) or none "
        "(no default)",
    )
    parser.add_argument(
        "--outcome-from",
        required=True,
        metavar="WHERE",
        help="what says a case failed: error (the root span ended in error), score:KEY (a "
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
        help="a value of the metadata key that means the case failed, repeatable (no default)",
    )
    parser.add_argument(
        "--select",
        action="append",
        metavar="metadata:KEY=VALUE",
        help="keep only the traces whose root span holds this, repeatable (default: every trace)",
    )
    parser.add_argument(
        "--keep-raw-text",
        action="store_true",
        help="with braintrust:PROJECT/EXPERIMENT, save the raw copy as Braintrust returned it "
        "(default: the inputs and outputs are measured and left out, and an error keeps its "
        "class alone)",
    )
    parser.add_argument(
        "--page-size",
        metavar="N",
        default=_PAGE_SIZE,
        help="with braintrust:PROJECT/EXPERIMENT, how many events one request asks for, 1 to "
        "1000 (default: 1000)",
    )


def _keyed(word: Any, prefix: str) -> bool:
    """Whether ``word`` is ``PREFIX:KEY`` with a key."""
    return isinstance(word, str) and word.startswith(prefix + ":") and len(word) > len(prefix) + 1


def _key(word: str) -> str:
    return word.split(":", 1)[1]


def _without(word: str, prefix: str) -> str:
    return word[len(prefix) :] if word.startswith(prefix) else word


def reads_a_score(outcome_from: Any, failed: bool) -> bool:
    """Whether the outcome is read at a cut: a score, or a metadata value with no failing
    value named."""
    return _keyed(outcome_from, "score") or (_keyed(outcome_from, "metadata") and not failed)


def stand_ins(signals: Mapping[str, Any], said: Mapping[str, Any]) -> dict[str, Any]:
    """The flags ``[signals]`` stands in for, by dest: ``case_field`` for ``--case-from`` and
    ``outcome_field`` for ``--outcome-from``, each written as the flag writes it;
    ``score_field`` a score's key, as ``KEY``, ``score:KEY`` or ``scores.KEY``, which an
    ``outcome_field`` beside it wins over; and ``cut`` for ``--cut``, only where a score is
    read, so that a cut that serves one import does not make another, read by its error, a
    wrong command line. ``said`` holds what the call itself gave, by dest."""
    found: dict[str, Any] = {}
    if signals.get("case_field") is not None:
        found["case_from"] = signals["case_field"]
    outcome, score = signals.get("outcome_field"), signals.get("score_field")
    if outcome is not None:
        found["outcome_from"] = outcome
    elif score is not None:
        named = _without(str(score), "scores.")
        found["outcome_from"] = named if _keyed(named, "score") else f"score:{named}"
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
    if case not in ("record", "input", "none") and not _keyed(case, "metadata"):
        return "--case-from takes record, metadata:KEY, input or none"
    out, cut, failed = ns.outcome_from, ns.cut, list(ns.failed or ())
    sides = [side for side in ("below", "above") if getattr(ns, side, False)]
    if out == "error":
        if cut is not None or sides or failed:
            return "--outcome-from error reads no score and no value: leave out --cut and --failed"
    elif _keyed(out, "score"):
        if failed:
            return "--failed goes with --outcome-from metadata:KEY"
        if cut is None:
            return "--outcome-from score:KEY reads a score: give --cut X with --below or --above"
    elif _keyed(out, "metadata"):
        if (cut is None) == (not failed):
            return "--outcome-from metadata:KEY needs --failed VALUE, or --cut X with its side"
    else:
        return "--outcome-from takes error, score:KEY or metadata:KEY"
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
        return f"--page-size takes a whole number from 1 to {_LARGEST_PAGE}"
    if not pulled and files and (getattr(ns, "keep_raw_text", False) or size != _PAGE_SIZE):
        return (
            "--keep-raw-text and --page-size go with an address to pull from, "
            "braintrust:PROJECT/EXPERIMENT"
        )
    return None


def _page_size(word: str) -> int | None:
    try:
        size = int(word)
    except ValueError:
        return None
    return size if 1 <= size <= _LARGEST_PAGE else None


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


def _names_a_class(text: Any) -> re.Match[str] | None:
    """The last line of an error where it names a class: ``TimeoutError: ...`` at a
    traceback's end, or the class alone, as a stripped raw copy keeps it. A traceback cut
    short ends in some other line (a ``File`` line, a class cut in two), which names none."""
    if not isinstance(text, str):
        return None
    lines = [line for line in text.splitlines() if line.strip()]
    return _CLASS.match(lines[-1]) if lines else None


def error_class(text: Any) -> str | None:
    """The exception's class an error names: the name its last line begins with."""
    found = _names_a_class(text)
    return found.group(1) if found else None


def error_kind(text: Any) -> str | None:
    """The failure kind the last line of an error says, as the source's own: a timeout, a
    rate limit or a context overflow; else None, and the taxonomy's rules decide. Nothing is
    read from an error cut short of the line that names its class."""
    found = _names_a_class(text)
    if found is None:
        return None
    line = found.string
    if TIMEOUT.search(line):
        return "timeout"
    if RATE_LIMIT.search(line):
        return "rate_limit"
    if CONTEXT.search(line):
        return "context_overflow"
    return None


# ---------- one row, whichever shape wrote it ----------


def nanoseconds(seconds: Any) -> int | None:
    """A Braintrust time, seconds since the epoch as a decimal number, as nanoseconds, or
    None. It is rounded to the nearest microsecond: a float holds the microsecond a hair
    under, and cutting it would lose one."""
    value = _number(seconds)
    if value is None or value < 0:
        return None
    return round(value * 1_000_000) * 1000


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


def _elapsed(start: int | None, end: int | None) -> float | None:
    return None if start is None or end is None or end < start else (end - start) / 1e9


@dataclass(frozen=True)
class _Item:
    """One row that carries its ids (a span, or a summary's row), with the shape its keys
    tell and the file it is in."""

    shape: str
    file: str
    doc: Mapping[str, Any]

    @property
    def id(self) -> str:
        """The event's id. A summary's row carries its root event's."""
        return str(self.doc.get("id"))

    @property
    def span(self) -> str:
        return str(self.doc.get("span_id"))

    @property
    def parent(self) -> str | None:
        """The span this one is under: the first of the parents it names."""
        chain = self.doc.get("span_parents")
        return str(chain[0]) if isinstance(chain, list) and chain else None

    @property
    def trace(self) -> str:
        return str(self.doc.get("root_span_id"))

    @property
    def type(self) -> str:
        return str(_mapping(self.doc.get("span_attributes")).get("type") or "").lower()

    @property
    def name(self) -> str:
        return str(_mapping(self.doc.get("span_attributes")).get("name") or "")

    @property
    def metrics(self) -> Mapping[str, Any]:
        return _mapping(self.doc.get("metrics"))

    @property
    def start(self) -> int | None:
        return nanoseconds(self.metrics.get("start"))

    @property
    def end(self) -> int | None:
        return nanoseconds(self.metrics.get("end"))

    @property
    def meta(self) -> Mapping[str, Any]:
        return _mapping(self.doc.get("metadata"))

    @property
    def errored(self) -> bool:
        return bool(self.doc.get("error"))

    @property
    def grades(self) -> bool:
        """Whether the span grades the case and is none of the agent's work."""
        return self.type in _GRADING

    def duration(self) -> float | None:
        return _elapsed(self.start, self.end)

    def tokens(self) -> dict[str, int | None]:
        """A model call's own token counts."""
        return {name: _count(self.metrics.get(key)) for name, key in _SPAN_TOKENS.items()}

    def first_token(self) -> float | None:
        """Braintrust's own time to first token, measured from this call's start."""
        return _number(self.metrics.get("time_to_first_token"))


# ---------- the files ----------


@dataclass
class _File:
    """One file read: its digest, the rows with ids it holds and the page's rows."""

    path: Path
    sha256: str
    items: list[_Item] = field(default_factory=list)
    page: list[Mapping[str, Any]] = field(default_factory=list)


def _not_an_export(path: Path, what: str) -> Refusal:
    return Refusal(f"{path} is not a Braintrust export: {what}")


def _load(path: Path) -> _File:
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise Refusal(f"{path} could not be read: {why(e)}") from e
    name = path.name.lower()
    if not name.endswith((".json", ".jsonl", ".csv")):
        raise Refusal(
            f"{path} is not a file the Braintrust reader reads: it reads .json, .jsonl and .csv"
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
        for key in ("events", "data"):
            if isinstance(doc.get(key), list):
                return list(doc[key])
        raise _not_an_export(path, "it holds no list of events (under events or data)")
    if not isinstance(doc, list):
        raise _not_an_export(path, "it is not a list of events or of an experiment's rows")
    return doc


def _shape(doc: Mapping[str, Any]) -> str | None:
    """The shape a row's keys tell, or None: a row with its span's ids is a summary's where
    it holds ``comparison_key`` or ``span_type_info`` and a span otherwise; a row with no id
    at all is the page's where it holds what the page writes."""
    if "span_id" in doc and "root_span_id" in doc:
        if "span_attributes" not in doc and "metrics" not in doc:
            return None
        return "summary" if "comparison_key" in doc or "span_type_info" in doc else "span"
    if any(key in doc for key in ("id", "span_id", "root_span_id")):
        return None
    return "ui" if all(key in doc for key in _UI_NEEDS) else None


def _take(held: _File, doc: Any, where: str) -> None:
    if not isinstance(doc, Mapping):
        raise _not_an_export(held.path, f"{where} is not a JSON object")
    shape = _shape(doc)
    if shape is None:
        raise _not_an_export(held.path, f"{where} is neither a span nor an experiment's row")
    if shape == "ui":
        held.page.append(doc)
    else:
        held.items.append(_Item(shape, held.path.name, doc))


def _load_csv(held: _File, text: str) -> None:
    """The page's CSV, each row as the page's JSON holds it: the cells that are JSON read."""
    reader = csv.DictReader(io.StringIO(text, newline=""))
    columns = list(reader.fieldnames or ())
    lacking = [column for column in _CSV_NEEDS if column not in columns]
    if lacking:
        raise Refusal(
            f"{held.path} is not the CSV a Braintrust experiment's page downloads: it has no "
            f"{lacking[0]} column"
        )
    try:
        for row in reader:
            held.page.append(
                {
                    column: _cell(held.path, reader.line_num, column, cell)
                    for column, cell in row.items()
                    if column is not None
                }
            )
    except csv.Error as e:
        raise Refusal(f"{held.path} line {reader.line_num} cannot be read as CSV: {why(e)}") from e


def _cell(path: Path, line: int, column: str, cell: Any) -> Any:
    """A cell of the page's CSV: the JSON it writes in the columns that hold JSON (None when
    empty), and its text in any other."""
    if column not in _CSV_JSON:
        return cell
    if not isinstance(cell, str) or not cell.strip():
        return None
    try:
        return json.loads(cell)
    except ValueError:
        raise Refusal(
            f"{path} line {line}: the {column} cell is not the JSON the page writes"
        ) from None


# ---------- scores and classifications ----------


def _scores(docs: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    """Each score key the rows hold: its value, or the mean where several rows hold it."""
    held: dict[str, list[float]] = {}
    for doc in docs:
        for key, value in _mapping(doc.get("scores")).items():
            number = _number(value)
            if number is not None:
                held.setdefault(str(key), []).append(number)
    return {key: math.fsum(values) / len(values) for key, values in held.items()}


def _classified(docs: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Each classification's word: the ids of its items, joined by a comma where there are
    several. The page's files write the items as a string of JSON, read alike. The first row
    that holds a key gives its word."""
    out: dict[str, str] = {}
    for doc in docs:
        for key, items in _mapping(doc.get("classifications")).items():
            if isinstance(items, str):
                try:
                    items = json.loads(items)
                except ValueError:
                    continue
            if not isinstance(items, list):
                continue
            ids = [
                str(item["id"])
                for item in items
                if isinstance(item, Mapping) and item.get("id") is not None
            ]
            if ids and str(key) not in out:
                out[str(key)] = ",".join(ids)
    return out


def _named_kind(labels: Mapping[str, str], tags: Any) -> str | None:
    """The failure kind a classification or a tag names: the first in the kinds' order."""
    words = {word for value in labels.values() for word in value.split(",")}
    if isinstance(tags, list):
        words.update(tag for tag in tags if isinstance(tag, str))
    return next((kind for kind in FAILURE_KINDS if kind in words), None)


# ---------- the case and the outcome ----------


@dataclass(frozen=True)
class _How:
    """How the rows are read: what the flags said."""

    case_from: str
    outcome_from: str
    cut: Cut | None
    failed: tuple[str, ...]
    selects: tuple[tuple[str, str], ...]
    cost_metric: str

    def selected(self, meta: Mapping[str, Any]) -> bool:
        for key, value in self.selects:
            held = meta.get(key)
            if held is None or _spelt(held) != value:
                return False
        return True

    def case(self, record: Any, meta: Mapping[str, Any], keyed: str | None) -> str | None:
        """The row's case, or None when its root holds none."""
        if self.case_from == "none":
            return UNPAIRED
        if self.case_from == "record":
            return case_id(str(record)) if record else None
        if self.case_from == "input":
            return keyed
        value = meta.get(_key(self.case_from))
        return None if value is None or value == "" else case_id(_spelt(value))

    def outcome(
        self, errored: bool, ended: bool, scores: Mapping[str, float], meta: Mapping[str, Any]
    ) -> tuple[str | None, str | None, float | None]:
        """The outcome word, the reason a row has none, and the score read."""
        if self.outcome_from == "error":
            if not ended:
                return None, PENDING, None
            return (MISSED if errored else MET), None, None
        key = _key(self.outcome_from)
        if _keyed(self.outcome_from, "score"):
            score = _number(scores.get(key))
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
                f"--cut reads {self.outcome_from} as a score, and a root span holds "
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
        cost_metric=_without(str(signals.get("cost_field") or COST_METRIC), "metrics."),
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
    """The trace's tool calls in start order, and its retries. Braintrust records no retry
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
    """One attribute as OTLP lists it, which is the form the writer's spans take."""
    held = {"intValue": value} if isinstance(value, int) else {"stringValue": value}
    return {"key": key, "value": held}


def _span(item: _Item) -> dict[str, Any] | None:
    """The event as one stored span: its own span id, its parent, its kind, a model call's
    model and token counts, and its error's class. No text of the event."""
    start = item.start
    if start is None:
        return None
    attributes: dict[str, Any] = {"source.type": item.type}
    if item.type in _OPERATION:
        attributes["gen_ai.operation.name"] = _OPERATION[item.type]
    model = item.meta.get("model")
    if item.type == "llm" and isinstance(model, str):
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
        "spanId": item.span.lower(),
        "parentSpanId": None if parent is None else parent.lower(),
        "name": item.name,
        "startTimeUnixNano": start,
        "endTimeUnixNano": item.end,
        "attributes": [_attribute(k, v) for k, v in attributes.items()],
        "status": {"code": 2 if item.errored else 1},
    }


def _length(doc: Mapping[str, Any], stamp: str, key: str) -> int | None:
    """The length a pull stamped before it left the text out, else the text's own."""
    stamped = _count(doc.get(stamp))
    return stamped if stamped is not None else chars(doc.get(key))


def _keyed_input(doc: Mapping[str, Any]) -> str | None:
    stamped = doc.get(INPUT_KEY)
    if isinstance(stamped, str) and stamped:
        return stamped
    given = doc.get("input")
    return None if given is None else input_key(given)


def _record(doc: Mapping[str, Any]) -> Any:
    """The id of the dataset record the case was run on, where the row carries it."""
    return _mapping(doc.get("origin")).get("id")


@dataclass
class _Read:
    """What a trace's structure gives: the signals, where the tokens and the cost came from,
    the stored spans, the tool calls, and what is known of the step that failed."""

    signals: dict[str, Any]
    sources: dict[str, str]
    spans: tuple[dict[str, Any], ...] | None = None
    calls: tuple[ToolCallRecord, ...] | None = None
    failed_kind: str | None = None
    failed_text: Any = None


def _from_spans(how: _How, root: _Item, held: Sequence[_Item]) -> _Read:
    """A trace read from its spans. The grading spans are left out of everything here."""
    work = sorted((item for item in held if not item.grades), key=lambda i: (i.start or 0, i.id))
    parents = {item.parent for item in work}
    leaves = [item for item in work if item.span not in parents]
    llms = [item for item in work if item.type == "llm"]
    calls, retries = _tool_calls([item for item in work if item.type == "tool"])
    signals: dict[str, Any] = dict.fromkeys(_SPAN_TOKENS)
    sources: dict[str, str] = {}
    each = [llm.tokens() for llm in llms]
    for name in _SPAN_TOKENS:
        counted = [n for n in (tokens[name] for tokens in each) if n is not None]
        if counted:
            signals[name] = sum(counted)
            sources["tokens_from"] = "llm spans"
    each_cost = (_number(llm.metrics.get(how.cost_metric)) for llm in llms)
    costs = [cost for cost in each_cost if cost is not None]
    signals["cost_usd"] = math.fsum(costs) if costs else None
    if costs:
        sources["cost_from"] = "llm spans"
    firsts = [t for t in (llm.first_token() for llm in llms) if t is not None]
    signals.update(
        wall_time_s=root.duration(),
        ttft_s=firsts[0] if firsts else None,
        steps=len(leaves),
        llm_calls=len(llms),
        retries=retries,
    )
    read = _Read(signals, sources, calls=calls)
    read.spans = tuple(span for span in (_span(item) for item in work) if span is not None)
    # the step that failed is the last step that ended in error; its span type is the kind
    failing = [leaf for leaf in leaves if leaf.errored]
    if failing:
        read.failed_kind = _STEP_KIND.get(failing[-1].type, "other")
        read.failed_text = failing[-1].doc.get("error")
    return read


def _from_row(how: _How, doc: Mapping[str, Any]) -> _Read:
    """A trace read from its one rolled-up row (a summary's, or the page's): what its metrics
    hold, and nothing of the structure but the count of model calls."""
    metrics = _mapping(doc.get("metrics"))
    signals: dict[str, Any] = {
        name: _count(metrics.get(key)) for name, key in _ROW_TOKENS.items()
    }
    sources: dict[str, str] = {}
    if any(value is not None for value in signals.values()):
        sources["tokens_from"] = "row metrics"
    signals["cost_usd"] = _number(metrics.get(how.cost_metric))
    if signals["cost_usd"] is not None:
        sources["cost_from"] = "row metrics"
    signals.update(
        wall_time_s=_elapsed(nanoseconds(metrics.get("start")), nanoseconds(metrics.get("end"))),
        ttft_s=_number(metrics.get("time_to_first_token")),
        llm_calls=_count(metrics.get("llm_calls")),
    )
    read = _Read(signals, sources)
    # the row counts the tool calls and the model calls that failed, and holds no span
    if _count(metrics.get("tool_errors")):
        read.failed_kind = "tool"
    elif _count(metrics.get("llm_errors")):
        read.failed_kind = "llm"
    return read


def _row(
    how: _How,
    doc: Mapping[str, Any],
    held: Sequence[_Item] | None,
    counts: Counter[str],
    inputs: dict[str, str],
) -> Row | None:
    """One trace as a row. ``doc`` is its root: a span, a summary's row or the page's;
    ``held`` is the trace's spans with the root among them, or None where the row rolls them
    up."""
    meta = _mapping(doc.get("metadata"))
    keyed = _keyed_input(doc)
    case = how.case(_record(doc), meta, keyed)
    if case is None:
        counts["no case"] += 1
        return None
    if keyed is not None:
        inputs.setdefault(case, keyed)
    docs = [doc] if held is None else [doc, *(item.doc for item in held if item.doc is not doc)]
    scores = _scores(docs)
    labels = _classified(docs)
    errored = bool(doc.get("error"))
    ended = nanoseconds(_mapping(doc.get("metrics")).get("end")) is not None
    outcome, reason, score = how.outcome(errored, ended, scores, meta)
    result = _result(outcome, errored)

    if held is None:
        read = _from_row(how, doc)
    else:
        read = _from_spans(how, next(item for item in held if item.doc is doc), held)
    signals = read.signals
    signals["input_chars"] = _length(doc, INPUT_CHARS, "input")
    signals["output_chars"] = _length(doc, OUTPUT_CHARS, "output")
    kind = None
    if errored:
        text = doc.get("error")
        signals["error_type"] = error_class(text)
        if signals["error_type"] is None:
            signals["error_type"] = error_class(read.failed_text)
        if read.failed_kind is not None:
            signals["error_span_kind"] = read.failed_kind
        if result in ("fail", "censored"):
            stamped = doc.get(ERROR_KIND)
            kind = stamped if isinstance(stamped, str) else error_kind(text)
            if kind is None and not isinstance(stamped, str):
                kind = error_kind(read.failed_text)
    elif result == "fail":
        kind = _named_kind(labels, doc.get("tags"))
        if kind is None and read.calls is not None and _loops(read.calls):
            kind = "loop_detected"
    return Row(
        case,
        outcome,
        reason,
        score,
        read.spans,
        dict(read.sources),
        result=result,
        failure_kind=kind,
        scores=scores,
        feedback=labels,
        tool_calls=read.calls,
        **signals,
    )


# ---------- the read ----------

_SPAN_COUNTS = ("events", "traces", "selected", "no root span", "no case")
_ROW_COUNTS = ("traces", "selected", "no case")
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

        pulled = pulling.pull_braintrust(
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


#: A row made, with what orders it (its root's start, then a tie-break) and its trace's
#: earliest start.
_Made = tuple[tuple[int, str], Row, int]


def _page_rows(
    how: _How, held: _File, counts: Counter[str], inputs: dict[str, str]
) -> list[_Made]:
    """The rows of the page's download: one a case, each carrying its root's start."""
    counts["traces"] = len(held.page)
    picked = [doc for doc in held.page if how.selected(_mapping(doc.get("metadata")))]
    counts["selected"] = len(picked)
    _check_case(how, picked, "the page's download leaves it out")
    made: list[_Made] = []
    for number, doc in enumerate(picked):
        row = _row(how, doc, None, counts, inputs)
        if row is not None:
            start = nanoseconds(_mapping(doc.get("metrics")).get("start")) or 0
            made.append(((start, f"{number:09d}"), row, start))
    return made


def _trace_rows(
    how: _How, items: Sequence[_Item], counts: Counter[str], inputs: dict[str, str]
) -> list[_Made]:
    """The rows of the API's answers: one a trace that has its root."""
    seen: dict[str, str] = {}
    for item in items:
        if item.id in seen:
            both = (
                f"{item.file} twice"
                if seen[item.id] == item.file
                else f"both {seen[item.id]} and {item.file}"
            )
            raise Refusal(
                f"the event {item.id} is in {both}: give one export of each experiment, since "
                "two would count it twice"
            )
        seen[item.id] = item.file
    traces: dict[str, list[_Item]] = {}
    for item in items:
        traces.setdefault(item.trace, []).append(item)
    counts["events"] = len(items)
    counts["traces"] = len(traces)
    picked: list[tuple[_Item, list[_Item]]] = []
    for held in traces.values():
        roots = [item for item in held if item.parent is None]
        if len(roots) != 1:
            counts["no root span"] += 1
        elif how.selected(roots[0].meta):
            counts["selected"] += 1
            picked.append((roots[0], held))
    _check_case(how, [root.doc for root, _ in picked], "no root span of the export holds one")
    made: list[_Made] = []
    for root, held in picked:
        # a summary's row rolls its spans up; a span's trace is read from the spans
        row = _row(how, root.doc, None if root.shape == "summary" else held, counts, inputs)
        if row is not None:
            starts = [s for s in (item.start for item in held) if s is not None]
            made.append(((root.start or 0, root.id), row, min(starts, default=0)))
    return made


def _check_case(how: _How, roots: Sequence[Mapping[str, Any]], why_not: str) -> None:
    """Refuse a case no root kept can give, naming another way to say it."""
    if how.case_from == "record" and roots and not any(_record(doc) for doc in roots):
        raise Refusal(
            f"--case-from record needs the dataset record's id, and {why_not}: name the case "
            "another way, such as --case-from input"
        )
    if how.case_from == "input" and roots and all(_keyed_input(doc) is None for doc in roots):
        raise Refusal("--case-from input needs the root spans' inputs, and the export holds none")


def _read(ns: argparse.Namespace, files: Sequence[_File]) -> Run:
    how = _how(ns)
    recorded = tuple({"name": held.path.name, "sha256": held.sha256} for held in files)
    pages = [held for held in files if held.page]
    items = [item for held in files for item in held.items]
    if pages and items:
        raise Refusal(
            "the files hold an experiment page's download and the API's answers; one import "
            "reads one or the other, since both would count each case twice"
        )
    if len(pages) > 1:
        raise Refusal(
            f"{pages[0].path.name} and {pages[1].path.name} are both an experiment page's "
            "download, which carries no id, so the same experiment given twice cannot be told "
            "from two experiments: import one file"
        )
    counts: Counter[str] = Counter()
    inputs: dict[str, str] = {}
    if pages:
        shapes = ["ui"]
        made = _page_rows(how, pages[0], counts, inputs)
    else:
        # a page of a fetch read alone holds traces with no root, and the last page nothing:
        # each reads to the rows it has and is never refused, since a folder's files are each
        # read alone to check that they are one run
        shapes = list(dict.fromkeys(item.shape for item in items))
        made = _trace_rows(how, items, counts, inputs)
    made.sort(key=lambda entry: entry[0])
    rows = [row for _, row, _ in made]
    starts = [earliest for _, _, earliest in made if earliest]
    if starts:
        started, started_from = _instant(min(starts)), "earliest span"
    else:
        started, started_from = _file_time(files[0].path), "file time"
    declared: dict[str, Any] = {"case_from": how.case_from, "outcome_from": how.outcome_from}
    if how.cut is not None:
        declared["cut"] = how.cut.cut
        declared["side"] = how.cut.side
    if how.failed:
        declared["failed"] = list(how.failed)
    if ns.select:
        declared["select"] = [str(chosen) for chosen in ns.select]
    declared["shapes"] = shapes
    shown = {label: counts[label] for label in (_SPAN_COUNTS if "span" in shapes else _ROW_COUNTS)}
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
        doc = next((doc[k] for k in ("events", "data") if isinstance(doc.get(k), list)), None)
    return doc[0] if isinstance(doc, list) and doc else None


def carries_records(path: Path | str) -> bool:
    """Whether the file's roots each carry the dataset record they were run on, so that
    ``--case-from record`` reads it: an answer of the API whose every root holds its record's
    id. The page's downloads hold none. It never raises."""
    try:
        held = _load(Path(path))
    except Exception:
        return False
    roots = [item for item in held.items if item.parent is None]
    return bool(roots) and all(_record(item.doc) for item in roots)


def looks_like(path: Path | str) -> str | None:
    """One line describing ``path`` when it is a Braintrust export, else None; it never
    raises. The CSV is told by its header; a ``.json`` or ``.jsonl`` file by its first row: a
    span with its parents and attributes, a summary's row, or the page's row."""
    try:
        found = Path(path)
        name = found.name.lower()
        if not found.is_file():
            return None
        if name.endswith(".csv"):
            with open(found, encoding="utf-8-sig", newline="") as f:
                header = next(csv.reader(f), [])
            if all(column in header for column in (*_CSV_NEEDS, "__bt_assignments")):
                return "a Braintrust experiment's CSV"
            return None
        if not name.endswith((".json", ".jsonl")):
            return None
        doc = _first_row(found)
        if not isinstance(doc, Mapping):
            return None
        shape = _shape(doc)
        if shape == "ui":
            return "a Braintrust experiment's rows, as its page downloads them"
        if shape == "summary":
            return "a Braintrust experiment's rows, as a summary query returns them"
        if shape == "span" and "span_parents" in doc and "span_attributes" in doc:
            return "Braintrust spans, as the experiment fetch returns them"
        return None
    except Exception:
        return None
