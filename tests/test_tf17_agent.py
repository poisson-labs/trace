"""TF17-1 to TF17-4: ``poisson-trace init --agent`` writes the setup a person's own coding agent
follows (spec section 17.4, the shared setup-file page section 1, and Prove's section 20.1 with
its readings (a) to (e) and (z), (dd), carried over with Trace's names).

- TF17-1: in the repository (the folder it runs in, or ``--repo DIR``; no root is looked for) it
  writes exactly four files, ``.agents/skills/poisson-trace-setup/SKILL.md`` and ``prompt.txt``
  and the same bytes under ``.claude/skills/poisson-trace-setup/``, and nothing else anywhere;
  each ``SKILL.md`` is the packaged template with only the ``poisson-tool-version`` line filled,
  to the version ``--version`` prints; each ``prompt.txt`` is the prompt and a final newline. A
  ``trace.toml`` or a store already there is not refused for: only the four files are its own.
  It makes no model call, reads no key and opens no connection.
- TF17-2: its output is ``ok  wrote … (4 files)``, one ``  wrote  <path>`` line per file, the
  ``  prompt  <the prompt>`` line and one ``  next:`` line that is not a command, nothing else on
  stdout and nothing on stderr; ``--json`` is ``poisson-trace.init/1`` with ``wrote`` (the four
  paths) and ``prompt``, and ``next`` last.
- TF17-3: any of the four existing is refused without ``--force`` (exit 1, stdout empty, the
  ``error:`` line naming each that exists, a ``next:`` line that is the command as typed with
  ``--force``, nothing written); ``--force`` replaces the four and keeps every other file, one of
  the person's own inside the skill's folder included; ``--print`` prints exactly the bytes
  ``init --agent`` writes, is never refused for existing files and writes nothing.
- TF17-4: ``--agent`` with any flag of the guided setup, and ``--repo`` or ``--print`` without
  ``--agent``, are wrong command lines (exit 2, nothing written); ``--print`` with ``--json``
  too; a ``--repo`` that is not a folder is a refusal naming it (exit 1); ``init --help`` names
  ``--agent``, ``--repo`` and ``--print``, each with its default where it takes a value.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from tf0_support import help_entries
from tf1_support import shell_words
from tf2_support import no_network, scratch_home, tau2_copy, tty, work  # noqa: F401  (fixtures)
from tf17_support import (
    COMMAND, FOLDERS, FOUR, INIT_KEYS, INIT_SCHEMA, PROMPT, TEMPLATE, added, agent, fresh_skill,
    parse_frontmatter, refusal, sample_repo, snapshot, split_frontmatter, trace_in, usage,
    users_own_files, version,
)

# ---------- TF17-1 ----------

TF17_1_CASES = [
    "an empty folder",
    "a repository with the person's own files",
    "a repository already set up",
    "--repo from another folder",
    "a folder inside a git repository",
    "a folder holding a store",
]


@pytest.mark.parametrize("case", TF17_1_CASES)
def test_tf17_1_init_agent_writes_the_four_files_from_the_template_and_nothing_else(case: str, tmp_path: Path, no_network: list[str]) -> None:  # noqa: F811
    home = Path(os.environ["HOME"])
    argv: list[str] = []
    if case == "an empty folder":
        repo = cwd = work(tmp_path, "empty")
    elif case == "a repository with the person's own files":
        repo = cwd = sample_repo(tmp_path, user_files=True)
    elif case == "a repository already set up":
        # trace.toml is there already: setting up the agent is not refused for it
        repo = cwd = sample_repo(tmp_path, with_expected=True, user_files=True)
    elif case == "--repo from another folder":
        repo = sample_repo(tmp_path, user_files=True)
        cwd = work(tmp_path, "elsewhere")
        argv = ["--repo", str(repo)]
    elif case == "a folder inside a git repository":
        (tmp_path / "project" / ".git").mkdir(parents=True)
        repo = cwd = tmp_path / "project" / "service"
        repo.mkdir()
    else:
        repo = cwd = work(tmp_path, "with-store")
        tau2_copy(repo, "proofload-runs")
    roots = (tmp_path, home)
    before = snapshot(*roots)

    r = agent(cwd, *argv)

    assert r.code == 0, r.text
    assert r.err == "", r.err
    assert no_network == []
    # exactly the four files, in the repository as given, and nothing else anywhere
    assert added(before, snapshot(*roots), tmp_path) == sorted(str((repo / f).relative_to(tmp_path)) for f in FOUR)
    skills = [(repo / f).read_bytes() for f in FOUR if f.endswith("SKILL.md")]
    assert skills[0] == skills[1]
    for f in FOUR:
        if f.endswith("prompt.txt"):
            assert (repo / f).read_text(encoding="utf-8") == PROMPT + "\n"
    # the packaged template with only the version filled (Prove's reading a)
    assert TEMPLATE.is_file(), TEMPLATE
    written = skills[0].decode("utf-8").splitlines()
    template = TEMPLATE.read_text(encoding="utf-8").splitlines()
    assert len(written) == len(template), (len(written), len(template))
    differ = [i for i, (w, t) in enumerate(zip(written, template, strict=True)) if w != t]
    assert len(differ) == 1 and written[differ[0]].startswith("  poisson-tool-version:"), [written[i] for i in differ]
    front = parse_frontmatter(split_frontmatter(skills[0].decode("utf-8"))[0])
    assert front["metadata"]["poisson-tool-version"] == version()


def test_tf17_1_the_template_is_package_data_and_the_skill_is_text() -> None:
    assert TEMPLATE.is_file()
    text = TEMPLATE.read_text(encoding="utf-8")
    assert text.startswith("---\n") and text.endswith("\n") and "\r" not in text and "\t" not in text


# ---------- TF17-2 ----------


def test_tf17_2_the_output_is_the_verdict_the_four_wrote_lines_the_prompt_and_one_next(tmp_path: Path) -> None:
    repo = work(tmp_path)
    r = agent(repo)
    assert r.code == 0 and r.err == "", r.text
    out = r.out.splitlines()
    assert re.match(r"^ok  wrote .*\(4 files\)$", out[0]), r.out
    wrote = [line[len("  wrote  "):] for line in out if line.startswith("  wrote  ")]
    assert sorted((repo / w).resolve() for w in wrote) == sorted((repo / f).resolve() for f in FOUR), wrote
    assert f"  prompt  {PROMPT}" in out, r.out
    nexts = [line for line in out if line.startswith("  next: ")]
    assert len(nexts) == 1, r.out
    # the one next: line that is not a command: it tells the person what to do with the prompt
    assert not nexts[0][len("  next: "):].startswith(COMMAND), nexts[0]
    assert "prompt" in nexts[0] and "review" in nexts[0], nexts[0]
    assert len(out) == 1 + 4 + 2, r.out


def test_tf17_2_with_repo_the_wrote_lines_name_the_files_as_given(tmp_path: Path) -> None:
    work(tmp_path, "repo")
    cwd = work(tmp_path, "elsewhere")
    r = agent(cwd, "--repo", "../repo")
    assert r.code == 0, r.text
    wrote = [line[len("  wrote  "):] for line in r.out.splitlines() if line.startswith("  wrote  ")]
    assert sorted(wrote) == sorted(f"../repo/{f}" for f in FOUR), wrote


def test_tf17_2_json_is_the_init_document_with_wrote_and_prompt(tmp_path: Path) -> None:
    repo = work(tmp_path)
    r = agent(repo, "--json")
    assert r.code == 0 and r.err == "", r.text
    data = r.json()
    assert data["schema"] == INIT_SCHEMA and data["verdict"] == "ok", data
    assert list(data)[:3] == INIT_KEYS[:3] and list(data)[-1] == "next", list(data)
    assert sorted(data["wrote"]) == sorted(FOUR), data
    assert data["prompt"] == PROMPT
    assert data["next"] and not str(data["next"]).startswith(COMMAND), data["next"]


# ---------- TF17-3 ----------

TF17_3_CASES = [
    *(f"refused: {f} exists" for f in FOUR),
    "refused: two exist",
    "refused: a link stands where a file goes",
    "--force replaces the four only",
    "--print in an empty folder",
    "--print where the four exist",
]


@pytest.mark.parametrize("case", TF17_3_CASES)
def test_tf17_3_an_existing_file_is_refused_force_replaces_only_the_four_and_print_writes_nothing(case: str, tmp_path: Path) -> None:
    skill = fresh_skill(tmp_path)
    repo = sample_repo(tmp_path, user_files=True)
    home = Path(os.environ["HOME"])
    if case.startswith("refused"):
        if case == "refused: two exist":
            existing: tuple[str, ...] = (FOUR[0], FOUR[3])
        elif case == "refused: a link stands where a file goes":
            existing = (FOUR[1],)
        else:
            existing = (case[len("refused: "):-len(" exists")],)
        for f in existing:
            (repo / f).parent.mkdir(parents=True, exist_ok=True)
            if "link" in case:
                (repo / "elsewhere.txt").write_text("the person's own text\n", encoding="utf-8")
                os.symlink(repo / "elsewhere.txt", repo / f)
            else:
                (repo / f).write_text("the person's own text\n", encoding="utf-8")
        before = snapshot(repo, home)
        r = agent(repo)
        line, nexts = refusal(r)
        for f in existing:
            assert f in line, (f, line)
        for f in FOUR:
            if f not in existing:
                assert f not in line, (f, line)
        assert snapshot(repo, home) == before
        assert any(sorted(shell_words(n)) == sorted([COMMAND, "init", "--agent", "--force"]) for n in nexts), nexts
        return
    if case == "--force replaces the four only":
        for f in FOUR:
            (repo / f).parent.mkdir(parents=True, exist_ok=True)
            (repo / f).write_text("an older setup\n", encoding="utf-8")
        own = repo / FOLDERS[0] / "my-notes.md"
        own.write_text("the person's own note beside the skill\n", encoding="utf-8")
        before = snapshot(repo, home)
        r = agent(repo, "--force")
        assert r.code == 0, r.text
        after = snapshot(repo, home)
        changed = sorted(k for k in before if after.get(k) != before[k])
        assert changed == sorted(f"repo/{f}" for f in FOUR), changed
        assert set(after) == set(before)
        for f in FOUR:
            assert (repo / f).read_text(encoding="utf-8") == (skill if f.endswith("SKILL.md") else PROMPT + "\n")
        return
    if case == "--print where the four exist":
        for f in FOUR:
            (repo / f).parent.mkdir(parents=True, exist_ok=True)
            (repo / f).write_text("an older setup\n", encoding="utf-8")
    else:
        repo = work(tmp_path, "empty")
    before = snapshot(repo, home)
    r = agent(repo, "--print")
    assert r.code == 0 and r.err == "", r.text
    assert r.out == skill
    assert r.out.splitlines()[0] == "---"
    assert snapshot(repo, home) == before


def test_tf17_3_the_refusal_with_repo_names_the_files_under_it_and_keeps_repo_in_the_next(tmp_path: Path) -> None:
    work(tmp_path, "repo")
    cwd = work(tmp_path, "elsewhere")
    assert agent(cwd, "--repo", "../repo").code == 0
    r = agent(cwd, "--repo", "../repo")
    line, nexts = refusal(r)
    assert all(f"../repo/{f}" in line for f in FOUR), line
    assert any(sorted(shell_words(n)) == sorted([COMMAND, "init", "--agent", "--repo", "../repo", "--force"]) for n in nexts), nexts


# ---------- TF17-4 ----------

WRONG = [
    ["--agent", "--yes"],
    ["--agent", "--store", "proofload-runs"],
    ["--agent", "--event", "unsolved"],
    ["--agent", "--add-store", "x"],
    ["--agent", "--import"],
    ["--agent", "--no-import"],
    ["--agent", "--names", "from=date"],
    ["--agent", "--max-mde", "0.2"],
    ["--agent", "--config", "team.toml"],
    ["--repo", "."],
    ["--print"],
    ["--agent", "--print", "--json"],
]


@pytest.mark.parametrize("argv", WRONG, ids=[" ".join(w) for w in WRONG])
def test_tf17_4_agent_with_a_setup_flag_and_repo_or_print_without_agent_are_wrong_command_lines(tmp_path: Path, argv: list[str]) -> None:
    repo = work(tmp_path)
    tau2_copy(repo, "proofload-runs")
    home = Path(os.environ["HOME"])
    before = snapshot(repo, home)
    r = trace_in(repo, ["init", *argv])
    usage(r)
    assert snapshot(repo, home) == before


def test_tf17_4_a_repo_that_is_not_a_folder_is_refused_naming_it(tmp_path: Path) -> None:
    cwd = work(tmp_path)
    (cwd / "a-file").write_text("x\n", encoding="utf-8")
    home = Path(os.environ["HOME"])
    for repo in ("missing", "a-file"):
        before = snapshot(cwd, home)
        line, _ = refusal(agent(cwd, "--repo", repo))
        assert repo in line, line
        assert snapshot(cwd, home) == before


def test_tf17_4_init_help_names_agent_repo_and_print() -> None:
    r = trace_in(Path.cwd(), ["init", "--help"])
    assert r.code == 0 and r.out.startswith("usage"), r.text
    entries = dict(help_entries(r.out))
    flags = {flag: words for invocation, words in entries.items() for flag in re.findall(r"--[a-z][a-z-]*", invocation)}
    assert {"--agent", "--repo", "--print"} <= set(flags), sorted(flags)
    assert "default" in flags["--repo"], flags["--repo"]
    assert re.search(r"init --agent", r.out), r.out


def test_tf17_4_init_agent_reads_no_key_and_never_asks(tmp_path: Path) -> None:
    """stdin closed: nothing is asked; a .env beside it is not read (its bytes reach no output)."""
    repo = work(tmp_path)
    users_own_files(repo)
    r = tty(["init", "--agent"], [], cwd=repo)
    assert r.code == 0 and r.err == "", r.text
    assert "sk-not-a-real-key" not in r.text
    for f in FOUR:
        assert "sk-not-a-real-key" not in (repo / f).read_text(encoding="utf-8")
