"""Rebuild the four Ragas score tables beside this script.

**The memory pair** (``memory-causal.jsonl.gz``, ``memory-strong.jsonl.gz``). Two stored runs of
a memory-retrieval experiment, the same 1,800 lookups on a memory with causal reads and on one
with strong reads. Each stored row holds the fact ids the memory returned and the fact ids that
answer the question; no model is involved. Each row becomes one Ragas ``SingleTurnSample``
(``user_input`` the row's own id, ``<config_hash>:<seed>``; ``retrieved_context_ids`` and
``reference_context_ids`` the two lists), Ragas 0.4.3's ``evaluate()`` scores every sample with
its two id-based context metrics, and the table ``to_pandas()`` gives is saved as JSON Lines and
gzipped as it is, with a fixed gzip header (no name, mtime 0). The source stores are not public,
so they are named on the command line and not here.

**The public pair** (``rag-base.jsonl``, ``rag-raft.jsonl``). Two result sets published on
Hugging Face, each the table ``to_pandas()`` gives for 150 rows (146 questions). They carry no
licence, so only a hash of each question and the three score columns are kept: ``case`` is ``q-``
and the first 16 hex characters of the SHA-256 of ``user_input``; ``faithfulness``,
``answer_relevancy`` and ``answer_correctness`` are written by pandas's JSON writer at its
default ten decimal digits. The two Parquet files are read by URL at the commits pinned below and
refused unless their SHA-256 is the one pinned.

Steps, because the rows are read through Prove and scored by Ragas, and the two need not share
an environment:

    python make.py memory-rows SOURCE CAUSAL STRONG WORK   # proofload importable
    python make.py memory-score WORK                       # ragas 0.4.3 importable
    python make.py memory-gzip WORK DEST
    python make.py pair WORK DEST                          # pandas and pyarrow; reads two URLs

``SOURCE`` is the root of the store holding the two runs and ``CAUSAL`` and ``STRONG`` their run
ids. Ragas's usage tracking is turned off before Ragas is imported.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import sys
import urllib.request
import warnings
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

MEMORY = ("causal", "strong")
RAGAS = "0.4.3"
LISTS = ("retrieved_fact_ids", "reference_fact_ids")

# the public pair: (fixture, dataset, commit, sha256 of the Parquet file at that commit)
PAIR = (
    (
        "rag-base",
        "R0bfried/RAGAS-BASE-llama-3-2-1B-eval2",
        "ebed5a6e42407ee10fc63abff17f5b270b7e0aa4",
        "fc76783271005b0f538bef880692da45edbe0ccee5f4accc44593fce3388426b",
    ),
    (
        "rag-raft",
        "R0bfried/RAGAS-RAFT-llama-3-2-1B-eval2",
        "5b131e43163020e01e13f2d9b195481ce3317c11",
        "52485d1ce1c8758cdec2ce174f4af82ae61e777c879c39a599791b3f8146acca",
    ),
)
PARQUET = "data/train-00000-of-00001.parquet"
SCORES = ("faithfulness", "answer_relevancy", "answer_correctness")


def _found(value: Any, key: str) -> Iterator[Any]:
    """Every value stored under ``key`` anywhere in a nested mapping."""
    if isinstance(value, Mapping):
        for k, v in value.items():
            if k == key:
                yield v
            yield from _found(v, key)
    elif isinstance(value, list):
        for v in value:
            yield from _found(v, key)


def _one(meta: Mapping[str, Any], key: str) -> list[str]:
    hits = list(_found(meta, key))
    if len(hits) != 1 or not isinstance(hits[0], list):
        raise SystemExit(
            f"a stored row holds {len(hits)} values under {key!r}; one list is required"
        )
    return [str(x) for x in hits[0]]


def memory_rows(source: Path, runs: tuple[str, str], work: Path) -> None:
    from proofload.store import Store

    store = Store(source)
    work.mkdir(parents=True, exist_ok=True)
    for label, run in zip(MEMORY, runs, strict=True):
        frame = store.read(run, meta=True, trace="none")
        out = []
        for config_hash, seed, meta in zip(
            frame["config_hash"], frame["seed"], frame["meta"], strict=True
        ):
            retrieved, reference = (_one(meta, key) for key in LISTS)
            out.append(
                {
                    "case": f"{config_hash}:{int(seed)}",
                    "retrieved": retrieved,
                    "reference": reference,
                }
            )
        (work / f"rows-{label}.json").write_text(json.dumps(out) + "\n")
        manifest = hashlib.sha256((source / run / "manifest.json").read_bytes()).hexdigest()
        print(
            f"memory-{label}: {len(out)} rows (source manifest sha256 {manifest}) -> rows-{label}.json"
        )


def memory_score(work: Path) -> None:
    os.environ["RAGAS_DO_NOT_TRACK"] = "true"
    warnings.simplefilter("ignore")
    import ragas
    from ragas import evaluate
    from ragas.dataset_schema import EvaluationDataset, SingleTurnSample
    from ragas.metrics import IDBasedContextPrecision, IDBasedContextRecall

    if ragas.__version__ != RAGAS:
        raise SystemExit(f"ragas {RAGAS} is required, found {ragas.__version__}")
    for label in MEMORY:
        stored = json.loads((work / f"rows-{label}.json").read_text())
        dataset = EvaluationDataset(
            samples=[
                SingleTurnSample(
                    user_input=r["case"],
                    retrieved_context_ids=r["retrieved"],
                    reference_context_ids=r["reference"],
                )
                for r in stored
            ]
        )
        result = evaluate(
            dataset,
            metrics=[IDBasedContextRecall(), IDBasedContextPrecision()],
            show_progress=False,
        )
        target = work / f"memory-{label}.jsonl"
        result.to_pandas().to_json(target, orient="records", lines=True)
        print(f"memory-{label}: {len(stored)} samples -> {target.name}")


def memory_gzip(work: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for label in MEMORY:
        source = work / f"memory-{label}.jsonl"
        raw = source.read_bytes()
        target = dest / f"memory-{label}.jsonl.gz"
        with open(target, "wb") as handle:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=handle, compresslevel=9, mtime=0
            ) as z:
                z.write(raw)
        print(
            f"{source.name} sha256 {hashlib.sha256(raw).hexdigest()} ({len(raw)} bytes) -> "
            f"{target.name} sha256 {hashlib.sha256(target.read_bytes()).hexdigest()}"
        )


def pair(work: Path, dest: Path) -> None:
    import pandas as pd

    work.mkdir(parents=True, exist_ok=True)
    dest.mkdir(parents=True, exist_ok=True)
    for name, dataset, commit, digest in PAIR:
        url = f"https://huggingface.co/datasets/{dataset}/resolve/{commit}/{PARQUET}"
        source = work / f"{name}.parquet"
        if not source.exists():
            with urllib.request.urlopen(url, timeout=60) as response:
                source.write_bytes(response.read())
        got = hashlib.sha256(source.read_bytes()).hexdigest()
        if got != digest:
            raise SystemExit(f"{url} has sha256 {got}, not the {digest} pinned")
        frame = pd.read_parquet(source)
        out = pd.DataFrame(
            {
                "case": [
                    "q-" + hashlib.sha256(u.encode("utf-8")).hexdigest()[:16]
                    for u in frame["user_input"]
                ],
                **{score: frame[score] for score in SCORES},
            }
        )
        target = dest / f"{name}.jsonl"
        out.to_json(target, orient="records", lines=True)
        print(
            f"{url} ({got}): {len(frame)} rows -> {target.name} sha256 {hashlib.sha256(target.read_bytes()).hexdigest()}"
        )


def main(argv: list[str]) -> int:
    if len(argv) == 5 and argv[0] == "memory-rows":
        memory_rows(Path(argv[1]), (argv[2], argv[3]), Path(argv[4]))
    elif len(argv) == 2 and argv[0] == "memory-score":
        memory_score(Path(argv[1]))
    elif len(argv) == 3 and argv[0] == "memory-gzip":
        memory_gzip(Path(argv[1]), Path(argv[2]))
    elif len(argv) == 3 and argv[0] == "pair":
        pair(Path(argv[1]), Path(argv[2]))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
