"""RUNREC-1 to RUNREC-8: the store descriptor an import writes, and Prove 0.1.3 reading every
store Trace writes (invariant 1; spec section 17.3 item 6 and the reuse list above item 1; the
artifact format's sections 2, 3, 8 and 9; RR5).

The descriptor is written as Prove 0.1.3 writes its own (``poisson_prove.core._artifacts.
ensure_descriptor``, the committed ``prove-0.1.3`` store): on the first write into a store,
``{"format": "poisson.store/1", "created_by", "created_at", "writers"}`` as two-space JSON
with one newline, times to the second; into a store that has one, Trace and its major.minor
version appended to ``writers`` once, every other byte left alone. A refused import writes
none; a descriptor in a newer major, or one that is not a descriptor, is refused before
anything is written (format sections 3 and 9). A store written before the format (Prove 0.0.1,
format 0) gains ``.poisson/store.json`` and nothing else changes (format section 2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import FIXTURES
from runrec_support import (
    DESCRIPTOR_KEYS, FAST, READERS, SECOND, STORE_FORMAT, TOOL, WRITER_KEYS, copy_store, descriptor,
    descriptor_file, events, import_key, major_minor, manifest_json, prove, trace_version, tree,
)
from tf21_support import run_import

PROVE_013 = FIXTURES / "prove-stores" / "prove-0.1.3"
PROVE_001 = FIXTURES / "prove-stores" / "prove-0.0.1"


def _as_prove_writes(path: Path) -> None:
    """Prove's own bytes for the document the file holds: two-space indent, UTF-8 as it is,
    one newline (``_write_json``)."""
    text = path.read_text(encoding="utf-8")
    assert text == json.dumps(json.loads(text), indent=2, ensure_ascii=False) + "\n"


# ---------- RUNREC-1: the first write into a store ----------


@pytest.mark.parametrize("key", ["junit-a", "ragas-base", "promptfoo-old", "inspect-eval",
                                 "openai-evals-old"])
def test_runrec_1_an_import_into_a_new_store_writes_the_descriptor(tmp_path: Path, key: str) -> None:
    root = tmp_path / "store"
    import_key(key, root, "r")
    doc = descriptor(root)
    assert list(doc) == DESCRIPTOR_KEYS
    assert doc["format"] == STORE_FORMAT
    assert doc["created_by"] == {"tool": TOOL, "version": trace_version()}
    assert SECOND.fullmatch(doc["created_at"]), doc
    assert doc["writers"] == [{"tool": TOOL, "version": trace_version(),
                               "first_write": doc["created_at"]}]
    assert list(doc["writers"][0]) == WRITER_KEYS
    _as_prove_writes(descriptor_file(root))
    # written through a temporary file renamed in: nothing else is left in .poisson
    assert sorted(p.name for p in (root / ".poisson").iterdir()) == ["store.json"]


# ---------- RUNREC-2: a store that has a descriptor ----------


def test_runrec_2_trace_is_appended_to_proves_writers_once(tmp_path: Path) -> None:
    root = copy_store(PROVE_013, tmp_path / "store")
    before = descriptor(root)
    import_key("junit-a", root, "first")
    after = descriptor(root)
    assert list(after) == DESCRIPTOR_KEYS
    assert {k: after[k] for k in ("format", "created_by", "created_at")} == {
        k: before[k] for k in ("format", "created_by", "created_at")}
    assert after["writers"][:-1] == before["writers"]
    mine = after["writers"][-1]
    assert list(mine) == WRITER_KEYS
    assert (mine["tool"], mine["version"]) == (TOOL, trace_version())
    assert SECOND.fullmatch(mine["first_write"])
    _as_prove_writes(descriptor_file(root))
    held = descriptor_file(root).read_bytes()
    import_key("ragas-base", root, "second")
    assert descriptor_file(root).read_bytes() == held


def test_runrec_2_a_second_import_into_a_new_store_leaves_the_descriptor_as_it_is(tmp_path: Path) -> None:
    root = tmp_path / "store"
    import_key("junit-a", root, "one")
    held = descriptor_file(root).read_bytes()
    import_key("promptfoo-old", root, "two")
    assert descriptor_file(root).read_bytes() == held


def test_runrec_2_a_save_and_an_import_share_one_entry(tmp_path: Path) -> None:
    from tf0_support import trace

    root = tmp_path / "store"
    import_key("junit-a", root, "a")
    import_key("junit-a", root, "b")
    held = descriptor_file(root).read_bytes()
    saved = trace(["fix-check", "a", "b", "--store", str(root), "--event", "missed", "--inputs",
                   "all", "--max-mde", "0.5", "--save"])
    assert saved.code == 0, saved.out + saved.err
    assert descriptor_file(root).read_bytes() == held


# ---------- RUNREC-3: Trace at another version ----------


def _with_writers(root: Path, writers: list[dict[str, str]]) -> bytes:
    doc = {"format": STORE_FORMAT, "created_by": {"tool": "poisson-prove", "version": "0.1.3"},
           "created_at": "2026-11-04T16:29:26Z", "writers": writers}
    descriptor_file(root).parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(doc, indent=2) + "\n").encode("utf-8")
    descriptor_file(root).write_bytes(data)
    return data


def test_runrec_3_another_major_minor_of_trace_gains_its_own_entry(tmp_path: Path) -> None:
    root = tmp_path / "store"
    older = [{"tool": "poisson-prove", "version": "0.1.3", "first_write": "2026-11-04T16:29:26Z"},
             {"tool": TOOL, "version": "0.0.9", "first_write": "2026-10-01T00:00:00Z"}]
    _with_writers(root, older)
    import_key("junit-a", root, "r")
    doc = descriptor(root)
    assert doc["writers"][:2] == older and len(doc["writers"]) == 3
    assert (doc["writers"][2]["tool"], doc["writers"][2]["version"]) == (TOOL, trace_version())


def test_runrec_3_the_same_major_minor_is_not_listed_again(tmp_path: Path) -> None:
    root = tmp_path / "store"
    same = major_minor(trace_version()) + ".99"
    data = _with_writers(root, [{"tool": TOOL, "version": same, "first_write": "2026-10-01T00:00:00Z"}])
    import_key("junit-a", root, "r")
    assert descriptor_file(root).read_bytes() == data


def test_runrec_3_writers_that_is_not_a_list_becomes_one(tmp_path: Path) -> None:
    # Prove's own reading: a descriptor whose writers is missing gains the list, every other
    # key as it was
    root = tmp_path / "store"
    descriptor_file(root).parent.mkdir(parents=True)
    descriptor_file(root).write_text(json.dumps(
        {"format": STORE_FORMAT, "created_by": {"tool": "poisson-prove", "version": "0.1.3"},
         "created_at": "2026-11-04T16:29:26Z"}, indent=2) + "\n", encoding="utf-8")
    import_key("junit-a", root, "r")
    doc = descriptor(root)
    assert doc["created_by"] == {"tool": "poisson-prove", "version": "0.1.3"}
    assert [(w["tool"], w["version"]) for w in doc["writers"]] == [(TOOL, trace_version())]


# ---------- RUNREC-4: a format 0 store ----------


def test_runrec_4_a_format_0_store_gains_the_descriptor_and_nothing_else_changes(tmp_path: Path) -> None:
    root = copy_store(PROVE_001, tmp_path / "store")
    assert not (root / ".poisson").exists()
    before = tree(root)
    import_key("junit-a", root, "r")
    after = tree(root)
    assert {k: v for k, v in after.items() if k in before} == before
    added = sorted(set(after) - set(before))
    assert ".poisson/store.json" in added
    assert all(k == ".poisson/store.json" or k.startswith("r/") for k in added), added
    assert descriptor(root)["created_by"] == {"tool": TOOL, "version": trace_version()}


# ---------- RUNREC-5: a refused import writes no descriptor ----------


def test_runrec_5_a_refused_import_into_a_new_store_writes_no_descriptor(tmp_path: Path) -> None:
    root = tmp_path / "store"
    _, argv = READERS["junit-a"]
    bad = run_import([*argv(root, "r"), "--started", "not a time"])
    assert bad.code in (1, 2), bad.out + bad.err
    assert not (root / ".poisson").exists()
    empty = tmp_path / "empty.csv"
    empty.write_text("case,outcome\n", encoding="utf-8")
    refused = run_import(["table", str(empty), "--store", str(root), "--run", "r",
                          "--case-column", "case", "--outcome-column", "outcome",
                          "--failed", "failed"])
    assert refused.code == 1, refused.out + refused.err
    assert not (root / ".poisson").exists() and not (root / "r").exists()


def test_runrec_5_a_refused_import_leaves_a_descriptor_as_it_was(tmp_path: Path) -> None:
    root = copy_store(PROVE_013, tmp_path / "store")
    before = tree(root)
    _, argv = READERS["junit-a"]
    # the name is taken: refused, nothing written
    taken = run_import(argv(root, "agent before"))
    assert taken.code == 1, taken.out + taken.err
    assert tree(root) == before


# ---------- RUNREC-6: a newer major, or no descriptor at all ----------


@pytest.mark.parametrize("found", ["poisson.store/2", "poisson.store/10"])
def test_runrec_6_a_newer_major_is_refused_naming_both(tmp_path: Path, found: str) -> None:
    root = tmp_path / "store"
    descriptor_file(root).parent.mkdir(parents=True)
    descriptor_file(root).write_text(json.dumps(
        {"format": found, "created_by": {"tool": "poisson-prove", "version": "9.0.0"},
         "created_at": "2030-01-01T00:00:00Z", "writers": []}, indent=2) + "\n", encoding="utf-8")
    before = tree(root)
    _, argv = READERS["junit-a"]
    result = run_import(argv(root, "r"))
    assert result.code == 1 and result.out == "", result.out + result.err
    first = result.err.splitlines()[0]
    assert first.startswith("error: ") and found in first and STORE_FORMAT in first, result.err
    assert tree(root) == before and sorted(p.name for p in root.iterdir()) == [".poisson"]


def test_runrec_6_an_older_or_same_major_is_written_into(tmp_path: Path) -> None:
    root = tmp_path / "store"
    _with_writers(root, [])
    import_key("junit-a", root, "r")
    assert [(w["tool"]) for w in descriptor(root)["writers"]] == [TOOL]


@pytest.mark.parametrize("text", ["[]\n", "{not json\n", "\"poisson.store/1\"\n"])
def test_runrec_6_a_file_that_is_not_a_descriptor_is_refused(tmp_path: Path, text: str) -> None:
    root = tmp_path / "store"
    descriptor_file(root).parent.mkdir(parents=True)
    descriptor_file(root).write_text(text, encoding="utf-8")
    before = tree(root)
    _, argv = READERS["junit-a"]
    result = run_import(argv(root, "r"))
    assert result.code == 1 and result.out == "", result.out + result.err
    first = result.err.splitlines()[0]
    assert first.startswith("error: ") and "store.json" in first, result.err
    assert tree(root) == before and sorted(p.name for p in root.iterdir()) == [".poisson"]


# ---------- RUNREC-7: Prove 0.1.3 lists and reads every store Trace writes ----------


def _prove_reads(root: Path) -> None:
    from poisson_prove.core._artifacts import check_store, read_events
    from poisson_prove.store import Store

    check_store(root)  # Prove's own refusal of a descriptor it cannot read
    store = Store(root)
    runs = store.runs()
    code, out, err = prove(root, "runs")
    assert code == 0, out + err
    for run in runs:
        assert run in out, (run, out)
        store.manifest(run)
        store.read(run, meta=True, trace="full")
        log = read_events(root / run)
        # every run has its log, and every line of it is one Prove reads: no kind it skips
        assert log is not None and len(log) == len(events(root, run)), run
    held = {run: (root / run / "manifest.json").read_bytes() for run in runs}
    code, out, err = prove(root, "ui")
    assert code == 0, out + err
    assert (root / ".poisson" / "ui" / "index.html").is_file()
    for run in runs:
        assert (root / ".poisson" / "ui" / "runs" / f"{run}.html").is_file(), run
        # Prove's reading leaves each manifest, produced_by with it, as it was
        assert (root / run / "manifest.json").read_bytes() == held[run]


def test_runrec_7_prove_lists_reads_and_builds_its_pages_over_trace_imports(tmp_path: Path) -> None:
    root = tmp_path / "store"
    for key in ("junit-a", "ragas-base", "promptfoo-old", "inspect-eval", "openai-evals-old"):
        import_key(key, root)
    _prove_reads(root)


def test_runrec_7_beside_proves_own_runs_and_a_saved_verdict(tmp_path: Path) -> None:
    from tf0_support import trace

    root = copy_store(PROVE_013, tmp_path / "store")
    import_key("junit-a", root, "a")
    import_key("junit-a", root, "b")
    saved = trace(["fix-check", "a", "b", "--store", str(root), "--event", "missed", "--inputs",
                   "all", "--max-mde", "0.5", "--save"])
    assert saved.code == 0, saved.out + saved.err
    _prove_reads(root)


def test_runrec_7_a_run_with_rows_with_no_outcome_is_read_by_prove(tmp_path: Path) -> None:
    from poisson_trace.ingest.rows import Row, Run
    from poisson_trace.ingest.writer import write

    rows = (Row("a", "met", None), Row("b", "missed", None), Row("c", None, "timeout",
                                                                  result="censored"))
    write(Run(name="r", tool="table", rows=rows, started="2026-09-05T18:54:07Z",
              started_from="given", declared={}, files=({"name": "x.csv", "sha256": "ab" * 32},)),
          tmp_path / "store")
    _prove_reads(tmp_path / "store")


@pytest.mark.slow
def test_runrec_7_slow_prove_reads_a_store_of_every_reader(tmp_path: Path) -> None:
    root = copy_store(PROVE_013, tmp_path / "store")
    for key in READERS:
        import_key(key, root)
    _prove_reads(root)


def test_runrec_7_the_fast_twin_covers_a_fast_key_of_every_reader() -> None:
    from runrec_support import SLOW

    fast_readers = {READERS[k][0] for k in ("junit-a", "ragas-base", "promptfoo-old", "inspect-eval",
                                             "openai-evals-old")}
    assert fast_readers | {READERS[k][0] for k in SLOW} == {r for r, _ in READERS.values()}
    assert set(FAST) <= set(READERS)


# ---------- RUNREC-8: the manifest Trace writes is still Prove's manifest ----------


def test_runrec_8_every_key_prove_writes_is_kept(tmp_path: Path) -> None:
    from poisson_prove.store import Store

    root = tmp_path / "store"
    import_key("junit-a", root, "r")
    doc = manifest_json(root, "r")
    prove_view = Store(root).manifest("r").to_dict()
    assert {k: doc[k] for k in prove_view} == prove_view
    assert set(doc) == set(prove_view) | {"produced_by"}
    assert doc["status"] == "complete"
