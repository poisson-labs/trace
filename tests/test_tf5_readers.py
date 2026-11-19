"""TF5-20 to TF5-25: every page that lists the readers lists them all, the same way (the
brief's rule 2; B-6, BT-44, WV-50), and help, ``doctor`` and ``init`` agree with the pages.

Trace reads eleven sources: Prove's stored runs, and ten tools' files (``tf5_support.TOOLS``,
in the one order every listing gives them: deepeval, ragas, table, junit, promptfoo, inspect,
openai-evals, langsmith, braintrust, weave).

- TF5-20: the order is the install's own: the readers the package registers, the tools the
  import's help lists, ``doctor``'s readers line and the refusal of a tool the install lacks
  all give the ten in that order, as main does (the pins); and ``init`` finds a file of every
  one of the ten.
- TF5-21: on every page, the agent skill and the contributing page: a passage (a paragraph, a
  list or a table) that names three or more of the tools names all ten, in that order by where
  each is first named; and one that writes three or more of their command words in code writes
  all ten. A passage about the three services alone (LangSmith, Braintrust,
  Weave) is not a list of the readers. In a block that is shown and not run, the same holds
  line by line.
- TF5-22: the pages that must carry such a list carry one: the README, ``docs/commands.md``,
  ``docs/config.md``, ``docs/setup-with-your-agent.md``, ``docs/python.md`` and the agent
  skill; and the README has one that opens with Prove's stored runs, so all eleven are named
  together.
- TF5-23: the README's section on the other tools gives each of the ten a line of its own
  that links its page, and every integration page says under what rule a tool is listed.
- TF5-24: no page counts the readers wrong: a count of readers, tools or sources written as a
  word or a figure is ten (the tools) or eleven (with Prove's stored runs), or it is the three
  that pull.
- TF5-25: every tool's page is reachable from ``docs/commands.md``'s section on the import.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tf5_pins import EVERY_LABEL, EVERY_TOOL, PINS
from tf5_support import (
    API_TOOLS, CONTRIBUTING, DOCS, GITHUB, INTEGRATIONS, README, REPO, TOOLS, WORDS, expected_pages, lists_readers, named, parse,
    passages, prose, read, rel, sections,
)

PINNED: dict[str, Any] = json.loads(PINS.read_text(encoding="utf-8"))
SKILL = REPO / "src" / "poisson_trace" / "skills" / "poisson-trace-setup" / "SKILL.md"
LISTING = [*expected_pages(), SKILL]
IDS = [rel(page) for page in LISTING]
MUST_LIST = [README, DOCS / "commands.md", DOCS / "config.md", DOCS / "setup-with-your-agent.md", DOCS / "python.md", SKILL]
COUNT = re.compile(r"\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+) (?:other )?(readers|tools|sources)\b", re.IGNORECASE)


def _in_order(tools: list[str]) -> bool:
    kept = [word for word in tools if word != "table"]
    return kept == [word for word in WORDS if word in kept]


# ---------- TF5-20 ----------


def test_tf5_20_the_install_gives_the_ten_in_one_order() -> None:
    from importlib.util import find_spec

    from poisson_trace.ingest.cli import READERS, module_name

    present = tuple(tool for tool in READERS if find_spec(module_name(tool)) is not None)
    assert present == WORDS == tuple(word for word, _, _ in TOOLS), "the readers this install has, in the order it lists them"
    assert len(WORDS) == 10 and API_TOOLS == WORDS[-3:]


def test_tf5_20_help_doctor_and_the_refusal_give_that_order_as_main_does() -> None:
    (code, out, err), = PINNED["readers"]["doctor"]
    assert (code, out, err) == (0, "  readers   " + ", ".join(WORDS) + "\n", "")
    (code, out, err), = PINNED["readers"]["import refusal"]
    assert code == 1 and err.splitlines()[0] == "error: unknown tool otel; this install reads: " + ", ".join(WORDS)
    (code, out, err), = PINNED["readers"]["help: import"]
    lines = out.splitlines()
    tools = [line.split()[0] for line in lines[lines.index("tools:") + 2:lines.index("examples:")] if re.match(r"^    \S", line)]
    assert code == 0 and tuple(tools) == WORDS
    examples = [line.split()[2] for line in lines[lines.index("examples:") + 1:] if line.strip().startswith("poisson-trace import ")]
    assert tuple(examples) == WORDS, "one example a tool, in the same order"


def test_tf5_20_the_install_still_says_so(tmp_path: Path) -> None:
    from tf5_pins import READERS_SAID, ran_case

    for label in ("import refusal", "help: import"):
        got = [list(step) for step in ran_case(tmp_path / label.replace(" ", "-").replace(":", ""), *READERS_SAID[label])]
        assert got == PINNED["readers"][label], label
    (code, out, _), = ran_case(tmp_path / "doctor", *READERS_SAID["doctor"])
    assert code == 0 and "  readers   " + ", ".join(WORDS) + "\n" in out


def test_tf5_20_init_finds_a_file_of_every_tool() -> None:
    (code, out, err), = PINNED["init"][EVERY_LABEL]
    assert code == 0 and "10 result files of 10 tools" in out
    assert tuple(word for word, _, _ in EVERY_TOOL) == WORDS
    for word, _, name in EVERY_TOOL:
        assert f"results/{name}" in err or (word == "deepeval" and "DeepEval results folder" in err), (word, err)
        assert re.search(rf"^    poisson-trace import {re.escape(word)} results/", out, re.M), word


# ---------- TF5-21 ----------


@pytest.mark.parametrize("page", LISTING, ids=IDS)
def test_tf5_21_a_passage_that_lists_the_readers_lists_all_ten_in_order(page: Path) -> None:
    text = read(page)
    for line, passage in passages(text):
        if lists_readers(passage):
            tools = named(passage)
            assert set(tools) == set(WORDS), f"{rel(page)}:{line}: lists {tools} and not {sorted(set(WORDS) - set(tools))}"
            assert _in_order(tools), f"{rel(page)}:{line}: names the tools in the order {tools}"
        coded = [word for word in WORDS if f"`{word}`" in passage]
        if len(coded) >= 3 and set(coded) != set(API_TOOLS):
            assert coded == list(WORDS), f"{rel(page)}:{line}: lists the readers' command words {coded}"
    for block in parse(text)[0]:
        if block.kind in ("skip", "data", "unmarked"):
            for offset, shown in enumerate(block.body.split("\n")):
                if lists_readers(shown):
                    tools = named(shown)
                    assert set(tools) == set(WORDS) and _in_order(tools), f"{rel(page)}:{block.line + offset}: lists {tools}"


def test_tf5_21_what_counts_as_a_list() -> None:
    ten = "DeepEval, Ragas, tables, JUnit, promptfoo, Inspect, OpenAI Evals, LangSmith, Braintrust and Weave"
    assert lists_readers(ten) and named(ten) == list(WORDS)
    assert named("  readers   " + ", ".join(WORDS)) == list(WORDS)
    assert not lists_readers("from the results a team already has in LangSmith, Braintrust or Weave")
    assert not lists_readers("the DeepEval page and the Ragas page")
    assert not lists_readers("inspect the table, then weave the JUnit report in")
    assert lists_readers("DeepEval, Ragas, a table of results or a JUnit report")
    assert lists_readers("for promptfoo, Inspect and OpenAI Evals files it prints the line")
    assert not _in_order(named("promptfoo, DeepEval, Ragas, tables, JUnit, Inspect, OpenAI Evals, LangSmith, Braintrust and Weave"))


# ---------- TF5-22 ----------


@pytest.mark.parametrize("page", MUST_LIST, ids=[rel(page) for page in MUST_LIST])
def test_tf5_22_the_page_carries_the_list(page: Path) -> None:
    assert any(lists_readers(passage) for _, passage in passages(read(page))), f"{rel(page)} lists the readers nowhere"


def test_tf5_22_the_readme_names_all_eleven_together() -> None:
    found = [passage for _, passage in passages(read(README)) if lists_readers(passage) and re.search(r"\bProve\b", passage)]
    assert found, "no passage of the README names Prove's stored runs with the ten tools"
    assert any(re.search(r"\bProve\b", p).start() < min(re.search(pattern, p, 0 if word == "inspect" else re.I).start()  # type: ignore[union-attr]
                                                         for word, _, pattern in TOOLS if word != "table") for p in found), "Prove's stored runs come first"


# ---------- TF5-23 ----------


def test_tf5_23_the_readme_gives_each_tool_a_line_that_links_its_page() -> None:
    section = sections(read(README)).get("Results from other tools")
    assert section is not None, "the README has no section 'Results from other tools'"
    lines = [line for line in section.split("\n") if line.startswith("- ")]
    at = []
    for word in WORDS:
        link = f"{GITHUB}docs/integrations/{word}.md"
        mine = [i for i, line in enumerate(lines) if link in line]
        assert len(mine) == 1, f"one line of the list links {link}"
        at.append(mine[0])
    assert at == sorted(at) and len(lines) == 10, "ten lines, one a tool, in the one order"
    assert re.search(r"(?i)\bcommitted\b|\bfixture\b|\breal (?:export|file)", prose(section)), "the listing rule, in a sentence"


@pytest.mark.parametrize("page", INTEGRATIONS, ids=[page.name for page in INTEGRATIONS])
def test_tf5_23_each_tool_s_page_shows_the_fixture_it_is_listed_by(page: Path) -> None:
    """The listing rule (spec section 6.1): a tool is named only when a real export of it is a
    committed fixture and its page shows a command on that fixture with what Trace printed."""
    blocks = parse(read(page))[0]
    word = page.stem
    folder = f"tests/fixtures/ingest/{word}/"
    shown = [i for i, block in enumerate(blocks) if block.kind == "command" and folder in block.body
             and i + 1 < len(blocks) and blocks[i + 1].kind in ("output", "excerpt") and blocks[i + 1].code == 0]
    assert shown, f"{page.name} shows no command on a fixture under {folder} with what it printed"
    sums = (REPO / "tests" / "fixtures" / "SHA256SUMS").read_text(encoding="utf-8")
    used = set(re.findall(re.escape(folder) + r"[\w./@+-]+", "\n".join(block.body for block in blocks if block.kind == "command")))
    for path in used:
        if (REPO / path).is_file():
            assert path.removeprefix("tests/fixtures/") in sums, f"{path} is in no SHA256SUMS line"


# ---------- TF5-24 ----------


@pytest.mark.parametrize("page", LISTING, ids=IDS)
def test_tf5_24_no_page_counts_the_readers_wrong(page: Path) -> None:
    for line, passage in passages(read(page)):
        for found in COUNT.finditer(passage):
            count, what = found.group(1).lower(), found.group(2).lower()
            if what == "readers":
                assert count in ("ten", "10", "eleven", "11", "three", "3"), f"{rel(page)}:{line}: {found.group(0)}"
            elif count in ("four", "seven", "eight", "nine", "4", "7", "8", "9"):
                assert not named(passage), f"{rel(page)}:{line}: {found.group(0)}"


# ---------- TF5-25 ----------


def test_tf5_25_the_commands_page_reaches_every_tool_s_page() -> None:
    text = read(DOCS / "commands.md")
    for word in WORDS:
        assert f"integrations/{word}.md" in text, word
    assert CONTRIBUTING.is_file()
