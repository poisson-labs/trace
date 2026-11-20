"""The terminal app: ``poisson-trace`` with no verb on a terminal.

A face over the core, as the command line is. It opens on home and reaches every screen by keys
alone; each screen renders an object the core returns (``commands.doctor``, ``api.runs``,
``api.where``, ``api.compare``, ``api.fix_check``, ``api.changes``, and the three objects only
the app needs, ``core.saved_verdicts``, ``core.run_sources`` and ``core.found_results``), laid
out by the shell copied from Prove (``_app_shell``). It computes nothing: every number, name,
verdict and sentence on a screen is one the plain command prints for the same runs and settings,
read off the result's own report. It writes only through the core: a verdict
it shows is saved and the pages are rebuilt, a name and an import happen after a ``[y/N]``
answered ``y``, and nothing else. It never makes a network call and reads no key; of the
environment it reads ``NO_COLOR`` alone.

**The screens.** Home (``doctor``'s verdict line and its next command, the config's stores and
failures, the pages' link, then the saved verdicts and the runs newest first); runs (the
listing with ``target or tool``, the saved verdicts, ``n`` names the focused run); run (one run's
``where``); imports (the store Trace's import wrote, each run's tool and file, and the files
``init`` found and did not import, each with its import line: Enter runs it after a question);
the two pickers (``compare``, ``fix-check``: ``space`` chooses, ``l`` previous and latest,
``h`` sets the limit when the config has none); the verdict screens; changes; could not say;
help. ``s`` on runs and imports moves to the config's next store.

**A verdict screen** is the report's sections laid out in the shell's three parts: above the
table, the summary (Compared or Read, Question, Answer, Next) and the command's ``next``, "before
you act on this" in full, each section's ``label  value`` lines and prose; the one table the
report's main section holds (the kinds of step for where, the arms for compare, the two versions
for fix-check, the inputs that changed for changes); below it, the figures that follow that table
in the report, then the links into the pages and the saved line. A section's prose stands above
the table and its figures below, so the links block is never pushed off a small window.
The failures by kind (and compare's per-kind table) are behind ``k``; the second table (where's
share not yet failed step by step, fix-check's per-input table) behind ``t``; what this cannot say
is its own screen, ``d``. At 80 × 24 the lines above the table with no room go behind ``m``, as
the shell has it, and there they scroll a page at a time (PgDn, PgUp, the arrows), so every caveat
is whole on one read. Letters mean one thing on every screen.

**Entry point.** ``TraceApp(config=None, store=None)``: ``config`` is the ``--config`` value as
typed, ``store`` the ``--store`` value as typed; with neither the app reads the current folder's
``trace.toml`` as every verb does, and with no ``trace.toml`` there it opens on home's empty
state. The exit code is Textual's ``return_code``: 0 for ``q``, 130 for Ctrl-C; ``after`` is the
one line the app leaves to print once it has left the terminal (Ctrl-C's ``stopped`` line, naming
what was kept). Work (a verdict worked out, an import) runs beside the screen, which says so in
one word; Ctrl-C during it exits at once and work let go saves nothing.
"""

from __future__ import annotations

import os
import re
import shlex
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.events import Key, Resize
from textual.filter import Monochrome, NoColor
from textual.widgets import Static

from poisson_trace import api, commands, core, look
from poisson_trace._app_shell import (
    BACK,
    BLANK,
    MIN_HEIGHT,
    MIN_WIDTH,
    MOVE,
    OPEN,
    Column,
    Detail,
    Line,
    Page,
    Shell,
    block,
    lay_table,
    text_line,
    verdict_line,
    verdict_style,
    wrap_line,
)

__all__ = ["TraceApp"]

TOOL = "poisson-trace"
#: The one word a screen shows while its verdict is worked out beside it.
WORKING = {
    "where": "reading…",
    "compare": "comparing…",
    "fix-check": "checking…",
    "changes": "listing…",
}
#: The report section whose table is the screen's table, by kind.
MAIN_TABLE = {
    "where": "Where they die, by kind of step",
    "compare": "Comparison",
    "fix-check": "The two versions",
    "changes": "Inputs that changed",
}
#: The sections (or subsections) behind ``k``, the failures by kind.
BEHIND_K = {
    "where": (),
    "compare": ("Per kind", "Failures by kind"),
    "fix-check": ("Failures by kind",),
    "changes": ("Failures by kind",),
}
#: The section behind ``t``, the screen's second table.
BEHIND_T = {"where": "Share not yet failed, by step", "fix-check": "Inputs that changed"}
CANNOT_SAY = "What this cannot say"
BEFORE_YOU_ACT = "Before you act on this"
SUMMARY = "Summary"
#: The report's sentence for an imported run, carried to the could not say screen too.
NO_TRACES = "This run has no traces"
KEPT_NONE = "stopped  interrupted; nothing was saved, named or imported"
KEPT = "stopped  interrupted; kept "
#: The widest a ``label: value`` line's label is before the line reads as prose.
LABEL_WIDTH = 36
#: The limit a comparison could not have seen below: the report says it under the per-kind
#: table, the verdict screen carries it under its own table.
LIMIT = "could not have detected"
_RULE = re.compile(r"\|(?:-+\|)+")
_NUMBER = re.compile(r"^[-+−]?[\d,.]+(?:e[-+]?\d+)?(?:%| points)?$|^–$|^-$")
_OPEN_KEYS = [MOVE, OPEN, BACK]
LINKS = ("tab", "links")
COPY = ("y", "copy")


# ---------- the parts of a screen the app adds to the shell's page ----------


@dataclass
class Screen(Page):
    """A page with what Trace's screens add: the store its links are in, the verdict's kind,
    the lines behind ``k`` and ``t``, and the whole of what scrolls while the lines behind
    ``m`` (or behind ``k`` or ``t``) are shown, with how far it has scrolled."""

    path: str = ""
    kind: str = ""
    kinds: list[Line] = field(default_factory=list)
    second_table: list[Line] = field(default_factory=list)
    whole_top: list[Line] | None = None
    whole_second: list[Line] | None = None
    skip: int = 0
    #: Work the screen cannot be left during (an import the user said yes to).
    busy: bool = False


@dataclass
class Section:
    """One ``##`` section of a plain report, or one ``###`` subsection of it."""

    name: str
    sub: str
    lines: list[str]


def _sections(report: str) -> list[Section]:
    """The report's sections in order, the title and the verdict line left out."""
    out: list[Section] = []
    started = False
    for line in report.splitlines():
        if line.startswith("# "):
            started = True
            continue
        if not started:
            continue
        if line.startswith("## "):
            out.append(Section(line[3:].strip(), "", []))
        elif line.startswith("### "):
            out.append(Section(out[-1].name if out else "", line[4:].strip(), []))
        elif out:
            out[-1].lines.append(line)
    return out


def _when(iso: str) -> str:
    """A time as the listing prints it: the day and the minute, UTC."""
    return f"{iso[:10]} {iso[11:16]}" if len(iso) >= 16 and iso[10] == "T" else iso


def _plain(text: str) -> str:
    return text.replace("**", "")


def _cells(row: str) -> list[str]:
    return [_plain(c.strip()) for c in row.strip().strip("|").split("|")]


def _detail_of(line: str) -> tuple[str, str] | None:
    """A ``- label: value`` line as its label and value, when the label is short enough to be
    one; otherwise the line reads as prose."""
    if not line.startswith("- "):
        return None
    label, sep, rest = line[2:].partition(": ")
    if not sep or not 0 < len(label) <= LABEL_WIDTH or "`" in label or label.startswith("{"):
        return None
    return _plain(label), _plain(rest)


def _figure_of(line: str) -> tuple[str, str] | None:
    """A ``label: value`` line written without a list mark, as the lines under compare's arm
    table are (``statistic``, ``direction``, ``hazard ratio, after against before``): its label
    and value, when the label is short, starts small and names no command; a label with a
    qualifier after a comma keeps the qualifier at the head of the value. Else None."""
    detail = _detail_of(line)
    if detail is not None:
        return detail
    label, sep, rest = line.partition(": ")
    if not sep or not 0 < len(label) <= LABEL_WIDTH or "`" in label or not label[:1].islower():
        return None
    head, comma, qualifier = label.partition(", ")
    if comma:
        return _plain(head), _plain(f"{qualifier}: {rest}")
    return _plain(label), _plain(rest)


def _heading(name: str) -> Line:
    """A section's heading on the screen: its first letter small."""
    return text_line(name[:1].lower() + name[1:], "dim")


def _table_lines(rows: Sequence[Sequence[str]], width: int) -> list[Line]:
    """A report table laid out for the width: its header dim, its number columns to the right."""
    if not rows:
        return []
    head, cells = rows[0], rows[1:]
    columns = [
        Column(name, right=bool(cells) and all(_NUMBER.match(r[i]) for r in cells))
        for i, name in enumerate(head)
    ]
    header, laid = lay_table(columns, cells, width)
    return [header, *laid]


def _render(lines: Sequence[str], width: int) -> list[Line]:
    """A section's lines on the screen: ``label: value`` lines as one ``label  value`` block,
    a table laid out for the width, a list item as a bullet, a bold line bold, the rest prose
    wrapping two deeper than it starts; blank lines part the blocks and are not drawn."""
    out: list[Line] = []
    details: list[Detail] = []
    table: list[list[str]] = []

    def flush() -> None:
        if details:
            out.extend(block(details))
            details.clear()
        if table:
            out.extend(_table_lines(table, width))
            table.clear()

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("|"):
            if details:
                flush()
            if not _RULE.fullmatch(line.strip()):
                table.append(_cells(line))
            continue
        if table:
            flush()
        if not line.strip():
            flush()
            continue
        if line.startswith("next: "):
            details.append(Detail("next", line[len("next: ") :], code=True))
            continue
        detail = _detail_of(line)
        if detail is not None:
            details.append(Detail(*detail))
            continue
        flush()
        if line.startswith("- "):
            out.append(Line(f"  - {_plain(line[2:])}", hang=4))
        elif line.startswith("**") and line.endswith("**"):
            text = _plain(line)
            out.append(Line(f"  {text}", [(2, 2 + len(text), "bold")], hang=2))
        else:
            out.append(Line(f"  {_plain(line)}", hang=2))
    flush()
    return out


def _split_at_table(lines: Sequence[str]) -> tuple[list[str], list[list[str]], list[str]]:
    """A section's lines parted at its first table: the lines before it, the table's rows, and
    the lines after it."""
    before: list[str] = []
    rows: list[list[str]] = []
    after: list[str] = []
    for line in lines:
        if line.startswith("|") and not after:
            if not _RULE.fullmatch(line.strip()):
                rows.append(_cells(line))
        elif rows:
            after.append(line)
        else:
            before.append(line)
    return before, rows, after


def _import_call(command: str) -> tuple[str, dict[str, Any]]:
    """An import line as the core takes it: the run's name and the reader's flags, from the
    words after ``poisson-trace import TOOL FILE``; a repeated flag is a list, a bare one True."""
    words = shlex.split(command)[4:]
    flags: dict[str, Any] = {}
    i = 0
    while i < len(words):
        name = words[i][2:].replace("-", "_")
        if i + 1 < len(words) and not words[i + 1].startswith("--"):
            value = words[i + 1]
            if name == "failed":
                flags.setdefault(name, []).append(value)
            else:
                flags[name] = value
            i += 2
        else:
            flags[name] = True
            i += 1
    flags.pop("store", None)
    return str(flags.pop("run", "")), flags


# ---------- the app ----------


class TraceApp(Shell):
    """The terminal app over a config's stores, or over one store."""

    CSS = """
    Screen { background: ansi_default; color: ansi_default; }
    Static { background: ansi_default; color: ansi_default; width: 100%; height: 100%; }
    """
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [Binding("ctrl+c", "interrupt", priority=True, show=False)]

    def __init__(self, config: str | None = None, store: str | None = None) -> None:
        no_color = os.environ.get("NO_COLOR")
        super().__init__(ansi_color=True)
        # NO_COLOR set and not empty drops the colours; set but empty changes nothing. Textual
        # takes any NO_COLOR as set, so its own filter goes when the value is empty.
        self.mono = bool(no_color)
        if no_color == "":
            self._filters = [f for f in self._filters if not isinstance(f, (NoColor, Monochrome))]
            self.no_color = False
        self.config_arg, self.store_arg = config, store
        self.cfg: api.Config | None = None
        self.refusal: api.Refusal | None = None
        try:
            self.cfg = api.load_config(config) if config is not None else api._config_here()
        except api.Refusal as e:
            self.refusal = e
        if store is not None:
            self.shown = store
        elif config is not None:
            self.shown = config
        elif self.cfg is not None:
            self.shown = "trace.toml"
        else:
            self.shown = "no config"
        self.stack: list[Screen] = []
        #: What the app leaves to print once it has left the terminal.
        self.after = ""
        #: What was written this session, for Ctrl-C's line: each saved verdict, name, import.
        self.kept: list[str] = []
        self.cancel = threading.Event()
        self._mounted = False

    # ---------- the config and its stores ----------

    def held(self) -> Any:
        return None if self.cfg is None else self.cfg._held

    def events(self) -> list[str]:
        held = self.held()
        return list(held.events or ()) if held is not None else []

    def config_shown(self) -> str:
        held = self.held()
        return str(held.shown) if held is not None else "trace.toml"

    def stores(self) -> list[tuple[str | None, str]]:
        """``(name, path)`` of every store the app can show: the one ``--store`` named first
        (by the name the config gives it, or as a path), else the config's unnamed store first,
        then every other store the config names."""
        held = self.held()
        everyone: list[tuple[str | None, str]] = (
            [(n, str(p)) for n, p in held.stores()] if held is not None else []
        )
        if self.store_arg is None:
            return everyone
        first = next(((n, p) for n, p in everyone if n == self.store_arg), (None, self.store_arg))
        rest = [
            (n, p) for n, p in everyone if os.path.realpath(p) != os.path.realpath(first[1])
        ]
        return [first, *rest]

    def word_of(self, name: str | None, path: str) -> str | None:
        """What the API takes as the store: the ``--store`` value as typed for the store it
        named, a config name for a named store, None for the config's unnamed store."""
        if self.store_arg is not None and (name, path) == self.stores()[0]:
            return self.store_arg
        return name

    def kw(self) -> dict[str, Any]:
        return {"config": self.cfg} if self.cfg is not None else {}

    def listing(self, word: str | None, path: str) -> tuple[Any, str]:
        """The store's runs as ``runs`` lists them under the config's failures, or, for a
        store that does not carry them, with the failed column uncounted and ``runs``'s
        note for the message line."""
        try:
            return api.runs(word, **self.kw()), ""
        except api.Refusal:
            listed = api.runs(path)
            return listed, f"note: {listed.notes[0]}" if listed.notes else ""

    def saved(self, path: str) -> list[core.SavedVerdict]:
        try:
            return core.saved_verdicts(path)
        except api.Refusal:
            return []

    def pages(self, word: str | None) -> bool:
        """The pages rebuilt before a link shows, so that the link resolves; whether
        they could be."""
        try:
            api.build_pages(word, **self.kw())
        except (api.Refusal, OSError):
            return False
        return True

    def uri(self, path: str, address: str) -> str:
        return f"file://{Path(path).resolve()}/.poisson/ui/{address}"

    # ---------- textual ----------

    def compose(self) -> ComposeResult:
        yield Static(id="canvas")

    def on_mount(self) -> None:
        self._mounted = True
        self.stack = [self.home()]
        self.redraw()

    def width(self) -> int:
        return int(self.size.width)

    def push(self, page: Screen) -> None:
        self.stack.append(page)
        self.redraw()

    def replace(self, page: Screen) -> None:
        self.stack[-1] = page
        self.redraw()

    def pop(self) -> None:
        if len(self.stack) > 1:
            left = self.stack.pop()
            if len(self.stack) == 1 and self.stack[0].title == "home" and left.title != "help":
                focus = self.stack[0].focus
                self.stack[0] = self.home()  # what was saved, named or imported since shows
                self.stack[0].focus = focus
        self.redraw()

    def message(self, text: str) -> None:
        if self.stack:
            self.stack[-1].message = text
        self.redraw()

    def action_interrupt(self) -> None:
        self.cancel.set()
        self.after = KEPT + ", ".join(self.kept) if self.kept else KEPT_NONE
        self.exit(return_code=130)

    def redraw(self) -> None:
        if not self._mounted or not self.stack:
            return
        try:
            canvas = self.query_one("#canvas", Static)
        except Exception:  # noqa: BLE001 - not composed yet: the next redraw draws it
            return
        w, h = self.size
        if w < MIN_WIDTH or h < MIN_HEIGHT:
            canvas.update(
                Text(
                    f"the window is {w} × {h}; the app needs at least {MIN_WIDTH} × "
                    f"{MIN_HEIGHT}\nq quit"
                )
            )
            return
        page = self.stack[-1]
        if page.layout is not None and page.laid_width != w:
            self._unscroll(page)
            page.layout(w)
            page.laid_width = w
            if not page.rows and page.links():
                page.in_links = True
        canvas.update(self._draw(page, w, h))

    def on_resize(self, event: Resize) -> None:
        self.call_after_refresh(self.redraw)  # a page is laid out again for a new width

    def on_key(self, event: Key) -> None:
        event.stop()
        event.prevent_default()
        w, h = self.size
        if w < MIN_WIDTH or h < MIN_HEIGHT:
            if event.character == "q":
                self.exit(return_code=0)
            return
        key, ch = event.key, event.character or ""
        if key == "space":
            ch = " "
        if not self.stack:
            return
        page = self.stack[-1]
        if not page.keep_message:
            page.message = ""
        if page.filtering:
            self._filter_key(page, key, ch)
            return
        typed = {"enter": "\r", "escape": "\x1b", "backspace": "\x7f"}.get(key, ch)
        if page.on_key is not None and typed and page.on_key(typed):
            self.redraw()
            return
        if (page.show_more or page.show_second) and key in ("up", "down", "pageup", "pagedown"):
            self._scroll(page, key, h)
        elif ch == "/" and page.rows:
            page.filtering, page.filter, page.focus = True, "", 0
        elif key == "escape" and page.filter:
            page.filter, page.focus = "", 0
        elif key in ("up", "down", "pageup", "pagedown", "home", "end"):
            self._move(page, key, h)
        elif key == "tab":
            if page.links() and page.visible_rows():
                page.in_links = not page.in_links
                page.focus, page.other_focus = page.other_focus, page.focus
        elif key == "enter":
            self._enter(page)
        elif ch == "y":
            self._copy(page)
        elif ch == "m":
            if page.show_more:
                self._unscroll(page)
            elif page.more:
                self._unscroll(page)
                page.whole_top, page.show_more = list(page.top), True
        elif key == "escape":
            self.pop()
            return
        elif ch == "?" and page.title != "help":
            self.push(self.help_page())
            return
        elif ch == "q":
            self.exit(return_code=0)
            return
        self.redraw()

    # ---------- the lines behind m, k and t: scrolled a page at a time ----------

    def _unscroll(self, page: Screen) -> None:
        """The screen's table again: the lines behind ``m``, ``k`` or ``t`` put away."""
        if page.whole_top is not None:
            page.top = page.whole_top
        page.whole_top, page.whole_second = None, None
        page.show_more, page.show_second, page.skip = False, False, 0
        page.second = []

    def _show_second(self, page: Screen, lines: list[Line]) -> None:
        """``k`` or ``t``: the lines in place of the table, or the table again when they are
        the lines already shown."""
        shown = page.show_second and page.whole_second is lines
        self._unscroll(page)
        if not shown and lines:
            page.whole_second, page.second, page.show_second = lines, lines, True

    def _scroll(self, page: Screen, key: str, height: int) -> None:
        whole = page.whole_top if page.show_more else page.whole_second
        if whole is None:
            return
        room = height - 5
        w = self.width()

        def rows_of(lines: Sequence[Line]) -> int:
            return sum(len(wrap_line(line, w, False)) for line in lines)

        def fitting(start: int) -> int:
            """How many lines from ``start`` on fit the body at once."""
            used, n = 0, 0
            for line in whole[start:]:
                used += rows_of([line])
                if used > room:
                    break
                n += 1
            return n

        at = page.skip
        if key in ("down", "pagedown"):
            if rows_of(whole[at:]) <= room:
                return  # the rest is whole on screen already
            at += 1 if key == "down" else max(1, fitting(at))
        else:
            if key == "up":
                at -= 1
            else:
                while at > 0 and rows_of(whole[max(0, at - 1) : page.skip]) <= room:
                    at -= 1
                if at == page.skip:
                    at -= 1
        page.skip = max(0, min(len(whole) - 1, at))
        if page.show_more:
            page.top = whole[page.skip :]
        else:
            page.second = whole[page.skip :]

    # ---------- links and copies ----------

    def _enter(self, page: Screen) -> None:
        link = self._focused_link(page)
        if link is not None and link.link is not None:
            commands.show_page(self.uri(page.path, link.link))
            return
        row = page.focused_row()
        if row is not None and row.opens is not None:
            row.opens()

    def _copy(self, page: Screen) -> None:
        """``y``: the focused link's whole ``file://`` address, the focused row's command, or
        the screen's first command."""
        link = self._focused_link(page)
        if link is not None and link.link is not None:
            self.copy_to_clipboard(self.uri(page.path, link.link))
            page.message = "note: copied the link"
            return
        row = page.focused_row()
        code = row.copy if row is not None and row.copy else None
        if code is None:
            code = next((line.copy for line in [*page.top, *page.bottom] if line.copy), None)
        if code is not None:
            self.copy_to_clipboard(code)
            page.message = "note: copied"

    def refused(self, page: Screen, exc: api.Refusal) -> Screen:
        """A refusal on the screen: the command's ``error:`` line on the message line, its
        notes and next commands, and the whole sentence when the window cannot hold it."""
        sentence = str(exc)
        page.message, page.keep_message = f"error: {sentence}", True
        nexts, notes = list(exc.next), list(exc.notes)

        def layout(width: int) -> None:
            page.top = block([Detail("note", n) for n in notes])
            if len(page.message) > width:
                page.top += [*block([Detail("error", sentence)]), BLANK]
            page.top += block([Detail("next", c, code=True) for c in nexts])
            page.header, page.rows, page.bottom = None, [], []

        page.layout = layout
        return page

    # ---------- home ----------

    def home(self) -> Screen:
        page = Screen(
            "home",
            keys=[MOVE, OPEN, LINKS, ("c", "compare"), ("f", "fix-check"), ("r", "runs"),
                  ("i", "imports"), COPY],
        )
        if self.refusal is not None:
            return self.refused(page, self.refusal)
        if self.cfg is None and self.store_arg is None:
            return self.empty_home()
        name, path = self.stores()[0]
        word = self.word_of(name, path)
        page.path = path
        doctor = commands.doctor(config=self.config_arg)
        try:
            listed, note = self.listing(word, path)
        except api.Refusal as e:
            return self.refused(page, e)
        built = self.pages(word)
        saved = self.saved(path)
        page.message, page.keep_message = note, bool(note)
        items: list[tuple[str, list[str], Callable[[], None]]] = [
            (v.saved_at, [v.kind, " → ".join(v.runs), v.verdict, "", v.id, _when(v.saved_at)],
             self.saved_opener(v, word, path))
            for v in saved
        ]
        items += [
            (str(r["created_at"]),
             ["run", str(r["name"]), str(r["status"]), look.count(r["rows"]), str(r["run_id"]),
              _when(str(r["created_at"]))],
             self.run_opener(word, path, str(r["name"])))
            for r in listed.runs
        ]
        items.sort(key=lambda item: item[0], reverse=True)
        checks = doctor.report.get("checks", ())
        config_line = next(
            (str(c.get("line", "")) for c in checks if c.get("name") == "config"), ""
        )
        stores_words = config_line.partition(": ")[2].split(", failures")[0] or config_line

        def layout(width: int) -> None:
            details = [
                Detail("stores", stores_words),
                Detail("failures", ", ".join(self.events()) or "none"),
                Detail("next", doctor.next, code=True) if doctor.next is not None else None,
            ]
            if built:
                details.append(Detail("pages", "trace/index.html", link="trace/index.html"))
            page.top = [
                verdict_line(doctor.verdict, doctor.sentence), BLANK, *block(details), BLANK
            ]
            columns = [
                Column("kind"),
                Column("name", cut=True),
                Column("result", style=verdict_style),
                Column("rows", right=True),
                Column("id", wide=True),
                Column("saved or started"),
            ]
            page.header, page.rows = lay_table(columns, [c for _, c, _ in items], width)
            for line, (_, _, opens) in zip(page.rows, items, strict=True):
                line.opens = opens

        page.layout = layout

        def keys(ch: str) -> bool:
            if ch == "r":
                self.push(self.runs_page(0))
            elif ch == "i":
                self.push(self.imports_page(self.imported_index()))
            elif ch == "c":
                self.push(self.picker("compare", word, path))
            elif ch == "f":
                self.push(self.picker("fix-check", word, path))
            else:
                return False
            return True

        page.on_key = keys
        return page

    def empty_home(self) -> Screen:
        """No ``trace.toml`` here and no store named: the two commands that begin, not a
        refusal."""
        page = Screen("home", keys=[MOVE, OPEN, COPY])

        def layout(width: int) -> None:
            lines = block([
                Detail("folder", "no trace.toml here, and no store named"),
                Detail("setup", f"{TOOL} init", code=True),
                Detail("agent", f"{TOOL} init --agent", code=True),
            ])
            page.top, page.header, page.rows = lines[:1], None, lines[1:]

        page.layout = layout
        return page

    def run_opener(self, word: str | None, path: str, run: str) -> Callable[[], None]:
        return lambda: self.open_run(word, path, run)

    def saved_opener(self, v: core.SavedVerdict, word: str | None, path: str) -> Callable[[], None]:
        """Enter on a saved verdict: the verdict worked out again and saved again under the
        same id; a saved where opens the run screen."""

        def opens() -> None:
            if v.kind == "where" or len(v.runs) < 2:
                self.open_run(word, path, v.runs[0])
            else:
                self.open_verdict(v.kind, word, path, v.runs[0], v.runs[1])

        return opens

    # ---------- runs ----------

    def runs_page(self, index: int) -> Screen:
        stores = self.stores()
        name, path = stores[index % len(stores)]
        word = self.word_of(name, path)
        page = Screen(
            "runs",
            path,
            keys=[*_OPEN_KEYS, ("/", "filter"), ("n", "name"), ("c", "compare"), ("f", "fix-check"),
                  ("s", "store")],
            path=path,
        )
        try:
            listed, note = self.listing(word, path)
            sources = {s.run_id: s for s in core.run_sources(path)}
        except api.Refusal as e:
            return self.refused(page, e)
        saved = self.saved(path)
        page.subject = str(listed.store)
        page.message, page.keep_message = note, bool(note)
        runs = list(listed.runs)

        def layout(width: int) -> None:
            page.top = [verdict_line(listed.verdict, listed.sentence), BLANK]
            columns = [
                Column("#", right=True),
                Column("name", cut=True),
                Column("id", drop=2),
                Column("target or tool", drop=1),
                Column("rows", right=True),
                Column("failed", right=True),
                Column("traces"),
                Column("started"),
                Column("status", style=verdict_style),
            ]
            cells = [
                [
                    str(r["number"]),
                    str(r["name"]),
                    str(r["run_id"]),
                    sources[str(r["run_id"])].target_or_tool if str(r["run_id"]) in sources else "",
                    look.count(r["rows"]),
                    "–" if r["failed"] is None else look.count(r["failed"]),
                    "yes" if r["traced"] else "no",
                    _when(str(r["created_at"])),
                    str(r["status"]),
                ]
                for r in runs
            ]
            page.header, page.rows = lay_table(columns, cells, width)
            for line, r in zip(page.rows, runs, strict=True):
                line.data = r
                line.opens = self.run_opener(word, path, str(r["name"]))
            page.bottom = []
            if saved:
                wide = max(len(v.kind) for v in saved)
                page.bottom += [BLANK, text_line("saved verdicts", "dim")]
                page.bottom += [
                    Line(
                        f"  {v.kind.ljust(wide)}  {' → '.join(v.runs)}: {v.verdict}, saved "
                        f"{_when(v.saved_at)} ({v.id[:12]})",
                        [(2, 2 + len(v.kind), "dim")],
                        hang=wide + 4,
                    )
                    for v in saved
                ]
            page.bottom += [BLANK, *block([Detail("next", listed.next, code=True)])]

        page.layout = layout
        asking: dict[str, Any] = {}

        def question(ch: str) -> bool:
            """``n``: the name typed on the message line, then asked ``[y/N]``."""
            if asking.get("typing") is not None:
                shown = str(asking["row"]["name"])
                if ch == "\r":
                    if asking["typing"]:
                        asking["new"], asking["typing"] = asking["typing"], None
                        page.message = (
                            f'name "{shown}" ({asking["row"]["run_id"]}) "{asking["new"]}"? [y/N]'
                        )
                    else:
                        asking.clear()
                        page.message, page.keep_message = note, bool(note)
                elif ch == "\x1b":
                    asking.clear()
                    page.message, page.keep_message = note, bool(note)
                elif ch == "\x7f":
                    asking["typing"] = asking["typing"][:-1]
                    page.message = f'name "{shown}" as: {asking["typing"]}_'
                elif ch.isprintable():
                    asking["typing"] += ch
                    page.message = f'name "{shown}" as: {asking["typing"]}_'
                return True
            if asking.get("new") is not None:
                if ch == "y":
                    new, row = str(asking["new"]), asking["row"]
                    asking.clear()
                    try:
                        named = api.name(word, str(row["run_id"]), new, **self.kw())
                    except api.Refusal as e:
                        page.message, page.keep_message = f"error: {e}", True
                        return True
                    self.kept.append(f'named "{new}"')
                    fresh = self.runs_page(index)
                    fresh.message, fresh.keep_message = f"{named.verdict}  {named.sentence}", True
                    self.replace(fresh)
                elif ch in ("n", "q", "\x1b", "\r"):
                    asking.clear()
                    page.message, page.keep_message = note, bool(note)
                return True
            return False

        def keys(ch: str) -> bool:
            if question(ch):
                return True
            if ch == "n":
                row = page.focused_row()
                if row is not None:
                    asking["row"], asking["typing"] = row.data, ""
                    page.message = f'name "{row.data["name"]}" as: _'
                    page.keep_message = True
                return True
            if ch == "s":
                self.replace(self.runs_page(index + 1))
            elif ch == "c":
                self.push(self.picker("compare", word, path))
            elif ch == "f":
                self.push(self.picker("fix-check", word, path))
            else:
                return False
            return True

        page.on_key = keys
        return page

    # ---------- imports ----------

    def imported_index(self) -> int:
        """The store Trace's import wrote: the first whose runs all came from a reader."""
        for i, (_name, path) in enumerate(self.stores()):
            try:
                sources = core.run_sources(path)
            except api.Refusal:
                continue
            if sources and all(s.tool is not None for s in sources):
                return i
        return 0

    def imports_page(self, index: int) -> Screen:
        stores = self.stores()
        name, path = stores[index % len(stores)]
        word = self.word_of(name, path)
        page = Screen(
            "imports", path, keys=[*_OPEN_KEYS, ("/", "filter"), ("s", "store"), COPY], path=path
        )
        try:
            listed, note = self.listing(word, path)
            sources = {s.run_id: s for s in core.run_sources(path)}
        except api.Refusal as e:
            return self.refused(page, e)
        found = [f for f in core.found_results(".", store=path) if not f.imported]
        page.subject = str(listed.store)
        page.message, page.keep_message = note, bool(note)
        runs = list(listed.runs)
        imported = bool(sources) and all(s.tool is not None for s in sources.values())
        written = f"written by {TOOL} import" if imported else "a store Prove wrote"
        where = f"{path}; {written}"
        if name:
            where = f"{path}, named {name} in {self.config_shown()}; {written}"
        failures = ", ".join(self.events()) or "none"
        if note:
            failures += "; not among this store's outcomes, so its failed column is not counted"

        def layout(width: int) -> None:
            columns = [
                Column("#", right=True),
                Column("name", cut=True),
                Column("tool"),
                Column("file", cut=True),
                Column("rows", right=True),
                Column("failed", right=True),
                Column("started"),
                Column("status", style=verdict_style),
            ]
            cells = [
                [
                    str(r["number"]),
                    str(r["name"]),
                    (sources[str(r["run_id"])].tool or "") if str(r["run_id"]) in sources else "",
                    (
                        ", ".join(sources[str(r["run_id"])].files)
                        if str(r["run_id"]) in sources
                        else ""
                    ),
                    look.count(r["rows"]),
                    "–" if r["failed"] is None else look.count(r["failed"]),
                    _when(str(r["created_at"])),
                    str(r["status"]),
                ]
                for r in runs
            ]
            head, laid = lay_table(columns, cells, width)
            page.top = [
                verdict_line(listed.verdict, listed.sentence),
                BLANK,
                *block([Detail("store", where), Detail("failures", failures)]),
                BLANK,
                *([head, *laid] if runs else []),
                BLANK,
                text_line(
                    "found by init, not imported: enter runs the line after a question"
                    if found
                    else "found by init, not imported: nothing under this folder",
                    "dim",
                ),
            ]
            page.header, page.rows = lay_table(
                [Column("file", cut=True), Column("what it is")],
                [[f.path, f.said] for f in found],
                width,
            )
            for line, f in zip(page.rows, found, strict=True):
                line.data = f
                line.copy = f.command
                line.opens = self.ask_opener(f, path, index)
            page.bottom = [BLANK, *block([Detail("next", listed.next, code=True)])]

        page.layout = layout

        def keys(ch: str) -> bool:
            if ch != "s":
                return False
            self.replace(self.imports_page(index + 1))
            return True

        page.on_key = keys
        return page

    def ask_opener(self, f: core.FoundResult, path: str, index: int) -> Callable[[], None]:
        return lambda: self.push(self.asking(f, path, index))

    def asking(self, f: core.FoundResult, path: str, index: int) -> Screen:
        """Enter on a found file: the file, what it is, the whole import line, and the question
        on the message line; ``y`` runs it. A line with a word in capitals to fill
        in is never run from here."""
        page = Screen("imports", path, keys=[("y", "yes"), ("n", "no"), BACK], path=path)
        run, flags = _import_call(f.command)
        page.top = block([
            Detail("file", f.path),
            Detail("what", f.said),
            Detail("run", run),
            Detail("store", path),
            Detail("command", f.command, code=True),
        ])
        if f.fill:
            page.keys = [BACK, COPY]
            page.message = (
                f"note: {', '.join(f.fill)} is yours to fill in before this line can run; "
                "y copies it"
            )
        else:
            page.message = "import this file into the store, as the run named above? [y/N]"
        page.keep_message = True

        def start() -> None:
            page.busy = True
            page.keys = []
            page.message, page.keep_message = "", False
            page.top = [*page.top, BLANK, Line("  importing…")]

            def work() -> None:
                try:
                    done = api.import_run(path, f.tool, [f.path], run=run, **self.kw(), **flags)
                except api.Refusal as e:
                    self._from_worker(self.import_failed, page, f"error: {e}")
                    return
                except Exception as e:  # noqa: BLE001 - what the import failed with, in one line
                    self._from_worker(self.import_failed, page, f"error: {look.why(e)}")
                    return
                if self.cancel.is_set():
                    return
                self.kept.append(f'imported "{done.run}"')
                self._from_worker(self.imported, page, index, done)

            threading.Thread(target=work, name="trace-app-import", daemon=True).start()

        def keys(ch: str) -> bool:
            if page.busy:
                if ch in ("q", "\x1b"):
                    page.message = "note: the import is running; ctrl-c stops the app at once"
                return True
            if f.fill:
                if ch == "y":
                    self.copy_to_clipboard(f.command)
                    page.message = "note: copied"
                    return True
                return ch not in ("\x1b", "q", "?")
            if ch == "y":
                start()
            elif ch in ("n", "q", "\x1b", "\r"):
                self.pop()
            return True

        page.on_key = keys
        return page

    def import_failed(self, page: Screen, message: str) -> None:
        page.busy = False
        page.keys = [BACK]
        page.top = [line for line in page.top if line.text.strip() != "importing…"]
        page.message, page.keep_message = message, True
        self.redraw()

    def imported(self, page: Screen, index: int, done: Any) -> None:
        """The import done: back on the imports screen, read again, its ``ok`` line on the
        message line."""
        if self.stack and self.stack[-1] is page:
            self.stack.pop()
        fresh = self.imports_page(index)
        fresh.message, fresh.keep_message = f"{done.verdict}  {done.sentence}", True
        self.replace(fresh)

    # ---------- the pickers ----------

    def picker(self, kind: str, word: str | None, path: str) -> Screen:
        """Pick two runs, before then after (``space``), or previous and latest (``l``); the
        limit asked for from the config's ``[check]``, or typed after ``h``."""
        limit = "max-mde-hr" if kind == "compare" else "max-mde"
        keyword = limit.replace("-", "_")
        page = Screen(
            kind,
            "pick two runs",
            keys=[MOVE, ("enter", kind), BACK, ("space", "choose"), ("l", "previous and latest"),
                  ("h", "limit")],
            path=path,
            kind=kind,
        )
        try:
            listed, _note = self.listing(word, path)
        except api.Refusal as e:
            return self.refused(page, e)
        runs = [r for r in listed.runs if r["status"] == "complete"]
        names = {str(r["run_id"]): str(r["name"]) for r in runs}
        held = self.held()
        configured = None if held is None else getattr(held, keyword)
        chosen: dict[str, str | None] = {"before": None, "after": None}
        turn = ["before"]
        asked: dict[str, Any] = {"typing": None, "value": None}

        def latest() -> None:
            chosen["after"] = str(runs[0]["run_id"]) if runs else None
            chosen["before"] = str(runs[1]["run_id"]) if len(runs) > 1 else None
            turn[0] = "before"

        latest()

        def limit_words() -> str:
            if asked["value"] is not None:
                return f"{asked['value']:g}, asked here"
            if configured is not None:
                return f"{configured:g}, from {self.config_shown()} [check]"
            return "none; h sets it"

        def layout(width: int) -> None:
            page.top = [
                *block([
                    Detail("before", names.get(chosen["before"] or "", "none chosen")),
                    Detail("after", names.get(chosen["after"] or "", "none chosen")),
                    Detail(limit, limit_words()),
                    Detail(
                        "failures",
                        f"{', '.join(self.events()) or 'none'}, from {self.config_shown()} "
                        "[events]",
                    ),
                ]),
                BLANK,
            ]
            mark = {chosen["before"]: "before", chosen["after"]: "after"}
            columns = [
                Column(""),
                Column("#", right=True),
                Column("name", cut=True),
                Column("id", drop=1),
                Column("rows", right=True),
                Column("traces"),
                Column("started"),
                Column("status", style=verdict_style),
            ]
            cells = [
                [
                    mark.get(str(r["run_id"]), ""),
                    str(r["number"]),
                    str(r["name"]),
                    str(r["run_id"]),
                    look.count(r["rows"]),
                    "yes" if r["traced"] else "no",
                    _when(str(r["created_at"])),
                    str(r["status"]),
                ]
                for r in runs
            ]
            page.header, page.rows = lay_table(columns, cells, width)
            for line, r in zip(page.rows, runs, strict=True):
                line.data = r
                line.opens = go

        def go() -> None:
            a, b = chosen["before"], chosen["after"]
            if not a or not b:
                page.message = "error: choose two runs, before then after"
                return
            extra = {} if asked["value"] is None else {keyword: asked["value"]}
            self.open_verdict(kind, word, path, names[a], names[b], extra)

        def keys(ch: str) -> bool:
            if asked["typing"] is not None:
                if ch == "\r":
                    try:
                        asked["value"] = float(asked["typing"])
                    except ValueError:
                        page.message = f"error: {asked['typing'] or 'nothing'} is not a number"
                    asked["typing"] = None
                    page.keep_message = False
                elif ch == "\x1b":
                    asked["typing"] = None
                    page.message, page.keep_message = "", False
                elif ch == "\x7f":
                    asked["typing"] = asked["typing"][:-1]
                    page.message = f"{limit}: {asked['typing']}_"
                elif ch.isprintable():
                    asked["typing"] += ch
                    page.message = f"{limit}: {asked['typing']}_"
                layout(self.width())
                return True
            if ch == "l":
                latest()
            elif ch == " ":
                row = page.focused_row()
                if row is None:
                    return True
                other = "after" if turn[0] == "before" else "before"
                run_id = str(row.data["run_id"])
                if chosen[other] == run_id:
                    chosen[other] = None
                chosen[turn[0]] = run_id
                turn[0] = other
            elif ch == "h":
                asked["typing"] = ""
                page.message, page.keep_message = f"{limit}: _", True
                return True
            else:
                return False
            layout(self.width())
            return True

        page.layout = layout
        page.on_key = keys
        return page

    # ---------- the verdicts, worked out beside the screen ----------

    def open_run(self, word: str | None, path: str, run: str) -> None:
        self.work("run", run, "where", word, path, lambda: api.where(word, run, **self.kw()), None)

    def open_verdict(
        self,
        kind: str,
        word: str | None,
        path: str,
        a: str,
        b: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        verbs: dict[str, Callable[..., Any]] = {
            "compare": api.compare, "fix-check": api.fix_check, "changes": api.changes
        }
        verb = verbs[kind]
        kwargs: dict[str, Any] = {**self.kw(), **(extra or {})}
        if kind == "fix-check":
            kwargs["inputs"] = "all"
        self.work(kind, f"{a} → {b}", kind, word, path, lambda: verb(word, a, b, **kwargs), (a, b))

    def work(
        self,
        title: str,
        subject: str,
        kind: str,
        word: str | None,
        path: str,
        call: Callable[[], Any],
        pair: tuple[str, str] | None,
    ) -> None:
        """The verb's work beside the screen, which says so in one word; its verdict screen
        once it is done. Leaving the screen before then, or Ctrl-C, lets the work go: nothing
        is saved by it."""
        target = Screen(title, subject, keys=[BACK], path=path, kind=kind)
        said = WORKING[kind]
        target.top = [Line(f"  {said}", [(2, 2 + len(said), "dim")])]
        self.push(target)

        def work() -> None:
            try:
                result = call()
            except api.Refusal as e:
                page = self.refused(Screen(title, subject, keys=[BACK], path=path), e)
            except Exception as e:  # noqa: BLE001 - what the verb failed with, in one line
                page = Screen(
                    title, subject, keys=[BACK], path=path,
                    message=f"error: {look.why(e)}", keep_message=True,
                )
            else:
                if self.cancel.is_set() or target not in self.stack:
                    return
                page = self.verdict_screen(kind, title, subject, result, word, path, pair)
            self._from_worker(self._swap, target, page)

        threading.Thread(target=work, name="trace-app-work", daemon=True).start()

    def _from_worker(self, call: Callable[..., None], *args: Any) -> None:
        """``call`` on the app's thread, unless the app has already left."""
        if not self.is_running:
            return
        try:
            self.call_from_thread(call, *args)
        except RuntimeError:
            return

    def _swap(self, old: Screen, new: Screen) -> None:
        if old in self.stack:
            self.stack[self.stack.index(old)] = new
        self.redraw()

    def verdict_screen(
        self,
        kind: str,
        title: str,
        subject: str,
        result: Any,
        word: str | None,
        path: str,
        pair: tuple[str, str] | None,
    ) -> Screen:
        """The verdict saved and the pages rebuilt, then its screen from its report."""
        delivered = api.save(result)
        ident: str | None = None
        if delivered.saved:
            ident = str(delivered.saved).rstrip("/").rsplit("/", 1)[-1]
            self.kept.append(f"{kind} {ident[:12]}")
            message = f"saved  {kind} {ident[:12]}"
        else:
            note = next(
                (n for n in delivered.notes if "not saved" in n),
                delivered.notes[-1] if delivered.notes else "the verdict was not saved",
            )
            message = f"note: {note}"
        built = ident is not None and self.pages(word)
        own: list[tuple[str, str]] = {
            "where": [("c", "compare"), ("t", "table"), ("d", "could not say")],
            "compare": [("k", "kinds"), ("d", "could not say"), ("f", "fix-check")],
            "fix-check": [("k", "kinds"), ("t", "table"), ("d", "could not say"), ("g", "changes")],
            "changes": [("k", "kinds"), ("d", "could not say")],
        }[kind]
        page = Screen(
            title, subject, keys=[*_OPEN_KEYS, *own, LINKS, COPY], message=message,
            keep_message=True, path=path, kind=kind,
        )
        page.keep_bottom = True
        report = str(result.to_markdown())
        sections = _sections(report)
        nexts = [
            line[len("next: ") :]
            for s in sections
            for line in s.lines
            if line.startswith("next: ")
        ]
        cannot = [
            line for s in sections if s.name == CANNOT_SAY for line in s.lines if line.strip()
        ]
        extra = [line for s in sections for line in s.lines if line.startswith(NO_TRACES)]
        links: list[Detail] = []
        if built and ident is not None:
            page_address = f"trace/{kind}/{ident}.html"
            charts = {"where": [("curve", "curve")], "compare": [("curves", "curves"),
                      ("hazard ratio chart", "hazard-ratio")]}.get(kind, [])
            links = [
                Detail(label, f"{page_address}#{anchor}", link=f"{page_address}#{anchor}")
                for label, anchor in charts
            ]
            links.append(Detail("page", page_address, link=page_address))
        if ident is not None:
            links.append(Detail("saved", f"{kind} {ident[:12]}"))

        def layout(width: int) -> None:
            top: list[Line] = [verdict_line(result.verdict, result.sentence), BLANK]
            kinds: list[Line] = []
            second: list[Line] = []
            rows: list[list[str]] = []
            after_details: list[str] = []
            for s in sections:
                lines = [line for line in s.lines if not line.startswith("next: ")]
                if s.name == SUMMARY:
                    top += _render([*lines, *(f"next: {n}" for n in nexts[:1])], width)
                elif s.name == CANNOT_SAY:
                    continue
                elif s.name == BEFORE_YOU_ACT:
                    top += [BLANK, text_line("before you act on this"), *_render(lines, width)]
                elif s.sub in BEHIND_K[kind] or (not s.sub and s.name in BEHIND_K[kind]):
                    if kind == "compare" and s.sub == "Per kind":
                        limits = [line for line in lines if line.startswith(LIMIT)]
                        lines = [line for line in lines if line not in limits]
                        after_details += [f"- limit: {line}" for line in limits]
                    if kinds:
                        kinds.append(BLANK)
                    kinds += [_heading(s.sub or s.name), *_render(lines, width)]
                elif not s.sub and s.name == BEHIND_T.get(kind):
                    second += [_heading(s.name), *_render(lines, width)]
                elif not s.sub and s.name == MAIN_TABLE[kind] and not rows:
                    before, rows, after = _split_at_table(lines)
                    prose = [line for line in after if _figure_of(line) is None]
                    after_details = [line for line in after if _figure_of(line) is not None]
                    top += [BLANK, _heading(s.name), *_render(before, width)]
                    top += _render(prose, width)
                else:
                    top += [BLANK, _heading(s.sub or s.name), *_render(lines, width)]
            if rows:
                page.header, page.rows = _table_lines(rows, width)[0], _table_lines(rows, width)[1:]
            else:
                page.header, page.rows = None, []
            parted = [_figure_of(line) for line in after_details]
            figures = [Detail(*d) for d in parted if d is not None]
            below = [BLANK, *block([*figures, *links])] if figures or links else []
            if figures and not self.fits_below(top, page.rows, below, width):
                # the figures go above the table instead, so the verdict line stays on screen
                top += [BLANK, *block(figures)]
                below = [BLANK, *block(links)] if links else []
            page.top, page.bottom = top, below
            page.kinds, page.second_table = kinds, second

        page.layout = layout

        def keys(ch: str) -> bool:
            if ch == "k" and page.kinds:
                self._show_second(page, page.kinds)
            elif ch == "t" and page.second_table:
                self._show_second(page, page.second_table)
            elif ch == "d":
                self.pages(word)
                self.push(self.could_not_say(subject, [*cannot, *extra], kind, ident, path))
            elif ch == "g" and kind == "fix-check" and pair is not None:
                self.open_verdict("changes", word, path, *pair)
            elif ch == "f" and kind == "compare" and pair is not None:
                self.open_verdict("fix-check", word, path, *pair)
            elif ch == "c" and kind == "where":
                self.push(self.picker("compare", word, path))
            else:
                return False
            return True

        page.on_key = keys
        return page

    def fits_below(self, top: list[Line], rows: list[Line], below: list[Line], width: int) -> bool:
        """Whether the lines below the table leave the window room for the verdict line and the
        blank under it above the table (the shell keeps the lines below the table and the first
        three rows on screen, and the rest of the top goes behind ``m``)."""
        height = int(self.size.height) if self._mounted else 40

        def rows_of(lines: list[Line]) -> int:
            return sum(len(wrap_line(line, width, False)) for line in lines)

        need = 1 + min(len(rows), 3) + rows_of(below)
        return (height - 5) - need - 1 >= rows_of(top[:2])

    def could_not_say(
        self, subject: str, lines: list[str], kind: str, ident: str | None, path: str
    ) -> Screen:
        """The report's "What this cannot say" sentences, whole, and the report's sentence
        for an imported run with no traces; the page of the saved verdict that holds them, as
        a link."""
        page = Screen("could not say", subject, keys=[*_OPEN_KEYS, COPY], path=path, kind=kind)
        address = f"trace/{kind}/{ident}/could-not-say.html" if ident is not None else None

        def layout(width: int) -> None:
            page.top = _render(lines, width)
            page.bottom = []
            if address is not None:
                page.bottom = [BLANK, *block([Detail("page", address, link=address)])]
            page.header, page.rows = None, []

        page.layout = layout
        return page

    # ---------- help ----------

    def help_page(self) -> Screen:
        page = Screen("help", keys=[MOVE, BACK, ("q", "quit")], scroll_only=True)
        shared = [
            ("↑ ↓", "move the focus one row; behind m, k or t, scroll the lines one row"),
            ("PgUp PgDn Home End", "move it a page, or to the first or last row; behind m, k or t, "
                                   "a page"),
            ("enter", "open the focused row's screen, or its link in the browser"),
            ("esc", "back, with the focus where it was; during a question, no"),
            ("tab", "move the focus between the links and the table"),
            ("/", "filter the table's rows by text; esc clears it"),
            ("y", "copy the focused link's file:// address, or the focused command"),
            ("m", "the lines above the table the window has no room for; m again, the table"),
            ("?", "this help"),
            ("q", "quit (exit 0); during a question, no"),
            ("ctrl-c", "quit (exit 130), saying what was kept; work under way is let go, unsaved"),
        ]
        own = [
            ("c", "home, runs, run", "compare two runs (the curves): the picker"),
            ("f", "home, runs, compare", "fix-check two runs (how often they fail): the picker"),
            ("r", "home", "the runs"),
            ("i", "home", "the imports"),
            ("n", "runs", "name the focused run, after a question"),
            ("s", "runs, imports", "the next store the config names"),
            ("space", "compare, fix-check", "choose the focused run, before then after"),
            ("l", "compare, fix-check", "choose previous and latest"),
            ("h", "compare, fix-check", "set the limit asked for, when trace.toml gives none"),
            ("k", "compare, fix-check, changes", "the failures by kind, in place of the table"),
            ("t", "run, fix-check", "the second table: the share not yet failed by step, or the "
                                   "inputs that changed"),
            ("d", "run, compare, fix-check, changes", "what this cannot say"),
            ("g", "fix-check", "the changes: the inputs whose failure share moved"),
            ("y", "imports", "yes, to the question asked; n, esc or enter is no"),
        ]

        def layout(width: int) -> None:
            lines = [text_line("keys on every screen", "dim")]
            lines += [Line(f"  {k:<20}{w}", [(2, 2 + len(k), "bold")], hang=22) for k, w in shared]
            lines.append(text_line("keys of one screen", "dim"))
            lines += [
                Line(f"  {k:<8}{s:<34}{w}", [(2, 2 + len(k), "bold")], hang=44) for k, s, w in own
            ]
            lines.append(text_line("screens", "dim"))
            lines.append(
                text_line(
                    "home · runs · run · imports · compare · fix-check · verdict (compare, "
                    "fix-check) · changes · could not say · help"
                )
            )
            lines.append(
                text_line(
                    "every verdict shown is saved, and its page is a link into the pages: "
                    f"{TOOL} ui --open"
                )
            )
            page.rows = [row for line in lines for row, _ in wrap_line(line, width, False)]
            page.top, page.header, page.bottom = [], None, []

        page.layout = layout
        return page
