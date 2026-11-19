"""PF-60 to PF-79: the floor in CI, in the release and in a clean install (PV-8, PV-15;
``pf_support``'s opening, item 7).

- PF-60: ``ci.yml`` has one job that installs the newest ``poisson-prove`` on the package index
  over the Prove the lanes were last green with, says which it got, and runs the pull-request
  lane. It runs on main and every night and never on a pull request.
- PF-61: every other lane runs at the floor: the constraints the lanes install through,
  ``.github/release/lanes-3.11.txt`` and ``lanes-3.12.txt``, each hold ``poisson-prove==`` the
  floor and no other Prove.
- PF-62: the release check holds the declaration's shape: a floor with no cap passes; an exact
  pin, a capped range, a bare name and a wheel that requires another Prove do not.
- PF-63: the release workflow asks for no exact Prove: its clean install checks the Prove it
  brought is at or above the floor, and it still runs lane J's clean-install test by its name.
- PF-64: no job of either workflow installs a Prove below the floor or names the exact pin the
  floor replaced.
- PF-70 (lane J): the wheel built from this tree installs beside the floor itself, with nothing
  else asked for, and Trace then reads the store the floor made and the store 0.1.3 made, saves
  into one, and ``doctor`` is ready.
- PF-71 (lane J): the wheel does not install beside a Prove below the floor: pip refuses the
  pair, naming both requirements.
- PF-72 (lane J): installed by one line with nothing named, the wheel brings a Prove at or above
  the floor (the newest the index serves), ``pip check`` is clean, and Trace reads both stores.
- PF-73: what lane J reads is declared without it: the installed package's own metadata holds
  the floor, as the wheel's would.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any

import pytest
from pf_support import EVENT, NAMES, REPO, RUNS, STORE_1_0, STORE_1_2
from pin_support import FORMAT_1_0, RECORDED, REQUIREMENT, at_or_above_the_floor
from tf5_support import jobs

WORKFLOWS = REPO / ".github" / "workflows"
CI = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
RELEASE = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
PR_LANE = 'env -u CI .venv/bin/python -m pytest -n auto -q -p no:cacheprovider -m "not math and not lane_j and not slow" tests'
#: A pip line that upgrades Prove to whatever is newest: no version, no range, no constraints file.
NEWEST = re.compile(r"pip install(?=[^\n]*(?:\s--upgrade\b|\s-U\b))[^\n]*[\s\"']poisson-prove[\"']?(?=\s|$)(?![^\n]*\s-c\s)")
A_PROVE = re.compile(r"poisson[-_]prove\s*(==|>=|<=|~=|<|>|!=)\s*([0-9][\w.]*)")
BELOW = "0.3.0"


def _steps(job: str) -> list[str]:
    return re.split(r"(?m)^      - ", job)[1:]


# ---------- PF-60 ----------


def _newest_jobs() -> dict[str, str]:
    return {name: job for name, job in jobs(CI).items() if NEWEST.search(job)}


def test_pf_60_one_job_installs_the_newest_prove() -> None:
    found = _newest_jobs()
    assert len(found) == 1, sorted(found)
    (job,) = found.values()
    assert len(NEWEST.findall(job)) == 1, "one upgrade, of Prove alone"
    (line,) = [line for line in job.split("\n") if NEWEST.search(line)]
    assert not A_PROVE.search(line) and not re.search(r"\s-c\s|--constraint", line), line
    assert not re.search(r"(?:--upgrade|-U)\b[^\n]*\s(?!poisson-prove)[a-z][\w.-]*\s*$", line.replace('"', "")), "nothing else is upgraded with it"


def test_pf_60_it_runs_the_pull_request_lane_on_it_in_order() -> None:
    (job,) = _newest_jobs().values()
    steps = _steps(job)

    def where(pattern: str) -> list[int]:
        return [i for i, text in enumerate(steps) if re.search(pattern, text)]

    dev = where(r'\.venv/bin/python -m pip install[^\n]*-c \.github/release/lanes-3\.1[12]\.txt[^\n]*-e "\.\[dev\]"')
    upgrade = where(NEWEST.pattern)
    said = where(r"\.venv/bin/poisson-trace --version")
    tokenizer = where(r"\.venv/bin/poisson-tasks doctor --fix --yes|\.venv/bin/python -m poisson_tasks\.fetch_encoding")
    lane = [i for i, text in enumerate(steps) if PR_LANE in text]
    assert dev and upgrade and said and tokenizer and lane, [text.split("\n")[0] for text in steps]
    # the lanes' own install first, the newest Prove over it, which Prove that is, the tokenizer, then the lane
    assert max(dev) < min(upgrade) <= min(said) and min(upgrade) < min(tokenizer) < min(lane), [text.split("\n")[0] for text in steps]
    # the version is printed after the upgrade, in that step or a later one
    text = steps[min(said)]
    if min(said) == min(upgrade):
        assert text.index("poisson-trace --version") > NEWEST.search(text).start()  # type: ignore[union-attr]
    assert len(lane) == 1 and "pytest" not in "".join(steps[: lane[0]])


def test_pf_60_it_runs_on_main_and_every_night_and_never_on_a_pull_request() -> None:
    (job,) = _newest_jobs().values()
    assert re.search(r"(?m)^    if: github\.event_name != 'pull_request'$", job), job[:400]
    head = CI[: CI.index("\njobs:")]
    assert re.search(r"(?m)^  schedule:\n    - cron: ", head) and re.search(r"(?m)^  push:\n    branches: \[main\]", head)
    assert re.search(r'python-version: "3\.1[12]"', job), "a Python the lanes have constraints for"
    assert re.search(r"(?m)^    runs-on: \S+$", job) and re.search(r"(?m)^    timeout-minutes: \d+$", job)


# ---------- PF-61 ----------


@pytest.mark.parametrize("python", ["3.11", "3.12"])
def test_pf_61_the_lanes_constraints_hold_the_floor(python: str) -> None:
    from pf_pins import main_text

    name = f".github/release/lanes-{python}.txt"
    lines = (REPO / name).read_text(encoding="utf-8").splitlines()
    assert [line for line in lines if re.match(r"poisson[-_]prove\b", line)] == [f"poisson-prove=={RECORDED}"]
    # every other line is main's: the lanes move the one package
    was = main_text(name).splitlines()
    assert [line for line in was if re.match(r"poisson[-_]prove\b", line)] == [f"poisson-prove=={FORMAT_1_0}"]
    assert [line for line in lines if not line.startswith("poisson-prove")] == [line for line in was if not line.startswith("poisson-prove")]
    assert len(lines) == len(was)


def test_pf_61_the_pull_request_lane_installs_through_them() -> None:
    held = jobs(CI)
    assert re.search(r'-c \.github/release/lanes-3\.11\.txt -e "\.\[dev\]"', held["pull-request"])
    assert PR_LANE in held["pull-request"] and not NEWEST.search(held["pull-request"])
    assert re.search(r'-c \.github/release/lanes-3\.12\.txt -e "\.\[dev\]"', held["lane-j"])


# ---------- PF-62 ----------


def _release_check() -> Any:
    spec = importlib.util.spec_from_file_location("release_check_pf", REPO / ".github" / "release" / "release_check.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dist(folder: Path, project: dict[str, Any], requires: list[str] | None = None) -> Path:
    """A wheel and a source archive of the project as declared, holding its metadata and one
    module: what ``check dist`` reads of them."""
    version = project["version"]
    stem = f"poisson_trace-{version}"
    meta = "".join(f"{key}: {value}\n" for key, value in (
        ("Metadata-Version", "2.4"), ("Name", "poisson-trace"), ("Version", version),
        *[("Requires-Dist", r) for r in (project["dependencies"] if requires is None else requires)]))
    folder.mkdir(parents=True)
    with zipfile.ZipFile(folder / f"{stem}-py3-none-any.whl", "w") as zf:
        zf.writestr("poisson_trace/__init__.py", f'__version__ = "{version}"\n')
        zf.writestr(f"{stem}.dist-info/METADATA", meta)
    with tarfile.open(folder / f"{stem}.tar.gz", "w:gz") as tf:
        for name, text in ((f"{stem}/PKG-INFO", meta), (f"{stem}/src/poisson_trace/__init__.py", f'__version__ = "{version}"\n')):
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return folder


def _declared(prove: str | None) -> dict[str, Any]:
    doc = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    others = [d for d in doc["project"]["dependencies"] if not re.match(r"\s*poisson[-_.]prove\b", d, re.IGNORECASE)]
    doc["project"]["dependencies"] = others if prove is None else [*others, prove]
    return doc


def test_pf_62_the_release_check_passes_the_floor(tmp_path: Path) -> None:
    check = _release_check()
    doc = _declared(REQUIREMENT)
    check.pyproject = lambda: doc
    assert check.check_dist(_dist(tmp_path / "dist", doc["project"])) == []
    # and the tree's own declaration is that one
    assert tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"].count(REQUIREMENT) == 1


@pytest.mark.parametrize("prove", [f"poisson-prove=={RECORDED}", f"poisson-prove>={RECORDED},<1", f"poisson-prove>={RECORDED},!=0.5.0",
                                   f"poisson-prove~={RECORDED}", "poisson-prove", f"poisson-prove<={RECORDED}", None])
def test_pf_62_the_release_check_refuses_any_other_shape(tmp_path: Path, prove: str | None) -> None:
    check = _release_check()
    doc = _declared(prove)
    check.pyproject = lambda: doc
    problems = check.check_dist(_dist(tmp_path / "dist", doc["project"]))
    assert problems and any("poisson-prove" in p for p in problems), problems


def test_pf_62_the_release_check_refuses_a_wheel_that_requires_another_prove(tmp_path: Path) -> None:
    check = _release_check()
    doc = _declared(REQUIREMENT)
    check.pyproject = lambda: doc
    others = [d for d in doc["project"]["dependencies"] if d != REQUIREMENT]
    for built in ([*others, f"poisson-prove=={FORMAT_1_0}"], [*others, f"poisson-prove>={BELOW}"], others):
        problems = check.check_dist(_dist(tmp_path / f"dist-{len(built)}-{built[-1][-5:]}", doc["project"], built))
        assert problems and any("Prove" in p for p in problems), (built, problems)


# ---------- PF-63 ----------


def test_pf_63_the_release_asks_for_no_exact_prove() -> None:
    for name, job in jobs(RELEASE).items():
        assert not re.search(r"version\('poisson-prove'\)\s*==", job), name
        assert not [m.group(0) for m in A_PROVE.finditer(job) if m.group(1) == "=="], name
    clean = [job for job in jobs(RELEASE).values() if "dist/*.whl" in job and "pip check" in job]
    assert clean, "the job that installs the built wheel alone"
    for job in clean:
        if "version('poisson-prove')" in job:
            assert re.search(r">=\s*\(0, 4, 0\)", job), "the Prove it brought is at or above the floor"
    assert "tests/test_pf_ci.py::test_pf_72_installed_by_one_line_the_wheel_brings_a_prove_at_or_above_the_floor" in RELEASE


def test_pf_63_the_release_names_the_tests_it_runs_and_they_are_there() -> None:
    for node in re.findall(r"tests/[\w/]+\.py::\w+", RELEASE):
        path, _, name = node.partition("::")
        assert f"def {name}(" in (REPO / path).read_text(encoding="utf-8"), node


# ---------- PF-64 ----------


@pytest.mark.parametrize("workflow", ["ci.yml", "release.yml"])
def test_pf_64_no_job_installs_a_prove_below_the_floor(workflow: str) -> None:
    text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    for found in A_PROVE.finditer(text):
        assert at_or_above_the_floor(found.group(2)), found.group(0)
    assert FORMAT_1_0 not in "\n".join(line for line in text.split("\n") if "prove" in line.lower()), workflow


# ---------- PF-70 to PF-72 (lane J) ----------


def _built(tmp: Path) -> tuple[Path, Path]:
    """A fresh environment and the wheel built from this tree; nothing installed yet."""
    venv = tmp / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, timeout=600)
    wheels = tmp / "wheels"
    subprocess.run([str(venv / "bin" / "python"), "-m", "pip", "wheel", "--quiet", "--no-deps", "--wheel-dir", str(wheels), str(REPO)],
                   check=True, timeout=1800)
    (wheel,) = wheels.glob("poisson_trace-*.whl")
    return venv, wheel


def _prove_of(venv: Path) -> str:
    found = subprocess.run([str(venv / "bin" / "python"), "-c", "import importlib.metadata as m; print(m.version('poisson-prove'))"],
                           capture_output=True, text=True, check=True, timeout=120)
    return found.stdout.strip()


def _reads_both_stores(venv: Path, tmp: Path, prove: str) -> None:
    env = {**os.environ, "HOME": str(tmp / "home"), "NO_COLOR": "1"}
    env.pop("CI", None)
    (tmp / "home").mkdir()

    def trace(*argv: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(venv / "bin" / "poisson-trace"), *argv], capture_output=True, text=True, env=env, cwd=tmp, timeout=300)

    said = trace("--version")
    assert said.returncode == 0 and f"(poisson-prove {prove}, Python " in said.stdout, said
    for source, name in ((STORE_1_2, "floor"), (STORE_1_0, "kept")):
        store = shutil.copytree(source, tmp / name)
        for argv in (["runs", "--store", str(store)], ["fix-check", *NAMES, "--store", str(store), *EVENT, "--inputs", "all", "--max-mde", "0.5"],
                     ["where", RUNS[source][1], "--store", str(store), *EVENT, "--save"]):
            ran = trace(*argv)
            assert ran.returncode == 0, (argv, ran.stdout + ran.stderr)
            assert "pip install" not in ran.stdout + ran.stderr, ran
    made = trace("init", "--store", "floor", *EVENT, "--yes")
    assert made.returncode == 0, made.stdout + made.stderr
    ready = trace("doctor", "--json")
    assert ready.returncode == 0, ready.stdout + ready.stderr
    (check,) = [c for c in json.loads(ready.stdout)["checks"] if c["name"] == "prove"]
    assert check["ok"] is True and check["line"].startswith(f"poisson-prove {prove} "), check


@pytest.mark.lane_j
def test_pf_70_the_wheel_installs_beside_the_floor_itself(tmp_path: Path) -> None:
    """Lane J: reads PyPI. The wheel and ``poisson-prove==`` the floor, installed by one line:
    pip resolves the pair, the floor is what is installed, and Trace reads through it."""
    venv, wheel = _built(tmp_path)
    python = str(venv / "bin" / "python")
    subprocess.run([python, "-m", "pip", "install", "--quiet", str(wheel), f"poisson-prove=={RECORDED}"], check=True, timeout=1800)
    assert _prove_of(venv) == RECORDED
    assert subprocess.run([python, "-m", "pip", "check"], capture_output=True, timeout=300).returncode == 0
    _reads_both_stores(venv, tmp_path, RECORDED)


@pytest.mark.lane_j
def test_pf_71_the_wheel_does_not_install_beside_a_prove_below_the_floor(tmp_path: Path) -> None:
    """Lane J: reads PyPI. pip refuses the wheel with a Prove below the floor named beside it,
    and installs neither."""
    venv, wheel = _built(tmp_path)
    python = str(venv / "bin" / "python")
    ran = subprocess.run([python, "-m", "pip", "install", str(wheel), f"poisson-prove=={BELOW}"], capture_output=True, text=True, timeout=1800)
    assert ran.returncode != 0, ran.stdout[-2000:]
    said = ran.stdout + ran.stderr
    assert f"poisson-prove>={RECORDED}" in said and f"poisson-prove=={BELOW}" in said, said[-3000:]
    listed = subprocess.run([python, "-m", "pip", "list", "--format=json"], capture_output=True, text=True, check=True, timeout=300)
    assert not [p for p in json.loads(listed.stdout) if p["name"].replace("_", "-") in ("poisson-trace", "poisson-prove")], listed.stdout


@pytest.mark.lane_j
def test_pf_72_installed_by_one_line_the_wheel_brings_a_prove_at_or_above_the_floor(tmp_path: Path) -> None:
    """Lane J: reads PyPI. With no Prove named, pip brings the newest the index serves, there
    being no cap; whatever that is, it is at or above the floor and Trace reads through it."""
    venv, wheel = _built(tmp_path)
    python = str(venv / "bin" / "python")
    with zipfile.ZipFile(wheel) as zf:
        (meta,) = [n for n in zf.namelist() if n.endswith(".dist-info/METADATA")]
        requires = [line.split(":", 1)[1].strip().replace(" ", "") for line in zf.read(meta).decode("utf-8").splitlines()
                    if line.startswith("Requires-Dist:")]
    assert [r for r in requires if re.match(r"poisson[-_.]prove\b", r, re.IGNORECASE)] == [REQUIREMENT], requires
    subprocess.run([python, "-m", "pip", "install", "--quiet", str(wheel)], check=True, timeout=1800)
    brought = _prove_of(venv)
    assert at_or_above_the_floor(brought), brought
    assert subprocess.run([python, "-m", "pip", "check"], capture_output=True, timeout=300).returncode == 0
    _reads_both_stores(venv, tmp_path, brought)


# ---------- PF-73 ----------


def test_pf_73_the_installed_package_declares_the_floor_as_the_wheel_would() -> None:
    import importlib.metadata

    requires = [r.replace(" ", "") for r in importlib.metadata.requires("poisson-trace") or []]
    prove = [r for r in requires if re.match(r"poisson[-_.]prove\b", r, re.IGNORECASE)]
    assert prove == [REQUIREMENT], requires
    assert at_or_above_the_floor(importlib.metadata.version("poisson-prove"))
