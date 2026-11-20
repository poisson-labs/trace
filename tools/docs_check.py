"""Check that every command a page shows runs as the page shows it.

    python tools/docs_check.py [--summary FILE] [PAGE ...]

With no page it checks the README, the contributing page and every page under ``docs/`` but
the look standard (``docs/cli-look.md``), of the checkout this file sits in. It exits 0 when
every block holds, and its last line is then

    ok  N blocks held on P pages, S skipped

It exits 1 when any block does not hold, with one line ``PAGE:LINE: what is wrong`` on stderr
for each, where LINE is the first line of the block. Every skipped block is listed on stdout
with its reason, and appended to the file ``--summary`` names (a CI job's summary).

How a page is run. Each page gets a scratch folder of its own, laid out as a clone of the
repository, holding an empty ``docs/figures`` and what the page names of the checkout's
``tests/fixtures`` and ``examples``, copied in: for each path ``tests/fixtures/NAME`` or
``examples/NAME`` written anywhere on the page, where NAME is a file or a folder at the top of
that folder in the checkout, that file or that folder whole. A page that names neither folder
gets neither. When a block the page runs writes ``fixtures`` or ``examples`` any other way
(the folder alone, a pattern, a name that is not at its top), the whole of that folder is
copied, less the folders of ``NOT_COPIED`` the page does not name. Its command blocks run
there with bash, in page order, with whatever
``poisson-trace`` is first on ``PATH`` (and, for the one recipe that runs them, whatever
``poisson-tasks``, ``poisson-prove`` and ``pytest``), a home folder of its own and no key in the
environment. Nothing is written to the
checkout, to the folder the checker was started in, or to the user's home.

The marks. A mark is an HTML comment alone on the line just above a fenced block:

``<!-- command -->``
    Run the block. Stdin, stdout and stderr are not a terminal.
``<!-- command pull -->``
    Run it with LangSmith, Braintrust and Weave answered from the committed captures under
    ``tests/fixtures/ingest/``, served on this machine's loopback address, and a planted key
    for each. A command that names a service's address anywhere else is a fault.
``<!-- command tty answers="A|B" -->``
    Run it with stdin a terminal and each answer typed as one line. Stdout and stderr stay
    pipes, so what prints is the plain text a page can show.
``<!-- output exit=N -->``
    The whole of what the command above printed (stdout, then stderr), and its exit code.
``<!-- excerpt exit=N -->``
    A run of whole lines of it, and its exit code.
``<!-- output exit=N varies -->``, ``<!-- excerpt exit=N varies -->``
    The same, where ``…`` in a line stands for a path, a time, an id or a version written
    whole, and for nothing else. Without ``varies`` a ``…`` is itself.
``<!-- skip reason="WHY" -->``
    Show the block and do not run it. A ``poisson-trace`` command may be skipped only when it
    holds a word in capitals that is the reader's to fill in, or ``…``, or is the bare
    command, which opens the terminal app.

Every fenced block carries a mark, except one whose fence names what it holds (``toml``,
``json``, ``python``, ``text`` and the rest of ``DATA_LANGUAGES``) and whose first line is not
a shell command.

This file needs the standard library alone: it runs beside an installed wheel, in an
environment that holds nothing of the repository's tests.
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import termios
import threading
import time
import urllib.parse
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CHECKOUT = Path(__file__).resolve().parents[1]
FIXTURES = CHECKOUT / "tests" / "fixtures"
#: The examples a recipe runs on (the three-tools recipe's), copied beside the fixtures.
EXAMPLES = CHECKOUT / "examples"
INGEST = FIXTURES / "ingest"
STANDARDS = ("cli-look.md",)
#: Fixture folders no page reads: earlier outputs the test suite pins. Left out of a copy of
#: the whole of ``tests/fixtures``, unless the page names one.
NOT_COPIED = ("tf5", "tf9", "tf18", "tf19", "tf24", "tf25", "tf26")
#: The two folders of the checkout a page's commands may read, each by the path a page writes.
COPIED = {"tests/fixtures": FIXTURES, "examples": EXAMPLES}
#: How long one block may run, in seconds.
TIME_LIMIT = 600

MARK = re.compile(
    r'^<!-- (?:(?P<command>command)(?: (?P<pull>pull)| tty answers="(?P<answers>[^"]*)")?'
    r"|(?P<shown>output|excerpt) exit=(?P<code>\d+)(?P<varies> varies)?"
    r'|skip reason="(?P<reason>[^"]+)") -->$'
)
#: A comment that means to be a mark, whether or not it is well formed.
MARKISH = re.compile(r"^<!--\s*(command|output|excerpt|skip|docs-check)\b")
DATA_LANGUAGES = (
    "toml", "json", "jsonl", "python", "text", "yaml", "markdown", "csv", "xml", "diff",
)  # fmt: skip
SHELLISH = re.compile(
    r"^\s*(?:\$ )?(?:poisson-trace(?:-import)?|pip3?|python3?(?:\.\d+)?|git|cd|mkdir|cp|tar"
    r"|gunzip|export|shasum|sha256sum|source|uv|pytest|ruff|mypy|\.)(?:\s|$)"
)
#: A word that is the reader's to fill in: three or more capitals, or an ellipsis.
PLACEHOLDER = re.compile(r"(?<![\w-])[A-Z][A-Z_]{2,}(?![\w])|…|\.\.\.")
#: What ``…`` may stand for under ``varies``: a path or a file address, a date or a time, a
#: span of time, an id in hexadecimal, a run's id, or a version of three numbers.
VARIES = re.compile(
    r"(?:file://)?(?:~|\.{0,2})?/[^\s]*"
    r"|\d{4}-\d\d-\d\d(?:[T ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[+-]\d\d:\d\d| UTC)?)?"
    r"|\d+(?:\.\d+)? ?(?:ms|s|min|h)"
    r"|[0-9a-f]{8,64}"
    r"|\d{8}T\d{6}Z-[0-9a-f]{4}"
    r"|\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?"
)
#: How a command asks a service: the word its address opens with.
ADDRESSES = ("langsmith:", "braintrust:", "weave:")
#: The key each service's pull reads, planted for a block marked ``pull``. None opens anything.
PLANTED = {
    "LANGSMITH_API_KEY": "lsv2_pt_0f1e2d3c4b5a69788796a5b4c3d2e1f0_planted00",
    "BRAINTRUST_API_KEY": "sk-0f1e2d3c4b5a69788796a5b4c3d2e1f0PlantedKey00",
    "WANDB_API_KEY": "0f1e2d3c4b5a69788796a5b4c3d2e1f0aa55planted0",
}
#: The variable that moves each service's requests to another host.
ENDPOINTS = {
    "langsmith": "LANGSMITH_ENDPOINT",
    "braintrust": "BRAINTRUST_API_URL",
    "weave": "WF_TRACE_SERVER_URL",
}
#: Variables of the caller's that must not reach a page's command.
REMOVED = (
    "VIRTUAL_ENV", "BROWSER", "CI", "FORCE_COLOR", "POISSON_TRACE_STYLE", "LANGCHAIN_API_KEY",
    "LANGCHAIN_ENDPOINT", "WANDB_BASE_URL", "WANDB_ENTITY", "WANDB_PROJECT", "WEAVE_DISABLED",
)  # fmt: skip
PROXIES = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY")
#: A port of this machine nothing listens on: where a request goes that should not be made.
CLOSED = "http://127.0.0.1:9"


# ---------- reading a page ----------


@dataclass(frozen=True)
class Block:
    """One fenced block of a page, with its mark read."""

    kind: str  # command, output, excerpt, skip, data (named by its fence) or unmarked
    line: int  # the first line of the body, counting from 1
    body: str
    code: int | None = None
    pull: bool = False
    answers: tuple[str, ...] | None = None
    varies: bool = False
    reason: str = ""


def parse(text: str) -> tuple[list[Block], list[tuple[int, str]]]:
    """Every fenced block of a page in order, and the page's faults as (line, what is wrong):
    a comment that means to be a mark and is not one, a mark with no block under it, a fence
    that is never closed."""
    lines = text.split("\n")
    blocks: list[Block] = []
    faults: list[tuple[int, str]] = []
    pending: tuple[int, re.Match[str]] | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            end = i + 1
            while end < len(lines) and not lines[end].startswith("```"):
                end += 1
            if end >= len(lines):
                faults.append((i + 1, "a fence that is never closed"))
                break
            body, language = "\n".join(lines[i + 1 : end]), line[3:].strip()
            mark = pending[1] if pending is not None and pending[0] == i - 1 else None
            blocks.append(_block(mark, i + 2, body, language))
            pending = None
            i = end + 1
            continue
        if pending is not None and pending[0] == i - 1:
            faults.append((pending[0] + 1, "a mark with no block under it"))
            pending = None
        if MARKISH.match(line):
            found = MARK.match(line)
            if found:
                pending = (i, found)
            else:
                faults.append((i + 1, f"not a mark the docs check reads: {line}"))
        i += 1
    if pending is not None:
        faults.append((pending[0] + 1, "a mark with no block under it"))
    return blocks, faults


def _block(mark: re.Match[str] | None, line: int, body: str, language: str) -> Block:
    if mark is None:
        first = next((b for b in body.split("\n") if b.strip()), "")
        named = language in DATA_LANGUAGES and not SHELLISH.match(first)
        return Block("data" if named else "unmarked", line, body)
    if mark.group("command"):
        answers = mark.group("answers")
        typed = None if answers is None else tuple(answers.split("|")) if answers else ()
        return Block("command", line, body, pull=bool(mark.group("pull")), answers=typed)
    if mark.group("shown"):
        return Block(
            mark.group("shown"), line, body,
            code=int(mark.group("code")), varies=bool(mark.group("varies")),
        )  # fmt: skip
    return Block("skip", line, body, reason=mark.group("reason"))


def commands(block: Block) -> list[list[str]]:
    """The commands of a block, each as its words; a line ending in a backslash joins the
    next, and a comment line is left out."""
    out = []
    for line in block.body.replace("\\\n", " ").split("\n"):
        if line.strip() and not line.lstrip().startswith("#"):
            try:
                out.append(shlex.split(line))
            except ValueError:
                out.append(line.split())
    return out


def could_run(command: Sequence[str]) -> bool:
    """Whether a skipped command is a ``poisson-trace`` command with nothing left for the
    reader to fill in, and so one the check could have run."""
    starts = [
        command[0],
        *[command[i + 1] for i, w in enumerate(command[:-1]) if w in ("&&", ";", "||")],
    ]
    if "poisson-trace" not in starts and "poisson-trace-import" not in starts:
        return False
    return list(command) != ["poisson-trace"] and not PLACEHOLDER.search(" ".join(command))


# ---------- the three services, answered from the committed captures ----------
#
# Each service's folder under tests/fixtures/ingest/ holds api/requests.json: every request
# that was made when the captures were taken, with the file that holds the answer it got. A
# request a page's pull makes is answered with the answer the service gave to that request,
# and a request no capture answers gets a 404, which fails the block.

Answer = tuple[str, bytes]
Asked = tuple[str, str, list[tuple[str, str]], Any]  # method, path, query, JSON body


def _table(service: str) -> list[dict[str, Any]]:
    table = json.loads((INGEST / service / "api" / "requests.json").read_text(encoding="utf-8"))
    return [entry for entry in table if entry["status"] == 200]


def _captured(entry: dict[str, Any]) -> Asked:
    parts = urllib.parse.urlsplit(entry["url"])
    return entry["method"].upper(), parts.path, urllib.parse.parse_qsl(parts.query), entry["body"]


def _langsmith(asked: Asked) -> Answer | None:
    def normal(request: Asked) -> tuple[Any, ...]:
        method, path, query, body = request
        fields = dict(query)
        if path.endswith("/feedback"):
            fields.setdefault("offset", "0")
        held = None
        if body is not None:
            held = dict(body)
            # the captures were asked with no lower bound on the runs' start; the pull sends
            # one, and the service's answer is the same
            held.pop("min_start_time", None)
            if "selects" in held:
                held["selects"] = sorted(held["selects"])
        return method, path, sorted(fields.items()), json.dumps(held, sort_keys=True)

    api = INGEST / "langsmith" / "api"
    for entry in _table("langsmith"):
        if normal(_captured(entry)) == normal(asked):
            return "application/json", (api / entry["file"]).read_bytes()
    return None


def _braintrust(asked: Asked) -> Answer | None:
    def normal(request: Asked) -> tuple[Any, ...]:
        method, path, query, body = request
        return method, path, sorted(query), json.dumps(body, sort_keys=True)

    api = INGEST / "braintrust" / "api"
    for entry in _table("braintrust"):
        if normal(_captured(entry)) == normal(asked):
            return "application/json", (api / entry["file"]).read_bytes()
    # A whole fetch ends with a cursor, and asking for the page after it returns a page of no
    # events. The captures hold that last, empty page once (the candidate's, page 5); it
    # answers the end cursor of every committed fetch.
    method, path, query, _ = asked
    pieces = path.strip("/").split("/")
    fields = dict(query)
    if (
        method == "GET"
        and len(pieces) == 4
        and pieces[:2] == ["v1", "experiment"]
        and pieces[3] == "fetch"
    ):
        ends = {
            json.loads(p.read_text(encoding="utf-8")).get("cursor")
            for p in api.glob("*.fetch.json")
        }
        if set(fields) == {"limit", "cursor"} and fields["cursor"] in ends - {None}:
            return "application/json", (api / "slice-candidate.fetch.page-5.json").read_bytes()
    return None


def _weave(asked: Asked) -> Answer | None:
    method, path, _, body = asked
    if method != "POST" or path != "/calls/stream_query" or not isinstance(body, dict):
        return None
    api = INGEST / "weave" / "api"
    whole = json.dumps(body, sort_keys=True)
    for entry in _table("weave"):
        if json.dumps(entry["body"], sort_keys=True) == whole:
            return "application/jsonl", (api / entry["file"]).read_bytes()
    # A request for one page (a limit and an offset) is answered with those lines of the
    # committed answer to the same request asked whole.
    limit, offset = body.get("limit"), body.get("offset")
    if type(limit) is int and type(offset) is int and limit > 0 and offset >= 0:
        rest = json.dumps(
            {k: v for k, v in body.items() if k not in ("limit", "offset")}, sort_keys=True
        )
        for entry in _table("weave"):
            if "limit" not in entry["body"] and json.dumps(entry["body"], sort_keys=True) == rest:
                lines = (api / entry["file"]).read_bytes().splitlines(keepends=True)
                return "application/jsonl", b"".join(lines[offset : offset + limit])
    return None


SERVICES: dict[str, Callable[[Asked], Answer | None]] = {
    "langsmith": _langsmith,
    "braintrust": _braintrust,
    "weave": _weave,
}


def _handler(answer: Callable[[Asked], Answer | None]) -> type[http.server.BaseHTTPRequestHandler]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def _serve(self) -> None:
            parts = urllib.parse.urlsplit(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else None
            try:
                body = json.loads(raw.decode("utf-8")) if raw else None
            except ValueError:
                body = None
            query = urllib.parse.parse_qsl(parts.query)
            found = answer((self.command.upper(), parts.path, query, body))
            if found is None:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", found[0])
            self.send_header("Content-Length", str(len(found[1])))
            self.end_headers()
            self.wfile.write(found[1])

        do_GET = do_POST = _serve

        def log_message(self, format: str, *args: Any) -> None:
            pass

    return Handler


class Captures:
    """The three services' committed answers, each served on a port of this machine's
    loopback address for as long as the check runs."""

    def __init__(self) -> None:
        self.servers = {
            name: http.server.ThreadingHTTPServer(("127.0.0.1", 0), _handler(answer))
            for name, answer in SERVICES.items()
        }
        for server in self.servers.values():
            threading.Thread(target=server.serve_forever, daemon=True).start()

    def addresses(self) -> dict[str, str]:
        """The variable that moves each service's requests, set to where its answers are."""
        return {
            ENDPOINTS[name]: f"http://127.0.0.1:{server.server_address[1]}"
            for name, server in self.servers.items()
        }

    def close(self) -> None:
        for server in self.servers.values():
            server.shutdown()
            server.server_close()


# ---------- running a block ----------


def environment(
    home: Path, addresses: dict[str, str] | None, extra: Mapping[str, str] | None = None
) -> dict[str, str]:
    """What a page's command runs with: the caller's environment with a home of its own, no
    key, and every proxy and service address pointed at a closed port; or, for a block marked
    ``pull`` (``addresses`` given), the planted keys and the captures' addresses. ``extra`` is
    the caller's own to add first (the test suite's ``PATH``, with the package under test
    first on it); nothing of it outlasts what is set here."""
    env = dict(os.environ, **(extra or {}))
    env["HOME"] = str(home)
    for name in (*REMOVED, *PLANTED, *ENDPOINTS.values()):
        env.pop(name, None)
    for name in PROXIES:
        env[name] = CLOSED
    env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost"
    if addresses is None:
        env.update({variable: CLOSED for variable in ENDPOINTS.values()})
    else:
        env.update(PLANTED)
        env.update(addresses)
    return env


#: The error number macOS gives ``openpty`` when the kernel's own "ask again" for an open leaks out
#: to the caller (XNU's ``EREDRIVEOPEN``); no terminal was opened and nothing is wrong with it.
_OPEN_AGAIN = -6


def _open_terminal(tries: int = 50) -> tuple[int, int]:
    """A new pseudo-terminal: its controlling end and the end a command is given. On macOS, while
    other processes open and close pseudo-terminals, ``os.openpty`` now and then fails with
    ``OSError: [Errno -6]``; that one error is asked again, a moment later each time, and any
    other, and this one ``tries`` times running, is raised (as ``tests/tf9_support.py`` does)."""
    for attempt in range(tries):
        try:
            return os.openpty()
        except OSError as e:
            if e.errno != _OPEN_AGAIN or attempt == tries - 1:
                raise
            time.sleep(0.01 * (attempt + 1))
    raise AssertionError("unreachable")


def run(block: Block, folder: Path, env: dict[str, str]) -> tuple[int, str]:
    """The block run with bash in the folder: its exit code and what it printed, stdout then
    stderr."""
    script = ["bash", "-c", block.body.replace("\\\n", " ")]
    if block.answers is None:
        try:
            done = subprocess.run(
                script, cwd=folder, env=env, capture_output=True, text=True,
                timeout=TIME_LIMIT, stdin=subprocess.DEVNULL,
            )  # fmt: skip
        except subprocess.TimeoutExpired:
            return -1, f"still running after {TIME_LIMIT} s, and stopped"
        return done.returncode, (done.stdout + done.stderr).rstrip("\n")
    # stdin a terminal, with the answers typed into it; stdout and stderr stay pipes
    controller, user = _open_terminal()
    attrs = termios.tcgetattr(user)
    attrs[3] &= ~termios.ECHO
    termios.tcsetattr(user, termios.TCSANOW, attrs)
    try:
        started = subprocess.Popen(
            script, cwd=folder, env=env, stdin=user, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        os.write(controller, "".join(answer + "\n" for answer in block.answers).encode("utf-8"))
        try:
            out, err = started.communicate(timeout=TIME_LIMIT)
        except subprocess.TimeoutExpired:
            started.kill()
            out, err = started.communicate()
    finally:
        os.close(controller)
        os.close(user)
    printed = (out + err).decode("utf-8", "replace").replace("\r\n", "\n")
    return started.returncode, printed.rstrip("\n")


def line_holds(shown: str, printed: str, varies: bool) -> bool:
    """One shown line against the line printed: equal, or, under ``varies``, equal once each
    ``…`` is given a path, a time, an id or a version to stand for."""
    if shown == printed:
        return True
    if not varies or "…" not in shown:
        return False
    found = re.fullmatch("(.+?)".join(re.escape(part) for part in shown.split("…")), printed)
    if found is None:
        return False
    return all(VARIES.fullmatch(group.strip().rstrip(".,;:)")) for group in found.groups())


def holds(block: Block, code: int, printed: str) -> bool:
    """An output is the whole of what was printed; an excerpt a run of whole lines of it;
    both with the exit code the mark names."""
    if code != block.code:
        return False
    shown, got = block.body.split("\n"), printed.split("\n")

    def same(lines: Sequence[str]) -> bool:
        return len(lines) == len(shown) and all(
            line_holds(a, b, block.varies) for a, b in zip(shown, lines, strict=True)
        )

    if block.kind == "output":
        return same(got)
    return any(same(got[at : at + len(shown)]) for at in range(len(got) - len(shown) + 1))


# ---------- checking a page ----------


@dataclass
class Checked:
    """What the check found on one page."""

    faults: list[tuple[int, str]]
    skips: list[tuple[int, str]]
    held: int = 0


@dataclass(frozen=True)
class Shown:
    """One output or excerpt block of a page that was run, with what it was held against: the
    text of the command block above it, the exit code that gave, what it printed, and that
    block."""

    block: Block
    command: str
    code: int
    printed: str
    ran: Block = field(compare=False, default=Block("command", 0, ""))


#: A path a page writes into one of the two folders, and the first name after the folder.
_NAMED = re.compile(r"(?<![\w-])(tests/fixtures|examples)/([A-Za-z0-9_.-]+)")
_OTHERWISE = {
    "tests/fixtures": re.compile(r"(?<![\w-])fixtures(?![\w-])"),
    "examples": re.compile(r"(?<![\w-])examples(?![\w-])"),
}


def _top(where: str, name: str) -> str | None:
    """``name`` as a file or folder at the top of that folder of the checkout, or None; a full
    stop that ends a sentence is not part of a name."""
    for candidate in (name, name.rstrip(".")):
        if candidate.strip(".") and (COPIED[where] / candidate).exists():
            return candidate
    return None


def named(text: str) -> dict[str, set[str]]:
    """For each of the two folders, the names at its top that a page writes a path to,
    anywhere on the page."""
    out: dict[str, set[str]] = {where: set() for where in COPIED}
    for where, name in _NAMED.findall(text):
        top = _top(where, name)
        if top is not None:
            out[where].add(top)
    return out


def whole(blocks: Sequence[Block]) -> set[str]:
    """The folders of the two a page gets whole: those a block it runs writes any other way
    than by a path to a name at the folder's top."""
    run_text = "\n".join(block.body for block in blocks if block.kind == "command")
    rest = _NAMED.sub(lambda m: "" if _top(m.group(1), m.group(2)) else m.group(0), run_text)
    return {where for where, word in _OTHERWISE.items() if word.search(rest)}


def lay_out(root: Path, text: str) -> None:
    """``root`` laid out as a clone's root for the page whose text this is: what the page
    names of ``tests/fixtures`` and ``examples`` (the module's opening gives the rule), copied,
    and an empty ``docs/figures``."""
    names, wholes = named(text), whole(parse(text)[0])
    for where, source in COPIED.items():
        if not source.is_dir():
            continue
        target = root / where
        inner = ("__pycache__",) if source == EXAMPLES else ()
        if where in wholes:
            left = inner if source == EXAMPLES else tuple(set(NOT_COPIED) - names[where])
            shutil.copytree(source, target, ignore=shutil.ignore_patterns(*left))
            continue
        for name in sorted(names[where]):
            if (source / name).is_dir():
                shutil.copytree(source / name, target / name, ignore=shutil.ignore_patterns(*inner))
            else:
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / name, target / name)
    (root / "docs" / "figures").mkdir(parents=True)


def scratch(tmp: Path, text: str) -> tuple[Path, Path]:
    """A folder laid out as a clone's root for the page whose text this is, and a home
    folder, both under ``tmp``."""
    root, home = tmp / "clone", tmp / "home"
    lay_out(root, text)
    home.mkdir()
    return root, home


def run_page(
    page: Path, tmp: Path, captures: Captures, extra: Mapping[str, str] | None = None
) -> tuple[Checked, list[Shown]]:
    """The page run in a scratch folder under ``tmp`` (``clone`` for its commands, ``home``
    for their home), which is left as the commands left it: what the check found, and each
    output and excerpt that stands under a command that was run, with what that command gave.
    ``extra`` is added to the environment of every block (``environment``)."""
    text = page.read_text(encoding="utf-8")
    blocks, faults = parse(text)
    found = Checked(faults=list(faults), skips=[])
    shown: list[Shown] = []
    root, home = scratch(tmp, text)
    above: Block | None = None  # the last command or skipped block
    ran: tuple[int, str] | None = None  # what the last command gave, if it was run
    for block in blocks:
        if block.kind == "unmarked":
            found.faults.append((block.line, "a fenced block with no mark above it"))
        elif block.kind == "skip":
            above, ran = block, None
            found.skips.append((block.line, block.reason))
            for command in commands(block):
                if could_run(command):
                    found.faults.append(
                        (
                            block.line,
                            f"a command that could be run is skipped: {' '.join(command)}",
                        )
                    )
        elif block.kind == "command":
            above, ran = block, None
            asked = [w for command in commands(block) for w in command if w.startswith(ADDRESSES)]
            if block.pull and not asked:
                found.faults.append((block.line, "marked pull, and it asks no service"))
            elif asked and not block.pull:
                found.faults.append(
                    (
                        block.line,
                        f"asks {', '.join(asked)} in a block not marked pull; it was not run",
                    )
                )
                continue
            ran = run(
                block, root, environment(home, captures.addresses() if block.pull else None, extra)
            )
        elif block.kind in ("output", "excerpt"):
            found.held += _shown(block, above, ran, found.faults)
            if above is not None and above.kind == "command" and ran is not None:
                shown.append(Shown(block, above.body, ran[0], ran[1], above))
    return found, shown


def check_page(page: Path, captures: Captures) -> Checked:
    with tempfile.TemporaryDirectory(prefix="poisson-trace-docs-check-") as tmp:
        return run_page(page, Path(tmp), captures)[0]


def _shown(
    block: Block, above: Block | None, ran: tuple[int, str] | None, faults: list[tuple[int, str]]
) -> int:
    """Hold one output or excerpt against what the command above it gave: 1 when it holds,
    0 with a fault added when it does not."""
    kind = f"an {block.kind}" if block.kind[0] in "aeiou" else f"a {block.kind}"
    if above is None or above.kind != "command":
        faults.append((block.line, f"{kind} with no command run above it"))
        return 0
    if ran is None:
        faults.append((block.line, f"{kind} under a command that was not run"))
        return 0
    lines = block.body.split("\n")
    if block.varies and not any("…" in line for line in lines):
        faults.append((block.line, "marked varies, and no line of it holds a …"))
        return 0
    if block.varies and any(line.strip() == "…" for line in lines):
        faults.append(
            (block.line, "marked varies, with a line that is … alone, which stands for anything")
        )
        return 0
    if holds(block, *ran):
        return 1
    code, printed = ran
    faults.append(
        (
            block.line,
            f"this {block.kind} (exit={block.code}) does not hold; "
            f"the command gave exit {code} and printed:\n{printed}",
        )
    )
    return 0


def default_pages() -> list[Path]:
    docs = sorted(p for p in (CHECKOUT / "docs").rglob("*.md") if p.name not in STANDARDS)
    return [p for p in (CHECKOUT / "README.md", CHECKOUT / "CONTRIBUTING.md", *docs) if p.is_file()]


def name_of(page: Path) -> str:
    """How a page is named in what the check prints: by its path in the checkout, else from
    the folder the check was started in, else by its file name."""
    for base in (CHECKOUT, Path.cwd().resolve()):
        if page.is_relative_to(base):
            return page.relative_to(base).as_posix()
    return page.name


def listing(skipped: Sequence[str]) -> Iterator[str]:
    for entry in skipped:
        where, _, reason = entry.partition(": ")
        yield f"- `{where}`: {reason}\n"


def _n(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="docs_check.py",
        description="Check that every command a page shows runs as the page shows it.",
    )
    parser.add_argument(
        "--summary", metavar="FILE", help="append the count and every skipped block to FILE"
    )
    parser.add_argument(
        "pages",
        nargs="*",
        metavar="PAGE",
        help="the pages to check (default: the README, CONTRIBUTING.md and docs/)",
    )
    args = parser.parse_args(argv)
    pages = [Path(p).resolve() for p in args.pages] or default_pages()
    missing = [str(page) for page in pages if not page.is_file()]
    if missing:
        print(f"error: no such page: {', '.join(missing)}", file=sys.stderr)
        return 1
    failed, held, skipped = 0, 0, []
    captures = Captures()
    try:
        for page in pages:
            name = name_of(page)
            found = check_page(page, captures)
            held += found.held
            for line, what in sorted(found.faults):
                failed += 1
                print(f"{name}:{line}: {what}", file=sys.stderr)
            for line, reason in found.skips:
                skipped.append(f"{name}:{line}: {reason}")
                print(f"skipped  {name}:{line}: {reason}")
    finally:
        captures.close()
    count = f"{_n(held, 'block')} held on {_n(len(pages), 'page')}, {len(skipped)} skipped"
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as out:
            out.write(f"\n### Docs check: {count}\n\n")
            out.writelines(listing(skipped))
            if failed:
                out.write(f"\n{_n(failed, 'block')} did not hold.\n")
    if failed:
        print(
            f"error: {_n(failed, 'block')} of {_n(len(pages), 'page')} did not hold",
            file=sys.stderr,
        )
        return 1
    print(f"ok  {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
