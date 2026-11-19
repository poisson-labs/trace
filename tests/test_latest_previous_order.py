"""latest and previous never order runs the wrong way.

They go by when each run started. Where the start times cannot order the runs a word ranks, the
word is refused and the runs to name are named: two runs that started at the same moment (two
files init imported together), or a run whose start is its file's modification time, which says
when the file was written or copied, not when the run ran. Runs whose starts are run times (a
start given with ``--started``, a JUnit suite's timestamp, Prove's own) are ordered by them.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from tf2_support import here, import_here, init_yes, scratch_home, work  # noqa: F401
from tf3_support import JUNIT, TABLE_A, TABLE_B, refusal

COLUMNS = ["--case-column", "case", "--outcome-column", "outcome", "--failed", "failed_assertion", "--failed", "crashed"]
COMPARE = ["--inputs", "all", "--max-mde", "0.02"]


def _verdict(folder: Path, argv: list[str]) -> str:
    result = here(folder, argv)
    assert result.code == 0, result.text
    return result.out.splitlines()[2]


def test_two_tables_init_imported_together_are_not_ordered_by_name(tmp_path: Path) -> None:
    folder = work(tmp_path)
    shutil.copy(TABLE_A, folder / "before.csv")
    shutil.copy(TABLE_B, folder / "after.csv")
    stamp = os.stat(folder / "before.csv").st_mtime
    os.utime(folder / "after.csv", (stamp, stamp))
    assert init_yes(folder, *COLUMNS).code == 0
    for argv in (["fix-check", "previous", "latest", *COMPARE], ["where", "latest"], ["changes", "previous", "latest"]):
        line = refusal(here(folder, argv))
        assert '"before"' in line and '"after"' in line, line
    # named, the pair reads as it is
    assert _verdict(folder, ["fix-check", "before", "after", *COMPARE]) == "# Poisson Trace · fix check · before (old) and after (new)"


def test_runs_whose_starts_are_file_times_are_not_ordered_by_them(tmp_path: Path) -> None:
    """The new file copied first: by file time it is the older, which it is not."""
    folder = work(tmp_path)
    shutil.copy(TABLE_B, folder / "after.csv")
    shutil.copy(TABLE_A, folder / "before.csv")
    os.utime(folder / "after.csv", (1_700_000_000, 1_700_000_000))
    os.utime(folder / "before.csv", (1_700_000_600, 1_700_000_600))
    assert init_yes(folder, *COLUMNS).code == 0
    line = refusal(here(folder, ["fix-check", "previous", "latest", *COMPARE]))
    assert '"before"' in line and '"after"' in line and "modification time" in line, line


def test_two_runs_given_the_same_start_are_not_ordered_by_their_names(tmp_path: Path) -> None:
    folder = work(tmp_path)
    for name, table in (("zz-old", TABLE_A), ("aa-new", TABLE_B)):
        argv = ["table", str(table), "--store", "st", "--run", name, *COLUMNS, "--started", "2026-09-05T18:54:07Z"]
        assert import_here(folder, argv).code == 0
    line = refusal(here(folder, ["fix-check", "previous", "latest", "--store", "st", "--event", "missed", *COMPARE]))
    assert '"zz-old"' in line and '"aa-new"' in line, line


def test_runs_with_run_times_are_ordered_by_them(tmp_path: Path) -> None:
    """Starts given with --started, and JUnit suites' timestamps, order the runs by them."""
    folder = work(tmp_path)
    for name, table, started in (("old", TABLE_A, "2026-09-05T18:54:07Z"), ("new", TABLE_B, "2026-09-05T19:50:09Z")):
        argv = ["table", str(table), "--store", "st", "--run", name, *COLUMNS, "--started", started]
        assert import_here(folder, argv).code == 0
    assert _verdict(folder, ["fix-check", "previous", "latest", "--store", "st", "--event", "missed", *COMPARE]) == (
        "# Poisson Trace · fix check · old (old) and new (new)"
    )
    reports = work(tmp_path, "reports")
    for which in ("a", "b"):
        shutil.copy(JUNIT / f"humaneval-{which}.xml", reports / f"humaneval-{which}.xml")
    assert init_yes(reports, "--case", "name").code == 0
    assert _verdict(reports, ["fix-check", "previous", "latest", "--inputs", "all", "--max-mde", "0.05"]) == (
        "# Poisson Trace · fix check · humaneval-a (old) and humaneval-b (new)"
    )
