"""PIN-1 to PIN-6: Trace pins the published Prove (Taylor's ruling of 2026-11-03).

Trace pins exactly ``poisson-prove`` 0.1.2, the newest on PyPI when these tests were frozen
(``pin_support.RECORDED``), as a declared dependency, and the pin moves later only on purpose.

- PIN-1: ``pyproject.toml`` declares ``poisson-prove==`` the recorded version as a dependency, and
  installing the Trace wheel into a clean environment installs that Prove: nothing asks for a
  second install line (the clean install runs in lane J, as it reads PyPI).
- PIN-2: the version Trace reads (``look.PROVE_VERSION``) is the declared pin, written in one place
  so the two cannot drift; the pages show no other.
- PIN-3: with any other ``poisson-prove``, or none, every command refuses as it does today: exit 1,
  one ``error:`` line naming the version Trace reads and the one it found, and under it the one
  command that fixes it, ``pip install poisson-prove==`` the recorded version; ``doctor`` fails
  its Prove check (exit 4) naming the same command. With the recorded Prove nothing refuses.
- PIN-4: every fixture store the suite reads that was made with Prove is listed, each is made by
  the recorded published Prove, and the recipe names that PyPI version, never a commit.
- PIN-5: no commit of the archived Prove repository is named anywhere in the repository.
- PIN-6: the README and the install pages give one install line: no line installs Prove on its
  own, and no page says Prove is off the package index or installed separately.
- PIN-F: green by construction: the digests of these files as the session that froze them left
  them.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

from pin_support import INSTALL, OLD_PROVE_COMMITS, RECORDED, REQUIREMENT

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
SRC = REPO / "src" / "poisson_trace"
FIXTURES = TESTS / "fixtures"
STORES = FIXTURES / "prove-stores"
PINNED_STORE = STORES / f"prove-{RECORDED}"
PAGES = [REPO / "README.md", *sorted((REPO / "docs").rglob("*.md"))]
INSTALL_PAGES = sorted((REPO / "docs" / "integrations").glob("*.md"))
# what a reader reads about installing: the pages, the licence notes and the package's own note
SAID = [*PAGES, REPO / "NOTICE", REPO / "pyproject.toml"]
VERSION = re.compile(r"(?<![\w.])" + re.escape(RECORDED) + r"(?![\w.])")


def _name(requirement: str) -> str:
    """A requirement's project name, normalised as PyPI compares them."""
    match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", requirement)
    assert match, requirement
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


def _project() -> dict:  # type: ignore[type-arg]
    project: dict = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]  # type: ignore[type-arg]
    return project


def _declared_pin() -> str:
    (prove,) = [d for d in _project().get("dependencies", []) if _name(d) == "poisson-prove"]
    return prove.replace(" ", "").removeprefix("poisson-prove==")


# ---------- PIN-1 ----------


def test_pin_1_pyproject_declares_exactly_the_recorded_prove() -> None:
    project = _project()
    assert "dependencies" not in project.get("dynamic", []), project.get("dynamic")
    prove = [d.replace(" ", "") for d in project.get("dependencies", []) if _name(d) == "poisson-prove"]
    assert prove == [REQUIREMENT], project.get("dependencies")
    # no extra adds a second way to get Prove, and the old name is never asked for
    for extra, deps in project.get("optional-dependencies", {}).items():
        assert not [d for d in deps if _name(d) in ("poisson-prove", "proofload")], (extra, deps)
    assert not [d for d in project.get("dependencies", []) if _name(d) == "proofload"]


def test_pin_1_the_installed_trace_requires_the_recorded_prove_and_has_it() -> None:
    """The metadata the installed package carries (what a wheel built from this tree says), and
    the Prove this suite runs against."""
    requires = [r.replace(" ", "") for r in importlib.metadata.requires("poisson-trace") or []]
    assert [r for r in requires if _name(r) == "poisson-prove"] == [REQUIREMENT], requires
    assert importlib.metadata.version("poisson-prove") == RECORDED


@pytest.mark.lane_j
def test_pin_1_a_clean_install_of_the_wheel_brings_the_recorded_prove(tmp_path: Path) -> None:
    """Lane J: reads PyPI. The wheel built from this tree, installed by one line into a fresh
    environment, brings ``poisson-prove`` at the recorded version, and Trace then reads a store
    with nothing more installed and no line asking for another install."""
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, timeout=600)
    python, bin_ = str(venv / "bin" / "python"), venv / "bin"
    wheels = tmp_path / "wheels"
    subprocess.run([python, "-m", "pip", "wheel", "--quiet", "--no-deps", "--wheel-dir", str(wheels), str(REPO)],
                   check=True, timeout=1800)
    (wheel,) = wheels.glob("poisson_trace-*.whl")
    with zipfile.ZipFile(wheel) as zf:
        (meta,) = [n for n in zf.namelist() if n.endswith(".dist-info/METADATA")]
        requires = [line.split(":", 1)[1].strip().replace(" ", "")
                    for line in zf.read(meta).decode("utf-8").splitlines()
                    if line.startswith("Requires-Dist:")]
    assert [r for r in requires if _name(r) == "poisson-prove"] == [REQUIREMENT], requires
    subprocess.run([python, "-m", "pip", "install", "--quiet", str(wheel)], check=True, timeout=1800)
    env = {**os.environ, "HOME": str(tmp_path / "home"), "NO_COLOR": "1"}
    (tmp_path / "home").mkdir()

    def run(*argv: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(bin_ / "poisson-trace"), *argv], capture_output=True, text=True,
                              env=env, cwd=tmp_path, timeout=300)

    found = subprocess.run([python, "-c", "import importlib.metadata as m; print(m.version('poisson-prove'))"],
                           capture_output=True, text=True, check=True, timeout=120)
    assert found.stdout.strip() == RECORDED
    assert subprocess.run([python, "-m", "pip", "check"], capture_output=True, timeout=300).returncode == 0
    version = run("--version")
    assert version.returncode == 0 and f"(poisson-prove {RECORDED}, Python " in version.stdout, version
    store = tmp_path / "store"
    shutil.copytree(PINNED_STORE, store)
    for argv in (["runs", "--store", str(store)], ["doctor", "--json"]):
        ran = run(*argv)
        assert "pip install" not in ran.stdout + ran.stderr, ran
        if argv[0] == "runs":
            assert ran.returncode == 0, ran
        else:
            (prove,) = [c for c in json.loads(ran.stdout)["checks"] if c["name"] == "prove"]
            assert prove["ok"] is True, prove


# ---------- PIN-2 ----------


def test_pin_2_the_version_trace_reads_is_the_declared_pin() -> None:
    from poisson_trace import look

    assert _declared_pin() == RECORDED
    assert look.PROVE_VERSION == _declared_pin()


def _written(path: Path) -> list[str]:
    return [f"{path.relative_to(REPO)}:{n}" for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if VERSION.search(line)]


def test_pin_2_the_pin_is_written_in_one_place() -> None:
    """The recorded version is written once, in ``pyproject.toml``'s dependency: the package's
    source, its build hook and the refusal's install command take it from there, so moving the pin
    is one edit and the version Trace reads cannot drift from the one it declares."""
    places = [REPO / "pyproject.toml", REPO / "hatch_build.py",
              *sorted(p for p in SRC.rglob("*") if p.is_file() and p.suffix in (".py", ".toml", ".json", ".txt"))]
    found = [hit for path in places if path.is_file() for hit in _written(path)]
    assert len(found) == 1 and found[0].startswith("pyproject.toml:"), found


PROVE_SHOWN = (
    re.compile(r"\(poisson-prove (\d+\.\d+\.\d+\S*), Python "),  # the version line
    re.compile(r"poisson-prove (\d+\.\d+\.\d+\S*) \(the version Trace reads\)"),  # doctor
    re.compile(r"poisson-prove\s*==\s*(\d+\.\d+\.\d+\S*)"),  # a requirement
    re.compile(r"Trace reads version (\d+\.\d+\.\d+\S*)"),  # doctor, on another Prove
    re.compile(r"the poisson-prove package, version (\d+\.\d+\.\d+\S*)\)"),  # the refusal
    re.compile(r"Poisson Trace \u00b7 Prove (\d+\.\d+\.\d+\S*?) \u00b7"),  # a figure's footer
)
FIGURES = sorted((REPO / "docs" / "figures").glob("*.svg"))


def test_pin_2_the_pages_show_no_other_prove_as_the_one_trace_reads() -> None:
    """The README, the pages under docs/ and the figures they show."""
    wrong = []
    for page in [*PAGES, *FIGURES]:
        for n, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
            wrong += [f"{page.relative_to(REPO)}:{n}: {line.strip()}" for pattern in PROVE_SHOWN
                      for shown in pattern.findall(line) if shown != RECORDED]
    assert wrong == []


# ---------- PIN-3 ----------

OTHERS = ("0.1.1", "0.1.0", "0.0.1", "0.1.3", "1.0.0")
# each command, the module that runs it, and the words its refusal opens with, as Trace says
# them today; only the version and the install command move
FAMILIES = {
    "runs": ("poisson_trace.cli", ["runs", "--store", "STORE"], "Poisson Trace reads stored runs"),
    "where": ("poisson_trace.cli", ["where", "agent before", "--store", "STORE", "--event", "violated"],
              "Poisson Trace reads stored runs"),
    "compare": ("poisson_trace.cli", ["compare", "#2", "#1", "--store", "STORE", "--event", "violated",
                                      "--max-mde-hr", "1.5"], "Poisson Trace reads stored runs"),
    "fix-check": ("poisson_trace.cli", ["fix-check", "#2", "#1", "--store", "STORE", "--event", "violated",
                                        "--inputs", "all", "--max-mde", "0.5"], "Poisson Trace reads stored runs"),
    "changes": ("poisson_trace.cli", ["changes", "#2", "#1", "--store", "STORE", "--event", "violated"],
                "Poisson Trace reads stored runs"),
    "name": ("poisson_trace.cli", ["name", "#1", "a name", "--store", "STORE"], "Poisson Trace reads stored runs"),
    "init": ("poisson_trace.cli", ["init", "--yes"], "poisson-trace init reads stores"),
    "import": ("poisson_trace.cli", ["import", "junit", "JUNIT", "--store", "NEWSTORE", "--run", "suite"],
               "poisson-trace import writes runs"),
    "poisson-trace-import": ("poisson_trace.ingest.cli", ["junit", "JUNIT", "--store", "NEWSTORE", "--run", "suite"],
                             "poisson-trace import writes runs"),
}
JUNIT = FIXTURES / "ingest" / "junit" / "trace-suite-1.xml"


def _with_prove(module: str, argv: list[str], prove: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """The command in a fresh interpreter whose ``poisson_prove`` is ``prove``: ``absent`` (none
    importable) or a module stating that version."""
    if prove == "absent":
        head = "sys.modules['poisson_prove'] = None\n"
    else:
        head = (f"fake = types.ModuleType('poisson_prove')\nfake.__version__ = {prove!r}\n"
                "sys.modules['poisson_prove'] = fake\n")
    code = f"import sys, types\n{head}from {module} import main\nsys.exit(main(sys.argv[1:]))\n"
    env = {**os.environ, "HOME": str(cwd / "home"), "NO_COLOR": "1"}
    (cwd / "home").mkdir(exist_ok=True)
    return subprocess.run([sys.executable, "-c", code, *argv], capture_output=True, text=True, cwd=cwd,
                          env=env, timeout=120)


def _argv(family: str, tmp_path: Path) -> list[str]:
    store = tmp_path / "store"
    if not store.exists():
        shutil.copytree(PINNED_STORE, store)
    swap = {"STORE": str(store), "NEWSTORE": str(tmp_path / "new-store"), "JUNIT": str(JUNIT)}
    return [swap.get(a, a) for a in FAMILIES[family][1]]


def _files(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and "home" not in p.relative_to(root).parts}


@pytest.mark.parametrize("prove", [*OTHERS, "absent"])
@pytest.mark.parametrize("family", list(FAMILIES))
def test_pin_3_without_the_recorded_prove_every_command_refuses_naming_both_versions_and_the_fix(
    tmp_path: Path, family: str, prove: str
) -> None:
    module, _, does = FAMILIES[family]
    argv = _argv(family, tmp_path)
    before = _files(tmp_path)
    ran = _with_prove(module, argv, prove, tmp_path)
    if prove == "absent":
        sentence = f"error: {does} through Prove (the poisson-prove package, version {RECORDED}), which is not installed here"
    else:
        sentence = f"error: {does} through Prove (the poisson-prove package, version {RECORDED}) and found poisson-prove {prove}"
    assert ran.returncode == 1, ran.stdout + ran.stderr
    assert ran.stdout == "", ran.stdout
    assert [line for line in ran.stderr.splitlines() if line.strip()] == [sentence, f"  next: {INSTALL}"], ran.stderr
    assert _files(tmp_path) == before


@pytest.mark.parametrize("prove", ["0.1.1", "0.0.1", "absent"])
def test_pin_3_doctor_fails_its_prove_check_naming_the_fix(tmp_path: Path, prove: str) -> None:
    ran = _with_prove("poisson_trace.cli", ["doctor", "--json"], prove, tmp_path)
    assert ran.returncode == 4, ran.stdout + ran.stderr
    doc = json.loads(ran.stdout)
    (check,) = [c for c in doc["checks"] if c["name"] == "prove"]
    if prove == "absent":
        line = f"poisson-prove is not installed, and Trace reads stores through it (version {RECORDED})"
    else:
        line = f"poisson-prove {prove} is installed, and Trace reads version {RECORDED}"
    assert check == {"name": "prove", "ok": False, "line": line, "next": INSTALL}, check
    assert doc["next"] == INSTALL


def test_pin_3_the_fix_names_the_recorded_version_from_pypi() -> None:
    from poisson_trace import look

    assert look.INSTALL_PROVE == INSTALL == f"pip install poisson-prove=={_declared_pin()}"


@pytest.mark.parametrize("family", [f for f in FAMILIES if f not in ("init",)])
def test_pin_3_with_the_recorded_prove_nothing_refuses(tmp_path: Path, family: str) -> None:
    module, _, _ = FAMILIES[family]
    argv = _argv(family, tmp_path)
    code = f"import sys\nfrom {module} import main\nsys.exit(main(sys.argv[1:]))\n"
    (tmp_path / "home").mkdir()
    ran = subprocess.run([sys.executable, "-c", code, *argv], capture_output=True, text=True, cwd=tmp_path,
                         env={**os.environ, "HOME": str(tmp_path / "home"), "NO_COLOR": "1"}, timeout=300)
    assert ran.returncode in (0, 2), ran.stdout + ran.stderr
    assert "pip install" not in ran.stdout + ran.stderr and "poisson-prove package" not in ran.stderr, ran.stderr


# ---------- PIN-4 ----------

# Every store root under tests/fixtures that holds runs Prove wrote, found by their manifests.
MADE_WITH_PROVE = {
    "tau2": "real runs, 2026-09-15 and 2026-09-17, copied with their observation bodies removed",
    "cs": "real runs, 2026-09-25, copied with their observation bodies removed",
    "humaneval": "real runs, 2026-09-05, copied outcome-only",
    "prove-stores/prove-0.0.1": "Prove's own sweep on its mock agent, under its old name proofload 0.0.1",
    f"prove-stores/prove-{RECORDED}": "Prove's own sweep on its mock agent, poisson-prove from PyPI",
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


def test_pin_4_every_store_made_with_prove_is_listed() -> None:
    assert _store_roots() == set(MADE_WITH_PROVE)


# PP1 (PENDING): the stores Prove made before it was published are kept as they were written: the
# three real-run pairs cannot be made again without paying for the model runs, and the 0.0.1
# store is the old shape TF16 reads beside the new. The rest are made by the recorded Prove.
BEFORE_PUBLISHED = {"tau2", "cs", "humaneval", "prove-stores/prove-0.0.1"}


@pytest.mark.parametrize("root", sorted(set(MADE_WITH_PROVE) - BEFORE_PUBLISHED))
def test_pin_4_every_store_made_with_prove_is_made_by_the_recorded_prove(root: str) -> None:
    """Every store the suite reads that Prove made is made with the recorded published Prove, but
    the ones it made before it was published (PP1)."""
    manifests = sorted((FIXTURES / root).glob("*/manifest.json"))
    assert manifests, root
    for path in manifests:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert _versions(manifest, "proofload_version") == [], path
        versions = _versions(manifest, "poisson_prove_version")
        assert versions and set(versions) == {RECORDED}, (path, versions)


@pytest.mark.parametrize("root", sorted(BEFORE_PUBLISHED))
def test_pin_4_the_stores_made_before_prove_was_published_are_kept_as_written(root: str) -> None:
    """PP1: each states the one version Prove had then, under its old name, and nothing newer."""
    manifests = sorted((FIXTURES / root).glob("*/manifest.json"))
    assert manifests, root
    for path in manifests:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert set(_versions(manifest, "proofload_version")) == {"0.0.1"}, path
        assert _versions(manifest, "poisson_prove_version") == [], path


def test_pin_4_the_store_made_now_is_written_whole_by_the_recorded_prove() -> None:
    """The pinned store's runs, its store descriptor and its saved comparison."""
    runs = sorted(PINNED_STORE.glob("*/manifest.json"))
    assert len(runs) == 2
    assert json.loads((PINNED_STORE / ".poisson" / "store.json").read_text())["format"] == "poisson.store/1"
    (artifact,) = (PINNED_STORE / ".poisson" / "artifacts" / "comparison").glob("*/artifact.json")
    made = json.loads(artifact.read_text(encoding="utf-8"))
    assert (made["tool"], made["tool_version"]) == ("poisson-prove", RECORDED), artifact
    for path in runs:
        assert set(_versions(json.loads(path.read_text()), "poisson_prove_version")) == {RECORDED}, path


def test_pin_4_the_recipe_names_the_pypi_version() -> None:
    """The store's recipe and its provenance say which published Prove made it, by the PyPI
    requirement, and how to get it."""
    provenance = (STORES / "PROVENANCE.md").read_text(encoding="utf-8")
    make = (STORES / "make.py").read_text(encoding="utf-8")
    for text in (provenance, make):
        assert REQUIREMENT in text and "PyPI" in text
    assert INSTALL in provenance
    assert f"prove-{RECORDED}/" in provenance and "make.py" in provenance


def test_pin_4_the_recipe_makes_the_store_again(tmp_path: Path) -> None:
    """Run with the recorded Prove (the one this suite runs against), the recipe writes a store
    of the same files, holding the same outcomes row for row; only the run ids, the times and the
    files that carry them differ."""
    from poisson_prove.store import Store

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


# ---------- PIN-5 ----------


def _tracked() -> list[Path]:
    """Every file of the repository: what git tracks when there is a checkout, else every file
    but the ones a build or a run leaves."""
    if (REPO / ".git").exists() and shutil.which("git"):
        listed = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True, timeout=120)
        return [REPO / name for name in listed.stdout.decode("utf-8").split("\0") if name]
    skip = {".git", "__pycache__", ".venv", "build", "dist", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
    return [p for p in REPO.rglob("*") if p.is_file() and not skip & set(p.relative_to(REPO).parts)]


def test_pin_5_no_commit_of_the_archived_prove_is_named_anywhere() -> None:
    hits = []
    for path in _tracked():
        if not path.is_file():
            continue
        data = path.read_bytes().lower()
        hits += [f"{path.relative_to(REPO)}: {c}" for c in OLD_PROVE_COMMITS if c.encode() in data]
    assert hits == []


# ---------- PIN-6 ----------

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


def test_pin_6_no_line_installs_prove_on_its_own() -> None:
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


def test_pin_6_every_install_block_is_one_line() -> None:
    hits = []
    for page in PAGES:
        for block in _blocks(page.read_text(encoding="utf-8")):
            installs = [line.strip() for line in block if INSTALLS.match(line)]
            if len(installs) > 1:
                hits.append(f"{page.relative_to(REPO)}: {installs}")
    assert hits == []


def test_pin_6_the_install_sections_give_one_line() -> None:
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


def test_pin_6_no_page_says_prove_is_off_the_index_or_installed_apart() -> None:
    hits = []
    for path in SAID:
        for n, para in _paragraphs(path.read_text(encoding="utf-8")):
            said = APART.search(para)
            if said and NAMES_PROVE.search(para):
                hits.append(f"{path.relative_to(REPO)}:{n}: ...{said.group(0)}...")
    assert hits == []


# ---------- PIN-F ----------

FROZEN = {
    "pin_support.py": "7e13ac4069fe24f48e62ed19efa1a53d4a98f8fa7d9a85e87670fd9abc8c29d4",
    "test_prove_pin.py": "e2345f458a98a23967025c7f456141f48830596fdb4b30223a07a33e00f930c6",
}


def test_pin_f_no_frozen_pin_test_is_edited() -> None:
    """Green by construction: these files as the session that froze them left them. A PENDING
    commit that moves one of them moves its digest here in the same commit; this file holds its
    own digest with this table's lines left out."""
    got = {}
    for name in FROZEN:
        data = (TESTS / name).read_text(encoding="utf-8")
        if name == "test_prove_pin.py":
            data = re.sub(r'(?m)^    "[\w.]+": "[0-9a-f]*",\n', "", data)
        got[name] = hashlib.sha256(data.encode("utf-8")).hexdigest()
    assert got == FROZEN
