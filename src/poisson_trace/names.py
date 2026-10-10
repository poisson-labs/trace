"""Names for stored runs: the names file beside the runs, the name every run has from its
manifest, and the words a verb takes for a run.

``trace-names.toml`` at the store root holds the names a user gave, written by ``poisson-trace
name`` alone; no run's bytes change. A run with no entry is named from its manifest: the target
up to its first ``/``, the day it started in UTC and a letter in start order among the runs that
would otherwise share that name. A run an import wrote is named by the name it was imported
under, which is its id. Names are computed each time, never stored, so they are the same on
every machine that holds the same store.

A verb takes a run as ``latest``, ``previous``, ``latest:TARGET``, ``previous:TARGET``, ``#N``
(row N of ``poisson-trace runs``), a name the user gave, a name from the manifest or the full
id. A word that reaches no run, or two, is refused and never guessed.

``proofload`` is imported inside the functions that read a store, so the checks on a name alone
can run before the check that Prove is installed.
"""

from __future__ import annotations

import contextlib
import os
import re
import tomllib
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from poisson_trace import look

NAMES_FILE = "trace-names.toml"
HEADER = "# Poisson Trace: your names for the runs in this store. Written by `poisson-trace name`."
LONGEST = 80
IMPORTED = "import:"
# the most runs a refusal names before it says how many more there are
SHOWN = 10


class Damaged(look.Refused):
    """The names file is not one: every verb that reads names refuses it."""


# ---------- a name alone ----------

# the characters str.splitlines breaks a line at
_BREAKS = frozenset("\n\r\v\f\x1c\x1d\x1e\x85  ")


def reserved(text: str) -> bool:
    """Whether ``text`` is one of the words a verb reads before any name."""
    return text in ("latest", "previous") or text.startswith(("latest:", "previous:", "#"))


def _unwritable(ch: str) -> bool:
    """A character a name never holds: a control character other than the tab, which a
    terminal acts on rather than shows, or half of a character that is not text (a byte a
    command line could not read as UTF-8)."""
    return ch != "\t" and unicodedata.category(ch) in ("Cc", "Cs")


def unfit(text: str) -> str | None:
    """Why ``text``, already trimmed, cannot be a name, or None when it can: a name is not
    empty, is one line of at most 80 characters of text, is not a word a verb reads before any
    name, and does not open with a dash, which a command line reads as an option."""
    if not text:
        return "a name is not empty"
    if len(text) > LONGEST:
        return f"a name is at most {LONGEST} characters, and this one has {look.count(len(text))}"
    if any(ch in _BREAKS for ch in text):
        return "a name is one line"
    if any(_unwritable(ch) for ch in text):
        return "a name holds no control character and nothing that is not text"
    if text in ("latest", "previous"):
        which = "newest" if text == "latest" else "second newest"
        return f'"{text}" is the word for the {which} complete run'
    if text.startswith(("latest:", "previous:")):
        return "a name beginning latest: or previous: is the word for a target's newest runs"
    if text.startswith("#"):
        return "a name beginning # is the word for a row of poisson-trace runs"
    if text.startswith("-"):
        return "a name beginning with a dash is read as an option on a command line"
    return None


def folder_hole(text: str) -> str | None:
    """Why ``text`` cannot be the folder a run is written to, or None when it can."""
    rule = "a run name is a folder name: not empty, no slash, at most 80 characters"
    if "\0" in text:
        return f"{rule}; a name holding a NUL character is not one"
    if len(text) > LONGEST:
        return f"{rule}; this one has {look.count(len(text))}"
    if text in ("", ".", "..") or "/" in text or "\\" in text:
        return f'{rule}; "{text}" is not one'
    return None


def import_name_refusal(text: str) -> str | None:
    """Why an import cannot write a run named ``text``, before any store is read: a folder
    name first, then a name a command could give back to a verb."""
    hole = folder_hole(text)
    if hole is not None:
        return hole
    if text in (NAMES_FILE, NAMES_FILE + ".partial"):
        return f'"{text}" is the name of the file that holds the names of yours in a store'
    if text != text.strip():
        return (
            f'"{text}" has a space at one end, and every word a verb takes is read trimmed, so '
            "no command could name this run"
        )
    why = unfit(text)
    if why is not None:
        return f'"{text}" cannot name a run: {why}'
    return None


# ---------- the names file ----------


def _toml_string(text: str) -> str:
    """``text`` as a TOML basic string."""
    out = []
    for ch in text:
        if ch in ('"', "\\"):
            out.append("\\" + ch)
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def names_file_text(entries: Mapping[str, str]) -> str:
    """The file, byte for byte: the comment, the version, a blank line and the names table,
    one entry per name, sorted by name."""
    lines = [HEADER, "version = 1", "", "[names]"]
    lines += [f"{_toml_string(n)} = {_toml_string(entries[n])}" for n in sorted(entries)]
    return "\n".join(lines) + "\n"


def write_names_file(root: Path, shown: str, entries: Mapping[str, str]) -> None:
    """Replace the names file whole: written beside it, then moved over it, so that a reader
    finds the old file or the new one and nothing between."""
    path = root / NAMES_FILE
    partial = root / (NAMES_FILE + ".partial")
    try:
        with open(partial, "w", encoding="utf-8", newline="\n") as names_file:
            names_file.write(names_file_text(entries))
        os.replace(partial, path)
    except OSError as e:
        raise look.Refused(
            f"cannot write {shown} ({look.why(e)}); the names are as they were"
        ) from e
    finally:
        # once moved, there is nothing left to remove; a file that cannot be removed holds no
        # name of anyone's, and the next write replaces it
        with contextlib.suppress(OSError):
            partial.unlink(missing_ok=True)


def _line_of(e: tomllib.TOMLDecodeError) -> str:
    found = re.search(r"\(at line (\d+)", str(e))
    return f" (line {found.group(1)})" if found else ""


def read_names_file(root: Path, shown: str) -> tuple[dict[str, str], dict[str, str]]:
    """The names a user gave, trimmed, mapped to the ids they name, empty when the store has
    no names file; and the names among them that cannot be names, each with why. A file that
    is not a names file is refused, naming it."""
    path = root / NAMES_FILE
    if not path.exists() and not path.is_symlink():
        return {}, {}

    def damaged(why: str, *nexts: str) -> Damaged:
        return Damaged(f"{shown} is not a names file: {why}", *nexts)

    try:
        raw = path.read_bytes()
    except OSError as e:
        raise Damaged(f"cannot read {shown} ({look.why(e)})") from e
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise damaged("it is not UTF-8 text") from None
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise damaged(f"it is not TOML{_line_of(e)}") from None
    except RecursionError:
        raise damaged("it is not TOML a reader can follow: it nests too deep") from None
    for key, value in doc.items():
        if key not in ("version", "names"):
            what = "table" if isinstance(value, dict) else "setting"
            raise damaged(f'"{key}" is not a {what} a names file has; it has version and [names]')
    version = doc.get("version")
    if version is None:
        raise damaged("it has no version line, version = 1")
    if type(version) is not int:
        raise damaged("its version is not the whole number 1")
    if version != 1:
        raise damaged(f"it is version {version}, and this Trace reads version 1")
    table = doc.get("names", {})
    if not isinstance(table, dict):
        raise damaged("its names are not a [names] table")
    entries: dict[str, str] = {}
    given: dict[str, str] = {}
    unfit_names: dict[str, str] = {}
    for key, value in table.items():
        if not isinstance(value, str):
            raise damaged(f'the name "{key}" is given a value that is not a run id in quotes')
        trimmed = key.strip()
        if trimmed in given:
            raise damaged(
                f'"{given[trimmed]}" and "{key}" are one name once their spaces are trimmed'
            )
        why = unfit(trimmed)
        if why is not None:
            unfit_names[trimmed] = why
        given[trimmed] = key
        entries[trimmed] = value
    return entries, unfit_names


# ---------- the runs of a store, named ----------


def _letters(n: int) -> str:
    """The n-th letter name, from 0: a … z, aa, ab …"""
    out = ""
    n += 1
    while n:
        n, rest = divmod(n - 1, 26)
        out = chr(ord("a") + rest) + out
    return out


def _started(created_at: Any) -> datetime | None:
    if not isinstance(created_at, str):
        return None
    try:
        at = datetime.fromisoformat(created_at)
        return at.replace(tzinfo=UTC) if at.tzinfo is None else at.astimezone(UTC)
    except (ValueError, OverflowError):
        # not a time, or one that falls outside the years 1 to 9999 once it is read as UTC
        return None


def target_of(target_id: str) -> str:
    """The target as names show it: the target id up to its first ``/``."""
    return target_id.split("/", 1)[0]


@dataclass(frozen=True)
class Named:
    """One run of a store and the name it goes by."""

    run_id: str
    name: str
    named_by: str  # "you" or "manifest"
    computed: str | None  # the name from its manifest; None for an imported run
    created_at: str
    started: datetime
    status: str
    target_id: str
    backend: str
    number: int | None = None

    @property
    def target(self) -> str:
        return target_of(self.target_id)

    @property
    def imported(self) -> bool:
        return self.backend.startswith(IMPORTED)

    @property
    def complete(self) -> bool:
        return self.status == "complete"

    def shown(self) -> str:
        """The run as a refusal names it: its name and its id."""
        return f'"{self.name}"' if self.name == self.run_id else f'"{self.name}" ({self.run_id})'


@dataclass
class Index:
    """The runs of one store, newest first, each with its name; the words that reach them."""

    store: str  # the store as the user typed it
    root: Path
    runs: list[Named]
    entries: dict[str, str]  # the names file: your name -> run id
    stale: dict[str, str] = field(default_factory=dict)  # entries for runs the store lacks
    unreadable: list[str] = field(default_factory=list)  # runs Prove could not read
    words: dict[str, set[str]] = field(default_factory=dict)
    doubled: dict[str, list[str]] = field(default_factory=dict)  # a run given two names
    unfit: dict[str, str] = field(default_factory=dict)  # names that cannot be names, and why

    def damage(self) -> Damaged | None:
        """The refusal a file with a stale entry, a name that cannot be one or two names for
        one run gets from every verb but ``name``, which can take such an entry back."""
        if self.stale:
            return self.stale_refusal()
        if self.unfit:
            name, why = next(iter(sorted(self.unfit.items())))
            shown = name if not any(ch in _BREAKS for ch in name) else name.splitlines()[0] + " …"
            return Damaged(
                f'{self.names_shown()} holds "{shown}", which cannot be a name: {why}',
                *(self.forget(n) for n in sorted(self.unfit) if not any(c in _BREAKS for c in n)),
            )
        if self.doubled:
            run_id, names = next(iter(sorted(self.doubled.items())))
            return Damaged(
                f"{self.names_shown()} gives the run {run_id} two names of yours, "
                + " and ".join(f'"{n}"' for n in names)
                + "; a run has one",
                *(self.forget(n) for n in names[1:]),
            )
        return None

    @property
    def complete(self) -> list[Named]:
        return [r for r in self.runs if r.complete]

    def by_id(self, run_id: str) -> Named | None:
        return next((r for r in self.runs if r.run_id == run_id), None)

    # ---------- the words a verb takes ----------

    def resolve(self, given: str) -> Named:
        """The one run ``given`` names, or a refusal; never a guess."""
        text = given.strip()
        if reserved(text) and self.unreadable:
            unread = ", ".join(self.unreadable)
            look.err(
                f"note: latest, previous and the numbers leave out what Prove could not read: "
                f"the record or the start time of {unread}\n"
            )
        if text in ("latest", "previous"):
            return self._newest(text, None)
        for form in ("latest", "previous"):
            if text.startswith(form + ":"):
                return self._newest(form, text[len(form) + 1 :].strip())
        if text.startswith("#"):
            return self._numbered(text)
        hits = self.words.get(text, set())
        if len(hits) > 1:
            runs = [r for r in self.runs if r.run_id in hits]
            shown = " and ".join(self._with_number(r) for r in runs)
            raise look.Refused(
                f'two runs answer to "{text}": {shown}; name one of them with poisson-trace '
                "name, or give it by its number",
                self.listing(),
            )
        if not hits:
            raise look.Refused(self._unknown(text), self.listing())
        (run_id,) = hits
        found = self.by_id(run_id)
        if found is None:
            # a run Prove could not read: reached by its id, and refused when it is read
            return Named(
                run_id=run_id,
                name=run_id,
                named_by="manifest",
                computed=None,
                created_at="",
                started=datetime.min.replace(tzinfo=UTC),
                status="unreadable",
                target_id="unreadable",
                backend="",
            )
        return found

    def _with_number(self, run: Named) -> str:
        return run.shown() if run.number is None else f"#{run.number} {run.shown()}"

    def _unknown(self, text: str) -> str:
        shown = [r.shown() for r in self.runs[:SHOWN]]
        more = len(self.runs) - SHOWN
        held = ", ".join(shown) + (f" and {look.count(more)} more" if more > 0 else "")
        return f'unknown run "{text}"; the store holds {held}'

    def _newest(self, form: str, target: str | None) -> Named:
        pool = self.complete if target is None else [r for r in self.complete if r.target == target]
        rank = 0 if form == "latest" else 1
        if len(pool) > rank:
            return pool[rank]
        if target is not None and "/" in target:
            raise look.Refused(
                f'{form}:TARGET takes the target as names show it, up to its first "/": '
                f'"{target_of(target)}", not "{target}"',
                self.listing(),
            )
        if target is not None and not any(r.target == target for r in self.runs):
            targets = sorted({f'"{r.target}"' for r in self.runs})
            raise look.Refused(
                f'no run of this store has the target "{target}"; its targets are '
                f"{', '.join(targets)}",
                self.listing(),
            )
        whose = "complete runs" if target is None else f'complete runs of the target "{target}"'
        held = "none" if not pool else "one"
        word = "the newest" if form == "latest" else "the second newest"
        raise look.Refused(
            f"{form if target is None else f'{form}:{target}'} is {word} of the {whose}, and "
            f"the store holds {held}",
            self.listing("--all"),
        )

    def _numbered(self, text: str) -> Named:
        digits = text[1:]
        complete = self.complete
        if not re.fullmatch(r"[1-9][0-9]*", digits, flags=re.ASCII):
            raise look.Refused(
                f'"{text}" is not a row of poisson-trace runs: a row is # and a number from 1',
                self.listing(),
            )
        # a number longer than the count of rows is past the last row, however long it is
        if len(digits) > len(str(len(complete))) or int(digits) > len(complete):
            shown = text if len(digits) <= 12 else f"#{digits[:6]}…"
            raise look.Refused(
                f"there is no run {shown}: the store holds {look.count(len(complete))} complete "
                f"{'run' if len(complete) == 1 else 'runs'}",
                self.listing(),
            )
        return complete[int(digits) - 1]

    def listing(self, *extra: str) -> str:
        """The command that lists this store's runs."""
        return look.command("poisson-trace", "runs", look.option("--store", self.store), *extra)

    def word_for(self, run: Named) -> str:
        """The word a command gives for ``run``: its name when that reaches it alone; else its
        number, or its id, which always does. Two runs can come to answer to one name when a
        name of yours or an import's name was given before a run with that computed name was
        stored."""
        if self.holder(run.name) == {run.run_id}:
            return run.name
        return f"#{run.number}" if run.number is not None else run.run_id

    # ---------- what the names file allows ----------

    def holder(self, text: str) -> set[str]:
        """The runs that answer to ``text`` now, by any route."""
        return set(self.words.get(text, set()))

    def stale_refusal(self) -> Damaged:
        shown = ", ".join(f'"{n}" for the run "{r}"' for n, r in sorted(self.stale.items()))
        return Damaged(
            f"{self.names_shown()} names {shown}, which the store does not hold",
            *(self.forget(n) for n in sorted(self.stale)),
        )

    def forget(self, name: str) -> str:
        """The command that takes back the name of yours ``name``; one a command line would read
        as an option comes after ``--``."""
        store = look.option("--store", self.store)
        if name.startswith("-"):
            return look.command("poisson-trace", "name", "--forget", store, "--", look.word(name))
        return look.command("poisson-trace", "name", look.word(name), "--forget", store)

    def names_shown(self) -> str:
        return shown_file(self.store)


def shown_file(store: str) -> str:
    """The names file as a user reads its path: under the store as they typed it."""
    return f"{store.rstrip('/') or '/'}/{NAMES_FILE}" if store else NAMES_FILE


def index(store: Any, held: Sequence[str], shown: str, *, lenient: bool = False) -> Index:
    """The runs ``store`` (Prove's store at the path ``shown``, as the user typed it) holds,
    named. A damaged names file is refused; so are an entry for a run the store does not hold
    and two names for one run, unless ``lenient`` (``name``, which can take either back)."""
    root = Path(shown)
    entries, unfit_names = read_names_file(root, shown_file(shown))
    runs: list[Named] = []
    unreadable: list[str] = []
    for run_id in held:
        try:
            manifest = store.manifest(run_id)
        except Exception:
            unreadable.append(run_id)
            continue
        started = _started(manifest.created_at)
        if started is None:
            unreadable.append(run_id)
            continue
        runs.append(
            Named(
                run_id=run_id,
                name=run_id,
                named_by="manifest",
                computed=None,
                created_at=manifest.created_at,
                started=started,
                status=str(manifest.status),
                target_id=str(manifest.target_id),
                backend=str(manifest.backend),
            )
        )
    runs.sort(key=lambda r: (r.started, r.run_id))
    computed: dict[str, str] = {}
    letters: dict[tuple[str, str], int] = {}
    for run in runs:
        if run.imported or not _nameable(run.target):
            continue
        day = run.started.strftime("%Y-%m-%d")
        n = letters.get((run.target, day), 0)
        letters[(run.target, day)] = n + 1
        computed[run.run_id] = f"{run.target} {day} {_letters(n)}"
    ids = {r.run_id for r in runs}
    stale = {n: r for n, r in entries.items() if r not in ids and r not in unreadable}
    mine: dict[str, list[str]] = {}
    for name, run_id in entries.items():
        if name not in unfit_names:
            mine.setdefault(run_id, []).append(name)
    doubled = {r: sorted(n) for r, n in mine.items() if len(n) > 1}
    checked = Index(shown, root, [], entries, stale, doubled=doubled, unfit=unfit_names)
    damage = checked.damage()
    if damage is not None and not lenient:
        raise damage
    named: list[Named] = []
    for run in runs:
        yours = mine.get(run.run_id)
        own = computed.get(run.run_id)
        if yours:
            name, by = sorted(yours)[0], "you"
        elif run.imported:
            name, by = run.run_id, "you"
        else:
            name, by = own or run.run_id, "manifest"
        named.append(replace(run, name=name, named_by=by, computed=own))
    named.reverse()
    numbered: list[Named] = []
    n = 0
    for run in named:
        if run.complete:
            n += 1
            numbered.append(replace(run, number=n))
        else:
            numbered.append(run)
    words: dict[str, set[str]] = {}

    def add(word: str, run_id: str) -> None:
        words.setdefault(word, set()).add(run_id)

    for run in numbered:
        add(run.run_id, run.run_id)
        if run.computed is not None:
            add(run.computed, run.run_id)
    for name, run_id in entries.items():
        if run_id in ids and name not in unfit_names:
            add(name, run_id)
    for run_id in unreadable:
        add(run_id, run_id)
    return Index(shown, root, numbered, entries, stale, unreadable, words, doubled, unfit_names)


def _nameable(target: str) -> bool:
    """Whether a name built on ``target`` could be given back to a verb: one with nothing at
    either end, no control character, and none of the words a verb reads first. A run whose
    target is not goes by its id."""
    return (
        bool(target)
        and target == target.strip()
        and "\t" not in target
        and unfit(f"{target} 2026-01-01 a") is None
    )


def taken(store: Any, held: Iterable[str], root: Path, name: str) -> str | None:
    """The refusal when an import named ``name`` would answer to a word another run of the
    store already answers to, else None."""
    found = index(store, list(held), str(root))
    others = found.holder(name)
    if not others:
        return None
    run = found.by_id(next(iter(sorted(others))))
    whose = "a name you gave" if name in found.entries else "the name from the manifest"
    of = run.shown() if run is not None else f'"{name}"'
    return (
        f'the store at {root} already has a run that answers to "{name}" ({whose} of {of}); '
        "an import's name is the word for its run, so give this one another name"
    )
