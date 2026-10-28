"""TF15-L1 to TF15-L8: the report lines that change with the summary (spec section 9.6, Taylor's
rulings of 2026-10-20, items 5 and 6): "started 0 s apart" on starts that are file times, where
each imported start came from (DeepEval's zone recorded), the control said by design, and "the
run's tally" for an imported run. The lines are pinned as section 9.6 writes them."""

from __future__ import annotations

import dataclasses
import gzip
import os
import re
import shutil
from pathlib import Path

from poisson_prove.store import Store

from conftest import FIXTURES, TAU2, TAU2_A, TAU2_B, where
from fixcheck_support import PILOT, TAU2_EVENTS, changes, fix_check, ok
from tf2_support import here, import_here, init_yes, scratch_home, work  # noqa: F401
from tf3_support import JUNIT, TABLE_A, TABLE_B

COLUMNS = ["--case-column", "case", "--outcome-column", "outcome", "--failed", "failed_assertion", "--failed", "crashed"]
ALL = ["--inputs", "all", "--max-mde", "0.05"]


def _lines(out: str) -> list[str]:
    return out.splitlines()


def _file_time_pair(tmp_path: Path) -> Path:
    folder = work(tmp_path)
    shutil.copy(TABLE_A, folder / "before.csv")
    shutil.copy(TABLE_B, folder / "after.csv")
    os.utime(folder / "before.csv", (1_700_000_000, 1_700_000_000))
    os.utime(folder / "after.csv", (1_700_000_600, 1_700_000_600))
    assert init_yes(folder, *COLUMNS).code == 0
    return folder


# ---------- 9.6 item 1: when the two ran ----------


def test_tf15_l1_both_starts_file_times(tmp_path: Path) -> None:
    folder = _file_time_pair(tmp_path)
    for argv in (["fix-check", "before", "after", *ALL], ["changes", "before", "after"]):
        result = here(folder, argv)
        assert result.code == 0, result.text
        lines = _lines(result.out)
        assert (
            "- when the two ran: not known; the starts of before and after are when their files were written or copied"
            in lines or
            "- when the two ran: not known; the starts of after and before are when their files were written or copied"
            in lines
        ), result.out
        assert not any(line.startswith("- the two runs started") for line in lines)


def test_tf15_l2_one_start_a_file_time(tmp_path: Path) -> None:
    folder = work(tmp_path)
    shutil.copy(TABLE_A, folder / "before.csv")
    assert import_here(folder, ["table", "before.csv", "--store", "st", "--run", "before", *COLUMNS]).code == 0
    assert import_here(folder, ["table", str(TABLE_B), "--store", "st", "--run", "after", *COLUMNS,
                                "--started", "2026-09-05T19:50:09Z"]).code == 0
    result = here(folder, ["fix-check", "before", "after", "--store", "st", "--event", "missed", *ALL])
    assert "- when the two ran: not known; the start of before is when its file was written or copied" in _lines(result.out), result.out


def test_tf15_l3_run_times_keep_the_gap() -> None:
    out = ok(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, "--inputs", "all", "--max-mde", "0.12")).out
    assert "- the two runs started 10 min apart" in _lines(out)


def test_tf15_l4_runs_marks_a_file_time(tmp_path: Path) -> None:
    folder = _file_time_pair(tmp_path)
    out = here(folder, ["runs"]).out
    rows = [line for line in _lines(out) if "before" in line or "after" in line]
    assert rows and all(re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} \(file\)", row) for row in rows), out
    assert "(file): the start is when the file was written or copied, not when the run ran" in _lines(out), out
    tau2 = here(folder, ["runs", "--store", str(TAU2)]).out
    assert "(file)" not in tau2


# ---------- 9.6 item 2: where each start came from ----------


def _started_bullets(out: str) -> list[str]:
    return [line for line in _lines(out) if line.startswith(("- old: ", "- new: ", "- A: ", "- B: "))]


def test_tf15_l5_each_imported_start_says_where_it_came_from(tmp_path: Path) -> None:
    folder = work(tmp_path)
    shutil.copy(TABLE_A, folder / "before.csv")
    assert import_here(folder, ["table", "before.csv", "--store", "st", "--run", "filed", *COLUMNS]).code == 0
    assert import_here(folder, ["table", str(TABLE_B), "--store", "st", "--run", "given", *COLUMNS,
                                "--started", "2026-09-05T19:50:09Z"]).code == 0
    for which in ("a", "b"):
        assert import_here(folder, ["junit", str(JUNIT / f"humaneval-{which}.xml"), "--store", "st", "--run", f"suite-{which}"]).code == 0
    (folder / "results").mkdir()
    for which, name in (("a", "test_run_20260905_185407.json"), ("b", "test_run_20260905_195009.json")):
        (folder / "results" / name).write_bytes(gzip.decompress((FIXTURES / "ingest" / "deepeval" / f"humaneval-{which}.json.gz").read_bytes()))
        assert import_here(folder, ["deepeval", f"results/{name}", "--store", "st", "--run", f"named-{which}", "--metric",
                                    "Tests Passed", "--cut", "recorded", "--case", "name"]).code == 0
    out = here(folder, ["fix-check", "filed", "given", "--store", "st", "--event", "missed", *ALL]).out
    old, new = _started_bullets(out)
    assert "(the file's modification time)" in old and "(given with --started)" in new, (old, new)
    out = here(folder, ["changes", "suite-a", "suite-b", "--store", "st", "--event", "missed"]).out
    a, b = _started_bullets(out)
    assert "(the report's earliest suite timestamp)" in a and "(the report's earliest suite timestamp)" in b, (a, b)
    out = here(folder, ["changes", "named-a", "named-b", "--store", "st", "--event", "missed"]).out
    a, b = _started_bullets(out)
    assert re.search(r"\(the time in the file's name, read in this machine's zone, [^,()]+, UTC[+-]\d\d:\d\d\)", b), b
    zone = Store(folder / "st").manifest("named-b").environment["import"]["zone"]
    assert set(zone) == {"name", "offset"} and re.fullmatch(r"UTC[+-]\d\d:\d\d", zone["offset"]), zone
    assert f"{zone['name']}, {zone['offset']})" in b, (zone, b)
    # a run Prove stored prints its start as before
    tau2 = ok(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, "--inputs", "all", "--max-mde", "0.12")).out
    assert all(line.split("started: ", 1)[1].split(" ·")[0].endswith("Z") and "(" not in line.split("started: ", 1)[1].split(" ·")[0]
               for line in _started_bullets(tau2))


def test_tf15_l6_a_deepeval_run_imported_before_this_pair(tmp_path: Path) -> None:
    """A run whose manifest records no zone (imported before this pair) says so."""
    folder = work(tmp_path)
    (folder / "results").mkdir()
    name = "test_run_20260905_185407.json"
    (folder / "results" / name).write_bytes(gzip.decompress((FIXTURES / "ingest" / "deepeval" / "humaneval-a.json.gz").read_bytes()))
    for run in ("old", "new"):
        assert import_here(folder, ["deepeval", f"results/{name}", "--store", "st", "--run", run, "--metric",
                                    "Tests Passed", "--cut", "recorded", "--case", "name"]).code == 0
    src, dst = Store(folder / "st"), Store(folder / "older")
    for run in ("old", "new"):
        manifest = src.manifest(run)
        environment = dict(manifest.environment)
        environment["import"] = {k: v for k, v in environment["import"].items() if k != "zone"}
        dst.create_run(dataclasses.replace(manifest, environment=environment, status="partial"))
        frame = src.read(run, meta=True, trace="none")
        from fixcheck_support import EpisodeRecord  # noqa: F401  (Prove's record, through the support module)
        from poisson_prove.store import EpisodeRecord as Record

        records = [
            Record(run_id=run, config_hash=str(h), config=dict(c), seed=int(s), replicate_index=int(r),
                   outcome=None if o is None else str(o), t=float(t), horizon=float(hz), confidence=None,
                   meta=dict(m) if isinstance(m, dict) else {}, error=None if o is not None else str(e),
                   wall_time=float(w), backend_meta={})
            for h, c, s, r, o, t, hz, e, w, m in zip(frame["config_hash"], frame["config"], frame["seed"],
                                                      frame["replicate_index"], frame["outcome"], frame["t"],
                                                      frame["horizon"], frame["error"], frame["wall_time"],
                                                      frame["meta"], strict=True)
        ]
        dst.append(run, records)
        dst.mark_complete(run)
    out = here(folder, ["changes", "old", "new", "--store", "older", "--event", "missed"]).out
    for bullet in _started_bullets(out):
        assert "(the time in the file's name, read in the zone of the machine that imported it)" in bullet, bullet


# ---------- 9.6 item 3: the control by design ----------


def test_tf15_l7_the_control_is_said_by_design() -> None:
    picked = ok(fix_check(TAU2, TAU2_B, PILOT, TAU2_EVENTS, "--failing-from", TAU2_A, "--max-mde", "0.20")).out
    lines = _lines(picked)
    at = lines.index("## The control")
    assert lines[at + 2] == "The old version's run on the inputs that failed in tau2-airline 2026-09-15 a, beside the new."
    assert "| version | runs | failed | failure share | did not fail on re-run |" in lines
    assert (
        "Re-running these inputs and counting the runs that did not fail would have read 25.0% on the old version, "
        "where nothing changed."
    ) in lines
    every = _lines(ok(fix_check(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, "--inputs", "all", "--max-mde", "0.12")).out)
    assert "## The control" not in every
    at = every.index("## The two versions")
    assert every[at + 2] == "The old version and the new on the same inputs."
    assert "| version | runs | failed | failure share | did not fail |" in every
    assert "The old version did not fail on 45.0% of its episodes on these inputs." in every
    assert not any("nothing changed" in line or "re-run" in line for line in every[at:every.index("## The comparison")])


# ---------- 9.6 item 4: the run's tally ----------


def test_tf15_l8_an_imported_runs_tally(tmp_path: Path) -> None:
    folder = work(tmp_path)
    for name, table, started in (("old", TABLE_A, "2026-09-05T18:54:07Z"), ("new", TABLE_B, "2026-09-05T19:50:09Z")):
        assert import_here(folder, ["table", str(table), "--store", "st", "--run", name, *COLUMNS, "--started", started]).code == 0
    for argv, labels in (
        (["fix-check", "old", "new", "--store", "st", "--event", "missed", *ALL], ("old", "new")),
        (["changes", "old", "new", "--store", "st", "--event", "missed"], ("A", "B")),
    ):
        lines = _lines(here(folder, argv).out)
        for label in labels:
            assert any(line.startswith(f"- the run's tally ({label}): rows ") for line in lines), lines
        assert not any(line.startswith("- Prove's tally") for line in lines)
    tau2 = _lines(ok(changes(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS)).out)
    assert any(line.startswith("- Prove's tally (A): rows ") for line in tau2)
    w = _lines(where(TAU2, TAU2_A, TAU2_EVENTS).out)
    assert any(line.startswith("- Prove's tally: rows ") for line in w)


def test_tf15_l9_the_summary_says_the_same_of_file_times(tmp_path: Path) -> None:
    """9.6 item 1: "The summary's gap clause says the same" (9.5.1's file-time form)."""
    from tf15_support import caveats

    folder = _file_time_pair(tmp_path)
    for argv in (["fix-check", "before", "after", *ALL], ["changes", "before", "after"]):
        first = caveats(here(folder, argv).out)[0]
        assert first.startswith("Trace can't tell when they ran (") and (
            "), so it can't tell whether they were run side by side either:" in first), first
        assert "apart" not in first, first


def test_tf15_l10_suite_timestamps_within_a_minute(tmp_path: Path) -> None:
    """9.5.1: starts from JUnit suites' timestamps a second apart say they started within a minute
    of each other, and that Trace still cannot confirm a side-by-side run."""
    from tf15_support import caveats

    folder = work(tmp_path)
    for which in ("a", "b"):
        assert import_here(folder, ["junit", str(JUNIT / f"humaneval-{which}.xml"), "--store", "st", "--run", f"s{which}", "--case", "name"]).code == 0
    first = caveats(here(folder, ["fix-check", "sa", "sb", "--store", "st", "--event", "missed", *ALL]).out)[0]
    assert "so they started within a minute of each other; Trace still can't confirm" in first, first


def test_tf15_l11_where_on_an_imported_run_says_the_runs_tally(tmp_path: Path) -> None:
    folder = work(tmp_path)
    assert import_here(folder, ["table", str(TABLE_A), "--store", "st", "--run", "t", *COLUMNS,
                                "--started", "2026-09-05T18:54:07Z"]).code == 0
    lines = _lines(here(folder, ["where", "t", "--store", "st", "--event", "missed"]).out)
    assert any(line.startswith("- the run's tally: rows ") for line in lines), lines
    assert not any(line.startswith("- Prove's tally") for line in lines)
