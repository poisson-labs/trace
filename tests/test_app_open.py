"""TF19-1: how the app opens (``docs/app.md``, How it opens).

**TF19-1** ``poisson-trace`` with no verb, on a pseudo-terminal as a shell runs it: the app opens
when stdin and stdout are terminals, ``CI`` is unset and ``TERM`` is not ``dumb`` (stderr may be a
pipe), and ``q`` leaves it with exit 0 and nothing printed after it. With ``CI`` set (to a value
or empty), ``TERM=dumb``, stdin or stdout not a terminal, or ``--plain``, it does not open and the
bare command prints what it prints without the app: the no-verb refusal.
``--config PATH`` and ``--store PATH`` open it on that config or store, the header's slot saying
which; with no ``trace.toml`` and no store it opens on home's empty state, not a refusal.
``NO_COLOR`` set and not empty keeps the app and draws no colour; set but empty it changes
nothing. A Textual that cannot be imported is one ``error:`` line and exit 1; a window below 80 ×
24 says so in one line.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app_support import (
    NO_TEXTUAL,
    NO_VERB,
    SMALL,
    Step,
    after_app,
    app_world,
    blocker,
    copy_world,
    drive,
    opened_app,
    run_pty,
    strip_escapes,
)


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return app_world(tmp_path_factory)


@pytest.fixture
def work(world: Path, tmp_path: Path) -> Path:
    return copy_world(world, tmp_path)


HOME = "poisson-trace · home"
QUIT = (Step(b"q", until=HOME),)


def _refused(run: object) -> None:
    from app_support import PtyRun

    assert isinstance(run, PtyRun)
    assert run.code == 2, (run.out, run.err)
    assert not opened_app(run.out) and not opened_app(run.err)
    text = strip_escapes(run.err).replace("\r", "")
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    assert lines == [NO_VERB, "  next: poisson-trace --help"], lines


# ---------- it opens ----------


def test_tf19_1_opens_on_a_terminal_and_q_leaves_it(work: Path, tmp_path: Path) -> None:
    run = run_pty([], home=tmp_path, cwd=work, steps=QUIT)
    assert run.code == 0, run.out
    assert opened_app(run.out)
    assert after_app(run.out).strip() == ""


def test_tf19_1_opens_with_stderr_piped(work: Path, tmp_path: Path) -> None:
    run = run_pty([], home=tmp_path, cwd=work, stderr="pipe", steps=QUIT)
    assert run.code == 0, (run.out, run.err)
    assert opened_app(run.out)
    assert run.err == ""


@pytest.mark.parametrize("argv", [["--config", "trace.toml"], ["--store", "store"], ["--config=trace.toml"],
                                  ["--store=store"], ["--store", "store", "--config", "trace.toml"]])
def test_tf19_1_opens_on_a_config_or_a_store(work: Path, tmp_path: Path, argv: list[str]) -> None:
    run = run_pty(argv, home=tmp_path, cwd=work, steps=QUIT)
    assert run.code == 0, run.out
    assert opened_app(run.out)


def test_tf19_1_opens_with_no_config_on_the_empty_state(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    run = run_pty([], home=tmp_path, cwd=empty, steps=(Step(b"q", until=(HOME, "poisson-trace init --agent")),))
    assert run.code == 0, run.out
    assert "error:" not in strip_escapes(run.out)


# ---------- it does not open ----------


@pytest.mark.parametrize("ci", ["1", "true", ""])
def test_tf19_1_ci_set_is_no_app(work: Path, tmp_path: Path, ci: str) -> None:
    _refused(run_pty([], home=tmp_path, cwd=work, CI=ci))


def test_tf19_1_term_dumb_is_no_app(work: Path, tmp_path: Path) -> None:
    _refused(run_pty([], home=tmp_path, cwd=work, TERM="dumb"))


def test_tf19_1_stdin_not_a_terminal_is_no_app(work: Path, tmp_path: Path) -> None:
    _refused(run_pty([], home=tmp_path, cwd=work, stdin="null"))


def test_tf19_1_stdout_not_a_terminal_is_no_app(work: Path, tmp_path: Path) -> None:
    run = run_pty([], home=tmp_path, cwd=work, stdout="pipe", stderr="pipe")
    assert run.code == 2 and run.out == ""
    assert run.err == f"{NO_VERB}\n  next: poisson-trace --help\n"


@pytest.mark.parametrize("argv", [["--plain"], ["--plain", "--config", "trace.toml"], ["--store", "store", "--plain"]])
def test_tf19_1_plain_is_no_app(work: Path, tmp_path: Path, argv: list[str]) -> None:
    _refused(run_pty(argv, home=tmp_path, cwd=work))


@pytest.mark.parametrize("ci", ["1", ""])
def test_tf19_1_ci_with_a_config_is_no_app(work: Path, tmp_path: Path, ci: str) -> None:
    _refused(run_pty(["--config", "trace.toml"], home=tmp_path, cwd=work, CI=ci))


def test_tf19_1_a_verb_on_a_terminal_is_the_verb(work: Path, tmp_path: Path) -> None:
    run = run_pty(["runs", "--plain"], home=tmp_path, cwd=work)
    assert run.code == 0
    assert not opened_app(run.out)
    assert strip_escapes(run.out).lstrip().startswith("ok  2 runs in store")


# ---------- the header's slot ----------


@pytest.mark.parametrize(("config", "store", "slot"), [
    ("trace.toml", None, "trace.toml"),
    ("./trace.toml", None, "./trace.toml"),
    ("conf/trace.toml", None, "conf/trace.toml"),
    (None, "store", "store"),
    (None, "jstore", "jstore"),
    ("trace.toml", "store", "store"),
])
def test_tf19_1_the_header_says_what_it_opened_on(work: Path, config: str | None, store: str | None, slot: str) -> None:
    s = drive(work, config=config, store=store)
    g = s.last
    assert g.title() == "home"
    assert g.slot() == slot
    assert g.header.startswith("poisson-trace · home")


# ---------- colour ----------


def _roles(s: object) -> set[str]:
    from app_support import Session

    assert isinstance(s, Session)
    return {c for g in s.grids for m in g.masks for c in m}


def test_tf19_1_colour_by_default(work: Path) -> None:
    s = drive(work)
    assert "G" in _roles(s), s.last.text()  # home's ok
    assert s.last.off_palette == set()


def test_tf19_1_no_color_keeps_the_app_and_drops_the_colours(work: Path) -> None:
    s = drive(work, ["r", "<snap>", "escape"], env={"NO_COLOR": "1"})
    roles = _roles(s)
    assert not roles & {"G", "Y", "R"}, roles
    assert {"V", "B", "D"} <= roles
    assert s.last.title() == "home"


def test_tf19_1_no_color_empty_changes_nothing(work: Path) -> None:
    s = drive(work, env={"NO_COLOR": ""})
    assert "G" in _roles(s)


# ---------- it cannot open ----------


def test_tf19_1_no_textual(work: Path, tmp_path: Path) -> None:
    blocked = blocker(tmp_path / "blocked", "textual")
    run = run_pty([], home=tmp_path, cwd=work, stderr="pipe", python_path=(blocked,))
    assert run.code == 1, (run.out, run.err)
    assert strip_escapes(run.out).strip() == ""
    assert run.err == f"{NO_TEXTUAL}\n  next: poisson-trace --help\n"


@pytest.mark.parametrize("size", [(79, 24), (80, 23), (60, 15)])
def test_tf19_1_a_small_window(work: Path, size: tuple[int, int]) -> None:
    s = drive(work, size=size)
    lines = [r.rstrip() for r in s.last.rows if r.strip()]
    assert len(lines) == 2, lines
    m = SMALL.match(lines[0])
    assert m and (int(m.group(1)), int(m.group(2))) == size, lines
    assert lines[1] == "q quit"
    s = drive(work, ["q"], size=size)
    assert s.code == 0
