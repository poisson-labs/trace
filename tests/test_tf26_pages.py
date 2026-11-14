"""TF26-61 to TF26-65: the reader's page and recipe (spec sections 6.1, the listing rule; 6.3, the
DeepEval page's shape; 6.4a, the four sentences; 7.1, the recipes; 7.2, plain words; and the facts
the captures correct, which the page must not repeat).

- TF26-61: ``docs/integrations/weave.md`` exists, of the other pages' shape: the one install
  line, the version that wrote the captures, and a command that imports a committed capture
  with the output Trace printed on it; its commands read the service's answer, the page's
  JSON or JSON Lines, and the page's table.
- TF26-62: the page says how an evaluation gets out, as the captures show it: the pull by
  ``weave:ENTITY/PROJECT/EVALUATION`` with ``WANDB_API_KEY``, what it asks (costs and feedback
  always, every call however old), where its raw copy goes and what is left out of it; and
  the Traces page's download, which must be filtered to the op
  ``Evaluation.predict_and_score`` to hold the cases, holds every evaluation of the project
  (``--evaluation``), and carries no cost and no feedback. It names no field where the
  captures do not hold it and no format the page does not offer.
- TF26-63: every marked block of the page holds when its commands are run in page order in a
  folder laid out as a clone, and no command of the page reaches for the network.
- TF26-64: the page ends with what it does not do: four sentences, one bullet each.
- TF26-65: ``docs/recipes/from-weave.md`` exists: under 150 lines, starting from the
  captures, importing twice and running ``fix-check``, every ``poisson-trace`` block marked and
  holding when run, no run named by its id, ending with ``What this does not do``; both files
  are in plain words.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from tf0_support import INTERNAL
from tf3_support import OLD, PAGES, REPO, blocks, fenced, holds_block, page_root, run_page, shims

TOOL = "weave"
PAGE = PAGES / "weave.md"
RECIPE = REPO / "docs" / "recipes" / "from-weave.md"
CAPTURES = "tests/fixtures/ingest/weave/"
INSTALL = "pip install poisson-trace"
VERSIONS = ("weave 0.54.1",)
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


def _no_network_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every command of a page runs with no key and with every proxy and Weave's own endpoint
    pointed at a closed port of this machine, so a command that reached for Weave would fail."""
    for name in ("WANDB_API_KEY", "BRAINTRUST_API_KEY", "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("WF_TRACE_SERVER_URL", "http://127.0.0.1:9")
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")


# ---------- TF26-61 ----------


def test_tf26_61_the_page_shows_a_capture_imported() -> None:
    assert PAGE.is_file(), PAGE
    text = PAGE.read_text(encoding="utf-8")
    assert text.startswith("# ") and "Weave" in text.splitlines()[0], text[:80]
    assert any(INSTALL in body.splitlines() for body in fenced(text)), "no install block"
    for version in VERSIONS:
        assert version in text, version
    assert _imports_shown(text), "weave.md shows no import of a capture with its whole output"


def test_tf26_61_the_page_shows_each_way_in_read(tmp_path: Path) -> None:
    """A command of the page reads the service's answer, one the page's JSON or JSON Lines, one
    its table; and a command that reads the page's download names the evaluation to read."""
    commands = _commands(PAGE.read_text(encoding="utf-8"))
    words = [w for command in commands for w in command if w.startswith(CAPTURES)]
    assert any("/api/" in w for w in words), words
    assert any("/ui/" in w and w.endswith((".json", ".jsonl")) for w in words), words
    assert any("/ui/" in w and w.endswith((".csv", ".tsv")) for w in words), words
    for command in commands:
        if any(w.startswith(CAPTURES + "ui/predict-and-score") for w in command):
            assert "--evaluation" in command, command


# ---------- TF26-62 ----------


def test_tf26_62_the_page_says_how_an_evaluation_gets_out_as_the_captures_show() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for said in ("WANDB_API_KEY", "weave:ENTITY/PROJECT/EVALUATION", ".poisson/raw/weave/", "raw.jsonl", "pull.json", "--keep-raw-text",
                 "/calls/stream_query", "include_costs", "include_feedback", "JSON", "CSV", "TSV", "WF_TRACE_SERVER_URL", "--case-from",
                 "--outcome-from", "--evaluation", "--page-size", "--case-from input", "score:KEY", "example:KEY",
                 "Evaluation.predict_and_score", "summary.weave.costs", "model_latency"):
        assert said in text, said
    # the Traces page with no filter gives one row an evaluation: the page says to filter it
    assert re.search(r"(?i)\bfilter", text), "the Traces page must be filtered to the op"
    # every call however old, and what the page's downloads do not carry
    assert re.search(r"(?i)however old", text)
    assert re.search(r"(?i)no\s+cost", text) and re.search(r"(?i)no\s+feedback", text), "the page's downloads carry neither"
    # a case whose model raised has no score; true is 1 and false is 0
    assert re.search(r"(?i)has no\s+score", text), "an errored case has no score"
    assert re.search(r"(?i)true\s+(?:is|as)\s+1", text), "true is read as 1"
    # what the captures correct is not repeated
    assert not re.search(r"summary\.costs|summary\.feedback", text), "costs and feedback are under summary.weave"
    assert not re.search(r"(?i)parquet", text) or re.search(r"(?i)no parquet", text), "the Traces page offers no Parquet"
    assert "op_or_eval" not in text and "--from-api" not in text and "time to first token" in text.lower()


# ---------- TF26-63 ----------


def test_tf26_63_every_marked_block_of_the_page_holds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_network_env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    home.mkdir()
    checked = run_page(PAGE, page_root(tmp_path), home, shims(tmp_path / "bin"))
    assert checked, "weave.md has no marked output"
    for c in checked:
        assert holds_block(c), f"weave.md:{c.block.line}: {c.command} -> exit {c.code}\n--- block\n{c.block.body}\n--- printed\n{c.printed}"


def test_tf26_63_no_marked_command_pulls() -> None:
    """Changed by the docs pair (TF5): a command that names the service's address stands in a
    block marked ``pull``, which is answered from the committed captures with no network
    (TF5-16); no other marked command names one."""
    from tf5_support import parse
    from tf5_support import words as commands_of

    for path in (PAGE, RECIPE):
        for block in parse(path.read_text(encoding="utf-8"))[0]:
            if block.kind == "command" and not block.pull:
                for words in commands_of(block):
                    assert not [w for w in words if w.startswith("weave:")], (path.name, words)


# ---------- TF26-64 ----------


def test_tf26_64_the_page_ends_with_what_it_does_not_do() -> None:
    heading, body = _last_section(PAGE.read_text(encoding="utf-8"))
    assert heading == "What this does not do", heading
    starts = [line for line in body if line.startswith("- ")]
    assert len(starts) == 4 and all(line.startswith(("- ", "  ")) for line in body), body
    joined = " ".join(body)
    assert "does not run" in joined and "one run" in joined and "0.54.1" in joined
    assert "keeps no prompt" in joined, joined


# ---------- TF26-65 ----------


def test_tf26_65_the_recipe_is_short_and_ends_with_what_it_does_not_do() -> None:
    assert RECIPE.is_file(), RECIPE
    text = RECIPE.read_text(encoding="utf-8")
    assert text.startswith("# ") and len(text.splitlines()) < 150, len(text.splitlines())
    heading, body = _last_section(text)
    assert heading == "What this does not do" and body, heading


def test_tf26_65_the_recipe_imports_twice_and_checks_the_fix() -> None:
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


def test_tf26_65_every_marked_block_of_the_recipe_holds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_network_env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    home.mkdir()
    checked = run_page(RECIPE, page_root(tmp_path), home, shims(tmp_path / "bin"))
    assert checked, "from-weave.md has no marked output"
    for c in checked:
        assert holds_block(c), f"from-weave.md:{c.block.line}: {c.command} -> exit {c.code}\n--- block\n{c.block.body}\n--- printed\n{c.printed}"


@pytest.mark.parametrize("path", [PAGE, RECIPE], ids=["weave.md", "from-weave.md"])
def test_tf26_65_the_page_and_the_recipe_are_in_plain_words(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    found = INTERNAL.search(text)
    assert found is None, (path.name, found.group(0) if found else None)
    for body in fenced(text):
        assert OLD not in body, body
