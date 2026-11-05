"""The ``[[import]]`` entries of a config at run time: which store their runs go to, which
entries are still pending, how an entry is read with its reader without writing anything, and
the import command that writes it. ``doctor --setup`` and ``init``'s hand-over read entries
through here; ``doctor``'s next command after the hand-over comes from here too.

The config itself (``config.py``) checks an entry's keys, types and choices and opens nothing;
this module opens the files, through the readers, and reads the stores through Prove.
"""

from __future__ import annotations

import argparse
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poisson_trace import config, look, names
from poisson_trace.config import Config, ImportEntry
from poisson_trace.ingest.cut import MET, MISSED
from poisson_trace.ingest.rows import Refusal, Run

# where an import from init writes its runs: beside the config
IMPORTED_STORE = "trace-store"
# the name verbs reach the imports' store by, beside a Prove store
IMPORTED = "imported"


@dataclass(frozen=True)
class ImportsStore:
    """The store the imports go to: ``[store.imported]`` when the config names it; else
    ``[store]`` when it is ``trace-store`` beside the config or holds no run Prove stored; else
    ``trace-store`` beside the config, which ``init`` adds as ``[store.imported]`` beside a
    Prove store, or as ``[store]`` when the config names none."""

    path: str  # as the current folder reads it
    table: str | None  # the table init adds for it: "store", "store.imported", or None
    name: str | None  # what --store carries to reach it: None for [store], else its name
    # whether it may hold no run yet: the imports' store is empty until the first import
    may_be_empty: bool


def imports_store(held: Config) -> ImportsStore:
    beside = config.beside(held.path, IMPORTED_STORE)
    if IMPORTED in held.named:
        return ImportsStore(held.named[IMPORTED], None, IMPORTED, True)
    if held.store is not None:
        if same_folder(held.store, beside):
            return ImportsStore(held.store, None, None, True)
        if not prove_stored(held.store):
            return ImportsStore(held.store, None, None, False)
        return ImportsStore(beside, "store.imported", IMPORTED, True)
    return ImportsStore(beside, "store", None, True)


def same_folder(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normpath(os.path.abspath(a)) == os.path.normpath(os.path.abspath(b))


def runs_of(store: str) -> list[str]:
    from poisson_prove.store import Store

    try:
        return [r for r in Store(store).runs() if not r.startswith(".")]
    except OSError:
        return []


def prove_stored(store: str) -> bool:
    """Whether the store holds a run Prove stored itself, which an import did not write."""
    from poisson_prove.store import Store

    held = Store(store)
    for run_id in runs_of(store):
        try:
            backend = str(getattr(held.manifest(run_id), "backend", "") or "")
        except Exception:
            continue
        if not backend.startswith(names.IMPORTED):
            return True
    return False


def answered(store: str, form: str = "target") -> set[str]:
    """Every word a run of the store answers to: its id, and its name."""
    from poisson_prove.store import Store

    held = runs_of(store)
    if not held:
        return set()
    try:
        index = names.index(Store(store), held, store, lenient=True, form=form)
    except names.Damaged:
        return set(held)
    words = {r.name for r in index.runs} | {r.run_id for r in index.runs}
    return words | set(index.unreadable)


def pending(held: Config, store: str) -> list[ImportEntry]:
    """The entries no run of the imports' store answers to, in the config's order."""
    taken = answered(store, held.names_from)
    return [e for e in held.imports if e.name not in taken]


def first_pair(held: Config) -> tuple[ImportEntry, ImportEntry] | None:
    """After the hand-over, the first two entries of the first tool with two or more, when
    every entry is imported: the pair the first fix-check compares."""
    if not held.imports:
        return None
    if pending(held, imports_store(held).path):
        return None
    for tool in dict.fromkeys(e.tool for e in held.imports):
        mine = [e for e in held.imports if e.tool == tool]
        if len(mine) >= 2:
            return mine[0], mine[1]
    return None


# ---------- reading an entry ----------


def options_of(held: Config, entry: ImportEntry) -> dict[str, Any]:
    """The entry's options with what ``[signals]`` stands in for filled in where the entry
    leaves it out; a cut from ``[signals]`` with no side in the entry reads below."""
    from poisson_trace.ingest.importing import stand_ins

    options: dict[str, Any] = {}
    filled = stand_ins(entry.tool, held.signals)
    for dest, value in filled.items():
        if dest in entry.options:
            continue
        options[dest] = value
        if dest == "cut" and "below" not in entry.options and "above" not in entry.options:
            options["below"] = True
    options.update(entry.options)
    return options


def file_of(held: Config, entry: ImportEntry) -> str:
    """The entry's file as the current folder reads it."""
    return config.beside(held.path, entry.file)


def namespace(held: Config, entry: ImportEntry, files: Sequence[str]) -> argparse.Namespace:
    """What the reader reads: its parser's defaults, then the options as flags give them."""
    from poisson_trace.ingest.importing import reader_defaults

    values: dict[str, Any] = dict(reader_defaults(entry.tool))
    for dest, value in options_of(held, entry).items():
        if isinstance(value, list):
            values[dest] = [str(v) for v in value]
        elif isinstance(value, bool):
            values[dest] = value
        elif dest == "cut":
            values[dest] = value if isinstance(value, str) else config.number(value)
        else:
            values[dest] = str(value)
    values.update(
        files=list(files),
        run=entry.name,
        started=None,
        verdicts=None,
        signals=dict(held.signals),
    )
    return argparse.Namespace(**values)


_FLAG = re.compile(r"--([a-z][a-z-]*)")


def _as_keys(said: str) -> str:
    """A reader's words with its flags as the entry's keys (``--case-column`` as
    ``case_column``), since the entry writes keys, not flags."""
    return _FLAG.sub(lambda m: m.group(1).replace("-", "_"), said)


def read(held: Config, entry: ImportEntry) -> Run:
    """The entry read with its reader, writing nothing: the file (or the folder, through the
    folder resolver, as the named tool's files alone), the reader's own usage rules, then its
    read; refused with the entry's file first when any of it fails."""
    from poisson_trace.ingest import importing as importer
    from poisson_trace.ingest.folder import resolve
    from poisson_trace.ingest.writer import runs_in

    path = file_of(held, entry)
    where = f"the [[import]] entry on line {entry.line}"
    try:
        if not os.path.lexists(path):
            raise Refusal(f"is not there ({where} names it)")
        if os.path.isdir(path):
            if runs_in(Path(path)):
                raise Refusal(
                    f"is a store Prove wrote, not a file to import; name it under [store], not "
                    f"[[import]] ({where})"
                )
            found = resolve(path, entry.tool)
            if found.kind in ("run", "store"):
                raise Refusal(
                    f"is a run Prove stored, not a file to import; name its store under [store], "
                    f"not [[import]] ({where})"
                )
            files = [str(f) for f in found.files]
        else:
            files = [path]
        ns = namespace(held, entry, files)
        module = importer.reader(entry.tool)
        wrong = getattr(module, "usage", None)
        said = wrong(ns) if wrong is not None else None
        if said is not None:
            raise Refusal(f"{_as_keys(said)} ({where})")
        run: Run = module.read(ns)
        importer.checked(run)
        range_fault = out_of_range(run)
        if range_fault is not None:
            raise Refusal(range_fault)
    except Refusal as e:
        raise Refusal(f"{entry.file}: {_as_keys(str(e))}", *e.nexts) from e
    return run


def out_of_range(run: Run) -> str | None:
    """A cut every scored row misses, or every one meets: the cut is outside the scores."""
    cut = run.declared.get("cut")
    if not isinstance(cut, (int, float)) or isinstance(cut, bool):
        return None
    scored = [row for row in run.rows if row.score is not None]
    if not scored:
        return None
    outcomes = {row.outcome for row in scored}
    if outcomes not in ({MISSED}, {MET}):
        return None
    low = min(row.score for row in scored if row.score is not None)
    high = max(row.score for row in scored if row.score is not None)
    what = run.declared.get("metric") or run.declared.get("score_column") or "the"
    every = "misses" if outcomes == {MISSED} else "meets"
    return (
        f"at the cut {config.number(cut)} every scored row {every} it; the {what} scores run "
        f"from {low:g} to {high:g}, so the cut is out of their range"
    )


def said(entry: ImportEntry, run: Run) -> str:
    """One line on a pending entry: the file, the tool, the rows, a scored file's metric and
    cut, and that it is not imported yet."""
    scored = ""
    metric = run.declared.get("metric") or run.declared.get("score_column")
    cut = run.declared.get("cut")
    if metric is not None and isinstance(cut, (int, float)) and not isinstance(cut, bool):
        scored = f"{metric} at {config.number(cut)}, "
    rows = f"{look.count(len(run.rows))} {'row' if len(run.rows) == 1 else 'rows'}"
    return f"{entry.file}: {entry.tool}, {rows}, {scored}not imported yet"


# ---------- the command that writes an entry ----------


def command(held: Config, entry: ImportEntry, store: str) -> list[str]:
    """``poisson-trace import TOOL FILE --store STORE --run NAME`` and the entry's options as
    the reader's flags, with what ``[signals]`` stands in for spelt out."""
    words = ["poisson-trace", "import", entry.tool, entry.file]
    words += _pair("--store", store)
    words += _pair("--run", entry.name)
    for dest, value in options_of(held, entry).items():
        flag = "--" + dest.replace("_", "-")
        if isinstance(value, bool):
            if value:
                words.append(flag)
        elif isinstance(value, list):
            for item in value:
                words += _pair(flag, str(item))
        elif dest == "cut" and not isinstance(value, str):
            words += _pair(flag, config.number(value))
        else:
            words += _pair(flag, str(value))
    return words


def _pair(flag: str, value: str) -> list[str]:
    return [f"{flag}={value}"] if value.startswith("-") else [flag, value]


def shell_line(words: Sequence[str]) -> str:
    """The words as one line a POSIX shell reads back."""
    out = []
    for word in words:
        if word.startswith("--") and "=" in word:
            flag, value = word.split("=", 1)
            out.append(f"{flag}={look.word(value)}")
        elif word.startswith("--"):
            out.append(word)
        else:
            out.append(look.word(word))
    return " ".join(out)
