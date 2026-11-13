"""Shared helpers for the pacing pair's tests (B-8, ruled by Taylor on 2026-11-11): a clock the
test controls, put in place of every clock the import's writer reads, so that what the run's
event log says about its progress is held the same however loaded the machine is. Not a test
module and not collected.

The promise (``log/trace-pacing-a``, P-1): **every progress line but the closing one is written
at least one second after the progress line before it, by the times written in the log**, to
the microsecond, without slack, whatever the machine is doing between reading a clock and
writing a line, and however the wall clock is slewed or set. The run record's RUNREC-11 and
RUNREC-12 hold the same with a millisecond's slack, on whatever lines a real import happens to
write; these hold it exactly, on lines a script of the clock decides.

What Session B builds, in one place:

``poisson_trace.ingest.writer`` (``_Log`` and ``_now``, nothing else)
    Progress is paced by the clock it is stamped with. One reading of the wall clock both
    decides whether a progress line is written and is the time written on it: a line is
    written when it is the first progress of the import, or when that reading, as written
    (microseconds, UTC), is at least one second after the time written on the last paced
    progress line. No monotonic clock decides it, and no second reading is taken to stamp it.
    The closing progress, and ``planned``, ``started``, ``finished`` and ``interrupted``, are
    stamped as today (the wall clock when emitted) and are not paced. Every clock the writer
    reads is read through the module's own names ``time`` and ``datetime``, as on main, so a
    test can stand a clock in their place. Nothing else moves: the lines' keys, details and
    format, the outputs of every verb, the pages and the app.

The clock (``Clock``): one count of nanoseconds that every reading moves on. The writer's module
gets ``Clock.time``, standing in for the ``time`` module (``monotonic``, ``perf_counter``,
``time`` and their ``_ns`` forms, and ``sleep``, read off the clock; anything else is the real
module's), and ``Clock.datetime``, a ``datetime`` whose ``now``, ``utcnow`` and ``today`` read
the clock. After every reading the clock moves on by the script's next step, which stands for
the work and the stalls between one reading and the next: under load, a step can be long. The
wall clock is the count, plus an offset the script can set (``Clock.set_wall``) and a rate the
script can slew (``Clock(slew=...)``); the monotonic clock is the count alone. Every wall time
the clock has handed out is kept (``Clock.handed``), so a test can say the log's times came from
it and from no other clock.
"""

from __future__ import annotations

import itertools
import time as _time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

#: The wall time the clock starts at: 2026-11-13 12:00:00 UTC, in nanoseconds.
START_NS = 1_794_571_200 * 1_000_000_000
SECOND = timedelta(seconds=1)
AT_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class Clock:
    """A clock the test controls (see the module's opening)."""

    def __init__(self, steps: Iterable[int], *, slew: float = 0.0,
                 when: Mapping[float, Callable[[Clock], None]] | None = None) -> None:
        self.elapsed = 0
        self.offset = 0
        self.slew = slew
        self.reads = 0
        self.handed: list[datetime] = []
        self._steps: Iterator[int] = iter(steps)
        # what the script does once the clock has run so many seconds, each once
        self._when = sorted((round(s * 1e9), act) for s, act in (when or {}).items())
        self.time = _Time(self)
        self.datetime = _datetime_of(self)

    # ---- readings ----

    def mono_ns(self) -> int:
        return self._read(self.elapsed)

    def wall_ns(self) -> int:
        wall = START_NS + self.offset + self.elapsed + round(self.elapsed * self.slew)
        return self._read(wall, wall=True)

    def _read(self, value: int, *, wall: bool = False) -> int:
        if wall:
            self.handed.append(_of_ns(value))
        self.reads += 1
        self.elapsed += next(self._steps)
        while self._when and self.elapsed >= self._when[0][0]:
            self._when.pop(0)[1](self)
        return value

    # ---- what a script does ----

    def set_wall(self, by_ns: int) -> None:
        """The wall clock set forward (positive) or back (negative) by ``by_ns``."""
        self.offset += by_ns


def _of_ns(ns: int) -> datetime:
    """A wall time in nanoseconds as an aware UTC datetime, cut to the microsecond as
    ``datetime.now`` gives it."""
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=ns // 1000)


class _Time:
    """The ``time`` module, its clocks read off a ``Clock``."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def monotonic(self) -> float:
        return self._clock.mono_ns() / 1e9

    def monotonic_ns(self) -> int:
        return self._clock.mono_ns()

    def perf_counter(self) -> float:
        return self._clock.mono_ns() / 1e9

    def perf_counter_ns(self) -> int:
        return self._clock.mono_ns()

    def time(self) -> float:
        return self._clock.wall_ns() / 1e9

    def time_ns(self) -> int:
        return self._clock.wall_ns()

    def sleep(self, seconds: float) -> None:
        self._clock.elapsed += round(seconds * 1e9)

    def __getattr__(self, name: str) -> Any:
        return getattr(_time, name)


def _datetime_of(clock: Clock) -> type[datetime]:
    class _Datetime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> Any:
            at = _of_ns(clock.wall_ns())
            return at.astimezone(tz) if tz is not None else at.astimezone().replace(tzinfo=None)

        @classmethod
        def utcnow(cls) -> Any:
            return _of_ns(clock.wall_ns()).replace(tzinfo=None)

        @classmethod
        def today(cls) -> Any:
            return cls.now()

    return _Datetime


# ---------- the scripts: what passes between one reading and the next ----------

MS = 1_000_000


def steady(step_ns: int = 10 * MS + 437) -> Iterator[int]:
    """An unloaded machine: the same short step between readings (a part of a microsecond in
    it, so that a writer deciding on nanoseconds and writing microseconds is seen)."""
    return itertools.repeat(step_ns)


def loaded(seed: int = 7) -> Iterator[int]:
    """A loaded machine, the same on every run: mostly short steps, now and then a stall of a
    few to a few hundred milliseconds (a collection, another process on the core), at no
    regular place."""
    state = seed
    while True:
        state = (state * 1_103_515_245 + 12_345) % 2**31
        roll = state % 100
        if roll < 70:
            yield 3 * MS + state % 997
        elif roll < 90:
            yield 9 * MS + state % 7_919 * 1000
        elif roll < 98:
            yield 30 * MS + state % 40 * MS
        else:
            yield 250 * MS + state % 13


def stalls_after_every(period: int, stall_ns: int, step_ns: int = 3 * MS + 211) -> Iterator[int]:
    """Short steps, and a stall of ``stall_ns`` after every ``period``-th reading."""
    for n in itertools.count(1):
        yield stall_ns if n % period == 0 else step_ns


def frozen_for(seconds: float, after: int, step_ns: int = 5 * MS + 3) -> Iterator[int]:
    """Short steps, and the machine stopped for ``seconds`` once, after reading ``after``."""
    for n in itertools.count(1):
        yield round(seconds * 1e9) if n == after else step_ns


SCRIPTS: dict[str, Callable[[], Iterator[int]]] = {
    "steady": steady,
    "loaded": loaded,
    "loaded, another seed": lambda: loaded(1_234_567),
    "a 7 ms stall after every 5th reading": lambda: stalls_after_every(5, 7 * MS + 1),
    "a 41 ms stall after every 3rd reading": lambda: stalls_after_every(3, 41 * MS + 9),
    "a 997 ms stall after every 3rd reading": lambda: stalls_after_every(3, 997 * MS),
    "stopped for 2.5 s once": lambda: frozen_for(2.5, 203),
}
# Each loaded script writes, through main 2ff191b's writer, two paced lines less than a second
# apart: the 7 ms stall as the 0.9977 s gap of the trace#31 session, the 41 ms one as 0.9936 s
# of TF24 Session B's slow lane and wider, the stop between a reading that decided a line and
# the reading that stamped it.


# ---------- an import under the clock ----------


def write_under(clock: Clock, rows: int, root: Path, monkeypatch: Any, *, name: str = "r",
                errored_first: int = 0) -> None:
    """``writer.write`` of a run of ``rows`` rows into ``root`` with ``clock`` standing for every
    clock the writer's module reads; the first ``errored_first`` rows have no outcome."""
    from poisson_trace.ingest import writer

    # the writer need not import ``time`` once no monotonic clock paces it: set it either way
    monkeypatch.setattr(writer, "time", clock.time, raising=False)
    monkeypatch.setattr(writer, "datetime", clock.datetime)
    writer.write(a_run(rows, name=name, errored_first=errored_first), root)


def a_run(rows: int, *, name: str = "r", errored_first: int = 0) -> Any:
    from poisson_trace.ingest.rows import Row, Run

    made = tuple(Row(f"c{i % 50}", None, "no score") if i < errored_first
                 else Row(f"c{i % 50}", "met" if i % 3 else "missed", None) for i in range(rows))
    return Run(name=name, tool="table", rows=made, started="2026-09-05T18:54:07Z",
               started_from="given", declared={"case_column": "case"},
               files=({"name": "results.csv", "sha256": "ab" * 32},))


def log_of(root: Path, run: str = "r") -> list[dict[str, Any]]:
    import json

    text = (root / run / "events.jsonl").read_text(encoding="utf-8")
    assert text.endswith("\n"), "every line of the log is whole"
    return [json.loads(line) for line in text.splitlines()]


def at(event: Mapping[str, Any]) -> datetime:
    """An event's written time, exactly as written (UTC, to the microsecond): read with no zone
    and none assumed, so that two of them subtract to the gap the log says."""
    return datetime.strptime(event["at"], AT_FORMAT)


def progress(log: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [e for e in log if e["kind"] == "progress"]


def paced(log: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The paced progress lines: every one but the closing one."""
    return progress(log)[:-1]


def gaps(lines: Sequence[Mapping[str, Any]]) -> list[timedelta]:
    times = [at(e) for e in lines]
    return [b - a for a, b in zip(times, times[1:], strict=False)]


def shown(lines: Sequence[Mapping[str, Any]]) -> list[str]:
    return [f'{e["at"]} done={e["detail"]["done"]}' for e in lines]
