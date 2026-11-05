"""TF10-38 to TF10-41: the three readers say which files are theirs, for init (spec sections 4.3,
4.4 as amended 2026-10-20, and 6.3: each reader exposes ``looks_like(path) -> str | None``).

- TF10-38: each committed export is claimed by its reader with one line; promptfoo's CSV by none.
- TF10-39: no file is claimed by two readers of the install: not the new exports, and not the
  files TF3-22 names or the other committed fixtures.
- TF10-40: ``looks_like`` never raises, on a file missing, a folder, an empty file, a damaged
  archive or a JSON value of another shape, and claims none of them.
- TF10-41: init lists each export as its reader's and, with ``--no-import``, prints for each the
  ``poisson-trace import`` line that would import it into ``trace-store``, writing no store;
  doctor lists the three readers among the install's.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tf1_support import shell_words
from tf2_support import check, doctor_doc, init_yes, numbered, scratch_home, work, write_config  # noqa: F401
from tf10_support import IN_EVAL, IN_JSON, OE_NEW, OE_OLD, PF_CSV, PF_JSON, PF_JSONL, PRESENT, looks_like, write_eval
from tf21_support import INGEST

EXPORTS = {"promptfoo": [PF_JSON, PF_JSONL], "inspect": [IN_EVAL, IN_JSON], "openai-evals": [OE_OLD, OE_NEW]}
WORD = {"promptfoo": "promptfoo", "inspect": "Inspect", "openai-evals": "OpenAI Evals"}


def _one_line(said: object) -> str:
    assert isinstance(said, str) and said.strip() and "\n" not in said, said
    return said


# ---------- TF10-38 ----------


@pytest.mark.parametrize("tool", list(EXPORTS))
def test_tf10_38_each_export_is_claimed_by_its_reader(tool: str) -> None:
    for path in EXPORTS[tool]:
        assert WORD[tool] in _one_line(looks_like(tool, path)), (tool, path.name)


def test_tf10_38_promptfoo_s_csv_is_claimed_by_no_reader() -> None:
    assert [tool for tool in PRESENT if looks_like(tool, PF_CSV) is not None] == []


# ---------- TF10-39 ----------


def _every_fixture() -> list[Path]:
    return sorted(p for p in INGEST.rglob("*") if p.is_file() and p.suffix in (".json", ".jsonl", ".gz", ".csv", ".xml", ".eval"))


def test_tf10_39_no_committed_file_is_claimed_by_two_readers() -> None:
    claimed_by: dict[str, list[str]] = {}
    for path in _every_fixture():
        claimed = [tool for tool in PRESENT if looks_like(tool, path) is not None]
        assert len(claimed) <= 1, (path.name, claimed)
        claimed_by[str(path.relative_to(INGEST))] = claimed
    for tool, paths in EXPORTS.items():
        for path in paths:
            assert claimed_by[str(path.relative_to(INGEST))] == [tool], path.name
    for name, claimed in claimed_by.items():
        if name.split("/")[0] not in EXPORTS:
            assert not set(claimed) & set(EXPORTS), (name, claimed)


def test_tf10_39_the_tf3_22_files_are_not_the_new_readers(tmp_path: Path) -> None:
    from tf2_support import deepeval_file, ragas_file
    from tf3_support import OWN_1, SUITE_1, TABLE_A, write_table

    files = [TABLE_A, SUITE_1, OWN_1, deepeval_file(tmp_path / "results" / "test_run_20261002_101500.json"),
             ragas_file(tmp_path / "scores" / "base.jsonl"), ragas_file(tmp_path / "scores" / "base.csv"),
             write_table(tmp_path / "mine.jsonl", [{"case": "a", "outcome": "x"}]),
             write_table(tmp_path / "list.json", [{"case": "a", "outcome": "x", "success": True}])]
    for path in files:
        assert [tool for tool in EXPORTS if looks_like(tool, path) is not None] == [], path.name


# ---------- TF10-40 ----------


def _odd_files(tmp_path: Path) -> list[Path]:
    (tmp_path / "folder.json").mkdir()
    (tmp_path / "empty.json").write_bytes(b"")
    (tmp_path / "empty.eval").write_bytes(b"")
    (tmp_path / "empty.jsonl").write_bytes(b"")
    (tmp_path / "junk.eval").write_bytes(b"PK\x03\x04 nothing else")
    (tmp_path / "junk.json").write_bytes(b"\xff\xfe\x00 not text")
    (tmp_path / "list.json").write_text("[1, 2, 3]", encoding="utf-8")
    (tmp_path / "number.jsonl").write_text("42\n", encoding="utf-8")
    (tmp_path / "other.jsonl").write_text('{"spec": 1}\n', encoding="utf-8")
    write_eval(tmp_path / "headless.eval", members=lambda raw: raw.pop("header.json"))
    shutil.copy(PF_JSON, tmp_path / "results.txt")
    return [tmp_path / name for name in ("missing.json", "missing.eval", "folder.json", "empty.json", "empty.eval",
                                         "empty.jsonl", "junk.eval", "junk.json", "list.json", "number.jsonl",
                                         "other.jsonl", "headless.eval", "results.txt")]


def test_tf10_40_looks_like_never_raises_and_claims_none_of_these(tmp_path: Path) -> None:
    for path in _odd_files(tmp_path):
        for tool in EXPORTS:
            assert looks_like(tool, path) is None, (tool, path.name)
            assert looks_like(tool, str(path)) is None, (tool, path.name)


def test_tf10_40_looks_like_takes_a_path_or_its_text() -> None:
    for tool, paths in EXPORTS.items():
        for path in paths:
            assert looks_like(tool, str(path)) == looks_like(tool, path)


# ---------- TF10-41 ----------

FOLDERS = {"promptfoo": [PF_JSON], "inspect": [IN_EVAL, IN_JSON], "openai-evals": [OE_OLD, OE_NEW]}


@pytest.mark.parametrize("tool", list(FOLDERS))
def test_tf10_41_init_lists_the_exports_and_prints_a_line_for_each(tmp_path: Path, tool: str) -> None:
    folder = work(tmp_path)
    (folder / "results").mkdir()
    for path in FOLDERS[tool]:
        shutil.copy(path, folder / "results" / path.name)
    result = init_yes(folder, "--no-import")
    assert result.code == 0, result.text
    listed = {line.split()[0]: line for line in numbered(result.err).values()}
    assert sorted(listed) == sorted(f"results/{p.name}" for p in FOLDERS[tool]), result.err
    for path in FOLDERS[tool]:
        assert WORD[tool] in listed[f"results/{path.name}"], listed
    lines = [shell_words(line.strip()) for line in result.out.splitlines() if line.strip().startswith("poisson-trace import ")]
    for path in FOLDERS[tool]:
        words = next(w for w in lines if f"results/{path.name}" in w)
        assert words[:4] == ["poisson-trace", "import", tool, f"results/{path.name}"], words
        assert words[4:6] == ["--store", "trace-store"] and words[6] == "--run" and words[7], words
    assert not (folder / "trace-store").exists()


def test_tf10_41_doctor_lists_the_three_readers(tmp_path: Path) -> None:
    folder = work(tmp_path)
    write_config(folder, "version = 1\n")
    _, data = doctor_doc(folder)
    line = check(data, "readers")["line"]
    for tool in PRESENT:
        assert tool in line, line
