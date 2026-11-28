"""What the tests of portable numbers share.

Every number Trace computes for a document, a report, a table or a page is computed with
arithmetic that gives the same bits on every platform: IEEE basic operations one at a time,
``math.fsum``, integers and fractions, ``decimal`` with an explicit context, the numpy
operations that are one IEEE operation per element, and the functions of
``poisson_trace.stats.portable``. No scipy, no transcendental function of numpy or ``math``, no
``**`` on a float, no BLAS reduction and no float reduction whose order belongs to numpy.

This module holds:

- the modules that compute those numbers (``NUMBER_MODULES``), and the modules that call numpy or
  ``math`` and write no number Trace prints, each with its reason (``EXEMPT``);
- the seeded inputs the golden table and the accuracy tests read;
- ``entries()``, every value of the golden table, computed by the installed build.
  ``tests/fixtures/portable/make_golden.py`` writes it to ``GOLDEN``, and
  ``tests/test_portable_golden.py`` recomputes it and requires the same bits.
"""

from __future__ import annotations

import json
import math
import random
import tempfile
from pathlib import Path
from typing import Any

from conftest import FIXTURES

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "poisson_trace"
PORTABLE = FIXTURES / "portable"
GOLDEN = PORTABLE / "golden.json"

#: The modules whose arithmetic reaches a document, a report, a table, a page or a verdict,
#: as paths under ``src/poisson_trace``.
NUMBER_MODULES: tuple[str, ...] = (
    "api.py",
    "config.py",
    "core.py",
    "pages.py",
    "paired.py",
    "report.py",
    "saved.py",
    "setup.py",
    "stats/continuous.py",
    "stats/portable.py",
    "steps.py",
    "summary.py",
    "survival.py",
)

#: Modules that the commands import and that call numpy, scipy or ``math``, but write no number
#: to a document, a report, a table or a page. Each line says why.
EXEMPT: dict[str, str] = {
    # the readers turn another tool's export into a stored run: they check that a value is a
    # finite number (math.isfinite, math.isnan) and copy it, and add token and cost counts with
    # math.fsum, which is exact; the commands then read the stored run
    "ingest/braintrust.py": "a reader of Braintrust exports",
    "ingest/cut.py": "a reader's cut of a stored run",
    "ingest/deepeval.py": "a reader of DeepEval results",
    "ingest/inspect.py": "a reader of Inspect logs",
    "ingest/junit.py": "a reader of JUnit files",
    "ingest/langsmith.py": "a reader of LangSmith exports",
    "ingest/openai_evals.py": "a reader of OpenAI Evals logs",
    "ingest/promptfoo.py": "a reader of promptfoo results",
    "ingest/prove.py": "a reader of Prove's run files",
    "ingest/ragas.py": "a reader of Ragas results",
    "ingest/rows.py": "a reader's rows of a table",
    "ingest/table.py": "a reader of tables",
    "ingest/tabular.py": "a reader of CSV and Parquet tables",
    "ingest/taxonomy.py": "a reader's failure kinds",
    "ingest/verdicts.py": "a reader of grades files",
    "ingest/weave.py": "a reader of Weave exports",
}

# The seeds of the inputs below. The generators use only ``random.random`` and ``randint`` and
# basic arithmetic, which give the same values on every platform.
COUNT_SEED = 20261127
CELL_SEED = 20261128
SAMPLE_SEED = 20261129


def count_tables() -> list[list[tuple[int, int, int, int]]]:
    """400 seeded tables of per-input counts ``(failed_old, runs_old, failed_new, runs_new)``:
    3 to 60 inputs, 1 to 8 tries per arm, the new rate within 0.3 of the old."""
    rng = random.Random(COUNT_SEED)
    tables = []
    for _ in range(400):
        rows = []
        for _ in range(rng.randint(3, 60)):
            runs_old, runs_new = rng.randint(1, 8), rng.randint(1, 8)
            rate_old = rng.random()
            rate_new = min(1.0, max(0.0, rate_old + rng.uniform(-0.3, 0.3)))
            failed_old = sum(1 for _ in range(runs_old) if rng.random() < rate_old)
            failed_new = sum(1 for _ in range(runs_new) if rng.random() < rate_new)
            rows.append((failed_old, runs_old, failed_new, runs_new))
        tables.append(rows)
    return tables


def counts(table: list[tuple[int, int, int, int]]) -> list[Any]:
    from poisson_trace.paired import Counts

    return [Counts(f"i{k}", *row) for k, row in enumerate(table)]


def wide_reach_table() -> list[tuple[int, int, int, int]]:
    """Forty moved inputs whose totals of tries carry every prime up to 59 and the powers 32, 27,
    25 and 49, so the least common multiple of the totals is far above 2**62 and the by-input
    reading compares in floating point."""
    totals = (32, 27, 25, 49, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59)
    rows = []
    for k in range(40):
        total = totals[k % len(totals)]
        runs_old = total // 2
        runs_new = total - runs_old
        failed_old = (3 * k) % (runs_old + 1)
        failed_new = (5 * k + 1) % (runs_new + 1)
        if failed_new * runs_old == failed_old * runs_new:
            failed_new = (failed_new + 1) % (runs_new + 1)
        rows.append((failed_old, runs_old, failed_new, runs_new))
    return rows


def cell_sets() -> list[tuple[list[tuple[str, int, bool]], list[tuple[str, int, bool]], list[float]]]:
    """50 seeded pairs of runs as ``(cell, step, died)`` rows, 1 to 12 cells, 1 to 10 tries per
    cell and arm, steps 1 to 20; and with each a list of p values for Benjamini-Hochberg."""
    rng = random.Random(CELL_SEED)
    sets = []
    for _ in range(50):
        a: list[tuple[str, int, bool]] = []
        b: list[tuple[str, int, bool]] = []
        for c in range(rng.randint(1, 12)):
            hazard_a = rng.random() * 0.6
            hazard_b = min(1.0, max(0.0, hazard_a + (rng.random() * 0.4 - 0.2)))
            for rows, hazard in ((a, hazard_a), (b, hazard_b)):
                for _ in range(rng.randint(1, 10)):
                    rows.append((f"c{c}", rng.randint(1, 20), rng.random() < hazard))
        ps = [rng.random() for _ in range(rng.randint(1, 30))]
        sets.append((a, b, ps))
    return sets


def samples() -> list[list[float]]:
    """50 seeded lists of paired case differences, 2 to 60 cases, about one in ten exactly 0,
    the rest in [-5, 5] to three places: some with 20 or fewer changed cases (the exact sign-flip
    count) and some with more (the drawn one)."""
    rng = random.Random(SAMPLE_SEED)
    out = []
    for _ in range(50):
        k = rng.randint(2, 60)
        out.append([0.0 if rng.random() < 0.1 else round(rng.random() * 10.0 - 5.0, 3) for _ in range(k)])
    return out


# ---------- the fixed points of each portable function ----------


def _spread(lo: float, hi: float, n: int) -> list[float]:
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)]


def _decades(first: int, last: int, n: int, sign: float = 1.0) -> list[float]:
    """``n`` points from ``10**first`` to ``10**last``, even in the exponent, read from text so
    that no power function is involved."""
    out = []
    for i in range(n):
        e = first + (last - first) * i / (n - 1)
        whole = math.floor(e)
        mantissa = round(1.0 + 9.0 * (e - whole), 6)
        out.append(sign * float(f"{mantissa}e{whole}"))
    return out


def function_points() -> dict[str, list[Any]]:
    """200 fixed arguments for each portable function, over the range Trace calls it on."""
    t_df = [1, 2, 3, 4, 5, 7, 10, 15, 30, 50, 100, 300, 1000, 3000, 10000]
    t_x = _spread(-40.0, 40.0, 100) + _decades(-3, 6, 50) + _decades(-3, 6, 50, -1.0)
    t_q = _spread(0.01, 0.99, 120) + _decades(-12, -2, 40) + [1.0 - q for q in _decades(-12, -2, 40)]
    tables = []
    for k in range(200):
        runs_a, runs_b = 1 + (k * 7) % 40, 1 + (k * 11) % 40
        tables.append([(k * 3) % (runs_a + 1), runs_a - (k * 3) % (runs_a + 1),
                       (k * 5) % (runs_b + 1), runs_b - (k * 5) % (runs_b + 1)])
    return {
        "exp": _spread(-745.0, 709.7, 200),
        "log": _decades(-300, 300, 200),
        "log1p": _decades(-300, 300, 100) + [-q for q in _decades(-300, -0.001, 100)],
        "expm1": _spread(-745.0, 709.7, 100) + _decades(-300, 0, 50) + _decades(-300, 0, 50, -1.0),
        "erfc": _spread(-6.0, 27.0, 200),
        "norm_sf": _spread(-38.0, 38.0, 200),
        "norm_cdf": _spread(-38.0, 38.0, 200),
        "norm_isf": _decades(-300, -1, 100) + _spread(0.1, 1.0 - 1e-16, 100),
        "norm_ppf": _decades(-300, -1, 100) + _spread(0.1, 1.0 - 1e-16, 100),
        "chi2_sf_1": [0.0] + _decades(-10, 3, 199),
        "t_cdf": [[t_x[i], t_df[i % len(t_df)]] for i in range(200)],
        "t_ppf": [[t_q[i], t_df[i % len(t_df)]] for i in range(200)],
        "fisher_two_sided": tables,
    }


# ---------- the golden table ----------


def _hex(x: Any) -> Any:
    """A float as ``float.hex()``; None, ints, bools and strings as they are; sequences item by
    item."""
    if x is None or isinstance(x, (bool, str)):
        return x
    if isinstance(x, int):
        return x
    if isinstance(x, (list, tuple)):
        return [_hex(v) for v in x]
    return float(x).hex()


def _functions() -> dict[str, list[Any]]:
    from poisson_trace.stats import portable

    out: dict[str, list[Any]] = {}
    for name, points in function_points().items():
        fn = getattr(portable, name)
        out[name] = [_hex(fn(*p)) if isinstance(p, list) else _hex(fn(p)) for p in points]
    return out


def _paired() -> list[dict[str, Any]]:
    from poisson_trace import paired

    rows = []
    tables = count_tables()
    for i, table in enumerate([*tables, wide_reach_table()]):
        cs = counts(table)
        row: dict[str, Any] = {
            "p": _hex(paired.paired_test(cs).p),
            "difference": _hex(paired.difference(cs)),
            "difference at 0.1": _hex(paired.difference(cs, alpha=0.1)),
            "by_input": _hex(paired.by_input(cs, seed=i)),
            "consistency": _hex(paired.consistency(cs)),
            "detection_limit drop": _hex(paired.detection_limit(cs, direction="drop")),
            "detection_limit rise": _hex(paired.detection_limit(cs, direction="rise")),
            "flags": [_hex([f.change, f.p, f.q, f.flag, f.limit_rise]) for f in paired.flags(cs)],
        }
        rows.append(row)
    return rows


def _survival() -> list[dict[str, Any]]:
    import numpy as np

    from poisson_trace import survival

    rows = []
    for a, b, ps in cell_sets():
        lr = survival.logrank_stratified(a, b)
        deaths = sum(1 for row in [*a, *b] if row[2])
        rows.append({
            "logrank": _hex([lr.cells, lr.observed_a, lr.expected_a, lr.variance, lr.statistic, lr.p]),
            "information_limit": _hex(survival.information_limit(lr.variance)),
            "one_step": _hex(survival.one_step(lr)),
            "mde_hazard_ratio": _hex(survival.mde_hazard_ratio(deaths, len(a) / (len(a) + len(b))) if deaths else None),
            "bh": _hex([float(q) for q in survival.bh(np.array(ps, dtype=np.float64), 0.05)]),
        })
    return rows


def _measures() -> list[dict[str, Any]]:
    from poisson_trace.stats import continuous

    rows = []
    for i, d in enumerate(samples()):
        rows.append({
            "t_range": _hex(continuous.t_range(d)),
            "signflip_p": _hex(continuous.signflip_p(d, seed=1000 + i)),
            "mde": _hex(continuous.mde(d)),
            "hl_range": _hex(continuous.hl_range(d)),
        })
    return rows


# ---------- the pairs the tie tests read ----------

#: A pair whose exact test's p lies inside the range ``--alpha`` accepts, with a difference that
#: is not zero.
TIE_P_TABLE: list[tuple[int, int, int, int]] = [
    (2, 4, 4, 4), (0, 4, 1, 4), (4, 5, 0, 5), (0, 4, 0, 4), (1, 3, 1, 3), (2, 3, 1, 3), (0, 3, 0, 3),
    (0, 3, 1, 3), (3, 3, 1, 3), (1, 4, 0, 4), (5, 6, 4, 6), (2, 3, 2, 3), (1, 4, 1, 4), (0, 5, 1, 5),
    (4, 6, 1, 6), (5, 5, 2, 5), (4, 4, 4, 4), (2, 6, 4, 6), (6, 6, 5, 6), (3, 6, 4, 6), (0, 4, 1, 4),
    (6, 6, 6, 6), (4, 4, 3, 4),
]
#: A pair whose range is reliable and whose exact test's p is at or above 0.05.
TIE_RANGE_TABLE: list[tuple[int, int, int, int]] = [
    (2, 4, 2, 4), (4, 6, 3, 6), (3, 6, 5, 6), (5, 6, 1, 6), (2, 3, 1, 3), (1, 3, 1, 3), (1, 3, 3, 3),
    (2, 3, 2, 3), (0, 5, 1, 5), (4, 4, 3, 4), (0, 4, 2, 4), (0, 5, 1, 5), (2, 4, 1, 4),
]
#: compare on the committed Prove 0.1.3 store at a level below its log-rank's p, so the verdict
#: falls to the detection limit.
TIE_COMPARE_ARGV: list[str] = ["compare", "agent before", "agent after", "--store", "store", "--event",
                               "violated", "--event", "timeout", "--alpha", "1e-12", "--json"]


def compare_store(tmp: Path) -> Path:
    """A folder holding ``store``, a copy of the committed Prove 0.1.3 store."""
    import shutil

    shutil.copytree(FIXTURES / "prove-stores" / "prove-0.1.3", tmp / "store")
    return tmp


def compare_document(work: Path, *extra: str) -> tuple[int, dict[str, Any]]:
    from look_support import chdir, trace

    with chdir(work):
        ran = trace([*TIE_COMPARE_ARGV, *extra])
    return ran.code, json.loads(ran.out)


def _ties() -> dict[str, Any]:
    from poisson_trace import paired

    _, _, lo, hi = paired.difference(counts(TIE_RANGE_TABLE))
    with tempfile.TemporaryDirectory() as tmp:
        code, doc = compare_document(compare_store(Path(tmp)), "--max-mde-hr", "1.5")
    assert code == 0, doc
    return {
        "fix-check p": _hex(paired.paired_test(counts(TIE_P_TABLE)).p),
        "fix-check range": _hex([lo, hi]),
        "compare mde": _hex(doc["comparison"]["mde_hazard_ratio"]),
    }


def entries() -> dict[str, Any]:
    """Every value of the golden table, as the installed build computes it."""
    return {
        "functions": _functions(),
        "paired": _paired(),
        "survival": _survival(),
        "measures": _measures(),
        "ties": _ties(),
    }


def golden() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return loaded
