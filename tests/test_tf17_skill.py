"""TF17-5 to TF17-12 and TF17-47: the skill ``init --agent`` writes passes the shared setup-file
check (the shared page's own check), says what ``docs/setup-with-your-agent.md`` says, and
keeps to the four tables the agent may write; and the docs name it.

- TF17-5: the frontmatter holds exactly ``name``, ``description`` and ``metadata``; ``name`` is
  ``poisson-trace-setup`` and equals its folder; ``description`` is ``DESCRIPTION``; the five
  metadata keys are present, every value a string: ``poisson-setup-format`` ``"1"``,
  ``poisson-tool`` ``poisson-trace``, ``poisson-tool-version`` the version ``--version`` prints,
  ``poisson-writes`` ``trace.toml``, ``poisson-check`` ``poisson-trace doctor --setup``.
- TF17-6: the ``#`` and ``##`` headings are the shared page's, in order, the last ("Words Trace
  uses") optional; "What you are doing" is one paragraph; "Files you write" is one line, for
  ``trace.toml``, equal to ``poisson-writes``.
- TF17-7: the shared rules, the shared check and the shared hand-over opening equal the page's
  text with Trace's names filled in, byte for byte (the fixture carries the page's text with its
  date); the prompt is the page's; the docs address is Trace's PyPI page.
- TF17-8: ``### Trace's own rules`` follows the shared rules directly and says: run no
  ``poisson-trace`` verb but ``doctor --setup`` and ``--help``; never write into a store or
  ``.poisson/``; never run the person's evaluations, tests or agent; open a result file only as
  far as its tool, its outcome values and its run names need.
- TF17-9: the seven steps of ``STEP_TITLES``, numbered, each opening with its title in bold, the
  last two "Run the check" and "Stop and hand over"; step 1 names Prove stores and every reader
  of this install and says "run nothing"; step 3 says the agent never chooses a cut and a file
  with no cut is left out; step 4 names old and new; step 5 names ``trace.toml``, ``[store]``,
  ``[events]``, ``[[import]]`` and ``[names]`` and says the imports' store is not the agent's to
  write; the hand-over lists what the person confirms (the stores and files, the failure
  outcomes and where each came from, the metric and cut per scored file, which run is old and
  which new).
- TF17-10: commands are read from fenced blocks only: every ``bash`` block's line is
  ``poisson-trace doctor --setup`` or a ``--help``, each parses (``--help`` exits 0, its options
  in its verb's help), none carries ``--yes`` or any flag that answers a question; the person's
  command is the one ``text`` block under "Hand over", ``poisson-trace init``; every block has a
  language tag and a ``poisson-trace`` line sits in no other block.
- TF17-11: the skill and the prompt are in plain words (the TF0-21 pattern).
- TF17-12: the skill names ``[signals]``, ``[[taxonomy.rules]]`` and
  ``[taxonomy]`` nowhere; the tables it tells the agent to write are ``[store]``, ``[events]``,
  ``[[import]]`` and ``[names]``, "nothing else".
- TF17-47: ``docs/setup-with-your-agent.md`` holds a table of the two locations with the agents
  verified to read each, the prompt and the check; the README's section "Let your coding agent
  set it up" names ``poisson-trace init --agent``, the prompt and ``poisson-trace init``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tf0_support import plain
from tf1_support import shell_words
from tf2_support import scratch_home, work  # noqa: F401
from tf17_support import (
    AGENT_TABLES, CHECK, COMMAND, DESCRIPTION, DOCS_PAGE, DOCS_URL, FOLDERS, FOUR, HEADINGS,
    LOCATIONS, METADATA_KEYS, NEXT_COMMAND, NOT_FOR_THE_AGENT, OPTIONAL_LAST_HEADING, OWN_RULES,
    PROMPT, READERS_HERE, REPO, SKILL, SKILL_NAME, STEP_TITLES, WRITES, agent, commands,
    fences, headings, parse_frontmatter, section, shared_text, split_frontmatter, steps_of,
    trace_in, version,
)


@pytest.fixture
def skill(tmp_path: Path) -> tuple[dict[str, object], str, str]:
    repo = work(tmp_path)
    assert agent(repo).code == 0
    text = (repo / FOUR[0]).read_text(encoding="utf-8")
    front, body = split_frontmatter(text)
    return parse_frontmatter(front), body, text


# ---------- TF17-5 ----------


def test_tf17_5_the_frontmatter_is_the_shared_shape_with_traces_values(skill: tuple[dict[str, object], str, str]) -> None:
    meta, _, _ = skill
    assert set(meta) == {"name", "description", "metadata"}, meta
    assert meta["name"] == SKILL and all(Path(folder).name == SKILL for folder in FOLDERS)
    assert SKILL_NAME.match(str(meta["name"])) and len(str(meta["name"])) <= 64
    assert meta["description"] == DESCRIPTION
    assert 1 <= len(str(meta["description"])) <= 1024
    metadata = meta["metadata"]
    assert isinstance(metadata, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in metadata.items()), metadata
    assert set(METADATA_KEYS) <= set(metadata), sorted(metadata)
    assert metadata["poisson-setup-format"] == "1"
    assert metadata["poisson-tool"] == "poisson-trace"
    assert metadata["poisson-tool-version"] == version()
    assert metadata["poisson-writes"] == " ".join(WRITES)
    assert metadata["poisson-check"] == CHECK


# ---------- TF17-6 ----------


def test_tf17_6_the_sections_are_the_shared_ones_in_order_and_files_you_write_is_trace_toml(skill: tuple[dict[str, object], str, str]) -> None:
    meta, body, _ = skill
    top = [h for h in headings(body) if re.match(r"^#{1,2} ", h)]
    assert top in (HEADINGS, [*HEADINGS, OPTIONAL_LAST_HEADING]), top
    doing = section(body, "## What you are doing").split("\n", 1)[1].strip()
    assert doing and "\n\n" not in doing, doing
    listed = []
    for line in section(body, "## Files you write").splitlines()[1:]:
        if line.strip():
            m = re.match(r"^- `([^`]+)`", line)
            assert m, f"not a file line: {line!r}"
            listed.append(m.group(1))
    assert listed == str(meta["metadata"]["poisson-writes"]).split() == WRITES, listed  # type: ignore[index]


# ---------- TF17-7 ----------


def test_tf17_7_the_shared_text_is_the_pages_byte_for_byte(skill: tuple[dict[str, object], str, str]) -> None:
    _, body, _ = skill
    shared = shared_text()
    rules = section(body, "## Rules")
    assert rules.startswith(shared["rules"] + "\n\n" + OWN_RULES), rules[:2000]
    assert section(body, "## The check").rstrip("\n") == shared["check"]
    hand_over = section(body, "## Hand over")
    assert hand_over.startswith(shared["hand-over"] + "\n"), hand_over
    assert PROMPT == shared["prompt"]
    assert DOCS_URL in shared["rules"]


# ---------- TF17-8 ----------


def test_tf17_8_traces_own_rules_follow_the_shared_ones(skill: tuple[dict[str, object], str, str]) -> None:
    _, body, _ = skill
    rules = section(body, "## Rules").splitlines()
    assert OWN_RULES in rules, rules
    own = section(body, OWN_RULES)
    for fact in ("doctor --setup", "--help", ".poisson/", "store"):
        assert fact in own, (fact, own)
    assert re.search(r"never run the person's (?:own )?evaluations, tests or agent", own, re.I), own
    assert re.search(r"runs nothing and captures nothing", own, re.I), own
    assert re.search(r"only as far as its tool, its outcome values and its run names", own, re.I), own


# ---------- TF17-9 ----------


def test_tf17_9_the_seven_steps_and_what_each_says(skill: tuple[dict[str, object], str, str]) -> None:
    _, body, _ = skill
    steps = steps_of(body)
    assert [s.number for s in steps] == [1, 2, 3, 4, 5, 6, 7], [s.number for s in steps]
    assert [s.title for s in steps] == list(STEP_TITLES), [s.title for s in steps]
    one = steps[0].text
    assert "manifest.json" in one and re.search(r"\brun nothing\b", one, re.I), one
    for reader in ("DeepEval", "Ragas", "promptfoo", "Inspect", "OpenAI Evals", "JUnit"):
        assert reader in one, (reader, one)
    assert "import --help" in one, one
    assert "```" not in one and COMMAND + " doctor" not in one, one
    assert re.search(r"dependencies", steps[1].text), steps[1].text
    three = steps[2].text
    assert re.search(r"never choose(?:s)? a cut", three, re.I) and re.search(r"lea(?:ve|ft) .*out", three), three
    four = steps[3].text
    assert re.search(r"\bold\b", four) and re.search(r"\bnew\b", four) and "name" in four, four
    five = steps[4].text
    assert "trace.toml" in five
    for table in AGENT_TABLES:
        assert table in five, (table, five)
    assert "failed" in five and re.search(r"nothing else", five, re.I), five
    assert re.search(r"not the agent's to write|not yours to write", five), five
    hand_over = section(body, "## Hand over")
    tail = hand_over.split("Do not run that command for them.", 1)[1]
    items = [line for line in tail.splitlines() if re.match(r"^(?:- |\d+\. )", line)]
    assert 4 <= len(items) <= 6, tail
    for facts in (("stores", "files"), ("failure",), ("metric", "cut"), ("old", "new")):
        assert any(all(f in i for f in facts) for i in items), (facts, items)


# ---------- TF17-10 ----------

TF17_10_PARTS = [
    "every command parses",
    "no --yes or answer",
    "the agent runs only the check and --help",
    "the person's command is one text block under Hand over",
    "commands only in tagged blocks",
]


@pytest.mark.parametrize("part", TF17_10_PARTS)
def test_tf17_10_every_command_parses_none_answers_for_the_person_and_the_agent_runs_only_the_check(part: str, skill: tuple[dict[str, object], str, str], tmp_path: Path) -> None:
    _, body, _ = skill
    repo = work(tmp_path, "parse")
    agent_commands = [command for _, command in commands(body, "bash")]
    person = commands(body, "text")
    assert agent_commands, "no bash block"
    everything = agent_commands + [command for _, command in person]

    if part == "every command parses":
        for command in everything:
            words = shell_words(command)
            assert words[0] == COMMAND, command
            helped = trace_in(repo, [*words[1:], "--help"])
            assert helped.code == 0 and helped.out.startswith("usage"), (command, helped.text)
            verb = next((w for w in words[1:] if not w.startswith("-")), None)
            verb_help = trace_in(repo, [verb, "--help"]).out if verb else trace_in(repo, ["--help"]).out
            for option in (w.split("=", 1)[0] for w in words[1:] if w.startswith("--")):
                assert re.search(rf"(?<![\w-]){re.escape(option)}(?![\w-])", verb_help), (command, option)
    elif part == "no --yes or answer":
        answers = {"--yes", "-y", "--force", "--import", "--no-import", "--event", "--store", "--add-store"}
        for command in everything:
            assert not answers & set(shell_words(command)), command
    elif part == "the agent runs only the check and --help":
        for command in agent_commands:
            words = shell_words(command)
            assert words == shell_words(CHECK) or "--help" in words, command
        assert CHECK in agent_commands, agent_commands
    elif part == "the person's command is one text block under Hand over":
        under = [c for s, c in person if s == "## Hand over"]
        assert under == [NEXT_COMMAND], person
    else:
        blocks = fences(body)
        assert all(b.lang for b in blocks), [b.lines[:1] for b in blocks if not b.lang]
        for b in blocks:
            if b.lang == "bash" or (b.lang == "text" and b.section == "## Hand over"):
                continue
            stray = [line for line in b.lines if line.strip().startswith(COMMAND)]
            assert not stray, (b.lang, b.section, stray)


# ---------- TF17-11 ----------


def test_tf17_11_the_skill_and_the_prompt_are_in_plain_words(skill: tuple[dict[str, object], str, str]) -> None:
    _, _, text = skill
    assert plain(text) == [], plain(text)
    assert plain(PROMPT) == []


# ---------- TF17-12 ----------


def test_tf17_12_the_skill_keeps_to_the_tables_the_agent_may_write(skill: tuple[dict[str, object], str, str]) -> None:
    _, body, text = skill
    for table in NOT_FOR_THE_AGENT:
        assert table not in text, table
    assert "taxonomy" not in text.lower() and "signals" not in text.lower(), text
    five = steps_of(body)[4].text
    for table in AGENT_TABLES:
        assert table in five, (table, five)


# ---------- TF17-47 ----------


def test_tf17_47_the_docs_page_holds_the_locations_table_and_the_readme_names_init_agent() -> None:
    assert DOCS_PAGE.is_file(), DOCS_PAGE
    page = DOCS_PAGE.read_text(encoding="utf-8")
    rows = [line for line in page.splitlines() if re.match(r"^\s*\|\s*`[^`]+`", line)]
    found: dict[str, str] = {}
    for row in rows:
        m = re.match(r"^\s*\|\s*`([^`]+)`\s*\|(.*)\|", row)
        assert m, row
        found[m.group(1)] = m.group(2)
    assert set(found) == set(LOCATIONS), (sorted(found), sorted(LOCATIONS))
    for folder, agents in LOCATIONS.items():
        for name in agents:
            assert name in found[folder], (folder, name, found[folder])
    assert PROMPT in page and CHECK in page and "init --agent" in page, page[:400]
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    m = re.search(r"^#+ Let your coding agent set it up\n(.*?)(?=^#+ |\Z)", readme, re.M | re.S)
    assert m, "the README has no section 'Let your coding agent set it up'"
    body = m.group(1)
    assert "poisson-trace init --agent" in body and PROMPT in body and NEXT_COMMAND in body, body
    assert "setup-with-your-agent.md" in body, body
    assert all(reader in page for reader in READERS_HERE), page
