"""TF16-1 to TF16-3: Trace reads Prove under its new name (spec section 16.1 step 1, section 8.2
as amended 2026-10-28, section 17.3).

- TF16-1: no module of the package imports ``proofload``, and every name it imports from
  ``poisson_prove`` is one Prove documents as public (Prove's ``docs/python.md`` in poisson-prove 0.1.2);
  none comes from a private module.
- TF16-2: where ``poisson_prove`` cannot be imported at the version Trace reads, every command
  that reads or writes runs refuses before it opens anything: one ``error:`` line naming
  ``poisson-prove`` and the version, never ``proofload``, then the line that installs it from
  PyPI. ``proofload`` 0.0.1, the pin Trace had before, does not satisfy it.
- TF16-3: ``--version`` names the ``poisson-prove`` it finds, and only that: with ``proofload``
  0.0.1 alone it says ``poisson-prove not installed``.
"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

import pytest

from tf16_support import INSTALL_PROVE, NEW, PROVE_VERSION, REPO, fresh, scratch_home  # noqa: F401

SOURCE = REPO / "src" / "poisson_trace"

# Prove's public Python surface, as its docs/python.md lists it in 0.1.2: each module and the
# names it makes public. Everything else under poisson_prove is private.
PUBLIC = {
    "poisson_prove": {"Episode", "EpisodeValidationError", "Rollout", "record", "step", "__version__"},
    "poisson_prove.store": {"Store", "RunManifest", "EpisodeRecord", "RunTally", "config_hash",
                            "StoreError", "SchemaMismatch"},
    "poisson_prove.trace": {
        "Span", "Trace", "Declaration", "SpanHandle", "Collector", "collect", "record", "step",
        "from_otel", "from_litellm", "merge", "split", "assemble", "finalize",
        "truncate_observations", "TraceValidationError", "SCHEMA", "KINDS", "CONTENT_KEYS",
        "OBSERVATION_KEYS", "OBSERVATION_ROUTING_BYTES", "TRUNCATED_KEY", "LOGPROBS_KEY", "GATE",
        "OUTCOME_BY", "SOURCES", "DROP_REASONS", "ATTRIBUTE_ALIASES", "ALIAS_MAP_VERSION",
        "OTEL_KIND_MAP", "OTEL_SEMCONV_VERSION",
    },
    "poisson_prove.steps": {"declaration_check", "DeclarationCheck"},
    "poisson_prove.stats": {
        "wilson", "WilsonInterval", "WILSON_LEVEL", "POWER", "kaplan_meier", "KMCurve",
        "aalen_johansen", "CIFCurve", "bh", "holm", "interval_rd", "interval_rd_paired",
        "mde_two_proportion", "fisher_test", "mcnemar_test", "logrank_test",
    },
    "poisson_prove.compare": {"diff", "check", "runs", "resolve", "Comparison", "CheckResult",
                              "RunInfo", "Refusal"},
}


def _imports(path: Path) -> list[tuple[str, str | None, int]]:
    """Each module a file imports, with the name taken from it (None for ``import M``)."""
    out: list[tuple[str, str | None, int]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out += [(a.name, None, node.lineno) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out += [(node.module, a.name, node.lineno) for a in node.names]
    return out


# ---------- TF16-1 ----------


def test_tf16_1_trace_imports_prove_as_poisson_prove_and_only_its_public_names() -> None:
    files = sorted(SOURCE.rglob("*.py"))
    assert files
    seen = set()
    for path in files:
        where = path.relative_to(REPO)
        for module, name, line in _imports(path):
            top = module.split(".")[0]
            assert top != "proofload", f"{where}:{line} imports {module}"
            if top != "poisson_prove":
                continue
            seen.add(module)
            if name is None:
                # ``import poisson_prove`` reads __version__; ``import poisson_prove.x`` would
                # reach a module whole, public or not
                assert module == "poisson_prove", f"{where}:{line} imports {module} whole"
                continue
            if module == "poisson_prove" and name in PUBLIC:
                continue  # from poisson_prove import store: a public module, by its name
            assert module in PUBLIC, f"{where}:{line} imports the private module {module}"
            assert name in PUBLIC[module], f"{where}:{line} imports {module}.{name}, which Prove does not make public"
    # the package reads runs through Prove's store: a build that stopped importing it is no move
    assert "poisson_prove.store" in seen, seen


# ---------- TF16-2 ----------


def _files(root: Path) -> list[Path]:
    """Every path under ``root`` but the scratch home's."""
    return sorted(p.relative_to(root) for p in root.rglob("*") if p.relative_to(root).parts[0] != "home")

# a command of each kind that reads or writes runs: the listing, a verb of two runs, a name
# written, an import
COMMANDS = {
    "runs": ["runs", "--store", "STORE"],
    "fix-check": ["fix-check", "#2", "#1", "--store", "STORE", "--event", "violated", "--inputs", "all", "--max-mde", "0.5"],
    "name": ["name", "#1", "a name", "--store", "STORE"],
    "import": ["import", "junit", REPO / "tests" / "fixtures" / "ingest" / "junit" / "trace-suite-1.xml",
               "--store", "STORE", "--run", "suite"],
}
# a Prove below the floor: 9.9.9, the stand-in before the floor, is one Trace now reads (ruled 2026-11-17, PV-4)
STATES = {"absent": "absent", "proofload 0.0.1 alone": "old", "poisson_prove 0.3.0": "0.3.0"}


@pytest.mark.parametrize("state", list(STATES))
@pytest.mark.parametrize("command", list(COMMANDS))
def test_tf16_2_without_poisson_prove_at_its_version_a_command_refuses_naming_it(
    tmp_path: Path, command: str, state: str
) -> None:
    store = tmp_path / "store"
    if command != "import":
        shutil.copytree(NEW, store)
    before = _files(tmp_path)
    argv = [store if a == "STORE" else a for a in COMMANDS[command]]
    ran = fresh(argv, prove=STATES[state], cwd=tmp_path)
    assert ran.code == 1, ran.text
    assert ran.out == "", ran.out
    lines = ran.err_lines()
    assert lines[0].startswith("error: "), lines
    assert "poisson-prove" in lines[0] and PROVE_VERSION in lines[0], lines[0]
    if state == "poisson_prove 0.3.0":
        assert "0.3.0" in lines[0], lines[0]
    assert "proofload" not in ran.text, ran.text
    assert f"  next: {INSTALL_PROVE}" in lines[1:], lines
    assert all(line.startswith("  next: ") for line in lines[1:]), lines
    assert _files(tmp_path) == before


# ---------- TF16-3 ----------


def test_tf16_3_the_version_line_names_poisson_prove_and_not_the_old_package(tmp_path: Path) -> None:
    ran = fresh(["--version"], prove="old", cwd=tmp_path)
    assert ran.code == 0, ran.text
    (line,) = ran.out.splitlines()
    assert "(poisson-prove not installed, Python " in line, line
    assert "proofload" not in ran.text and ran.err == ""
