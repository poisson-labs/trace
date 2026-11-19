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

TF24-63's and TF24-65's runs of the page's and the recipe's marked blocks were cut on the ruling of
2026-11-18 (AR-7): ``test_tf5_blocks.py`` (TF5-14) runs the same page through the same runner.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from tf0_support import INTERNAL
from tf3_support import OLD, PAGES, REPO, blocks, fenced

TOOL = "langsmith"
PAGE = PAGES / "langsmith.md"
RECIPE = REPO / "docs" / "recipes" / "from-langsmith.md"
CAPTURES = "tests/fixtures/ingest/langsmith/"
INSTALL = "pip install poisson-trace"
VERSIONS = ("langsmith 0.14.17", "v0.3.13")
RUN_ID = re.compile(r"\b\d{8}T\d{6}Z-[0-9a-f]{4}\b")


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


# ---------- TF24-63 ----------


def test_tf24_63_no_marked_command_pulls() -> None:
    """Changed by the docs pair (TF5): a command that names the service's address stands in a
    block marked ``pull``, which is answered from the committed captures with no network
    (TF5-16); no other marked command names one."""
    from tf5_support import parse
    from tf5_support import words as commands_of

    for path in (PAGE, RECIPE):
        for block in parse(path.read_text(encoding="utf-8"))[0]:
            if block.kind == "command" and not block.pull:
                for words in commands_of(block):
                    assert not [w for w in words if w.startswith("langsmith:")], (path.name, words)


# ---------- TF24-64 ----------


def test_tf24_64_the_page_ends_with_what_it_does_not_do() -> None:
    heading, body = _last_section(PAGE.read_text(encoding="utf-8"))
    assert heading == "What this does not do", heading
    starts = [line for line in body if line.startswith("- ")]
    assert len(starts) == 4 and all(line.startswith(("- ", "  ")) for line in body), body
    joined = " ".join(body)
    assert "does not run" in joined and "one run" in joined and "0.14.17" in joined
    assert "keeps no prompt" in joined, joined


# ---------- TF24-65 ----------


def test_tf24_65_the_recipe_is_short_and_ends_with_what_it_does_not_do() -> None:
    assert RECIPE.is_file(), RECIPE
    text = RECIPE.read_text(encoding="utf-8")
    assert text.startswith("# ") and len(text.splitlines()) < 150, len(text.splitlines())
    heading, body = _last_section(text)
    assert heading == "What this does not do" and body, heading


def test_tf24_65_the_recipe_imports_twice_and_checks_the_fix() -> None:
    text = RECIPE.read_text(encoding="utf-8")
    commands = _commands(text)
    imports = [w for w in commands if w[:3] == ["poisson-trace", "import", TOOL]]
    assert len(imports) >= 2 and len(_imports_shown(text, ("output", "excerpt"))) >= 2, commands
    runs = [w[w.index("--run") + 1] for w in imports]
    assert len(set(runs)) == len(runs), runs
    checks = [w for w in commands if w[:2] == ["poisson-trace", "fix-check"]]
    assert checks and all(any(r in w for r in runs) for w in checks), commands
    assert commands.index(checks[0]) > commands.index(imports[1])
    marked = {b.body for b in blocks(text) if b.kind == "command"}
    for body in fenced(text):
        if body.lstrip().startswith("poisson-trace"):
            assert body in marked, body
    for words in commands:
        assert not any(RUN_ID.search(w) for w in words), words


@pytest.mark.parametrize("path", [PAGE, RECIPE], ids=["langsmith.md", "from-langsmith.md"])
def test_tf24_65_the_page_and_the_recipe_are_in_plain_words(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    found = INTERNAL.search(text)
    assert found is None, (path.name, found.group(0) if found else None)
    for body in fenced(text):
        assert OLD not in body, body
