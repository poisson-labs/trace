"""TF19-2: every screen of section 17.2's table, as the design draws it (A4 to A7, DM5, DM6, DM9,
DM12, DM13).

**TF19-2** Each screen, reached by keys alone from home, at 120 × 40 and at 80 × 24: its header
(``poisson-trace · <title>``, its subject, the store slot), the six bands (a dim rule under the
header, the message line, a dim rule, the key bar), its verdict line where it shows a result
(the core's word and sentence, the word in its meaning's style), its detail labels in the
design's order, its table's columns, the focus (one row, ``›`` and reverse video, on the first
row when the screen opens), and its key bar (the shared keys first, the screen's own letters, ``?
help`` and ``q quit`` last). Home with no ``trace.toml`` is the empty state naming ``poisson-trace
init`` and ``poisson-trace init --agent``, not a refusal.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tf19_support import (
    KEY_NAME,
    OWN,
    PLANTED_KEYS,
    Grid,
    app_world,
    cli,
    columns,
    copy_world,
    drive,
    found_steps,
    name_shown,
    norm,
)

SIZES = [(120, 40), (80, 24)]

#: How each screen is reached from home, its title, its subject, and its own letters' key.
NAV: dict[str, tuple[list[str], str, str, str]] = {
    "home": ([], "home", "", "home"),
    "runs": (["r"], "runs", "store", "runs"),
    "run": (["r", "enter"], "run", "agent after", "run"),
    "imports": (["i"], "imports", "jstore", "imports"),
    "compare": (["c"], "compare", "pick two runs", "compare"),
    "fix-check": (["f"], "fix-check", "pick two runs", "fix-check"),
    "verdict compare": (["c", "enter"], "compare", "agent before → agent after", "verdict compare"),
    "verdict fix-check": (["f", "enter"], "fix-check", "agent before → agent after", "verdict fix-check"),
    "changes": (["f", "enter", "g"], "changes", "agent before → agent after", "changes"),
    "could not say": (["c", "enter", "d"], "could not say", "agent before → agent after", "could not say"),
    "help": (["?"], "help", "", ""),
}


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return app_world(tmp_path_factory)


@pytest.fixture
def work(world: Path, tmp_path: Path) -> Path:
    return copy_world(world, tmp_path)


def _verdict(work: Path, argv: list[str]) -> tuple[str, str]:
    doc = json.loads(cli(work, [*argv, "--json"]).out)
    return str(doc["verdict"]), str(doc["sentence"])


EXPECTED_VERDICT: dict[str, list[str]] = {
    "run": ["where", "agent after"],
    "verdict compare": ["compare", "agent before", "agent after"],
    "verdict fix-check": ["fix-check", "agent before", "agent after", "--inputs", "all"],
    "changes": ["changes", "agent before", "agent after"],
    "runs": ["runs"],
}


def _bands(g: Grid, w: int, h: int) -> None:
    assert (g.width, g.height) == (w, h)
    assert g.rows[1] == "─" * w and set(g.mask_of(1, 0, w)) == {"D"}
    assert g.rows[-2] == "─" * w and set(g.mask_of(h - 2, 0, w)) == {"D"}
    assert g.mask_of(0, 0, len("poisson-trace")) == "B" * len("poisson-trace")
    assert len(g.header.rstrip()) <= w


def _keybar(g: Grid, screen: str) -> None:
    keys = g.keys()
    assert keys[-2:] == ["?", "q"] or (screen == "help" and keys[-1] == "q"), keys
    shared = [k for k in keys if k in ("↑↓", "enter", "esc")]
    assert keys[: len(shared)] == shared, keys  # move, Enter, Esc first, in that order
    assert shared == [k for k in ("↑↓", "enter", "esc") if k in shared]
    if screen not in ("home", "help"):
        assert "esc" in keys, keys
    for letter in OWN.get(NAV[screen][3], ()):
        assert letter in keys, (screen, letter, keys)
    assert ("m" in keys) == any("more lines above the table: m shows them" in r for r in g.body), keys


@pytest.mark.parametrize("size", SIZES, ids=["120x40", "80x24"])
@pytest.mark.parametrize("screen", list(NAV))
def test_tf19_2_each_screen_s_frame(work: Path, screen: str, size: tuple[int, int]) -> None:
    keys, title, subject, _ = NAV[screen]
    s = drive(work, keys, size=size)
    g = s.last
    _bands(g, *size)
    assert g.title() == title, g.header
    assert g.subject() == subject, g.header
    assert g.slot() == "trace.toml"
    _keybar(g, screen)
    if screen in EXPECTED_VERDICT:
        word, sentence = _verdict(work, EXPECTED_VERDICT[screen])
        first = g.body[0]
        assert first.startswith(f"  {word}  "), (first, word)
        assert g.value_of(word) == sentence or g.body_text().startswith(f"{word} {sentence}"), g.text()
        role = g.mask_of(2, 2, len(word))
        assert len(set(role)) == 1 and role[0] in "GYRB", role
        if size == (120, 40) and screen != "runs":
            # the verdict line is the plain command's first line
            plain = cli(work, EXPECTED_VERDICT[screen]).out.splitlines()[0]
            assert norm(" ".join(g.body[:3])).startswith(norm(plain)), (plain, g.body[:3])
    if screen in ("home", "runs", "run", "imports", "compare", "fix-check"):
        focused = g.focused()
        assert len(focused) == 1, g.text()
        row = focused[0]
        assert set(g.mask_of(row, 0, len(g.rows[row].rstrip()))) == {"V"}, g.masks[row]
        # the first row of the table: the row after the table's header
        header = row - 1
        assert g.masks[header].strip() and set(g.masks[header].strip()) == {"D"}, (g.rows[header], g.masks[header])
    if size == (80, 24):
        # TF19-7: opening the screen makes no network call, reads no key, shows no planted key
        assert s.fakes.connects == []
        assert not {k for k in s.fakes.env_read if KEY_NAME.search(k) or k == "*"}
        for value in PLANTED_KEYS.values():
            assert all(value not in grid.text() for grid in s.grids)


# ---------- home (DM5) ----------


def test_tf19_2_home_opens_with_doctor_s_line_and_its_next(work: Path) -> None:
    s = drive(work)
    g = s.last
    doctor = cli(work, ["doctor"]).out.splitlines()
    assert g.body[0] == f"  {doctor[0]}"
    assert g.value_of("next") == doctor[-1].removeprefix("next: ")
    labels = [lab for lab in ("stores", "failures", "next", "pages") if g.line_starting(lab)]
    assert labels == ["stores", "failures", "next", "pages"]
    order = [g.body.index(g.line_starting(lab)) for lab in labels]  # type: ignore[arg-type]
    assert order == sorted(order)
    assert g.value_of("pages") == "trace/index.html"
    assert g.value_of("failures") == "violated, timeout"


@pytest.mark.parametrize(("size", "expected"), [((120, 40), ["kind", "name", "result", "rows", "id", "saved or started"]),
                                                ((80, 24), ["kind", "name", "result", "rows", "saved or started"])])
def test_tf19_2_home_s_table(work: Path, size: tuple[int, int], expected: list[str]) -> None:
    s = drive(work, size=size)
    g = s.last
    header = next(r for r in g.body if r.lstrip().startswith("kind "))
    assert columns(header) == expected, header
    rows = g.body[g.body.index(header) + 1:]
    kinds = [r[2:].split()[0] for r in rows if r.strip() and not r.strip().startswith("↓")]
    from poisson_trace import core

    saved = core.saved_verdicts(work / "store")
    assert kinds[: len(saved)] == [v.kind for v in saved]
    assert kinds[len(saved): len(saved) + 2] == ["run", "run"]


def test_tf19_2_home_rows_are_newest_first_saved_and_runs_together(work: Path) -> None:
    from poisson_trace import core

    s = drive(work, size=(120, 40))
    g = s.last
    saved = core.saved_verdicts(work / "store")
    for v in saved:
        assert any(v.id in r for r in g.body), v.id
    when = [r.rstrip()[-16:] for r in g.body if r[2:].split()[:1] and r[2:].split()[0] in ("where", "compare", "fix-check", "changes", "run")]
    assert when == sorted(when, reverse=True), when


def test_tf19_2_home_empty_state(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    for size in SIZES:
        s = drive(empty, size=size)
        g = s.last
        _bands(g, *size)
        assert g.title() == "home" and g.slot() == "no config"
        assert g.value_of("setup") == "poisson-trace init"
        assert g.value_of("agent") == "poisson-trace init --agent"
        assert g.message == ""
        assert not any("error:" in r for r in g.rows)
        assert set(s.spy.names()) <= {"commands.doctor", "api.load_config", "api.open_store"}
    assert list(empty.iterdir()) == []


def test_tf19_2_home_empty_y_copies_the_command(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    s = drive(empty, ["y"])
    assert s.fakes.copied == ["poisson-trace init"]
    s = drive(empty, ["down", "y"])
    assert s.fakes.copied == ["poisson-trace init --agent"]


# ---------- runs ----------


def test_tf19_2_runs_screen(work: Path) -> None:
    from poisson_trace import core

    s = drive(work, ["r"], size=(120, 40))
    g = s.last
    header = next(r for r in g.body if r.lstrip().startswith("#"))
    assert columns(header) == ["#", "name", "id", "target or tool", "rows", "failed", "traces", "started", "status"]
    listed = json.loads(cli(work, ["runs", "--json"]).out)["runs"]
    rows = g.body[g.body.index(header) + 1: g.body.index(header) + 1 + len(listed)]
    for r, run in zip(rows, listed, strict=True):
        cells = r[2:].split()
        assert cells[0] == str(run["number"])
        assert run["run_id"] in r and "mock-agent" in r
    assert "saved verdicts" in [r.strip() for r in g.body]
    for v in core.saved_verdicts(work / "store"):
        assert any(f"({v.id[:12]})" in r and f"{v.verdict}, saved " in r for r in g.body), v
    assert g.value_of("next") == json.loads(cli(work, ["runs", "--json"]).out)["next"]


def test_tf19_2_runs_s_moves_to_the_next_store_dm9(work: Path) -> None:
    s = drive(work, ["r", "s"], size=(120, 40))
    g = s.last
    assert g.title() == "runs" and g.subject() == "jstore"
    assert g.message == "note: no --event was given, so the failed column is not counted"
    rows = [r for r in g.body if r[2:].split()[:1] in (["1"], ["2"])]
    assert len(rows) == 2 and all(" – " in r or r.rstrip().endswith("–") or "  –  " in r for r in rows), rows
    assert all("junit" in r for r in rows)
    s = drive(work, ["r", "s", "s"], size=(120, 40))
    assert s.last.subject() == "store"


# ---------- run ----------


def test_tf19_2_run_screen(work: Path) -> None:
    s = drive(work, ["r", "enter"], size=(120, 60))
    g = s.last
    for label in ("Read", "Question", "Answer", "Next", "next", "run", "placement", "curve", "page"):
        assert g.line_starting(label), (label, g.text())
    header = next(r for r in g.body if r.lstrip().startswith("kind "))
    cols = columns(header)
    assert cols[:2] == ["kind", "tries"] and cols[-1] == "95% band" and cols[2].startswith("share by step "), cols


# ---------- imports (DM9, DM12) ----------


def test_tf19_2_imports_screen(work: Path) -> None:
    from poisson_trace import core

    s = drive(work, ["i"], size=(120, 60))
    g = s.last
    assert g.subject() == "jstore"
    assert g.message == "note: no --event was given, so the failed column is not counted"
    assert g.line_starting("store") and g.line_starting("failures")
    header = next(r for r in g.body if r.lstrip().startswith("#"))
    assert columns(header) == ["#", "name", "tool", "file", "rows", "failed", "started", "status"]
    table = next(r for r in g.body if r.lstrip().startswith("file "))
    assert columns(table) == ["file", "what it is"]
    focused = g.focused_text()
    assert g.body.index(focused.rstrip()) == g.body.index(table) + 1
    text = "\n".join(g.body)
    assert "humaneval-a.xml" in text and "humaneval-b.xml" in text
    found = [f for f in core.found_results(work, store="jstore") if not f.imported]
    assert found
    for f in found:
        assert any(name_shown(f.path, r) and r.rstrip().endswith(f.said) for r in g.body), f.path
    for f in core.found_results(work, store="jstore"):
        if f.imported:
            assert not any(r.strip().startswith(f.path) for r in g.body), f.path


def test_tf19_2_imports_asking(work: Path) -> None:
    from poisson_trace import core

    listed = [f for f in core.found_results(work, store="jstore") if not f.imported]
    found = [f for f in listed if not f.fill]
    s = drive(work, found_steps(work, listed.index(found[0])), size=(120, 40))
    g = s.last
    assert g.title() == "imports"
    assert g.value_of("file") == found[0].path
    assert g.value_of("what") == found[0].said
    assert found[0].command.replace(" ", "") in "".join(g.body).replace(" ", "")
    assert g.message.endswith("[y/N]"), g.message
    assert g.keys()[:2] == ["y", "n"] and "esc" in g.keys()


# ---------- the pickers ----------


@pytest.mark.parametrize(("key", "limit"), [("c", "max-mde-hr"), ("f", "max-mde")])
def test_tf19_2_pick_two_runs(work: Path, key: str, limit: str) -> None:
    s = drive(work, [key], size=(120, 40))
    g = s.last
    assert g.value_of("before") == "agent before"
    assert g.value_of("after") == "agent after"
    value = g.value_of(limit)
    assert value is not None and value.endswith("from trace.toml [check]"), value
    assert g.value_of("failures") == "violated, timeout, from trace.toml [events]"
    header = next(r for r in g.body if "#" in r and "name" in r)
    assert columns(header) == ["#", "name", "id", "rows", "traces", "started", "status"]
    marks = {r.split()[1] if r.startswith("›") else r.split()[0] for r in g.body if "agent " in r and "#" not in r and ("after " in r[:12] or "before " in r[:12])}
    assert marks <= {"after", "before"}


# ---------- the verdict screens ----------


def test_tf19_2_compare_verdict_screen(work: Path) -> None:
    s = drive(work, ["c", "enter"], size=(120, 60))
    g = s.last
    for label in ("Compared", "Question", "Answer", "Next", "next", "curves", "page"):
        assert g.line_starting(label), (label, g.text())
    assert any(r.strip() == "before you act on this" for r in g.body)
    header = next(r for r in g.body if r.lstrip().startswith("arm "))
    assert columns(header) == ["arm", "placed", "died", "observed", "expected"]


def test_tf19_2_fix_check_verdict_screen(work: Path) -> None:
    s = drive(work, ["f", "enter"], size=(120, 60))
    g = s.last
    for label in ("Compared", "Question", "Answer", "Next", "page"):
        assert g.line_starting(label), (label, g.text())
    assert any(r.strip() == "before you act on this" for r in g.body)


@pytest.mark.parametrize(("steps", "title"), [(["c", "enter", "d"], "could not say"), (["f", "enter", "g"], "changes"),
                                              (["f", "enter", "d"], "could not say"), (["f", "enter", "g", "d"], "could not say")])
def test_tf19_2_screens_reached_from_a_verdict(work: Path, steps: list[str], title: str) -> None:
    s = drive(work, [*steps[:-1], "<snap>", steps[-1], "<snap>", "escape", "<snap>"], size=(120, 40))
    before, opened, back = s.grids
    assert opened.title() == title
    assert (back.title(), back.subject()) == (before.title(), before.subject())


# ---------- help ----------


def test_tf19_2_help_names_every_screen(work: Path) -> None:
    s = drive(work, ["?"], size=(120, 60))
    text = s.last.body_text()
    for screen in ("home", "runs", "run", "imports", "compare", "fix-check", "verdict", "changes", "could not say", "help"):
        assert screen in text, screen


def test_tf19_2_screens_render_core_objects(work: Path) -> None:
    """Each screen's object is the core's (A7): the calls the app made to reach every screen."""
    s = drive(work, ["r", "enter", "escape", "escape", "i", "escape", "c", "enter", "d", "escape", "escape", "escape",
                     "f", "enter", "g"], size=(120, 40))
    names = set(s.spy.names())
    assert {"commands.doctor", "core.saved_verdicts", "api.runs", "core.run_sources", "api.where", "core.found_results",
            "api.compare", "api.fix_check", "api.changes"} <= names, names
    fc = s.spy.called("api.fix_check")[-1]
    assert fc[1].get("inputs") == "all", fc
    cmp = s.spy.called("api.compare")[-1]
    assert cmp[1].get("config") is not None, cmp

