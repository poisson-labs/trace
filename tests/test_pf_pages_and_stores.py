"""PF-8, PF-9 and PF-14 to PF-16: the floor is written once, the pages give one install line, and
the fixture stores Prove made are what their provenance says. These seventeen tests were
``test_prove_pin.py``'s (PIN-2, PIN-4, PIN-5, PIN-6) and moved here, under floor names and otherwise
as they were, on the ruling of 2026-11-18 (AR-6); the rest of that file held what PF-1 to PF-5,
PF-72 and PF-73 hold.

- PF-8: the recorded floor is written once, in ``pyproject.toml``'s dependency, so the floor Trace
  checks cannot drift from the one it declares; the pages name no other floor, show no Prove
  below it as installed, and no longer say Trace reads one exact version.
- PF-9: the README and the install pages give one install line: no line installs Prove on its
  own, and no page says Prove is off the package index or installed separately.
- PF-14: every fixture store the suite reads that was made with Prove is listed. The store 0.1.3
  made is kept as it wrote it, the fixture of the stored format's 1.0; the stores made before
  Prove was published are kept as written; the floor's store is written whole by the floor.
- PF-15: the store's recipe names the PyPI version that made it, never a commit, refuses any
  other Prove, and makes the store again.
- PF-16: no commit of the archived Prove repository is named anywhere in the repository.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pin_support import FORMAT_1_0, INSTALL, OLD_PROVE_COMMITS, RECORDED, REQUIREMENT, at_or_above_the_floor, installed

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
SRC = REPO / "src" / "poisson_trace"
FIXTURES = TESTS / "fixtures"
STORES = FIXTURES / "prove-stores"
PINNED_STORE = STORES / f"prove-{RECORDED}"
#: The store poisson-prove 0.1.3 made, kept as the fixture of the stored format's 1.0 (PV-7).
KEPT_STORE = STORES / f"prove-{FORMAT_1_0}"
#: The floor as one exact published version: what the recipe installs to make the floor's store.
EXACT = f"poisson-prove=={RECORDED}"
PAGES = [REPO / "README.md", *sorted((REPO / "docs").rglob("*.md"))]
INSTALL_PAGES = sorted((REPO / "docs" / "integrations").glob("*.md"))
# what a reader reads about installing: the pages, the licence notes and the package's own note
SAID = [*PAGES, REPO / "NOTICE", REPO / "pyproject.toml"]
VERSION = re.compile(r"(?<![\w.])" + re.escape(RECORDED) + r"(?![\w.])")


# ---------- PF-8 ----------


def _written(path: Path) -> list[str]:
    return [f"{path.relative_to(REPO)}:{n}" for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if VERSION.search(line)]


def test_pf_8_the_floor_is_written_in_one_place() -> None:
    """The recorded floor is written once, in ``pyproject.toml``'s dependency: the package's
    source, its build hook and the refusal's install command take it from there, so moving the
    floor is one edit and the floor Trace checks cannot drift from the one it declares."""
    places = [REPO / "pyproject.toml", REPO / "hatch_build.py",
              *sorted(p for p in SRC.rglob("*") if p.is_file() and p.suffix in (".py", ".toml", ".json", ".txt"))]
    found = [hit for path in places if path.is_file() for hit in _written(path)]
    assert len(found) == 1 and found[0].startswith("pyproject.toml:"), found


# where a page names the floor Trace reads: nothing but the recorded floor
FLOOR_SHOWN = (
    re.compile(r"poisson-prove\s*[>=]=\s*(\d+\.\d+\.\d+[\w.]*)"),  # a requirement
    re.compile(r"Trace reads version (\d+\.\d+\.\d+[\w.]*)"),  # doctor
    re.compile(r"the poisson-prove package, version (\d+\.\d+\.\d+[\w.]*)"),  # the refusal
    re.compile(r"Prove[^.\n]*?\bat version (\d+\.\d+\.\d+[\w.]*) or later"),  # prose
)
# where a page shows a Prove that was installed when it was written: the floor or one above it
FOUND_SHOWN = (
    re.compile(r"\(poisson-prove (\d+\.\d+\.\d+[\w.]*), Python "),  # the version line
    re.compile(r"poisson-prove (\d+\.\d+\.\d+[\w.]*) \(Trace reads version"),  # doctor
)
# a figure's footer names the Prove it was drawn with: 0.1.3 for the figures drawn before the floor
FOOTER = re.compile(r"Poisson Trace \u00b7 Prove (\d+\.\d+\.\d+[\w.]*?) \u00b7")
FIGURES = sorted((REPO / "docs" / "figures").glob("*.svg"))
# the two pages outside docs/ that a reader installs by: the contributing page and the setup skill
OTHER_PAGES = [REPO / "CONTRIBUTING.md", SRC / "skills" / "poisson-trace-setup" / "SKILL.md"]
# a page's prose naming a Prove by its version alone: the floor or one above it
PROSE = re.compile(r"\bProve `?(\d+\.\d+\.\d+[\w.]*)")


def test_pf_8_the_pages_show_no_other_floor_as_the_one_trace_reads() -> None:
    """The README, the pages under docs/, the contributing page, the setup skill and the figures
    the pages show: no page names another floor, shows or names a Prove below it, or says any more
    that Trace reads one exact version."""
    wrong = []
    for page in [*PAGES, *OTHER_PAGES, *FIGURES]:
        for n, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
            where = f"{page.relative_to(REPO)}:{n}: {line.strip()}"
            wrong += [where for pattern in FLOOR_SHOWN for shown in pattern.findall(line) if shown != RECORDED]
            wrong += [where for pattern in FOUND_SHOWN for shown in pattern.findall(line) if not at_or_above_the_floor(shown)]
            wrong += [where for shown in FOOTER.findall(line) if shown != FORMAT_1_0 and not at_or_above_the_floor(shown)]
            if page.suffix == ".md":
                wrong += [where for shown in PROSE.findall(line) if not at_or_above_the_floor(shown.rstrip("."))]
            if "(the version Trace reads)" in line or re.search(r"\bone exact version\b", line):
                wrong.append(where)
    assert wrong == []


# ---------- PF-9 ----------

FENCE = re.compile(r"^\s*(```|~~~)")
INSTALLS = re.compile(r"^\s*(?:\$\s*)?(?:python3?(?:\.\d+)? -m pip|pip3?|uv pip|uv tool|pipx|uv) (?:install|add)\b")


def _blocks(text: str) -> list[list[str]]:
    out, body, inside = [], [], False
    for line in text.split("\n"):
        if FENCE.match(line):
            if inside:
                out.append(body)
                body = []
            inside = not inside
        elif inside:
            body.append(line)
    return out


def _section(text: str, heading: str) -> str:
    """The text under a ``## `` heading, up to the next heading of that level or above."""
    lines = text.split("\n")
    start = lines.index(heading) + 1
    end = next((i for i in range(start, len(lines)) if re.match(r"^#{1,2} ", lines[i])), len(lines))
    return "\n".join(lines[start:end])


def test_pf_9_no_line_installs_prove_on_its_own() -> None:
    off = re.compile(r"git\+https?://github\.com/poisson-labs/prove|proofload-\d[\w.-]*\.whl|/path/to/prove",
                     re.IGNORECASE)
    hits = []
    for path in SAID:
        text = path.read_text(encoding="utf-8")
        hits += [f"{path.relative_to(REPO)}:{n}: {line.strip()}" for n, line in enumerate(text.splitlines(), 1)
                 if off.search(line)]
        for block in _blocks(text):
            hits += [f"{path.relative_to(REPO)}: {line.strip()}" for line in block
                     if INSTALLS.match(line) and re.search(r"poisson[-_]prove|proofload|/prove\b", line)]
    assert hits == []


def test_pf_9_every_install_block_is_one_line() -> None:
    hits = []
    for page in PAGES:
        for block in _blocks(page.read_text(encoding="utf-8")):
            installs = [line.strip() for line in block if INSTALLS.match(line)]
            if len(installs) > 1:
                hits.append(f"{page.relative_to(REPO)}: {installs}")
    assert hits == []


def test_pf_9_the_install_sections_give_one_line() -> None:
    """The README's Install section opens with the one line, and each integration page's Install
    section is that one line and nothing else."""
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    first = _blocks(_section(readme, "## Install"))[0]
    assert [line for line in first if line.strip()] == ["pip install poisson-trace"], first
    assert INSTALL_PAGES
    for page in INSTALL_PAGES:
        section = _section(page.read_text(encoding="utf-8"), "## Install")
        installs = [line.strip() for block in _blocks(section) for line in block if INSTALLS.match(line)]
        assert installs == ["pip install poisson-trace"], (page.name, installs)


# a paragraph that names Prove and says it is off the index, unreleased, or installed apart
NAMES_PROVE = re.compile(r"\bProve\b|proofload|poisson[-_]prove", re.IGNORECASE)
APART = re.compile(
    "|".join((
        r"not\s+(?:yet\s+)?(?:on|in)\s+(?:PyPI|a\s+package\s+index|any\s+package\s+index)",
        r"not\s+(?:yet\s+)?(?:released|published|public)",
        r"isn't\s+(?:yet\s+)?(?:on|in)\s+PyPI",
        r"install(?:ed|s)?\s+(?:it\s+)?separately",
        r"separate(?:ly)?\s+install",
        r"not\s+(?:a\s+)?declared\s+dependenc",
        r"not\s+listed\s+here",
        r"(?:installed|install\s+it)\s+from\s+its\s+repository",
        r"install\s+the\s+Prove\s+wheel",
        r"until\s+Prove\s+is\s+public",
        r"two\s+install\s+lines",
        r"the\s+same\s+two\s+lines",
    )),
    re.IGNORECASE,
)


def _paragraphs(text: str) -> list[tuple[int, str]]:
    out, start, para = [], 1, []
    for n, line in enumerate(text.splitlines(), 1):
        if line.strip():
            if not para:
                start = n
            para.append(line.strip().lstrip("#").strip())
        elif para:
            out.append((start, " ".join(para)))
            para = []
    if para:
        out.append((start, " ".join(para)))
    return out


def test_pf_9_no_page_says_prove_is_off_the_index_or_installed_apart() -> None:
    hits = []
    for path in SAID:
        for n, para in _paragraphs(path.read_text(encoding="utf-8")):
            said = APART.search(para)
            if said and NAMES_PROVE.search(para):
                hits.append(f"{path.relative_to(REPO)}:{n}: ...{said.group(0)}...")
    assert hits == []


# ---------- PF-14 ----------

# Every store root under tests/fixtures that holds runs Prove wrote, found by their manifests.
MADE_WITH_PROVE = {
    "tau2": "real runs, 2026-09-15 and 2026-09-17, copied with their observation bodies removed",
    "cs": "real runs, 2026-09-25, copied with their observation bodies removed",
    "humaneval": "real runs, 2026-09-05, copied outcome-only",
    "prove-stores/prove-0.0.1": "Prove's own sweep on its mock agent, under its old name proofload 0.0.1",
    f"prove-stores/prove-{FORMAT_1_0}": "Prove's own sweep on its mock agent, poisson-prove 0.1.3 from PyPI: the stored format's 1.0",
    f"prove-stores/prove-{RECORDED}": "Prove's own sweep on its mock agent, poisson-prove from PyPI at the floor",
}


def _store_roots() -> set[str]:
    return {str(m.parent.parent.relative_to(FIXTURES)) for m in FIXTURES.rglob("manifest.json")
            if ".poisson" not in m.parts}


def _versions(manifest: dict, key: str) -> list[str]:  # type: ignore[type-arg]
    """Every value under ``key`` anywhere in a manifest."""
    found = []
    stack: list[object] = [manifest]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            found += [str(v) for k, v in item.items() if k == key]
            stack += list(item.values())
        elif isinstance(item, list):
            stack += item
    return found


def test_pf_14_every_store_made_with_prove_is_listed() -> None:
    assert _store_roots() == set(MADE_WITH_PROVE)


# PP1 (PENDING): the stores Prove made before it was published are kept as they were written: the
# three real-run pairs cannot be made again without paying for the model runs, and the 0.0.1
# store is the old shape TF16 reads beside the new. The store 0.1.3 made is kept as the fixture of
# the stored format's 1.0 (PV-7). The rest are made by the recorded Prove, the floor.
BEFORE_PUBLISHED = {"tau2", "cs", "humaneval", "prove-stores/prove-0.0.1"}
KEPT_1_0 = {f"prove-stores/prove-{FORMAT_1_0}"}


def test_pf_14_the_store_0_1_3_made_is_kept_as_written() -> None:
    """PV-7: the fixture of the stored format's 1.0 states the Prove that wrote it and no other,
    in its runs, its descriptor and its saved comparison, and holds no key a later format added."""
    runs = sorted(KEPT_STORE.glob("*/manifest.json"))
    assert len(runs) == 2
    descriptor = json.loads((KEPT_STORE / ".poisson" / "store.json").read_text(encoding="utf-8"))
    assert descriptor["format"] == "poisson.store/1" and descriptor["created_by"] == {"tool": "poisson-prove", "version": FORMAT_1_0}
    assert [(w["tool"], w["version"]) for w in descriptor["writers"]] == [("poisson-prove", FORMAT_1_0)]
    (artifact,) = (KEPT_STORE / ".poisson" / "artifacts" / "comparison").glob("*/artifact.json")
    made = json.loads(artifact.read_text(encoding="utf-8"))
    assert (made["tool"], made["tool_version"]) == ("poisson-prove", FORMAT_1_0), artifact
    comparison = json.loads((artifact.parent / "comparison.json").read_text(encoding="utf-8"))
    assert "note_a" not in comparison and "note_b" not in comparison
    for path in runs:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert set(_versions(manifest, "poisson_prove_version")) == {FORMAT_1_0}, path
        assert _versions(manifest, "proofload_version") == [], path
        assert not {"produced_by", "stopped_by", "note"} & set(manifest), path


@pytest.mark.parametrize("root", sorted(BEFORE_PUBLISHED))
def test_pf_14_the_stores_made_before_prove_was_published_are_kept_as_written(root: str) -> None:
    """PP1: each states the one version Prove had then, under its old name, and nothing newer."""
    manifests = sorted((FIXTURES / root).glob("*/manifest.json"))
    assert manifests, root
    for path in manifests:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert set(_versions(manifest, "proofload_version")) == {"0.0.1"}, path
        assert _versions(manifest, "poisson_prove_version") == [], path


def test_pf_14_the_floors_store_is_written_whole_by_the_floor() -> None:
    """The floor's store: its runs, its store descriptor and its saved comparison, with every key
    the stored format has gained since 1.0 (``produced_by``, 1.1; the notes, 1.2)."""
    runs = sorted(PINNED_STORE.glob("*/manifest.json"))
    assert len(runs) == 2
    assert json.loads((PINNED_STORE / ".poisson" / "store.json").read_text())["format"] == "poisson.store/1"
    (artifact,) = (PINNED_STORE / ".poisson" / "artifacts" / "comparison").glob("*/artifact.json")
    made = json.loads(artifact.read_text(encoding="utf-8"))
    assert (made["tool"], made["tool_version"]) == ("poisson-prove", RECORDED), artifact
    comparison = json.loads((artifact.parent / "comparison.json").read_text(encoding="utf-8"))
    notes = []
    for path in runs:
        manifest = json.loads(path.read_text())
        assert set(_versions(manifest, "poisson_prove_version")) == {RECORDED}, path
        assert manifest["produced_by"]["tool"] == "poisson-prove" and manifest["produced_by"]["version"] == RECORDED, path
        notes.append(manifest["note"])
    assert notes == ["the agent as it was", "retry each tool call once"] == [comparison["note_a"], comparison["note_b"]]


# ---------- PF-15 ----------


def test_pf_15_the_recipe_names_the_pypi_version() -> None:
    """The store's recipe and its provenance say which published Prove made it, by the PyPI
    requirement of that one version (the floor, exactly), and how to get it; the provenance also
    gives the requirement Trace declares and Trace's own install line, and says the 0.1.3 store
    is kept."""
    provenance = (STORES / "PROVENANCE.md").read_text(encoding="utf-8")
    make = (STORES / "make.py").read_text(encoding="utf-8")
    for text in (provenance, make):
        assert EXACT in text and "PyPI" in text
    assert f"pip install {EXACT}" in provenance and REQUIREMENT in provenance and INSTALL in provenance
    assert f"prove-{RECORDED}/" in provenance and "make.py" in provenance
    assert f"prove-{FORMAT_1_0}/" in provenance and f"poisson-prove=={FORMAT_1_0}" in provenance
    assert f"poisson-prove=={FORMAT_1_0}" not in make


def test_pf_15_the_recipe_refuses_a_prove_that_is_not_the_floor(tmp_path: Path) -> None:
    """The recipe makes the floor's store with the floor and nothing else: given a Python whose
    Prove states another version, it stops, names the floor, and writes nothing."""
    python = tmp_path / "python-with-another-prove"
    python.write_text(f"#!/bin/sh\necho {FORMAT_1_0}\n", encoding="utf-8")
    python.chmod(0o755)
    dest = tmp_path / "made"
    ran = subprocess.run([sys.executable, str(STORES / "make.py"), str(dest), "--python", str(python)],
                         capture_output=True, text=True, timeout=120)
    assert ran.returncode != 0, ran.stdout + ran.stderr
    assert FORMAT_1_0 in ran.stderr and EXACT in ran.stderr, ran.stderr
    assert not dest.exists()


def test_pf_15_the_recipe_makes_the_store_again(tmp_path: Path) -> None:
    """Run with the recorded Prove, the floor, the recipe writes a store of the same files,
    holding the same outcomes row for row; only the run ids, the times and the files that carry
    them differ. Under a Prove above the floor the recipe refuses (the test above), so this is
    skipped there and says so."""
    from poisson_prove.store import Store

    if installed() != RECORDED:
        pytest.skip(f"poisson-prove {installed()} is installed; the recipe makes the floor's store with {RECORDED}")

    dest = tmp_path / "made"
    env = {**os.environ, "HOME": str(tmp_path / "home"), "NO_COLOR": "1"}
    (tmp_path / "home").mkdir()
    subprocess.run([sys.executable, str(STORES / "make.py"), str(dest), "--python", sys.executable],
                   check=True, capture_output=True, env=env, timeout=600)
    made = dest / f"prove-{RECORDED}"

    def shape(root: Path) -> list[str]:
        return sorted(re.sub(r"\d{8}T\d{6}Z-[0-9a-f]{4}|(?<=/)[0-9a-f]{16}(?=/|$)", "*", str(p.relative_to(root)))
                      for p in root.rglob("*") if p.is_file())

    def rows(root: Path) -> list[list[tuple]]:  # type: ignore[type-arg]
        store = Store(root)
        out = []
        for run in sorted(p.parent.name for p in root.glob("*/manifest.json")):
            frame = store.read(run)
            out.append(sorted(zip(frame["config_hash"], frame["replicate_index"], frame["outcome"], frame["t"],
                                  strict=True)))
        return out

    assert shape(made) == shape(PINNED_STORE)
    assert rows(made) == rows(PINNED_STORE)


# ---------- PF-16 ----------


def _tracked() -> list[Path]:
    """Every file of the repository: what git tracks when there is a checkout, else every file
    but the ones a build or a run leaves."""
    if (REPO / ".git").exists() and shutil.which("git"):
        listed = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True, timeout=120)
        return [REPO / name for name in listed.stdout.decode("utf-8").split("\0") if name]
    skip = {".git", "__pycache__", ".venv", "build", "dist", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
    return [p for p in REPO.rglob("*") if p.is_file() and not skip & set(p.relative_to(REPO).parts)]


def test_pf_16_no_commit_of_the_archived_prove_is_named_anywhere() -> None:
    hits = []
    for path in _tracked():
        if not path.is_file():
            continue
        data = path.read_bytes().lower()
        hits += [f"{path.relative_to(REPO)}: {c}" for c in OLD_PROVE_COMMITS if c.encode() in data]
    assert hits == []
