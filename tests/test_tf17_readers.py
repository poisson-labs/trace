"""TF17-43: ``init`` imports promptfoo, Inspect and OpenAI Evals files on a yes (RD9, deferred to
TF17 by TF10 Session A's ruling; RB2, TF10 Session B's refusal that stands until this is built).

- A yes (``--yes`` with the answers, ``--import``, or ``y`` on a terminal) imports these files
  as it imports DeepEval's, Ragas's, the tables and the JUnit reports: one run per file, named
  after the file, into ``trace-store`` beside ``trace.toml``, the failures from the imported
  rows (``missed``); the RB2 refusal ("init lists … but does not import them itself") is gone.
- One promptfoo file holds both versions: init imports each prompt as its own run, named by the
  file and the prompt's number counting from 1 (``results-1``, ``results-2``), its line carrying
  ``--prompt N``; the case is the test variable init reads from the file (``--case var:case``),
  else asked as promptfoo's ``--case`` is: ``var:NAME`` or ``test``. ``init``'s ``--case`` takes
  those two forms beside DeepEval's and JUnit's.
- An Inspect log and an OpenAI Evals record need no answer: no question is asked.
- ``--no-import`` still lists the files with their lines and writes no store (TF10-41); files
  of these readers beside another tool's are still the several-tools refusal.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from tf0_support import FIXTURES
from tf1_support import shell_words
from tf2_support import init_yes, refused, scratch_home, tty, work  # noqa: F401
from tf17_support import RAGAS, read_toml, rows_of, runs_in

PROMPTFOO = FIXTURES / "ingest" / "promptfoo" / "results.json"
INSPECT_EVAL = FIXTURES / "ingest" / "inspect" / "2026-10-07T04-23-47-00-00_trace-fixture_CV3jq8f7FTjwkaYb3zj3m2.eval"
INSPECT_JSON = FIXTURES / "ingest" / "inspect" / "2026-10-07T04-23-51-00-00_trace-fixture_2nSEDuHHzKiTUjJW3kXknY.json"
OPENAI = FIXTURES / "ingest" / "openai-evals"


def with_files(tmp_path: Path, *paths: Path) -> Path:
    folder = work(tmp_path)
    (folder / "results").mkdir()
    for path in paths:
        shutil.copy(path, folder / "results" / path.name)
    return folder


def import_lines(out: str) -> dict[str, list[str]]:
    lines = [shell_words(line.strip()[len("import"):].strip()) for line in out.splitlines() if line.strip().startswith("import   poisson-trace import ")]
    return {words[words.index("--run") + 1]: words for words in lines}


# ---------- promptfoo: one file, both versions ----------


def test_tf17_43_a_promptfoo_file_with_two_prompts_is_imported_as_two_runs(tmp_path: Path) -> None:
    folder = with_files(tmp_path, PROMPTFOO)
    r = init_yes(folder, "--case", "var:case")
    assert r.code == 0, r.text
    assert runs_in(folder / "trace-store") == ["results-1", "results-2"]
    lines = import_lines(r.out)
    assert set(lines) == {"results-1", "results-2"}, r.out
    for n in (1, 2):
        words = lines[f"results-{n}"]
        assert words[:4] == ["poisson-trace", "import", "promptfoo", "results/results.json"], words
        assert words[4:6] == ["--store", "trace-store"]
        assert words[words.index("--prompt") + 1] == str(n), words
        assert words[words.index("--case") + 1] == "var:case", words
    doc = read_toml(folder)
    assert doc["store"] == {"path": "trace-store"} and doc["events"] == {"failed": ["missed"]}, doc
    assert len(rows_of(folder / "trace-store", "results-1")) == 4
    assert "does not import them" not in r.text


def test_tf17_43_without_the_case_init_yes_names_the_flag(tmp_path: Path) -> None:
    folder = with_files(tmp_path, PROMPTFOO)
    line = refused(init_yes(folder))
    assert "--case" in line, line
    assert not (folder / "trace-store").exists()


def test_tf17_43_on_a_terminal_the_case_is_asked_in_promptfoos_forms(tmp_path: Path) -> None:
    folder = with_files(tmp_path, PROMPTFOO)
    r = tty(["init"], ["y", "var:case", ""], cwd=folder)
    assert r.code == 0, r.text
    assert "var:NAME" in r.err and "test" in r.err, r.err
    assert runs_in(folder / "trace-store") == ["results-1", "results-2"]


# ---------- Inspect and OpenAI Evals: no answer needed ----------


def test_tf17_43_inspect_logs_are_imported_without_a_question(tmp_path: Path) -> None:
    folder = with_files(tmp_path, INSPECT_EVAL, INSPECT_JSON)
    r = tty(["init"], ["y", ""], cwd=folder)
    assert r.code == 0, r.text
    names = runs_in(folder / "trace-store")
    assert len(names) == 2 and all(not n.endswith((".eval", ".json")) for n in names), names
    lines = import_lines(r.out)
    assert all(words[2] == "inspect" for words in lines.values()), lines


def test_tf17_43_openai_evals_records_are_imported_with_yes(tmp_path: Path) -> None:
    folder = with_files(tmp_path, OPENAI / "old.jsonl", OPENAI / "new.jsonl")
    r = init_yes(folder)
    assert r.code == 0, r.text
    assert runs_in(folder / "trace-store") == ["new", "old"]
    lines = import_lines(r.out)
    assert lines["old"][:4] == ["poisson-trace", "import", "openai-evals", "results/old.jsonl"], lines


# ---------- what stays ----------


def test_tf17_43_no_import_still_lists_and_writes_no_store(tmp_path: Path) -> None:
    folder = with_files(tmp_path, PROMPTFOO)
    r = init_yes(folder, "--no-import")
    assert r.code == 0, r.text
    assert any("poisson-trace import promptfoo" in line for line in r.out.splitlines()), r.out
    assert not (folder / "trace-store").exists()


def test_tf17_43_beside_another_tools_files_it_is_still_the_several_tools_refusal(tmp_path: Path) -> None:
    folder = with_files(tmp_path, PROMPTFOO)
    shutil.copy(RAGAS / "rag-base.jsonl", folder / "results" / "rag-base.jsonl")
    line = refused(init_yes(folder, "--case", "var:case"))
    assert "promptfoo" in line and "ragas" in line and "--no-import" in line, line
    assert not (folder / "trace-store").exists()
