"""Shared helpers for TF5's tests: the recipes, the README, the docs set, the docs checker and
the CI workflow (spec sections 7 and 8; the rulings sent to this pair: TF16 item 4, SB6, SG7,
RB3, SC1, RR6, N3, LS-46, B-6, BT-44, WV-50; the launch note of 2026-11-12). Not collected.

What Session B writes, in one place (each test file's opening says which invariant it holds):

the pages
    ``README.md``; ``CONTRIBUTING.md``; ``CHANGELOG.md``; under ``docs/``: ``commands.md``,
    ``config.md``, ``how-it-decides.md``, ``handover.md``, ``app.md``, ``python.md``,
    ``setup-with-your-agent.md``; the ten pages of ``docs/integrations/``; and the sixteen
    recipes of ``docs/recipes/`` (``RECIPES``). The two standards (``docs/cli-look.md``,
    ``docs/repo-hygiene.md``) are not Trace's to change.
``tools/docs_check.py``
    The docs checker the clean-install job runs. In the repository, not in the wheel.
``.github/workflows/ci.yml``
    The suite's lanes and the clean-install job.
the product
    One word of what a command prints moves: the store folder the help examples name,
    ``proofload-runs`` to ``prove-runs``. Nothing else (``test_tf5_unchanged.py``).

The marks (the grammar every page is held to)
---------------------------------------------
A mark is an HTML comment alone on the line just above a fenced block. The three the pages
already use keep their meaning; the rest are new here.

``<!-- command -->``
    The block is run with bash, in a folder laid out as a clone (the committed fixtures under
    ``tests/fixtures/``, the committed examples under ``examples/``, an empty ``docs/figures/``),
    with a home folder of its own, no key in the environment, and stdin, stdout and stderr not
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
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import stat
import subprocess
import sys
import termios
import threading
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
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

#: The recipes of 0.1.0 (spec section 7.1, less the two that wait with the pull-request check
#: and the upload; and section 17.6's three-tools recipe, TF20's): the page and the source whose
#: first result it shows (None: the recipe is about something else).
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
#: The docs set of 0.1.0 beside the recipes and the integration pages (section 7.2).
DOCS_SET = ("commands.md", "config.md", "how-it-decides.md", "handover.md", "app.md", "python.md", "setup-with-your-agent.md")
STANDARDS = ("cli-look.md", "repo-hygiene.md")
#: The verbs, in the order the top help lists them.
VERBS = ("init", "runs", "name", "where", "compare", "fix-check", "changes", "import", "doctor", "handover", "ui", "report")


def recipe(name: str) -> Path:
    return DOCS / "recipes" / name


def run_pages() -> list[Path]:
    """Every page whose blocks are held: the README, the contributing page, and every page under
    ``docs/`` but the two standards."""
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


# ---------- the marks ----------

FENCE = re.compile(r"^```(.*)$")
MARK = re.compile(
    r'^<!-- (?:(?P<command>command)(?: (?P<pull>pull)| tty answers="(?P<answers>[^"]*)")?'
    r'|(?P<shown>output|excerpt) exit=(?P<code>\d+)(?P<varies> varies)?'
    r'|skip reason="(?P<reason>[^"]+)") -->$'
)
#: A comment that means to be a mark, whether or not it is well formed.
MARKISH = re.compile(r"^<!--\s*(command|output|excerpt|skip|docs-check)\b")
DATA_LANGUAGES = ("toml", "json", "jsonl", "python", "text", "yaml", "markdown", "csv", "xml", "diff")
SHELLISH = re.compile(r"^\s*(?:\$ )?(?:poisson-trace(?:-import)?|pip3?|python3?(?:\.\d+)?|git|cd|mkdir|cp|tar|gunzip|export|shasum|sha256sum|source|uv|pytest|ruff|mypy|\.)(?:\s|$)")
PLACEHOLDER = re.compile(r"(?<![\w-])[A-Z][A-Z_]{2,}(?![\w])|…|\.\.\.")
#: What ``…`` may stand for in a block marked ``varies``: a path or a file address, a time or
#: a date, a span of time, an id in hexadecimal, a run's id, or a version written whole (three
#: numbers: a figure with one point in it is a result, never a version).
VARIES = re.compile(
    r"(?:file://)?(?:~|\.{0,2})?/[^\s]*"
    r"|\d{4}-\d\d-\d\d(?:[T ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[+-]\d\d:\d\d| UTC)?)?"
    r"|\d+(?:\.\d+)? ?(?:ms|s|min|h)"
    r"|[0-9a-f]{8,64}"
    r"|\d{8}T\d{6}Z-[0-9a-f]{4}"
    r"|\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?"
)


@dataclass(frozen=True)
class Block:
    kind: str  # command, output, excerpt, skip, data (a named block that needs no mark) or unmarked
    line: int  # the first line of the body, counting from 1
    body: str
    language: str = ""
    code: int | None = None
    pull: bool = False
    answers: tuple[str, ...] | None = None
    varies: bool = False
    reason: str = ""


def parse(text: str) -> tuple[list[Block], list[tuple[int, str]]]:
    """Every fenced block of a page in order, each with its mark read, and the page's faults:
    (line, what is wrong) for a comment that means to be a mark and is not one, a mark with no
    block under it, and a fence never closed."""
    lines = text.split("\n")
    found: list[Block] = []
    faults: list[tuple[int, str]] = []
    pending: tuple[int, re.Match[str]] | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        opened = FENCE.match(line)
        if opened:
            k = i + 1
            while k < len(lines) and not lines[k].startswith("```"):
                k += 1
            if k >= len(lines):
                faults.append((i + 1, "a fence that is never closed"))
                break
            body, language = "\n".join(lines[i + 1:k]), opened.group(1).strip()
            mark = pending[1] if pending is not None and pending[0] == i - 1 else None
            if mark is None:
                first = next((b for b in body.split("\n") if b.strip()), "")
                kind = "data" if language in DATA_LANGUAGES and not SHELLISH.match(first) else "unmarked"
                found.append(Block(kind, i + 2, body, language))
            elif mark.group("command"):
                answers = mark.group("answers")
                found.append(Block("command", i + 2, body, language, pull=bool(mark.group("pull")),
                                   answers=None if answers is None else tuple(answers.split("|")) if answers else ()))
            elif mark.group("shown"):
                found.append(Block(mark.group("shown"), i + 2, body, language, code=int(mark.group("code")), varies=bool(mark.group("varies"))))
            else:
                found.append(Block("skip", i + 2, body, language, reason=mark.group("reason")))
            pending = None
            i = k + 1
            continue
        if pending is not None and pending[0] == i - 1:
            faults.append((pending[0] + 1, "a mark with no block under it"))
            pending = None
        if MARKISH.match(line):
            m = MARK.match(line)
            if m:
                pending = (i, m)
            else:
                faults.append((i + 1, f"not a mark this page's checker reads: {line}"))
        i += 1
    return found, faults


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
    import shlex

    out = []
    for line in block.body.replace("\\\n", " ").split("\n"):
        if line.strip() and not line.lstrip().startswith("#"):
            try:
                out.append(shlex.split(line))
            except ValueError:
                out.append(line.split())
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

_PLANTED = {
    "LANGSMITH_API_KEY": "lsv2_pt_0f1e2d3c4b5a69788796a5b4c3d2e1f0_planted00",
    "BRAINTRUST_API_KEY": "sk-0f1e2d3c4b5a69788796a5b4c3d2e1f0PlantedKey00",
    "WANDB_API_KEY": "0f1e2d3c4b5a69788796a5b4c3d2e1f0aa55planted0",
}
_SERVICE_VARIABLES = ("LANGSMITH_ENDPOINT", "LANGCHAIN_API_KEY", "LANGCHAIN_ENDPOINT", "BRAINTRUST_API_URL", "WF_TRACE_SERVER_URL",
                      "WANDB_BASE_URL", "WANDB_ENTITY", "WANDB_PROJECT", "WEAVE_DISABLED")
_CLOSED = "http://127.0.0.1:9"
PULL_SWITCH = "POISSON_TRACE_TF5_ANSWERED"


@contextlib.contextmanager
def answered() -> Iterator[list[str]]:
    """The pull's one sending function replaced for the block by the three earlier pairs'
    transports, each answering its own service from the committed captures; its wait replaced
    by nothing; every socket connection refused. Yields the addresses asked."""
    import socket
    from importlib import import_module

    from tf24_support import HOST as LS_HOST, Transport as LangSmith
    from tf25_support import HOST as BT_HOST, Transport as Braintrust
    from tf26_support import HOST as WV_HOST, Transport as Weave

    module = import_module("poisson_trace.ingest.pulling")
    services = {LS_HOST: LangSmith(), BT_HOST: Braintrust(), WV_HOST: Weave()}
    asked: list[str] = []

    def send(method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float) -> Any:
        asked.append(url)
        for host, service in services.items():
            if url.startswith(host + "/"):
                return service(method, url, headers, body, timeout)
        raise AssertionError(f"a request went to {url}, which is none of the three services")

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a page's command reached for the network")

    old = (module.send, module.sleep, socket.socket.connect, socket.create_connection)
    try:
        module.send, module.sleep = send, lambda seconds: None
        socket.socket.connect = no_network  # type: ignore[method-assign]
        socket.create_connection = no_network
        yield asked
    finally:
        module.send, module.sleep = old[0], old[1]
        socket.socket.connect = old[2]  # type: ignore[method-assign]
        socket.create_connection = old[3]


def shims(folder: Path) -> Path:
    """A folder holding ``poisson-trace`` and ``poisson-trace-import`` as small scripts that run
    this interpreter on the package under test, whatever console scripts are installed. Under
    ``PULL_SWITCH`` each runs inside ``answered()``; without it, as it is."""
    folder.mkdir(parents=True, exist_ok=True)
    bodies = {"poisson-trace": "from poisson_trace.cli import main", "poisson-trace-import": "from poisson_trace.ingest.cli import main"}
    for name, line in bodies.items():
        path = folder / name
        path.write_text(
            f"#!{sys.executable}\nimport os\nimport sys\n{line}\n"
            f"if os.environ.get({PULL_SWITCH!r}):\n"
            f"    sys.path.insert(0, {str(TESTS)!r})\n"
            "    from tf5_support import answered\n"
            "    with answered():\n"
            "        code = main(sys.argv[1:])\n"
            "    sys.exit(code)\n"
            "sys.exit(main(sys.argv[1:]))\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return folder


def page_root(tmp: Path) -> Path:
    """A folder laid out as a clone's root for a page's commands: the committed fixtures and
    the committed examples, copied, and an empty ``docs/figures/``, so nothing a page runs can
    touch the repository."""
    root = tmp / "clone"
    shutil.copytree(FIXTURES, root / "tests" / "fixtures", ignore=shutil.ignore_patterns("tf5", "tf9", "tf18", "tf19", "tf20", "tf24", "tf25", "tf26"))
    if EXAMPLES.is_dir():
        shutil.copytree(EXAMPLES, root / "examples", ignore=shutil.ignore_patterns("__pycache__"))
    (root / "docs" / "figures").mkdir(parents=True)
    return root


def page_env(home: Path, bin_dir: Path, *, pull: bool) -> dict[str, str]:
    env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}", HOME=str(home))
    for name in ("VIRTUAL_ENV", "BROWSER", "CI", "FORCE_COLOR", "POISSON_TRACE_STYLE", PULL_SWITCH, *_PLANTED, *_SERVICE_VARIABLES):
        env.pop(name, None)
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY"):
        env[name] = _CLOSED
    if pull:
        env.update(_PLANTED)
        env[PULL_SWITCH] = "1"
    else:
        for name in ("LANGSMITH_ENDPOINT", "BRAINTRUST_API_URL", "WF_TRACE_SERVER_URL"):
            env[name] = _CLOSED
    return env


def run_block(block: Block, root: Path, env: dict[str, str]) -> tuple[int, str]:
    command = block.body.replace("\\\n", " ")
    if block.answers is None:
        proc = subprocess.run(["bash", "-c", command], cwd=root, env=env, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
        return proc.returncode, (proc.stdout + proc.stderr).rstrip("\n")
    # asked again when macOS fails the open with its own "ask again" (tf9_support.open_terminal; ruled 2026-11-18, MF-2)
    from tf9_support import open_terminal

    controller, user = open_terminal()
    attrs = termios.tcgetattr(user)
    attrs[3] &= ~termios.ECHO
    termios.tcsetattr(user, termios.TCSANOW, attrs)
    try:
        started = subprocess.Popen(["bash", "-c", command], cwd=root, env=env, stdin=user, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        os.write(controller, "".join(answer + "\n" for answer in block.answers).encode("utf-8"))
        got: dict[str, bytes] = {}

        def drain(name: str, pipe: Any) -> None:
            got[name] = pipe.read()

        readers = [threading.Thread(target=drain, args=(name, pipe), daemon=True) for name, pipe in (("out", started.stdout), ("err", started.stderr))]
        for reader in readers:
            reader.start()
        try:
            code = started.wait(timeout=300)
        except subprocess.TimeoutExpired:
            started.kill()
            code = started.wait()
        for reader in readers:
            reader.join(timeout=10)
    finally:
        os.close(controller)
        os.close(user)
    return code, (got.get("out", b"") + got.get("err", b"")).decode("utf-8", "replace").rstrip("\n")


@dataclass(frozen=True)
class Checked:
    block: Block
    command: str
    code: int
    printed: str
    ran: Block = field(compare=False, default=Block("command", 0, ""))


def run_page(page: Path, tmp: Path) -> list[Checked]:
    """Every command block of the page run in page order in one folder of the page's own; each
    output and excerpt block paired with the command above it, its exit code and what it
    printed."""
    root, home = page_root(tmp), tmp / "home"
    home.mkdir()
    bin_dir = shims(tmp / "bin")
    out: list[Checked] = []
    last: tuple[str, int, str, Block] | None = None
    for block in parse(read(page))[0]:
        if block.kind == "command":
            code, printed = run_block(block, root, page_env(home, bin_dir, pull=block.pull))
            last = (block.body, code, printed.replace("\r\n", "\n"), block)
        elif block.kind in ("output", "excerpt"):
            assert last is not None, f"{rel(page)}:{block.line}: an {block.kind} with no command above it"
            out.append(Checked(block, last[0], last[1], last[2], last[3]))
    return out


def _line_holds(shown: str, printed: str) -> bool:
    """One line of a block marked ``varies`` against the line printed: equal, or equal once each
    ``…`` of the shown line is given a path, a time, an id or a version to stand for."""
    if shown == printed:
        return True
    if "…" not in shown:
        return False
    pattern = "(.+?)".join(re.escape(part) for part in shown.split("…"))
    found = re.fullmatch(pattern, printed)
    return found is not None and all(VARIES.fullmatch(group.strip().rstrip(".,;:)")) for group in found.groups())


def holds(checked: Checked) -> bool:
    """An output block is the whole of what the command printed; an excerpt a run of whole lines
    of it; both with the exit code the mark names, and under ``varies`` line by line by that
    rule."""
    block = checked.block
    if checked.code != block.code:
        return False
    shown, printed = block.body.split("\n"), checked.printed.split("\n")
    same = _line_holds if block.varies else (lambda a, b: a == b)
    if block.kind == "output":
        return len(shown) == len(printed) and all(same(a, b) for a, b in zip(shown, printed, strict=True))
    return any(all(same(a, b) for a, b in zip(shown, printed[at:at + len(shown)], strict=True))
               for at in range(len(printed) - len(shown) + 1))


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
