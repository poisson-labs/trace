"""ID12, lane J: DeepEval itself, at the pinned version, writes what section 3 says.

Deselected by default (``pyproject.toml`` adds ``-m "not lane_j"``); run with ``-m lane_j``. It
installs DeepEval from PyPI into a fresh environment, or uses the interpreter named by
``INT1_DEEPEVAL_PYTHON`` when that already has the pinned version. No model is called.
"""

from __future__ import annotations

import glob
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from support import read_rows, run_import

pytestmark = pytest.mark.lane_j

DEEPEVAL = "4.2.6"

SCRIPT = '''
import importlib
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase
from deepeval.evaluate.configs import AsyncConfig, CacheConfig, DisplayConfig, ErrorConfig

evaluate = importlib.import_module("deepeval.evaluate.evaluate").evaluate


class TestsPassed(BaseMetric):
    def __init__(self, threshold=1.0):
        self.threshold = threshold
        self.async_mode = False

    def measure(self, test_case, *args, **kwargs):
        if test_case.actual_output == "raise":
            raise RuntimeError("the metric raised")
        self.score = 1.0 if test_case.actual_output == "passed" else 0.0
        self.success = self.score >= self.threshold
        self.reason = test_case.actual_output
        return self.score

    async def a_measure(self, test_case, *args, **kwargs):
        return self.measure(test_case)

    def is_successful(self):
        return self.success

    @property
    def __name__(self):
        return "Tests Passed"


cases = [
    LLMTestCase(name=name, input=f"the question {name}", actual_output=out, expected_output="passed")
    for name, out in (("met", "passed"), ("missed", "failed"), ("raised", "raise"))
]
evaluate(
    test_cases=cases, metrics=[TestsPassed()], identifier="lane-j",
    display_config=DisplayConfig(print_results=False, show_indicator=False),
    cache_config=CacheConfig(write_cache=False, use_cache=False),
    async_config=AsyncConfig(run_async=False),
    error_config=ErrorConfig(ignore_errors=True),
)
'''


@pytest.fixture(scope="module")
def deepeval_python(tmp_path_factory: pytest.TempPathFactory) -> str:
    python = os.environ.get("INT1_DEEPEVAL_PYTHON")
    if not python:
        venv = tmp_path_factory.mktemp("venv-deepeval")
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, timeout=600)
        python = str(venv / "bin" / "python")
        subprocess.run([python, "-m", "pip", "install", "--quiet", f"deepeval=={DEEPEVAL}"], check=True, timeout=1800)
    found = subprocess.run(
        [python, "-c", "import importlib.metadata as m; print(m.version('deepeval'))"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert found == DEEPEVAL, found
    return python


def _snapshot(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def test_id12_deepeval_writes_what_the_reader_reads(tmp_path: Path, deepeval_python: str) -> None:
    work, home = tmp_path / "work", tmp_path / "home"
    work.mkdir()
    home.mkdir()
    script = tmp_path / "evaluate_three.py"
    script.write_text(SCRIPT)
    before = _snapshot(tmp_path)
    env = {
        "PATH": os.environ.get("PATH", ""), "HOME": str(home), "DEEPEVAL_TELEMETRY_OPT_OUT": "YES",
        "DEEPEVAL_RESULTS_FOLDER": str(work / "results"), "TZ": "UTC",
    }
    proc = subprocess.run([deepeval_python, str(script)], cwd=work, env=env, capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    after = _snapshot(tmp_path)
    assert {k: v for k, v in after.items() if k in before} == before
    new = sorted(set(after) - set(before))
    outside = [p for p in new if not (p.startswith("work/results/") or p.startswith("work/.deepeval/"))]
    assert outside == [], outside
    written = glob.glob(str(work / "results" / "test_run_*.json"))
    assert len(written) == 1, new
    root = tmp_path / "store"
    r = run_import(["deepeval", written[0], "--store", str(root), "--run", "lane-j", "--metric", "Tests Passed",
                    "--cut", "recorded", "--case", "name"])
    assert r.code == 0, r.text
    got = {row["case"]: (row["outcome"], row["error"]) for row in read_rows(root, "lane-j")}
    assert got == {"met": ("met", None), "missed": ("missed", None), "raised": (None, "no score")}
