"""TF18-B3, ruled 2026-11-08: ``poisson-trace report DIR --open`` on a bundle that already holds
its page opens that page, without ``--force`` and without rewriting it.

``handover --check DIR`` on a bundle that has its page ends ``next: poisson-trace report DIR
--open`` (A12). As TF18 built it, ``report`` refused the page that was there without ``--force``
(A14), so the command the check printed was refused. Now:

**RO-1** The check's ``next:`` command, run as printed, succeeds: exit 0, the page opened, and
nothing in the bundle written (every byte and every modification time as before).

**RO-2** ``report DIR --open`` on a bundle with its page prints ``ok  <the sentence report
prints>``, ``  opened  DIR/report.html`` and the same ``next:`` line, opens the page's
``file:`` address once, and writes nothing: no file of the bundle or the store changes, in its
bytes or its modification time.

**RO-3** When the page that is there is not the page ``report`` would write now (a page from
another version of Trace, or one edited by hand and re-listed), ``--open`` still opens it as it
is and writes nothing, and says so on stderr in one ``note:`` line that names the command that
writes it again. A page that is the one ``report`` would write gets no note. A page edited and
not re-listed fails the validator, and ``--open`` is refused before anything is opened, as
without it.

**RO-4** Without ``--open`` a page that is there is still refused without ``--force`` (A14):
exit 1, nothing on stdout, nothing opened, nothing written.

**RO-5** ``--force`` still rewrites the page, with or without ``--open``; with ``--open`` it
opens the page it wrote, and prints ``wrote``. A bundle with no page yet is written and opened
by ``--open`` as before.

**RO-6** The API: ``commands.report(folder, open=True)`` behaves the same: the same text, the
same note, nothing written; ``open=False`` refuses; ``force=True`` rewrites.

**RO-7** On a terminal, pretty and ``--plain`` at 80 columns: the same words as piped, ``ok``
green when pretty, ``  opened  DIR/report.html`` whole on its line.

Opening is always faked: in-process the opener is replaced by a recorder, and a subprocess
gets a ``BROWSER`` that writes the address to a file. No test opens a real browser.
"""

from __future__ import annotations

import contextlib
import os
import shlex
import subprocess
import sys
import webbrowser
from collections.abc import Iterator
from pathlib import Path

import pytest
from tf0_support import REPO
from tf9_support import cells, runs_of, strip
from tf9_support import run as pty
from tf13_support import cli, workspace
from tf18_support import SAVES, copy_work, recording_browser, redigest, sha256

FIX = SAVES["fix-check"][1]
SENTENCE = "the fix-check verdict in fb as one page that opens from disk with nothing else present"
NOTE = ("note: fb/report.html is not the page this version of Trace writes for the bundle; "
        "poisson-trace report fb --force writes it again")


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """TF13's workspace with one fix-check bundle, ``fb``, that holds its page."""
    work = workspace(tmp_path_factory.mktemp("report-open"))
    ran = cli(work, [*FIX, "--out", "fb"])
    assert ran.code == 0, ran.text
    ran = cli(work, ["report", "fb"])
    assert ran.code == 0, ran.text
    return work


@pytest.fixture(scope="module")
def bare(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The same workspace with the bundle and no page in it yet."""
    work = workspace(tmp_path_factory.mktemp("report-open-bare"))
    ran = cli(work, [*FIX, "--out", "fb"])
    assert ran.code == 0, ran.text
    return work


@pytest.fixture
def work(base: Path, tmp_path: Path) -> Path:
    return copy_work(base, tmp_path)


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every address the package asks to open, in order; a real browser can never start:
    ``webbrowser.open`` itself fails the test if anything reaches it."""
    from poisson_trace import commands

    log: list[str] = []
    monkeypatch.setattr(commands, "show_page", log.append)

    def no_browser(*a: object, **k: object) -> bool:
        raise AssertionError("a real browser was asked for")

    monkeypatch.setattr(webbrowser, "open", no_browser)
    return log


def stamps(folder: Path) -> dict[str, tuple[str, int]]:
    """Every file under a folder: its digest and its modification time in nanoseconds."""
    return {str(p.relative_to(folder)): (sha256(p.read_bytes()), p.stat().st_mtime_ns)
            for p in sorted(folder.rglob("*")) if p.is_file()}


def address(work: Path) -> str:
    return (work / "fb" / "report.html").resolve().as_uri()


def lines(verb: str) -> str:
    return f"ok  {SENTENCE}\n  {verb}  fb/report.html\nnext: poisson-trace handover --check fb\n"


def subprocess_env(extra: dict[str, str]) -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(REPO / "src"), **extra}


def make_stale(work: Path) -> None:
    """The page made into one ``report`` would not write now, and re-listed: what a page from
    another version of Trace, or a page edited by hand and listed again, looks like."""
    page = work / "fb" / "report.html"
    text = page.read_text(encoding="utf-8")
    assert "</footer>" in text
    page.write_text(text.replace("</footer>", "</footer>\n<p>an older page</p>", 1), encoding="utf-8")
    redigest(work / "fb", "report.html")
    assert cli(work, ["handover", "--check", "fb"]).code == 0


@contextlib.contextmanager
def chdir(path: Path) -> Iterator[None]:
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


# ---------- RO-1: the check's next command runs as printed ----------


def test_ro_1_the_checks_next_command_runs_as_printed(work: Path, tmp_path: Path) -> None:
    checked = cli(work, ["handover", "--check", "fb"])
    assert checked.code == 0, checked.text
    last = checked.out.splitlines()[-1]
    assert last == "next: poisson-trace report fb --open"
    argv = shlex.split(last[len("next: "):])
    assert argv[0] == "poisson-trace"
    env, log = recording_browser(tmp_path)
    before = stamps(work)
    ran = subprocess.run([sys.executable, "-m", "poisson_trace", *argv[1:]], cwd=work, capture_output=True,
                         text=True, env=subprocess_env(env), timeout=600)
    assert ran.returncode == 0, ran.stderr
    assert (ran.stdout, ran.stderr) == (lines("opened"), "")
    assert log.read_text(encoding="utf-8").splitlines() == [address(work)]
    assert stamps(work) == before


# ---------- RO-2: --open opens the page that is there and writes nothing ----------


def test_ro_2_open_opens_the_page_that_is_there(work: Path, opened: list[str]) -> None:
    before = stamps(work)
    ran = cli(work, ["report", "fb", "--open"])
    assert (ran.code, ran.out, ran.err) == (0, lines("opened"), ""), ran.text
    assert opened == [address(work)]
    assert stamps(work) == before


def test_ro_2_the_check_still_says_the_same_after(work: Path, opened: list[str]) -> None:
    first = cli(work, ["handover", "--check", "fb"])
    assert cli(work, ["report", "fb", "--open"]).code == 0
    assert cli(work, ["handover", "--check", "fb"]).out == first.out


# ---------- RO-3: a page report would not write now ----------


def test_ro_3_a_different_page_is_opened_as_it_is_with_a_note(work: Path, opened: list[str]) -> None:
    make_stale(work)
    before = stamps(work)
    ran = cli(work, ["report", "fb", "--open"])
    assert (ran.code, ran.out) == (0, lines("opened")), ran.text
    assert ran.err == NOTE + "\n"
    assert opened == [address(work)]
    assert stamps(work) == before


def test_ro_3_the_command_the_note_names_writes_it_again(work: Path, opened: list[str], bare: Path,
                                                        tmp_path: Path) -> None:
    make_stale(work)
    command = NOTE.split("; ", 1)[1].removesuffix(" writes it again")
    ran = cli(work, shlex.split(command)[1:])
    assert ran.code == 0, ran.text
    fresh = copy_work(bare, tmp_path, name="fresh")
    assert cli(fresh, ["report", "fb"]).code == 0
    assert (work / "fb" / "report.html").read_bytes() == (fresh / "fb" / "report.html").read_bytes()
    again = cli(work, ["report", "fb", "--open"])
    assert (again.code, again.err) == (0, "")
    assert opened == [address(work)]


def test_ro_3_a_page_edited_and_not_relisted_is_refused_first(work: Path, opened: list[str]) -> None:
    with (work / "fb" / "report.html").open("ab") as f:
        f.write(b" ")
    checked = cli(work, ["handover", "--check", "fb"])
    assert checked.code == 4 and checked.out.startswith("not valid  ")
    before = stamps(work)
    ran = cli(work, ["report", "fb", "--open"])
    assert ran.code == 1 and ran.out == ""
    assert ran.err.splitlines()[0] == "error: " + checked.out.splitlines()[0][len("not valid  "):]
    assert opened == []
    assert stamps(work) == before


# ---------- RO-4: without --open, still refused ----------


def test_ro_4_without_open_still_refused(work: Path, opened: list[str]) -> None:
    before = stamps(work)
    ran = cli(work, ["report", "fb"])
    assert ran.code == 1 and ran.out == ""
    assert ran.err.splitlines()[0] == "error: fb/report.html exists; add --force to replace it"
    assert opened == []
    assert stamps(work) == before


# ---------- RO-5: --force still rewrites; a bundle with no page ----------


@pytest.mark.parametrize("extra", [[], ["--open"]])
def test_ro_5_force_still_rewrites(work: Path, opened: list[str], extra: list[str]) -> None:
    make_stale(work)
    stale = (work / "fb" / "report.html").read_bytes()
    ran = cli(work, ["report", "fb", "--force", *extra])
    assert (ran.code, ran.out, ran.err) == (0, lines("wrote"), ""), ran.text
    assert (work / "fb" / "report.html").read_bytes() != stale
    assert cli(work, ["handover", "--check", "fb"]).code == 0
    assert opened == ([address(work)] if extra else [])


def test_ro_5_force_writes_the_file_again(work: Path, opened: list[str]) -> None:
    page = work / "fb" / "report.html"
    os.utime(page, ns=(1, 1))
    ran = cli(work, ["report", "fb", "--force", "--open"])
    assert ran.code == 0, ran.text
    assert page.stat().st_mtime_ns != 1
    assert opened == [address(work)]


def test_ro_5_open_on_a_bundle_with_no_page_writes_and_opens(bare: Path, tmp_path: Path, opened: list[str]) -> None:
    work = copy_work(bare, tmp_path)
    ran = cli(work, ["report", "fb", "--open"])
    assert (ran.code, ran.out, ran.err) == (0, lines("wrote"), ""), ran.text
    assert (work / "fb" / "report.html").is_file()
    assert opened == [address(work)]
    assert cli(work, ["handover", "--check", "fb"]).out.splitlines()[-1] == "next: poisson-trace report fb --open"


# ---------- RO-6: the API ----------


def test_ro_6_api_open_on_a_page_that_is_there(work: Path, opened: list[str]) -> None:
    from poisson_trace import commands

    before = stamps(work)
    with chdir(work):
        r = commands.report("fb", open=True)
    assert r.to_markdown() == lines("opened")
    assert (r.exit_code, r.notes) == (0, ())
    assert opened == [address(work)]
    assert stamps(work) == before


def test_ro_6_api_open_on_a_different_page(work: Path, opened: list[str]) -> None:
    from poisson_trace import commands

    make_stale(work)
    before = stamps(work)
    with chdir(work):
        r = commands.report("fb", open=True)
    assert r.to_markdown() == lines("opened")
    assert r.notes == (NOTE[len("note: "):],)
    assert opened == [address(work)]
    assert stamps(work) == before


def test_ro_6_api_without_open_refuses(work: Path, opened: list[str]) -> None:
    from poisson_trace import api, commands

    before = stamps(work)
    with chdir(work), pytest.raises(api.Refusal) as e:
        commands.report("fb")
    assert e.value.message == "fb/report.html exists; add --force to replace it"
    assert opened == []
    assert stamps(work) == before


def test_ro_6_api_force_rewrites(work: Path, opened: list[str]) -> None:
    from poisson_trace import commands

    make_stale(work)
    stale = (work / "fb" / "report.html").read_bytes()
    with chdir(work):
        r = commands.report("fb", open=True, force=True)
    assert r.to_markdown() == lines("wrote") and r.notes == ()
    assert (work / "fb" / "report.html").read_bytes() != stale
    assert opened == [address(work)]


# ---------- RO-7: on a terminal ----------


def test_ro_7_open_on_a_terminal(base: Path, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    for i, extra in enumerate(([], ["--plain"])):
        work = copy_work(base, tmp_path, name=f"w{i}")
        browser = tmp_path / f"b{i}"
        browser.mkdir()
        env, log = recording_browser(browser)
        before = stamps(work)
        ran = pty(["report", "fb", "--open", *extra], cwd=work, home=home, cols=80, env=env)
        assert ran.code == 0, (ran.out, ran.err)
        shown = [strip(line) for line in ran.out.splitlines() if strip(line).strip()]
        assert "  opened  fb/report.html" in shown
        assert " ".join(strip(ran.out).split()) == " ".join(lines("opened").split())
        if not extra:
            assert ("G", "ok") in runs_of(cells(ran.out)[0])
        assert log.read_text(encoding="utf-8").splitlines() == [address(work)]
        assert stamps(work) == before
