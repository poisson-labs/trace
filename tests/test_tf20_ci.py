"""TF20-70 to TF20-74: the recipe in CI and in the docs check (spec section 17.6, "In CI"; section
8.4; the brief's rules 1 and 2).

- TF20-70: ``tools/docs_check.py`` lays each page's folder out with the committed examples
  beside the fixtures, as the docs runner does, and leaves nothing behind.
- TF20-71: the docs check passes the recipe's page with every connection that is not to this
  machine refused (the pull-request lane's twin of TF5-88, which checks every page in the slow
  lane).
- TF20-72: the clean-install job installs Tasks at its pin into the environment it made, and
  fetches Tasks' tokenizer file, after the install of Trace and before the socket guard; never
  an editable install. The docs check, which runs every block of the page and with it the
  byte-for-byte comparison of what ``generate`` writes, comes after the guard (TF5-94).
- TF20-73: the one pin of Tasks: the development extra holds it, and no other line of the
  repository's packaging names another version; the page, the provenance and the job name the
  same one; Prove is Trace's pin.
- TF20-74: the recipe's page and its folder are not in the wheel, and the folder is in the
  source archive; the folder holds no machine's path and nothing shaped like a key, by the
  release's own check.
- TF20-75: every job of ``ci.yml`` and ``release.yml`` that runs the pull-request or the slow
  lane fetches Tasks' tokenizer file into its environment after the development install and
  before the lane: the lanes run the recipe, and its first command needs that file.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

from tf5_support import REPO, check, jobs, read
from tf20_support import EXAMPLE, PAGE, PROVE_VERSION, PROVENANCE, TASKS_PIN, TASKS_VERSION

BIN = Path(sys.executable).parent
PROJECT = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))


def _env(extra: dict[str, str] | None = None) -> dict[str, str]:
    import os

    env = dict(os.environ, PATH=f"{BIN}{os.pathsep}{os.environ.get('PATH', '')}")
    for name in ("LANGSMITH_API_KEY", "BRAINTRUST_API_KEY", "WANDB_API_KEY", "CI", "VIRTUAL_ENV"):
        env.pop(name, None)
    env.update(extra or {})
    return env


def _guard(tmp: Path) -> tuple[Path, Path]:
    folder, log = tmp / "guard", tmp / "refused.log"
    folder.mkdir()
    (folder / "sitecustomize.py").write_text(
        "import socket\n"
        "_connect = socket.socket.connect\n"
        "def _guarded(self, address):\n"
        "    host = address[0] if isinstance(address, tuple) else address\n"
        "    if isinstance(host, str) and (host in ('localhost', '::1') or host.startswith('127.') or host.startswith('/')):\n"
        "        return _connect(self, address)\n"
        f"    open({str(log)!r}, 'a').write(repr(address) + '\\n')\n"
        "    raise OSError('the docs check reached for the network: ' + repr(address))\n"
        "socket.socket.connect = _guarded\n", encoding="utf-8")
    return folder, log


# ---------- TF20-70 ----------


def test_tf20_70_the_checker_copies_the_examples_beside_the_fixtures(tmp_path: Path) -> None:
    before = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True).stdout
    page = tmp_path / "page.md"
    page.write_text(
        "# A page\n\n<!-- command -->\n```\n"
        "test -f examples/three-tools/agent.py && test -f examples/three-tools/tasks/depth-d3.jsonl && test -f tests/fixtures/SHA256SUMS "
        "&& echo both && touch examples/three-tools/made-here\n```\n\n<!-- output exit=0 -->\n```\nboth\n```\n", encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    proc = check([page], cwd=tmp_path, env=_env({"HOME": str(home)}))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not (EXAMPLE / "made-here").exists(), "the page ran in the checkout's examples"
    assert subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True).stdout == before


# ---------- TF20-71 ----------


def test_tf20_71_the_docs_check_passes_the_recipe_with_no_network(tmp_path: Path) -> None:
    folder, log = _guard(tmp_path)
    empty, home = tmp_path / "empty", tmp_path / "home"
    empty.mkdir()
    home.mkdir()
    proc = check(["--summary", tmp_path / "summary.md", PAGE], cwd=empty, env=_env({"PYTHONPATH": str(folder), "HOME": str(home)}), timeout=1800)
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-6000:]
    assert not log.exists(), log.read_text(encoding="utf-8")
    assert re.match(r"ok  \d+ blocks held on 1 page", proc.stdout.strip().splitlines()[-1]), proc.stdout
    assert list(empty.iterdir()) == []
    assert not list(EXAMPLE.glob("prove-runs")) and not list(EXAMPLE.glob("*.xml")) and not (EXAMPLE / "trace.toml").exists(), \
        "nothing is written into the checkout's examples"


# ---------- TF20-72 ----------


def _steps(job: str) -> list[tuple[str, str]]:
    """The job's steps, each as (its name, its text)."""
    parts = re.split(r"(?m)^      - ", job)[1:]
    out = []
    for part in parts:
        name = re.match(r"name:\s*(.+)", part)
        out.append((name.group(1).strip() if name else "", part))
    return out


def test_tf20_72_the_clean_install_installs_tasks_and_its_tokenizer_before_the_guard() -> None:
    job = jobs()["clean-install"]
    steps = _steps(job)
    names = [name for name, _ in steps]

    def where(pattern: str) -> list[int]:
        return [i for i, (_, text) in enumerate(steps) if re.search(pattern, text)]

    trace_install = where(r"pip install[^\n]*dist/\*\.whl")
    tasks_install = where(rf'clean/bin/python"? -m pip install[^\n]*"?{re.escape(TASKS_PIN)}"?')
    tokenizer = where(r'clean/bin/poisson-tasks"? doctor --fix --yes|clean/bin/python"? -m poisson_tasks\.fetch_encoding')
    guard = [i for i, name in enumerate(names) if re.search(r"(?i)socket guard", name)]
    check_step = where(r"tools/docs_check\.py")
    assert trace_install and tasks_install and tokenizer and guard and check_step, names
    assert trace_install[0] <= tasks_install[0] <= tokenizer[0] < guard[0] < check_step[0], names
    for i in tasks_install:
        assert not re.search(r"pip install[^\n]*(?:\s-e\s|--editable)", steps[i][1])
    assert job.count(TASKS_PIN) == 1, "one install of Tasks, at its pin"


# ---------- TF20-73 ----------


def test_tf20_73_one_pin_of_tasks() -> None:
    dev = PROJECT["project"]["optional-dependencies"]["dev"]
    assert [d for d in dev if d.replace(" ", "").startswith("poisson-tasks")] == [TASKS_PIN]
    for extra, wanted in PROJECT["project"]["optional-dependencies"].items():
        if extra != "dev":
            assert not [d for d in wanted if "poisson-tasks" in d], extra
    assert not [d for d in PROJECT["project"]["dependencies"] if "poisson-tasks" in d], "Trace itself never needs Tasks"
    assert f"poisson-prove=={PROVE_VERSION}" in [d.replace(" ", "") for d in PROJECT["project"]["dependencies"]]
    for text in (read(PAGE), PROVENANCE.read_text(encoding="utf-8"), jobs()["clean-install"]):
        assert TASKS_VERSION in text
        for version in re.findall(r"poisson-tasks==(\S+?)[\"'\s]", text + " "):
            assert version == TASKS_VERSION, version


# ---------- TF20-74 ----------


def test_tf20_74_the_example_is_in_the_source_archive_and_not_the_wheel() -> None:
    build = PROJECT["tool"]["hatch"]["build"]["targets"]
    assert build["wheel"]["packages"] == ["src/poisson_trace"]
    excluded = build["sdist"].get("exclude", [])
    assert not [e for e in excluded if "examples" in e or "with-tasks-and-prove" in e], excluded
    assert not (REPO / "src" / "poisson_trace" / "examples").exists()


def test_tf20_74_the_example_holds_no_path_and_no_key() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("release_check", REPO / ".github" / "release" / "release_check.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    files = [path for path in sorted(EXAMPLE.rglob("*")) if path.is_file() and "__pycache__" not in path.parts]
    assert len(files) >= 8, "the example's files: two task files, the provenance, the agent, the wrapper, two spec files, the pytest file"
    for path in files:
        data = path.read_bytes()
        assert not module.PATHS.search(data), path.name
        assert not [m for m in module.KEYS.finditer(data) if not any(f in m.group(0) for f in module.FAKES)], path.name


# ---------- TF20-75 ----------


LANES = ('-m "not math and not lane_j and not slow"', "-m slow")
FETCH = re.compile(r"\.venv/bin/poisson-tasks doctor --fix --yes|\.venv/bin/python -m poisson_tasks\.fetch_encoding")
DEV = re.compile(r"\.venv/bin/python -m pip install[^\n]*-e \"\.\[dev\]\"")


def test_tf20_75_every_job_that_runs_the_lanes_fetches_the_tokenizer() -> None:
    seen = 0
    for workflow in ("ci.yml", "release.yml"):
        text = (REPO / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
        for name, job in jobs(text).items():
            runs = [job.find(lane) for lane in LANES if lane in job]
            if not runs:
                continue
            seen += 1
            installs = [m.end() for m in DEV.finditer(job)]
            fetches = [m.start() for m in FETCH.finditer(job)]
            assert installs and fetches, f"{workflow}: the job {name} runs the lanes and fetches no tokenizer file"
            assert max(installs) < min(fetches) < min(runs), f"{workflow}: {name} fetches it after the install and before the lane"
    assert seen >= 3, "the pull-request job, the full job and the release's lanes"
