"""Shared helpers for TF19's tests: the terminal app (spec section 17.2, with section 17.3 for the
pages it links to; the design's terminal-app section and its rulings DM5, DM6, DM9, DM12 and
DM13, all ruled yes on 2026-11-05; PA11 of TF13, which sent the objects only the app needs
here). This pair's own readings are TF19-A1 on, ``log/trace-tf19-a/rulings.md``; each is frozen
at its recommended answer.

Not a test module and not collected.

**How the app is reached.** Two ways, as a user reaches it, as Prove's PF6 reaches its own.

- Textual's test pilot runs the app in this process (:func:`drive`), presses keys and reads the
  screen cell by cell with each cell's colour role (:func:`grid_of`, Prove's own reader). What
  the core returned to the app is recorded by wrapping the core's functions (:class:`Spy`), so a
  test holds each screen to the object it renders and never to a number of its own. The
  browser and the clipboard are fakes; a network call fails the test.
- A pseudo-terminal runs ``python -m poisson_trace`` as a shell does (:func:`run_pty`), for what
  happens before the app opens and after it leaves.

**The app as these tests read it** (A1 to A14).

- **A1 The entry point.** ``poisson_trace._app.TraceApp``, a Textual ``App[int]`` built as
  ``TraceApp(config=None, store=None)``: ``config`` is the ``--config`` value as typed, ``store``
  the ``--store`` value as typed, each None when not given; with neither, the app reads the
  current folder's ``trace.toml`` as every verb does, and with no ``trace.toml`` there it opens
  on home's empty state. Its exit code is Textual's ``return_code``. ``TraceApp.after`` is what
  the app leaves to print once it has left the terminal (a string, possibly empty), as a verb's
  ``stopped`` line prints. Textual is imported by the app's modules alone: the modules of
  ``poisson_trace`` whose name begins ``_app`` (``_app.py``, the screens; ``_app_shell.py``, the
  copy of Prove's shell; any further ``_app_*.py``).
- **A2 How it opens.** ``poisson-trace`` with no verb opens the app when stdin and stdout are
  terminals (stderr may be piped; the app draws on stdout's terminal, as Prove's A21), ``CI`` is
  unset (any value, the empty one included, is set) and ``TERM`` is not ``dumb``. ``--config
  PATH`` and ``--store PATH`` with no verb open it on that config or store; both may be given,
  and the store then wins, as on every verb. ``--plain`` with no verb is never the app.
  Otherwise the bare command prints what main prints today: ``error: no verb was given; the
  verbs are …`` and ``  next: poisson-trace --help``, exit 2. On a pipe, ``--config PATH`` or
  ``--store PATH`` with no verb is that same refusal (today it is ``unrecognized arguments``),
  since both are now options of the bare command (A3). ``NO_COLOR`` set and not empty keeps the
  app and draws no green, yellow or red; set but empty, it changes nothing. A Textual that
  cannot be imported: ``error: the terminal app cannot start: Textual cannot be imported``,
  ``  next: poisson-trace --help``, nothing on stdout, exit 1 (Prove's A16). Below 80 × 24 the
  one line is ``the window is W × H; the app needs at least 80 × 24``, with ``q quit``.
- **A3 The top options.** The top ``--help`` gains two rows in its options, ``--store PATH`` and
  ``--config PATH``, and nothing else moves: every verb keeps its own ``--store`` and
  ``--config``, and ``--store``/``--config`` before a verb are read as today.
- **A4 The header.** ``poisson-trace · <title>``, then two spaces and the subject when there is
  one, and at the right edge the store slot (DM6): ``trace.toml`` when the app reads the
  folder's config, the ``--config`` value as typed when one was given, the ``--store`` value as
  typed when one was given, ``no config`` on the empty state.
- **A5 The screens and their titles.** ``home``, ``runs``, ``run``, ``imports``, ``compare``,
  ``fix-check`` (the two pickers; subject ``pick two runs``), the verdict screen titled
  ``compare`` or ``fix-check`` (subject ``<before> → <after>``), ``changes``, ``could not say``
  and ``help``. From home: ``r`` runs, ``i`` imports, ``c`` compare's picker, ``f`` fix-check's
  picker, ``?`` help, Enter on a run row its run screen, Enter on a saved verdict row its
  verdict screen (a saved where opens the run screen). From runs: Enter on a run its run screen.
  From a picker: Enter compares the two chosen runs. From a verdict screen and the run screen: ``d`` its
  could not say screen; from the fix-check verdict ``g`` the changes screen of the same two runs.
- **A6 The screen's own letters** (the look file: a letter means the same on every screen that
  has it). ``c`` compare, ``f`` fix-check, ``r`` runs, ``i`` imports, ``n`` name the focused run,
  ``s`` the next store the config names (DM9), ``k`` the failures by kind (the per-kind table
  and the failures-by-kind section), ``t`` the screen's second table (the run's long table of
  the share not yet failed, step by step; the fix-check verdict's per-input table), ``d`` what
  this cannot say, ``g`` the changes screen, ``l`` previous and latest, ``h`` set the limit
  asked for, ``m`` the lines the window has no room for, ``space`` choose. ``m``, ``k`` and ``t``
  show what they show in place of the table, and the same key pressed again goes back to it. The design's ``c``
  for could not say and ``s`` for the run's steps would give one letter two meanings; they are
  ``d`` and ``t`` here (A6, put to Taylor).
- **A7 What each screen renders** (the facts rule). Home: ``commands.doctor`` (its verdict line
  first and its ``next`` as the ``next`` detail line, DM5), ``core.saved_verdicts`` and
  ``api.runs`` of the config's main store, newest first together; with no ``trace.toml``, the
  empty state, no refusal. Runs: ``api.runs`` of the store, ``core.run_sources`` for the
  ``target or tool`` column, ``core.saved_verdicts`` below. Run: ``api.where``. Imports: the
  config's store that Trace's import wrote (``imported`` in the workspace), ``api.runs`` of it
  (uncounted when it does not carry the config's failures, with ``runs``'s note on the message
  line, DM9), ``core.run_sources`` for each run's tool and file, listed above the screen's table;
  the table's rows are ``core.found_results`` for the files ``init`` finds under the current
  folder and nothing imported (columns ``file`` and ``what it is``), since Enter acts on them. The verdict screens:
  ``api.compare``, ``api.fix_check`` and ``api.changes`` with the config's failures and
  ceilings (``--max-mde-hr``, ``--max-mde`` from ``[check]``), fix-check with ``--inputs all``.
  The app calls these as module attributes (``api.where(...)``, ``core.saved_verdicts(...)``,
  ``commands.doctor(...)``), so the spy sees each call.
- **A8 Every fact.** Each screen, with what its keys show (``m``, ``k``, ``t``) and its could not
  say screen, carries every fact the plain command prints for the same runs and settings: each
  number as it prints it, each run's name and id, each command it names; the summary's lines
  (Compared or Read, Question, Answer, Next) and every line of "Before you act on this" whole,
  on the verdict screen itself, never shortened (at 80 × 24 the lines that do not fit are
  behind ``m``, DM13, and the links block stays on screen). Behind ``m``, the lines the body has
  no room for scroll a page at a time with PgDn and ↓ (and back with PgUp and ↑), so each is
  whole on one read; ``m`` again returns to the table (A16: Prove's shell cuts them to the
  window). Could not say carries each sentence of the report's "What this cannot say" whole.
- **A9 Saves (AD7).** Every verdict the app shows (where on the run screen, compare, fix-check,
  changes) is saved as ``api.save`` saves it, into the store the verb saves into, and the
  message line is ``saved  <kind> <first 12 hex>``. A store that cannot be written: the screen
  shows the verdict and the message line is ``note: the verdict was not saved: <the system's
  words>``.
- **A10 Links (section 17.2, Charts).** A link is a detail line ``label  trace/<address>``:
  ``pages  trace/index.html`` on home; ``curve  trace/where/<id>.html#curve`` and ``page
  trace/where/<id>.html`` on the run screen; ``curves  trace/compare/<id>.html#curves``,
  ``hazard ratio  trace/compare/<id>.html#hazard-ratio`` and ``page  trace/compare/<id>.html``
  on compare's verdict; ``page  trace/<kind>/<id>.html`` on fix-check's and changes';
  ``page  trace/<kind>/<id>/could-not-say.html`` on could not say. When a link is on screen its
  page is on disk. ``tab`` moves the focus to the links; Enter on a focused link calls
  ``webbrowser.open`` once with ``file://<the store, absolute>/.poisson/ui/trace/<address>``;
  ``y`` copies that same address with Textual's ``copy_to_clipboard`` and the message line is
  ``note: copied the link``.
- **A11 Questions.** Naming a run (``n``) and importing a found file (Enter) ask on the message
  line, ending ``[y/N]``; only ``y`` answers yes; ``n``, Esc, Enter and ``q`` answer no, and
  ``q`` does not quit then. A yes runs the core's ``api.name`` or ``api.import_run`` and the
  message line is its verdict line (word and sentence). A found file whose import line holds a
  word in capitals (promptfoo's ``PROMPT``) is never run: Enter shows the line and a ``note:``
  naming the word to fill (DM12).
- **A12 Exits.** ``q`` exits 0 and the app leaves nothing to print. Ctrl-C exits 130; the app
  leaves one line, ``stopped  interrupted; nothing was saved, named or imported`` when it wrote
  none of those, and otherwise ``stopped  interrupted; kept `` followed by what it wrote, each
  saved verdict as ``<kind> <first 12 hex>``, each import and each name by the run's name.
  Work (a comparison, a where, an import) runs beside the screen, which says so in one body line,
  one word ending ``…`` (``comparing…``, ``importing…``); Ctrl-C during it exits 130 at once, and
  work let go saves and keeps nothing (an import the app's exit ends; the import cannot be
  stopped part way through the core today, TF19-A21).
- **A13 Help** lists every key of every screen's key bar, and names every screen.
- **A14 Never.** No network call; no environment variable read whose name holds ``KEY``,
  ``TOKEN``, ``SECRET`` or ``PASSWORD``; no file written but through the core (a saved verdict
  and its pages, an import, a name): no write in the app's modules' own code, and nothing
  changed outside the stores' ``.poisson/`` but an import's run folder and the names file the
  core writes.

**The PA11 objects** (A15), core functions in ``poisson_trace.core``, each reading only the
paths it is given, printing nothing, reading no environment variable and writing nothing:

- ``core.saved_verdicts(store) -> list[SavedVerdict]``: Trace's saved verdicts in a store,
  newest first (by save time, then kind, then id, as the runs page orders them). A
  ``SavedVerdict`` is a frozen dataclass: ``kind``, ``id`` (16 hex), ``runs`` (the runs' names,
  a tuple), ``run_ids`` (a tuple), ``verdict``, ``sentence``, ``saved_at`` (as ``artifact.json``
  records it), ``folder`` (``.poisson/artifacts/<kind>/<id>``) and ``page``
  (``trace/<kind>/<id>.html``).
- ``core.run_sources(store) -> list[RunSource]``: each run ``runs`` lists, in its order: a
  frozen dataclass ``run_id``, ``target`` (a Prove run's target, None for an import), ``tool``
  (the reader an import came from, None for a Prove run), ``files`` (the imported files' names,
  no folder, a tuple; empty for a Prove run) and ``target_or_tool`` (the tool, else the target).
- ``core.found_results(folder, *, store="trace-store") -> list[FoundResult]``: the result files
  ``init`` finds under ``folder`` and would offer to import (a JUnit report with no test case is
  left out, as ``init`` leaves it out), in the order its search finds them (its listing's order
  for every file but DeepEval's, which the listing shows by folder): a frozen dataclass ``path``
  (as ``init`` prints it, relative to ``folder``), ``tool``, ``said`` (``init``'s words for it),
  ``command`` (the import line ``init`` prints for it, with ``--store STORE``), ``fill`` (the
  words in capitals the user must fill in, a tuple) and ``imported`` (whether a run of a store
  under ``folder`` was imported from a file with these bytes, by the digest its run record
  keeps).

**The stores.** :func:`app_world` builds TF18's pages workspace (``tf18_support.build_work``:
the Prove store ``store`` with two where verdicts, a compare, a fix-check and a changes saved;
``tables`` with a fix-check and a changes; ``jstore``, two JUnit imports), adds ``trace.toml``
at its root (:data:`CONFIG_TEXT`: ``store`` main, ``jstore`` as ``imported``, the failures
``violated`` and ``timeout``, both ceilings) and ``results/`` (result files found and not
imported). It is built once per worker; a test that opens the app copies it first.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import fcntl
import hashlib
import json
import os
import re
import select
import shutil
import socket
import struct
import subprocess
import sys
import termios
import time
from collections.abc import Callable, Iterator, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from conftest import FIXTURES
from tf0_support import REPO, Ran, chdir, trace

TF19 = FIXTURES / "tf19"
PINS = TF19 / "main-pins.json"
PROVE_SHELL = TF19 / "prove-shell.json"
MAIN = "b988bd3"
PACKAGE = REPO / "src" / "poisson_trace"
TOOL = "poisson-trace"
APP_MODULE = "poisson_trace._app"
SHELL_MODULE = "poisson_trace._app_shell"
EV = ["--event", "violated", "--event", "timeout"]

CONFIG_TEXT = """\
version = 1

[store]
path = "store"

[store.imported]
path = "jstore"

[events]
failed = ["violated", "timeout"]

[check]
max_mde = 0.1
max_mde_hr = 1.5
"""

#: The result files put under ``results/``: found by init's search, none of them imported.
RESULT_FILES = (
    ("inspect", "2026-10-07T04-23-47-00-00_trace-fixture_CV3jq8f7FTjwkaYb3zj3m2.eval"),
    ("openai-evals", "old.jsonl"),
    ("openai-evals", "new.jsonl"),
    ("promptfoo", "results.json"),
    ("junit", "trace-suite-2.xml"),
)

NO_VERB = "error: no verb was given; the verbs are init, runs, name, where, compare, fix-check, changes, handover, import, doctor, ui and report"
NO_TEXTUAL = "error: the terminal app cannot start: Textual cannot be imported"
KEPT_NONE = "stopped  interrupted; nothing was saved, named or imported"
KEPT = "stopped  interrupted; kept "
SMALL = re.compile(r"^the window is (\d+) × (\d+); the app needs at least 80 × 24$")
#: Keys planted in the environment while the app runs: Trace reads no key (A14).
PLANTED_KEYS = {
    "OPENAI_API_KEY": "sk-tf19-planted-openai-0000000000000000",
    "ANTHROPIC_API_KEY": "sk-ant-tf19-planted-anthropic-000000000",
    "POISSON_TRACE_UPLOAD_TOKEN": "tf19-planted-upload-token-00000000000",
    "HF_TOKEN": "hf_tf19plantedtoken000000000000000",
}
KEY_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.IGNORECASE)
HEX12 = re.compile(r"\b[0-9a-f]{12}\b")
RUN_ID = re.compile(r"\b\d{8}T\d{6}Z-[0-9a-f]{4}\b")


# ---------- the workspace ----------


def make_world(tmp: Path) -> Path:
    """The app's workspace (see the module's opening), built in ``tmp``."""
    from tf18_support import build_work

    work = build_work(tmp)
    (work / "trace.toml").write_text(CONFIG_TEXT, encoding="utf-8")
    results = work / "results"
    results.mkdir()
    for reader, name in RESULT_FILES:
        shutil.copy2(FIXTURES / "ingest" / reader / name, results / name)
    return work


_WORLD: dict[str, Path] = {}


def app_world(tmp_factory: Any) -> Path:
    """The workspace, built once per worker (``tmp_path_factory``); never written by a test."""
    if "world" not in _WORLD:
        _WORLD["world"] = make_world(tmp_factory.mktemp("tf19-world"))
    return _WORLD["world"]


def copy_world(world: Path, tmp: Path, name: str = "work") -> Path:
    dest = tmp / name
    shutil.copytree(world, dest, symlinks=True)
    return dest


def ids(work: Path) -> dict[str, tuple[str, str, str]]:
    """``label -> (store, kind, id)`` of every verdict the workspace saved (``tf18_support.SAVES``)."""
    doc = json.loads((work / "ids.json").read_text(encoding="utf-8"))
    return {label: (s, k, i) for label, (s, k, i) in doc.items()}


def cli(work: Path, argv: Sequence[str]) -> Ran:
    with chdir(work):
        return trace(list(argv))


def snapshot(root: Path) -> dict[str, str]:
    """Every file under ``root`` and the digest of its bytes."""
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink() and "__pycache__" not in p.parts:
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def changed(before: Mapping[str, str], after: Mapping[str, str]) -> set[str]:
    return {k for k in set(before) | set(after) if before.get(k) != after.get(k)}


# ---------- the screen, cell by cell (Prove's PF6 reader, as its A22 has it) ----------


@dataclass
class Grid:
    """One screen of the app: each row's text, exactly as wide as the window, and each cell's role:
    ``V`` reverse (the focus), ``G``/``Y``/``R`` green, yellow, red, ``B`` bold, ``D`` dim, blank."""

    rows: list[str]
    masks: list[str]
    off_palette: set[str]

    @property
    def width(self) -> int:
        return len(self.rows[0]) if self.rows else 0

    @property
    def height(self) -> int:
        return len(self.rows)

    def text(self) -> str:
        return "\n".join(r.rstrip() for r in self.rows)

    @property
    def header(self) -> str:
        return self.rows[0]

    @property
    def body(self) -> list[str]:
        return [r.rstrip() for r in self.rows[2:-3]]

    @property
    def message(self) -> str:
        return self.rows[-3].rstrip()

    @property
    def keybar(self) -> str:
        return self.rows[-1].rstrip()

    def title(self) -> str:
        """The header's words after ``poisson-trace · ``, up to two spaces."""
        m = re.match(r"^poisson-trace · (\S+(?: \S+)*)", self.header)
        assert m, self.header
        return m.group(1)

    def _parts(self) -> list[str]:
        return re.split(r"\s{2,}", self.header.rstrip())

    def subject(self) -> str:
        """The header's subject: what follows the title after two spaces, up to the store slot."""
        parts = self._parts()
        return parts[1] if len(parts) == 3 else ""

    def slot(self) -> str:
        """The store slot at the header's right edge."""
        parts = self._parts()
        assert len(parts) >= 2, self.header
        return parts[-1]

    def focused(self) -> list[int]:
        return [i for i, row in enumerate(self.rows) if row.startswith("›")]

    def focused_text(self) -> str:
        f = self.focused()
        assert len(f) == 1, (f, self.text())
        return self.rows[f[0]]

    def mask_of(self, row: int, start: int, length: int) -> str:
        return self.masks[row][start:start + length]

    def bar(self) -> list[tuple[str, str]]:
        """The key bar's entries, ``(key, word)``, in order: entries part at three spaces, a key
        from its word at one."""
        return [(e.split(" ", 1)[0], e.split(" ", 1)[1] if " " in e else "") for e in self.keybar.strip().split("   ") if e]

    def keys(self) -> list[str]:
        """The key bar's keys, in order (a key is bold; its word, when shown, is dim)."""
        row, mask = self.rows[-1], self.masks[-1]
        out, i = [], 0
        while i < len(row):
            if mask[i] == "B":
                j = i
                while j < len(row) and mask[j] == "B":
                    j += 1
                out.append(row[i:j])
                i = j
            else:
                i += 1
        return out

    def body_text(self) -> str:
        """The body's rows joined, the focus marker read as a space, whitespace collapsed: what a
        fact is looked for in (a wrapped line reads whole)."""
        rows = [(" " + r[1:]) if r.startswith("›") else r for r in self.body]
        return norm(" ".join(rows))

    def line_starting(self, label: str) -> str | None:
        """The body row that holds ``label`` as a detail line's label (``  label  value``)."""
        for r in self.body:
            if re.match(rf"^[ ›] {re.escape(label)}(?:\s{{2,}}|$)", r):
                return r
        return None

    def value_of(self, label: str) -> str | None:
        """A detail line's value, its wrapped rows joined."""
        rows = [(" " + r[1:]) if r.startswith("›") else r for r in self.body]
        for i, r in enumerate(rows):
            m = re.match(rf"^  {re.escape(label)}(\s{{2,}})(\S.*)$", r)
            if not m:
                continue
            col = 2 + len(label) + len(m.group(1))
            parts = [m.group(2)]
            for nxt in rows[i + 1:]:
                if nxt[:col].strip() == "" and nxt.strip():
                    parts.append(nxt.strip())
                else:
                    break
            return norm(" ".join(parts))
        return None


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def columns(header: str) -> list[str]:
    """A table header's column names: its words split where two spaces or more part them."""
    return [c for c in re.split(r"\s{2,}", header.strip()) if c]


def name_shown(name: str, shown: str) -> bool:
    """Whether a name is on a screen whole, or cut in the middle with ``…`` as the shell cuts a
    name column (its whole form is on the screen its row opens)."""
    if name in shown:
        return True
    for m in re.finditer(r"(\S+)…(\S+)", shown):
        head, tail = m.group(1), m.group(2)
        if name.startswith(head) and name.endswith(tail) and len(head) + len(tail) < len(name):
            return True
    return False


def found_steps(work: Path, i: int) -> list[str]:
    """The keys from home to the ``i``-th file the imports screen lists as found, not imported,
    and Enter on it: the imports screen's rows are those files, in ``core.found_results``'s order
    (A7)."""
    return ["i", *["down"] * i, "enter"]


def _role(style: Any) -> str:
    if style is None:
        return " "
    if style.reverse:
        return "V"
    color = style.color
    number = None
    if color is not None and not color.is_default and color.number is not None and color.type.name in ("STANDARD", "WINDOWS"):
        number = color.number
    if number in (2, 10):
        return "G"
    if number in (3, 11):
        return "Y"
    if number in (1, 9):
        return "R"
    if style.bold:
        return "B"
    if style.dim:
        return "D"
    return " "


def _off(color: Any, *, background: bool = False) -> str | None:
    if color is None or color.is_default:
        return None
    if not background and color.type.name in ("STANDARD", "WINDOWS") and color.number in (1, 2, 3, 9, 10, 11):
        return None
    return f"{'background' if background else 'foreground'} {color.type.name}:{color.name}"


def grid_of(app: Any) -> Grid:
    """The screen as the user's terminal shows it, cell by cell: the compositor's full update, the
    one Textual's own ``export_screenshot`` reads (Prove's ``pf6_support.grid_of``)."""
    width, height = app.size
    update = app.screen._compositor.render_update(full=True, screen_stack=app._background_screens)
    rows: list[str] = []
    masks: list[str] = []
    off: set[str] = set()
    for line in update.strips:
        text, mask = [], []
        for strip in line:
            for seg in strip:
                if seg.control:
                    continue
                for ch in seg.text:
                    text.append(ch)
                    mask.append(_role(seg.style))
                if seg.style is not None:
                    for c, background in ((seg.style.color, False), (seg.style.bgcolor, True)):
                        bad = _off(c, background=background)
                        if bad:
                            off.add(bad)
        row, m = "".join(text), "".join(mask)
        rows.append(row[:width].ljust(width))
        masks.append(m[:width].ljust(width))
    assert len(rows) == height, (len(rows), height)
    return Grid(rows, masks, off)


# ---------- what the core returned to the app ----------


#: The core's functions the app reads through (A7, A9, A11), by module.
SPIED = {
    "poisson_trace.api": ("open_store", "load_config", "where", "compare", "fix_check", "changes", "runs", "name",
                          "forget_name", "list_names", "import_run", "save", "build_pages"),
    "poisson_trace.core": ("saved_verdicts", "run_sources", "found_results"),
    "poisson_trace.commands": ("doctor",),
}


class Spy:
    """Every call the app made of a core function (:data:`SPIED`), with its arguments and its
    result or the exception it raised, in order."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any], Any]] = []

    @contextlib.contextmanager
    def installed(self) -> Iterator[Spy]:
        import importlib

        saved: list[tuple[Any, str, Any]] = []
        try:
            for module_name, names in SPIED.items():
                module = importlib.import_module(module_name)
                for name in names:
                    real = getattr(module, name, None)
                    if real is None:
                        continue
                    saved.append((module, name, real))
                    setattr(module, name, self._wrap(f"{module_name.rsplit('.', 1)[1]}.{name}", real))
            yield self
        finally:
            for module, name, real in saved:
                setattr(module, name, real)

    def _wrap(self, name: str, real: Callable[..., Any]) -> Callable[..., Any]:
        def call(*args: Any, **kwargs: Any) -> Any:
            try:
                result = real(*args, **kwargs)
            except BaseException as exc:
                self.calls.append((name, args, kwargs, exc))
                raise
            self.calls.append((name, args, kwargs, result))
            return result

        call.__wrapped__ = real  # type: ignore[attr-defined]
        return call

    def results(self, name: str) -> list[Any]:
        return [r for n, _, _, r in self.calls if n == name and not isinstance(r, BaseException)]

    def called(self, name: str) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
        return [(a, k) for n, a, k, _ in self.calls if n == name]

    def names(self) -> list[str]:
        return [n for n, _, _, _ in self.calls]


# ---------- the fakes ----------


@dataclass
class Fakes:
    opened: list[str] = field(default_factory=list)
    copied: list[str] = field(default_factory=list)
    connects: list[Any] = field(default_factory=list)
    env_read: list[str] = field(default_factory=list)


class _RecordingEnviron(MutableMapping[str, str]):
    """``os.environ`` in the test's process while the app runs, recording each name Trace's own
    code reads (as TF13's ``EnvRecorder`` does: a read whose nearest caller outside ``os`` and the
    mapping machinery is a module of ``poisson_trace``; a whole copy of the environment so taken is
    recorded as ``*``)."""

    def __init__(self, real: Any, seen: list[str]) -> None:
        self._real = real
        self._seen = seen

    def _note(self, key: str) -> None:
        frame = sys._getframe(2)
        skip = (os.__file__, __file__, "_collections_abc.py", "<frozen os>", "<frozen _collections_abc>")
        while frame is not None and frame.f_code.co_filename.endswith(skip):
            frame = frame.f_back  # type: ignore[assignment]
        if frame is not None and frame.f_code.co_filename.startswith(str(PACKAGE)):
            self._seen.append(key)

    def __getitem__(self, key: str) -> str:
        self._note(key)
        return self._real[key]  # type: ignore[no-any-return]

    def get(self, key: str, default: Any = None) -> Any:  # type: ignore[override]
        self._note(key)
        return self._real.get(key, default)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            self._note(key)
        return key in self._real

    def __setitem__(self, key: str, value: str) -> None:
        self._real[key] = value

    def __delitem__(self, key: str) -> None:
        del self._real[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._real)

    def __len__(self) -> int:
        return len(self._real)

    def copy(self) -> dict[str, str]:
        self._note("*")
        return dict(self._real)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


@contextlib.contextmanager
def faked(fakes: Fakes) -> Iterator[Fakes]:
    """The browser, the clipboard and the network replaced while the app runs; ``os.environ``
    recording what is read."""
    import webbrowser

    from textual.app import App

    saved_web = {n: getattr(webbrowser, n) for n in ("open", "open_new", "open_new_tab", "get")}
    saved_copy = App.copy_to_clipboard
    saved_sock = (socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo)
    saved_env = os.environ

    def opened(url: str, *a: Any, **k: Any) -> bool:
        fakes.opened.append(url)
        return True

    class _Browser:
        def open(self, url: str, *a: Any, **k: Any) -> bool:
            return opened(url)

        open_new = open_new_tab = open

    def copy(self: Any, text: str) -> None:
        fakes.copied.append(text)

    def refuse(*a: Any, **k: Any) -> Any:
        fakes.connects.append(a[1:] if a else k)
        raise OSError("a network call in a TF19 test")

    try:
        webbrowser.open = opened  # type: ignore[assignment]
        webbrowser.open_new = opened  # type: ignore[assignment]
        webbrowser.open_new_tab = opened  # type: ignore[assignment]
        webbrowser.get = lambda *a, **k: _Browser()  # type: ignore[assignment]
        App.copy_to_clipboard = copy  # type: ignore[method-assign]
        socket.socket.connect = refuse  # type: ignore[method-assign]
        socket.socket.connect_ex = refuse  # type: ignore[method-assign]
        socket.create_connection = refuse  # type: ignore[assignment]
        socket.getaddrinfo = refuse  # type: ignore[assignment]
        os.environ = _RecordingEnviron(saved_env, fakes.env_read)  # type: ignore[assignment]  # noqa: B003
        yield fakes
    finally:
        os.environ = saved_env  # noqa: B003
        for n, f in saved_web.items():
            setattr(webbrowser, n, f)
        App.copy_to_clipboard = saved_copy  # type: ignore[method-assign]
        (socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo) = saved_sock  # type: ignore[method-assign]


@contextlib.contextmanager
def environment(**variables: str | None) -> Iterator[None]:
    saved = {k: os.environ.get(k) for k in variables}
    try:
        for k, v in variables.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------- driving the app ----------

#: A step of :func:`drive` that reads the screen instead of pressing a key.
SNAP = "<snap>"
#: A step that types text into whatever is asking (a name), a character at a time.


@dataclass(frozen=True)
class Type:
    text: str


@dataclass(frozen=True)
class Quick:
    """A key pressed without waiting for the work it starts to end (the screen read a moment
    later): for a key pressed while the app works."""

    key: str


@dataclass(frozen=True)
class Resize:
    width: int
    height: int


@dataclass
class Session:
    grids: list[Grid]
    code: int | None
    after: str
    spy: Spy
    fakes: Fakes
    app: Any

    @property
    def last(self) -> Grid:
        return self.grids[-1]


#: A body line that says work is under way, one word ending ``…`` (``  comparing…``, as Prove's
#: app writes it): :func:`drive` waits it out.
WORKING = re.compile(r"^[ ›] [a-z]+ing…$")


async def _settle(pilot: Any, app: Any, timeout: float = 120.0) -> None:
    """Until the app's work is done and its screen stands still: no body line saying work is
    under way, the screen the same over two reads."""
    deadline = time.monotonic() + timeout
    last = None
    still = 0
    while time.monotonic() < deadline:
        await pilot.pause(0.05)
        if getattr(app, "_exit", False) or not app.is_running:
            return
        try:
            g = grid_of(app)
        except Exception:  # noqa: BLE001 - not drawn yet
            continue
        busy = any(WORKING.match(r) for r in g.body)
        if not busy and g.rows == last:
            still += 1
            if still >= 2:
                return
        else:
            still = 0
        last = g.rows
    raise AssertionError("the app did not settle")


def drive(
    work: Path | None,
    steps: Sequence[str | Type | Resize | Quick | Callable[[], object]] = (),
    *,
    size: tuple[int, int] = (120, 40),
    config: str | None = None,
    store: str | None = None,
    env: Mapping[str, str | None] | None = None,
    patch: Callable[[], contextlib.AbstractContextManager[Any]] | None = None,
) -> Session:
    """The app run by Textual's pilot in ``work`` (the current folder while it runs), each step
    pressed in turn (a key name as Textual's pilot takes it, :class:`Type` for text, :data:`SNAP`
    to read the screen, a callable to call between keys), the screen read once more at the end unless the app has left. The core
    is spied on, and the browser, the clipboard, the network and the environment faked. The
    screen is read once more at the end, unless the app has left or the last step read it."""
    import importlib

    module = importlib.import_module(APP_MODULE)
    spy, fakes = Spy(), Fakes()
    grids: list[Grid] = []
    holder: dict[str, Any] = {}

    async def run() -> None:
        app = module.TraceApp(config=config, store=store)
        holder["app"] = app
        async with app.run_test(size=size) as pilot:
            await _settle(pilot, app)
            for step in steps:
                if not app.is_running:
                    break
                if step == SNAP:
                    grids.append(grid_of(app))
                    continue
                if callable(step):
                    step()
                    continue
                if isinstance(step, Type):
                    for ch in step.text:
                        await pilot.press(ch if ch != " " else "space")
                elif isinstance(step, Resize):
                    await pilot.resize_terminal(step.width, step.height)
                elif isinstance(step, Quick):
                    await pilot.press(step.key)
                    await pilot.pause(0.3)
                    continue
                else:
                    await pilot.press(step)
                await _settle(pilot, app)
            if app.is_running and (not steps or steps[-1] != SNAP):
                grids.append(grid_of(app))

    extra = dict(env or {})
    with contextlib.ExitStack() as stack:
        if work is not None:
            stack.enter_context(chdir(work))
        stack.enter_context(environment(**{**{k: None for k in ("CI", "NO_COLOR")}, **PLANTED_KEYS, **extra}))
        stack.enter_context(spy.installed())
        stack.enter_context(faked(fakes))
        if patch is not None:
            stack.enter_context(patch())
        asyncio.run(run())
    app = holder["app"]
    return Session(grids, app.return_code, str(getattr(app, "after", "") or ""), spy, fakes, app)


# ---------- a screen's keys and the facts it carries ----------

#: How each screen is reached from home, by keys alone (A5).
NAV_KEYS: dict[str, list[str]] = {
    "home": [],
    "runs": ["r"],
    "run": ["r", "enter"],
    "imports": ["i"],
    "compare": ["c"],
    "fix-check": ["f"],
    "verdict compare": ["c", "enter"],
    "verdict fix-check": ["f", "enter"],
    "changes": ["f", "enter", "g"],
    "could not say": ["c", "enter", "d"],
    "help": ["?"],
}

#: The keys every screen shares, as the key bar writes them (the look file's table).
SHARED = ("↑↓", "enter", "esc", "tab", "/", "y", "m", "?", "q")
#: Each screen's own letters (A6), as the key bar writes them.
OWN = {
    "home": ("c", "f", "r", "i"),
    "runs": ("n", "c", "f", "s"),
    "run": ("c", "t", "d"),
    "imports": ("s",),
    "compare": ("space", "l", "h"),
    "fix-check": ("space", "l", "h"),
    "verdict compare": ("k", "d", "f"),
    "verdict fix-check": ("k", "t", "d", "g"),
    "changes": ("d",),
    "could not say": (),
}

NUMBER = re.compile(r"(?<![\w.])[-+−]?\d[\d,]*(?:\.\d+)?(?:e[-+]?\d+)?%?(?![\w])")
BACKTICKED = re.compile(r"`([^`]+)`")


def plain_lines(text: str) -> list[str]:
    """A plain report's lines as facts are read from them: markdown's marks dropped (a heading's
    ``#``, a list's ``- ``, bold, code), a table row's cells joined by two spaces, rule rows and
    blank lines left out."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or re.fullmatch(r"\|(?:-+\|)+", s):
            continue
        s = re.sub(r"^#+ ", "", s)
        s = re.sub(r"^- ", "", s)
        s = s.replace("**", "")
        if s.startswith("|"):
            s = "  ".join(c.strip() for c in s.strip("|").split("|"))
        out.append(s)
    return out


def facts_of(text: str) -> set[str]:
    """The facts of a plain command's output (A8): every number as it prints it, every run id,
    every 12- or 16-hex id at 12, and every command it names in backticks or after ``next:``."""
    facts: set[str] = set()
    for line in plain_lines(text):
        for m in NUMBER.finditer(line):
            facts.add(m.group(0))
        facts.update(RUN_ID.findall(line))
        for m in re.finditer(r"\b[0-9a-f]{16}\b", line):
            facts.add(m.group(0)[:12])
        for m in BACKTICKED.finditer(line):
            facts.add(norm(m.group(1)))
        if line.startswith("next: "):
            facts.add(norm(line[len("next: "):]))
    return facts


def missing_facts(text: str, shown: str) -> list[str]:
    """The facts of ``text`` not on the screens read as ``shown`` (their body text joined): a
    number is found as a whole token, a command whole with its spaces collapsed."""
    shown = norm(shown.replace("`", ""))
    out = []
    for fact in sorted(facts_of(text)):
        if " " in fact:
            if fact not in shown:
                out.append(fact)
        elif not re.search(rf"(?<![\w.]){re.escape(fact)}(?![\w])", shown):
            out.append(fact)
    return out


def section_lines(report: str, heading: str) -> list[str]:
    """The list items of one ``## heading`` section of a plain report, markdown's marks dropped."""
    out, inside = [], False
    for line in report.splitlines():
        if line.startswith("## "):
            inside = line[3:].strip() == heading
            continue
        if inside and line.startswith("- "):
            out.append(norm(line[2:].replace("**", "").replace("`", "")))
    return out


def summary_values(report: str) -> list[tuple[str, str]]:
    """The summary's lines as ``(label, text)``: ``- Compared: …`` read as ``("Compared", "…")``."""
    out = []
    for line in section_lines(report, "Summary"):
        label, _, rest = line.partition(": ")
        out.append((label, rest))
    return out


# ---------- the pseudo-terminal ----------


@dataclass
class Step:
    """Wait until the terminal shows ``until`` (or ``delay`` seconds pass), then type ``send``."""

    send: bytes
    until: str | tuple[str, ...] | None = None
    delay: float = 0.0


@dataclass
class PtyRun:
    code: int
    out: str
    err: str
    out_screen: list[str] = field(default_factory=list)
    seen: list[list[str]] = field(default_factory=list)


def _winsize(fd: int, cols: int, rows: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def child_env(home: Path, **extra: str | None) -> dict[str, str]:
    """An environment for ``python -m poisson_trace``: this one with ``HOME`` in the test's folder,
    no ``CI``, no ``NO_COLOR``, ``TERM=xterm-256color``, and ``extra`` on top (None removes)."""
    env = {k: v for k, v in os.environ.items() if k not in ("CI", "NO_COLOR", "PYTEST_XDIST_WORKER")}
    env.update({"HOME": str(home), "TERM": "xterm-256color", "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8",
                "COLUMNS": "", "LINES": ""})
    env.pop("COLUMNS")
    env.pop("LINES")
    for k, v in extra.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    return env


def run_pty(
    argv: Sequence[str],
    *,
    home: Path,
    cwd: Path,
    cols: int = 120,
    rows: int = 40,
    stdin: str = "pty",
    stdout: str = "pty",
    stderr: str = "pty",
    steps: Sequence[Step] = (),
    timeout: float = 60,
    python_path: Sequence[Path] = (),
    **extra: str | None,
) -> PtyRun:
    """``python -m poisson_trace ARGV…`` with stdin, stdout and stderr each on a terminal or not
    (Prove's ``pf6_support.run_pty``): ``stdin`` is ``pty`` or ``null``; ``stdout`` ``pty`` or
    ``pipe``; ``stderr`` ``pty`` (stdout's terminal) or ``pipe``. Each terminal is ``cols`` ×
    ``rows``. ``steps`` are typed in turn into stdin's terminal."""
    import pyte

    terminals: dict[str, tuple[int, int]] = {}

    def terminal(name: str) -> tuple[int, int]:
        if name not in terminals:
            controller, user = os.openpty()
            _winsize(user, cols, rows)
            terminals[name] = (controller, user)
        return terminals[name]

    out_fd: Any = terminal("main")[1] if stdout == "pty" else subprocess.PIPE
    if stdin == "pty":
        in_fd: Any = terminal("main")[1] if stdout == "pty" else terminal("input")[1]
    else:
        in_fd = subprocess.DEVNULL
    err_fd: Any = (terminal("main")[1] if "main" in terminals else terminal("errors")[1]) if stderr == "pty" else subprocess.PIPE
    env = child_env(home, **extra)
    if python_path:
        env["PYTHONPATH"] = os.pathsep.join([*(str(p) for p in python_path), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    proc = subprocess.Popen(
        [sys.executable, "-m", "poisson_trace", *argv], cwd=cwd, env=env,
        stdin=in_fd, stdout=out_fd, stderr=err_fd, close_fds=True, start_new_session=True,
    )
    for _, user in terminals.values():
        os.close(user)
    readers: dict[int, str] = {controller: name for name, (controller, _) in terminals.items()}
    if proc.stdout is not None:
        readers[proc.stdout.fileno()] = "out-pipe"
    if proc.stderr is not None:
        readers[proc.stderr.fileno()] = "err-pipe"
    raw: dict[str, bytearray] = {name: bytearray() for name in readers.values()}
    screens = {name: pyte.Screen(cols, rows) for name in terminals}
    streams = {name: pyte.ByteStream(screens[name]) for name in terminals}
    typed_into = terminals.get("main", terminals.get("input", (None, None)))[0]
    pending = list(steps)
    seen: list[list[str]] = []
    step_started = time.monotonic()
    deadline = time.monotonic() + timeout
    open_fds = set(readers)
    shown_name = "main" if "main" in screens else next(iter(screens), None)
    try:
        while open_fds:
            if time.monotonic() > deadline:
                shown = screens[shown_name].display if shown_name else raw
                raise AssertionError(f"timed out after {timeout} s; screen: {shown}")
            ready, _, _ = select.select(list(open_fds), [], [], 0.05)
            for fd in ready:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    chunk = b""
                if not chunk:
                    open_fds.discard(fd)
                    continue
                name = readers[fd]
                raw[name] += chunk
                if name in streams:
                    streams[name].feed(chunk)
            if pending and typed_into is not None and shown_name is not None:
                step = pending[0]
                shown = "\n".join(screens[shown_name].display)
                wanted = (step.until,) if isinstance(step.until, str) else step.until or ()
                if all(w in shown for w in wanted) and time.monotonic() - step_started >= step.delay:
                    seen.append(list(screens[shown_name].display))
                    os.write(typed_into, step.send)
                    pending.pop(0)
                    step_started = time.monotonic()
            if proc.poll() is not None and not ready:
                for fd in list(open_fds):
                    with contextlib.suppress(OSError):
                        while True:
                            r, _, _ = select.select([fd], [], [], 0.05)
                            if not r:
                                break
                            chunk = os.read(fd, 65536)
                            if not chunk:
                                break
                            raw[readers[fd]] += chunk
                            if readers[fd] in streams:
                                streams[readers[fd]].feed(chunk)
                    open_fds.discard(fd)
        code = proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        for controller, _ in terminals.values():
            with contextlib.suppress(OSError):
                os.close(controller)
    assert not pending, f"steps left untaken: {pending}; screen: {screens[shown_name].display if shown_name else raw}"

    def text(name: str) -> str:
        return raw.get(name, bytearray()).decode("utf-8", "replace").replace("\r\n", "\n")

    out = text("main") if stdout == "pty" else text("out-pipe")
    if stderr == "pty":
        err = out if stdout == "pty" else text("errors")
    else:
        err = text("err-pipe")
    return PtyRun(code, out, err, out_screen=list(screens["main"].display) if "main" in screens else [], seen=seen)


_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]|\x1b[()][0-9A-Za-z]")


def strip_escapes(text: str) -> str:
    return _ESCAPE.sub("", text)


def after_app(text: str) -> str:
    """What the terminal shows once a full-screen app has left: the text after its last return
    from the alternate screen, escapes removed."""
    at = text.rfind("\x1b[?1049l")
    return strip_escapes(text[at + len("\x1b[?1049l"):] if at >= 0 else text).replace("\r", "")


def opened_app(text: str) -> bool:
    """Whether a full-screen app took the terminal: the alternate screen was entered."""
    return "\x1b[?1049h" in text


def blocker(folder: Path, *modules: str) -> Path:
    """A folder to put first on ``PYTHONPATH`` in which each module named cannot be imported."""
    folder.mkdir(parents=True, exist_ok=True)
    for name in modules:
        (folder / f"{name}.py").write_text(f"raise ImportError('{name} is blocked by a TF19 test')\n", encoding="utf-8")
    return folder


# ---------- the app's modules, read as source ----------


def app_files() -> list[Path]:
    """The app's modules (A1): ``poisson_trace/_app*.py``."""
    return sorted(p for p in PACKAGE.glob("_app*.py"))


def imports_of(path: Path) -> set[str]:
    """Every module a source file imports, by its full dotted name (``from a.b import c`` is
    ``a.b`` and ``a.b.c``)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = ("." * node.level) + (node.module or "")
            if node.level:
                base = "poisson_trace" + ("." + node.module if node.module else "")
            out.add(base)
            out.update(f"{base}.{a.name}" for a in node.names)
    return out


# ---------- what must not move: the pins of main ----------


def pin_corpus() -> dict[str, tuple[str, str, list[list[str]]]]:
    """Every invocation whose plain and ``--json`` output TF19 leaves as main prints it, piped:
    TF18's corpus whole (the failure breakdown pair's, every verb's help, the four verbs with
    ``--save``, ``--out``, ``--svg``, ``handover``), the three TF18 changed and main now prints
    (the refusals naming the verbs, ``handover --check``'s ``ok``), and beside them the pages'
    verbs as TF18 built them: ``ui`` and ``report`` and their helps and refusals, and the bare
    command on a pipe with no argument, ``--plain``, ``--json`` and ``--debug``. Left out, as
    another session (Trace Report Open Fix, branch ``trace-report-open``) changes them: ``report
    --help``, and ``report DIR`` on a bundle that already has its page."""
    from tf18_support import CHANGED, SAVES, pin_corpus as tf18_corpus

    out = dict(tf18_corpus())
    for label in ("verb: unknown", "verb: none", "handover: ok"):
        out[label] = CHANGED[label]
    out["help: ui"] = ("work", "trace", [["ui", "--help"]])
    out["ui: store"] = ("work", "trace", [["ui", "--store", "store"], ["ui", "--store", "store", "--json"]])
    out["ui: config"] = ("work", "trace", [["ui", "--config", "conf/trace.toml"]])
    out["ui: tables"] = ("work", "trace", [["ui", "--store", "tables"]])
    out["ui: no store"] = ("work", "trace", [["ui", "--store", "no-such"], ["ui", "--store", "no-such", "--json"]])
    out["ui: none named"] = ("work", "trace", [["ui"]])
    fix = SAVES["fix-check"][1]
    where = SAVES["where after"][1]
    out["report: made"] = ("work", "trace", [[*fix, "--out", "rb"], ["report", "rb"], ["report", "rb", "--force"]])
    out["report: where"] = ("work", "trace", [[*where, "--out", "rw"], ["report", "rw"]])
    out["report: not a bundle"] = ("work", "trace", [["report", "conf"]])
    out["report: no folder"] = ("work", "trace", [["report", "no-such"]])
    out["report: not valid"] = ("work", "trace", [[*fix, "--out", "rv"], ["!edit", "rv/result.json"], ["report", "rv"]])
    out["report: usage"] = ("work", "trace", [["report"], ["report", "rb", "--json"]])
    for label, argv in (("bare: plain", ["--plain"]), ("bare: json", ["--json"]), ("bare: debug", ["--debug"]),
                        ("bare: config=", ["--config=conf/trace.toml"])):
        out[label] = ("work", "trace", [argv])
    return out


#: The invocations whose output TF19 changes, pinned from main to say exactly how (A2, A3).
CHANGED: dict[str, tuple[str, str, list[list[str]]]] = {
    "help: top": ("work", "trace", [["--help"]]),
    "bare: config": ("work", "trace", [["--config", "conf/trace.toml"]]),
    "bare: store": ("work", "trace", [["--store", "store"]]),
    "bare: both": ("work", "trace", [["--store", "store", "--config", "conf/trace.toml"]]),
    "bare: plain config": ("work", "trace", [["--plain", "--config", "conf/trace.toml"]]),
}

#: The slow ones: TF18's.
def slow() -> frozenset[str]:
    from tf18_support import SLOW

    return SLOW


def run_steps(work: Path, place: str, kind: str, steps: Sequence[Sequence[str]]) -> Iterator[Ran]:
    from tf18_support import run_steps as tf18_steps

    yield from tf18_steps(work, place, kind, steps)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


TIME = re.compile(r"\d{4}-\d\d-\d\d[T ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|\+00:00)?")


def normal(text: str, *roots: Path) -> str:
    for root in roots:
        text = text.replace(str(root.resolve()), "<ROOT>").replace(str(root), "<ROOT>")
    return text


def pages_pins(work: Path) -> dict[str, str]:
    """The pages TF18 builds for the workspace, each file's digest with every time written as
    ``<TIME>`` (a saved verdict's save time is the moment it was saved): ``ui --config
    conf/trace.toml`` (the Prove store and the table store) and ``ui --store jstore``. Each saved
    verdict's save time is first set to one moment, so the saved verdicts' order on the runs page
    is by kind and id alone (the workspace saves them within a second or two, which may straddle
    a second)."""
    out: dict[str, str] = {}
    for path in sorted(work.glob("*/.poisson/artifacts/*/*/artifact.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("tool") == "poisson-trace" or path.parts[-3] in ("where", "compare", "fix-check", "changes"):
            doc["created_at"] = "2026-11-08T00:00:00Z"
            path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    for argv in (["ui", "--config", "conf/trace.toml"], ["ui", "--config", "conf/trace.toml", "--store", "tables"],
                 ["ui", "--store", "jstore"]):
        ran = cli(work, argv)
        assert ran.code == 0, (argv, ran.text)
    for store in ("store", "tables", "jstore"):
        base = work / store / ".poisson" / "ui" / "trace"
        for p in sorted(base.rglob("*")):
            if p.is_file():
                text = p.read_bytes().decode("utf-8", "replace")
                out[f"{store}/{p.relative_to(base)}"] = digest(TIME.sub("<TIME>", normal(text, work)))
    return out
