"""TF19-8: built on Prove's app shell (spec section 17.2, AD5; A1).

**TF19-8** Trace's private copy of Prove's shell, ``poisson_trace/_app_shell.py``, names the Prove
commit it was copied from (``PROVE_COMMIT``, the fixture's ``commit``: Prove's ``main`` at
``d04e378``, whose two app files are byte for byte those of the 0.1.3 release Trace pins), and
every definition the fixture lists is that commit's, its syntax tree equal to Prove's once the
fixture's renames are made (``poisson-prove`` to ``poisson-trace``): the bands, the key bar, the
focus marker, the message line, the width and line-break rules. A method of Prove's ``ProveApp``
is a method of the shell's class ``Shell``. The installed Prove's two files are the commit's, so
the comparison reads that commit's bytes without the network. The app imports none of Prove's
private modules; Textual is imported by the app's modules alone, and nothing else Trace imports
loads it; Textual is a declared dependency.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from tf19_support import PACKAGE, PROVE_SHELL, REPO, SHELL_MODULE, app_files, imports_of

SHELL = json.loads(PROVE_SHELL.read_text(encoding="utf-8"))


def _prove_file(name: str) -> Path:
    spec = importlib.util.find_spec("poisson_prove")
    assert spec is not None and spec.origin is not None
    return Path(spec.origin).parent / name


def _definitions(tree: ast.Module) -> dict[str, ast.AST]:
    """Every top-level function, class and assigned name, and each method as ``Class.method``."""
    out: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = node
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        out[f"{node.name}.{item.name}"] = item
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for name in ([target] if isinstance(target, ast.Name) else getattr(target, "elts", [])):
                    if isinstance(name, ast.Name):
                        out[name.id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out[node.target.id] = node
    return out


class _Renamed(ast.NodeTransformer):
    def __init__(self, renames: dict[str, str]) -> None:
        self.renames = renames

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, str):
            value = node.value
            for old, new in self.renames.items():
                value = value.replace(old, new)
            return ast.copy_location(ast.Constant(value), node)
        return node

    def visit_Name(self, node: ast.Name) -> ast.AST:
        return ast.copy_location(ast.Name(self.renames.get(node.id, node.id), node.ctx), node)


def _dump(node: ast.AST, renames: dict[str, str] | None = None) -> str:
    import copy

    node = copy.deepcopy(node)
    if renames:
        node = _Renamed(renames).visit(node)
    return ast.dump(node, include_attributes=False)


def _shell_tree() -> ast.Module:
    path = PACKAGE / "_app_shell.py"
    assert path.is_file(), "the shell's copy is poisson_trace/_app_shell.py"
    return ast.parse(path.read_text(encoding="utf-8"))


def test_tf19_8_the_copy_names_the_prove_commit() -> None:
    import importlib

    shell = importlib.import_module(SHELL_MODULE)
    assert shell.PROVE_COMMIT == SHELL["commit"]


@pytest.mark.parametrize("name", sorted(SHELL["files"]))
def test_tf19_8_the_installed_prove_is_the_commit(name: str) -> None:
    """The installed Prove's app files are the named commit's (and the 0.1.3 release's), so the
    copy is compared with that commit's bytes; a moved Prove pin shows here."""
    data = _prove_file(name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == SHELL["files"][name]


COPIED = [(f, n) for f, names in SHELL["copied"].items() for n in names]


@pytest.mark.parametrize(("source", "name"), COPIED, ids=[f"{f}:{n}" for f, n in COPIED])
def test_tf19_8_each_definition_is_the_commits(source: str, name: str) -> None:
    prove = _definitions(ast.parse(_prove_file(source).read_text(encoding="utf-8")))
    trace = _definitions(_shell_tree())
    theirs = prove[name]
    ours_name = name.replace("ProveApp.", "Shell.")
    assert ours_name in trace, f"{ours_name} is not in poisson_trace/_app_shell.py"
    assert _dump(trace[ours_name]) == _dump(theirs, SHELL["renamed"]), name


def test_tf19_8_the_app_imports_no_private_module_of_prove() -> None:
    files = app_files()
    assert any(p.name == "_app.py" for p in files) and any(p.name == "_app_shell.py" for p in files)
    for path in files:
        private = sorted(m for m in imports_of(path) if m.startswith("poisson_prove._") or m.startswith("poisson_prove") and "._" in m)
        assert private == [], (path.name, private)


def test_tf19_8_nothing_in_trace_imports_prove_s_app() -> None:
    for path in sorted(PACKAGE.rglob("*.py")):
        names = imports_of(path)
        assert not {m for m in names if m.startswith(("poisson_prove._cli_app", "poisson_prove._cli_app_pages"))}, path


def test_tf19_8_textual_is_imported_by_the_app_s_modules_alone() -> None:
    app = {p.resolve() for p in app_files()}
    for path in sorted(PACKAGE.rglob("*.py")):
        uses = {m for m in imports_of(path) if m == "textual" or m.startswith("textual.")}
        if path.resolve() in app:
            continue
        assert not uses, (path, uses)
    assert any("textual" in {m.split(".")[0] for m in imports_of(p)} for p in app_files())


def test_tf19_8_the_rest_of_trace_does_not_load_textual() -> None:
    """Importing every module but the app's leaves Textual unloaded: a verb never pays for it."""
    modules = sorted(
        "poisson_trace." + ".".join(p.relative_to(PACKAGE).with_suffix("").parts)
        for p in PACKAGE.rglob("*.py")
        if not p.name.startswith("_app") and p.name != "__main__.py" and "skills" not in p.parts
    )
    code = (
        "import importlib, sys\n"
        f"for m in {modules!r}:\n"
        "    importlib.import_module(m.removesuffix('.__init__'))\n"
        "print(sorted(m for m in sys.modules if m == 'textual' or m.startswith('textual.')))\n"
    )
    ran = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd=REPO)
    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.strip() == "[]", ran.stdout


def test_tf19_8_textual_is_a_declared_dependency() -> None:
    doc = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    deps = doc["project"]["dependencies"]
    assert any(d.split(">")[0].split("=")[0].split("<")[0].strip().lower() == "textual" for d in deps), deps
