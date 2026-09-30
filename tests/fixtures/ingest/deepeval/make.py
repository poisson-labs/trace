"""Rebuild the two DeepEval result files beside this script from Trace's HumanEval fixture pair.

Each stored row of ``tests/fixtures/humaneval`` becomes one DeepEval test case named
``<task_id>@<temperature>``, scored by a custom metric ``Tests Passed`` (1.0 when the stored
sandbox result was ``passed``, threshold 1.0), and DeepEval's own ``evaluate()`` writes the result
file with ``DEEPEVAL_RESULTS_FOLDER`` set. The file DeepEval wrote is gzipped as it is, with a
fixed gzip header (no name, mtime 0), so the gzip adds nothing that varies.

Three steps, because the rows are read through Prove and the file is written by DeepEval, and
the two need not share an environment:

    python make.py rows WORK                 # proofload importable: the pair's rows as JSON
    python make.py deepeval WORK             # deepeval 4.2.6 importable: one result file per run
    python make.py gzip WORK DEST            # each result file, gzipped, into DEST
    python make.py compare FILE FILE         # equal but for DeepEval's timings

DeepEval records wall-clock timings (``runDuration``) in the file, so a rebuild is equal to the
committed files in every value but those, and ``compare`` says so; the digests in
``SHA256SUMS`` are of the files as committed.
"""

from __future__ import annotations

import glob
import gzip
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
HUMANEVAL = HERE.parent.parent / "humaneval"
RUNS = (("a", "20260905T185407Z-0313"), ("b", "20260905T195009Z-18ac"))
METRIC = "Tests Passed"
DEEPEVAL = "4.2.6"
TIMINGS = ("runDuration",)


def rows(work: Path) -> None:
    from proofload.store import Store

    store = Store(HUMANEVAL)
    work.mkdir(parents=True, exist_ok=True)
    for label, run in RUNS:
        frame = store.read(run, meta=False, trace="none")
        out = [
            {
                "task_id": config["task_id"],
                "temperature": config["temperature"],
                "outcome": outcome,
            }
            for config, outcome in zip(frame["config"], frame["outcome"], strict=True)
        ]
        (work / f"rows-{label}.json").write_text(json.dumps(out) + "\n")
        print(f"{run}: {len(out)} rows -> rows-{label}.json")


def deepeval(work: Path) -> None:
    os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"
    import deepeval as package
    from deepeval.evaluate.configs import AsyncConfig, CacheConfig, DisplayConfig
    from deepeval.metrics import BaseMetric
    from deepeval.test_case import LLMTestCase

    if package.__version__ != DEEPEVAL:
        raise SystemExit(f"deepeval {DEEPEVAL} is required, found {package.__version__}")
    # ``from deepeval import evaluate`` is a function that shadows the module of that name
    evaluate = importlib.import_module("deepeval.evaluate.evaluate").evaluate

    class TestsPassed(BaseMetric):  # type: ignore[misc]
        def __init__(self, threshold: float = 1.0) -> None:
            self.threshold = threshold
            self.async_mode = False

        def measure(self, test_case: Any, *args: Any, **kwargs: Any) -> float:
            self.score = 1.0 if test_case.actual_output == "passed" else 0.0
            self.success = self.score >= self.threshold
            self.reason = test_case.actual_output
            return self.score

        async def a_measure(self, test_case: Any, *args: Any, **kwargs: Any) -> float:
            return self.measure(test_case)

        def is_successful(self) -> bool:
            return bool(self.success)

        @property
        def __name__(self) -> str:  # type: ignore[override]
            return METRIC

    for label, _ in RUNS:
        folder = work / f"results-{label}"
        os.environ["DEEPEVAL_RESULTS_FOLDER"] = str(folder)
        stored = json.loads((work / f"rows-{label}.json").read_text())
        cases = [
            LLMTestCase(
                name=f"{r['task_id']}@{r['temperature']}",
                input=f"{r['task_id']} at temperature {r['temperature']}",
                actual_output=r["outcome"],
                expected_output="passed",
            )
            for r in stored
        ]
        evaluate(
            test_cases=cases,
            metrics=[TestsPassed()],
            identifier=f"humaneval-{label}",
            display_config=DisplayConfig(print_results=False, show_indicator=False),
            cache_config=CacheConfig(write_cache=False, use_cache=False),
            async_config=AsyncConfig(run_async=False),
        )
        written = sorted(glob.glob(str(folder / "test_run_*.json")))
        print(f"humaneval-{label}: {len(cases)} test cases -> {written}")


def gzip_files(work: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for label, _ in RUNS:
        (source,) = sorted((work / f"results-{label}").glob("test_run_*.json"))
        raw = source.read_bytes()
        target = dest / f"humaneval-{label}.json.gz"
        with open(target, "wb") as handle:
            with gzip.GzipFile(filename="", mode="wb", fileobj=handle, compresslevel=9, mtime=0) as z:
                z.write(raw)
        print(
            f"{source.name} sha256 {hashlib.sha256(raw).hexdigest()} ({len(raw)} bytes) -> "
            f"{target.name} sha256 {hashlib.sha256(target.read_bytes()).hexdigest()}"
        )


def _load(path: Path) -> Any:
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    return json.loads(raw)


def _without_timings(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _without_timings(v) for k, v in value.items() if k not in TIMINGS}
    if isinstance(value, list):
        return [_without_timings(v) for v in value]
    return value


def compare(first: Path, second: Path) -> int:
    a, b = _without_timings(_load(first)), _without_timings(_load(second))
    for key in sorted(set(a) | set(b)):
        if a.get(key) != b.get(key):
            print(f"differ at {key!r}")
            return 1
    print(f"equal but for {', '.join(TIMINGS)}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "rows":
        rows(Path(argv[1]))
    elif len(argv) == 2 and argv[0] == "deepeval":
        deepeval(Path(argv[1]))
    elif len(argv) == 3 and argv[0] == "gzip":
        gzip_files(Path(argv[1]), Path(argv[2]))
    elif len(argv) == 3 and argv[0] == "compare":
        return compare(Path(argv[1]), Path(argv[2]))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
