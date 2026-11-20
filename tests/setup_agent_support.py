"""Shared helpers for the tests of the setup agent (TF17-1 to TF17-47): ``init --agent``, the
skill it writes, ``[[import]]`` in ``trace.toml``, ``doctor --setup`` and ``init``'s hand-over.

Not a test module and not collected. Every command runs in-process through ``setup_support``'s
runners (a scratch ``HOME`` for every test, a folder of the test's own to run in) or on a
terminal of its own where a question has to be answered. No test here calls a model, a coding
agent or any paid service, and none opens a connection.

The skill is read as the shared setup-file page, format 1, reads it (``FORMAT``; see also
``docs/setup-with-your-agent.md``): the frontmatter is parsed with a reader of the one shape
the Agent Skills format allows there (string keys, string values, one ``metadata`` map of
strings), the body by its headings and fenced blocks, and the shared parts against the fixture
that carries the page's text with its date.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poisson_prove.store import Store

from look_support import FIXTURES, Ran, chdir, trace
from names_support import shell_words
from setup_support import here

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
SETUP_AGENT = FIXTURES / "setup-agent"
SAMPLE = SETUP_AGENT / "sample-repo"
EXPECTED = SETUP_AGENT / "expected"
FORMAT = SETUP_AGENT / "setup-file-format-1.txt"
TEMPLATE = REPO / "src" / "poisson_trace" / "skills" / "poisson-trace-setup" / "SKILL.md"
DOCS_PAGE = REPO / "docs" / "setup-with-your-agent.md"
CS = FIXTURES / "cs"
RAGAS = FIXTURES / "ingest" / "ragas"
JUNIT = FIXTURES / "ingest" / "junit"
CS_RECORD, CS_REPLAY = "20260925T234602Z-3ea0", "20260925T235434Z-af48"
CS_FAILURES = ("forbidden_action", "unresolved", "max_turns", "app_error")

COMMAND = "poisson-trace"
SKILL = "poisson-trace-setup"
FOLDERS = (f".agents/skills/{SKILL}", f".claude/skills/{SKILL}")
FOUR = tuple(f"{folder}/{name}" for folder in FOLDERS for name in ("SKILL.md", "prompt.txt"))
PROMPT = (
    "Use the poisson-trace-setup skill in this repository: set Poisson Trace up for me to "
    "review, then stop."
)
DESCRIPTION = (
    "Set up Poisson Trace in this repository so the person can check whether a change made "
    "their agent fail less, from results they already have. Use when asked to set up Trace or "
    "poisson-trace."
)
WRITES = ["trace.toml"]
CHECK = "poisson-trace doctor --setup"
NEXT_COMMAND = "poisson-trace init"
DOCS_URL = "https://pypi.org/project/poisson-trace/"
#: What Trace fills into the shared text.
NAMES = {
    "<Product full name>": "Poisson Trace",
    "<next command>": NEXT_COMMAND,
    "<docs-url>": DOCS_URL,
    "<command>": COMMAND,
    "<Product>": "Trace",
    "<check>": CHECK,
    "<tool>": "trace",
}
METADATA_KEYS = (
    "poisson-setup-format", "poisson-tool", "poisson-tool-version", "poisson-writes", "poisson-check",
)
HEADINGS = [
    "# Set up Trace in this repository",
    "## What you are doing",
    "## Rules",
    "## Files you write",
    "## Steps",
    "## The check",
    "## Hand over",
]
OPTIONAL_LAST_HEADING = "## Words Trace uses"
OWN_RULES = "### Trace's own rules"
#: The seven steps of the skill, by title, in order.
STEP_TITLES = (
    "The results already on disk",
    "The tools that wrote them",
    "The outcomes",
    "The old and the new version",
    "Write trace.toml",
    "Run the check",
    "Stop and hand over",
)
#: The tables the setup file lets the agent write, and the two it may not name.
AGENT_TABLES = ("[store]", "[events]", "[[import]]", "[names]")
NOT_FOR_THE_AGENT = ("[signals]", "[[taxonomy.rules]]", "[taxonomy")

#: Where the skill goes and the agents verified to read each (the shared page, and each
#: agent's own documentation).
LOCATIONS: dict[str, tuple[str, ...]] = {
    ".agents/skills/": ("Codex", "Cursor"),
    ".claude/skills/": ("Claude Code", "Cursor"),
}

SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
IMPORT_LINE = re.compile(r"^  import\s+(\S+): (\S+), ([\d,]+) rows?, (.*?)not imported yet$")
SETUP_READY = "ok  trace.toml is ready for the person to review"
SETUP_SCHEMA = "poisson-trace.doctor/1"
INIT_SCHEMA = "poisson-trace.init/1"
INIT_KEYS = [
    "schema", "verdict", "sentence", "config_path", "stores", "events", "named", "prove",
    "equivalent_command", "next",
]
#: The pullers an address names by its prefix; all but ``lemma`` are in this install.
PULLERS = ("langsmith", "braintrust", "weave", "lemma")
#: Readers in this install that a refusal of an unknown tool must name; the install has more
#: (promptfoo, Inspect, OpenAI Evals, LangSmith, Braintrust, Weave).
READERS_HERE = ("deepeval", "ragas", "table", "junit")


# ---------- running ----------


def agent(folder: Path, *argv: Any) -> Ran:
    """``poisson-trace init --agent ARGV`` in-process, run in ``folder``."""
    return here(folder, ["init", "--agent", *argv])


def setup_check(folder: Path, *argv: Any) -> Ran:
    """``poisson-trace doctor --setup ARGV`` in-process, run in ``folder``."""
    return here(folder, ["doctor", "--setup", *argv])


def setup_doc(folder: Path, *argv: Any) -> tuple[int, dict[str, Any]]:
    result = setup_check(folder, *argv, "--json")
    assert result.code in (0, 1), result.text
    data: dict[str, Any] = result.json()
    return result.code, data


def trace_in(folder: Path, argv: Sequence[Any]) -> Ran:
    with chdir(folder):
        return trace(list(argv))


def version() -> str:
    """The version ``--version`` prints for Trace."""
    r = trace(["--version"])
    assert r.code == 0, r.text
    words = r.out.split()
    assert words[0] == COMMAND, r.out
    return words[1]


# ---------- files ----------


def snapshot(*roots: Path) -> dict[str, str]:
    """Every file and folder under the roots: a file by its sha256, a folder by ``dir``."""
    found: dict[str, str] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            key = f"{root.name}/{path.relative_to(root)}"
            found[key] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "dir"
    return found


def added(before: dict[str, str], after: dict[str, str], root: Path) -> list[str]:
    """Files under ``root`` that are new; asserts that nothing that was there changed or went,
    and that every new folder holds a new file."""
    changed = {k for k in before if after.get(k) != before[k]}
    assert not changed, sorted(changed)
    new = {k for k in after if k not in before}
    assert all(k.startswith(f"{root.name}/") for k in new), sorted(new)
    files = {k for k in new if after[k] != "dir"}
    lonely = [k for k in new if after[k] == "dir" and not any(f.startswith(k + "/") for f in files)]
    assert not lonely, lonely
    return sorted(k[len(root.name) + 1:] for k in files)


def users_own_files(repo: Path) -> None:
    """Files the person owns that a setup must never write to."""
    for name, text in (
        ("AGENTS.md", "# Notes for coding agents\n\nRun the tests with pytest.\n"),
        ("CLAUDE.md", "Follow AGENTS.md.\n"),
        (".cursor/rules/style.mdc", "---\ndescription: house style\n---\nShort functions.\n"),
        (".claude/settings.json", "{}\n"),
        (".agents/skills/release-log/SKILL.md", "---\nname: release-log\ndescription: Write release notes.\n---\n# Release notes\n"),
        (".env", "OPENAI_API_KEY=sk-not-a-real-key-0000\n"),
    ):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def sample_repo(base: Path, *, name: str = "repo", with_expected: bool = False, user_files: bool = False) -> Path:
    """The sample repository: its committed files, the ``cs`` store copied to ``store/``, the
    Ragas pair to ``evals/results/`` and the JUnit pair to ``reports/``."""
    repo = base / name
    shutil.copytree(SAMPLE, repo, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(CS, repo / "store")
    (repo / "evals" / "results").mkdir()
    for name_ in ("rag-base.jsonl", "rag-raft.jsonl"):
        shutil.copy(RAGAS / name_, repo / "evals" / "results" / name_)
    (repo / "reports").mkdir()
    shutil.copy(JUNIT / "humaneval-a.xml", repo / "reports" / "junit-old.xml")
    shutil.copy(JUNIT / "humaneval-b.xml", repo / "reports" / "junit-new.xml")
    if with_expected:
        shutil.copy(EXPECTED / "trace.toml", repo / "trace.toml")
    if user_files:
        users_own_files(repo)
    return repo


def expected_toml() -> str:
    return (EXPECTED / "trace.toml").read_text(encoding="utf-8")


def fresh_skill(tmp_path: Path) -> str:
    """The skill as ``init --agent`` writes it into an empty folder."""
    folder = tmp_path / "fresh"
    folder.mkdir()
    r = agent(folder)
    assert r.code == 0, r.text
    return (folder / FOUR[0]).read_text(encoding="utf-8")


def runs_in(store: Path | str) -> list[str]:
    try:
        return sorted(Store(store).runs())
    except OSError:
        return []


def rows_of(store: Path | str, run: str) -> list[dict[str, Any]]:
    frame = Store(store).read(run, meta=True, trace="none")
    return [dict(zip(frame.columns, row, strict=True)) for row in frame.itertuples(index=False)]


# ---------- the skill's text ----------


def shared_text() -> dict[str, str]:
    """The shared page's byte-fixed text (format 1), parts by name, with Trace's names filled."""
    raw = FORMAT.read_text(encoding="utf-8")
    parts = re.split(r"^==> ([a-z-]+) <==\n", raw, flags=re.M)
    assert "as the shared page writes it (Prove's copy is the same text)" in " ".join(parts[0].split()), parts[0]
    texts = dict(zip(parts[1::2], parts[2::2], strict=True))
    assert set(texts) == {"rules", "check", "prompt", "hand-over"}, sorted(texts)
    filled = {}
    for name, text in texts.items():
        for placeholder, value in NAMES.items():
            text = text.replace(placeholder, value)
        assert not re.search(r"<[A-Za-z][^>]*>", text), (name, text)
        filled[name] = text.rstrip("\n")
    return filled


def split_frontmatter(text: str) -> tuple[str, str]:
    assert text.startswith("---\n"), text[:80]
    end = text.index("\n---\n", 4)
    return text[4:end + 1], text[end + len("\n---\n"):]


_SCALAR = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):(?: (.*))?$")


def _value(raw: str) -> str:
    """A YAML scalar as the frontmatter writes it: a double-quoted string, or a plain one."""
    raw = raw.strip()
    if raw.startswith('"'):
        assert raw.endswith('"') and len(raw) >= 2, raw
        return json.loads(raw)
    assert raw and not raw.startswith(("'", "[", "{", "|", ">", "&", "*", "!")), raw
    return raw


def parse_frontmatter(front: str) -> dict[str, Any]:
    """The frontmatter as the Agent Skills format allows it: string keys, string values, and
    one level of nesting under a key written with no value (``metadata:``). Anything else is
    refused here, so a frontmatter YAML would read as something richer fails the test."""
    out: dict[str, Any] = {}
    nested: dict[str, str] | None = None
    for line in front.splitlines():
        assert "\t" not in line, line
        if not line.strip():
            continue
        if line.startswith("  "):
            assert nested is not None, line
            m = _SCALAR.match(line[2:])
            assert m and m.group(2) is not None, line
            nested[m.group(1)] = _value(m.group(2))
            continue
        m = _SCALAR.match(line)
        assert m, line
        key, raw = m.group(1), m.group(2)
        assert key not in out, key
        if raw is None:
            nested = {}
            out[key] = nested
        else:
            nested = None
            out[key] = _value(raw)
    return out


@dataclass(frozen=True)
class Fence:
    lang: str
    lines: tuple[str, ...]
    #: the ``##`` heading the block sits under
    section: str


def fences(body: str) -> list[Fence]:
    found: list[Fence] = []
    section, opened, lang, indent, held = "", False, "", "", []
    for line in body.splitlines():
        if not opened:
            m = re.match(r"^(\s*)```(.*)$", line)
            if m:
                opened, indent, lang, held = True, m.group(1), m.group(2).strip(), []
            elif line.startswith("## ") or line.startswith("# "):
                section = line
            continue
        if line.strip() == "```":
            found.append(Fence(lang, tuple(held), section))
            opened = False
        else:
            held.append(line[len(indent):] if line.startswith(indent) else line)
    assert not opened, "a fenced block is never closed"
    return found


def headings(body: str) -> list[str]:
    out, opened = [], False
    for line in body.splitlines():
        if re.match(r"^\s*```", line):
            opened = not opened
        elif not opened and re.match(r"^#{1,6} ", line):
            out.append(line)
    return out


def section(body: str, heading: str) -> str:
    """The text under a heading, up to the next heading of the same or a higher level."""
    lines = body.splitlines()
    assert heading in lines, (heading, headings(body))
    at = lines.index(heading)
    level = len(heading) - len(heading.lstrip("#"))
    opened, end = False, len(lines)
    for i in range(at + 1, len(lines)):
        if re.match(r"^\s*```", lines[i]):
            opened = not opened
        elif not opened and re.match(rf"^#{{1,{level}}} ", lines[i]):
            end = i
            break
    return "\n".join(lines[at:end])


@dataclass(frozen=True)
class Step:
    number: int
    title: str
    text: str


def steps_of(body: str) -> list[Step]:
    """The numbered items of "Steps"; each opens with its title in bold."""
    text = section(body, "## Steps")
    items = re.split(r"^(\d+)\. ", text, flags=re.M)
    steps = []
    for number, item in zip(items[1::2], items[2::2], strict=True):
        m = re.match(r"\*\*(.+?)\.?\*\*", item)
        assert m, f"step {number} does not open with its title in bold: {item[:80]!r}"
        steps.append(Step(int(number), m.group(1).rstrip("."), item))
    return steps


def commands(body: str, lang: str) -> list[tuple[str, str]]:
    """(section, command) for every non-empty line of every block tagged ``lang``."""
    return [
        (f.section, line.strip())
        for f in fences(body) if f.lang == lang
        for line in f.lines if line.strip()
    ]


# ---------- the config ----------


def import_entry(file: str, tool: str | None, name: str, **options: Any) -> str:
    """One ``[[import]]`` table as ``docs/config.md`` writes it: the file, the tool, the name,
    then the reader's options by their flags' names."""
    lines = ["[[import]]", f"file = {json.dumps(file)}"]
    if tool is not None:
        lines.append(f"tool = {json.dumps(tool)}")
    lines.append(f"name = {json.dumps(name)}")
    for key, value in options.items():
        lines.append(f"{key} = {toml_value(value)}")
    return "\n".join(lines) + "\n"


def toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    raise TypeError(value)


def ragas_entry(file: str, name: str, **changes: Any) -> str:
    options: dict[str, Any] = {"metric": "faithfulness", "cut": 0.5, "below": True, "case_column": "case"}
    options.update(changes)
    return import_entry(file, "ragas", name, **options)


def junit_entry(file: str, name: str, **changes: Any) -> str:
    options: dict[str, Any] = {"case": "name"}
    options.update(changes)
    return import_entry(file, "junit", name, **options)


def config_text(*blocks: str, store: str | None = None, events: Sequence[str] | None = CS_FAILURES, imported: str | None = None) -> str:
    """A version 1 config: the store (none when ``store`` is None), the failures, then the
    blocks given (``[[import]]`` tables, or anything else)."""
    parts = ["version = 1\n"]
    if store is not None:
        parts.append(f"[store]\npath = {json.dumps(store)}\n")
    if imported is not None:
        parts.append(f"[store.imported]\npath = {json.dumps(imported)}\n")
    if events:
        parts.append("[events]\nfailed = [" + ", ".join(json.dumps(e) for e in events) + "]\n")
    parts.extend(blocks)
    return "\n".join(parts)


def write_toml(folder: Path, text: str, name: str = "trace.toml") -> Path:
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


def read_toml(folder: Path, name: str = "trace.toml") -> dict[str, Any]:
    doc: dict[str, Any] = tomllib.loads((folder / name).read_text(encoding="utf-8"))
    return doc


def ragas_pair(folder: Path, into: str = "evals") -> tuple[str, str]:
    """The committed Ragas pair copied under ``folder/into``; the two paths relative to ``folder``."""
    (folder / into).mkdir(parents=True, exist_ok=True)
    for name in ("rag-base.jsonl", "rag-raft.jsonl"):
        shutil.copy(RAGAS / name, folder / into / name)
    return f"{into}/rag-base.jsonl", f"{into}/rag-raft.jsonl"


def junit_pair(folder: Path, into: str = "reports") -> tuple[str, str]:
    (folder / into).mkdir(parents=True, exist_ok=True)
    shutil.copy(JUNIT / "humaneval-a.xml", folder / into / "junit-old.xml")
    shutil.copy(JUNIT / "humaneval-b.xml", folder / into / "junit-new.xml")
    return f"{into}/junit-old.xml", f"{into}/junit-new.xml"


def cs_store(folder: Path, name: str = "store") -> str:
    shutil.copytree(CS, folder / name)
    return name


# ---------- reading what the commands print ----------


def refusal(result: Ran, code: int = 1) -> tuple[str, list[str]]:
    """The shared check's and the look's shape of a refusal: the exit code, stdout empty, one
    ``error:`` line on stderr with only ``  next:`` lines under it (``init``'s progress lines
    may come before it). The error line and the next lines."""
    assert result.code == code and result.out == "", result.text
    lines = result.lines()
    errors = [i for i, line in enumerate(lines) if line.startswith("error: ")]
    assert len(errors) == 1, result.err
    rest = lines[errors[0] + 1:]
    assert all(line.startswith("  next: ") for line in rest), result.err
    return lines[errors[0]], [line[len("  next: "):] for line in rest]


def usage(result: Ran) -> str:
    """A wrong command line: exit 2, stdout empty, the one ``error:`` line."""
    assert result.code == 2 and result.out == "", result.text
    lines = [line for line in result.lines() if line.startswith("error: ")]
    assert len(lines) == 1, result.err
    return lines[0]


def next_lines(result: Ran) -> list[str]:
    return [line[len("next: "):] for line in result.out.splitlines() if line.startswith("next: ")]


def detail(out: str, label: str) -> list[str]:
    """The ``  <label>  …`` detail lines of a report's stdout."""
    return [m.group(1) for m in (re.match(rf"^  {re.escape(label)} {{2,}}(\S.*)$", line) for line in out.splitlines()) if m]


def import_lines(out: str) -> list[dict[str, Any]]:
    """The ``  import  FILE: TOOL, N rows, …, not imported yet`` lines of ``doctor --setup``."""
    found = []
    for line in out.splitlines():
        m = IMPORT_LINE.match(line)
        if m:
            found.append({"file": m.group(1), "tool": m.group(2), "rows": int(m.group(3).replace(",", "")), "said": m.group(4)})
    return found


def words_of(command: str) -> list[str]:
    return shell_words(command)
