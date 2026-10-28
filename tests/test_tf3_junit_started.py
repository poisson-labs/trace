"""TF3-38: a JUnit report's start is its suites' timestamp (spec section 6.3) — pending: this file
and the rewrite of IC12's vocabulary (``tests/ingest/test_import_cli.py``) are one commit, dropped
together on a no.

The start-time vocabulary every import records (``started_from``, Integrations — Spec INT1
section 2.6) has no word for a time the tool wrote inside the file: ``file name`` is a time in the
file's name and ``file time`` its modification time. The spec's promptfoo reader names the word
``file``; the JUnit reader is the first to need it.

- The start is the earliest ``timestamp`` of any suite of the files read, as UTC; ``started_from``
  is ``file``.
- A timestamp with no zone is read as UTC, and the summary says so.
- A timestamp that is not a time is refused, naming the file.
- The committed reports start at their suites' timestamps.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from poisson_prove.store import Store

from tf0_support import chdir
from tf2_support import scratch_home  # noqa: F401
from tf3_support import OWN_1, OWN_2, SUITE_1, SUITE_2, Case, imported, junit_argv, refusal, report, suite, verb, write_report

CASES = [Case("test_a"), Case("test_b", result="failure")]


def _instant(text: str) -> datetime:
    assert text.endswith("Z"), text
    return datetime.fromisoformat(text[:-1] + "+00:00")


def _started(folder: Path, run: str) -> tuple[datetime, str]:
    m = Store(folder / "st").manifest(run)
    return _instant(m.created_at), m.environment["import"]["started_from"]


def test_tf3_38_the_start_is_the_suite_s_timestamp(tmp_path: Path) -> None:
    write_report(tmp_path / "r.xml", report(suite(CASES, timestamp="2026-10-12T09:30:15.250000+02:00")))
    with chdir(tmp_path):
        doc = imported(verb([*junit_argv("r.xml", "st", "r"), "--json"]))
    assert _started(tmp_path, "r") == (datetime(2026, 10, 12, 7, 30, 15, 250000, tzinfo=UTC), "file")
    assert doc["started"]["from"] == "file" and _instant(doc["started"]["at"]) == datetime(2026, 10, 12, 7, 30, 15, 250000, tzinfo=UTC)


def test_tf3_38_the_earliest_timestamp_of_every_suite_read_is_the_start(tmp_path: Path) -> None:
    write_report(tmp_path / "late.xml", report(suite(CASES, timestamp="2026-10-12T11:00:00+00:00"), suite(CASES, timestamp=None)))
    write_report(tmp_path / "early.xml", report(suite(CASES, timestamp=None), suite(CASES, timestamp="2026-10-12T12:00:00+03:00")))
    with chdir(tmp_path):
        imported(verb([*junit_argv(["late.xml", "early.xml"], "st", "r"), "--json"]))
    assert _started(tmp_path, "r") == (datetime(2026, 10, 12, 9, 0, 0, tzinfo=UTC), "file")


def test_tf3_38_a_timestamp_with_no_zone_is_read_as_utc_and_said(tmp_path: Path) -> None:
    write_report(tmp_path / "bare.xml", report(suite(CASES, timestamp="2026-10-12T09:30:15")))
    write_report(tmp_path / "zoned.xml", report(suite(CASES, timestamp="2026-10-12T09:30:15Z")))
    with chdir(tmp_path):
        bare = verb(junit_argv("bare.xml", "st", "bare"))
        zoned = verb(junit_argv("zoned.xml", "st", "zoned"))
    assert bare.code == 0 and zoned.code == 0, bare.text + zoned.text
    assert _started(tmp_path, "bare") == _started(tmp_path, "zoned") == (datetime(2026, 10, 12, 9, 30, 15, tzinfo=UTC), "file")

    def started_line(out: str) -> str:
        return next(line for line in out.splitlines() if line.startswith("- started:"))

    # the zoned report's line says only where the start came from; the zone-less one says more
    assert started_line(bare.out).startswith(started_line(zoned.out)), (bare.out, zoned.out)
    assert started_line(bare.out) != started_line(zoned.out), (bare.out, zoned.out)
    with chdir(tmp_path):
        bare_doc = imported(verb([*junit_argv("bare.xml", "st", "bare-json"), "--json"]))
        zoned_doc = imported(verb([*junit_argv("zoned.xml", "st", "zoned-json"), "--json"]))
    assert set(zoned_doc["started"]) == {"at", "from"}, zoned_doc["started"]
    assert set(bare_doc["started"]) > {"at", "from"}, bare_doc["started"]


def test_tf3_38_a_timestamp_that_is_no_time_is_refused(tmp_path: Path) -> None:
    write_report(tmp_path / "r.xml", report(suite(CASES, timestamp="yesterday")))
    with chdir(tmp_path):
        line = refusal(verb(junit_argv("r.xml", "st", "r")))
    assert "r.xml" in line
    assert not (tmp_path / "st").exists()


def test_tf3_38_the_committed_reports_start_at_their_timestamps(tmp_path: Path) -> None:
    want = {
        OWN_1: datetime(2026, 10, 13, 4, 1, 11, 564615, tzinfo=UTC), OWN_2: datetime(2026, 10, 13, 4, 1, 23, 261977, tzinfo=UTC),
        SUITE_1: datetime(2026, 10, 13, 4, 20, 34, 510483, tzinfo=UTC), SUITE_2: datetime(2026, 10, 13, 4, 20, 35, 677086, tzinfo=UTC),
    }
    for n, (path, at) in enumerate(want.items()):
        with chdir(tmp_path):
            imported(verb([*junit_argv(path, "st", f"s{n}"), "--json"]))
        assert _started(tmp_path, f"s{n}") == (at, "file")
