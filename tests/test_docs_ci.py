"""TF5-90 to TF5-97: ``.github/workflows/ci.yml`` and the packaging.

Frozen here: what ``ci.yml`` must run, on which Pythons, and when. Left open: which
runner each job uses (``runs-on``, hosted or not, and which systems the
full matrix covers), how the jobs are cut into shards, and how the socket guard is made.
Nothing here reads ``runs-on``. ``ci.yml`` is read as text, by its indentation, since the
suite carries no YAML reader.

- TF5-90: the workflow runs on every pull request, on every push to ``main`` and on a
  schedule; it holds read access to the repository's contents and no secret; every action is
  pinned to a full commit SHA; every job has a time limit.
- TF5-91: on every pull request, on Python 3.11: the pull-request lane (``python -m pytest``
  with ``-m "not math and not lane_j and not slow"`` over ``tests``), ``ruff check src
  tests`` and ``mypy --strict``. Every pytest line unsets ``CI``, which Trace reads as a
  reason to print plain.
- TF5-92: the math lane (``-m math``) runs on the schedule, and on a pull request when the
  statistics code or the resolved numpy, scipy, pandas or lifelines changed: the workflow, or
  a script under ``.github/lanes/`` it runs, names each of those, in what it runs or holds and not
  in a comment alone.
- TF5-93: the slow lane (``-m slow``), lane J (``-m lane_j``, which reads the package index
  for DeepEval and Ragas) and the full matrix (Python 3.11, 3.12 and 3.13) run on a push to
  ``main`` and on the schedule, and never on a pull request.
- TF5-94: the job ``clean-install``: builds the source archive and the wheel from the commit;
  installs the wheel with plain pip into a fresh environment, and the source archive in one
  cell; leaves the checkout for an empty folder with ``HOME`` set to another; checks
  ``poisson_trace.__file__`` is inside that environment; runs ``tools/docs_check.py`` over
  the README and the docs with its summary in the job's summary; and has a step, after the
  install and before the docs check, that refuses every connection but to this machine.
- TF5-95: the workflow file says in its opening comment what each job is for, as
  ``release.yml`` does, and the lanes are the four ``pyproject.toml`` names, mark for mark.
- TF5-96: the packaging: both commands and ``python -m poisson_trace``;
  Python 3.11 to 3.13 declared and classified, macOS and Linux classified; ``pyarrow``
  declared at a floor of Trace's own, since Trace imports it itself, and the one installed at or above it; the setup skill and the
  pages' fixed files in the wheel, and neither ``tools/`` nor the tests; the description not
  the one that says Trace reads Prove's stored runs alone.
- TF5-97: the release workflow still runs the same lanes by the same marks, so CI and the
  release cannot drift.
- The floors of numpy and scipy: one job installs the two at exactly the versions
  ``pyproject.toml`` declares, read from it by the job's own lines, and every other package
  as ``lanes-3.11.txt`` holds it; checks that the two installed are those before any lane;
  and runs the four lanes on Python 3.11, on a push to ``main``, on the schedule and on a
  hand start, never on a pull request.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import tomllib
from pathlib import Path

import pytest

from docs_support import REPO, jobs, triggers, workflow

PR_LANE = '-m "not math and not lane_j and not slow"'
PROJECT = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
PYTEST = re.compile(r"^.*python\S* -m pytest\b.*$", re.M)


def _all() -> dict[str, str]:
    return jobs()


def _with(pattern: str) -> dict[str, str]:
    return {name: text for name, text in _all().items() if re.search(pattern, text)}


def _never_on_a_pull_request(text: str) -> bool:
    """A job that a pull request never starts: its ``if:`` asks for another event."""
    found = re.search(r"^    if:\s*(.+)$", text, re.M)
    if not found:
        return False
    cond = found.group(1)
    return bool(re.search(r"github\.event_name\s*!=\s*'pull_request'", cond)
                or (re.search(r"github\.event_name\s*==\s*'(?:push|schedule|workflow_dispatch)'", cond) and "'pull_request'" not in cond))


def _pythons(text: str) -> set[str]:
    return set(re.findall(r"[\"']?(3\.1\d)[\"']?", "\n".join(line for line in text.split("\n") if re.search(r"python(?:-version)?:|python:", line))))


# ---------- TF5-90 ----------


def test_tf5_90_when_it_runs() -> None:
    on = triggers()
    assert re.search(r"^  pull_request:", on, re.M), "every pull request"
    assert re.search(r"^  push:\s*\n\s+branches:\s*\[\s*main\s*\]", on, re.M), "every push to main"
    assert re.search(r"^  schedule:\s*\n\s+- cron:", on, re.M), "nightly"
    assert "paths" not in on.split("pull_request:")[1].split("push:")[0], "no pull request is skipped by its paths: the pull-request lane always runs"


def test_tf5_90_it_holds_no_more_than_it_needs() -> None:
    text = workflow()
    assert re.search(r"^permissions:\s*\n  contents: read\s*$", text, re.M)
    assert not re.search(r"\bsecrets\.", text), "no secret"
    assert not re.search(r"^\s+(?:id-token|packages|pull-requests|issues|actions|checks): write", text, re.M)
    uses = re.findall(r"uses:\s*(\S+)", text)
    assert uses and all(re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", use) for use in uses), [use for use in uses if not re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", use)]
    for name, body in _all().items():
        assert re.search(r"^    timeout-minutes: \d+", body, re.M), f"{name} has no time limit"


# ---------- TF5-91 ----------


def test_tf5_91_the_pull_request_lane() -> None:
    lanes = _with(re.escape(PR_LANE))
    on_pr = {name: text for name, text in lanes.items() if not _never_on_a_pull_request(text)}
    assert on_pr, "no job runs the pull-request lane on a pull request"
    assert any("3.11" in _pythons(text) for text in on_pr.values()), "on Python 3.11, the oldest the package declares"
    for text in on_pr.values():
        line = next(found for found in PYTEST.findall(text) if PR_LANE in found)
        assert re.search(r"\btests\b", line.split(PR_LANE)[1]) or " tests" in line, line


def test_tf5_91_ruff_and_mypy_on_every_pull_request() -> None:
    for pattern in (r"ruff check src tests\b", r"mypy --strict\b"):
        found = {name: text for name, text in _with(pattern).items() if not _never_on_a_pull_request(text)}
        assert found, f"no job runs {pattern} on a pull request"


def test_tf5_91_every_pytest_line_unsets_ci() -> None:
    lines = PYTEST.findall(workflow())
    assert len(lines) >= 4
    for line in lines:
        assert re.search(r"\benv -u CI\b", line), line


# ---------- TF5-92 ----------


def _strings(path: Path) -> str:
    """Every string a lane script holds that is not a docstring: what it can act on, not what a
    comment says of it."""
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = {id(node.value) for node in ast.walk(tree) if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)}
    return "\n".join(node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs)


def test_tf5_92_the_math_lane() -> None:
    lanes = _with(r"-m math\b")
    assert lanes, "no job runs -m math"
    said = "\n".join(_all().values()) + "\n" + "\n".join(_strings(path) for path in sorted((REPO / ".github" / "lanes").glob("*.py")))
    for word in ("src/poisson_trace/paired.py", "src/poisson_trace/survival.py", "src/poisson_trace/stats", "numpy", "scipy", "pandas", "lifelines"):
        assert word in said, f"the math lane's rule never names {word}"
    assert any(re.search(r"schedule", text) or not re.search(r"^    if:", text, re.M) for text in lanes.values()), "and on the schedule"


# ---------- TF5-93 ----------


@pytest.mark.parametrize(("what", "pattern"), [("the slow lane", r"-m slow\b"), ("lane J", r"-m lane_j\b")])
def test_tf5_93_never_on_a_pull_request(what: str, pattern: str) -> None:
    lanes = _with(pattern)
    assert lanes, f"no job runs {what}"
    for name, text in lanes.items():
        assert _never_on_a_pull_request(text), f"{name} runs {what} on a pull request"


def test_tf5_93_the_full_matrix() -> None:
    full = {name: text for name, text in _with(re.escape(PR_LANE)).items() if {"3.11", "3.12", "3.13"} <= _pythons(text)}
    assert full, "no job runs the pull-request lane on Python 3.11, 3.12 and 3.13"
    assert all(_never_on_a_pull_request(text) for text in full.values()), "the full matrix is main's and the night's"
    lane_j = _with(r"-m lane_j\b")
    for text in lane_j.values():
        installs = " ".join(line for line in text.split("\n") if re.search(r"\bpip install\b", line))
        assert re.search(r"\bdeepeval\b", installs) and re.search(r"\bragas\b", installs), "lane J installs the real DeepEval and Ragas"


# ---------- TF5-94 ----------


def _clean() -> str:
    found = _all().get("clean-install")
    assert found is not None, "ci.yml has no job clean-install"
    return found


def test_tf5_94_the_clean_install_builds_and_installs_as_a_user_does() -> None:
    text = _clean()
    assert re.search(r"python\S* -m build\b", text), "the source archive and the wheel, built from the commit"
    assert re.search(r"-m venv\b", text), "a fresh environment"
    assert re.search(r"pip install\b", text) and ".whl" in text and ".tar.gz" in text, "the wheel, and the source archive in one cell"
    assert not re.search(r"pip install\b[^\n]* -e\b|pip install\b[^\n]*--editable", text), "never an editable install"
    assert "poisson_trace.__file__" in text, "the package imported is the installed one"
    assert re.search(r"\bHOME[=:]", text), "a home of its own"
    assert re.search(r"\bcd \S+|working-directory:", text), "an empty folder, not the checkout"


def test_tf5_94_the_clean_install_runs_the_docs_check_with_no_network() -> None:
    text = _clean()
    at_check = text.find("tools/docs_check.py")
    assert at_check >= 0, "the docs check"
    assert re.search(r"tools/docs_check\.py[^\n]*--summary[^\n]*GITHUB_STEP_SUMMARY", text), "every skip in the job's summary"
    names = [(found.start(), found.group(1)) for found in re.finditer(r"^      - name:\s*(.+)$", text, re.M)]
    guard = [at for at, name in names if re.search(r"(?i)socket guard|no network|no connection|loopback|this machine", name)]
    install = [at for at, name in names if re.search(r"(?i)install", name)]
    assert guard and install, [name for _, name in names]
    assert min(install) < min(guard) < at_check, "after the install, before the docs check"


# ---------- TF5-95 ----------


def test_tf5_95_the_workflow_says_what_each_job_is_for() -> None:
    text = workflow()
    opening = text.split("\nname:")[0]
    assert opening.startswith("#") and len(opening.splitlines()) >= 8
    for name in _all():
        assert re.search(rf"(?m)^# - {re.escape(name)}\b", opening), f"the opening comment has no line for the job {name}"
    assert re.search(r"(?i)runner", opening), "and that the runner is the CI setup's to choose"


def test_tf5_95_the_lanes_are_the_ones_pyproject_names() -> None:
    comment = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    text = workflow()
    for mark in (PR_LANE, "-m math", "-m slow", "-m lane_j"):
        assert mark in comment and mark in text, mark


# ---------- TF5-96 ----------


def test_tf5_96_the_commands_and_the_module() -> None:
    assert PROJECT["scripts"] == {"poisson-trace": "poisson_trace.cli:main", "poisson-trace-import": "poisson_trace.ingest.cli:main"}
    assert (REPO / "src" / "poisson_trace" / "__main__.py").is_file()


def test_tf5_96_the_pythons_and_systems_declared() -> None:
    assert PROJECT["requires-python"] == ">=3.11,<3.14"
    classifiers = PROJECT["classifiers"]
    for wanted in ("Programming Language :: Python :: 3.11", "Programming Language :: Python :: 3.12", "Programming Language :: Python :: 3.13",
                   "Operating System :: MacOS", "Operating System :: POSIX :: Linux", "License :: OSI Approved :: MIT License", "Typing :: Typed"):
        assert wanted in classifiers, wanted
    assert not [c for c in classifiers if "Windows" in c or c.endswith(":: 3.14")]


def test_tf5_96_pyarrow_is_declared() -> None:
    import importlib.metadata

    declared = [d.replace(" ", "") for d in PROJECT["dependencies"] if d.replace(" ", "").startswith("pyarrow")]
    assert len(declared) == 1 and re.fullmatch(r"pyarrow>=\d+(?:\.\d+)*", declared[0]), PROJECT["dependencies"]
    installed = [r.replace(" ", "") for r in importlib.metadata.requires("poisson-trace") or [] if r.replace(" ", "").startswith("pyarrow")]
    assert installed == declared, installed
    floor = [int(n) for n in declared[0].removeprefix("pyarrow>=").split(".")]
    found = [int(n) for n in re.findall(r"\d+", importlib.metadata.version("pyarrow"))[:len(floor)]]
    assert found >= floor, importlib.metadata.version("pyarrow")


def test_every_dependency_is_declared_with_a_floor() -> None:
    """Each requirement of the package and of its extras names the oldest version it is run
    with, or one exact version: a bare name would let an install resolve to any version."""
    declared = [*PROJECT["dependencies"], *[d for extra in PROJECT["optional-dependencies"].values() for d in extra]]
    assert len(declared) >= 16, declared
    bare = [d for d in declared if not re.fullmatch(r"[A-Za-z0-9_.-]+(>=|==)\d+(\.\d+)*", d.replace(" ", ""))]
    assert not bare, f"declared with no floor: {bare}"


def test_tf5_96_the_description_is_not_the_one_of_one_source() -> None:
    assert not re.search(r"read from Prove's stored runs\.?$", PROJECT["description"]), PROJECT["description"]
    assert len(PROJECT["description"]) <= 200


def test_tf5_96_what_the_wheel_holds() -> None:
    build = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"]
    assert build["wheel"]["packages"] == ["src/poisson_trace"]
    assert (REPO / "src" / "poisson_trace" / "skills" / "poisson-trace-setup" / "SKILL.md").is_file()
    assert not (REPO / "src" / "poisson_trace" / "tools").exists() and (REPO / "tools" / "docs_check.py").is_file()


# ---------- TF5-97 ----------


def test_tf5_97_the_release_runs_the_same_lanes() -> None:
    release = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    for mark in (PR_LANE, "-m slow", "-m math", "ruff check src tests", "mypy --strict"):
        assert mark in release and mark in workflow(), mark


def test_the_release_runs_its_lanes_on_every_python_declared() -> None:
    """A release runs the lanes, and installs the built wheel alone, on each Python the package
    says it runs on, and each installs through constraints recorded for it: one exact version a
    line, Prove at the floor, and every package the package and its dev extra name."""
    release = jobs((REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8"))
    declared = {c.rsplit(" ", 1)[1] for c in PROJECT["classifiers"] if re.fullmatch(r"Programming Language :: Python :: 3\.\d+", c)}
    for job in ("lanes", "lane-j"):
        matrix = re.search(r"(?m)^        python: \[(.+)\]$", release[job])
        assert matrix, f"the {job} job has no list of Pythons"
        assert set(re.findall(r"3\.\d+", matrix.group(1))) == declared, (job, matrix.group(1))
    named = {re.split(r"[><=]", d.replace(" ", ""))[0].lower().replace("_", "-") for d in [*PROJECT["dependencies"], *PROJECT["optional-dependencies"]["dev"]]}
    (floor,) = [d.replace(" ", "").removeprefix("poisson-prove>=") for d in PROJECT["dependencies"] if d.startswith("poisson-prove")]
    for python in sorted(declared):
        path = REPO / ".github" / "release" / f"lanes-{python}.txt"
        assert path.is_file(), f"no constraints are recorded for Python {python}"
        lines = path.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith(f"# The packages the release lanes ran green with on Python {python} "), lines[0]
        held = [line for line in lines if not line.startswith("#")]
        assert held and all(re.fullmatch(r"[A-Za-z0-9_.-]+==\S+", line) for line in held), path.name
        assert [line for line in held if line.startswith("poisson-prove")] == [f"poisson-prove=={floor}"], path.name
        assert not [line for line in held if line.startswith("poisson-trace")], "Trace itself is left out"
        recorded = {line.split("==")[0].lower().replace("_", "-") for line in held}
        assert named <= recorded, f"{path.name} does not hold {sorted(named - recorded)}"


# ---------- the floors of numpy and scipy ----------

FLOORS = {name: d.replace(" ", "").removeprefix(f"{name}>=") for name in ("numpy", "scipy") for d in PROJECT["dependencies"]
          if re.fullmatch(rf"{name}>=\d+(\.\d+)*", d.replace(" ", ""))}


def _floors() -> str:
    """The one job that installs numpy at an exact version, and scipy beside it."""
    found = {name: text for name, text in _all().items() if re.search(r"pip install\b[^\n]*\bnumpy==", text)}
    assert len(found) == 1, f"one job installs numpy at an exact version: {sorted(found)}"
    (job,) = found.values()
    return job


def test_the_floors_cell_runs_on_main_and_every_night_and_never_on_a_pull_request() -> None:
    job = _floors()
    assert _never_on_a_pull_request(job), "a push to main, the night and a hand start"
    assert re.search(r"(?m)^  schedule:", triggers()) and re.search(r"(?m)^  workflow_dispatch:", triggers())
    assert _pythons(job) == {"3.11"}, "the oldest Python the package declares, where both floors install"


def test_the_floors_cell_reads_each_floor_from_pyproject() -> None:
    """The versions are the ones ``pyproject.toml`` declares, read from it by the job's own
    lines, so a floor that moves there moves the cell. Each line is run here as the job runs
    it, so a ``pyproject.toml`` the lines no longer read fails here and not on main alone."""
    assert sorted(FLOORS) == ["numpy", "scipy"], PROJECT["dependencies"]
    job = _floors()
    reads = dict(re.findall(r"(?m)^ +(numpy|scipy)=\$\((sed -n '[^'\n]+' pyproject\.toml)\)$", job))
    assert sorted(reads) == ["numpy", "scipy"], "each floor is read from pyproject.toml"
    for name, command in reads.items():
        ran = subprocess.run(shlex.split(command), cwd=REPO, capture_output=True, text=True, timeout=60)
        assert (ran.returncode, ran.stdout) == (0, FLOORS[name] + "\n"), (command, ran.stdout, ran.stderr)
    assert not re.search(r"\b(?:numpy|scipy)==\d", job), "no version of either is written in the job"
    for name in reads:
        assert re.search(rf'(?m)^ +test -n "\${name}"$', job), f"an empty reading of {name} stops the job, on a line of its own"


def test_the_floors_cell_installs_them_exactly_and_the_rest_as_the_lanes_do() -> None:
    job = _floors()
    made = re.search(r'(?m)^ +grep -v -i -E "\^\(numpy\|scipy\)==" \.github/release/lanes-3\.11\.txt > (\S+)$', job)
    assert made, "the constraints are those of lanes-3.11.txt with its numpy and scipy lines left out"
    install = re.search(r'(?m)^ +\.venv/bin/python -m pip install [^\n]*-c (\S+) -e "\.\[dev\]" "numpy==\$numpy" "scipy==\$scipy"$', job)
    assert install and install.group(1) == made.group(1), "the dev extra through them, numpy and scipy named exactly"
    assert not re.search(r"-c \.github/release/lanes-", job), "never through the whole file, which holds another numpy"
    assert re.search(r"(?m)^ +\.venv/bin/python -m pip check$", job)
    # the file holds one line for each of the two, written as the job's pattern reads them
    lines = (REPO / ".github" / "release" / "lanes-3.11.txt").read_text(encoding="utf-8").splitlines()
    assert sorted(line.split("==")[0] for line in lines if re.match(r"(?i)(numpy|scipy)==", line)) == ["numpy", "scipy"]


def test_the_floors_cell_checks_what_it_installed_before_any_lane() -> None:
    job = _floors()
    steps = re.split(r"(?m)^      - ", job)[1:]
    checks = [n for n, step in enumerate(steps) if "importlib.metadata.version" in step and re.search(r"\bassert\b", step)]
    assert checks, "a step compares the installed numpy and scipy with the floors"
    (compared,) = [line for line in steps[checks[0]].split("\n") if "importlib.metadata.version" in line]
    assert "|" not in compared, "the comparison is not piped: a pipe would hide its failure from the step"
    for name in ("numpy", "scipy"):
        assert re.search(rf"os\.environ\['{name.upper()}_FLOOR'\]", steps[checks[0]]), name
        assert re.search(rf'(?m)^ +echo "{name.upper()}_FLOOR=\${name}" >> "\$GITHUB_ENV"$', job), name
    lanes = [n for n, step in enumerate(steps) if PYTEST.search(step)]
    assert lanes and checks[0] < min(lanes), "before any lane runs"


def test_the_floors_cell_runs_the_four_lanes() -> None:
    lines = PYTEST.findall(_floors())
    for mark in (PR_LANE, "-m slow", "-m math", "-m lane_j"):
        assert [line for line in lines if line.endswith(f"{mark} tests")], f"the floors cell does not run {mark}"
    assert len(lines) == 4, lines
