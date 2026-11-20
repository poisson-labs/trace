"""TF10-42 to TF10-46: each reader's page and recipe.

- TF10-42: ``docs/integrations/promptfoo.md``, ``inspect.md`` and ``openai-evals.md`` exist, of
  the DeepEval page's shape: the install line, which version of the tool wrote the fixture, a
  command that imports the committed fixture with the output Trace printed on it. Inspect's page
  shows the extra a ``.eval`` needs in a block after its Install section, and says a ``.eval`` is
  read whole into memory and one over 200 MB refused.
- TF10-44: each page ends with what it does not do: four sentences, one bullet each.
- TF10-45: ``docs/recipes/from-promptfoo.md``, ``from-inspect.md`` and ``from-openai-evals.md``
  exist: each under 150 lines, starting from the tool's own file, importing twice and running
  ``fix-check``, every ``poisson-trace`` block marked (an output in full or an excerpt of whole
  lines of it, so that the recipe stays short), no run named by its id, and ending with ``What
  this does not do``.
- TF10-46: the six files are in plain words: no internal id, no session or ruling word, and no
  block spells the import's old name.

The pages' and the recipes' marked blocks are run, in page order in a folder laid out as a
clone, by ``test_docs_blocks.py`` (TF5-14), through the runner every page shares.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from look_support import INTERNAL
from junit_table_support import OLD, PAGES, REPO, blocks, fenced

TOOLS = ("promptfoo", "inspect", "openai-evals")
RECIPES = REPO / "docs" / "recipes"
FIXTURE = {"promptfoo": ("tests/fixtures/ingest/promptfoo/results.json", "tests/fixtures/ingest/promptfoo/results.jsonl"),
           "inspect": ("tests/fixtures/ingest/inspect/2026-10-07T04-23-47-00-00_trace-fixture_CV3jq8f7FTjwkaYb3zj3m2.eval",
                       "tests/fixtures/ingest/inspect/2026-10-07T04-23-51-00-00_trace-fixture_2nSEDuHHzKiTUjJW3kXknY.json"),
           "openai-evals": ("tests/fixtures/ingest/openai-evals/old.jsonl", "tests/fixtures/ingest/openai-evals/new.jsonl")}
VERSION = {"promptfoo": "promptfoo 0.120.19", "inspect": "inspect_ai 0.3.277", "openai-evals": "evals 3.0.1.post1"}
# every page's Install section is the one line (as test_prove_floor_pages_and_stores.py holds it); the
# Inspect page shows the extra a .eval log needs in a block of its own after it
INSTALL = "pip install poisson-trace"
EXTRA = "pip install 'poisson-trace[inspect]'"
# a Prove run id, which no command a user types names
RUN_ID = re.compile(r"\b\d{8}T\d{6}Z-[0-9a-f]{4}\b")


def _page(tool: str) -> Path:
    return PAGES / f"{tool}.md"


def _recipe(tool: str) -> Path:
    return RECIPES / f"from-{tool}.md"


def _commands(text: str) -> list[list[str]]:
    return [shlex.split(b.body.replace("\\\n", " ")) for b in blocks(text) if b.kind == "command"]


def _imports_shown(text: str, tool: str, kinds: tuple[str, ...] = ("output",)) -> list[int]:
    """The indexes of the marked command blocks that import a committed fixture of the tool and
    are followed by their output (on a recipe, an excerpt of it will do), exit 0."""
    marked = blocks(text)
    shown = []
    for i, block in enumerate(marked):
        if block.kind != "command":
            continue
        words = shlex.split(block.body.replace("\\\n", " "))
        if words[:3] == ["poisson-trace", "import", tool] and any(f in words for f in FIXTURE[tool]):
            following = marked[i + 1] if i + 1 < len(marked) else None
            if following is not None and following.kind in kinds and following.code == 0:
                shown.append(i)
    return shown


def _last_section(text: str) -> tuple[str, list[str]]:
    last = text.rstrip("\n").split("\n## ")[-1].split("\n")
    return last[0], [line for line in last[1:] if line.strip()]


# ---------- TF10-42 ----------


@pytest.mark.parametrize("tool", TOOLS)
def test_tf10_42_each_reader_has_a_page_showing_its_fixture(tool: str) -> None:
    page = _page(tool)
    assert page.is_file(), page
    text = page.read_text(encoding="utf-8")
    assert text.startswith("# "), text[:80]
    assert any(INSTALL in body.splitlines() for body in fenced(text)), "no install block"
    assert any(EXTRA in body.splitlines() for body in fenced(text)) == (tool == "inspect"), "the extra"
    assert VERSION[tool] in text, VERSION[tool]
    assert _imports_shown(text, tool), f"{page.name} shows no import of its fixture with its output"


def test_tf10_42_the_inspect_page_says_how_a_eval_is_read() -> None:
    text = _page("inspect").read_text(encoding="utf-8")
    assert "memory" in text and "200 MB" in text and "zstandard" in text.lower(), text
    assert "inspect log convert" in text


def test_tf10_42_the_promptfoo_page_names_the_json_export_and_the_csv() -> None:
    text = _page("promptfoo").read_text(encoding="utf-8")
    assert "-o results.json" in text and "--prompt" in text and ".csv" in text


# ---------- TF10-44 ----------


@pytest.mark.parametrize("tool", TOOLS)
def test_tf10_44_each_page_ends_with_what_it_does_not_do(tool: str) -> None:
    heading, body = _last_section(_page(tool).read_text(encoding="utf-8"))
    assert heading == "What this does not do", heading
    starts = [line for line in body if line.startswith("- ")]
    assert len(starts) == 4 and all(line.startswith(("- ", "  ")) for line in body), body
    joined = " ".join(body)
    assert "does not run" in joined and "one run" in joined and VERSION[tool].split()[1] in joined
    assert "keeps no prompt" in joined, joined


# ---------- TF10-45 ----------


@pytest.mark.parametrize("tool", TOOLS)
def test_tf10_45_each_recipe_is_short_and_ends_with_what_it_does_not_do(tool: str) -> None:
    path = _recipe(tool)
    assert path.is_file(), path
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# ") and len(text.splitlines()) < 150, len(text.splitlines())
    heading, body = _last_section(text)
    assert heading == "What this does not do" and body, heading


@pytest.mark.parametrize("tool", TOOLS)
def test_tf10_45_each_recipe_imports_twice_and_checks_the_fix(tool: str) -> None:
    text = _recipe(tool).read_text(encoding="utf-8")
    commands = _commands(text)
    imports = [w for w in commands if w[:3] == ["poisson-trace", "import", tool]]
    assert len(imports) >= 2 and len(_imports_shown(text, tool, ("output", "excerpt"))) >= 2, commands
    runs = [w[w.index("--run") + 1] for w in imports]
    assert len(set(runs)) == len(runs), runs
    checks = [w for w in commands if w[:2] == ["poisson-trace", "fix-check"]]
    assert checks and all(any(r in w for r in runs) for w in checks), commands
    assert commands.index(checks[0]) > commands.index(imports[1])
    # every fenced block that runs poisson-trace is marked, so the runner runs it
    marked = {b.body for b in blocks(text) if b.kind == "command"}
    for body in fenced(text):
        if body.lstrip().startswith("poisson-trace"):
            assert body in marked, body
    for words in commands:
        assert not any(RUN_ID.search(w) for w in words), words


# ---------- TF10-46 ----------


@pytest.mark.parametrize("path", [*(PAGES / f"{t}.md" for t in TOOLS), *(RECIPES / f"from-{t}.md" for t in TOOLS)],
                         ids=[*(f"{t}.md" for t in TOOLS), *(f"from-{t}.md" for t in TOOLS)])
def test_tf10_46_the_pages_are_in_plain_words(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    found = INTERNAL.search(text)
    assert found is None, (path.name, found.group(0) if found else None)
    for body in fenced(text):
        assert OLD not in body, body
