"""The type the look standard sets for the static pages and the charts (``docs/cli-look.md``, "The
static UI", Type): the system's own fonts, no other; prose and labels (table headers, detail
labels, captions) in the system's sans, and verdict words, numbers, names, addresses and table
cells in the monospace.

- The pages ``ui`` writes, and the HTML report: each carries Prove's stylesheet and then Trace's
  own rules. Read in that order, the last rule that names a table cell, a detail value or the
  crumbs (``td``, ``dd``, ``nav``) sets them in the monospace, and the last that names a table
  header, a detail label or a caption (``th``, ``dt``, ``figcaption``) sets them in the sans, or
  names no font and leaves them the page's own, the sans.
- The curve ``where --svg`` draws, and the HTML report around it, name no font outside the look's
  two: the sans for the chart, and nothing that is not the system's own.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from prove_floor_support import EVENT, STORE_1_2, copy

from poisson_trace import api

SANS = "system-ui, -apple-system, 'Segoe UI', sans-serif"
MONO = "ui-monospace, Menlo, Consolas, monospace"
CELLS = ("td", "dd", "nav")
LABELS = ("th", "dt", "figcaption")

_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_FONT = re.compile(r"(?:^|;)\s*font(?:-family)?\s*:\s*([^;]+)")


def _face(value: str) -> str | None:
    if "ui-monospace" in value:
        return "mono"
    if "system-ui" in value:
        return "sans"
    return None


def faces(css: str) -> dict[str, str | None]:
    """For each element of ``CELLS`` and ``LABELS``, the face the last rule naming it alone sets
    (``mono`` or ``sans``), else the page's own (``body``'s)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    last: dict[str, str] = {}
    for selectors, body in _RULE.findall(css):
        named = {s.strip() for s in selectors.split(",")}
        found = [_face(m) for m in _FONT.findall(body)]
        face = next((f for f in reversed(found) if f is not None), None)
        if face is None:
            continue
        for element in (*CELLS, *LABELS, "body"):
            if element in named:
                last[element] = face
    return {element: last.get(element, last.get("body")) for element in (*CELLS, *LABELS)}


def _styles(html: str) -> str:
    return "\n".join(re.findall(r"<style>(.*?)</style>", html, flags=re.S))


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = tmp_path_factory.mktemp("type")
    copy(STORE_1_2, work)
    return work / "store"


@pytest.fixture(scope="module")
def where(store: Path) -> api.WhereResult:
    return api.where(str(store), "#1", event=[EVENT[1]])


def test_the_pages_set_cells_in_the_monospace_and_labels_in_the_sans(store: Path, where: api.WhereResult) -> None:
    api.save(where)
    api.build_pages(str(store))
    base = store / ".poisson" / "ui" / "trace"
    sheet = (base / "style.css").read_text(encoding="utf-8")
    pages = sorted(base.rglob("*.html"))
    assert len(pages) >= 2, pages
    for page in pages:
        got = faces(sheet + "\n" + _styles(page.read_text(encoding="utf-8")))
        assert got == {"td": "mono", "dd": "mono", "nav": "mono", "th": "sans", "dt": "sans", "figcaption": "sans"}, \
            (page.relative_to(base).as_posix(), got)


def test_the_html_report_sets_cells_in_the_monospace_and_labels_in_the_sans(where: api.WhereResult) -> None:
    got = faces(_styles(where.to_html()))
    assert got == {"td": "mono", "dd": "mono", "nav": "mono", "th": "sans", "dt": "sans", "figcaption": "sans"}, got


def test_the_curve_names_the_sans_and_no_other_font(where: api.WhereResult) -> None:
    svg = where.to_svg()
    assert re.findall(r'font-family="([^"]*)"', svg) == [SANS], svg[:400]
    assert "font:" not in svg and "font-family:" not in svg, "the curve sets its face once, on the drawing"


def test_the_html_report_names_only_the_systems_own_fonts(where: api.WhereResult) -> None:
    html = where.to_html()
    named = re.findall(r'font-family="([^"]*)"', html) + [m.strip() for m in re.findall(r"font-family\s*:\s*([^;}]+)", html)]
    assert named, "the report names its fonts"
    allowed = {" ".join(stack.replace('"', "'").split()) for stack in (SANS, MONO)}
    for family in named:
        assert " ".join(family.replace('"', "'").replace(",", ", ").split()) in allowed, family
    assert not re.search(r"(?i)helvetica|arial", html), "a font that is not the system's own"
