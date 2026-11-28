"""What the JSON promises about numbers, and where the docs say it.

The form of the documents does not change: every float in every document is written as
``json.dumps`` writes a Python float, and no number is written as a string; the function that
writes them, ``report.json_text``, is the one main had; and the tests that hold each document's
public keys, with their lines in ``tests/frozen.sha256``, are the ones main had. No schema id in
``src/`` or ``docs/`` changes.

The docs say that the same inputs give the same bytes on macOS and on Linux, on every Python Trace
declares, and with any numpy and scipy at or above the declared floors; and the changelog says that
the last digits of the ``--json`` and ``result.json`` numbers can differ from 0.1.0a1.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from pathlib import Path
from typing import Any

from api_support import VERBS_ARGV, cli, workspace
from portable_support import REPO

#: The objects whose keys and values are the run's or the user's, not Trace's.
NOT_TRACES = frozenset({"config", "ceilings"})
#: A float written as text: digits, a point and digits, as a float would be written unquoted.
#: (Identifiers such as a run's hash can be all digits, or digits round an ``e``.)
NUMBER_TEXT = re.compile(r"^-?(?:0|[1-9]\d*)\.\d+(?:[eE][-+]?\d+)?$")
BUNDLED = ("where", "compare", "fix-check", "changes")

#: ``report.json_text`` as main wrote it: the SHA-256 of its source.
JSON_TEXT = "cd6a95146770cb215d1f4fea32c2576ecd64177a24edf88fb3f868523bbe3536"
#: The tests that hold each document's public keys, and their lines as main held them.
KEY_TESTS = {
    "tests/json_promise_pins.py": "c5e8a9aa50fefc01b544d4e83e93a443ca21921e02eb1f4de8ccdc86d0a4700f",
    "tests/test_json_promise.py": "bf419507d0330fc83ca674bc06863dd25766adb0dec6befb340d97410880508c",
    "tests/test_steps_timings_promise.py": "1c3a594b9e71f1f605643c18f35147bf3c51c24cd3a47692f28e6d8403942f20",
}
#: Every schema id that ``src/`` and ``docs/`` name.
SCHEMAS = frozenset({
    "poisson-trace.changes/2", "poisson-trace.chart/1", "poisson-trace.compare/1", "poisson-trace.doctor/1",
    "poisson-trace.fix-check/2", "poisson-trace.handover/1", "poisson-trace.import/1", "poisson-trace.init/1",
    "poisson-trace.runs/1", "poisson-trace.ui/1", "poisson-trace.where/1",
})
PROMISE = ("The same inputs give the same bytes on macOS and on Linux, on every Python Trace declares, and "
           "with any numpy and scipy at or above the declared floors.")
OLD_PROMISE = "The same inputs give the same bytes."


class _Float(str):
    """A float as it is written in the document."""


def _strings_and_floats(value: Any, at: str, out: list[tuple[str, Any]]) -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            if key not in NOT_TRACES and not key.startswith("_"):
                _strings_and_floats(inner, f"{at}/{key}", out)
    elif isinstance(value, list):
        for i, inner in enumerate(value):
            _strings_and_floats(inner, f"{at}/{i}", out)
    elif isinstance(value, (_Float, str)):
        out.append((at, value))


def _documents(tmp: Path) -> dict[str, str]:
    work = workspace(tmp)
    docs = {}
    for name, argv in VERBS_ARGV.items():
        ran = cli(work, [*argv, "--json"])
        if ran.code == 0 and ran.out.lstrip().startswith("{"):
            docs[f"{name} --json"] = ran.out
    for name in BUNDLED:
        out = work / f"bundle {name}"
        ran = cli(work, [*VERBS_ARGV[name], "--out", str(out)])
        assert ran.code == 0, ran.err
        docs[f"{name} result.json"] = (out / "result.json").read_text(encoding="utf-8")
    return docs


def test_every_float_is_written_as_python_writes_it_and_no_number_is_a_string(tmp_path: Path) -> None:
    from poisson_trace import report

    docs = _documents(tmp_path)
    assert {"fix-check --json", "compare --json", "changes --json", "where --json", "fix-check measures --json"} <= set(docs)
    wrong = []
    for name, text in docs.items():
        assert report.json_text(json.loads(text)) == text, f"{name}: not as report.json_text writes it"
        found: list[tuple[str, Any]] = []
        _strings_and_floats(json.loads(text, parse_float=_Float), "", found)
        for at, value in found:
            if isinstance(value, _Float):
                if json.dumps(float(value)) != value:
                    wrong.append(f"{name} {at}: {value} is not how Python writes {float(value)!r}")
            elif NUMBER_TEXT.match(value):
                wrong.append(f"{name} {at}: the number {value!r} is written as a string")
    assert not wrong, "\n".join(wrong[:20])


def test_json_text_and_the_key_tests_are_as_main_had_them() -> None:
    from poisson_trace import report

    source = inspect.getsource(report.json_text)
    assert hashlib.sha256(source.encode("utf-8")).hexdigest() == JSON_TEXT, source
    lines = dict(reversed(line.split("  ", 1)) for line in (REPO / "tests" / "frozen.sha256").read_text(encoding="utf-8").splitlines())
    for name, digest in KEY_TESTS.items():
        assert lines.get(name) == digest, f"{name}'s line in tests/frozen.sha256 moved"
        assert hashlib.sha256((REPO / name).read_bytes()).hexdigest() == digest, f"{name} changed"


def test_no_schema_id_changes() -> None:
    found = set()
    for folder, pattern in (("src", "*.py"), ("docs", "*.md")):
        for path in (REPO / folder).rglob(pattern):
            found.update(re.findall(r"poisson-trace\.[a-z-]+/\d+", path.read_text(encoding="utf-8")))
    assert found == SCHEMAS, f"schema ids added {sorted(found - SCHEMAS)}, gone {sorted(SCHEMAS - found)}"


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def test_the_handover_page_promises_the_same_bytes_on_macos_and_linux() -> None:
    page = (REPO / "docs" / "handover.md").read_text(encoding="utf-8")
    found = re.search(r"^## What `result\.json` promises\n(.*?)(?=^## )", page, re.S | re.M)
    assert found, "docs/handover.md has no section What `result.json` promises"
    section = _flat(found.group(1))
    assert PROMISE in section, "the section does not hold the platform sentence word for word"
    assert OLD_PROMISE not in section, "the section still holds the sentence that names no platform"


def test_the_changelog_says_the_last_digits_moved() -> None:
    log = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    found = re.search(r"^## [^\n]*unreleased[^\n]*\n(.*?)(?=^## |\Z)", log, re.S | re.M | re.I)
    assert found, "CHANGELOG.md has no unreleased section"
    entries = [_flat(e) for e in re.split(r"^- ", found.group(1), flags=re.M)[1:]]
    wanted = ("--json", "result.json", "last digits", "macOS", "Linux")
    assert any(all(word in entry for word in wanted) for entry in entries), (
        f"no entry under the unreleased heading names all of {wanted}"
    )

