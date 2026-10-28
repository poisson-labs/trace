"""TR9, TR10, TR11, TR23, TR31: the command line, its refusals and exit codes, and the two
source-level rules (read-only, through Prove only)."""

from __future__ import annotations

import ast
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (
    CELL_A, CELL_B, CS, CS_EVENTS, CS_RECORD, FIXTURES, SYNTH_EVENTS, TAU2, TAU2_A, TAU2_B,
    TAU2_EVENTS, compare, deaths_rows, run_cli, where,
)


def src_files() -> list[Path]:
    import poisson_trace

    return sorted(Path(poisson_trace.__file__).resolve().parent.glob("*.py"))


def _one_sentence(result) -> None:  # type: ignore[no-untyped-def]
    lines = [line for line in result.text.splitlines() if line.strip()]
    # one sentence, and the command to run under it on its own next: lines (rule 4)
    assert lines and all(line.startswith("  next: ") for line in lines[1:]), result.text
    assert result.code == 1


# ---------- TR9 ----------


def _snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    out = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        stat = path.stat()
        out[str(path.relative_to(root))] = (stat.st_size, stat.st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
    return out


def test_tr9_nothing_under_the_store_changes(tmp_path: Path) -> None:
    before = _snapshot(FIXTURES)
    assert where(TAU2, TAU2_A, TAU2_EVENTS, "--svg", str(tmp_path / "a.svg")).code == 0
    assert where(CS, CS_RECORD, CS_EVENTS, "--json").code == 0
    assert compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.5).code == 0
    assert _snapshot(FIXTURES) == before


def _calls(tree: ast.AST):  # type: ignore[no-untyped-def]
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def _call_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        base = f.value
        return (base.id + "." if isinstance(base, ast.Name) else "") + f.attr
    return ""


def _enclosing_functions(tree: ast.AST) -> dict[int, list[str]]:
    """Line number -> the names of the functions enclosing it, outermost first."""
    spans: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            spans.append((node.lineno, node.end_lineno or node.lineno, node.name))
    out: dict[int, list[str]] = {}
    for lo, hi, name in sorted(spans):
        for line in range(lo, hi + 1):
            out.setdefault(line, []).append(name)
    return out


def test_tr9_src_writes_nothing_but_the_svg_and_the_json(synth) -> None:  # type: ignore[no-untyped-def]
    assert where(*synth, SYNTH_EVENTS).code == 0
    for path in src_files():
        source = path.read_text()
        tree = ast.parse(source)
        lines = source.splitlines()
        inside = _enclosing_functions(tree)
        for call in _calls(tree):
            name = _call_name(call)
            fns = inside.get(call.lineno, [])
            # the svg writer: a function named for it, or the one line that writes the file
            in_svg = any("svg" in f for f in fns) or "svg" in lines[call.lineno - 1].lower()
            # the errors log's appender (the shared look's rule 4): a function named for it,
            # which opens its file to append (mode "a" or "at") and nothing else
            in_log = any("errors_log" in f for f in fns)
            # R18: the names file's writer, a function named for it (name writes trace-names.toml)
            in_names = any("names_file" in f for f in fns)
            # R18: the config file's writer, a function named for it (init writes trace.toml)
            in_config = any("config_file" in f for f in fns)
            if name.endswith("to_parquet"):
                raise AssertionError(f"{path.name}:{call.lineno}: to_parquet")
            if name == "open" or name.endswith(".open"):
                mode = ""
                if len(call.args) > 1 and isinstance(call.args[1], ast.Constant):
                    mode = str(call.args[1].value)
                # a method named open, Path.open among them, takes its mode first
                first = call.args[0] if call.args else None
                if isinstance(call.func, ast.Attribute) and isinstance(first, ast.Constant) and isinstance(first.value, str) and re.fullmatch(r"[rwxabt+]+", first.value):
                    mode = first.value
                for kw in call.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        mode = str(kw.value.value)
                assert not set(mode) & set("wax+") or in_svg or ((in_names or in_config) and mode in ("w", "wt", "x", "xt")) or (in_log and mode in ("a", "at")), f"{path.name}:{call.lineno}: open for writing outside the svg writer, the names and config files' writers and the errors log"
            if name.endswith("write_text") or name.endswith("write_bytes"):
                assert in_svg or in_names or in_config, f"{path.name}:{call.lineno}: a write outside the svg writer and the names and config files' writers"
            if name in ("json.dump", "json.dumps") or name.endswith(".dump"):
                assert path.name in ("report.py", "cli.py"), f"{path.name}:{call.lineno}: json.dump outside the printers"


# ---------- TR10 ----------


ALLOWED_PROVE_IMPORTS = {
    "poisson_prove": set(),
    "poisson_prove.store": {"Store", "RunManifest", "RunTally"},
    "poisson_prove.steps": {"declaration_check", "DeclarationCheck"},
    "poisson_prove.trace": {"KINDS"},
}


def test_tr10_reads_through_prove_only(synth) -> None:  # type: ignore[no-untyped-def]
    assert where(*synth, SYNTH_EVENTS).code == 0
    for path in src_files():
        text = path.read_text()
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("pyarrow"), path.name
                    assert alias.name == "poisson_prove" or not alias.name.startswith("poisson_prove"), (path.name, alias.name)
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith("pyarrow"), path.name
                if module.startswith("poisson_prove"):
                    assert module in ALLOWED_PROVE_IMPORTS, (path.name, module)
                    names = {alias.name for alias in node.names}
                    assert names <= ALLOWED_PROVE_IMPORTS[module], (path.name, module, names)
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                low = node.value.lower()
                assert "parquet" not in low, (path.name, node.value)
                assert "manifest.json" not in low, (path.name, node.value)
            if isinstance(node, ast.Attribute):
                assert node.attr != "from_dict", (path.name, node.lineno)
        assert "pyarrow" not in text
        assert "from_dict" not in text


# ---------- TR11 ----------


def test_tr11_an_unknown_event_is_refused_naming_the_outcomes_present() -> None:
    result = where(TAU2, TAU2_A, ["max_steps"])
    _one_sentence(result)
    assert "max_steps" in result.text
    assert "solved" in result.text and "unsolved" in result.text


def test_tr11_an_unknown_run_is_refused_naming_the_runs_in_the_store() -> None:
    result = where(TAU2, "nope", TAU2_EVENTS)
    _one_sentence(result)
    assert TAU2_A in result.text and TAU2_B in result.text
    result = compare(TAU2, TAU2_A, "nope", TAU2_EVENTS, 1.5)
    _one_sentence(result)
    assert TAU2_B in result.text


def test_tr11_no_common_cell_is_refused(two_run_store) -> None:  # type: ignore[no-untyped-def]
    root = two_run_store(deaths_rows([2, 3, 4], cell=CELL_A), deaths_rows([2, 3, 4], cell=CELL_B))
    result = compare(root, "a", "b", ["fail"], 1.5)
    _one_sentence(result)


def test_tr11_compare_refuses_an_event_absent_from_both_and_allows_one_absent_from_one(two_run_store) -> None:  # type: ignore[no-untyped-def]
    root = two_run_store(deaths_rows([2, 3, 4, 5]), deaths_rows([2, 3, 4, 5], died=False))
    both = compare(root, "a", "b", ["fail", "never_seen"], 100.0)
    _one_sentence(both)
    assert "never_seen" in both.text
    one = compare(root, "a", "b", ["fail"], 100.0)
    assert one.code in (0, 2), one.text
    assert "fail" in one.out


def test_tr11_no_death_in_either_run_is_refused_and_where_still_prints(two_run_store) -> None:  # type: ignore[no-untyped-def]
    # The event is carried, so it is not refused as unknown; every row that carries it sits at
    # the cap and is censored, so neither run has a death.
    rows = deaths_rows([2, 3], died=False) + deaths_rows([4, 4], died=True, start_rep=5)
    root = two_run_store(rows, rows, cap=4)
    result = compare(root, "a", "b", ["fail"], 100.0)
    _one_sentence(result)
    alive = where(root, "a", ["fail"])
    assert alive.code == 0, alive.text
    data = where(root, "a", ["fail"], "--json").json()
    assert data["curve"] == []
    assert data["median_step"] is None
    assert data["causes"] == []
    assert data["run"]["placement"] == {"placed": 4, "died": 0, "ended": 2, "timed out": 0, "capped": 2,
                                        "excluded": {"no trace": 0, "unreadable trace": 0, "no leaf span": 0, "no outcome, not a timeout": 0}}


def test_tr11_every_refusal_is_one_sentence_and_an_argument_error_exits_two() -> None:
    # R17: the command line is wrong, so exit 2 (the shared exit-code table); still one sentence
    for argv in (
        ["where", TAU2_A, "--store", str(TAU2)],                       # no --event
        ["where", TAU2_A, "--event", "unsolved"],                      # no --store
        ["where", TAU2_A, "--store", str(TAU2), "--event", "unsolved", "--by", "wall"],
    ):
        result = run_cli(argv)
        lines = [line for line in result.text.splitlines() if line.strip()]
        assert lines and all(line.startswith("  next: ") for line in lines[1:]), result.text
        assert result.code == 2
    # the missing ceiling stays the command's own refusal, exit 1
    _one_sentence(run_cli(["compare", TAU2_A, TAU2_B, "--store", str(TAU2), "--event", "unsolved"]))


# ---------- TR23 ----------


def test_tr23_the_three_verdict_rows(two_run_store) -> None:  # type: ignore[no-untyped-def]
    different = two_run_store(deaths_rows(list(range(1, 21))), deaths_rows(list(range(21, 41))))
    same = two_run_store(deaths_rows(list(range(1, 11))), deaths_rows(list(range(1, 11))))
    d = compare(different, "a", "b", ["fail"], 100.0)
    assert d.code == 0, d.text
    assert "different:" in d.out and "p =" in d.out
    dj = compare(different, "a", "b", ["fail"], 100.0, "--json").json()["comparison"]
    assert dj["verdict"] == "different" and dj["p"] < 0.05
    n = compare(same, "a", "b", ["fail"], 100.0)
    assert n.code == 0, n.text
    assert "no significant difference" in n.out and "could not have detected a hazard ratio below" in n.out
    nj = compare(same, "a", "b", ["fail"], 100.0, "--json").json()["comparison"]
    assert nj["verdict"] == "no significant difference" and nj["p"] >= 0.05 and nj["mde_hazard_ratio"] <= 100.0
    t = compare(same, "a", "b", ["fail"], 1.3)
    assert t.code == 0, t.text  # R17: a result exits 0, too small to tell included
    assert "too small to tell" in t.out and "could not have detected a hazard ratio below" in t.out and "1.3" in t.out
    tj = compare(same, "a", "b", ["fail"], 1.3, "--json").json()["comparison"]
    assert tj["verdict"] == "too small to tell" and tj["mde_hazard_ratio"] > 1.3 and tj["max_mde_hr"] == 1.3
    for out in (d.out, n.out, t.out):
        assert sum(word in out for word in ("different:", "no significant difference", "too small to tell")) == 1


def test_tr23_missing_ceiling_is_a_refusal(two_run_store) -> None:  # type: ignore[no-untyped-def]
    root = two_run_store(deaths_rows([1, 2, 3]), deaths_rows([1, 2, 3]))
    result = compare(root, "a", "b", ["fail"], None)
    _one_sentence(result)
    assert "max-mde-hr" in result.text


# ---------- TR31 ----------


def _run(code: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120)


CALLS = (
    ["where", "run", "--store", "no-such-store", "--event", "fail"],
    ["compare", "a", "b", "--store", "no-such-store", "--event", "fail", "--max-mde-hr", "1.5"],
)


@pytest.mark.parametrize("argv", CALLS)
def test_tr31_refuses_before_the_store_when_prove_is_unimportable(argv) -> None:  # type: ignore[no-untyped-def]
    code = f"import sys; sys.modules['poisson_prove'] = None; from poisson_trace.cli import main; sys.exit(main({argv!r}))"
    proc = _run(code, dict(os.environ))
    assert proc.returncode == 1, proc.stderr + proc.stdout
    lines = [line for line in (proc.stdout + proc.stderr).splitlines() if line.strip()]
    assert lines and all(line.startswith("  next: ") for line in lines[1:]), proc.stdout + proc.stderr
    assert "poisson-prove" in lines[0] and "0.0.1" in lines[0] and "pip install" in " ".join(lines)
    assert "no-such-store" not in " ".join(lines)


@pytest.mark.parametrize("argv", CALLS)
def test_tr31_refuses_on_the_wrong_prove_version(tmp_path: Path, argv) -> None:  # type: ignore[no-untyped-def]
    fake = tmp_path / "fake" / "poisson_prove"
    fake.mkdir(parents=True)
    (fake / "__init__.py").write_text('__version__ = "9.9.9"\n')
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path / "fake") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    code = f"import sys; from poisson_trace.cli import main; sys.exit(main({argv!r}))"
    proc = _run(code, env)
    assert proc.returncode == 1, proc.stderr + proc.stdout
    lines = [line for line in (proc.stdout + proc.stderr).splitlines() if line.strip()]
    assert lines and all(line.startswith("  next: ") for line in lines[1:]), proc.stdout + proc.stderr
    assert "poisson-prove" in lines[0] and "0.0.1" in lines[0] and "9.9.9" in lines[0] and "pip install" in " ".join(lines)


def test_tr31_prints_no_such_line_when_prove_is_present() -> None:
    result = where(TAU2, TAU2_A, TAU2_EVENTS)
    assert result.code == 0, result.text
    assert "pip install" not in result.text
    assert result.err == ""
