"""TF10-47 to TF10-50: nothing written that Prove 0.1.2 cannot read, and no verb's existing output
changed (spec sections 6.3, 6.4, 18.4.2 as SA1 reads it; TF21-64 and TF21-65 keep pinning the
eleven earlier imports byte for byte, and stay frozen).

- TF10-47: each new import is a run Prove 0.1.2 reads: its manifest, its tally, its rows with
  their meta, its ``events.jsonl`` in Prove's shape; the Parquet part has the schema of a run the
  JUnit reader writes; the signals record has exactly the writer's keys.
- TF10-48: ``runs`` lists each imported run with no traces and its backend ``import:TOOL``;
  ``where`` says in one line that it has no traces and which tool it came from.
- TF10-49: ``fix-check`` reads each pair of imports with ``--event missed``, exit 0, in text and in
  JSON, and the pair it reads is the files' own: promptfoo's two prompts, Inspect's old and new
  logs, OpenAI Evals' two records.
- TF10-50: the import's help and its unknown-tool sentence are the only words that change for a
  user of the earlier readers: each earlier reader's help is byte for byte what main printed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tf0_support import chdir, trace
from tf10_support import IN_EVAL, IN_JSON, OE_NEW, OE_OLD, PF_JSON, imported, in_argv, oe_argv, pf_argv
from tf21_support import IMPORTS, INGEST

PAIRS = {
    "promptfoo": (pf_argv(PF_JSON, Path("st"), "old", prompt="1"), pf_argv(PF_JSON, Path("st"), "new", prompt="2")),
    "inspect": (in_argv(IN_EVAL, Path("st"), "old"), in_argv(IN_JSON, Path("st"), "new")),
    "openai-evals": (oe_argv(OE_OLD, Path("st"), "old"), oe_argv(OE_NEW, Path("st"), "new")),
}
# what each pair's fix check counts, read from the files: (old missed, old rows, new missed, new rows)
COUNTS = {"promptfoo": (2, 4, 0, 4), "inspect": (3, 6, 1, 6), "openai-evals": (3, 3, 3, 3)}
# each earlier reader's help on main 680a1e3, as SHA-256 of its bytes (moved from 73b45ef's by RB1)
EARLIER_HELP_SHA = {
    "deepeval": "fa997eb02bd609e9e62e14a7ab4c9ca960e33b3534cefe5a259631424ab1390d",
    "ragas": "2fd4273275204f7ff58bcd03e1acb7a66b8861b22fe08d2b9ea6149893dbadd9",
    "table": "82a3700050edd09b2a9e9c6f76ee978d986576af4af29bf5cdb1ce5e86620dd9",
    "junit": "1e27de024b2bfb2472992d18d9e1d08eb987dbbfc3086122bf3c53f0163ad0ef",
}


def _pair(folder: Path, tool: str) -> None:
    with chdir(folder):
        for argv in PAIRS[tool]:
            imported(argv)


# ---------- TF10-47 ----------


@pytest.mark.parametrize("tool", list(PAIRS))
def test_tf10_47_prove_reads_each_new_run(tmp_path: Path, tool: str) -> None:
    import pyarrow.parquet as pq
    from poisson_prove.store import Store

    from tf21_support import do_import
    from poisson_trace.ingest.writer import RECORD_KEYS

    _pair(tmp_path, tool)
    store = Store(tmp_path / "st")
    assert sorted(store.runs()) == ["new", "old"]
    junit = tmp_path / "junit-store"
    do_import("junit-a", junit, "j")
    want_schema = pq.read_schema(next((junit / "j").rglob("*.parquet")))
    for run, (missed, rows) in (("old", COUNTS[tool][:2]), ("new", COUNTS[tool][2:])):
        manifest = store.manifest(run)
        assert manifest.status == "complete" and manifest.backend == f"import:{tool}"
        assert manifest.target_id == f"import/{tool}"
        frame = store.read(run, meta=True, trace="full")
        assert len(frame) == rows
        tally = store.tally(run).to_dict()
        assert json.dumps(tally, default=str)
        for meta in frame["meta"]:
            assert set(meta["trace_signals"]) == set(RECORD_KEYS)
            assert meta["trace_signals"]["schema"] == "poisson.trace-signals/1"
        assert sum(1 for o in frame["outcome"] if o == "missed") == missed
        part = next((tmp_path / "st" / run).rglob("*.parquet"))
        assert pq.read_schema(part).remove_metadata() == want_schema.remove_metadata()
        events = [json.loads(line) for line in (tmp_path / "st" / run / "events.jsonl").read_text().splitlines()]
        # the run record's full log (section 17.3 item 6, SV1), where SA4 had two events
        kinds = [e["kind"] for e in events]
        assert kinds[:2] == ["planned", "started"] and kinds[-1] == "finished"
        assert set(kinds[2:-1]) == {"progress"}
        assert all(set(e) == {"schema", "at", "kind", "detail"} and e["schema"] == "poisson.run-event/1" for e in events)
        imported_block = manifest.to_dict()["environment"]["import"]
        assert imported_block["tool"] == tool and len(imported_block["taxonomy_sha256"]) == 64


# ---------- TF10-48 ----------


@pytest.mark.parametrize("tool", list(PAIRS))
def test_tf10_48_runs_and_where_say_the_run_has_no_traces(tmp_path: Path, tool: str) -> None:
    _pair(tmp_path, tool)
    with chdir(tmp_path):
        listed = trace(["runs", "--store", "st", "--json"])
        where = trace(["where", "old", "--store", "st", "--event", "missed", "--json"])
        text = trace(["where", "old", "--store", "st", "--event", "missed"])
    assert listed.code == 0 and where.code == 0 and text.code == 0, listed.text + where.text + text.text
    doc = json.loads(listed.out)
    found = json.dumps(doc)
    assert f"import:{tool}" in found, found
    note = json.loads(where.out)["note"]
    assert isinstance(note, str) and f"imported from {tool}" in note and "\n" not in note, note
    assert note in text.out.splitlines(), text.out


# ---------- TF10-49 ----------


@pytest.mark.parametrize("tool", list(PAIRS))
def test_tf10_49_fix_check_reads_each_pair(tmp_path: Path, tool: str) -> None:
    _pair(tmp_path, tool)
    with chdir(tmp_path):
        text = trace(["fix-check", "old", "new", "--store", "st", "--event", "missed", "--inputs", "all", "--max-mde", "0.5"])
        data = trace(["fix-check", "old", "new", "--store", "st", "--event", "missed", "--inputs", "all", "--max-mde", "0.5",
                      "--json"])
    assert text.code == 0 and data.code == 0, text.text + data.text
    doc = json.loads(data.out)
    blob = json.dumps(doc)
    old_missed, old_rows, new_missed, new_rows = COUNTS[tool]
    assert str(old_rows) in blob and str(new_rows) in blob, blob[:400]
    assert text.out.startswith(("different", "no significant difference", "too small to tell", "unconfirmed")), text.out[:120]


# ---------- TF10-50 ----------


def _help(tool: str) -> str:
    result = trace(["import", tool, "--help"])
    assert result.code == 0, result.text
    return result.out


@pytest.mark.parametrize("tool", ["deepeval", "ragas", "table", "junit"])
def test_tf10_50_each_earlier_reader_s_help_is_unchanged(tool: str) -> None:
    got = hashlib.sha256(_help(tool).encode("utf-8")).hexdigest()
    assert got == EARLIER_HELP_SHA[tool], (tool, got)


def test_tf10_50_the_earlier_imports_are_still_pinned() -> None:
    """TF21-64 pins what a verb reads of all eleven earlier imports and their --json; its file is
    under TF21's guard, unedited by this pair."""
    from test_tf21_frozen import FROZEN

    digest = hashlib.sha256((Path(__file__).parent / "test_tf21_unchanged.py").read_bytes()).hexdigest()
    assert digest == FROZEN["test_tf21_unchanged.py"]
    assert set(IMPORTS) >= {"deepeval-a", "junit-a", "ragas-base", "table-a"}
    assert all(Path(a).exists() for argv in IMPORTS.values() for a in argv if a.startswith(str(INGEST)))

