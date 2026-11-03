"""The command-line look both commands keep, as ``docs/cli-look.md`` writes it: the exit codes,
the ``error:`` and ``stopped`` lines, the version line, counts with thousands separators, the
ASCII fallback, a reader that has gone away, the errors log, and an argument parser that
reads options before or after the verb and refuses abbreviations.

Standard library only. Every line a command prints goes through ``out`` or ``err``.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import importlib.metadata
import os
import re
import shlex
import sys
import traceback
import unicodedata
from collections.abc import Callable, Collection, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn, TextIO

# the exit codes (docs/cli-look.md); 4 belongs to a check the user asks for (doctor)
DONE = 0
REFUSED = 1
USAGE = 2
FAILED = 3
CHECK_FAILED = 4
INTERRUPTED = 130

def _declared_prove() -> str:
    """The version of Prove this package pins: the ``poisson-prove==X`` that ``pyproject.toml``
    declares, read back from the installed package's own metadata, so it is written in one place
    and what Trace checks for cannot drift from what it declares."""
    try:
        requires = importlib.metadata.requires("poisson-trace") or []
    except importlib.metadata.PackageNotFoundError:
        requires = []
    pin = re.compile(r"\s*poisson[-_.]prove\s*==\s*([^\s;,]+)\s*(?:;|$)", re.IGNORECASE)
    for requirement in requires:
        pinned = pin.match(requirement)
        if pinned:
            return pinned.group(1)
    raise RuntimeError(
        "the installed poisson-trace does not state which poisson-prove it pins (the metadata "
        "pip wrote when it installed this package has no poisson-prove==VERSION requirement); "
        "install it again with pip"
    )


# The one Prove this package reads: poisson-prove, imported as poisson_prove, at the exact version
# pyproject.toml declares, from PyPI.
PROVE_VERSION = _declared_prove()
INSTALL_PROVE = f"pip install poisson-prove=={PROVE_VERSION}"
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
    _write(sys.stdout, text)


def err(text: str) -> None:
    _write(sys.stderr, text)


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


def prove_refusal(does: str) -> str | None:
    """The refusal when Prove is not importable at the version this package reads, else None.
    ``does`` is what the command does through Prove, as the sentence's opening words. The line
    that installs it is the command to run next, under the sentence, and not in it."""
    try:
        import poisson_prove
    except ImportError:
        return (
            f"{does} through Prove (the poisson-prove package, version {PROVE_VERSION}), which "
            "is not installed here"
        )
    found = _found(poisson_prove)
    if found != PROVE_VERSION:
        saw = f"poisson-prove {found}" if found else "a poisson-prove that states no version"
        return (
            f"{does} through Prove (the poisson-prove package, version {PROVE_VERSION}) and "
            f"found {saw}"
        )
    return None


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


def run(
    tool: str,
    argv: Sequence[str],
    body: Callable[[Session], int],
    refusals: tuple[type[Exception], ...] = (),
) -> int:
    """``body`` under the look's rules: a refusal is one ``error:`` line and exit 1, a wrong
    command line exit 2, a failure after work started exit 3, Ctrl-C a ``stopped`` line on
    stdout and exit 130, and anything unexpected one line naming the errors log, exit 3."""
    session = Session(tool, list(argv))
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
    except KeyboardInterrupt:
        line = session.stopped()
        out(line + "\n" if session.render is None else session.render(line))
        return INTERRUPTED
    except Exception as e:
        _unexpected(session, e)
        return FAILED


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


class Parser(argparse.ArgumentParser):
    """No abbreviations, help as written (description and examples keep their lines), help on
    stdout through ``out``, and every error a ``Usage``. ``show_required`` names options the
    usage line shows as required that the command itself checks, so that a missing one is the
    command's own refusal."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("allow_abbrev", False)
        kwargs.setdefault("formatter_class", argparse.RawDescriptionHelpFormatter)
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
