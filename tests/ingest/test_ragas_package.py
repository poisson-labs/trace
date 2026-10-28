"""IR10, lane J: Ragas itself, at the pinned version, gives what section 3 says.

Deselected by default (``pyproject.toml`` adds ``-m "not lane_j"``); run with ``-m lane_j``. It
installs Ragas 0.4.3 from PyPI into a fresh environment with ``langchain-community`` 0.3.31
(Ragas 0.4.3 does not import beside ``langchain-community`` 0.4.2), or uses the interpreter named
by ``INT2_RAGAS_PYTHON`` when that already has both pinned versions. No model is called. Ragas
posts usage events to its own server unless ``RAGAS_DO_NOT_TRACK`` is ``true``; the tests set it,
and an audit hook in Ragas's process records and refuses every socket lookup and connection: there
must be none.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from poisson_prove.store import Store
from support import read_rows, run_import

pytestmark = pytest.mark.lane_j

PINS = {"ragas": "0.4.3", "langchain-community": "0.3.31"}

HOOK = """
import sys
_network = []
def _hook(event, args):
    if event in ("socket.getaddrinfo", "socket.connect", "socket.connect_ex"):
        _network.append(f"{event} {args!r}")
        raise OSError("lane J allows no network")
sys.addaudithook(_hook)
import atexit
atexit.register(lambda: open(sys.argv[1] + "/network.txt", "w").write("\\n".join(_network)))
import warnings
warnings.simplefilter("ignore")
"""

EVALUATE = (
    HOOK
    + """
from ragas import evaluate
from ragas.dataset_schema import EvaluationDataset, SingleTurnSample
from ragas.metrics import IDBasedContextPrecision, IDBasedContextRecall

out = sys.argv[1]
samples = [
    SingleTurnSample(user_input="all-found", retrieved_context_ids=["f1", "f2"], reference_context_ids=["f1", "f2"]),
    SingleTurnSample(user_input="half-found", retrieved_context_ids=["f1", "f9"], reference_context_ids=["f1", "f3"]),
    SingleTurnSample(user_input="none-retrieved", retrieved_context_ids=[], reference_context_ids=["f4"]),
]
result = evaluate(EvaluationDataset(samples=samples), metrics=[IDBasedContextRecall(), IDBasedContextPrecision()],
                  show_progress=False)
frame = result.to_pandas()
frame.to_json(out + "/scores.jsonl", orient="records", lines=True)
frame.to_csv(out + "/scores.csv", index=False)
frame.to_parquet(out + "/scores.parquet", index=False)
"""
)

EXPERIMENT = (
    HOOK
    + """
import asyncio
from ragas import Dataset, experiment

out, backend = sys.argv[1], sys.argv[2]
questions = Dataset(name="questions", backend=backend, root_dir=out)
for qid, value in (("q-a", 0.9), ("q-b", 0.2), ("q-c", None), ("q-d", float("nan")), ("q-raises", 0.7), ("q-e", 0.5)):
    questions.append({"qid": qid, "value": value})


@experiment()
async def judge(row):
    if row["qid"] == "q-raises":
        raise RuntimeError("the task raised")
    return {"qid": row["qid"], "judged": row["value"], "note": "judged " + row["qid"]}


asyncio.run(judge.arun(questions, name="version-1"))
"""
)


@pytest.fixture(scope="module")
def ragas_python(tmp_path_factory: pytest.TempPathFactory) -> str:
    python = os.environ.get("INT2_RAGAS_PYTHON")
    if not python:
        venv = tmp_path_factory.mktemp("venv-ragas")
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, timeout=600)
        python = str(venv / "bin" / "python")
        subprocess.run(
            [python, "-m", "pip", "install", "--quiet", *[f"{k}=={v}" for k, v in PINS.items()]],
            check=True,
            timeout=1800,
        )
    found = subprocess.run(
        [
            python,
            "-c",
            f"import importlib.metadata as m, json; print(json.dumps({{k: m.version(k) for k in {list(PINS)!r}}}))",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert json.loads(found) == PINS, found
    return python


def _run(python: str, script: str, tmp_path: Path, *args: str) -> Path:
    """The script in Ragas's environment, its home and its working directory under ``tmp_path``,
    usage tracking off; returns the directory it wrote to, after checking no socket was used."""
    out, home = tmp_path / "out", tmp_path / "home"
    out.mkdir()
    home.mkdir()
    (tmp_path / "script.py").write_text(script)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "RAGAS_DO_NOT_TRACK": "true",
        "TZ": "UTC",
    }
    proc = subprocess.run(
        [python, str(tmp_path / "script.py"), str(out), *args],
        cwd=out,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (out / "network.txt").read_text() == "", (out / "network.txt").read_text()
    return out


def _got(root: Path, run: str) -> dict[str, tuple[str | None, str | None, float | None]]:
    rows = read_rows(root, run)
    assert all(r["repeat"] == 0 for r in rows)
    return {r["case"]: (r["outcome"], r["error"], r["import"]["score"]) for r in rows}


def test_ir10_evaluate_gives_no_precision_where_nothing_was_retrieved_and_its_tables_import(
    tmp_path: Path, ragas_python: str
) -> None:
    out = _run(ragas_python, EVALUATE, tmp_path)
    written = [json.loads(line) for line in (out / "scores.jsonl").read_text().splitlines()]
    assert [(r["user_input"], r["id_based_context_precision"]) for r in written] == [
        ("all-found", 1.0),
        ("half-found", 0.5),
        ("none-retrieved", None),
    ]
    frames: dict[str, list[pd.DataFrame]] = {}
    for name in ("scores.jsonl", "scores.csv", "scores.parquet"):
        root = tmp_path / f"store-{name}"
        for run, metric, cut in (
            ("precision", "id_based_context_precision", "0.5"),
            ("recall", "id_based_context_recall", "1.0"),
        ):
            r = run_import(
                [
                    "ragas",
                    str(out / name),
                    "--store",
                    str(root),
                    "--run",
                    run,
                    "--metric",
                    metric,
                    "--cut",
                    cut,
                    "--below",
                    "--case-column",
                    "user_input",
                    "--started",
                    "2026-09-30T09:00:00Z",
                ]
            )
            assert r.code == 0, (name, r.text)
        assert _got(root, "precision") == {
            "all-found": ("met", None, 1.0),
            "half-found": ("met", None, 0.5),
            "none-retrieved": (None, "no score", None),
        }, name
        assert _got(root, "recall") == {
            "all-found": ("met", None, 1.0),
            "half-found": ("missed", None, 0.5),
            "none-retrieved": ("missed", None, 0.0),
        }, name
        frames[name] = [
            Store(root).read(run, meta=True, trace="none").drop(columns=["run_id"])
            for run in ("precision", "recall")
        ]
    for name in ("scores.csv", "scores.parquet"):
        for a, b in zip(frames["scores.jsonl"], frames[name], strict=True):
            pd.testing.assert_frame_equal(a, b, check_exact=True, obj=name)


@pytest.mark.parametrize(
    "backend,suffix,missing", [("local/csv", "csv", "nan"), ("local/jsonl", "jsonl", "NaN")]
)
def test_ir10_an_experiment_file_ragas_writes_imports_by_its_own_columns(
    tmp_path: Path, ragas_python: str, backend: str, suffix: str, missing: str
) -> None:
    """An ``@experiment`` file: the function's own columns, the rows in the order they finished,
    the row whose task raised left out; a NaN written as Ragas's backend writes it."""
    out = _run(ragas_python, EXPERIMENT, tmp_path, backend)
    f = out / "experiments" / f"version-1.{suffix}"
    text = f.read_text()
    assert "q-raises" not in text and missing in text, text
    root = tmp_path / "store"
    r = run_import(
        [
            "ragas",
            str(f),
            "--store",
            str(root),
            "--run",
            "v1",
            "--metric",
            "judged",
            "--cut",
            "0.5",
            "--below",
            "--case-column",
            "qid",
            "--json",
        ]
    )
    assert r.code == 0, r.text
    assert _got(root, "v1") == {
        "q-a": ("met", None, 0.9),
        "q-b": ("missed", None, 0.2),
        "q-c": (None, "no score", None),
        "q-d": (None, "no score", None),
        "q-e": ("met", None, 0.5),
    }
    summary: dict[str, Any] = r.json()
    assert (summary["rows"], summary["no_outcome"]) == (5, {"no score": 2})
