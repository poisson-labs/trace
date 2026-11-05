"""RUNREC-20 to RUNREC-25: ``produced_by`` in each imported run's manifest (invariant 3; spec
section 17.3 item 6; the artifact format's section 4.1, format 1.1; RR3, RR4).

Read as the static pages will read it (section 17.3 item 7: the runs view names the tool an
import came from): plain JSON from ``<store>/<run>/manifest.json``, never through Prove's
``RunManifest``, which does not carry the key. The format's shared members are ``version`` (the
writing tool's, Trace's) and ``from`` (``{"name", "sha256"}`` per thing the run was made from,
named without a folder and digested over its bytes); Trace's own are ``tool``
(``poisson-trace``), ``reader`` (the tool the results came from, as the import names it) and
``options`` (what the import declared, as its ``--json`` prints ``declared``). ``from`` lists
every file the import read, in its ``--json`` order (RR4: the spec's "one" predates several
files and folders), then the ``--verdicts`` file when one was joined."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import FIXTURES
from runrec_support import (
    FAST, HEX64, PRODUCED_BY_KEYS, READERS, SLOW, SUITE_1, TOOL, all_strings, import_json,
    import_key, manifest_json, produced_by, sha256_file, suite_verdicts, trace_version, unpacked_inspect,
)
from tf21_support import run_import


def _check(root: Path, run: str, data: dict[str, Any], reader: str) -> dict[str, Any]:
    got = produced_by(root, run)
    assert set(got) == PRODUCED_BY_KEYS, sorted(got)
    assert got["version"] == trace_version()
    assert got["tool"] == TOOL
    assert got["reader"] == reader == data["tool"]
    assert got["options"] == data["declared"]
    assert isinstance(got["from"], list) and got["from"]
    for entry in got["from"]:
        assert list(entry) == ["name", "sha256"], entry
        assert isinstance(entry["name"], str) and HEX64.fullmatch(entry["sha256"]), entry
    files = [{"name": f["name"], "sha256": f["sha256"]} for f in data["files"]]
    assert got["from"][: len(files)] == files
    return got


# ---------- RUNREC-20: every reader ----------


@pytest.mark.parametrize("key", FAST)
def test_runrec_20_each_import_records_produced_by(tmp_path: Path, key: str) -> None:
    root = tmp_path / "store"
    data = import_json(key, root, "r")
    got = _check(root, "r", data, READERS[key][0])
    assert len(got["from"]) == len(data["files"])


@pytest.mark.slow
@pytest.mark.parametrize("key", SLOW)
def test_runrec_20_slow_every_other_import_records_produced_by(tmp_path: Path, key: str) -> None:
    root = tmp_path / "store"
    data = import_json(key, root, "r")
    got = _check(root, "r", data, READERS[key][0])
    assert len(got["from"]) == len(data["files"])


# ---------- RUNREC-21: what each file's digest is over ----------


def test_runrec_21_a_files_digest_is_over_its_bytes(tmp_path: Path) -> None:
    root = tmp_path / "store"
    import_key("junit-suite", root, "r")
    junit = FIXTURES / "ingest" / "junit"
    assert produced_by(root, "r")["from"] == [
        {"name": "trace-suite-1.xml", "sha256": sha256_file(junit / "trace-suite-1.xml")},
        {"name": "trace-suite-2.xml", "sha256": sha256_file(junit / "trace-suite-2.xml")},
    ]


def test_runrec_21_a_compressed_file_is_digested_as_given(tmp_path: Path) -> None:
    root = tmp_path / "store"
    import_key("ragas-causal", root, "r")
    path = FIXTURES / "ingest" / "ragas" / "memory-causal.jsonl.gz"
    assert produced_by(root, "r")["from"] == [{"name": path.name, "sha256": sha256_file(path)}]


def test_runrec_21_an_unpacked_inspect_folder_is_its_one_entry(tmp_path: Path) -> None:
    from tf10_support import in_argv

    folder = unpacked_inspect(tmp_path)
    root = tmp_path / "store"
    out = run_import([*in_argv(folder, root, "r"), "--json"])
    assert out.code == 0, out.out + out.err
    data = json.loads(out.out)
    got = _check(root, "r", data, "inspect")
    assert [e["name"] for e in got["from"]] == ["inspect-log/"]


# ---------- RUNREC-22: no folder, no absolute path ----------


@pytest.mark.parametrize("key", ["junit-a", "promptfoo-old", "inspect-json", "openai-evals-old"])
def test_runrec_22_no_path_reaches_produced_by(tmp_path: Path, key: str) -> None:
    root = tmp_path / "store"
    import_key(key, root, "r")
    got = produced_by(root, "r")
    for text in all_strings(got):
        assert str(tmp_path) not in text and str(FIXTURES) not in text, text
    assert all("/" not in e["name"].rstrip("/") for e in got["from"]), got["from"]


# ---------- RUNREC-23: a --verdicts file is what the run was made from too (RR4) ----------


def test_runrec_23_the_verdicts_file_follows_the_files(tmp_path: Path) -> None:
    root = tmp_path / "store"
    verdicts = suite_verdicts(tmp_path / "private" / "grades.csv")
    out = run_import(["junit", str(SUITE_1), "--store", str(root), "--run", "r", "--verdicts",
                      str(verdicts), "--json"])
    assert out.code == 0, out.out + out.err
    data = json.loads(out.out)
    got = _check(root, "r", data, "junit")
    assert got["from"] == [
        {"name": SUITE_1.name, "sha256": sha256_file(SUITE_1)},
        {"name": "grades.csv", "sha256": sha256_file(verdicts)},
    ]
    assert str(verdicts.parent) not in json.dumps(got)


def test_runrec_23_without_verdicts_from_holds_the_files_alone(tmp_path: Path) -> None:
    root = tmp_path / "store"
    out = run_import(["junit", str(SUITE_1), "--store", str(root), "--run", "r", "--json"])
    assert out.code == 0, out.out + out.err
    assert produced_by(root, "r")["from"] == [{"name": SUITE_1.name, "sha256": sha256_file(SUITE_1)}]


# ---------- RUNREC-24: the manifest stays the import's record ----------


def test_runrec_24_reading_verbs_leave_the_manifest_as_it_is(tmp_path: Path) -> None:
    from tf0_support import trace

    root = tmp_path / "store"
    import_key("junit-a", root, "a")
    import_key("junit-a", root, "b")
    held = {r: (root / r / "manifest.json").read_bytes() for r in ("a", "b")}
    for argv in (["runs"], ["where", "a", "--event", "missed"],
                 ["fix-check", "a", "b", "--event", "missed", "--inputs", "all", "--max-mde", "0.5",
                  "--save"],
                 ["changes", "a", "b", "--event", "missed"], ["name", "a", "first"]):
        ran = trace([*argv, "--store", str(root)])
        assert ran.code == 0, (argv, ran.out + ran.err)
    assert {r: (root / r / "manifest.json").read_bytes() for r in ("a", "b")} == held


def test_runrec_24_the_import_block_keeps_its_place(tmp_path: Path) -> None:
    # produced_by is beside what the import recorded, never in place of it (SA5's block stays)
    root = tmp_path / "store"
    data = import_json("junit-a", root, "r")
    block = manifest_json(root, "r")["environment"]["import"]
    assert block["tool"] == "junit" and block["declared"] == data["declared"]
    assert block["files"] == data["files"]
    assert "produced_by" not in block


# ---------- RUNREC-25: the format's reading ----------


def test_runrec_25_a_reader_of_the_shared_members_reads_what_it_needs(tmp_path: Path) -> None:
    root = tmp_path / "store"
    import_key("promptfoo-old", root, "r")
    doc = manifest_json(root, "r")
    shared = {k: doc["produced_by"][k] for k in ("version", "from")}
    assert isinstance(shared["version"], str) and shared["version"]
    assert [sorted(e) for e in shared["from"]] == [["name", "sha256"]]
    # the manifest is one JSON document, as Prove writes it
    text = (root / "r" / "manifest.json").read_text(encoding="utf-8")
    assert text.endswith("\n") and json.loads(text) == doc
