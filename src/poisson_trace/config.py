"""The config file, ``trace.toml``: where the results are, what counts as a failure, the
check's ceilings, how runs are named when no name was given, where an upload goes, the signal
field mappings and budgets, the failure taxonomy's own rules, and the files another tool wrote
that ``init`` imports after asking (``[[import]]``).

Read from the current folder, or from the file ``--config PATH`` names, and never from a folder
above. A store path in it is read from the folder that holds the file. A file that is not a
version 1 config is refused in one sentence naming the file and the line the fault is written
on, before anything else is read or written. ``poisson-trace init`` writes it; a user may edit it
by hand, and ``poisson-trace doctor`` checks it.

Standard library and the taxonomy's own rules (``ingest/taxonomy.py``, itself standard library
only): ``tomllib`` reads the file, and nothing here reads a store. An ``[[import]]`` entry's
options are checked against its reader's own flags (``ingest/cli.py`` says which keys, types
and choices each reader takes); no file an entry names is opened here.
"""

from __future__ import annotations

import contextlib
import ipaddress
import math
import os
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import poisson_trace
from poisson_trace import look
from poisson_trace.ingest.taxonomy import (
    BUDGETS,
    CONDITIONS,
    FAILURE_KINDS,
    Budgets,
    Rule,
    taxonomy_sha256,
)
from poisson_trace.names import import_name_refusal, toml_string

CONFIG = "trace.toml"
VERSION = 1
HEADER = (
    "# Poisson Trace: where your results are, and what counts as a failure.\n"
    "# Written by `poisson-trace init`. Edit it freely; `poisson-trace doctor` checks it.\n"
)
FORMS: tuple[str, ...] = ("target", "date", "target-date")
FAIL_ON: tuple[str, ...] = ("failed-more", "too-small")
TOKEN_ENV = "POISSON_TRACE_UPLOAD_TOKEN"
# a store's name: what --store NAME takes for the store the config names so
STORE_NAME = re.compile(r"[A-Za-z0-9_-]{1,40}")
STORE_NAME_RULE = "a store name is 1 to 40 letters, digits, - and _"

# the settings of version 1, by table; the top level's own and its tables
_SETTINGS: dict[str, tuple[str, ...]] = {
    "store": ("path",),
    "events": ("failed",),
    "check": ("max_mde", "max_mde_hr", "fail_on", "max_change"),
    "names": ("from",),
    "upload": ("enabled", "url", "token_env"),
    "signals": ("case_field", "outcome_field", "score_field", "cut", "cost_field", "budgets"),
    "taxonomy": ("rules",),
}
# the array of tables that lists the files to import, checked after the tables above
_IMPORT = "import"
_TOP = ("version", *_SETTINGS, _IMPORT)
# the keys of an [[import]] entry that are the entry's own; the rest are its reader's options
_ENTRY = ("file", "tool", "name")
# the import's own flags, which are never a reader's option
_IMPORTS_OWN = ("run", "store", "config", "started", "verdicts", "json", "debug", "plain", "files")
# the pullers that fetch results from a service, by the prefix of an address (section 18.3.2 of
# the spec); none is in this install yet, so an address is refused naming the puller
PULLERS: tuple[str, ...] = ("langsmith", "braintrust", "weave", "lemma")
# the [signals] settings that name a field or column of the source
_FIELDS = ("case_field", "outcome_field", "score_field", "cost_field")
# a word the spec once used for a budget, and the budget it means (SA9)
_BUDGET_ALIASES = {"max_tokens": "max_total_tokens"}
# the most edits between a word written and the setting it is taken to mean
_NEAR = 2
_VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class ConfigError(look.Refused):
    """The config file is not one: refused in one sentence, exit 1."""


@dataclass(frozen=True)
class ImportEntry:
    """One ``[[import]]`` table: a file another tool wrote, for ``init`` to import after asking.
    ``file`` is kept as written, relative to the config's folder; ``options`` are the reader's,
    by the keys as written (a flag's name without ``--`` and with ``_`` for ``-``)."""

    file: str
    tool: str
    name: str
    options: Mapping[str, Any]
    line: int  # the line its [[import]] header is written on


@dataclass(frozen=True)
class Config:
    """A version 1 config, read and checked. Store paths are as the current folder reads them."""

    path: Path
    shown: str  # the file as the user named it, or trace.toml
    given: bool  # named by --config
    text: str
    store: str | None = None
    named: Mapping[str, str] = field(default_factory=dict)
    events: tuple[str, ...] | None = None
    max_mde: float | None = None
    max_mde_hr: float | None = None
    fail_on: tuple[str, ...] | None = None
    # [check] max_change: each continuous measure's ceiling as a share of the old mean (CT2,
    # CS10); empty when the file sets none
    max_change: Mapping[str, float] = field(default_factory=dict)
    names_from: str = "target"
    upload: Mapping[str, Any] = field(default_factory=dict)
    # [signals]: the field mappings as written (read and checked; in TF21 the import's flags
    # still say which columns it reads, SA8), the budgets and the taxonomy's rules
    signals: Mapping[str, Any] = field(default_factory=dict)
    budgets: Budgets | None = None
    rules: tuple[Rule, ...] = ()
    # [[import]]: the files to import, in the file's order
    imports: tuple[ImportEntry, ...] = ()

    @property
    def folder(self) -> Path:
        return self.path.parent

    @property
    def taxonomy_sha256(self) -> str:
        """The digest of the rules and budgets this config classifies with (SA9)."""
        return taxonomy_sha256(self.rules, self.budgets)

    def flags(self) -> tuple[str, ...]:
        """What a command carries to read this same file: ``--config PATH`` when the file was
        named by flag, and nothing when it is the current folder's ``trace.toml``."""
        return (look.option("--config", str(self.path)),) if self.given else ()

    def stores(self) -> list[tuple[str | None, str]]:
        """``(name, path)`` for every store, the unnamed ``[store]`` first."""
        first = [] if self.store is None else [(None, self.store)]
        return [*first, *self.named.items()]


# ---------- finding and reading the file ----------


def path_of(given: str | None) -> Path:
    return Path(given) if given is not None else Path(CONFIG)


def load(given: str | None) -> Config | None:
    """The config: the file ``given`` names, or the current folder's ``trace.toml``; None when
    no file was named and there is none here. Refused when it is not a version 1 config."""
    path = path_of(given)
    shown = look.shown(given) if given is not None else CONFIG
    if given is None and not path.exists() and not path.is_symlink():
        return None
    if not path.exists():
        raise ConfigError(f"no config file at {shown}")
    if path.is_dir():
        raise ConfigError(f"{shown} is a folder, not a config file")
    if not path.is_file():
        # a pipe or a device would be read without end, or not at all
        raise ConfigError(f"{shown} is not a file a config can be read from")
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise ConfigError(f"cannot read {shown} ({look.why(e)})") from e
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ConfigError(f"{shown} is not a config file: it is not UTF-8 text") from None
    return parse(text, path, shown, given=given is not None)


def parse(text: str, path: Path, shown: str, *, given: bool) -> Config:
    """The config ``text`` holds, checked against version 1."""
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        found = re.search(r"\(at line (\d+)", str(e))
        at = f" line {found.group(1)}" if found else ""
        raise ConfigError(f"{shown}{at}: this is not TOML a config can be read from") from None
    except RecursionError:
        raise ConfigError(f"{shown}: it nests too deep to be read as a config") from None
    return _Checker(text, shown).check(doc, path, given)


# ---------- the lines settings are written on ----------

_PART = r'[A-Za-z0-9_-]+|"(?:[^"\\\n]|\\.)*"|\'[^\'\n]*\''
_DOTTED = rf"(?:{_PART})(?:\s*\.\s*(?:{_PART}))*"
_TABLE = re.compile(rf"^\s*\[\[?\s*({_DOTTED})\s*\]\]?")
_ASSIGNED = re.compile(rf"^\s*({_DOTTED})\s*=(.*)$")


def _parts(dotted: str) -> tuple[str, ...]:
    """A dotted key as its parts, each unquoted as TOML reads it."""
    out = []
    for part in re.findall(_PART, dotted):
        if part[0] in "\"'":
            try:
                part = tomllib.loads(f"k = {part}")["k"]
            except tomllib.TOMLDecodeError:
                part = part[1:-1]
        out.append(part)
    return tuple(out)


def _lines(text: str) -> dict[tuple[Any, ...], int]:
    """Every table and setting the text writes, by its full key, with the line it is first
    written on. Lines inside a string of several lines are not read as settings. An array of
    tables (``[[taxonomy.rules]]``) is keyed as the array, and each of its tables also by its
    number from zero, so a fault in the third rule names the third rule's lines."""
    found: dict[tuple[Any, ...], int] = {}
    table: tuple[Any, ...] = ()
    arrays: dict[tuple[str, ...], int] = {}
    open_quote: str | None = None
    for n, line in enumerate(text.splitlines(), start=1):
        if open_quote is not None:
            if open_quote in line:
                open_quote = None
            continue
        header = _TABLE.match(line)
        if header is not None:
            named = _parts(header.group(1))
            found.setdefault(named, n)
            if line.lstrip().startswith("[["):
                at = arrays.get(named, 0)
                arrays[named] = at + 1
                table = (*named, at)
                found.setdefault(table, n)
            else:
                table = named
            continue
        setting = _ASSIGNED.match(line)
        if setting is None:
            continue
        key = table + _parts(setting.group(1))
        for at in range(len(table) + 1, len(key) + 1):
            found.setdefault(key[:at], n)
        open_quote = _left_open(setting.group(2))
    return found


def _left_open(rest: str) -> str | None:
    """The quotes of a string of several lines that ``rest``, what follows a setting's ``=``,
    opens and does not close on its line; None when it leaves none open. Strings on one line
    and a comment are read as such, so the quotes inside them open nothing."""
    at = 0
    while at < len(rest):
        if rest[at] == "#":
            return None
        quote = next((q for q in ('"""', "'''") if rest.startswith(q, at)), None)
        if quote is not None:
            end = rest.find(quote, at + 3)
            if end < 0:
                return quote
            at = end + 3
        elif rest[at] in "\"'":
            mark, at = rest[at], at + 1
            while at < len(rest) and rest[at] != mark:
                at += 2 if mark == '"' and rest[at] == "\\" else 1
            at += 1
        else:
            at += 1
    return None


def _edits(a: str, b: str) -> int:
    """The fewest single-character insertions, deletions and substitutions from ``a`` to ``b``."""
    before = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        now = [i]
        for j, cb in enumerate(b, start=1):
            now.append(min(before[j] + 1, now[j - 1] + 1, before[j - 1] + (ca != cb)))
        before = now
    return before[-1]


def nearest(word: str, known: Sequence[str]) -> str | None:
    """The known word fewest edits from ``word``, if it is at most two edits away."""
    scored = sorted((_edits(word, k), i, k) for i, k in enumerate(known))
    if scored and scored[0][0] <= _NEAR:
        return scored[0][2]
    return None


def _and(words: Sequence[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def _quoted(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _value(value: Any) -> str:
    """A value as the file writes it, for a sentence."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _quoted(value)
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "a list"
    if isinstance(value, dict):
        return "a table"
    return "a date or a time"


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def loopback(host: str | None) -> bool:
    """Whether ``host`` is this machine: localhost, an address in 127.0.0.0/8, or ::1."""
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class _Checker:
    def __init__(self, text: str, shown: str) -> None:
        self.shown = shown
        self.lines = _lines(text)
        self.text = text

    def fault(self, key: Sequence[Any], why: str) -> ConfigError:
        at = None
        for n in range(len(key), 0, -1):
            at = self.lines.get(tuple(key[:n]))
            if at is not None:
                break
        where = f"{self.shown} line {at}" if at is not None else self.shown
        return ConfigError(f"{where}: {why}")

    def unknown(
        self,
        key: Sequence[Any],
        known: Sequence[str],
        table: str | None,
        *,
        whole: bool = False,
        array: bool = False,
    ) -> ConfigError:
        """A table or setting version 1 does not have, with the one nearest it, if any is."""
        word = str(key[-1])
        near = nearest(word, known)
        if table is None:
            if array:
                written = f"[[{word}]] is not a table"
            else:
                written = f"[{word}] is not a table" if whole else f'"{word}" is not a setting'
            if near is None:
                return self.fault(
                    key,
                    f"{written}; a config has version, the tables "
                    f"{_and([f'[{k}]' for k in _SETTINGS])}, and [[{_IMPORT}]] tables",
                )
            if near == _IMPORT:
                meant = f"[[{_IMPORT}]]"
            else:
                meant = f"[{near}]" if near in _SETTINGS else f'"{near}"'
            return self.fault(key, f"{written}; did you mean {meant}?")
        written = f'[{table}] "{word}" is not a setting'
        if near is None:
            has = _and(list(known))
            if table == "store":
                has += ", and a named store is a [store.NAME] table"
            return self.fault(key, f"{written}; [{table}] has {has}")
        return self.fault(key, f'{written}; did you mean "{near}"?')

    def check(self, doc: Mapping[str, Any], path: Path, given: bool) -> Config:
        values: dict[str, Any] = {}
        entries: Any = None
        for key, value in doc.items():
            if key not in _TOP:
                tables = [*_SETTINGS, _IMPORT]
                if isinstance(value, dict):
                    raise self.unknown((key,), tables, None, whole=True)
                if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
                    raise self.unknown((key,), tables, None, array=True)
                raise self.unknown((key,), list(_TOP), None)
            if key == "version":
                self.version(value)
                continue
            if key == _IMPORT:
                entries = self.import_tables(value)
                continue
            if not isinstance(value, dict):
                raise self.fault((key,), f"{key} is a table, written [{key}] on a line of its own")
            values.update(getattr(self, f"table_{key}")(value))
        if "version" not in doc:
            raise ConfigError(
                f"{self.shown} has no version line; a config opens with version = {VERSION}"
            )
        imports: tuple[ImportEntry, ...] = ()
        if entries is not None:
            # after [signals], whose field mappings may stand in for a reader's required options
            imports = self.table_import(entries, values.get("signals", {}))
        folder = path.parent
        store = values.get("store")
        return Config(
            path=path,
            shown=self.shown,
            given=given,
            text=self.text,
            store=None if store is None else _from(folder, store),
            named={name: _from(folder, p) for name, p in values.get("named", {}).items()},
            events=values.get("events"),
            max_mde=values.get("max_mde"),
            max_mde_hr=values.get("max_mde_hr"),
            fail_on=values.get("fail_on"),
            max_change=values.get("max_change", {}),
            names_from=values.get("names_from", "target"),
            upload=values.get("upload", {}),
            signals=values.get("signals", {}),
            budgets=values.get("budgets"),
            rules=values.get("rules", ()),
            imports=imports,
        )

    def version(self, value: Any) -> None:
        key = ("version",)
        if type(value) is not int:
            raise self.fault(key, f"version is the whole number {VERSION}, not {_value(value)}")
        if value != VERSION:
            newer = "newer than this Trace" if value > VERSION else "not a version of the config"
            raise self.fault(
                key,
                f"version {value} is {newer}: poisson-trace {poisson_trace.__version__} reads "
                f"version {VERSION}",
            )

    def path(self, key: tuple[str, ...], value: Any) -> str:
        table = ".".join(key[:-1])
        if not isinstance(value, str):
            raise self.fault(
                key, f"[{table}] path is the folder of the store in quotes, not {_value(value)}"
            )
        if not value:
            raise self.fault(key, f"[{table}] path is empty; it names the folder of the store")
        return value

    def table_store(self, table: Mapping[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {"named": {}}
        for key, value in table.items():
            if key == "path":
                out["store"] = self.path(("store", "path"), value)
                continue
            if not isinstance(value, dict):
                raise self.unknown(("store", key), _SETTINGS["store"], "store")
            shown = key if STORE_NAME.fullmatch(key) else _quoted(key)
            if not STORE_NAME.fullmatch(key):
                raise self.fault(
                    ("store", key), f"[store.{shown}] is not a store name: {STORE_NAME_RULE}"
                )
            for inner in value:
                if inner != "path":
                    raise self.unknown(("store", key, inner), _SETTINGS["store"], f"store.{key}")
            if "path" not in value:
                raise self.fault(
                    ("store", key),
                    f"[store.{key}] has no path; a named store is "
                    'written path = "FOLDER" under its table',
                )
            out["named"][key] = self.path(("store", key, "path"), value["path"])
        return out

    def table_events(self, table: Mapping[str, Any]) -> dict[str, Any]:
        for key in table:
            if key != "failed":
                raise self.unknown(("events", key), _SETTINGS["events"], "events")
        if "failed" not in table:
            return {}
        failed = table["failed"]
        at = ("events", "failed")
        rule = '[events] failed is a list of one or more outcomes in quotes, such as ["unsolved"]'
        if not isinstance(failed, list):
            raise self.fault(at, f"{rule}, not {_value(failed)}")
        if not failed:
            raise self.fault(at, f"{rule}, and this one is empty")
        seen: set[str] = set()
        for item in failed:
            if not isinstance(item, str):
                raise self.fault(at, f"{rule}; {_value(item)} is not in quotes")
            if not item:
                raise self.fault(at, f'{rule}; "" is no outcome')
            if item in seen:
                raise self.fault(at, f"{rule}, each once; {_quoted(item)} is listed twice")
            seen.add(item)
        return {"events": tuple(failed)}

    def table_check(self, table: Mapping[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in table.items():
            at = ("check", key)
            if key == "max_mde":
                if not _number(value) or not 0.0 < value < 1.0:
                    raise self.fault(
                        at,
                        "[check] max_mde is a number strictly between 0 and 1, "
                        f"such as 0.2 for twenty points, not {_value(value)}",
                    )
                out["max_mde"] = float(value)
            elif key == "max_mde_hr":
                if not _number(value) or not value > 1.0:
                    raise self.fault(
                        at,
                        f"[check] max_mde_hr is a number above 1, such as 1.5, not {_value(value)}",
                    )
                out["max_mde_hr"] = float(value)
            elif key == "fail_on":
                out["fail_on"] = self.fail_on(value)
            elif key == "max_change":
                out["max_change"] = self.max_change(value)
            else:
                raise self.unknown(at, _SETTINGS["check"], "check")
        return out

    def max_change(self, value: Any) -> dict[str, float]:
        """``[check] max_change``: a table of measure to ``"N%"``, each read as the flag
        ``--max-change measure=N%`` is (TF23's ``parse_max_change``), in the measures' order."""
        from poisson_trace.stats.continuous import MEASURES, parse_max_change

        rule = (
            '[check] max_change is a table of measure = "N%", such as '
            '{ wall_time_s = "10%" }, each a share of the old mean'
        )
        key = ("check", "max_change")
        if not isinstance(value, dict):
            raise self.fault(key, f"{rule}, not {_value(value)}")
        held: dict[str, float] = {}
        for measure, share in value.items():
            if not isinstance(share, str):
                raise self.fault(
                    (*key, measure),
                    f"{rule}; {measure} is given {_value(share)}, not a percentage in quotes",
                )
            try:
                name, fraction = parse_max_change(f"{measure}={share}")
            except ValueError as e:
                raise self.fault((*key, measure), f"{rule}; {e}") from None
            held[name] = fraction
        return {m: held[m] for m in MEASURES if m in held}

    def fail_on(self, value: Any) -> tuple[str, ...]:
        rule = (
            '[check] fail_on is a list drawn from "failed-more" and "too-small", each at most '
            'once, such as ["failed-more"] ([] never fails)'
        )
        key = ("check", "fail_on")
        if not isinstance(value, list):
            raise self.fault(key, f"{rule}, not {_value(value)}")
        for i, item in enumerate(value):
            if item not in FAIL_ON:
                raise self.fault(key, f"{rule}; {_value(item)} is not one of them")
            if item in value[:i]:
                raise self.fault(key, f"{rule}; {_value(item)} is listed twice")
        return tuple(value)

    def table_names(self, table: Mapping[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in table.items():
            if key != "from":
                raise self.unknown(("names", key), _SETTINGS["names"], "names")
            if value not in FORMS:
                raise self.fault(
                    ("names", "from"),
                    '[names] from is one of "target", "date" '
                    f'and "target-date", not {_value(value)}',
                )
            out["names_from"] = value
        return out

    def table_upload(self, table: Mapping[str, Any]) -> dict[str, Any]:
        upload: dict[str, Any] = {}
        for key, value in table.items():
            at = ("upload", key)
            if key == "enabled":
                if not isinstance(value, bool):
                    raise self.fault(at, f"[upload] enabled is true or false, not {_value(value)}")
            elif key == "url":
                if not isinstance(value, str) or not _destination(value):
                    raise self.fault(
                        at,
                        "[upload] url is an https:// address, or an http:// "
                        "address on this machine (localhost, 127.0.0.1 or ::1), not "
                        f"{_value(value)}",
                    )
            elif key == "token_env":
                if (
                    not isinstance(value, str)
                    or not _VARIABLE.fullmatch(value)
                    or not ("TOKEN" in value or "API_KEY" in value)
                ):
                    raise self.fault(
                        at,
                        "[upload] token_env is the name of the environment "
                        f"variable that holds the token, such as {TOKEN_ENV}, and "
                        f"holds TOKEN or API_KEY; not {_value(value)}",
                    )
            else:
                raise self.unknown(at, _SETTINGS["upload"], "upload")
            upload[key] = value
        return {"upload": upload}


    def table_signals(self, table: Mapping[str, Any]) -> dict[str, Any]:
        signals: dict[str, Any] = {}
        out: dict[str, Any] = {"signals": signals}
        for key, value in table.items():
            at = ("signals", key)
            if key in _FIELDS:
                if not isinstance(value, str) or not value:
                    raise self.fault(
                        at,
                        f"[signals] {key} is the field's or column's name in quotes, not "
                        f"{_value(value)}",
                    )
                signals[key] = value
            elif key == "cut":
                if not _number(value):
                    raise self.fault(at, f"[signals] cut is a number, not {_value(value)}")
                signals[key] = float(value)
            elif key == "budgets":
                if not isinstance(value, dict):
                    raise self.fault(
                        at,
                        "[signals] budgets is a table, written [signals.budgets] on a line of "
                        "its own",
                    )
                out["budgets"] = self.budgets(value)
            else:
                raise self.unknown(at, _SETTINGS["signals"][:-1], "signals")
        return out

    def budgets(self, table: Mapping[str, Any]) -> Budgets:
        """``[signals.budgets]``: each a number from zero; the token budget a whole number."""
        kept: dict[str, Any] = {}
        for key, value in table.items():
            at = ("signals", "budgets", key)
            if key not in BUDGETS:
                meant = _BUDGET_ALIASES.get(key) or nearest(key, BUDGETS)
                if meant is not None:
                    raise self.fault(
                        at, f'[signals.budgets] "{key}" is not a budget; did you mean "{meant}"?'
                    )
                raise self.fault(
                    at,
                    f'[signals.budgets] "{key}" is not a budget; the budgets are '
                    f"{_and(list(BUDGETS))}",
                )
            if key == "max_total_tokens":
                if type(value) is not int or value < 0:
                    raise self.fault(
                        at,
                        f"[signals.budgets] max_total_tokens is a whole number of tokens from 0, "
                        f"not {_value(value)}",
                    )
                kept[key] = value
            else:
                if not _number(value) or value < 0:
                    raise self.fault(
                        at, f"[signals.budgets] {key} is a number from 0, not {_value(value)}"
                    )
                kept[key] = float(value)
        return Budgets(**kept)

    def table_taxonomy(self, table: Mapping[str, Any]) -> dict[str, Any]:
        for key, value in table.items():
            if key != "rules":
                raise self.unknown(("taxonomy", key), _SETTINGS["taxonomy"], "taxonomy")
            if not isinstance(value, list) or not all(isinstance(r, dict) for r in value):
                raise self.fault(
                    ("taxonomy", "rules"),
                    "[taxonomy] rules is an array of tables, each written [[taxonomy.rules]] on a "
                    f"line of its own, not {_value(value)}",
                )
        rules = [self.rule(i, rule) for i, rule in enumerate(table.get("rules", []))]
        return {"rules": tuple(rules)}

    def rule(self, i: int, table: Mapping[str, Any]) -> Rule:
        """One ``[[taxonomy.rules]]``: a failure_kind and at least one when_ condition."""
        at = ("taxonomy", "rules", i)
        known = ("failure_kind", *CONDITIONS)
        for key, value in table.items():
            if key not in known:
                raise self.unknown((*at, key), known, "taxonomy.rules")
            if key == "failure_kind" and value not in FAILURE_KINDS:
                raise self.fault(
                    (*at, key),
                    f"[[taxonomy.rules]] failure_kind is one of {_and(list(FAILURE_KINDS))}, "
                    f"not {_value(value)}",
                )
            if key in ("when_error_matches", "when_span_kind") and not isinstance(value, str):
                raise self.fault(
                    (*at, key), f"[[taxonomy.rules]] {key} is text in quotes, not {_value(value)}"
                )
            if key == "when_metric_below" and not isinstance(value, dict):
                raise self.fault(
                    (*at, key),
                    '[[taxonomy.rules]] when_metric_below is { metric = "NAME", cut = X }, not '
                    f"{_value(value)}",
                )
        if "failure_kind" not in table:
            raise self.fault(at, "[[taxonomy.rules]] a rule names the failure_kind it gives")
        if not any(c in table for c in CONDITIONS):
            raise self.fault(
                at, f"[[taxonomy.rules]] a rule needs at least one of {_and(list(CONDITIONS))}"
            )
        try:
            return Rule(**{k: table[k] for k in known if k in table})
        except (TypeError, ValueError) as e:
            key = next((c for c in CONDITIONS if c in table), "failure_kind")
            said = str(e)
            for c in CONDITIONS:
                if said.startswith(c):
                    key = c
            raise self.fault((*at, key), f"[[taxonomy.rules]] {said}") from None


    # ---------- [[import]] ----------

    def import_tables(self, value: Any) -> list[Mapping[str, Any]]:
        """``[[import]]`` as an array of tables; one table, or anything else, is refused."""
        at = (_IMPORT,)
        if isinstance(value, dict):
            raise self.fault(
                at,
                f"[{_IMPORT}] is one table; the files to import are written as [[{_IMPORT}]] "
                "tables, one for each file",
            )
        if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
            raise self.fault(
                at,
                f"{_IMPORT} is written as [[{_IMPORT}]] tables, one for each file to import, "
                f"not {_value(value)}",
            )
        return list(value)

    def table_import(
        self, entries: Sequence[Mapping[str, Any]], signals: Mapping[str, Any]
    ) -> tuple[ImportEntry, ...]:
        """Every ``[[import]]`` entry: ``file``, ``tool`` and ``name`` each required; the tool
        a reader in the install; the file a relative path inside the repository and not an
        address; the name one the import accepts, used once; the reader's options checked as
        its flags are, with what ``[signals]`` stands in for counted as given."""
        from poisson_trace.ingest.cli import present, reader_options, stand_ins

        here = present()
        held: list[ImportEntry] = []
        seen: dict[str, int] = {}
        for i, table in enumerate(entries):
            at = (_IMPORT, i)
            line = self.lines.get(at) or self.lines.get((_IMPORT,)) or 0
            for key in _ENTRY:
                if key not in table:
                    raise self.fault(
                        at, f"[[{_IMPORT}]] has no {key}; each entry names its file, tool and name"
                    )
                if not isinstance(table[key], str) or not table[key]:
                    raise self.fault(
                        (*at, key),
                        f"[[{_IMPORT}]] {key} is {_ENTRY_IS[key]}, in quotes, not "
                        f"{_value(table[key])}",
                    )
            file, tool, name = (str(table[k]) for k in _ENTRY)
            if tool not in here:
                raise self.fault(
                    (*at, "tool"),
                    f'[[{_IMPORT}]] tool "{tool}" is not in this install; the readers here are '
                    f"{_and(list(here))}",
                )
            self.import_file(at, file)
            hole = import_name_refusal(name)
            if hole is not None:
                raise self.fault((*at, "name"), f"[[{_IMPORT}]] name: {hole}")
            if name in seen:
                raise self.fault(
                    at,
                    f'[[{_IMPORT}]] name "{name}" is used by the entry on line {seen[name]} '
                    "too; each entry's run has a name of its own",
                )
            seen[name] = line
            options = self.import_options(at, tool, table, reader_options(tool))
            given = {*stand_ins(tool, signals), *options}
            for dest, option in reader_options(tool).items():
                if option.required and dest not in given:
                    raise self.fault(
                        at,
                        f"[[{_IMPORT}]] a {tool} entry needs {dest} (the reader's "
                        f"{option.flag}), and nothing in [signals] stands in for it",
                    )
            held.append(ImportEntry(file, tool, name, options, line))
        return tuple(held)

    def import_file(self, at: tuple[Any, ...], file: str) -> None:
        key = (*at, "file")
        puller = file.split(":", 1)[0] if ":" in file else None
        if puller in PULLERS:
            raise self.fault(
                key,
                f'[[{_IMPORT}]] file "{file}" is an address to pull from, and the {puller} '
                "puller is not in this install; save the export as a file and name that file",
            )
        normal = os.path.normpath(file)
        if os.path.isabs(file) or normal == ".." or normal.startswith(".." + os.sep):
            raise self.fault(
                key,
                f'[[{_IMPORT}]] file "{file}" is not a relative path inside the repository; '
                f"it is read from the folder that holds {self.shown}",
            )

    def import_options(
        self, at: tuple[Any, ...], tool: str, table: Mapping[str, Any], spec: Mapping[str, Any]
    ) -> dict[str, Any]:
        """The reader's options of one entry, each checked as its flag is."""
        options: dict[str, Any] = {}
        for key, value in table.items():
            if key in _ENTRY:
                continue
            where = (*at, key)
            if key in _IMPORTS_OWN:
                raise self.fault(
                    where,
                    f'[[{_IMPORT}]] "{key}" is the import\'s own flag, not an option of the '
                    f"{tool} reader; the entry's file, run name and store are its file, name, "
                    "and the store init writes to",
                )
            if key not in spec:
                near = nearest(key, list(spec))
                if near is not None:
                    raise self.fault(
                        where,
                        f'[[{_IMPORT}]] "{key}" is not an option of the {tool} reader; did you '
                        f'mean "{near}"?',
                    )
                raise self.fault(
                    where,
                    f'[[{_IMPORT}]] "{key}" is not an option of the {tool} reader; a {tool} entry '
                    f"has file, tool, name and the options {_and(list(spec))}",
                )
            option = spec[key]
            if not option.takes_value:
                if not isinstance(value, bool):
                    raise self.fault(
                        where, f"[[{_IMPORT}]] {key} is true or false, not {_value(value)}"
                    )
            elif option.many:
                if not isinstance(value, list):
                    raise self.fault(
                        where,
                        f'[[{_IMPORT}]] {key} is a list of values in quotes, such as ["x", "y"], '
                        f"not {_value(value)}",
                    )
                for item in value:
                    if not isinstance(item, str):
                        raise self.fault(
                            where,
                            f"[[{_IMPORT}]] {key} is a list of values in quotes, and "
                            f"{_value(item)} is not in quotes",
                        )
            elif key == "cut":
                recorded = tool == "deepeval"
                if not (_number(value) or (recorded and value == "recorded")):
                    takes = 'a number or "recorded"' if recorded else "a number"
                    raise self.fault(where, f"[[{_IMPORT}]] cut is {takes}, not {_value(value)}")
            elif option.choices:
                if not isinstance(value, str) or value not in option.choices:
                    raise self.fault(
                        where,
                        f"[[{_IMPORT}]] {key} is one of {_and(list(option.choices))}, not "
                        f"{_value(value)}",
                    )
            elif key == "prompt":
                if not (isinstance(value, str) and value) and type(value) is not int:
                    raise self.fault(
                        where,
                        f"[[{_IMPORT}]] prompt is the prompt's label in quotes, or its number "
                        f"counting from 1, not {_value(value)}",
                    )
            elif not isinstance(value, str) or not value:
                raise self.fault(
                    where, f"[[{_IMPORT}]] {key} is {option.takes} in quotes, not {_value(value)}"
                )
            options[key] = value
        if options.get("below") is True and options.get("above") is True:
            raise self.fault(
                (*at, "above"), f"[[{_IMPORT}]] below and above are two sides of a cut; give one"
            )
        return options


# what each of an entry's own keys is, for a refusal
_ENTRY_IS = {
    "file": "the file's path, relative to the config's folder",
    "tool": "the name of a reader in the install",
    "name": "the run's name",
}


def _destination(url: str) -> bool:
    try:
        parts = urlsplit(url)
        host = parts.hostname
        _ = parts.port  # a port that is not a number is refused here
    except ValueError:
        return False
    if parts.scheme == "https":
        return bool(host)
    return parts.scheme == "http" and loopback(host)


def _from(folder: Path, path: str) -> str:
    """A store path the file holds, as the current folder reads it: joined to the file's folder,
    and written short (``conf/../runs`` as ``runs``) when no link stands on the way, which would
    make the short form name another folder."""
    if os.path.isabs(path) or str(folder) in ("", "."):
        return path
    joined = os.path.join(str(folder), path)
    if os.path.realpath(folder) == os.path.abspath(folder):
        return os.path.normpath(joined)
    return joined


def beside(config_path: Path, name: str) -> str:
    """The folder ``name`` beside the config file, as the current folder reads it."""
    return _from(config_path.parent, name)


def written_path(config_path: Path, typed: str) -> str:
    """A store path typed here, as the config file's folder reads it."""
    folder = str(config_path.parent)
    if os.path.isabs(typed) or folder in ("", "."):
        return typed
    return os.path.relpath(os.path.abspath(typed), os.path.abspath(folder))


# ---------- writing the file ----------


def number(value: float) -> str:
    """A number as TOML writes it."""
    return repr(float(value))


def text_of(
    stores: Sequence[tuple[str | None, str]],
    events: Sequence[str],
    *,
    max_mde: float | None = None,
    max_mde_hr: float | None = None,
    fail_on: Sequence[str] | None = None,
    names_from: str = "target",
) -> str:
    """A version 1 config, byte for byte: the header, the version, each store (the unnamed one
    first), the failures when there are any, the check's ceilings and gate that were given, and
    how runs are named."""
    blocks = [HEADER + f"version = {VERSION}\n"]
    for name, path in stores:
        table = "store" if name is None else f"store.{name}"
        blocks.append(f"[{table}]\npath = {toml_string(path)}\n")
    if events:
        blocks.append(events_block(events))
    check = []
    if max_mde is not None:
        check.append(f"max_mde = {number(max_mde)}")
    if max_mde_hr is not None:
        check.append(f"max_mde_hr = {number(max_mde_hr)}")
    if fail_on is not None:
        check.append("fail_on = [" + ", ".join(toml_string(f) for f in fail_on) + "]")
    if check:
        blocks.append("[check]\n" + "\n".join(check) + "\n")
    blocks.append(f"[names]\nfrom = {toml_string(names_from)}\n")
    return "\n".join(blocks)


def events_block(events: Sequence[str]) -> str:
    return "[events]\nfailed = [" + ", ".join(toml_string(e) for e in events) + "]\n"


def appended(text: str, block: str) -> str:
    """``text`` with ``block`` after everything it holds, a blank line between."""
    if not text:
        return block
    return text + ("" if text.endswith("\n") else "\n") + "\n" + block


def write_config_file(path: Path, shown: str, text: str) -> None:
    """Write the file whole: written beside it, then moved over it, so that a reader finds the
    old file or the new one and nothing between."""
    partial = path.with_name(path.name + ".partial")
    try:
        with open(partial, "w", encoding="utf-8", newline="\n") as config_file:
            config_file.write(text)
        os.replace(partial, path)
    except OSError as e:
        raise look.Refused(f"cannot write {shown} ({look.why(e)}); nothing was written") from e
    finally:
        with contextlib.suppress(OSError):
            partial.unlink(missing_ok=True)
