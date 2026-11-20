"""TF0-1, TF0-19 and TF0-20: the look held over the whole corpus, and the written standard
(``docs/cli-look.md``).

Every invocation of the corpus (every verb's help, the version, the README's worked examples on
the fixtures, two imports and their fix check, a set of common user mistakes and the paths that
ended in a traceback) is held to the rules a test can see:
the exit code is in the table and is the one the invocation calls for; no traceback; stderr is
``error:`` and ``note:`` lines and their two-space continuations; a refusal or a wrong command
line prints nothing on stdout; nothing a user reads holds a Python representation of a value;
``--json`` is one strict document with ``schema`` first; a ``next:`` line closes stdout. And the
two clauses TF1 builds: a result's first stdout line is its verdict line, and
``--json`` opens ``schema``, ``verdict``, ``sentence``.

``docs/cli-look.md`` is the written standard: its sixteen rules in order and the exit-code table
the commands keep."""

from __future__ import annotations

import json
import re

import pytest

from tf0_support import CLI_LOOK, EXIT_CODES, REPR, VERDICT_LINE, Item, Ran, corpus, corpus_ran, doc_exit_codes, stderr_shape

CORPUS = corpus()


@pytest.fixture(scope="module")
def ran(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Ran]:
    return corpus_ran(tmp_path_factory)


def _held(item: Item, result: Ran) -> list[str]:
    """What breaks the look in one invocation, as sentences; empty when it holds."""
    broken = []
    if result.code not in EXIT_CODES:
        broken.append(f"exit {result.code} is not in the table")
    if result.code != item.expect:
        broken.append(f"exit {result.code}, where {item.expect} is called for")
    if "Traceback" in result.text:
        broken.append("a traceback")
    bad = stderr_shape(result.lines())
    if bad:
        broken.append(f"stderr lines that are not error:, note: or a continuation: {bad[:2]}")
    if result.code in (1, 2):
        if result.out:
            broken.append("stdout written on a refusal")
        if not result.err.startswith("error: "):
            broken.append("a refusal that does not open with error:")
    if REPR.search(result.text):
        broken.append(f"a Python representation: {REPR.search(result.text).group(0)!r}")  # type: ignore[union-attr]
    if "--json" in item.argv and result.code == 0:
        try:
            doc = json.loads(result.out, parse_constant=_refuse)
        except ValueError as e:
            broken.append(f"--json is not one strict document: {e}")
        else:
            if not isinstance(doc, dict) or next(iter(doc), None) != "schema":
                broken.append("--json does not open with schema")
            elif list(doc)[:3] != ["schema", "verdict", "sentence"]:
                broken.append("--json does not open with schema, verdict and sentence")
    if item.kind == "report" and result.code == 0 and "--json" not in item.argv:
        first = result.lines("out")[:1]
        if not first or not VERDICT_LINE.match(first[0]):
            broken.append("the first stdout line is not a verdict line")
    lines = result.lines("out")
    nexts = [i for i, line in enumerate(lines) if line.startswith("next:")]
    if nexts and nexts != [len(lines) - 1]:
        broken.append("a next: line that does not close stdout")
    if item.kind == "help" and not result.out.startswith("usage:"):
        broken.append("help that does not open with usage")
    return broken


def _refuse(name: str) -> object:
    raise ValueError(f"{name} is not a JSON number")


@pytest.mark.parametrize("kind", ["report", "help", "version", "refusal", "usage"])
def test_tf0_19_the_corpus_holds_the_look(ran: dict[str, Ran], kind: str) -> None:
    broken = {item.label: _held(item, ran[item.label]) for item in CORPUS if item.kind == kind}
    broken = {label: why for label, why in broken.items() if why}
    assert broken == {}, broken


# ---------- TF0-1 and TF0-20: the written standard ----------


def test_tf0_20_the_standard_is_in_the_repository_with_its_sixteen_rules_in_order() -> None:
    text = CLI_LOOK.read_text(encoding="utf-8")
    # each rule opens a line, numbered "L1." or "1."
    first = {}
    for m in re.finditer(r"(?m)^\s*(?:[-*]\s+)?(?:\*\*)?L?(1[0-6]|[1-9])\.\s", text):
        first.setdefault(int(m.group(1)), m.start())
    assert sorted(first) == list(range(1, 17)), sorted(first)
    assert [n for n, _ in sorted(first.items(), key=lambda kv: kv[1])] == list(range(1, 17))


def test_tf0_01_the_exit_codes_the_standard_writes_are_the_table() -> None:
    codes = doc_exit_codes(CLI_LOOK.read_text(encoding="utf-8"))
    assert codes == sorted(EXIT_CODES), codes
