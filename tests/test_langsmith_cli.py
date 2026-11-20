"""TF24-47 to TF24-60: the reader in the import's command line, its refusals, its detector, folders
of its files, and its place in the config, ``init`` and ``doctor`` (the folder rules TF22 holds and
the ``[[import]]`` entries TF17 holds, as every reader has them).

- TF24-47: the import's help lists ``langsmith``; the reader's help is the verb's under both
  spellings, with its flags, each saying what it is and its default; the module has the readers'
  shape, and its example runs as written on a committed capture of the example's extension.
- TF24-48: the summary is the import's: ``poisson-trace.import/1``, the files' digests, a
  ``next:`` fix check on ``--event missed``; its plain Next line carries the flags that read the
  other version the same way, and that line runs when its two capitals are filled in; it says
  when a try counts as failed. A name the store holds is refused and the store unchanged.
- TF24-49: a file that is missing, empty, not JSON, of another shape, another tool's, of another
  extension, or a CSV that is not the page's, is refused in one plain line naming it, exit 1,
  nothing written; a broken line of a JSON Lines file is named by its number.
- TF24-50: a wrong command line exits 2 in one line naming the flag: no ``--case-from``, no
  ``--outcome-from``, a value neither takes, a score with no cut or no side or both sides, a cut
  or ``--failed`` where none is read, a metadata outcome with neither, a ``--select`` that is not
  ``metadata:KEY=VALUE``, a cut that is not a number.
- TF24-51: both spellings of the import print the same bytes, done or refused.
- TF24-52: ``looks_like`` claims each run export, feedback list and CSV with one line naming
  LangSmith, and no other file of the captures; no committed file of any tool is claimed by two
  readers (the table reader gives LangSmith's CSV and JSON Lines up); it never raises.
- TF24-53: a folder of the command's trace files is one run, named after the folder, the same
  run its files give (with the tool named or not); a folder holding a pull's runs and its
  feedback list is one run; a folder holding two versions' exports is refused as more than one
  run, naming an import for each.
- TF24-54: the verbs read two folders of trace files with the reader's flags, and print what
  they print on the same folders imported one by one.
- TF24-55: ``--verdicts`` joins by case; a verdict that differs from what the file recorded is
  refused.
- TF24-56: ``init`` lists each export as LangSmith's and prints an import line for each;
  ``doctor`` lists ``langsmith`` among the readers.
- TF24-57: an ``[[import]]`` entry of ``tool = "langsmith"`` is read with its options by their
  flags' names and checked as the flags are; ``init`` imports a pending pair and ``doctor
  --setup`` reads them.
- TF24-58: an entry whose ``file`` is ``langsmith:NAME`` is an address: accepted with ``tool =
  "langsmith"`` and refused under any other tool; no verb, and neither ``doctor`` nor ``doctor
  --setup``, asks the service anything; ``doctor --setup`` says it is not pulled there and
  whether the key is set; ``init`` pulls it into the imports' store, saving the raw copy.
- TF24-59: the readers' two sentences: ``runs`` shows an imported run's backend as
  ``import:langsmith`` and whether it has traces.
- TF24-60: the module of each reader that pulls (LangSmith, Braintrust, Weave) documents what
  it does not keep, in plain words, and its description names its key and its address.

That the import's help lists ``langsmith`` (TF24-47) and that ``doctor`` lists it among the
readers (TF24-56) is held by ``test_docs_readers.py`` (TF5-20), which holds the whole help and
``doctor``'s readers line byte for byte.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from look_support import chdir, trace, trace_import
from names_support import shell_words
from setup_support import init_yes, numbered, work
from setup_agent_support import config_text, import_entry, setup_check, trace_in, write_toml
from signals_support import INGEST, run_import
from langsmith_support import (
    API, CASES, EXPERIMENT, EXPORTS, KEY_VARIABLE, PLANTED_KEY, Transport, address, by_status, columns, export, feedback_file,
    imported, ls_argv, pulling, raw_folder, recs, refused, snapshot, tally, wrong_line, write_csv,
)

PRESENT = ("deepeval", "ragas", "table", "junit", "promptfoo", "inspect", "openai-evals", "langsmith")
FLAGS = ("--case-from", "--outcome-from", "--cut", "--below", "--above", "--failed", "--select", "--keep-raw-text", "--page-size")
OPTIONS = {"case_from": "metadata:ls_example_case", "outcome_from": "feedback:exact", "cut": 0.5, "below": True}


def _never() -> Transport:
    class Never(Transport):
        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("a request was made")

    return Never()


# ---------- TF24-47 ----------


def test_tf24_47_the_reader_s_help_is_the_verb_s_and_names_its_flags() -> None:
    a, b = trace(["import", "langsmith", "--help"]), trace_import(["langsmith", "--help"])
    assert a.code == b.code == 0 and a.out == b.out and a.err == b.err == "", a.text + b.text
    assert a.out.split("\n\n")[0].startswith("usage: poisson-trace import langsmith"), a.out
    for flag in ("--store", "--run", "--started", "--json", "--verdicts", *FLAGS):
        assert flag in a.out, flag
    for word in ("example", "metadata:KEY", "input", "none", "status", "feedback:KEY", "LANGSMITH_API_KEY", "langsmith:"):
        assert word in a.out, word


def test_tf24_47_the_module_has_the_readers_shape() -> None:
    from poisson_trace.ingest import langsmith
    from poisson_trace.ingest.importing import READERS, present, reader_options

    # the readers through this one, in the import's order; a reader after it has its own tests
    assert "langsmith" in READERS and present()[:len(PRESENT)] == PRESENT
    for attr in ("add_arguments", "read", "usage", "looks_like", "DESCRIPTION", "EXAMPLE", "SHAPES"):
        assert hasattr(langsmith, attr), attr
    assert langsmith.EXAMPLE.startswith("poisson-trace import langsmith "), langsmith.EXAMPLE
    options = reader_options("langsmith")
    assert options["case_from"].required and options["outcome_from"].required
    assert options["select"].many and options["failed"].many
    assert not options["below"].takes_value and not options["keep_raw_text"].takes_value
    for dest in ("cut", "below", "above", "failed", "select", "keep_raw_text", "page_size"):
        assert not options[dest].required, dest


def test_tf24_47_the_example_runs_as_written_on_a_capture_of_its_extension(tmp_path: Path) -> None:
    from poisson_trace.ingest import langsmith

    words = shell_words(langsmith.EXAMPLE)
    assert words[:3] == ["poisson-trace", "import", "langsmith"]
    files = [w for w in words[3:] if not w.startswith("-") and re.search(r"\.(json|jsonl|csv)$", w)]
    assert len(files) == 1, words
    source = {".json": export("baseline", "v1")[0], ".jsonl": export("baseline", "cli-runs")[0], ".csv": export("baseline", "ui")[0]}
    shutil.copy(source[Path(files[0]).suffix], tmp_path / files[0])
    with chdir(tmp_path):
        ran = trace(words[1:])
    assert ran.code == 0 and ran.out.startswith("ok  wrote run "), ran.text


# ---------- TF24-48 ----------


@pytest.mark.parametrize("kind", EXPORTS)
def test_tf24_48_the_summary_is_the_import_s(tmp_path: Path, kind: str) -> None:
    data = imported(by_status(export("baseline", kind), tmp_path / "st", "first"))
    assert data["run"] == "first" and data["store"] == str(tmp_path / "st") and data["tool"] == "langsmith"
    assert data["next"].startswith("poisson-trace fix-check OLD NEW ") and "--event missed" in data["next"]
    assert data["declared"]["case_from"] == "metadata:ls_example_case"
    text = run_import(ls_argv(export("baseline", kind), tmp_path / "st2", "first"))
    assert text.code == 0 and text.out.startswith("ok  wrote run first to "), text.out
    assert text.out.rstrip("\n").splitlines()[-1].startswith("next: poisson-trace fix-check OLD NEW"), text.out
    failed = next(line for line in text.out.splitlines() if line.startswith("- Failures: "))
    assert "exact" in failed and "0.5" in failed and "below" in failed, failed
    by = run_import(by_status(export("baseline", kind), tmp_path / "st3", "first"))
    failed = next(line for line in by.out.splitlines() if line.startswith("- Failures: "))
    assert "error" in failed and "1 failed and 9 passed" in failed, failed


@pytest.mark.parametrize("kind", ["v1", "cli-runs", "ui"])
def test_tf24_48_the_next_line_reads_the_other_version_the_same_way(tmp_path: Path, kind: str) -> None:
    files = export("baseline", kind)
    argv = ls_argv(files, tmp_path / "st", "old", "--select", "metadata:version=baseline")
    text = run_import(argv)
    assert text.code == 0, text.err
    line = next(line for line in text.out.splitlines() if line.startswith("- Next: "))
    command = re.search(r"`(poisson-trace import langsmith [^`]+)`", line)
    assert command, line
    words = shell_words(command.group(1))
    for flag, value in (("--case-from", "metadata:ls_example_case"), ("--outcome-from", "feedback:exact"), ("--cut", "0.5")):
        assert words[words.index(flag) + 1] == value, words
    assert "--below" in words and words[words.index("--select") + 1] == "metadata:version=baseline"
    other = export("candidate", kind)[0]
    filled = [str(other) if w.startswith("OTHER.") else ("new" if w == "OTHER" else w) for w in words]
    filled[filled.index("metadata:version=baseline")] = "metadata:version=candidate"
    assert trace(filled[1:]).code == 0
    assert sorted(columns(tmp_path / "st", "new")) == list(CASES)


@pytest.mark.parametrize("kind", ["v2"])
def test_tf24_48_a_name_in_use_is_refused_and_nothing_changes(tmp_path: Path, kind: str) -> None:
    imported(by_status(export("baseline", kind), tmp_path / "st", "first"))
    before = snapshot(tmp_path / "st")
    line = refused(run_import(by_status(export("candidate", kind), tmp_path / "st", "first")))
    assert "first" in line, line
    assert snapshot(tmp_path / "st") == before


# ---------- TF24-49 ----------


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def _dir(path: Path) -> Path:
    path.mkdir()
    return path


def _csv_without(tmp: Path, column: str) -> Path:
    return write_csv(tmp / "page.csv", export("baseline", "ui")[0], header=lambda fields: [f for f in fields if f != column])


def _csv_bad_cell(tmp: Path) -> Path:
    def edit(rows: list[dict[str, str]]) -> None:
        rows[2]["run"] = "{not json"

    return write_csv(tmp / "cell.csv", export("baseline", "ui")[0], edit)


MALFORMED: dict[str, Any] = {
    "missing": lambda tmp: tmp / "gone.json",
    "empty": lambda tmp: _write(tmp / "e.json", b""),
    "an empty line file": lambda tmp: _write(tmp / "e.jsonl", b"\n\n"),
    "not JSON": lambda tmp: _write(tmp / "n.json", b'{"items": [1, 2'),
    "not text": lambda tmp: _write(tmp / "b.json", b"\xff\xfe\x00\x01"),
    "a JSON number": lambda tmp: _write(tmp / "num.json", b"42\n"),
    "a list of numbers": lambda tmp: _write(tmp / "l.json", b"[1, 2, 3]\n"),
    "an object with no runs": lambda tmp: _write(tmp / "o.json", (API / "dataset.json").read_bytes() and b'{"name": "x"}'),
    "the dataset's examples": lambda tmp: _write(tmp / "examples.json", (API / "examples.json").read_bytes()),
    "the session record": lambda tmp: _write(tmp / "session.json", (API / "baseline.session.json").read_bytes()),
    "promptfoo's results": lambda tmp: _write(tmp / "pf.json", (INGEST / "promptfoo" / "results.json").read_bytes()),
    "an OpenAI Evals record": lambda tmp: _write(tmp / "oe.jsonl", (INGEST / "openai-evals" / "old.jsonl").read_bytes()),
    "a table": lambda tmp: _write(tmp / "table.csv", (INGEST / "table" / "humaneval-a.csv").read_bytes()),
    "Braintrust's CSV": lambda tmp: _write(tmp / "bt.csv", (INGEST / "braintrust" / "ui" / "slice-baseline.csv").read_bytes()),
    "a folder named as a file": lambda tmp: _dir(tmp / "folder.json"),
    "another extension": lambda tmp: _write(tmp / "runs.txt", export("baseline", "v2")[0].read_bytes()),
    "another extension, a run a line": lambda tmp: _write(tmp / "runs.ndjson", export("baseline", "cli-runs")[0].read_bytes()),
    "a CSV without its run column": lambda tmp: _csv_without(tmp, "run"),
    "a CSV without its status column": lambda tmp: _csv_without(tmp, "status"),
    "a CSV cell that is not JSON": _csv_bad_cell,
}


@pytest.mark.parametrize("label", list(MALFORMED))
def test_tf24_49_a_file_not_the_reader_s_is_refused_in_one_line_naming_it(tmp_path: Path, label: str) -> None:
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


def test_tf24_49_a_broken_line_is_named_by_its_number(tmp_path: Path) -> None:
    lines = export("baseline", "cli-runs")[0].read_text(encoding="utf-8").splitlines()
    lines[6] = lines[6][:40]
    path = tmp_path / "runs.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    line = refused(run_import(by_status(path, tmp_path / "st", "v")))
    assert "runs.jsonl" in line and "line 7" in line, line
    lines[6] = "[1, 2]"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    line = refused(run_import(by_status(path, tmp_path / "st", "v")))
    assert "line 7" in line, line
    assert not (tmp_path / "st").exists()


def test_tf24_49_a_feedback_list_alone_is_no_run(tmp_path: Path) -> None:
    line = refused(run_import(ls_argv(feedback_file("baseline"), tmp_path / "st", "v")))
    assert "no row" in line or "no run" in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF24-50 ----------

V2 = export("baseline", "v2")
USAGE: dict[str, Any] = {
    "no --case-from": (lambda root: ls_argv(V2, root, "r", case=None), "--case-from"),
    "no --outcome-from": (lambda root: ls_argv(V2, root, "r", outcome=None), "--outcome-from"),
    "a case that is none of the four": (lambda root: by_status(V2, root, "r", case="row"), "--case-from"),
    "a case of metadata with no key": (lambda root: by_status(V2, root, "r", case="metadata:"), "--case-from"),
    "an outcome that is none of the three": (lambda root: ls_argv(V2, root, "r", outcome="score"), "--outcome-from"),
    "a feedback outcome with no key": (lambda root: ls_argv(V2, root, "r", outcome="feedback:"), "--outcome-from"),
    "a score with no cut": (lambda root: ls_argv(V2, root, "r", cut=None), "--cut"),
    "a cut with no side": (lambda root: ls_argv(V2, root, "r", side=None), "--below"),
    "a cut with both sides": (lambda root: ls_argv(V2, root, "r", "--above"), "--above"),
    "a side with no cut": (lambda root: ls_argv(V2, root, "r", "--below", cut=None), "--cut"),
    "a cut with status": (lambda root: by_status(V2, root, "r", "--cut", "0.5", "--below"), "--cut"),
    "failed values with status": (lambda root: by_status(V2, root, "r", "--failed", "x"), "--failed"),
    "failed values with a score": (lambda root: ls_argv(V2, root, "r", "--failed", "x"), "--failed"),
    "a metadata outcome with neither": (lambda root: ls_argv(V2, root, "r", outcome="metadata:version", cut=None), "--failed"),
    "a metadata outcome with both": (lambda root: ls_argv(V2, root, "r", "--failed", "x", outcome="metadata:version"), "--failed"),
    "a cut that is no number": (lambda root: ls_argv(V2, root, "r", cut="high"), "--cut"),
    "a cut that is not a number at all": (lambda root: ls_argv(V2, root, "r", cut="nan"), "--cut"),
    "a selection with no value": (lambda root: by_status(V2, root, "r", "--select", "metadata:version"), "--select"),
    "a selection of another kind": (lambda root: by_status(V2, root, "r", "--select", "tag:x=y"), "--select"),
    "no file": (lambda root: by_status([], root, "r"), "FILE"),
}


@pytest.mark.parametrize("label", list(USAGE))
def test_tf24_50_a_wrong_command_line_exits_2_naming_the_flag(tmp_path: Path, label: str) -> None:
    make, flag = USAGE[label]
    line = wrong_line(run_import(make(tmp_path / "st")))
    assert flag in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF24-51 ----------


@pytest.mark.parametrize("kind", ["v2"])
def test_tf24_51_both_spellings_print_the_same_bytes(tmp_path: Path, kind: str) -> None:
    outs = []
    for spelling in ("verb", "alias"):
        folder = tmp_path / spelling
        folder.mkdir()
        argv = by_status(export("candidate", kind), Path("st"), "first", "--started", "2026-11-09T20:38:19Z")
        with chdir(folder):
            ran = trace(["import", *argv]) if spelling == "verb" else trace_import(argv)
            again = trace(["import", *argv]) if spelling == "verb" else trace_import(argv)
        outs.append((ran.code, ran.out, ran.err, again.code, again.out, again.err))
        assert ran.code == 0 and again.code == 1, ran.text + again.text
    assert outs[0] == outs[1]


# ---------- TF24-52 ----------


def _claimed(path: Path) -> list[str]:
    from poisson_trace.ingest.importing import present, reader

    return [tool for tool in present() if reader(tool).looks_like(path) is not None]


def _ours() -> list[Path]:
    files = [p for v in ("baseline", "candidate") for k in EXPORTS for p in export(v, k)]
    files += [p for k in ("v1-pages", "v2-pages") for p in export("candidate", k)]
    files += [feedback_file("baseline"), feedback_file("candidate"), API / "candidate.feedback.page-1.json", API / "candidate.feedback.page-2.json"]
    return files


def test_tf24_52_every_export_is_claimed_by_langsmith_alone_with_one_line() -> None:
    from poisson_trace.ingest import langsmith

    for path in _ours():
        said = langsmith.looks_like(path)
        assert isinstance(said, str) and said.strip() and "\n" not in said and "LangSmith" in said, (path.name, said)
        assert langsmith.looks_like(str(path)) == said
        assert _claimed(path) == ["langsmith"], (path.name, _claimed(path))


def test_tf24_52_the_other_files_of_the_capture_are_not_runs() -> None:
    from poisson_trace.ingest import langsmith

    for name in ("requests.json", "dataset.json", "examples.json", "baseline.session.json", "candidate.session.json", "candidate.feedback.page-3.json"):
        assert langsmith.looks_like(API / name) is None, name
    for name in ("fixture_langsmith.py", "pull.py"):
        assert langsmith.looks_like(API.parent / name) is None, name


def test_tf24_52_no_committed_file_is_claimed_by_two_readers() -> None:
    from poisson_trace.ingest import langsmith

    ours = {p.resolve() for p in _ours()}
    for path in sorted(p for p in INGEST.rglob("*") if p.is_file() and p.suffix in (".json", ".jsonl", ".gz", ".csv", ".xml", ".eval", ".tsv")):
        claimed = _claimed(path)
        assert len(claimed) <= 1, (str(path.relative_to(INGEST)), claimed)
        if path.resolve() not in ours:
            assert langsmith.looks_like(path) is None, str(path.relative_to(INGEST))


def test_tf24_52_looks_like_never_raises_and_claims_none_of_these(tmp_path: Path) -> None:
    from poisson_trace.ingest import langsmith

    (tmp_path / "folder.json").mkdir()
    for name, data in (("empty.json", b""), ("empty.jsonl", b""), ("empty.csv", b""), ("junk.json", b"\xff\xfe\x00"), ("list.json", b"[1, 2, 3]"),
                       ("number.jsonl", b"42\n"), ("spec.jsonl", b'{"spec": 1}\n'), ("half.json", b'{"items": [{"id": '),
                       ("header.csv", b"id,inputs\n"), ("items.json", b'{"items": []}'), ("runs.json", b'{"runs": [1]}')):
        (tmp_path / name).write_bytes(data)
    shutil.copy(export("baseline", "v2")[0], tmp_path / "runs.txt")
    for path in [tmp_path / "missing.json", *sorted(tmp_path.iterdir())]:
        assert langsmith.looks_like(path) is None, path.name
        assert langsmith.looks_like(str(path)) is None, path.name


# ---------- TF24-53 ----------


def _traces(tmp: Path, version: str, name: str) -> Path:
    folder = tmp / name
    shutil.copytree(export(version, "cli-traces")[0].parent, folder)
    return folder


@pytest.mark.parametrize("named", [True, False])
def test_tf24_53_a_folder_of_trace_files_is_one_run(tmp_path: Path, named: bool) -> None:
    folder = _traces(tmp_path, "candidate", "new-traces")
    (folder / ".DS_Store").write_bytes(b"x")
    (folder / "README.md").write_text("notes", encoding="utf-8")
    flags = ["--case-from", "metadata:ls_example_case", "--outcome-from", "status", "--json"]
    argv = [*(["langsmith"] if named else []), str(folder), "--store", str(tmp_path / "st"), *flags]
    result = run_import(argv)
    assert result.code == 0, result.err
    data = json.loads(result.out)
    assert data["run"] == "new-traces" and data["tool"] == "langsmith" and data["rows"] == 10
    assert [f["name"] for f in data["files"]] == sorted(p.name for p in export("candidate", "cli-traces"))
    files = imported(by_status(export("candidate", "cli-traces"), tmp_path / "files", "new-traces"))
    assert recs(tmp_path / "st", "new-traces") == recs(tmp_path / "files", "new-traces")
    for key in ("rows", "cases", "outcomes", "counts", "started", "declared", "files"):
        assert data[key] == files[key], key
    assert sorted(p.name for p in folder.iterdir()) == sorted([".DS_Store", "README.md", *[p.name for p in export("candidate", "cli-traces")]])


def test_tf24_53_a_folder_of_a_pull_s_runs_and_feedback_is_one_run(tmp_path: Path) -> None:
    folder = tmp_path / "baseline"
    folder.mkdir()
    for path in (*export("baseline", "v2"), feedback_file("baseline")):
        shutil.copy(path, folder / path.name)
    data = imported(ls_argv(folder, tmp_path / "st", None))
    assert data["run"] == "baseline" and tally(data) == {"met": 6, "missed": 4}
    assert sorted(f["name"] for f in data["files"]) == ["baseline.feedback.json", "baseline.runs-v2.json"]


def test_tf24_53_a_folder_of_two_versions_is_refused_naming_an_import_for_each(tmp_path: Path) -> None:
    folder = tmp_path / "both"
    folder.mkdir()
    for version in ("baseline", "candidate"):
        shutil.copy(export(version, "v2")[0], folder)
    result = run_import(by_status(folder, tmp_path / "st", None, case="example"))
    line = refused(result)
    assert "more than one run" in line and "baseline.runs-v2.json" in line and "candidate.runs-v2.json" in line, line
    nexts = [shell_words(following[len("  next: "):]) for following in result.err.splitlines()[1:]]
    assert len(nexts) == 2 and all(w[:3] == ["poisson-trace", "import", "langsmith"] for w in nexts), result.err
    assert all("--case-from" in w and "--outcome-from" in w for w in nexts), nexts
    assert not (tmp_path / "st").exists()


# ---------- TF24-54 ----------

READER = ["--case-from", "metadata:ls_example_case", "--outcome-from", "status"]
VERBS = {
    "fix-check": lambda a, b: ["fix-check", a, b, "--event", "missed", "--inputs", "all", "--max-mde", "0.2"],
    "compare": lambda a, b: ["compare", a, b, "--event", "missed", "--max-mde-hr", "1.5"],
    "changes": lambda a, b: ["changes", a, b, "--event", "missed"],
    "where": lambda a, b: ["where", a, "--event", "missed"],
}


def _scrub(doc: Any) -> Any:
    """A verb's JSON with its store and its commands set aside."""
    if isinstance(doc, dict):
        return {k: (None if k in ("store", "next", "created_at") else _scrub(v)) for k, v in doc.items() if k != "commands"}
    if isinstance(doc, list):
        return [_scrub(v) for v in doc]
    return doc


@pytest.mark.parametrize("verb", list(VERBS))
def test_tf24_54_the_verbs_read_two_folders_of_trace_files(tmp_path: Path, verb: str) -> None:
    old, new = _traces(tmp_path, "baseline", "old-traces"), _traces(tmp_path, "candidate", "new-traces")
    before = snapshot(tmp_path)
    with chdir(tmp_path):
        on_folders = trace([*VERBS[verb]("old-traces", "new-traces"), *READER, "--json"])
    assert on_folders.code == 0, on_folders.err
    assert snapshot(tmp_path) == before, "a verb on folders writes nothing that stays"
    for folder in (old, new):
        imported([str(folder), "--store", str(tmp_path / "st"), *READER])
    stored = trace([*VERBS[verb]("old-traces", "new-traces"), "--store", str(tmp_path / "st"), "--json"])
    assert stored.code == 0, stored.err
    assert _scrub(json.loads(on_folders.out)) == _scrub(json.loads(stored.out))


def test_tf24_54_a_verb_on_folders_without_the_reader_s_flags_exits_2(tmp_path: Path) -> None:
    _traces(tmp_path, "baseline", "old-traces")
    _traces(tmp_path, "candidate", "new-traces")
    with chdir(tmp_path):
        ran = trace(["fix-check", "old-traces", "new-traces", "--event", "missed", "--inputs", "all", "--max-mde", "0.2"])
    assert ran.code == 2 and "--case-from" in ran.err, ran.text


# ---------- TF24-55 ----------


@pytest.mark.parametrize("kind", ["v2", "cli-runs"])
def test_tf24_55_a_verdicts_file_fills_what_the_statistics_lack_by_case(tmp_path: Path, kind: str) -> None:
    verdicts = tmp_path / "v.csv"
    verdicts.write_text("case,outcome,failure_kind\nc10,fail,abstained\n", encoding="utf-8")
    data = imported(ls_argv(export("baseline", kind), tmp_path / "st", "r", "--verdicts", verdicts))
    assert data["verdicts"]["by_case"] == 1 and data["verdicts"]["unmatched"] == 0, data["verdicts"]
    assert tally(data) == {"met": 6, "missed": 3} and data["no_outcome"] == {"no score": 1}
    stored = recs(tmp_path / "st", "r")
    assert stored["c10"]["outcome"] == "fail" and stored["c10"]["failure_kind"] == "abstained"
    # the errored root with no score is censored, which is the file's own word: a verdict
    # fills what a file left out and never overturns what it recorded (TF22)
    assert stored["c08"]["outcome"] == "censored" and stored["c08"]["failure_kind"] == "timeout"
    verdicts.write_text("case,outcome\nc08,fail\n", encoding="utf-8")
    line = refused(run_import(ls_argv(export("baseline", kind), tmp_path / "st", "r2", "--verdicts", verdicts)))
    assert "c08" in line and "censored" in line, line


def test_tf24_55_a_verdict_that_differs_from_the_file_is_refused(tmp_path: Path) -> None:
    verdicts = tmp_path / "v.csv"
    verdicts.write_text("case,outcome\nc01,fail\n", encoding="utf-8")
    line = refused(run_import(ls_argv(export("baseline", "v1"), tmp_path / "st", "r", "--verdicts", verdicts)))
    assert "c01" in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF24-56 ----------

LISTED = {"cli-runs": "baseline-runs.jsonl", "v1": "candidate.runs-v1.json", "v2": "baseline.runs-v2.json", "ui": "trace-fixture-candidate-7e3f7200.csv"}


def test_tf24_56_init_lists_the_exports_and_prints_a_line_for_each(tmp_path: Path) -> None:
    folder = work(tmp_path)
    (folder / "results").mkdir()
    for kind, name in LISTED.items():
        version = "baseline" if name.startswith("baseline") else "candidate"
        shutil.copy(export(version, kind)[0], folder / "results" / name)
    result = init_yes(folder, "--no-import")
    assert result.code == 0, result.text
    listed = {line.split()[0]: line for line in numbered(result.err).values()}
    assert sorted(listed) == sorted(f"results/{name}" for name in LISTED.values()), result.err
    assert all("LangSmith" in line for line in listed.values()), listed
    lines = [shell_words(line.strip()) for line in result.out.splitlines() if line.strip().startswith("poisson-trace import ")]
    for name in LISTED.values():
        words = next(w for w in lines if f"results/{name}" in w)
        assert words[:4] == ["poisson-trace", "import", "langsmith", f"results/{name}"], words
        assert words[4:6] == ["--store", "trace-store"] and words[6] == "--run" and words[7], words
    assert not (folder / "trace-store").exists()


# ---------- TF24-57 ----------


def _pair_config(folder: Path, *, store: str | None = None) -> str:
    (folder / "exports").mkdir(exist_ok=True)
    blocks = []
    for version, run in (("baseline", "old"), ("candidate", "new")):
        shutil.copy(export(version, "v1")[0], folder / "exports" / f"{run}.json")
        blocks.append(import_entry(f"exports/{run}.json", "langsmith", run, **OPTIONS))
    return config_text(*blocks, store=store, events=("missed",))


def test_tf24_57_an_entry_reads_with_its_options_by_their_flags_names(tmp_path: Path) -> None:
    from poisson_trace import config

    folder = work(tmp_path)
    text = config_text(import_entry("exports/old.json", "langsmith", "old", case_from="example", outcome_from="metadata:version",
                                    failed=["baseline"], select=["metadata:model=gpt-4.1-mini"]), store="s")
    held = config.parse(text, folder / "trace.toml", "trace.toml", given=False)
    entry = held.imports[0]
    assert (entry.tool, entry.name, entry.file) == ("langsmith", "old", "exports/old.json")
    assert dict(entry.options) == {"case_from": "example", "outcome_from": "metadata:version", "failed": ["baseline"], "select": ["metadata:model=gpt-4.1-mini"]}


@pytest.mark.parametrize(("options", "said"), [
    ({"outcome_from": "status"}, "case_from"),
    ({"case_from": "example"}, "outcome_from"),
    ({"case_from": "example", "outcome_from": "status", "cutt": 0.5}, "cutt"),
    ({"case_from": "example", "outcome_from": "status", "select": "metadata:a=b"}, "select"),
    ({"case_from": "example", "outcome_from": "status", "below": "yes"}, "below"),
])
def test_tf24_57_an_entry_s_options_are_checked_as_the_flags_are(tmp_path: Path, options: dict[str, Any], said: str) -> None:
    from poisson_trace import config

    folder = work(tmp_path)
    text = config_text(import_entry("exports/old.json", "langsmith", "old", **options), store="s")
    with pytest.raises(config.ConfigError) as caught:
        config.parse(text, folder / "trace.toml", "trace.toml", given=False)
    assert said in str(caught.value) and "line " in str(caught.value), str(caught.value)


def test_tf24_57_doctor_setup_reads_a_pending_pair_and_init_imports_it(tmp_path: Path) -> None:
    folder = work(tmp_path)
    write_toml(folder, _pair_config(folder))
    with pulling(_never(), key=None):
        checked = setup_check(folder, "--json")
        assert checked.code == 0, checked.text
        lines = [c["line"] for c in checked.json()["checks"] if c["name"] == "import"]
        assert len(lines) == 2 and all("langsmith, 10 rows" in line and "not imported yet" in line for line in lines), lines
        assert not (folder / "trace-store").exists()
        done = init_yes(folder, "--import")
        assert done.code == 0, done.text
    assert tally({"outcomes": {k: sum(1 for r in columns(folder / "trace-store", "old").values() if r["outcome"] == k) for k in ("met", "missed")}}) == {"met": 6, "missed": 4}
    assert sorted(columns(folder / "trace-store", "new")) == sorted(columns(folder / "trace-store", "old"))
    ran = trace_in(folder, ["fix-check", "old", "new", "--store", "trace-store", "--event", "missed", "--inputs", "all", "--max-mde", "0.2"])
    assert ran.code == 0, ran.text


def test_tf24_57_an_entry_whose_file_is_not_langsmith_s_fails_the_setup_check(tmp_path: Path) -> None:
    folder = work(tmp_path)
    (folder / "exports").mkdir()
    shutil.copy(INGEST / "promptfoo" / "results.json", folder / "exports" / "old.json")
    write_toml(folder, config_text(import_entry("exports/old.json", "langsmith", "old", **OPTIONS), store=None, events=("missed",)))
    checked = setup_check(folder, "--json")
    assert checked.code != 0, checked.text
    assert "exports/old.json" in checked.text


# ---------- TF24-58 ----------


def _address_config(version: str = "baseline", name: str = "old", **changes: Any) -> str:
    options = {**OPTIONS, **changes}
    return config_text(import_entry(address(version), "langsmith", name, **options), store=None, events=("missed",))


def test_tf24_58_an_address_is_an_entry_of_the_langsmith_reader(tmp_path: Path) -> None:
    from poisson_trace import config

    folder = work(tmp_path)
    held = config.parse(_address_config(), folder / "trace.toml", "trace.toml", given=False)
    assert held.imports[0].file == address("baseline") and held.imports[0].tool == "langsmith"
    for tool, options in (("table", {"case_column": "c", "outcome_column": "o", "failed": ["x"]}), ("junit", {})):
        text = config_text(import_entry(address("baseline"), tool, "pulled", **options), store="s")
        with pytest.raises(config.ConfigError) as caught:
            config.parse(text, folder / "trace.toml", "trace.toml", given=False)
        said = str(caught.value)
        assert address("baseline") in said and "langsmith" in said and "line " in said, said
    # a file whose name starts the same way and is no address stays a file
    held = config.parse(config_text(import_entry("langsmith/old.json", "langsmith", "old", **OPTIONS), store="s"), folder / "trace.toml", "trace.toml", given=False)
    assert held.imports[0].file == "langsmith/old.json"


def test_tf24_58_no_verb_and_no_doctor_asks_the_service_anything(tmp_path: Path) -> None:
    from setup_agent_support import CS

    folder = work(tmp_path)
    shutil.copytree(CS, folder / "store")
    text = config_text(import_entry(address("baseline"), "langsmith", "old", **OPTIONS), store="store")
    write_toml(folder, text)
    with pulling(_never()) as (_, _waits):
        assert trace_in(folder, ["runs"]).code == 0
        assert trace_in(folder, ["doctor"]).code in (0, 4)
        ready = setup_check(folder, "--json")
        line = next(c for c in ready.json()["checks"] if c["name"] == "import")
        assert line["ok"] is True and address("baseline") in line["line"] and "not pulled" in line["line"], line
        assert KEY_VARIABLE in line["line"] and PLANTED_KEY not in ready.text
    with pulling(_never(), key=None) as (_, _waits):
        unready = setup_check(folder, "--json")
        line = next(c for c in unready.json()["checks"] if c["name"] == "import")
        assert line["ok"] is False and KEY_VARIABLE in line["line"], line
        assert unready.code != 0
    assert not (folder / "trace-store").exists() and not (folder / "store" / ".poisson" / "raw").exists()


def test_tf24_58_init_pulls_a_pending_address_into_the_imports_store(tmp_path: Path) -> None:
    folder = work(tmp_path)
    write_toml(folder, config_text(
        import_entry(address("baseline"), "langsmith", "old", **OPTIONS),
        import_entry(address("candidate"), "langsmith", "new", **OPTIONS), store=None, events=("missed",)))
    with pulling() as (sent, _):
        done = init_yes(folder, "--import")
        assert done.code == 0, done.text
        assert sent.paths() == ["GET /api/v1/sessions", "POST /api/v2/runs/query", "GET /api/v1/feedback"] * 2
    store = folder / "trace-store"
    for run in ("old", "new"):
        assert sorted(p.name for p in raw_folder(store, run).iterdir()) == ["pull.json", "raw.jsonl"]
        assert sorted(columns(store, run)) == list(CASES)
    assert EXPERIMENT["baseline"] in (raw_folder(store, "old") / "pull.json").read_text(encoding="utf-8")
    assert PLANTED_KEY not in done.text
    with pulling(_never(), key=None):
        again = setup_check(folder)
        assert again.code == 0, again.text


def test_tf24_58_init_without_the_key_refuses_and_writes_no_run(tmp_path: Path) -> None:
    folder = work(tmp_path)
    write_toml(folder, _address_config())
    with pulling(_never(), key=None):
        done = init_yes(folder, "--import")
    assert done.code == 1 and KEY_VARIABLE in done.err, done.text
    assert not (folder / "trace-store" / "old").exists()


# ---------- TF24-59 ----------


@pytest.mark.parametrize(("kind", "traces"), [("v2", "yes"), ("ui", "no")])
def test_tf24_59_runs_says_where_the_run_came_from_and_whether_it_has_traces(tmp_path: Path, kind: str, traces: str) -> None:
    imported(by_status(export("baseline", kind), tmp_path / "st", "old"))
    ran = trace(["runs", "--store", str(tmp_path / "st"), "--json"])
    assert ran.code == 0, ran.err
    row = json.loads(ran.out)["runs"][0]
    assert row["traced"] is (traces == "yes") and row["backend"] == "import:langsmith", row


# ---------- TF24-60 ----------


#: Each reader that pulls, with what its description names: its key and, where it has one of
#: several parts, its address.
DESCRIBED: dict[str, tuple[str, ...]] = {
    "langsmith": ("LANGSMITH_API_KEY",),
    "braintrust": ("BRAINTRUST_API_KEY", "braintrust:PROJECT/EXPERIMENT"),
    "weave": ("WANDB_API_KEY", "weave:ENTITY/PROJECT/EVALUATION"),
}


def test_tf24_60_the_reader_s_words_are_plain() -> None:
    """The three readers that pull, and the module that pulls for them."""
    from importlib import import_module

    from look_support import INTERNAL

    from poisson_trace.ingest import pulling as module

    texts = {"pulling": module.__doc__ or ""}
    for reader, named in DESCRIBED.items():
        read = import_module(f"poisson_trace.ingest.{reader}")
        texts[f"{reader}: description"], texts[reader] = read.DESCRIPTION, read.__doc__ or ""
        for word in named:
            assert word in read.DESCRIPTION, (reader, word)
    for label, text in texts.items():
        assert text.strip(), label
        assert not INTERNAL.search(text), (label, INTERNAL.search(text))
    assert "Weave" in texts["pulling"], "the pull's own words say what the Weave pull asks"
