"""TF5-70 to TF5-76: the recipes (spec section 7.1; the brief's rules 1 and 7). That each
recipe's blocks hold when run is TF5-14; that each source has its first result, TF5-18.

- TF5-70: every recipe is one page under 150 lines, written for a reader who has the data it
  names and nothing else: it opens by saying what the reader has and what it ends with, and
  ends with the section ``What this does not do``, a list.
- TF5-71: every block of a recipe that runs ``poisson-trace`` is run by the docs check, and a
  recipe shows something of what every such block printed.
- TF5-72: a recipe names its runs before it uses them: before any ``where``, ``compare``,
  ``fix-check`` or ``changes`` it has run ``init``, ``name`` or an import that names the run.
- TF5-73: ``check-a-fix.md``: the tau2 fixture; the recipe for checking a change (the old
  version re-run on the same inputs beside the new, as two Prove sweeps, shown and not run);
  then ``fix-check``, with its control shown.
- TF5-74: ``a-page-to-send.md`` and ``into-the-product.md``: a bundle written with ``--out``
  from the recorded demo's store; the page made with ``report``; the bundle's files listed;
  ``handover --check`` passing; each with what it printed.
- TF5-75: ``what-it-cannot-say.md``: from reports the recipe itself runs, the limit, the
  guidance and what the report cannot say, each as lines the command printed; one of a single
  run and one of a pair.
- TF5-76: the recipes link one another and the pages they lean on by paths that exist, and
  each tool's recipe links that tool's page.
"""

from __future__ import annotations

import re

import pytest

from tf5_support import RECIPES, Block, parse, prose, read, recipe, trace_commands, words

NAMES = list(RECIPES)
READS_RUNS = ("where", "compare", "fix-check", "changes")


def _blocks(name: str) -> list[Block]:
    return parse(read(recipe(name)))[0]


def _ran(block: Block) -> list[list[str]]:
    return trace_commands("<!-- command -->\n```\n" + block.body + "\n```\n")


def _shown_under(name: str, verb: str, code: int = 0) -> list[str]:
    """What the recipe shows printed under the blocks that run the verb, block by block."""
    blocks = _blocks(name)
    out = []
    for at, block in enumerate(blocks):
        if block.kind == "command" and any(command[:1] == [verb] for command in _ran(block)):
            for later in blocks[at + 1:]:
                if later.kind in ("command", "skip"):
                    break
                if later.kind in ("output", "excerpt") and later.code == code:
                    out.append(later.body)
    return out


# ---------- TF5-70 ----------


@pytest.mark.parametrize("name", NAMES)
def test_tf5_70_a_recipe_is_short_and_ends_with_what_it_does_not_do(name: str) -> None:
    text = read(recipe(name))
    lines = text.rstrip("\n").split("\n")
    assert lines[0].startswith("# ") and len(lines) < 150, len(lines)
    last = text.rstrip("\n").split("\n## ")[-1].split("\n")
    assert last[0] == "What this does not do", last[0]
    body = [line for line in last[1:] if line.strip()]
    assert body and all(line.startswith(("- ", "  ")) for line in body) and len([line for line in body if line.startswith("- ")]) >= 2, body
    opening = prose(text.split("\n## ")[0])
    assert len(opening.split()) >= 20, "it opens by saying what you have and what you will end with"


# ---------- TF5-71 ----------


@pytest.mark.parametrize("name", NAMES)
def test_tf5_71_every_trace_command_of_a_recipe_is_run_and_shown(name: str) -> None:
    blocks = _blocks(name)
    for at, block in enumerate(blocks):
        runs_trace = any(word in ("poisson-trace", "poisson-trace-import") and (at == 0 or command[at - 1] in ("&&", ";", "||"))
                         for command in words(block) for at, word in enumerate(command))
        if block.kind in ("skip", "data", "unmarked") and runs_trace:
            raise AssertionError(f"{name}:{block.line}: a poisson-trace command a recipe shows is run")
        if block.kind == "command" and runs_trace:
            following = next((later for later in blocks[at + 1:] if later.kind in ("command", "skip", "output", "excerpt")), None)
            assert following is not None and following.kind in ("output", "excerpt"), f"{name}:{block.line}: nothing of what this printed is shown"
    assert any(block.kind == "command" for block in blocks), name


# ---------- TF5-72 ----------


@pytest.mark.parametrize("name", NAMES)
def test_tf5_72_a_recipe_names_its_runs_before_it_reads_them(name: str) -> None:
    named = False
    for command in trace_commands(read(recipe(name))):
        if command[:1] in (["init"], ["name"]) or (command[:1] == ["import"] and "--run" in command):
            named = True
        if command[:1] and command[0] in READS_RUNS:
            assert named, f"{name}: {command[0]} before any init, name or import"


# ---------- TF5-73 ----------


def test_tf5_73_check_a_fix() -> None:
    name = "check-a-fix.md"
    text = read(recipe(name))
    assert "tests/fixtures/tau2" in text
    skipped = [block for block in _blocks(name) if block.kind == "skip"]
    assert any(re.search(r"(?m)^(?:poisson-)?prove\b", block.body) for block in skipped), "the two Prove sweeps, shown and not run"
    said = prose(text)
    assert re.search(r"(?i)same inputs", said) and re.search(r"(?i)side by side", said) and "--failing-from" in text
    control = [body for body in _shown_under(name, "fix-check") if "## The control" in body]
    assert control and any(line.startswith("|") for line in control[0].split("## The control")[1].split("\n")), "the control, with its table"
    assert re.search(r"(?i)\bcontrol\b", said), "and read aloud: a sentence on what the control shows"


# ---------- TF5-74 ----------


def test_tf5_74_a_page_to_send() -> None:
    name = "a-page-to-send.md"
    text = read(recipe(name))
    ran = trace_commands(text)
    assert "tests/fixtures/cs" in text
    assert any("--out" in command for command in ran), "a bundle"
    reports = [command for command in ran if command[:1] == ["report"]]
    assert reports and _shown_under(name, "report"), "report DIR, with what it printed"
    assert "report.html" in text and "`--open`" in prose(text), "the page, and how it is opened"


def test_tf5_74_into_the_product() -> None:
    name = "into-the-product.md"
    text = read(recipe(name))
    ran = trace_commands(text)
    assert "tests/fixtures/cs" in text
    assert any("--out" in command for command in ran)
    assert any(command[:2] == ["handover", "--check"] for command in ran) and _shown_under(name, "handover"), "the check, passing"
    listed = [block for block in _blocks(name) if block.kind in ("output", "excerpt") and block.code == 0
              and all(file in block.body for file in ("handover.json", "result.json", "report.md"))]
    assert listed, "what the bundle holds, listed by a command"
    assert "handover.md" in text


# ---------- TF5-75 ----------


def test_tf5_75_what_it_cannot_say() -> None:
    name = "what-it-cannot-say.md"
    single = "\n".join(_shown_under(name, "where"))
    pair = "\n".join(_shown_under(name, "fix-check"))
    assert "## What this cannot say" in single and re.search(r"(?m)^- ", single.split("## What this cannot say")[1]), "of a single run"
    assert "## What this cannot say" in pair and re.search(r"(?m)^- ", pair.split("## What this cannot say")[1]), "of a pair"
    assert "## What it could not have detected" in pair, "the limit"
    assert "## Guidance" in pair and re.search(r"(?m)^- ", pair.split("## Guidance")[1]), "the guidance"


# ---------- TF5-76 ----------


@pytest.mark.parametrize("name", NAMES)
def test_tf5_76_a_recipe_s_links_lead_somewhere(name: str) -> None:
    page = recipe(name)
    links = [link for link in re.findall(r"\]\(([^)\s]+)\)", prose(read(page))) if not link.startswith(("https://", "http://", "#", "mailto:"))]
    for link in links:
        assert (page.parent / link.split("#")[0]).resolve().exists(), f"{name}: {link}"
    tool = RECIPES[name]
    if tool not in (None, "prove"):
        assert f"../integrations/{tool}.md" in links, f"{name} links its tool's page"
