"""Trace's copy of Prove's terminal-app shell: the bands, the key
bar, the focus marker, the message line, the width and line-break rules, and the moves over a
screen's rows and links. Copied from Prove's ``main`` at the commit ``PROVE_COMMIT`` names, whose
two app files (``_cli_app_pages.py`` and ``_cli_app.py``) are byte for byte those of the Prove
release Trace pins; ``tests/test_tf19_shell.py`` holds each definition here to that commit's,
syntax tree for syntax tree, with ``poisson-prove`` read as ``poisson-trace``. Prove's private
modules are not imported; the screens are Trace's own (``_app.py``) and sit on this shell.

What is copied: from ``_cli_app_pages.py`` the parts of a screen (``Line``, ``Page``, ``Detail``,
``Column``), the layout helpers (``block``, ``wrap_line``, ``code_line``, ``text_line``,
``lay_table``, ``verdict_line``, ``verdict_style``) and the key bar's shared entries; from
``_cli_app.py`` the window's floor, the key bar, and the app's drawing and moves (``_draw``,
``_style``, ``_move``, ``_filter_key``, ``_focused_link``) as methods of :class:`Shell`, which
Trace's app extends. Prove's own screens, its key handling and its sweep are not copied.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from rich.text import Text
from textual.app import App

from poisson_trace import look

#: Prove's ``main`` the shell is copied from; its app files are the pinned release's.
PROVE_COMMIT = "d04e3788f3f6cb9b61e46c9494e9dba396b448ef"


class _Look:
    """What the copied drawing spells through Prove's look: a count, which Trace's look spells
    the same way."""

    @staticmethod
    def fmt_count(value: Any) -> str:
        return look.count(int(value))


_look = _Look()
meaning_of = look.meaning


WIDE = 120


@dataclass
class Line:
    """One line of a screen's body: its text (from column 1), its styled spans (``green``,
    ``yellow``, ``red``, ``bold``, ``dim``), and what it does: a link opens a page of the static UI
    (``link`` is its address inside the UI), ``copy`` is what ``y`` copies, ``opens`` what Enter on
    a table row does. ``code`` marks a command or code line, never cut (it wraps at spaces only)."""

    text: str
    spans: list[tuple[int, int, str]] = field(default_factory=list)
    link: str | None = None
    copy: str | None = None
    opens: Callable[[], None] | None = None
    code: bool = False
    #: The column a wrapped line continues at; ``None``: under a ``label  value`` line's value.
    hang: int | None = None
    #: What a table row stands for (a run, an episode, an event), for the screen's own keys.
    data: Any = None


@dataclass
class Page:
    """One screen: its title and subject, the lines above its table (they never scroll), the
    table's header and rows (the focus moves over them), and the lines below; its keys for the key
    bar; the message line. ``layout`` (re)builds the lines for a width; ``on_key`` takes the
    screen's own letters."""

    title: str
    subject: str = ""
    top: list[Line] = field(default_factory=list)
    header: Line | None = None
    rows: list[Line] = field(default_factory=list)
    bottom: list[Line] = field(default_factory=list)
    keys: list[tuple[str, str]] = field(default_factory=list)
    message: str = ""
    #: The message is the screen's own state (a refusal), kept until the screen is left.
    keep_message: bool = False
    focus: int = 0
    in_links: bool = False
    offset: int = 0
    #: The second block's lines with no room above the table, shown by ``m``.
    more: list[Line] = field(default_factory=list)
    #: A second block shown only behind a key at this width (the run's event log at 80 columns).
    second: list[Line] = field(default_factory=list)
    show_more: bool = False
    show_second: bool = False
    #: Help: the rows are text the keys scroll, and nothing has the focus.
    scroll_only: bool = False
    #: The lines below the table keep their rows (the verdict's chart links at 80 columns).
    keep_bottom: bool = False
    layout: Callable[[int], None] | None = None
    #: The width ``layout`` last laid the page out for.
    laid_width: int = 0
    on_key: Callable[[str], bool] | None = None
    on_focus: Callable[[], None] | None = None
    #: The filter (``/``) on the table's rows: being typed, and its text.
    filtering: bool = False
    filter: str = ""
    #: The focus the table or the links had when ``Tab`` moved it to the other.
    other_focus: int = 0
    #: The document the screen renders.
    view: dict[str, Any] | None = None

    def links(self) -> list[Line]:
        return [line for line in [*self.top, *self.bottom] if line.link]

    def visible_rows(self) -> list[Line]:
        """The table's rows as shown: those the filter (``/``) matches."""
        if not self.filter:
            return self.rows
        needle = self.filter.lower()
        return [r for r in self.rows if needle in r.text.lower()]

    def table_row(self) -> Line | None:
        """The table row the focus is on, or was on before ``Tab`` moved it to the links: the row
        the links follow."""
        rows = self.visible_rows()
        if not rows:
            return None
        return rows[min(self.other_focus if self.in_links else self.focus, len(rows) - 1)]

    def focused_row(self) -> Line | None:
        """The table row with the focus, when a row has it."""
        rows = self.visible_rows()
        if not rows or self.in_links:
            return None
        return rows[min(self.focus, len(rows) - 1)]


def verdict_line(word: str, sentence: str) -> Line:
    """``  word  sentence``, the word in its meaning's style."""
    return Line(f"  {word}  {sentence}", [(2, 2 + len(word), meaning_of(word))])


@dataclass
class Detail:
    label: str
    value: str
    link: str | None = None
    code: bool = False


def block(details: Sequence[Detail | None]) -> list[Line]:
    """``label  value`` lines, the labels dim and padded to one column."""
    shown = [d for d in details if d is not None]
    if not shown:
        return []
    width = max(len(d.label) for d in shown)
    out = []
    for d in shown:
        text = f"  {d.label.ljust(width)}  {d.value}"
        copy = d.value if d.code and d.link is None else None
        out.append(
            Line(
                text,
                [(2, 2 + len(d.label), "dim")],
                link=d.link,
                copy=copy,
                code=d.code or d.link is not None,
                hang=width + 4,
            )
        )
    return out


def wrap_line(line: Line, w: int, focused: bool) -> list[tuple[Line, bool]]:
    """A body line on rows of ``w``: a ``label  value`` line wraps under its value; a command or
    code line that does not fit starts at column 1 on the rows below its label, broken only at
    spaces; other text wraps two deeper than it starts."""
    if len(line.text) <= w:
        return [(line, focused)]
    m = re.match(r"^(  \S(?:[^ ]| (?! ))*  +)", line.text)
    if line.code:
        label = m.group(1).rstrip() if m else ""
        rest = line.text[len(m.group(1)) :] if m else line.text.lstrip(" ")
        rows = [Line(label, line.spans, line.link, line.copy, line.opens, True)] if label else []
        chunk = ""
        for word in rest.split(" "):
            if chunk and len(chunk) + 1 + len(word) > w:
                rows.append(Line(chunk, [], line.link, line.copy, line.opens, True))
                chunk = word
            else:
                chunk = f"{chunk} {word}" if chunk else word
        rows.append(Line(chunk, [], line.link, line.copy, line.opens, True))
        return [(r, focused) for r in rows]
    if line.hang is not None and line.hang < w // 2:
        hang = line.hang
    elif m and len(m.group(1)) < w // 2:
        hang = len(m.group(1))
    else:
        hang = len(line.text) - len(line.text.lstrip(" ")) + 2
    parts, rest, first = [], line.text, True
    while len(rest) > w:
        cut = rest.rfind(" ", hang + 1, w + 1)
        if cut <= hang:
            cut = w
        parts.append(
            Line(rest[:cut].rstrip(), line.spans if first else [], line.link, line.copy, line.opens)
        )
        rest = " " * hang + rest[cut:].lstrip(" ")
        first = False
    parts.append(Line(rest, [], line.link, line.copy, line.opens))
    return [(p, focused) for p in parts]


def code_line(text: str) -> Line:
    return Line(f"  {text}", code=True, copy=text)


def text_line(text: str, style: str = "") -> Line:
    line = f"  {text}"
    return Line(line, [(2, len(line), style)] if style else [])


BLANK = Line("")


@dataclass
class Column:
    name: str
    right: bool = False
    #: Dropped when the window is narrow, the highest first; ``None``: never dropped.
    drop: int | None = None
    #: Shown only at the wide layout (``WIDE`` columns and up).
    wide: bool = False
    #: A name, cut in the middle with ``…`` when the table is too wide; its whole form is on the
    #: screen the row opens.
    cut: bool = False
    #: The style a cell's first word is drawn in, from the cell (a verdict's meaning).
    style: Callable[[str], str] | None = None


def lay_table(
    columns: Sequence[Column], cells: Sequence[Sequence[str]], width: int
) -> tuple[Line, list[Line]]:
    """The header and rows of a table laid out for ``width``. The columns keep one order; those
    marked ``wide`` show only at the wide layout, and below it the ``drop`` columns go, highest
    first, until the table fits. Still too wide, a name column (``cut``) is cut in the middle
    with ``…``, the widest first, then the columns close to one space apart and the names are cut
    further; a condition, a number or a note is never cut."""
    keep = [i for i, c in enumerate(columns) if not (c.wide and width < WIDE)]
    ws = {i: max([len(columns[i].name)] + [len(r[i]) for r in cells]) for i in range(len(columns))}
    gap = 2

    def total() -> int:
        return 2 + sum(ws[i] for i in keep) + gap * (len(keep) - 1)

    if width < WIDE:
        droppable = sorted(
            (i for i in keep if columns[i].drop is not None), key=lambda i: -(columns[i].drop or 0)
        )
        for i in droppable:
            if total() <= width:
                break
            keep.remove(i)
    for closer in (False, True):
        if closer and total() > width:
            gap = 1
        cuttable = [i for i in keep if columns[i].cut]
        while total() > width and cuttable:  # a character at a time from the widest name
            i = max(cuttable, key=lambda i: ws[i])
            if ws[i] <= max(12, len(columns[i].name)):
                cuttable.remove(i)
                continue
            ws[i] -= 1

    def cut(text: str, w: int) -> str:
        if len(text) <= w:
            return text
        head = (w - 1) // 2
        return text[:head] + "…" + text[len(text) - (w - 1 - head) :]

    def laid(values: Sequence[str], styled: bool) -> Line:
        parts, spans, at = [], [], 2
        for i in keep:
            cell = cut(values[i], ws[i]) if columns[i].cut else values[i]
            shown = cell.rjust(ws[i]) if columns[i].right else cell.ljust(ws[i])
            style = columns[i].style
            if styled and style is not None and cell.strip():
                word = cell.split(",", 1)[0].strip()
                start = at + shown.index(word)
                spans.append((start, start + len(word), style(word)))
            parts.append(shown)
            at += len(shown) + gap
        return Line(("  " + (" " * gap).join(parts)).rstrip(), [s for s in spans if s[2]])

    head = laid([c.name for c in columns], False)
    head.spans = [(2, len(head.text), "dim")]
    return head, [laid(r, True) for r in cells]


def verdict_style(word: str) -> str:
    """A verdict word's style in a table cell: its meaning's colour, or bold for a result; a
    run's status yellow when it stopped short."""
    if word == "partial":
        return "yellow"
    if word in ("complete", ""):
        return ""
    return meaning_of(word)


MOVE = ("↑↓", "move")


OPEN = ("enter", "open")


BACK = ("esc", "back")


MIN_WIDTH, MIN_HEIGHT = 80, 24


_COLOURS = ("green", "yellow", "red")


def _key_bar(
    keys: list[tuple[str, str]], w: int, *, help_screen: bool
) -> tuple[str, list[tuple[int, int, str]]]:
    """The key bar: move, Enter, Esc, the screen's own, ``? help``, ``q quit``; each key bold, its
    word dim. Too narrow, words drop first from the move, Enter and Esc keys, then from the
    screen's own from the right; ``? help`` and ``q quit`` keep theirs."""
    shared = {"↑↓", "enter", "esc"}
    tail = [] if help_screen else [("?", "help"), ("q", "quit")]
    entries = [[k, word] for k, word in [*keys, *tail]]

    def laid() -> str:
        return "  " + "   ".join(f"{k} {word}".rstrip() for k, word in entries)

    order = [i for i, (k, _) in enumerate(entries) if k in shared]
    order += [
        i
        for i in reversed(range(len(entries)))
        if entries[i][0] not in shared and i < len(entries) - len(tail)
    ]
    for i in order:
        if len(laid()) <= w:
            break
        entries[i][1] = ""
    bar, spans, pos = "  ", [], 2
    for k, word in entries:
        piece = f"{k} {word}".rstrip()
        spans.append((pos, pos + len(k), "bold"))
        if word:
            spans.append((pos + len(k) + 1, pos + len(piece), "dim"))
        bar += piece + "   "
        pos += len(piece) + 3
    return bar.rstrip(), spans


class Shell(App[int]):
    """The drawing and the moves of Prove's app, as copied: ``_draw`` lays a page out in the six
    bands for a width and height, ``_move`` and ``_filter_key`` move the focus and filter the
    rows, ``_focused_link`` is the link the focus is on. The app that extends this sets
    ``shown`` (the header's store slot), ``mono`` (``NO_COLOR``: no green, yellow or red) and
    ``redraw`` (the canvas drawn again)."""

    shown: str
    mono: bool

    def redraw(self) -> None:
        raise NotImplementedError

    def _draw(self, page: Page, w: int, h: int) -> Text:
        out = Text()

        def put(
            text: str, spans: list[tuple[int, int, str]] | None = None, whole: str = ""
        ) -> None:
            if len(text.rstrip()) > w:  # a row longer than the window shows where it is cut
                text = text[: w - 1] + "…"
            t = Text(text[:w].ljust(w))
            for a, b, style in spans or []:
                style = self._style(style)
                if style and a < w:
                    t.stylize(style, a, min(b, w))
            if whole:
                t.stylize(whole)
            out.append(t)
            out.append("\n")

        # the header and its rule
        title = f"poisson-trace · {page.title}"
        subject = f"  {page.subject}" if page.subject else ""
        room = w - len(self.shown) - 1
        left = (title + subject)[:room]
        put(
            left.ljust(w - len(self.shown)) + self.shown,
            [
                (0, 13, "bold"),
                (13, 16, "dim"),
                (len(title), len(left), "dim"),
                (w - len(self.shown), w, "dim"),
            ],
        )
        put("─" * w, [(0, w, "dim")])
        body_room = h - 5
        focus_link = self._focused_link(page)
        groups = [wrap_line(line, w, line is focus_link) for line in page.top]
        top = [x for g in groups for x in g]
        rows = page.visible_rows()
        bottom = [x for line in page.bottom for x in wrap_line(line, w, line is focus_link)]
        header = [(page.header, False)] if page.header is not None else []
        if page.filtering or page.filter:
            shown_filter = f"  filter  {page.filter}" + ("_" if page.filtering else "")
            top.append((Line(shown_filter, [(2, 8, "dim")]), False))
            if not rows:
                top.append(
                    (Line(f'  no row matches "{page.filter}"; esc clears the filter'), False)
                )
        # The rows above the table never scroll: the whole lines with no room are a second block
        # behind ``m``, and one row says so.
        below = bottom if page.keep_bottom else []
        need = len(header) + min(len(rows), 3) + len(below)
        page.more = []
        if len(top) + need > body_room and not (page.filtering or page.filter):
            room = max(1, body_room - need - 1)
            kept: list[tuple[Line, bool]] = []
            for i, g in enumerate(groups):
                if len(kept) + len(g) > room:
                    page.more = page.top[i:]
                    break
                kept += g
            hidden = sum(len(g) for g in groups[len(page.top) - len(page.more) :])
            hint = f"  {_look.fmt_count(hidden)} more lines above the table: m shows them"
            top = [*kept, (Line(hint, [(2, len(hint), "dim")]), False)]
        if page.show_second and page.second:
            second = [x for line in page.second for x in wrap_line(line, w, False)]
            lines = top[: max(2, body_room - len(second))] + second
        elif page.show_more and page.more:
            more = [x for line in page.more for x in wrap_line(line, w, False)]
            lines = top[:-1] + more
        else:
            window = max(0, body_room - len(top) - len(header) - len(below))
            mark = not page.in_links and not page.scroll_only
            scroll = [(r, mark and i == page.focus) for i, r in enumerate(rows)]
            scroll += [] if below else bottom
            if page.scroll_only:  # help: the keys scroll the text, nothing has the focus
                page.focus = min(page.focus, max(0, len(scroll) - window))
                page.offset = page.focus
            focus = page.focus if rows and not page.in_links else 0
            if focus < page.offset:
                page.offset = focus
            if focus >= page.offset + window:
                page.offset = focus - window + 1
            if rows and focus == len(rows) - 1:
                page.offset = max(page.offset, min(focus, len(scroll) - window))
            page.offset = max(0, min(page.offset, max(0, len(scroll) - window)))
            visible = scroll[page.offset : page.offset + window]
            after = len(scroll) - page.offset - len(visible)
            if after > 0 and len(visible) > 1 and not visible[-1][1]:
                # ``↓ 7 more``: the last row says how many follow
                hint = f"  ↓ {_look.fmt_count(after + 1)} more"
                visible = [*visible[:-1], (Line(hint, [(2, len(hint), "dim")]), False)]
            lines = top + header + visible + below
        lines = lines[:body_room]
        for line, focused in lines:
            text = ("›" + line.text[1:]) if focused else line.text
            put(text, line.spans, "reverse" if focused else "")
        for _ in range(body_room - len(lines)):
            put("")
        message = page.message
        put(
            message,
            [(0, 5, "yellow")]
            if message.startswith("note:")
            else [(0, 6, "red")]
            if message.startswith("error:")
            else [],
        )
        put("─" * w, [(0, w, "dim")])
        keys = [k for k in page.keys if k[0] != "q"]
        if page.more:
            keys.append(("m", "more"))
        keys += [k for k in page.keys if k[0] == "q"]
        bar, spans = _key_bar(keys, w, help_screen=page.title == "help")
        put(bar, spans)
        out.rstrip()
        return out

    def _style(self, style: str) -> str:
        return "" if self.mono and style in _COLOURS else style

    def _move(self, page: Page, key: str, height: int) -> None:
        focusables = (
            page.links() if page.in_links or not page.visible_rows() else page.visible_rows()
        )
        if not focusables:
            return
        page_rows = max(1, height - 8)
        step = {
            "up": -1,
            "down": 1,
            "pageup": -page_rows,
            "pagedown": page_rows,
            "home": -(10**9),
            "end": 10**9,
        }[key]
        page.focus = max(0, min(len(focusables) - 1, page.focus + step))
        if page.on_focus is not None:
            page.on_focus()

    def _filter_key(self, page: Page, key: str, ch: str) -> None:
        if key == "escape":
            page.filtering, page.filter = False, ""
        elif key == "enter":
            page.filtering = False
        elif key == "backspace":
            page.filter = page.filter[:-1]
        elif ch and ch.isprintable():
            page.filter += ch
        page.focus = 0
        self.redraw()

    def _focused_link(self, page: Page) -> Line | None:
        links = page.links()
        if not links or (page.visible_rows() and not page.in_links):
            return None
        return links[min(page.focus, len(links) - 1)]
