"""TF17-33 to TF17-41: ``init`` on a ``trace.toml`` with pending ``[[import]]`` entries, the
hand-over from the agent's file (``docs/setup-with-your-agent.md``, "The hand-over, and what
you do next").

- TF17-33: on a terminal, init shows the stores, the failures and the pending files, then asks
  ``Import these N files as the runs named here? [y/N]``; Enter or ``n`` writes nothing and
  ends ``ok``, with the files still pending; ``y`` imports.
- TF17-34: a yes (``--yes``, ``--import``, or ``y``) imports the pending entries into
  ``trace-store`` beside the config, each as the run its ``name`` says with its options, and
  writes ``trace.toml`` once, keeping every line the agent wrote and adding one table at the
  end: ``[store] path = "trace-store"`` when the config names no store, ``[store.imported] path
  = "trace-store"`` when ``[store]`` is a Prove store, nothing when the config names the imports'
  store already. It ends with ``next: poisson-trace doctor``, and doctor then reads ready.
- TF17-35: ``--no-import`` leaves the entries pending and writes nothing.
- TF17-36: stdin not a terminal without ``--yes`` is refused before the question,
  and nothing is written.
- TF17-37: a ``trace.toml`` with nothing pending is refused without ``--force``, as any config is;
  with ``--force`` init sets up again.
- TF17-38: a refusal on any entry (a file that reads but whose metric is not in it; a file
  missing) writes no run and leaves the config as it was.
- TF17-39: entries already imported are left as they are: a second init imports the pending
  ones only, and the earlier runs' bytes do not change.
- TF17-40: the summary names the runs imported and the store, carries one ``  import`` line per
  run (the ``poisson-trace import`` command that wrote it), and ``--json`` is
  ``poisson-trace.init/1`` with the stores (the config's, the imports' with its run count), the
  events and ``next``.
- TF17-41: a pending config with no ``[events]`` gets its failures after the import: the
  question over the runs the store holds (the Prove store's when there is one, else the imported
  runs), or with ``--yes`` the default, every outcome that is not a word for success, written
  into ``trace.toml`` as ``[events]``; nothing else in the file changes.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from tf1_support import shell_words
from tf2_support import doctor, init_yes, refused, scratch_home, tty, work  # noqa: F401
from tf17_support import (
    CS_FAILURES, INIT_KEYS, INIT_SCHEMA, config_text, cs_store, expected_toml, import_lines,
    junit_entry, junit_pair, ragas_entry, ragas_pair, read_toml, rows_of, runs_in, sample_repo,
    setup_check, snapshot, trace_in, write_toml,
)

QUESTION = re.compile(r"Import these (\d+) files as the runs named here\? \[y/N\]")
NEXT_DOCTOR = "poisson-trace doctor"


def pending_repo(tmp_path: Path) -> Path:
    return sample_repo(tmp_path, with_expected=True)


def no_store_folder(tmp_path: Path, events: tuple[str, ...] | None = ("missed",)) -> tuple[Path, str, str]:
    folder = work(tmp_path)
    base, raft = ragas_pair(folder)
    write_toml(folder, config_text(ragas_entry(base, "old"), ragas_entry(raft, "new"), store=None, events=events))
    return folder, base, raft


def imported_into(repo: Path) -> list[str]:
    return runs_in(repo / "trace-store")


# ---------- TF17-33 ----------


@pytest.mark.parametrize("answer", ["", "n"])
def test_tf17_33_on_a_terminal_the_question_defaults_to_no_and_writes_nothing(tmp_path: Path, answer: str) -> None:
    repo = pending_repo(tmp_path)
    before = snapshot(repo)
    r = tty(["init"], [answer], cwd=repo)
    assert r.code == 0, r.text
    m = QUESTION.search(r.err)
    assert m and m.group(1) == "4", r.err
    for fact in ("store", *CS_FAILURES, "evals/results/rag-base.jsonl", "reports/junit-new.xml"):
        assert fact in r.err, (fact, r.err)
    assert snapshot(repo) == before
    assert r.out.startswith("ok  ") and "pending" in r.out.splitlines()[0] and "4" in r.out.splitlines()[0], r.out
    assert [line for line in r.out.splitlines() if line.startswith("next: poisson-trace")], r.out


def test_tf17_33_y_imports(tmp_path: Path) -> None:
    repo = pending_repo(tmp_path)
    r = tty(["init"], ["y"], cwd=repo)
    assert r.code == 0, r.text
    assert QUESTION.search(r.err), r.err
    assert imported_into(repo) == ["rag-base", "rag-raft", "tests-new", "tests-old"]


# ---------- TF17-34 ----------


def test_tf17_34_yes_imports_into_trace_store_and_adds_the_imported_store_beside_a_prove_store(tmp_path: Path) -> None:
    repo = pending_repo(tmp_path)
    r = init_yes(repo)
    assert r.code == 0, r.text
    assert imported_into(repo) == ["rag-base", "rag-raft", "tests-new", "tests-old"]
    text = (repo / "trace.toml").read_text(encoding="utf-8")
    assert text.startswith(expected_toml()), text
    assert text == expected_toml() + '\n[store.imported]\npath = "trace-store"\n', text
    doc = read_toml(repo)
    assert doc["store"] == {"path": "store", "imported": {"path": "trace-store"}}
    assert r.out.splitlines()[-1] == f"next: {NEXT_DOCTOR}", r.out
    # the runs as the entries say
    old = rows_of(repo / "trace-store", "rag-base")
    assert len(old) == 150 and {row["outcome"] for row in old if isinstance(row["outcome"], str)} == {"met", "missed"}
    tests = rows_of(repo / "trace-store", "tests-old")
    assert len(tests) == 656
    # doctor then reads ready, and the setup check has nothing pending
    d = doctor(repo)
    assert d.code == 0, d.text
    assert "store imported at trace-store (4 runs" in d.out, d.out
    s = setup_check(repo)
    assert s.code == 0 and import_lines(s.out) == [], s.text


def test_tf17_34_with_no_store_the_imported_store_becomes_the_store(tmp_path: Path) -> None:
    folder, base, raft = no_store_folder(tmp_path)
    before = (folder / "trace.toml").read_text(encoding="utf-8")
    r = init_yes(folder)
    assert r.code == 0, r.text
    assert imported_into(folder) == ["new", "old"]
    text = (folder / "trace.toml").read_text(encoding="utf-8")
    assert text == before + '\n[store]\npath = "trace-store"\n', text
    assert doctor(folder).code == 0


def test_tf17_34_the_store_is_beside_the_config_and_written_from_its_folder(tmp_path: Path) -> None:
    folder = work(tmp_path)
    (folder / "conf").mkdir()
    base, raft = ragas_pair(folder / "conf")
    write_toml(folder / "conf", config_text(ragas_entry(base, "old"), ragas_entry(raft, "new"), store=None, events=("missed",)))
    r = init_yes(folder, "--config", "conf/trace.toml")
    assert r.code == 0, r.text
    assert runs_in(folder / "conf" / "trace-store") == ["new", "old"]
    assert not (folder / "trace-store").exists()
    assert read_toml(folder / "conf")["store"] == {"path": "trace-store"}
    assert r.out.splitlines()[-1] == "next: poisson-trace doctor --config conf/trace.toml", r.out


def test_tf17_34_a_config_naming_the_imports_store_already_gets_no_table(tmp_path: Path) -> None:
    folder, base, raft = no_store_folder(tmp_path)
    text = config_text(ragas_entry(base, "old"), ragas_entry(raft, "new"), store="trace-store", events=("missed",))
    write_toml(folder, text)
    r = init_yes(folder)
    assert r.code == 0, r.text
    assert (folder / "trace.toml").read_text(encoding="utf-8") == text
    assert imported_into(folder) == ["new", "old"]


def test_tf17_34_import_on_a_terminal_asks_nothing(tmp_path: Path) -> None:
    repo = pending_repo(tmp_path)
    r = tty(["init", "--import"], [], cwd=repo)
    assert r.code == 0, r.text
    assert not QUESTION.search(r.err), r.err
    assert len(imported_into(repo)) == 4


# ---------- TF17-35 ----------


def test_tf17_35_no_import_leaves_the_entries_pending_and_writes_nothing(tmp_path: Path) -> None:
    repo = pending_repo(tmp_path)
    before = snapshot(repo)
    r = init_yes(repo, "--no-import")
    assert r.code == 0, r.text
    assert snapshot(repo) == before
    assert not (repo / "trace-store").exists()
    s = setup_check(repo)
    assert len(import_lines(s.out)) == 4


# ---------- TF17-36 ----------


def test_tf17_36_stdin_not_a_terminal_without_yes_is_refused_before_the_question(tmp_path: Path) -> None:
    repo = pending_repo(tmp_path)
    before = snapshot(repo)
    r = trace_in(repo, ["init"])
    line = refused(r)
    assert "stdin is not a terminal" in line and "--yes" in line, line
    assert not QUESTION.search(r.err), r.err
    assert snapshot(repo) == before


# ---------- TF17-37 ----------


def test_tf17_37_nothing_pending_is_refused_as_today_and_force_sets_up_again(tmp_path: Path) -> None:
    repo = pending_repo(tmp_path)
    assert init_yes(repo).code == 0
    before = snapshot(repo)
    r = init_yes(repo)
    line = refused(r)
    assert "there already" in line and "--force" in line, line
    assert snapshot(repo) == before
    r = init_yes(repo, "--force", "--store", "store", "--event", "unresolved")
    assert r.code == 0, r.text
    doc = read_toml(repo)
    assert "import" not in doc and doc["store"] == {"path": "store"} and doc["events"] == {"failed": ["unresolved"]}


# ---------- TF17-38 ----------


@pytest.mark.parametrize("case", ["a metric not in the second file", "the second file missing"])
def test_tf17_38_a_refusal_on_any_entry_writes_nothing(tmp_path: Path, case: str) -> None:
    folder, base, raft = no_store_folder(tmp_path)
    if case == "a metric not in the second file":
        write_toml(folder, config_text(ragas_entry(base, "old"), ragas_entry(raft, "new", metric="precision"), store=None, events=("missed",)))
    else:
        (folder / raft).unlink()
    before = snapshot(folder)
    r = init_yes(folder)
    line = refused(r)
    assert raft in line, line
    assert snapshot(folder) == before
    assert not (folder / "trace-store").exists()


# ---------- TF17-39 ----------


def test_tf17_39_a_second_init_imports_the_pending_entries_only(tmp_path: Path) -> None:
    folder, base, raft = no_store_folder(tmp_path)
    write_toml(folder, config_text(ragas_entry(base, "old"), store=None, events=("missed",)))
    assert init_yes(folder).code == 0
    assert imported_into(folder) == ["old"]
    earlier = snapshot(folder / "trace-store")
    text = (folder / "trace.toml").read_text(encoding="utf-8")
    # the agent (or the person) adds the second entry; the store table init added is kept
    write_toml(folder, text + "\n" + ragas_entry(raft, "new"))
    s = setup_check(folder)
    assert [p["file"] for p in import_lines(s.out)] == [raft], s.out
    r = init_yes(folder)
    assert r.code == 0, r.text
    assert "1 run" in r.out.splitlines()[0], r.out
    assert imported_into(folder) == ["new", "old"]
    after = snapshot(folder / "trace-store")
    assert all(after[k] == v for k, v in earlier.items()), "the earlier run's bytes changed"
    assert (folder / "trace.toml").read_text(encoding="utf-8") == text + "\n" + ragas_entry(raft, "new")


# ---------- TF17-40 ----------


def test_tf17_40_the_summary_and_the_json(tmp_path: Path) -> None:
    repo = pending_repo(tmp_path)
    r = init_yes(repo)
    assert r.code == 0, r.text
    first = r.out.splitlines()[0]
    assert first.startswith("ok  ") and "4 runs" in first and "trace-store" in first, first
    lines = [shell_words(line.strip()[len("import"):].strip()) for line in r.out.splitlines() if line.strip().startswith("import   poisson-trace import ")]
    assert len(lines) == 4, r.out
    by_run = {words[words.index("--run") + 1]: words for words in lines}
    assert set(by_run) == {"rag-base", "rag-raft", "tests-old", "tests-new"}, by_run
    assert by_run["rag-base"][:4] == ["poisson-trace", "import", "ragas", "evals/results/rag-base.jsonl"]
    assert by_run["rag-base"][4:6] == ["--store", "trace-store"]
    for flag in ("--metric", "--cut", "--below", "--case-column"):
        assert flag in by_run["rag-base"], by_run["rag-base"]
    assert by_run["tests-old"][:4] == ["poisson-trace", "import", "junit", "reports/junit-old.xml"]
    # the same from a fresh copy, as JSON
    repo2 = sample_repo(tmp_path, name="repo2", with_expected=True)
    r = init_yes(repo2, "--json")
    assert r.code == 0, r.text
    data = r.json()
    assert list(data) == INIT_KEYS and data["schema"] == INIT_SCHEMA and data["verdict"] == "ok", data
    assert data["stores"] == [{"name": None, "path": "store", "runs": 2}, {"name": "imported", "path": "trace-store", "runs": 4}], data["stores"]
    assert data["events"] == list(CS_FAILURES)
    assert data["next"] == NEXT_DOCTOR
    assert data["config_path"] == "trace.toml"


# ---------- TF17-41 ----------


def test_tf17_41_no_events_with_no_store_takes_the_default_from_the_imported_runs(tmp_path: Path) -> None:
    folder, base, raft = no_store_folder(tmp_path, events=None)
    before = (folder / "trace.toml").read_text(encoding="utf-8")
    r = init_yes(folder)
    assert r.code == 0, r.text
    doc = read_toml(folder)
    assert doc["events"] == {"failed": ["missed"]} and doc["store"] == {"path": "trace-store"}, doc
    text = (folder / "trace.toml").read_text(encoding="utf-8")
    assert text.startswith(before), text
    assert doctor(folder).code == 0


def test_tf17_41_no_events_on_a_terminal_asks_the_failure_question(tmp_path: Path) -> None:
    folder, base, raft = no_store_folder(tmp_path, events=None)
    r = tty(["init"], ["y", ""], cwd=folder)
    assert r.code == 0, r.text
    assert "Which outcomes count as a failure?" in r.err, r.err
    assert read_toml(folder)["events"] == {"failed": ["missed"]}


def test_tf17_41_no_events_with_a_prove_store_takes_the_default_from_its_runs(tmp_path: Path) -> None:
    folder = work(tmp_path)
    store = cs_store(folder)
    old, new = junit_pair(folder)
    write_toml(folder, config_text(junit_entry(old, "old"), junit_entry(new, "new"), store=store, events=None))
    r = init_yes(folder)
    assert r.code == 0, r.text
    doc = read_toml(folder)
    assert sorted(doc["events"]["failed"]) == sorted(CS_FAILURES), doc
    assert doc["store"] == {"path": "store", "imported": {"path": "trace-store"}}
    assert imported_into(folder) == ["new", "old"]


def test_tf17_41_nothing_outside_the_config_and_the_store_is_written(tmp_path: Path) -> None:
    repo = pending_repo(tmp_path)
    home = Path(os.environ["HOME"])
    elsewhere = work(tmp_path, "elsewhere")
    before = snapshot(repo, home, elsewhere)
    assert init_yes(repo).code == 0
    after = snapshot(repo, home, elsewhere)
    changed = sorted(k for k in before if after.get(k) != before[k])
    assert changed == ["repo/trace.toml"], changed
    new = sorted(k for k in after if k not in before)
    assert new and all(k.startswith("repo/trace-store") for k in new), new
