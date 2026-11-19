"""TF0-16 to TF0-18: how output reads and where it can go (rules 10, 16 and 4 of
``docs/cli-look.md``).

Counts carry thousands separators in every report a user reads, and stay plain numbers in the
JSON. A stdout that cannot encode the report's glyphs (``·``, ``–``, ``×``) gets the same report
in ASCII, line for line and number for number, instead of a traceback. A stdout whose reader has
gone away ends the command quietly, with no traceback and no message from the interpreter."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from tf0_support import (
    EXIT_CODES, changes_he, compare_tau2, deepeval_import, fix_check_he, fix_check_tau2,
    run_sub, trace, trace_import, where_cs,
)

# A whole number of four digits or more standing alone: not inside a run id, a date, a time, a
# decimal, a version, a hash or a value such as HumanEval/129. A comma or a full stop after it
# ends a sentence unless a digit follows.
BARE_COUNT = re.compile(r"(?<![\w.,:/+\-−])\d{4,}(?![\w:/\-])(?![.,]\d)")


def _markdown(tmp_path: Path) -> dict[str, str]:
    store = tmp_path / "store"
    imported = trace_import(deepeval_import(store, "he-a"))
    other = trace_import(deepeval_import(store, "he-b", "b"))
    assert imported.code == 0 and other.code == 0, imported.text + other.text
    outs = {"import": imported.out}
    for name, argv in {
        "where": where_cs("--at", "20"),
        "compare": compare_tau2("1.5"),
        "fix-check": fix_check_he(),
        "changes": changes_he(),
        "fix-check on the imports": ["fix-check", "he-a", "he-b", "--store", str(store), "--event", "missed", "--inputs", "all", "--max-mde", "0.5"],
    }.items():
        result = trace(argv)
        assert result.code == 0, (name, result.text)
        outs[name] = result.out
    return outs


# ---------- TF0-16: thousands separators ----------


def test_tf0_16_no_count_of_a_thousand_or_more_is_printed_without_separators(tmp_path: Path) -> None:
    outs = _markdown(tmp_path)
    bare = {name: BARE_COUNT.findall(text) for name, text in outs.items() if BARE_COUNT.search(text)}
    assert bare == {}, bare
    # the counts this rule is about are there to be read: the HumanEval runs hold 10,496 rows
    assert "10,496" in outs["fix-check"] and "10,496" in outs["import"]


@pytest.fixture(scope="module")
def large(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Two runs of 1,100 traced episodes on one cell, and two runs over 1,000 inputs: every
    count the compare, where, fix-check and changes reports print reaches four digits."""
    from conftest import Row, build_store, deaths_rows

    root = tmp_path_factory.mktemp("large")
    steps = [1 + i % 20 for i in range(1100)]
    build_store(root / "traced", "a", deaths_rows(steps))
    build_store(root / "traced", "b", deaths_rows([s + 1 for s in steps]))
    for run, shift in (("a", 0), ("b", 1)):
        rows = [Row({"case": f"c{i}"}, "fail" if (i + shift) % 3 == 0 else "ok", None) for i in range(1000)]
        build_store(root / "inputs", run, rows)
    return root


def test_tf0_16_large_counts_carry_separators_in_every_report(large: Path) -> None:
    traced, inputs = str(large / "traced"), str(large / "inputs")
    outs = {
        "compare": trace(["compare", "a", "b", "--store", traced, "--event", "fail", "--max-mde-hr", "100"]),
        "where": trace(["where", "a", "--store", traced, "--event", "fail"]),
        "fix-check": trace(["fix-check", "a", "b", "--store", inputs, "--event", "fail", "--inputs", "all", "--max-mde", "0.5"]),
        "changes": trace(["changes", "a", "b", "--store", inputs, "--event", "fail", "--top", "0"]),
    }
    for name, result in outs.items():
        assert result.code == 0, (name, result.text)
        assert BARE_COUNT.findall(result.out) == [], (name, BARE_COUNT.findall(result.out))
    assert "1,100" in outs["compare"].out and "1,100" in outs["where"].out
    assert "1,000" in outs["fix-check"].out and "1,000" in outs["changes"].out


def test_tf0_16_the_json_keeps_counts_as_numbers() -> None:
    d = trace(fix_check_he("--json")).json()
    rows = d["runs"]["old"]["tally"]["rows"]
    assert isinstance(rows, int) and not isinstance(rows, bool) and rows == 10496


# ---------- TF0-17: the ASCII fallback ----------


def _numbers(line: str) -> list[str]:
    return re.findall(r"\d[\d,]*(?:\.\d+)?(?:e[+-]?\d+)?", line)


def _in_order(wanted: list[str], found: list[str]) -> bool:
    """Every number of ``wanted`` appears in ``found``, in the same order; a glyph spelt out in
    ASCII (``²`` as ``^2``) may add one."""
    rest = iter(found)
    return all(any(number == seen for seen in rest) for number in wanted)


def _env(encoding: str) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = encoding
    return env


ASCII_CASES = {
    "where": ("trace", where_cs("--at", "20")),
    "compare": ("trace", compare_tau2("1.3", "--at", "10")),
    "fix-check": ("trace", fix_check_tau2()),
    "changes": ("trace", changes_he()),
}


@pytest.mark.parametrize("name", [*ASCII_CASES, "import"])
def test_tf0_17_a_stdout_that_cannot_encode_the_glyphs_gets_ascii(tmp_path: Path, name: str) -> None:
    if name == "import":
        stores = {"utf-8": tmp_path / "wide", "ascii": tmp_path / "narrow"}
        runs = {enc: run_sub("import", deepeval_import(stores[enc], "he-a"), env=_env(enc)) for enc in stores}
    else:
        command, argv = ASCII_CASES[name]
        runs = {enc: run_sub(command, argv, env=_env(enc)) for enc in ("utf-8", "ascii")}
    utf8, ascii_ = runs["utf-8"], runs["ascii"]
    assert utf8.code == 0 and ascii_.code == 0, ascii_.text
    assert "Traceback" not in ascii_.err and ascii_.err == "", ascii_.err
    assert ascii_.out.isascii()
    assert not utf8.out.isascii(), "the report holds a glyph to fall back from"
    wide, narrow = utf8.out.splitlines(), ascii_.out.splitlines()
    assert len(wide) == len(narrow)
    for w, n in zip(wide, narrow, strict=True):
        if w.isascii():
            assert n == w.replace(str(tmp_path / "wide"), str(tmp_path / "narrow"))
        else:
            # every number kept in order, and every glyph spelt by something: none dropped
            assert _in_order(_numbers(w), _numbers(n)), (w, n)
            assert len(n.split()) == len(w.split()) and len(n) >= len(w), (w, n)
            # and spelt in ASCII, not as a question mark or an escape
            assert n.count("?") == w.count("?") and "\\x" not in n and "\\u" not in n, (w, n)


@pytest.mark.parametrize("encoding", ["ascii", "latin-1"])
def test_tf0_17_json_is_the_same_bytes_on_any_stdout(tmp_path: Path, encoding: str) -> None:
    """On runs whose names a user wrote in letters outside ASCII: the JSON keeps them whole."""
    store = tmp_path / "store"
    for name, which in (("café-a", "a"), ("café-b", "b")):
        made = trace_import(deepeval_import(store, name, which))
        assert made.code == 0, made.text
    argv = ["fix-check", "café-a", "café-b", "--store", str(store), "--event", "missed", "--inputs", "all", "--max-mde", "0.05", "--json"]
    utf8 = run_sub("trace", argv, env=_env("utf-8"))
    other = run_sub("trace", argv, env=_env(encoding))
    assert utf8.code == 0 and other.err == "", other.err
    assert other.out == utf8.out
    assert other.json()["runs"]["old"]["run_id"] == "café-a"


def test_tf0_17_a_latin_1_stdout_reads_without_a_traceback() -> None:
    result = run_sub("trace", compare_tau2("1.3"), env=_env("latin-1"))
    assert result.code == 0 and result.err == "", result.err
    assert len(result.out.splitlines()) == len(trace(compare_tau2("1.3")).out.splitlines())


# ---------- TF0-18: a closed pipe ----------


def _closed_pipe(command: str, argv: list[str], cwd: Path, home: Path | None = None) -> tuple[int, str]:
    """The command's exit code and stderr, its stdout a pipe nobody reads; ``home`` is its ``HOME``."""
    read, write = os.pipe()
    os.close(read)
    env = None if home is None else dict(os.environ, HOME=str(home))
    try:
        result = run_sub(command, argv, stdout=write, cwd=cwd, env=env)
    finally:
        os.close(write)
    return result.code, result.err


@pytest.mark.parametrize(
    "command,argv",
    [
        ("trace", where_cs()),
        ("trace", fix_check_he()),
        ("trace", changes_he("--json")),
        ("trace", ["--help"]),
        ("trace", ["--version"]),
        ("import", ["deepeval", "--help"]),
    ],
    ids=["where", "fix-check", "changes json", "help", "version", "import help"],
)
def test_tf0_18_a_reader_that_went_away_ends_the_command_quietly(tmp_path: Path, command: str, argv: list[str]) -> None:
    home = tmp_path / "home"
    home.mkdir()
    code, err = _closed_pipe(command, argv, tmp_path, home)
    assert "Traceback" not in err and "Exception ignored" not in err and "BrokenPipeError" not in err, err
    assert code in EXIT_CODES, code
    assert all(line.startswith(("error: ", "note: ", "  ")) for line in err.splitlines() if line.strip()), err
    if argv == where_cs():
        # the report's work is done: exit 0, nothing on stderr, nothing in the errors log
        assert (code, err) == (0, ""), err
        assert not (home / ".cache").exists()


def test_tf0_18_an_import_into_a_closed_pipe_still_writes_its_run(tmp_path: Path) -> None:
    from poisson_prove.store import Store

    home = tmp_path / "home"
    home.mkdir()
    code, err = _closed_pipe("import", deepeval_import(tmp_path / "store", "v1"), tmp_path, home)
    assert "Traceback" not in err and "Exception ignored" not in err, err
    assert (code, err) == (0, ""), err
    assert not (home / ".cache").exists()
    assert Store(tmp_path / "store").manifest("v1").status == "complete"
