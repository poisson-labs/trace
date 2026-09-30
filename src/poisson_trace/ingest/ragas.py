"""Ragas's per-row score tables, saved as CSV, JSON Lines, JSON or Parquet.

Ragas writes no result file of its own. A team saves the table ``to_pandas()`` gives, or has an
``@experiment`` file whose columns are whatever its function returned, so this reader takes a
table and not a Ragas format: ``.csv``, ``.jsonl``, ``.json`` (a list of objects), each also as
``.gz``, or ``.parquet``, told by the file's extension and by nothing else. One import reads
one score column at a cut the user declares, and one column that identifies the case. No
value of any other column is kept, and nothing here imports Ragas.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from poisson_trace.ingest.cut import Cut
from poisson_trace.ingest.rows import Refusal, Row, Run, case_id

FORMATS: tuple[str, ...] = ("csv", "jsonl", "json", "parquet")

TOOL = "ragas"
NO_SCORE = "no score"
_GZIPPED = FORMATS[:3]  # .gz is read on these
_TAKES = ".csv, .jsonl and .json, each also as .gz, and .parquet"
_SAYS = {"csv": "CSV", "jsonl": "JSON Lines", "json": "JSON", "parquet": "Parquet"}
# a number as a table writes one: a sign, digits with or without a point, an exponent
_NUMBER = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
# the csv module's own limit on a cell is 131,072 characters; a context cell can be longer
_CELL_LIMIT = 2**31 - 1

# one table row as the reader keeps it: the score cell and the case cell, None where absent
_Pair = tuple[Any, Any]


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--metric", required=True, metavar="COLUMN", help="the column that holds the score"
    )
    parser.add_argument(
        "--cut",
        required=True,
        metavar="X",
        help="the cut, a number, with its side; a Ragas table records no threshold",
    )
    parser.add_argument("--below", action="store_true", help="a score under the cut missed it")
    parser.add_argument("--above", action="store_true", help="a score over the cut missed it")
    parser.add_argument(
        "--case-column",
        required=True,
        metavar="COLUMN",
        help="the column that identifies a case across the two versions",
    )


def _number(text: str) -> float:
    """The number the text spells, or NaN when it spells none."""
    text = text.strip()
    return float(text) if _NUMBER.fullmatch(text) else math.nan


def _cut(ns: argparse.Namespace) -> Cut:
    value = _number(str(ns.cut))
    if not math.isfinite(value):
        raise Refusal(
            f"--cut takes a number, not {ns.cut}; a Ragas table records no threshold, so the "
            "cut is yours to declare"
        )
    if ns.below == ns.above:
        raise Refusal(
            f"--cut {ns.cut} needs exactly one side: --below if a score under it missed, "
            "--above if a score over it missed"
        )
    return Cut(value, "below" if ns.below else "above")


def _format(path: Path) -> tuple[str, bool]:
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


def _bytes(path: Path) -> tuple[bytes, float]:
    """The file's bytes and its modification time."""
    try:
        return path.read_bytes(), path.stat().st_mtime
    except OSError as e:
        raise Refusal(f"{path} could not be read: {e.strerror or e}") from e


def _not_a_table(path: Path, fmt: str, why: str) -> Refusal:
    return Refusal(f"{path} is not a {_SAYS[fmt]} table: {why}")


def _text(path: Path, fmt: str, body: bytes) -> str:
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise _not_a_table(path, fmt, "it is not UTF-8 text") from None


def _named(columns: tuple[str, ...]) -> str:
    return ", ".join(column if column else "(a column with no name)" for column in columns)


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


def _csv(path: Path, body: bytes, wanted: tuple[str, str]) -> list[_Pair]:
    """Every cell of a CSV is text. A line with nothing on it is not a row."""
    source = csv.reader(io.StringIO(_text(path, "csv", body), newline=""), strict=True)
    limit = csv.field_size_limit(_CELL_LIMIT)
    try:
        lines = [line for line in source if line]
    except csv.Error as e:
        raise _not_a_table(path, "csv", f"line {source.line_num}: {e}") from None
    finally:
        csv.field_size_limit(limit)
    if not lines:
        raise _not_a_table(path, "csv", "it has no header line")
    columns = tuple(lines[0])
    _columns_checked(path, columns, wanted)
    score_at, case_at = columns.index(wanted[0]), columns.index(wanted[1])
    pairs: list[_Pair] = []
    for n, cells in enumerate(lines[1:], start=1):
        if len(cells) > len(columns):
            raise _not_a_table(
                path, "csv", f"row {n} has {len(cells)} cells and the header names {len(columns)}"
            )
        pairs.append(
            (
                cells[score_at] if score_at < len(cells) else None,
                cells[case_at] if case_at < len(cells) else None,
            )
        )
    return pairs


def _objects(path: Path, fmt: str, rows: list[Any], wanted: tuple[str, str]) -> list[_Pair]:
    """The rows of a JSON table. A row need not carry every key another row has (an
    ``@experiment`` row is whatever the function returned), so the file's columns are the
    keys of all its rows, and a key a row lacks is an empty cell."""
    columns: dict[str, None] = {}
    for row in rows:
        columns.update(dict.fromkeys(row))
    if rows:
        _columns_checked(path, tuple(columns), wanted)
    return [(row.get(wanted[0]), row.get(wanted[1])) for row in rows]


def _jsonl(path: Path, body: bytes, wanted: tuple[str, str]) -> list[_Pair]:
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
    return _objects(path, "jsonl", rows, wanted)


def _json(path: Path, body: bytes, wanted: tuple[str, str]) -> list[_Pair]:
    try:
        rows = json.loads(_text(path, "json", body))
    except (ValueError, RecursionError):
        raise _not_a_table(path, "json", "it is not one JSON value") from None
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise _not_a_table(path, "json", "it is not a list of objects")
    return _objects(path, "json", rows, wanted)


def _parquet(path: Path, body: bytes, wanted: tuple[str, str]) -> list[_Pair]:
    """Only the two named columns are read from the file."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    try:
        file = pq.ParquetFile(pa.BufferReader(body))
        columns = tuple(str(name) for name in file.schema_arrow.names)
    except (pa.ArrowException, OSError, ValueError):
        raise _not_a_table(path, "parquet", "it could not be opened as one") from None
    _columns_checked(path, columns, wanted)
    try:
        table = file.read(columns=list(wanted))
        scores, cases = (table.column(column).to_pylist() for column in wanted)
    except (pa.ArrowException, OSError, ValueError, KeyError):
        raise _not_a_table(path, "parquet", "its columns could not be read") from None
    return list(zip(scores, cases, strict=True))


_READ = {"csv": _csv, "jsonl": _jsonl, "json": _json, "parquet": _parquet}


def _pairs(path: Path, fmt: str, gzipped: bool, raw: bytes, wanted: tuple[str, str]) -> list[_Pair]:
    body = raw
    if gzipped:
        try:
            body = gzip.decompress(raw)
        except (OSError, EOFError, ValueError):
            raise Refusal(f"{path} is named .gz and is not a gzip file") from None
    pairs = _READ[fmt](path, body, wanted)
    if not pairs:
        raise Refusal(f"{path} holds no row, so there is nothing to read from it")
    return pairs


def _score(cell: Any) -> float | None:
    """The cell as a number, or None when it holds none: an empty cell, a null, NaN, an
    infinity, a true or false, or text that does not spell a number. A missing score is never
    read as zero."""
    if isinstance(cell, str):
        value = _number(cell)
    elif isinstance(cell, bool) or not isinstance(cell, (int, float, Decimal)):
        return None
    else:
        try:
            value = float(cell)
        except (OverflowError, ValueError):
            return None
    return value if math.isfinite(value) else None


def _case(path: Path, n: int, column: str, cell: Any) -> str:
    """The case cell as the text the file holds. Text is kept as it is, so a CSV's ``007`` and
    ``7`` are two cases; a number is written as Python writes it."""
    if cell is None or cell == "" or (isinstance(cell, float) and math.isnan(cell)):
        raise Refusal(
            f"row {n} of {path} has no value in the column {column}, so nothing identifies its case"
        )
    if isinstance(cell, str):
        return case_id(cell)
    if isinstance(cell, bool) or not isinstance(cell, (int, float, Decimal)):
        raise Refusal(
            f"row {n} of {path} holds a value in the column {column} that is neither text "
            "nor a number, so it cannot identify a case"
        )
    return case_id(repr(cell) if isinstance(cell, float) else str(cell))


def _utc(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def read(ns: argparse.Namespace) -> Run:
    cut = _cut(ns)
    metric, case_column = str(ns.metric), str(ns.case_column)
    if metric == case_column:
        raise Refusal(
            f"--metric and --case-column both name the column {metric}; the score and the "
            "case are two columns"
        )
    paths = [Path(f) for f in ns.files]
    formats = [_format(path) for path in paths]
    detail = {"metric": metric, "cut": cut.cut, "side": cut.side}
    files, rows = [], []
    first_modified = 0.0
    for at, (path, (fmt, gzipped)) in enumerate(zip(paths, formats, strict=True)):
        raw, modified = _bytes(path)
        if at == 0:
            first_modified = modified
        files.append({"name": path.name, "sha256": hashlib.sha256(raw).hexdigest()})
        pairs = _pairs(path, fmt, gzipped, raw, (metric, case_column))
        for n, (score_cell, case_cell) in enumerate(pairs, start=1):
            case = _case(path, n, case_column, case_cell)
            score = _score(score_cell)
            if score is None:
                rows.append(Row(case, None, NO_SCORE, None, None, detail))
            else:
                rows.append(Row(case, cut.outcome(score), None, score, None, detail))
    return Run(
        name=ns.run,
        tool=TOOL,
        rows=tuple(rows),
        started=_utc(datetime.fromtimestamp(first_modified, UTC)),
        started_from="file time",
        declared={**detail, "case_column": case_column},
        files=tuple(files),
    )
