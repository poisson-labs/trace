"""TF26-47 to TF26-60: the reader in the import's command line, its refusals, its detector, folders
of its files, and its place in the config, ``init`` and ``doctor`` (spec sections 3.3, 4.3, 4.4,
6.1, 6.3, 12, 17.4, 18.3.1; the shared core of INT1 to INT4; TF22's FI1 to FI7; TF17's entries;
the two finished pairs' rules for the same).

- TF26-47: the import's help lists ``weave``; the reader's help is the verb's under both
  spellings, with its flags, each saying what it is and its default; the module has the readers'
  shape, and its example runs as written on a committed capture of the example's extension.
- TF26-48: the summary is the import's: ``poisson-trace.import/1``, the files' digests, a
  ``next:`` fix check on ``--event missed``; its plain Next line carries the flags that read the
  other version the same way, the evaluation among them, and that line runs when its capitals
  are filled in; it says when a try counts as failed. A name the store holds is refused and the
  store unchanged.
- TF26-49: a file that is missing, empty, not JSON, of another shape, another tool's, of another
  extension, or a table that is not the page's, is refused in one plain line naming it, exit 1,
  nothing written; a broken line of a JSON Lines file is named by its number.
- TF26-50: a wrong command line exits 2 in one line naming the flag: no ``--case-from``, no
  ``--outcome-from``, a value neither takes (the other readers' words among them), a score with
  no cut or no side or both sides, a cut where none is read, a cut that is not a number, an
  evaluation with no name.
- TF26-51: both spellings of the import print the same bytes, done or refused.
- TF26-52: ``looks_like`` claims each answer of the service and each of the page's downloads
  with one line naming Weave, and no other file of the captures; no committed file of any tool
  is claimed by two readers; it never raises.
- TF26-53: a folder of an answer's pages is one run, named after the folder, the same run its
  files give (with the tool named or not); a folder holding two evaluations' answers is refused
  naming each, and one holding one evaluation's answer twice as a call given twice.
- TF26-54: the verbs read two folders of the reader's files with the reader's flags, and print
  what they print on the same folders imported one by one.
- TF26-55: ``--verdicts`` joins by case; a verdict that differs from what the file recorded is
  refused.
- TF26-56: ``init`` lists each export as Weave's and prints an import line for each;
  ``doctor`` lists ``weave`` among the readers.
- TF26-57: an ``[[import]]`` entry of ``tool = "weave"`` is read with its options by their
  flags' names and checked as the flags are; ``init`` imports a pending pair and ``doctor
  --setup`` reads them.
- TF26-58: an entry whose ``file`` is ``weave:ENTITY/PROJECT/EVALUATION`` is an address:
  accepted with ``tool = "weave"`` and refused under any other tool, as the other readers'
  addresses are refused under this one; no verb, and neither ``doctor`` nor ``doctor --setup``,
  asks the service anything; ``doctor --setup`` says it is not pulled there and whether Weave's
  key is set; ``init`` pulls it into the imports' store, saving the raw copy. The address of
  the puller this install still lacks stays refused.
- TF26-59: the readers' two sentences: ``runs`` shows an imported run's backend as
  ``import:weave`` and whether it has traces.
- TF26-60: the reader's module documents what it does not keep, in plain words: held by
  TF24-60 in ``test_tf24_cli.py``, for the three readers that pull.

That the import's help lists ``weave`` (TF26-47) and that ``doctor`` lists it among the readers
(TF26-56) is held by ``test_tf5_readers.py`` (TF5-20), which holds the whole help and ``doctor``'s
readers line byte for byte; that the address of a puller this install lacks stays refused
(TF26-58) by ``test_tf17_config.py`` (TF17-20).
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from tf0_support import chdir, trace, trace_import
from tf1_support import shell_words
from tf2_support import init_yes, numbered, work
from tf17_support import config_text, import_entry, setup_check, trace_in, write_toml
from tf21_support import INGEST, run_import
from tf26_support import (
    API, CALL_ID, CASES, EVALUATION, EXPORTS, KEY_VARIABLE, NAMES, PLANTED_KEY, PROJECT_ID, ROOTS_ONLY, UI, UI_EXPORTS, UI_TABLES, WHOLE,
    WV, address, by_status, calls_of, columns, edited_table, evaluation, export, imported, never, of, of_evaluation, outcomes,
    pulling, raw_folder, recs, refused, snapshot, tally, write_calls, wrong_line, wv_argv,
)

PRESENT = ("deepeval", "ragas", "table", "junit", "promptfoo", "inspect", "openai-evals", "langsmith", "braintrust", "weave")
FLAGS = ("--case-from", "--outcome-from", "--cut", "--below", "--above", "--evaluation", "--keep-raw-text", "--page-size")
OPTIONS = {"case_from": "example", "outcome_from": "score:exact", "cut": 0.5, "below": True}


def _one_evaluation(tmp: Path, name: str, suffix: str, stem: str = "old") -> Path:
    """One evaluation's rows alone, in a file of the extension given: the service's expanded
    answer as a call a line or as a list, or the page's table cut down to that evaluation's
    rows."""
    if suffix in (".jsonl", ".json"):
        return write_calls(tmp / f"{stem}{suffix}", calls_of(export(name, "expanded")[0]))

    def only(rows: list[dict[str, str]]) -> None:
        rows[:] = [r for r in rows if r["parent_id"] == CALL_ID[name]]

    made = edited_table(tmp, "ui-csv" if suffix == ".csv" else "ui-tsv", only, stem=stem)
    assert made.suffix == suffix
    return made


# ---------- TF26-47 ----------


def test_tf26_47_the_reader_s_help_is_the_verb_s_and_names_its_flags() -> None:
    a, b = trace(["import", "weave", "--help"]), trace_import(["weave", "--help"])
    assert a.code == b.code == 0 and a.out == b.out and a.err == b.err == "", a.text + b.text
    assert a.out.split("\n\n")[0].startswith("usage: poisson-trace import weave"), a.out
    for flag in ("--store", "--run", "--started", "--json", "--verdicts", *FLAGS):
        assert flag in a.out, flag
    for word in ("example", "example:KEY", "input", "none", "status", "score:KEY", "WANDB_API_KEY", "weave:ENTITY/PROJECT/EVALUATION",
                 "Evaluation.predict_and_score"):
        assert word in a.out, word


def test_tf26_47_the_module_has_the_readers_shape() -> None:
    from poisson_trace.ingest import weave
    from poisson_trace.ingest.importing import READERS, present, pulls, reader_options

    assert "weave" in READERS and present() == PRESENT
    assert READERS.index("braintrust") < READERS.index("weave") < READERS.index("otel")
    for attr in ("add_arguments", "read", "usage", "looks_like", "stand_ins", "DESCRIPTION", "EXAMPLE", "SHAPES", "ADDRESS"):
        assert hasattr(weave, attr), attr
    assert weave.EXAMPLE.startswith("poisson-trace import weave "), weave.EXAMPLE
    assert pulls("weave") == "weave:" and pulls("braintrust") == "braintrust:" and pulls("langsmith") == "langsmith:"
    options = reader_options("weave")
    assert options["case_from"].required and options["outcome_from"].required
    assert not options["below"].takes_value and not options["keep_raw_text"].takes_value
    assert set(options) == {"case_from", "outcome_from", "cut", "below", "above", "evaluation", "keep_raw_text", "page_size"}
    for dest in ("cut", "below", "above", "evaluation", "keep_raw_text", "page_size"):
        assert not options[dest].required and not options[dest].many, dest


def test_tf26_47_the_example_runs_as_written_on_a_capture_of_its_extension(tmp_path: Path) -> None:
    from poisson_trace.ingest import weave

    words = shell_words(weave.EXAMPLE)
    assert words[:3] == ["poisson-trace", "import", "weave"]
    files = [w for w in words[3:] if not w.startswith("-") and re.search(r"\.(json|jsonl|csv|tsv)$", w)]
    assert len(files) == 1, words
    made = _one_evaluation(tmp_path / "made", "baseline", Path(files[0]).suffix)
    shutil.copy(made, tmp_path / files[0])
    with chdir(tmp_path):
        ran = trace(words[1:])
    assert ran.code == 0 and ran.out.startswith("ok  wrote run "), ran.text


# ---------- TF26-48 ----------


@pytest.mark.parametrize("kind", EXPORTS)
def test_tf26_48_the_summary_is_the_import_s(tmp_path: Path, kind: str) -> None:
    data = imported(of("baseline", kind, tmp_path / "st", "first", mode="status"))
    assert data["run"] == "first" and data["store"] == str(tmp_path / "st") and data["tool"] == "weave"
    assert data["next"].startswith("poisson-trace fix-check OLD NEW ") and "--event missed" in data["next"]
    text = run_import(of("baseline", kind, tmp_path / "st2", "first"))
    assert text.code == 0 and text.out.startswith("ok  wrote run first to "), text.out
    assert text.out.rstrip("\n").splitlines()[-1].startswith("next: poisson-trace fix-check OLD NEW"), text.out
    failed = next(line for line in text.out.splitlines() if line.startswith("- Failures: "))
    assert "exact" in failed and "0.5" in failed and "below" in failed and "3 failed and 6 passed" in failed, failed
    by = run_import(of("baseline", kind, tmp_path / "st3", "first", mode="status"))
    failed = next(line for line in by.out.splitlines() if line.startswith("- Failures: "))
    assert "error" in failed and "1 failed and 9 passed" in failed, failed


@pytest.mark.parametrize("kind", ["pull", "ui-jsonl", "ui-json", "ui-csv", "ui-tsv"])
def test_tf26_48_the_next_line_reads_the_other_version_the_same_way(tmp_path: Path, kind: str) -> None:
    text = run_import(of("baseline", kind, tmp_path / "st", "old"))
    assert text.code == 0, text.err
    line = next(line for line in text.out.splitlines() if line.startswith("- Next: "))
    command = re.search(r"`(poisson-trace import weave [^`]+)`", line)
    assert command, line
    words = shell_words(command.group(1))
    case = "example:id" if kind in UI_TABLES else "example"
    for flag, value in (("--case-from", case), ("--outcome-from", "score:exact"), ("--cut", "0.5")):
        assert words[words.index(flag) + 1] == value, words
    assert "--below" in words
    other = export("candidate", kind)[0]
    assert f"OTHER{other.suffix}" in words, words
    filled = [str(other) if w.startswith("OTHER.") else ("new" if w == "OTHER" else w) for w in words]
    if kind in UI_EXPORTS:
        # the page's download holds every evaluation: the line carries the one read, to be changed
        assert filled[filled.index("--evaluation") + 1] == evaluation("baseline")
        filled[filled.index("--evaluation") + 1] = evaluation("candidate")
    else:
        assert "--evaluation" not in words
    assert trace(filled[1:]).code == 0
    assert sorted(columns(tmp_path / "st", "new")) == list(CASES)


@pytest.mark.parametrize("kind", ["pull"])
def test_tf26_48_a_name_in_use_is_refused_and_nothing_changes(tmp_path: Path, kind: str) -> None:
    imported(of("baseline", kind, tmp_path / "st", "first", mode="status"))
    before = snapshot(tmp_path / "st")
    line = refused(run_import(of("candidate", kind, tmp_path / "st", "first", mode="status")))
    assert "first" in line, line
    assert snapshot(tmp_path / "st") == before


# ---------- TF26-49 ----------


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def _dir(path: Path) -> Path:
    path.mkdir()
    return path


def _table_without(tmp: Path, kind: str, column: str) -> Path:
    return edited_table(tmp, kind, header=lambda fields: [f for f in fields if f != column], stem=f"no-{column.split('.')[-1]}")


def _table_no_id(tmp: Path) -> Path:
    def edit(rows: list[dict[str, str]]) -> None:
        rows[2]["id"] = ""

    return edited_table(tmp, "ui-csv", edit, stem="no-id-cell")


LS = INGEST / "langsmith"
BT = INGEST / "braintrust"
MALFORMED: dict[str, Any] = {
    "missing": lambda tmp: tmp / "gone.jsonl",
    "empty": lambda tmp: _write(tmp / "e.json", b""),
    "an empty table": lambda tmp: _write(tmp / "e.csv", b""),
    "not JSON": lambda tmp: _write(tmp / "n.json", b'[{"id": 1, '),
    "not text": lambda tmp: _write(tmp / "b.jsonl", b"\xff\xfe\x00\x01"),
    "a JSON number": lambda tmp: _write(tmp / "num.json", b"42\n"),
    "a list of numbers": lambda tmp: _write(tmp / "l.json", b"[1, 2, 3]\n"),
    "an object and no list": lambda tmp: _write(tmp / "o.json", b'{"calls": []}'),
    "objects that are no calls": lambda tmp: _write(tmp / "ev.jsonl", b'{"id": "a", "name": "x"}\n'),
    "the list of requests": lambda tmp: _write(tmp / "requests.json", (API / "requests.json").read_bytes()),
    "promptfoo's results": lambda tmp: _write(tmp / "pf.json", (INGEST / "promptfoo" / "results.json").read_bytes()),
    "an OpenAI Evals record": lambda tmp: _write(tmp / "oe.jsonl", (INGEST / "openai-evals" / "old.jsonl").read_bytes()),
    "a table of another tool": lambda tmp: _write(tmp / "table.csv", (INGEST / "table" / "humaneval-a.csv").read_bytes()),
    "LangSmith's CSV": lambda tmp: _write(tmp / "ls.csv", (LS / "ui" / "trace-fixture-baseline-bbb64b8e.csv").read_bytes()),
    "LangSmith's runs": lambda tmp: _write(tmp / "ls.json", (LS / "api" / "baseline.runs-v2.json").read_bytes()),
    "LangSmith's runs, a run a line": lambda tmp: _write(tmp / "ls.jsonl", (LS / "cli" / "baseline-runs.jsonl").read_bytes()),
    "Braintrust's events": lambda tmp: _write(tmp / "bt.json", (BT / "api" / "slice-baseline.fetch.json").read_bytes()),
    "Braintrust's CSV": lambda tmp: _write(tmp / "bt.csv", (BT / "ui" / "slice-baseline.csv").read_bytes()),
    "a folder named as a file": lambda tmp: _dir(tmp / "folder.jsonl"),
    "another extension": lambda tmp: _write(tmp / "calls.txt", export("baseline", "pull")[0].read_bytes()),
    "another extension, a list of calls": lambda tmp: _write(tmp / "list.txt", export("baseline", "ui-json")[0].read_bytes()),
    "another extension, a call a line": lambda tmp: _write(tmp / "calls.ndjson", export("baseline", "pull")[0].read_bytes()),
    "a table without its status column": lambda tmp: _table_without(tmp, "ui-csv", "summary.weave.status"),
    "a table without its op column": lambda tmp: _table_without(tmp, "ui-tsv", "op_name"),
    "a table read with the other separator": lambda tmp: _write(tmp / "tabs.csv", export("baseline", "ui-tsv")[0].read_bytes()),
    "a table row that names no call": _table_no_id,
}


@pytest.mark.parametrize("label", list(MALFORMED))
def test_tf26_49_a_file_not_the_reader_s_is_refused_in_one_line_naming_it(tmp_path: Path, label: str) -> None:
    path = MALFORMED[label](tmp_path)
    result = run_import(by_status(path, tmp_path / "st", "v"))
    if label == "a folder named as a file":
        # a folder is the folder resolver's to refuse (TF22)
        assert result.code == 1 and result.out == "" and path.name in result.err, result.err
    else:
        line = refused(result)
        assert path.name in line, line
    assert "Traceback" not in result.err and len(result.err.splitlines()) <= 3, result.err
    assert not (tmp_path / "st").exists()


def test_tf26_49_a_broken_line_is_named_by_its_number(tmp_path: Path) -> None:
    lines = export("baseline", "pull")[0].read_text(encoding="utf-8").splitlines()
    lines[6] = lines[6][:40]
    path = tmp_path / "calls.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    line = refused(run_import(by_status(path, tmp_path / "st", "v")))
    assert "calls.jsonl" in line and "line 7" in line, line
    lines[6] = "[1, 2]"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    line = refused(run_import(by_status(path, tmp_path / "st", "v")))
    assert "line 7" in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("empty", [b"", b"\n\n"])
def test_tf26_49_an_empty_page_alone_is_no_run(tmp_path: Path, empty: bytes) -> None:
    """An answer of no call is the last page of a paged answer: it is read beside the others,
    and alone it is no run."""
    path = _write(tmp_path / "page.jsonl", empty)
    assert export("candidate", "pages")[3].read_bytes() == b""
    line = refused(run_import(wv_argv(path, tmp_path / "st", "v")))
    assert "no row" in line or "no run" in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF26-50 ----------

PULLED = export("baseline", "pull")
USAGE: dict[str, Any] = {
    "no --case-from": (lambda root: wv_argv(PULLED, root, "r", case=None), "--case-from"),
    "no --outcome-from": (lambda root: wv_argv(PULLED, root, "r", outcome=None), "--outcome-from"),
    "a case that is none of the four": (lambda root: by_status(PULLED, root, "r", case="row"), "--case-from"),
    "braintrust's word for the case": (lambda root: by_status(PULLED, root, "r", case="record"), "--case-from"),
    "a metadata key for the case": (lambda root: by_status(PULLED, root, "r", case="metadata:case"), "--case-from"),
    "a key of the example with no key": (lambda root: by_status(PULLED, root, "r", case="example:"), "--case-from"),
    "an outcome that is neither": (lambda root: wv_argv(PULLED, root, "r", outcome="score"), "--outcome-from"),
    "braintrust's word for the outcome": (lambda root: wv_argv(PULLED, root, "r", outcome="error", cut=None), "--outcome-from"),
    "langsmith's word for a score": (lambda root: wv_argv(PULLED, root, "r", outcome="feedback:exact"), "--outcome-from"),
    "a score outcome with no key": (lambda root: wv_argv(PULLED, root, "r", outcome="score:"), "--outcome-from"),
    "a score with no cut": (lambda root: wv_argv(PULLED, root, "r", cut=None), "--cut"),
    "a cut with no side": (lambda root: wv_argv(PULLED, root, "r", side=None), "--below"),
    "a cut with both sides": (lambda root: wv_argv(PULLED, root, "r", "--above"), "--above"),
    "a side with no cut": (lambda root: wv_argv(PULLED, root, "r", "--below", cut=None), "--cut"),
    "a cut with the status": (lambda root: by_status(PULLED, root, "r", "--cut", "0.5", "--below"), "--cut"),
    "a side with the status": (lambda root: by_status(PULLED, root, "r", "--below"), "--cut"),
    "a cut that is no number": (lambda root: wv_argv(PULLED, root, "r", cut="high"), "--cut"),
    "a cut that is not a number at all": (lambda root: wv_argv(PULLED, root, "r", cut="nan"), "--cut"),
    "an evaluation with no name": (lambda root: by_status(PULLED, root, "r", "--evaluation", " "), "--evaluation"),
    "a flag of another reader": (lambda root: by_status(PULLED, root, "r", "--select", "metadata:a=b"), "--select"),
    "no file": (lambda root: by_status([], root, "r"), "FILE"),
}


@pytest.mark.parametrize("label", list(USAGE))
def test_tf26_50_a_wrong_command_line_exits_2_naming_the_flag(tmp_path: Path, label: str) -> None:
    make, flag = USAGE[label]
    line = wrong_line(run_import(make(tmp_path / "st")))
    assert flag in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF26-51 ----------


@pytest.mark.parametrize("kind", ["pull"])
def test_tf26_51_both_spellings_print_the_same_bytes(tmp_path: Path, kind: str) -> None:
    outs = []
    for spelling in ("verb", "alias"):
        folder = tmp_path / spelling
        folder.mkdir()
        argv = of("candidate", kind, Path("st"), "first", mode="status")
        with chdir(folder):
            ran = trace(["import", *argv]) if spelling == "verb" else trace_import(argv)
            again = trace(["import", *argv]) if spelling == "verb" else trace_import(argv)
        outs.append((ran.code, ran.out, ran.err, again.code, again.out, again.err))
        assert ran.code == 0 and again.code == 1, ran.text + again.text
    assert outs[0] == outs[1]


# ---------- TF26-52 ----------


def _claimed(path: Path) -> list[str]:
    from poisson_trace.ingest.importing import present, reader

    return [tool for tool in present() if reader(tool).looks_like(path) is not None]


def _ours() -> list[Path]:
    """Every committed file that holds calls: the service's answers and the page's downloads,
    the views of evaluations alone among them (the reader reads those to refuse them plainly)."""
    files = [p for p in sorted(API.iterdir()) if p.suffix == ".jsonl" and p.stat().st_size]
    return [*files, *sorted(UI.iterdir())]


def test_tf26_52_every_export_is_claimed_by_weave_alone_with_one_line() -> None:
    from poisson_trace.ingest import weave

    assert len(_ours()) == 13 + 8
    assert all(p in _ours() for name in NAMES for kind in EXPORTS for p in export(name, kind))
    assert all(p in _ours() for p in ROOTS_ONLY)
    for path in _ours():
        said = weave.looks_like(path)
        assert isinstance(said, str) and said.strip() and "\n" not in said and "Weave" in said, (path.name, said)
        assert weave.looks_like(str(path)) == said
        assert _claimed(path) == ["weave"], (path.name, _claimed(path))


def test_tf26_52_the_other_files_of_the_capture_are_no_export() -> None:
    from poisson_trace.ingest import weave

    for name in ("requests.json", "trace-fixture-slice-candidate.page-4.jsonl"):
        assert weave.looks_like(API / name) is None, name
    for name in ("fixture_weave.py", "slice_weave.py", "pull.py"):
        assert weave.looks_like(WV / name) is None, name


def test_tf26_52_no_committed_file_is_claimed_by_two_readers() -> None:
    from poisson_trace.ingest import weave

    ours = {p.resolve() for p in _ours()}
    for path in sorted(p for p in INGEST.rglob("*") if p.is_file() and p.suffix in (".json", ".jsonl", ".gz", ".csv", ".xml", ".eval", ".tsv")):
        claimed = _claimed(path)
        assert len(claimed) <= 1, (str(path.relative_to(INGEST)), claimed)
        if path.resolve() not in ours:
            assert weave.looks_like(path) is None, str(path.relative_to(INGEST))


def test_tf26_52_looks_like_never_raises_and_claims_none_of_these(tmp_path: Path) -> None:
    from poisson_trace.ingest import weave

    (tmp_path / "folder.jsonl").mkdir()
    for name, data in (("empty.json", b""), ("empty.jsonl", b""), ("empty.csv", b""), ("empty.tsv", b""), ("junk.json", b"\xff\xfe\x00"),
                       ("list.json", b"[1, 2, 3]"), ("number.jsonl", b"42\n"), ("spec.jsonl", b'{"spec": 1}\n'), ("half.json", b'[{"id": '),
                       ("header.csv", b"id,op_name\n"), ("header.tsv", b"id\top_name\ttrace_id\n"), ("object.json", b'{"calls": []}'),
                       ("ids.json", b'[{"id": "a", "trace_id": "b"}]'),
                       ("op.jsonl", b'{"id": "a", "trace_id": "b", "started_at": "x", "op_name": "predict", "project_id": "e/p"}\n')):
        (tmp_path / name).write_bytes(data)
    shutil.copy(export("baseline", "pull")[0], tmp_path / "calls.txt")
    for path in [tmp_path / "missing.jsonl", *sorted(tmp_path.iterdir())]:
        assert weave.looks_like(path) is None, path.name
        assert weave.looks_like(str(path)) is None, path.name


# ---------- TF26-53 ----------


def _pages(tmp: Path, name: str) -> Path:
    folder = tmp / name
    folder.mkdir()
    for path in export("candidate", "pages"):
        shutil.copy(path, folder / path.name)
    return folder


@pytest.mark.parametrize("named", [True, False])
def test_tf26_53_a_folder_of_an_answer_s_pages_is_one_run(tmp_path: Path, named: bool) -> None:
    folder = _pages(tmp_path, "new-pages")
    (folder / ".DS_Store").write_bytes(b"x")
    (folder / "README.md").write_text("notes", encoding="utf-8")
    flags = ["--case-from", "example", "--outcome-from", "status", "--json"]
    argv = [*(["weave"] if named else []), str(folder), "--store", str(tmp_path / "st"), *flags]
    result = run_import(argv)
    assert result.code == 0, result.err
    data = json.loads(result.out)
    assert data["run"] == "new-pages" and data["tool"] == "weave" and data["rows"] == 10
    # the empty last page is no export on its own, and a folder leaves it out
    pages = export("candidate", "pages")[:3]
    assert [f["name"] for f in data["files"]] == sorted(p.name for p in pages)
    files = imported(by_status(pages, tmp_path / "files", "new-pages"))
    assert recs(tmp_path / "st", "new-pages") == recs(tmp_path / "files", "new-pages")
    for key in ("rows", "cases", "outcomes", "counts", "started", "declared", "files"):
        assert data[key] == files[key], key
    assert len(list(folder.iterdir())) == 6


@pytest.mark.parametrize("kind", ["pull", "expanded"])
def test_tf26_53_a_folder_of_two_evaluations_answers_is_refused_naming_each(tmp_path: Path, kind: str) -> None:
    folder = tmp_path / "both"
    folder.mkdir()
    for version in ("baseline", "candidate"):
        shutil.copy(export(version, kind)[0], folder)
    line = refused(run_import(by_status(folder, tmp_path / "st", None)))
    assert "2 evaluations" in line and EVALUATION["baseline"] in line and EVALUATION["candidate"] in line and "--evaluation" in line, line
    assert not (tmp_path / "st").exists()
    # each file is one evaluation, and is imported by itself
    for version in ("baseline", "candidate"):
        imported(by_status(folder / export(version, kind)[0].name, tmp_path / "st", version))


@pytest.mark.parametrize("held", [("pull", "expanded"), ("ui-json", "ui-csv")])
def test_tf26_53_a_folder_of_one_evaluation_s_answer_twice_is_refused_as_a_call_given_twice(tmp_path: Path, held: tuple[str, str]) -> None:
    folder = tmp_path / "twice"
    folder.mkdir()
    names = []
    for kind in held:
        shutil.copy(export("baseline", kind)[0], folder)
        names.append(export("baseline", kind)[0].name)
    line = refused(run_import(by_status(folder, tmp_path / "st", None, "--evaluation", evaluation("baseline"), case="none")))
    assert all(name in line for name in names) and "twice" in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF26-54 ----------

READER = ["--case-from", "example", "--outcome-from", "status"]
VERBS = {
    "fix-check": lambda a, b: ["fix-check", a, b, "--event", "missed", "--inputs", "all", "--max-mde", "0.2"],
    "compare": lambda a, b: ["compare", a, b, "--event", "missed", "--max-mde-hr", "1.5"],
    "changes": lambda a, b: ["changes", a, b, "--event", "missed"],
    "where": lambda a, b: ["where", a, "--event", "missed"],
}


def _folders(tmp: Path, kind: str) -> tuple[Path, Path]:
    """Two folders, each holding one version's export: the service's answer, or that
    evaluation's rows of the page's download."""
    made = []
    for version, name in (("baseline", "old-export"), ("candidate", "new-export")):
        folder = tmp / name
        folder.mkdir()
        if kind == "pull":
            shutil.copy(export(version, kind)[0], folder)
        else:
            write_calls(folder / "rows.jsonl", of_evaluation(calls_of(export(version, kind)[0]), version))
        made.append(folder)
    return made[0], made[1]


def _scrub(doc: Any) -> Any:
    """A verb's JSON with its store and its commands set aside (FI13)."""
    if isinstance(doc, dict):
        return {k: (None if k in ("store", "next", "created_at") else _scrub(v)) for k, v in doc.items() if k != "commands"}
    if isinstance(doc, list):
        return [_scrub(v) for v in doc]
    return doc


@pytest.mark.parametrize("verb", list(VERBS))
@pytest.mark.parametrize("kind", ["pull", "ui-json"])
def test_tf26_54_the_verbs_read_two_folders_of_the_reader_s_files(tmp_path: Path, verb: str, kind: str) -> None:
    old, new = _folders(tmp_path, kind)
    before = snapshot(tmp_path)
    with chdir(tmp_path):
        on_folders = trace([*VERBS[verb]("old-export", "new-export"), *READER, "--json"])
    if (verb, kind) == ("compare", "ui-json"):
        # the page's rows carry no step, and compare places tries on steps: it says so, and
        # names the fix check, which reads outcomes alone
        assert on_folders.code == 1 and "no traces" in on_folders.err and "fix-check" in on_folders.err, on_folders.text
        assert snapshot(tmp_path) == before
        return
    assert on_folders.code == 0, on_folders.err
    assert snapshot(tmp_path) == before, "a verb on folders writes nothing that stays"
    for folder in (old, new):
        imported([str(folder), "--store", str(tmp_path / "st"), *READER])
    stored = trace([*VERBS[verb]("old-export", "new-export"), "--store", str(tmp_path / "st"), "--json"])
    assert stored.code == 0, stored.err
    assert _scrub(json.loads(on_folders.out)) == _scrub(json.loads(stored.out))


def test_tf26_54_a_verb_on_folders_without_the_reader_s_flags_exits_2(tmp_path: Path) -> None:
    _folders(tmp_path, "pull")
    with chdir(tmp_path):
        ran = trace(["fix-check", "old-export", "new-export", "--event", "missed", "--inputs", "all", "--max-mde", "0.2"])
    assert ran.code == 2 and "--case-from" in ran.err, ran.text


# ---------- TF26-55 ----------


@pytest.mark.parametrize("kind", ["expanded", "ui-json", "ui-csv"])
def test_tf26_55_a_verdicts_file_joins_by_case_and_cannot_overturn_the_file(tmp_path: Path, kind: str) -> None:
    verdicts = tmp_path / "v.csv"
    # the errored case has no score and is censored, which is the file's own word: a verdict
    # fills what a file left out and never overturns what it recorded (TF22)
    verdicts.write_text("case,outcome\nc08,fail\n", encoding="utf-8")
    line = refused(run_import(of("baseline", kind, tmp_path / "st", "r", "--verdicts", verdicts, case="example:case")))
    assert "c08" in line and "censored" in line, line
    # a verdict that agrees with the file joins and changes nothing but the kind it names
    verdicts.write_text("case,outcome,failure_kind\nc10,fail,abstained\nc01,pass,\n", encoding="utf-8")
    data = imported(of("baseline", kind, tmp_path / "st", "r", "--verdicts", verdicts, case="example:case"))
    assert data["verdicts"]["by_case"] == 2 and data["verdicts"]["unmatched"] == 0, data["verdicts"]
    assert tally(data) == {"met": 6, "missed": 3} and data["no_outcome"] == {"no score": 1}
    assert recs(tmp_path / "st", "r")["c10"]["failure_kind"] == "abstained"


def test_tf26_55_a_verdict_that_differs_from_the_file_is_refused(tmp_path: Path) -> None:
    verdicts = tmp_path / "v.csv"
    verdicts.write_text("case,outcome\nc01,fail\n", encoding="utf-8")
    line = refused(run_import(of("baseline", "expanded", tmp_path / "st", "r", "--verdicts", verdicts, case="example:id")))
    assert "c01" in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF26-56 ----------

LISTED = {"pull": "old.jsonl", "expanded": "new.jsonl", "ui-json": "page.json", "ui-tsv": "page.tsv"}


def test_tf26_56_init_lists_the_exports_and_prints_a_line_for_each(tmp_path: Path) -> None:
    folder = work(tmp_path)
    (folder / "results").mkdir()
    for kind, name in LISTED.items():
        version = "baseline" if name.startswith("old") else "candidate"
        shutil.copy(export(version, kind)[0], folder / "results" / name)
    result = init_yes(folder, "--no-import")
    assert result.code == 0, result.text
    listed = {line.split()[0]: line for line in numbered(result.err).values()}
    assert sorted(listed) == sorted(f"results/{name}" for name in LISTED.values()), result.err
    assert all("Weave" in line for line in listed.values()), listed
    lines = [shell_words(line.strip()) for line in result.out.splitlines() if line.strip().startswith("poisson-trace import ")]
    for name in LISTED.values():
        words = next(w for w in lines if f"results/{name}" in w)
        assert words[:4] == ["poisson-trace", "import", "weave", f"results/{name}"], words
        assert words[4:6] == ["--store", "trace-store"] and words[6] == "--run" and words[7], words
    assert not (folder / "trace-store").exists()


# ---------- TF26-57 ----------


def _pair_config(folder: Path, *, store: str | None = None) -> str:
    (folder / "exports").mkdir(exist_ok=True)
    blocks = []
    for version, run in (("baseline", "old"), ("candidate", "new")):
        shutil.copy(export(version, "pull")[0], folder / "exports" / f"{run}.jsonl")
        blocks.append(import_entry(f"exports/{run}.jsonl", "weave", run, **OPTIONS))
    return config_text(*blocks, store=store, events=("missed",))


def test_tf26_57_an_entry_reads_with_its_options_by_their_flags_names(tmp_path: Path) -> None:
    from poisson_trace import config

    folder = work(tmp_path)
    text = config_text(import_entry("exports/page.json", "weave", "old", case_from="example:case", outcome_from="score:exact", cut=0.5,
                                    above=True, evaluation="trace-fixture-slice-baseline"), store="s")
    held = config.parse(text, folder / "trace.toml", "trace.toml", given=False)
    entry = held.imports[0]
    assert (entry.tool, entry.name, entry.file) == ("weave", "old", "exports/page.json")
    assert dict(entry.options) == {"case_from": "example:case", "outcome_from": "score:exact", "cut": 0.5, "above": True,
                                   "evaluation": "trace-fixture-slice-baseline"}


@pytest.mark.parametrize(("options", "said"), [
    ({"outcome_from": "status"}, "case_from"),
    ({"case_from": "example"}, "outcome_from"),
    ({"case_from": "example", "outcome_from": "status", "cutt": 0.5}, "cutt"),
    ({"case_from": "example", "outcome_from": "status", "select": ["metadata:a=b"]}, "select"),
    ({"case_from": "example", "outcome_from": "status", "below": "yes"}, "below"),
    ({"case_from": "example", "outcome_from": "status", "evaluation": ["a", "b"]}, "evaluation"),
])
def test_tf26_57_an_entry_s_options_are_checked_as_the_flags_are(tmp_path: Path, options: dict[str, Any], said: str) -> None:
    from poisson_trace import config

    folder = work(tmp_path)
    text = config_text(import_entry("exports/old.jsonl", "weave", "old", **options), store="s")
    with pytest.raises(config.ConfigError) as caught:
        config.parse(text, folder / "trace.toml", "trace.toml", given=False)
    assert said in str(caught.value) and "line " in str(caught.value), str(caught.value)


def test_tf26_57_doctor_setup_reads_a_pending_pair_and_init_imports_it(tmp_path: Path) -> None:
    folder = work(tmp_path)
    write_toml(folder, _pair_config(folder))
    with pulling(never(), key=None):
        checked = setup_check(folder, "--json")
        assert checked.code == 0, checked.text
        lines = [c["line"] for c in checked.json()["checks"] if c["name"] == "import"]
        assert len(lines) == 2 and all("weave, 10 rows" in line and "not imported yet" in line for line in lines), lines
        assert not (folder / "trace-store").exists()
        done = init_yes(folder, "--import")
        assert done.code == 0, done.text
    old = outcomes(folder / "trace-store", "old")
    assert sum(1 for o in old.values() if o == "met") == 6 and sum(1 for o in old.values() if o == "missed") == 3
    assert sorted(columns(folder / "trace-store", "new")) == sorted(old) == list(CASES)
    ran = trace_in(folder, ["fix-check", "old", "new", "--store", "trace-store", "--event", "missed", "--inputs", "all", "--max-mde", "0.2"])
    assert ran.code == 0, ran.text


def test_tf26_57_an_entry_picks_one_evaluation_out_of_the_page_s_download(tmp_path: Path) -> None:
    folder = work(tmp_path)
    (folder / "exports").mkdir()
    shutil.copy(export("baseline", "ui-json")[0], folder / "exports" / "page.json")
    blocks = [import_entry("exports/page.json", "weave", run, evaluation=evaluation(version), **OPTIONS)
              for version, run in (("baseline", "old"), ("candidate", "new"))]
    write_toml(folder, config_text(*blocks, store=None, events=("missed",)))
    done = init_yes(folder, "--import")
    assert done.code == 0, done.text
    assert sorted(columns(folder / "trace-store", "old")) == sorted(columns(folder / "trace-store", "new")) == list(CASES)
    old, new = outcomes(folder / "trace-store", "old"), outcomes(folder / "trace-store", "new")
    assert (sum(1 for o in old.values() if o == "missed"), sum(1 for o in new.values() if o == "missed")) == (3, 1)


def test_tf26_57_an_entry_whose_file_is_not_weave_s_fails_the_setup_check(tmp_path: Path) -> None:
    folder = work(tmp_path)
    (folder / "exports").mkdir()
    shutil.copy(INGEST / "promptfoo" / "results.json", folder / "exports" / "old.json")
    write_toml(folder, config_text(import_entry("exports/old.json", "weave", "old", **OPTIONS), store=None, events=("missed",)))
    checked = setup_check(folder, "--json")
    assert checked.code != 0, checked.text
    assert "exports/old.json" in checked.text


# ---------- TF26-58 ----------

OTHERS = {
    "langsmith": ("langsmith:trace-fixture-baseline-bbb64b8e", {"case_from": "example", "outcome_from": "status"}),
    "braintrust": ("braintrust:trace-fixture/slice-baseline", {"case_from": "record", "outcome_from": "error"}),
}


def _address_config(version: str = "baseline", name: str = "old", **changes: Any) -> str:
    options = {**OPTIONS, **changes}
    return config_text(import_entry(address(version), "weave", name, **options), store=None, events=("missed",))


def test_tf26_58_an_address_is_an_entry_of_the_weave_reader(tmp_path: Path) -> None:
    from poisson_trace import config

    folder = work(tmp_path)
    held = config.parse(_address_config(), folder / "trace.toml", "trace.toml", given=False)
    assert held.imports[0].file == address("baseline") and held.imports[0].tool == "weave"
    assert address("baseline") == f"weave:{PROJECT_ID}/trace-fixture-slice-baseline"
    for tool, options in (("table", {"case_column": "c", "outcome_column": "o", "failed": ["x"]}), ("junit", {}), *((t, o) for t, (_, o) in OTHERS.items())):
        text = config_text(import_entry(address("baseline"), tool, "pulled", **options), store="s")
        with pytest.raises(config.ConfigError) as caught:
            config.parse(text, folder / "trace.toml", "trace.toml", given=False)
        said = str(caught.value)
        assert address("baseline") in said and "weave" in said and "line " in said, said
    # the other readers' addresses under this reader are refused the same way, each naming its own
    for tool, (other, _) in OTHERS.items():
        text = config_text(import_entry(other, "weave", "pulled", **OPTIONS), store="s")
        with pytest.raises(config.ConfigError) as caught:
            config.parse(text, folder / "trace.toml", "trace.toml", given=False)
        assert other in str(caught.value) and tool in str(caught.value), str(caught.value)
    # a file whose name starts the same way and is no address stays a file
    held = config.parse(config_text(import_entry("weave/old.jsonl", "weave", "old", **OPTIONS), store="s"), folder / "trace.toml", "trace.toml", given=False)
    assert held.imports[0].file == "weave/old.jsonl"


def test_tf26_58_no_verb_and_no_doctor_asks_the_service_anything(tmp_path: Path) -> None:
    from tf17_support import CS

    folder = work(tmp_path)
    shutil.copytree(CS, folder / "store")
    text = config_text(import_entry(address("baseline"), "weave", "old", **OPTIONS), store="store")
    write_toml(folder, text)
    with pulling(never()) as (_, _waits):
        assert trace_in(folder, ["runs"]).code == 0
        assert trace_in(folder, ["doctor"]).code in (0, 4)
        ready = setup_check(folder, "--json")
        line = next(c for c in ready.json()["checks"] if c["name"] == "import")
        assert line["ok"] is True and address("baseline") in line["line"] and "not pulled" in line["line"], line
        assert KEY_VARIABLE in line["line"] and PLANTED_KEY not in ready.text
        assert "LANGSMITH_API_KEY" not in line["line"] and "BRAINTRUST_API_KEY" not in line["line"], line
    with pulling(never(), key=None) as (_, _waits):
        import os

        # another reader's key being set says nothing of Weave's
        os.environ["LANGSMITH_API_KEY"] = "lsv2_pt_another_key_entirely_0000"
        os.environ["BRAINTRUST_API_KEY"] = "sk-another-key-entirely-0000"
        unready = setup_check(folder, "--json")
        line = next(c for c in unready.json()["checks"] if c["name"] == "import")
        assert line["ok"] is False and KEY_VARIABLE in line["line"], line
        assert unready.code != 0 and "lsv2_pt" not in unready.text and "sk-another" not in unready.text
    assert not (folder / "trace-store").exists() and not (folder / "store" / ".poisson" / "raw").exists()


def test_tf26_58_init_pulls_a_pending_address_into_the_imports_store(tmp_path: Path) -> None:
    folder = work(tmp_path)
    write_toml(folder, config_text(
        import_entry(address("baseline"), "weave", "old", **OPTIONS),
        import_entry(address("candidate"), "weave", "new", **OPTIONS), store=None, events=("missed",)))
    with pulling() as (sent, _):
        done = init_yes(folder, "--import")
        assert done.code == 0, done.text
        assert sent.kinds() == WHOLE * 2
    store = folder / "trace-store"
    for run in ("old", "new"):
        assert sorted(p.name for p in raw_folder(store, run).iterdir()) == ["pull.json", "raw.jsonl"]
        assert sorted(columns(store, run)) == list(CASES)
    assert f"{PROJECT_ID}/trace-fixture-slice-baseline" in (raw_folder(store, "old") / "pull.json").read_text(encoding="utf-8")
    assert PLANTED_KEY not in done.text
    with pulling(never(), key=None):
        again = setup_check(folder)
        assert again.code == 0, again.text


def test_tf26_58_init_without_the_key_refuses_and_writes_no_run(tmp_path: Path) -> None:
    folder = work(tmp_path)
    write_toml(folder, _address_config())
    with pulling(never(), key=None):
        done = init_yes(folder, "--import")
    assert done.code == 1 and KEY_VARIABLE in done.err, done.text
    assert not (folder / "trace-store" / "old").exists()


# ---------- TF26-59 ----------


@pytest.mark.parametrize(("kind", "traces"), [("pull", "yes"), ("expanded", "yes"), ("ui-json", "no"), ("ui-csv", "no")])
def test_tf26_59_runs_says_where_the_run_came_from_and_whether_it_has_traces(tmp_path: Path, kind: str, traces: str) -> None:
    imported(of("baseline", kind, tmp_path / "st", "old", mode="status"))
    ran = trace(["runs", "--store", str(tmp_path / "st"), "--json"])
    assert ran.code == 0, ran.err
    row = json.loads(ran.out)["runs"][0]
    assert row["traced"] is (traces == "yes") and row["backend"] == "import:weave", row
