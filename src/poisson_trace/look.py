"""The command-line look both commands keep, as ``docs/cli-look.md`` writes it: the exit codes,
the ``error:`` and ``stopped`` lines, the version line, counts with thousands separators, the
ASCII fallback, a reader that has gone away, the errors log, and an argument parser that
reads options before or after the verb and refuses abbreviations.

Standard library only. Every line a command prints goes through ``out`` or ``err``.
"""

from __future__ import annotations

import argparse
import contextlib
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

# the exit codes (docs/cli-look.md); 4 belongs to a check the user asks for, and no command
# here has one yet
DONE = 0
REFUSED = 1
USAGE = 2
FAILED = 3
INTERRUPTED = 130

PROVE_VERSION = "0.0.1"
INSTALL_PROVE = "pip install git+https://github.com/poisson-labs/prove"
NOTHING_WRITTEN = "stopped  interrupted; nothing was written"


class Usage(Exception):
    """The command line is wrong: one ``error:`` line, exit 2."""


class Failed(Exception):
    """A failure after work started: one ``error:`` line, exit 3."""


# ---------- numbers ----------


def count(n: float) -> str:
    """A count with thousands separators: ``10,496``. A whole number held as a float prints
    as the whole number."""
    return f"{int(n):,}" if float(n).is_integer() else f"{n:,}"


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
    if ch in _SPELT:
        return _SPELT[ch]
    folded = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
    return folded if folded and folded.isascii() else "?"


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
    the stream is pointed at the null device, so nothing more fails, then or at exit."""
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


def error(sentence: str) -> None:
    """``error: <sentence>`` on stderr, as one line."""
    err("error: " + " ".join(sentence.split()) + "\n")


def why(e: BaseException) -> str:
    """What a library's exception can tell a user: the system's own words for a failed file
    operation, else the exception's type, and never its text."""
    if isinstance(e, OSError) and e.strerror:
        return e.strerror
    return type(e).__name__


# ---------- the version line and the Prove check ----------


def version_line() -> str:
    """``poisson-trace 0.1.0 (poisson-prove 0.0.1, Python 3.11.7)``: what is installed."""
    import poisson_trace

    try:
        import proofload
    except ImportError:
        prove = "poisson-prove not installed"
    else:
        found = getattr(proofload, "__version__", None)
        prove = "poisson-prove " + (found if isinstance(found, str) else "of no version")
    python = ".".join(str(n) for n in sys.version_info[:3])
    return f"poisson-trace {poisson_trace.__version__} ({prove}, Python {python})\n"


def prove_refusal(does: str) -> str | None:
    """The refusal when Prove is not importable at the version this package reads, else None.
    ``does`` is what the command does through Prove, as the sentence's opening words."""
    try:
        import proofload
    except ImportError:
        return (
            f"{does} through Prove (the proofload package, version {PROVE_VERSION}), which is "
            f"not installed here; install it with {INSTALL_PROVE}"
        )
    found = getattr(proofload, "__version__", None)
    if found != PROVE_VERSION:
        return (
            f"{does} through Prove (the proofload package, version {PROVE_VERSION}) and found "
            f"proofload {found or 'of no version'}; install the version it reads with "
            f"{INSTALL_PROVE}"
        )
    return None


# ---------- the errors log ----------


def errors_log_path() -> Path:
    return Path.home() / ".cache" / "poisson-trace" / "errors.log"


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
        with open(path, "a", encoding="utf-8") as errors_log:
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
        error(str(e))
        return USAGE
    except refusals as e:
        error(str(e))
        return REFUSED
    except Failed as e:
        error(str(e))
        return FAILED
    except KeyboardInterrupt:
        out(session.stopped() + "\n")
        return INTERRUPTED
    except Exception as e:
        _unexpected(session, e)
        return FAILED


def _unexpected(session: Session, e: Exception) -> None:
    details = "".join(traceback.format_exception(e))
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = (
        f"--- {stamp} {version_line()}"
        f"{shlex.join([session.tool, *session.argv])}\n{details}\n"
    )
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


def _quotes(message: str) -> str:
    """Argparse's message with its values in double quotes and its lists of choices bare, never
    in Python's single quotes."""
    message = re.sub(
        r"\(choose from ([^)]*)\)",
        lambda m: "(choose from " + m.group(1).replace("'", "") + ")",
        message,
    )
    return re.sub(r"'([^'\n]*)'", r'"\1"', message)


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
        raise Usage(f"{_quotes(message)}; see {self.prog} --help")

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


def verb_first(
    args: Sequence[str], valued: Collection[str], kept: Collection[str]
) -> tuple[list[str], int | None]:
    """The command line with the options written before the verb moved after it, and the
    verb's place, or None when there is no verb. An option's value is never taken for the
    verb; the options in ``kept`` (the command's own, such as ``--help``) stay before it."""
    head: list[str] = []
    moved: list[str] = []
    i = 0
    while i < len(args):
        word = args[i]
        if word == "--":
            break
        if word.startswith("-") and word != "-":
            name = word.split("=", 1)[0]
            where = head if name in kept else moved
            where.append(word)
            if "=" not in word and name in valued and i + 1 < len(args):
                where.append(args[i + 1])
                i += 1
            i += 1
            continue
        return [*head, word, *moved, *args[i + 1 :]], len(head)
    return list(args), None
