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
import hashlib
import math
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from poisson_trace.ingest import tabular
from poisson_trace.ingest.cut import Cut
from poisson_trace.ingest.rows import Refusal, Row, Run
from poisson_trace.ingest.tabular import METRICS

DESCRIPTION = """\
Read the per-row score table saved from Ragas (.csv, .jsonl, .json as a list of objects, each
also as .gz, or .parquet, told by the extension) and write one score column of it, at a cut you
declare, as one new run. Each row is one result for a case; rows that share the case column's
value are its repeats. No other column is kept. Nothing has a default but the start time.
"""
EXAMPLE = (
    "poisson-trace import ragas base-scores.jsonl --store trace-store --run base \\\n"
    "      --metric faithfulness --cut 0.5 --below --case-column question_id"
)

TOOL = "ragas"
NO_SCORE = "no score"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--metric",
        required=True,
        metavar="COLUMN",
        help="the column that holds the score (no default)",
    )
    parser.add_argument(
        "--cut",
        required=True,
        metavar="X",
        help="the cut, a number, with its side; a Ragas table records no threshold (no default)",
    )
    parser.add_argument("--below", action="store_true", help="a score under the cut missed it")
    parser.add_argument("--above", action="store_true", help="a score over the cut missed it")
    parser.add_argument(
        "--case-column",
        required=True,
        metavar="COLUMN",
        help="the column that identifies a case across the two versions (no default)",
    )


def _cut(ns: argparse.Namespace) -> Cut:
    value = tabular.number(str(ns.cut))
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


def _score(cell: Any) -> float | None:
    """The cell as a number, or None when it holds none: an empty cell, a null, NaN, an
    infinity, a true or false, or text that does not spell a number. A missing score is never
    read as zero."""
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
    """One line describing ``path`` when it looks like a table Ragas scored, else None; it
    never raises. A table is a ``.csv``, ``.jsonl`` or ``.json`` file (a ``.json`` file being a
    list of rows) with a column named like a Ragas metric within its first 4 KB: a CSV's header,
    or the keys of the first row of a JSON Lines file or a JSON list. A metric's word in a cell,
    or a column whose name only begins with one, is not a metric's column."""
    try:
        head = tabular.head_columns(path)
        if head is None:
            return None
        fmt, columns = head
        metrics = [c for c in dict.fromkeys(columns) if c in METRICS]
    except Exception:
        return None
    if not metrics:
        return None
    named = "metric" if len(metrics) == 1 else "metrics"
    return f"a {tabular.SAYS[fmt]} table with the Ragas {named} " + ", ".join(metrics)


def read(ns: argparse.Namespace) -> Run:
    cut = _cut(ns)
    metric, case_column = str(ns.metric), str(ns.case_column)
    if metric == case_column:
        raise Refusal(
            f"--metric and --case-column both name the column {metric}; the score and the "
            "case are two columns"
        )
    paths = [Path(f) for f in ns.files]
    formats = [tabular.format_of(path) for path in paths]
    detail = {"metric": metric, "cut": cut.cut, "side": cut.side}
    files, rows = [], []
    first_modified = 0.0
    for at, (path, (fmt, gzipped)) in enumerate(zip(paths, formats, strict=True)):
        raw, modified = tabular.read_bytes(path)
        if at == 0:
            first_modified = modified
        files.append({"name": path.name, "sha256": hashlib.sha256(raw).hexdigest()})
        pairs = tabular.pairs(path, fmt, gzipped, raw, (metric, case_column))
        for n, (score_cell, case_cell) in enumerate(pairs, start=1):
            case = tabular.case(path, n, case_column, case_cell)
            score = _score(score_cell)
            if score is None:
                rows.append(Row(case, None, NO_SCORE, None, None, detail))
            else:
                rows.append(Row(case, cut.outcome(score), None, score, None, detail))
    return Run(
        name=ns.run,
        tool=TOOL,
        rows=tuple(rows),
        started=tabular.utc(datetime.fromtimestamp(first_modified, UTC)),
        started_from="file time",
        declared={**detail, "case_column": case_column},
        files=tuple(files),
    )
