"""W&B Weave evaluations: the calls Weave's service answers with, and the files its Traces page
downloads.

What is read, each told by the file's extension (the reader's ``SHAPES``):

- ``call``: one call an object. A ``.jsonl`` file holds a call a line, as ``POST
  /calls/stream_query`` answers and as the Traces page downloads its JSON Lines; a ``.json``
  file holds a list of calls, as the page downloads its JSON.
- ``table``: one call a row and one value a column named by its dotted path, as the page
  downloads its CSV and its TSV.

One ``Evaluation.predict_and_score`` call is one row: one case of the dataset, run once. The
rows of one evaluation are the calls whose parent is its ``Evaluation.evaluate`` call. The
row's example decides the case (``--case-from``) and the row's call the outcome
(``--outcome-from``), written ``met`` or ``missed``. Rows come in the order their calls
started, so every export of one evaluation gives the same rows in the same order.

Files that hold the rows of more than one evaluation are refused, naming each, unless
``--evaluation`` names the one to read. A file that holds nothing but ``Evaluation.evaluate``
calls, which is what the Traces page shows with no filter, has no case in it and is refused
saying how to get the rows. A call given twice is refused, so pages of one answer are given
together and two exports of one evaluation are not. In the files' place,
``weave:ENTITY/PROJECT/EVALUATION`` pulls the evaluation through ``ingest/pulling.py``, which
saves a raw copy under the store first; the saved copy is then read as any other file.

A case errored when its own call raised, or when something under it raised and it holds no
output and no score. A step that failed and was tried again under a case that answered fails
nothing. Scores are the scorers' outputs under the row's ``output.scores``: a number as it is,
true as 1 and false as 0, each named by its dotted path, and by its scorer alone where the
value sits under the scorer's own name. A scorer's text is never kept. A case that errored
has no score, and none is guessed: read by a score, it has no outcome. A reaction on the
row's call is the row's feedback; a note is never read.

Signals: wall time is Weave's own figure for the model's run (``output.model_latency``), else
the call's end less its start; Weave records no time to first token; lengths are the
characters of every value of the example and of the model's output, and are not recorded
where the file holds a reference in their place; tokens and cost are the call's own summary
(``summary.usage``, ``summary.weave.costs``), summed over its models, with where each was
read from kept beside the row. From the calls under the row, where the files hold them: steps
are the calls under the model's call that have no call under them; model calls are the calls
marked ``llm`` and tool calls the calls marked ``tool``; a call that follows a failed call of
the same op under the same parent is the next attempt and one retry. The scorers' calls are
no step of the agent's and no stored span. The page's downloads hold the rows alone, so
their steps, tool calls and retries are not recorded and no trace is stored.

No prompt, input, output, expected value, error or note text is kept. Standard library only.
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
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from poisson_trace.ingest.cut import MET, MISSED, Cut
from poisson_trace.ingest.rows import Refusal, Row, Run, ToolCallRecord, case_id
from poisson_trace.ingest.taxonomy import CONTEXT, RATE_LIMIT, TIMEOUT
from poisson_trace.look import option, why

DESCRIPTION = """\
Read a W&B Weave evaluation and write it as one new run: the calls Weave's service answers
with (POST /calls/stream_query), or the JSON, JSON Lines, CSV or TSV the Traces page downloads
once it is filtered to the op Evaluation.predict_and_score. Each such call is one row; its
example decides the case and the call the outcome, as --case-from and --outcome-from say. In
place of the files, weave:ENTITY/PROJECT/EVALUATION pulls the evaluation with the key in
WANDB_API_KEY, saves a raw copy under the store and reads that. No input, output or error
text is kept.
"""
EXAMPLE = (
    "poisson-trace import weave old.jsonl --store trace-store --run old "
    "--case-from example --outcome-from score:exact --cut 0.5 --below"
)

TOOL = "weave"
#: The shapes read: one call an object, and one call a row of the page's table.
SHAPES: tuple[str, ...] = ("call", "table")
#: What an address to pull from starts with, in the files' place.
ADDRESS = "weave:"

#: The two ops an evaluation is made of: the call that runs it, and the call that runs one
#: case of it.
EVALUATE = "Evaluation.evaluate"
PREDICT_AND_SCORE = "Evaluation.predict_and_score"

#: What a pull stamps on a call it strips, so that the saved copy reads as the answer did.
INPUT_CHARS = "_poisson_input_chars"
OUTPUT_CHARS = "_poisson_output_chars"
INPUT_KEY = "_poisson_input_key"
ERROR_KIND = "_poisson_error_kind"
#: Stamped true on a row whose answer is a reference: a reference has no length, and without
#: the stamp a stripped copy could not tell that answer from no answer.
OUTPUT_REF = "_poisson_output_ref"

#: Why a row has no outcome.
NO_SCORE = "no score"
PENDING = "pending"

#: The case every row shares under ``--case-from none``.
UNPAIRED = "unpaired"

#: Where a row's tokens and cost are read from.
CALL_SUMMARY = "call summary"

#: The feedback Weave keeps for a reaction made on a call.
REACTION = "wandb.reaction.1"

_PAGE_SIZE = "1000"
_LARGEST_PAGE = 1000
# what a reference to an object Weave holds starts with
_REF = "weave:///"
# the digest of a dataset row, at the end of the reference to it
_ROW_DIGEST = re.compile(r"/attr/rows/id/([^/]+)$")
# the name of the object a reference names, before its digest
_OBJECT = re.compile(r"/object/([^/:]+)")
# a class as a line names it: dotted names, then a colon, a bracket or the end
_CLASS = re.compile(r"^([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)(?::|\(|$)")
# a call's mark as the stored span's operation, and as the kind of the step that failed
_OPERATION = {"llm": "chat", "tool": "execute_tool"}
_STEP_KIND = {"llm": "llm", "tool": "tool"}
# the columns every table of the Traces page has, by which it is told from any other table
_TABLE_NEEDS = ("id", "op_name", "trace_id", "started_at", "summary.weave.status")
# the columns of the table that are a call's own keys
_TABLE_KEYS = (
    "id",
    "project_id",
    "op_name",
    "display_name",
    "trace_id",
    "parent_id",
    "started_at",
    "ended_at",
    "exception",
)
# a model's token counts as its usage names them (OpenAI's names, then Anthropic's), by signal
_TOKENS = {
    "input_tokens": ("prompt_tokens", "input_tokens"),
    "output_tokens": ("completion_tokens", "output_tokens"),
    "total_tokens": ("total_tokens",),
}
_TOKEN_DETAILS = {
    "cached_tokens": ("prompt_tokens_details", "cached_tokens"),
    "reasoning_tokens": ("completion_tokens_details", "reasoning_tokens"),
}
# the two costs a row's cost is the sum of; the cache costs beside them are not added
_COSTS = ("prompt_tokens_total_cost", "completion_tokens_total_cost")
# what a column of a model's usage ends with. A model's name holds dots, so the model is what
# stands before one of these, never a part between two dots.
_USAGE_LEAVES = (
    "prompt_tokens_details.cached_tokens",
    "completion_tokens_details.reasoning_tokens",
    "prompt_tokens",
    "completion_tokens",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "requests",
)
_USAGE = "summary.usage."
_COST = "summary.weave.costs."
_EXAMPLE = "inputs.example."
_ANSWER = "output.output."
_SCORE = "output.scores."
_REACTION_COLUMN = f"summary.weave.feedback.{REACTION}.payload.alias"

_BOOLEANS = "scores that are true or false, read as 1 and 0"
_NO_COST = "no cost recorded"
_ONE_INPUT = (
    "calls read as one input, which is right only if both versions saw the same mix of inputs"
)
_COUNTS = ("calls", "predict_and_score calls", "selected", "no case", _NO_COST)


# ---------- the command line ----------


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--case-from",
        required=True,
        metavar="WHERE",
        help="what identifies a case across the two versions: example (the dataset row the "
        "case was run on, by the reference to it), example:KEY (a key of that row), input (a "
        "key of the row's values, never their text) or none (no default)",
    )
    parser.add_argument(
        "--outcome-from",
        required=True,
        metavar="WHERE",
        help="what says a case failed: status (the case errored) or score:KEY (a scorer's "
        "output, read at --cut; true is 1 and false is 0) (no default)",
    )
    parser.add_argument(
        "--cut",
        metavar="X",
        help="the cut a score is read at, with --below or --above (no default)",
    )
    parser.add_argument("--below", action="store_true", help="a score below the cut missed it")
    parser.add_argument("--above", action="store_true", help="a score above the cut missed it")
    parser.add_argument(
        "--evaluation",
        metavar="NAME",
        help="the evaluation to read, where the files hold more than one: its name, the id of "
        "its Evaluation.evaluate call, or the name Weave shows for that call (default: the "
        "one evaluation the files hold)",
    )
    parser.add_argument(
        "--keep-raw-text",
        action="store_true",
        help="with weave:ENTITY/PROJECT/EVALUATION, save the raw copy as Weave returned it "
        "(default: the inputs and outputs are measured and left out, and an error keeps its "
        "class alone)",
    )
    parser.add_argument(
        "--page-size",
        metavar="N",
        default=_PAGE_SIZE,
        help="with weave:ENTITY/PROJECT/EVALUATION, how many calls one request asks for, 1 to "
        "1000 (default: 1000)",
    )


def _keyed(word: Any, prefix: str) -> bool:
    """Whether ``word`` is ``PREFIX:KEY`` with a key."""
    return isinstance(word, str) and word.startswith(prefix + ":") and len(word) > len(prefix) + 1


def _key(word: str) -> str:
    return word.split(":", 1)[1]


def stand_ins(signals: Mapping[str, Any], said: Mapping[str, Any]) -> dict[str, Any]:
    """The flags ``[signals]`` stands in for, by dest: ``case_field`` for ``--case-from`` and
    ``outcome_field`` for ``--outcome-from``, each written as the flag writes it;
    ``score_field`` a score's key, as ``KEY``, ``score:KEY``, ``scores.KEY`` or
    ``output.scores.KEY``, which an ``outcome_field`` beside it wins over; and ``cut`` for
    ``--cut``, only where a score is read, so that a cut that serves one import does not make
    another, read by its status, a wrong command line. Nothing stands in for
    ``--evaluation``, and ``cost_field`` is not read: a cost here is two fields under a
    model's name. ``said`` holds what the call itself gave, by dest."""
    found: dict[str, Any] = {}
    if signals.get("case_field") is not None:
        found["case_from"] = signals["case_field"]
    outcome, score = signals.get("outcome_field"), signals.get("score_field")
    if outcome is not None:
        found["outcome_from"] = outcome
    elif score is not None:
        named = str(score)
        for prefix in ("output.scores.", "scores."):
            if named.startswith(prefix):
                named = named[len(prefix) :]
                break
        found["outcome_from"] = named if _keyed(named, "score") else f"score:{named}"
    read = said.get("outcome_from") or found.get("outcome_from")
    if signals.get("cut") is not None and _keyed(read, "score"):
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
    if case not in ("example", "input", "none") and not _keyed(case, "example"):
        return "--case-from takes example, example:KEY, input or none"
    out, cut = ns.outcome_from, ns.cut
    sides = [side for side in ("below", "above") if getattr(ns, side, False)]
    if out == "status":
        if cut is not None or sides:
            return "--outcome-from status reads no score: leave out --cut and its side"
    elif _keyed(out, "score"):
        if cut is None and not sides:
            return "--outcome-from score:KEY reads a score: give --cut X with --below or --above"
    else:
        return "--outcome-from takes status or score:KEY"
    if cut is None and sides:
        return "--below and --above go with --cut"
    if cut is not None:
        if len(sides) != 1:
            return "--cut needs one of --below and --above"
        if _finite(cut) is None:
            return f"--cut takes a number, not {cut}"
    named = getattr(ns, "evaluation", None)
    if named is not None and not str(named).strip():
        return "--evaluation takes the evaluation's name, or the id of its call"
    size = str(getattr(ns, "page_size", _PAGE_SIZE))
    if _page_size(size) is None:
        return f"--page-size takes a whole number from 1 to {_LARGEST_PAGE}"
    if not pulled and files and (getattr(ns, "keep_raw_text", False) or size != _PAGE_SIZE):
        return (
            "--keep-raw-text and --page-size go with an address to pull from, "
            "weave:ENTITY/PROJECT/EVALUATION"
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


def is_ref(value: Any) -> bool:
    """Whether ``value`` is a reference to an object Weave holds, and not the value itself."""
    return isinstance(value, str) and value.startswith(_REF)


def chars(value: Any) -> int | None:
    """The characters of every value in ``value``: text as written, a number or true/false as
    JSON writes it, null nothing; keys and punctuation are not counted. None when there is no
    value at all, or a reference stands in its place: the text is not in the file, which is
    "not recorded" and not zero."""
    if value is None or is_ref(value):
        return None
    return _characters(value)


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


def op_name(ref: Any) -> str:
    """The op a call's ``op_name`` names: the last part of the reference, without its
    digest."""
    return str(ref or "").rsplit("/", 1)[-1].split(":", 1)[0]


def object_name(ref: Any) -> str | None:
    """The name of the object a reference names (an evaluation's, a model's), or None."""
    found = _OBJECT.search(ref) if isinstance(ref, str) else None
    return found.group(1) if found else None


def shown_name(doc: Mapping[str, Any]) -> str | None:
    """The name Weave shows for a call: the one given to it, which the call carries and its
    summary repeats; None for a call shown by its op alone."""
    said = _mapping(_mapping(doc.get("summary")).get("weave")).get("display_name")
    for held in (doc.get("display_name"), said):
        if isinstance(held, str) and held:
            return held
    return None


def example_of(doc: Mapping[str, Any]) -> tuple[Mapping[str, Any] | None, str | None]:
    """The dataset row a ``predict_and_score`` call was run on, where the file holds it, and
    the reference to it, where the file holds that. The service's plain answer holds the
    reference alone; with the example expanded it holds the row with its reference in it;
    the page's table holds the row and no reference."""
    given = _mapping(doc.get("inputs")).get("example")
    if is_ref(given):
        return None, str(given)
    if not isinstance(given, Mapping):
        return None, None
    ref = given.get("_ref")
    row = {key: value for key, value in given.items() if key != "_ref"}
    return (row or None), (str(ref) if is_ref(ref) else None)


def row_digest(ref: str) -> str:
    """What names a dataset row in a reference to it: the row's own digest, which is the same
    in every version of the dataset that holds the row; else the reference whole."""
    found = _ROW_DIGEST.search(ref)
    return found.group(1) if found else ref


def exception_of(value: Any) -> tuple[str | None, str | None]:
    """The class and the words of a call's exception. Weave writes a JSON object in a string
    (``type``, ``message``, ``traceback``), and a stripped raw copy keeps its ``type`` alone;
    an exception written as plain text names its class at the start of its last line."""
    if isinstance(value, str) and value.strip():
        try:
            value = json.loads(value)
        except ValueError:
            found = _CLASS.match(value.strip().splitlines()[-1])
            return (found.group(1) if found else None), value
    if isinstance(value, Mapping):
        kind, said = value.get("type"), value.get("message")
        return (
            kind if isinstance(kind, str) and kind else None,
            said if isinstance(said, str) else None,
        )
    return None, None


def error_kind(value: Any) -> str | None:
    """The failure kind an exception's class or words say, as the source's own: a timeout, a
    rate limit or a context overflow; else None, and the taxonomy's rules decide."""
    kind, said = exception_of(value)
    line = f"{kind or ''}: {said or ''}"
    if TIMEOUT.search(line):
        return "timeout"
    if RATE_LIMIT.search(line):
        return "rate_limit"
    if CONTEXT.search(line):
        return "context_overflow"
    return None


# ---------- one call ----------

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def nanoseconds(stamp: Any) -> int | None:
    """A Weave time (ISO 8601, to the microsecond) as nanoseconds since the epoch, or None.
    A time with no zone is UTC, as Weave writes them."""
    if not isinstance(stamp, str) or not stamp.strip():
        return None
    try:
        at = datetime.fromisoformat(stamp.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    gone = at - _EPOCH
    micro = (gone.days * 86_400 + gone.seconds) * 1_000_000 + gone.microseconds
    return micro * 1000 if micro >= 0 else None


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


def _elapsed(start: int | None, end: int | None) -> float | None:
    return None if start is None or end is None or end < start else (end - start) / 1e9


@dataclass(frozen=True)
class _Call:
    """One call, with the shape it was read from and the file it is in."""

    shape: str
    file: str
    doc: Mapping[str, Any]

    @property
    def id(self) -> str:
        return str(self.doc.get("id"))

    @property
    def parent(self) -> str | None:
        held = self.doc.get("parent_id")
        return str(held) if held else None

    @property
    def op(self) -> str:
        return op_name(self.doc.get("op_name"))

    @property
    def start(self) -> int | None:
        return nanoseconds(self.doc.get("started_at"))

    @property
    def end(self) -> int | None:
        return nanoseconds(self.doc.get("ended_at"))

    @property
    def order(self) -> tuple[int, str]:
        """What orders calls: their start, then their id, which Weave makes in time order."""
        return (self.start or 0, self.id)

    @property
    def summary(self) -> Mapping[str, Any]:
        """What Weave itself says of the call: its status, its costs, its feedback."""
        return _mapping(_mapping(self.doc.get("summary")).get("weave"))

    @property
    def status(self) -> str:
        return str(self.summary.get("status") or "")

    @property
    def raised(self) -> bool:
        """Whether the call itself raised: its status says ``error``. A call that only holds
        one that raised says ``descendant_error``, which is not this."""
        return self.status == "error" or bool(self.doc.get("exception"))

    @property
    def kind(self) -> str:
        """What the call is marked as (``llm``, ``tool``), or nothing."""
        held = _mapping(_mapping(self.doc.get("attributes")).get("weave")).get("kind")
        return held.lower() if isinstance(held, str) else ""

    @property
    def inputs(self) -> Mapping[str, Any]:
        return _mapping(self.doc.get("inputs"))

    @property
    def output(self) -> Mapping[str, Any]:
        return _mapping(self.doc.get("output"))

    @property
    def error_class(self) -> str | None:
        return exception_of(self.doc.get("exception"))[0]

    def duration(self) -> float | None:
        return _elapsed(self.start, self.end)


# ---------- the files ----------


@dataclass
class _File:
    """One file read: its digest and the calls it holds."""

    path: Path
    sha256: str
    calls: list[_Call] = field(default_factory=list)


def _not_an_export(path: Path, what: str) -> Refusal:
    return Refusal(f"{path} is not a Weave export: {what}")


def _load(path: Path) -> _File:
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise Refusal(f"{path} could not be read: {why(e)}") from e
    name = path.name.lower()
    if not name.endswith((".jsonl", ".json", ".csv", ".tsv")):
        raise Refusal(
            f"{path} is not a file the Weave reader reads: it reads .jsonl, .json, .csv and .tsv"
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise _not_an_export(path, "it is not UTF-8 text") from None
    held = _File(path, hashlib.sha256(raw).hexdigest())
    if name.endswith(".jsonl"):
        # an empty answer is the last page of a paged pull: it holds no call and is no fault
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
            except ValueError:
                raise _not_an_export(path, f"line {number} is not JSON") from None
            _take(held, doc, f"line {number}")
        return held
    if not text.strip():
        raise _not_an_export(path, "it is empty")
    if name.endswith(".json"):
        try:
            doc = json.loads(text)
        except ValueError:
            raise _not_an_export(path, "it is not JSON") from None
        if not isinstance(doc, list):
            raise _not_an_export(path, "it is not a list of calls")
        for number, item in enumerate(doc, start=1):
            _take(held, item, f"item {number}")
        return held
    _load_table(held, text, "\t" if name.endswith(".tsv") else ",")
    return held


def _is_call(doc: Any) -> bool:
    """Whether an object is a call: it names itself, its op, its trace and its start."""
    return (
        isinstance(doc, Mapping)
        and bool(doc.get("id"))
        and isinstance(doc.get("op_name"), str)
        and "trace_id" in doc
        and "started_at" in doc
    )


def _take(held: _File, doc: Any, where: str) -> None:
    if not isinstance(doc, Mapping):
        raise _not_an_export(held.path, f"{where} is not a JSON object")
    if not _is_call(doc):
        raise _not_an_export(held.path, f"{where} is not a call")
    held.calls.append(_Call("call", held.path.name, doc))


def _load_table(held: _File, text: str, delimiter: str) -> None:
    """The page's table, each row as the call it is."""
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
    columns = list(reader.fieldnames or ())
    lacking = [column for column in _TABLE_NEEDS if column not in columns]
    if lacking:
        raise Refusal(
            f"{held.path} is not the table a Weave Traces page downloads: it has no "
            f"{lacking[0]} column"
        )
    try:
        for row in reader:
            doc = _table_call(row)
            if not doc.get("id") or not doc.get("op_name"):
                raise Refusal(
                    f"{held.path} line {reader.line_num}: the row names no call (its id or "
                    "its op_name cell is empty)"
                )
            held.calls.append(_Call("table", held.path.name, doc))
    except csv.Error as e:
        raise Refusal(
            f"{held.path} line {reader.line_num} cannot be read as a table: {why(e)}"
        ) from e


def _cell(cell: str) -> Any:
    """A cell as the value the page wrote: ``True`` or ``False``, a number, else its text."""
    if cell in ("True", "true"):
        return True
    if cell in ("False", "false"):
        return False
    try:
        return int(cell)
    except ValueError:
        pass
    number = _finite(cell)
    return cell if number is None else number


def _put(into: dict[str, Any], path: Sequence[str], value: Any) -> None:
    """``value`` at ``path`` under ``into``, making the objects on the way."""
    for part in path[:-1]:
        held = into.get(part)
        if not isinstance(held, dict):
            held = into[part] = {}
        into = held
    into[path[-1]] = value


def _under_a_model(column: str, prefix: str, leaves: Sequence[str]) -> tuple[str, str] | None:
    """The model and the leaf a column of ``prefix`` names, told by the leaf it ends with: a
    model's name holds dots, so it cannot be cut at one."""
    rest = column[len(prefix) :]
    for leaf in leaves:
        if rest.endswith("." + leaf) and len(rest) > len(leaf) + 1:
            return rest[: -len(leaf) - 1], leaf
    return None


def _table_call(row: Mapping[str | None, Any]) -> dict[str, Any]:
    """A row of the page's table as the call it is: what its columns hold, in the form the
    service writes a call in. A cell that is empty holds nothing. The example's values stay
    the text the cells hold."""
    cells = {
        column: cell
        for column, cell in row.items()
        if isinstance(column, str) and isinstance(cell, str) and cell != ""
    }
    doc: dict[str, Any] = {key: cells.get(key) for key in _TABLE_KEYS}
    inputs: dict[str, Any] = {}
    example: dict[str, Any] = {}
    answer: dict[str, Any] = {}
    output: dict[str, Any] = {"output": None, "scores": {}}
    usage: dict[str, Any] = {}
    weave: dict[str, Any] = {}
    for column, cell in cells.items():
        if column in ("inputs.self", "inputs.model", "inputs.example"):
            inputs[column.split(".", 1)[1]] = cell
        elif column.startswith(_EXAMPLE):
            example[column[len(_EXAMPLE) :]] = cell
        elif column == "output.output":
            output["output"] = cell
        elif column.startswith(_ANSWER):
            answer[column[len(_ANSWER) :]] = cell
        elif column.startswith(_SCORE):
            _put(output["scores"], column[len(_SCORE) :].split("."), _cell(cell))
        elif column == "output.model_latency":
            output["model_latency"] = _finite(cell)
        elif column == "summary.weave.status":
            weave["status"] = cell
        elif column == _REACTION_COLUMN:
            weave["feedback"] = [{"feedback_type": REACTION, "payload": {"alias": cell}}]
        elif column.startswith(_USAGE):
            found = _under_a_model(column, _USAGE, _USAGE_LEAVES)
            if found is not None:
                _put(usage, [found[0], *found[1].split(".")], _cell(cell))
        elif column.startswith(_COST):
            found = _under_a_model(column, _COST, _COSTS)
            if found is not None:
                _put(weave, ["costs", *found], _finite(cell))
    if example:
        # a reference the table does carry stands where the service writes it: in the row
        if is_ref(inputs.get("example")):
            example.setdefault("_ref", inputs["example"])
        inputs["example"] = example
    if answer and output["output"] is None:
        output["output"] = answer
    summary: dict[str, Any] = {"weave": weave}
    if usage:
        summary["usage"] = usage
    doc.update(inputs=inputs, output=output, summary=summary, attributes={})
    return doc


# ---------- scores and feedback ----------


def leaves(value: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    """Every value that is no object under ``value``, with the keys that lead to it."""
    if isinstance(value, Mapping):
        for key, held in value.items():
            yield from leaves(held, (*path, str(key)))
    else:
        yield path, value


def is_score(value: Any) -> bool:
    """Whether a scorer's value is a score: true or false, or a finite number. Text is not."""
    return isinstance(value, bool) or _number(value) is not None


@dataclass(frozen=True)
class _Scores:
    """A row's scores by name, the dotted path each may also be asked by, and the names whose
    value was true or false."""

    held: Mapping[str, float]
    paths: Mapping[str, str]
    booleans: frozenset[str]

    def named(self, key: str) -> str | None:
        """The name of the score ``key`` asks for, by its name or by its dotted path."""
        return key if key in self.held else self.paths.get(key)


def scores_of(doc: Mapping[str, Any]) -> _Scores:
    """The scores of a row: every value its scorers gave under ``output.scores`` that is a
    number or true or false. A score is named by its dotted path, and by its scorer alone
    where the value sits under the scorer's own name (``exact.exact`` is ``exact``). The name
    never depends on how many values the scorer gave, so a scorer whose text was left out of
    a raw copy still names its score as it did."""
    held: dict[str, float] = {}
    paths: dict[str, str] = {}
    booleans: set[str] = set()
    for scorer, out in _mapping(_mapping(doc.get("output")).get("scores")).items():
        for path, value in leaves(out, (str(scorer),)):
            if not is_score(value):
                continue
            dotted = ".".join(path)
            name = str(scorer) if path[1:] in ((), (str(scorer),)) else dotted
            held[name] = float(value)
            paths[dotted] = name
            if isinstance(value, bool):
                booleans.add(name)
    return _Scores(held, paths, frozenset(booleans))


def _reactions(call: _Call) -> dict[str, str]:
    """The reactions on the call, as the row's feedback: their names, joined by a comma in
    the order they were made. A note's text and an annotation's value are never read."""
    listed = call.summary.get("feedback")
    if not isinstance(listed, list):
        return {}
    made: list[tuple[str, int, str]] = []
    for number, entry in enumerate(listed):
        if not isinstance(entry, Mapping) or entry.get("feedback_type") != REACTION:
            continue
        payload = _mapping(entry.get("payload"))
        word = payload.get("alias") or payload.get("emoji")
        if isinstance(word, str) and word:
            made.append((str(entry.get("created_at") or ""), number, word))
    made.sort()
    return {"reaction": ",".join(word for _, _, word in made)} if made else {}


# ---------- the case and the outcome ----------


@dataclass(frozen=True)
class _How:
    """How the rows are read: what the flags said."""

    case_from: str
    outcome_from: str
    cut: Cut | None
    evaluation: str | None

    def case(self, doc: Mapping[str, Any]) -> str | None:
        """The row's case, or None when the call holds none."""
        if self.case_from == "none":
            return UNPAIRED
        if self.case_from == "input":
            return _keyed_input(doc)
        row, ref = example_of(doc)
        if self.case_from == "example":
            return case_id(row_digest(ref)) if ref else None
        value = None if row is None else row.get(_key(self.case_from))
        if value is None or value == "":
            return None
        return case_id(value if isinstance(value, str) else json.dumps(value))


def _how(ns: argparse.Namespace) -> _How:
    cut = None
    if ns.cut is not None:
        cut = Cut(float(ns.cut), "below" if ns.below else "above")
    named = getattr(ns, "evaluation", None)
    return _How(
        case_from=str(ns.case_from),
        outcome_from=str(ns.outcome_from),
        cut=cut,
        evaluation=None if named is None else str(named),
    )


def _keyed_input(doc: Mapping[str, Any]) -> str | None:
    """The key of the row's input: the one a pull stamped before it left the row out, else
    the key of the dataset row where the file holds it."""
    stamped = doc.get(INPUT_KEY)
    if isinstance(stamped, str) and stamped:
        return stamped
    row, _ = example_of(doc)
    return None if row is None else input_key(row)


def _result(outcome: str | None, errored: bool) -> str | None:
    """The normalised result: a row with no outcome is censored when its case errored, and
    unscored (None) otherwise, which a verdicts file may still fill."""
    if outcome == MET:
        return "pass"
    if outcome == MISSED:
        return "fail"
    return "censored" if errored else None


# ---------- one call, one row ----------


def _model_call(row: _Call, under: Sequence[_Call]) -> _Call | None:
    """The model's call among the calls under a row: the one made on the row's model (a
    model object's method, or the function that is the model), else the first that started,
    since a case's model runs before its scorers. The others are the scorers' calls."""
    model = row.inputs.get("model")
    if model:
        for call in under:
            if call.inputs.get("self") == model or call.doc.get("op_name") == model:
                return call
    return under[0] if under else None


def _attempts(calls: Sequence[_Call]) -> tuple[list[int], int]:
    """Each call's attempt, and the retries among the calls. Weave records no retry, so a
    call that follows a failed call of the same op under the same parent is the next attempt
    of it, and one retry."""
    last: dict[tuple[str | None, str], tuple[bool, int]] = {}
    attempts: list[int] = []
    retries = 0
    for call in calls:
        at = (call.parent, call.op)
        attempt = 1
        if at in last and last[at][0]:
            attempt = last[at][1] + 1
            retries += 1
        last[at] = (call.raised, attempt)
        attempts.append(attempt)
    return attempts, retries


def _loops(calls: Sequence[ToolCallRecord]) -> bool:
    """Whether three calls in a row went to one tool."""
    run = 0
    for i, call in enumerate(calls):
        run = run + 1 if i and calls[i - 1].name == call.name else 1
        if run >= 3:
            return True
    return False


def _usage(call: _Call) -> tuple[dict[str, int | None], int | None, list[str]]:
    """The call's token counts, summed over the models its summary names; the requests it
    counts; and the models' names. A count no model gives is None, not zero."""
    held = _mapping(_mapping(call.doc.get("summary")).get("usage"))
    tokens: dict[str, int | None] = dict.fromkeys((*_TOKENS, *_TOKEN_DETAILS))
    requests: int | None = None
    models: list[str] = []

    def add(signal: str, found: int | None) -> None:
        if found is not None:
            tokens[signal] = (tokens[signal] or 0) + found

    for model, used in held.items():
        if not isinstance(used, Mapping):
            continue
        models.append(str(model))
        for signal, keys in _TOKENS.items():
            named = (_count(used.get(key)) for key in keys)
            add(signal, next((n for n in named if n is not None), None))
        for signal, (outer, inner) in _TOKEN_DETAILS.items():
            add(signal, _count(_mapping(used.get(outer)).get(inner)))
        asked = _count(used.get("requests"))
        if asked is not None:
            requests = (requests or 0) + asked
    return tokens, requests, models


def _cost(call: _Call) -> float | None:
    """The call's cost in US dollars: its prompt's and its completion's, summed over its
    models. None where the export carries no figure, which is not a cost of zero."""
    held = call.summary.get("costs")
    if not isinstance(held, Mapping):
        return None
    parts = [
        number
        for cost in held.values()
        if isinstance(cost, Mapping)
        for number in (_number(cost.get(key)) for key in _COSTS)
        if number is not None
    ]
    return math.fsum(parts) if parts else None


def span_id(call_id: str) -> str:
    """A call's id as a stored span's: its hexadecimal digits, without the dashes Weave
    writes between them. The store keeps hexadecimal ids, and would read the dashed form as
    something else."""
    return call_id.replace("-", "").lower()


def _attribute(key: str, value: Any) -> dict[str, Any]:
    """One attribute as OTLP lists it, which is the form the writer's spans take."""
    held = {"intValue": value} if isinstance(value, int) else {"stringValue": value}
    return {"key": key, "value": held}


def _span(call: _Call, parent: str | None) -> dict[str, Any] | None:
    """The call as one stored span: its id, its parent, its kind, a model call's model and
    token counts, and its exception's class. No text of the call."""
    start = call.start
    if start is None:
        return None
    attributes: dict[str, Any] = {"source.type": call.kind or "op"}
    if call.kind in _OPERATION:
        attributes["gen_ai.operation.name"] = _OPERATION[call.kind]
    if call.kind == "llm":
        tokens, _, models = _usage(call)
        if len(models) == 1:
            attributes["llm.model_name"] = models[0]
        for name in ("input_tokens", "output_tokens"):
            if tokens[name] is not None:
                attributes[f"gen_ai.usage.{name}"] = tokens[name]
    failed = call.error_class
    if call.raised and failed is not None:
        attributes["error.type"] = failed
    return {
        "spanId": span_id(call.id),
        "parentSpanId": None if parent is None else span_id(parent),
        "name": call.op,
        "startTimeUnixNano": start,
        "endTimeUnixNano": call.end,
        "attributes": [_attribute(k, v) for k, v in attributes.items()],
        "status": {"code": 2 if call.raised else 1},
    }


@dataclass
class _Structure:
    """What the calls under a row give: the signals of its structure, the stored spans, the
    tool calls, and the step that failed."""

    signals: dict[str, Any] = field(default_factory=dict)
    spans: tuple[dict[str, Any], ...] | None = None
    calls: tuple[ToolCallRecord, ...] | None = None
    failed: _Call | None = None


def _structure(row: _Call, children: Mapping[str, Sequence[_Call]]) -> _Structure:
    """The row's structure, read from the calls under it where the files hold them: the
    model's call and everything under that. The scorers' calls are left out of all of it. A
    file that holds the rows alone gives nothing here, which is "not recorded"."""
    model = _model_call(row, sorted(children.get(row.id, ()), key=lambda c: c.order))
    if model is None:
        return _Structure()
    work: list[_Call] = []
    seen: set[str] = set()
    waiting = [model]
    while waiting:
        call = waiting.pop()
        if call.id in seen:
            continue
        seen.add(call.id)
        work.append(call)
        waiting.extend(children.get(call.id, ()))
    work.sort(key=lambda c: c.order)
    parents = {call.parent for call in work}
    steps = [call for call in work if call.id not in parents]
    _, retries = _attempts(work)
    tools = [call for call in work if call.kind == "tool"]
    attempts, _ = _attempts(tools)
    read = _Structure(
        {
            "steps": len(steps),
            "llm_calls": sum(1 for call in work if call.kind == "llm"),
            "retries": retries,
        },
        calls=tuple(
            ToolCallRecord(
                name=tool.op or "tool",
                status="error" if tool.raised else "ok",
                duration_s=tool.duration(),
                error_type=tool.error_class if tool.raised else None,
                attempt=attempt,
            )
            for tool, attempt in zip(tools, attempts, strict=True)
        ),
    )
    spans = [_span(row, None), *(_span(call, call.parent) for call in work)]
    read.spans = tuple(span for span in spans if span is not None)
    # the step that failed is the last step that raised; the model's call where no step did
    raised = [step for step in steps if step.raised]
    if raised:
        read.failed = raised[-1]
    elif model.raised:
        read.failed = model
    return read


def _length(doc: Mapping[str, Any], stamp: str, value: Any) -> int | None:
    """The length a pull stamped before it left the text out, else the text's own."""
    if stamp in doc:
        return _count(doc.get(stamp))
    return chars(value)


def _row(
    how: _How,
    call: _Call,
    children: Mapping[str, Sequence[_Call]],
    counts: Counter[str],
    inputs: dict[str, str],
) -> Row | None:
    """One ``predict_and_score`` call as a row."""
    doc = call.doc
    case = how.case(doc)
    if case is None:
        counts["no case"] += 1
        return None
    keyed = _keyed_input(doc)
    if keyed is not None:
        inputs.setdefault(case, keyed)
    scores = scores_of(doc)
    example, _ = example_of(doc)
    answer = call.output.get("output")
    input_chars = _length(doc, INPUT_CHARS, example)
    output_chars = _length(doc, OUTPUT_CHARS, answer)
    # the case errored when its own call raised, or when something under it raised and it
    # holds no output and no score; a stripped copy holds the output's length in its place,
    # and says so where the output was a reference, which has no length
    if OUTPUT_CHARS in doc:
        answered = output_chars is not None or doc.get(OUTPUT_REF) is True
    else:
        answered = answer is not None
    silent = not answered and not scores.held
    errored = call.raised or (call.status == "descendant_error" and silent)

    outcome: str | None = None
    reason: str | None = None
    score: float | None = None
    if how.outcome_from == "status":
        if call.end is None:
            reason = PENDING
        else:
            outcome = MISSED if errored else MET
    else:
        name = scores.named(_key(how.outcome_from))
        if name is None or how.cut is None:
            reason = NO_SCORE
        else:
            score = scores.held[name]
            outcome = how.cut.outcome(score)
            if name in scores.booleans:
                counts[_BOOLEANS] += 1
    result = _result(outcome, errored)

    tokens, requests, _ = _usage(call)
    sources: dict[str, str] = {}
    if any(value is not None for value in tokens.values()):
        sources["tokens_from"] = CALL_SUMMARY
    cost = _cost(call)
    if cost is not None:
        sources["cost_from"] = CALL_SUMMARY
    elif "tokens_from" in sources:
        counts[_NO_COST] += 1
    read = _structure(call, children)
    latency = _number(call.output.get("model_latency"))
    signals: dict[str, Any] = {
        **tokens,
        "cost_usd": cost,
        "wall_time_s": latency if latency is not None and latency >= 0 else call.duration(),
        "ttft_s": None,
        "input_chars": input_chars,
        "output_chars": output_chars,
        # the rows alone hold the count of model calls; the calls under a row say it themselves
        "llm_calls": requests,
        **read.signals,
    }
    kind = None
    if errored:
        failed = doc if read.failed is None else read.failed.doc
        signals["error_type"] = exception_of(failed.get("exception"))[0]
        if read.failed is not None:
            signals["error_span_kind"] = _STEP_KIND.get(read.failed.kind, "other")
        if result in ("fail", "censored"):
            stamped = failed.get(ERROR_KIND)
            kind = stamped if isinstance(stamped, str) else error_kind(failed.get("exception"))
    elif result == "fail" and read.calls is not None and _loops(read.calls):
        kind = "loop_detected"
    return Row(
        case,
        outcome,
        reason,
        score,
        read.spans,
        dict(sources),
        result=result,
        failure_kind=kind,
        scores=dict(scores.held),
        feedback=_reactions(call),
        tool_calls=read.calls,
        **signals,
    )


# ---------- the evaluations the files hold ----------


@dataclass(frozen=True)
class Evaluation:
    """One evaluation the files hold rows of: the id of its ``Evaluation.evaluate`` call, the
    name of its evaluation object, the name Weave shows for the call where the files hold
    it, and its rows in the order they started."""

    id: str
    name: str | None
    shown: str | None
    rows: tuple[_Call, ...]

    def said(self) -> str:
        """The evaluation as a refusal names it: its name, its call's id and its rows."""
        rows = "1 row" if len(self.rows) == 1 else f"{len(self.rows)} rows"
        return f"{self.name or 'an evaluation with no name'} ({self.id or 'no call id'}, {rows})"

    def answers_to(self, word: str) -> bool:
        return word in (self.id, self.name, self.shown)

    def carries_references(self) -> bool:
        """Whether every row carries the reference to its dataset row."""
        return all(example_of(row.doc)[1] for row in self.rows)


def evaluations(calls: Sequence[_Call]) -> list[Evaluation]:
    """The evaluations the calls hold rows of, in the order their first rows started. The
    rows of one evaluation are the ``predict_and_score`` calls under one parent."""
    by_id = {call.id: call for call in calls}
    found: dict[str, list[_Call]] = {}
    for row in sorted((c for c in calls if c.op == PREDICT_AND_SCORE), key=lambda c: c.order):
        found.setdefault(row.parent or "", []).append(row)
    out = []
    for parent, rows in found.items():
        over = by_id.get(parent)
        out.append(
            Evaluation(
                id=parent,
                name=object_name(rows[0].inputs.get("self")),
                shown=None if over is None else shown_name(over.doc),
                rows=tuple(rows),
            )
        )
    return out


def _chosen(how: _How, held: Sequence[Evaluation], files: Sequence[_File]) -> Evaluation | None:
    """The one evaluation to read, or None when the files hold no row."""
    each = ", ".join(evaluation.said() for evaluation in held)
    if how.evaluation is None:
        if len(held) > 1:
            raise Refusal(
                f"the files hold {len(held)} evaluations, {each}; one import reads one, since "
                "reading them together would pool versions: name it with --evaluation, by its "
                "name or by the id of its call"
            )
        return held[0] if held else None
    named = [evaluation for evaluation in held if evaluation.answers_to(how.evaluation)]
    if not named:
        where = " and ".join(dict.fromkeys(f.path.name for f in files))
        raise Refusal(
            f"{where} holds no evaluation named {how.evaluation}"
            + (f": it holds {each}" if held else ": it holds no evaluation's rows")
        )
    if len(named) > 1:
        ids = " and ".join(evaluation.id for evaluation in named)
        raise Refusal(
            f"the evaluation {how.evaluation} was run {len(named)} times in the files ({ids}), "
            "and one import reads one run of it: name it with --evaluation, by the id of its "
            "call"
        )
    return named[0]


def _check_case(how: _How, rows: Sequence[_Call]) -> None:
    """Refuse a case no row kept can give, naming another way to say it."""
    if not rows:
        return
    examples = [example_of(row.doc) for row in rows]
    if how.case_from == "example" and not any(ref for _, ref in examples):
        if all(row.shape == "table" for row in rows):
            raise Refusal(
                "--case-from example needs the reference to the dataset row, and the page's "
                "table leaves it out: name the case by a key of the row, such as --case-from "
                "example:id, or by --case-from input"
            )
        raise Refusal(
            "--case-from example needs the reference to the dataset row, and no row of the "
            "export holds one: name the case another way, such as --case-from input"
        )
    if _keyed(how.case_from, "example") and not any(row for row, _ in examples):
        raise Refusal(
            f"--case-from {how.case_from} needs the dataset row itself, and the export holds "
            "only the reference to it: name the case by --case-from example, or pull the "
            "evaluation with --keep-raw-text, which keeps the rows"
        )
    if how.case_from == "input" and all(_keyed_input(row.doc) is None for row in rows):
        raise Refusal(
            "--case-from input needs the dataset row itself, and the export holds only the "
            "reference to it: name the case by --case-from example"
        )


# ---------- the read ----------


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

        if _keyed(ns.case_from, "example") and not ns.keep_raw_text:
            # the raw copy leaves the dataset row out by default, and the read that follows
            # the pull needs it: refused here, before anything is asked or saved
            raise Refusal(
                f"--case-from {ns.case_from} reads the dataset row, which a pull's raw copy "
                "leaves out by default: add --keep-raw-text to keep the rows, or name the "
                "case by --case-from example. Nothing was asked of Weave"
            )
        pulled = pulling.pull_weave(
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
    if getattr(ns, "evaluation", None) is not None:
        words.append(option("--evaluation", str(ns.evaluation)))
    return words


def _once(calls: Sequence[_Call]) -> None:
    """Refuse a call given twice, naming it and where it is."""
    seen: dict[str, str] = {}
    for call in calls:
        if call.id in seen:
            both = (
                f"{call.file} twice"
                if seen[call.id] == call.file
                else f"both {seen[call.id]} and {call.file}"
            )
            raise Refusal(
                f"the call {call.id} is in {both}: give one export of each evaluation, since "
                "two would count it twice"
            )
        seen[call.id] = call.file


def _read(ns: argparse.Namespace, files: Sequence[_File]) -> Run:
    how = _how(ns)
    recorded = tuple({"name": held.path.name, "sha256": held.sha256} for held in files)
    calls = [call for held in files for call in held.calls]
    _once(calls)
    held = evaluations(calls)
    counts: Counter[str] = Counter()
    counts["calls"] = len(calls)
    counts["predict_and_score calls"] = sum(len(evaluation.rows) for evaluation in held)
    if calls and not held and all(c.op == EVALUATE and c.parent is None for c in calls):
        # one row an evaluation, with totals and no case: only this is refused. A page of an
        # answer that holds no row is read to no rows, since a folder's files are each read
        # alone to check that they are one run
        said = "1 Evaluation.evaluate call" if len(calls) == 1 else (
            f"{len(calls)} Evaluation.evaluate calls"
        )
        raise Refusal(
            f"{files[0].path} holds {said} and none of the cases: it is one row an "
            "evaluation, as the Traces page gives with no filter. Filter the page to the op "
            "Evaluation.predict_and_score and download again, or pull the evaluation with "
            "weave:ENTITY/PROJECT/EVALUATION"
        )
    chosen = _chosen(how, held, files)
    picked = () if chosen is None else chosen.rows
    counts["selected"] = len(picked)
    _check_case(how, picked)
    children: dict[str, list[_Call]] = {}
    for call in calls:
        if call.parent is not None:
            children.setdefault(call.parent, []).append(call)
    inputs: dict[str, str] = {}
    rows = [row for row in (_row(how, call, children, counts, inputs) for call in picked) if row]
    # the first row's start: the evaluation's own call started a little earlier, and only the
    # service's answers hold it, so reading it would make the exports disagree
    starts = [start for start in (call.start for call in picked) if start is not None]
    if starts:
        started, started_from = _instant(min(starts)), "earliest span"
    else:
        started, started_from = _file_time(files[0].path), "file time"
    declared: dict[str, Any] = {"case_from": how.case_from, "outcome_from": how.outcome_from}
    if how.cut is not None:
        declared["cut"] = how.cut.cut
        declared["side"] = how.cut.side
    if how.evaluation is not None:
        declared["evaluation"] = how.evaluation
    declared["shapes"] = list(dict.fromkeys(call.shape for call in calls))
    shown = {label: counts[label] for label in _COUNTS}
    if counts[_BOOLEANS]:
        shown[_BOOLEANS] = counts[_BOOLEANS]
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


# ---------- what a file holds, for a listing ----------


@dataclass(frozen=True)
class FoundRun:
    """One evaluation a found file holds rows of: the name that picks it out where the file
    holds more than one (else None), and a way to name its cases that every row can give."""

    evaluation: str | None
    case_from: str


def found_runs(path: Path | str) -> list[FoundRun]:
    """The runs a file would import as: one for each evaluation it holds rows of. The case is
    ``example`` where every row carries the reference to its dataset row, else ``input``,
    which the page's table can give. A file with no row, such as the Traces page's view of
    evaluations alone, gives none. It never raises."""
    try:
        held = evaluations(_load(Path(path)).calls)
    except Exception:
        return []
    names = Counter(evaluation.name for evaluation in held)
    return [
        FoundRun(
            # by its name, or by its call's id where it has none or shares it with another
            evaluation=None
            if len(held) == 1
            else evaluation.name
            if evaluation.name and names[evaluation.name] == 1
            else evaluation.id,
            case_from="example" if evaluation.carries_references() else "input",
        )
        for evaluation in held
    ]


# ---------- the detector ----------

_WHOLE_FILE_MAX = 64 * 1024 * 1024


def _first_row(found: Path) -> Any:
    """The first call of a ``.json`` or ``.jsonl`` file, or None."""
    if found.name.lower().endswith(".jsonl"):
        with open(found, "rb") as f:
            for line in f:
                if line.strip():
                    return json.loads(line.decode("utf-8-sig"))
        return None
    if found.stat().st_size > _WHOLE_FILE_MAX:
        return None
    doc = json.loads(found.read_bytes().decode("utf-8-sig"))
    return doc[0] if isinstance(doc, list) and doc else None


def looks_like(path: Path | str) -> str | None:
    """One line describing ``path`` when it is a Weave export, else None; it never raises. A
    table is told by its header; a ``.json`` or ``.jsonl`` file by its first row, a call of a
    project whose op is a reference Weave wrote. The empty last page of a paged answer holds
    nothing to tell it by, and is no export here."""
    try:
        found = Path(path)
        name = found.name.lower()
        if not found.is_file():
            return None
        if name.endswith((".csv", ".tsv")):
            with open(found, encoding="utf-8-sig", newline="") as f:
                header = next(csv.reader(f, delimiter="\t" if name.endswith(".tsv") else ","), [])
            if all(column in header for column in _TABLE_NEEDS):
                return "a W&B Weave Traces table, as its page downloads it"
            return None
        if not name.endswith((".json", ".jsonl")):
            return None
        doc = _first_row(found)
        if _is_call(doc) and is_ref(doc.get("op_name")) and "project_id" in doc:
            return "W&B Weave calls, as its service returns them and its Traces page downloads them"
        return None
    except Exception:
        return None
