"""TF19-6: keys and exits (spec section 17.2; the look file's terminal-app section; A5, A6, A11 to
A13, DM9).

**TF19-6** The arrows move the focus one row (and no further than the last); Enter opens the
focused row's screen; Esc goes back with the focus where it was; ``/`` filters the rows and Esc
clears the filter; ``s`` moves the runs and imports screens to the config's next store (DM9); the
picker's ``space`` chooses before then after, ``l`` previous and latest. ``q`` exits 0 on every
screen and the app leaves nothing to print (during a question it answers no and the app stays:
held with the name question, TF19-4; ``q`` on a pseudo-terminal: TF19-1).
Ctrl-C exits 130 and the app leaves one line saying what it kept (A12), on every screen and
during work, through the pilot and on a pseudo-terminal. Help lists every key of every screen's
key bar, and each screen's own letters mean one thing.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from tf19_support import (
    KEPT,
    KEPT_NONE,
    NAV_KEYS,
    OWN,
    Grid,
    Quick,
    Resize,
    Step,
    Type,
    after_app,
    app_world,
    cli,
    columns,
    copy_world,
    drive,
    found_steps,
    norm,
    run_pty,
)


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return app_world(tmp_path_factory)


@pytest.fixture
def work(world: Path, tmp_path: Path) -> Path:
    return copy_world(world, tmp_path)


def _tour(world: Path, tmp: Path, size: tuple[int, int], *, help_too: bool) -> dict[str, list[Grid]]:
    """Every screen opened in turn in one run of the app, in a copy of its own, each reached from
    home by its keys and left by as many Esc: what each screen showed when it opened and, with
    ``help_too``, what ``?`` then showed and what Esc came back to. Nothing a tour presses writes
    but the verdict screens' own saves, into the tour's copy."""
    work = copy_world(world, tmp)
    steps: list[object] = []
    counts: dict[str, int] = {}
    for screen, keys in NAV_KEYS.items():
        steps += [*keys, "<snap>"]
        counts[screen] = 1
        if help_too and screen != "help":
            steps += ["?", "<snap>", "escape", "<snap>"]
            counts[screen] = 3
        steps += ["escape"] * len(keys)
    grids = drive(work, steps, size=size).grids
    assert len(grids) >= sum(counts.values()), [g.title() for g in grids]
    out: dict[str, list[Grid]] = {}
    at = 0
    for screen, n in counts.items():
        out[screen] = grids[at:at + n]
        at += n
    return out


@pytest.fixture(scope="module")
def toured(world: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[Grid]]:
    """Each screen at 120 x 40: as it opened, with help over it, and back from help."""
    return _tour(world, tmp_path_factory.mktemp("tf19-keys-tour"), (120, 40), help_too=True)


@pytest.fixture(scope="module")
def toured_wide(world: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[Grid]]:
    """Each screen at 160 x 40, as it opened: wide enough for every word of its key bar."""
    return _tour(world, tmp_path_factory.mktemp("tf19-keys-tour-wide"), (160, 40), help_too=False)


# ---------- moving ----------


def test_tf19_6_arrows_move_the_focus(work: Path) -> None:
    s = drive(work, ["r", "<snap>", "down", "<snap>", "down", "<snap>", "up", "<snap>"], size=(120, 40))
    first, second, still, back = (g.focused_text() for g in s.grids)
    assert "agent after" in first and "agent before" in second
    assert still == second  # no further than the last row
    assert back == first


@pytest.mark.parametrize("key", ["end", "pagedown"])
def test_tf19_6_end_and_page_down(work: Path, key: str) -> None:
    s = drive(work, ["<snap>", key, "<snap>"], size=(120, 40))
    rows = [r for r in s.grids[0].body if r[2:].split()[:1] and r[2:].split()[0] in ("where", "compare", "fix-check", "changes", "run")]
    assert s.last.focused_text().rstrip()[1:] == rows[-1].rstrip()[1:]
    s = drive(work, [key, "home"], size=(120, 40))
    assert s.last.focused_text()[1:].strip() == rows[0][1:].strip()


def test_tf19_6_enter_opens_and_esc_goes_back_with_the_focus(work: Path) -> None:
    s = drive(work, ["r", "down", "<snap>", "enter", "<snap>", "escape"], size=(120, 40))
    before, opened, back = s.grids[0], s.grids[1], s.last
    assert opened.title() == "run" and opened.subject() == "agent before"
    assert back.title() == "runs"
    assert back.focused_text() == before.focused_text()


def test_tf19_6_esc_on_home_stays(work: Path) -> None:
    s = drive(work, ["escape"], size=(120, 40))
    assert s.code is None and s.last.title() == "home"


def test_tf19_6_enter_on_a_home_row(work: Path) -> None:
    from poisson_trace import core

    saved = core.saved_verdicts(work / "store")
    i = next(k for k, v in enumerate(saved) if v.kind == "compare")
    s = drive(work, [*["down"] * i, "enter"], size=(120, 40))
    assert s.last.title() == "compare" and s.last.subject() == "agent before → agent after"
    j = next(k for k, v in enumerate(saved) if v.kind == "where")
    s = drive(work, [*["down"] * j, "enter"], size=(120, 40))
    assert s.last.title() == "run"
    s = drive(work, [*["down"] * len(saved), "enter"], size=(120, 40))
    assert s.last.title() == "run"


def test_tf19_6_filter(work: Path) -> None:
    s = drive(work, ["r", "/", Type("before"), "enter", "<snap>", "escape"], size=(120, 40))
    filtered, cleared = s.grids[0], s.last
    rows = [r for r in filtered.body if "agent " in r and r[1:].split()[:1] in (["1"], ["2"])]
    assert len(rows) == 1 and "agent before" in rows[0]
    assert cleared.title() == "runs"
    assert len([r for r in cleared.body if "agent " in r and r[1:].split()[:1] in (["1"], ["2"])]) == 2


def test_tf19_6_s_moves_through_the_config_s_stores(work: Path) -> None:
    s = drive(work, ["i", "<snap>", "s", "<snap>", "s"], size=(120, 40))
    assert [g.subject() for g in s.grids] == ["jstore", "store", "jstore"]


# ---------- the pickers ----------


def test_tf19_6_space_chooses_before_then_after(work: Path) -> None:
    s = drive(work, ["c", "down", "space", "up", "space"], size=(120, 40))
    g = s.last
    assert (g.value_of("before"), g.value_of("after")) == ("agent before", "agent after")
    s = drive(work, ["c", "space", "down", "space", "enter"], size=(120, 40))
    assert s.last.subject() == "agent after → agent before"
    compare = s.spy.called("api.compare")[-1]
    assert list(compare[0][1:3]) == ["20261104T162928Z-1596", "20261104T162926Z-b4d5"] or \
        list(compare[0][1:3]) == ["agent after", "agent before"], compare


def test_tf19_6_l_picks_previous_and_latest(work: Path) -> None:
    s = drive(work, ["f", "space", "down", "space", "l"], size=(120, 40))
    assert (s.last.value_of("before"), s.last.value_of("after")) == ("agent before", "agent after")


# ---------- quitting ----------


@pytest.mark.parametrize("screen", list(NAV_KEYS))
def test_tf19_6_q_exits_0_on_every_screen(work: Path, screen: str) -> None:
    s = drive(work, [*NAV_KEYS[screen], "q"], size=(120, 40))
    assert s.code == 0, (screen, s.grids[-1].text() if s.grids else "")
    assert s.after == ""


@pytest.mark.parametrize("screen", list(NAV_KEYS))
def test_tf19_6_ctrl_c_exits_130_on_every_screen(work: Path, screen: str) -> None:
    s = drive(work, [*NAV_KEYS[screen], "ctrl+c"], size=(120, 40))
    assert s.code == 130, screen
    saved = [n for n in s.spy.names() if n == "api.save"]
    if saved:
        assert s.after.startswith(KEPT), s.after
        for result in s.spy.results("api.save"):
            if result.saved:
                kind, ident = result.saved.split("/")[-2:]
                assert f"{kind} {ident[:12]}" in s.after, s.after
    else:
        assert s.after == KEPT_NONE


def test_tf19_6_ctrl_c_says_what_was_kept(work: Path) -> None:
    s = drive(work, ["c", "enter", "escape", "escape", "r", "n", Type("kept name"), "enter", "y", "ctrl+c"], size=(120, 40))
    assert s.code == 130
    assert s.after.startswith(KEPT) and "\n" not in s.after.strip()
    ident = next(p.name for p in (work / "store" / ".poisson" / "artifacts" / "compare").iterdir())
    # the workspace saved this compare before: the app saved it again, and says so
    assert f"compare {ident[:12]}" in s.after
    assert "kept name" in s.after


def test_tf19_6_ctrl_c_during_work(work: Path) -> None:
    """Ctrl-C while the comparison is being worked out: exit 130 at once, nothing saved."""
    from contextlib import contextmanager

    from poisson_trace import api

    gate = threading.Event()
    real = api.compare

    def slow(*a: object, **k: object) -> object:
        gate.wait(30)
        return real(*a, **k)

    @contextmanager
    def patched():  # type: ignore[no-untyped-def]
        api.compare = slow
        try:
            yield
        finally:
            gate.set()
            api.compare = real

    import shutil

    shutil.rmtree(work / "store" / ".poisson" / "artifacts", ignore_errors=True)
    from tf0_support import chdir

    # the folder held until the comparison let go has ended, so that it reads what it read
    with chdir(work):
        s = drive(work, ["c", Quick("enter"), "<snap>", Quick("ctrl+c")], size=(120, 40), patch=patched)
        assert any(line.rstrip().endswith("…") for line in s.grids[0].body), s.grids[0].text()
        assert s.code == 130
        assert s.after == KEPT_NONE
        # the comparison, let go once the app has left, ends; nothing is saved by it
        for t in threading.enumerate():
            if t is not threading.current_thread() and not t.name.startswith(("pytest", "execnet")):
                t.join(60)
    assert not (work / "store" / ".poisson" / "artifacts").exists()


# ---------- on a terminal ----------


HOME = "poisson-trace · home"


def test_tf19_6_ctrl_c_on_a_terminal(work: Path, tmp_path: Path) -> None:
    run = run_pty([], home=tmp_path, cwd=work, steps=(Step(b"\x03", until=HOME),))
    assert run.code == 130
    assert after_app(run.out).strip() == KEPT_NONE


def test_tf19_6_ctrl_c_on_a_terminal_after_a_save(work: Path, tmp_path: Path) -> None:
    run = run_pty([], home=tmp_path, cwd=work, timeout=120,
                  steps=(Step(b"c", until=HOME), Step(b"\r", until="pick two runs"), Step(b"\x03", until="saved  compare")))
    assert run.code == 130
    shown = after_app(run.out).strip()
    assert shown.startswith(KEPT) and "compare " in shown, shown


# ---------- help ----------


def _listed(help_rows: list[str], keys: set[str]) -> list[str]:
    names = {"↑↓": "↑ ↓"}
    missing = []
    for key in sorted(keys):
        word = names.get(key, key)
        if not any(row.lstrip().startswith(word + " ") or f" {word} " in f" {row} " for row in help_rows):
            missing.append(key)
    return missing


def test_tf19_6_help_lists_every_key(work: Path) -> None:
    """Every shared key and every screen's own letter (A6's table) is on help."""
    s = drive(work, ["?"], size=(120, 80))
    keys = {k for own in OWN.values() for k in own} | {"↑↓", "enter", "esc", "tab", "/", "y", "m", "?", "q", "ctrl-c", "PgUp"}
    assert _listed(s.last.body, keys) == [], s.last.text()


@pytest.mark.slow
def test_tf19_6_help_lists_every_key_of_every_key_bar(work: Path, toured: dict[str, list[Grid]]) -> None:
    """Every key on every screen's key bar is on help (fast twin: the one above, from A6's table)."""
    s = drive(work, ["?"], size=(120, 80))
    seen: set[str] = set()
    for screen in NAV_KEYS:
        seen.update(toured[screen][0].keys())
    assert _listed(s.last.body, seen) == [], (seen, s.last.text())


def _one_meaning(grids: list[Grid]) -> dict[str, set[str]]:
    words: dict[str, set[str]] = {}
    for g in grids:
        for key, word in g.bar():
            if len(key) == 1 and key.isalpha() and word:
                words.setdefault(key, set()).add(word)
    return {k: v for k, v in words.items() if len(v) > 1}


def test_tf19_6_a_letter_means_one_thing_on_a_few_screens(work: Path) -> None:
    """Fast twin of the next: home, runs, run and compare's verdict share ``c`` and ``f``."""
    screens = ["home", "runs", "run", "verdict compare"]
    assert _one_meaning([drive(work, NAV_KEYS[screen], size=(160, 40)).last for screen in screens]) == {}


@pytest.mark.slow
def test_tf19_6_a_letter_means_one_thing(toured_wide: dict[str, list[Grid]]) -> None:
    """Each letter's word is the same on every key bar that has it (the look file)."""
    assert _one_meaning([toured_wide[screen][0] for screen in NAV_KEYS]) == {}


@pytest.mark.parametrize("screen", ["runs", "verdict compare"])
def test_tf19_6_help_from_a_screen_and_back(work: Path, screen: str) -> None:
    """Fast twin of the next."""
    s = drive(work, [*NAV_KEYS[screen], "<snap>", "?", "<snap>", "escape", "<snap>"], size=(120, 40))
    assert s.grids[1].title() == "help"
    assert s.grids[2].title() == s.grids[0].title() and s.grids[2].focused_text() == s.grids[0].focused_text()


@pytest.mark.slow
def test_tf19_6_help_from_every_screen_and_back(toured: dict[str, list[Grid]]) -> None:
    for screen in NAV_KEYS:
        if screen == "help":
            continue
        opened, with_help, back = toured[screen]
        assert with_help.title() == "help", screen
        assert back.title() == opened.title(), screen


# ---------- the limit asked for, when trace.toml has none ----------

NO_CHECK = """\
version = 1

[store]
path = "store"

[events]
failed = ["violated", "timeout"]
"""


@pytest.mark.parametrize(("key", "limit", "keyword", "verb"), [("c", "max-mde-hr", "max_mde_hr", "compare"),
                                                              ("f", "max-mde", "max_mde", "fix-check")])
def test_tf19_6_h_sets_the_limit_when_trace_toml_has_none(work: Path, key: str, limit: str, keyword: str, verb: str) -> None:
    """The design's ``h``: with no ``[check]`` in ``trace.toml``, ``h`` asks for the limit on the
    message line, the typed value is the picker's limit line, and the verdict is the plain
    command's with that flag."""
    (work / "trace.toml").write_text(NO_CHECK, encoding="utf-8")
    value = "1.5" if verb == "compare" else "0.1"
    s = drive(work, [key, "<snap>", "h", Type(value), "enter", "<snap>", "enter"], size=(120, 40))
    before, chosen, shown = s.grids[0], s.grids[1], s.last
    assert before.value_of(limit) is not None and "h" in before.keys()
    got = chosen.value_of(limit)
    assert got is not None and got.startswith(value), got
    fn = "api.compare" if verb == "compare" else "api.fix_check"
    assert s.spy.called(fn)[-1][1].get(keyword) == float(value), s.spy.called(fn)
    argv = [verb, "agent before", "agent after", f"--{limit}", value, *(["--inputs", "all"] if verb == "fix-check" else [])]
    first = cli(work, argv).out.splitlines()[0]
    assert norm(" ".join(shown.body[:3])).startswith(norm(first)), (first, shown.body[:3])


# ---------- a new size ----------


def test_tf19_6_a_new_size_lays_the_screen_out_again(work: Path) -> None:
    s = drive(work, ["<snap>", Resize(80, 24), "<snap>", Resize(120, 40), "<snap>"], size=(120, 40))
    wide, narrow, back = s.grids
    head = [next(r for r in g.body if r.lstrip().startswith("kind ")) for g in s.grids]
    assert "id" in columns(head[0]) and "id" not in columns(head[1]) and "id" in columns(head[2])
    assert (narrow.width, narrow.height) == (80, 24)
    assert back.focused_text() == wide.focused_text()


# ---------- Ctrl-C during an import ----------


def test_tf19_6_ctrl_c_during_an_import(work: Path) -> None:
    """Ctrl-C while an import the user said yes to is being worked: exit 130 at once, and the
    line names no import (none was kept when Ctrl-C came). What an import let go of does next is
    the process's: on a terminal the app's exit ends it (the next test)."""
    from contextlib import contextmanager

    from poisson_trace import api, core

    found = [f for f in core.found_results(work, store="jstore") if not f.imported]
    i = next(k for k, f in enumerate(found) if not f.fill)
    gate = threading.Event()
    real = api.import_run

    def slow(*a: object, **k: object) -> object:
        gate.wait(30)
        raise api.Refusal("held back by the test")

    @contextmanager
    def patched():  # type: ignore[no-untyped-def]
        api.import_run = slow
        try:
            yield
        finally:
            gate.set()
            api.import_run = real

    s = drive(work, [*found_steps(work, i), Quick("y"), "<snap>", Quick("ctrl+c")], size=(120, 40), patch=patched)
    assert any(line.rstrip().endswith("…") for line in s.grids[0].body), s.grids[0].text()
    assert s.code == 130
    assert s.after == KEPT_NONE


HOLD_IMPORT = """\
import time
from pathlib import Path
from poisson_trace import api
_real = api.import_run
def _held(*a, **k):
    time.sleep(20)
    Path(__file__).with_name("ran-out").write_text("the 20 s hold ran out\\n", encoding="utf-8")
    return _real(*a, **k)
api.import_run = _held
"""


def test_tf19_6_ctrl_c_during_an_import_on_a_terminal(work: Path, tmp_path: Path) -> None:
    """On a terminal, the import held back 20 s before it writes (a ``sitecustomize`` the test
    puts first): Ctrl-C exits 130 at once, the line names no import, and the store is as it was.
    "At once" is held by the hold itself, not by a time bound (S-2): the held import writes
    ``ran-out`` beside it only if its 20 s sleep runs out, so the process did not wait for it if
    there is none; the terminal driver's own deadline is the guard against a hang."""
    from poisson_trace import core

    found = [f for f in core.found_results(work, store="jstore") if not f.imported]
    i = next(k for k, f in enumerate(found) if not f.fill)
    hold = tmp_path / "hold"
    hold.mkdir()
    (hold / "sitecustomize.py").write_text(HOLD_IMPORT, encoding="utf-8")
    before = {p.name for p in (work / "jstore").iterdir()}
    steps = (Step(b"i", until=HOME), *[Step(b"\x1b[B", until="found by init") for _ in range(i)],
             Step(b"\r", until="found by init"), Step(b"y", until="[y/N]"), Step(b"\x03", until="importing", delay=0.5))
    run = run_pty([], home=tmp_path, cwd=work, steps=steps, python_path=(hold,))
    assert run.code == 130
    assert not (hold / "ran-out").exists(), "Ctrl-C waited for the import"
    assert after_app(run.out).strip() == KEPT_NONE
    assert {p.name for p in (work / "jstore").iterdir()} == before


# ---------- a refusal inside the app ----------


def test_tf19_6_a_refusal_is_one_error_line_and_the_app_stays(work: Path) -> None:
    """A compare of the imported store's runs, whose outcomes are not the config's failures: the
    message line is ``error:`` and the sentence the plain command prints; the app stays open and
    ``q`` exits 0."""
    plain = cli(work, ["compare", "ja", "jb", "--store", "imported"])
    assert plain.code == 1, plain.text
    sentence = next(line for line in plain.err.splitlines() if line.startswith("error: "))
    s = drive(work, ["r", "s", "c", "enter", "<snap>", "q"], size=(200, 40))
    g = s.grids[0]
    assert g.message == sentence or norm(sentence) in norm(g.message + " " + " ".join(g.body)), (sentence, g.text())
    assert g.message.startswith("error: ")
    assert s.code == 0
