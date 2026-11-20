"""TF0-11 to TF0-13: ``--version``, ``python -m poisson_trace``, and help a stranger can act on
(rules 1 and 2 of ``docs/cli-look.md``).

Every verb's help has a description, every argument with help text, every option that takes a
value with its default or "no default". The usage line shows the two
ceilings as required, though a missing one stays the command's own refusal (exit 1), because the
value may come from a config later."""

from __future__ import annotations

import os
import re
import sys
from importlib.metadata import version
from pathlib import Path

import pytest

from look_support import (
    TOOLS, VERBS, compare_tau2, depth_at, fix_check_tau2_all,
    help_blocks, help_entries, run_module, run_sub, trace, trace_import, usage_line, where_cs,
)

TRACE_VERSION = version("poisson-trace")
PYTHON = ".".join(str(n) for n in sys.version_info[:3])
VERSION_LINE = re.compile(r"^poisson-trace(?:-import)? (\S+) \(poisson-prove (\S+), Python (\d+\.\d+\.\d+)\)$")

HELPS = [("trace", [])] + [("trace", [v]) for v in VERBS] + [("import", [])] + [("import", [t]) for t in TOOLS]
HELP_IDS = ["poisson-trace"] + list(VERBS) + ["import"] + [f"import {t}" for t in TOOLS]


def _help(command: str, words: list[str]) -> str:
    result = (trace if command == "trace" else trace_import)([*words, "--help"])
    assert result.code == 0 and result.err == "", result.text
    return result.out


# ---------- TF0-13: help ----------


@pytest.mark.parametrize("command,words", HELPS, ids=HELP_IDS)
def test_tf0_13_help_opens_with_a_description(command: str, words: list[str]) -> None:
    blocks = help_blocks(_help(command, words))
    assert blocks[0].startswith("usage:")
    description = blocks[1] if len(blocks) > 1 else ""
    assert not re.match(r"^\S[^\n]*:\n", description + "\n"), "the block after usage is a description, not a list"
    assert len(description.split()) >= 8 and "." in description, description


@pytest.mark.parametrize("command,words", HELPS, ids=HELP_IDS)
def test_tf0_13_every_argument_says_what_it_is_and_its_default(command: str, words: list[str]) -> None:
    text = _help(command, words)
    entries = help_entries(text)
    assert entries, text
    for invocation, words_ in entries:
        if invocation.startswith("-h, --help"):
            continue
        assert words_, f"{invocation} has no help text"
        takes_value = invocation.startswith("-") and " " in invocation.split(",")[-1].strip()
        if takes_value:
            assert "default" in words_, f"{invocation}: {words_}"
    assert not re.search(r"\b(?:None|True|False)\b|\[\]", text), "a Python value shown as a default"


@pytest.mark.parametrize("verb,flag", [("compare", "--max-mde-hr"), ("fix-check", "--max-mde")])
def test_tf0_13_the_ceiling_is_shown_required_and_its_absence_is_a_refusal(verb: str, flag: str) -> None:
    usage = usage_line(_help("trace", [verb]))
    at = [m.start() for m in re.finditer(re.escape(flag) + r" [A-Z][A-Z_-]*(?![\w-])", usage)]
    assert at and all(depth_at(usage, i) == 0 for i in at), usage
    argv = compare_tau2("1.5") if verb == "compare" else fix_check_tau2_all("0.2")
    missing = trace(argv[: argv.index(flag)] + argv[argv.index(flag) + 2 :])
    assert missing.code == 1 and missing.out == "", missing.text


# ---------- TF0-11: --version ----------
# The import gets it too, as the main command does. Prove's version is read from the imported
# module.


@pytest.mark.parametrize("command", ["trace", "import"])
def test_tf0_11_version_names_trace_prove_and_python(command: str) -> None:
    import poisson_prove

    result = (trace if command == "trace" else trace_import)(["--version"])
    assert result.code == 0 and result.err == "", result.text
    lines = result.out.splitlines()
    assert len(lines) == 1, result.out
    m = VERSION_LINE.match(lines[0])
    assert m is not None, lines[0]
    assert m.groups() == (TRACE_VERSION, poisson_prove.__version__, PYTHON), lines[0]


@pytest.mark.parametrize("command", ["trace", "import"])
def test_tf0_11_version_names_the_prove_that_is_installed_or_none(command: str) -> None:
    other = run_sub(command, ["--version"], prove="9.9.9")
    assert other.code == 0, other.text
    m = VERSION_LINE.match(other.out.strip())
    assert m is not None and m.group(2) == "9.9.9", other.out
    none = run_sub(command, ["--version"], prove="absent")
    assert none.code == 0, none.text
    line = none.out.strip()
    assert re.match(rf"^poisson-trace(?:-import)? {re.escape(TRACE_VERSION)} \(poisson-prove not installed(?:, Python {re.escape(PYTHON)})?\)$", line), line


# ---------- TF0-12: python -m poisson_trace ----------


def test_tf0_12_python_m_is_the_same_command(tmp_path: Path) -> None:
    env = dict(os.environ)
    for argv, code in (
        (["--version"], 0),
        (where_cs("--at", "20"), 0),
        (compare_tau2("1.3", "--json"), 0),
        (["where", "--bogus"], 2),
    ):
        module = run_module(argv, env=env, cwd=tmp_path)
        script = run_sub("trace", argv, env=env, cwd=tmp_path)
        assert module.code == script.code == code, module.text
        assert (module.out, module.err) == (script.out, script.err)
