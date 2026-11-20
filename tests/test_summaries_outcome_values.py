"""TF15-P25: the table import lists every value
its outcome column holds, with its rows, so a value counted as a pass is seen. It meets
test_junit_table.py::test_tf3_13_no_value_of_another_column_is_kept[outcome], which keeps every
outcome value but the failure values out of the output before the listing this test holds.
"""

from __future__ import annotations

import re
from pathlib import Path

from conftest import FIXTURES, norm
from look_support import trace_import
from summaries_support import section


def _table_import(tmp_path: Path):  # type: ignore[no-untyped-def]
    return trace_import([
        "table", str(FIXTURES / "ingest" / "table" / "humaneval-a.csv"), "--store", str(tmp_path / "st"),
        "--run", "ha", "--case-column", "case", "--outcome-column", "outcome", "--failed", "failed_assertion",
        "--failed", "crashed",
    ])


def test_tf15_p25_the_table_import_lists_every_outcome_value(tmp_path: Path) -> None:
    """The table holds passed (9,158), failed_assertion (1,330) and crashed (8): each value is listed
    with its rows, so a value counted as a pass is seen."""
    out = _table_import(tmp_path).out
    body = norm(" ".join(section(out, "What was written")))
    for value, rows in (("passed", "9,158"), ("failed_assertion", "1,330"), ("crashed", "8")):
        assert re.search(rf'"{value}"\D*{rows}\b', body), (value, body)


