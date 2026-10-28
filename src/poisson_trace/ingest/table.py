"""Any table of results a tool or a script saved: CSV, JSON Lines, JSON or Parquet.

The file is a table and nothing more: ``.csv``, ``.jsonl``, ``.json`` (a list of objects), each
also as ``.gz``, or ``.parquet``, told by the file's extension. One column identifies the case,
and one other column gives each row's result, read one of two ways: an outcome column whose
cells the user names as failures, or a score column at a cut the user declares. No value of any
other column is kept, and of the result column only met or missed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from poisson_trace.ingest import tabular
from poisson_trace.ingest.cut import MET, MISSED, Cut
from poisson_trace.ingest.rows import Refusal, Row, Run

# the column names that make a table look like results to init's search: one of them, named
# exactly, within the file's first 4 KB
OUTCOME_COLUMNS: tuple[str, ...] = ("outcome", "passed", "result", "status")

DESCRIPTION = """\
Read a table of results (.csv, .jsonl, .json as a list of objects, each also as .gz, or
.parquet, told by the extension) and write it as one new run. Each row is one result for a
case; rows that share the case column's value are its repeats. A row's result is read one of
two ways: from an outcome column, where a cell equal to a --failed value missed and any other
cell met; or from a score column, at a cut you declare. An empty cell is a row with no outcome.
No other column is kept. Nothing has a default but the start time.
"""
EXAMPLE = (
    "poisson-trace import table results-old.csv --store trace-store --run old \\\n"
    "      --case-column case --outcome-column outcome --failed failed --failed crashed"
)

TOOL = "table"
NO_OUTCOME = "empty cell"
NO_SCORE = "no score"
_SIDES = "--cut, --below and --above"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--case-column",
        required=True,
        metavar="COLUMN",
        help="the column that identifies a case across the two versions (no default)",
    )
    parser.add_argument(
        "--outcome-column",
        metavar="COLUMN",
        help="the column that holds each row's outcome, read with --failed (no default)",
    )
    parser.add_argument(
        "--failed",
        action="append",
        metavar="VALUE",
        help="a cell of the outcome column that means the row failed, as the file writes it; "
        "repeatable (no default)",
    )
    parser.add_argument(
        "--score-column",
        metavar="COLUMN",
        help="the column that holds each row's score, read at --cut (no default)",
    )
    parser.add_argument(
        "--cut",
        metavar="X",
        help="for a score column: the cut, a number, with its side (no default)",
    )
    parser.add_argument("--below", action="store_true", help="a score under the cut missed it")
    parser.add_argument("--above", action="store_true", help="a score over the cut missed it")


def usage(ns: argparse.Namespace) -> str | None:
    """Why the command line does not say one way to read the result, or None: exactly one of
    the two forms, each with its own flags and without the other's."""
    by_outcome, by_score = ns.outcome_column is not None, ns.score_column is not None
    sided = ns.cut is not None or ns.below or ns.above
    if by_outcome and by_score:
        return "--outcome-column and --score-column are two ways to read a result; give one"
    if by_outcome:
        if sided:
            return f"{_SIDES} read a score column, and --outcome-column was given"
        if not ns.failed:
            return "--outcome-column needs --failed VALUE, a cell that means a failure"
        return None
    if by_score:
        if ns.failed:
            return "--failed reads an outcome column, and --score-column was given"
        if ns.cut is None:
            return "--score-column needs --cut X, with --below or --above"
        return None
    return (
        "give --outcome-column with --failed VALUE, or --score-column with --cut X and --below "
        "or --above"
    )


def _cut(ns: argparse.Namespace) -> Cut:
    value = tabular.number(str(ns.cut))
    if not math.isfinite(value):
        raise Refusal(f"--cut takes a number, not {ns.cut}")
    if ns.below == ns.above:
        raise Refusal(
            f"--cut {ns.cut} needs exactly one side: --below if a score under it missed, "
            "--above if a score over it missed"
        )
    return Cut(value, "below" if ns.below else "above")


def spelt(cell: Any) -> str | None:
    """The cell as the text it is compared by, or None when it is empty: text as written, a
    true or false or a number as JSON writes it (``true``, ``1``, ``0.5``), and anything else
    in JSON. An empty text, a null and NaN are empty."""
    if cell is None or (isinstance(cell, float) and math.isnan(cell)):
        return None
    if isinstance(cell, str):
        return cell if cell != "" else None
    if isinstance(cell, Decimal):
        return str(cell)
    return json.dumps(cell, ensure_ascii=False, default=str)


def _score(cell: Any) -> float | None:
    """The cell as a number, or None when it holds none, as the Ragas reader reads a score: a
    missing score is never read as zero."""
    if isinstance(cell, str):
        value = tabular.number(cell)
    elif isinstance(cell, bool) or not isinstance(cell, (int, float, Decimal)):
        return None
    else:
        try:
            value = float(cell)
        except (OverflowError, ValueError):
            return None
    return value if math.isfinite(value) else None


def looks_like(path: Path | str) -> str | None:
    """One line describing ``path`` when it looks like a table of results, else None; it never
    raises. A table is a ``.csv``, ``.jsonl`` or ``.json`` file (a ``.json`` file being a list of
    rows) with a column named exactly one of ``OUTCOME_COLUMNS`` within its first 4 KB, and no
    column named like a Ragas metric: such a table is the Ragas reader's, so that no file is
    read by two readers."""
    try:
        head = tabular.head_columns(path)
        if head is None:
            return None
        fmt, columns = head
        named = list(dict.fromkeys(columns))
        if any(c in tabular.METRICS for c in named):
            return None
        outcomes = [c for c in named if c in OUTCOME_COLUMNS]
    except Exception:
        return None
    if not outcomes:
        return None
    which = "column" if len(outcomes) == 1 else "columns"
    return f"a {tabular.SAYS[fmt]} table with the outcome {which} " + ", ".join(outcomes)


def read(ns: argparse.Namespace) -> Run:
    case_column = str(ns.case_column)
    by_score = ns.score_column is not None
    column = str(ns.score_column if by_score else ns.outcome_column)
    cut = _cut(ns) if by_score else None
    failed = tuple(dict.fromkeys(str(v) for v in ns.failed or ()))
    if column == case_column:
        flag = "--score-column" if by_score else "--outcome-column"
        raise Refusal(
            f"{flag} and --case-column both name the column {column}; the result and the case "
            "are two columns"
        )
    detail: dict[str, Any]
    if cut is not None:
        detail = {"score_column": column, "cut": cut.cut, "side": cut.side}
    else:
        detail = {"outcome_column": column, "failed": list(failed)}
    paths = [Path(f) for f in ns.files]
    formats = [tabular.format_of(path) for path in paths]
    files, rows = [], []
    matched: Counter[str] = Counter()
    cells: Counter[str] = Counter()
    first_modified = 0.0
    for at, (path, (fmt, gzipped)) in enumerate(zip(paths, formats, strict=True)):
        raw, modified = tabular.read_bytes(path)
        if at == 0:
            first_modified = modified
        files.append({"name": path.name, "sha256": hashlib.sha256(raw).hexdigest()})
        pairs = tabular.pairs(path, fmt, gzipped, raw, (column, case_column))
        for n, (cell, case_cell) in enumerate(pairs, start=1):
            case = tabular.case(path, n, case_column, case_cell)
            if cut is not None:
                score = _score(cell)
                if score is None:
                    rows.append(Row(case, None, NO_SCORE, None, None, detail))
                else:
                    rows.append(Row(case, cut.outcome(score), None, score, None, detail))
                continue
            text = spelt(cell)
            if text is not None:
                cells[text] += 1
            if text is None:
                rows.append(Row(case, None, NO_OUTCOME, None, None, detail))
            elif text in failed:
                matched[text] += 1
                rows.append(Row(case, MISSED, None, None, None, detail))
            else:
                rows.append(Row(case, MET, None, None, None, detail))
    # each failure value's rows, so that a value that matched nothing shows as 0
    counts = {
        f"rows whose {column} is {json.dumps(value, ensure_ascii=False)}": matched[value]
        for value in failed
    }
    return Run(
        name=ns.run,
        tool=TOOL,
        rows=tuple(rows),
        started=tabular.utc(datetime.fromtimestamp(first_modified, UTC)),
        started_from="file time",
        declared={"case_column": case_column, **detail},
        files=tuple(files),
        counts=counts,
        cells=dict(cells),
    )
