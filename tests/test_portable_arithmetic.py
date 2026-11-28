"""The numbers Trace computes use only arithmetic that gives the same bits on every platform,
read from the source.

Each number module is parsed and refused on:

- an import of scipy, and every call through it;
- a call to a numpy or ``math`` function that the platform's math library or a vectorised
  path computes (exp, log, the trigonometric functions, power and their kin);
- a BLAS call (``convolve``, ``correlate``, ``dot``, ``vdot``, ``inner``, ``tensordot``,
  ``matmul``, ``einsum``, or the ``@`` operator) outside ``survival._resampled_incidence``,
  which multiplies integer-valued arrays whose sums are exact in any order;
- a ``**`` whose left operand is not an integer literal: a float ``**`` calls ``pow``;
- a call to the builtin ``sum``: integers go through ``portable.isum`` and floats through
  ``math.fsum``;
- a numpy reduction (``.sum``, ``np.sum``, ``.mean``, ``np.mean``, ``.std``, ``np.std``,
  ``np.average``, ``np.nansum``) whose operand is not a comparison or a boolean combination of
  comparisons, since numpy chooses the order a float sum is added in.

A second test holds the list of number modules to the commands' imports: a module the commands
import that calls numpy, scipy or ``math`` is either a number module or exempt, with its reason.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from portable_support import EXEMPT, NUMBER_MODULES, SRC

NUMPY_FORBIDDEN = frozenset({
    "exp", "expm1", "log", "log1p", "log2", "log10", "sin", "cos", "tan", "arcsin", "arccos",
    "arctan", "arctan2", "sinh", "cosh", "tanh", "power", "float_power", "cbrt", "hypot",
})
MATH_FORBIDDEN = frozenset({
    "exp", "expm1", "log", "log1p", "log2", "log10", "pow", "sin", "cos", "tan", "asin", "acos",
    "atan", "atan2", "erf", "erfc", "gamma", "lgamma", "hypot", "dist", "prod",
})
BLAS = frozenset({"convolve", "correlate", "dot", "vdot", "inner", "tensordot", "matmul", "einsum"})
METHOD_REDUCTIONS = frozenset({"sum", "mean", "std"})
NUMPY_REDUCTIONS = frozenset({"sum", "mean", "std", "average", "nansum"})
#: The one function where an integer-valued product of arrays is allowed.
ALLOWED_PRODUCT = ("survival.py", "_resampled_incidence")


def _is_count(node: ast.AST) -> bool:
    """A comparison, or a boolean combination of comparisons."""
    if isinstance(node, ast.Compare):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.BitAnd, ast.BitOr, ast.BitXor)):
        return _is_count(node.left) and _is_count(node.right)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.Invert, ast.Not)):
        return _is_count(node.operand)
    if isinstance(node, ast.BoolOp):
        return all(_is_count(value) for value in node.values)
    return False


def _aliases(tree: ast.Module, module: str) -> set[str]:
    """The names a module is bound to: ``import numpy as np`` gives ``np``."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module:
                    names.add(alias.asname or module)
    return names


def _scipy_names(tree: ast.Module) -> set[str]:
    """The names scipy, or a part of it, is bound to anywhere in the module."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "scipy":
                    names.add(alias.asname or "scipy")
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0 and node.module.split(".")[0] == "scipy":
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def violations(path: Path, name: str) -> list[str]:
    """Every place in ``path`` that breaks the rule, as ``file:line: what``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    numpy_names, math_names = _aliases(tree, "numpy"), _aliases(tree, "math")
    scipy_names = _scipy_names(tree)
    found: list[str] = []

    def say(node: ast.AST, what: str) -> None:
        found.append(f"src/poisson_trace/{name}:{getattr(node, 'lineno', 0)}: {what}")

    def visit(node: ast.AST, function: str | None) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function = node.name
        allowed_product = (name, function) == ALLOWED_PRODUCT
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "scipy":
                    say(node, f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            root = node.module.split(".")[0]
            if root == "scipy":
                say(node, f"from {node.module} import ...")
            for alias in node.names:
                if root == "numpy" and alias.name in NUMPY_FORBIDDEN | BLAS | NUMPY_REDUCTIONS:
                    say(node, f"from numpy import {alias.name}")
                if root == "math" and alias.name in MATH_FORBIDDEN:
                    say(node, f"from math import {alias.name}")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            if not (isinstance(node.left, ast.Constant) and type(node.left.value) is int):
                say(node, f"{ast.unparse(node)} (** on an operand that is not an integer literal)")
        elif isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Pow):
            say(node, f"{ast.unparse(node)} (**=)")
        if isinstance(node, (ast.BinOp, ast.AugAssign)) and isinstance(node.op, ast.MatMult) and not allowed_product:
            say(node, f"{ast.unparse(node)} (the @ operator)")
        if isinstance(node, ast.Call):
            func = node.func
            root = func
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name) and root.id in scipy_names:
                say(node, f"{ast.unparse(func)} (scipy)")
            if isinstance(func, ast.Name) and func.id == "sum":
                say(node, f"{ast.unparse(node)} (builtin sum)")
            elif isinstance(func, ast.Attribute):
                base = func.value.id if isinstance(func.value, ast.Name) else None
                if base in numpy_names:
                    if func.attr in NUMPY_FORBIDDEN:
                        say(node, f"{base}.{func.attr}")
                    elif func.attr in BLAS and not allowed_product:
                        say(node, f"{base}.{func.attr}")
                    elif func.attr in NUMPY_REDUCTIONS and not (node.args and _is_count(node.args[0])):
                        say(node, f"{ast.unparse(node)} (a numpy float reduction)")
                elif base in math_names:
                    if func.attr in MATH_FORBIDDEN:
                        say(node, f"{base}.{func.attr}")
                elif func.attr in METHOD_REDUCTIONS and not _is_count(func.value):
                    say(node, f"{ast.unparse(node)} (a numpy float reduction)")
                elif func.attr in BLAS and not allowed_product:
                    say(node, f"{ast.unparse(node)} (a BLAS product)")
        for child in ast.iter_child_nodes(node):
            visit(child, function)

    visit(tree, None)
    return found


@pytest.mark.parametrize("name", NUMBER_MODULES)
def test_each_number_module_computes_with_portable_arithmetic_only(name: str) -> None:
    path = SRC / name
    assert path.is_file(), f"src/poisson_trace/{name} is a number module and is not there"
    found = violations(path, name)
    assert not found, f"{len(found)} calls whose result can differ by platform:\n" + "\n".join(found)


def _module(path: Path) -> str:
    parts = path.relative_to(SRC.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imports(path: Path, here: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = here if path.name == "__init__.py" else here.rsplit(".", 1)[0]
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[: len(base) - (node.level - 1)]
                module = ".".join([*base, node.module] if node.module else base)
            else:
                module = node.module or ""
            found.add(module)
            found.update(f"{module}.{alias.name}" for alias in node.names)
    return found


def _calls_numeric(path: Path) -> bool:
    """Whether the module calls a function of numpy, scipy or ``math``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bound = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in ("numpy", "scipy", "math"):
                    bound.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if node.module.split(".")[0] in ("numpy", "scipy", "math"):
                bound.update(alias.asname or alias.name for alias in node.names)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            while isinstance(func, ast.Attribute):
                func = func.value
            if isinstance(func, ast.Name) and func.id in bound:
                return True
    return False


def test_every_module_the_commands_import_that_does_arithmetic_is_listed() -> None:
    modules = {_module(path): path for path in SRC.rglob("*.py")}
    graph = {name: {m for m in _imports(path, name) if m in modules} for name, path in modules.items()}
    reached: set[str] = set()
    todo = ["poisson_trace.core", "poisson_trace.api", "poisson_trace.cli"]
    while todo:
        name = todo.pop()
        if name not in reached:
            reached.add(name)
            todo.extend(graph[name])
    listed = {f"poisson_trace.{n.removesuffix('.py').replace('/', '.')}" for n in (*NUMBER_MODULES, *EXEMPT)}
    unlisted = sorted(name for name in reached if _calls_numeric(modules[name]) and name not in listed)
    assert not unlisted, (
        "imported by the commands, calling numpy, scipy or math, and neither a number module nor "
        f"exempt with its reason in tests/portable_support.py: {unlisted}"
    )
    both = sorted(set(NUMBER_MODULES) & set(EXEMPT))
    assert not both, f"listed as a number module and as exempt: {both}"
    for name, reason in EXEMPT.items():
        assert reason.strip(), f"{name} is exempt with no reason"
