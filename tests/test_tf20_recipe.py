"""TF20-1 to TF20-9, TF20-40 to TF20-46 and TF20-50: the recipe that runs Tasks, Prove and Trace
together, as a page (spec section 17.6; section 7.1's rules; the brief's rules 1, 5 and 6). What
its fixtures must be is ``test_tf20_fixtures.py``; that it moves nothing else,
``test_tf20_unchanged.py``.

The page is one of the docs pair's recipes (``tf5_support.RECIPES``), so every rule the docs pair
holds a recipe to holds it too, by the docs pair's own tests: the marks and their faults, no
unmarked block, skipped blocks and what may be skipped (TF5-11 to TF5-13); every marked block
holding when the page is run, byte for byte or under *varies* (TF5-14, TF5-15); no run named by
its id (TF5-17); under 150 lines, opening with what you have and ending with "What this does not
do" (TF5-70); every ``poisson-trace`` block run and shown (TF5-71); runs named before they are
read (TF5-72); relative links that lead somewhere (TF5-76); the reader-list rule (TF5-21,
TF5-24); the unit rule (TF5-38); plain words (TF0-21); reached from the README by an absolute
link (TF5-25, TF5-69). TF20-46 holds that those tests read this page.

**Rule 1: every step of section 17.6's story, as blocks the docs runner runs.**

- TF20-1: the story's commands, each in a block marked ``command`` (never skipped), in the
  story's order: Tasks' ``generate`` word for word as section 17.6 writes it; ``generate
  --show``; Prove's two sweeps, each of its spec file, named ``agent before`` and ``agent
  after``; Trace's ``init``; ``fix-check "agent before" "agent after" --inputs all --max-mde
  0.20``; ``where "agent before"``; the team's pytest file run twice with ``--junitxml``, to two
  reports; ``import junit`` of each, under two names; and a ``fix-check`` of those two runs.
- TF20-2: each of those blocks shows, exit 0, something of what it printed.
- TF20-3: ``init`` is run with its answers given (``command tty answers="…"``, at least one
  answer), shows the line that says it wrote ``trace.toml``, and finds the store Prove wrote.
- TF20-4: Trace reads the names from the runs' manifests: no ``poisson-trace name``, and the
  verbs name the runs ``agent before`` and ``agent after``.
- TF20-5: the two sweeps are the same command but for the spec file and the name: the same
  flags, the local backend, and the replicates the spec files hold (no ``--replicates``); a
  ``--pair-with`` on the after sweep is allowed and not required. Both carry one fixed
  ``--salt``, the same on both (Taylor's ruling on TT-11, 2026-11-15), so that every count
  ``fix-check`` and ``where`` print repeats from run to run: what the page shows of them is held
  byte for byte, never under *varies*; a sweep run again as the page writes it stores the same
  tries; and two whole runs of the page print the same ``fix-check`` and ``where``, byte for byte
  but for the runs' ids, start times and the seconds between them (slow; the sweep run again is
  its fast twin).
- TF20-6: ``generate --show`` prints one task in full, and the page shows its reference solution;
  and the page says in one sentence what a task is.
- TF20-7: run whole, the page's ``fix-check`` on Prove's runs says the new version failed less;
  the fix check on the JUnit reports gives the same answer, its verdict line the same line.
- TF20-8: the page installs Tasks at its pin, in a block that is shown and skipped as an
  install, and fetches the tokenizer file there too.
- TF20-9: the page compares what ``generate`` wrote with the committed files, byte for byte, in
  a block the docs runner runs, and shows the comparison passing.

**Rule 5: what the page claims it shows, it shows.**

- TF20-40: every figure the page writes in prose is one its commands printed, or one of its
  commands holds.
- TF20-41: each claim of section 17.6's story the page makes is backed by a block it runs and
  shows: the 20 tasks, the files byte for byte, no model and the cost ($0, from Prove's plan),
  fewer failures, the step the old version dies at, the same answer from JUnit.
- TF20-42: every link to another of the lab's tools is absolute; the page names
  ``examples/three-tools/`` and links nothing outside the repository but by ``https://``.
- TF20-43: the stand-in is said plainly to be one, and to call no model.
- TF20-44: the page names no version of Tasks but the pin, and no version of Prove but Trace's.
- TF20-45: each command word the page runs is one a reader has after the install line:
  ``poisson-tasks``, ``poisson-prove``, ``poisson-trace``, ``pytest`` and the shell's own.
- TF20-46: the docs pair's tests read this page: it is among their recipes, their pages and the
  pages the reader-list and unit rules read.

**Rule 6.** TF20-50: "What this does not do" says what section 17.6 lists: the stand-in is not an
agent; a real agent's runs cost what its model costs; Tasks' ``run`` and ``card`` need a model
and are not in the recipe; Prove's run here is the local backend.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from tf5_support import RECIPES, Block, expected_pages, read
from tf20_support import (
    FIX_CHECK, GENERATE, NAME, PAGE, PROVE_VERSION, RUNS, SPECS, TASKS_PIN, TASKS_VERSION, Ran, blocks, every_command, first_line, page_prose,
    page_sections, rows, run_whole, sentences, shared_run, store_of,
)


@pytest.fixture(scope="module")
def ran(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Ran]:
    yield shared_run(tmp_path_factory)


def _commands() -> list[tuple[int, Block, list[str]]]:
    return list(every_command())


def _find(predicate: object) -> list[tuple[int, Block, list[str]]]:
    return [(at, block, command) for at, block, command in _commands() if predicate(command)]  # type: ignore[operator]


def _trace(command: list[str], verb: str) -> bool:
    return command[:2] == ["poisson-trace", verb]


def _sweep(command: list[str], version: str) -> bool:
    return command[:2] == ["poisson-prove", "sweep"] and any(Path(word).name == SPECS[version].name for word in command[2:])


def _junit_imports() -> list[tuple[int, Block, list[str]]]:
    return _find(lambda c: c[:3] == ["poisson-trace", "import", "junit"])


def _junit_check() -> list[tuple[int, Block, list[str]]]:
    names = {c[c.index("--run") + 1] for _, _, c in _junit_imports() if "--run" in c}
    return _find(lambda c: _trace(c, "fix-check") and len(c) > 3 and {c[2], c[3]} == names and len(names) == 2)


def _shown_under(at: int) -> list[Block]:
    out = []
    for later in blocks()[at + 1:]:
        if later.kind in ("command", "skip"):
            break
        if later.kind in ("output", "excerpt"):
            out.append(later)
    return out


def _story() -> dict[str, list[tuple[int, Block, list[str]]]]:
    return {
        "generate": _find(lambda c: tuple(c) == GENERATE),
        "show": _find(lambda c: c[:2] == ["poisson-tasks", "generate"] and "--show" in c),
        "sweep before": _find(lambda c: _sweep(c, "before")),
        "sweep after": _find(lambda c: _sweep(c, "after")),
        "init": _find(lambda c: _trace(c, "init")),
        "fix-check": _find(lambda c: tuple(c[1:]) == FIX_CHECK),
        "where": _find(lambda c: c[1:3] == ["where", RUNS["before"]]),
        "pytest": _find(lambda c: c[:1] == ["pytest"] or c[:3] == ["python", "-m", "pytest"]),
        "import junit": _junit_imports(),
        "fix-check junit": _junit_check(),
    }


# ---------- TF20-1 ----------


def test_tf20_1_every_step_of_the_story_is_run_in_its_order() -> None:
    story = _story()
    missing = [step for step, found in story.items() if not found]
    assert missing == [], f"{NAME} runs no block for {missing}"
    order = ["generate", "sweep before", "sweep after", "init", "fix-check", "pytest", "import junit", "fix-check junit"]
    firsts = [min(at for at, _, _ in story[step]) for step in order]
    assert firsts == sorted(firsts), dict(zip(order, firsts, strict=True))
    assert min(at for at, _, _ in story["show"]) >= min(at for at, _, _ in story["generate"]), "one task shown, of the tasks generated"
    assert min(at for at, _, _ in story["where"]) > min(at for at, _, _ in story["init"])
    assert max(at for at, _, _ in story["sweep before"]) < min(at for at, _, _ in story["fix-check"])


def test_tf20_1_the_team_s_tests_write_one_report_a_version() -> None:
    reports: list[str] = []
    for _, _, command in _story()["pytest"]:
        found = [w.split("=", 1)[1] for w in command if w.startswith("--junitxml=")]
        found += [command[i + 1] for i, w in enumerate(command[:-1]) if w == "--junitxml"]
        reports += found
    assert len(reports) == 2 and len(set(reports)) == 2, reports
    imported = [w for _, _, c in _junit_imports() for w in c[3:] if w.endswith(".xml")]
    assert sorted(imported) == sorted(reports), (imported, reports)
    names = [c[c.index("--run") + 1] for _, _, c in _junit_imports() if "--run" in c]
    assert len(names) == 2 and len(set(names)) == 2, names
    assert len(_story()["fix-check junit"]) >= 1
    for _, _, command in _story()["fix-check junit"]:
        assert ["--inputs", "all"] == command[command.index("--inputs"):command.index("--inputs") + 2] and "--max-mde" in command, command
        assert command[command.index("--max-mde") + 1] == "0.20", "the same fix check: the same size asked about"


def test_tf20_1_every_story_block_is_run_and_never_skipped() -> None:
    for block in blocks():
        if block.kind == "skip":
            body = block.body
            for word in ("generate", "sweep", "fix-check", "where", "--junitxml", "import junit"):
                assert word not in body, f"{NAME}:{block.line}: a step of the story is shown and not run: {body}"


# ---------- TF20-2 ----------


def test_tf20_2_each_step_shows_what_it_printed() -> None:
    for step, found in _story().items():
        for at, block, _ in found:
            shown = _shown_under(at)
            assert shown and any(b.code == 0 and b.body.strip() for b in shown), f"{NAME}:{block.line}: {step} shows nothing it printed, exit 0"


# ---------- TF20-3 ----------


def test_tf20_3_init_is_run_with_its_answers_given(ran: Ran) -> None:
    (at, block, command), = _story()["init"]
    assert block.answers is not None and len(block.answers) >= 1, \
        f"{NAME}:{block.line}: init is run with its answers typed (command tty answers=\"…\"), as section 8.4 runs it"
    assert "--yes" not in command, "the answers given, not --yes"
    shown = "\n".join(b.body for b in _shown_under(at))
    assert re.search(r"(?m)^ok  wrote trace\.toml: store \S+ \(2 runs\)", shown), shown
    printed = [c for c in ran.checked if c.ran.line == block.line]
    assert printed and printed[0].code == 0 and re.search(r"(?m)^ok  wrote trace\.toml: store ", printed[0].printed), printed


# ---------- TF20-4 ----------


def test_tf20_4_the_names_are_the_manifests() -> None:
    assert not _find(lambda c: _trace(c, "name")), "Trace reads the names the sweeps gave: no poisson-trace name"
    for _, _, command in _story()["sweep before"]:
        assert command[command.index("--name") + 1] == RUNS["before"], command
    for _, _, command in _story()["sweep after"]:
        assert command[command.index("--name") + 1] == RUNS["after"], command


# ---------- TF20-5 ----------


def test_tf20_5_the_two_sweeps_differ_in_the_spec_and_the_name_alone() -> None:
    (_, _, before), = _story()["sweep before"]
    (_, _, after), = _story()["sweep after"]
    assert "--replicates" not in before + after, "the replicates are the spec files'"
    assert not any(w.startswith("--backend") for w in before + after) or ("--backend" in before and before[before.index("--backend") + 1] == "local")

    def bare(command: list[str], version: str) -> list[str]:
        out = []
        skip = False
        for word in command:
            if skip:
                skip = False
                continue
            if word == "--name":
                skip = True
                continue
            if Path(word).name == SPECS[version].name:
                out.append("SPEC")
                continue
            if word == "--pair-with" and version == "after":
                skip = True
                continue
            out.append(word)
        return out

    assert bare(before, "before") == bare(after, "after"), (before, after)


def _salts(command: list[str]) -> list[str]:
    found = [w.split("=", 1)[1] for w in command if w.startswith("--salt=")]
    return found + [command[i + 1] for i, w in enumerate(command[:-1]) if w == "--salt"]


def test_tf20_5_both_sweeps_carry_one_fixed_salt_the_same() -> None:
    (_, _, before), = _story()["sweep before"]
    (_, _, after), = _story()["sweep after"]
    salts = {"before": _salts(before), "after": _salts(after)}
    assert len(salts["before"]) == 1 and len(salts["after"]) == 1, salts
    assert salts["before"] == salts["after"] and salts["before"][0].strip(), salts
    assert not re.search(r"[$`*?]", salts["before"][0]), "a fixed salt, written out"


def test_tf20_5_what_fix_check_and_where_print_is_held_byte_for_byte() -> None:
    for step in ("fix-check", "where"):
        for at, block, _ in _story()[step]:
            shown = _shown_under(at)
            assert shown, f"{NAME}:{block.line}: {step} shows nothing"
            for b in shown:
                assert not b.varies, f"{NAME}:{b.line}: what {step} prints repeats from run to run, so it is held, never under varies"
    (at, _, _), = _story()["where"][:1]
    table = "\n".join(b.body for b in _shown_under(at))
    assert re.search(r"(?m)^\| \d+ \| [\d,]+ \| [\d,]+ \| ", table), "where's counts are shown, and held"


def _episodes(run: Path) -> list[tuple[object, ...]]:
    found = rows(run)
    return sorted(zip(found["config"], found["seed"], found["outcome"], found["t"], found["horizon"], strict=True))


def test_tf20_5_a_sweep_run_again_stores_the_same_tries(ran: Ran, tmp_path: Path) -> None:
    (_, block, _), = _story()["sweep before"]
    shutil.copytree(ran.root / "examples", tmp_path / "examples",
                    ignore=shutil.ignore_patterns("prove-runs", "tests-runs", "*.xml", "trace.toml", "__pycache__"))
    proc = subprocess.run(["bash", "-c", block.body.replace("\\\n", " ").strip()], cwd=tmp_path, env=ran.env(ran.own_home(tmp_path)), capture_output=True,
                          text=True, timeout=900, stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    again, first = store_of(tmp_path, RUNS["before"]), store_of(ran.root, RUNS["before"])
    assert again != first
    assert _episodes(again) == _episodes(first), "the same salt, the same tries: every count fix-check and where print repeats"


VARYING = (
    (re.compile(r"\b\d{8}T\d{6}Z-[0-9a-f]+\b"), "RUN-ID"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\b"), "STARTED"),
    (re.compile(r"\bstarted [\d,.]+ (?:s|min|h|seconds?|minutes?|hours?) apart\b"), "started APART"),
    (re.compile(r"\btimestamps are [\d,.]+ (?:s|min|h|seconds?|minutes?|hours?) apart\b"), "timestamps are APART"),
)


def _held(text: str) -> str:
    for pattern, word in VARYING:
        text = pattern.sub(word, text)
    return text


@pytest.mark.slow
def test_tf20_5_two_whole_runs_of_the_page_print_the_same_counts(ran: Ran, tmp_path: Path) -> None:
    """The first whole run is the one every test of the page reads; the second is made here."""
    printed = []
    (tmp_path / "run-2").mkdir()
    for whole in (ran, run_whole(tmp_path / "run-2")):
        printed.append({c.command: c.printed for c in whole.checked
                        if re.search(r"poisson-trace (fix-check|where) ", c.command)})
    assert printed[0] and set(printed[0]) == set(printed[1])
    assert len([c for c in printed[0] if "fix-check" in c]) >= 2 and [c for c in printed[0] if " where " in c]
    for command in printed[0]:
        assert _held(printed[0][command]) == _held(printed[1][command]), command


# ---------- TF20-6 ----------


def test_tf20_6_one_task_shown_whole_and_what_a_task_is(ran: Ran) -> None:
    (at, block, _), = _story()["show"][:1]
    printed = [c for c in ran.checked if c.ran.line == block.line]
    assert printed and printed[0].code == 0
    for part in ("what the model is shown", "the tools it may call", "the reference solution", "the wrong answers it ships with"):
        assert part in printed[0].printed, part
    shown = "\n".join(b.body for b in _shown_under(at))
    assert "the reference solution" in shown or "the wrong answers it ships with" in shown, "the page shows the task's answer and its checker's verdicts"
    said = [s for s in sentences(page_prose()) if re.match(r"(?i)^an? task is\b", s)]
    assert len(said) == 1 and len(said[0].split()) >= 8, said


# ---------- TF20-7 ----------


def test_tf20_7_prove_s_runs_and_the_team_s_tests_give_the_same_answer(ran: Ran) -> None:
    (_, prove_block, _), = _story()["fix-check"]
    junit_block = _story()["fix-check junit"][0][1]
    prove = [c for c in ran.checked if c.ran.line == prove_block.line]
    junit = [c for c in ran.checked if c.ran.line == junit_block.line]
    assert prove and junit and prove[0].code == 0 and junit[0].code == 0
    verdict = first_line(prove[0].printed)
    assert verdict.startswith("different ") and "failed less" in verdict, verdict
    assert first_line(junit[0].printed) == verdict, (first_line(junit[0].printed), verdict)


# ---------- TF20-8 ----------


def test_tf20_8_the_install_names_the_pin_and_fetches_the_tokenizer() -> None:
    installs = [b for b in blocks() if b.kind == "skip" and re.search(r"\bpip install\b", b.body)]
    assert installs, "the install, shown and skipped"
    text = "\n".join(b.body for b in installs)
    assert TASKS_PIN in text and "poisson-trace" in text, text
    assert re.search(r"poisson-tasks doctor --fix\b|poisson_tasks\.fetch_encoding", text), "the tokenizer file, fetched in the install"
    for block in installs:
        assert re.search(r"(?i)package index|network|internet", block.reason), block.reason


# ---------- TF20-9 ----------


def test_tf20_9_the_files_are_compared_byte_for_byte(ran: Ran) -> None:
    compares = [(at, block, c) for at, block, c in _commands() if c[:1] in (["cmp"], ["diff"])
                and any("examples/three-tools/tasks" in w or w.startswith("tasks/") or w == "tasks" for w in c)]
    files = {w for _, _, c in compares for w in c if w.endswith(".jsonl")}
    folders = [c for _, _, c in compares if c[:1] == ["diff"] and "-r" in c]
    assert compares and (folders or {"depth-d1.jsonl", "depth-d3.jsonl"} <= {Path(f).name for f in files}), compares
    for at, block, _ in compares:
        printed = [c for c in ran.checked if c.ran.line == block.line]
        assert printed and printed[0].code == 0, f"{NAME}:{block.line}: the comparison passes"
        assert any(b.code == 0 for b in _shown_under(at))


# ---------- TF20-40 ----------


FIGURE = re.compile(r"(?<![\w.\-/:])\d[\d,]*(?:\.\d+)*(?![\w\-/])")


def _figures(text: str) -> list[str]:
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    text = re.sub(r"(?m)^#+ \d+\.", "#", text)
    text = re.sub(r"(?m)^\s*\d+\. ", "", text)
    return [m.group(0).rstrip(".,") for m in FIGURE.finditer(text)]


def test_tf20_40_every_figure_in_prose_is_one_a_command_printed(ran: Ran) -> None:
    shown = "\n".join(b.body for b in blocks() if b.kind in ("output", "excerpt", "command"))
    printed = "\n".join(c.printed for c in ran.checked)
    allowed = {TASKS_VERSION, PROVE_VERSION}
    for figure in _figures(page_prose()):
        if figure in allowed:
            continue
        assert re.search(rf"(?<![\d.]){re.escape(figure)}(?![\d])", shown) and re.search(rf"(?<![\d.]){re.escape(figure)}(?![\d])", printed), \
            f"{NAME}: {figure} is written in prose and no block shows a command printing it"


# ---------- TF20-41 ----------


CLAIMS: tuple[tuple[str, str, str], ...] = (
    (r"\b20 tasks\b|\btwenty tasks\b", r"generated 20 tasks", "the twenty tasks"),
    (r"(?i)byte for byte", r"(?s).", "the files byte for byte (TF20-9)"),
    (r"(?i)\$0\b|costs? nothing|no cost|free of charge|\bfor free\b", r"\$0\b", "the cost, as Prove's plan states it"),
    (r"(?i)fails? less|failed less|fewer failures", r"(?m)^different\s+the new version failed less", "the verdict"),
    (r"(?i)\bdies?\b|\bdied\b|\bdying\b", r"(?i)\bstep\b", "where it dies"),
)


@pytest.mark.parametrize("said, printed, what", CLAIMS, ids=[what for _, _, what in CLAIMS])
def test_tf20_41_each_claim_is_backed_by_a_block_that_shows_it(said: str, printed: str, what: str) -> None:
    if not re.search(said, page_prose()):
        return
    shown = [b.body for b in blocks() if b.kind in ("output", "excerpt") and b.code == 0]
    assert any(re.search(printed, body) for body in shown), f"{NAME} says {what} and shows no block that prints it"


def test_tf20_41_the_page_says_the_story_s_claims() -> None:
    said = page_prose()
    assert re.search(r"(?i)no model", said), "no model call"
    assert re.search(r"(?i)\$0\b|costs? nothing", said), "and $0"
    assert re.search(r"(?i)fails? less|failed less|fewer failures", said)
    assert re.search(r"(?i)byte for byte", said)


def test_tf20_41_where_shows_the_step_the_old_version_dies_at() -> None:
    (at, _, _), = _story()["where"][:1]
    shown = "\n".join(b.body for b in _shown_under(at))
    for step in (2, 3):
        assert re.search(rf"(?m)^\| {step} \||\bstep {step}\b", shown), f"where's shown lines name step {step}, where the token is lost"
    assert not re.search(r"(?m)^\| 1 \|", shown), "and no try fails at step 1"


# ---------- TF20-42 ----------


def test_tf20_42_links_to_the_other_tools_are_absolute_and_the_fixtures_are_named() -> None:
    text = read(PAGE)
    links = re.findall(r"\]\(([^)\s]+)\)", page_prose())
    for link in links:
        if re.search(r"(?i)poisson-labs/(tasks|prove)|poisson[-_](tasks|prove)", link):
            assert link.startswith("https://"), link
        assert not link.startswith(("http://", "file:", "/")), link
        if not link.startswith(("https://", "#", "mailto:")):
            assert (PAGE.parent / link.split("#")[0]).resolve().is_relative_to(PAGE.parents[2]), f"{link} leaves the repository"
    assert "examples/three-tools" in page_prose(), "the page says where its files are"
    assert "Obsidian" not in text and "vault" not in text.lower()


# ---------- TF20-43 ----------


def test_tf20_43_the_stand_in_is_said_plainly_to_call_no_model() -> None:
    said = [s for s in sentences(page_prose()) if re.search(r"(?i)stand-in", s)]
    assert any(re.search(r"(?i)\bcalls no model\b|\bno model call\b|\bmakes no model call\b|\bdoes not call a model\b", s) for s in said), said
    assert "agent.py" in page_prose()


# ---------- TF20-44 ----------


def test_tf20_44_the_versions_are_the_pins() -> None:
    text = read(PAGE)
    for found in re.finditer(r"poisson-tasks\s*(?:==|\s)\s*(\d+\.\d+\.\d+)|Poisson Tasks (\d+\.\d+\.\d+)", text):
        assert TASKS_VERSION in found.groups(), found.group(0)
    for found in re.finditer(r"poisson-prove\s*(?:==|\s)\s*(\d+\.\d+\.\d+)|Prove (\d+\.\d+\.\d+)", text):
        assert PROVE_VERSION in found.groups(), found.group(0)


# ---------- TF20-45 ----------


SHELL = ("cd", "cmp", "diff", "echo", "test", "ls", "cat", "head", "tail", "grep", "mkdir", "cp", "rm", "export", "env", "sed", "wc", "sort",
         "shasum", "sha256sum", "true", "[")


def test_tf20_45_every_command_is_one_the_reader_has() -> None:
    for _, block, command in _commands():
        word = command[0]
        assert word in ("poisson-tasks", "poisson-prove", "poisson-trace", "pytest", *SHELL) or command[:3] == ["python", "-m", "pytest"], \
            f"{NAME}:{block.line}: {shlex.join(command)}"


# ---------- TF20-46 ----------


def test_tf20_46_the_docs_pair_s_tests_read_this_page() -> None:
    assert NAME in RECIPES and RECIPES[NAME] is None
    assert PAGE in expected_pages()
    from test_tf5_readers import LISTING
    from test_tf5_units import PAGES as UNIT_PAGES

    assert PAGE in LISTING and PAGE in UNIT_PAGES
    from test_tf0_plain_words import _user_files

    assert PAGE in [Path(p).resolve() for p in _user_files()]


# ---------- TF20-50 ----------


NOT_DONE: tuple[tuple[str, str], ...] = (
    ("the stand-in is not an agent", r"(?i)stand-in[^.;]*\bis not an? (?:real )?agent"),
    ("a real agent's runs cost what its model costs", r"(?i)real agent[^.;]*\bcosts?\b[^.;]*\bmodel\b"),
    ("Tasks' run and card need a model and are not in the recipe",
     r"(?i)(?=[^\n]*`run`)(?=[^\n]*`card`)(?=[^\n]*\bmodel\b)(?=[^\n]*\bnot (?:in|part of|used in|run in)\b)"),
    ("Prove's run here is the local backend", r"(?i)\bProve\b[^.;]*\blocal backend\b"),
)


@pytest.mark.parametrize("what, pattern", NOT_DONE, ids=[what for what, _ in NOT_DONE])
def test_tf20_50_what_this_does_not_do(what: str, pattern: str) -> None:
    section = page_sections().get("What this does not do")
    assert section is not None
    items = re.split(r"(?m)^- ", section)
    flat = [re.sub(r"\s+", " ", item) for item in items if item.strip()]
    assert any(re.search(pattern, item) for item in flat), f"{NAME}'s last section does not say: {what}"
