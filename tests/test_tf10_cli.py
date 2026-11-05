"""TF10-33 to TF10-37: the three readers in the import's command line (spec sections 3.3, 5.1, 6.1
and 6.3; the shared core of INT1 to INT4; RD3).

- TF10-33: the import's help lists ``promptfoo``, ``inspect`` and ``openai-evals``; each reader's
  help is the verb's under both spellings, byte for byte; a tool the install lacks is refused
  naming every reader it has.
- TF10-34: each import's ``--json`` is ``poisson-trace.import/1`` with the files' digests and a
  ``next:`` fix check on ``--event missed``; the text summary ends with that ``next:`` line; a run
  name the store holds is refused and the store is unchanged.
- TF10-35: a file that is missing, not the tool's, or damaged is refused in one plain line naming
  it, exit 1, nothing written; a wrong command line exits 2 (the exit-code table, section 3.3).
- TF10-36: both spellings of the import print the same bytes for each reader, refused or done.
- TF10-37: the readers import nothing from the tools or from Prove; ``zstandard`` is imported only
  when a ``.eval`` is read; the third reader's module is ``openai_evals`` (RD3).
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from tf0_support import trace, trace_import
from tf10_support import (
    IN_EVAL, IN_JSON, OE_OLD, PF_JSON, PF_JSONL, PRESENT, TOOLS, imported, in_argv, module, oe_argv, pf_argv,
    refused, wrong_line,
)
from tf21_support import run_import

NEW = ("promptfoo", "inspect", "openai-evals")
FIRST = {"promptfoo": lambda root, run: pf_argv(PF_JSON, root, run),
         "inspect": lambda root, run: in_argv(IN_JSON, root, run),
         "openai-evals": lambda root, run: oe_argv(OE_OLD, root, run)}
FILES = {"promptfoo": [PF_JSON], "inspect": [IN_JSON], "openai-evals": [OE_OLD]}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------- TF10-33 ----------


def test_tf10_33_the_import_s_help_lists_the_three_readers() -> None:
    helped = trace(["import", "--help"])
    assert helped.code == 0, helped.text
    for tool in PRESENT:
        # a long name is set on a line of its own, its description under it
        assert re.search(rf"^ +{re.escape(tool)}(?: {{2,}}\S.*)?$", helped.out, re.M), (tool, helped.out)


@pytest.mark.parametrize("tool", NEW)
def test_tf10_33_each_reader_s_help_is_the_verb_s(tool: str) -> None:
    a, b = trace(["import", tool, "--help"]), trace_import([tool, "--help"])
    assert a.code == b.code == 0 and a.out == b.out and a.err == b.err == "", a.text + b.text
    assert a.out.split("\n\n")[0].startswith(f"usage: poisson-trace import {tool}"), a.out
    for flag in ("--store", "--run", "--started", "--json"):
        assert flag in a.out, flag


def test_tf10_33_each_reader_s_flags_are_the_spec_s() -> None:
    flags = {"promptfoo": ("--prompt", "--provider", "--case", "--outcome", "--cut", "--below", "--above"),
             "inspect": ("--scorer", "--outcome", "--cut", "--below", "--above", "--failed")}
    for tool, wanted in flags.items():
        text = trace(["import", tool, "--help"]).out
        for flag in wanted:
            assert flag in text, (tool, flag)
    assert "--case" not in trace(["import", "openai-evals", "--help"]).out


def test_tf10_33_an_absent_tool_is_refused_naming_every_reader() -> None:
    unknown = trace(["import", "langsmith", "x.json", "--store", "st", "--run", "r1"])
    assert unknown.code == 1 and all(tool in unknown.lines()[0] for tool in PRESENT), unknown.err


# ---------- TF10-34 ----------


@pytest.mark.parametrize("tool", NEW)
def test_tf10_34_the_summary_is_the_import_s(tmp_path: Path, tool: str) -> None:
    data = imported(FIRST[tool](tmp_path / "st", "first"))
    assert data["run"] == "first" and data["store"] == str(tmp_path / "st") and data["tool"] == tool
    assert [f["sha256"] for f in data["files"]] == [_sha(p) for p in FILES[tool]]
    assert [f["name"] for f in data["files"]] == [p.name for p in FILES[tool]]
    assert data["next"].startswith("poisson-trace fix-check OLD NEW ") and "--event missed" in data["next"]
    text = run_import(FIRST[tool](tmp_path / "st2", "first"))
    assert text.code == 0 and text.out.startswith("ok  wrote run first to "), text.out
    assert text.out.rstrip("\n").splitlines()[-1].startswith("next: poisson-trace fix-check OLD NEW"), text.out


@pytest.mark.parametrize("tool", NEW)
def test_tf10_34_a_name_in_use_is_refused_and_nothing_changes(tmp_path: Path, tool: str) -> None:
    imported(FIRST[tool](tmp_path / "st", "first"))
    before = sorted((str(p), p.read_bytes()) for p in (tmp_path / "st").rglob("*") if p.is_file())
    line = refused(run_import(FIRST[tool](tmp_path / "st", "first")))
    assert "first" in line, line
    after = sorted((str(p), p.read_bytes()) for p in (tmp_path / "st").rglob("*") if p.is_file())
    assert after == before


# ---------- TF10-35 ----------


def _not_the_tool_s(tmp_path: Path, tool: str) -> Path:
    """A file of the tool's extension holding another tool's results."""
    if tool == "promptfoo":
        path = tmp_path / "other.json"
        path.write_bytes(IN_JSON.read_bytes())
    elif tool == "inspect":
        path = tmp_path / "other.json"
        path.write_bytes(PF_JSON.read_bytes())
    else:
        path = tmp_path / "other.jsonl"
        path.write_bytes(PF_JSONL.read_bytes())
    return path


MALFORMED: dict[str, Any] = {
    "missing": lambda tmp, tool: tmp / ("gone.eval" if tool == "inspect" else "gone.json"),
    "empty": lambda tmp, tool: _write(tmp / ("e.jsonl" if tool == "openai-evals" else "e.json"), b""),
    "not JSON": lambda tmp, tool: _write(tmp / ("n.jsonl" if tool == "openai-evals" else "n.json"), b"{\"results\": [1, 2"),
    "a JSON list": lambda tmp, tool: _write(tmp / ("l.jsonl" if tool == "openai-evals" else "l.json"), b"[1, 2, 3]\n"),
    "another tool's": _not_the_tool_s,
    "a directory": lambda tmp, tool: _dir(tmp / "folder.json"),
}


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def _dir(path: Path) -> Path:
    path.mkdir()
    return path


def _argv(tool: str, path: Path, root: Path) -> list[str]:
    if tool == "promptfoo":
        return pf_argv(path, root, "v", "--started", "2026-10-07T04:00:00Z")
    if tool == "inspect":
        return in_argv(path, root, "v")
    return oe_argv(path, root, "v")


@pytest.mark.parametrize("label", list(MALFORMED))
@pytest.mark.parametrize("tool", NEW)
def test_tf10_35_a_file_not_the_reader_s_is_refused_in_one_line_naming_it(tmp_path: Path, tool: str, label: str) -> None:
    path = MALFORMED[label](tmp_path, tool)
    result = run_import(_argv(tool, path, tmp_path / "st"))
    line = refused(result)
    assert path.name in line, line
    assert "Traceback" not in result.err and len(result.err.splitlines()) <= 3, result.err
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("tool", NEW)
@pytest.mark.parametrize("drop", ["--run", "files"])
def test_tf10_35_a_wrong_command_line_exits_2(tmp_path: Path, tool: str, drop: str) -> None:
    argv = FIRST[tool](tmp_path / "st", "first")
    if drop == "--run":
        at = argv.index("--run")
        argv = argv[:at] + argv[at + 2:]
    else:
        argv = [argv[0], *[a for a in argv[1:] if a not in {str(p) for p in FILES[tool]}]]
    wrong_line(run_import(argv))
    assert not (tmp_path / "st").exists()


def test_tf10_35_the_eval_and_json_forms_are_told_by_extension(tmp_path: Path) -> None:
    disguised = tmp_path / "log.json"
    disguised.write_bytes(IN_EVAL.read_bytes())
    line = refused(run_import(in_argv(disguised, tmp_path / "st", "v")))
    assert "log.json" in line, line
    other = tmp_path / "log.txt"
    other.write_bytes(IN_JSON.read_bytes())
    line = refused(run_import(in_argv(other, tmp_path / "st", "v")))
    assert "log.txt" in line and ".eval" in line and ".json" in line, line


# ---------- TF10-36 ----------


@pytest.mark.parametrize("tool", NEW)
def test_tf10_36_both_spellings_print_the_same_bytes(tmp_path: Path, tool: str) -> None:
    import os

    from tf0_support import chdir

    outs = []
    for spelling in ("verb", "alias"):
        folder = tmp_path / spelling
        folder.mkdir()
        argv = FIRST[tool](Path("st"), "first")
        with chdir(folder):
            ran = trace(["import", *argv]) if spelling == "verb" else trace_import(argv)
            again = trace(["import", *argv]) if spelling == "verb" else trace_import(argv)
        outs.append((ran.code, ran.out, ran.err, again.code, again.out, again.err))
        assert ran.code == 0 and again.code == 1, ran.text + again.text
        assert os.path.isdir(folder / "st" / "first")
    assert outs[0] == outs[1]


# ---------- TF10-37 ----------


def _imports(tool: str) -> tuple[set[str], set[str]]:
    """The modules the reader imports at its top level, and those it imports inside a function."""
    tree = ast.parse(Path(module(tool).__file__).read_text(encoding="utf-8"))
    top: set[str] = set()
    inner: set[str] = set()

    def names(node: ast.AST) -> list[str]:
        if isinstance(node, ast.Import):
            return [a.name for a in node.names]
        if isinstance(node, ast.ImportFrom) and node.module:
            return [node.module]
        return []

    for node in tree.body:
        top.update(names(node))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for inside in ast.walk(node):
                inner.update(names(inside))
    return top, inner


@pytest.mark.parametrize("tool", NEW)
def test_tf10_37_no_reader_imports_the_tool_or_prove(tool: str) -> None:
    top, inner = _imports(tool)
    for name in top | inner:
        root = name.split(".")[0]
        assert root not in ("poisson_prove", "inspect_ai", "evals", "openai", "promptfoo"), (tool, name)
    assert "zstandard" not in top, tool


def test_tf10_37_the_modules_are_named_for_their_tools() -> None:
    for tool, name in TOOLS.items():
        reader = module(tool)
        assert reader.__name__ == f"poisson_trace.ingest.{name}"
        for attr in ("add_arguments", "read", "looks_like", "DESCRIPTION", "EXAMPLE"):
            assert hasattr(reader, attr), (tool, attr)
        assert reader.EXAMPLE.startswith(f"poisson-trace import {tool} "), reader.EXAMPLE
    assert "zstandard" in _imports("inspect")[1]


def test_tf10_37_the_inspect_extra_holds_zstandard() -> None:
    import tomllib

    from tf3_support import REPO

    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    extras = project["optional-dependencies"]
    assert any(re.match(r"zstandard\b", d) for d in extras["inspect"]), extras
    assert any(re.match(r"zstandard\b", d) for d in extras["dev"]), extras
    assert not any(re.match(r"zstandard\b", d) for d in project["dependencies"]), project["dependencies"]


def test_tf10_37_the_json_summary_is_one_document(tmp_path: Path) -> None:
    for tool in NEW:
        result = run_import([*FIRST[tool](tmp_path / tool, "first"), "--json"])
        assert result.code == 0 and json.loads(result.out)["schema"] == "poisson-trace.import/1", result.err
