"""TF0-14 and TF0-15: options may come before or after the verb, and abbreviated options are
refused (spec section 9.1, rule L15), in both commands.

Moving every option in front of the verb changes nothing a user can see: the same bytes on
stdout and stderr and the same exit code. An option's value is never taken for the verb, even
when it is spelt like one. An abbreviation (``--ev`` for ``--event``) is a wrong command line,
exit 2, where the main command took it today."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import CS, CS_RECORD
from tf0_support import (
    Ran, chdir, changes_he, compare_tau2, deepeval_import, fix_check_tau2, trace, trace_import, where_cs,
)

# Each command split into its verb and positionals, and its options with their values.
SPLIT = {
    "where": (["where", CS_RECORD], ["--store", str(CS), "--event", "unresolved", "--event", "max_turns", "--at", "20", "--by", "kind"]),
    "compare": (compare_tau2("1.5")[:3], compare_tau2("1.5", "--at", "10")[3:]),
    "fix-check": (fix_check_tau2()[:3], fix_check_tau2("--top", "3")[3:]),
    "changes": (changes_he()[:3], changes_he("--json")[3:]),
}


def _same(a: Ran, b: Ran) -> None:
    assert (a.code, a.out, a.err) == (b.code, b.out, b.err), b.text


@pytest.mark.parametrize("verb", SPLIT)
def test_tf0_14_options_before_the_verb_read_as_after_it(verb: str) -> None:
    head, options = SPLIT[verb]
    after = trace([*head, *options])
    assert after.code == 0, after.text
    _same(after, trace([*options, *head]))
    middle = len(options) // 2 - len(options) // 2 % 2
    _same(after, trace([*options[:middle], head[0], *options[middle:], *head[1:]]))


def test_tf0_14_a_value_spelt_like_a_verb_is_a_value() -> None:
    """``--event compare`` before the verb: ``compare`` is the event asked for, which the run
    does not carry (a refusal), not the verb (which would leave a run missing)."""
    result = trace(["--event", "compare", "where", CS_RECORD, "--store", str(CS)])
    assert result.code == 1 and result.out == "", result.text
    assert "compare" in result.err
    real = trace(["--event", "unresolved", "where", CS_RECORD, "--store", str(CS)])
    assert real.code == 0, real.text


@pytest.mark.parametrize("flag", ["--json", "--debug"])
def test_tf0_14_a_switch_before_the_verb_is_the_same_switch(flag: str) -> None:
    after = trace([*where_cs(), flag])
    assert after.code == 0, after.text
    _same(after, trace([flag, *where_cs()]))


def test_tf0_14_import_options_before_the_tool_read_as_after_it(tmp_path: Path) -> None:
    argv = deepeval_import("store", "v1", "a", "--json")
    tool, rest = argv[:2], argv[2:]
    (tmp_path / "after").mkdir()
    (tmp_path / "before").mkdir()
    with chdir(tmp_path / "after"):
        after = trace_import([*tool, *rest])
    with chdir(tmp_path / "before"):
        before = trace_import([*rest, *tool])
    assert after.code == 0, after.text
    _same(after, before)


@pytest.mark.parametrize(
    "argv",
    [
        ["where", CS_RECORD, "--store", str(CS), "--ev", "unresolved"],
        ["where", CS_RECORD, "--sto", str(CS), "--event", "unresolved"],
        [*where_cs(), "--js"],
        [*compare_tau2("1.5")[:-2], "--max-mde", "1.5"],
        [*fix_check_tau2()[:-2], "--max", "0.20"],
        ["--deb", *where_cs()],
        ["--vers"],
    ],
    ids=["--ev", "--sto", "--js", "compare --max-mde", "fix-check --max", "--deb", "--vers"],
)
def test_tf0_15_an_abbreviated_option_is_refused(argv: list[str]) -> None:
    result = trace(argv)
    assert result.code == 2 and result.out == "", result.text
    assert result.err.startswith("error: ")


def test_tf0_15_an_abbreviated_import_option_is_refused(tmp_path: Path) -> None:
    argv = deepeval_import(tmp_path / "store", "v1")
    argv[argv.index("--metric")] = "--met"
    result = trace_import(argv)
    assert result.code == 2 and result.out == "", result.text
    assert not (tmp_path / "store").exists()
