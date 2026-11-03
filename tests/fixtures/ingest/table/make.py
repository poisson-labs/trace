"""Rebuild the two HumanEval outcome tables from the committed HumanEval store.

    python tests/fixtures/ingest/table/make.py SOURCE DEST

SOURCE is ``tests/fixtures/humaneval`` (a Prove store); DEST the folder the two tables are
written into. ``poisson_prove`` must be importable. Each stored row of a run, in the order
``Store.read`` returns it (by config hash, then replicate index), becomes one line:
``case`` is ``<task_id>@<temperature>``, as the DeepEval fixture names its test cases;
``task_id``, ``temperature`` and ``replicate`` are the row's config and replicate index; and
``outcome`` is the stored outcome word. Nothing else of the row is written. The file is UTF-8
with a header line and a line feed after every line.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from poisson_prove.store import Store

RUNS = {"humaneval-a.csv": "20260905T185407Z-0313", "humaneval-b.csv": "20260905T195009Z-18ac"}
COLUMNS = ("case", "task_id", "temperature", "replicate", "outcome")


def main() -> int:
    source, dest = Path(sys.argv[1]), Path(sys.argv[2])
    dest.mkdir(parents=True, exist_ok=True)
    store = Store(source)
    for name, run in RUNS.items():
        frame = store.read(run, meta=False)
        with open(dest / name, "w", encoding="utf-8", newline="") as out:
            writer = csv.writer(out, lineterminator="\n")
            writer.writerow(COLUMNS)
            for row in frame.itertuples(index=False):
                task, temperature = row.config["task_id"], row.config["temperature"]
                writer.writerow(
                    (f"{task}@{temperature}", task, temperature, row.replicate_index, row.outcome)
                )
        print(f"{name}: {len(frame)} rows from {run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
