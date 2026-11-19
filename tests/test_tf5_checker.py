"""TF5-80 to TF5-88: ``tools/docs_check.py``, the docs checker the clean-install job runs.
Held by what it does, run as a command, never by how it is written.

    python tools/docs_check.py [--summary FILE] [PAGE ...]

With no page it checks the README, the contributing page and every page under ``docs/`` but
the two standards, of the checkout it sits in. It runs each page's commands with whatever
``poisson-trace`` is first on ``PATH`` (in CI, the wheel just installed), in a scratch folder
of the page's own laid out as a clone, what the page names of the checkout's fixtures and
examples copied in, with a home folder of its own. It holds every page to the marks ``tf5_support`` writes out, by the same rules as
TF5-11 to TF5-16.

- TF5-80: it is in the repository and not in the wheel (TF5-96 holds what the wheel is built
  from); it needs the standard library alone
  (nothing of the tests, nothing of the package), so it runs in an environment that holds
  only the installed wheel.
- TF5-81: a page whose blocks hold passes: exit 0, and the last line it prints is ``ok``, two
  spaces, and how many blocks held on how many pages and how many were skipped.
- TF5-82: a block that does not hold fails the run: exit 1, with a line that opens
  ``PAGE:LINE:`` (the block's first line) for each: an output that differs by one character,
  an excerpt whose lines are not a run of the output's, an exit code that is not the mark's.
- TF5-83: an unmarked block, a comment that means to be a mark and is not one, an output
  under no command and a skipped ``poisson-trace`` command that could run each fail the run,
  by the page and the line.
- TF5-84: ``varies``: ``…`` stands for a path, a time, an id or a version and for nothing
  else; a block marked ``varies`` with no ``…`` fails.
- TF5-85: ``tty``: the block's stdin is a terminal and its answers are typed, a line each;
  a block not marked so has no terminal.
- TF5-86: ``pull``: a block marked so reaches the three services' answers from the committed
  captures, with no network; the same command not marked so fails.
- TF5-87: every skipped block is listed with its page, its line and its reason, on stdout and
  in the file ``--summary`` names (appended, as a job summary is); the checkout is left as it
  was, and the page's commands ran in a folder that is not the checkout, with a home that is
  not the user's.
- TF5-88: the whole of the repository's pages pass it, with every connection to an address
  that is not this machine's refused (slow; its twin runs two short pages the same way).
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tf5_support import CHECKER, REPO, check, rel, recipe, run_pages

BIN = Path(sys.executable).parent


def _env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """The environment a checker run gets here: this interpreter's ``poisson-trace`` first on
    PATH, no key, and the caller's home (which the checker must not use)."""
    env = dict(os.environ, PATH=f"{BIN}{os.pathsep}{os.environ.get('PATH', '')}")
    for name in ("LANGSMITH_API_KEY", "BRAINTRUST_API_KEY", "WANDB_API_KEY", "CI", "VIRTUAL_ENV"):
        env.pop(name, None)
    env.update(extra or {})
    return env


def _page(tmp: Path, body: str, name: str = "page.md") -> Path:
    path = tmp / name
    path.write_text("# A page\n\n" + body, encoding="utf-8")
    return path


def _block(mark: str, body: str) -> str:
    return f"<!-- {mark} -->\n```\n{body}\n```\n\n"


def _ran(tmp: Path, body: str, *args: str) -> subprocess.CompletedProcess[str]:
    return check([*args, _page(tmp, body)], cwd=tmp, env=_env())


def _lines(proc: subprocess.CompletedProcess[str]) -> list[str]:
    return [line for line in (proc.stdout + proc.stderr).splitlines() if line.strip()]


HOLDS = _block("command", "echo one; echo two >&2; echo three") + _block("output exit=0", "one\nthree\ntwo")


# ---------- TF5-80 ----------


def test_tf5_80_the_checker_is_in_the_repository_and_needs_the_standard_library_alone() -> None:
    assert CHECKER.is_file(), "tools/docs_check.py"
    tree = ast.parse(CHECKER.read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {(node.module or "").split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level == 0}
    assert imported <= set(sys.stdlib_module_names), sorted(imported - set(sys.stdlib_module_names))
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level], "no relative import"


# ---------- TF5-81 ----------


def test_tf5_81_a_page_that_holds_passes(tmp_path: Path) -> None:
    proc = _ran(tmp_path, HOLDS + _block("command", "poisson-trace --version") + _block("excerpt exit=0 varies", "poisson-trace … (poisson-prove …, Python …)"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    last = proc.stdout.strip().splitlines()[-1]
    assert last.startswith("ok  ") and "2 blocks" in last and "1 page" in last and "0 skipped" in last, last


# ---------- TF5-82 ----------


@pytest.mark.parametrize("shown", [
    _block("output exit=0", "one\nthree\ntwO"),
    _block("output exit=0", "one\nthree"),
    _block("excerpt exit=0", "one\ntwo"),
    _block("output exit=1", "one\nthree\ntwo"),
    _block("excerpt exit=0", "on"),
], ids=["one character", "a line short", "not a run of lines", "the exit code", "part of a line"])
def test_tf5_82_a_block_that_does_not_hold_fails_the_run(tmp_path: Path, shown: str) -> None:
    proc = _ran(tmp_path, _block("command", "echo one; echo two >&2; echo three") + shown)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert any(line.startswith("page.md:10:") for line in _lines(proc)), _lines(proc)
    assert not proc.stdout.strip().splitlines()[-1:] or not proc.stdout.strip().splitlines()[-1].startswith("ok  ")


def test_tf5_82_every_failing_block_is_named_and_the_rest_still_run(tmp_path: Path) -> None:
    body = (_block("command", "echo a") + _block("output exit=0", "b") + _block("command", "echo c") + _block("output exit=0", "c")
            + _block("command", "echo d") + _block("output exit=0", "e"))
    proc = _ran(tmp_path, body)
    named = [line.split(":")[1] for line in _lines(proc) if line.startswith("page.md:")]
    assert proc.returncode == 1 and named == ["10", "30"], _lines(proc)


# ---------- TF5-83 ----------


@pytest.mark.parametrize(("body", "line"), [
    ("```\npoisson-trace --version\n```\n", 4),
    ("```toml\npoisson-trace --version\n```\n", 4),
    ("<!-- docs-check: run -->\n```\necho a\n```\n", 3),
    ("<!-- command exit=0 -->\n```\necho a\n```\n", 3),
    (_block("output exit=0", "a"), 5),
    (_block("skip reason=\"shown\"", "echo a") + _block("output exit=0", "a"), 10),
    (_block("command", "echo a") + _block("output exit=0", "a") + _block("skip reason=\"shown, not run\"", "echo b") + _block("output exit=0", "a"), 20),
    (_block("skip reason=\"it would take a while\"", "poisson-trace --version"), 5),
    ("<!-- command -->\n\nNo block.\n", 3),
], ids=["unmarked", "a command under a data fence", "another tool's mark", "not a mark", "an output under no command",
        "an output under a skipped block", "an output under a skipped block, after a command", "a command that could run, skipped",
        "a mark with no block"])
def test_tf5_83_a_page_that_breaks_the_marks_fails(tmp_path: Path, body: str, line: int) -> None:
    proc = _ran(tmp_path, body)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert any(text.startswith(f"page.md:{line}:") for text in _lines(proc)), (line, _lines(proc))


def test_tf5_83_a_block_whose_fence_says_what_it_holds_needs_no_mark(tmp_path: Path) -> None:
    proc = _ran(tmp_path, HOLDS + "```toml\n[store]\npath = \"prove-runs\"\n```\n\n```python\nfrom poisson_trace import api\n```\n")
    assert proc.returncode == 0, proc.stdout + proc.stderr


# ---------- TF5-84 ----------


def test_tf5_84_varies_stands_for_a_path_a_time_an_id_or_a_version(tmp_path: Path) -> None:
    command = _block("command", "echo \"wrote $PWD/out.json at 2026-11-12T18:50:01Z, id 3fa9c1d2e4b5a697, in 0.4 s\"")
    good = _ran(tmp_path, command + _block("output exit=0 varies", "wrote … at …, id …, in …"))
    assert good.returncode == 0, good.stdout + good.stderr


@pytest.mark.parametrize("shown", ["no … difference", "… significant difference", "no significant difference", "…"],
                         ids=["a word", "two words", "nothing varies", "a line that is … alone"])
def test_tf5_84_and_for_nothing_else(tmp_path: Path, shown: str) -> None:
    proc = _ran(tmp_path, _block("command", "echo 'no significant difference'") + _block("output exit=0 varies", shown))
    assert proc.returncode == 1 and any(line.startswith("page.md:10:") for line in _lines(proc)), _lines(proc)


def test_tf5_84_every_ellipsis_of_a_line_is_held(tmp_path: Path) -> None:
    """Two on one line, one standing for a path and one for a word: the line does not hold."""
    command = _block("command", "echo \"wrote $PWD/out.json, no significant difference\"")
    proc = _ran(tmp_path, command + _block("output exit=0 varies", "wrote …, no … difference"))
    assert proc.returncode == 1 and any(line.startswith("page.md:10:") for line in _lines(proc)), _lines(proc)
    proc = _ran(tmp_path, command + _block("output exit=0 varies", "wrote …, no significant difference"))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_tf5_84_without_the_mark_an_ellipsis_is_itself(tmp_path: Path) -> None:
    proc = _ran(tmp_path, _block("command", "echo 'Looking for results under /tmp/x …'") + _block("output exit=0", "Looking for results under … …"))
    assert proc.returncode == 1
    proc = _ran(tmp_path, _block("command", "echo 'Looking …'") + _block("output exit=0", "Looking …"))
    assert proc.returncode == 0, proc.stdout + proc.stderr


# ---------- TF5-85 ----------


def test_tf5_85_tty_types_the_answers_into_a_terminal(tmp_path: Path) -> None:
    body = (_block("command", "test -t 0 && echo terminal || echo none") + _block("output exit=0", "none")
            + _block('command tty answers="first|second answer"', "test -t 0 && echo terminal; test -t 1 || echo piped; read a; read b; echo \"$a, $b\"")
            + _block("output exit=0", "terminal\npiped\nfirst, second answer"))
    proc = _ran(tmp_path, body)
    assert proc.returncode == 0, proc.stdout + proc.stderr


# ---------- TF5-86 ----------

_PULL = ("poisson-trace import {tool} {address} --store store-{tool} --run old {flags}")
_ASKED = {
    "langsmith": ("langsmith:trace-fixture-baseline-bbb64b8e", "--case-from example --outcome-from status"),
    "braintrust": ("braintrust:trace-fixture/slice-baseline", "--case-from record --outcome-from error"),
    "weave": ("weave:example-entity/trace-fixture/trace-fixture-slice-baseline", "--case-from example --outcome-from status"),
}


@pytest.mark.parametrize("tool", list(_ASKED))
def test_tf5_86_pull_is_answered_from_the_captures(tmp_path: Path, tool: str) -> None:
    address, flags = _ASKED[tool]
    command = _PULL.format(tool=tool, address=address, flags=flags)
    body = (_block("command pull", command + f" > out.txt; echo $?; ls store-{tool}/.poisson/raw/{tool}/old")
            + _block("output exit=0", "0\npull.json\nraw.jsonl"))
    proc = _ran(tmp_path, body)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "planted" not in (proc.stdout + proc.stderr).lower()


def test_tf5_86_the_same_command_not_marked_pull_fails(tmp_path: Path) -> None:
    address, flags = _ASKED["weave"]
    command = _PULL.format(tool="weave", address=address, flags=flags)
    proc = _ran(tmp_path, _block("command", command + " > out.txt 2>&1; echo $?") + _block("output exit=0", "0"))
    assert proc.returncode == 1, proc.stdout + proc.stderr


# ---------- TF5-87 ----------


def test_tf5_87_every_skip_is_listed_and_nothing_is_left_behind(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    before = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True).stdout
    body = (_block('skip reason="installs from the package index"', "pip install poisson-trace")
            + _block("command", "test -f tests/fixtures/SHA256SUMS && echo fixtures; test \"$HOME\" != \"" + str(home) + "\" && echo a home of its own; "
                                "test \"$PWD\" != \"" + str(REPO) + "\" && echo a folder of its own; touch made-here")
            + _block("output exit=0", "fixtures\na home of its own\na folder of its own")
            + _block('skip reason="yours to fill in"', "poisson-trace import TOOL FILE --store STORE --run NAME"))
    summary = tmp_path / "summary.md"
    summary.write_text("earlier\n", encoding="utf-8")
    assert not (REPO / "made-here").exists()
    proc = check(["--summary", summary, _page(tmp_path, body)], cwd=tmp_path, env=_env({"HOME": str(home)}))
    in_the_checkout = (REPO / "made-here").exists()
    (REPO / "made-here").unlink(missing_ok=True)
    assert not in_the_checkout, "the page's command ran in the checkout"
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "2 skipped" in proc.stdout.strip().splitlines()[-1]
    written = summary.read_text(encoding="utf-8")
    assert written.startswith("earlier\n")
    for where in (proc.stdout, written):
        assert "page.md:5" in where and "installs from the package index" in where, where
        assert "page.md:22" in where and "yours to fill in" in where, where
    assert not (tmp_path / "made-here").exists() and list(home.iterdir()) == []
    assert subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True).stdout == before


# ---------- TF5-88 ----------


def _guard(tmp: Path) -> tuple[Path, Path]:
    """A folder to put on PYTHONPATH that refuses, and writes down, every connection to an
    address that is not this machine's, in every Python started under it."""
    folder, log = tmp / "guard", tmp / "refused.log"
    folder.mkdir()
    (folder / "sitecustomize.py").write_text(
        "import os, socket\n"
        "_connect = socket.socket.connect\n"
        "def _guarded(self, address):\n"
        "    host = address[0] if isinstance(address, tuple) else address\n"
        "    if isinstance(host, str) and (host in ('localhost', '::1') or host.startswith('127.') or host.startswith('/')):\n"
        "        return _connect(self, address)\n"
        f"    open({str(log)!r}, 'a').write(repr(address) + '\\n')\n"
        "    raise OSError('the docs check reached for the network: ' + repr(address))\n"
        "socket.socket.connect = _guarded\n", encoding="utf-8")
    return folder, log


def _whole(tmp: Path, pages: list[Path]) -> None:
    folder, log = _guard(tmp)
    summary = tmp / "summary.md"
    empty = tmp / "empty"
    empty.mkdir()
    proc = check(["--summary", summary, *pages], cwd=empty, env=_env({"PYTHONPATH": str(folder), "HOME": str(tmp / "home")}), timeout=1800)
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-6000:]
    assert not log.exists(), log.read_text(encoding="utf-8")
    assert proc.stdout.strip().splitlines()[-1].startswith("ok  ")
    assert list(empty.iterdir()) == [], "nothing is written where it was started"


@pytest.mark.slow
def test_tf5_88_every_page_of_the_repository_passes_with_no_network(tmp_path: Path) -> None:
    (tmp_path / "home").mkdir()
    _whole(tmp_path, [])
    listed = (tmp_path / "summary.md").read_text(encoding="utf-8")
    for page in run_pages():
        from tf5_support import parse, read

        for block in parse(read(page))[0]:
            if block.kind == "skip":
                assert f"{rel(page)}:{block.line}" in listed, f"{rel(page)}:{block.line} is skipped and not listed"


def test_tf5_88_two_short_pages_pass_the_same_way(tmp_path: Path) -> None:
    (tmp_path / "home").mkdir()
    _whole(tmp_path, [recipe("from-junit.md"), recipe("from-weave.md")])
