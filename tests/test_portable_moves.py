"""The move check, ``tests/fixtures/portable/check_moves.py``, refuses every move a re-take of pins
must not make, and passes one that changes only floats, by less than the bound.

Each case is a synthetic old and new pair: a JSON document whose floats moved within
``max(1e-12 * |old|, 1e-13)`` passes; a renamed, added, removed or reordered key, a string, an
integer, a boolean, a null, a float past the bound, an integer written as a float, and a plain line
are each refused. An invocation hashed with its exit code and stderr moves only its JSON stdout's
floats. The pin stores are held the same way: only strings may move, and a moved exit code or label
is refused.

Rows that tie exactly on p may change places, into ``config_hash`` order: in a document, rows whose
new p are equal, each row still held to its own old one; in a plain text, the rows of a table that
print the same p. Rows whose p differ, tied rows out of ``config_hash`` order, a row that changed
besides its place, and a line outside a table's tied rows are each refused.
"""

from __future__ import annotations

import importlib.util
import json
from types import ModuleType

import pytest
from conftest import FIXTURES


def _check_moves() -> ModuleType:
    path = FIXTURES / "portable" / "check_moves.py"
    spec = importlib.util.spec_from_file_location("check_moves", path)
    assert spec and spec.loader, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OLD = {
    "schema": "poisson-trace.fix-check/2",
    "verdict": "too small to tell",
    "test": {"p": 0.8830726813465343, "observed_new": 12},
    "difference": {"points": -0.0225, "lo": -0.06044114322482627, "hi": 0.0142, "variance": None},
    "tiny": 3e-15,
    "flags": [True, False],
    "rows": [1.5, 2.0],
}


def _text(doc: object) -> str:
    return json.dumps(doc, indent=2) + "\n"


def _moved(**changes: object) -> dict[str, object]:
    doc = json.loads(json.dumps(OLD))
    for path, value in changes.items():
        *head, last = path.split("__")
        at = doc
        for key in head:
            at = at[key]
        at[last] = value
    return doc


def test_floats_within_the_bound_pass_and_the_largest_change_is_given() -> None:
    check = _check_moves()
    new = _moved(test__p=0.8830726813465342, difference__lo=-0.06044114322482634, tiny=3.05e-15, rows=[1.5, 2.0000000000001])
    largest = check.compare_texts(_text(OLD), _text(new))
    assert largest == pytest.approx(1.0000000000287557e-13, rel=1e-9)
    assert check.compare_texts(_text(OLD), _text(OLD)) == 0.0
    assert check.compare_texts("same plain report\n", "same plain report\n") == 0.0


@pytest.mark.parametrize(("label", "new_text"), [
    ("a key renamed", _text({("verdicts" if k == "verdict" else k): v for k, v in OLD.items()})),
    ("a key added", _text({**OLD, "added": 1})),
    ("a key removed", _text({k: v for k, v in OLD.items() if k != "tiny"})),
    ("keys reordered", _text(dict(reversed(list(OLD.items()))))),
    ("a string", _text(_moved(verdict="no significant difference"))),
    ("an integer", _text(_moved(test__observed_new=13))),
    ("a boolean", _text(_moved(flags=[True, True]))),
    ("a null", _text(_moved(difference__variance=0.0))),
    ("a float past the bound", _text(_moved(test__p=0.8830726813475343))),
    ("a small float past the absolute bound", _text(_moved(tiny=1.2e-13))),
    ("an integer written as a float", _text(_moved(test__observed_new=12.0))),
    ("a list that grew", _text(_moved(rows=[1.5, 2.0, 3.0]))),
])
def test_each_forbidden_change_to_a_document_is_refused(label: str, new_text: str) -> None:
    check = _check_moves()
    with pytest.raises(check.Refused):
        check.compare_texts(_text(OLD), new_text)


def test_a_plain_line_that_moves_is_refused() -> None:
    check = _check_moves()
    old = "too small to tell: the range, -6.0 to 1.4 points, does not lie inside ±20\nnext: run more\n"
    with pytest.raises(check.Refused, match="line 1"):
        check.compare_texts(old, old.replace("-6.0", "-6.1"))
    with pytest.raises(check.Refused):
        check.compare_texts(old, old + "one more line\n")
    with pytest.raises(check.Refused):
        check.compare_texts(_text(OLD), "not a document now\n")


def _run(code: int, doc: object, err: str) -> str:
    return f"{code}\n{_text(doc)}\n{err}"


def test_an_invocation_hashed_with_its_exit_code_and_stderr_moves_only_its_floats() -> None:
    """A pin that hashes ``f"{code}\\n{stdout}\\n{stderr}"``: the JSON stdout is held as a document,
    and the exit code and stderr byte for byte."""
    check = _check_moves()
    new = _moved(test__p=0.8830726813465342)
    assert check.compare_texts(_run(0, OLD, ""), _run(0, new, "")) == pytest.approx(1.1102230246251565e-16)
    assert check.compare_texts(_run(1, OLD, "warning: x\n"), _run(1, new, "warning: x\n")) > 0
    with pytest.raises(check.Refused, match="exit code"):
        check.compare_texts(_run(0, OLD, ""), _run(1, new, ""))
    with pytest.raises(check.Refused, match="stderr"):
        check.compare_texts(_run(0, OLD, "a\n"), _run(0, new, "b\n"))
    with pytest.raises(check.Refused):
        check.compare_texts(_run(0, OLD, ""), _run(0, _moved(test__p=0.8830726813475343), ""))
    with pytest.raises(check.Refused):
        check.compare_texts(_run(0, OLD, ""), _run(0, _moved(verdict="no significant difference"), ""))
    with pytest.raises(check.Refused):
        # a plain stdout gets no such reading
        check.compare_texts("0\np = 0.8830726813465343\n\n", "0\np = 0.8830726813465342\n\n")


def test_a_pin_store_may_move_only_its_strings() -> None:
    check = _check_moves()
    old = {"main": "98c7b96", "pins": {"a --json": [0, "1" * 64, "2" * 64], "b": [1, "3" * 64, "4" * 64]}}
    new = {"main": "98c7b96", "pins": {"a --json": [0, "5" * 64, "2" * 64], "b": [1, "3" * 64, "4" * 64]}}
    moves = check.storage_moves("x/main-pins.json", json.dumps(old), json.dumps(new))
    assert moves == [("x/main-pins.json:/pins/a --json/1", "1" * 64, "5" * 64)]
    for bad in (
        {**new, "pins": {**new["pins"], "a --json": [2, "5" * 64, "2" * 64]}},
        {**new, "pins": {"b": new["pins"]["b"], "a --json": new["pins"]["a --json"]}},
        {**new, "pins": {**new["pins"], "c": [0, "6" * 64, "7" * 64]}},
    ):
        with pytest.raises(check.Refused):
            check.storage_moves("x/main-pins.json", json.dumps(old), json.dumps(bad))


def test_a_test_module_may_move_only_its_pinned_strings() -> None:
    check = _check_moves()
    first, second = "1" * 64, "2" * 64
    old = f'PINNED = {{"case": ("argv", "{first}", "{second}")}}\n\ndef test_it():\n    assert run() == PINNED["case"]\n'
    new = old.replace("1" * 64, "9" * 64)
    assert check.storage_moves("tests/test_x.py", old, new) == [("tests/test_x.py:string 2", "1" * 64, "9" * 64)]
    with pytest.raises(check.Refused):
        check.storage_moves("tests/test_x.py", old, new.replace("assert run() ==", "assert run() !="))


TIED_OLD = {
    "verdict": "different",
    "rows": [
        {"config_hash": "b2", "change": 0.125, "p": 0.11319281811085088, "flag": None},
        {"config_hash": "a1", "change": -0.125, "p": 0.1131928181108509, "flag": None},
        {"config_hash": "c3", "change": 0.125, "p": 0.1131928181108509, "flag": None},
        {"config_hash": "d4", "change": 0.0, "p": 1.0, "flag": None},
    ],
}


def _rows(order: str, **p: float) -> dict[str, object]:
    by_tag = {row["config_hash"]: dict(row) for row in TIED_OLD["rows"]}  # type: ignore[index]
    for tag, value in p.items():
        by_tag[tag]["p"] = value
    return {**TIED_OLD, "rows": [by_tag[tag] for tag in order.split()]}


def test_rows_that_tie_on_p_may_change_places_into_config_hash_order() -> None:
    check = _check_moves()
    exact = 0.1131928181108509
    new = _rows("a1 b2 c3 d4", b2=exact)
    assert check.compare_texts(_text(TIED_OLD), _text(new)) == pytest.approx(abs(exact - 0.11319281811085088))
    # the same in an invocation hashed with its exit code and stderr
    assert check.compare_texts(_run(0, TIED_OLD, ""), _run(0, new, "")) > 0


@pytest.mark.parametrize(("label", "new"), [
    ("rows whose p differ", _rows("d4 b2 a1 c3")),
    ("tied rows out of config_hash order", _rows("c3 a1 b2 d4", b2=0.1131928181108509)),
    ("a tie only in the old document", _rows("a1 b2 c3 d4", b2=0.11319281811085085)),
    ("a row that changed besides its place", {**_rows("a1 b2 c3 d4", b2=0.1131928181108509),
                                              "rows": [*_rows("a1 b2 c3", b2=0.1131928181108509)["rows"],  # type: ignore[misc]
                                                       {"config_hash": "d4", "change": 0.0, "p": 1.0, "flag": "failed more in B"}]}),
    ("a row replaced", {**TIED_OLD, "rows": [*TIED_OLD["rows"][:3], {"config_hash": "e5", "change": 0.0, "p": 1.0, "flag": None}]}),  # type: ignore[index]
])
def test_every_other_change_of_order_is_refused(label: str, new: dict[str, object]) -> None:
    check = _check_moves()
    with pytest.raises(check.Refused):
        check.compare_texts(_text(TIED_OLD), _text(new))


TABLE = """**different: the new version failed more on these inputs**

## Inputs that changed

| input | old failed/runs | new failed/runs | change | p | q | flag |
|---|---|---|---|---|---|---|
| {"task_id":"HumanEval/129"} | 12/32 | 32/32 | +62.5 points | 2.30e-08 | 7.55e-06 | failed more in new |
| {"task_id":"HumanEval/91"} | 28/32 | 32/32 | +12.5 points | 0.113 | 1.000 | – |
| {"task_id":"HumanEval/64"} | 4/32 | 0/32 | -12.5 points | 0.113 | 1.000 | – |
| {"task_id":"HumanEval/22"} | 0/32 | 4/32 | +12.5 points | 0.113 | 1.000 | – |
| {"task_id":"HumanEval/75"} | 19/32 | 12/32 | -21.9 points | 0.133 | 1.000 | – |

next: nothing
"""


def _swapped(text: str, first: str, second: str) -> str:
    lines = text.split("\n")
    i = next(k for k, line in enumerate(lines) if first in line)
    j = next(k for k, line in enumerate(lines) if second in line)
    lines[i], lines[j] = lines[j], lines[i]
    return "\n".join(lines)


def test_rows_of_a_plain_table_that_print_the_same_p_may_change_places() -> None:
    check = _check_moves()
    moved = _swapped(TABLE, "HumanEval/91", "HumanEval/64")
    assert check.compare_texts(TABLE, moved) == 0.0
    assert check.compare_texts(TABLE, _swapped(moved, "HumanEval/91", "HumanEval/22")) == 0.0
    assert check.compare_texts(f"0\n{TABLE}\n", f"0\n{moved}\n") == 0.0


def test_every_other_moved_line_of_a_plain_text_is_refused() -> None:
    check = _check_moves()
    for new in (
        _swapped(TABLE, "HumanEval/22", "HumanEval/75"),  # the p printed differ
        _swapped(TABLE, "HumanEval/129", "HumanEval/91"),
        _swapped(TABLE, "**different", "## Inputs"),  # lines outside the table
        _swapped(TABLE, "HumanEval/91", "HumanEval/64").replace("+12.5 points", "+12.6 points", 1),
        TABLE.replace("| 0.113 | 1.000 | – |\n| {\"task_id\":\"HumanEval/64\"}", "| 0.113 | 1.000 | – |\n| {\"task_id\":\"HumanEval/65\"}"),
    ):
        assert new != TABLE
        with pytest.raises(check.Refused, match="line"):
            check.compare_texts(TABLE, new)
