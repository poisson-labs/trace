"""TF13-28 to TF13-31: the command line is a caller of the API only; no verb computes anything
outside it.

TF13-28: the command lines (``cli.py``, ``ingest/cli.py``, ``__main__.py``) import, of the
package, only ``api``, ``commands``, ``look`` and each other; none of Prove, numpy, scipy,
pandas, pyarrow, rich, the arithmetic and hashing libraries, the file formats or ``importlib``;
no ``eval``, ``exec`` or ``__import__``; and they read, write and list no file themselves.

TF13-29: the layers. Nothing in the package imports a command line but a command line;
``api`` (and the core behind it) imports neither ``commands`` nor a command line; ``commands``
imports no command line.

TF13-30: watched at the seam: each verb of the command line calls its one function, through the
module (``api.where``, ``commands.doctor``), once, with the inputs it was given; it prints what
the returned object gives and nothing it made itself; and an ``api.Refusal`` the function
raises is the command's ``error:`` line, its ``next:`` lines, its notes and its exit code.

TF13-31: TR40's rule follows the code. ``tests/test_fix_check_cli.py`` (TR40) holds that
``paired.py`` and ``cli.py`` read neither the replicate nor the seed column; once the verbs'
work leaves ``cli.py`` the same rule holds wherever it went: ``api``, ``core`` and ``commands``.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest
from tf13_support import (
    COMMAND_LINES, EV, IMPORT_ARGV, PACKAGE, VERBS_ARGV, api, call_for, cli, cli_import, commands,
    import_call_for, jsonable, keyword, options_of, plain_default, source_modules, workspace,
)

ALLOWED = {"poisson_trace", "poisson_trace.api", "poisson_trace.commands", "poisson_trace.look", *COMMAND_LINES}
COMPUTING = {"poisson_prove", "numpy", "scipy", "pandas", "pyarrow", "rich", "textual", "math", "statistics",
             "random", "hashlib", "tomllib", "zipfile", "zstandard", "gzip", "csv", "importlib", "sqlite3",
             "decimal", "fractions"}
FILE_CALLS = {"read_text", "read_bytes", "write_text", "write_bytes", "open", "mkdir", "unlink", "rmdir", "touch",
              "rmtree", "copy2", "copytree", "copyfile", "iterdir", "rglob", "glob", "scandir", "listdir", "walk",
              "makedirs", "rename"}


def _resolved_imports(path: Path) -> list[tuple[str, int]]:
    """The modules a file imports: ``from x import y`` is ``x.y`` when that is a module of the
    package, else ``x``."""
    known = source_modules()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    here = path.relative_to(PACKAGE).parent.parts
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [(alias.name, node.lineno) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = ["poisson_trace", *here][: len(here) + 2 - node.level]
                module = ".".join([*base, *([node.module] if node.module else [])])
            else:
                module = node.module or ""
            for alias in node.names:
                full = f"{module}.{alias.name}"
                out.append((full if full in known else module, node.lineno))
    return out


def _package_part(module: str) -> str | None:
    if module != "poisson_trace" and not module.startswith("poisson_trace."):
        return None
    known = source_modules()
    parts = module.split(".")
    while parts and ".".join(parts) not in known:
        parts.pop()
    return ".".join(parts) or module


# ---------- TF13-28 ----------


@pytest.mark.parametrize("name", COMMAND_LINES)
def test_tf13_28_the_command_lines_import_only_the_api_commands_and_the_look(name: str) -> None:
    path = source_modules()[name]
    for module, line in _resolved_imports(path):
        part = _package_part(module)
        if part is not None:
            assert part in ALLOWED, f"{path.name}:{line}: imports {module}"
        else:
            assert module.split(".")[0] not in COMPUTING, f"{path.name}:{line}: imports {module}"


@pytest.mark.parametrize("name", COMMAND_LINES)
def test_tf13_28_a_the_command_lines_read_and_write_no_file_and_import_nothing_by_name(name: str) -> None:
    path = source_modules()[name]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                assert func.id not in ("eval", "exec", "__import__", "open", "compile"), f"{path.name}:{node.lineno}: {func.id}"
            if isinstance(func, ast.Attribute):
                assert func.attr not in FILE_CALLS, f"{path.name}:{node.lineno}: .{func.attr}"
                assert func.attr not in ("import_module",), f"{path.name}:{node.lineno}"


# ---------- TF13-29 ----------


def test_tf13_29_nothing_imports_a_command_line_but_a_command_line() -> None:
    for name, path in source_modules().items():
        if name in COMMAND_LINES:
            continue
        for module, line in _resolved_imports(path):
            assert _package_part(module) not in COMMAND_LINES, f"{path.relative_to(PACKAGE)}:{line}: imports {module}"


def test_tf13_29_a_the_api_touches_no_command_and_commands_no_command_line() -> None:
    modules = source_modules()
    core = [n for n in modules if n in ("poisson_trace.api", "poisson_trace.core")
            or n.startswith(("poisson_trace.api.", "poisson_trace.core."))]
    assert "poisson_trace.api" in core
    for name in core:
        for module, line in _resolved_imports(modules[name]):
            part = _package_part(module)
            assert part not in COMMAND_LINES, f"{modules[name].name}:{line}: imports {module}"
            assert part != "poisson_trace.commands" and not (part or "").startswith("poisson_trace.commands."), \
                f"{modules[name].name}:{line}: the API imports the environment's commands"
    for name in [n for n in modules if n == "poisson_trace.commands" or n.startswith("poisson_trace.commands.")]:
        for module, line in _resolved_imports(modules[name]):
            assert _package_part(module) not in COMMAND_LINES, f"{modules[name].name}:{line}: imports {module}"


# ---------- TF13-30 ----------


class Spy:
    """A function of the API, watched: each call's arguments kept, the real function run (or a
    stand-in result returned, or a refusal raised)."""

    def __init__(self, real: Any, returns: Any = None, raises: BaseException | None = None) -> None:
        self.real, self.returns, self.raises = real, returns, raises
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        if self.raises is not None:
            raise self.raises
        if self.returns is not None:
            return self.returns
        return self.real(*args, **kwargs)


def _store_word(value: Any) -> Any:
    a = api()
    return str(value.path) if isinstance(value, a.Store) else value


def _config_word(value: Any) -> Any:
    a = api()
    return "<a config>" if isinstance(value, a.Config) else value


WATCHED = ["where", "where by step", "compare at", "fix-check max-change", "fix-check verdicts", "changes top",
           "runs all", "where config", "changes config name"]


@pytest.mark.parametrize("label", WATCHED)
def test_tf13_30_each_verb_calls_its_function_once_with_its_inputs(tmp_path: Path, label: str, monkeypatch: pytest.MonkeyPatch) -> None:
    work = workspace(tmp_path)
    argv = VERBS_ARGV[label]
    unwatched = cli(work, argv)
    call = call_for(argv)
    a = api()
    spy = Spy(getattr(a, call.function))
    monkeypatch.setattr(a, call.function, spy)
    ran = cli(work, argv)
    assert (ran.code, ran.out, ran.err) == (unwatched.code, unwatched.out, unwatched.err)
    assert len(spy.calls) == 1, spy.calls
    args, kwargs = spy.calls[0]
    assert _store_word(args[0]) == call.args[0], (args[0], call.args[0])
    assert list(args[1:]) == list(call.args[1:])
    from poisson_trace import cli as the_cli

    _top, verbs = the_cli.parsers()
    given = {w.split("=", 1)[0] for w in argv if w.startswith("--")}
    for action in options_of(verbs[argv[0]]):
        if not set(action.option_strings) & given or set(action.option_strings) & {"--store"}:
            continue
        name = keyword(action)
        if name == "config":
            assert _config_word(kwargs[name]) in (call.kwargs[name], "<a config>"), kwargs[name]
            continue
        assert plain_default(kwargs[name]) == plain_default(call.kwargs[name]), (name, kwargs.get(name))


@pytest.mark.parametrize("label", ["where", "compare", "fix-check", "changes", "runs"])
def test_tf13_30_a_the_command_line_prints_what_the_function_returns(tmp_path: Path, label: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Handed a result of another invocation, the command prints that result: it made nothing
    of its own."""
    work = workspace(tmp_path)
    other = {"where": VERBS_ARGV["where by step"], "compare": VERBS_ARGV["compare at"],
             "fix-check": VERBS_ARGV["fix-check top"], "changes": VERBS_ARGV["changes top"],
             "runs": VERBS_ARGV["runs no event"]}[label]
    from tf13_support import attempt

    canned = attempt(call_for(other), work).result
    a = api()
    monkeypatch.setattr(a, call_for(VERBS_ARGV[label]).function, Spy(None, returns=canned))
    plain, as_json = cli(work, VERBS_ARGV[label]), cli(work, [*VERBS_ARGV[label], "--json"])
    assert plain.out == canned.to_markdown() and as_json.out == canned.to_json()
    assert plain.code == canned.exit_code
    assert [line for line in plain.err.splitlines() if line.startswith("note: ")] == [f"note: {n}" for n in canned.notes]


@pytest.mark.parametrize("code", [1, 2, 3])
def test_tf13_30_b_a_refusal_the_api_raises_is_the_commands_error(tmp_path: Path, code: int, monkeypatch: pytest.MonkeyPatch) -> None:
    work = workspace(tmp_path)
    a = api()
    # a failure after work started (exit 3) is one line, with no command under it (the look's rule)
    nexts = ("poisson-trace runs --store zq",) if code != 3 else ()
    refusal = a.Refusal("zq-sentinel-13 cannot be read", next=nexts, exit_code=code,
                        notes=("zq-note-13 was left out",))
    cases = [
        ("where", lambda: cli(work, VERBS_ARGV["where"])),
        ("fix_check", lambda: cli(work, [*VERBS_ARGV["fix-check"], "--json"])),
        ("runs", lambda: cli(work, VERBS_ARGV["runs"])),
        ("import_run", lambda: cli_import(work, IMPORT_ARGV["junit"])),
        ("import_run", lambda: cli(work, ["import", *IMPORT_ARGV["junit"]])),
        ("name", lambda: cli(work, ["name", "agent after", "shipped", "--store", "store"])),
        ("list_names", lambda: cli(work, ["name", "--list", "--store", "store"])),
        ("validate_bundle", lambda: cli(work, ["handover", "--check", "conf"])),
    ]
    for function, run in cases:
        with monkeypatch.context() as m:
            m.setattr(a, function, Spy(None, raises=refusal))
            ran = run()
        assert ran.code == code and ran.out == "", (function, ran.text)
        assert ran.err == ("note: zq-note-13 was left out\nerror: zq-sentinel-13 cannot be read\n"
                           + "".join(f"  next: {n}\n" for n in nexts)), (function, ran.err)


def test_tf13_30_c_the_import_name_and_handover_call_their_functions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work = workspace(tmp_path)
    a = api()
    spies = {f: Spy(getattr(a, f)) for f in ("import_run", "name", "forget_name", "list_names", "validate_bundle", "save")}
    for f, spy in spies.items():
        monkeypatch.setattr(a, f, spy)
    assert cli_import(work, IMPORT_ARGV["junit"]).code == 0
    assert cli(work, ["import", *IMPORT_ARGV["ragas"]]).code == 0
    assert len(spies["import_run"].calls) == 2
    args, kwargs = spies["import_run"].calls[0]
    call = import_call_for(IMPORT_ARGV["junit"])
    assert _store_word(args[0]) == call.args[0] and list(args[1:]) == list(call.args[1:])
    assert {k: kwargs[k] for k in ("run", "started")} == {"run": "suite-a", "started": call.kwargs["started"]}
    args, kwargs = spies["import_run"].calls[1]
    assert kwargs["metric"] == "faithfulness" and kwargs["cut"] == "0.5" and kwargs["below"] is True
    assert kwargs["case_column"] == "case"
    assert cli(work, ["name", "agent after", "shipped", "--store", "store"]).code == 0
    assert cli(work, ["name", "--list", "--store", "store"]).code == 0
    assert cli(work, ["name", "shipped", "--forget", "--store", "store"]).code == 0
    assert [len(spies[f].calls) for f in ("name", "list_names", "forget_name")] == [1, 1, 1]
    assert spies["name"].calls[0][0][1:] == ("agent after", "shipped")
    assert cli(work, [*VERBS_ARGV["fix-check"], "--save"]).code == 0
    assert len(spies["save"].calls) == 1
    assert cli(work, [*VERBS_ARGV["fix-check"], "--out", "bundle"]).code == 0
    assert cli(work, ["handover", "--check", "bundle"]).code == 0
    assert len(spies["validate_bundle"].calls) == 1 and spies["validate_bundle"].calls[0][0] == ("bundle",)


def test_tf13_30_d_the_deliveries_are_the_results_methods(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work = workspace(tmp_path)
    from tf13_support import attempt

    kind = type(attempt(call_for(VERBS_ARGV["where"]), work).result)
    seen: list[str] = []
    for method in ("to_bundle", "write_svg"):
        real = getattr(kind, method)

        def watched(self: Any, *args: Any, real: Any = real, method: str = method, **kwargs: Any) -> Any:
            seen.append(method)
            return real(self, *args, **kwargs)

        monkeypatch.setattr(kind, method, watched)
    assert cli(work, [*VERBS_ARGV["where"], "--svg", "curve.svg", "--out", "bundle"]).code == 0
    assert sorted(seen) == ["to_bundle", "write_svg"]


def test_tf13_30_e_doctor_and_init_call_their_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work = workspace(tmp_path)
    c = commands()
    doctor = Spy(c.doctor)
    monkeypatch.setattr(c, "doctor", doctor)
    ran = cli(work, ["doctor", "--config", "conf/trace.toml", "--json"])
    assert len(doctor.calls) == 1
    given = doctor.calls[0][1].get("config")
    assert given == "conf/trace.toml" or _config_word(given) == "<a config>", given
    assert json.loads(ran.out)["schema"] == "poisson-trace.doctor/1"
    init = Spy(c.init)
    monkeypatch.setattr(c, "init", init)
    folder = tmp_path / "fresh"
    folder.mkdir()
    import shutil

    shutil.copytree(work / "store", folder / "runs")
    ran = cli(folder, ["init", "--yes", *EV])
    assert ran.code == 0, ran.text
    assert len(init.calls) == 1
    args, kwargs = init.calls[0]
    assert args == () and kwargs["yes"] is True and plain_default(kwargs["event"]) == ("violated", "timeout")
    assert jsonable(kwargs.get("store")) in (None, [])


# ---------- TF13-31 ----------


def test_tf13_31_tr40_follows_the_code_into_the_api() -> None:
    """In ``api``, ``core`` and ``commands`` (module or package): no string constant
    ``"replicate_index"`` and no attribute of that name; no string constant ``"seed"`` but as a
    key of a dict literal; no attribute ``.seed`` but on the parsed arguments ``ns``."""
    modules = source_modules()
    names = [n for n in modules if n.split(".")[1:2] and n.split(".")[1] in ("api", "core", "commands")]
    assert "poisson_trace.api" in names
    for name in names:
        path = modules[name]
        tree = ast.parse(path.read_text(encoding="utf-8"))
        dict_keys = {id(k) for node in ast.walk(tree) if isinstance(node, ast.Dict) for k in node.keys if k is not None}
        for node in ast.walk(tree):
            where = f"{path.relative_to(PACKAGE)}:{getattr(node, 'lineno', '?')}"
            if isinstance(node, ast.Constant) and node.value == "replicate_index":
                raise AssertionError(f"{where}: replicate_index")
            if isinstance(node, ast.Constant) and node.value == "seed" and id(node) not in dict_keys:
                raise AssertionError(f"{where}: 'seed' read")
            if isinstance(node, ast.Attribute) and node.attr == "replicate_index":
                raise AssertionError(f"{where}: .replicate_index")
            if isinstance(node, ast.Attribute) and node.attr == "seed":
                assert isinstance(node.value, ast.Name) and node.value.id == "ns", f"{where}: .seed"
