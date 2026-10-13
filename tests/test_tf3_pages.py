"""TF3-32 to TF3-34: the readers' pages (spec sections 6.1 and 6.3, the listing rule; section 5.1,
ruled 2026-10-12: every documented example uses ``poisson-trace import``).

- TF3-32: ``docs/integrations/table.md`` and ``docs/integrations/junit.md`` exist, of the DeepEval
  page's shape: the install lines, and a command that imports the committed fixture with the
  output Trace printed on it. Every marked block of the four integration pages holds when its
  commands are run, in page order, in a folder laid out as a clone: an output block is the whole
  of what the command printed, an excerpt a run of its lines, each with its exit code.
- TF3-33: no command or output block of the README or of any page under ``docs/`` spells
  ``poisson-trace-import``; a page may say in words that the alias exists.
- TF3-34: the JUnit page names the pytest version that wrote its fixture.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from tf3_support import OLD, PAGES, REPO, blocks, fenced, holds_block, page_root, run_page, shims

FIXTURE = {"table": "tests/fixtures/ingest/table/humaneval-a.csv", "junit": "tests/fixtures/ingest/junit/humaneval-a.xml"}
INSTALL = ("pip install poisson-trace", "pip install git+https://github.com/poisson-labs/prove")


@pytest.mark.parametrize("tool", ["table", "junit"])
def test_tf3_32_each_new_reader_has_a_page_showing_its_fixture(tool: str) -> None:
    page = PAGES / f"{tool}.md"
    assert page.is_file(), page
    text = page.read_text(encoding="utf-8")
    assert text.startswith("# "), text[:80]
    assert any(all(line in body.splitlines() for line in INSTALL) for body in fenced(text)), "no install block"
    marked = blocks(text)
    shown = False
    for i, block in enumerate(marked):
        if block.kind != "command":
            continue
        words = shlex.split(block.body.replace("\\\n", " "))
        if words[:3] == ["poisson-trace", "import", tool] and FIXTURE[tool] in words:
            following = marked[i + 1] if i + 1 < len(marked) else None
            shown = shown or (following is not None and following.kind == "output" and following.code == 0)
    assert shown, f"{page.name} shows no import of {FIXTURE[tool]} with its output"


@pytest.mark.parametrize("page", ["deepeval.md", "ragas.md", "table.md", "junit.md"])
def test_tf3_32_every_marked_block_of_the_page_holds(tmp_path: Path, page: str) -> None:
    path = PAGES / page
    assert path.is_file(), path
    home = tmp_path / "home"
    home.mkdir()
    checked = run_page(path, page_root(tmp_path), home, shims(tmp_path / "bin"))
    assert checked, f"{page} has no marked output"
    for c in checked:
        assert holds_block(c), f"{page}:{c.block.line}: {c.command} -> exit {c.code}\n--- block\n{c.block.body}\n--- printed\n{c.printed}"


@pytest.mark.parametrize("tool", ["table", "junit"])
def test_tf3_32_each_new_page_ends_with_what_it_does_not_do(tool: str) -> None:
    """The page's last section is four sentences, one bullet each, and nothing after them."""
    text = (PAGES / f"{tool}.md").read_text(encoding="utf-8").rstrip("\n")
    last = text.split("\n## ")[-1].split("\n")
    body = [line for line in last[1:] if line.strip()]
    starts = [line for line in body if line.startswith("- ")]
    assert len(starts) == 4 and all(line.startswith(("- ", "  ")) for line in body), last


def _documents() -> list[Path]:
    return [REPO / "README.md", *sorted((REPO / "docs").rglob("*.md"))]


def test_tf3_33_no_block_of_the_docs_spells_the_old_command() -> None:
    for path in _documents():
        for body in fenced(path.read_text(encoding="utf-8")):
            assert OLD not in body, f"{path.relative_to(REPO)}: {body[:200]}"


def test_tf3_34_the_junit_page_names_the_pytest_that_wrote_its_fixture() -> None:
    provenance = (REPO / "tests" / "fixtures" / "PROVENANCE.md").read_text(encoding="utf-8")
    section = next(s for s in provenance.split("\n## ") if s.startswith("Added for the JUnit import"))
    m = re.search(r"pytest (\d+\.\d+\.\d+)", section)
    assert m is not None, "the provenance names no pytest version"
    text = (PAGES / "junit.md").read_text(encoding="utf-8")
    assert f"pytest {m.group(1)}" in text
