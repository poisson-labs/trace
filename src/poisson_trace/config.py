"""The config file, ``trace.toml``: where the results are, what counts as a failure, the
check's ceilings, how runs are named when no name was given, and where an upload goes.

Read from the current folder, or from the file ``--config PATH`` names, and never from a folder
above. A store path in it is read from the folder that holds the file. A file that is not a
version 1 config is refused in one sentence naming the file and the line the fault is written
on, before anything else is read or written. ``poisson-trace init`` writes it; a user may edit it
by hand, and ``poisson-trace doctor`` checks it.

Standard library only: ``tomllib`` reads it, and nothing here reads a store.
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
from poisson_trace.names import toml_string

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
    "check": ("max_mde", "max_mde_hr", "fail_on"),
    "names": ("from",),
    "upload": ("enabled", "url", "token_env"),
}
_TOP = ("version", *_SETTINGS)
# the most edits between a word written and the setting it is taken to mean
_NEAR = 2
_VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class ConfigError(look.Refused):
    """The config file is not one: refused in one sentence, exit 1."""


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
    names_from: str = "target"
    upload: Mapping[str, Any] = field(default_factory=dict)

    @property
    def folder(self) -> Path:
        return self.path.parent

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


def _lines(text: str) -> dict[tuple[str, ...], int]:
    """Every table and setting the text writes, by its full key, with the line it is first
    written on. Lines inside a string of several lines are not read as settings."""
    found: dict[tuple[str, ...], int] = {}
    table: tuple[str, ...] = ()
    open_quote: str | None = None
    for n, line in enumerate(text.splitlines(), start=1):
        if open_quote is not None:
            if open_quote in line:
                open_quote = None
            continue
        header = _TABLE.match(line)
        if header is not None:
            table = _parts(header.group(1))
            found.setdefault(table, n)
            continue
        setting = _ASSIGNED.match(line)
        if setting is None:
            continue
        key = table + _parts(setting.group(1))
        for at in range(len(table) + 1, len(key) + 1):
            found.setdefault(key[:at], n)
        rest = setting.group(2)
        for quote in ('"""', "'''"):
            if rest.count(quote) % 2 == 1:
                open_quote = quote
                break
    return found


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

    def fault(self, key: Sequence[str], why: str) -> ConfigError:
        at = None
        for n in range(len(key), 0, -1):
            at = self.lines.get(tuple(key[:n]))
            if at is not None:
                break
        where = f"{self.shown} line {at}" if at is not None else self.shown
        return ConfigError(f"{where}: {why}")

    def unknown(
        self, key: Sequence[str], known: Sequence[str], table: str | None, *, whole: bool = False
    ) -> ConfigError:
        """A table or setting version 1 does not have, with the one nearest it, if any is."""
        word = key[-1]
        near = nearest(word, known)
        if table is None:
            written = f"[{word}] is not a table" if whole else f'"{word}" is not a setting'
            if near is None:
                return self.fault(
                    key,
                    f"{written}; a config has version and the tables "
                    f"{_and([f'[{k}]' for k in _SETTINGS])}",
                )
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
        for key, value in doc.items():
            if key not in _TOP:
                if isinstance(value, dict):
                    raise self.unknown((key,), list(_SETTINGS), None, whole=True)
                raise self.unknown((key,), list(_TOP), None)
            if key == "version":
                self.version(value)
                continue
            if not isinstance(value, dict):
                raise self.fault((key,), f"{key} is a table, written [{key}] on a line of its own")
            values.update(getattr(self, f"table_{key}")(value))
        if "version" not in doc:
            raise ConfigError(
                f"{self.shown} has no version line; a config opens with version = {VERSION}"
            )
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
            names_from=values.get("names_from", "target"),
            upload=values.get("upload", {}),
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
            else:
                raise self.unknown(at, _SETTINGS["check"], "check")
        return out

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
