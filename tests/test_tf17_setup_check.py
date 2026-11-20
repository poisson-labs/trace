"""TF17-22 and TF17-24 to TF17-32: ``poisson-trace doctor --setup``, the check the setup file
names (``docs/setup-with-your-agent.md``, "The check"; its exit codes as the shared setup-file
page gives them).

- TF17-24: ready is exit 0 and, on stdout, ``ok  trace.toml is ready for the person to review``,
  then ``doctor``'s detail lines, then one ``  import  FILE: TOOL, N rows, …, not imported yet``
  line per pending ``[[import]]`` entry (a scored file says its metric and cut), then
  ``next: poisson-trace init``; nothing on stderr.
- TF17-25: not ready is exit 1, nothing on stdout, ``error:`` naming the first failing check's
  fact and one ``  next:`` line per failing check that has one (``doctor``'s ``not ready`` line
  is not printed); no ``trace.toml`` is not ready, its next ``poisson-trace init``.
- TF17-26: a ``trace.toml`` wrong by the config's rules (an unknown key, a wrong type, a
  ``[[import]]`` fault, a ``[signals]`` or ``[[taxonomy.rules]]`` fault) is exit 2 with the
  validation's line as the ``error:`` line.
- TF17-27: ``--json`` is ``poisson-trace.doctor/1`` (``schema``, ``verdict``, ``sentence``,
  ``checks``, ``next``) with ``doctor``'s six checks then one check named ``import`` per
  ``[[import]]`` entry, exit 0 or 1 as the text; ``--config PATH`` is carried in the next.
- TF17-28: each wrong setup: a missing file, a tool not in the install (``otel``), a metric not
  in the file, a cut no score reaches on one side or a cut with no side, a failure no run
  carries, a name used twice or refused, a store path that is no store, no failures set, no
  store and nothing to import, a file no reader reads, a folder with none of the tool's files, a
  folder that is a Prove store, a required option missing. A folder of two tools' files is not
  refused: the tool named reads its own files there.
- TF17-29: it writes nothing (no store, no run, no byte code in the repository), opens no
  connection and reads no key.
- TF17-30: plain ``doctor`` is unchanged: its lines on a ready config are those pinned here, and
  on a config with pending entries and no store it still says the config names no store (exit 4).
- TF17-31: a config with no store is ready when it has pending entries that read, and not ready
  when it has none; the imports' store named and holding no run yet is ready; an entry already
  imported is not pending and has no line.
- TF17-32: the failures are checked against the stores' runs and the pending files' rows
  together: a failure only a pending file carries is ready.
- TF17-22: an entry is pending when no run of the imports' store (``[store.imported]``, else
  ``[store]``, else ``trace-store`` beside the config) answers to its ``name``.
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from tf1_support import shell_words, tau2_copy
from tf2_support import config_of, doctor, no_network, scratch_home, work, write_config  # noqa: F401
from pin_support import OR_LATER, installed
from tf17_support import (
    CS_FAILURES, CS_RECORD, CS_REPLAY, DOCS_URL, NEXT_COMMAND, SETUP_READY, SETUP_SCHEMA,
    config_text, cs_store, detail, expected_toml, import_entry, import_lines, junit_entry,
    junit_pair, ragas_entry, ragas_pair, refusal, sample_repo, setup_check, setup_doc, snapshot,
    trace_in, usage, users_own_files, write_toml,
)

DOCTOR_CHECKS = ("python", "package", "prove", "config", "names", "readers")
PENDING = {
    "evals/results/rag-base.jsonl": ("ragas", 150, "faithfulness at 0.5"),
    "evals/results/rag-raft.jsonl": ("ragas", 150, "faithfulness at 0.5"),
    "reports/junit-old.xml": ("junit", 656, ""),
    "reports/junit-new.xml": ("junit", 656, ""),
}


def ready_repo(tmp_path: Path) -> Path:
    return sample_repo(tmp_path, with_expected=True)


# ---------- TF17-24 ----------


def test_tf17_24_ready_prints_the_verdict_doctors_lines_the_pending_files_and_next_init(tmp_path: Path) -> None:
    repo = ready_repo(tmp_path)
    r = setup_check(repo)
    assert r.code == 0, r.text
    assert r.err == "", r.err
    lines = r.out.splitlines()
    assert lines[0] == SETUP_READY, lines[0]
    for name in DOCTOR_CHECKS:
        assert detail(r.out, name), (name, r.out)
    pending = import_lines(r.out)
    assert {p["file"]: (p["tool"], p["rows"]) for p in pending} == {f: (t, n) for f, (t, n, _) in PENDING.items()}, r.out
    for p in pending:
        assert PENDING[p["file"]][2] in p["said"], p
    assert [p["file"] for p in pending] == list(PENDING), "the lines are in the file's order"
    assert lines[-1] == f"next: {NEXT_COMMAND}", lines[-1]
    assert DOCS_URL not in r.out


# ---------- TF17-25 ----------


def test_tf17_25_not_ready_is_an_error_line_and_a_next_per_failing_check(tmp_path: Path) -> None:
    repo = ready_repo(tmp_path)
    (repo / "evals" / "results" / "rag-raft.jsonl").unlink()
    r = setup_check(repo)
    line, nexts = refusal(r)
    assert "evals/results/rag-raft.jsonl" in line, line
    assert "not ready" not in r.err, r.err
    assert nexts, r.err


def test_tf17_25_no_config_is_not_ready_and_the_next_is_init(tmp_path: Path) -> None:
    repo = sample_repo(tmp_path)
    line, nexts = refusal(setup_check(repo))
    assert "trace.toml" in line, line
    assert any(shell_words(n) == ["poisson-trace", "init"] for n in nexts), nexts


def test_tf17_25_two_failing_checks_give_two_nexts_and_the_first_fact(tmp_path: Path) -> None:
    repo = ready_repo(tmp_path)
    shutil.rmtree(repo / "store")
    (repo / "reports" / "junit-new.xml").unlink()
    line, nexts = refusal(setup_check(repo))
    assert "store" in line, line
    assert len(nexts) >= 2, nexts


# ---------- TF17-26 ----------

FAULTS = [
    ("an unknown key", 'version = 1\n[events]\nfaild = ["x"]\n', "faild"),
    ("a wrong type", 'version = 1\n[store]\npath = 3\n', "path"),
    ("an import fault", config_text(ragas_entry("e.jsonl", "r", metrc="x"), store="store"), "metrc"),
    ("a tool not in the install", config_text(import_entry("e.jsonl", "otel", "r"), store="store"), "otel"),
    ("a signals fault", config_text(ragas_entry("evals/results/rag-base.jsonl", "r"), '[signals]\ncut = "high"\n', store="store"), "cut"),
    ("a rules fault", config_text(ragas_entry("evals/results/rag-base.jsonl", "r"), '[[taxonomy.rules]]\nfailure_kind = "oops"\nwhen_span_kind = "tool"\n', store="store"), "oops"),
]


@pytest.mark.parametrize("case,text,fact", FAULTS, ids=[c for c, _, _ in FAULTS])
def test_tf17_26_a_config_wrong_under_the_config_rules_is_exit_2_with_the_validations_line(tmp_path: Path, case: str, text: str, fact: str) -> None:
    repo = sample_repo(tmp_path)
    write_toml(repo, text)
    line = usage(setup_check(repo))
    assert line.startswith("error: trace.toml line ") and fact in line, line


# ---------- TF17-27 ----------


def test_tf17_27_json_is_the_doctor_document_with_an_import_check_per_entry(tmp_path: Path) -> None:
    repo = ready_repo(tmp_path)
    code, data = setup_doc(repo)
    assert code == 0 and data["schema"] == SETUP_SCHEMA and data["verdict"] == "ok", data
    assert list(data) == ["schema", "verdict", "sentence", "checks", "next"], list(data)
    names = [c["name"] for c in data["checks"]]
    assert names == [*DOCTOR_CHECKS, *["import"] * 4], names
    for c in data["checks"]:
        assert list(c) == ["name", "ok", "line", "next"] and c["ok"] is True and c["next"] is None, c
    imports = [c["line"] for c in data["checks"] if c["name"] == "import"]
    assert all(any(f in line for f in PENDING) for line in imports), imports
    assert data["next"] == NEXT_COMMAND
    (repo / "reports" / "junit-new.xml").unlink()
    r = setup_check(repo, "--json")
    assert r.code == 1 and r.err == "", r.text
    data = r.json()
    assert data["verdict"] == "not ready" and "junit-new.xml" in data["sentence"], data
    failing = [c for c in data["checks"] if not c["ok"]]
    assert len(failing) == 1 and failing[0]["name"] == "import" and failing[0]["next"], failing


def test_tf17_27_config_path_is_read_and_carried(tmp_path: Path) -> None:
    repo = sample_repo(tmp_path)
    (repo / "team.toml").write_text(expected_toml(), encoding="utf-8")
    r = setup_check(repo, "--config", "team.toml")
    assert r.code == 0, r.text
    assert r.out.splitlines()[0] == "ok  team.toml is ready for the person to review", r.out
    assert r.out.splitlines()[-1] == "next: poisson-trace init --config team.toml", r.out
    code, data = setup_doc(repo, "--config", "team.toml")
    assert code == 0 and data["next"] == "poisson-trace init --config team.toml"


# ---------- TF17-28 ----------


@dataclass(frozen=True)
class Row:
    edit: Callable[[Path], None]
    code: int
    #: facts on the error line
    facts: tuple[str, ...] = ()


def edit_toml(old: str, new: str) -> Callable[[Path], None]:
    def apply(repo: Path) -> None:
        text = (repo / "trace.toml").read_text(encoding="utf-8")
        assert text.count(old) >= 1, old
        (repo / "trace.toml").write_text(text.replace(old, new), encoding="utf-8")
    return apply


def write(text: str) -> Callable[[Path], None]:
    def apply(repo: Path) -> None:
        (repo / "trace.toml").write_text(text, encoding="utf-8")
    return apply


def remove(path: str) -> Callable[[Path], None]:
    def apply(repo: Path) -> None:
        target = repo / path
        shutil.rmtree(target) if target.is_dir() else target.unlink()
    return apply


def test_tf17_28_a_folder_of_two_tools_reads_the_named_tools_files_alone(tmp_path: Path) -> None:
    """The tool named reads its files alone, so a mixed folder under a junit entry is the
    JUnit report it holds."""
    repo = ready_repo(tmp_path)
    (repo / "mixed").mkdir()
    shutil.copy(repo / "evals" / "results" / "rag-base.jsonl", repo / "mixed" / "rag-base.jsonl")
    shutil.copy(repo / "reports" / "junit-old.xml", repo / "mixed" / "junit-old.xml")
    edit_toml('file = "reports/junit-old.xml"', 'file = "mixed"')(repo)
    r = setup_check(repo)
    assert r.code == 0, r.text
    assert [p for p in import_lines(r.out) if p["file"] == "mixed"][0]["tool"] == "junit", r.out


WRONG = {
    "a missing file": Row(remove("evals/results/rag-base.jsonl"), 1, ("evals/results/rag-base.jsonl",)),
    "a tool not in the install": Row(edit_toml('tool = "junit"', 'tool = "otel"'), 2, ("otel", "not in this install")),
    "a metric not in the file": Row(edit_toml('metric = "faithfulness"', 'metric = "precision"'), 1, ("precision", "rag-base.jsonl")),
    "a cut every row misses": Row(edit_toml("cut = 0.5", "cut = 2.0"), 1, ("2.0", "rag-base.jsonl")),
    "a cut every row meets": Row(edit_toml("cut = 0.5", "cut = -1.0"), 1, ("-1.0", "rag-base.jsonl")),
    "a failure no run carries": Row(edit_toml('"max_turns"', '"max_turnz"'), 1, ("max_turnz",)),
    "a name used twice": Row(edit_toml('name = "rag-raft"', 'name = "rag-base"'), 2, ("rag-base",)),
    "a name refused": Row(edit_toml('name = "rag-raft"', 'name = "latest"'), 2, ("latest",)),
    "a store path that is no store": Row(edit_toml('path = "store"', 'path = "evals"'), 1, ("evals",)),
    "no failures set": Row(edit_toml('failed = ["forbidden_action", "unresolved", "max_turns", "app_error"]', ""), 1, ("failure",)),
    "no store and nothing to import": Row(write("version = 1\n\n[events]\nfailed = [\"x\"]\n"), 1, ("store",)),
    "a file no reader reads": Row(edit_toml('file = "reports/junit-old.xml"', 'file = "pyproject.toml"'), 1, ("pyproject.toml",)),
    "a folder with none of the tool's files": Row(edit_toml('file = "reports/junit-old.xml"', 'file = "evals"'), 1, ("evals",)),
    "a folder that is a Prove store": Row(edit_toml('file = "reports/junit-old.xml"', 'file = "store"'), 1, ("store",)),
    "a required option missing": Row(edit_toml('case_column = "case"\n', ""), 2, ("case_column",)),
    "a cut with no side": Row(edit_toml("below = true\n", ""), 1, ("rag-base.jsonl",)),
}


@pytest.mark.parametrize("case", list(WRONG))
def test_tf17_28_each_wrong_setup_is_refused_with_its_facts(tmp_path: Path, case: str, no_network: list[str]) -> None:  # noqa: F811
    repo = ready_repo(tmp_path)
    users_own_files(repo)
    WRONG[case].edit(repo)
    home = Path(os.environ["HOME"])
    before = snapshot(repo, home)
    r = setup_check(repo)
    if WRONG[case].code == 2:
        line = usage(r)
    else:
        line, _ = refusal(r)
    for fact in WRONG[case].facts:
        assert fact in line, (fact, line)
    assert snapshot(repo, home) == before
    assert no_network == []
    assert "sk-not-a-real-key" not in r.text


# ---------- TF17-29 ----------


def test_tf17_29_the_check_writes_nothing_opens_no_connection_and_reads_no_key(tmp_path: Path, no_network: list[str]) -> None:  # noqa: F811
    repo = ready_repo(tmp_path)
    users_own_files(repo)
    home = Path(os.environ["HOME"])
    elsewhere = work(tmp_path, "elsewhere")
    before = snapshot(repo, home, elsewhere)
    r = setup_check(repo)
    assert r.code == 0, r.text
    assert snapshot(repo, home, elsewhere) == before
    assert not (repo / "trace-store").exists() and not (repo / ".poisson").exists()
    assert not list(repo.rglob("__pycache__"))
    assert no_network == []
    assert "sk-not-a-real-key" not in r.text


# ---------- TF17-30 ----------


def test_tf17_30_plain_doctor_is_unchanged_on_a_ready_config(tmp_path: Path) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    write_config(folder, config_of("proofload-runs"))
    r = doctor(folder)
    assert r.code == 0 and r.err == "", r.text
    lines = [line for line in r.out.splitlines() if not re.match(r"^  (?:python|package|readers) ", line)]
    assert lines == [
        "ok  this environment is ready",
        f"  prove     poisson-prove {installed()} (Trace reads version {OR_LATER})",  # the floor
        "  config    trace.toml: store proofload-runs (3 runs, 3 complete, 0 partial), failures unsolved",
        "  names     proofload-runs: no names of yours yet",
        "next: poisson-trace runs",
    ], r.out


def test_tf17_30_plain_doctor_on_pending_entries_and_no_store_still_fails_the_config(tmp_path: Path) -> None:
    folder = work(tmp_path)
    base, raft = ragas_pair(folder)
    write_toml(folder, config_text(ragas_entry(base, "old"), ragas_entry(raft, "new"), store=None, events=("missed",)))
    r = doctor(folder)
    assert r.code == 4, r.text
    assert "names no store yet" in r.out and "not ready" in r.out.splitlines()[0], r.out


# ---------- TF17-31 and TF17-22 ----------


def test_tf17_31_no_store_is_ready_with_pending_entries_that_read(tmp_path: Path) -> None:
    folder = work(tmp_path)
    base, raft = ragas_pair(folder)
    write_toml(folder, config_text(ragas_entry(base, "old"), ragas_entry(raft, "new"), store=None, events=("missed",)))
    r = setup_check(folder)
    assert r.code == 0, r.text
    assert [p["file"] for p in import_lines(r.out)] == [base, raft]
    assert r.out.splitlines()[-1] == f"next: {NEXT_COMMAND}"


def test_tf17_31_no_store_and_no_entry_is_not_ready(tmp_path: Path) -> None:
    folder = work(tmp_path)
    write_toml(folder, config_text(store=None, events=("missed",)))
    line, nexts = refusal(setup_check(folder))
    assert "store" in line, line
    assert nexts, line


def test_tf17_31_the_imports_store_named_and_empty_is_ready(tmp_path: Path) -> None:
    folder = work(tmp_path)
    base, raft = ragas_pair(folder)
    write_toml(folder, config_text(ragas_entry(base, "old"), ragas_entry(raft, "new"), store="trace-store", events=("missed",)))
    r = setup_check(folder)
    assert r.code == 0, r.text
    (folder / "trace-store").mkdir()
    r = setup_check(folder)
    assert r.code == 0, r.text
    assert len(import_lines(r.out)) == 2


def test_tf17_22_an_entry_whose_run_is_in_the_imports_store_is_not_pending(tmp_path: Path) -> None:
    folder = work(tmp_path)
    base, raft = ragas_pair(folder)
    r = trace_in(folder, ["import", "ragas", base, "--store", "trace-store", "--run", "old", "--metric", "faithfulness", "--cut", "0.5", "--below", "--case-column", "case"])
    assert r.code == 0, r.text
    # [store] is the imports' store when there is no [store.imported]
    write_toml(folder, config_text(ragas_entry(base, "old"), ragas_entry(raft, "new"), store="trace-store", events=("missed",)))
    r = setup_check(folder)
    assert r.code == 0, r.text
    assert [p["file"] for p in import_lines(r.out)] == [raft], r.out
    assert r.out.splitlines()[-1] == f"next: {NEXT_COMMAND}"
    # a Prove store first, the imports in [store.imported]
    store = cs_store(folder)
    write_toml(folder, config_text(ragas_entry(base, "old"), ragas_entry(raft, "new"), store=store, imported="trace-store", events=CS_FAILURES))
    r = setup_check(folder)
    assert r.code == 0, r.text
    assert [p["file"] for p in import_lines(r.out)] == [raft], r.out
    # nothing pending: ready, no import line, doctor's own next
    r = trace_in(folder, ["import", "ragas", raft, "--store", "trace-store", "--run", "new", "--metric", "faithfulness", "--cut", "0.5", "--below", "--case-column", "case"])
    assert r.code == 0, r.text
    r = setup_check(folder)
    assert r.code == 0 and import_lines(r.out) == [], r.text
    assert r.out.splitlines()[-1] == "next: poisson-trace runs", r.out


def test_tf17_22_without_a_store_table_the_imports_store_is_trace_store_beside_the_config(tmp_path: Path) -> None:
    folder = work(tmp_path)
    (folder / "conf").mkdir()
    base, raft = ragas_pair(folder / "conf")
    r = trace_in(folder, ["import", "ragas", f"conf/{base}", "--store", "conf/trace-store", "--run", "old", "--metric", "faithfulness", "--cut", "0.5", "--below", "--case-column", "case"])
    assert r.code == 0, r.text
    write_toml(folder / "conf", config_text(ragas_entry(base, "old"), ragas_entry(raft, "new"), store=None, events=("missed",)))
    r = setup_check(folder, "--config", "conf/trace.toml")
    assert r.code == 0, r.text
    assert [p["file"] for p in import_lines(r.out)] == [raft], r.out


# ---------- TF17-32 ----------


def test_tf17_32_a_failure_only_a_pending_file_carries_is_ready(tmp_path: Path) -> None:
    folder = work(tmp_path)
    store = cs_store(folder)
    old, new = junit_pair(folder)
    write_toml(folder, config_text(junit_entry(old, "old"), junit_entry(new, "new"), store=store, events=(*CS_FAILURES, "missed")))
    r = setup_check(folder)
    assert r.code == 0, r.text
    write_toml(folder, config_text(junit_entry(old, "old"), junit_entry(new, "new"), store=store, events=("missed", "nope")))
    line, _ = refusal(setup_check(folder))
    assert "nope is carried by no" in line and "missed is carried" not in line and "missed, nope is carried" not in line, line
    assert CS_RECORD not in line and CS_REPLAY not in line, "no run id is something to type"
