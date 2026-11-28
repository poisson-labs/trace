"""A value on a threshold is decided by the written rule, the same way on every platform.

The thresholds are values of the golden table (``ties`` in ``tests/fixtures/portable/golden.json``),
which holds the same bits on macOS and on Linux, so these assertions are the same on both. Each
case also checks that the command gives exactly the golden value, so the threshold is the value the
verdict reads:

- fix-check is *different* only when its exact test's p is below ``--alpha``: at
  ``--alpha`` equal to the p, written as its shortest repr, it is not *different*; at the next
  float above, it is;
- a reliable range decides *no significant difference* when it lies inside plus or minus
  ``--max-mde``, the ends included: at ``--max-mde`` equal to the larger of ``-lo`` and ``hi`` it
  does; at the next float below, the verdict is *too small to tell*;
- compare decides *no significant difference* by its detection limit when the limit is at or
  under ``--max-mde-hr``: at the limit itself it does; at the next float below, *too small to tell*;
- the range excludes zero only when its low end is above zero or its high end below it, so an
  end exactly at zero, of either sign, includes zero; and it lies inside ``±m`` with the ends
  included.

Every verdict is a printed result, so every one of these runs exits 0.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from fixcheck_support import pair_store
from look_support import chdir, trace
from portable_support import TIE_P_TABLE, TIE_RANGE_TABLE, compare_document, compare_store, golden


def _ties() -> dict[str, Any]:
    ties: dict[str, Any] = golden()["ties"]
    return ties


def _fix_check(store: Path, *extra: str) -> tuple[int, dict[str, Any]]:
    with chdir(store.parent):
        ran = trace(["fix-check", "old", "new", "--store", store.name, "--event", "fail", "--inputs", "all", "--json", *extra])
    return ran.code, json.loads(ran.out)


def test_fix_check_is_different_only_when_p_is_below_alpha(tmp_path: Path) -> None:
    p = float.fromhex(_ties()["fix-check p"])
    store = pair_store(tmp_path / "store", TIE_P_TABLE)
    code, doc = _fix_check(store, "--max-mde", "0.2", "--alpha", repr(p))
    assert (code, doc["test"]["p"]) == (0, p), "the command's p is the golden one"
    assert doc["difference"]["points"] != 0
    assert doc["verdict"] != "different", (repr(p), doc["verdict"], doc["sentence"])
    above = math.nextafter(p, 1.0)
    code, doc = _fix_check(store, "--max-mde", "0.2", "--alpha", repr(above))
    assert (code, doc["verdict"]) == (0, "different"), (repr(above), doc["sentence"])


def test_a_reliable_range_lies_inside_with_its_ends_included(tmp_path: Path) -> None:
    lo, hi = (float.fromhex(v) for v in _ties()["fix-check range"])
    store = pair_store(tmp_path / "store", TIE_RANGE_TABLE)
    edge = max(-lo, hi)
    code, doc = _fix_check(store, "--max-mde", repr(edge))
    assert code == 0
    assert (doc["difference"]["lo"], doc["difference"]["hi"]) == (lo, hi), "the command's range is the golden one"
    assert doc["test"]["p"] >= 0.05
    # the drop limit is wider than the range's edge, so only the range can pass the size asked
    assert doc["limits"]["drop"] > edge
    assert doc["verdict"] == "no significant difference", doc["sentence"]
    below = math.nextafter(edge, 0.0)
    code, doc = _fix_check(store, "--max-mde", repr(below))
    assert (code, doc["verdict"]) == (0, "too small to tell"), doc["sentence"]


def test_compare_passes_its_limit_at_the_limit_itself(tmp_path: Path) -> None:
    mde = float.fromhex(_ties()["compare mde"])
    work = compare_store(tmp_path)
    code, doc = compare_document(work, "--max-mde-hr", repr(mde))
    assert (code, doc["comparison"]["mde_hazard_ratio"]) == (0, mde), "the command's limit is the golden one"
    assert doc["comparison"]["p"] >= doc["comparison"]["alpha"]
    assert doc["verdict"] == "no significant difference", doc["sentence"]
    below = math.nextafter(mde, 0.0)
    code, doc = compare_document(work, "--max-mde-hr", repr(below))
    assert (code, doc["verdict"]) == (0, "too small to tell"), doc["sentence"]


def test_an_end_at_zero_includes_zero_and_the_ends_of_the_bound_are_inside() -> None:
    from poisson_trace.paired import excludes_zero, lies_inside

    assert excludes_zero(0.0, 0.1) is False
    assert excludes_zero(-0.1, 0.0) is False
    assert excludes_zero(-0.0, 0.1) is False
    assert excludes_zero(-0.1, -0.0) is False
    assert excludes_zero(5e-324, 0.1) is True
    assert excludes_zero(-0.1, -5e-324) is True
    lo, hi = (float.fromhex(v) for v in _ties()["fix-check range"])
    for m in (0.1, 0.2, max(-lo, hi)):
        assert lies_inside(-m, m, m) is True
        assert lies_inside(-math.nextafter(m, math.inf), m, m) is False
        assert lies_inside(-m, math.nextafter(m, math.inf), m) is False
