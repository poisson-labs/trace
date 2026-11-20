"""Shared helpers for TF5's tests: the recipes, the README, the docs set, the docs checker and
the CI workflow. Not collected.

What the docs set holds, in one place (each test file's opening says which invariant it holds):

the pages
    ``README.md``; ``CONTRIBUTING.md``; ``CHANGELOG.md``; under ``docs/``: ``commands.md``,
    ``config.md``, ``how-it-decides.md``, ``handover.md``, ``app.md``, ``python.md``,
    ``setup-with-your-agent.md``; the ten pages of ``docs/integrations/``; and the sixteen
    recipes of ``docs/recipes/`` (``RECIPES``). The look standard (``docs/cli-look.md``) is not
    Trace's to change.
``tools/docs_check.py``
    The docs checker the clean-install job runs. In the repository, not in the wheel.
``.github/workflows/ci.yml``
    The suite's lanes and the clean-install job.
the product
    One word of what a command prints moves: the store folder the help examples name,
    ``proofload-runs`` to ``prove-runs``. Nothing else (``test_docs_unchanged.py``).

The marks (the grammar every page is held to)
---------------------------------------------
A mark is an HTML comment alone on the line just above a fenced block.

``<!-- command -->``
    The block is run with bash, in a folder laid out as a clone (what the page names of the
    committed fixtures under ``tests/fixtures/`` and of the committed examples under
    ``examples/``, and an empty ``docs/figures/``), with a home folder of its own, no key in the environment, and stdin, stdout and stderr not
    a terminal; the commands of the environment under test (``poisson-prove``,
    ``poisson-tasks``, ``pytest``) come first on PATH after Trace's own. Blocks of one page run
    in page order in one folder.
``<!-- command pull -->``
    The same, with LangSmith, Braintrust and Weave answered from the committed captures (each
    request with the response that service gave to it), a planted key for each, and no network.
``<!-- command tty answers="A|B" -->``
    The same as ``command``, with stdin a terminal and each answer typed as one line; stdout
    and stderr stay pipes, so what prints is the plain text a page can show.
``<!-- output exit=N -->``
    The whole of what the command above it printed (stdout, then stderr), with its exit code.
``<!-- excerpt exit=N -->``
    A run of whole lines of it, with its exit code.
``<!-- output exit=N varies -->`` and ``<!-- excerpt exit=N varies -->``
    The same, where a line may hold ``…`` in the place of a path, a time, an id or a version
    (``VARIES``), and of nothing else: the rule named *varies*.
``<!-- skip reason="WHY" -->``
    The block is shown and not run; the checker lists it with its reason.

Every fenced block is marked, with one exception: a block whose opening fence names what it
holds (``DATA_LANGUAGES``: a config, a JSON document, a Python example, plain text) and whose
first line is not a shell command needs no mark. A block that runs ``poisson-trace`` may be
skipped only if it holds a word in capitals that is the reader's to fill in or ``…``, or is
the bare command, which opens the terminal app.

The marks are read and a page is run by ``tools/docs_check.py`` alone, loaded here from the
repository (``docs_check``): the names below that read a mark, lay a page's folder out, run a
block or hold a block against what was printed are that file's own, under the names the tests
use.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
FIXTURES = TESTS / "fixtures"
#: The examples a recipe runs on (the three-tools recipe's, TF20), copied beside the fixtures.
EXAMPLES = REPO / "examples"
DOCS = REPO / "docs"
README = REPO / "README.md"
CHANGELOG = REPO / "CHANGELOG.md"
CONTRIBUTING = REPO / "CONTRIBUTING.md"
CHECKER = REPO / "tools" / "docs_check.py"
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"
GITHUB = "https://github.com/poisson-labs/trace/blob/main/"

#: The ten tools beside Prove's own stores, in the order every listing gives them: the command
#: word, the name a sentence gives it, and how a sentence may name it (a pattern).
TOOLS: tuple[tuple[str, str, str], ...] = (
    ("deepeval", "DeepEval", r"\bdeepeval\b"),
    ("ragas", "Ragas", r"\bragas\b"),
    ("table", "tables", r"\btables?\b"),
    ("junit", "JUnit", r"\bjunit\b"),
    ("promptfoo", "promptfoo", r"\bpromptfoo\b"),
    ("inspect", "Inspect", r"\bInspect\b|`inspect`|\binspect\.md\b|(?<![\w-])inspect(?=,)"),
    ("openai-evals", "OpenAI Evals", r"\bopenai[- ]evals\b"),
    ("langsmith", "LangSmith", r"\blangsmith\b"),
    ("braintrust", "Braintrust", r"\bbraintrust\b"),
    ("weave", "Weave", r"\bweave\b"),
)
WORDS = tuple(word for word, _, _ in TOOLS)
API_TOOLS = ("langsmith", "braintrust", "weave")
#: A tool's integration page; the table reader's is ``table.md``.
INTEGRATIONS = tuple(DOCS / "integrations" / f"{word}.md" for word in WORDS)
#: The address a pull is asked by, and a committed address the captures answer, per service.
ADDRESS = {
    "langsmith": ("langsmith:", "langsmith:trace-fixture-baseline-bbb64b8e"),
    "braintrust": ("braintrust:", "braintrust:trace-fixture/slice-baseline"),
    "weave": ("weave:", "weave:example-entity/trace-fixture/trace-fixture-slice-baseline"),
}

#: The recipes of 0.1.0 (less the two that wait with the pull-request check and the upload;
#: with the three-tools recipe, TF20's): the page and the source whose first result it shows
#: (None: the recipe is about something else).
RECIPES: dict[str, str | None] = {
    "first-look.md": "prove",
    "check-a-fix.md": "prove",
    "from-deepeval.md": "deepeval",
    "from-ragas.md": "ragas",
    "from-a-table.md": "table",
    "from-junit.md": "junit",
    "from-promptfoo.md": "promptfoo",
    "from-inspect.md": "inspect",
    "from-openai-evals.md": "openai-evals",
    "from-langsmith.md": "langsmith",
    "from-braintrust.md": "braintrust",
    "from-weave.md": "weave",
    "a-page-to-send.md": None,
    "into-the-product.md": None,
    "what-it-cannot-say.md": None,
    "with-tasks-and-prove.md": None,
}
#: The recipes that wait: the page must not exist until its feature does.
WAITING = ("on-a-pull-request.md", "sending-results.md")
#: The docs set of 0.1.0 beside the recipes and the integration pages.
DOCS_SET = ("commands.md", "config.md", "how-it-decides.md", "handover.md", "app.md", "python.md", "setup-with-your-agent.md")
STANDARDS = ("cli-look.md",)
#: The verbs, in the order the top help lists them.
VERBS = ("init", "runs", "name", "where", "compare", "fix-check", "changes", "import", "doctor", "handover", "ui", "report")


def recipe(name: str) -> Path:
    return DOCS / "recipes" / name


def run_pages() -> list[Path]:
    """Every page whose blocks are held: the README, the contributing page, and every page under
    ``docs/`` but the look standard."""
    pages = [README, CONTRIBUTING]
    pages += sorted(p for p in DOCS.rglob("*.md") if p.name not in STANDARDS)
    return pages


def expected_pages() -> list[Path]:
    """The pages 0.1.0 has, whether or not they are written yet."""
    return [README, CONTRIBUTING, *[DOCS / name for name in DOCS_SET], *INTEGRATIONS, *[recipe(name) for name in RECIPES]]


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def read(path: Path) -> str:
    assert path.is_file(), f"{rel(path)} is not written"
    return path.read_text(encoding="utf-8")


# ---------- the marks: the docs checker's own ----------


def _checker() -> Any:
    """``tools/docs_check.py`` as a module, loaded from the repository by its path, once (it is
    not on the import path: it is not in the wheel)."""
    import importlib.util

    name = "docs_check"
    if name not in sys.modules:
        assert CHECKER.is_file(), "tools/docs_check.py is not written"
        spec = importlib.util.spec_from_file_location(name, CHECKER)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[name]
            raise
    return sys.modules[name]


#: The docs checker: the one reader of the marks and the one runner of a page.
docs_check = _checker()
MARK = docs_check.MARK
#: A comment that means to be a mark, whether or not it is well formed.
MARKISH = docs_check.MARKISH
DATA_LANGUAGES = docs_check.DATA_LANGUAGES
SHELLISH = docs_check.SHELLISH
PLACEHOLDER = docs_check.PLACEHOLDER
#: What ``…`` may stand for in a block marked ``varies``: a path or a file address, a time or
#: a date, a span of time, an id in hexadecimal, a run's id, or a version written whole (three
#: numbers: a figure with one point in it is a result, never a version).
VARIES = docs_check.VARIES
#: One fenced block of a page, with its mark read: its ``kind`` (command, output, excerpt, skip,
#: data or unmarked), the ``line`` its body starts at, its ``body``, and what its mark says
#: (``code``, ``pull``, ``answers``, ``varies``, ``reason``).
Block = docs_check.Block


def parse(text: str) -> tuple[list[Block], list[tuple[int, str]]]:
    """Every fenced block of a page in order, each with its mark read, and the page's faults:
    (line, what is wrong) for a comment that means to be a mark and is not one, a mark with no
    block under it, and a fence never closed."""
    found: tuple[list[Block], list[tuple[int, str]]] = docs_check.parse(text)
    return found


def outside(text: str) -> list[tuple[int, str]]:
    """The lines of a page that are in no fenced block, each with its number."""
    out, inside = [], False
    for n, line in enumerate(text.split("\n"), 1):
        if line.startswith("```"):
            inside = not inside
        elif not inside:
            out.append((n, line))
    return out


def prose(text: str) -> str:
    return "\n".join(line for _, line in outside(text))


def passages(text: str) -> list[tuple[int, str]]:
    """The page's passages outside its fenced blocks: each run of lines with no blank line in
    it (a paragraph, a list, a table), with the number of its first line."""
    out: list[tuple[int, str]] = []
    start, held = 0, []
    for n, line in [*outside(text), (0, "")]:
        if line.strip() and not line.startswith("<!--"):
            if not held:
                start = n
            held.append(line)
        elif held:
            out.append((start, "\n".join(held)))
            held = []
    return out


def sections(text: str, level: int = 2) -> dict[str, str]:
    """The page's sections at one heading level, by title, fenced blocks left whole."""
    out: dict[str, str] = {}
    title: str | None = None
    held: list[str] = []
    inside = False
    marker = "#" * level + " "
    for line in text.split("\n"):
        if line.startswith("```"):
            inside = not inside
        if not inside and line.startswith(marker):
            if title is not None:
                out[title] = "\n".join(held)
            title, held = line[len(marker):].strip(), []
        elif not inside and level > 1 and re.match(rf"^#{{1,{level - 1}}} ", line):
            if title is not None:
                out[title] = "\n".join(held)
            title, held = None, []
        elif title is not None:
            held.append(line)
    if title is not None:
        out[title] = "\n".join(held)
    return out


def words(block: Block) -> list[list[str]]:
    """The commands of a command block, each as its words; a line ending in a backslash joins
    the next. A line that is not a simple command (a loop, a pipe) is kept as bash would split
    it, which is enough to see what it runs."""
    out: list[list[str]] = docs_check.commands(block)
    return out


def trace_commands(text: str, kinds: Sequence[str] = ("command",)) -> list[list[str]]:
    """Every ``poisson-trace`` command the page's blocks of those kinds hold, its words after
    the command's name."""
    out = []
    for block in parse(text)[0]:
        if block.kind in kinds:
            for command in words(block):
                for at, word in enumerate(command):
                    if word == "poisson-trace" and (at == 0 or command[at - 1] in ("&&", ";", "||")):
                        end = next((j for j in range(at + 1, len(command)) if command[j] in ("&&", ";", "||", "|", ">")), len(command))
                        out.append(command[at + 1:end])
    return out


# ---------- running a page ----------

#: Put on the import path of every Python a page's command starts: every connection to an
#: address that is not this machine's is refused, so a page's command cannot reach the network
#: (a pull is answered on this machine's loopback address).
_NO_NETWORK = (
    "import socket\n"
    "_connect = socket.socket.connect\n"
    "def _guarded(self, address):\n"
    "    host = address[0] if isinstance(address, tuple) else address\n"
    "    if isinstance(host, bytes):\n"
    "        host = host.decode('utf-8', 'replace')\n"
    "    if isinstance(host, str) and (host in ('localhost', '::1') or host.startswith('127.') or host.startswith('/')"
    " or host.startswith('\\x00')):\n"
    "        return _connect(self, address)\n"
    "    raise OSError('a page\\'s command reached for the network: ' + repr(address))\n"
    "socket.socket.connect = _guarded\n"
)
_CAPTURES: list[Any] = []


def _captures() -> Any:
    """The checker's stand-in for the three services (``docs_check.Captures``: their committed
    answers served on this machine's loopback address), started once for the process."""
    if not _CAPTURES:
        _CAPTURES.append(docs_check.Captures())
    return _CAPTURES[0]


def shims(folder: Path) -> Path:
    """A folder holding ``poisson-trace`` and ``poisson-trace-import`` as small scripts that run
    this interpreter on the package under test, whatever console scripts are installed, and the
    ``sitecustomize`` module that refuses the network (``_NO_NETWORK``)."""
    folder.mkdir(parents=True, exist_ok=True)
    bodies = {"poisson-trace": "from poisson_trace.cli import main", "poisson-trace-import": "from poisson_trace.ingest.cli import main"}
    for name, line in bodies.items():
        path = folder / name
        path.write_text(f"#!{sys.executable}\nimport sys\n{line}\nsys.exit(main(sys.argv[1:]))\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    (folder / "sitecustomize.py").write_text(_NO_NETWORK, encoding="utf-8")
    return folder


def page_root(tmp: Path, text: str = "") -> Path:
    """A folder laid out as a clone's root for the commands of the page whose text this is, by
    the checker's rule (``docs_check.lay_out``: what the page names of the committed fixtures
    and examples, copied, and an empty ``docs/figures/``), so nothing a page runs can touch the
    repository."""
    root = tmp / "clone"
    docs_check.lay_out(root, text)
    return root


def _first(bin_dir: Path) -> dict[str, str]:
    """What the tests add to the checker's environment for a block: the shims, then this
    interpreter's commands, first on ``PATH``; and the shims' folder first on the import path."""
    path = os.environ.get("PYTHONPATH")
    return {"PATH": f"{bin_dir}{os.pathsep}{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}",
            "PYTHONPATH": f"{bin_dir}{os.pathsep}{path}" if path else str(bin_dir)}


def page_env(home: Path, bin_dir: Path, *, pull: bool) -> dict[str, str]:
    """The checker's environment for a block (``docs_check.environment``), with the shims first."""
    env: dict[str, str] = docs_check.environment(home, _captures().addresses() if pull else None, _first(bin_dir))
    return env


def run_block(block: Block, root: Path, env: dict[str, str]) -> tuple[int, str]:
    """The block run as the checker runs it (``docs_check.run``)."""
    ran: tuple[int, str] = docs_check.run(block, root, env)
    return ran


#: One output or excerpt block of a page that was run, with what it was held against: its
#: ``block``, the ``command`` block's text above it, the ``code`` that gave, what it ``printed``,
#: and the command block itself (``ran``).
Checked = docs_check.Shown


def run_page(page: Path, tmp: Path) -> list[Checked]:
    """The page run by the checker (``docs_check.run_page``) under ``tmp``, which keeps what the
    commands left (``clone``, ``home``) and the shims (``bin``): each output and excerpt block
    paired with the command above it, its exit code and what it printed. An output or excerpt
    the checker held against no command fails here, with the checker's faults."""
    blocks = parse(read(page))[0]
    found, shown = docs_check.run_page(page, tmp, _captures(), _first(shims(tmp / "bin")))
    out: list[Checked] = list(shown)
    held = [c.block for c in out]
    for block in blocks:
        if block.kind in ("output", "excerpt"):
            assert block in held, f"{rel(page)}:{block.line}: this {block.kind} was held against no command: {sorted(found.faults)}"
    return out


def line_holds(shown: str, printed: str, varies: bool) -> bool:
    """One shown line against the line printed, by the checker's rule (``docs_check.line_holds``):
    equal, or, under ``varies``, equal once each ``…`` of the shown line is given a path, a time,
    an id or a version to stand for."""
    same: bool = docs_check.line_holds(shown, printed, varies)
    return same


def holds(checked: Checked) -> bool:
    """An output block is the whole of what the command printed; an excerpt a run of whole lines
    of it; both with the exit code the mark names, and under ``varies`` line by line by that
    rule: the checker's own (``docs_check.holds``)."""
    same: bool = docs_check.holds(checked.block, checked.code, checked.printed)
    return same


def why(page: Path, checked: Checked) -> str:
    return (f"{rel(page)}:{checked.block.line}: {checked.block.kind} exit={checked.block.code} does not hold; the command gave exit "
            f"{checked.code}\n--- command\n{checked.command}\n--- block\n{checked.block.body}\n--- printed\n{checked.printed}")


# ---------- the readers a passage names ----------


def named(text: str) -> list[str]:
    """The tools a passage names, in the order it first names them."""
    at = {}
    for word, _, pattern in TOOLS:
        flags = 0 if word == "inspect" else re.IGNORECASE
        found = re.search(pattern, text, flags)
        if found:
            at[word] = found.start()
    return sorted(at, key=lambda word: at[word])


def lists_readers(text: str) -> bool:
    """Whether a passage is a list of the readers: it names three or more of the tools (the
    table reader's common word aside) and they are not just the three services."""
    tools = [word for word in named(text) if word != "table"]
    return len(tools) >= 3 and set(tools) != set(API_TOOLS)


# ---------- the checker and the workflow ----------


def check(args: Sequence[str | Path], *, cwd: Path | None = None, env: Mapping[str, str] | None = None, timeout: float = 900) -> subprocess.CompletedProcess[str]:
    """``python tools/docs_check.py ARGS``, with the test's shims first on PATH unless ``env``
    is given."""
    assert CHECKER.is_file(), "tools/docs_check.py is not written"
    return subprocess.run([sys.executable, str(CHECKER), *[str(a) for a in args]], cwd=cwd or REPO, env=None if env is None else dict(env),
                          capture_output=True, text=True, timeout=timeout)


def workflow() -> str:
    assert WORKFLOW.is_file(), ".github/workflows/ci.yml is not written"
    return WORKFLOW.read_text(encoding="utf-8")


def jobs(text: str | None = None) -> dict[str, str]:
    """``ci.yml``'s jobs, each as the text of its block with comments taken out: read by its
    indentation, as the suite carries no YAML reader. A job is a key two spaces in, under
    ``jobs:``."""
    lines = (workflow() if text is None else text).split("\n")
    assert "jobs:" in lines, "ci.yml has no jobs"
    out: dict[str, list[str]] = {}
    name: str | None = None
    for line in lines[lines.index("jobs:") + 1:]:
        if line and not line.startswith((" ", "#")):
            break
        opened = re.match(r"^  ([A-Za-z0-9_-]+):\s*(?:#.*)?$", line)
        if opened:
            name = opened.group(1)
            out[name] = []
        elif name is not None and not line.lstrip().startswith("#"):
            out[name].append(line)
    return {job: "\n".join(body) for job, body in out.items()}


def triggers(text: str | None = None) -> str:
    """The workflow's ``on:`` block, as text."""
    lines = (workflow() if text is None else text).split("\n")
    start = next(i for i, line in enumerate(lines) if re.match(r"^on:", line))
    held = [lines[start]]
    for line in lines[start + 1:]:
        if line and not line.startswith((" ", "#")):
            break
        held.append(line)
    return "\n".join(held)
