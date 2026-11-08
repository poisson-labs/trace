"""The static pages and the HTML report: one renderer from the core's view objects (spec
section 17.3 items 7 to 9; section 11.7 as amended; the design's section 3), and the two charts
a saved ``compare`` carries (SV15).

A view (``core.View``) is the data behind one page: every fact the page shows, as the saved
verdict holds it, and the addresses of the pages it links to. This module formats a view and
computes nothing in it. Every page is Prove's page skeleton, its Content-Security-Policy and
its footer, with Trace's name; the fixed files, ``style.css`` and ``ui.js``, are Prove's UI
bundle byte for byte, and the pages' own rules (the charts' classes, the verdict panel's lists)
are the one ``<style>`` element every page carries. The HTML report (``poisson-trace report
DIR``, ``to_html()``) is the same verdict page rendered self-contained: the stylesheet inlined
in that one element, no script, no link, no ``href`` but an anchor of its own, the narrower
policy. Nothing on any page loads from the network; an SVG inside a page carries no namespace
(a scheme section 11.7 refuses) and no style of its own.

Every element that shows a fact of the verdict carries ``data-fact``, its JSON pointer, and
``data-value``, its value as JSON. The report's lines are shown as the plain command prints
them, in its order, under its own headings; a condition written as JSON in a table is shown as
its words (``task_id search · tool_fail_rate 0.55``). Standard library, the shared look and the
reports' JSON spelling only.
"""

from __future__ import annotations

import html as _html
import json
import math
import re
from collections.abc import Mapping, Sequence
from importlib import resources
from typing import Any

from poisson_trace import look, report

TOOL = "poisson-trace"
#: Prove's Content-Security-Policy, on every static page (poisson_prove._render_ui.POLICY).
PROVE_POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' "
    "data:; base-uri 'none'; form-action 'none'"
)
#: The report's: inline style and images and nothing else (section 17.3 item 8).
REPORT_POLICY = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; "
    "form-action 'none'"
)
#: Prove's UI bundle, copied byte for byte beside the pages (section 17.3 item 7).
BUNDLE = ("style.css", "ui.js")
FOOTER = f"Built by {TOOL} from the store. Nothing was loaded from the network. Address: "
#: The look's chart tokens by value, light and dark, for a chart saved as a file of its own.
LIGHT = {
    "bg": "#fcfcfb",
    "surface": "#f4f3ef",
    "rule": "#dddcd6",
    "text": "#0b0b0b",
    "dim": "#5f5e59",
    "after": "#5444c9",
}
DARK = {
    "bg": "#1a1a19",
    "surface": "#242422",
    "rule": "#3a3a37",
    "text": "#f0efec",
    "dim": "#a8a79f",
    "after": "#9085e9",
}
_FONT = "ui-monospace,Menlo,Consolas,monospace"
#: The pages' own rules beside Prove's stylesheet: the charts' classes (the first run in
#: ``--dim``, the second in ``--after``, each band a faint fill of its line's colour, DM7) and
#: the verdict panel's lists and links.
#: Trace's mark, as the lab's site draws it beside the tool's name (its colour there, and the
#: stepped line of a survival curve: the share of runs still alive, falling at the step where
#: they die), on a tile of the header mark's shape; the line in white on the tile's own colour.
MARK_COLOUR = "#1098ad"
_MARK = (
    "data:image/svg+xml,"
    "%3Csvg%20xmlns%3D%27http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%27%20viewBox%3D%270%200"
    "%201024%201024%27%3E%3Crect%20x%3D%27128%27%20y%3D%27320%27%20width%3D%27384%27%"
    "20height%3D%27192%27%20fill%3D%27%23fff%27%2F%3E%3Crect%20x%3D%27480%27%20y%3D%2"
    "7512%27%20width%3D%27416%27%20height%3D%27192%27%20fill%3D%27%23fff%27%2F%3E%3C%"
    "2Fsvg%3E"
)
_SANS = 'system-ui,-apple-system,"Segoe UI",sans-serif'
PAGE_CSS = (
    # the header's mark: Trace's tile
    f"header .tool::before{{background:{MARK_COLOUR} url({_MARK}) center/100% no-repeat;"
    "box-shadow:none}"
    # prose everywhere but code: a table cell, a detail line's value and the crumbs read in the
    # page's face; ids, addresses, identifiers and commands keep the monospace
    f"td,dd,nav{{font-family:{_SANS}}}"
    "td .mono,dd .mono,td code,dd code{font-family:ui-monospace,Menlo,Consolas,monospace}"
    ".chart .dimt{fill:var(--dim)}"
    ".chart .axis{stroke:var(--rule);stroke-width:1}"
    ".chart .thr{stroke:var(--text);stroke-width:1}"
    ".chart .zero{stroke:var(--dim);stroke-width:1}"
    ".chart .asked{stroke:var(--dim);stroke-width:1}"
    ".chart .line{fill:none;stroke-width:1.5}"
    ".chart .line.before{stroke:var(--dim)}"
    ".chart .line.after{stroke:var(--after);stroke-width:2.5}"
    ".chart .band{stroke:none;fill-opacity:.1}"
    ".chart .band.before{fill:var(--dim)}"
    ".chart .band.after{fill:var(--after)}"
    ".chart .mark{stroke:none}"
    ".chart .mark.before{fill:var(--dim)}"
    ".chart .mark.after{fill:var(--after)}"
    ".chart .label.before{fill:var(--dim)}"
    ".chart .label.after{fill:var(--after)}"
    "svg.chart{max-width:720px}"
    "figure#hazard-ratio svg.chart{max-width:760px}"
    "figure .tablewrap{margin:0;border:0;border-top:1px solid var(--rule);border-radius:0;"
    "box-shadow:none}"
    "section#verdict > ul.plain{margin:0;border:0;border-radius:0;box-shadow:none;"
    "background:var(--surface);padding-bottom:6px}"
    "section#verdict > ul.plain li{padding:8px 20px;border-bottom:1px solid var(--hair)}"
    "section#verdict > p.links{margin:0;padding:12px 20px;border-top:1px solid var(--rule);"
    "font-size:13px}"
    "p.links{font-size:13px}"
    "p.bold{font-weight:650}"
    "ul.plain li code,dd code{font-size:13px}"
)


def esc(value: Any) -> str:
    return _html.escape(str(value), quote=True)


def bundle_files() -> dict[str, bytes]:
    """Prove's UI bundle as the installed package ships it."""
    folder = resources.files("poisson_prove") / "_ui_bundle"
    return {name: (folder / name).read_bytes() for name in BUNDLE}


def fact(ptr: str, value: Any, text: str | None = None, *, tag: str = "span", cls: str = "") -> str:
    """An element showing one fact: its JSON pointer and its value as JSON, its text as given
    (escaped) or the value's own."""
    classes = f' class="{cls}"' if cls else ""
    shown = esc(value) if text is None else esc(text)
    return (
        f'<{tag}{classes} data-fact="{esc(ptr)}" data-value="{esc(report.json_value(value))}">'
        f"{shown}</{tag}>"
    )


def word_class(word: str) -> str:
    """The class a verdict word is drawn in: the look's four meanings."""
    return {"green": "w-ok", "yellow": "w-warn", "red": "w-bad"}.get(look.meaning(word), "w-res")


def verdict_heading(verdict: str, sentence: str) -> str:
    """A page's first heading: the verdict line, ``<verdict>␣␣<sentence>``, in Prove's verdict
    panel (section 11.7's check reads the text of the first ``<h1>``)."""
    return (
        f'<h1 class="verdict">{fact("/verdict", verdict, tag="b", cls=word_class(verdict))}  '
        f"{fact('/sentence', sentence)}</h1>"
    )


# ---------- the skeleton ----------


def _head(title: str, up: str, standalone: bool) -> str:
    out = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        f'<meta http-equiv="Content-Security-Policy" content="'
        f'{REPORT_POLICY if standalone else PROVE_POLICY}">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<meta name="generator" content="{TOOL} {_version()}">',
        f"<title>{esc(title)}</title>",
    ]
    if standalone:
        style = bundle_files()["style.css"].decode("utf-8")
        out.append(f"<style>{style}\n{PAGE_CSS}</style>")
    else:
        out.append(f'<link rel="stylesheet" href="{up}style.css">')
        out.append(f'<script src="{up}ui.js" defer></script>')
        out.append(f"<style>{PAGE_CSS}</style>")
    out += ["</head>", "<body>"]
    return "\n".join(out) + "\n"


def _version() -> str:
    from importlib.metadata import version

    return version(TOOL)


def frame(
    *,
    title: str,
    view: str,
    crumbs: str,
    store: str,
    address: str,
    body: str,
    standalone: bool,
) -> str:
    """A whole page: Prove's skeleton with Trace's name, the header (the tool, where you are,
    the store's folder name), the body in ``<main>``, and Prove's footer with the page's address
    inside the UI."""
    up = "../" * (address.count("/") - 1)
    kind = fact("/view", view, cls="dim")
    nav = f'{crumbs} <span class="dim">·</span> {kind}' if crumbs else kind
    return (
        _head(title, up, standalone) + f'<header><span class="tool">{TOOL}</span><nav>{nav}</nav>'
        f'<span class="store">{esc(store)}</span></header>\n<main>\n'
        + body
        + f"\n</main>\n<footer>{FOOTER}{fact('/address', address, cls='mono')}</footer>\n"
        "</body>\n</html>\n"
    )


# ---------- the report's lines as HTML ----------

_NUMBERISH = re.compile(
    r"^(?:[+\-−]?[\d,]*\.?\d+(?:e[+\-]?\d+)?(?: [A-Za-z%]+)?|\d[\d,]*/\d[\d,]*|[–-]|none"
    r"|[\d.,]+ (?:–|to|and) [\d.,]+)$"
)
_NUMBER = re.compile(r"^[+\-−]?[\d,]*\.?\d+")
_RULE_ROW = re.compile(r"^\|(?:\s*:?-+:?\s*\|)+$")
#: The words a table cell may hold that are verdict words, drawn in their meaning.
_CELL_WORDS = frozenset(
    {
        *look.GREEN_WORDS,
        *look.YELLOW_WORDS,
        *look.RED_WORDS,
        "different",
        "no significant change",
    }
)


def inline(text: str) -> str:
    """A report line's text as HTML: ``**bold**`` and ```code``` marks rendered, the rest
    escaped."""
    out: list[str] = []
    for part in re.split(r"(\*\*.+?\*\*|`[^`]*`)", text):
        if len(part) > 4 and part.startswith("**") and part.endswith("**"):
            out.append(f"<b>{esc(part[2:-2])}</b>")
        elif len(part) >= 2 and part.startswith("`") and part.endswith("`"):
            out.append(f"<code>{esc(part[1:-1])}</code>")
        else:
            out.append(esc(part))
    return "".join(out)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def condition_words(cell: str) -> str | None:
    """A condition written as JSON in a table, as its words: ``key value · key value``, each
    value spelt as a sentence spells it (``report.value_words``); None for any other cell."""
    if not cell.startswith("{"):
        return None
    try:
        value = json.loads(cell)
    except ValueError:
        return None
    if not isinstance(value, dict):
        return None
    return " · ".join(f"{k} {report.value_words(v)}" for k, v in value.items())


#: What a table cell holds that is code: a run id, a hex id, a snake_case identifier (a
#: failure kind, a signal, a measure), a path.
_CODE_CELL = re.compile(
    r"^(?:\d{8}T\d{6}Z-[0-9a-f]{4}|[0-9a-f]{12,64}|[a-z][a-z0-9]*(?:_[a-z0-9]+)+"
    r"|\.?[\w.-]*[A-Za-z][\w.-]*(?:/[\w.-]+)+)$"
)


def _cell(text: str, first: bool) -> str:
    words = condition_words(text) if first else None
    if words is not None:
        return f'<span class="mono">{esc(words)}</span>'
    if _CODE_CELL.match(text):
        return f'<span class="mono">{esc(text)}</span>'
    plain = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    head, _, tail = plain.partition(", ")
    if plain in _CELL_WORDS:
        return f'<b class="{word_class(plain)}">{esc(plain)}</b>'
    if tail and head in _CELL_WORDS:
        return f'<b class="{word_class(head)}">{esc(head)}</b>, {esc(tail)}'
    return inline(text)


def table_html(
    rows: Sequence[Sequence[str]],
    ident: str,
    *,
    sortable: bool = True,
    filter_rows: bool = False,
    flagged: Sequence[bool] | None = None,
    first_cond: bool = True,
    links: Mapping[tuple[int, int], str] | None = None,
    raw: bool = False,
    numeric: set[int] | None = None,
) -> str:
    """A table in Prove's panel: the header row first; a column of numbers to the right; the
    first column sticky; a filter box over it when asked; sortable by the fixed script. A cell
    in ``links`` (by body row and column) is a link to the address given. ``raw`` cells are
    HTML already, with ``numeric`` naming their columns of numbers."""
    head, body = list(rows[0]), [list(r) for r in rows[1:]]
    width = len(head)
    if numeric is None:
        numeric = set()
        for j in range(1, width):
            column = [r[j] for r in body if j < len(r)]
            if (
                column
                and all(_NUMBERISH.match(c) for c in column)
                and any(_NUMBER.match(c) for c in column)
            ):
                numeric.add(j)
    out = []
    if filter_rows:
        out.append(
            f'<input class="filter" data-filter="{esc(ident)}" placeholder="filter rows" '
            'aria-label="filter rows" hidden>'
        )
    sort = " data-sort" if sortable else ""
    out.append(f'<div class="tablewrap"><table id="{esc(ident)}"{sort}><thead><tr>')
    out.append(
        "".join(
            f'<th class="num">{inline(h)}</th>' if j in numeric else f"<th>{inline(h)}</th>"
            for j, h in enumerate(head)
        )
    )
    out.append("</tr></thead><tbody>")
    for i, row in enumerate(body):
        out.append('<tr class="flagged">' if flagged and flagged[i] else "<tr>")
        for j, text in enumerate(row):
            classes = " ".join(
                c
                for c in ("num" if j in numeric else "", "cond" if j == 0 and first_cond else "")
                if c
            )
            cell = text if raw else _cell(text, j == 0)
            if links and (i, j) in links:
                cell = f'<a href="{esc(links[(i, j)])}">{cell}</a>'
            out.append(f'<td class="{classes}">{cell}</td>' if classes else f"<td>{cell}</td>")
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def _list(items: Sequence[str], cls: str) -> str:
    return f'<ul class="{cls}">' + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>"


def _paragraph(text: str) -> str:
    """A line of prose: the report's technical lines (a test's caption, a statistic, a line that
    opens lowercase or with a figure) as a note, a sentence as a paragraph, a bold line bold."""
    if len(text) > 4 and text.startswith("**") and text.endswith("**"):
        return f'<p class="bold"><b>{inline(text[2:-2])}</b></p>'
    if text[:1].isupper():
        return f"<p>{inline(text)}</p>"
    return f'<p class="note">{inline(text)}</p>'


def lines_html(
    lines: Sequence[str], ident: str, *, rules: bool = False, inputs: bool = False
) -> str:
    """A section's lines as blocks, in order: a run of ``- `` lines a list, a run of ``|`` lines
    a table, ``###`` a sub-heading, anything else a paragraph. Tables are numbered under the
    section's id; the per-input table (``inputs``) gets a filter box and its flagged rows."""
    out: list[str] = []
    i, n = 0, 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("### "):
            out.append(f"<h3>{inline(line[4:])}</h3>")
            i += 1
        elif line.startswith("|"):
            block = []
            while i < len(lines) and lines[i].startswith("|"):
                if not _RULE_ROW.match(lines[i].strip()):
                    block.append(_cells(lines[i]))
                i += 1
            n += 1
            table_id = f"{ident}-{n}"
            if inputs and block and block[0][:1] == ["input"]:
                flags = [r[-1] not in ("–", "-", "") for r in block[1:]]
                out.append(table_html(block, table_id, filter_rows=True, flagged=flags))
            else:
                out.append(table_html(block, table_id))
        elif line.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(lines[i][2:])
                i += 1
            out.append(_list(items, "rules" if rules else "plain"))
        else:
            out.append(_paragraph(line))
            i += 1
    return "".join(out)


def _summary_dl(lines: Sequence[str]) -> str:
    """The summary's lines, ``- Label: text``, as a list of label and value."""
    pairs = []
    for line in lines:
        if not line.startswith("- "):
            continue
        label, sep, text = line[2:].partition(": ")
        pairs.append((label, text) if sep else ("", line[2:]))
    return "<dl>" + "".join(f"<dt>{esc(k)}</dt><dd>{inline(v)}</dd>" for k, v in pairs) + "</dl>"


# ---------- the charts ----------

_CW, _CH, _X0, _X1, _Y0, _Y1 = 660, 260, 56, 476, 20, 220
_LABEL = 24  # the most characters an end label shows of a run's name


def _n(x: float) -> str:
    return f"{x:.1f}"


def _f(x: Any) -> str:
    return "–" if x is None else f"{float(x):.3f}"


def _ticks(last: int) -> list[int]:
    if last <= 0:
        return [0]
    unit = 1
    for candidate in (1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000):
        unit = candidate
        if candidate * 6 >= last:
            break
    return list(range(0, last + 1, unit))


def _text(x: float, y: float, text: str, *, cls: str = "", anchor: str = "start") -> str:
    classes = f' class="{cls}"' if cls else ""
    at = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return f'<text{classes} x="{_n(x)}" y="{_n(y)}"{at}>{esc(text)}</text>'


def _svg(
    ident: str,
    title: str,
    desc: str,
    width: int,
    height: int,
    body: Sequence[str],
    standalone: bool,
) -> str:
    """One chart: its title and description first, the marks after. Saved as a file of its own
    it carries the SVG namespace and its own style with the look's colours by value, light and
    dark; inside a page it carries neither (the page's one stylesheet draws it) and no scheme."""
    t, d = f"{ident}-title", f"{ident}-desc"
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" id="{esc(ident)}" role="img" '
        f'aria-labelledby="{t} {d}" viewBox="0 0 {width} {height}" width="100%">'
        if standalone
        else f'<svg class="chart" role="img" aria-labelledby="{t} {d}" '
        f'viewBox="0 0 {width} {height}">'
    )
    style = f"<style>{_file_style(ident)}</style>" if standalone else ""
    return (
        head
        + f'<title id="{t}">{esc(title)}</title><desc id="{d}">{esc(desc)}</desc>'
        + style
        + "".join(body)
        + "</svg>"
    )


def _file_style(ident: str) -> str:
    def rules(c: Mapping[str, str]) -> str:
        i = f"#{ident}"
        return (
            f"{i} text{{font:11px {_FONT};fill:{c['text']}}}{i} .dimt{{fill:{c['dim']}}}"
            f"{i} .axis{{stroke:{c['rule']};stroke-width:1}}"
            f"{i} .thr{{stroke:{c['text']};stroke-width:1}}"
            f"{i} .zero{{stroke:{c['dim']};stroke-width:1}}"
            f"{i} .asked{{stroke:{c['dim']};stroke-width:1}}"
            f"{i} .line{{fill:none;stroke-width:1.5}}{i} .line.before{{stroke:{c['dim']}}}"
            f"{i} .line.after{{stroke:{c['after']};stroke-width:2.5}}"
            f"{i} .band{{stroke:none;fill-opacity:.1}}{i} .band.before{{fill:{c['dim']}}}"
            f"{i} .band.after{{fill:{c['after']}}}"
            f"{i} .mark{{stroke:none}}{i} .mark.before{{fill:{c['dim']}}}"
            f"{i} .mark.after{{fill:{c['after']}}}"
            f"{i} .label.before{{fill:{c['dim']}}}{i} .label.after{{fill:{c['after']}}}"
        )

    return f"{rules(LIGHT)}@media (prefers-color-scheme: dark){{{rules(DARK)}}}"


def curve_words(events: Sequence[str], bootstrap: Mapping[str, Any], unit: str) -> str:
    """A curve chart's title, in the commands' words: what it shows, the event, the estimator
    and the band's level, resamples and seed."""
    b, seed = bootstrap.get("b"), bootstrap.get("seed")
    said = " or ".join(events)
    return (
        f"Share of tries not yet failed, by {unit}: {said}; Aalen–Johansen, 95% band by bootstrap "
        f"resampling inputs, B = {look.count(b) if b is not None else '–'}, seed = {seed}"
    )


def curves_svg(
    ident: str,
    series: Sequence[Mapping[str, Any]],
    *,
    unit: str,
    title: str,
    standalone: bool,
) -> str:
    """The share of tries not yet failed by step, each run a step line from 1 at step 0: the
    first run in ``--dim``, the second in ``--after``, each labelled where its line ends; its 95%
    band a faint fill of its line's colour (DM7); a mark with a hover title on every step."""
    last = max([int(p["step"]) for s in series for p in s["curve"]] or [1])
    last = max(last, 1)

    def x(step: float) -> float:
        return _X0 + (_X1 - _X0) * step / last

    def y(share: float) -> float:
        return _Y1 - (_Y1 - _Y0) * share

    body: list[str] = []
    for k in range(6):
        v = k / 5
        body.append(f'<line class="axis" x1="{_X0}" x2="{_X1}" y1="{_n(y(v))}" y2="{_n(y(v))}"/>')
        body.append(_text(_X0 - 8, y(v) + 4, f"{v:.1f}", cls="dimt", anchor="end"))
    for tick in _ticks(last):
        body.append(_text(x(tick), _Y1 + 16, look.count(tick), cls="dimt", anchor="middle"))
    body.append(f'<line class="thr" x1="{_n(x(last))}" x2="{_n(x(last))}" y1="{_Y0}" y2="{_Y1}"/>')
    body.append(
        _text(x(last), _Y0 - 6, f"last {unit} {look.count(last)}", cls="dimt", anchor="middle")
    )
    for s in series:
        curve = s["curve"]
        if not curve or any(p.get("lo") is None or p.get("hi") is None for p in curve):
            continue
        up = f"M{_n(x(0))},{_n(y(1.0))}"
        for p in curve:
            up += f" H{_n(x(p['step']))} V{_n(y(p['hi']))}"
        up += f" H{_n(x(last))} V{_n(y(curve[-1]['lo']))}"
        for p in reversed(curve):
            up += f" H{_n(x(p['step']))} V{_n(y(p['lo']))}"
        up += f" H{_n(x(0))} Z"
        tip = f"{s['name']}: 95% band, bootstrap resampling inputs"
        body.append(f'<path class="band {s["cls"]}" d="{up}"><title>{esc(tip)}</title></path>')
    ends: list[tuple[str, str, float]] = []
    for s in series:
        curve, cls, name = s["curve"], s["cls"], s["name"]
        d = f"M{_n(x(0))},{_n(y(1.0))}"
        share = 1.0
        for p in curve:
            d += f" H{_n(x(p['step']))} V{_n(y(p['survival']))}"
            share = float(p["survival"])
        d += f" H{_n(x(last))}"
        tip = f"{name}: {_f(share)} not yet failed by {unit} {look.count(last)}"
        body.append(f'<path class="line {cls}" d="{d}"><title>{esc(tip)}</title></path>')
        for p in curve:
            tip = (
                f"{name}, {unit} {look.count(p['step'])}: at risk {look.count(p['at_risk'])}, "
                f"failed {look.count(p['died'])}, not yet failed {_f(p['survival'])} "
                f"({_f(p.get('lo'))} – {_f(p.get('hi'))})"
            )
            body.append(
                f'<circle class="mark {cls}" cx="{_n(x(p["step"]))}" cy="{_n(y(p["survival"]))}" '
                f'r="2.5"><title>{esc(tip)}</title></circle>'
            )
        ends.append((cls, name, share))
    placed: list[float] = []
    for cls, name, share in ends:
        at = y(share) + 4
        if any(abs(at - other) < 14 for other in placed):
            at = max(placed) + 14
        placed.append(at)
        shown = name if len(name) <= _LABEL else name[: _LABEL - 1] + "…"
        body.append(_text(_X1 + 8, at, f"{shown} {_f(share)}", cls=f"label {cls}"))
    body.append(_text((_X0 + _X1) / 2, _CH + 18, f"{unit}", cls="dimt", anchor="middle"))
    desc = (
        "Each run's share of tries not yet failed at each step, "
        + " and ".join(s["name"] for s in series)
        + "; the first in grey, the second in violet; each band its 95% range."
    )
    return _svg(ident, title, desc, _CW, _CH + 26, body, standalone)


def curve_rows(series: Sequence[Mapping[str, Any]], unit: str) -> list[list[str]]:
    """The curves' data as a table: one row a step, each run's at risk, failed, share and band
    at that step, blank where a run has no step there."""
    head = [unit]
    for s in series:
        head += [f"{s['name']}: at risk", "failed", "not yet failed", "95% band"]
    steps = sorted({int(p["step"]) for s in series for p in s["curve"]})
    rows = [head]
    for step in steps:
        row = [look.count(step)]
        for s in series:
            p = next((q for q in s["curve"] if int(q["step"]) == step), None)
            if p is None:
                row += ["", "", "", ""]
            else:
                band = (
                    "–"
                    if p.get("lo") is None or p.get("hi") is None
                    else f"{_f(p['lo'])} – {_f(p['hi'])}"
                )
                row += [look.count(p["at_risk"]), look.count(p["died"]), _f(p["survival"]), band]
        rows.append(row)
    return rows


_HR_TICKS = (0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0)


def hazard_words(hazard: Mapping[str, Any]) -> str:
    cells = hazard.get("cells")
    alpha = hazard.get("alpha")
    over = (
        ""
        if cells is None
        else f" over {look.count(cells)} common {'cell' if cells == 1 else 'cells'}"
    )
    level = "" if alpha is None else f", α = {alpha:g}"
    return (
        "Hazard ratio, after against before, with its 95% range, beside the limit the test could "
        f"not have seen below and the ratio asked for: log-rank, stratified by config cell{over}"
        f"{level}, 80% power"
    )


def hazard_svg(ident: str, hazard: Mapping[str, Any], *, title: str, standalone: bool) -> str:
    """The hazard ratio with its 95% range on a log axis, the no-change line at 1, the limit the
    test could not have seen below in both directions and the ratio asked for (DM8), each a
    solid line with its value written on it; the direction marked ▲ or ▼."""
    hr, lo, hi = (
        hazard.get("hazard_ratio"),
        hazard.get("hazard_ratio_lo"),
        hazard.get("hazard_ratio_hi"),
    )
    mde, asked = hazard.get("mde_hazard_ratio"), hazard.get("max_mde_hr")
    values = [v for v in (hr, lo, hi, mde, asked, 1.0) if v is not None and v > 0]
    values += [1.0 / v for v in (mde, asked) if v is not None and v > 0]
    low = max([t for t in _HR_TICKS if t <= min(values) * 1.0001] or [_HR_TICKS[0]])
    high = min([t for t in _HR_TICKS if t >= max(values) * 0.9999] or [_HR_TICKS[-1]])
    if low >= high:
        low, high = 0.1, 10.0
    width, height, x0, x1, mid = 700, 124, 60, 640, 62

    def x(v: float) -> float:
        return x0 + (math.log(v) - math.log(low)) / (math.log(high) - math.log(low)) * (x1 - x0)

    body: list[str] = []
    for tick in _HR_TICKS:
        if low <= tick <= high:
            body.append(
                f'<line class="axis" x1="{_n(x(tick))}" x2="{_n(x(tick))}" y1="42" y2="82"/>'
            )
            body.append(_text(x(tick), 98, f"{tick:g}", cls="dimt", anchor="middle"))
    body.append(f'<line class="zero" x1="{_n(x(1.0))}" x2="{_n(x(1.0))}" y1="32" y2="92"/>')
    body.append(_text(x(1.0) + 5, 38, "no change", cls="dimt"))
    if mde is not None and mde > 0:
        for v in (mde, 1.0 / mde):
            body.append(
                f'<line class="thr" x1="{_n(x(v))}" x2="{_n(x(v))}" y1="38" y2="86">'
                f"<title>could not have detected a hazard ratio below {_f(v)}</title></line>"
            )
            body.append(_text(x(v), 114, f"limit {_f(v)}", anchor="middle"))
    if asked is not None and asked > 0:
        for v in (asked, 1.0 / asked):
            body.append(
                f'<line class="asked" x1="{_n(x(v))}" x2="{_n(x(v))}" y1="46" y2="78">'
                f"<title>asked for {v:g}</title></line>"
            )
            shown = f"{v:g}" if v == asked else _f(v)
            body.append(_text(x(v), 16, f"asked {shown}", cls="dimt", anchor="middle"))
    if lo is not None and hi is not None and lo > 0 and hi > 0:
        body.append(
            f'<line class="line after" x1="{_n(x(lo))}" x2="{_n(x(hi))}" y1="{mid}" y2="{mid}">'
            f"<title>95% range {_f(lo)} to {_f(hi)}</title></line>"
        )
    if hr is not None and hr > 0:
        body.append(
            f'<circle class="mark after" cx="{_n(x(hr))}" cy="{mid}" r="5">'
            f"<title>hazard ratio {_f(hr)}, after against before</title></circle>"
        )
        arrow = "▼" if hr < 1 else "▲" if hr > 1 else ""
        body.append(
            _text(x(hr), mid - 12, f"{arrow} {_f(hr)}".strip(), cls="label after", anchor="middle")
        )
    desc = (
        "The per-step failure rate after against before on a log axis; the range is Peto's "
        "one-step estimate's; the limit is from the log-rank's own information at 80% power."
    )
    return _svg(ident, title, desc, width, height, body, standalone)


def hazard_rows(hazard: Mapping[str, Any]) -> list[list[str]]:
    lo, hi = hazard.get("hazard_ratio_lo"), hazard.get("hazard_ratio_hi")
    mde, asked = hazard.get("mde_hazard_ratio"), hazard.get("max_mde_hr")
    return [
        ["hazard ratio", "95% range", "could not have detected below", "asked for"],
        [
            _f(hazard.get("hazard_ratio")),
            "–" if lo is None or hi is None else f"{_f(lo)} to {_f(hi)}",
            "–" if mde is None else f"{_f(mde)} and {_f(1.0 / mde)}",
            "–" if asked is None else f"{asked:g}",
        ],
    ]


def figure(ident: str, caption: str, svg: str, rows: Sequence[Sequence[str]]) -> str:
    """A chart in Prove's panel: its caption, the SVG, and its data as a table under it."""
    return (
        f'<figure id="{esc(ident)}"><figcaption>{esc(caption)}</figcaption>{svg}'
        f"{table_html(rows, f'{ident}-data', sortable=False, first_cond=False)}</figure>"
    )


# ---------- the pages ----------


def render(view: Mapping[str, Any], store: str, *, standalone: bool = False) -> str:
    """One page from one view document (``core.View.document``): the runs page, a verdict's
    page, or a verdict's could-not-say page; ``standalone`` renders the verdict page as the
    HTML report."""
    kind = str(view["view"])
    if kind == "runs":
        return _runs_page(view, store)
    if kind == "could not say":
        return _could_not_say_page(view, store)
    return _verdict_page(view, store, standalone)


def _runs_page(v: Mapping[str, Any], store: str) -> str:
    parts = [verdict_heading(str(v["verdict"]), str(v["sentence"]))]
    head = ["#", "name", "id", "target or tool", "rows", "failed", "traces", "started", "status"]
    rows: list[list[str]] = [head]
    for i, run in enumerate(v["runs"]):
        p = f"/runs/{i}"
        name = fact(f"{p}/name", run["name"])
        if run.get("where"):
            name = f'<a href="{esc(run["where"])}">{name}</a>'
        failed = run["failed"]
        rows.append(
            [
                fact(f"{p}/number", run["number"]),
                name,
                fact(f"{p}/run_id", run["run_id"], cls="mono"),
                fact(f"{p}/tool", run["tool"]),
                fact(f"{p}/rows", run["rows"], look.count(run["rows"])),
                fact(f"{p}/failed", failed, "–" if failed is None else look.count(failed)),
                fact(f"{p}/traced", run["traced"], "yes" if run["traced"] else "no"),
                fact(f"{p}/created_at", run["created_at"]),
                fact(f"{p}/status", run["status"]),
            ]
        )
    if len(rows) > 1:
        # a run's name links its newest saved where page (A8)
        parts.append(table_html(rows, "runs", filter_rows=True, raw=True, numeric={0, 4, 5}))
        events = v.get("events")
        if events:
            counted = f"failed counts the outcomes {', '.join(str(e) for e in events)}."
        else:
            counted = "No failures were given, so the failed column is not counted."
        parts.append(
            f'<p class="note">Newest first. {esc(counted)} A run with a saved where verdict links '
            "its newest; one without has no page of its own.</p>"
        )
    else:
        parts.append('<p class="note">No complete run is listed in this store.</p>')
    parts.append("<h2>Saved verdicts</h2>")
    saved = v["saved"]
    if saved:
        rows = [["kind", "runs", "verdict", "sentence", "id", "saved"]]
        for i, s in enumerate(saved):
            p = f"/saved/{i}"
            word = str(s["verdict"])
            short = fact(f"{p}/id", s["id"], s["id"][:12], cls="mono")
            rows.append(
                [
                    fact(f"{p}/kind", s["kind"]),
                    fact(f"{p}/runs", s["runs"]),
                    fact(f"{p}/verdict", word, tag="b", cls=word_class(word)),
                    # the sentence wraps: a cell's fact never does, by Prove's rule
                    f'<span class="wrap">{esc(s["sentence"])}</span>',
                    f'<a href="{esc(s["address"])}">{short}</a>',
                    fact(f"{p}/saved_at", s["saved_at"]),
                ]
            )
        parts.append(table_html(rows, "saved", first_cond=False, raw=True, numeric=set()))
        parts.append(
            '<p class="note">Newest first. Saved by --save and --out on where, compare, fix-check '
            "and changes; each id opens the verdict's page.</p>"
        )
    else:
        parts.append(
            '<p class="note">No saved verdict yet. --save on where, compare, fix-check or changes '
            "saves one; --out saves it and hands it over.</p>"
        )
    others = list(v.get("others") or ())
    prove = v.get("prove")
    if others or prove:
        parts.append("<h2>Other pages</h2>")
        for other in others:
            parts.append(
                f'<p class="note">The store <b>{esc(other["name"])}</b>, which the config names: '
                f'<a href="{esc(other["href"])}">its runs and saved verdicts</a>.</p>'
            )
        if prove:
            parts.append(
                f'<p class="note">Prove\'s dashboard for this store, built beside these pages: '
                f'<a href="{esc(prove)}">its pages</a>.</p>'
            )
    return frame(
        title=f"Runs · {TOOL}",
        view="runs",
        crumbs="",
        store=store,
        address=str(v["address"]),
        body="\n".join(parts),
        standalone=False,
    )


def _verdict_page(v: Mapping[str, Any], store: str, standalone: bool) -> str:
    kind, ident = str(v["kind"]), str(v["id"])
    sections: list[dict[str, Any]] = list(v["sections"])
    summary = next((s for s in sections if s["heading"] == "Summary"), None)
    caveats = next((s for s in sections if s["heading"] == "Before you act on this"), None)
    parts = ['<section id="verdict">', verdict_heading(str(v["verdict"]), str(v["sentence"]))]
    if summary is not None:
        parts.append("<h3>Summary</h3>" + _summary_dl(summary["lines"]))
    if caveats is not None:
        items = [line[2:] for line in caveats["lines"] if line.startswith("- ")]
        parts.append("<h3>Before you act on this</h3>" + _list(items, "plain"))
    versions = v.get("versions") or {}
    files = " · ".join(str(f) for f in v["files"])
    parts.append(
        "<h3>Saved</h3><dl>"
        f"<dt>artifact</dt><dd>{fact('/saved', v['saved'], cls='mono')}</dd>"
        f'<dt>files</dt><dd><span class="mono">{esc(files)}</span></dd>'
        f"<dt>versions</dt><dd>{TOOL} {esc(versions.get('trace', '–'))} "
        f'<span class="dim">·</span> poisson-prove {esc(versions.get("prove", "–"))}</dd></dl>'
    )
    if not standalone:
        parts.append(
            f'<p class="links"><a href="{esc(ident)}/could-not-say.html">what this cannot say</a> '
            '<span class="dim">·</span> <a href="../index.html">runs</a></p>'
        )
    parts.append("</section>")
    seen: set[str] = set()
    for section in sections:
        heading = section["heading"]
        if heading in ("Summary", "Before you act on this") or heading is None:
            continue
        ident_s = slug(heading) or "section"
        while ident_s in seen or ident_s in (
            "verdict",
            "charts",
            "curve",
            "curves",
            "hazard-ratio",
        ):
            ident_s += "-"
        seen.add(ident_s)
        inner = _section_html(v, heading, section["lines"], ident_s)
        parts.append(f'<section id="{ident_s}"><h2>{inline(heading)}</h2>{inner}</section>')
        if kind == "compare" and heading == "Comparison" and v.get("curves"):
            parts.append(_compare_charts(v))
    return frame(
        title=str(v["title"]),
        view=kind,
        crumbs=("" if standalone else '<a href="../index.html">runs</a> / ') + esc(v["name"]),
        store=store,
        address=str(v["address"]),
        body="\n".join(parts),
        standalone=standalone,
    )


def _section_html(v: Mapping[str, Any], heading: str, lines: Sequence[str], ident: str) -> str:
    kind = str(v["kind"])
    if kind == "where" and heading.startswith("Share not yet failed") and v.get("curve"):
        return _where_curve(v, lines, ident)
    rules = heading == "What this cannot say"
    return lines_html(lines, ident, rules=rules, inputs=heading == "Inputs that changed")


def _where_curve(v: Mapping[str, Any], lines: Sequence[str], ident: str) -> str:
    """The where page's curve section: the report's caption as the figure's, the chart, the
    report's own table of the curve as its data, then the section's remaining lines."""
    c = v["curve"]
    kept = [line for line in lines if line.strip()]
    caption = kept[0] if kept and not kept[0].startswith(("|", "- ")) else ""
    table = [
        _cells(line) for line in kept if line.startswith("|") and not _RULE_ROW.match(line.strip())
    ]
    rest = [line for line in kept[1 if caption else 0 :] if not line.startswith("|")]
    unit = str(c["unit"])
    series = [{"cls": "after", "name": c["name"], "curve": c["curve"]}]
    title = curve_words(c["events"], c["bootstrap"], unit)
    svg = curves_svg("curve", series, unit=unit, title=title, standalone=False)
    rows = table or curve_rows(series, unit)
    return (
        f'<figure id="curve"><figcaption>{inline(caption)}</figcaption>{svg}'
        f"{table_html(rows, 'curve-data', sortable=False, first_cond=False)}</figure>"
        + lines_html(rest, ident)
    )


def _compare_charts(v: Mapping[str, Any]) -> str:
    """The compare page's charts (SV15, DM7, DM8): the two runs' curves under compare's
    failures and the hazard ratio with its range, each with its data under it."""
    c = v["curves"]
    unit = str(c["unit"])
    series = [
        {"cls": "before" if r["arm"] == "a" else "after", "name": r["name"], "curve": r["curve"]}
        for r in c["runs"]
    ]
    title = curve_words(c["events"], c["bootstrap"], unit)
    parts = [
        '<section id="charts"><h2>Charts</h2>',
        figure(
            "curves",
            title,
            curves_svg("curves", series, unit=unit, title=title, standalone=False),
            curve_rows(series, unit),
        ),
    ]
    hazard = v.get("hazard")
    if hazard:
        words = hazard_words(hazard)
        parts.append(
            figure(
                "hazard-ratio",
                words,
                hazard_svg("hazard-ratio", hazard, title=words, standalone=False),
                hazard_rows(hazard),
            )
        )
    parts.append(
        "<p class=\"note\">The curves are each run's where curve under this comparison's failures, "
        "with where's own defaults; the hazard ratio is this comparison's.</p></section>"
    )
    return "".join(parts)


def _could_not_say_page(v: Mapping[str, Any], store: str) -> str:
    kind, ident = str(v["kind"]), str(v["id"])
    parts = [
        verdict_heading(str(v["verdict"]), str(v["sentence"])),
        '<section id="what-this-cannot-say"><h2>What this cannot say</h2>'
        + _list([str(s) for s in v["cannot_say"]], "rules")
        + "</section>",
    ]
    detected = v.get("detected")
    if detected:
        parts.append(
            '<section id="what-it-could-not-have-detected"><h2>What it could not have detected</h2>'
            + lines_html(detected, "what-it-could-not-have-detected")
            + "</section>"
        )
    parts.append(
        f'<p class="links"><a href="../{esc(ident)}.html">the verdict</a> '
        '<span class="dim">·</span> <a href="../../index.html">runs</a></p>'
    )
    return frame(
        title=f"What this cannot say · {v['title']}",
        view="could not say",
        crumbs=f'<a href="../../index.html">runs</a> / '
        f'<a href="../{esc(ident)}.html">{esc(v["name"])}</a>',
        store=store,
        address=f"trace/{kind}/{ident}/could-not-say.html",
        body="\n".join(parts),
        standalone=False,
    )
