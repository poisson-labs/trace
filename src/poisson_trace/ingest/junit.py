"""JUnit XML reports, as pytest, Jest, Go, Maven and CI systems write them.

A report is a ``<testsuites>`` root holding ``<testsuite>`` elements, or a lone ``<testsuite>``
root, suites possibly nested in suites; each ``<testcase>`` is one row. A test case with a
``<failure>`` or an ``<error>`` missed, one ``<skipped>`` has no outcome, and any other met. The
case is the class name and the name, or the name alone. Nothing of a message, a failure's text,
a test's output or a property is kept, and a report that declares a document type is refused
before anything it names is read.
"""

from __future__ import annotations

import argparse
import hashlib
import xml.parsers.expat as expat
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from poisson_trace.ingest.cut import MET, MISSED
from poisson_trace.ingest.rows import Refusal, Row, Run, case_id
from poisson_trace.look import why

CASES: tuple[str, ...] = ("classname-name", "name")
ROOTS: tuple[str, ...] = ("testsuites", "testsuite")
# how much of a file looks_like reads to find its root element
HEAD = 4096

DESCRIPTION = """\
Read JUnit XML reports (pytest's --junitxml, and the reports Jest, Go, Maven and CI systems
write) and write them as one new run. Each test case is one row: a failure or an error missed,
a skip has no outcome, any other met. Test cases that share a case, within a file or across
the files of one import, are its repeats. The start is the earliest suite timestamp, read as UTC
when it carries no zone. No message, output or property is kept.
"""
EXAMPLE = "poisson-trace import junit reports/old.xml --store trace-store --run old"

TOOL = "junit"
SKIPPED = "skipped"
# what joins the class name and the name in the default case
_JOIN = "::"
_MISSED_BY = ("failure", "error")
UNZONED = "a suite timestamp carries no zone, so it was read as UTC"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--case",
        choices=CASES,
        default=CASES[0],
        metavar="classname-name|name",
        help="what identifies a test case across the two versions: its class name and its "
        "name, or its name alone (default: classname-name)",
    )


class _Declared(Exception):
    """The report declares a document type."""


class _Root(Exception):
    """The report's root element is not a JUnit one."""

    def __init__(self, root: str) -> None:
        super().__init__(root)
        self.root = root


@dataclass
class _Read:
    """What one report holds that the import keeps: each test case's class name, name and the
    kinds of child that decide its outcome, and each suite's timestamp."""

    cases: list[tuple[str | None, str | None, set[str]]] = field(default_factory=list)
    stamps: list[str] = field(default_factory=list)
    depth: int = 0
    open_case: int | None = None  # the depth of the test case being read


def _parser(read: _Read) -> Any:
    parser = expat.ParserCreate()
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)

    def doctype(*_: Any) -> None:
        raise _Declared

    def start(name: str, attrs: dict[str, str]) -> None:
        if read.depth == 0 and name not in ROOTS:
            raise _Root(name)
        read.depth += 1
        if name == "testsuite" and "timestamp" in attrs:
            read.stamps.append(attrs["timestamp"])
        elif name == "testcase" and read.open_case is None:
            read.cases.append((attrs.get("classname"), attrs.get("name"), set()))
            read.open_case = read.depth
        elif read.open_case is not None and read.depth == read.open_case + 1:
            read.cases[-1][2].add(name)

    def end(name: str) -> None:
        if read.open_case == read.depth:
            read.open_case = None
        read.depth -= 1

    parser.StartDoctypeDeclHandler = doctype
    parser.EntityDeclHandler = doctype
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    return parser


def _report(path: Path, raw: bytes) -> _Read:
    if not raw.strip():
        raise Refusal(f"{path} is not a JUnit report: it is empty")
    read = _Read()
    try:
        _parser(read).Parse(raw, True)
    except _Declared:
        raise Refusal(
            f"{path} declares a document type, which no test runner writes, so it is not read"
        ) from None
    except _Root as e:
        raise Refusal(
            f"{path} is not a JUnit report: its root element is <{e.root}>, not <testsuites> "
            "or <testsuite>"
        ) from None
    except expat.ExpatError as e:
        raise Refusal(f"{path} is not a JUnit report: it is not XML that can be read ({e})") from e
    if not read.cases:
        raise Refusal(f"{path} holds no test case, so there is nothing to read from it")
    return read


def _case(path: Path, form: str, classname: str | None, name: str | None) -> str:
    """The test case's class name and its name, kept apart, or its name alone; a test case with
    no class name is its name under either form."""
    if not name:
        raise Refusal(f"{path} holds a test case with no name, so nothing identifies it")
    text = name if form == "name" or not classname else f"{classname}{_JOIN}{name}"
    try:
        return case_id(text)
    except UnicodeEncodeError:
        raise Refusal(
            f"{path} holds a test case whose name is not valid Unicode, so it cannot identify a "
            "case"
        ) from None


def _instant(path: Path, stamp: str) -> tuple[datetime, bool]:
    """A suite timestamp as an instant, and whether it carried a zone; one that carries none
    is read as UTC. A timestamp that is no time is refused."""
    try:
        at = datetime.fromisoformat(stamp)
    except ValueError:
        raise Refusal(f'{path} holds a suite timestamp that is not a time: "{stamp}"') from None
    zoned = at.tzinfo is not None and at.utcoffset() is not None
    try:
        return (at.astimezone(UTC) if zoned else at.replace(tzinfo=UTC)), zoned
    except OverflowError:
        raise Refusal(
            f"{path} holds a suite timestamp that falls outside the years 1 to 9999 in UTC: "
            f'"{stamp}"'
        ) from None


def _utc(at: datetime) -> str:
    """An instant as UTC with a ``Z``, to the microsecond when it has a fraction of a second."""
    fraction = f".{at.microsecond:06d}" if at.microsecond else ""
    return at.strftime("%Y-%m-%dT%H:%M:%S") + fraction + "Z"


def _root_of(head: bytes) -> str | None:
    """The root element's name, when the bytes reach it and declare no document type before it."""

    class _Found(Exception):
        pass

    names: list[str] = []
    parser = expat.ParserCreate()
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)

    def doctype(*_: Any) -> None:
        raise _Declared

    def start(name: str, attrs: dict[str, str]) -> None:
        names.append(name)
        raise _Found

    parser.StartDoctypeDeclHandler = doctype
    parser.StartElementHandler = start
    try:
        parser.Parse(head, False)
    except _Found:
        return names[0]
    except (_Declared, expat.ExpatError):
        return None
    return None


def looks_like(path: Path | str) -> str | None:
    """One line describing ``path`` when it is a JUnit report, else None; it never raises. A
    report is a ``.xml`` file whose root element, within its first 4 KB, is ``testsuites`` or
    ``testsuite``, and that declares no document type."""
    try:
        found = Path(path)
        if not found.name.lower().endswith(".xml") or not found.is_file():
            return None
        with open(found, "rb") as report:
            head = report.read(HEAD)
        root = _root_of(head)
    except Exception:
        return None
    if root not in ROOTS:
        return None
    return f"a JUnit XML report, its root <{root}>"


def read(ns: argparse.Namespace) -> Run:
    form = str(ns.case)
    paths = [Path(f) for f in ns.files]
    files, rows = [], []
    stamps: list[tuple[datetime, bool]] = []
    kinds: Counter[str] = Counter()
    first_modified = 0.0
    for at, path in enumerate(paths):
        try:
            raw = path.read_bytes()
            if at == 0:
                first_modified = path.stat().st_mtime
        except OSError as e:
            raise Refusal(f"{path} could not be read: {why(e)}") from e
        files.append({"name": path.name, "sha256": hashlib.sha256(raw).hexdigest()})
        report = _report(path, raw)
        stamps += [_instant(path, stamp) for stamp in report.stamps]
        for classname, name, children in report.cases:
            case = _case(path, form, classname, name)
            missed_by = [kind for kind in _MISSED_BY if kind in children]
            if missed_by:
                kinds[missed_by[0]] += 1
                rows.append(Row(case, MISSED, None, None, None, {"case": form}))
            elif SKIPPED in children:
                rows.append(Row(case, None, SKIPPED, None, None, {"case": form}))
            else:
                rows.append(Row(case, MET, None, None, None, {"case": form}))
    if stamps:
        earliest = min(at for at, _ in stamps)
        started, started_from = _utc(earliest), "file"
        note = None if all(zoned for _, zoned in stamps) else UNZONED
    else:
        first = datetime.fromtimestamp(first_modified, UTC)
        started, started_from, note = first.strftime("%Y-%m-%dT%H:%M:%SZ"), "file time", None
    return Run(
        name=ns.run,
        tool=TOOL,
        rows=tuple(rows),
        started=started,
        started_from=started_from,
        declared={"case": form},
        files=tuple(files),
        counts={
            "test cases with a failure": kinds["failure"],
            "test cases with an error": kinds["error"],
        },
        started_note=note,
    )
