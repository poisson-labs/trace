"""PACE-1 to PACE-9: an import's progress is paced by the clock it is stamped with (B-8, ruled by
Taylor on 2026-11-11; the promise is P-1 of ``log/trace-pacing-a``). Every progress line but the
closing one is written at least one second after the progress line before it, by the times
written in the log, to the microsecond and with no slack, however loaded the machine is, and
however the wall clock is slewed or set.

Each test runs the import's writer under a clock the test controls (``pacing_support.Clock``),
standing for every clock the writer reads, so nothing here waits on or depends on the real one:
a test that passed only because the machine was quick would be the bug B-8 found. On main
2ff191b the writer decides by the monotonic clock and stamps the wall clock a moment later, so
a stall between the two readings, or a wall clock running slower than the monotonic one,
writes two paced lines less than a second apart; RUNREC-11 and RUNREC-12 failed that way on a
loaded machine (0.9977 s and 0.9936 s against their 0.999 s floor).

**PACE-1** Under each script of the clock (an unloaded machine, two loaded ones, stalls of 7 ms,
41 ms and a second at regular places, the machine stopped for 2.5 s), every paced progress line
is at least a second after the one before by the times written.
**PACE-2** Progress keeps coming: the first progress line counts the first row, and each paced
line is written at the first reading a second after the last, so on an unloaded machine no gap
is longer than a second and a few steps, and an import of N seconds writes about N lines.
**PACE-3** A wall clock slewed against the monotonic one, slow or fast, by a little or by half:
the gaps by the times written are still at least a second and at most a second and a few steps.
**PACE-4** A wall clock set back during an import: no paced line is written less than a second
after the last by the times written (none at all until the clock is past it again), progress
resumes then, and the import ends with its closing progress and ``finished``.
**PACE-5** A wall clock set forward during an import: progress goes on once a second from the
new time.
**PACE-6** Every time in the log is one the controlled clock handed out: no line is stamped by
another clock.
**PACE-7** The closing progress always comes, however soon after the last paced line, with every
row; a one-row import writes the first-row progress and the closing one.
**PACE-8** An import stopped by Ctrl-C after its run folder exists: the paced lines before it
are a second apart by the times written, then the closing progress and ``interrupted``.
**PACE-9** The run record's own check of the log (``runrec_support.check_finished``, which
RUNREC-10 to RUNREC-12 apply) holds on RUNREC-11's import, the rows with no outcome first, under
each loaded script: the frozen tests' floor is met whatever the load.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from pacing_support import (
    MS, SCRIPTS, SECOND, Clock, at, gaps, log_of, paced, progress, shown, steady, write_under,
)

LOADED = [name for name in SCRIPTS if name != "steady"]


def _assert_a_second_apart(log: list[dict[str, Any]], *, at_least: int = 3) -> None:
    lines = paced(log)
    assert len(lines) > at_least, ("too few paced lines to hold the promise on", shown(progress(log)))
    short = [(i, g) for i, g in enumerate(gaps(lines)) if g < SECOND]
    assert not short, (short, shown(lines))


# ---------- PACE-1: a second apart by the times written, under any load ----------


@pytest.mark.parametrize("script", list(SCRIPTS))
def test_pace_1_paced_lines_are_a_second_apart_by_the_times_written(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: str) -> None:
    clock = Clock(SCRIPTS[script]())
    write_under(clock, 2_000, tmp_path / "store", monkeypatch)
    _assert_a_second_apart(log_of(tmp_path / "store"))


# ---------- PACE-2: progress keeps coming ----------


def test_pace_2_the_first_progress_counts_the_first_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_under(Clock(steady()), 500, tmp_path / "store", monkeypatch)
    first = progress(log_of(tmp_path / "store"))[0]["detail"]
    # row 0 of ``a_run`` is "missed": an outcome, so kept
    assert first == {"done": 1, "kept": 1, "errored": 0, "total": 500}, first


def test_pace_2_each_paced_line_comes_at_the_first_reading_a_second_after_the_last(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    step = 10 * MS + 437
    clock = Clock(steady(step))
    write_under(clock, 3_000, tmp_path / "store", monkeypatch)
    log = log_of(tmp_path / "store")
    lines = paced(log)
    # a writer may read the clock more than once a row: a few steps of room, never a second more
    late = [(i, g) for i, g in enumerate(gaps(lines)) if g > SECOND + timedelta(microseconds=3 * step // 1000)]
    assert not late, (late, shown(lines))
    span = at(progress(log)[-1]) - at(lines[0])
    assert len(lines) >= int(span / SECOND), (len(lines), span, shown(lines))


# ---------- PACE-3: a slewed wall clock ----------


@pytest.mark.parametrize("slew", [-0.001, 0.001, -0.5, 0.5])
def test_pace_3_a_slewed_wall_clock_paces_by_its_own_seconds(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, slew: float) -> None:
    step = 10 * MS + 437
    clock = Clock(steady(step), slew=slew)
    write_under(clock, 3_000, tmp_path / "store", monkeypatch)
    log = log_of(tmp_path / "store")
    _assert_a_second_apart(log)
    room = SECOND + timedelta(microseconds=round(3 * step * (1 + slew)) // 1000)
    late = [(i, g) for i, g in enumerate(gaps(paced(log))) if g > room]
    assert not late, (late, shown(paced(log)))


# ---------- PACE-4: a wall clock set back ----------


def test_pace_4_a_wall_clock_set_back_writes_no_line_under_a_second_after_the_last(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    back = 30 * 10**9
    clock = Clock(steady(), when={5.0: lambda c: c.set_wall(-back)})
    write_under(clock, 6_000, tmp_path / "store", monkeypatch)
    log = log_of(tmp_path / "store")
    _assert_a_second_apart(log)
    lines = paced(log)
    before = [e for e in lines if at(e) < at(lines[0]) + timedelta(seconds=5)]
    after = lines[len(before):]
    # none written until the clock was a second past the last line again; then once a second
    assert after, shown(lines)
    assert all(at(e) >= at(before[-1]) + SECOND for e in after), shown(lines)
    assert len(after) >= 20, shown(lines)
    kinds = [e["kind"] for e in log]
    assert kinds[-2:] == ["progress", "finished"] and log[-2]["detail"]["done"] == 6_000, kinds[-2:]


# ---------- PACE-5: a wall clock set forward ----------


def test_pace_5_a_wall_clock_set_forward_goes_on_once_a_second_from_the_new_time(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Clock(steady(), when={5.0: lambda c: c.set_wall(3_600 * 10**9)})
    write_under(clock, 3_000, tmp_path / "store", monkeypatch)
    log = log_of(tmp_path / "store")
    _assert_a_second_apart(log)
    lines = paced(log)
    jumped = [i for i, g in enumerate(gaps(lines)) if g > timedelta(seconds=3_000)]
    assert len(jumped) == 1, shown(lines)
    after = lines[jumped[0] + 1:]
    assert len(after) >= 20, shown(lines)
    assert all(g < timedelta(seconds=1.1) for g in gaps(after)), shown(after)


# ---------- PACE-6: no other clock ----------


@pytest.mark.parametrize("script", ["steady", "loaded"])
def test_pace_6_every_time_in_the_log_is_one_the_clock_handed_out(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: str) -> None:
    clock = Clock(SCRIPTS[script]())
    write_under(clock, 1_000, tmp_path / "store", monkeypatch)
    handed = {t.replace(tzinfo=None) for t in clock.handed}
    log = log_of(tmp_path / "store")
    stray = [e["at"] for e in log if at(e) not in handed]
    assert not stray, stray
    assert len(paced(log)) > 3, shown(progress(log))


# ---------- PACE-7: the closing progress ----------


def test_pace_7_the_closing_progress_comes_however_soon_after_the_last_paced_line(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 150 rows at ten milliseconds and a bit a reading: the last paced line about a second in,
    # the end about half a second later
    write_under(Clock(steady()), 150, tmp_path / "store", monkeypatch)
    log = log_of(tmp_path / "store")
    lines = progress(log)
    assert lines[-1]["detail"] == {"done": 150, "kept": 150, "errored": 0, "total": 150}, shown(lines)
    assert at(lines[-1]) - at(lines[-2]) < SECOND, shown(lines)
    assert [e["kind"] for e in log][-2:] == ["progress", "finished"]


def test_pace_7_a_one_row_import_writes_the_first_row_s_progress_and_the_closing_one(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_under(Clock(steady()), 1, tmp_path / "store", monkeypatch)
    log = log_of(tmp_path / "store")
    assert [e["kind"] for e in log] == ["planned", "started", "progress", "progress", "finished"]
    # row 0 of ``a_run`` is "missed": an outcome, so kept
    one = {"done": 1, "kept": 1, "errored": 0, "total": 1}
    assert [e["detail"] for e in progress(log)] == [one, one]


# ---------- PACE-8: Ctrl-C ----------


@pytest.mark.parametrize("script", ["loaded", "a 41 ms stall after every 3rd reading"])
def test_pace_8_an_interrupted_import_paces_its_lines_before_the_stop(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: str) -> None:
    from poisson_prove.store import Store

    def stop(self: Any, run_id: str, records: Any) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(Store, "append", stop)
    clock = Clock(SCRIPTS[script]())
    with pytest.raises(KeyboardInterrupt):
        write_under(clock, 2_000, tmp_path / "store", monkeypatch)
    log = log_of(tmp_path / "store")
    assert [e["kind"] for e in log][-2:] == ["progress", "interrupted"]
    _assert_a_second_apart(log)


# ---------- PACE-9: the run record's own check, under load ----------


@pytest.mark.parametrize("script", LOADED)
def test_pace_9_the_run_record_s_check_holds_under_load(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: str) -> None:
    from runrec_support import check_finished

    root = tmp_path / "store"
    write_under(Clock(SCRIPTS[script]()), 2_000, root, monkeypatch, errored_first=1_000)
    log = log_of(root)
    assert len(paced(log)) > 3, shown(progress(log))
    check_finished(root, "r", 2_000)
