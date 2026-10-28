"""TF0-2 and TF0-3: the exit codes a result and a wrong command line get (spec section 3.3, the
Tasks table kept to the letter). A result exits 0 whatever it says, *too small to tell* included;
a command line that is wrong exits 2 with one ``error:`` line and nothing on stdout, in both
commands. Refusals (1), unexpected failures (3) and Ctrl-C (130) are in test_tf0_errors.py; the
table itself, as docs/cli-look.md writes it, is in test_tf0_conformance.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import CS, CS_RECORD, TAU2, TAU2_A
from tf0_support import (
    Ran, compare_tau2, deepeval_import, fix_check_tau2_all, trace, trace_import, where_cs,
)

# ---------- TF0-2: a result exits 0, whatever it says ----------


@pytest.mark.parametrize(
    "argv",
    # ST2 (ruled 2026-10-20): tau2 on all inputs at 0.10 reads no significant difference; 0.075 does not
    [compare_tau2("1.3"), fix_check_tau2_all("0.075")],
    ids=["compare", "fix-check"],
)
def test_tf0_02_too_small_to_tell_exits_zero(argv: list[str]) -> None:
    md = trace(argv)
    js = trace([*argv, "--json"])
    data = js.json()
    verdict = data["comparison"]["verdict"] if argv[0] == "compare" else data["verdict"]
    assert verdict == "too small to tell", verdict
    assert (md.code, js.code) == (0, 0), md.text
    assert md.err == "" and js.err == ""


# ---------- TF0-3: the command line is wrong, exit 2 ----------


def _usage(result: Ran) -> None:
    assert result.code == 2, result.text
    assert result.out == "", result.out
    lines = result.lines()
    assert lines and lines[0].startswith("error: ") and all(line.startswith("  next: ") for line in lines[1:]), result.err


TRACE_USAGE = {
    "no verb": [],
    "an unknown verb": ["bogus", CS_RECORD, "--store", str(CS), "--event", "unresolved"],
    "a run missing": ["compare", TAU2_A, "--store", str(TAU2), "--event", "unsolved", "--max-mde-hr", "1.5"],
    "an unknown option": where_cs("--bogus"),
    "a value not among the choices": where_cs("--by", "wall"),
    "a value that is not an integer": where_cs("--boot", "many"),
    "a value that is not a number": fix_check_tau2_all("twenty"),
    "a word too many": [*where_cs(), "extra"],
}


@pytest.mark.parametrize("argv", TRACE_USAGE.values(), ids=TRACE_USAGE.keys())
def test_tf0_03_a_wrong_command_line_exits_two(argv: list[str]) -> None:
    _usage(trace(argv))


def _import_usage(store: Path) -> dict[str, list[str]]:
    full = deepeval_import(store, "v1")
    no_case = full[: full.index("--case")] + full[full.index("--case") + 2 :]
    bad_case = [*full[: full.index("--case")], "--case", "identifier", *full[full.index("--case") + 2 :]]
    no_file = [w for w in full if not w.endswith(".json.gz")]
    return {
        "no tool": [],
        "a flag missing": no_case,
        "a value not among the choices": bad_case,
        "no file": no_file,
        "an unknown option": [*full, "--bogus"],
    }


@pytest.mark.parametrize("case", ["no tool", "a flag missing", "a value not among the choices", "no file", "an unknown option"])
def test_tf0_03_a_wrong_import_command_line_exits_two(tmp_path: Path, case: str) -> None:
    store = tmp_path / "store"
    _usage(trace_import(_import_usage(store)[case]))
    assert not store.exists()
    # the control: the full command line imports
    assert trace_import(deepeval_import(store, "v1")).code == 0
