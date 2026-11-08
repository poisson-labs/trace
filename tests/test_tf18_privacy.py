"""TF18-19: what no page holds (spec section 17.3 item 9): an absolute path, a platform string, a
key, or a row's content.

The pages workspace, plus a table store whose rows carry a prompt and a response beside their
case and outcome, with two verdicts saved on it; built with a key in the environment (an
``OPENAI_API_KEY``, an upload token) and in a file beside the config; every page of every store
and the HTML report of a bundle of each kind are read whole. The control: the content and the
keys are in what was read in, and the absolute paths are in what ``ui`` printed (one store's
pages are built from its absolute path, as a user may type it).
"""

from __future__ import annotations

import platform
import re
import sys
from pathlib import Path

import pytest
from tf0_support import chdir, trace_import
from tf13_support import cli
from tf18_support import SAVES, build_work, pages_of, ui

KEY = "sk-tf18-a-planted-key-0123456789abcdef"
TOKEN = "tf18-planted-upload-token-fedcba9876543210"
CONTENT = {f"c{i}": (f"Please summarise the planted prompt number {i} about quarterly invoices for Ms Example",
                     f"The planted response number {i} says the invoices were paid on the ninth of the month")
           for i in range(8)}


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    mp = pytest.MonkeyPatch()
    mp.setenv("OPENAI_API_KEY", KEY)
    mp.setenv("POISSON_TRACE_UPLOAD_TOKEN", TOKEN)
    try:
        work = build_work(tmp_path_factory.mktemp("tf18-privacy"))
        (work / "conf" / ".env").write_text(f"OPENAI_API_KEY={KEY}\n", encoding="utf-8")
        with chdir(work):
            for run, fail in (("cold", {0, 1, 2}), ("cnew", {0})):
                rows = "".join(f'{c},{"failed" if i in fail else "passed"},"{p}","{r}"\n'
                               for i, (c, (p, r)) in enumerate(CONTENT.items()))
                Path(f"{run}.csv").write_text("case,outcome,prompt,response\n" + rows, encoding="utf-8")
                made = trace_import(["table", f"{run}.csv", "--store", "content", "--run", run, "--case-column", "case",
                                     "--outcome-column", "outcome", "--failed", "failed"])
                assert made.code == 0, made.text
        for argv in (["fix-check", "cold", "cnew", "--store", "content", "--event", "missed", "--inputs", "all", "--max-mde", "0.5"],
                     ["changes", "cold", "cnew", "--store", "content", "--event", "missed"]):
            ran = cli(work, [*argv, "--save"])
            assert ran.code == 0, ran.text
            assert cli(work, [*argv, "--out", f"b-content-{argv[0]}"]).code == 0
        for label in ("where after", "compare", "fix-check", "changes"):
            assert cli(work, [*SAVES[label][1], "--out", f"b-{label.replace(' ', '-')}"]).code == 0
        for folder in sorted(p.name for p in work.iterdir() if p.name.startswith("b-")):
            assert cli(work, ["report", folder]).code == 0, folder
        # the content store's pages built from its absolute path, as a user may type it
        printed = ui(work, "--config", "conf/trace.toml").out + ui(work, "--store", str((work / "content").resolve())).out
        (work / "printed.txt").write_text(printed, encoding="utf-8")
    finally:
        mp.undo()
    return work


def everything(work: Path) -> dict[str, str]:
    out = {}
    for store in ("store", "tables", "content"):
        for p in pages_of(work / store).rglob("*"):
            if p.is_file():
                out[str(p.relative_to(work))] = p.read_text(encoding="utf-8")
    for p in work.glob("b-*/report.html"):
        out[str(p.relative_to(work))] = p.read_text(encoding="utf-8")
    return out


def test_tf18_19_the_control(built: Path) -> None:
    pages = everything(built)
    assert len([k for k in pages if k.endswith("report.html")]) == 6
    assert any(k.startswith("content/") for k in pages)
    assert str(built.resolve()) in (built / "printed.txt").read_text(encoding="utf-8")
    raw = (built / "cold.csv").read_text(encoding="utf-8")
    assert all(p in raw and r in raw for p, r in CONTENT.values())
    assert KEY in (built / "conf" / ".env").read_text(encoding="utf-8")


def test_tf18_19_no_absolute_path(built: Path) -> None:
    roots = {str(built), str(built.resolve()), str(Path.home()), str(Path(sys.executable).parent), sys.prefix,
             str(Path(__file__).resolve().parents[1])}
    for name, text in everything(built).items():
        for root in roots:
            assert root not in text, (name, root)
        assert "file://" not in text, name
        assert not re.search(r"(?<![\w.])/(?:Users|home|private|tmp|var|opt)/", text), name
        assert not re.search(r"\b[A-Za-z]:\\\\", text), name


def test_tf18_19_no_platform_string(built: Path) -> None:
    words = {platform.platform(), platform.node(), sys.version, platform.python_implementation() + " " + platform.python_version()}
    for name, text in everything(built).items():
        for word in words:
            assert word not in text, (name, word)
        assert not re.search(rf"\b{re.escape(sys.platform)}\b", text, flags=re.I), name


def test_tf18_19_no_key(built: Path) -> None:
    for name, text in everything(built).items():
        assert KEY not in text and TOKEN not in text, name
        assert not re.search(r"\bsk-[A-Za-z0-9_-]{8,}", text), name


def test_tf18_19_no_rows_content(built: Path) -> None:
    pages = everything(built)
    for name, text in pages.items():
        for prompt, response in CONTENT.values():
            for piece in (prompt, response, prompt[:40], response[-40:]):
                assert piece not in text, (name, piece)
        assert "quarterly invoices" not in text and "Ms Example" not in text, name
