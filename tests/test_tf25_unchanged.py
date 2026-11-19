"""TF25-70: Prove reads every run the Braintrust reader writes.

**TF25-70** Prove 0.1.3 reads every run this reader writes, from every export and from a pull:
its manifest, its tally, its rows with their meta, its ``events.jsonl`` in Prove's shape; the
Parquet part has the schema of a run the JUnit reader writes; the run record names the reader
and the files; and Prove's own ``runs`` and ``ui`` list it and build their pages over it, the
rows sharing one horizon though they took different numbers of steps.

TF25-66 to TF25-69 and TF25-71 (every command, the pages and the app as an older main gave them,
what the import's help and one refusal gained with this reader, and the tests of those pins) were
cut on the rulings of 2026-11-18 (AR-1, AR-3): ``test_pl_unchanged.py`` (PL-51 to PL-55) holds each
of those commands, the pages and the app at today's bytes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tf25_support import (
    EXPORTS, LOOKUP, SPAN_EXPORTS, VERSIONS, address, bt_argv, by_error, export, imported, pulling,
)


# ---------- TF25-70 ----------


@pytest.fixture(scope="module")
def junit_schema(tmp_path_factory: Any) -> Any:
    """The Parquet schema of a run the JUnit reader writes, read once from a store of its own
    that no test writes to."""
    import pyarrow.parquet as pq

    from tf21_support import do_import

    junit = tmp_path_factory.mktemp("junit") / "st"
    do_import("junit-a", junit, "j")
    return pq.read_schema(next((junit / "j").rglob("*.parquet")))


def _prove_reads(want_schema: Any, root: Path, run: str, rows: int, missed: int, files: list[str], shared: bool) -> None:
    import pyarrow.parquet as pq
    from poisson_prove.store import Store

    from poisson_trace.ingest.writer import RECORD_KEYS

    store = Store(root)
    assert run in store.runs()
    manifest = store.manifest(run)
    assert manifest.status == "complete" and manifest.backend == "import:braintrust"
    assert manifest.target_id == "import/braintrust"
    frame = store.read(run, meta=True, trace="full")
    assert len(frame) == rows
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
    assert block["tool"] == "braintrust" and len(block["taxonomy_sha256"]) == 64
    assert [f["name"] for f in block["files"]] == files, block["files"]
    assert block["declared"]["case_from"] == "input"
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
    if shared:
        assert len(set(scored["t"])) > 1, "the rows took different numbers of steps"


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("kind", EXPORTS)
def test_tf25_70_prove_reads_every_run_the_reader_writes(tmp_path: Path, junit_schema: Any,version: str, kind: str) -> None:
    files = export(version, kind)
    imported(by_error(files, tmp_path / "st", "r"))
    _prove_reads(junit_schema, tmp_path / "st", "r", 10, 1, [p.name for p in files], kind in SPAN_EXPORTS)


@pytest.mark.parametrize("name", LOOKUP)
@pytest.mark.parametrize("kind", ["fetch", "ui-csv"])
def test_tf25_70_and_a_run_of_two_tries_a_case(tmp_path: Path, junit_schema: Any,name: str, kind: str) -> None:
    files = export(name, kind)
    imported(bt_argv(files, tmp_path / "st", "r"))
    _prove_reads(junit_schema, tmp_path / "st", "r", 6, 4 if name == "old" else 0, [p.name for p in files], False)


@pytest.mark.parametrize("version", VERSIONS)
def test_tf25_70_and_every_run_a_pull_writes(tmp_path: Path, junit_schema: Any,version: str) -> None:
    with pulling() as (_, _waits):
        imported(by_error(address(version), tmp_path / "st", "r"))
    _prove_reads(junit_schema, tmp_path / "st", "r", 10, 1, ["raw.jsonl"], True)
    from poisson_prove.store import Store

    # the raw copy sits under the store's own folder, which Prove's listing leaves alone
    assert Store(tmp_path / "st").runs() == ["r"]
