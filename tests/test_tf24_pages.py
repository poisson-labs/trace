"""TF24-61 to TF24-65: the reader's page and recipe (spec sections 6.1, the listing rule; 6.3, the
DeepEval page's shape; 6.4a, the four sentences; 7.1, the recipes; 7.2, plain words; and the three
facts the captures correct, which the page must not repeat).

- TF24-61: ``docs/integrations/langsmith.md`` exists, of the other pages' shape: the one install
  line, the versions that wrote the captures (the SDK's and the command's), and a command that
  imports a committed capture with the output Trace printed on it.
- TF24-62: the page says how the runs get out, as the captures show it: the pull by
  ``langsmith:NAME`` with ``LANGSMITH_API_KEY``, where its raw copy goes and that the text is
  left out of it; the command's exports with ``--full``, whose trace export is a folder; and the
  page's download, which is CSV, with the root run alone. It claims no JSON download from the
  page.
- TF24-63: every marked block of the page holds when its commands are run in page order in a
  folder laid out as a clone, and no command of the page reaches for the network.
- TF24-64: the page ends with what it does not do: four sentences, one bullet each.
- TF24-65: ``docs/recipes/from-langsmith.md`` exists: under 150 lines, starting from the
  captures, importing twice and running ``fix-check``, every ``poisson-trace`` block marked and
  holding when run, no run named by its id, ending with ``What this does not do``; both files
  are in plain words.

What TF24-63 and TF24-65 say is held for these two files where every page's is: the marked
blocks are run by ``test_tf5_blocks.py`` (TF5-14), which also holds that a service is asked only
in a block marked pull (TF5-16), that no run is named by its id (TF5-17) and that the recipe
imports twice and checks the fix on those runs (TF5-18); ``test_tf5_recipes.py`` holds the
recipe's length, its last section and its marked commands (TF5-70, TF5-71);
``test_tf0_plain_words.py`` (TF0-21) and ``test_tf3_pages.py`` (TF3-33) hold the plain words.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from tf3_support import PAGES, REPO, blocks, fenced

TOOL = "langsmith"
PAGE = PAGES / "langsmith.md"
CAPTURES = "tests/fixtures/ingest/langsmith/"
INSTALL = "pip install poisson-trace"
VERSIONS = ("langsmith 0.14.17", "v0.3.13")


def _commands(text: str) -> list[list[str]]:
    return [shlex.split(b.body.replace("\\\n", " ")) for b in blocks(text) if b.kind == "command"]


def _imports_shown(text: str, kinds: tuple[str, ...] = ("output",)) -> list[int]:
    """The marked command blocks that import a committed capture and are followed by their
    output (on a recipe, an excerpt of it will do), exit 0."""
    marked = blocks(text)
    shown = []
    for i, block in enumerate(marked):
        if block.kind != "command":
            continue
        words = shlex.split(block.body.replace("\\\n", " "))
        if words[:3] == ["poisson-trace", "import", TOOL] and any(w.startswith(CAPTURES) and (REPO / w).exists() for w in words):
            following = marked[i + 1] if i + 1 < len(marked) else None
            if following is not None and following.kind in kinds and following.code == 0:
                shown.append(i)
    return shown


def _last_section(text: str) -> tuple[str, list[str]]:
    last = text.rstrip("\n").split("\n## ")[-1].split("\n")
    return last[0], [line for line in last[1:] if line.strip()]


# ---------- TF24-61 ----------


def test_tf24_61_the_page_shows_a_capture_imported() -> None:
    assert PAGE.is_file(), PAGE
    text = PAGE.read_text(encoding="utf-8")
    assert text.startswith("# LangSmith\n"), text[:80]
    assert any(INSTALL in body.splitlines() for body in fenced(text)), "no install block"
    for version in VERSIONS:
        assert version in text, version
    assert _imports_shown(text), "langsmith.md shows no import of a capture with its whole output"


def test_tf24_61_the_page_shows_each_way_in_read(tmp_path: Path) -> None:
    """A command of the page reads the API's answer, one the command's export, one the CSV."""
    words = [w for command in _commands(PAGE.read_text(encoding="utf-8")) for w in command if w.startswith(CAPTURES)]
    for part in ("/api/", "/cli/", "/ui/"):
        assert any(part in w for w in words), (part, words)


# ---------- TF24-62 ----------


def test_tf24_62_the_page_says_how_the_runs_get_out_as_the_captures_show() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for said in ("LANGSMITH_API_KEY", "langsmith:", ".poisson/raw/langsmith/", "raw.jsonl", "pull.json", "--keep-raw-text",
                 "/api/v2/runs/query", "/api/v1/feedback", "--full", "CSV", "LANGSMITH_ENDPOINT", "--case-from", "--outcome-from",
                 "--select"):
        assert said in text, said
    assert re.search(r"langsmith runs? export \S+\.jsonl", text), "the run export's file"
    assert re.search(r"langsmith traces? export ", text) and "folder" in text
    assert re.search(r"root run", text)
    # the three facts the captures correct are not repeated
    assert not re.search(r"(?i)\bJSON (?:download|export) from the (?:UI|page)|CSV(?: or |/| and )JSON", text)
    assert not re.search(r"<trace_id>\.json\b(?!l)", text)
    assert "SUCCESS" not in text and "ERROR" not in text.replace("ERROR_MAX", "")


# ---------- TF24-64 ----------


def test_tf24_64_the_page_ends_with_what_it_does_not_do() -> None:
    heading, body = _last_section(PAGE.read_text(encoding="utf-8"))
    assert heading == "What this does not do", heading
    starts = [line for line in body if line.startswith("- ")]
    assert len(starts) == 4 and all(line.startswith(("- ", "  ")) for line in body), body
    joined = " ".join(body)
    assert "does not run" in joined and "one run" in joined and "0.14.17" in joined
    assert "keeps no prompt" in joined, joined
