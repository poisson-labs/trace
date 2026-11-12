"""TF1-13: every help example runs as written, and the two new verbs' help is a stranger's (spec
sections 9.1 rule L2 and 5.3; TF0's examples name runs by ``latest`` and ``previous``, which
resolve once names are built).

Each example is read as a shell reads it, then run in a folder that holds what it names: the
store an example names is a copy of the tau2 fixture (runs Prove stored, which carry the
``unsolved`` outcome the examples count), and each file an import example names is the reader's
own fixture under that name, its case column named as the example names it (the promptfoo,
Inspect and OpenAI Evals readers' fixtures as TF10 committed them). Each exits 0 and
prints its verdict line first. ``runs`` and ``name`` have a description, help on every argument
with its default, and an example, as every verb does."""

from __future__ import annotations

import gzip
import json
import re
import shutil
from pathlib import Path

import pytest

from conftest import TAU2
from tf0_support import DEEPEVAL, RAGAS, TOOLS, VERBS, chdir, examples, help_blocks, help_entries, trace, trace_import
from tf1_support import shell_words

NEW_VERBS = ("runs", "name")
# the table and JUnit readers' committed files, for examples that name those readers
TABLE = Path(__file__).resolve().parent / "fixtures" / "ingest" / "table" / "humaneval-a.csv"
JUNIT = Path(__file__).resolve().parent / "fixtures" / "ingest" / "junit" / "humaneval-a.xml"
# the promptfoo, Inspect and OpenAI Evals readers' committed files (TF10, its RD3), each copied
# under the name an example gives it, the form told by the name's extension
_TF10 = Path(__file__).resolve().parent / "fixtures" / "ingest"
TF10_FILES = {
    "promptfoo": {".json": _TF10 / "promptfoo" / "results.json", ".jsonl": _TF10 / "promptfoo" / "results.jsonl"},
    "inspect": {".eval": _TF10 / "inspect" / "2026-10-07T04-23-47-00-00_trace-fixture_CV3jq8f7FTjwkaYb3zj3m2.eval",
                ".json": _TF10 / "inspect" / "2026-10-07T04-23-51-00-00_trace-fixture_2nSEDuHHzKiTUjJW3kXknY.json"},
    "openai-evals": {".jsonl": _TF10 / "openai-evals" / "old.jsonl"},
    # the LangSmith reader's example, by its file's extension: the API's answer, the command's
    # export or the page's CSV (the reader pair's TF24)
    "langsmith": {".json": _TF10 / "langsmith" / "api" / "baseline.runs-v1.json",
                  ".jsonl": _TF10 / "langsmith" / "cli" / "baseline-runs.jsonl",
                  ".csv": _TF10 / "langsmith" / "ui" / "trace-fixture-baseline-bbb64b8e.csv"},
    # the Braintrust reader's example, by its file's extension: the experiment fetch's answer
    # or the page's CSV (the reader pair's TF25)
    "braintrust": {".json": _TF10 / "braintrust" / "api" / "slice-baseline.fetch.json",
                   ".csv": _TF10 / "braintrust" / "ui" / "slice-baseline.csv"},
    # the Weave reader's example: the service's answer for one evaluation, a call a line (the
    # page's downloads hold every evaluation, so an example on one would have to name one; the
    # reader pair's TF26)
    "weave": {".jsonl": _TF10 / "weave" / "api" / "trace-fixture-slice-baseline.jsonl"},
}
TRACE_HELPS = [[], *[[v] for v in (*VERBS, *NEW_VERBS)]]
IMPORT_HELPS = [[], *[[t] for t in TOOLS]]


def _help(command: str, words: list[str]) -> str:
    result = (trace if command == "trace" else trace_import)([*words, "--help"])
    assert result.code == 0 and result.err == "", result.text
    return result.out


HELPS = [("trace", w) for w in TRACE_HELPS] + [("import", w) for w in IMPORT_HELPS]
HELP_IDS = ["poisson-trace", *[f"{w[0]}" for w in TRACE_HELPS[1:]], "import", *[f"import {w[0]}" for w in IMPORT_HELPS[1:]]]


def _examples(command: str, words: list[str]) -> list[str]:
    starts = ["poisson-trace"] if command == "trace" else ["poisson-trace-import", "poisson-trace import"]
    return examples(_help(command, words), starts)


def _option(words: list[str], flag: str) -> str | None:
    return words[words.index(flag) + 1] if flag in words else None


def _files(words: list[str], start: int) -> list[str]:
    out = []
    for word in words[start:]:
        if word.startswith("-"):
            break
        out.append(word)
    return out


def _write_table(path: Path, rows: list[dict[str, object]]) -> None:
    """The rows in the format the file's extension names, as the Ragas reader tells it."""
    import pandas as pd

    plain = path.name[: -len(".gz")] if path.name.endswith(".gz") else path.name
    frame = pd.DataFrame(rows)
    if plain.endswith(".parquet"):
        frame.to_parquet(path)
        return
    if plain.endswith(".csv"):
        data = frame.to_csv(index=False).encode("utf-8")
    elif plain.endswith(".jsonl"):
        data = "".join(json.dumps(row) + "\n" for row in rows).encode("utf-8")
    else:
        data = json.dumps(rows).encode("utf-8")
    path.write_bytes(gzip.compress(data) if path.name.endswith(".gz") else data)


def _set_up(folder: Path, command: str, words: list[str]) -> list[str]:
    """Put in ``folder`` what the example names; the argv to run."""
    if command == "trace" and words[1:2] != ["import"]:
        store = _option(words, "--store")
        if store is not None:
            shutil.copytree(TAU2, folder / store)
        return words[1:]
    start = 2 if words[0] == "poisson-trace" else 1
    tool = words[start]
    for name in _files(words, start + 1):
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if tool == "deepeval":
            raw = gzip.decompress((DEEPEVAL / "humaneval-a.json.gz").read_bytes())
            path.write_bytes(gzip.compress(raw) if name.endswith(".gz") else raw)
        elif tool == "junit":
            shutil.copy(JUNIT, path)
        elif tool == "table":
            _write_table(path, _table_rows(words))
        elif tool in TF10_FILES:
            shutil.copy(TF10_FILES[tool][path.suffix], path)
        else:
            column = _option(words, "--case-column") or "case"
            rows = [json.loads(line) for line in (RAGAS / "rag-base.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            rows = [{(column if k == "case" else k): v for k, v in row.items()} for row in rows]
            _write_table(path, rows)
    return words[start:] if command == "import" else words[1:]


def _table_rows(words: list[str]) -> list[dict[str, object]]:
    """The committed HumanEval table's rows under the columns the example names: its case
    column, and its outcome column with a failure value of the example's for each failure, or its
    score column with 1 for a pass and 0 otherwise."""
    import csv

    failed = [words[i + 1] for i, w in enumerate(words) if w == "--failed"]
    case, outcome, score = (_option(words, flag) for flag in ("--case-column", "--outcome-column", "--score-column"))
    with open(TABLE, encoding="utf-8", newline="") as f:
        source = list(csv.DictReader(f))
    rows: list[dict[str, object]] = []
    for row in source:
        made: dict[str, object] = {str(case): row["case"]}
        if outcome is not None:
            made[outcome] = failed[0] if row["outcome"] != "passed" else "passed"
        if score is not None:
            made[score] = 1.0 if row["outcome"] == "passed" else 0.0
        rows.append(made)
    return rows


@pytest.mark.parametrize("command,words", HELPS, ids=HELP_IDS)
def test_tf1_13_every_help_example_runs_as_written(tmp_path: Path, command: str, words: list[str]) -> None:
    found = _examples(command, words)
    assert found, (command, words)
    if command == "trace" and words:
        assert all(shell_words(e)[1] == words[0] for e in found), found
    for i, example in enumerate(found):
        folder = tmp_path / f"example-{i}"
        folder.mkdir()
        shown = shell_words(example)
        assert shown[0] in ("poisson-trace", "poisson-trace-import"), example
        argv = _set_up(folder, command, shown)
        with chdir(folder):
            result = (trace if command == "trace" else trace_import)(argv)
        assert result.code == 0, (example, result.err)
        assert re.match(r"^[a-z][a-z ]*  \S", result.out.splitlines()[0]), (example, result.out[:200])


# ---------- help on the two new verbs ----------


@pytest.mark.parametrize("verb", NEW_VERBS)
def test_tf1_13_the_new_verbs_help_a_stranger(verb: str) -> None:
    text = _help("trace", [verb])
    blocks = help_blocks(text)
    assert blocks[0].startswith("usage:")
    description = blocks[1]
    assert not re.match(r"^\S[^\n]*:\n", description + "\n"), description
    assert len(description.split()) >= 8 and "." in description, description
    entries = help_entries(text)
    assert entries, text
    for invocation, words in entries:
        if invocation.startswith("-h, --help"):
            continue
        assert words, f"{invocation} has no help text"
        if invocation.startswith("-") and " " in invocation.split(",")[-1].strip():
            assert "default" in words, f"{invocation}: {words}"
    assert not re.search(r"\b(?:None|True|False)\b|\[\]", text)
    assert examples(text, [f"poisson-trace {verb}"]), text


def test_tf1_13_the_main_help_lists_the_new_verbs() -> None:
    """Each in the list of verbs with what it does, not only in an example."""
    text = _help("trace", [])
    listed = {m.group(1) for m in re.finditer(r"(?m)^ {2,}([a-z][\w-]*)(?: {2,}\S|$)", text)}
    assert set(VERBS) | set(NEW_VERBS) <= listed, text
