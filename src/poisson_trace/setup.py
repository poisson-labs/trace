"""``poisson-trace init``: the guided setup.

It finds the results already in the current folder's tree (the stores Prove wrote, and the
result files of the readers in the install: DeepEval's test runs, tables, JUnit reports), asks
which store to start with when there are several, or offers to import the result files when
there is no store, asks which outcomes count as a failure, shows the runs' names, and writes
``trace.toml`` once, after the last answer. It prints the same setup as one command that asks
nothing, and the first command to run next.

On a ``trace.toml`` with ``[[import]]`` entries not imported yet, as the person's coding agent
writes one (``init --agent``), it shows the stores, the failures and the pending files, asks
whether to import them, imports the pending ones into the imports' store (``trace-store``
beside the config, or the store the config names for them) and writes the config once more,
keeping every line and adding the store's table when the config does not name it.

Every read of a store goes through Prove's ``Store``: listing a store reads its runs' records
alone, and of the store chosen the rows of the newest 20 runs are read for their outcomes and
nothing else. Nothing is written under any store but the runs of an import the user agreed to;
no host is contacted. The questions and the listing go to stderr and are answered on stdin a
line at a time; stdout holds the summary, which the command line prints, as text or as JSON.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import re
import shutil
import sys
from collections import Counter, deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from poisson_trace import config, imports, look, names
from poisson_trace.imports import IMPORTED_STORE
from poisson_trace.look import count

# the outcomes whose names mean success, which the failure question's default leaves out
SUCCESS_WORDS: tuple[str, ...] = (
    "solved",
    "resolved",
    "passed",
    "met",
    "ok",
    "success",
    "fixed",
    "planned",
    "cited",
    "survived",
    "correct",
    "fresh",
    "fast",
)
# how far the search goes: a store's folder at most six folders below the current one, and at
# most 10,000 entries read in all, files and folders alike
DEPTH = 6
ENTRIES = 10_000
# the most candidate result files (.csv, .jsonl, .json, .xml, .eval) opened to see whether a
# reader reads them
CANDIDATES = 200
RESULT_FILES = (".csv", ".jsonl", ".json", ".xml", ".eval")
# the runs whose outcomes the failure question reads, newest first
NEWEST = 20
# the folders never searched; every other folder whose name opens with a dot is skipped too,
# but for the ones a reader names. ".poisson" is a store's own folder for what Prove and its
# tools write beside the runs (the store descriptor, saved artifacts, the pages), none of it a
# run and none of it a result file to import
SKIPPED = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", ".work", "site-packages", ".poisson"}
)
READERS_FOLDERS = frozenset({".deepeval"})
# the forms --case takes, by reader: DeepEval's three, JUnit's name, promptfoo's variable or
# position
_CASE_FORMS = ("name", "input", "position", "test")
# the targets a store's line names, and the runs' names the summary shows, before "more"
TARGETS_SHOWN = 4
NAMES_SHOWN = 3
STOPPED = "stopped  setup interrupted; nothing was written"
# where a store comes from when nothing here holds results
SWEEP = "poisson-prove sweep … (see https://github.com/poisson-labs/prove)"
_HELP = "poisson-trace init --help"


class Refused(look.Refused):
    """``init`` refuses: one sentence, exit 1, nothing written."""


def _plural(n: int, one: str, many: str) -> str:
    return f"{count(n)} {one if n == 1 else many}"


def _and(words: Sequence[str]) -> str:
    words = list(words)
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def _reach(ns: argparse.Namespace) -> list[str]:
    """What a command carries to read the config this setup writes."""
    return [] if ns.config is None else [look.option("--config", ns.config)]


# ---------- the search ----------


@dataclass(frozen=True)
class StoreRun:
    """A run of a found store, as its record names it."""

    run_id: str
    target_id: str
    created_at: str
    backend: str = ""

    @property
    def tool(self) -> str | None:
        """The tool whose files Trace's import wrote this run from; None for a run Prove
        stored."""
        return (
            self.backend[len(names.IMPORTED) :] if self.backend.startswith(names.IMPORTED) else None
        )


@dataclass
class FoundStore:
    path: str  # as the current folder reads it
    depth: int
    runs: list[StoreRun] = field(default_factory=list)


@dataclass(frozen=True)
class FoundFile:
    path: str
    folder: str
    reader: str
    said: str  # the reader's one line about it
    modified: float


@dataclass
class Found:
    stores: list[FoundStore]
    files: list[FoundFile]
    stopped: bool  # the bound was reached


def present_readers() -> dict[str, Callable[[Path], str | None]]:
    """The readers of the install that say which files they read, each by its name."""
    from poisson_trace.ingest.importing import present, reader

    out = {}
    for name in present():
        module = reader(name)
        if hasattr(module, "looks_like"):
            out[name] = module.looks_like
    return out


def _joined(rel: str, name: str) -> str:
    return name if rel == "" else f"{rel}/{name}"


def search(root: Path) -> Found:
    """The tree under ``root``, read once, breadth first and each folder's entries in name
    order: the stores, and the files a reader of the install reads. A store is a folder holding
    a run folder whose record Prove reads; a run folder is not searched further. No link is
    followed, and no folder is searched past the depth or once the bound is reached."""
    from poisson_prove.store import Store

    readers = present_readers()
    stores: dict[str, FoundStore] = {}
    files: list[FoundFile] = []
    queue: deque[tuple[Path, str, int]] = deque([(root, "", 0)])
    entries = candidates = 0
    stopped = False
    while queue and not stopped:
        folder, rel, depth = queue.popleft()
        listed = []
        try:
            with os.scandir(folder) as scan:
                for entry in scan:
                    if entries >= ENTRIES:
                        stopped = True
                        break
                    entries += 1
                    listed.append(entry)
        except OSError:
            continue
        store = Store(folder)
        for entry in sorted(listed, key=lambda e: e.name):
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name in SKIPPED or (
                        entry.name.startswith(".") and entry.name not in READERS_FOLDERS
                    ):
                        continue
                    run = _run_of(store, entry.name)
                    if run is not None:
                        here = rel or "."
                        stores.setdefault(here, FoundStore(here, depth)).runs.append(run)
                    elif depth < DEPTH:
                        queue.append((Path(entry.path), _joined(rel, entry.name), depth + 1))
                elif entry.is_file(follow_symlinks=False) and entry.name.lower().endswith(
                    RESULT_FILES
                ):
                    candidates += 1
                    if candidates <= CANDIDATES:
                        found = _read_by(readers, Path(entry.path))
                        if found is not None:
                            reader, said = found
                            modified = entry.stat(follow_symlinks=False).st_mtime
                            files.append(
                                FoundFile(
                                    _joined(rel, entry.name), rel or ".", reader, said, modified
                                )
                            )
            except OSError:
                continue
    ordered = sorted(stores.values(), key=lambda s: (s.depth, s.path))
    return Found(ordered, files, stopped)


def _left_in(files: Sequence[FoundFile]) -> list[FoundFile]:
    """The files found but the JUnit reports that hold no test case, as a runner writes when it
    collected none: each is left out, in one line on stderr naming it."""
    from poisson_trace.ingest import junit

    kept = []
    for f in files:
        if f.reader == "junit" and junit.holds_no_test_case(f.path):
            look.err(
                f"Leaving out {f.path}: a JUnit report with no test case in it, as a runner "
                "writes when it collected no test.\n"
            )
        else:
            kept.append(f)
    return kept


def _read_by(
    readers: Mapping[str, Callable[[Path], str | None]], path: Path
) -> tuple[str, str] | None:
    """The first reader that reads the file, and what it says of it."""
    for name, looks_like in readers.items():
        said = looks_like(path)
        if said is not None:
            return name, said
    return None


def _run_of(store: Any, name: str) -> StoreRun | None:
    """The run in the folder ``name`` of the store, when Prove reads a record there that names
    its run, target and unit."""
    try:
        manifest = store.manifest(name)
    except Exception:
        return None
    return StoreRun(
        manifest.run_id,
        str(manifest.target_id),
        str(manifest.created_at),
        str(getattr(manifest, "backend", "") or ""),
    )


def _day(created_at: str) -> str | None:
    started = names.started(created_at)
    return None if started is None else started.strftime("%Y-%m-%d")


def written_by(runs: Sequence[StoreRun]) -> str:
    """What wrote a store's runs, by the tools Trace's import read them from: "imported from
    ragas", or "" for runs Prove stored alone."""
    tools = list(dict.fromkeys(r.tool for r in runs if r.tool is not None))
    return f"imported from {_and(sorted(tools))}" if tools else ""


def store_line(found: FoundStore) -> str:
    """A store's runs, its targets as names show them (what wrote them, for runs Trace's import
    wrote), and its newest day in UTC."""
    targets = sorted({names.target_of(r.target_id) for r in found.runs if r.tool is None})
    shown = targets[:TARGETS_SHOWN]
    more = len(targets) - len(shown)
    said = ", ".join(shown) + (f" and {count(more)} more" if more > 0 else "")
    days = [d for d in (_day(r.created_at) for r in found.runs) if d is not None]
    parts = [_plural(len(found.runs), "run", "runs"), said, written_by(found.runs)]
    if days:
        parts.append(f"newest {max(days)}")
    return " · ".join(p for p in parts if p)


# the day DeepEval writes into a results-folder file's name, on its own clock
_SAVED_ON = re.compile(r"test_run_(\d{4})(\d{2})(\d{2})_")


def _saved(found: FoundFile) -> str:
    """The day a test run was saved: the one its file's name holds, else the file's own time."""
    named = _SAVED_ON.match(Path(found.path).name)
    if named is not None:
        return "-".join(named.groups())
    return f"{datetime.fromtimestamp(found.modified, UTC):%Y-%m-%d}"


@dataclass
class Listed:
    """The stores the listing numbered, by number."""

    stores: dict[int, FoundStore]


def show(found: Found) -> Listed:
    """The listing, on stderr: the stores, then DeepEval's saved test runs by folder, then the
    other result files by file, numbered on across all of them."""
    stores: dict[int, FoundStore] = {}
    n = 0
    folders: dict[str, list[FoundFile]] = {}
    for f in found.files:
        if f.reader == "deepeval":
            folders.setdefault(f.folder, []).append(f)
    others = [f for f in found.files if f.reader != "deepeval"]
    shown = [s.path for s in found.stores] + list(folders) + [f.path for f in others]
    width = max([len(p) for p in shown] + [24])
    if found.stopped:
        look.err(
            f"  looked at {count(ENTRIES)} entries under . and stopped; give --store PATH to "
            "point at a store elsewhere\n"
        )
    if found.stores:
        look.err(f"  found {_plural(len(found.stores), 'store', 'stores')}:\n")
        for s in found.stores:
            n += 1
            stores[n] = s
            look.err(f"    {n}) {s.path.ljust(width)}  {store_line(s)}\n")
    if folders:
        heading = _plural(len(folders), "DeepEval results folder", "DeepEval results folders")
        look.err(f"  found {heading}:\n")
        for folder, held in folders.items():
            n += 1
            newest = max(_saved(f) for f in held)
            saved = _plural(len(held), "saved test run", "saved test runs")
            look.err(f"    {n}) {folder.ljust(width)}  {saved} · newest {newest}\n")
    if others:
        look.err(f"  found {_plural(len(others), 'result file', 'result files')}:\n")
        for f in others:
            n += 1
            look.err(f"    {n}) {f.path.ljust(width)}  {f.said}\n")
    if not found.stores and not found.files:
        look.err("  found no store and no result file a reader of this install reads\n")
    return Listed(stores)


# ---------- the questions ----------


def _store_question(listed: Listed) -> FoundStore:
    """Which store; Enter takes the first, and an answer that is no store's number is asked
    again."""
    numbers = sorted(listed.stores)
    while True:
        answer = look.ask(f"Which results do you want to start with? [{numbers[0]}]")
        if answer == "":
            return listed.stores[numbers[0]]
        if answer.isascii() and answer.isdigit() and int(answer) in listed.stores:
            return listed.stores[int(answer)]
        look.err(f"  answer with the number of a store: {_and([str(n) for n in numbers])}\n")


def _yes_no(question: str) -> bool:
    while True:
        answer = look.ask(question).lower()
        if answer in ("", "y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        look.err("  answer y or n\n")


@dataclass(frozen=True)
class Outcomes:
    """The episodes of each outcome the runs read carry, and the words for those runs."""

    counts: Mapping[str, int]
    whose: str  # "its 3 runs", "the newest 20 of its 22 runs", "the runs to import"
    one: bool  # whose names a single run

    @property
    def carry(self) -> str:
        return "carries" if self.one else "carry"


def _no_value(x: Any) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def newest_outcomes(store: Any, index: Any, *, quiet: bool = False) -> Outcomes:
    """The outcomes of a store's newest 20 runs, read from their rows' outcomes and nothing
    else; a run whose rows Prove cannot read is left out, with a note unless ``quiet``."""
    newest = index.runs[:NEWEST]
    total = len(index.runs)
    if total > NEWEST:
        whose = f"the newest {count(NEWEST)} of its {count(total)} runs"
    else:
        whose = "its one run" if total == 1 else f"its {count(total)} runs"
    counts: Counter[str] = Counter()
    for run in newest:
        try:
            frame = store.read(run.run_id, meta=False, trace="none")
        except Exception as e:
            if not quiet:
                look.err(f"  note: Prove could not read the rows of {run.name} ({look.why(e)})\n")
            continue
        counts.update(str(o) for o in frame["outcome"] if not _no_value(o))
    return Outcomes(counts, whose, total == 1)


def _outcome_order(counts: Mapping[str, int]) -> list[str]:
    """The outcomes as the question lists them: those that are not words for success first,
    then the words for success, each by its count, most first."""

    def by_count(words: list[str]) -> list[str]:
        return sorted(words, key=lambda o: (-counts[o], o))

    return by_count([o for o in counts if o not in SUCCESS_WORDS]) + by_count(
        [o for o in counts if o in SUCCESS_WORDS]
    )


def failures(read: Outcomes, given: Sequence[str], terminal: bool) -> list[str]:
    """The failures: the events given, each refused when no run read carries it; else the
    question, or with no terminal its default, every outcome that is not a word for success."""
    counts = read.counts
    if given:
        events = list(dict.fromkeys(given))
        missing = [e for e in events if e not in counts]
        if missing:
            raise Refused(
                f"unknown event {', '.join(missing)}; {read.whose} {read.carry} the outcomes: "
                f"{', '.join(sorted(counts)) or 'none'}",
                _HELP,
            )
        return events
    if not counts:
        look.err("  these runs carry no outcome; Trace needs one to count failures\n")
        return []
    order = _outcome_order(counts)
    default = [i for i, o in enumerate(order, start=1) if o not in SUCCESS_WORDS]
    if not terminal:
        return [order[i - 1] for i in default]
    look.err(
        f"Which outcomes count as a failure? {read.whose[0].upper()}{read.whose[1:]} "
        f"{read.carry}:\n"
    )
    width = max(len(o) for o in order)
    digits = max(len(count(counts[o])) for o in order)
    for i, o in enumerate(order, start=1):
        episodes = "episode" if counts[o] == 1 else "episodes"
        look.err(f"  {i}) {o.ljust(width)}  {count(counts[o]).rjust(digits)} {episodes}\n")
    look.err("  The default is a guess: every outcome whose name is not a word for success.\n")
    shown = ",".join(str(i) for i in default) or "none"
    while True:
        answer = look.ask(f"Enter the numbers of the failures, separated by commas [{shown}]")
        if answer == "":
            return [order[i - 1] for i in default]
        picked = _numbers(answer, len(order))
        if picked is not None:
            return [order[i - 1] for i in picked]
        look.err(f"  answer with numbers from 1 to {len(order)}, separated by commas\n")


def _numbers(answer: str, last: int) -> list[int] | None:
    picked: list[int] = []
    for part in answer.split(","):
        part = part.strip()
        if not (part.isascii() and part.isdigit()) or not 1 <= int(part) <= last:
            return None
        if int(part) not in picked:
            picked.append(int(part))
    return picked


# ---------- the import of result files ----------

# what each reader asks, in the order its flags read: (the flag's dest, the question)
_ASKED: dict[str, tuple[tuple[str, str], ...]] = {
    "deepeval": (
        ("metric", "Which metric do you want to read? Its name, as the files have it:"),
        ("cut", "Where is the cut? recorded, for DeepEval's own decision, or a number:"),
        ("side", "Does a score below the cut miss it, or above it? below or above:"),
        ("case", "What identifies a test case across versions? name, input or position:"),
    ),
    "ragas": (
        ("metric", "Which column holds the score?"),
        ("cut", "Where is the cut? A number:"),
        ("side", "Does a score below the cut miss it, or above it? below or above:"),
        ("case_column", "Which column identifies a case across versions?"),
    ),
    "table": (
        ("case_column", "Which column identifies a case across versions?"),
        ("outcome_column", "Which column holds each row's outcome?"),
        ("failed", "Which of its values mean a failure? Separate them with commas:"),
    ),
    "junit": (),
    "promptfoo": (
        (
            "case",
            "What identifies a test across versions? var:NAME, the test variable NAME, or "
            "test, the test's position in the file:",
        ),
    ),
    "inspect": (),
    "openai-evals": (),
}
_FLAG = {
    "metric": "--metric",
    "cut": "--cut",
    "side": "--below or --above",
    "case": "--case",
    "case_column": "--case-column",
    "outcome_column": "--outcome-column",
    "failed": "--failed",
    "case_from": "--case-from",
    "outcome_from": "--outcome-from",
}
# the forms of --case init takes that the JUnit reader reads; the other is its default
_JUNIT_CASES = ("name",)


def _fits(reader: str, dest: str, answer: str) -> bool:
    """Whether an answer is one the question takes; the reader judges the rest."""
    if not answer:
        return False
    if dest == "cut":
        if reader == "deepeval" and answer == "recorded":
            return True
        try:
            return math.isfinite(float(answer))
        except ValueError:
            return False
    if dest == "side":
        return answer in ("below", "above")
    if dest == "case":
        if reader == "promptfoo":
            return _promptfoo_case(answer)
        return answer in ("name", "input", "position")
    if dest == "failed":
        return bool(_values(answer))
    return True


def _values(answer: str) -> tuple[str, ...]:
    """The failure values of an answer: the words between its commas, trimmed, each once."""
    return tuple(dict.fromkeys(v.strip() for v in answer.split(",") if v.strip()))


def _promptfoo_case(answer: str) -> bool:
    return answer == "test" or (answer.startswith("var:") and len(answer) > len("var:"))


@dataclass
class Answers:
    """The import's answers, each as its flag takes it, by the flag's dest."""

    values: dict[str, str] = field(default_factory=dict)
    failed: tuple[str, ...] = ()  # --failed, given once for each value

    @classmethod
    def given(cls, ns: argparse.Namespace) -> Answers:
        """The answers the flags give."""
        values = {}
        for dest in ("metric", "cut", "case", "case_column", "outcome_column"):
            value = getattr(ns, dest)
            if value is not None:
                values[dest] = str(value)
        case = values.get("case")
        if case is not None and case not in _CASE_FORMS and not _promptfoo_case(case):
            raise look.Usage(
                f"--case takes name, input or position (DeepEval), name (JUnit), or var:NAME or "
                f"test (promptfoo), not {case}",
                _HELP,
            )
        if ns.below and ns.above:
            raise look.Usage("--below and --above are two sides; give one", _HELP)
        if ns.below or ns.above:
            values["side"] = "below" if ns.below else "above"
        return cls(values, tuple(dict.fromkeys(ns.failed or ())))

    def has(self, dest: str) -> bool:
        return bool(self.failed) if dest == "failed" else dest in self.values

    def flags(self) -> list[str]:
        words: list[str] = []
        for dest in ("metric", "cut"):
            if dest in self.values:
                words += _pair(_FLAG[dest], self.values[dest])
        if "side" in self.values:
            words.append(f"--{self.values['side']}")
        for dest in ("case", "case_column", "outcome_column"):
            if dest in self.values:
                words += _pair(_FLAG[dest], self.values[dest])
        for value in self.failed:
            words += _pair(_FLAG["failed"], value)
        return words


def import_answers(readers: Sequence[str], answers: Answers, terminal: bool) -> Answers:
    """Each reader's questions, in the order its flags read, each asked once and only when its
    flag was not given; with no terminal, a missing answer is a refusal."""
    got = Answers(dict(answers.values), answers.failed)
    values = got.values
    missing: list[str] = []
    sided = False
    for reader in readers:
        for dest, question in _ASKED[reader]:
            if got.has(dest) or (dest == "side" and values.get("cut") in ("recorded", None)):
                if dest == "side" and not terminal and values.get("cut") is None:
                    sided = True
                continue
            if not terminal:
                missing.append(_FLAG[dest])
                continue
            while True:
                answer = look.ask(question)
                if _fits(reader, dest, answer):
                    if dest == "failed":
                        got.failed = _values(answer)
                    else:
                        values[dest] = answer
                    break
                look.err("  that is not an answer this question takes\n")
    if missing:
        side = " (and --below or --above for a cut that is a number)" if sided else ""
        raise Refused(
            "the result files found need the import's answers, and --yes asks nothing: give "
            f"{_and(list(dict.fromkeys(missing)))}{side}, or --no-import to write the config with "
            "no store",
            _HELP,
        )
    return got


def answers_fit(readers: Sequence[str], answers: Answers) -> None:
    """Refused before anything is asked or written: an answer given that a reader of the files
    found cannot read them by. The JUnit reader reads a test case by its class name and its
    name, or by its name alone (``--case name``); input and position are DeepEval's; promptfoo
    reads a test by a variable (``var:NAME``) or its position (``test``)."""
    case = answers.values.get("case")
    if case is None:
        return
    if "junit" in readers and case not in _JUNIT_CASES:
        raise Refused(
            f"--case {case} cannot identify a test case of a JUnit report: give --case name to "
            "read the reports by the test's name alone, or leave --case out to read them by its "
            "class name and its name",
            _HELP,
        )
    if "deepeval" in readers and case not in ("name", "input", "position"):
        raise Refused(
            f"--case {case} cannot identify a test case of a DeepEval test run: give name, input "
            "or position",
            _HELP,
        )
    if "promptfoo" in readers and not _promptfoo_case(case):
        raise Refused(
            f"--case {case} cannot identify a test of a promptfoo file: give var:NAME, the test "
            "variable NAME, or test, the test's position in the file",
            _HELP,
        )


def run_name(path: str) -> str:
    """A run named after its file, without the extensions that say its format."""
    name = Path(path).name.lstrip(".")
    for suffix in (".gz", ".csv", ".jsonl", ".json", ".xml", ".eval"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
    return name


@dataclass(frozen=True)
class Imported:
    path: str
    reader: str
    run: Any  # the reader's Run, written once every answer is in
    # a promptfoo file's prompt, counting from 1: one file holds every prompt, and each is its
    # own run
    prompt: int | None = None


def _prompts_in(path: str) -> int:
    """How many prompts a promptfoo file holds; one when it cannot be read, so that the reader's
    own refusal says why."""
    from poisson_trace.ingest import promptfoo

    try:
        loaded = promptfoo._load(Path(path))
        return len({int(r["promptIdx"]) for r in loaded.results}) or 1
    except Exception:
        return 1


def read_imports(files: Sequence[FoundFile], answers: Answers) -> list[Imported]:
    """Every file read by its reader before anything is written: a refusal on any file writes
    no run of the others."""
    from poisson_trace.ingest.importing import reader, reader_defaults
    from poisson_trace.ingest.rows import Refusal

    made: list[Imported] = []
    seen: dict[str, str] = {}
    values = answers.values
    for f in files:
        stem = run_name(f.path)
        # one promptfoo file holds every prompt: each is its own run, named by the file and the
        # prompt's number counting from 1
        prompts = _prompts_in(f.path) if f.reader == "promptfoo" else 1
        numbered = [None] if prompts == 1 else list(range(1, prompts + 1))
        for prompt in numbered:
            name = stem if prompt is None else f"{stem}-{prompt}"
            hole = names.import_name_refusal(name)
            if hole is not None:
                raise Refused(f"{f.path} cannot be imported as a run named after it: {hole}", _HELP)
            if name in seen:
                raise Refused(
                    f"{seen[name]} and {f.path} would both be imported as the run {name}; import "
                    "them one at a time with poisson-trace import, each under a name of its own",
                    _HELP,
                )
            seen[name] = f.path
            # the reader's own defaults, where it has them (the JUnit reader's case, promptfoo's
            # and Inspect's outcome), then the answers
            given: dict[str, Any] = dict(reader_defaults(f.reader))
            given.update(
                files=[f.path],
                run=name,
                started=None,
                verdicts=None,
                metric=values.get("metric"),
                cut=values.get("cut"),
                below=values.get("side") == "below",
                above=values.get("side") == "above",
                case=values.get("case", given.get("case")),
                case_column=values.get("case_column"),
                outcome_column=values.get("outcome_column"),
                failed=list(answers.failed),
                score_column=None,
                prompt=None if prompt is None else str(prompt),
            )
            ns = argparse.Namespace(**given)
            try:
                run = reader(f.reader).read(ns)
            except Refusal as e:
                raise Refused(str(e), *e.nexts) from e
            if not run.rows:
                raise Refused(f"no row was read from {f.path}, so there is no run to write")
            if all(row.outcome is None for row in run.rows):
                raise Refused(
                    f"none of the rows read from {f.path} has an outcome, so there is nothing to "
                    "compare and no run was written"
                )
            made.append(Imported(f.path, f.reader, run, prompt))
    _failed_carried(made, answers)
    return made


def _failed_carried(made: Sequence[Imported], answers: Answers) -> None:
    """Refused when a failure value given for the tables matches no cell of their outcome
    column in any file found: no row would count as a failure, so the setup would have none."""
    tables = [item for item in made if item.reader == "table"]
    if not tables or not answers.failed:
        return
    cells: Counter[str] = Counter()
    for item in tables:
        cells.update(item.run.cells)
    missing = [v for v in answers.failed if cells[v] == 0]
    if not missing:
        return
    column = answers.values.get("outcome_column", "")
    held = [f'"{v}" ({_plural(n, "row", "rows")})' for v, n in cells.most_common(_CELLS_SHOWN)]
    more = len(cells) - len(held)
    if more > 0:
        held.append(f"{count(more)} more")
    files = "the file found" if len(tables) == 1 else f"the {count(len(tables))} files found"
    values = " and ".join(f'"{v}"' for v in missing)
    raise Refused(
        f"--failed {values} matches no cell of the column {column} in {files}, so no row "
        f"would count as a failure; its cells are {', '.join(held) or 'all empty'}: give "
        "--failed with the values that mean a failure",
        _HELP,
    )


# how many of a column's values a refusal lists
_CELLS_SHOWN = 10


def no_failures_why(counts: Mapping[str, int]) -> str:
    """Why no failure was set for runs whose outcomes are ``counts``: they carry none, or
    every one they carry is a word for success."""
    if not counts:
        return "these runs carry no outcome"
    carried = sorted(counts)
    words = "a word" if len(carried) == 1 else "words"
    return f"these runs carry only {', '.join(carried)}, {words} for success"


def import_line(item: Imported, store: str) -> str:
    """The import that writes one of the runs, as one command."""
    declared = dict(item.run.declared)
    words = ["poisson-trace", "import", item.reader, item.path, *_pair("--store", store)]
    words += _pair("--run", item.run.name)
    if item.prompt is not None:
        words += _pair("--prompt", str(item.prompt))
    if item.reader == "inspect" and declared.get("scorer") is not None:
        words += _pair("--scorer", str(declared["scorer"]))
    if item.reader == "promptfoo" and declared.get("provider") is not None:
        words += _pair("--provider", str(declared["provider"]))
    if item.reader in ("promptfoo", "inspect") and declared.get("outcome") not in (
        None,
        "success",
        "correct",
    ):
        words += _pair("--outcome", str(declared["outcome"]))
    if "metric" in declared:
        words += _pair("--metric", str(declared["metric"]))
    if "cut" in declared and ("metric" in declared or item.reader in ("promptfoo", "inspect")):
        words += _pair("--cut", str(declared["cut"]))
    if "side" in declared:
        words.append(f"--{declared['side']}")
    if "case" in declared:
        words += _pair("--case", str(declared["case"]))
    if "case_column" in declared:
        words += _pair("--case-column", str(declared["case_column"]))
    if "outcome_column" in declared:
        words += _pair("--outcome-column", str(declared["outcome_column"]))
    if "outcome_column" in declared or item.reader == "inspect":
        for value in declared.get("failed", ()):
            words += _pair("--failed", str(value))
    return " ".join(_shell_word(w) for w in words)


# ---------- the lines that import the files init leaves ----------

# the most import lines a refusal or a summary prints; the rest are counted
LINES_SHOWN = 12
# the column names init reads as a table's case, in the order it prefers them
CASE_COLUMNS = ("case", "id", "case_id", "question_id", "sample_id")


def listing_order(files: Sequence[FoundFile]) -> list[FoundFile]:
    """The files in the order the listing shows them: DeepEval's saved test runs first, then
    the other result files."""
    return [f for f in files if f.reader == "deepeval"] + [
        f for f in files if f.reader != "deepeval"
    ]


def by_tool(files: Sequence[FoundFile]) -> list[FoundFile]:
    """The files grouped by the tool that wrote them, the tools in the order the listing first
    shows each, each tool's files in the listing's order."""
    ordered = listing_order(files)
    tools = dict.fromkeys(f.reader for f in ordered)
    return [f for tool in tools for f in ordered if f.reader == tool]


def tools_of(files: Sequence[FoundFile]) -> list[str]:
    return list(dict.fromkeys(f.reader for f in listing_order(files)))


def _guessed(found: FoundFile) -> dict[str, Any]:
    """The answers an import of the file takes, read from the file where it says them, else a
    word in capitals for the user to fill in."""
    path = Path(found.path)
    if found.reader == "deepeval":
        return _deepeval_guess(path)
    if found.reader == "promptfoo":
        return _promptfoo_guess(path)
    if found.reader == "langsmith":
        from poisson_trace.ingest import langsmith

        # the case is the dataset example where the export carries its id; what says a run
        # failed is the user's to name
        return {
            "case_from": "example" if langsmith.carries_examples(path) else "CASE",
            "outcome_from": "OUTCOME",
        }
    if found.reader in ("ragas", "table"):
        try:
            head = _columns(path)
        except Exception:
            head = []
        case = next((c for c in CASE_COLUMNS if c in head), "CASE")
        if found.reader == "ragas":
            from poisson_trace.ingest.tabular import METRICS

            metrics = [c for c in dict.fromkeys(head) if c in METRICS]
            return {
                "metric": metrics[0] if len(metrics) == 1 else "METRIC",
                "cut": "CUT",
                "side": "below",
                "case_column": case,
            }
        from poisson_trace.ingest.table import OUTCOME_COLUMNS

        outcomes = [c for c in dict.fromkeys(head) if c in OUTCOME_COLUMNS]
        column = outcomes[0] if len(outcomes) == 1 else "OUTCOME"
        failed = _failure_values(path, column) if column != "OUTCOME" else []
        return {
            "case_column": case,
            "outcome_column": column,
            "failed": failed or ["FAILED"],
        }
    return {}


def _promptfoo_guess(path: Path) -> dict[str, Any]:
    """A promptfoo file's prompt (PROMPT when it holds several: one import is one of them) and
    its case: a test variable named as a case column is, in every result, else the test's
    position."""
    try:
        if path.name.lower().endswith(".jsonl"):
            text = path.read_bytes().decode("utf-8")
            results = [json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            results = json.loads(path.read_bytes().decode("utf-8"))["results"]["results"]
        prompts = {r.get("promptIdx") for r in results}
        named = [
            c
            for c in CASE_COLUMNS
            if results and all(isinstance(r.get("vars"), dict) and c in r["vars"] for r in results)
        ]
    except Exception:
        return {"prompt": "PROMPT", "case": "test"}
    guess: dict[str, Any] = {} if len(prompts) == 1 else {"prompt": "PROMPT"}
    guess["case"] = f"var:{named[0]}" if named else "test"
    return guess


def _columns(path: Path) -> list[str]:
    from poisson_trace.ingest.tabular import head_columns

    head = head_columns(path)
    return [] if head is None else list(head[1])


def _failure_values(path: Path, column: str) -> list[str]:
    """The values of a table's outcome column that are not words for success, the most rows
    first; none when the column cannot be read."""
    from poisson_trace.ingest import tabular
    from poisson_trace.ingest.table import spelt

    try:
        fmt, gzipped = tabular.format_of(path)
        raw, _ = tabular.read_bytes(path)
        cells = Counter(
            text
            for cell, _ in tabular.pairs(path, fmt, gzipped, raw, (column, column))
            if (text := spelt(cell)) is not None
        )
    except Exception:
        return []
    return [v for v in _outcome_order(cells) if v not in SUCCESS_WORDS]


def _deepeval_guess(path: Path) -> dict[str, Any]:
    """A DeepEval test run's one metric, read at DeepEval's own decision, its cases by name
    where each has a name of its own."""
    from poisson_trace.ingest import deepeval

    metrics: list[str] = []
    case = "CASE"
    try:
        _, test_run = deepeval._test_run(path, json.loads(path.read_bytes().decode("utf-8")))
        entries = deepeval._entries(path, test_run)
        for _, test_case in entries:
            metrics += [str(m.get("name")) for m in deepeval._metrics(path, test_case)]
        named = [test_case.get("name") for _, test_case in entries]
        if named and all(
            isinstance(n, str) and n and not deepeval._POSITIONAL.fullmatch(n) for n in named
        ):
            case = "name"
    except Exception:
        # a file the reader would refuse: every answer is the user's to give
        metrics, case = [], "CASE"
    held = list(dict.fromkeys(metrics))
    return {"metric": held[0] if len(held) == 1 else "METRIC", "cut": "recorded", "case": case}


def _run_names(files: Sequence[FoundFile]) -> dict[str, str]:
    """Each file's run name: the file's own, with its tool's name after it where two files
    would share one; RUN where the file's name cannot be a run's."""
    named: dict[str, str] = {}
    stems = Counter(run_name(f.path) for f in files)
    for f in files:
        name = run_name(f.path)
        if stems[name] > 1:
            name = f"{name}-{f.reader}"
        named[f.path] = "RUN" if names.import_name_refusal(name) is not None else name
    taken: Counter[str] = Counter()
    for f in files:
        taken[named[f.path]] += 1
        if taken[named[f.path]] > 1 and named[f.path] != "RUN":
            named[f.path] = f"{named[f.path]}-{taken[named[f.path]]}"
    return named


def file_lines(
    files: Sequence[FoundFile], store: str, *, limit: int | None = LINES_SHOWN
) -> list[str]:
    """One import line for each file, grouped by tool, at most 12 of them (each file shown is
    opened for its answers): every answer init can read from the file filled in, and a word in
    capitals for each it cannot (METRIC, CUT, CASE). ``limit`` None gives every file its line
    (the terminal app's imports screen, TF19-A9); the run names are read over every file
    either way, so a line is the same whether or not the ones before it are shown."""
    ordered = by_tool(files)
    run_names = _run_names(ordered)
    lines = []
    for f in ordered[:limit]:
        guess = _guessed(f)
        words = ["poisson-trace", "import", f.reader, f.path, *_pair("--store", store)]
        words += _pair("--run", run_names[f.path])
        for dest in ("metric", "cut"):
            if dest in guess:
                words += _pair(_FLAG[dest], str(guess[dest]))
        if "side" in guess:
            words.append(f"--{guess['side']}")
        if "prompt" in guess:
            words += _pair("--prompt", str(guess["prompt"]))
        for dest in ("case", "case_column", "outcome_column"):
            if dest in guess:
                words += _pair(_FLAG[dest], str(guess[dest]))
        for value in guess.get("failed", ()):
            words += _pair("--failed", str(value))
        for dest in ("case_from", "outcome_from"):
            if dest in guess:
                words += _pair(_FLAG[dest], str(guess[dest]))
        lines.append(" ".join(_shell_word(w) for w in words))
    return lines


def shown_lines(files: Sequence[FoundFile], store: str) -> list[str]:
    """The lines a refusal or a summary prints: at most 12, then how many more and where the
    import's help is."""
    shown = file_lines(files, store)
    more = len(files) - len(shown)
    if more > 0:
        word = "file" if more == 1 else "files"
        shown.append(f"and {count(more)} more {word}: {_IMPORT_HELP}")
    else:
        shown.append(_IMPORT_HELP)
    return shown


def files_said(files: Sequence[FoundFile]) -> str:
    """``8 result files of 4 tools``."""
    tools = len(tools_of(files))
    return (
        f"{_plural(len(files), 'result file', 'result files')} of {_plural(tools, 'tool', 'tools')}"
    )


def _not_empty(files: Sequence[FoundFile]) -> list[FoundFile]:
    """The files but the JUnit reports that hold no test case, left out without a word: init
    imports none of them here, so it has none to say it leaves out."""
    from poisson_trace.ingest import junit

    return [f for f in files if not (f.reader == "junit" and junit.holds_no_test_case(f.path))]


_IMPORT_HELP = "poisson-trace import --help"


def _imported_outcomes(made: Sequence[Imported]) -> Outcomes:
    counts: Counter[str] = Counter()
    for item in made:
        counts.update(row.outcome for row in item.run.rows if row.outcome is not None)
    one = len(made) == 1
    return Outcomes(counts, "the run to import" if one else "the runs to import", one)


# ---------- writing ----------


def _write(
    made: Sequence[Imported],
    store: Path,
    form: str,
    path: Path,
    shown: str,
    text: str,
    *,
    rules: Sequence[Any] = (),
    budgets: Any = None,
) -> None:
    """The runs to import, then the config. On a refusal, a failure or Ctrl-C, every run this
    wrote is removed, and so is the store folder it made, with the store descriptor the first
    run wrote into it (the run record, SV1), so nothing is left behind. ``rules`` and
    ``budgets`` are a config's, when the runs join one that has them."""
    from poisson_trace.ingest.rows import Refusal
    from poisson_trace.ingest.writer import write

    made_store = not store.exists()
    written: list[Path] = []
    try:
        for item in made:
            target = store / item.run.name
            existed = target.exists()
            try:
                write(item.run, store, form, rules=rules, budgets=budgets)
            finally:
                if not existed and target.exists():
                    written.append(target)
        config.write_config_file(path, shown, text)
    except BaseException as e:
        for run in written:
            shutil.rmtree(run, ignore_errors=True)
        if made_store:
            with contextlib.suppress(OSError):
                (store / ".poisson" / "store.json").unlink()
            with contextlib.suppress(OSError):
                (store / ".poisson").rmdir()
            with contextlib.suppress(OSError):
                store.rmdir()
        if isinstance(e, Refusal):
            raise Refused(str(e), *e.nexts) from e
        raise


# ---------- the setup ----------


@dataclass
class Done:
    """What init did: the JSON's fields, and the text summary."""

    data: dict[str, Any]
    text: str


def _here_is_home() -> bool:
    """Whether the current folder is the home folder or a folder above it."""
    try:
        home = Path.home().resolve()
        here = Path.cwd().resolve()
    except (RuntimeError, OSError):
        return False
    return here == home or here in home.parents


def _held(path: str) -> list[str]:
    from poisson_prove.store import Store

    try:
        return Store(path).runs()
    except OSError:
        return []


def _index(path: str, form: str) -> tuple[Any, Any]:
    """The store at ``path`` and its runs, named. A names file with an entry every verb but
    name refuses is read here as name reads it, since the setup names nothing; one that is not
    a names file at all is refused."""
    from poisson_prove.store import Store

    store = Store(path)
    return store, names.index(store, _held(path), path, lenient=True, form=form)


def _ceilings(ns: argparse.Namespace) -> None:
    if ns.max_mde is not None and not (math.isfinite(ns.max_mde) and 0.0 < ns.max_mde < 1.0):
        raise Refused(
            "--max-mde takes a number strictly between 0 and 1 (0.2 is twenty points), not "
            f"{ns.max_mde:g}"
        )
    if ns.max_mde_hr is not None and not (math.isfinite(ns.max_mde_hr) and ns.max_mde_hr > 1.0):
        raise Refused(f"--max-mde-hr takes a number above 1, such as 1.5, not {ns.max_mde_hr:g}")


# the flags that set what a config holds, beside the failures
_SETTING = (
    "store",
    "names",
    "import_",
    "metric",
    "cut",
    "case",
    "case_column",
    "outcome_column",
    "failed",
    "max_mde",
    "max_mde_hr",
    "fail_on",
)


def _sets(ns: argparse.Namespace, dests: Sequence[str]) -> list[str]:
    return [d for d in dests if getattr(ns, d) not in (None, [])] + [
        side for side in ("below", "above") if getattr(ns, side)
    ]


def _no_hook(line: str) -> None:
    del line


def init(ns: argparse.Namespace, written: Callable[[str], None] = _no_hook) -> Done:
    """The setup, the questions answered on a terminal or from the flags. Prove at the version
    Trace reads is checked before this is called. ``written`` is told, once anything is on
    disk, the line Ctrl-C prints from then on."""
    _ceilings(ns)
    path = config.path_of(ns.config)
    shown = look.shown(ns.config) if ns.config is not None else config.CONFIG
    if ns.add_store is not None:
        return add_store(ns, path, shown, written)
    answers = Answers.given(ns)
    terminal = not ns.yes
    if terminal and (sys.stdin is None or not sys.stdin.isatty()):
        raise Refused(
            "init asks questions and stdin is not a terminal; give --yes and the answers as "
            "flags (poisson-trace init --help lists them)",
            _HELP,
        )
    held = _existing(ns, path, shown)
    if held is not None:
        if held.imports and imports.pending(held, imports.imports_store(held).path):
            return _hand_over(ns, held, terminal, written)
        return _complete(ns, held, terminal, written)
    _not_in_a_store(path, shown)
    form = ns.names or "target"
    stores: list[tuple[str | None, str]] = []
    found: Found | None = None
    made: list[Imported] = []
    imported: bool | None = ns.import_
    if ns.store:
        stores = _stores_given(ns.store)
        look.err(
            f"Poisson Trace setup. This writes {shown} and runs nothing. Ctrl-C stops without "
            "writing.\n\n"
        )
    else:
        if _here_is_home():
            raise Refused(
                "init never searches the home folder or a folder above it; run it in a "
                "project's folder, or give --store PATH to name a store",
                _HELP,
            )
        look.err(
            f"Poisson Trace setup. This writes {shown} and runs nothing. Ctrl-C stops without "
            "writing.\n\n"
        )
        look.err(f"Looking for results under {Path.cwd()} …\n")
        found = search(Path("."))
        listed = show(found)
        if not found.stores:
            found.files = _left_in(found.files)
        if len(found.stores) > 1 and terminal:
            stores = [(None, _store_question(listed).path)]
        elif found.stores:
            first = found.stores[0]
            which = "the store found" if len(found.stores) == 1 else "the first store listed"
            look.err(f"Using {first.path}, {which}.\n")
            stores = [(None, first.path)]
        elif found.files:
            readers = list(dict.fromkeys(f.reader for f in found.files))
            if len(readers) > 1 and imported is not False:
                _several_tools(ns, found.files, config.beside(path, IMPORTED_STORE), shown)
            if imported is not False and readers[0] not in _ASKED:
                _not_asked(ns, found.files, config.beside(path, IMPORTED_STORE), shown)
            if imported is not False:
                answers_fit(readers, answers)
            if imported is None:
                imported = not terminal or _yes_no(
                    "No store here, but these look like results another tool wrote. "
                    "Import them as runs Trace can read? [Y/n]"
                )
            if imported:
                answers = import_answers(readers, answers, terminal)
                made = read_imports(found.files, answers)
    imported_store = config.beside(path, IMPORTED_STORE)
    if made:
        events = failures(_imported_outcomes(made), ns.event or (), terminal)
    elif stores:
        store, first_index = _index(stores[0][1], form)
        events = failures(newest_outcomes(store, first_index), ns.event or (), terminal)
    elif ns.event:
        raise Refused(f"--event {ns.event[0]} names a failure, and no store is set up", _HELP)
    else:
        events = []
    # every answer is in: nothing was written before this line
    setup = [(None, imported_store)] if made else stores
    text = config.text_of(
        [(name, config.written_path(path, p)) for name, p in setup],
        events,
        max_mde=ns.max_mde,
        max_mde_hr=ns.max_mde_hr,
        fail_on=ns.fail_on,
        names_from=form,
    )
    config.parse(text, path, shown, given=ns.config is not None)
    _write(made, Path(imported_store), form, path, shown, text)
    if made:
        kept = f"{shown} and {_plural(len(made), 'imported run', 'imported runs')} were"
    else:
        kept = f"{shown} was"
    written(f"stopped  interrupted: {kept} written whole; poisson-trace doctor checks it")
    command = _command(ns, [] if made else stores, events, imported, answers)
    others = []
    if found is not None and stores and not made:
        others = [s for s in found.stores if s.path != stores[0][1]]
    left: list[FoundFile] = []
    if found is not None and not made:
        left = found.files if not found.stores else _not_empty(found.files)
    return _summary(ns, shown, setup, form, events, command, others, made, "wrote", left)


def _several_tools(
    ns: argparse.Namespace, files: Sequence[FoundFile], store: str, shown: str
) -> None:
    """Refused: files of several tools, which init cannot import with one set of answers; the
    refusal carries one import line for each file."""
    tools = tools_of(files)
    finish = look.command(
        "poisson-trace",
        "init",
        "--force",
        *(_shell_word(w) for w in _pair("--store", store)),
        *_reach(ns),
    )
    raise Refused(
        f"the {_plural(len(files), 'result file', 'result files')} here were written by "
        f"{_plural(len(tools), 'tool', 'tools')} ({_and(tools)}), and init can import one "
        "tool's files at a time, so it imported none; pick the two files you want to compare, "
        "the old version's and the new one's, import each with its line below (a word in "
        f"capitals is yours to fill in), then run {finish}; or give --no-import to write "
        f"{shown} with no store first",
        *shown_lines(files, store),
    )


def _not_asked(ns: argparse.Namespace, files: Sequence[FoundFile], store: str, shown: str) -> None:
    """Refused: files of a tool whose import needs answers init has no question and no flag
    for (a LangSmith export's case and outcome); the refusal carries one import line for each
    file."""
    from poisson_trace.ingest.importing import reader_options

    tool = files[0].reader
    needed = [option.flag for option in reader_options(tool).values() if option.required]
    finish = look.command(
        "poisson-trace",
        "init",
        "--force",
        *(_shell_word(w) for w in _pair("--store", store)),
        *_reach(ns),
    )
    raise Refused(
        f"the {_plural(len(files), 'result file', 'result files')} here "
        f"{'was' if len(files) == 1 else 'were'} written by {tool}, and an import of them needs "
        f"{_and(needed) if needed else 'answers'}, which init does not ask for, so it imported "
        "none; import the old version's file and the new one's, each with its line below (a "
        f"word in capitals is yours to fill in), then run {finish}; or name them under "
        f"[[import]] in {shown}; or give --no-import to write {shown} with no store first",
        *shown_lines(files, store),
    )


def _existing(ns: argparse.Namespace, path: Path, shown: str) -> config.Config | None:
    """A config there already: refused without --force, but for one with a store and no
    failures given only failures, which init completes. None when there is none, or when
    --force replaces it."""
    if not path.exists() and not path.is_symlink():
        if not path.parent.is_dir():
            raise Refused(f"the folder {path.parent} does not exist, so {shown} cannot be written")
        return None
    if path.is_dir():
        raise Refused(f"{shown} is a folder, so the config cannot be written there")
    if ns.force:
        return None
    try:
        held = config.load(ns.config)
    except config.ConfigError:
        held = None
    if held is not None and held.imports:
        pending = imports.pending(held, imports.imports_store(held).path)
        if pending:
            other = _sets(ns, [d for d in _SETTING if d != "import_"])
            if other:
                raise look.Usage(
                    f"{shown} names {_plural(len(pending), 'file', 'files')} to import, and init "
                    "takes no setup flag for that but --import, --no-import, --event and --yes; "
                    "give --force to set up again",
                    _HELP,
                )
            return held
    if (
        held is not None
        and held.store is not None
        and held.events is None
        and not _sets(ns, _SETTING)
    ):
        return held
    raise Refused(
        f"{shown} is there already, and init leaves it as it is; give --force to replace it, or "
        "edit it by hand",
        look.command("poisson-trace", "doctor", *_reach(ns)),
    )


# ---------- the hand-over from the agent's file ----------

IMPORT_QUESTION = "Import these {n} files as the runs named here? [y/N]"


def _hand_over(
    ns: argparse.Namespace, held: config.Config, terminal: bool, written: Callable[[str], None]
) -> Done:
    """A config with ``[[import]]`` entries not imported yet: the stores, the failures and the
    pending files shown, the question (No by default; ``--yes`` and ``--import`` answer yes,
    ``--no-import`` no), every pending file read before anything is written, the failures
    asked when the config sets none, then the runs written into the imports' store and the
    config written once, every line kept and the store's table added when it names none."""
    store = imports.imports_store(held)
    pending = imports.pending(held, store.path)
    n = len(pending)
    look.err(
        f"Poisson Trace setup. {held.shown} names {_plural(n, 'file', 'files')} to import; this "
        f"imports them into {store.path} and keeps every line of the file. Ctrl-C stops without "
        "writing.\n\n"
    )
    for name, store_path in held.stores():
        runs = _held(store_path)
        if not runs:
            if store.may_be_empty and imports.same_folder(store_path, store.path):
                look.err(f"  {_store_words(name, store_path)}: no run yet\n")
                continue
            raise Refused(
                f"{held.shown} names the {_store_words(name, store_path)}, and no folder under it "
                "holds a run Prove stored; give --force to set up again",
                _HELP,
            )
        look.err(f"  {_store_words(name, store_path)}: {_plural(len(runs), 'run', 'runs')}\n")
    events: Sequence[str] | None = held.events
    look.err(f"  failures: {', '.join(events) if events else 'none set yet'}\n")
    look.err("  files to import:\n")
    for entry in pending:
        look.err(f"    {entry.file}  as the run {entry.name} ({entry.tool})\n")
    look.err("\n")
    if events is not None and ns.event:
        raise look.Usage(
            f"{held.shown} sets the failures already ({', '.join(events)}); edit [events] by "
            "hand, or give --force to set up again",
            _HELP,
        )
    decision: bool | None = ns.import_
    if decision is None:
        decision = True if not terminal else _yes_no_default_no(IMPORT_QUESTION.format(n=n))
    reach = _reach(ns)
    if not decision:
        sentence = f"{held.shown}: {_plural(n, 'file', 'files')} pending import, left as they are"
        following = look.command("poisson-trace", "init", "--import", *reach)
        return _hand_over_summary(ns, held, store, [], events or [], sentence, following)
    from poisson_trace.ingest.rows import Refusal

    made: list[Imported] = []
    for entry in pending:
        try:
            run = imports.read(held, entry, pull_into=store.path)
        except Refusal as e:
            raise Refused(str(e), *e.nexts) from e
        made.append(Imported(entry.file, entry.tool, run))
    text = held.text
    if events is None:
        if held.store is not None and imports.prove_stored(held.store):
            first, index = _index(held.store, held.names_from)
            read = newest_outcomes(first, index)
        else:
            read = _imported_outcomes(made)
        events = failures(read, ns.event or (), terminal)
        if events:
            text = _with_events(held, events)
    assert events is not None
    if store.table is not None:
        where = names.toml_string(config.written_path(held.path, store.path))
        text = config.appended(text, f"[{store.table}]\npath = {where}\n")
    after = config.parse(text, held.path, held.shown, given=held.given)
    _write(
        made,
        Path(store.path),
        held.names_from,
        held.path,
        held.shown,
        text,
        rules=held.rules,
        budgets=held.budgets,
    )
    written(
        f"stopped  interrupted: {held.shown} and {_plural(n, 'imported run', 'imported runs')} "
        "were written whole; poisson-trace doctor checks it"
    )
    sentence = f"imported {_plural(n, 'run', 'runs')} into {store.path}"
    if events:
        sentence += f", failures {', '.join(events)}"
    if store.table is not None:
        sentence += f"; [{store.table}] added to {held.shown}"
    following = look.command("poisson-trace", "doctor", *reach)
    return _hand_over_summary(ns, after, store, made, events, sentence, following)


def _yes_no_default_no(question: str) -> bool:
    while True:
        answer = look.ask(question).lower()
        if answer in ("", "n", "no"):
            return False
        if answer in ("y", "yes"):
            return True
        look.err("  answer y or n\n")


def _hand_over_summary(
    ns: argparse.Namespace,
    held: config.Config,
    store: imports.ImportsStore,
    made: Sequence[Imported],
    events: Sequence[str],
    sentence: str,
    following: str,
) -> Done:
    stores = [(n, p) for n, p in held.stores() if _held(p)]
    indexes = [_index(p, held.names_from)[1] for _, p in stores]
    runs = {p: len(i.runs) + len(i.unreadable) for (_, p), i in zip(stores, indexes, strict=True)}
    lines = [f"ok  {sentence}"]
    lines.append("  prove    poisson-prove is installed at the version Trace reads")
    entries = {e.name: e for e in held.imports}
    for item in made:
        entry = entries[item.run.name]
        lines.append(f"  import   {imports.shell_line(imports.command(held, entry, store.path))}")
    command = ["poisson-trace", "init", "--yes"]
    if ns.config is not None:
        command += _pair("--config", ns.config)
    command.append("--import" if made else "--no-import")
    for event in events:
        if ns.event and event in ns.event:
            command += _pair("--event", event)
    lines += ["  the same setup, without questions:", "    " + shell_line(command)]
    lines.append(f"next: {following}")
    data = {
        "schema": "poisson-trace.init/1",
        "verdict": "ok",
        "sentence": sentence,
        "config_path": held.shown,
        "stores": [{"name": n, "path": p, "runs": runs[p]} for n, p in stores],
        "events": list(events),
        "named": sum(1 for index in indexes for r in index.runs if r.named_by == "you"),
        "prove": {"installed": True, "version": look.prove_found()},
        "equivalent_command": command,
        "next": following,
    }
    return Done(data, "\n".join(lines) + "\n")


def _store_words(name: str | None, path: str) -> str:
    return f"store {path}" if name is None else f"store {name} at {path}"


def _not_in_a_store(path: Path, shown: str) -> None:
    """The config is never written into a store or a run's folder."""
    from poisson_prove.store import Store

    folder = path.parent
    try:
        run = Store(folder.resolve().parent).manifest(folder.resolve().name)
    except Exception:
        run = None
    if _held(str(folder)) or run is not None:
        what = "a run Prove stored" if run is not None else "a store (it holds runs Prove stored)"
        raise Refused(
            f"{shown} would be written in {folder}, which is {what}, and init writes nothing "
            "into a store; run it in the folder above, or give --config PATH outside it",
            _HELP,
        )


def _storable(typed: str) -> str | None:
    """Why the store at ``typed`` cannot be set up, or None: it holds no run, or no run whose
    record Prove reads."""
    held = _held(typed)
    if not held:
        return f"no store at {look.shown(typed)} (no folder under it holds a run Prove stored)"
    if not _index(typed, "target")[1].runs:
        return f"Prove reads the record of no run of the store at {look.shown(typed)}"
    return None


def store_name(typed: str) -> tuple[str, str | None]:
    """The name a store is given by its folder, and why it cannot be, or None."""
    name = Path(os.path.abspath(typed)).name
    if not config.STORE_NAME.fullmatch(name):
        return name, f'"{name}" is not a store name: {config.STORE_NAME_RULE}'
    if name == "path":
        return name, 'a store cannot be named "path", which [store] holds as its own setting'
    return name, None


def _stores_given(paths: Sequence[str]) -> list[tuple[str | None, str]]:
    """The stores --store names: the first unnamed, each other named by its folder."""
    stores: list[tuple[str | None, str]] = []
    for i, typed in enumerate(paths):
        why = _storable(typed)
        if why is not None:
            raise Refused(why, _HELP)
        for _, earlier in stores:
            with contextlib.suppress(OSError):
                if os.path.samefile(earlier, typed):
                    raise Refused(f"{earlier} and {typed} are one store, given twice", _HELP)
        if i == 0:
            stores.append((None, typed))
            continue
        name, why = store_name(typed)
        if why is not None:
            raise Refused(f"the store at {typed} is named by its folder, and {why}", _HELP)
        if any(n == name for n, _ in stores):
            raise Refused(
                f"two of the stores given would both be named {name}, by their folders", _HELP
            )
        stores.append((name, typed))
    return stores


def _complete(
    ns: argparse.Namespace, held: config.Config, terminal: bool, written: Callable[[str], None]
) -> Done:
    """A config with a store and no failures: the failure question for its store, and the
    failures added (in its ``[events]`` table when it has one, else after what it holds), every
    other line kept."""
    assert held.store is not None
    look.err(
        f"Poisson Trace setup. {held.shown} names a store and no failures; this adds them and "
        "keeps every other line. Ctrl-C stops without writing.\n\n"
    )
    why = _storable(held.store)
    if why is not None:
        raise Refused(
            f"{held.shown} names the store {held.store}: {why}; give --force to set up again", _HELP
        )
    store, index = _index(held.store, held.names_from)
    events = failures(newest_outcomes(store, index), ns.event or (), terminal)
    verb = "left as it was"
    if events:
        config.write_config_file(held.path, held.shown, _with_events(held, events))
        written(
            f"stopped  interrupted: {held.shown} was written whole; poisson-trace doctor checks it"
        )
        verb = "completed"
    command = _command(ns, [], events, None, Answers())
    stores = [(n, p) for n, p in held.stores() if _held(p)]
    return _summary(ns, held.shown, stores, held.names_from, events, command, [], [], verb)


# a table header for [events] on a line of its own
_EVENTS_TABLE = re.compile(r"(?m)^[ \t]*\[[ \t]*events[ \t]*\][ \t]*(?:#[^\n]*)?(?:\n|$)")


def _with_events(held: config.Config, events: Sequence[str]) -> str:
    """The config's text with its failures added, every other line as it was: under its own
    ``[events]`` header when it has one, else as a table after what it holds."""
    line = config.events_block(events).split("\n", 1)[1]
    for text in (
        config.appended(held.text, config.events_block(events)),
        *(
            held.text[: m.end()]
            + ("" if m.group(0).endswith("\n") else "\n")
            + line
            + held.text[m.end() :]
            for m in [_EVENTS_TABLE.search(held.text)]
            if m is not None
        ),
    ):
        try:
            config.parse(text, held.path, held.shown, given=held.given)
        except config.ConfigError:
            continue
        return text
    raise Refused(
        f"{held.shown} sets [events] in a way the failures cannot be added to; write "
        f"failed = [...] under [events] by hand, or give --force to set up again",
        _HELP,
    )


def _decimal(value: float) -> str:
    """A number as a command line gives it, read back as the same number."""
    short = f"{value:g}"
    return short if float(short) == value else repr(value)


def _pair(flag: str, value: str) -> list[str]:
    """An option and its value as command words: one word, joined by ``=``, when the value
    opens with a dash, which a command line would otherwise read as an option of its own."""
    return [f"{flag}={value}"] if value.startswith("-") else [flag, value]


def _command(
    ns: argparse.Namespace,
    stores: Sequence[tuple[str | None, str]],
    events: Sequence[str],
    imported: bool | None,
    answers: Answers,
) -> list[str]:
    """The same setup as one command that asks nothing: the store chosen, each failure, every
    flag given; run in a copy of the folder as it was, it writes the same file."""
    words = ["poisson-trace", "init", "--yes"]
    if ns.config is not None:
        words += _pair("--config", ns.config)
    if ns.force:
        words.append("--force")
    for _, p in stores:
        words += _pair("--store", p)
    if imported is not None:
        words.append("--import" if imported else "--no-import")
    words += answers.flags()
    for event in events:
        words += _pair("--event", event)
    if ns.names is not None:
        words += ["--names", f"from={ns.names}"]
    if ns.max_mde is not None:
        words += _pair("--max-mde", _decimal(ns.max_mde))
    if ns.max_mde_hr is not None:
        words += _pair("--max-mde-hr", _decimal(ns.max_mde_hr))
    if ns.fail_on is not None:
        words += _pair("--fail-on", ",".join(ns.fail_on))
    return words


# an option as a command line writes it, with its value after "=" or not
_OPTION = re.compile(r"(--[a-z][a-z-]*)(?:=(.*))?", re.DOTALL)


def _shell_word(word: str) -> str:
    """One command word as a POSIX shell reads it back: an option bare, its value quoted."""
    option = _OPTION.fullmatch(word)
    if option is None:
        return look.word(word)
    flag, value = option.groups()
    return flag if value is None else f"{flag}={look.word(value)}"


def shell_line(words: Sequence[str], indent: str = "    ") -> str:
    """The words as lines a POSIX shell reads back as one command, broken before an option
    once a line grows long."""
    lines: list[str] = []
    line = ""
    for w in (_shell_word(w) for w in words):
        if line and w.startswith("--") and len(line) + 1 + len(w) > 72:
            lines.append(line)
            line = w
        else:
            line = f"{line} {w}" if line else w
    lines.append(line)
    return (" \\\n" + indent + "  ").join(lines)


def _store_said(name: str | None, path: str, runs: int) -> str:
    held = _plural(runs, "run", "runs")
    return f"store {path} ({held})" if name is None else f"store {name} at {path} ({held})"


def _names_line(index: Any) -> str:
    """The runs, how they are named, the newest names, and how to give one a name."""
    total = len(index.runs)
    if total == 0:
        return "no run whose record Prove can read"
    shown = [r.name for r in index.runs[:NAMES_SHOWN]]
    more = ", …" if total > NAMES_SHOWN else ""
    imported = sum(1 for r in index.runs if r.imported and r.name == r.run_id)
    yours = sum(1 for r in index.runs if r.named_by == "you") - imported
    computed = total - yours - imported
    manifests = "its manifest" if computed == 1 else "their manifests"
    labels = (
        ("named by you", yours),
        ("named at import", imported),
        (f"named from {manifests}", computed),
    )
    parts = [f"{count(n)} {label}" for label, n in labels if n]
    if len(parts) == 1:
        # one way for every run: said once, without its count
        parts = [parts[0].split(" ", 1)[1]]
    mine = yours + imported
    tail = "" if mine else '; none named by you yet: poisson-trace name RUN "a name"'
    return f"{_plural(total, 'run', 'runs')}, {', '.join(parts)} ({', '.join(shown)}{more}){tail}"


def _summary(
    ns: argparse.Namespace,
    shown: str,
    stores: Sequence[tuple[str | None, str]],
    form: str,
    events: Sequence[str],
    command: list[str],
    others: Sequence[FoundStore],
    made: Sequence[Imported],
    verb: str,
    left: Sequence[FoundFile] = (),
) -> Done:
    reach = _reach(ns)
    opened = [_index(p, form) for _, p in stores]
    indexes = [index for _, index in opened]
    runs = {p: len(i.runs) + len(i.unreadable) for (_, p), i in zip(stores, indexes, strict=True)}
    if made:
        sentence = (
            f"{verb} {shown} and imported {_plural(len(made), 'run', 'runs')} into {stores[0][1]}"
        )
        if events:
            sentence += f", failures {', '.join(events)}"
        else:
            sentence += f"; no failures, as {no_failures_why(_imported_outcomes(made).counts)}"
    elif stores:
        said = " and ".join(_store_said(n, p, runs[p]) for n, p in stores)
        if events:
            sentence = f"{verb} {shown}: {said}, failures {', '.join(events)}"
        else:
            reason = no_failures_why(newest_outcomes(opened[0][0], opened[0][1], quiet=True).counts)
            if verb == "left as it was":
                sentence = f"left {shown} as it was: {said}; no failures, as {reason}"
            else:
                sentence = f"{verb} {shown}: {said}; no failures, as {reason}"
    else:
        sentence = f"{verb} {shown} with no store yet"
    if left:
        sentence += f"; {files_said(left)} not imported"
    lines = [f"ok  {sentence}"]
    if indexes:
        lines.append(f"  names    {_names_line(indexes[0])}")
    lines.append("  prove    poisson-prove is installed at the version Trace reads")
    for item in made:
        lines.append(f"  import   {import_line(item, stores[0][1])}")
    if left:
        lines += _left_lines(ns, left, stores)
    taken = {n for n, _ in stores}
    for other in others:
        name, why = store_name(other.path)
        if why is None and name not in taken:
            taken.add(name)
            words = _pair("--add-store", other.path)
            add = look.command("poisson-trace", "init", *(_shell_word(w) for w in words), *reach)
            lines.append(f"  another  {add}")
        else:
            why = why or f"another store here is named {name} by its folder"
            lines.append(f"  another  {other.path} is not added by its folder's name: {why}")
    if stores:
        following = look.command("poisson-trace", "runs", *reach)
    elif left:
        following = _IMPORT_HELP
    else:
        lines.append(
            "Trace reads runs Prove stored, or the result files of the tools "
            "poisson-trace import --help lists."
        )
        following = f"{SWEEP} · or · poisson-trace import --help"
    lines += ["  the same setup, without questions:", "    " + shell_line(command)]
    lines.append(f"next: {following}")
    data = {
        "schema": "poisson-trace.init/1",
        "verdict": "ok",
        "sentence": sentence,
        "config_path": shown,
        "stores": [{"name": n, "path": p, "runs": runs[p]} for n, p in stores],
        "events": list(events),
        "named": sum(1 for index in indexes for r in index.runs if r.named_by == "you"),
        "prove": {"installed": True, "version": look.prove_found()},
        "equivalent_command": command,
        "next": following,
    }
    return Done(data, "\n".join(lines) + "\n")


def _left_lines(
    ns: argparse.Namespace, left: Sequence[FoundFile], stores: Sequence[tuple[str | None, str]]
) -> list[str]:
    """The result files init found and did not import, one import line for each, and what to
    run once a pair is imported: set up with their store, add it beside the one set up, or
    nothing more where they join the store set up."""
    store = config.beside(config.path_of(ns.config), IMPORTED_STORE)
    reach = _reach(ns)
    one = len(left) == 1
    said = (
        f"  left out {_plural(len(left), 'result file', 'result files')}, not imported; "
        + ("the line below imports it." if one else "the lines below import them.")
        + " To compare two, run the pair's lines (a word in capitals is yours to fill in)"
    )
    if not stores:
        finish = look.command(
            "poisson-trace",
            "init",
            "--force",
            *(_shell_word(w) for w in _pair("--store", store)),
            *reach,
        )
        said += f", then run {finish}:"
    elif _same_folder(stores[0][1], store):
        held = config.CONFIG if ns.config is None else look.shown(ns.config)
        said += f"; they join {stores[0][1]}, which {held} reads:"
    else:
        add = look.command(
            "poisson-trace", "init", *(_shell_word(w) for w in _pair("--add-store", store)), *reach
        )
        said += f", then run {add} to add their store beside this one:"
    shown = shown_lines(left, store)
    if len(left) <= LINES_SHOWN:
        # the import's help is the next command, or a line away from it
        shown = shown[:-1]
    return [said, *(f"    {line}" for line in shown)]


def _same_folder(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normpath(os.path.abspath(a)) == os.path.normpath(os.path.abspath(b))


# ---------- --add-store ----------


def add_store(
    ns: argparse.Namespace, path: Path, shown: str, written: Callable[[str], None] = _no_hook
) -> Done:
    """One store added to the config there already, named by its folder, or as the store every
    verb reads when the config names none; every line it holds is kept, and nothing is asked."""
    if _sets(ns, ("event", *_SETTING)) or ns.force:
        raise look.Usage(
            "--add-store adds one store to a config and takes no other setup flag", _HELP
        )
    reach = _reach(ns)
    if not path.exists() and not path.is_symlink():
        raise Refused(
            f"there is no {shown} to add a store to; poisson-trace init writes one",
            look.command("poisson-trace", "init", *reach),
        )
    held = config.load(ns.config)
    assert held is not None
    typed = ns.add_store
    why = _storable(typed)
    if why is not None:
        raise Refused(why, _HELP)
    for _, p in held.stores():
        with contextlib.suppress(OSError):
            if os.path.samefile(p, typed):
                raise Refused(f"{held.shown} names the store at {typed} already", _HELP)
    where = names.toml_string(config.written_path(path, typed))
    if held.store is None:
        # the config names no store every verb reads: this one becomes it
        name: str | None = None
        block = f"[store]\npath = {where}\n"
    else:
        name, why = store_name(typed)
        if why is not None:
            raise Refused(f"a store added is named by its folder, and {why}", _HELP)
        if name in held.named:
            raise Refused(
                f"{held.shown} names a store {name} already, at {held.named[name]}", _HELP
            )
        block = f"[store.{name}]\npath = {where}\n"
    text = config.appended(held.text, block)
    try:
        after = config.parse(text, held.path, held.shown, given=held.given)
    except config.ConfigError:
        after = None
    if (
        after is None
        or (name is None and after.store is None)
        or (name and name not in after.named)
    ):
        table = "[store]" if name is None else f"[store.{name}]"
        raise Refused(
            f"{held.shown} sets its stores in a way a new {table} table cannot follow; add it "
            "by hand",
            _HELP,
        )
    config.write_config_file(held.path, held.shown, text)
    written(f"stopped  interrupted: {held.shown} was written whole; poisson-trace doctor checks it")
    stores = after.stores()
    indexes = [_index(p, after.names_from)[1] for _, p in stores]
    added = next(i for (n, _), i in zip(stores, indexes, strict=True) if n == name)
    held_runs = _plural(len(added.runs) + len(added.unreadable), "run", "runs")
    if name is None:
        sentence = (
            f"added the store at {typed} ({held_runs}) to {held.shown}, as the store every verb "
            "reads"
        )
    else:
        sentence = f"added the store {name} at {typed} ({held_runs}) to {held.shown}"
    following = look.command("poisson-trace", "doctor", *reach)
    if after.events and name is not None:
        added_store, _ = _index(typed, after.names_from)
        read = newest_outcomes(added_store, added, quiet=True)
        if not any(e in read.counts for e in after.events):
            sentence += (
                f"; {read.whose} {read.carry} none of the failures {', '.join(after.events)}, so "
                f"give --event with --store {name}"
            )
        else:
            following = look.command("poisson-trace", "runs", *_pair("--store", name), *reach)
    command = ["poisson-trace", "init", *_pair("--add-store", typed)]
    if ns.config is not None:
        command += _pair("--config", ns.config)
    data = {
        "schema": "poisson-trace.init/1",
        "verdict": "ok",
        "sentence": sentence,
        "config_path": held.shown,
        "stores": [
            {"name": n, "path": p, "runs": len(i.runs) + len(i.unreadable)}
            for (n, p), i in zip(stores, indexes, strict=True)
        ],
        "events": list(after.events or ()),
        "named": sum(1 for index in indexes for r in index.runs if r.named_by == "you"),
        "prove": {"installed": True, "version": look.prove_found()},
        "equivalent_command": command,
        "next": following,
    }
    return Done(data, f"ok  {sentence}\n\nnext: {following}\n")
