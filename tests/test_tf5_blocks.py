"""TF5-10 to TF5-19: every command a page shows runs as shown. The marks are written out in
``tf5_support``'s opening.

- TF5-10: the pages of 0.1.0 are all written, and the two recipes that wait with the
  pull-request check and the upload are not.
- TF5-11: every page reads under the marks with no fault: no comment that means to be a mark
  and is not one, no mark with no block under it, no other tool's spelling of a mark.
- TF5-12: no fenced block is unmarked, but one whose fence names what it holds and whose first
  line is not a shell command; and outside the fenced blocks no indented line shows a
  ``poisson-trace`` command, but on the README's first screen.
- TF5-13: a skipped block says why, and one that runs ``poisson-trace`` is skipped only when it
  holds a word in capitals that is the reader's to fill in or ``…``, or is the bare command;
  every output and excerpt stands under a command that is run, never under a skipped block.
- TF5-14: every marked block of every page holds when the page's commands are run in page
  order: an output is the whole of what its command printed, an excerpt a run of whole lines
  of it, each with its exit code; byte for byte, or under ``varies`` with ``…`` standing for
  a path, a time, an id or a version alone. The longer pages are slow; ``TWINS`` names the
  short page of the same kind that stands for each in the pull-request lane.
- TF5-15: a block marked ``varies`` holds a ``…`` and no line that is ``…`` alone; what each
  ``…`` stood for when the page ran was a path, a time, an id or a version.
- TF5-16: an address of a service (``langsmith:``, ``braintrust:``, ``weave:``) that a page
  runs is run in a block marked ``pull``, and a block marked ``pull`` holds one; while a page's
  other commands run, each service's address points at a closed port of this machine.
- TF5-17: no command a page runs names a run by its id.
- TF5-18: every source has a first result on a page that runs: Prove's stored runs on
  ``first-look.md`` (``init``, ``runs``, ``where``), each of the ten tools on its recipe (two
  imports under two names, then ``fix-check`` on them, each with what it printed), and each of
  the three services pulled by its address, from the captures, with what the pull printed and
  a verb reading the pulled run.
- TF5-19: every block the README shows is a recipe's block: its command is a recipe's
  command, and what it shows of the output is a run of whole lines of what that recipe shows.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tf5_support import (
    ADDRESS, API_TOOLS, DOCS, DOCS_SET, INTEGRATIONS, PLACEHOLDER, README, RECIPES, VARIES, WAITING, Block, expected_pages, holds, outside, parse,
    read, recipe, rel, run_page, run_pages, trace_commands, why, words,
)

RUN_ID = re.compile(r"\b\d{8}T\d{6}Z-[0-9a-f]{4}\b")
#: The pages whose commands take longest, run whole in the slow lane; each is stood for in the
#: pull-request lane by a short page of the same kind, which runs the same runner on the same
#: kinds of block.
TWINS = {
    "README.md": "docs/recipes/first-look.md",
    "docs/integrations/ragas.md": "docs/integrations/table.md",
    "docs/integrations/deepeval.md": "docs/integrations/junit.md",
    "docs/recipes/from-deepeval.md": "docs/recipes/from-junit.md",
    "docs/recipes/check-a-fix.md": "docs/recipes/first-look.md",
    "docs/recipes/what-it-cannot-say.md": "docs/recipes/first-look.md",
    "docs/commands.md": "docs/config.md",
}
PAGES = expected_pages()
IDS = [rel(page) for page in PAGES]


def _blocks(page: Path) -> list[Block]:
    return parse(read(page))[0]


# ---------- TF5-10 ----------


def test_tf5_10_the_pages_are_these_and_no_recipe_that_waits_is_written() -> None:
    assert len(RECIPES) == 16 and len(INTEGRATIONS) == 10 and len(DOCS_SET) == 7
    written = {p.name for p in (DOCS / "recipes").glob("*.md")}
    assert not written & set(WAITING), written & set(WAITING)
    assert not (DOCS / "pull-request-check.md").exists(), "the pull-request check's page waits with the check"
    assert set(run_pages()) >= set(PAGES)


# ---------- TF5-11 ----------


@pytest.mark.parametrize("page", PAGES, ids=IDS)
def test_tf5_11_the_page_reads_under_the_marks(page: Path) -> None:
    text = read(page)
    assert text.startswith("# "), rel(page)
    assert parse(text)[1] == [], rel(page)
    assert "docs-check:" not in text, "the marks are Trace's own (command, output, excerpt, skip)"


# ---------- TF5-12 ----------


@pytest.mark.parametrize("page", PAGES, ids=IDS)
def test_tf5_12_no_block_is_unmarked(page: Path) -> None:
    unmarked = [(block.line, block.body.split("\n")[0]) for block in _blocks(page) if block.kind == "unmarked"]
    assert unmarked == [], rel(page)


@pytest.mark.parametrize("page", PAGES, ids=IDS)
def test_tf5_12_no_command_hides_in_an_indented_line(page: Path) -> None:
    text = read(page)
    first_screen = text.split("\n---\n")[0].count("\n") + 1 if page == README else 0
    hits = [(n, line) for n, line in outside(text) if re.match(r"^(?: {4,}|\t)(?:\$ )?(?:poisson-trace|pip install)\b", line) and n > first_screen]
    assert hits == [], rel(page)


# ---------- TF5-13 ----------


@pytest.mark.parametrize("page", PAGES, ids=IDS)
def test_tf5_13_a_skipped_block_may_be_skipped(page: Path) -> None:
    for block in _blocks(page):
        if block.kind != "skip":
            continue
        assert len(block.reason.strip()) >= 8, (rel(page), block.line, block.reason)
        for command in words(block):
            starts = [command[0], *[command[at + 1] for at, word in enumerate(command[:-1]) if word in ("&&", ";", "||")]]
            if "poisson-trace" not in starts and "poisson-trace-import" not in starts:
                continue
            bare = command == ["poisson-trace"]
            assert bare or PLACEHOLDER.search(" ".join(command)), f"{rel(page)}:{block.line}: a command that could be run is skipped: {' '.join(command)}"


@pytest.mark.parametrize("page", PAGES, ids=IDS)
def test_tf5_13_what_a_page_shows_printed_stands_under_a_command_that_is_run(page: Path) -> None:
    above: Block | None = None
    for block in _blocks(page):
        if block.kind in ("output", "excerpt"):
            assert above is not None and above.kind == "command", f"{rel(page)}:{block.line}: no command is run above this {block.kind}"
        elif block.kind in ("command", "skip"):
            above = block


# ---------- TF5-14 ----------


def _lane(page: Path) -> object:
    return pytest.param(page, marks=pytest.mark.slow, id=rel(page)) if rel(page) in TWINS else pytest.param(page, id=rel(page))


@pytest.mark.parametrize("page", [_lane(page) for page in PAGES])
def test_tf5_14_every_marked_block_of_the_page_holds(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory, page: Path) -> None:
    if rel(page) == "docs/recipes/with-tasks-and-prove.md":
        # this page's commands take minutes: its one run by this same runner is shared with the tests of the page itself
        from tf20_support import shared_run

        checked = shared_run(tmp_path_factory).checked
    else:
        checked = run_page(page, tmp_path)
    for c in checked:
        assert holds(c), why(page, c)
    commands = [block for block in _blocks(page) if block.kind == "command"]
    if commands:
        assert checked, f"{rel(page)} runs commands and shows nothing they print"
    if rel(page) == "README.md":
        # the figures the README's commands write (--svg docs/figures/... --force) are written in the copy and equal the
        # committed ones, so the README shows the curve where prints
        assert len(checked) >= 20, len(checked)
        written = sorted((tmp_path / "clone" / "docs" / "figures").glob("*.svg"))
        assert written, "the README writes no figure"
        from pin_support import as_pinned

        for svg in written:
            # a figure's footer names the Prove that drew it: the committed ones were drawn with 0.1.3, and Prove's
            # version is written as the pins hold it (pin_support.as_pinned)
            assert as_pinned(svg.read_text(encoding="utf-8")).encode("utf-8") == (DOCS / "figures" / svg.name).read_bytes(), svg.name


def test_tf5_14_a_short_page_of_its_kind_stands_for_each_slow_one() -> None:
    names = {rel(page) for page in PAGES}
    for slow, fast in TWINS.items():
        assert slow in names and fast in names and fast not in TWINS, (slow, fast)
        kinds = {block.kind for block in _blocks(DOCS.parent / fast)}
        assert {"command", "excerpt"} <= kinds or {"command", "output"} <= kinds, (fast, kinds)


# ---------- TF5-15 ----------


@pytest.mark.parametrize("page", PAGES, ids=IDS)
def test_tf5_15_a_block_that_varies_says_where(page: Path) -> None:
    for block in _blocks(page):
        if block.varies:
            lines = block.body.split("\n")
            assert any("…" in line for line in lines), f"{rel(page)}:{block.line}: marked varies and nothing in it does"
            assert all(line.strip() != "…" for line in lines), f"{rel(page)}:{block.line}: a line that is … alone stands for anything"


def test_tf5_15_what_may_vary_is_a_path_a_time_an_id_or_a_version() -> None:
    for fine in ("/tmp/work/store", "file:///tmp/x/index.html", "~/.cache/poisson-trace/errors.log", "2026-11-12", "2026-11-12T18:50:01Z",
                 "2026-11-12 18:50", "0.4 s", "12 ms", "3fa9c1d2e4b5a697", "20260915T210140Z-4847", "3.12.13", "0.1.0a1"):
        assert VARIES.fullmatch(fine), fine
    for not_fine in ("different", "3 of 9", "12.5%", "no significant difference", "old", "0.21", "p = 0.4", "ok", "8", "unsolved"):
        assert not VARIES.fullmatch(not_fine), not_fine
    from tf5_support import docs_check

    assert VARIES is docs_check.VARIES, "the rule held here is the checker's own"
    assert docs_check.line_holds("wrote …, in …", "wrote /tmp/x/out.json, in 0.4 s", True)
    assert not docs_check.line_holds("wrote …, no … difference", "wrote /tmp/x/out.json, no significant difference", True), "every … of a line is held"
    assert not docs_check.line_holds("no significant difference", "no significant differencE", True)


# ---------- TF5-16 ----------


@pytest.mark.parametrize("page", PAGES, ids=IDS)
def test_tf5_16_a_service_is_asked_only_in_a_block_marked_pull(page: Path) -> None:
    prefixes = tuple(prefix for prefix, _ in ADDRESS.values())
    for block in _blocks(page):
        if block.kind != "command":
            continue
        asked = [word for command in words(block) for word in command if word.startswith(prefixes)]
        if block.pull:
            assert asked, f"{rel(page)}:{block.line}: marked pull and asks no service"
        else:
            assert not asked, f"{rel(page)}:{block.line}: asks {asked} and is not marked pull"


def test_tf5_16_a_command_not_marked_pull_cannot_reach_a_service(tmp_path: Path) -> None:
    """The runner itself: the same address refused outside a block marked pull, answered from
    the captures inside one."""
    page = tmp_path / "page.md"
    command = ("poisson-trace import weave weave:example-entity/trace-fixture/trace-fixture-slice-baseline --store s{n} --run old "
               "--case-from example --outcome-from status")
    page.write_text(
        "# A page\n\n<!-- command -->\n```\n" + command.format(n=1) + "\n```\n\n<!-- excerpt exit=0 -->\n```\nok\n```\n\n"
        "<!-- command pull -->\n```\n" + command.format(n=2) + "\n```\n\n<!-- excerpt exit=0 -->\n```\nok\n```\n", encoding="utf-8")
    import tf5_support

    blocks = tf5_support.parse(page.read_text(encoding="utf-8"))[0]
    root, home, bin_dir = tf5_support.page_root(tmp_path), tmp_path / "home", tf5_support.shims(tmp_path / "bin")
    home.mkdir()
    plain = tf5_support.run_block(blocks[0], root, tf5_support.page_env(home, bin_dir, pull=False))
    pulled = tf5_support.run_block(blocks[2], root, tf5_support.page_env(home, bin_dir, pull=True))
    assert plain[0] != 0 and not (root / "s1").exists(), plain
    assert pulled[0] == 0 and (root / "s2" / "old" / "manifest.json").is_file() and pulled[1].startswith("ok  "), pulled
    assert "planted" not in pulled[1] and "planted" not in plain[1]


# ---------- TF5-17 ----------


@pytest.mark.parametrize("page", PAGES, ids=IDS)
def test_tf5_17_no_command_names_a_run_by_its_id(page: Path) -> None:
    for command in trace_commands(read(page), ("command", "skip")):
        assert not [word for word in command if RUN_ID.search(word)], (rel(page), command)


# ---------- TF5-18 ----------


def _shown_after(blocks: list[Block], at: int) -> Block | None:
    """The first output or excerpt under the command block at ``at``, before the next command."""
    for block in blocks[at + 1:]:
        if block.kind in ("output", "excerpt"):
            return block
        if block.kind in ("command", "skip"):
            return None
    return None


def _runs_shown(page: Path, verb: str) -> list[tuple[int, list[str]]]:
    """The page's command blocks that run the verb and show, exit 0, what it printed."""
    blocks = _blocks(page)
    out = []
    for at, block in enumerate(blocks):
        if block.kind != "command":
            continue
        shown = _shown_after(blocks, at)
        if shown is None or shown.code != 0 or not shown.body.strip():
            continue
        for command in trace_commands("<!-- command -->\n```\n" + block.body + "\n```\n"):
            if command[:1] == [verb]:
                out.append((at, command))
    return out


def test_tf5_18_prove_s_stored_runs_have_a_first_result() -> None:
    page = recipe("first-look.md")
    order = [_runs_shown(page, verb) for verb in ("init", "runs", "where")]
    assert all(order), "first-look.md runs init, runs and where, and shows what each printed"
    assert order[0][0][0] <= order[1][0][0] <= order[2][0][0], "init, then runs, then where"
    copied = [command for block in _blocks(page) if block.kind == "command" for command in words(block) if "tests/fixtures/cs" in " ".join(command)]
    assert copied, "first-look.md starts from the committed store of the recorded demo"


@pytest.mark.parametrize("tool", [source for source in RECIPES.values() if source not in (None, "prove")])
def test_tf5_18_each_tool_has_a_first_result_on_its_recipe(tool: str) -> None:
    (name,) = [page for page, source in RECIPES.items() if source == tool]
    page = recipe(name)
    imports = [(at, command) for at, command in _runs_shown(page, "import") if command[1:2] == [tool]]
    by_init = [command for _, command in _runs_shown(page, "init")]
    assert len(imports) >= 2 or by_init, f"{name}: two imports of {tool}, or init importing them, each with what it printed"
    if len(imports) >= 2:
        runs = [command[command.index("--run") + 1] for _, command in imports if "--run" in command]
        assert len(set(runs)) >= 2, (name, runs)
    checks = _runs_shown(page, "fix-check")
    assert checks, f"{name}: fix-check on the two runs, with what it printed"
    if len(imports) >= 2:
        assert all(any(run in command for run in runs) for _, command in checks), f"{name}: the fix check names the runs imported"
    first = min(at for at, _ in checks)
    assert all(at < first for at, _ in imports[:2]), f"{name}: the imports come before the fix check"
    fixtures = [word for block in _blocks(page) if block.kind == "command" for command in words(block) for word in command
                if "tests/fixtures/" in word]
    assert fixtures, f"{name}: runs on the committed fixtures"


@pytest.mark.parametrize("tool", API_TOOLS)
def test_tf5_18_each_service_is_pulled_once_on_a_page_that_runs(tool: str) -> None:
    """On the tool's recipe or its integration page: a block marked pull that imports by the
    committed address, shows what the pull printed, and is followed by a verb that reads the
    pulled run and shows its result."""
    prefix, _ = ADDRESS[tool]
    (name,) = [page for page, source in RECIPES.items() if source == tool]
    found = False
    for page in (recipe(name), DOCS / "integrations" / f"{tool}.md"):
        blocks = _blocks(page)
        for at, block in enumerate(blocks):
            if block.kind != "command" or not block.pull:
                continue
            pulls = [command for command in trace_commands("<!-- command -->\n```\n" + block.body + "\n```\n")
                     if command[:2] == ["import", tool] and any(word.startswith(prefix) for word in command)]
            shown = _shown_after(blocks, at)
            if not pulls or shown is None or shown.code != 0:
                continue
            store = pulls[0][pulls[0].index("--store") + 1]
            later = [command for a, command in (*_runs_shown(page, "fix-check"), *_runs_shown(page, "where"), *_runs_shown(page, "runs"))
                     if a > at and store in command]
            found = found or bool(later)
    assert found, f"{tool}: no page pulls it by its address from the captures and reads the pulled run"


# ---------- TF5-19 ----------


def _recipe_blocks() -> tuple[set[str], list[str]]:
    commands: set[str] = set()
    shown: list[str] = []
    for name in RECIPES:
        for block in _blocks(recipe(name)):
            if block.kind == "command":
                commands.add(block.body.strip())
            elif block.kind in ("output", "excerpt"):
                shown.append(block.body)
    return commands, shown


def test_tf5_19_every_block_the_readme_shows_is_a_recipe_s_block() -> None:
    commands, shown = _recipe_blocks()
    for block in _blocks(README):
        if block.kind == "command":
            assert block.body.strip() in commands, f"README.md:{block.line}: this command is on no recipe:\n{block.body}"
        elif block.kind in ("output", "excerpt"):
            assert any(("\n" + block.body + "\n") in ("\n" + body + "\n") for body in shown), \
                f"README.md:{block.line}: these lines are on no recipe:\n{block.body}"
