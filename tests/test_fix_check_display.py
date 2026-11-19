"""TR71 and TR72: the two display fixes ruled for the 0.1.0 tag (2026-09-29, Integrations ruling
16). A p too small for a double prints as a bound, never as 0.00e+00; with one run per input per
version the consistency block says consistency cannot be measured, and prints no κ."""

from __future__ import annotations

import math
import re
from pathlib import Path

from conftest import Row, build_store, norm
from fixcheck_support import fix_check

# Every input failed once on the old version and did not fail once on the new one. The exact
# two-sided p is 2^(1-N), about 1.8e-331 at N = 1100: below the smallest positive double.
N = 1100


def _underflow(root: Path) -> None:
    build_store(root, "a", [Row({"input": i}, "fail", None) for i in range(N)])
    build_store(root, "b", [Row({"input": i}, "ok", None) for i in range(N)])


def _one_run_each(root: Path) -> None:
    """60 inputs, one run per input per version, outcomes mixed on both sides."""
    old = ["fail"] * 20 + ["fail"] * 10 + ["ok"] * 25 + ["ok"] * 5
    new = ["ok"] * 20 + ["fail"] * 10 + ["ok"] * 25 + ["fail"] * 5
    build_store(root, "a", [Row({"input": i}, o, None) for i, o in enumerate(old)])
    build_store(root, "b", [Row({"input": i}, o, None) for i, o in enumerate(new)])


def _block(text: str, heading: str) -> str:
    start = text.index(f"## {heading}")
    end = text.find("\n## ", start + 3)
    return text[start: end if end != -1 else len(text)]


def test_tr71_a_p_too_small_for_a_double_prints_as_a_bound(tmp_path: Path) -> None:
    _underflow(tmp_path)
    r = fix_check(tmp_path, "a", "b", ("fail",), "--inputs", "all", "--max-mde", "0.5")
    assert r.code == 0, r.text
    assert "0.00e+00" not in r.text
    line = next(line for line in r.out.splitlines() if line.startswith("new failures:"))
    found = re.search(r"\bp < ([0-9][0-9.]*(?:e[+-]?[0-9]+)?)", line)
    assert found is not None, line
    bound = float(found.group(1))
    assert 0.0 < bound <= 1e-300, bound
    assert math.log10(bound) >= (1 - N) * math.log10(2.0), bound
    verdict = next(line for line in r.out.splitlines() if line.startswith("**"))
    assert "different: the new version failed less on these inputs" in verdict
    assert f"p < {found.group(1)}" in verdict, verdict


def test_tr72_one_run_per_input_per_version_prints_no_kappa(tmp_path: Path) -> None:
    for i, build in enumerate((_one_run_each, _underflow)):
        root = tmp_path / f"s{i}"
        build(root)
        r = fix_check(root, "a", "b", ("fail",), "--inputs", "all", "--max-mde", "0.5")
        assert r.code == 0, r.text
        block = _block(r.out, "Consistency")
        assert "κ" not in block and "times the runs" not in block and "fails again" not in block, block
        text = norm(block).lower()
        assert "cannot" in text and "one run per" in text, block
        # ruled 2026-09-29 (Session A ruling 5): the JSON says the same, and keeps the p computed
        j = fix_check(root, "a", "b", ("fail",), "--inputs", "all", "--max-mde", "0.5", "--json")
        c = j.json()["consistency"]
        assert c["fails_again"] is None and c["kappa"] is None, c
        assert isinstance(j.json()["test"]["p"], float)
