"""Ragas's per-row score tables, saved as CSV, JSON Lines, JSON or Parquet.

Ragas writes no result file of its own. A team saves the table ``to_pandas()`` gives, or has an
``@experiment`` file whose columns are whatever its function returned, so this reader takes a
table and not a Ragas format: ``.csv``, ``.jsonl``, ``.json`` (a list of objects), each also as
``.gz``, or ``.parquet``, told by the file's extension and by nothing else. One import reads
one score column at a cut the user declares, and one column that identifies the case. Beyond
the result, every numeric column but the case column is a score in the row's ``scores``, the
length of ``user_input`` (or ``question``) and of ``response`` (or ``answer``) is measured and
the text dropped, and a column named exactly as a signal field is read into that signal. No value
of any other column is kept, and nothing here imports Ragas. A judge's NaN is a censored row with
no score, unclassified.
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
from poisson_trace.ingest.cut import MISSED, Cut
from poisson_trace.ingest.rows import Refusal, Row, Run
from poisson_trace.ingest.tabular import METRICS
from poisson_trace.ingest.verdicts import input_case

# the columns whose text is measured for the input's and the output's length, in the order tried
INPUT_COLUMNS: tuple[str, ...] = ("user_input", "question")
OUTPUT_COLUMNS: tuple[str, ...] = ("response", "answer")

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
    cost_field = (getattr(ns, "signals", None) or {}).get("cost_field")
    detail = {"metric": metric, "cut": cut.cut, "side": cut.side}
    files, rows = [], []
    inputs: dict[str, str] = {}
    first_modified = 0.0
    for at, (path, (fmt, gzipped)) in enumerate(zip(paths, formats, strict=True)):
        raw, modified = tabular.read_bytes(path)
        if at == 0:
            first_modified = modified
        files.append({"name": path.name, "sha256": hashlib.sha256(raw).hexdigest()})
        columns, lines = tabular.table(path, fmt, gzipped, raw, (metric, case_column))
        mapping = tabular.signal_columns(path, columns, cost_field, (case_column,))
        for n, line in enumerate(lines, start=1):
            case = tabular.case(path, n, case_column, line.get(case_column))
            score = _score(line.get(metric))
            signals = tabular.signal_cells(path, n, line, mapping)
            scores = {
                c: s
                for c, s in ((c, _score(line.get(c))) for c in columns)
                if s is not None and c != case_column and c not in mapping
            }
            for name, named in (("input_chars", INPUT_COLUMNS), ("output_chars", OUTPUT_COLUMNS)):
                text = next((line.get(c) for c in named if isinstance(line.get(c), str)), None)
                if text is not None and name not in signals:
                    signals[name] = len(text)
                if text is not None and name == "input_chars":
                    # the input's key alone is kept, for --verdicts; the first try's
                    inputs.setdefault(case, input_case(text))
            try:
                if score is None:
                    rows.append(Row(case, None, NO_SCORE, None, None, detail, result="censored",
                                    scores=scores, **signals))
                else:
                    outcome = cut.outcome(score)
                    rows.append(Row(case, outcome, None, score, None, detail,
                                    result="fail" if outcome == MISSED else "pass", scores=scores,
                                    **signals))
            except ValueError as e:
                raise Refusal(f"row {n} of {path} cannot be read: {e}") from None
    return Run(
        name=ns.run,
        tool=TOOL,
        rows=tuple(rows),
        started=tabular.utc(datetime.fromtimestamp(first_modified, UTC)),
        started_from="file time",
        declared={**detail, "case_column": case_column},
        files=tuple(files),
        inputs=inputs,
    )
