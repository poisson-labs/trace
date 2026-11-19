"""TF24-70: Prove reads every run the LangSmith reader writes.

**TF24-70** Prove 0.1.3 reads every run this reader writes, from every export and from a pull:
its manifest, its tally, its rows with their meta, its ``events.jsonl`` in Prove's shape; the
Parquet part has the schema of a run the JUnit reader writes; the run record names the reader
and the files; and Prove's own ``runs`` and ``ui`` list it and build their pages over it, which
needs the rows to share one horizon though they took different numbers of steps.

TF24-66 to TF24-69 and TF24-71 (every command, the pages and the app as an older main gave them,
what the import's help and one refusal gained with this reader, and the tests of those pins) were
cut on the rulings of 2026-11-18 (AR-1, AR-3): ``test_pl_unchanged.py`` (PL-51 to PL-55) holds each
of those commands, the pages and the app at today's bytes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tf24_support import EXPORTS, VERSIONS, address, by_status, export, imported, ls_argv, pulling


# ---------- TF24-70 ----------


def _prove_reads(root: Path, run: str, missed: int, files: list[str]) -> None:
    import pyarrow.parquet as pq
    from poisson_prove.store import Store

    from poisson_trace.ingest.writer import RECORD_KEYS
    from tf21_support import do_import

    store = Store(root)
    assert run in store.runs()
    junit = root.parent / f"junit-store-{run}"
    do_import("junit-a", junit, "j")
    want_schema = pq.read_schema(next((junit / "j").rglob("*.parquet")))
    manifest = store.manifest(run)
    assert manifest.status == "complete" and manifest.backend == "import:langsmith"
    assert manifest.target_id == "import/langsmith"
    frame = store.read(run, meta=True, trace="full")
    assert len(frame) == 10
    assert json.dumps(store.tally(run).to_dict(), default=str)
    for meta in frame["meta"]:
        assert set(meta["trace_signals"]) == set(RECORD_KEYS)
        assert meta["trace_signals"]["schema"] == "poisson.trace-signals/1"
    assert sum(1 for o in frame["outcome"] if o == "missed") == missed
    part = next((root / run).rglob("*.parquet"))
    assert pq.read_schema(part).remove_metadata() == want_schema.remove_metadata()
    events = [json.loads(line) for line in (root / run / "events.jsonl").read_text().splitlines()]
    kinds = [e["kind"] for e in events]
    assert kinds[:2] == ["planned", "started"] and kinds[-1] == "finished"
    assert set(kinds[2:-1]) == {"progress"}
    assert all(set(e) == {"schema", "at", "kind", "detail"} and e["schema"] == "poisson.run-event/1" for e in events)
    block = manifest.to_dict()["environment"]["import"]
    assert block["tool"] == "langsmith" and len(block["taxonomy_sha256"]) == 64
    assert [f["name"] for f in block["files"]] == files, block["files"]
    assert block["declared"]["case_from"] == "metadata:ls_example_case"
    descriptor = json.loads((root / ".poisson" / "store.json").read_text(encoding="utf-8"))
    assert descriptor["format"].startswith("poisson.store/"), descriptor
    # Prove's own command lists the run and builds its pages over it, which it refuses for a run
    # whose rows hold different horizons: the rows share one, the most steps any of them took
    from runrec_support import prove

    code, out, err = prove(root, "runs")
    assert code == 0 and run in out, out + err
    code, out, err = prove(root, "ui")
    assert code == 0, out + err
    assert (root / ".poisson" / "ui" / "runs" / f"{run}.html").is_file()
    scored = frame[frame["outcome"].notna()]
    assert len(set(scored["horizon"])) == 1 and float(scored["horizon"].iloc[0]) == float(scored["t"].max())


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("kind", EXPORTS)
def test_tf24_70_prove_reads_every_run_the_reader_writes(tmp_path: Path, version: str, kind: str) -> None:
    files = export(version, kind)
    imported(by_status(files, tmp_path / "st", "r"))
    _prove_reads(tmp_path / "st", "r", 1, [p.name for p in files])


@pytest.mark.parametrize("version", VERSIONS)
def test_tf24_70_and_every_run_a_pull_writes(tmp_path: Path, version: str) -> None:
    with pulling() as (_, _waits):
        imported(ls_argv(address(version), tmp_path / "st", "r"))
    _prove_reads(tmp_path / "st", "r", {"baseline": 4, "candidate": 2}[version], ["raw.jsonl"])
    from poisson_prove.store import Store

    # the raw copy sits under the store's own folder, which Prove's listing leaves alone
    assert Store(tmp_path / "st").runs() == ["r"]
