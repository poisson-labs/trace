"""TF18-13: ``poisson-trace ui`` (Prove 0.1.3's own ``ui`` for the form).

- ``ui`` builds the pages of the store it reads (``--store``, or the config's own store) and,
  when a config is read, of every other store it names, so the links between them hold;
  it prints one line, ``ok  pages at file:///…/.poisson/ui/trace/index.html``, the store
  it read, and no ``next:`` line, as Prove's ``ui`` prints; stderr is empty.
- ``--json``: ``schema`` ``poisson-trace.ui/1``, ``verdict``, ``sentence``, ``location`` (the same
  address), ``next`` null; nothing else.
- ``--open`` opens that address in the browser (``webbrowser``, which a ``BROWSER`` variable
  points at a recorder here), and prints the same; without it nothing is opened.
- A store it cannot read is the refusal ``runs`` gives for the same store options, word for
  word and with its exit code, a command under it naming ``ui`` where ``runs``'s names ``runs``; a store whose pages cannot be written is one ``error:`` line,
  exit 1, nothing on stdout.
- Building twice gives the same bytes. ``python -m poisson_trace ui`` is the same command.
- Its help: a description, every option with its default, an example.

**TF18-23** On a terminal (rule 16): pretty and ``--plain`` at 80 and 160 columns, the exit code
and the verdict line's words are plain's, ``ok`` is drawn green when pretty, and the address
stands whole on one line, never broken.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from look_support import REPO
from api_support import cli
from pages_support import build_work, copy_work, pages_of, recording_browser, snapshot, ui, ui_root
from terminal_support import cells, runs_of, strip
from terminal_support import run as pty


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_work(tmp_path_factory.mktemp("tf18-ui"))


@pytest.fixture
def work(base: Path, tmp_path: Path) -> Path:
    return copy_work(base, tmp_path)


def uri(store: Path) -> str:
    return (pages_of(store) / "index.html").resolve().as_uri()


def module(work: Path, argv: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    full = {**os.environ, "PYTHONPATH": str(REPO / "src"), **(env or {})}
    full.pop("NO_COLOR", None)
    return subprocess.run([sys.executable, "-m", "poisson_trace", *argv], cwd=work, capture_output=True, text=True,
                          env=full, timeout=600)


@pytest.mark.parametrize("argv,store", [(["--store", "store"], "store"), (["--config", "conf/trace.toml"], "store"),
                                        (["--store", "tables"], "tables"), (["--config", "conf/trace.toml", "--store", "tables"], "tables")])
def test_tf18_13_one_line_with_the_address(work: Path, argv: list[str], store: str) -> None:
    ran = ui(work, *argv)
    assert (ran.code, ran.out, ran.err) == (0, f"ok  pages at {uri(work / store)}\n", "")
    assert (pages_of(work / store) / "index.html").is_file()


def test_tf18_13_a_store_alone_builds_that_store_alone(work: Path) -> None:
    assert ui(work, "--store", "store").code == 0
    assert not ui_root(work / "tables").exists()


def test_tf18_13_json(work: Path) -> None:
    ran = ui(work, "--store", "store", "--json")
    assert ran.code == 0 and ran.err == ""
    doc = json.loads(ran.out)
    assert list(doc) == ["schema", "verdict", "sentence", "location", "next"]
    assert doc == {"schema": "poisson-trace.ui/1", "verdict": "ok", "sentence": f"pages at {uri(work / 'store')}",
                   "location": uri(work / "store"), "next": None}
    assert ran.out == json.dumps(doc, indent=2) + "\n"


def test_tf18_13_open_opens_the_address(work: Path, tmp_path: Path) -> None:
    env, log = recording_browser(tmp_path)
    ran = module(work, ["ui", "--store", "store", "--open"], env)
    assert (ran.returncode, ran.stdout) == (0, f"ok  pages at {uri(work / 'store')}\n"), ran.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [uri(work / "store")]


def test_tf18_13_without_open_nothing_is_opened(work: Path, tmp_path: Path) -> None:
    env, log = recording_browser(tmp_path)
    ran = module(work, ["ui", "--store", "store"], env)
    assert ran.returncode == 0, ran.stderr
    assert not log.exists()
    # ``python -m poisson_trace ui`` is the same command: it prints what ``ui`` prints
    assert (ran.returncode, ran.stdout, ran.stderr) == (0, f"ok  pages at {uri(work / 'store')}\n", "")


@pytest.mark.parametrize("store_argv", [["--store", "no-such-store"], ["--store", "grades.csv"], ["--store", "conf"],
                                        [], ["--config", "conf/none.toml"], ["--config", "conf/trace.toml", "--store", "nameless"]])
def test_tf18_13_a_store_it_cannot_read_is_the_refusal_runs_gives(work: Path, store_argv: list[str]) -> None:
    got = ui(work, *store_argv)
    want = cli(work, ["runs", *store_argv])
    assert want.code != 0
    assert (got.code, got.out, got.err) == (want.code, "", want.err.replace("poisson-trace runs", "poisson-trace ui"))


def test_tf18_13_pages_that_cannot_be_written(work: Path) -> None:
    (work / "store" / ".poisson" / "ui").write_text("not a folder\n", encoding="utf-8")
    ran = ui(work, "--store", "store")
    assert ran.code == 1 and ran.out == ""
    lines = ran.err.splitlines()
    assert len([line for line in lines if line.startswith("error: ")]) == 1 and lines[0].startswith("error: ")
    assert (work / "store" / ".poisson" / "ui").read_text(encoding="utf-8") == "not a folder\n"


def test_tf18_13_building_twice_gives_the_same_bytes(work: Path) -> None:
    assert ui(work, "--config", "conf/trace.toml").code == 0
    first = {s: snapshot(ui_root(work / s)) for s in ("store", "tables")}
    assert ui(work, "--config", "conf/trace.toml").code == 0
    assert {s: snapshot(ui_root(work / s)) for s in ("store", "tables")} == first


def test_tf18_13_help(work: Path) -> None:
    ran = cli(work, ["ui", "--help"])
    assert ran.code == 0 and ran.err == ""
    text = ran.out
    for flag in ("--open", "--store", "--config", "--json"):
        assert flag in text, flag
    assert "examples:" in text and "  poisson-trace ui" in text
    assert "ui" in cli(work, ["--help"]).out.split("verbs:")[1].split()


@pytest.mark.parametrize("cols", [80, 160])
def test_tf18_23_on_a_terminal(work: Path, tmp_path: Path, cols: int) -> None:
    home = tmp_path / "home"
    home.mkdir()
    address = uri(work / "store")
    for extra in ([], ["--plain"]):
        ran = pty(["ui", "--store", "store", *extra], cwd=work, home=home, cols=cols)
        assert ran.code == 0, (extra, ran.out, ran.err)
        lines = [strip(line) for line in ran.out.splitlines() if strip(line).strip()]
        assert lines[0].startswith("ok  pages at"), lines
        assert any(address in line for line in lines), (address, lines)
        assert " ".join(" ".join(lines).split()) == f"ok pages at {address}"
        if not extra:
            first = cells(ran.out)[0]
            assert ("G", "ok") in runs_of(first), runs_of(first)
        else:
            assert strip(ran.out) == ran.out
