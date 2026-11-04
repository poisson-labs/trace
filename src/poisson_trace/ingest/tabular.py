"""Tables saved as CSV, JSON Lines, JSON or Parquet: what the Ragas and table readers share.

A table is told by its file's extension and by nothing else: ``.csv``, ``.jsonl``, ``.json`` (a
list of objects), each also as ``.gz``, or ``.parquet``. A reader names two columns, the one it
reads a result from and the one that identifies the case. Beyond those two, a column named
exactly as a signal field (``wall_time_s``, ``input_tokens``, ``failure_kind``, ...) is read into
that signal, and the column a config's ``[signals] cost_field`` names is read as the cost; an
empty cell is not recorded, a ``0`` is a recorded zero, and a cell that is not what the signal
takes is refused naming the column and the cell. No other column's value is kept.
``looks_like`` reads the columns a file's first 4 KB names, for init's search.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import math
import re
import zlib
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from poisson_trace.ingest.rows import (
    AMOUNT_SIGNALS,
    COUNT_SIGNALS,
    ERROR_SPAN_KINDS,
    FAILURE_KINDS,
    UNITS,
    Refusal,
    case_id,
)
from poisson_trace.look import why

FORMATS: tuple[str, ...] = ("csv", "jsonl", "json", "parquet")
# the columns Ragas names its metrics, which a table it scored carries
METRICS: tuple[str, ...] = (
    "faithfulness",
    "answer_relevancy",
    "answer_correctness",
    "context_precision",
    "context_recall",
    "id_based_context_precision",
    "id_based_context_recall",
)
# how much of a file looks_like reads to find the columns it names
HEAD = 4096
SAYS = {"csv": "CSV", "jsonl": "JSON Lines", "json": "JSON", "parquet": "Parquet"}

_GZIPPED = FORMATS[:3]  # .gz is read on these
_TAKES = ".csv, .jsonl and .json, each also as .gz, and .parquet"
# a number as a table writes one: a sign, digits with or without a point, an exponent
_NUMBER = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
# the csv module's own limit on a cell is 131,072 characters; a context cell can be longer
_CELL_LIMIT = 2**31 - 1

# one table row as a reader keeps it: the result cell and the case cell, None where absent
Pair = tuple[Any, Any]
# one table row whole, by column; a column a row lacks is an empty cell
Line = dict[str, Any]

#: The signal fields a column is read into when it is named exactly so: the counts, the
#: amounts and the three words (a failure kind, an error's type and the span kind it happened in).
TEXT_SIGNALS: tuple[str, ...] = ("failure_kind", "error_type", "error_span_kind")
SIGNAL_COLUMNS: tuple[str, ...] = (*COUNT_SIGNALS, *AMOUNT_SIGNALS, *TEXT_SIGNALS)


def number(text: str) -> float:
    """The number the text spells, or NaN when it spells none."""
    text = text.strip()
    return float(text) if _NUMBER.fullmatch(text) else math.nan


def format_of(path: Path) -> tuple[str, bool]:
    """The format the file's name declares, and whether the name says it is gzipped."""
    name = path.name.lower()
    gzipped = name.endswith(".gz")
    stem = name[: -len(".gz")] if gzipped else name
    fmt = stem.rpartition(".")[2] if "." in stem else ""
    if fmt not in FORMATS or (gzipped and fmt not in _GZIPPED):
        raise Refusal(
            f"{path} is not a file this reader takes: it reads {_TAKES}, and tells the format "
            "by the file's extension"
        )
    return fmt, gzipped


def read_bytes(path: Path) -> tuple[bytes, float]:
    """The file's bytes and its modification time."""
    try:
        return path.read_bytes(), path.stat().st_mtime
    except OSError as e:
        raise Refusal(f"{path} could not be read: {why(e)}") from e


def _not_a_table(path: Path, fmt: str, reason: str) -> Refusal:
    return Refusal(f"{path} is not a {SAYS[fmt]} table: {reason}")


def _text(path: Path, fmt: str, body: bytes) -> str:
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise _not_a_table(path, fmt, "it is not UTF-8 text") from None


def _named(columns: tuple[str, ...]) -> str:
    """The columns for a refusal; a name that is not valid Unicode is written with escapes."""
    names = (column.encode("utf-8", "backslashreplace").decode("utf-8") for column in columns)
    return ", ".join(name if name else "(a column with no name)" for name in names)


def _columns_checked(path: Path, columns: tuple[str, ...], wanted: tuple[str, str]) -> None:
    """Both named columns are in the file, each once; else the refusal lists the file's."""
    for column in wanted:
        if column not in columns:
            raise Refusal(
                f"{path} has no column named {column}; its columns are: {_named(columns) or 'none'}"
            )
        if columns.count(column) > 1:
            raise Refusal(
                f"{path} has {columns.count(column)} columns named {column}, so which one is "
                "meant cannot be told"
            )


Read = tuple[tuple[str, ...], list[Line]]


def _csv(path: Path, body: bytes, wanted: tuple[str, str]) -> Read:
    """Every cell of a CSV is text. A line with nothing on it, or with spaces alone, is not a
    row. A row shorter than the header leaves its last cells empty."""
    source = csv.reader(io.StringIO(_text(path, "csv", body), newline=""), strict=True)
    limit = csv.field_size_limit(_CELL_LIMIT)
    try:
        lines = [line for line in source if line and (len(line) > 1 or line[0].strip())]
    except csv.Error:
        raise _not_a_table(path, "csv", f"line {source.line_num} cannot be read as CSV") from None
    finally:
        csv.field_size_limit(limit)
    if not lines:
        raise _not_a_table(path, "csv", "it has no header line")
    columns = tuple(lines[0])
    _columns_checked(path, columns, wanted)
    rows: list[Line] = []
    for n, cells in enumerate(lines[1:], start=1):
        if len(cells) > len(columns):
            raise _not_a_table(
                path, "csv", f"row {n} has {len(cells)} cells and the header names {len(columns)}"
            )
        row: Line = {}
        for at, column in enumerate(columns):
            # a column named twice: the first keeps its cell, as the readers check it is one
            row.setdefault(column, cells[at] if at < len(cells) else None)
        rows.append(row)
    return columns, rows


def _objects(path: Path, rows: list[Any], wanted: tuple[str, str]) -> Read:
    """The rows of a JSON table. A row need not carry every key another row has (an
    ``@experiment`` row is whatever the function returned), so the file's columns are the
    keys of all its rows, and a key a row lacks is an empty cell."""
    columns: dict[str, None] = {}
    for row in rows:
        columns.update(dict.fromkeys(row))
    if rows:
        _columns_checked(path, tuple(columns), wanted)
    return tuple(columns), [dict(row) for row in rows]


def _jsonl(path: Path, body: bytes, wanted: tuple[str, str]) -> Read:
    """One object a line. A line that is not one refuses the file: a line cut short is a table
    cut short, and the rows that happened to parse say nothing about the rest."""
    rows: list[Any] = []
    # split on the line feed alone: a JSON string may hold other line separators as they are
    for n, line in enumerate(_text(path, "jsonl", body).split("\n"), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (ValueError, RecursionError):
            raise _not_a_table(path, "jsonl", f"line {n} is not JSON") from None
        if not isinstance(row, Mapping):
            raise _not_a_table(path, "jsonl", f"line {n} is not an object")
        rows.append(row)
    return _objects(path, rows, wanted)


def _json(path: Path, body: bytes, wanted: tuple[str, str]) -> Read:
    try:
        rows = json.loads(_text(path, "json", body))
    except (ValueError, RecursionError):
        raise _not_a_table(path, "json", "it is not one JSON value") from None
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise _not_a_table(path, "json", "it is not a list of objects")
    return _objects(path, rows, wanted)


def _parquet(path: Path, body: bytes, wanted: tuple[str, str]) -> Read:
    import pyarrow as pa
    import pyarrow.parquet as pq

    try:
        file = pq.ParquetFile(pa.BufferReader(body))
        columns = tuple(str(name) for name in file.schema_arrow.names)
    except (pa.ArrowException, OSError, ValueError):
        raise _not_a_table(path, "parquet", "it could not be opened as one") from None
    _columns_checked(path, columns, wanted)
    try:
        rows = file.read().to_pylist()
    except (pa.ArrowException, OSError, ValueError, KeyError, ArithmeticError):
        # ArithmeticError: a value Python cannot hold, such as a timestamp out of its range
        raise _not_a_table(path, "parquet", "its columns could not be read") from None
    return columns, [dict(row) for row in rows]


_READ = {"csv": _csv, "jsonl": _jsonl, "json": _json, "parquet": _parquet}


def _gunzipped(path: Path, raw: bytes) -> bytes:
    """The content of a file named ``.gz``. An empty file is not a gzip file, and a damaged
    one is refused like any file that is not what its name says."""
    try:
        if not raw:
            raise EOFError
        return gzip.decompress(raw)
    except (OSError, EOFError, ValueError, zlib.error):
        raise Refusal(f"{path} is named .gz and is not a gzip file that can be read") from None


def table(path: Path, fmt: str, gzipped: bool, raw: bytes, wanted: tuple[str, str]) -> Read:
    """The file's columns and every row whole, in the order the file holds them, the two
    columns ``wanted`` names (the result's and the case's) checked to be there once each. A file
    with no row is refused."""
    body = _gunzipped(path, raw) if gzipped else raw
    columns, rows = _READ[fmt](path, body, wanted)
    if not rows:
        raise Refusal(f"{path} holds no row, so there is nothing to read from it")
    return columns, rows


def pairs(path: Path, fmt: str, gzipped: bool, raw: bytes, wanted: tuple[str, str]) -> list[Pair]:
    """Each row's cells of the two columns ``wanted`` names, the result's and the case's, in
    the order the file holds the rows. A file with no row is refused."""
    _, rows = table(path, fmt, gzipped, raw, wanted)
    return [(row.get(wanted[0]), row.get(wanted[1])) for row in rows]


# ---------- the signal columns ----------


def signal_columns(
    path: Path, columns: tuple[str, ...], cost_field: str | None, apart: tuple[str, ...] = ()
) -> dict[str, str]:
    """Which column is read into which signal: every column named exactly as a signal field,
    and the column ``cost_field`` names into ``cost_usd``; none of ``apart`` (the two columns
    the reader reads its result and case from). A signal column named twice is refused."""
    found = {c: c for c in columns if c in SIGNAL_COLUMNS and c not in apart}
    if cost_field is not None:
        if cost_field not in columns:
            raise Refusal(
                f"{path} has no column named {cost_field}, which [signals] cost_field names; its "
                f"columns are: {_named(columns) or 'none'}"
            )
        if cost_field in apart:
            raise Refusal(
                f"[signals] cost_field names the column {cost_field}, which this import reads "
                "its result or case from"
            )
        found = {c: f for c, f in found.items() if f != "cost_usd"}
        found[cost_field] = "cost_usd"
    for column in found:
        if columns.count(column) > 1:
            raise Refusal(
                f"{path} has {columns.count(column)} columns named {column}, so which one is "
                "meant cannot be told"
            )
    return found


def empty(cell: Any) -> bool:
    """Whether a cell records nothing: an empty text, a null, or NaN."""
    return cell is None or cell == "" or (isinstance(cell, float) and math.isnan(cell))


def _amount_cell(cell: Any) -> float | None:
    """The cell as a finite number from zero, or None when it is not one."""
    if isinstance(cell, str):
        value = number(cell)
    elif isinstance(cell, bool) or not isinstance(cell, (int, float, Decimal)):
        return None
    else:
        try:
            value = float(cell)
        except (OverflowError, ValueError):
            return None
    return value if math.isfinite(value) and value >= 0.0 else None


def signal_cells(
    path: Path, n: int, row: Mapping[str, Any], mapping: Mapping[str, str]
) -> dict[str, Any]:
    """Row ``n``'s signal cells as ``Row`` keywords, by ``signal_columns``' mapping: an empty
    cell is left out (not recorded), a number is read as its signal's count or amount, a word
    as its signal's word. A cell that is not what the signal takes is refused naming the row,
    the column and the cell."""
    out: dict[str, Any] = {}
    for column, name in mapping.items():
        cell = row.get(column)
        if empty(cell):
            continue
        shown = cell if isinstance(cell, str) else json.dumps(cell, default=str)
        if name in COUNT_SIGNALS:
            value = _amount_cell(cell)
            if value is None or not value.is_integer():
                raise Refusal(
                    f"row {n} of {path} holds {shown!r} in the column {column}, which is not a "
                    f"whole number of {UNITS[name]}"
                )
            out[name] = int(value)
        elif name in AMOUNT_SIGNALS:
            value = _amount_cell(cell)
            if value is None:
                raise Refusal(
                    f"row {n} of {path} holds {shown!r} in the column {column}, which is not a "
                    f"number of {UNITS[name]}"
                )
            out[name] = value
        elif name == "failure_kind":
            if cell not in FAILURE_KINDS:
                raise Refusal(
                    f"row {n} of {path} holds {shown!r} in the column {column}, which is not one "
                    f"of the failure kinds: {', '.join(FAILURE_KINDS)}"
                )
            out[name] = cell
        elif name == "error_span_kind":
            if cell not in ERROR_SPAN_KINDS:
                raise Refusal(
                    f"row {n} of {path} holds {shown!r} in the column {column}, which is not a "
                    f"span kind: {', '.join(ERROR_SPAN_KINDS)}"
                )
            out[name] = cell
        else:
            out[name] = shown
    return out


def case(path: Path, n: int, column: str, cell: Any) -> str:
    """The case cell as the text the file holds. Text is kept as it is, so a CSV's ``007`` and
    ``7`` are two cases; a number is written as Python writes it."""
    if cell is None or cell == "" or (isinstance(cell, float) and math.isnan(cell)):
        raise Refusal(
            f"row {n} of {path} has no value in the column {column}, so nothing identifies its case"
        )
    if isinstance(cell, str):
        try:
            return case_id(cell)
        except UnicodeEncodeError:
            raise Refusal(
                f"row {n} of {path} holds text in the column {column} that is not valid "
                "Unicode (half of a surrogate pair), so it cannot identify a case"
            ) from None
    if isinstance(cell, bool) or not isinstance(cell, (int, float, Decimal)):
        raise Refusal(
            f"row {n} of {path} holds a value in the column {column} that is neither text "
            "nor a number, so it cannot identify a case"
        )
    return case_id(repr(cell) if isinstance(cell, float) else str(cell))


def utc(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- the columns a file's head names, for init's search ----------


def head_columns(path: Path | str) -> tuple[str, list[str]] | None:
    """The format and the columns a ``.csv``, ``.jsonl`` or ``.json`` file names within its
    first 4 KB: a CSV's header, or the keys of the first row of a JSON Lines file or a JSON
    list. None for any other file, or one whose head is not text. It may raise ``OSError``."""
    found = Path(path)
    fmt = found.name.rpartition(".")[2].lower() if "." in found.name else ""
    if fmt not in FORMATS[:3] or not found.is_file():
        return None
    with open(found, "rb") as table:
        head = table.read(HEAD + 1)
    whole = len(head) <= HEAD
    text = _head_text(head[:HEAD], whole)
    if text is None:
        return None
    return fmt, _csv_head(text, whole) if fmt == "csv" else _json_head(text, fmt == "json")


def _head_text(head: bytes, whole: bool) -> str | None:
    """The first bytes as text; a character cut in two at the end of the bytes read is left
    out. Bytes that are not UTF-8 are not a table."""
    for cut in range(1 if whole else 4):
        try:
            return head[: len(head) - cut].decode("utf-8-sig")
        except UnicodeDecodeError:
            continue
    return None


def _csv_head(text: str, whole: bool) -> list[str]:
    """A CSV's header, as far as the text holds it: a cell the text cuts short is not a column.
    A cell is the name as the readers read it, spaces and all."""
    line, newline, _ = text.partition("\n")
    cells = next(csv.reader([line.rstrip("\r")]), [])
    if not newline and not whole:
        cells = cells[:-1]
    return cells


def _json_head(text: str, listed: bool) -> list[str]:
    """The keys of the first row the text opens, as far as it holds them: of a JSON list's
    first object (``listed``), or of the first line of a JSON Lines file. A key whose value the
    text cuts short still counts, since its name is read whole."""
    keys: list[str] = []
    decoder = json.JSONDecoder()
    at = _space(text, 0)
    if listed:
        if text[at : at + 1] != "[":
            return []
        at = _space(text, at + 1)
    if text[at : at + 1] != "{":
        return []
    at = _space(text, at + 1)
    while at < len(text) and text[at] == '"':
        try:
            key, at = decoder.raw_decode(text, at)
        except ValueError:
            return keys
        at = _space(text, at)
        if text[at : at + 1] != ":":
            return keys
        keys.append(str(key))
        at = _skip_value(text, _space(text, at + 1))
        at = _space(text, at)
        if text[at : at + 1] != ",":
            return keys
        at = _space(text, at + 1)
    return keys


def _space(text: str, at: int) -> int:
    while at < len(text) and text[at] in " \t\r\n":
        at += 1
    return at


def _skip_value(text: str, at: int) -> int:
    """Where the JSON value that opens at ``at`` ends; the end of the text when it ends first."""
    depth = 0
    quoted = False
    escaped = False
    while at < len(text):
        ch = text[at]
        at += 1
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
                if depth == 0:
                    return at
        elif ch == '"':
            quoted = True
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth <= 0:
                return at if depth == 0 else at - 1
        elif ch == "," and depth == 0:
            return at - 1
    return at
