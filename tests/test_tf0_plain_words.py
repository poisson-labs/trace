"""TF0-21: plain words in everything a user reads (spec section 7.2 and rule L11).

No spec, invariant or test-group number (TR, IT, IL, IC, ID, IR, FD, LST, TF and the rest), no
decision number, no session name, and none of the words that only mean something inside the lab,
in the README, the CHANGELOG, every file under docs/ but the two standards (kept byte for byte
as the lab writes them), every string a user can meet in the source (help text, refusals,
report text: every literal that is not a docstring), and every output of the corpus: help,
version, results and errors of both commands. The pattern is the Tasks test's, copied, with
Trace's own identifiers."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tf0_support import INTERNAL, REPO, Ran, corpus_ran, plain

STANDARDS = {"cli-look.md", "repo-hygiene.md"}


def _user_files() -> list[Path]:
    docs = sorted(p for p in (REPO / "docs").rglob("*.md") if p.name not in STANDARDS)
    return [REPO / "README.md", REPO / "CHANGELOG.md", *docs]


def _literals(path: Path) -> list[tuple[int, str]]:
    """Every string literal that is not a bare statement (so not a docstring), with its line;
    the literal parts of f-strings included."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bare = {id(node.value) for node in ast.walk(tree) if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)}
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in bare
    ]


@pytest.mark.parametrize("path", _user_files(), ids=lambda p: str(p.relative_to(REPO)))
def test_tf0_21_the_users_files_are_in_plain_words(path: Path) -> None:
    assert plain(path.read_text(encoding="utf-8")) == []


def test_tf0_21_every_string_the_source_can_show_is_in_plain_words() -> None:
    import poisson_trace

    package = Path(poisson_trace.__file__).resolve().parent
    hits = [
        (str(path.relative_to(package)), line, text[:100])
        for path in sorted(package.rglob("*.py"))
        for line, text in _literals(path)
        if INTERNAL.search(text)
    ]
    assert hits == []


@pytest.fixture(scope="module")
def outputs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Ran]:
    return corpus_ran(tmp_path_factory)


def test_tf0_21_every_output_of_the_corpus_is_in_plain_words(outputs: dict[str, Ran]) -> None:
    for internal in ("TR11", "IC10", "ID13", "IR5", "FD8", "LST2", "TF0", "R17", "Session A", "frozen", "the vault", "§9.2", "Taylor", "ruling"):
        assert INTERNAL.search(internal), f"the pattern misses {internal}"
    for fine in ("20260915T210140Z-4847", "gpt-4.1-mini", "HumanEval/129", "poisson-trace 0.1.0", "Python 3.11.7", "p = 2.3e-08", "B = 1,000", "S(20)"):
        assert not INTERNAL.search(fine), f"the pattern catches {fine}"
    hits = {label: plain(result.text) for label, result in outputs.items() if plain(result.text)}
    assert hits == {}, hits
