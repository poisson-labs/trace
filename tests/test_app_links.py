"""TF19-5: charts as links (``docs/app.md``).

**TF19-5** The app draws no chart. Where a page has one the screen shows its link, a detail line
``label  trace/<address>``; the pages are rebuilt before a link shows, so every link on screen
resolves to a file on disk (and a page that was removed comes back). ``tab`` moves the focus to
the links; Enter on a focused link opens it in the browser (faked: ``webbrowser.open`` once, with
the page's whole ``file://`` address and its anchor), and ``y`` copies that same address
(Textual's ``copy_to_clipboard``), the message line saying ``note: copied the link``.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from app_support import app_world, copy_world, drive

LINK = re.compile(r"^[ ›] (\S(?:[^ ]| (?! ))*?)\s{2,}(trace/\S+)$")


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return app_world(tmp_path_factory)


@pytest.fixture
def work(world: Path, tmp_path: Path) -> Path:
    work = copy_world(world, tmp_path)
    for store in ("store", "tables", "jstore"):
        shutil.rmtree(work / store / ".poisson" / "ui", ignore_errors=True)
    return work


def _links(rows: list[str]) -> list[tuple[str, str]]:
    out = []
    for r in rows:
        m = LINK.match(r.rstrip())
        if m:
            out.append((m.group(1).strip(), m.group(2)))
    return out


def _uri(work: Path, address: str, store: str = "store") -> str:
    return f"file://{(work / store).resolve()}/.poisson/ui/{address}"


EXPECTED = {
    "home": ([], [("pages", r"trace/index\.html")]),
    "run": (["r", "enter"], [("curve", r"trace/where/[0-9a-f]{16}\.html#curve"), ("page", r"trace/where/[0-9a-f]{16}\.html")]),
    "verdict compare": (["c", "enter"], [("curves", r"trace/compare/[0-9a-f]{16}\.html#curves"),
                                        ("hazard ratio chart", r"trace/compare/[0-9a-f]{16}\.html#hazard-ratio"),
                                        ("page", r"trace/compare/[0-9a-f]{16}\.html")]),
    "verdict fix-check": (["f", "enter"], [("page", r"trace/fix-check/[0-9a-f]{16}\.html")]),
    "changes": (["f", "enter", "g"], [("page", r"trace/changes/[0-9a-f]{16}\.html")]),
    "could not say": (["c", "enter", "d"], [("page", r"trace/compare/[0-9a-f]{16}/could-not-say\.html")]),
}


@pytest.mark.parametrize("screen", list(EXPECTED))
def test_tf19_5_each_screen_s_links_and_their_pages(work: Path, screen: str) -> None:
    keys, expected = EXPECTED[screen]
    s = drive(work, keys, size=(120, 60))
    links = _links(s.last.body)
    assert [label for label, _ in links] == [label for label, _ in expected], (links, s.last.text())
    for (label, address), (_, pattern) in zip(links, expected, strict=True):
        assert re.fullmatch(pattern, address), (label, address)
        page = work / "store" / ".poisson" / "ui" / address.split("#")[0]
        assert page.is_file(), page
        if "#" in address:
            assert f'id="{address.split("#")[1]}"' in page.read_text(encoding="utf-8")


def test_tf19_5_the_ids_are_the_saved_verdicts(work: Path) -> None:
    s = drive(work, ["c", "enter"], size=(120, 40))
    ident = next(p.name for p in (work / "store" / ".poisson" / "artifacts" / "compare").iterdir())
    assert all(ident in a for _, a in _links(s.last.body) if a.startswith("trace/compare/"))


def test_tf19_5_pages_are_rebuilt_before_a_link_shows(work: Path) -> None:
    """The pages removed while the app is open (as Prove's own rebuild of its dashboard removes
    them): the next screen with a link builds them again before it draws."""
    ui = work / "store" / ".poisson" / "ui"
    for keys, then in ((["r"], "enter"), (["c", "enter"], "d"), (["f", "enter"], "g")):
        s = drive(work, [*keys, lambda: shutil.rmtree(ui, ignore_errors=True), then], size=(120, 60))
        links = _links(s.last.body)
        assert links, s.last.text()
        for _label, address in links:
            assert (ui / address.split("#")[0]).is_file(), address


@pytest.mark.parametrize("screen", ["run", "verdict compare", "could not say", "home"])
def test_tf19_5_enter_opens_the_focused_link(work: Path, screen: str) -> None:
    keys, _expected = EXPECTED[screen]
    s = drive(work, [*keys, "<snap>"], size=(120, 60))
    links = _links(s.grids[0].body)
    has_rows = bool(s.grids[0].focused()) and not _links([s.grids[0].focused_text()])
    tab = ["tab"] if has_rows else []
    s = drive(work, [*keys, *tab, "enter"], size=(120, 60))
    assert s.fakes.opened == [_uri(work, links[0][1])], (s.fakes.opened, links)


def test_tf19_5_enter_on_the_second_link(work: Path) -> None:
    s = drive(work, ["c", "enter", "<snap>"], size=(120, 60))
    links = _links(s.grids[0].body)
    s = drive(work, ["c", "enter", "tab", "down", "enter"], size=(120, 60))
    assert s.fakes.opened == [_uri(work, links[1][1])]


@pytest.mark.parametrize("screen", ["run", "verdict compare", "verdict fix-check"])
def test_tf19_5_y_copies_the_focused_link(work: Path, screen: str) -> None:
    keys, _expected = EXPECTED[screen]
    s = drive(work, [*keys, "<snap>", "tab", "y"], size=(120, 60))
    links = _links(s.grids[0].body)
    assert s.fakes.copied == [_uri(work, links[0][1])], s.fakes.copied
    assert s.last.message == "note: copied the link"
    assert s.fakes.opened == []


def test_tf19_5_the_focused_link_is_marked(work: Path) -> None:
    s = drive(work, ["r", "enter", "tab"], size=(120, 60))
    g = s.last
    row = g.focused_text()
    assert _links([row]), row
    assert row.startswith("›")

