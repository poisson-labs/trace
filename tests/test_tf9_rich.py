"""TF9, invariant 5: Rich is a core dependency, imported only by one private rendering module (spec
section 17.1; the look file's rule 16: "Rich is an ordinary dependency, not an optional extra").

- **TF9-5a** ``pyproject.toml`` declares ``rich`` among the project's dependencies, not under an
  extra, and the installed package's metadata says the same.
- **TF9-5b** The one module that imports Rich is ``poisson_trace._pretty``: no other file under
  ``src/`` imports it, by an ``import`` statement or by naming it to an import function, and
  ``_pretty`` does. The terminal app's modules (``poisson_trace/_app*.py``) are the one
  exception: Textual draws through Rich, and Prove's shell, which Trace's app copies, imports
  Rich's ``Text`` (section 17.2, AD5; TF19's FT3).
"""

from __future__ import annotations

import ast
import importlib.metadata
import re
import tomllib

from tf9_support import PRETTY_FILE, REPO, SRC

_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _name(requirement: str) -> str:
    m = _NAME.match(requirement)
    assert m, requirement
    return m.group(1).lower().replace("_", "-")


def test_tf9_5a_rich_is_a_core_dependency() -> None:
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert "rich" in [_name(r) for r in project["dependencies"]]
    for extra, listed in project.get("optional-dependencies", {}).items():
        assert "rich" not in [_name(r) for r in listed], f"rich is under the extra {extra}"
    installed = importlib.metadata.requires("poisson-trace") or []
    core = [r for r in installed if "extra ==" not in r]
    assert "rich" in [_name(r) for r in core], "the installed metadata does not require rich"


def _imports_rich(path: str, tree: ast.AST) -> list[str]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name == "rich" or a.name.startswith("rich.") for a in node.names):
            found.append(f"{path}:{node.lineno}")
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and (node.module == "rich" or node.module.startswith("rich.")):
            found.append(f"{path}:{node.lineno}")
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            target = node.args[0].value
            func = node.func
            called = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
            if called in ("import_module", "__import__", "find_spec") and (target == "rich" or target.startswith("rich.")):
                found.append(f"{path}:{node.lineno}")
    return found


def test_tf9_5b_only_the_private_rendering_module_imports_rich() -> None:
    importing: dict[str, list[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        found = _imports_rich(rel, ast.parse(path.read_text(encoding="utf-8"), filename=rel))
        if found:
            importing[rel] = found
    assert PRETTY_FILE.exists(), "there is no poisson_trace/_pretty.py"
    # the terminal app's modules draw through Textual, which is built on Rich (TF19's FT3)
    app = [k for k in importing if k.startswith("poisson_trace/_app")]
    assert [k for k in importing if k not in app] == ["poisson_trace/_pretty.py"], importing
