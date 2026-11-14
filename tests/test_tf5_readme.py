"""TF5-40 to TF5-47: the README (the brief's rule 4; spec sections 8.1 and 8.3; the launch note
of 2026-11-12). The facts are frozen, and that each is shown by a command on the page; the
sentences are Session B's and Taylor's.

The launch note: Trace says where runs die (which step, which kind of span), which inputs got
worse, which failure kinds grew, and whether it is real or noise, from the results a team
already has in LangSmith, Braintrust or Weave.

- TF5-40: the first screen is everything above the first ``---``: the title ``# Poisson
  Trace``; the three commands in one block, in order (``pip install poisson-trace``,
  ``poisson-trace init``, ``poisson-trace fix-check previous latest --inputs all --max-mde
  0.2``: a fix check takes the two runs it compares, which inputs to compare and the size
  asked about, and has no default for any of them, so nothing shorter runs as shown; ruled
  2026-11-13, B-1); the page runs ``init`` lower down, and that fix check word for word; the
  bare command, which opens the
  terminal app, and ``poisson-trace init --agent``; the three verdicts; the three services by
  name; and no pull-request check, which is not built.
- TF5-41: the five facts the opening may claim, each shown by a command the README runs, with
  what it printed: (a) where runs die by step, a ``where`` report's table of the share not yet
  failed; (b) by kind of step, its table of where they die; (c) which inputs got worse, the
  table of inputs that changed; (d) which failure kinds grew, the table of failures by kind
  under a command that reads two runs; (e) whether it is real or noise, a fix check's verdict
  line and the table of the two versions' failure shares (the control, where the
  inputs were chosen by an earlier run's failures).
- TF5-42: and from results a team already has: at least one of those reports reads runs the
  README itself imports from a service's committed answers (LangSmith's, Braintrust's or
  Weave's), and the ``where`` among them reads such a run.
- TF5-43: the opening claims no more than the page shows: every command, verb and flag it
  names in code is run on the page with what it printed (the install line and the bare
  command aside), and every figure it writes is in a block the page's commands printed, or is
  a version of Python.
- TF5-44: the rest, in the order section 8.3 gives: what a first run looks like; letting your
  coding agent set it up; what a fix check says and what it does not; the commands; results
  from other tools; into the product; how it decides; what is built and what is not claimed;
  development, licence, citation. Beside them only the Install section and, while the package
  is one, the pre-release section.
- TF5-45: what each section must hold: the first run shows ``init`` and ``runs``; the fix
  check's section the three verdicts in one list and the six things a fix check cannot say in
  another, as many as the report itself prints; the commands one line a verb, every verb,
  linking ``docs/commands.md``; into the product ``--out`` and ``handover --check``, the
  pages (``ui``, ``report``) and ``docs/handover.md``; how it decides links
  ``docs/how-it-decides.md`` and keeps no method's detail; development links
  ``CONTRIBUTING.md``.
- TF5-46: every link is absolute, because the README is the package index's page: a link to
  the repository opens with ``https://github.com/poisson-labs/trace/blob/main/`` and names a
  file that exists; nothing links a relative path.
- TF5-47: it says what Trace does not do, as the first screen's last line: it runs nothing,
  captures nothing and sends nothing; and the Pythons and systems it names are the ones the
  package declares.
"""

from __future__ import annotations

import re
import tomllib

from tf5_support import API_TOOLS, GITHUB, README, REPO, VERBS, Block, parse, prose, read, sections, trace_commands, words

TEXT = read(README) if README.is_file() else ""
VERDICTS = ("different", "no significant difference", "too small to tell")
ORDER = (
    "What a first run looks like", "Let your coding agent set it up", "What a fix check says, and what it does not", "The commands",
    "Results from other tools", "Into the product", "How it decides", "What is built and what is not claimed", "Development", "Licence",
    "Citation",
)
PROJECT = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def _first_screen() -> str:
    assert "\n---\n" in TEXT, "the README has no first screen: nothing ends it with ---"
    return TEXT.split("\n---\n")[0]


def _shown() -> list[tuple[list[list[str]], Block]]:
    """Each output or excerpt of the README with the ``poisson-trace`` commands of the block it
    stands under."""
    out = []
    above: list[list[str]] = []
    for block in parse(TEXT)[0]:
        if block.kind == "command":
            above = trace_commands("<!-- command -->\n```\n" + block.body + "\n```\n")
        elif block.kind in ("output", "excerpt"):
            out.append((above, block))
    return out


def _table_under(body: str, heading: str) -> bool:
    """Whether a shown block holds the report's section of that heading with a row of its
    table: the heading alone shows nothing."""
    lines = body.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(heading):
            rest = lines[i + 1:]
            end = next((j for j, later in enumerate(rest) if later.startswith("## ")), len(rest))
            rows = [later for later in rest[:end] if later.startswith("|") and not set(later) <= set("|- ")]
            if len(rows) >= 2:
                return True
    return False


def _shows(verbs: tuple[str, ...], heading: str) -> list[list[list[str]]]:
    return [above for above, block in _shown() if block.code == 0 and any(c[:1] == [v] for c in above for v in verbs) and _table_under(block.body, heading)]


# ---------- TF5-40 ----------


def test_tf5_40_the_first_screen() -> None:
    first = _first_screen()
    assert first.startswith("# Poisson Trace\n"), first[:40]
    lines = [line.strip() for line in first.split("\n")]
    three = ["pip install poisson-trace", "poisson-trace init", "poisson-trace fix-check previous latest --inputs all --max-mde 0.2"]
    at = lines.index(three[0]) if three[0] in lines else -1
    assert at >= 0 and lines[at:at + 3] == three, "the three commands, in one block, in order"
    ran = [" ".join(command) for command in trace_commands(TEXT)]
    assert any(command == "init" or command.startswith("init ") for command in ran), "and the page runs init"
    assert three[2].removeprefix("poisson-trace ") in ran, "and the page runs that fix check, word for word"
    assert "`poisson-trace`" in first and re.search(r"(?i)\bapp\b", first), "the bare command opens the terminal app"
    assert "`poisson-trace init --agent`" in first
    for verdict in VERDICTS:
        assert f"*{verdict}*" in first, verdict
    for service in ("LangSmith", "Braintrust", "Weave"):
        assert service in first, service
    assert len(first.split("\n")) <= 60, "a first screen, not a page"


def test_tf5_40_no_pull_request_check_is_named() -> None:
    assert not re.search(r"`(?:poisson-trace )?check`|poisson-trace check\b|--fail-on", TEXT), "the pull-request check is not built"
    assert not re.search(r"(?i)^#+ On a pull request", TEXT, re.M)
    assert not re.search(r"`(?:poisson-trace )?upload`|poisson-trace upload\b", TEXT), "the upload is not built"


# ---------- TF5-41 ----------


def test_tf5_41_a_where_runs_die_by_step_is_shown() -> None:
    assert _shows(("where",), "## Share not yet failed, by"), "no where report on the page shows its table of the share not yet failed"


def test_tf5_41_b_by_kind_of_step_is_shown() -> None:
    assert _shows(("where",), "## Where they die, by kind of step"), "no where report on the page shows where runs die by kind of step"


def test_tf5_41_c_which_inputs_got_worse_is_shown() -> None:
    assert _shows(("changes", "fix-check"), "## Inputs that changed"), "no report on the page shows the inputs that changed"


def test_tf5_41_d_which_failure_kinds_grew_is_shown() -> None:
    assert _shows(("fix-check", "compare", "changes"), "## Failures by kind"), "no report on the page shows the failures by kind of two runs"


def test_tf5_41_e_whether_it_is_real_or_noise_is_shown() -> None:
    lines = [block.body.split("\n")[0] for above, block in _shown() if block.code == 0 and any(c[:1] == ["fix-check"] for c in above)]
    assert any(line.startswith(tuple(f"{verdict}  " for verdict in VERDICTS)) for line in lines), "no fix check on the page shows its verdict line"
    assert _shows(("fix-check",), "## The control") or _shows(("fix-check",), "## The two versions"), \
        "no fix check on the page shows the two versions' failure shares side by side"


# ---------- TF5-42 ----------


def _imports_before(at_block: int) -> set[str]:
    """The services whose committed answers the README's commands have imported, by the block."""
    tools: set[str] = set()
    for block in parse(TEXT)[0][:at_block + 1]:
        if block.kind == "command":
            for command in trace_commands("<!-- command -->\n```\n" + block.body + "\n```\n"):
                if command[:1] == ["import"] and command[1:2] and command[1] in API_TOOLS:
                    files = [word for word in command if f"tests/fixtures/ingest/{command[1]}/" in word]
                    if any((REPO / word).exists() for word in files) or any(word.startswith(f"{command[1]}:") for word in command):
                        tools.add(command[1])
    return tools


def test_tf5_42_from_results_a_team_already_has() -> None:
    blocks = parse(TEXT)[0]
    read_from_a_service: dict[str, bool] = {"where": False, "fix-check": False}
    for at, block in enumerate(blocks):
        if block.kind != "command":
            continue
        following = blocks[at + 1] if at + 1 < len(blocks) else None
        if following is None or following.kind not in ("output", "excerpt") or following.code != 0:
            continue
        imported_here = [c for c in trace_commands("<!-- command -->\n```\n" + block.body + "\n```\n") if c[:1] == ["import"]]
        for command in trace_commands("<!-- command -->\n```\n" + block.body + "\n```\n"):
            if command[:1] in (["where"], ["fix-check"]) and _imports_before(at):
                stores = {c[c.index("--store") + 1] for b in blocks[:at + 1] if b.kind == "command"
                          for c in trace_commands("<!-- command -->\n```\n" + b.body + "\n```\n")
                          if c[:1] == ["import"] and c[1:2] and c[1] in API_TOOLS and "--store" in c}
                if "--store" in command and command[command.index("--store") + 1] in stores:
                    read_from_a_service[command[0]] = True
        del imported_here
    assert read_from_a_service["where"], "no where on the page reads a run imported from LangSmith, Braintrust or Weave"
    assert read_from_a_service["fix-check"], "no fix check on the page reads runs imported from LangSmith, Braintrust or Weave"


# ---------- TF5-43 ----------


def test_tf5_43_the_opening_names_no_command_the_page_does_not_run() -> None:
    first = _first_screen()
    ran = trace_commands(TEXT)
    verbs_run = {command[0] for command in ran if command}
    flags_run = {word.split("=")[0] for command in ran for word in command if word.startswith("--")}
    for code in re.findall(r"`([^`\n]+)`", first):
        parts = code.split()
        if parts[:1] == ["poisson-trace"]:
            parts = parts[1:]
        if not parts or code in ("poisson-trace", "pip install poisson-trace", "trace.toml"):
            continue
        if parts[0] in VERBS:
            assert parts[0] in verbs_run, f"the opening names `{code}` and the page never runs {parts[0]}"
        for flag in (word for word in parts if word.startswith("--") and word != "--agent"):
            assert flag in flags_run, f"the opening names {flag} and the page never runs it"


def test_tf5_43_every_figure_of_the_opening_is_one_a_command_printed() -> None:
    first = prose(_first_screen())
    printed = "\n".join(block.body for block in parse(TEXT)[0] if block.kind in ("output", "excerpt"))
    for figure in re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d+)?%?(?![\w.])", first):
        if re.search(rf"3\.1[1-9]|Python {re.escape(figure)}", first) and re.fullmatch(r"3\.\d+", figure):
            continue
        assert figure in printed, f"the opening writes {figure}, which no command on the page printed"


# ---------- TF5-44 ----------


def test_tf5_44_the_sections_in_order() -> None:
    titles = [line[3:].strip() for line in "\n".join(line for line in _outside_blocks()).split("\n") if line.startswith("## ")]
    kept = [title for title in titles if title in ORDER]
    assert kept == list(ORDER), kept
    extra = [title for title in titles if title not in ORDER]
    for title in extra:
        assert title == "Install" or re.search(r"(?i)pre-release", title), f"a section section 8.3 does not name: {title}"


def _outside_blocks() -> list[str]:
    from tf5_support import outside

    return [line for _, line in outside(TEXT)]


# ---------- TF5-45 ----------


def _section(title: str) -> str:
    found = sections(TEXT).get(title)
    assert found is not None, f"the README has no section '{title}'"
    return found


def test_tf5_45_the_first_run_shows_init_and_runs() -> None:
    section = _section("What a first run looks like")
    ran = [command[0] for command in trace_commands(section) if command]
    assert "init" in ran and "runs" in ran and ran.index("init") < ran.index("runs"), ran


def test_tf5_45_the_fix_check_in_two_lists() -> None:
    from tf0_support import trace

    section = prose(_section("What a fix check says, and what it does not"))
    for verdict in VERDICTS:
        assert re.search(rf"^- \*{verdict}\*:", section, re.M), verdict
    assert re.search(r"(?i)\bcontrol\b", section) and "--max-mde" in section and re.search(r"(?i)\brepeats\b", section)
    ran = trace(["fix-check", "tau2-airline 2026-09-15 a", "tau2-airline 2026-09-15 b", "--store", str(REPO / "tests" / "fixtures" / "tau2"),
                 "--event", "unsolved", "--inputs", "all", "--max-mde", "0.1", "--json"])
    import json

    cannot = json.loads(ran.out)["cannot_say"]
    assert len(cannot) == 6
    bullets = [line for line in section.split("\n") if line.startswith("- ") and not line.startswith("- *")]
    assert len(bullets) == len(cannot), f"{len(bullets)} things it cannot say; the report prints {len(cannot)}"


def test_tf5_45_the_commands_one_line_each() -> None:
    section = prose(_section("The commands"))
    assert f"{GITHUB}docs/commands.md" in section
    lines = [line for line in section.split("\n") if line.startswith("- ")]
    for verb in VERBS:
        mine = [line for line in lines if re.match(rf"^- `(?:poisson-trace )?{re.escape(verb)}`", line)]
        assert len(mine) == 1, f"one line for {verb}"
    assert len(lines) in (len(VERBS), len(VERBS) + 1), "a line a verb, and one for the bare command at most"


def test_tf5_45_into_the_product() -> None:
    section = _section("Into the product")
    said = prose(section)
    for word in ("--out", "handover --check", f"{GITHUB}docs/handover.md", "`poisson-trace ui`", "report"):
        assert word in said, word
    assert re.search(r"(?m)^\*\*The pages\.?\*\*|^### The pages", section), "a paragraph on the pages"


def test_tf5_45_how_it_decides_points_to_its_page() -> None:
    section = prose(_section("How it decides"))
    assert f"{GITHUB}docs/how-it-decides.md" in section
    paragraphs = [p for p in re.split(r"\n\s*\n", section.strip()) if p.strip()]
    assert len(paragraphs) == 2, "two paragraphs"
    for method in ("Mantel", "Miettinen", "Benjamini", "hypergeometric"):
        assert method not in prose(TEXT), f"{method}: the methods are docs/how-it-decides.md's (a report the page shows may name its own)"


def test_tf5_45_development_points_to_the_contributing_page() -> None:
    assert f"{GITHUB}CONTRIBUTING.md" in prose(_section("Development"))
    assert "MIT" in _section("Licence") and _section("Citation").strip()


# ---------- TF5-46 ----------


def test_tf5_46_every_link_is_absolute_and_leads_somewhere() -> None:
    links = re.findall(r"\]\(([^)\s]+)\)", prose(TEXT))
    assert len(links) >= 30
    for link in links:
        if link.startswith("#"):
            continue
        assert link.startswith("https://"), f"a relative link: {link}"
        if link.startswith("https://github.com/poisson-labs/trace/"):
            assert link.startswith(GITHUB), link
            path = link[len(GITHUB):].split("#")[0]
            assert (REPO / path).is_file(), f"{link} names no file of the repository"
    for src in re.findall(r"<img[^>]+src=\"([^\"]+)\"|!\[[^\]]*\]\(([^)\s]+)\)", TEXT):
        target = src[0] or src[1]
        assert target.startswith("https://"), target


# ---------- TF5-47 ----------


def test_tf5_47_what_trace_does_not_do_and_where_it_runs() -> None:
    first = prose(_first_screen())
    last = [line for line in first.strip().split("\n\n")][-1]
    assert re.search(r"(?i)runs nothing", last) and re.search(r"(?i)captures nothing", last) and re.search(r"(?i)sends? nothing|phones nowhere", last), last
    classifiers = PROJECT["classifiers"]
    pythons = sorted(c.rsplit(" ", 1)[1] for c in classifiers if re.fullmatch(r"Programming Language :: Python :: 3\.\d+", c))
    assert pythons, classifiers
    assert f"Python {pythons[0]}" in last and (len(pythons) == 1 or pythons[-1] in last), (pythons, last)
    for system, classifier in (("macOS", "Operating System :: MacOS"), ("Linux", "Operating System :: POSIX :: Linux")):
        assert (system in last) == (classifier in classifiers), system
    assert "Windows" not in last


def test_tf5_47_the_readme_says_where_the_example_files_are() -> None:
    """Section 8.4: a pip user gets the example files from the repository; the README says so
    before its first command that reads one."""
    said = " ".join(TEXT.split())
    found = re.search(r"(?i)\bclone of the repository\b|\bclone the repository\b|\bsource archive\b", said)
    assert found, "the README never says the examples run from a clone of the repository"
    assert found.start() < said.index("tests/fixtures/"), "and says it before the first example"


def test_tf5_47_every_command_the_readme_runs_is_one_of_trace_s() -> None:
    for block in parse(TEXT)[0]:
        if block.kind == "command":
            for command in words(block):
                assert command[0] in ("poisson-trace", "mkdir", "cp", "cd", "gunzip", "cat", "ls"), command
