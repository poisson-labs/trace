"""The move check, ``tests/fixtures/portable/check_moves.py``, refuses every move a re-take of pins
must not make, and passes one that changes only floats, by less than the bound.

Each case is a synthetic old and new pair: a JSON document whose floats moved within
``max(1e-12 * |old|, 1e-13)`` passes; a renamed, added, removed or reordered key, a string, an
integer, a boolean, a null, a float past the bound, an integer written as a float, and a plain line
are each refused. An invocation hashed with its exit code and stderr moves only its JSON stdout's
floats. The pin stores are held the same way: only strings may move, and a moved exit code or label
is refused.
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
