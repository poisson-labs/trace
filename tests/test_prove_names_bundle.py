"""IG-10 to IG-13: a Prove that is installed without its page bundle is named as that, by every
command that builds a page, and nothing is written.

Trace builds its pages with two files Prove ships, ``poisson_prove/_ui_bundle/style.css`` and
``ui.js``. Unchecked, their absence makes ``ui`` say ``cannot write the pages into STORE: No such
file or directory`` and leave an empty ``ui`` folder in the store, and ``report`` say it cannot
write ``report.html``: both blame the place written to, which is not at fault. The rule these
tests hold:

- IG-10: ``ui`` refuses, exit 1, nothing on stdout, in one ``error:`` line that names the Prove
  found and what it lacks, in the words ``doctor`` uses for a Prove that lacks a name: ``poisson-prove
  0.4.0 is installed and has no poisson_prove/_ui_bundle, which Trace builds its pages with``.
  One file missing is named as the file. The store is left exactly as it was.
- IG-11: ``report`` refuses in the same line, and writes no ``report.html`` and no new
  ``handover.json``.
- IG-12: a ``--save`` still saves, exit 0; its note says the pages were not rebuilt and why, in
  that sentence.
- IG-13: the stand-in with its bundle whole builds the pages and the report, so it is the missing
  bundle that is refused and nothing else of the stand-in.

The stand-in: a copy of the installed ``poisson_prove`` package in a scratch folder put first on
``PYTHONPATH``, with the bundle, or one file of it, removed. The installed package is never edited.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest
from prove_floor_support import EVENT, MODULES, STORE_1_2, Ran, copy, env_of, home_of, run, tree
from pin_support import installed

BUNDLE = "poisson_prove/_ui_bundle"
#: What each stand-in lacks, and how the refusal names it.
LACKS = {
    "the bundle": (("style.css", "ui.js"), BUNDLE),
    "ui.js": (("ui.js",), f"{BUNDLE}/ui.js"),
    "style.css": (("style.css",), f"{BUNDLE}/style.css"),
}
FIX_CHECK = ["fix-check", "#2", "#1", "--store", "store", *EVENT, "--inputs", "all", "--max-mde", "0.5"]


def refusal(lacks: str) -> list[str]:
    return [f"error: poisson-prove {installed()} is installed and has no {LACKS[lacks][1]}, which Trace builds its pages with"]


@pytest.fixture(scope="module")
def standins(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """A folder for ``PYTHONPATH`` per stand-in: the installed Prove copied whole (``whole``), and
    copied with each of ``LACKS`` removed."""
    spec = importlib.util.find_spec("poisson_prove")
    assert spec is not None and spec.origin is not None
    package = Path(spec.origin).parent
    assert all((package / "_ui_bundle" / name).is_file() for name in ("style.css", "ui.js")), "the installed Prove ships its bundle"
    out = {}
    for label, gone in {"whole": (), **{k: v[0] for k, v in LACKS.items()}}.items():
        folder = tmp_path_factory.mktemp("prove") / "path"
        held = shutil.copytree(package, folder / "poisson_prove", ignore=shutil.ignore_patterns("__pycache__"))
        for name in gone:
            (Path(held) / "_ui_bundle" / name).unlink()
        if len(gone) == 2:
            (Path(held) / "_ui_bundle").rmdir()
        out[label] = folder
    return out


def under(standin: Path, argv: Sequence[object], cwd: Path) -> Ran:
    """The command in an interpreter that imports the stand-in Prove."""
    env = env_of(cwd)
    env["PYTHONPATH"] = str(standin)
    script = f"import sys\nimport poisson_prove\nassert poisson_prove.__file__.startswith({str(standin)!r}), poisson_prove.__file__\n" \
             f"from {MODULES['trace']} import main\nsys.exit(main(sys.argv[1:]))\n"
    return Ran(subprocess.run([sys.executable, "-c", script, *[str(a) for a in argv]], capture_output=True, text=True, cwd=cwd, env=env,
                              timeout=300))


# ---------- IG-10 ----------


@pytest.mark.parametrize("lacks", list(LACKS))
def test_ig_10_ui_names_the_missing_bundle_and_writes_nothing(tmp_path: Path, standins: dict[str, Path], lacks: str) -> None:
    store = copy(STORE_1_2, tmp_path)
    before = tree(tmp_path)
    ran = under(standins[lacks], ["ui", "--store", "store"], tmp_path)
    assert (ran.code, ran.out) == (1, ""), ran.text
    assert ran.lines() == refusal(lacks), ran.err
    assert "cannot write the pages" not in ran.err, "the store is not what is wrong"
    assert tree(tmp_path) == before
    assert not (store / ".poisson" / "ui").exists(), "no empty folder is left behind"
    assert not (home_of(tmp_path) / ".cache").exists(), "a refusal is no failure to log"


# ---------- IG-11 ----------


def test_ig_11_report_names_the_missing_bundle_and_writes_nothing(tmp_path: Path, standins: dict[str, Path]) -> None:
    copy(STORE_1_2, tmp_path)
    made = run([*FIX_CHECK, "--out", "bundle"], tmp_path)
    assert made.code == 0, made.text
    before = tree(tmp_path)
    ran = under(standins["the bundle"], ["report", "bundle"], tmp_path)
    assert (ran.code, ran.out) == (1, ""), ran.text
    assert ran.lines() == refusal("the bundle"), ran.err
    assert "cannot write" not in ran.err, "the folder is not what is wrong"
    assert tree(tmp_path) == before and not (tmp_path / "bundle" / "report.html").exists()


# ---------- IG-12 ----------


def test_ig_12_a_save_stands_and_its_note_names_the_missing_bundle(tmp_path: Path, standins: dict[str, Path]) -> None:
    store = copy(STORE_1_2, tmp_path)
    ran = under(standins["the bundle"], [*FIX_CHECK, "--save"], tmp_path)
    assert ran.code == 0 and ran.out.strip(), ran.text
    notes = [line for line in ran.err.splitlines() if line.startswith("note: the pages were not rebuilt")]
    assert notes == [f"note: the pages were not rebuilt: {refusal('the bundle')[0].removeprefix('error: ')}"], ran.err
    assert list((store / ".poisson" / "artifacts" / "fix-check").iterdir()), "the verdict is saved"
    assert not (store / ".poisson" / "ui").exists(), "no empty folder is left behind"


# ---------- IG-13 ----------


def test_ig_13_the_stand_in_with_its_bundle_builds_the_pages_and_the_report(tmp_path: Path, standins: dict[str, Path]) -> None:
    store = copy(STORE_1_2, tmp_path)
    ran = under(standins["whole"], ["ui", "--store", "store"], tmp_path)
    assert ran.code == 0 and ran.err == "", ran.text
    built = store / ".poisson" / "ui" / "trace"
    assert (built / "index.html").is_file() and (built / "style.css").is_file() and (built / "ui.js").is_file()
    made = under(standins["whole"], [*FIX_CHECK, "--out", "bundle"], tmp_path)
    assert made.code == 0, made.text
    ran = under(standins["whole"], ["report", "bundle"], tmp_path)
    assert ran.code == 0 and (tmp_path / "bundle" / "report.html").is_file(), ran.text
