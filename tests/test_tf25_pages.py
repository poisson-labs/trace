"""TF25-61 to TF25-65: the reader's page and recipe (spec sections 6.1, the listing rule; 6.3, the
DeepEval page's shape; 6.4a, the four sentences; 7.1, the recipes; 7.2, plain words; and the facts
the captures correct, which the page must not repeat).

- TF25-61: ``docs/integrations/braintrust.md`` exists, of the other pages' shape: the one
  install line, the version that wrote the captures, and a command that imports a committed
  capture with the output Trace printed on it; its commands read the API's answer, the page's
  JSON and the page's CSV.
- TF25-62: the page says how an experiment gets out, as the captures show it: the pull by
  ``braintrust:PROJECT/EXPERIMENT`` with ``BRAINTRUST_API_KEY``, where its raw copy goes and
  what is left out of it; and the page's download, JSON or CSV, which holds no id, so that two
  versions pair by the input. It names no record field the captures do not hold and writes no
  address by an experiment's id.
- TF25-63: every marked block of the page holds when its commands are run in page order in a
  folder laid out as a clone, and no command of the page reaches for the network.
- TF25-64: the page ends with what it does not do: four sentences, one bullet each.
- TF25-65: ``docs/recipes/from-braintrust.md`` exists: under 150 lines, starting from the
  captures, importing twice and running ``fix-check``, every ``poisson-trace`` block marked and
  holding when run, no run named by its id, ending with ``What this does not do``; both files
  are in plain words.

What TF25-63 and TF25-65 say is held for these two files where every page's is: the marked
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

TOOL = "braintrust"
PAGE = PAGES / "braintrust.md"
CAPTURES = "tests/fixtures/ingest/braintrust/"
INSTALL = "pip install poisson-trace"
VERSIONS = ("braintrust 0.49.3",)


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


# ---------- TF25-61 ----------


def test_tf25_61_the_page_shows_a_capture_imported() -> None:
    assert PAGE.is_file(), PAGE
    text = PAGE.read_text(encoding="utf-8")
    assert text.startswith("# Braintrust\n"), text[:80]
    assert any(INSTALL in body.splitlines() for body in fenced(text)), "no install block"
    for version in VERSIONS:
        assert version in text, version
    assert _imports_shown(text), "braintrust.md shows no import of a capture with its whole output"


def test_tf25_61_the_page_shows_each_way_in_read(tmp_path: Path) -> None:
    """A command of the page reads the API's answer, one the page's JSON, one its CSV."""
    words = [w for command in _commands(PAGE.read_text(encoding="utf-8")) for w in command if w.startswith(CAPTURES)]
    assert any("/api/" in w for w in words), words
    assert any("/ui/" in w and w.endswith(".json") for w in words), words
    assert any("/ui/" in w and w.endswith(".csv") for w in words), words


# ---------- TF25-62 ----------


def test_tf25_62_the_page_says_how_an_experiment_gets_out_as_the_captures_show() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for said in ("BRAINTRUST_API_KEY", "braintrust:PROJECT/EXPERIMENT", ".poisson/raw/braintrust/", "raw.jsonl", "pull.json",
                 "--keep-raw-text", "/v1/experiment", "fetch", "JSON", "CSV", "BRAINTRUST_API_URL", "--case-from", "--outcome-from",
                 "--select", "--page-size", "--case-from input", "score:KEY", "record"):
        assert said in text, said
    assert re.search(r"root span", text)
    # the page's download carries no id, and the page says so where it says how versions pair
    assert re.search(r"(?i)\bno id\b", text), "the page's download holds no id"
    # every event however old, and what the raw copy leaves out beyond the inputs and outputs
    assert re.search(r"(?i)however old", text) and "context" in text and "audit_data" in text
    # an errored case has no score and no metadata
    assert re.search(r"(?i)ended in error has no\s+score", text), "an errored case has no score"
    # what the captures correct is not repeated
    assert "dataset_record_id" not in text
    assert not re.search(r"braintrust:(?:exp_|<experiment_id>|[0-9a-f]{8}-)", text)
    assert "--from-api" not in text


# ---------- TF25-64 ----------


def test_tf25_64_the_page_ends_with_what_it_does_not_do() -> None:
    heading, body = _last_section(PAGE.read_text(encoding="utf-8"))
    assert heading == "What this does not do", heading
    starts = [line for line in body if line.startswith("- ")]
    assert len(starts) == 4 and all(line.startswith(("- ", "  ")) for line in body), body
    joined = " ".join(body)
    assert "does not run" in joined and "one run" in joined and "0.49.3" in joined
    assert "keeps no prompt" in joined, joined
