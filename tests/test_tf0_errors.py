"""TF0-5 to TF0-10: problems go to stderr, one line each, and every path that ended in a traceback
is closed (rules 4 and 6 of ``docs/cli-look.md``, its exit-code table, and the install line).

A refusal is ``error: <sentence>`` on stderr, two-space continuations only, nothing on stdout,
exit 1. A store that is not there says so instead of reading as an unknown run. ``--svg`` refuses
a folder that is not there and a file that is, and says what it wrote. An unexpected failure is
one line naming the log the details went to, exit 3. Ctrl-C is ``stopped  …`` and exit 130. A
library's own exception text never reaches the user. The Prove check runs after the command line
is read. No message words are matched: lines are told apart by their shape, by the facts they
name (a path, a run, a version) and by sentinels that must not leak.

Where a test makes a failure happen, it does so at a seam the code reads at call time: Prove's
``Store`` methods (``runs`` is how a store's runs are listed, outside any refusal; ``read``,
``manifest``, ``create_run`` and ``append`` as today), and a reader module's ``read(ns)``, which
the import calls by module attribute (the reader contract in ``ingest/cli.py``). Prove's presence
and version are read from the imported ``poisson_prove`` module, as the check does today and as
TR31 and TR41 already pin; the wrong-version line names the version found, as TR31 pins. No
progress lines are printed off a terminal, so stderr is empty on success."""

from __future__ import annotations

import csv
import dataclasses
import io
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from poisson_prove.store import Store

from conftest import CS, CS_RECORD, TAU2
from tf0_support import (
    COMMANDS, INSTALL_PROVE, PLACEHOLDER_INSTALL, REPR, VERDICT_LINE, Ran, changes_he, compare_tau2,
    deepeval_import, fix_check_tau2, ragas_import, run_sub,
    trace, trace_import, where_cs,
)

SENTINEL = "zq-sentinel-7f3e"

def _one_error(result: Ran, code: int = 1) -> str:
    """Exit ``code``, nothing on stdout, one ``error:`` line and at most ``  next:`` lines under
    it (rule 4); the error line."""
    assert result.code == code, result.text
    assert result.out == "", result.out
    lines = result.lines()
    assert lines and lines[0].startswith("error: "), result.err
    assert all(line.startswith("  next: ") for line in lines[1:]), result.err
    return lines[0]


# ---------- TF0-5: no store at ----------


def _store_argv(verb: str, store: str) -> list[str]:
    return {
        "where": ["where", "run-one", "--store", store, "--event", "unsolved"],
        "compare": ["compare", "run-one", "run-two", "--store", store, "--event", "unsolved", "--max-mde-hr", "1.5"],
        "fix-check": ["fix-check", "run-one", "run-two", "--store", store, "--event", "unsolved", "--inputs", "all", "--max-mde", "0.2"],
        "changes": ["changes", "run-one", "run-two", "--store", store, "--event", "unsolved"],
    }[verb]


@pytest.mark.parametrize("verb", ["where", "compare", "fix-check", "changes"])
@pytest.mark.parametrize("what", ["not there", "an empty folder", "a file"])
def test_tf0_05_a_store_that_is_not_there_is_named_as_such(tmp_path: Path, verb: str, what: str) -> None:
    path = tmp_path / "nowhere-store"
    if what == "an empty folder":
        path.mkdir()
    elif what == "a file":
        path.write_text("text\n")
    line = _one_error(trace(_store_argv(verb, str(path))))
    assert str(path) in line, line
    assert "run-one" not in line and "run-two" not in line, line


def test_tf0_05_a_store_that_holds_runs_still_names_the_run_it_lacks() -> None:
    """The control: the store is there, so the refusal is about the run."""
    line = _one_error(trace(["where", "run-one", "--store", str(TAU2), "--event", "unsolved"]))
    assert "run-one" in line, line


# ---------- TF0-6: --svg ----------


def _wrote(out: str, path: Path) -> list[str]:
    return [line for line in out.splitlines() if line == f"  wrote  {path}"]


def test_tf0_06_an_svg_into_a_folder_that_is_not_there_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "no-such-dir" / "curve.svg"
    line = _one_error(trace(where_cs("--svg", str(target))))
    assert str(target) in line, line
    assert not target.parent.exists()


@pytest.mark.parametrize("force", [False, True], ids=["without --force", "with --force"])
def test_tf0_06_an_svg_onto_a_folder_is_refused(tmp_path: Path, force: bool) -> None:
    target = tmp_path / "a-folder"
    target.mkdir()
    _one_error(trace(where_cs("--svg", str(target), *(["--force"] if force else []))))
    assert list(target.iterdir()) == []


@pytest.mark.skipif(os.geteuid() == 0, reason="a folder is never read-only to root")
def test_tf0_06_an_svg_into_a_folder_that_cannot_be_written_is_refused(tmp_path: Path) -> None:
    folder = tmp_path / "read-only"
    folder.mkdir()
    folder.chmod(0o500)
    try:
        result = trace(where_cs("--svg", str(folder / "curve.svg")))
    finally:
        folder.chmod(0o700)
    assert "Traceback" not in result.text and result.code == 1 and result.out == "", result.text
    lines = result.lines()
    assert lines and lines[0].startswith("error: ") and str(folder / "curve.svg") in lines[0], result.err
    assert list(folder.iterdir()) == []


def test_tf0_06_an_svg_over_a_file_is_refused_without_force_and_the_file_is_untouched(tmp_path: Path) -> None:
    target = tmp_path / "curve.svg"
    target.write_text("<svg>mine</svg>\n")
    before = (target.read_bytes(), target.stat().st_mtime_ns)
    line = _one_error(trace(where_cs("--svg", str(target))))
    assert str(target) in line, line
    assert (target.read_bytes(), target.stat().st_mtime_ns) == before


def test_tf0_06_force_replaces_the_svg_and_says_what_it_wrote(tmp_path: Path) -> None:
    fresh, target = tmp_path / "fresh.svg", tmp_path / "curve.svg"
    target.write_text("<svg>mine</svg>\n")
    plain = trace(where_cs())
    new = trace(where_cs("--svg", str(fresh)))
    forced = trace(where_cs("--svg", str(target), "--force"))
    for result, path in ((new, fresh), (forced, target)):
        assert result.code == 0 and result.err == "", result.text
        assert len(_wrote(result.out, path)) == 1, result.out
        rest = "\n".join(line for line in result.out.splitlines() if line != f"  wrote  {path}")
        assert rest == "\n".join(plain.out.splitlines()), "the report is the one printed without --svg"
    assert target.read_bytes() == fresh.read_bytes() and fresh.read_bytes().lstrip().startswith(b"<svg")


def test_tf0_06_svg_with_json_leaves_stdout_one_document(tmp_path: Path) -> None:
    target = tmp_path / "curve.svg"
    with_svg = trace(where_cs("--svg", str(target), "--json"))
    alone = trace(where_cs("--json"))
    assert with_svg.code == 0, with_svg.text
    assert with_svg.json() == alone.json()
    assert target.read_bytes().lstrip().startswith(b"<svg")


# ---------- TF0-7: an unexpected failure ----------


def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    return home / ".cache" / "poisson-trace" / "errors.log"


def _boom(*args: object, **kwargs: object) -> None:
    raise RuntimeError(SENTINEL)


def _names_the_log(line: str, log: Path) -> bool:
    return str(log) in line or "~/.cache/poisson-trace/errors.log" in line


def test_tf0_07_an_unexpected_failure_is_one_line_and_the_details_go_to_the_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = _home(tmp_path, monkeypatch)
    monkeypatch.setattr(Store, "runs", _boom)
    first = trace(where_cs())
    line = _one_error(first, 3)
    assert _names_the_log(line, log) and "RuntimeError" in line, line
    assert SENTINEL not in first.err and "Traceback" not in first.err
    written = log.read_text()
    assert "Traceback" in written and SENTINEL in written
    second = trace(compare_tau2("1.5"))
    assert second.code == 3, second.text
    again = log.read_text()
    assert again.startswith(written) and again.count(SENTINEL) == 2 * written.count(SENTINEL), "appended, not replaced"


def test_tf0_07_an_unexpected_failure_in_the_import_goes_to_the_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import poisson_trace.ingest.deepeval as reader

    log = _home(tmp_path, monkeypatch)
    monkeypatch.setattr(reader, "read", _boom)
    store = tmp_path / "store"
    result = trace_import(deepeval_import(store, "v1"))
    line = _one_error(result, 3)
    assert _names_the_log(line, log) and SENTINEL not in result.err, line
    debug = trace_import([*deepeval_import(store, "v1"), "--debug"])
    assert debug.code == 3 and "Traceback" in debug.err and SENTINEL in debug.err, debug.text
    assert SENTINEL in log.read_text()
    assert not store.exists() or Store(store).runs() == []


@pytest.mark.parametrize("where", ["before the verb", "after the verb"])
def test_tf0_07_debug_prints_the_details_too(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, where: str) -> None:
    log = _home(tmp_path, monkeypatch)
    monkeypatch.setattr(Store, "runs", _boom)
    argv = ["--debug", *where_cs()] if where == "before the verb" else [*where_cs(), "--debug"]
    result = trace(argv)
    assert result.code == 3, result.text
    assert result.err.startswith("error: ") and "Traceback" in result.err and SENTINEL in result.err
    assert SENTINEL in log.read_text()


# ---------- TF0-8: Ctrl-C ----------


def _stop(*args: object, **kwargs: object) -> None:
    raise KeyboardInterrupt


@pytest.mark.parametrize(
    "argv", [where_cs(), compare_tau2("1.5"), fix_check_tau2(), changes_he()], ids=["where", "compare", "fix-check", "changes"]
)
def test_tf0_08_ctrl_c_stops_a_verb_that_reads(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> None:
    monkeypatch.setattr(Store, "read", _stop)
    result = trace(argv)
    assert result.code == 130, result.text
    out = result.lines("out")
    assert out and out[0].startswith("stopped  ") and VERDICT_LINE.match(out[0]), result.out
    assert not any(line.startswith("#") for line in out), "no part of a report"
    assert "Traceback" not in result.text and "KeyboardInterrupt" not in result.text


def test_tf0_08_ctrl_c_before_an_import_writes_leaves_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import poisson_trace.ingest.deepeval as reader

    monkeypatch.setattr(reader, "read", _stop)
    store = tmp_path / "store"
    result = trace_import(deepeval_import(store, "v1"))
    assert result.code == 130, result.text
    assert result.lines("out")[0].startswith("stopped  "), result.out
    assert "Traceback" not in result.text
    assert not store.exists() or Store(store).runs() == []


def test_tf0_08_ctrl_c_while_an_import_writes_leaves_the_run_partial_and_named(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = tmp_path / "store"
    with monkeypatch.context() as patched:
        patched.setattr(Store, "append", _stop)
        result = trace_import(deepeval_import(store, "v1"))
    assert result.code == 130, result.text
    first = result.lines("out")[0]
    assert first.startswith("stopped  ") and "v1" in first and str(store) in first, result.out
    assert "Traceback" not in result.text
    held = Store(store)
    assert "v1" in held.runs() and held.manifest("v1").status != "complete"
    # the next import of that name is refused, and adds nothing to the partial run
    again = trace_import(deepeval_import(store, "v1"))
    _one_error(again)
    assert Store(store).manifest("v1").status != "complete"


# ---------- TF0-9: a library's own text never reaches the user ----------


@pytest.mark.parametrize("argv", [where_cs(), fix_check_tau2()], ids=["where", "fix-check"])
def test_tf0_09_a_run_prove_cannot_read_is_refused_in_trace_words(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise ValueError(SENTINEL)

    monkeypatch.setattr(Store, "read", broken)
    line = _one_error(trace(argv))
    assert SENTINEL not in line and not REPR.search(line), line
    assert argv[1] in line, "the line names the run"


def test_tf0_09_an_unreadable_start_time_is_refused_in_trace_words(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = "the ninth of May"
    try:
        datetime.fromisoformat(bad)
    except ValueError as e:
        library = str(e)
    real = Store.manifest

    def manifest(self: Store, run_id: str) -> object:
        return dataclasses.replace(real(self, run_id), created_at=bad)

    monkeypatch.setattr(Store, "manifest", manifest)
    line = _one_error(trace(fix_check_tau2()))
    assert library not in line and not REPR.search(line), line


@pytest.mark.parametrize("method", ["create_run", "append"])
def test_tf0_09_a_store_prove_cannot_write_is_refused_in_trace_words(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, method: str) -> None:
    store = tmp_path / "store"
    with monkeypatch.context() as patched:
        patched.setattr(Store, method, _boom)
        line = _one_error(trace_import(deepeval_import(store, "v1")))
    assert SENTINEL not in line and not REPR.search(line), line
    assert not store.exists() or Store(store).runs() == []


def test_tf0_09_a_csv_the_csv_reader_rejects_is_refused_in_trace_words(tmp_path: Path) -> None:
    body = 'case,faithfulness\n"a"x,0.5\n'
    try:
        list(csv.reader(io.StringIO(body, newline=""), strict=True))
    except csv.Error as e:
        library = str(e)
    table = tmp_path / "scores.csv"
    table.write_text(body)
    argv = ["ragas", str(table), "--store", str(tmp_path / "store"), "--run", "v1", "--metric", "faithfulness", "--cut", "0.5", "--below", "--case-column", "case"]
    line = _one_error(trace_import(argv))
    assert library not in line and not REPR.search(line), line
    assert str(table) in line


# ---------- TF0-10: the Prove check after the command line ----------


HELPS = {
    "trace": [["--help"], ["where", "--help"], ["compare", "--help"], ["fix-check", "--help"], ["changes", "--help"], ["--version"]],
    "import": [["--help"], ["deepeval", "--help"], ["ragas", "--help"], ["--version"]],
}


# Every help and version in one interpreter where Prove cannot be imported: each command's
# ``main`` is called in turn, its streams and exit code kept apart, a failure of one kept to it.
_WITHOUT_PROVE = """
import contextlib, io, json, sys, traceback
from importlib import import_module
sys.modules['poisson_prove'] = None
results = []
for module, argv in json.loads(sys.argv[1]):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = import_module(module).main(argv)
        except SystemExit as e:
            code = e.code
        except BaseException:
            code = -1
            traceback.print_exc()
    results.append([0 if code is None else code, out.getvalue(), err.getvalue()])
print(json.dumps(results))
"""
HELP_CASES = [(c, a) for c, argvs in HELPS.items() for a in argvs]


@pytest.fixture(scope="module")
def without_prove() -> dict[tuple[str, tuple[str, ...]], Ran]:
    """What each help and version gives where Prove is absent, by command and argv."""
    asked = [[COMMANDS[c], a] for c, a in HELP_CASES]
    proc = subprocess.run([sys.executable, "-c", _WITHOUT_PROVE, json.dumps(asked)], capture_output=True, timeout=300)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    results = json.loads(proc.stdout.decode("utf-8"))
    return {(c, tuple(a)): Ran(code, out, err) for (c, a), (code, out, err) in zip(HELP_CASES, results, strict=True)}


@pytest.mark.parametrize("command,argv", HELP_CASES, ids=[f"{c} {' '.join(a)}" for c, a in HELP_CASES])
def test_tf0_10_help_and_version_work_without_prove(without_prove: dict[tuple[str, tuple[str, ...]], Ran], command: str, argv: list[str]) -> None:
    result = without_prove[command, tuple(argv)]
    assert result.code == 0, result.text
    assert result.out.strip() and result.err == "", result.text


def test_tf0_10_a_wrong_command_line_without_prove_is_a_usage_error(tmp_path: Path) -> None:
    trace_usage = run_sub("trace", where_cs("--bogus"), prove="absent")
    full = deepeval_import(tmp_path / "store", "v1")
    import_usage = run_sub("import", full[: full.index("--case")], prove="absent")
    for result in (trace_usage, import_usage):
        assert result.code == 2, result.text
        assert INSTALL_PROVE not in result.text


# absent, or a Prove below the floor: 0.3.0 (9.9.9 is above the floor, a version Trace reads)
@pytest.mark.parametrize("prove", ["absent", "0.3.0"])
@pytest.mark.parametrize("command", ["trace", "import"])
def test_tf0_10_a_command_that_needs_prove_names_the_install_line(tmp_path: Path, prove: str, command: str) -> None:
    store = tmp_path / "store"
    argv = where_cs() if command == "trace" else ragas_import(store, "v1")
    result = run_sub(command, argv, prove=prove)
    line = _one_error(result)
    # the install line once, alone on the next line under the error, not in the sentence too
    assert INSTALL_PROVE not in line and PLACEHOLDER_INSTALL not in result.text, line
    assert [ln for ln in result.lines() if INSTALL_PROVE in ln] == [f"  next: {INSTALL_PROVE}"], result.err
    assert len(result.lines()) == 2, result.err
    if prove != "absent":
        assert prove in line, line
    assert not store.exists()


def test_tf0_10_the_fixture_store_is_read_when_prove_is_there() -> None:
    """The control for the three above: the same command with Prove present reads the store."""
    result = run_sub("trace", where_cs("--json"))
    assert result.code == 0, result.text
    assert result.json()["run"]["run_id"] == CS_RECORD and str(CS) == result.json()["prove"]["store"]
