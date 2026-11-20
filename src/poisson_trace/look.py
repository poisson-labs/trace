"""The command-line look both commands keep, as ``docs/cli-look.md`` writes it: the exit codes,
the ``error:`` and ``stopped`` lines, the version line, counts with thousands separators, the
ASCII fallback, a reader that has gone away, the errors log, an argument parser that reads
options before or after the verb and refuses abbreviations, and the switch between the two
renderings of a result (rule 16): plain, the contract, and pretty, drawn on a terminal.

Standard library only: the pretty rendering's styles and tables are ``_pretty``'s, the one
module that imports Rich, and this module imports it only once the switch has chosen pretty.
Every line a command prints goes through ``out`` or ``err``, which hand it to the rendering
chosen for the process; on a pipe the text is written as it is.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import importlib
import importlib.metadata
import os
import re
import shlex
import shutil
import sys
import traceback
import unicodedata
from collections.abc import Callable, Collection, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn, Protocol, TextIO

# the exit codes (docs/cli-look.md); 4 belongs to a check the user asks for (doctor)
DONE = 0
REFUSED = 1
USAGE = 2
FAILED = 3
CHECK_FAILED = 4
INTERRUPTED = 130

def _declared_prove() -> str:
    """The oldest Prove this package reads: the ``poisson-prove>=X`` that ``pyproject.toml``
    declares, read back from the installed package's own metadata, so the floor is written in one
    place and what Trace checks for cannot drift from what it declares. A requirement of any
    other shape (an exact pin, a range with a cap) is not read as a floor, and nothing is guessed
    in its place."""
    try:
        requires = importlib.metadata.requires("poisson-trace") or []
    except importlib.metadata.PackageNotFoundError:
        requires = []
    floor = re.compile(r"\s*poisson[-_.]prove\s*>=\s*(\d+(?:\.\d+)*)\s*(?:;|$)", re.IGNORECASE)
    for requirement in requires:
        declared = floor.match(requirement)
        if declared:
            return declared.group(1)
    raise RuntimeError(
        "the installed poisson-trace does not state the oldest poisson-prove it reads (the "
        "metadata pip wrote when it installed this package has no poisson-prove>=VERSION "
        "requirement); install it again with pip"
    )


# The Prove this package reads: poisson-prove, imported as poisson_prove, from PyPI, at the floor
# pyproject.toml declares or any later version. PROVE_VERSION is that floor.
PROVE_VERSION = _declared_prove()
#: How a sentence names the versions of Prove this package reads.
PROVE_READ = f"version {PROVE_VERSION} or later"
# quoted, since a shell reads an unquoted > as "send the output to a file"
INSTALL_PROVE = f'pip install "poisson-prove>={PROVE_VERSION}"'
NOTHING_WRITTEN = "stopped  interrupted; nothing was written"


class _Said(Exception):
    """One sentence, and under it the commands that move the user on, if there are any: each
    printed on its own ``  next:`` line (the look's rule 4)."""

    def __init__(self, sentence: str, *nexts: str) -> None:
        super().__init__(sentence)
        self.nexts = nexts


class Usage(_Said):
    """The command line is wrong: one ``error:`` line, exit 2."""


class Refused(_Said):
    """A refusal: one ``error:`` line, exit 1, nothing written."""


class Failed(Exception):
    """A failure after work started: one ``error:`` line, exit 3."""


class Interrupted(KeyboardInterrupt):
    """Ctrl-C inside work that may have written something: carries the ``stopped`` line that
    says what was left behind, worked out where the writing happened, for the command line
    to print (the look's rule 5)."""

    def __init__(self, line: str) -> None:
        super().__init__(line)
        self.line = line


# ---------- numbers ----------


def count(n: float) -> str:
    """A count with thousands separators: ``10,496``. A whole number held as a float prints
    as the whole number."""
    if isinstance(n, int):
        return f"{n:,}"
    return f"{int(n):,}" if float(n).is_integer() else f"{n:,}"


def shown(value: str) -> str:
    """A value the user gave, as an error line shows it: as it is, or ``""`` when empty."""
    return value if value else '""'


# ---------- writing ----------

# The glyphs the reports print, spelt in ASCII for a stream that cannot encode them. Each is
# one word for one word, so a line keeps its words and its numbers in order.
_SPELT = {
    "·": "-",
    "–": "-",
    "—": "-",
    "−": "-",
    "×": "x",
    "α": "alpha",
    "χ": "chi",
    "κ": "kappa",
    "²": "^2",
    "±": "+/-",
}


def _spelt(ch: str) -> str:
    """A report glyph in its ASCII spelling; any other character, such as one in a name the
    user chose, as an escape, so that it never reads as another name."""
    return _SPELT.get(ch) or ch.encode("ascii", "backslashreplace").decode("ascii")


def fit(text: str, encoding: str | None) -> str:
    """The text as a stream in ``encoding`` can write it: as it is when it can, else every
    character it cannot encode spelt in ASCII."""
    if not encoding or text.isascii() or _encodes(text, encoding):
        return text
    return "".join(ch if ch.isascii() or _encodes(ch, encoding) else _spelt(ch) for ch in text)


def _encodes(text: str, encoding: str) -> bool:
    """Whether the encoding can write the text; an encoding Python does not know is left to
    the stream."""
    try:
        text.encode(encoding)
    except UnicodeEncodeError:
        return False
    except LookupError:
        return True
    return True


def _write(stream: TextIO, text: str) -> None:
    """Write and flush. A reader that has gone away (a closed pipe) ends the output quietly:
    the stream is pointed at the null device, so nothing more fails, then or at exit. A stream
    that is closed (None) takes nothing."""
    if stream is None:
        return
    try:
        stream.write(fit(text, getattr(stream, "encoding", None)))
        stream.flush()
    except BrokenPipeError:
        with contextlib.suppress(AttributeError, OSError, ValueError):
            null = os.open(os.devnull, os.O_WRONLY)
            os.dup2(null, stream.fileno())
            os.close(null)


def out(text: str) -> None:
    """A piece of stdout. On a pipe it is written as it is; on a terminal it goes through the
    rendering the switch chose (``_Rendering``): plain, wrapped at the terminal's width, or
    pretty."""
    if _rendering is None:
        _write(sys.stdout, text)
    else:
        _rendering.out(text)


def err(text: str) -> None:
    """A piece of stderr: as it is on a pipe and in plain; its ``error:``, ``note:`` and
    ``next:`` words in their styles in pretty. Never wrapped: each problem is one line."""
    if _rendering is None:
        _write(sys.stderr, text)
    else:
        _rendering.err(text)


def _visible(ch: str) -> str:
    """A character of an error line as a terminal shows it: a control character a user typed
    (an escape, a bell) written as its escape, never acted on; a tab as itself."""
    if ch != "\t" and unicodedata.category(ch) in ("Cc", "Cs"):
        return ch.encode("unicode_escape", "backslashreplace").decode("ascii")
    return ch


def error(sentence: str, nexts: Sequence[str] = ()) -> None:
    """``error: <sentence>`` on stderr, as one line, and each command to run next on its own
    ``  next:`` line under it."""
    # one line: a line break inside it (a value the user gave, a wrapped string) reads as a
    # space; every other space is kept, so a name with two spaces is shown as it is
    line = " ".join(sentence.splitlines())
    err("error: " + "".join(_visible(ch) for ch in line) + "\n")
    for command in nexts:
        err(f"  next: {command}\n")


# ---------- questions ----------


class Unanswered(Refused):
    """Stdin ended before a question was answered."""


def ask(question: str) -> str:
    """Print ``question`` on stderr and read one line of answer from stdin, trimmed. Stdin that
    ends before a line is a refusal."""
    err(question + " ")
    line = sys.stdin.readline() if sys.stdin is not None else ""
    if not line:
        err("\n")
        raise Unanswered("stdin ended before the question was answered; nothing was written")
    return line.strip()


# ---------- commands a user can copy ----------

# the characters a shell reads as themselves in a word
_PLAIN = re.compile(r"[A-Za-z0-9_./:@%+=,-]+")


def word(text: str) -> str:
    """``text`` as one word a POSIX shell (sh, bash, zsh) reads back exactly: bare when every
    character is read as itself, else in double quotes with the four characters a shell reads
    inside them (``"``, ``\\``, ``$`` and the backquote) escaped. A ``!``, which an interactive
    shell may expand even inside double quotes, is written outside them, escaped."""
    if _PLAIN.fullmatch(text) and not text.startswith(("-", "=")):
        return text
    parts = []
    for i, piece in enumerate(text.split("!")):
        if i:
            parts.append("\\!")
        if piece:
            parts.append('"' + re.sub(r'(["\\$`])', r"\\\1", piece) + '"')
    return "".join(parts) or '""'


def option(flag: str, value: str) -> str:
    """An option and its value for a command line: joined by ``=`` when the value opens with a
    dash, which a command line would otherwise read as an option of its own."""
    return f"{flag}={word(value)}" if value.startswith("-") else f"{flag} {word(value)}"


def command(*words: str) -> str:
    """A command line from words already quoted with ``word`` where they need it."""
    return " ".join(words)


def why(e: BaseException) -> str:
    """What a library's exception can tell a user: the system's own words for a failed file
    operation, else the exception's type, and never its text."""
    if isinstance(e, OSError) and e.strerror:
        return e.strerror
    return type(e).__name__


# ---------- the version line and the Prove check ----------


def version_line() -> str:
    """``poisson-trace 0.1.0 (poisson-prove X.Y.Z, Python 3.11.7)``: what is installed."""
    import poisson_trace

    try:
        import poisson_prove
    except ImportError:
        prove = "poisson-prove not installed"
    else:
        prove = "poisson-prove " + (_found(poisson_prove) or "of no version")
    python = ".".join(str(n) for n in sys.version_info[:3])
    return f"poisson-trace {poisson_trace.__version__} ({prove}, Python {python})\n"


# a version as a package states one: its release's numbers, then whatever follows them
_VERSION = re.compile(r"(\d+(?:\.\d+)*)(.*)", re.DOTALL)
# what follows a release's numbers when the version comes before that release: a pre-release
# (1.2.0rc1, 1.2.0a1, 1.2.0-beta.2) or a development release (1.2.0.dev1)
_BEFORE_ITS_RELEASE = re.compile(r"[-_.]?(?:a|b|c|rc|alpha|beta|pre|preview|dev)(?![a-z])", re.I)


def _at_or_above(found: str, floor: str) -> bool:
    """Whether the version ``found`` is ``floor`` or a later one, as pip orders versions.
    ``floor`` is a release's numbers alone (``1.2.0``). The numbers are compared part by part, a
    missing part counting as zero, so 1.10.0 is above 1.2.0, and 1.2 is 1.2.0. Where they are
    equal, a pre-release or a development release of the floor is below it, and a post-release
    is not. A version that does not open with numbers is not at or above any floor."""
    read = _VERSION.fullmatch(found.strip())
    if read is None:
        return False
    mine = [int(n) for n in read.group(1).split(".")]
    least = [int(n) for n in floor.split(".")]
    width = max(len(mine), len(least))
    mine += [0] * (width - len(mine))
    least += [0] * (width - len(least))
    if mine != least:
        return mine > least
    return _BEFORE_ITS_RELEASE.match(read.group(2)) is None


def prove_refusal(does: str) -> str | None:
    """The refusal when Prove is not importable at a version this package reads (the floor or
    a later one), else None. ``does`` is what the command does through Prove, as the sentence's
    opening words. The line that installs it is the command to run next, under the sentence, and
    not in it."""
    wanted = f"{does} through Prove (the poisson-prove package, {PROVE_READ})"
    try:
        import poisson_prove
    except ImportError:
        return f"{wanted}, which is not installed here"
    found = _found(poisson_prove)
    if found is None:
        return f"{wanted} and found a poisson-prove that states no version"
    if not _at_or_above(found, PROVE_VERSION):
        return f"{wanted} and found poisson-prove {found}"
    gone = prove_missing()
    if gone:
        return f"{wanted} and found poisson-prove {found}, which has no {listed(gone)}"
    return None


# Every module of Prove this package imports, and every name it imports from each, wherever in
# the package it imports them. The floor says which versions are read; a later one that drops or
# renames one of these is refused by the same check, before any command imports it.
PROVE_IMPORTS: dict[str, tuple[str, ...]] = {
    "poisson_prove.steps": ("declaration_check",),
    "poisson_prove.store": ("EpisodeRecord", "RunManifest", "RunTally", "Store", "config_hash"),
    "poisson_prove.trace": ("CONTENT_KEYS", "KINDS", "OBSERVATION_KEYS", "Trace", "from_otel"),
}


def prove_missing() -> list[str]:
    """What of ``PROVE_IMPORTS`` the Prove this interpreter imports does not have, dotted and in
    order: a module that does not import is named as the module, not as its names. Asked only
    once Prove itself imports at or above the floor."""
    gone: list[str] = []
    for module, names in PROVE_IMPORTS.items():
        try:
            held = importlib.import_module(module)
        except ImportError:
            gone.append(module)
            continue
        gone.extend(f"{module}.{name}" for name in names if not hasattr(held, name))
    return sorted(gone)


def prove_nexts() -> tuple[str, ...]:
    """The commands under ``prove_refusal``'s sentence: the floor's install line, unless the
    Prove found is at or above the floor and lacks what Trace imports, where pip holds that line
    met and installing it would move nothing."""
    found = prove_found()
    if found is not None and at_or_above_the_floor(found) and prove_missing():
        return ()
    return (INSTALL_PROVE,)


def at_or_above_the_floor(found: str) -> bool:
    """Whether the version ``found`` is one this package reads by its number alone."""
    return _at_or_above(found, PROVE_VERSION)


def listed(items: Sequence[str]) -> str:
    """``A``, ``A and B``, ``A, B and C``: the items as given."""
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def prove_found() -> str | None:
    """The version of Prove this interpreter imports, or None when there is none."""
    try:
        import poisson_prove
    except ImportError:
        return None
    return _found(poisson_prove)


def _found(module: Any) -> str | None:
    """The version a module states, or None when it states none as text."""
    found = getattr(module, "__version__", None)
    return found if isinstance(found, str) and found else None


# ---------- the errors log ----------


def errors_log_path() -> Path:
    """The log under the home folder; a home that is not an absolute path has no log."""
    home = Path.home()
    if not home.is_absolute():
        raise RuntimeError("no home folder")
    return home / ".cache" / "poisson-trace" / "errors.log"


def _shown(path: Path) -> str:
    """The path as a user reads it: under the home folder, from ``~``."""
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except (ValueError, RuntimeError):
        return str(path)


def _append_errors_log(path: Path, entry: str) -> bool:
    """Append one entry to the log, never replacing what it holds; False when it cannot be
    written."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # a value the command line could not read as text is kept escaped, never refused
        with open(path, "a", encoding="utf-8", errors="backslashreplace") as errors_log:
            errors_log.write(entry)
    except OSError:
        return False
    return True


# ---------- the two renderings (docs/cli-look.md, rule 16) ----------

# The four meanings, mapped to Trace's verdict words: green, the command did what was asked;
# yellow, it stopped short or cannot say; red, an error or a failed check. A verdict that is a
# result and neither good nor bad (different, plan) is bold with no colour.
GREEN_WORDS = ("ok", "done")
YELLOW_WORDS = (
    "stopped",
    "refused",
    "too small to tell",
    "no significant difference",
    "no control",
    "unconfirmed",  # a measure's call the timeouts leave unconfirmed: it cannot say
)
RED_WORDS = ("not ready", "not whole", "not valid")


def meaning(word: str) -> str:
    """The style a verdict word is drawn in: ``green``, ``yellow``, ``red`` or ``bold``."""
    if word in GREEN_WORDS:
        return "green"
    if word in YELLOW_WORDS:
        return "yellow"
    if word in RED_WORDS:
        return "red"
    return "bold"


def table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """The plain face of a table: the markdown table the reports print, ``| a | b |``, then
    ``|---|---|``, then one ``| … |`` line a row, each line ended. The pretty face is
    ``_pretty.table``; every table goes through both, so a new table gets every rule."""
    lines = ["| " + " | ".join(str(h) for h in header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "".join(line + "\n" for line in lines)


#: The first line a verb prints: a lowercase verdict word or phrase, two spaces, one sentence.
VERDICT_LINE = re.compile(r"^([a-z][a-z ]*?)  (\S.*)$")
#: A command printed for the user to copy opens with the command's name and a verb or an option,
#: or with pip install.
_OPENS = (
    r"(?:(?:poisson-trace|python -m poisson_trace)\s+"
    r"(?:init|runs|name|where|compare|fix-check|changes|doctor|import|--?[a-z])"
    r"|pip install\s)"
)
_NEXT = re.compile(r"^(\s*)(next:)( .*)$")
_COMMAND_LINE = re.compile(rf"^\s*{_OPENS}")
_DETAIL = re.compile(r"^(\s{2,})(\S+(?: \S+)?)(\s{2,})(\S.*)$")
_DETAIL_COMMAND = re.compile(rf"^\s{{2,}}\S+(?: \S+)?\s{{2,}}{_OPENS}")
_SPAN = re.compile(rf"`{_OPENS}[^`]*`")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_RULE_ROW = re.compile(r"^\s*\|(?:\s*:?-+:?\s*\|)+\s*$")
_HEADING = re.compile(r"^(\s*)#{1,6} (\S.*)$")
_BOLD = re.compile(r"^(\s*)\*\*(\S.*?)\*\*$")
_PROBLEM = re.compile(r"^(\s*)(error:|note:)( .*|)$")


def terminal_width() -> int:
    """The terminal's width in columns, from ``COLUMNS`` or stdout's terminal; 80 when neither
    says."""
    return max(20, shutil.get_terminal_size((80, 24)).columns)


def wrap(line: str, width: int, hang: int, whole: Collection[str] = ()) -> list[str]:
    """``line`` as rows no wider than ``width`` where its words allow: broken at spaces, every
    run of spaces inside a row kept, the first row at the line's own indent and every row after
    it indented by ``hang`` (deeper than the line, a hanging indent). A word is never broken,
    and a span in ``whole`` (a command in backquotes) is one word. A line that fits is itself."""
    if len(line) <= width:
        return [line]
    indent = len(line) - len(line.lstrip(" "))
    if hang <= indent or hang >= width // 2:
        hang = indent + 2
    rest = line[indent:]
    words: list[tuple[str, str]] = []  # each word with the spaces that follow it
    at = 0
    while at < len(rest):
        span = next((s for s in whole if rest.startswith(s, at)), None)
        end = at + len(span) if span else _word_end(rest, at)
        gap = end
        while gap < len(rest) and rest[gap] == " ":
            gap += 1
        words.append((rest[at:end], rest[end:gap]))
        at = gap
    rows: list[str] = []
    row = " " * indent
    first = True
    for word, spaces in words:
        if not first and len(row) + len(word) > width:
            rows.append(row.rstrip(" "))
            row = " " * hang
        row += word + spaces
        first = False
    rows.append(row.rstrip(" ") if rows else row)
    return rows


def _word_end(text: str, at: int) -> int:
    end = text.find(" ", at)
    return len(text) if end < 0 else end


def _holds_command(line: str, continued: bool) -> bool:
    """Whether the line carries a command to copy, which is never broken: a ``next:`` line, a
    command line or the line a command continues onto, a ``label  command`` detail line, or a
    command in backquotes."""
    return bool(
        (continued and line.strip())
        or _NEXT.match(line)
        or _COMMAND_LINE.match(line)
        or _DETAIL_COMMAND.match(line)
        or _SPAN.search(line)
    )


def _take_plain(argv: Sequence[str]) -> tuple[list[str], bool]:
    """The command line without ``--plain``, and whether it was given, anywhere before ``--``."""
    kept: list[str] = []
    plain = False
    for i, word in enumerate(argv):
        if word == "--":
            kept += argv[i:]
            break
        if word == "--plain":
            plain = True
        else:
            kept.append(word)
    return kept, plain


def _asked_json(argv: Sequence[str]) -> bool:
    for word in argv:
        if word == "--":
            return False
        if word == "--json":
            return True
    return False


def _is_terminal(stream: Any) -> bool:
    try:
        return bool(stream is not None and stream.isatty())
    except (AttributeError, ValueError, OSError):
        return False


def opens_app() -> bool:
    """Whether the bare command opens the terminal app: stdin and stdout
    are terminals (stderr may be a pipe), ``CI`` is unset (any value, the empty one included,
    counts as set) and ``TERM`` is not ``dumb``. ``--plain`` is the caller's to check."""
    return (
        _is_terminal(sys.stdin)
        and _is_terminal(sys.stdout)
        and "CI" not in os.environ
        and os.environ.get("TERM") != "dumb"
    )


def _utf8(stream: Any) -> bool:
    import codecs

    name = getattr(stream, "encoding", None)
    if not name:
        return False
    try:
        return codecs.lookup(name).name == "utf-8"
    except LookupError:
        return False


class _Pretty(Protocol):
    """What the pretty rendering module (``_pretty``) draws: a piece of text in a style, a verdict
    line, and a table for a width."""

    def style(self, text: str, meaning: str) -> str: ...

    def verdict(self, word: str, sentence: str) -> str: ...

    def table(self, header: Sequence[str], rows: Sequence[Sequence[str]], *, width: int) -> str: ...


def _choose(plain: bool, as_json: bool) -> _Rendering | None:
    """The rendering for this process, or None for a pipe's (text as it is). Pretty runs only
    when stdout and stderr are both terminals, ``NO_COLOR`` is unset or empty, ``CI`` is unset,
    ``TERM`` is not ``dumb``, stdout is UTF-8, and neither ``--json`` nor ``--plain`` was given;
    anything else on a terminal is plain, wrapped at the terminal's width. ``--json`` is one
    document, as on a pipe. A Trace that cannot import Rich prints plain and says nothing."""
    if as_json or not _is_terminal(sys.stdout):
        return None
    pretty = (
        not plain
        and _is_terminal(sys.stderr)
        and os.environ.get("NO_COLOR", "") == ""
        and "CI" not in os.environ
        and os.environ.get("TERM") != "dumb"
        and _utf8(sys.stdout)
    )
    styles: _Pretty | None = None
    if pretty:
        try:
            from poisson_trace import _pretty

            styles = _pretty
        except ImportError:
            styles = None
    return _Rendering(terminal_width(), styles)


class _Rendering:
    """One process's rendering on a terminal: plain, wrapping stdout's long lines at the width
    with a hanging indent (``pretty`` None), or pretty, the same lines drawn through
    ``_pretty``: the verdict word in its meaning, headings bold, a detail line's label and a
    ``next:`` dim, the report's tables aligned or folded, ``error:`` red and ``note:`` yellow on
    stderr. What each line is, is read from its shape: the first stdout line is the verdict
    line; a line holding a command is never broken; a table's rows are gathered until the line
    after them; stderr is never wrapped, each problem one line."""

    def __init__(self, width: int, pretty: _Pretty | None) -> None:
        self.width = width
        self.pretty = pretty
        self._out = ""  # the part of a stdout line not yet ended
        self._err = ""
        self._lines = 0  # stdout lines rendered
        self._detail = False  # between the verdict line and the first blank line
        self._continued = False  # the last stdout line was a command ending in a backslash
        self._table: list[str] = []  # the rows of a table not yet drawn
        self._err_mid = False  # stderr is in the middle of a line written as it was

    # -- stdout --

    def out(self, text: str) -> None:
        self._out += text
        while "\n" in self._out:
            line, self._out = self._out.split("\n", 1)
            self._line(line)

    def _line(self, line: str) -> None:
        if _TABLE_ROW.match(line) and (self.pretty is not None):
            self._table.append(line)
            return
        self._draw_table()
        n = self._lines
        self._lines += 1
        if not line.strip():
            self._detail = False
            self._continued = False
            _write(sys.stdout, line + "\n")
            return
        if n == 0:
            m = VERDICT_LINE.match(line)
            if m:
                self._detail = True
            if self.pretty is not None and m:
                _write(sys.stdout, self.pretty.verdict(m.group(1), m.group(2)) + "\n")
            else:
                _write(sys.stdout, line + "\n")
            return
        if self.pretty is None:
            self._plain_line(line)
        else:
            self._pretty_line(line)

    def _plain_line(self, line: str) -> None:
        if _holds_command(line, self._continued) or line.lstrip().startswith("|"):
            rows = [line]
        else:
            rows = wrap(line, self.width, self._hang(line))
        self._continued = line.rstrip().endswith("\\") and _holds_command(line, self._continued)
        _write(sys.stdout, "".join(r + "\n" for r in rows))

    def _hang(self, line: str) -> int:
        """Where a wrapped line's rows after the first start: under a detail line's value, else
        two deeper than the line."""
        indent = len(line) - len(line.lstrip(" "))
        if self._detail:
            m = _DETAIL.match(line)
            if m:
                return len(m.group(1)) + len(m.group(2)) + len(m.group(3))
        return indent + 2

    def _pretty_line(self, line: str) -> None:
        assert self.pretty is not None
        style = self.pretty.style
        continued = self._continued
        self._continued = line.rstrip().endswith("\\") and _holds_command(line, continued)
        m = _NEXT.match(line)
        if m:
            _write(sys.stdout, m.group(1) + style(m.group(2), "dim") + m.group(3) + "\n")
            return
        if (continued and line.strip()) or _COMMAND_LINE.match(line):
            _write(sys.stdout, line + "\n")
            return
        d = _DETAIL.match(line) if self._detail else None
        if d:
            label = style(d.group(2), "dim")
            if _DETAIL_COMMAND.match(line):
                rows = [line]
            else:
                rows = wrap(line, self.width, self._hang(line), _SPAN.findall(line))
            rows[0] = d.group(1) + label + rows[0][len(d.group(1)) + len(d.group(2)) :]
            _write(sys.stdout, "".join(r + "\n" for r in rows))
            return
        h = _HEADING.match(line) or _BOLD.match(line)
        if h:
            text = h.group(1) + h.group(2)
            rows = wrap(text, self.width, len(h.group(1)) + 2, _SPAN.findall(text))
            _write(sys.stdout, "".join(_styled_row(r, "bold", style) + "\n" for r in rows))
            return
        rows = wrap(line, self.width, self._hang(line), _SPAN.findall(line))
        _write(sys.stdout, "".join(r + "\n" for r in rows))

    def _draw_table(self) -> None:
        """The gathered rows as the pretty table, or as they are when they are not one table."""
        rows, self._table = self._table, []
        if not rows:
            return
        self._lines += len(rows)
        self._detail = False
        cells = [_cells(r) for r in rows if not _RULE_ROW.match(r)]
        if len(rows) < 2 or not cells or len({len(c) for c in cells}) != 1:
            _write(sys.stdout, "".join(r + "\n" for r in rows))
            return
        indent = len(rows[0]) - len(rows[0].lstrip(" "))
        assert self.pretty is not None
        drawn = self.pretty.table(cells[0], cells[1:], width=self.width - indent)
        if indent:
            drawn = "".join(" " * indent + r + "\n" for r in drawn.split("\n") if r)
        _write(sys.stdout, drawn)

    # -- stderr --

    def err(self, text: str) -> None:
        self._flush_out()
        if self.pretty is None:
            _write(sys.stderr, text)
            return
        self._err += text
        while "\n" in self._err:
            line, self._err = self._err.split("\n", 1)
            if self._err_mid:
                _write(sys.stderr, line + "\n")
                self._err_mid = False
            else:
                _write(sys.stderr, self._err_line(line) + "\n")
        if self._err:
            # a question, written as it is up to its answer
            _write(sys.stderr, self._err)
            self._err = ""
            self._err_mid = True

    def _err_line(self, line: str) -> str:
        assert self.pretty is not None
        style = self.pretty.style
        m = _PROBLEM.match(line)
        if m:
            colour = "red" if m.group(2) == "error:" else "yellow"
            return m.group(1) + style(m.group(2), colour) + m.group(3)
        m = _NEXT.match(line)
        if m:
            return m.group(1) + style(m.group(2), "dim") + m.group(3)
        return line

    # -- the end --

    def _flush_out(self) -> None:
        """What stdout holds: a table not yet drawn and a line not yet ended."""
        if self._out:
            line, self._out = self._out, ""
            self._line(line)
            self._out = ""
        self._draw_table()

    def close(self) -> None:
        self._flush_out()
        if self._err:
            _write(sys.stderr, self._err)
            self._err = ""


def _styled_row(row: str, meaning_: str, style: Callable[[str, str], str]) -> str:
    lead = len(row) - len(row.lstrip(" "))
    return row[:lead] + style(row[lead:], meaning_)


def _cells(row: str) -> list[str]:
    """A markdown row's cells, a ``\\|`` inside a cell read as a pipe."""
    text = row.strip()
    text = text[1:-1] if text.startswith("|") and text.endswith("|") else text
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", text)]


_rendering: _Rendering | None = None
_depth = 0


# ---------- running a command ----------


@dataclass
class Session:
    """What a running command knows that its error lines need: whether ``--debug`` was given,
    and the line Ctrl-C prints, which a command that writes sets once it knows what it would
    leave behind."""

    tool: str
    argv: Sequence[str]
    debug: bool = False
    stopped: Callable[[], str] = field(default=lambda: NOTHING_WRITTEN)
    # under --json, the stopped line as the verb's JSON document, so that stdout stays one
    render: Callable[[str], str] | None = None
    # whether ``--plain`` was given: ``run`` takes it off the command line before the body
    # sees it, and the bare command never opens the terminal app under it
    plain: bool = False


def run(
    tool: str,
    argv: Sequence[str],
    body: Callable[[Session], int],
    refusals: tuple[type[Exception], ...] = (),
) -> int:
    """``body`` under the look's rules: a refusal is one ``error:`` line and exit 1, a wrong
    command line exit 2, a failure after work started exit 3, Ctrl-C a ``stopped`` line on
    stdout and exit 130, and anything unexpected one line naming the errors log, exit 3.

    The outermost ``run`` of a process chooses the rendering (rule 16): it takes ``--plain``,
    the tool's own option, off the command line wherever it stands before a ``--``, and decides
    between plain and pretty from the streams and the environment. The command ``import`` hands
    to the import's own ``run`` keeps the rendering already chosen."""
    global _depth, _rendering
    outer = _depth == 0
    plain = False
    if outer:
        argv, plain = _take_plain(argv)
        _rendering = _choose(plain, _asked_json(argv))
    session = Session(tool, list(argv), plain=plain)
    _depth += 1
    try:
        try:
            return body(session)
        except Usage as e:
            error(str(e), e.nexts)
            return USAGE
        except Refused as e:
            error(str(e), e.nexts)
            return REFUSED
        except refusals as e:
            error(str(e), getattr(e, "nexts", ()))
            return REFUSED
        except Failed as e:
            error(str(e))
            return FAILED
        except KeyboardInterrupt as e:
            line = e.line if isinstance(e, Interrupted) else session.stopped()
            out(line + "\n" if session.render is None else session.render(line))
            return INTERRUPTED
        except Exception as e:
            _unexpected(session, e)
            return FAILED
    finally:
        _depth -= 1
        if outer:
            if _rendering is not None:
                _rendering.close()
            _rendering = None


def _unexpected(session: Session, e: Exception) -> None:
    details = "".join(traceback.format_exception(e))
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = f"--- {stamp} {version_line()}{shlex.join([session.tool, *session.argv])}\n{details}\n"
    try:
        path = errors_log_path()
    except RuntimeError:
        kept, shown = False, "~/.cache/poisson-trace/errors.log"
    else:
        kept, shown = _append_errors_log(path, entry), _shown(path)
    failure = f"an unexpected failure inside {session.tool} ({type(e).__name__})"
    if kept:
        error(f"{failure}; the details are in {shown}")
    else:
        error(f"{failure}; the details could not be written to {shown}, so they follow")
    if session.debug or not kept:
        err("".join(f"  {line}\n" for line in details.splitlines()))


# ---------- the argument parser ----------


# a string as Python prints it: in single quotes, or in double quotes when it holds one
_LITERAL = re.compile(r"'(?:[^'\\\n]|\\.)*'" + r'|"(?:[^"\\\n]|\\.)*"')


def _literal(text: str) -> str | None:
    try:
        value = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None
    return value if isinstance(value, str) else None


def quoted(message: str) -> str:
    """A parser's message as ``Parser.error`` prints it: the quotes argparse puts around a
    value made the look's."""
    return _quotes(message)


def _quotes(message: str) -> str:
    """Argparse's message with its values in double quotes and its lists of choices bare, never
    as Python prints a string."""

    def bare(m: re.Match[str]) -> str:
        value = _literal(m.group(0))
        return m.group(0) if value is None else value

    def quoted(m: re.Match[str]) -> str:
        value = _literal(m.group(0))
        return m.group(0) if value is None else f'"{value}"'

    message = re.sub(
        r"\(choose from ([^)]*)\)",
        lambda m: "(choose from " + _LITERAL.sub(bare, m.group(1)) + ")",
        message,
    )
    return _LITERAL.sub(quoted, message)


#: The width the help is laid out at: what argparse takes on a pipe with no ``COLUMNS`` set.
HELP_WIDTH = 78


def _help_width() -> int:
    """The help's width: ``COLUMNS`` less two when it is set, as argparse reads it, else 78. The
    terminal's own width is not read, so the help's usage and options lay out the same on every
    terminal and on a pipe, and its first line reads the same everywhere."""
    columns = os.environ.get("COLUMNS")
    if columns and columns.isdigit() and int(columns) > 2:
        return int(columns) - 2
    return HELP_WIDTH


class _HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Argparse's formatter at ``_help_width``. Off a terminal the description and the examples
    keep their lines, as written. On a terminal a paragraph written as unindented lines (the
    description) is reflowed to the terminal's width, and a block with an indented line (the
    examples) keeps its lines, so a command is never broken."""

    def __init__(self, prog: str, **kwargs: Any) -> None:
        kwargs.setdefault("width", _help_width())
        super().__init__(prog, **kwargs)

    if sys.version_info < (3, 12, 7):

        def add_argument(self, action: argparse.Action) -> None:
            # Python 3.12.7 and later count a sub-command's own indent when they size the help
            # column (cpython GH-87041); 3.11 and 3.12.0 to 3.12.6 do not, which lays
            # `import --help` out differently. This is the newer rule.
            if action.help is not argparse.SUPPRESS:
                get_invocation = self._format_action_invocation
                lengths = [len(get_invocation(action)) + self._current_indent]
                for subaction in self._iter_indented_subactions(action):
                    lengths.append(len(get_invocation(subaction)) + self._current_indent)
                self._action_max_length = max(self._action_max_length, max(lengths))
                self._add_item(self._format_action, [action])

    def _fill_text(self, text: str, width: int, indent: str) -> str:
        if _rendering is None:
            return str(super()._fill_text(text, width, indent))
        import textwrap

        room = max(20, _rendering.width - len(indent))
        head = text[: len(text) - len(text.lstrip("\n"))]
        tail = text[len(text.rstrip("\n")) :]
        blocks = re.split(r"\n[ \t]*\n", text.strip("\n"))
        out = []
        for block in blocks:
            lines = block.split("\n")
            if all(line == line.lstrip(" ") for line in lines):
                out.append(
                    textwrap.fill(
                        " ".join(lines),
                        width=room,
                        initial_indent=indent,
                        subsequent_indent=indent,
                        break_long_words=False,
                        break_on_hyphens=False,
                    )
                )
            else:
                out.append("".join(indent + line + "\n" for line in lines).rstrip("\n"))
        return head + "\n\n".join(out) + tail


class Parser(argparse.ArgumentParser):
    """No abbreviations, help laid out at one width everywhere (``_HelpFormatter``: the
    examples keep their lines; the description does off a terminal and reflows on one), help on
    stdout through ``out``, and every error a ``Usage``. ``show_required`` names options the
    usage line shows as required that the command itself checks, so that a missing one is the
    command's own refusal."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("allow_abbrev", False)
        kwargs.setdefault("formatter_class", _HelpFormatter)
        if sys.version_info >= (3, 14):
            kwargs.setdefault("color", False)
        super().__init__(*args, **kwargs)
        self._shown_required: list[argparse.Action] = []

    def show_required(self, action: argparse.Action) -> None:
        self._shown_required.append(action)

    @contextlib.contextmanager
    def _as_shown(self) -> Iterator[None]:
        held = [(a, a.required) for a in self._shown_required]
        for a, _ in held:
            a.required = True
        try:
            yield
        finally:
            for a, required in held:
                a.required = required

    def format_usage(self) -> str:
        with self._as_shown():
            return super().format_usage()

    def format_help(self) -> str:
        with self._as_shown():
            return super().format_help()

    def error(self, message: str) -> NoReturn:
        raise Usage(_quotes(message), f"{self.prog} --help")

    def _print_message(self, message: str, file: Any = None) -> None:
        if message:
            (out if file is None or file is sys.stdout else err)(message)


def takes_value(parsers: Sequence[argparse.ArgumentParser]) -> set[str]:
    """Every option string, across the parsers, that is followed by a value."""
    return {
        option
        for parser in parsers
        for action in parser._actions
        if action.nargs != 0
        for option in action.option_strings
    }


def options(parsers: Sequence[argparse.ArgumentParser]) -> set[str]:
    """Every option string the parsers know."""
    return {o for parser in parsers for action in parser._actions for o in action.option_strings}


def asks(args: Sequence[str], valued: Collection[str], option: str) -> bool:
    """Whether the command line gives ``option`` anywhere as an option, not as a value."""
    i = 0
    while i < len(args) and args[i] != "--":
        if args[i] == option:
            return True
        i += 2 if args[i] in valued else 1
    return False


def verb_first(
    args: Sequence[str],
    valued: Collection[str],
    kept: Collection[str],
    known: Collection[str],
    prog: str,
) -> tuple[list[str], int | None]:
    """The command line with the options written before the verb moved after it, and the
    verb's place, or None when there is no verb. An option's value is never taken for the
    verb; the options in ``kept`` (the command's own, such as ``--version``) stay before it. An
    option before the verb that none of the parsers knows, an abbreviation among them, is a
    wrong command line: what follows it cannot be told for its value or the verb."""
    head: list[str] = []
    moved: list[str] = []
    i = 0
    while i < len(args):
        word = args[i]
        if word == "--":
            break
        if word.startswith("-") and word != "-":
            name = word.split("=", 1)[0]
            if name not in known:
                raise Usage(f"unrecognized arguments: {word}", f"{prog} --help")
            where = head if name in kept else moved
            where.append(word)
            if "=" not in word and name in valued and i + 1 < len(args):
                where.append(args[i + 1])
                i += 1
            i += 1
            continue
        return [*head, word, *moved, *args[i + 1 :]], len(head)
    return list(args), None
