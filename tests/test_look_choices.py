"""Choices the look leaves to the build, pinned where a plausible wrong build would harm a user.

- A closed pipe is the command's work done: exit 0, nothing on stderr, nothing in the errors
  log. The wrong build reads the broken pipe as an unexpected failure (exit 3, an error line,
  a log entry).
- An SVG into a folder that cannot be written is refused before any work: exit 1, nothing on
  stdout. The wrong build finds out at the write, after the report is computed (exit 3).
- An import stopped by Ctrl-C under a run name the store already held has written nothing, and
  says so as an import stopped before writing does. The wrong builds tell what was left from the
  run's folder: one tells the user to remove the folder of a run that was whole before the import
  began, the other that the import wrote it whole.
- An errors log that cannot be written still leaves the details where the user can read them,
  as continuation lines on stderr, and exits 3. The wrong build appends without a guard and
  ends in the traceback the log was for.
- An option before the verb or the tool that the command does not know, an abbreviation among
  them, is a wrong command line (exit 2). The wrong build reads past it and takes its value for
  the verb or the tool: an unknown verb (2 by luck) or, in the import, an unknown tool (1).
- A value a user can type is the command's own refusal or a result, never an unexpected failure.
  The wrong build hands it to a library that raises (exit 3, "an unexpected failure").
- The SVG is written as UTF-8 whatever the locale's encoding. The wrong build writes in the
  locale's encoding and fails on the report's glyphs (an unexpected failure, exit 3).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from proofload.store import Store

from conftest import CS, CS_RECORD, TAU2, TAU2_A, TAU2_B
from tf0_support import RAGAS, deepeval_import, ragas_import, run_sub, trace, trace_import, where_cs


def test_a_closed_pipe_exits_zero_with_nothing_on_stderr(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home))
    for command, argv in (("trace", where_cs()), ("import", deepeval_import(tmp_path / "store", "v1"))):
        read, write = os.pipe()
        os.close(read)
        try:
            result = run_sub(command, argv, stdout=write, env=env, cwd=tmp_path)
        finally:
            os.close(write)
        assert (result.code, result.err) == (0, ""), result.err
    assert not (home / ".cache").exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="a folder is never read-only to root")
def test_an_svg_into_a_folder_that_cannot_be_written_is_a_refusal(tmp_path: Path) -> None:
    folder = tmp_path / "read-only"
    folder.mkdir()
    folder.chmod(0o500)
    try:
        result = trace(where_cs("--svg", str(folder / "curve.svg")))
    finally:
        folder.chmod(0o700)
    assert (result.code, result.out) == (1, ""), result.text


def test_ctrl_c_under_a_name_the_store_held_says_nothing_was_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import poisson_trace.ingest.deepeval as reader

    store = tmp_path / "store"
    assert trace_import(deepeval_import(store, "v1")).code == 0
    before = sorted((p.relative_to(store), p.stat().st_mtime_ns) for p in store.rglob("*"))

    def stop(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(reader, "read", stop)
    result = trace_import(deepeval_import(store, "v1"))
    fresh = trace_import(deepeval_import(store, "v2"))
    assert result.code == fresh.code == 130, result.text
    first = result.lines("out")[0]
    assert first.startswith("stopped  ") and first == fresh.lines("out")[0], (first, fresh.out)
    assert sorted((p.relative_to(store), p.stat().st_mtime_ns) for p in store.rglob("*")) == before
    assert Store(store).manifest("v1").status == "complete"


@pytest.mark.skipif(os.geteuid() == 0, reason="a folder is never read-only to root")
def test_an_errors_log_that_cannot_be_written_leaves_the_details_on_stderr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    home.chmod(0o500)
    monkeypatch.setenv("HOME", str(home))

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("zq-sentinel-log")

    monkeypatch.setattr(Store, "runs", boom)
    try:
        result = trace(where_cs())
    finally:
        home.chmod(0o700)
    assert result.code == 3 and result.out == "", result.text
    lines = result.err.splitlines()
    assert lines[0].startswith("error: ") and "RuntimeError" in lines[0], result.err
    assert all(line.startswith("  ") for line in lines[1:]) and "zq-sentinel-log" in result.err
    assert not (home / ".cache").exists()


def _latin_1_locale() -> dict[str, str] | None:
    """An environment whose locale encoding is ISO-8859-1, or None where none is installed."""
    for name in ("en_US.ISO8859-1", "en_US.ISO-8859-1", "en_US.iso88591", "de_DE.ISO8859-1"):
        env = dict(os.environ, LC_ALL=name, LANG=name, PYTHONUTF8="0")
        env.pop("PYTHONIOENCODING", None)
        probe = subprocess.run(
            [sys.executable, "-c", "import locale; print(locale.getpreferredencoding(False))"],
            capture_output=True, text=True, env=env,
        )
        if probe.stdout.strip().replace("-", "").upper() in ("ISO88591", "LATIN1"):
            return env
    return None


def test_the_svg_is_written_as_utf_8_whatever_the_locale(tmp_path: Path) -> None:
    env = _latin_1_locale()
    if env is None:
        pytest.skip("no ISO-8859-1 locale is installed here")
    target = tmp_path / "curve.svg"
    result = run_sub("trace", where_cs("--svg", str(target), "--json"), env=env)
    assert result.code == 0, result.text
    assert "–" in target.read_bytes().decode("utf-8")


def test_an_unknown_option_before_the_verb_or_the_tool_is_a_wrong_command_line(tmp_path: Path) -> None:
    for result, helps in (
        (trace(["--ev", "unresolved", "where", CS_RECORD, "--store", str(CS)]), ("poisson-trace --help",)),
        (trace_import(["--sto", str(tmp_path / "store"), "ragas", str(RAGAS / "rag-base.jsonl"), "--run", "v1",
                       "--metric", "faithfulness", "--cut", "0.5", "--below", "--case-column", "case"]),
         ("poisson-trace-import --help", "poisson-trace import --help")),
    ):
        assert result.code == 2 and result.out == "", result.text
        # one error line, then the command's help on its own next line, as every other wrong
        # command line has it, and not inside the sentence
        lines = result.lines()
        assert len(lines) == 2 and lines[0].startswith("error: ") and "--help" not in lines[0], result.err
        assert lines[1] in tuple(f"  next: {h}" for h in helps), result.err
    assert not (tmp_path / "store").exists()


@pytest.mark.parametrize(
    "command,argv",
    [
        ("trace", where_cs("--seed", "-1")),
        ("trace", ["fix-check", TAU2_A, TAU2_B, "--store", str(TAU2), "--event", "unsolved", "--inputs", "all", "--max-mde", "0.2", "--seed", "-1"]),
        ("trace", where_cs("--boot", str(10**20))),
        ("trace", where_cs("--at", "9" * 400)),
        ("import", "started"),
    ],
    ids=["where --seed -1", "fix-check --seed -1", "--boot 10^20", "--at 400 digits", "--started past year 9999"],
)
def test_a_value_a_user_types_is_never_an_unexpected_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str, argv: object) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    if command == "import":
        result = trace_import([*ragas_import(tmp_path / "store", "v1")[:-2], "--started", "9999-12-31T23:59:59-14:00"])
    else:
        result = trace(argv)  # type: ignore[arg-type]
    assert result.code in (0, 1), result.text
    if result.code == 1:
        assert result.out == "" and len(result.lines()) == 1 and result.err.startswith("error: "), result.err
    assert not (tmp_path / ".cache").exists()
