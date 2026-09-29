"""IC2: the case id; and the rule that cut.py and rows.py use the standard library only."""

from __future__ import annotations

import ast
import hashlib
import re
import sys

from hypothesis import given, settings
from hypothesis import strategies as st
from support import INGEST

from poisson_trace.ingest.rows import case_id


def _digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def test_ic2_a_printable_text_of_80_characters_or_fewer_is_its_own_id() -> None:
    for text in ("HumanEval/129@0.7", "a", "x" * 80, "two words", "café", "position-like:3", "日本語の質問"):
        assert case_id(text) == text


def test_ic2_a_longer_or_unprintable_text_is_sha256_and_16_hex() -> None:
    for text in ("x" * 81, "é" * 81, "line\nbreak", "tab\there", "nul\x00", "​" * 3):
        got = case_id(text)
        assert got == _digest(text)
        assert re.fullmatch(r"sha256:[0-9a-f]{16}", got)


@settings(max_examples=400, deadline=None)
@given(st.text(min_size=1, max_size=160))
def test_ic2_the_rule_holds_for_any_text(text: str) -> None:
    got = case_id(text)
    if len(text) <= 80 and text.isprintable():
        assert got == text
    else:
        assert got == _digest(text)
    assert got != ""
    assert case_id(str(text)) == got


def test_ic2_it_never_returns_an_empty_string() -> None:
    try:
        got = case_id("")
    except ValueError:
        return
    assert got != ""


def _imports(path) -> list[str]:  # type: ignore[no-untyped-def]
    out = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.append(node.module)
    return out


def test_ic8_cut_and_rows_import_the_standard_library_only() -> None:
    """Green by construction on the skeleton: a static rule over two files."""
    for name in ("cut.py", "rows.py"):
        for module in _imports(INGEST / name):
            top = module.split(".")[0]
            assert top == "__future__" or top in sys.stdlib_module_names, (name, module)


def test_s22_run_carries_the_readers_counts_empty_by_default() -> None:
    """Ruled 2026-09-29 (Session A ruling 3). Green by construction on the skeleton that has it."""
    from poisson_trace.ingest.rows import Run

    base = {"name": "r", "tool": "deepeval", "rows": (), "started": "2026-01-01T00:00:00Z",
            "started_from": "given", "declared": {}, "files": ()}
    assert dict(Run(**base).counts) == {}
    assert dict(Run(**base, counts={"without this metric": 2}).counts) == {"without this metric": 2}
