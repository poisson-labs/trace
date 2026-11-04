"""What the clean-look tests (TF9) share: the command run on pipes or on pseudo-terminals, the
screens those terminals are left showing, the escape sequences read back as a terminal draws them,
the commands a user copies, and the corpus of invocations the pretty rendering is held to.

Not a test module and not collected.

**How a run is reached.** The command runs the way a user runs it, as ``python -c`` with the
console script's body (``tf0_support.script``), in a process of its own whose stdout and stderr
are each a pipe or a pseudo-terminal of a given width. Nothing is mocked: ``isatty`` is whatever
the operating system says about the descriptor. The child's environment starts from the test's
and is then set so that, but for what a case changes, every condition of the switch holds:
``TERM`` is ``xterm-256color``, ``NO_COLOR``, ``CI``, ``COLUMNS``, ``LINES``,
``PYTHONIOENCODING`` and the variables Rich reads to force or drop colour are removed, and the
locale is UTF-8. A case that tests a condition sets or removes one variable on top.

**Runs are shared.** One run of an invocation on one set of streams is made once per test
session and kept in a folder every ``-n`` worker reads (``shared_run``), so the invariants that
read the same run do not each pay for it.

**The pseudo-terminal's screen** is read by ``pyte``, a terminal emulator (a dev dependency): what
the user would see when the command has ended, after every cursor movement and erase.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import select
import shutil
import struct
import subprocess
import sys
import termios
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from conftest import CS, CS_EVENTS, CS_RECORD, FIXTURES, TAU2, TAU2_A, TAU2_B, events_args
from tf0_support import DEEPEVAL, HE_A, HE_B, HE_EVENTS, HUMANEVAL, PILOT, script

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
LOOK = REPO / "docs" / "cli-look.md"

#: Prove's look file as poisson-prove 0.1.2 publishes it (tag v0.1.2, commit a6f211b), the same
#: bytes spec section 17.1 records: 275 lines.
LOOK_SHA256 = "92e71488c2824c056252be9a7b340e7fc138d15359fbcb7431bcfc6fa267d85f"
LOOK_LINES = 275

#: The one module that may import Rich (spec section 17.1: "Rich as a core dependency imported
#: only by a private rendering module").
PRETTY_MODULE = "poisson_trace._pretty"
PRETTY_FILE = SRC / "poisson_trace" / "_pretty.py"

# ---------- the look's colours, mapped to Trace's words (spec section 17.1, AD2) ----------

GREEN = ("ok", "done")
YELLOW = ("stopped", "refused", "too small to tell", "no significant difference", "no control")
RED = ("not ready", "not whole")
BOLD = ("different", "plan")
#: Every verdict word Trace has or has ruled, and the role its word takes: G green, Y yellow, R
#: red, B bold with no colour.
ROLE = {**{w: "G" for w in GREEN}, **{w: "Y" for w in YELLOW}, **{w: "R" for w in RED}, **{w: "B" for w in BOLD}}
#: The text a colour may be drawn on, and nothing else: the verdict words, the two problem
#: prefixes, and the look file's own words for a check (``passed``, ``fail``) in doctor's lines.
MAY_BE = {
    "G": {*GREEN, "passed"},
    "Y": {*YELLOW, "note:"},
    "R": {*RED, "error:", "fail", "fails"},
}

# ---------- small things ----------

ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][0-9A-Za-z]|\x1b[@-Z\\-_=>]")
SGR = re.compile(r"\x1b\[([0-9;:]*)m")
#: The SGR parameters the look allows: reset, bold, dim, normal intensity, the 16 named
#: foreground colours and the default foreground.
ALLOWED_SGR = frozenset({0, 1, 2, 22, 39, *range(30, 38), *range(90, 98)})
#: The controls beyond SGR a live display on stderr needs to remove itself: a carriage return is
#: not an escape; erase in line, cursor up, and hide and show the cursor.
LIVE_CONTROLS = re.compile(r"\x1b\[[0-2]?K|\x1b\[\d*A|\x1b\[\?25[lh]")
VERDICT = re.compile(r"^([a-z][a-z ]*?)  (\S.*)$")
TOKEN = re.compile(r"[A-Za-z0-9]+")
#: What only running work draws: a block bar's or a spinner's glyph (`━`, which Rich draws for a
#: bar and for a table's header rule alike, is left out).
PROGRESS = re.compile(r"[█▉▊▋▌▍▎▏░▒▓⠀-⣿]")


def strip(text: str) -> str:
    return ESCAPE.sub("", text)


def tokens(text: str) -> set[str]:
    """The words and numbers of a text, whatever joins or breaks them."""
    return set(TOKEN.findall(strip(text)))


def words(text: str) -> list[str]:
    return strip(text).split()


def screen_text(rows: Sequence[str], cols: int) -> str:
    """A terminal's screen as text, a row that reaches the right edge joined to the next (the
    terminal wrapped it, not the program)."""
    out = ""
    for row in rows:
        out += row if len(row) >= cols else row + "\n"
    return out


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------- the escape sequences, read as a terminal draws them ----------


@dataclass(frozen=True)
class Cell:
    char: str
    bold: bool
    dim: bool
    fg: int | None  # one of the 16 named colours (0 to 15), or None for the terminal's own


def role(cell: Cell) -> str:
    """``G``, ``Y`` or ``R`` for green, yellow or red (normal or bright), ``O`` for any other
    colour, ``B`` bold with no colour, ``D`` dim, blank for plain."""
    if cell.fg is not None:
        return {2: "G", 10: "G", 3: "Y", 11: "Y", 1: "R", 9: "R"}.get(cell.fg, "O")
    if cell.bold:
        return "B"
    if cell.dim:
        return "D"
    return " "


def cells(text: str) -> list[list[Cell]]:
    """``text`` as lines of cells, each with the SGR state it is drawn in. Escapes that are not
    SGR draw nothing."""
    lines: list[list[Cell]] = [[]]
    bold = dim = False
    fg: int | None = None
    pos = 0
    text = text.replace("\r\n", "\n")
    while pos < len(text):
        m = SGR.match(text, pos)
        if m:
            params = [int(p or 0) for p in re.split("[;:]", m.group(1))] if m.group(1) else [0]
            for p in params:
                if p == 0:
                    bold = dim = False
                    fg = None
                elif p == 1:
                    bold = True
                elif p == 2:
                    dim = True
                elif p == 22:
                    bold = dim = False
                elif 30 <= p <= 37:
                    fg = p - 30
                elif 90 <= p <= 97:
                    fg = p - 90 + 8
                elif p == 39:
                    fg = None
            pos = m.end()
            continue
        e = ESCAPE.match(text, pos)
        if e:
            pos = e.end()
            continue
        ch = text[pos]
        if ch == "\n":
            lines.append([])
        elif ch != "\r":
            lines[-1].append(Cell(ch, bold, dim, fg))
        pos += 1
    return lines


def odd_escapes(text: str, *, live: bool) -> list[str]:
    """Every escape sequence in ``text`` the look does not allow: an SGR with any parameter
    outside ``ALLOWED_SGR`` (a background, 256 or true colour, italic, underline, reverse,
    blink, a hyperlink's OSC), and any other escape, but for a live display's controls when
    ``live`` (stderr)."""
    odd = []
    for m in ESCAPE.finditer(text):
        seq = m.group(0)
        s = SGR.fullmatch(seq)
        if s:
            params = [int(p or 0) for p in re.split("[;:]", s.group(1))] if s.group(1) else [0]
            if any(p not in ALLOWED_SGR for p in params):
                odd.append(repr(seq))
        elif not (live and LIVE_CONTROLS.fullmatch(seq)):
            odd.append(repr(seq))
    return odd


def runs_of(line: list[Cell]) -> list[tuple[str, str]]:
    """A line's maximal runs of one colour role, as (role, text), for the coloured roles only;
    spaces between two words of one colour stay in the run."""
    out: list[tuple[str, str]] = []
    cur, buf = "", ""
    for c in line:
        r = role(c)
        r = r if r in "GYRO" else ""
        if c.char == " " and cur and r in ("", cur):
            buf += " "
            continue
        if r != cur:
            if cur:
                out.append((cur, buf.rstrip()))
            cur, buf = r, ""
        buf += c.char
    if cur:
        out.append((cur, buf.rstrip()))
    return [(r, t) for r, t in out if t]


# ---------- the commands a user copies ----------

_NEXT = re.compile(r"^\s*next: (\S.*)$")
#: A command opens with the command's name and then a verb or an option, or with pip install.
_OPENS = (
    r"(?:(?:poisson-trace|python -m poisson_trace)\s+(?:init|runs|name|where|compare|fix-check|changes|doctor|import|--?[a-z])"
    r"|poisson-trace-import\s+\S|pip install\s)"
)
_WHOLE = re.compile(rf"^\s*({_OPENS}.*)$")
_DETAIL = re.compile(rf"^\s{{2,}}\S+(?: \S+)?\s{{2,}}({_OPENS}.*)$")
_SPAN = re.compile(rf"`({_OPENS}[^`]*)`")


def commands(plain: str) -> list[str]:
    """The commands a plain rendering prints for the user to copy: each ``next:`` line's command,
    each line that is a command, each ``label  command`` detail line's command, and each command
    in backquotes inside prose. A shell continuation's trailing backslash is part of its line, and
    the line it continues onto is a command of its own."""
    found: list[str] = []
    continued = False
    for line in plain.splitlines():
        if continued and line.strip():
            found.append(line.strip())
            continued = line.rstrip().endswith("\\")
            continue
        continued = False
        for pattern in (_NEXT, _DETAIL, _WHOLE):
            m = pattern.match(line)
            if m:
                found.append(m.group(1).rstrip())
                continued = line.rstrip().endswith("\\")
                break
        found += [m.group(1) for m in _SPAN.finditer(line)]
    return found


def broken(command: str, rendered: str) -> bool:
    """Whether ``command`` is not on one line of ``rendered`` (escapes removed) as it is, every
    character in place and none inserted."""
    return not any(command in line for line in strip(rendered).replace("\r\n", "\n").split("\n"))


# ---------- the child's environment ----------

#: Removed from the child's environment, so that only what a case sets decides the switch.
CLEARED = (
    "NO_COLOR", "CI", "COLUMNS", "LINES", "PYTHONIOENCODING", "FORCE_COLOR", "CLICOLOR",
    "CLICOLOR_FORCE", "TTY_COMPATIBLE", "TTY_INTERACTIVE", "TERM", "COLORTERM", "JUPYTER_COLUMNS",
    "JUPYTER_LINES", "GITHUB_ACTIONS",
)


def child_env(home: Path, extra: Mapping[str, str | None] = ()) -> dict[str, str]:  # type: ignore[assignment]
    env = {k: v for k, v in os.environ.items() if k not in CLEARED and not k.startswith("PYTEST_")}
    env.update({"TERM": "xterm-256color", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "HOME": str(home)})
    for k, v in dict(extra).items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    return env


# ---------- a run on pipes or pseudo-terminals ----------


@dataclass
class Run:
    code: int
    #: Everything written to stdout and to stderr, decoded; a terminal's ``\r\n`` read as ``\n``.
    out: str
    err: str
    #: What each terminal shows when the command has ended (empty for a pipe).
    out_screen: list[str] = field(default_factory=list)
    err_screen: list[str] = field(default_factory=list)


def _winsize(fd: int, cols: int, rows: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def run(
    argv: Sequence[str],
    *,
    cwd: Path,
    home: Path,
    command: str = "trace",
    stdout: str = "pty",
    stderr: str = "own",
    cols: int = 80,
    rows: int = 200,
    env: Mapping[str, str | None] = (),  # type: ignore[assignment]
    prelude: str = "",
    timeout: float = 120,
) -> Run:
    """The command with stdout ``pty`` or ``pipe`` and stderr ``own`` (a terminal of its own),
    ``pty`` (stdout's terminal) or ``pipe``; stdin is the null device. Each terminal is ``cols``
    wide. ``prelude`` is Python run before the console script's body."""
    import pyte

    terminals: dict[str, tuple[int, int]] = {}

    def terminal(name: str) -> int:
        if name not in terminals:
            controller, user = os.openpty()
            _winsize(user, cols, rows)
            terminals[name] = (controller, user)
        return terminals[name][1]

    out_fd: Any = terminal("out") if stdout == "pty" else subprocess.PIPE
    if stderr == "pty":
        assert stdout == "pty"
        err_fd: Any = terminal("out")
    elif stderr == "own":
        err_fd = terminal("err")
    else:
        err_fd = subprocess.PIPE
    proc = subprocess.Popen(
        [sys.executable, "-c", prelude + script(command), *[str(a) for a in argv]],
        cwd=cwd, env=child_env(home, env), stdin=subprocess.DEVNULL, stdout=out_fd, stderr=err_fd,
        close_fds=True, start_new_session=True,
    )
    for _, user in terminals.values():
        os.close(user)
    readers = {controller: name for name, (controller, _) in terminals.items()}
    if proc.stdout is not None:
        readers[proc.stdout.fileno()] = "out-pipe"
    if proc.stderr is not None:
        readers[proc.stderr.fileno()] = "err-pipe"
    raw = {name: bytearray() for name in readers.values()}
    screens = {name: pyte.Screen(cols, rows) for name in terminals}
    streams = {name: pyte.ByteStream(screens[name]) for name in terminals}
    for screen in screens.values():
        screen.set_mode(pyte.modes.LNM)  # a line feed returns the carriage, as the tty's onlcr does
    open_fds = set(readers)
    deadline = time.monotonic() + timeout
    try:
        while open_fds:
            if time.monotonic() > deadline:
                raise AssertionError(f"timed out after {timeout} s: {list(argv)}")
            ready, _, _ = select.select(list(open_fds), [], [], 0.05)
            for fd in ready:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:  # a terminal whose other end has closed reads as an error
                    chunk = b""
                if not chunk:
                    open_fds.discard(fd)
                    continue
                raw[readers[fd]] += chunk
                if readers[fd] in streams:
                    streams[readers[fd]].feed(chunk)
        code = proc.wait(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        for controller, _ in terminals.values():
            with contextlib.suppress(OSError):
                os.close(controller)

    def text(name: str) -> str:
        return raw.get(name, bytearray()).decode("utf-8", "replace").replace("\r\n", "\n")

    out = text("out") if stdout == "pty" else text("out-pipe")
    err = out if stderr == "pty" else text("err") if stderr == "own" else text("err-pipe")

    def shown(name: str) -> list[str]:
        return [line.rstrip() for line in screens[name].display] if name in screens else []

    return Run(code, out, err, shown("out"), shown("err") if stderr == "own" else shown("out"))


# ---------- runs shared by every worker ----------


@contextlib.contextmanager
def _lock(path: Path) -> Iterator[None]:
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            time.sleep(0.05)
            continue
        os.close(fd)
        break
    try:
        yield
    finally:
        path.unlink()


def shared_run(base: Path, item: Item, **how: Any) -> Run:
    """``run`` of ``item`` with ``how``, made once for the whole test session (under ``base``, a
    folder every worker shares) and read back by every test and worker that asks for it again."""
    # an item and the same item with --plain given share their folder
    folder = [item.command, [a for a in item.argv if a != "--plain"], item.stage]
    of = hashlib.sha256(json.dumps(folder).encode()).hexdigest()[:16]
    key = hashlib.sha256(json.dumps([asdict(item), sorted(how.items())], default=str).encode()).hexdigest()[:24]
    done = base / f"{key}.json"
    # every run of one item runs in the same folder, staged afresh, so that a path a command
    # prints (init prints the folder it looks under) reads the same in every run of it
    with _lock(base / f"{of}.lock"):
        if not done.exists():
            work, home = base / of / "w", base / of / "home"
            if work.parent.exists():
                shutil.rmtree(work.parent)
            stage(work, item)
            home.mkdir()
            made = run(item.argv, cwd=work, home=home, command=item.command, **how)
            done.write_text(json.dumps(asdict(made)), encoding="utf-8")
    return Run(**json.loads(done.read_text(encoding="utf-8")))


def shared_base(tmp_path_factory: Any) -> Path:
    """A folder every ``-n`` worker of this test session shares."""
    root = tmp_path_factory.getbasetemp()
    if os.environ.get("PYTEST_XDIST_WORKER"):
        root = root.parent
    base = root / "tf9-runs"
    base.mkdir(exist_ok=True)
    return base


# ---------- the corpus the pretty rendering is held to ----------


@dataclass(frozen=True)
class Item:
    label: str
    command: str  # "trace" or "import"
    argv: tuple[str, ...]
    expect: int
    #: What the folder the item runs in holds before it runs: "" nothing, "csv" the HumanEval
    #: pair as two CSV tables, "imported" a store ``imported`` holding the DeepEval pair,
    #: "tf0-bare" what ``tf0_support.prepare`` leaves, "tf0" that and the conformance corpus's
    #: imports made (the folder the corpus's own runs read).
    stage: str = ""


def stage(work: Path, item: Item) -> None:
    work.mkdir(parents=True)
    if item.stage == "csv":
        for p in sorted((FIXTURES / "ingest" / "table").glob("humaneval-*.csv")):
            shutil.copy(p, work / p.name)
    elif item.stage in ("tf0", "tf0-bare"):
        from tf0_support import chdir, corpus, prepare, run_item

        work.rmdir()
        prepare(work)
        if item.stage == "tf0":
            with chdir(work):
                for made in (run_item(i) for i in corpus() if i.command == "import" and i.kind == "report"):
                    assert made.code == 0, made.text
    elif item.stage == "imported":
        from tf0_support import chdir, deepeval_import, trace_import

        with chdir(work):
            for run_name, which in (("he-a", "a"), ("he-b", "b")):
                made = trace_import(deepeval_import("imported", run_name, which))
                assert made.code == 0, made.text


def _deepeval(store: str, run_name: str, which: str = "a") -> tuple[str, ...]:
    return (
        "deepeval", str(DEEPEVAL / f"humaneval-{which}.json.gz"), "--store", store, "--run", run_name,
        "--metric", "Tests Passed", "--cut", "recorded", "--case", "name",
        "--started", "2026-09-05T18:54:07Z" if which == "a" else "2026-09-05T19:50:09Z",
    )


def _t(label: str, argv: Sequence[str], expect: int = 0, stage_: str = "") -> Item:
    return Item(label, "trace", tuple(str(a) for a in argv), expect, stage_)


#: The fixture runs the per-input table folds on: Prove's own HumanEval store, whose inputs are
#: keyed by two fields (task_id and temperature).
FIX_CHECK_HE = _t("fix-check, every input", ["fix-check", HE_A, HE_B, "--store", HUMANEVAL, *events_args(HE_EVENTS), "--inputs", "all", "--max-mde", "0.05"])
CHANGES_HE = _t("changes", ["changes", HE_A, HE_B, "--store", HUMANEVAL, *events_args(HE_EVENTS), "--top", "4"])
COMPARE_SMALL = _t("compare, too small to tell", ["compare", TAU2_A, TAU2_B, "--store", TAU2, "--event", "unsolved", "--max-mde-hr", "1.3"])

#: One of each verb, each verdict word a verb on main reaches without timing, both problem
#: prefixes, help and the version: the fast lane's corpus (the slow lane runs the whole of
#: ``tf0_support.corpus`` the same way).
CORPUS: tuple[Item, ...] = (
    _t("where", ["where", CS_RECORD, "--store", CS, *events_args(CS_EVENTS), "--at", "20", "--at", "40"]),
    COMPARE_SMALL,
    _t("compare, no significant difference", ["compare", TAU2_A, TAU2_B, "--store", TAU2, "--event", "unsolved", "--max-mde-hr", "1.457"]),
    _t("fix-check with a selecting run", ["fix-check", TAU2_B, PILOT, "--store", TAU2, "--event", "unsolved", "--failing-from", TAU2_A, "--max-mde", "0.20"]),
    FIX_CHECK_HE,
    CHANGES_HE,
    _t("fix-check on imports, different", ["fix-check", "he-a", "he-b", "--store", "imported", "--event", "missed", "--inputs", "all", "--max-mde", "0.02", "--top", "3"], 0, "imported"),
    _t("runs", ["runs", "--store", TAU2, "--event", "unsolved"]),
    _t("runs with a note", ["runs", "--store", TAU2]),
    _t("doctor, not ready", ["doctor"], 4),
    _t("init", ["init", "--yes", "--case-column", "case", "--outcome-column", "outcome", "--failed", "failed_assertion", "--failed", "crashed"], 0, "csv"),
    Item("import", "import", _deepeval("store", "he-a"), 0),
    _t("a refusal", ["where", "no-such-run", "--store", CS, "--event", "unresolved"], 1),
    _t("a wrong command line", ["where", CS_RECORD, "--store", CS, "--bogus"], 2),
    _t("help", ["--help"]),
    _t("fix-check help", ["fix-check", "--help"]),
    _t("version", ["--version"]),
)
REPORTS = tuple(i for i in CORPUS if i.expect in (0, 4) and "help" not in i.label and i.label != "version")
JSON_ITEMS: tuple[Item, ...] = (
    _t("where as JSON", ["where", TAU2_A, "--store", TAU2, "--event", "unsolved", "--json"]),
    _t("compare as JSON", ["compare", TAU2_A, TAU2_B, "--store", TAU2, "--event", "unsolved", "--max-mde-hr", "1.3", "--json"]),
    _t("fix-check as JSON", [*FIX_CHECK_HE.argv, "--json"]),
    _t("changes as JSON", [*CHANGES_HE.argv, "--json"]),
    _t("doctor as JSON", ["doctor", "--json"], 4),
    Item("import as JSON", "import", (*_deepeval("store", "he-a"), "--json"), 0),
)


def piped(base: Path, item: Item) -> Run:
    """The item on two pipes, under an environment in which every other condition holds: the
    plain rendering, as a script reads it."""
    return shared_run(base, item, stdout="pipe", stderr="pipe")


def pretty(base: Path, item: Item, cols: int = 80) -> Run:
    """The item with stdout and stderr each on a terminal of its own, ``cols`` wide."""
    return shared_run(base, item, stdout="pty", stderr="own", cols=cols)


def plain_on_terminal(base: Path, item: Item, cols: int = 80) -> Run:
    """The item on the same two terminals with ``--plain`` given after it."""
    forced = Item(item.label + " --plain", item.command, (*item.argv, "--plain"), item.expect, item.stage)
    return shared_run(base, forced, stdout="pty", stderr="own", cols=cols)


def unwrap(plain: str, wrapped: str, cols: int) -> list[str]:
    """What breaks plain's own wrapping of ``plain`` (piped) into ``wrapped`` (on a terminal
    ``cols`` wide), as sentences; empty when it holds. A line that fits is printed as it is. A
    longer line is printed as consecutive lines that fit, the first opening with the line's own
    indentation and each after it indented further than the first (a hanging indent), whose words
    in order are the line's words. The first line of stdout (the verdict line), a table row
    (opening with ``|``) and a line holding a command to copy are printed as they are, whatever
    their length. A word longer than the width is never broken."""
    problems: list[str] = []
    rows = wrapped.split("\n")
    at = 0
    copy = commands(plain)
    for n, line in enumerate(plain.split("\n")):
        whole = n == 0 or line.lstrip().startswith("|") or any(c in line for c in copy)
        if len(line) <= cols or whole or not line.strip():
            if at >= len(rows) or rows[at] != line:
                problems.append(f"line {n + 1} not printed as it is: {line[:60]!r}")
                return problems
            at += 1
            continue
        indent = len(line) - len(line.lstrip(" "))
        want = line.split()
        got: list[str] = []
        first = True
        while len(got) < len(want) and at < len(rows):
            row = rows[at]
            row_indent = len(row) - len(row.lstrip(" "))
            if first and row_indent != indent:
                problems.append(f"line {n + 1}'s first part is not at its own indent")
            if not first and row_indent <= indent:
                problems.append(f"line {n + 1}'s continuation has no hanging indent: {row[:60]!r}")
            if len(row) > cols and len(row.split()) > 1:
                problems.append(f"line {n + 1} wrapped wider than {cols}: {row[:60]!r}")
            got += row.split()
            first = False
            at += 1
        if got != want:
            problems.append(f"line {n + 1}'s words are not kept in order: {line[:60]!r}")
            return problems
    return problems
