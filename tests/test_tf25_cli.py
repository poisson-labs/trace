"""TF25-47 to TF25-60: the reader in the import's command line, its refusals, its detector, folders
of its files, and its place in the config, ``init`` and ``doctor`` (spec sections 3.3, 4.3, 4.4,
6.1, 6.3, 12, 17.4, 18.3.1; the shared core of INT1 to INT4; TF22's FI1 to FI7; TF17's entries;
the LangSmith pair's LS-24 and LS-28 to LS-30).

- TF25-47: the import's help lists ``braintrust``; the reader's help is the verb's under both
  spellings, with its flags, each saying what it is and its default; the module has the readers'
  shape, and its example runs as written on a committed capture of the example's extension.
- TF25-48: the summary is the import's: ``poisson-trace.import/1``, the files' digests, a
  ``next:`` fix check on ``--event missed``; its plain Next line carries the flags that read the
  other version the same way, and that line runs when its two capitals are filled in; it says
  when a try counts as failed. A name the store holds is refused and the store unchanged.
- TF25-49: a file that is missing, empty, not JSON, of another shape, another tool's, of another
  extension, or a CSV that is not the page's, is refused in one plain line naming it, exit 1,
  nothing written; a broken line of a JSON Lines file is named by its number.
- TF25-50: a wrong command line exits 2 in one line naming the flag: no ``--case-from``, no
  ``--outcome-from``, a value neither takes, a score with no cut or no side or both sides, a cut
  or ``--failed`` where none is read, a metadata outcome with neither, a ``--select`` that is not
  ``metadata:KEY=VALUE``, a cut that is not a number.
- TF25-51: both spellings of the import print the same bytes, done or refused.
- TF25-52: ``looks_like`` claims each answer of the API and each of the page's downloads with
  one line naming Braintrust, and no other file of the captures; no committed file of any tool
  is claimed by two readers; it never raises.
- TF25-53: a folder of a fetch's pages is one run, named after the folder, the same run its
  files give (with the tool named or not); a folder holding two versions' exports, or one
  experiment's page downloaded twice, is refused as more than one run, naming an import for
  each.
- TF25-54: the verbs read two folders of the reader's files with the reader's flags, and print
  what they print on the same folders imported one by one.
- TF25-55: ``--verdicts`` joins by case; a verdict that differs from what the file recorded is
  refused.
- TF25-56: ``init`` lists each export as Braintrust's and prints an import line for each;
  ``doctor`` lists ``braintrust`` among the readers.
- TF25-57: an ``[[import]]`` entry of ``tool = "braintrust"`` is read with its options by their
  flags' names and checked as the flags are; ``init`` imports a pending pair and ``doctor
  --setup`` reads them.
- TF25-58: an entry whose ``file`` is ``braintrust:PROJECT/EXPERIMENT`` is an address: accepted
  with ``tool = "braintrust"`` and refused under any other tool, as LangSmith's address is
  refused under this one; no verb, and neither ``doctor`` nor ``doctor --setup``, asks the
  service anything; ``doctor --setup`` says it is not pulled there and whether Braintrust's key
  is set; ``init`` pulls it into the imports' store, saving the raw copy. The addresses of the
  pullers this install still lacks stay refused.
- TF25-59: the readers' two sentences: ``runs`` shows an imported run's backend as
  ``import:braintrust`` and whether it has traces.
- TF25-60: the reader's module documents what it does not keep, in plain words.
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
from tf2_support import check, doctor_doc, init_yes, numbered, work, write_config
from tf17_support import config_text, import_entry, setup_check, trace_in, write_toml
from tf21_support import INGEST, run_import
from tf25_support import (
    API, BT, CASES, EXPERIMENTS, EXPORTS, KEY_VARIABLE, PAGED, PLANTED_KEY, PROJECT, UI, address, bt_argv, by_error,
    columns, export, imported, never, outcomes, pulling, raw_folder, recs, refused, rows_of, snapshot, tally, write_csv,
    wrong_line,
)

PRESENT = ("deepeval", "ragas", "table", "junit", "promptfoo", "inspect", "openai-evals", "langsmith", "braintrust")
FLAGS = ("--case-from", "--outcome-from", "--cut", "--below", "--above", "--failed", "--select", "--keep-raw-text", "--page-size")
OPTIONS = {"case_from": "input", "outcome_from": "score:exact", "cut": 0.5, "below": True}


# ---------- TF25-47 ----------


def test_tf25_47_the_import_s_help_lists_braintrust() -> None:
    helped = trace(["import", "--help"])
    assert helped.code == 0, helped.text
    for tool in PRESENT:
        assert re.search(rf"^ +{re.escape(tool)}(?: {{2,}}\S.*)?$", helped.out, re.M), (tool, helped.out)
    assert "poisson-trace import braintrust " in helped.out


def test_tf25_47_the_reader_s_help_is_the_verb_s_and_names_its_flags() -> None:
    a, b = trace(["import", "braintrust", "--help"]), trace_import(["braintrust", "--help"])
    assert a.code == b.code == 0 and a.out == b.out and a.err == b.err == "", a.text + b.text
    assert a.out.split("\n\n")[0].startswith("usage: poisson-trace import braintrust"), a.out
    for flag in ("--store", "--run", "--started", "--json", "--verdicts", *FLAGS):
        assert flag in a.out, flag
    for word in ("record", "metadata:KEY", "input", "none", "error", "score:KEY", "BRAINTRUST_API_KEY", "braintrust:PROJECT/EXPERIMENT"):
        assert word in a.out, word


def test_tf25_47_the_module_has_the_readers_shape() -> None:
    from poisson_trace.ingest import braintrust
    from poisson_trace.ingest.importing import READERS, present, pulls, reader_options

    # the readers through this one, in the import's order; a reader after it is its own pair's
    assert "braintrust" in READERS and present()[:len(PRESENT)] == PRESENT
    assert READERS.index("langsmith") < READERS.index("braintrust") < READERS.index("otel")
    for attr in ("add_arguments", "read", "usage", "looks_like", "DESCRIPTION", "EXAMPLE", "SHAPES", "ADDRESS"):
        assert hasattr(braintrust, attr), attr
    assert braintrust.EXAMPLE.startswith("poisson-trace import braintrust "), braintrust.EXAMPLE
    assert pulls("braintrust") == "braintrust:" and pulls("langsmith") == "langsmith:"
    options = reader_options("braintrust")
    assert options["case_from"].required and options["outcome_from"].required
    assert options["select"].many and options["failed"].many
    assert not options["below"].takes_value and not options["keep_raw_text"].takes_value
    for dest in ("cut", "below", "above", "failed", "select", "keep_raw_text", "page_size"):
        assert not options[dest].required, dest


def test_tf25_47_the_example_runs_as_written_on_a_capture_of_its_extension(tmp_path: Path) -> None:
    from poisson_trace.ingest import braintrust

    words = shell_words(braintrust.EXAMPLE)
    assert words[:3] == ["poisson-trace", "import", "braintrust"]
    files = [w for w in words[3:] if not w.startswith("-") and re.search(r"\.(json|jsonl|csv)$", w)]
    assert len(files) == 1, words
    suffix = Path(files[0]).suffix
    if suffix == ".jsonl":
        rows = rows_of(export("baseline", "fetch")[0])
        (tmp_path / files[0]).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    else:
        shutil.copy(export("baseline", "fetch" if suffix == ".json" else "ui-csv")[0], tmp_path / files[0])
    with chdir(tmp_path):
        ran = trace(words[1:])
    assert ran.code == 0 and ran.out.startswith("ok  wrote run "), ran.text


# ---------- TF25-48 ----------


@pytest.mark.parametrize("kind", EXPORTS)
def test_tf25_48_the_summary_is_the_import_s(tmp_path: Path, kind: str) -> None:
    data = imported(by_error(export("baseline", kind), tmp_path / "st", "first"))
    assert data["run"] == "first" and data["store"] == str(tmp_path / "st") and data["tool"] == "braintrust"
    assert data["next"].startswith("poisson-trace fix-check OLD NEW ") and "--event missed" in data["next"]
    assert data["declared"]["case_from"] == "input"
    text = run_import(bt_argv(export("baseline", kind), tmp_path / "st2", "first"))
    assert text.code == 0 and text.out.startswith("ok  wrote run first to "), text.out
    assert text.out.rstrip("\n").splitlines()[-1].startswith("next: poisson-trace fix-check OLD NEW"), text.out
    failed = next(line for line in text.out.splitlines() if line.startswith("- Failures: "))
    assert "exact" in failed and "0.5" in failed and "below" in failed and "3 failed and 6 passed" in failed, failed
    by = run_import(by_error(export("baseline", kind), tmp_path / "st3", "first"))
    failed = next(line for line in by.out.splitlines() if line.startswith("- Failures: "))
    assert "error" in failed and "1 failed and 9 passed" in failed, failed


@pytest.mark.parametrize("kind", ["fetch", "summary", "ui-json", "ui-csv"])
def test_tf25_48_the_next_line_reads_the_other_version_the_same_way(tmp_path: Path, kind: str) -> None:
    files = export("baseline", kind)
    text = run_import(bt_argv(files, tmp_path / "st", "old", "--select", "metadata:version=baseline"))
    assert text.code == 0, text.err
    line = next(line for line in text.out.splitlines() if line.startswith("- Next: "))
    command = re.search(r"`(poisson-trace import braintrust [^`]+)`", line)
    assert command, line
    words = shell_words(command.group(1))
    for flag, value in (("--case-from", "input"), ("--outcome-from", "score:exact"), ("--cut", "0.5")):
        assert words[words.index(flag) + 1] == value, words
    assert "--below" in words and words[words.index("--select") + 1] == "metadata:version=baseline"
    other = export("candidate", kind)[0]
    filled = [str(other) if w.startswith("OTHER.") else ("new" if w == "OTHER" else w) for w in words]
    filled[filled.index("metadata:version=baseline")] = "metadata:version=candidate"
    assert trace(filled[1:]).code == 0
    # the errored case holds no metadata, so the selection leaves it out of each version
    assert sorted(columns(tmp_path / "st", "new")) == [c for c in CASES if c != "c09"]


@pytest.mark.parametrize("kind", ["fetch", "ui-json"])
def test_tf25_48_a_name_in_use_is_refused_and_nothing_changes(tmp_path: Path, kind: str) -> None:
    imported(by_error(export("baseline", kind), tmp_path / "st", "first"))
    before = snapshot(tmp_path / "st")
    line = refused(run_import(by_error(export("candidate", kind), tmp_path / "st", "first")))
    assert "first" in line, line
    assert snapshot(tmp_path / "st") == before


# ---------- TF25-49 ----------


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def _dir(path: Path) -> Path:
    path.mkdir()
    return path


def _csv_without(tmp: Path, column: str) -> Path:
    return write_csv(tmp / "page.csv", export("baseline", "ui-csv")[0], header=lambda fields: [f for f in fields if f != column])


def _csv_bad_cell(tmp: Path) -> Path:
    def edit(rows: list[dict[str, str]]) -> None:
        rows[2]["metrics"] = "{not json"

    return write_csv(tmp / "cell.csv", export("baseline", "ui-csv")[0], edit)


LS = INGEST / "langsmith"
MALFORMED: dict[str, Any] = {
    "missing": lambda tmp: tmp / "gone.json",
    "empty": lambda tmp: _write(tmp / "e.json", b""),
    "an empty line file": lambda tmp: _write(tmp / "e.jsonl", b"\n\n"),
    "not JSON": lambda tmp: _write(tmp / "n.json", b'{"events": [1, 2'),
    "not text": lambda tmp: _write(tmp / "b.json", b"\xff\xfe\x00\x01"),
    "a JSON number": lambda tmp: _write(tmp / "num.json", b"42\n"),
    "a list of numbers": lambda tmp: _write(tmp / "l.json", b"[1, 2, 3]\n"),
    "an object with no events": lambda tmp: _write(tmp / "o.json", b'{"name": "x"}'),
    "events that are not objects": lambda tmp: _write(tmp / "ev.json", b'{"events": [1, 2]}'),
    "the experiments' listing": lambda tmp: _write(tmp / "experiments.json", (API / "experiments.json").read_bytes()),
    "the list of requests": lambda tmp: _write(tmp / "requests.json", (API / "requests.json").read_bytes()),
    "promptfoo's results": lambda tmp: _write(tmp / "pf.json", (INGEST / "promptfoo" / "results.json").read_bytes()),
    "an OpenAI Evals record": lambda tmp: _write(tmp / "oe.jsonl", (INGEST / "openai-evals" / "old.jsonl").read_bytes()),
    "a table": lambda tmp: _write(tmp / "table.csv", (INGEST / "table" / "humaneval-a.csv").read_bytes()),
    "LangSmith's CSV": lambda tmp: _write(tmp / "ls.csv", (LS / "ui" / "trace-fixture-baseline-bbb64b8e.csv").read_bytes()),
    "LangSmith's runs": lambda tmp: _write(tmp / "ls.json", (LS / "api" / "baseline.runs-v2.json").read_bytes()),
    "LangSmith's runs, a run a line": lambda tmp: _write(tmp / "ls.jsonl", (LS / "cli" / "baseline-runs.jsonl").read_bytes()),
    "a folder named as a file": lambda tmp: _dir(tmp / "folder.json"),
    "another extension": lambda tmp: _write(tmp / "events.txt", export("baseline", "fetch")[0].read_bytes()),
    "another extension, a row a line": lambda tmp: _write(tmp / "events.ndjson", b"".join(json.dumps(r).encode() + b"\n" for r in rows_of(export("baseline", "fetch")[0]))),
    "a CSV without its scores column": lambda tmp: _csv_without(tmp, "scores"),
    "a CSV without its metrics column": lambda tmp: _csv_without(tmp, "metrics"),
    "a CSV cell that is not JSON": _csv_bad_cell,
}


@pytest.mark.parametrize("label", list(MALFORMED))
def test_tf25_49_a_file_not_the_reader_s_is_refused_in_one_line_naming_it(tmp_path: Path, label: str) -> None:
    path = MALFORMED[label](tmp_path)
    result = run_import(by_error(path, tmp_path / "st", "v"))
    if label == "a folder named as a file":
        # a folder is the folder resolver's to refuse (TF22)
        assert result.code == 1 and result.out == "" and path.name in result.err, result.err
    else:
        line = refused(result)
        assert path.name in line, line
    assert "Traceback" not in result.err and len(result.err.splitlines()) <= 3, result.err
    assert not (tmp_path / "st").exists()


def test_tf25_49_a_broken_line_is_named_by_its_number(tmp_path: Path) -> None:
    lines = [json.dumps(r) for r in rows_of(export("baseline", "fetch")[0])]
    lines[6] = lines[6][:40]
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    line = refused(run_import(by_error(path, tmp_path / "st", "v")))
    assert "events.jsonl" in line and "line 7" in line, line
    lines[6] = "[1, 2]"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    line = refused(run_import(by_error(path, tmp_path / "st", "v")))
    assert "line 7" in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("kind", PAGED)
def test_tf25_49_an_empty_page_alone_is_no_run(tmp_path: Path, kind: str) -> None:
    line = refused(run_import(bt_argv(export("candidate", kind)[4], tmp_path / "st", "v")))
    assert "no row" in line or "no run" in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF25-50 ----------

FETCHED = export("baseline", "fetch")
USAGE: dict[str, Any] = {
    "no --case-from": (lambda root: bt_argv(FETCHED, root, "r", case=None), "--case-from"),
    "no --outcome-from": (lambda root: bt_argv(FETCHED, root, "r", outcome=None), "--outcome-from"),
    "a case that is none of the four": (lambda root: by_error(FETCHED, root, "r", case="row"), "--case-from"),
    "langsmith's word for the case": (lambda root: by_error(FETCHED, root, "r", case="example"), "--case-from"),
    "a case of metadata with no key": (lambda root: by_error(FETCHED, root, "r", case="metadata:"), "--case-from"),
    "an outcome that is none of the three": (lambda root: bt_argv(FETCHED, root, "r", outcome="score"), "--outcome-from"),
    "langsmith's word for the outcome": (lambda root: bt_argv(FETCHED, root, "r", outcome="status", cut=None), "--outcome-from"),
    "a score outcome with no key": (lambda root: bt_argv(FETCHED, root, "r", outcome="score:"), "--outcome-from"),
    "a score with no cut": (lambda root: bt_argv(FETCHED, root, "r", cut=None), "--cut"),
    "a cut with no side": (lambda root: bt_argv(FETCHED, root, "r", side=None), "--below"),
    "a cut with both sides": (lambda root: bt_argv(FETCHED, root, "r", "--above"), "--above"),
    "a side with no cut": (lambda root: bt_argv(FETCHED, root, "r", "--below", cut=None), "--cut"),
    "a cut with error": (lambda root: by_error(FETCHED, root, "r", "--cut", "0.5", "--below"), "--cut"),
    "failed values with error": (lambda root: by_error(FETCHED, root, "r", "--failed", "x"), "--failed"),
    "failed values with a score": (lambda root: bt_argv(FETCHED, root, "r", "--failed", "x"), "--failed"),
    "a metadata outcome with neither": (lambda root: bt_argv(FETCHED, root, "r", outcome="metadata:version", cut=None), "--failed"),
    "a metadata outcome with both": (lambda root: bt_argv(FETCHED, root, "r", "--failed", "x", outcome="metadata:version"), "--failed"),
    "a cut that is no number": (lambda root: bt_argv(FETCHED, root, "r", cut="high"), "--cut"),
    "a cut that is not a number at all": (lambda root: bt_argv(FETCHED, root, "r", cut="nan"), "--cut"),
    "a selection with no value": (lambda root: by_error(FETCHED, root, "r", "--select", "metadata:version"), "--select"),
    "a selection of another kind": (lambda root: by_error(FETCHED, root, "r", "--select", "tag:x=y"), "--select"),
    "no file": (lambda root: by_error([], root, "r"), "FILE"),
}


@pytest.mark.parametrize("label", list(USAGE))
def test_tf25_50_a_wrong_command_line_exits_2_naming_the_flag(tmp_path: Path, label: str) -> None:
    make, flag = USAGE[label]
    line = wrong_line(run_import(make(tmp_path / "st")))
    assert flag in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF25-51 ----------


@pytest.mark.parametrize("kind", ["fetch", "ui-csv"])
def test_tf25_51_both_spellings_print_the_same_bytes(tmp_path: Path, kind: str) -> None:
    outs = []
    for spelling in ("verb", "alias"):
        folder = tmp_path / spelling
        folder.mkdir()
        argv = by_error(export("candidate", kind), Path("st"), "first")
        with chdir(folder):
            ran = trace(["import", *argv]) if spelling == "verb" else trace_import(argv)
            again = trace(["import", *argv]) if spelling == "verb" else trace_import(argv)
        outs.append((ran.code, ran.out, ran.err, again.code, again.out, again.err))
        assert ran.code == 0 and again.code == 1, ran.text + again.text
    assert outs[0] == outs[1]


# ---------- TF25-52 ----------


def _claimed(path: Path) -> list[str]:
    from poisson_trace.ingest.importing import present, reader

    return [tool for tool in present() if reader(tool).looks_like(path) is not None]


def _ours() -> list[Path]:
    files = [p for name in EXPERIMENTS for kind in EXPORTS for p in export(name, kind)]
    files += [p for kind in PAGED for p in export("candidate", kind)[:4]]
    return files


def test_tf25_52_every_export_is_claimed_by_braintrust_alone_with_one_line() -> None:
    from poisson_trace.ingest import braintrust

    assert len(_ours()) == 4 * 6 + 8
    for path in _ours():
        said = braintrust.looks_like(path)
        assert isinstance(said, str) and said.strip() and "\n" not in said and "Braintrust" in said, (path.name, said)
        assert braintrust.looks_like(str(path)) == said
        assert _claimed(path) == ["braintrust"], (path.name, _claimed(path))


def test_tf25_52_the_other_files_of_the_capture_are_not_an_experiment_s() -> None:
    from poisson_trace.ingest import braintrust

    for name in ("requests.json", "experiments.json", "slice-candidate.fetch.page-5.json", "slice-candidate.btql-spans.page-5.json"):
        assert braintrust.looks_like(API / name) is None, name
    for name in ("fixture.eval.py", "slice.eval.py", "pull.py"):
        assert braintrust.looks_like(BT / name) is None, name
    assert sorted(p.name for p in UI.iterdir()) == sorted(p.name for p in _ours() if p.parent == UI)


def test_tf25_52_no_committed_file_is_claimed_by_two_readers() -> None:
    from poisson_trace.ingest import braintrust

    ours = {p.resolve() for p in _ours()}
    for path in sorted(p for p in INGEST.rglob("*") if p.is_file() and p.suffix in (".json", ".jsonl", ".gz", ".csv", ".xml", ".eval", ".tsv")):
        claimed = _claimed(path)
        assert len(claimed) <= 1, (str(path.relative_to(INGEST)), claimed)
        if path.resolve() not in ours:
            assert braintrust.looks_like(path) is None, str(path.relative_to(INGEST))


def test_tf25_52_looks_like_never_raises_and_claims_none_of_these(tmp_path: Path) -> None:
    from poisson_trace.ingest import braintrust

    (tmp_path / "folder.json").mkdir()
    for name, data in (("empty.json", b""), ("empty.jsonl", b""), ("empty.csv", b""), ("junk.json", b"\xff\xfe\x00"), ("list.json", b"[1, 2, 3]"),
                       ("number.jsonl", b"42\n"), ("spec.jsonl", b'{"spec": 1}\n'), ("half.json", b'{"events": [{"id": '),
                       ("header.csv", b"name,input\n"), ("events.json", b'{"events": []}'), ("data.json", b'{"data": [1]}'),
                       ("ids.json", b'[{"span_id": "a", "root_span_id": "a"}]'), ("row.json", b'[{"input": 1, "output": 2}]')):
        (tmp_path / name).write_bytes(data)
    shutil.copy(export("baseline", "fetch")[0], tmp_path / "events.txt")
    for path in [tmp_path / "missing.json", *sorted(tmp_path.iterdir())]:
        assert braintrust.looks_like(path) is None, path.name
        assert braintrust.looks_like(str(path)) is None, path.name


# ---------- TF25-53 ----------


def _pages(tmp: Path, name: str) -> Path:
    folder = tmp / name
    folder.mkdir()
    for path in export("candidate", "fetch-pages"):
        shutil.copy(path, folder / path.name)
    return folder


@pytest.mark.parametrize("named", [True, False])
def test_tf25_53_a_folder_of_a_fetch_s_pages_is_one_run(tmp_path: Path, named: bool) -> None:
    folder = _pages(tmp_path, "new-pages")
    (folder / ".DS_Store").write_bytes(b"x")
    (folder / "README.md").write_text("notes", encoding="utf-8")
    flags = ["--case-from", "input", "--outcome-from", "error", "--json"]
    argv = [*(["braintrust"] if named else []), str(folder), "--store", str(tmp_path / "st"), *flags]
    result = run_import(argv)
    assert result.code == 0, result.err
    data = json.loads(result.out)
    assert data["run"] == "new-pages" and data["tool"] == "braintrust" and data["rows"] == 10
    # the empty last page is no export on its own, and a folder leaves it out
    pages = export("candidate", "fetch-pages")[:4]
    assert [f["name"] for f in data["files"]] == sorted(p.name for p in pages)
    files = imported(by_error(pages, tmp_path / "files", "new-pages"))
    assert recs(tmp_path / "st", "new-pages") == recs(tmp_path / "files", "new-pages")
    for key in ("rows", "cases", "outcomes", "counts", "started", "declared", "files"):
        assert data[key] == files[key], key
    assert len(list(folder.iterdir())) == 7


@pytest.mark.parametrize(("held", "names"), [
    ((("baseline", "fetch"), ("candidate", "fetch")), ("slice-baseline.fetch.json", "slice-candidate.fetch.json")),
    ((("baseline", "summary"), ("candidate", "summary")), ("slice-baseline.btql-summary.json", "slice-candidate.btql-summary.json")),
])
def test_tf25_53_a_folder_of_more_than_one_run_is_refused_naming_an_import_for_each(tmp_path: Path, held: Any, names: tuple[str, str]) -> None:
    folder = tmp_path / "both"
    folder.mkdir()
    for name, kind in held:
        shutil.copy(export(name, kind)[0], folder)
    result = run_import(by_error(folder, tmp_path / "st", None))
    line = refused(result)
    assert "more than one run" in line and names[0] in line and names[1] in line, line
    nexts = [shell_words(following[len("  next: "):]) for following in result.err.splitlines()[1:]]
    assert len(nexts) == 2 and all(w[:3] == ["poisson-trace", "import", "braintrust"] for w in nexts), result.err
    assert all("--case-from" in w and "--outcome-from" in w for w in nexts), nexts
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("held", [(("baseline", "ui-json"), ("baseline", "ui-csv")), (("baseline", "ui-json"), ("candidate", "ui-json"))])
def test_tf25_53_a_folder_of_two_of_the_page_s_downloads_is_refused_naming_both(tmp_path: Path, held: Any) -> None:
    """One experiment's page downloaded twice, or two experiments' pages: with no id in the
    files they cannot be told apart, so the folder is refused as two given files are."""
    folder = tmp_path / "both"
    folder.mkdir()
    names = []
    for name, kind in held:
        shutil.copy(export(name, kind)[0], folder)
        names.append(export(name, kind)[0].name)
    line = refused(run_import(by_error(folder, tmp_path / "st", None)))
    assert all(name in line for name in names) and "one file" in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF25-54 ----------

READER = ["--case-from", "input", "--outcome-from", "error"]
VERBS = {
    "fix-check": lambda a, b: ["fix-check", a, b, "--event", "missed", "--inputs", "all", "--max-mde", "0.2"],
    "compare": lambda a, b: ["compare", a, b, "--event", "missed", "--max-mde-hr", "1.5"],
    "changes": lambda a, b: ["changes", a, b, "--event", "missed"],
    "where": lambda a, b: ["where", a, "--event", "missed"],
}


def _folders(tmp: Path, kind: str) -> tuple[Path, Path]:
    made = []
    for version, name in (("baseline", "old-export"), ("candidate", "new-export")):
        folder = tmp / name
        folder.mkdir()
        shutil.copy(export(version, kind)[0], folder)
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
@pytest.mark.parametrize("kind", ["fetch", "ui-json"])
def test_tf25_54_the_verbs_read_two_folders_of_the_reader_s_files(tmp_path: Path, verb: str, kind: str) -> None:
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


def test_tf25_54_a_verb_on_folders_without_the_reader_s_flags_exits_2(tmp_path: Path) -> None:
    _folders(tmp_path, "fetch")
    with chdir(tmp_path):
        ran = trace(["fix-check", "old-export", "new-export", "--event", "missed", "--inputs", "all", "--max-mde", "0.2"])
    assert ran.code == 2 and "--case-from" in ran.err, ran.text


# ---------- TF25-55 ----------


@pytest.mark.parametrize("kind", ["fetch", "summary"])
def test_tf25_55_a_verdicts_file_joins_by_case_and_cannot_overturn_the_file(tmp_path: Path, kind: str) -> None:
    verdicts = tmp_path / "v.csv"
    # the errored case has no score and is censored, which is the file's own word: a verdict
    # fills what a file left out and never overturns what it recorded (TF22)
    verdicts.write_text("case,outcome\nc08,fail\n", encoding="utf-8")
    line = refused(run_import(bt_argv(export("baseline", kind), tmp_path / "st", "r", "--verdicts", verdicts, case="record")))
    assert "c08" in line and "censored" in line, line
    # a verdict that agrees with the file joins and changes nothing
    verdicts.write_text("case,outcome,failure_kind\nc10,fail,abstained\nc01,pass,\n", encoding="utf-8")
    data = imported(bt_argv(export("baseline", kind), tmp_path / "st", "r", "--verdicts", verdicts, case="record"))
    assert data["verdicts"]["by_case"] == 2 and data["verdicts"]["unmatched"] == 0, data["verdicts"]
    assert tally(data) == {"met": 6, "missed": 3} and data["no_outcome"] == {"no score": 1}
    assert recs(tmp_path / "st", "r")["c10"]["failure_kind"] == "abstained"


def test_tf25_55_a_verdict_that_differs_from_the_file_is_refused(tmp_path: Path) -> None:
    verdicts = tmp_path / "v.csv"
    verdicts.write_text("case,outcome\nc01,fail\n", encoding="utf-8")
    line = refused(run_import(bt_argv(export("baseline", "fetch"), tmp_path / "st", "r", "--verdicts", verdicts, case="record")))
    assert "c01" in line, line
    assert not (tmp_path / "st").exists()


# ---------- TF25-56 ----------

LISTED = {"fetch": "old.json", "summary": "new-summary.json", "ui-json": "new-page.json", "ui-csv": "old-page.csv"}


def test_tf25_56_init_lists_the_exports_and_prints_a_line_for_each(tmp_path: Path) -> None:
    folder = work(tmp_path)
    (folder / "results").mkdir()
    for kind, name in LISTED.items():
        version = "baseline" if name.startswith("old") else "candidate"
        shutil.copy(export(version, kind)[0], folder / "results" / name)
    result = init_yes(folder, "--no-import")
    assert result.code == 0, result.text
    listed = {line.split()[0]: line for line in numbered(result.err).values()}
    assert sorted(listed) == sorted(f"results/{name}" for name in LISTED.values()), result.err
    assert all("Braintrust" in line for line in listed.values()), listed
    lines = [shell_words(line.strip()) for line in result.out.splitlines() if line.strip().startswith("poisson-trace import ")]
    for name in LISTED.values():
        words = next(w for w in lines if f"results/{name}" in w)
        assert words[:4] == ["poisson-trace", "import", "braintrust", f"results/{name}"], words
        assert words[4:6] == ["--store", "trace-store"] and words[6] == "--run" and words[7], words
    assert not (folder / "trace-store").exists()


def test_tf25_56_doctor_lists_braintrust_among_the_readers(tmp_path: Path) -> None:
    folder = work(tmp_path)
    write_config(folder, "version = 1\n")
    _, data = doctor_doc(folder)
    line = check(data, "readers")["line"]
    for tool in PRESENT:
        assert tool in line, line
    for absent in ("otel", "lemma"):
        assert absent not in line, line


# ---------- TF25-57 ----------


def _pair_config(folder: Path, *, store: str | None = None) -> str:
    (folder / "exports").mkdir(exist_ok=True)
    blocks = []
    for version, run in (("baseline", "old"), ("candidate", "new")):
        shutil.copy(export(version, "fetch")[0], folder / "exports" / f"{run}.json")
        blocks.append(import_entry(f"exports/{run}.json", "braintrust", run, **OPTIONS))
    return config_text(*blocks, store=store, events=("missed",))


def test_tf25_57_an_entry_reads_with_its_options_by_their_flags_names(tmp_path: Path) -> None:
    from poisson_trace import config

    folder = work(tmp_path)
    text = config_text(import_entry("exports/old.json", "braintrust", "old", case_from="record", outcome_from="metadata:version",
                                    failed=["baseline"], select=["metadata:model=gpt-4.1-mini"]), store="s")
    held = config.parse(text, folder / "trace.toml", "trace.toml", given=False)
    entry = held.imports[0]
    assert (entry.tool, entry.name, entry.file) == ("braintrust", "old", "exports/old.json")
    assert dict(entry.options) == {"case_from": "record", "outcome_from": "metadata:version", "failed": ["baseline"], "select": ["metadata:model=gpt-4.1-mini"]}


@pytest.mark.parametrize(("options", "said"), [
    ({"outcome_from": "error"}, "case_from"),
    ({"case_from": "record"}, "outcome_from"),
    ({"case_from": "record", "outcome_from": "error", "cutt": 0.5}, "cutt"),
    ({"case_from": "record", "outcome_from": "error", "select": "metadata:a=b"}, "select"),
    ({"case_from": "record", "outcome_from": "error", "below": "yes"}, "below"),
])
def test_tf25_57_an_entry_s_options_are_checked_as_the_flags_are(tmp_path: Path, options: dict[str, Any], said: str) -> None:
    from poisson_trace import config

    folder = work(tmp_path)
    text = config_text(import_entry("exports/old.json", "braintrust", "old", **options), store="s")
    with pytest.raises(config.ConfigError) as caught:
        config.parse(text, folder / "trace.toml", "trace.toml", given=False)
    assert said in str(caught.value) and "line " in str(caught.value), str(caught.value)


def test_tf25_57_doctor_setup_reads_a_pending_pair_and_init_imports_it(tmp_path: Path) -> None:
    folder = work(tmp_path)
    write_toml(folder, _pair_config(folder))
    with pulling(never(), key=None):
        checked = setup_check(folder, "--json")
        assert checked.code == 0, checked.text
        lines = [c["line"] for c in checked.json()["checks"] if c["name"] == "import"]
        assert len(lines) == 2 and all("braintrust, 10 rows" in line and "not imported yet" in line for line in lines), lines
        assert not (folder / "trace-store").exists()
        done = init_yes(folder, "--import")
        assert done.code == 0, done.text
    old = outcomes(folder / "trace-store", "old")
    assert sum(1 for o in old.values() if o == "met") == 6 and sum(1 for o in old.values() if o == "missed") == 3
    assert sorted(columns(folder / "trace-store", "new")) == sorted(old) == list(CASES)
    ran = trace_in(folder, ["fix-check", "old", "new", "--store", "trace-store", "--event", "missed", "--inputs", "all", "--max-mde", "0.2"])
    assert ran.code == 0, ran.text


def test_tf25_57_an_entry_whose_file_is_not_braintrust_s_fails_the_setup_check(tmp_path: Path) -> None:
    folder = work(tmp_path)
    (folder / "exports").mkdir()
    shutil.copy(INGEST / "promptfoo" / "results.json", folder / "exports" / "old.json")
    write_toml(folder, config_text(import_entry("exports/old.json", "braintrust", "old", **OPTIONS), store=None, events=("missed",)))
    checked = setup_check(folder, "--json")
    assert checked.code != 0, checked.text
    assert "exports/old.json" in checked.text


# ---------- TF25-58 ----------

LS_OPTIONS = {"case_from": "example", "outcome_from": "status"}
LS_ADDRESS = "langsmith:trace-fixture-baseline-bbb64b8e"


def _address_config(version: str = "baseline", name: str = "old", **changes: Any) -> str:
    options = {**OPTIONS, **changes}
    return config_text(import_entry(address(version), "braintrust", name, **options), store=None, events=("missed",))


def test_tf25_58_an_address_is_an_entry_of_the_braintrust_reader(tmp_path: Path) -> None:
    from poisson_trace import config

    folder = work(tmp_path)
    held = config.parse(_address_config(), folder / "trace.toml", "trace.toml", given=False)
    assert held.imports[0].file == address("baseline") and held.imports[0].tool == "braintrust"
    for tool, options in (("table", {"case_column": "c", "outcome_column": "o", "failed": ["x"]}), ("junit", {}), ("langsmith", LS_OPTIONS)):
        text = config_text(import_entry(address("baseline"), tool, "pulled", **options), store="s")
        with pytest.raises(config.ConfigError) as caught:
            config.parse(text, folder / "trace.toml", "trace.toml", given=False)
        said = str(caught.value)
        assert address("baseline") in said and "braintrust" in said and "line " in said, said
    # LangSmith's address under this reader is refused the same way, naming its own reader
    text = config_text(import_entry(LS_ADDRESS, "braintrust", "pulled", **OPTIONS), store="s")
    with pytest.raises(config.ConfigError) as caught:
        config.parse(text, folder / "trace.toml", "trace.toml", given=False)
    assert LS_ADDRESS in str(caught.value) and "langsmith" in str(caught.value), str(caught.value)
    # a file whose name starts the same way and is no address stays a file
    held = config.parse(config_text(import_entry("braintrust/old.json", "braintrust", "old", **OPTIONS), store="s"), folder / "trace.toml", "trace.toml", given=False)
    assert held.imports[0].file == "braintrust/old.json"


@pytest.mark.parametrize("puller", ["lemma"])
def test_tf25_58_the_addresses_of_the_pullers_this_install_lacks_stay_refused(tmp_path: Path, puller: str) -> None:
    from poisson_trace import config

    folder = work(tmp_path)
    text = config_text(import_entry(f"{puller}:some/name", "table", "pulled", case_column="c", outcome_column="o", failed=["x"]), store="s")
    with pytest.raises(config.ConfigError) as caught:
        config.parse(text, folder / "trace.toml", "trace.toml", given=False)
    assert puller in str(caught.value) and "not in this install" in str(caught.value), str(caught.value)


def test_tf25_58_no_verb_and_no_doctor_asks_the_service_anything(tmp_path: Path) -> None:
    from tf17_support import CS

    folder = work(tmp_path)
    shutil.copytree(CS, folder / "store")
    text = config_text(import_entry(address("baseline"), "braintrust", "old", **OPTIONS), store="store")
    write_toml(folder, text)
    with pulling(never()) as (_, _waits):
        assert trace_in(folder, ["runs"]).code == 0
        assert trace_in(folder, ["doctor"]).code in (0, 4)
        ready = setup_check(folder, "--json")
        line = next(c for c in ready.json()["checks"] if c["name"] == "import")
        assert line["ok"] is True and address("baseline") in line["line"] and "not pulled" in line["line"], line
        assert KEY_VARIABLE in line["line"] and "LANGSMITH_API_KEY" not in line["line"] and PLANTED_KEY not in ready.text
    with pulling(never(), key=None) as (_, _waits):
        import os

        # LangSmith's key being set says nothing of Braintrust's
        os.environ["LANGSMITH_API_KEY"] = "lsv2_pt_another_key_entirely_0000"
        unready = setup_check(folder, "--json")
        line = next(c for c in unready.json()["checks"] if c["name"] == "import")
        assert line["ok"] is False and KEY_VARIABLE in line["line"], line
        assert unready.code != 0 and "lsv2_pt" not in unready.text
    assert not (folder / "trace-store").exists() and not (folder / "store" / ".poisson" / "raw").exists()


def test_tf25_58_init_pulls_a_pending_address_into_the_imports_store(tmp_path: Path) -> None:
    from tf25_support import FETCH, LISTING

    folder = work(tmp_path)
    write_toml(folder, config_text(
        import_entry(address("baseline"), "braintrust", "old", **OPTIONS),
        import_entry(address("candidate"), "braintrust", "new", **OPTIONS), store=None, events=("missed",)))
    with pulling() as (sent, _):
        done = init_yes(folder, "--import")
        assert done.code == 0, done.text
        assert sent.paths() == [LISTING, FETCH, FETCH] * 2
    store = folder / "trace-store"
    for run in ("old", "new"):
        assert sorted(p.name for p in raw_folder(store, run).iterdir()) == ["pull.json", "raw.jsonl"]
        assert sorted(columns(store, run)) == list(CASES)
    assert f"{PROJECT}/slice-baseline" in (raw_folder(store, "old") / "pull.json").read_text(encoding="utf-8")
    assert PLANTED_KEY not in done.text
    with pulling(never(), key=None):
        again = setup_check(folder)
        assert again.code == 0, again.text


def test_tf25_58_init_without_the_key_refuses_and_writes_no_run(tmp_path: Path) -> None:
    folder = work(tmp_path)
    write_toml(folder, _address_config())
    with pulling(never(), key=None):
        done = init_yes(folder, "--import")
    assert done.code == 1 and KEY_VARIABLE in done.err, done.text
    assert not (folder / "trace-store" / "old").exists()


# ---------- TF25-59 ----------


@pytest.mark.parametrize(("kind", "traces"), [("fetch", "yes"), ("summary", "no"), ("ui-csv", "no")])
def test_tf25_59_runs_says_where_the_run_came_from_and_whether_it_has_traces(tmp_path: Path, kind: str, traces: str) -> None:
    imported(by_error(export("baseline", kind), tmp_path / "st", "old"))
    ran = trace(["runs", "--store", str(tmp_path / "st"), "--json"])
    assert ran.code == 0, ran.err
    row = json.loads(ran.out)["runs"][0]
    assert row["traced"] is (traces == "yes") and row["backend"] == "import:braintrust", row


# ---------- TF25-60 ----------


def test_tf25_60_the_reader_s_words_are_plain() -> None:
    from tf0_support import INTERNAL

    from poisson_trace.ingest import braintrust, pulling as module

    for text in (braintrust.DESCRIPTION, braintrust.__doc__ or "", module.__doc__ or ""):
        assert text.strip()
        assert not INTERNAL.search(text), INTERNAL.search(text)
    assert "BRAINTRUST_API_KEY" in braintrust.DESCRIPTION and "braintrust:PROJECT/EXPERIMENT" in braintrust.DESCRIPTION
